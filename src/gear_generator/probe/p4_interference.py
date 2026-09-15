"""Tier 4: interference detection in an assembly, with overlap volume as the oracle.

A gear pair's teeth either mesh or run into each other, and the assembly can
say which. Two r 20 mm cylinders 10 mm thick are inserted 30 mm apart, where
they overlap in a lens of known area, and 50 mm apart, where they do not. The
check is believed only if it finds exactly the lens in the first and nothing in
the second.

Late binding reaches some zero-argument members as property gets and some as
methods (``FixComponent`` came back as a bound method), so each such member is
read and, if what comes back is a method, called; which it was is recorded.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p4_assembly import _part_with_axis, _translation_mm
from .p2_solid import BLANK_R, BLANK_W

OVERLAP_AT = 30.0   # mm between the two cylinders' axes
APART_AT = 50.0

OPTIONS = (
    ("TreatCoincidenceAsInterference", False),
    ("TreatSubAssembliesAsComponents", True),
    ("IncludeMultibodyPartInterferences", True),
    ("MakeInterferingPartsTransparent", False),
    ("CreateFastenersFolder", False),
    ("IgnoreHiddenBodies", True),
    ("ShowIgnoredInterferences", False),
    ("UseTransform", False),
)


def lens_mm3(radius: float, distance: float, width: float) -> float:
    """Where two equal cylinders overlap: the lens of two circles, times the width."""
    if distance >= 2.0 * radius:
        return 0.0
    area = 2.0 * radius * radius * math.acos(distance / (2.0 * radius)) \
        - distance / 2.0 * math.sqrt(4.0 * radius * radius - distance * distance)
    return area * width


def member(obj: Any, name: str) -> Tuple[Any, str]:
    """A zero-argument member, read, and called if what comes back is a method."""
    value = call(obj, name)
    if type(value).__name__ in ("method", "function"):
        return value(), "method"
    return value, "property"


def interferences(px: Px, asm: Any, label: str) -> Dict[str, Any]:
    """Run the interference check on the whole assembly. Returns what it found, as plain data."""
    got, manager = px.attempt(f"{label}: IAssemblyDoc.InterferenceDetectionManager",
                              lambda: call(asm, "InterferenceDetectionManager"))
    if not got or manager is None:
        raise Require("The assembly has no interference detection manager.")
    for name, value in OPTIONS:
        px.attempt(f"{label}: set {name} = {value}", lambda n=name, v=value: setattr(manager, n, v))
    got, counted = px.attempt(f"{label}: GetInterferenceCount", lambda: member(manager, "GetInterferenceCount"))
    count, count_form = (int(counted[0]), counted[1]) if got else (None, None)
    got, listed = px.attempt(f"{label}: GetInterferences", lambda: member(manager, "GetInterferences"))
    items, list_form = (list(listed[0] or ()), listed[1]) if got else ([], None)
    volumes: List[float] = []
    for item in items:
        ok, value = px.attempt(f"{label}: IInterference.Volume", lambda i=item: member(i, "Volume"))
        if ok:
            volumes.append(float(value[0]) * 1e9)
    got, done = px.attempt(f"{label}: Done", lambda: member(manager, "Done"))
    return {"count": count, "count_form": count_form, "listed": len(items), "list_form": list_form,
            "volumes_mm3": volumes, "done_form": done[1] if got else None}


def _assembly_with(px: Px, path_a: str, path_b: str, x_mm: float) -> Any:
    asm = sc.new_document(px, sc.SW_DOC_ASSEMBLY)
    ext = sc.extension(asm)
    if int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, 0)) != sc.SW_MM:
        call(ext, "SetUserPreferenceInteger", sc.SW_UNIT_SYSTEM, 0, sc.SW_UNIT_SYSTEM_MMGS)
    first = call(asm, "AddComponent5", path_a, 0, "", False, "", 0.0, 0.0, 0.0)
    second = call(asm, "AddComponent5", path_b, 0, "", False, "", x_mm / sc.MM, 0.0, 0.0)
    if first is None or second is None:
        raise Require("AddComponent5 did not insert both cylinders.")
    call(asm, "ForceRebuild3", False)
    where = _translation_mm(second)
    if abs(where[0] - x_mm) > 1e-6:
        raise Require(f"The second cylinder is at {where}, not {x_mm} mm along X.")
    return asm


@probe("interference", needs=("assembly_components_and_mates",), tier=4,
       members=("IAssemblyDoc.InterferenceDetectionManager", "IInterferenceDetectionMgr.GetInterferenceCount",
                "IInterferenceDetectionMgr.GetInterferences", "IInterference.Volume", "IInterferenceDetectionMgr.Done"))
def interference(px: Px) -> None:
    """Two cylinders that overlap by a known lens, and the same two apart: the check must tell them apart."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder), "there is a scratch folder to save parts in")
    part_a, path_a = _part_with_axis(px, folder, "Probe Clash A")
    part_b, path_b = _part_with_axis(px, folder, "Probe Clash B")
    try:
        for label, at in (("overlap", OVERLAP_AT), ("apart", APART_AT)):
            asm = _assembly_with(px, path_a, path_b, at)
            try:
                found = interferences(px, asm, label)
                px.fact(f"interference_{label}", found)
                expected = lens_mm3(BLANK_R, at, BLANK_W)
                total = sum(found["volumes_mm3"])
                if expected:
                    px.check(found["count"] == 1 and found["listed"] == 1,
                             f"{label}: one interference is counted and listed ({found['count']}, {found['listed']})")
                    px.check(abs(total - expected) < 1e-3 * expected,
                             f"{label}: its volume is the lens, {total:.3f} mm³ (expected {expected:.3f})")
                else:
                    px.check(found["count"] == 0 and found["listed"] == 0,
                             f"{label}: nothing interferes ({found['count']}, {found['listed']})")
            finally:
                sc.close(px, asm)
        overlap = px.record.facts.get("interference_overlap") or {}
        px.fact("interference_route", {"count": overlap.get("count_form"), "list": overlap.get("list_form"),
                                       "done": overlap.get("done_form")})
    finally:
        for doc in (part_b, part_a):
            try:
                sc.close(px, doc)
            except Exception as exc:  # noqa: BLE001
                px.note(f"CLEANUP {exc}")
