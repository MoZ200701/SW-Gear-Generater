"""Tier 5: a ring and the pinion inside it, built end to end through the tool's own code.

As :mod:`p5_helical`, nothing here calls COM raw: both parts and the assembly
are planned by the gear kinds and :func:`pair.assembly_plan`, and built by
:func:`swbuild.build_pair`, which checks the assembly for interference. For a
spur pair and a helical one (β 15°, both right-hand):

* **interference** — the pair as built touches nowhere; with the pinion's mesh
  angle moved half a pitch its teeth run into the ring's, which is what shows
  the check could have failed;
* **the volume** — a spur ring weighs its annular blank less N times what one
  tooth space removes, measured on the same plan with its pattern left out; a
  helical ring weighs what its straight twin does (Cavalieri);
* **the equations** — the ring's teeth changed 60 → 64 through
  :func:`swbuild.update_variables`, after which it weighs what a fresh build of
  the 64-tooth ring weighs, with every sketch still fully defined.
"""

from __future__ import annotations

import math
import os
from typing import List

from .. import findings, swbuild
from ..gears import kind_for, pair
from ..gears.base import BuildPlan
from ..spec import HAND_RIGHT, KIND_HELICAL, KIND_SPUR, GearSpec
from . import scaffold as sc
from .harness import Px, probe
from .p5_helical import TWIN_TOLERANCE, _Builds, _require_built, single_space, twin

RING_TEETH = 60
PINION_TEETH = 20
CHANGED_TEETH = 64
# Relative to the ring. On SolidWorks 2026 a single tooth space's cut weighed about 1e-3 of itself
# more than a sixtieth of the patterned ring's (157.494 mm³ against 157.346), which sixty spaces
# amplify to 2.8e-4 of the ring; the updated ring and a fresh build of it agreed to 1e-13. The
# outline's own polygon shows the teeth 1.25 mm thick at their tips, so the spaces do not overlap:
# it is the mass properties' resolution on a spline cut, and the twin tolerance covers it.
SPUR_TOLERANCE = TWIN_TOLERANCE
NAMES = {
    KIND_SPUR: ("Gear Axis", "Blank Sketch", "Blank", "Tooth Space Sketch", "Tooth Space", "Teeth"),
    KIND_HELICAL: ("Gear Axis", "Blank Sketch", "Blank", "Profile Plane", "Tooth Space Sketch", "Path Sketch",
                   "Tooth Space", "Teeth"),
}
SKETCHES = {
    KIND_SPUR: ("Blank Sketch", "Tooth Space Sketch"),
    KIND_HELICAL: ("Blank Sketch", "Tooth Space Sketch", "Path Sketch"),
}


class _PairBuilds(_Builds):
    def build_pair(self, gear_a: BuildPlan, gear_b: BuildPlan, assembly: BuildPlan) -> swbuild.PairResult:
        before = sc.open_titles(self.px)
        try:
            return swbuild.build_pair(self.px.session, gear_a, gear_b, assembly)
        finally:
            made = [t for t in sc.open_titles(self.px) if t not in before]
            self.titles.extend(made)
            self.px.shared.setdefault("created", []).extend(made)


def _annulus_mm3(outer: float, inner: float, width: float) -> float:
    return math.pi / 4.0 * (outer ** 2 - inner ** 2) * width


