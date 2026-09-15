"""Tier 5: a straight bevel pair and a crossed helical pair, built end to end through the tool's own code.

As :mod:`p5_internal`, nothing here calls COM raw: the parts are planned by the
gear kinds, the assemblies by :func:`pair.assembly_plan`, and both are built by
:func:`swbuild.build_pair`, which checks the assembly for interference.

For the **bevel** pair (m 3, 20 and 40 teeth, Σ 90°, face 20, bore 10):

* **the build** — every part and the assembly build with no failures and every
  sketch fully defined, the pinion is one body with every named feature;
* **interference** — the pair as mated touches nowhere, and with the gear turned
  half a pitch its teeth run into the pinion's, which shows the check could fail;
* **the equations** — every global in the pinion reads what :func:`bevel.derive`
  says, the outside diameter and the crown's distance from the apex among them;
* **a change** — the pinion's teeth changed 20 → 21 through
  :func:`swbuild.update_variables` rebuild it with every sketch still fully
  defined, weighing what a fresh 21-tooth build weighs.

For the **crossed** pair (mn 2, 20 and 40 teeth, β 45° both right-hand, Σ 90°):
it builds, and meshes without interference, and half a pitch round it interferes.
"""

from __future__ import annotations

import math
import os

from .. import findings, swbuild
from ..gears import kind_for, pair
from ..spec import HAND_RIGHT, KIND_BEVEL, KIND_HELICAL, GearSpec
from . import scaffold as sc
from .harness import Px, probe
from .p5_helical import TWIN_TOLERANCE, _require_built
from .p5_internal import _PairBuilds

PINION_TEETH = 20
GEAR_TEETH = 40
CHANGED_TEETH = 21
NAMES = ("Gear Axis", "Blank Sketch", "Blank", "Cone Sketch", "Heel Plane", "Toe Plane", "Heel Section Sketch",
         "Toe Section Sketch", "Tooth Space", "Teeth")
SKETCHES = ("Blank Sketch", "Cone Sketch", "Heel Section Sketch", "Toe Section Sketch")


def _build_pair(px: Px, builds: _PairBuilds, label: str, specs, paths, path_pair: str, **shafts) -> swbuild.PairResult:
    for path in list(paths) + [path_pair]:
        px.require(not os.path.exists(path), f"{path} does not exist yet")
    plans = []
    for spec, path in zip(specs, paths):
        gear = kind_for(spec)
        plan = gear.plan(spec, gear.derive(spec), gear.recipe_for(spec), "", path)
        px.require(plan.check() == [], f"{label}: the {os.path.basename(path)} plan is sound", plan.check())
        plans.append(plan)
    assembly = pair.assembly_plan(specs[0], specs[1], paths[0], paths[1], "", path_pair, **shafts)
    px.require(assembly.check() == [], f"{label}: the assembly plan is sound", assembly.check())
    result = builds.build_pair(plans[0], plans[1], assembly)
    px.fact(f"{label}_pair_log", result.log_lines())
    for line in result.log_lines():
        px.note(f"{label}: {line}")
    px.require(result.ok, f"{label}: the pair builds with no failures")
    for part in (result.gear_a, result.gear_b):
        px.check(not part.checks, f"{label}: every sketch of {part.document} is fully defined", part.checks)
    px.check("no interference between the gears" in result.assembly.done,
             f"{label}: the gears mesh without interference", result.assembly.checks)
    return result


def _half_pitch_control(px: Px, label: str, angle: float, teeth: int) -> None:
    session = px.session
    session.set_global_variable(pair.MESH_ANGLE, f"{angle + 180.0 / teeth:.9g}")
    px.check(session.rebuild(), f"{label}: the assembly rebuilds with gear 2 half a pitch round")
    count, volume = session.interference_count()
    px.fact(f"{label}_half_pitch_interference", {"count": count, "volume_mm3": volume})
    px.check(count > 0 and volume > 0.0, f"{label}: half a pitch round, the teeth interfere ({count}, {volume:.3f} mm³)")


@probe("bevel_end_to_end", tier=5,
       needs=("revolve", "ref_plane_normal", "loft_cut_sections", "nonparallel_mates", "interference", "end_to_end"),
       members=("swbuild.build_pair", "Session.revolve", "Session.ref_plane_normal", "Session.loft_cut",
                "Session.place_component", "swbuild.update_variables"))
