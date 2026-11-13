"""Tier 4, extra: a gear mate between two axes, with a driven turn as the oracle.

A pair assembly that turns needs gear 1 free about its axis and a gear mate
that turns gear 2 with it. Two cylinders with a ``Gear Axis`` are inserted; the
first is unfixed and held on the assembly's own planes, with an angle mate
between its top plane and the assembly's that drives its turn; the second's axis
is held 60 mm away on the assembly's planes; and a gear mate joins the two axes
at 20 : 40. The drive is linked to a global and turned 30°, and the second
cylinder must turn 15° — the tooth ratio — or 60°, if the ratio's numerator goes
with the second selection. That is run with ``Flip`` off and on, and the turn's
direction each way round is what the build needs: an external pair turns
opposite ways, a pinion in a ring the same way.

No enum value is written from memory. ``swMateType_e`` is read from
``swconst.tlb`` beside ``sldworks.exe`` at run time, and the reader is believed
only once it has given back the three mate types :mod:`findings` already holds.

Written without SolidWorks; first run on SolidWorks 2026 (34.0.0) and 2024
(32.5.0) on 2026-11-13, where it passed unchanged. A failure here is a finding,
not a bug to route around.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

from .. import findings
from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p1_equations import adder
from .p4_assembly import ALIGN_CLOSEST, CENTRE, MATE_ANGLE, MATE_COINCIDENT, MATE_DISTANCE, _mate, \
    _mate_features, _part_with_axis, _select_in_component

TEETH_A, TEETH_B = 20, 40
DRIVE_FROM, DRIVE_TO = 10.0, 40.0     # degrees, the first cylinder's angle mate


def _turn_deg(component: Any) -> float:
    """How far a component is turned about Z, degrees, from its ``Transform2`` (rotation in columns)."""
    data = call(call(component, "Transform2"), "ArrayData")
    return math.degrees(math.atan2(float(data[1]), float(data[0])))


def _unwrap(delta: float) -> float:
    return (delta + 180.0) % 360.0 - 180.0


def _select_assembly_plane(asm: Any, index: int, append: bool) -> bool:
    return sc.select_plane(asm, index, append=append, mark=1)


def _run(px: Px, path_a: str, path_b: str, mate_gear: int, flip: bool) -> Optional[Dict[str, Any]]:
    """One assembly: both cylinders held, the gear mate with ``flip``, and the drive turned. Returns what turned."""
    label = f"flip {'on' if flip else 'off'}"
    asm = sc.new_document(px, sc.SW_DOC_ASSEMBLY)
    try:
        ext = sc.extension(asm)
        if int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, 0)) != sc.SW_MM:
            call(ext, "SetUserPreferenceInteger", sc.SW_UNIT_SYSTEM, 0, sc.SW_UNIT_SYSTEM_MMGS)
        first = call(asm, "AddComponent5", path_a, 0, "", False, "", 0.0, 0.0, 0.0)
        second = call(asm, "AddComponent5", path_b, 0, "", False, "", CENTRE / sc.MM, 0.0, 0.0)
        px.require(first is not None and second is not None, f"{label}: both cylinders are inserted")
        planes = [str(call(p, "Name")) for p in sc.planes(call(first, "GetModelDoc2"))]
        front, top, right = planes[0], planes[1], planes[2]

        call(asm, "ClearSelection2", True)
        px.require(bool(call(first, "Select4", False, sc.null(), False)), f"{label}: the first cylinder selects")
        got, _ = px.attempt(f"{label}: UnfixComponent() on the first cylinder", lambda: asm.UnfixComponent())
        call(asm, "ClearSelection2", True)
        px.require(got and not bool(call(first, "IsFixed")), f"{label}: the first cylinder floats after UnfixComponent")

        # The first cylinder on the assembly's own planes, free only to turn, and an angle that turns it.
        px.require(_select_in_component(px, asm, first, front, "PLANE", False) and _select_assembly_plane(asm, 1, True),
                   f"{label}: A's front and the assembly's front select")
        _mate(px, asm, f"{label}: A's front on the assembly's", MATE_COINCIDENT)
        for index, what in ((2, "top"), (3, "right")):
            px.require(_select_in_component(px, asm, first, "Gear Axis", "AXIS", False) and
                       _select_assembly_plane(asm, index, True), f"{label}: A's axis and the assembly's {what} select")
            _mate(px, asm, f"{label}: A's axis in the assembly's {what} plane", MATE_COINCIDENT)
        px.require(_select_in_component(px, asm, first, top, "PLANE", False) and _select_assembly_plane(asm, 2, True),
                   f"{label}: A's top and the assembly's top select")
        drive = _mate(px, asm, f"{label}: the drive angle", MATE_ANGLE, angle=math.radians(DRIVE_FROM))
        px.require(drive is not None, f"{label}: the drive angle mate is made")

        # The second cylinder's axis held on the assembly's planes, CENTRE mm off; its turn left free.
        px.require(_select_in_component(px, asm, second, front, "PLANE", False) and _select_assembly_plane(asm, 1, True),
                   f"{label}: B's front and the assembly's front select")
        _mate(px, asm, f"{label}: B's front on the assembly's", MATE_COINCIDENT)
        px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                   _select_assembly_plane(asm, 2, True), f"{label}: B's axis and the assembly's top select")
        _mate(px, asm, f"{label}: B's axis in the assembly's top plane", MATE_COINCIDENT)
        px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                   _select_assembly_plane(asm, 3, True), f"{label}: B's axis and the assembly's right select")
        _mate(px, asm, f"{label}: B's axis {CENTRE} mm from the assembly's right plane", MATE_DISTANCE,
              distance=CENTRE / sc.MM)

        # The gear mate: A's axis first, at TEETH_A : TEETH_B.
        px.require(_select_in_component(px, asm, first, "Gear Axis", "AXIS", False) and
                   _select_in_component(px, asm, second, "Gear Axis", "AXIS", True), f"{label}: the two axes select")
        before = [n for n, _ in _mate_features(asm)]
        got, result = px.attempt(
            f"{label}: AddMate5 gear {TEETH_A}:{TEETH_B}",
            lambda: call(asm, "AddMate5", mate_gear, ALIGN_CLOSEST, flip, 0.0, 0.0, 0.0, float(TEETH_A),
                         float(TEETH_B), 0.0, 0.0, 0.0, False, False, 0, sc.out_long()),
        )
        call(asm, "ClearSelection2", True)
        made = [(n, t) for n, t in _mate_features(asm) if n not in before]
        px.fact(f"gear_mate_made_{'flipped' if flip else 'plain'}", made)
        px.require(got and len(made) == 1, f"{label}: one gear mate appears under Mates")

        call(asm, "ForceRebuild3", False)
        a0, b0 = _turn_deg(first), _turn_deg(second)

        # Turn the drive through a global, the verified way to change a mate's value.
        feature = next((m for m in sc.top_features(asm) if sc.type_name(m) == "MateGroup"), None)
        px.require(feature is not None, f"{label}: the Mates folder is found")
        angle_mate = None
        child = call(feature, "GetFirstSubFeature")
        while child is not None:
            if str(call(child, "Name")) == drive:
                angle_mate = child
            child = call(child, "GetNextSubFeature")
        px.require(angle_mate is not None, f"{label}: the drive mate is found")
        angle_mate.Name = "Drive"
        match = [d for d in sc.dimensions_of(angle_mate)
                 if abs(float(call(d, "SystemValue")) - math.radians(DRIVE_FROM)) < 1e-9]
        px.require(len(match) == 1, f"{label}: the drive's dimension is found by value")
        eqm = call(asm, "GetEquationMgr")
        add = adder(px, eqm)
        index = add(f'"Drive"= {DRIVE_FROM:g}')
        px.require(index >= 0 and add(f'"{call(match[0], "Name")}@Drive"= "Drive"') >= 0,
                   f"{label}: the drive is linked to a global")
        sc.put_indexed(eqm, "Equation", index, f'"Drive"= {DRIVE_TO:g}')
        call(asm, "ForceRebuild3", False)
        a1, b1 = _turn_deg(first), _turn_deg(second)
        turned = {"a": _unwrap(a1 - a0), "b": _unwrap(b1 - b0), "a_from": a0, "b_from": b0}
        px.fact(f"gear_mate_turn_{'flipped' if flip else 'plain'}", turned)
        return turned
    finally:
        try:
            sc.close(px, asm)
        except Exception as exc:  # noqa: BLE001
            px.note(f"CLEANUP {exc}")


@probe("gear_mate", needs=("assembly_distance_link",), tier=4, extra=True,
       members=("ISldWorks.GetExecutablePath", "swconst.swMateType_e.swMateGEAR", "IAssemblyDoc.UnfixComponent",
                "IAssemblyDoc.AddMate5 gear"))
def gear_mate(px: Px) -> None:
    """A gear mate between two axes turns the second by the tooth ratio, and Flip turns it the other way."""
    mates = sc.swconst(px, "swMateType_e")
    known = {"swMateCOINCIDENT": findings.MATE_COINCIDENT, "swMateDISTANCE": findings.MATE_DISTANCE,
             "swMateANGLE": findings.MATE_ANGLE}
    read = {name: mates.get(name) for name in known}
    px.fact("swconst_reader_positive_control", read)
    px.require(read == known, "the swconst reader gives back the three mate types already verified")
    mate_gear = mates.get("swMateGEAR")
    px.require(mate_gear is not None, "swMateType_e has swMateGEAR")
    px.fact("mate_gear_type", mate_gear)

    folder = sc.env_scratch_folder(px)
    px.require(bool(folder), "there is a scratch folder to save parts in")
    part_a, path_a = _part_with_axis(px, folder, "Probe Gear Mate A")
    part_b, path_b = _part_with_axis(px, folder, "Probe Gear Mate B")
    try:
        runs: List[Tuple[bool, Dict[str, Any]]] = []
        for flip in (False, True):
            turned = _run(px, path_a, path_b, mate_gear, flip)
            if turned is not None:
                runs.append((flip, turned))
        px.require(len(runs) == 2, "both assemblies turned")
        expected = DRIVE_TO - DRIVE_FROM
        orders = []
        for flip, turned in runs:
            px.check(abs(abs(turned["a"]) - expected) < 1e-6, f"flip {flip}: the drive turned A {expected}°: {turned}")
            ratio = abs(turned["b"]) / abs(turned["a"]) if turned["a"] else math.nan
            if abs(ratio - TEETH_A / TEETH_B) < 1e-6:
                orders.append(True)
            elif abs(ratio - TEETH_B / TEETH_A) < 1e-6:
                orders.append(False)
            else:
                px.check(False, f"flip {flip}: B turned {ratio:.6f} of A, neither {TEETH_A}:{TEETH_B} nor the inverse")
        px.require(len(orders) == 2 and orders[0] == orders[1], "the ratio went the same way both times")
        px.fact("gear_mate_numerator_first", orders[0])
        opposite = {flip: (turned["a"] > 0) != (turned["b"] > 0) for flip, turned in runs}
        px.fact("gear_mate_opposite_by_flip", {str(k): v for k, v in opposite.items()})
        px.require(opposite[False] != opposite[True], "Flip turns B the other way")
        px.fact("gear_mate_external_flip", next(flip for flip, turns in opposite.items() if turns))
    finally:
        for doc in (part_b, part_a):
            try:
                sc.close(px, doc)
            except Exception as exc:  # noqa: BLE001
                px.note(f"CLEANUP {exc}")