def _run_kind(px: Px, builds: _PairBuilds, kind: str, folder: str) -> None:
    recipe = px.options.get("flank") or findings.DEFAULT_RECIPE
    common = dict(kind=kind, module="2", face_width="10", recipe=recipe, hand=HAND_RIGHT,
                  helix_angle="15" if kind == KIND_HELICAL else "")
    pinion = GearSpec(teeth=str(PINION_TEETH), bore="8", **common)
    ring = GearSpec(teeth=str(RING_TEETH), teeth_side="internal", bore="", **common)
    stem = f"Probe ring {kind}"
    paths = [os.path.join(folder, f"{stem} {part}.SLDPRT") for part in ("pinion", "ring")]
    path_pair = os.path.join(folder, f"{stem} pair.SLDASM")
    for path in paths + [path_pair]:
        px.require(not os.path.exists(path), f"{path} does not exist yet")
    plans = []
    for spec, path in zip((pinion, ring), paths):
        gear = kind_for(spec)
        plan = gear.plan(spec, gear.derive(spec), recipe, "", path)
        px.require(plan.check() == [], f"{kind}: the {os.path.basename(path)} plan is sound", plan.check())
        plans.append(plan)
    assembly = pair.assembly_plan(pinion, ring, paths[0], paths[1], "", path_pair)
    px.require(assembly.check() == [], f"{kind}: the assembly plan is sound", assembly.check())

    result = builds.build_pair(plans[0], plans[1], assembly)
    px.fact(f"{kind}_pair_log", result.log_lines())
    for line in result.log_lines():
        px.note(f"{kind}: {line}")
    px.require(result.ok, f"{kind}: the pair builds with no failures")
    for part in (result.gear_a, result.gear_b):
        px.check(not part.checks, f"{kind}: every sketch of {part.document} is fully defined", part.checks)
    px.check("no interference between the gears" in result.assembly.done,
             f"{kind}: the pinion meshes inside the ring without interference", result.assembly.checks)
    session = px.session

    # The negative control: half a pinion pitch round, a tooth faces a tooth.
    mesh = pair.internal_mesh_angle(PINION_TEETH)
    session.set_global_variable(pair.MESH_ANGLE, f"{mesh + 180.0 / PINION_TEETH:g}")
    px.check(session.rebuild(), f"{kind}: the assembly rebuilds with the pinion half a pitch round")
    count, volume = session.interference_count()
    px.fact(f"{kind}_half_pitch_interference", {"count": count, "volume_mm3": volume})
    px.check(count > 0 and volume > 0.0, f"{kind}: half a pitch round, the teeth interfere ({count}, {volume:.3f} mm³)")

    ring_gear = kind_for(ring)
    derived = ring_gear.derive(ring)
    session.activate(os.path.basename(paths[1]))
    names = [f.name for f in session.features()]
    px.fact(f"{kind}_ring_features", names)
    missing = [n for n in NAMES[kind] if n not in names]
    px.check(not missing, f"{kind}: every feature the tool names is in the ring's tree", missing)
    px.check(session.solid_body_count() == 1, f"{kind}: the ring is one solid body")
    ring_volume = session.volume_mm3()

    if kind == KIND_SPUR:
        one_path = os.path.join(folder, f"{stem} one space.SLDPRT")
        one = builds.build(single_space(plans[1], one_path))
        _require_built(px, f"{kind} one space", one, one_path)
        blank = _annulus_mm3(derived.rim, derived.da, derived.face_width)
        removed = blank - session.volume_mm3()
        expected = blank - RING_TEETH * removed
        px.fact(f"{kind}_ring_volumes_mm3", {"ring": ring_volume, "blank": blank, "one_space": removed,
                                             "expected": expected})
        px.check(removed > 0 and abs(ring_volume - expected) <= SPUR_TOLERANCE * expected,
                 f"{kind}: the ring weighs its blank less {RING_TEETH} spaces: {ring_volume:.3f} vs {expected:.3f} mm³")
    else:
        twin_path = os.path.join(folder, f"{stem} twin.SLDPRT")
        straight = builds.build(twin(plans[1], twin_path))
        _require_built(px, f"{kind} twin", straight, twin_path)
        twin_volume = session.volume_mm3()
        px.fact(f"{kind}_ring_volumes_mm3", {"ring": ring_volume, "twin": twin_volume})
        px.check(abs(ring_volume - twin_volume) <= TWIN_TOLERANCE * twin_volume,
                 f"{kind}: the ring weighs what its straight twin does: {ring_volume:.3f} vs {twin_volume:.3f} mm³")

    session.activate(os.path.basename(paths[1]))
    wanted = ring.with_values(teeth=str(CHANGED_TEETH))
    changed = ring_gear.derive(wanted)
    update = swbuild.update_variables(session, ring_gear.variables(wanted, changed), paths[1])
    px.fact(f"{kind}_update_changed", update.changed)
    px.require(update.ok, f"{kind}: update_variables reports no failures", update.failures)
    px.check(update.changed == ["No. of Teeth"], f"{kind}: only the teeth changed", update.changed)
    px.check(update.rebuilt, f"{kind}: the update rebuilt once")
    after = session.volume_mm3()
    values = session.equation_values()
    wrong = {k: (values.get(k), v) for k, v in changed.values().items()
             if abs(values.get(k, math.inf) - v) > 1e-6 * max(1.0, abs(v))}
    px.check(not wrong, f"{kind}: every global follows the change", wrong)
    statuses = {name: session.sketch_status(name) for name in SKETCHES[kind]}
    px.fact(f"{kind}_sketch_statuses_after", statuses)
    px.check(all(v == findings.FULLY_CONSTRAINED for v in statuses.values()),
             f"{kind}: every sketch is still fully defined after the change", statuses)

    fresh_path = os.path.join(folder, f"{stem} fresh {CHANGED_TEETH}.SLDPRT")
    fresh = builds.build(ring_gear.plan(wanted, changed, recipe, "", fresh_path))
    _require_built(px, f"{kind} fresh {CHANGED_TEETH}", fresh, fresh_path)
    fresh_volume = session.volume_mm3()
    tolerance = SPUR_TOLERANCE if kind == KIND_SPUR else TWIN_TOLERANCE
    px.fact(f"{kind}_volumes_after_mm3", {"updated": after, "fresh": fresh_volume})
    px.check(abs(after - fresh_volume) <= tolerance * fresh_volume,
             f"{kind}: after the change it weighs what a fresh {CHANGED_TEETH}-tooth ring does: "
             f"{after:.3f} vs {fresh_volume:.3f} mm³")


@probe("internal_end_to_end", tier=5,
       needs=("annulus_extrude", "interference", "end_to_end", "helical_end_to_end", "assembly_distance_link"),
       members=("swbuild.build_pair", "Session.interference_count", "swbuild.update_variables"))
def internal_end_to_end(px: Px) -> None:
    """Build a spur and a helical ring with their pinions, check the mesh both ways, weigh and change the rings."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    builds = _PairBuilds(px)
    try:
        for kind in (KIND_SPUR, KIND_HELICAL):
            _run_kind(px, builds, kind, folder)
    finally:
        builds.close()
