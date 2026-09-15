"""Tier 5: a helical and a herringbone gear built end to end, through the tool's own code.

Like :mod:`p5_end_to_end`, nothing here calls COM raw: each gear is planned by
its :class:`GearKind` and built by :func:`swbuild.build` through the
:class:`swcom.Session` members the tier 2 probes settled. Three oracles:

* **the twin** — the same plan with the twisted sweep swapped for a straight
  cut of the same section. A section turned uniformly along a line encloses the
  volume it would straight (Cavalieri), so the two parts weigh the same;
* **the hand** — the same plan with the pattern left out: one tooth space, cut
  from a round blank, pulls the part's centre of mass away from the side the
  space turned to, so the sign of its y says which way the helix went;
* **the equations** — the helix angle and face width changed through
  :func:`swbuild.update_variables`, after which the part weighs what a fresh
  twin of the new gear weighs.
"""

from __future__ import annotations

import math
import os
from dataclasses import replace
from typing import Any, Dict, List

from .. import findings, swbuild
from ..gears import KINDS
from ..gears.base import BuildPlan, CircularPattern, Cut, LinkDimension, SaveAs, SweepCut
from ..spec import HAND_LEFT, HAND_RIGHT, KIND_HELICAL, KIND_HERRINGBONE, GearSpec
from . import scaffold as sc
from .harness import Px, probe

COMMON = ("Gear Axis", "Blank Sketch", "Blank", "Tooth Space Sketch", "Path Sketch", "Tooth Space", "Teeth",
          "Bore Sketch", "Bore")
NAMES = {KIND_HELICAL: COMMON + ("Profile Plane",), KIND_HERRINGBONE: COMMON + ("Mid Plane", "Mirror")}
SKETCHES = ("Blank Sketch", "Tooth Space Sketch", "Path Sketch", "Bore Sketch")
HELIX = {KIND_HELICAL: "20", KIND_HERRINGBONE: "30"}
TWIN_TOLERANCE = 5e-4     # relative; twisted sweeps are spline surfaces


def twin(plan: BuildPlan, path: str) -> BuildPlan:
    """The plan with its twisted sweep cut straight, saved elsewhere."""
    ops = []
    for op in plan.ops:
        if isinstance(op, SweepCut):
            ops.append(Cut(op.id, op.profile, op.name))
        elif isinstance(op, LinkDimension) and op.dimension.startswith("Twist@"):
            continue
        elif isinstance(op, SaveAs):
            ops.append(SaveAs(path))
        else:
            ops.append(op)
    return replace(plan, ops=tuple(ops), path=path)


def single_space(plan: BuildPlan, path: str) -> BuildPlan:
    """The plan without its pattern: one tooth space, saved elsewhere."""
    ops = []
    for op in plan.ops:
        if isinstance(op, CircularPattern) or (isinstance(op, LinkDimension) and op.dimension.startswith("Count@")):
            continue
        ops.append(SaveAs(path) if isinstance(op, SaveAs) else op)
    return replace(plan, ops=tuple(ops), path=path)


def expected_centre_y_sign(kind: str, hand: str) -> int:
    """Which side of y the part's centre of mass sits on with one space cut.

    A right-hand section turns counter-clockwise about +Z as z increases from
    the section drawn. A helical gear's section is ahead of the Front plane, so
    through the part it has turned counter-clockwise, toward +y, and the
    removed material's centre is at +y. A herringbone's section is the apex:
    the half toward the Front plane turned the other way, and the mirrored half
    matches it, so the removed material is at -y. The part's centre is on the
    other side from what was removed.
    """
    hand_sign = 1 if hand == HAND_RIGHT else -1
    removed = hand_sign if kind == KIND_HELICAL else -hand_sign
    return -removed


class _Builds:
    """Every document this probe builds, so all of them are closed at the end."""

    def __init__(self, px: Px) -> None:
        self.px = px
        self.titles: List[str] = []

    def build(self, plan: BuildPlan) -> swbuild.BuildResult:
        before = sc.open_titles(self.px)
        try:
            return swbuild.build(self.px.session, plan)
        finally:
            made = [t for t in sc.open_titles(self.px) if t not in before]
            self.titles.extend(made)
            self.px.shared.setdefault("created", []).extend(made)

    def close(self) -> None:
        if self.px.options.get("keep"):
            return
        for title in reversed(self.titles):
            try:
                self.px.session.close_document(title)
            except Exception as exc:  # noqa: BLE001 - one that will not close must not hide the rest
                self.px.note(f"CLEANUP could not close {title}: {exc}")


def _require_built(px: Px, label: str, result: swbuild.BuildResult, path: str) -> None:
    px.fact(f"{label}_log", result.log_lines())
    for line in result.log_lines():
        px.note(f"{label}: {line}")
    px.require(result.ok, f"{label}: the build reports no failures", result.failures)
    px.require(result.saved.lower() == path.lower() and os.path.isfile(path), f"{label}: saved where asked")


