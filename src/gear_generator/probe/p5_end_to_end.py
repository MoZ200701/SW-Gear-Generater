"""Tier 5: a small gear built end to end, through the tool's own code.

Every earlier probe calls COM members raw. This one does not: it builds a
12-tooth, module 2 gear with the decided recipe through :func:`swbuild.build`
and the :class:`swcom.Session` members written from those probes, then changes
the gear through :func:`swbuild.update_variables`. So a pass here says the
tool works, not only that the API does.

The plan asks for Module 2 → 2.5 and an OD of 33.75 mm; 33.75 is
(13 + 2) × 2.25, so Module goes to 2.25 here and the OD it names is checked.
"""

from __future__ import annotations

import math
import os

from .. import findings, swbuild
from ..gears import KINDS
from ..spec import GearSpec
from ..swcom import MM_PER_METRE
from . import scaffold as sc
from .harness import Px, probe

SPUR = KINDS["spur"]
NAMES = ("Gear Axis", "Blank Sketch", "Blank", "Tooth Space Sketch", "Tooth Space", "Teeth", "Bore Sketch", "Bore")
SKETCHES = ("Blank Sketch", "Tooth Space Sketch", "Bore Sketch")


def _cylinder_mm3(diameter: float, bore: float, width: float) -> float:
    return math.pi / 4.0 * (diameter ** 2 - bore ** 2) * width


def _dims(session, feature: str) -> dict:
    return {name: value for name, value in session.feature_dimensions(feature)}


@probe("end_to_end", tier=5,
       needs=("pattern_count_link", "curve_fixed_rebuild", "save_as", "document_units", "cut", "dimension_link"),
       members=("swbuild.build", "swbuild.update_variables"))
def end_to_end(px: Px) -> None:
    """Build m 2 z 12, check it, change it to m 2.25 z 13 through its equations, check again."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    path = os.path.join(folder, "Probe Gear m2 N12.SLDPRT")
    px.require(not os.path.exists(path), f"{path} does not exist yet")

    recipe = px.options.get("flank") or findings.DEFAULT_RECIPE
    spec = GearSpec(module="2", teeth="12", bore="8", face_width="10", recipe=recipe)
    derived = SPUR.derive(spec)
    plan = SPUR.plan(spec, derived, recipe, "", path)
    px.require(plan.check() == [], "the plan is sound", plan.check())
    session = px.session
    px.fact("recipe", recipe)

    before = sc.open_titles(px)
    made = []
    try:
        result = swbuild.build(session, plan)
        made = [t for t in sc.open_titles(px) if t not in before]
        px.shared.setdefault("created", []).extend(made)
        _check(px, session, spec, derived, result, path)
    finally:
        made = made or [t for t in sc.open_titles(px) if t not in before]
        px.shared.setdefault("created", []).extend(t for t in made if t not in px.shared["created"])
        if not px.options.get("keep"):
            for title in made:
                session.close_document(title)


def _check(px: Px, session, spec: GearSpec, derived, result, path: str) -> None:
    px.fact("build_log", result.log_lines())
    for line in result.log_lines():
        px.note(line)
    px.require(result.ok, "the build reports no failures", result.failures)
    px.check(result.rebuilt, "ForceRebuild3 reported success")
    px.require(result.saved.lower() == path.lower() and os.path.isfile(path), "the part is saved where asked")
    px.fact("sketch_checks", result.checks)
    px.check(not result.checks, "every sketch is fully defined", result.checks)

    names = [f.name for f in session.features()]
    px.fact("feature_names", names)
    px.check(all(n in names for n in NAMES), "every feature the tool names is in the tree, by that name")
    statuses = {name: session.sketch_status(name) for name in SKETCHES}
    px.fact("sketch_statuses", statuses)

    width = derived.face_width
    volume = session.volume_mm3()
    low, high = _cylinder_mm3(derived.df, 8.0, width), _cylinder_mm3(derived.da, 8.0, width)
    px.fact("volume_mm3_z12", {"volume": volume, "root_cylinder": low, "od_cylinder": high})
    px.check(low < volume < high, "the volume lies between the root and OD cylinders")
    teeth_dims = _dims(session, "Teeth")
    px.fact("teeth_dimensions", teeth_dims)
    px.check(teeth_dims.get("Count") == 12.0, "Count@Teeth is 12")

    wanted = spec.with_values(teeth="13", module="2.25")
    changed = SPUR.derive(wanted)
    update = swbuild.update_variables(session, SPUR.variables(wanted, changed), path)
    px.fact("update_changed", update.changed)
    px.require(update.ok, "update_variables reports no failures", update.failures)
    px.check(sorted(update.changed) == ["Module", "No. of Teeth"], "exactly the two typed values changed")
    px.check(update.rebuilt, "the update rebuilt once")

    values = session.equation_values()
    px.check(abs(values.get("Outer Diameter", 0.0) - 33.75) < 1e-9, "\"Outer Diameter\" is 33.75")
    teeth_dims = _dims(session, "Teeth")
    px.check(teeth_dims.get("Count") == 13.0, "Count@Teeth follows to 13", teeth_dims)
    blank = _dims(session, "Blank")
    px.fact("blank_dimensions_after", blank)
    px.check(abs(blank.get("OD", 0.0) * MM_PER_METRE - 33.75) < 1e-6, "OD@Blank Sketch reads 33.75 mm")
    after = session.volume_mm3()
    low, high = _cylinder_mm3(changed.df, 8.0, width), _cylinder_mm3(changed.da, 8.0, width)
    px.fact("volume_mm3_z13", {"volume": after, "root_cylinder": low, "od_cylinder": high})
    px.check(abs(after - volume) > 1.0, "the volume changed")
    px.check(low < after < high, "the new volume lies between the new root and OD cylinders")
    statuses = {name: session.sketch_status(name) for name in SKETCHES}
    px.fact("sketch_statuses_after", statuses)
    px.check(all(v == findings.FULLY_CONSTRAINED for v in statuses.values()),
             "every sketch is still fully defined after the change")