def bevel_end_to_end(px: Px) -> None:
    """Build a bevel pinion, its gear and their assembly; check the mesh both ways, the globals and a change."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    recipe = px.options.get("flank") or findings.DEFAULT_RECIPE
    common = dict(kind=KIND_BEVEL, module="3", face_width="20", shaft_angle="90", recipe=recipe)
    pinion = GearSpec(teeth=str(PINION_TEETH), mate_teeth=str(GEAR_TEETH), bore="10", **common)
    gear = GearSpec(teeth=str(GEAR_TEETH), mate_teeth=str(PINION_TEETH), bore="10", **common)
    stem = "Probe bevel"
    paths = [os.path.join(folder, f"{stem} {part}.SLDPRT") for part in ("pinion", "gear")]
    builds = _PairBuilds(px)
    try:
        _build_pair(px, builds, "bevel", (pinion, gear), paths, os.path.join(folder, f"{stem} pair.SLDASM"))
        _half_pitch_control(px, "bevel", pair.mate_angle(GEAR_TEETH), GEAR_TEETH)

        session = px.session
        kind = kind_for(pinion)
        derived = kind.derive(pinion)
        session.activate(os.path.basename(paths[0]))
        names = [f.name for f in session.features()]
        px.fact("bevel_pinion_features", names)
        missing = [n for n in NAMES if n not in names]
        px.check(not missing, "bevel: every feature the tool names is in the pinion's tree", missing)
        px.check(session.solid_body_count() == 1, "bevel: the pinion is one solid body")
        values = session.equation_values()
        wrong = {k: (values.get(k), v) for k, v in derived.values().items()
                 if abs(values.get(k, math.inf) - v) > 1e-6 * max(1.0, abs(v))}
        px.fact("bevel_pinion_outside_and_crown", {"Outer Diameter": values.get("Outer Diameter"),
                                                   "da": derived.da, "crown_to_apex": derived.crown_to_apex})
        px.check(not wrong, "bevel: every global in the pinion is what the maths says", wrong)
        volume = session.volume_mm3()
        px.fact("bevel_pinion_volume_mm3", volume)

        wanted = pinion.with_values(teeth=str(CHANGED_TEETH))
        changed = kind.derive(wanted)
        update = swbuild.update_variables(session, kind.variables(wanted, changed), paths[0])
        px.fact("bevel_update_changed", update.changed)
        px.require(update.ok, "bevel: update_variables reports no failures", update.failures)
        px.check(update.rebuilt, "bevel: the update rebuilt once")
        after = session.volume_mm3()
        statuses = {name: session.sketch_status(name) for name in SKETCHES}
        px.fact("bevel_sketch_statuses_after", statuses)
        px.check(all(v == findings.FULLY_CONSTRAINED for v in statuses.values()),
                 "bevel: every sketch is still fully defined after the change", statuses)
        px.check(session.solid_body_count() == 1, "bevel: after the change the pinion is still one body")

        fresh_path = os.path.join(folder, f"{stem} fresh {CHANGED_TEETH}.SLDPRT")
        fresh = builds.build(kind.plan(wanted, changed, recipe, "", fresh_path))
        _require_built(px, f"bevel fresh {CHANGED_TEETH}", fresh, fresh_path)
        fresh_volume = session.volume_mm3()
        px.fact("bevel_volumes_after_mm3", {"updated": after, "fresh": fresh_volume})
        px.check(abs(after - fresh_volume) <= TWIN_TOLERANCE * fresh_volume,
                 f"bevel: after the change it weighs what a fresh {CHANGED_TEETH}-tooth pinion does: "
                 f"{after:.3f} vs {fresh_volume:.3f} mm³")
    finally:
        builds.close()


@probe("crossed_end_to_end", tier=5, needs=("nonparallel_mates", "interference", "helical_end_to_end"),
       members=("swbuild.build_pair", "Session.place_component", "Session.add_mate"))
def crossed_end_to_end(px: Px) -> None:
    """Build two 45° right-hand helical gears on shafts at 90° and check the mesh both ways."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    px.require(getattr(findings, "CROSSED_ROUTE", None) in (pair.ROUTE_MATES, pair.ROUTE_FIXED),
               "how crossed gears are held has been decided")
    recipe = px.options.get("flank") or findings.DEFAULT_RECIPE
    common = dict(kind=KIND_HELICAL, module="2", face_width="10", bore="8", recipe=recipe, hand=HAND_RIGHT,
                  helix_angle="45")
    first = GearSpec(teeth=str(PINION_TEETH), **common)
    second = GearSpec(teeth=str(GEAR_TEETH), **common)
    stem = "Probe crossed"
    paths = [os.path.join(folder, f"{stem} {part}.SLDPRT") for part in ("pinion", "gear")]
    builds = _PairBuilds(px)
    try:
        _build_pair(px, builds, "crossed", (first, second), paths, os.path.join(folder, f"{stem} pair.SLDASM"),
                    shafts="crossed", shaft_angle=90.0)
        px.fact("crossed_route", findings.CROSSED_ROUTE)
        if findings.CROSSED_ROUTE == pair.ROUTE_MATES:
            values = px.session.equation_values()
            _half_pitch_control(px, "crossed", values[pair.MESH_ANGLE], GEAR_TEETH)
    finally:
        builds.close()