def _run_kind(px: Px, builds: _Builds, kind: str, folder: str) -> None:
    gear = KINDS[kind]
    recipe = px.options.get("flank") or findings.DEFAULT_RECIPE
    spec = GearSpec(kind=kind, module="2", teeth="13", helix_angle=HELIX[kind], face_width="10", bore="8",
                    recipe=recipe, hand=HAND_RIGHT)
    derived = gear.derive(spec)
    stem = f"Probe {kind} m2 N13"
    path = os.path.join(folder, f"{stem}.SLDPRT")
    px.require(not os.path.exists(path), f"{path} does not exist yet")
    plan = gear.plan(spec, derived, recipe, "", path)
    px.require(plan.check() == [], f"{kind}: the plan is sound", plan.check())
    session = px.session

    result = builds.build(plan)
    _require_built(px, kind, result, path)
    px.fact(f"{kind}_checks", result.checks)
    px.check(not result.checks, f"{kind}: every sketch is fully defined", result.checks)
    names = [f.name for f in session.features()]
    px.fact(f"{kind}_features", names)
    missing = [n for n in NAMES[kind] if n not in names]
    px.check(not missing, f"{kind}: every feature the tool names is in the tree", missing)
    volume = session.volume_mm3()
    bodies = session.solid_body_count()
    px.check(bodies == 1, f"{kind}: one solid body ({bodies})")

    twin_path = os.path.join(folder, f"{stem} twin.SLDPRT")
    twin_result = builds.build(twin(plan, twin_path))
    _require_built(px, f"{kind} twin", twin_result, twin_path)
    twin_volume = session.volume_mm3()
    px.fact(f"{kind}_volumes_mm3", {"part": volume, "twin": twin_volume})
    px.check(abs(volume - twin_volume) <= TWIN_TOLERANCE * twin_volume,
             f"{kind}: {volume:.3f} mm³ weighs what its straight twin does ({twin_volume:.3f})")

    hands = (HAND_RIGHT, HAND_LEFT) if kind == KIND_HELICAL else (HAND_RIGHT,)
    for hand in hands:
        one = spec.with_values(hand=hand)
        one_path = os.path.join(folder, f"{stem} one space {hand}.SLDPRT")
        one_result = builds.build(single_space(gear.plan(one, gear.derive(one), recipe, "", one_path), one_path))
        _require_built(px, f"{kind} one space {hand}", one_result, one_path)
        centre = session.center_of_mass_mm()
        want = expected_centre_y_sign(kind, hand)
        px.fact(f"{kind}_{hand}_one_space_centre_mm", centre)
        px.check(abs(centre[1]) > 1e-3 and math.copysign(1, centre[1]) == want,
                 f"{kind} {hand}: one space pulls the centre of mass to {'+' if want > 0 else '-'}y: {centre}")

    # Saved, the part's title is its file name, not the PartN it was built as.
    session.activate(os.path.basename(path))
    wanted = spec.with_values(helix_angle=str(int(HELIX[kind]) + 5), face_width="12")
    changed = gear.derive(wanted)
    update = swbuild.update_variables(session, gear.variables(wanted, changed), path)
    px.fact(f"{kind}_update_changed", update.changed)
    px.require(update.ok, f"{kind}: update_variables reports no failures", update.failures)
    px.check(sorted(update.changed) == ["Face Width", "Helix Angle"], f"{kind}: exactly the two typed values changed")
    px.check(update.rebuilt, f"{kind}: the update rebuilt once")
    after = session.volume_mm3()
    values = session.equation_values()
    expected = changed.values()
    wrong = {k: (values.get(k), v) for k, v in expected.items() if abs(values.get(k, math.inf) - v) > 1e-6 * max(1, abs(v))}
    px.check(not wrong, f"{kind}: every global follows the change", wrong)
    statuses = {name: session.sketch_status(name) for name in SKETCHES}
    px.fact(f"{kind}_sketch_statuses_after", statuses)
    px.check(all(v == findings.FULLY_CONSTRAINED for v in statuses.values()),
             f"{kind}: every sketch is still fully defined after the change", statuses)

    twin2_path = os.path.join(folder, f"{stem} twin after.SLDPRT")
    twin2 = builds.build(twin(gear.plan(wanted, changed, recipe, "", twin2_path), twin2_path))
    _require_built(px, f"{kind} twin after", twin2, twin2_path)
    twin2_volume = session.volume_mm3()
    px.fact(f"{kind}_volumes_after_mm3", {"part": after, "twin": twin2_volume})
    px.check(abs(after - twin2_volume) <= TWIN_TOLERANCE * twin2_volume,
             f"{kind}: after the change it weighs what a fresh twin does: {after:.3f} vs {twin2_volume:.3f}")


@probe("helical_end_to_end", tier=5,
       needs=("sweep_cut_ends", "sweep_twist_link", "mirror_body_merge", "path_sketch_relations", "pattern_count_link",
              "save_as", "curve_fixed_rebuild", "equation_inverse_trig"),
       members=("swbuild.build", "swbuild.update_variables", "Session.ref_plane", "Session.sweep_cut",
                "Session.mirror_body"))
def helical_end_to_end(px: Px) -> None:
    """Build a right-hand helical and a herringbone gear, weigh them against straight twins, and change them."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    builds = _Builds(px)
    try:
        for kind in (KIND_HELICAL, KIND_HERRINGBONE):
            _run_kind(px, builds, kind, folder)
    finally:
        builds.close()
