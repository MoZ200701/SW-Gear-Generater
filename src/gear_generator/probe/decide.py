"""From probe results to decisions. Pure: it reads records, it never calls COM.

The decisions are what the tool is allowed to rely on, so the rules here are
the plan's, spelled out: the flank recipe is A only if an Equation Driven Curve
works literally, with global names, and follows a rebuild; otherwise B only if
plain entities, relations and a linked dimension work; otherwise STOP, and
nothing is improvised.

Every other decision is read from the fact a probe recorded, and is ``None``
when that probe did not pass — a decision is never made on a failed probe's
leftovers. ``tests/test_findings.py`` checks :mod:`findings` against the
committed ``latest.json`` through this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

PASS = "pass"

RECIPE_A_NEEDS = ("curve_literal", "curve_globals", "curve_rebuild")
RECIPE_B_NEEDS = ("sketch_entities", "relations", "dimension_link")
PARAMETRIC_NEEDS = ("equation_add", "equation_syntax", "equation_set")

STOP = "STOP"

CUT_ROUTES = {
    "through all both": 9,
    "through all, both ends": 1,
    "through all, direction flipped": 1,
}

Records = Mapping[str, Mapping[str, Any]]


def _passed(records: Records, name: str) -> bool:
    return (records.get(name) or {}).get("status") == PASS


def _fact(records: Records, probe: str, key: str, default: Any = None) -> Any:
    if not _passed(records, probe):
        return default
    return ((records.get(probe) or {}).get("facts") or {}).get(key, default)


def flank_recipe(records: Records) -> str:
    if not all(_passed(records, name) for name in PARAMETRIC_NEEDS):
        return STOP
    if all(_passed(records, name) for name in RECIPE_A_NEEDS):
        return "A"
    if all(_passed(records, name) for name in RECIPE_B_NEEDS):
        return "B"
    return STOP


def manual_steps(records: Records, recipe: str) -> List[str]:
    """Steps a negative probe turns into something a person does, by cause."""
    steps: List[str] = ["material"]
    if recipe == "A" and not _passed(records, "curve_fixed_rebuild"):
        steps.append("fully define the flank curves")
    if _passed(records, "pattern") and not _passed(records, "pattern_count_link"):
        steps.append("link Count@Teeth in Equations")
    if _passed(records, "assembly_components_and_mates") and not _passed(records, "assembly_distance_link"):
        steps.append("link the centre distance mate in Equations")
    return steps


def _cut_end_condition(records: Records) -> Optional[int]:
    routes = _fact(records, "cut", "cut_routes_that_remove_the_hole") or []
    for preferred in ("through all both", "through all, both ends", "through all, direction flipped"):
        if preferred in routes:
            return CUT_ROUTES[preferred]
    return None


def _plane_select_route(records: Records) -> Optional[str]:
    if not _passed(records, "sketch_open_close"):
        return None
    facts = records["sketch_open_close"].get("facts") or {}
    by_id = (facts.get("select_by_id2_plane_tree_name") or {}).get("selected")
    return "Select2 checked by count, then SelectByID2 by tree name" if by_id else "Select2"


def _equation_add_call(records: Records) -> Optional[str]:
    form = _fact(records, "equation_add", "add3_form")
    return "Add2" if form == "Add2" else form


def decide(records: Records) -> Dict[str, Any]:
    recipe = flank_recipe(records)
    units = _fact(records, "document_units", "default_template_is_mm")
    return {
        "flank_recipe": recipe,
        "trig_default": _fact(records, "equation_syntax", "trig_units"),
        "equation_add_call": _equation_add_call(records),
        "equation_set_route": (_fact(records, "equation_set", "equation_set_routes") or [None])[0],
        "set_units_mmgs_after_new": (units is False and bool(_fact(records, "document_units", "set_mmgs_works")))
        if units is not None else None,
        "plane_select_route": _plane_select_route(records),
        "equal_constraint": _fact(records, "relations", "equal_radius_constraint"),
        "circle_dimension": _fact(records, "dimensions", "circle_dimension_measures"),
        "arc_dimension": _fact(records, "dimensions", "arc_dimension_measures"),
        "curve_trig": _fact(records, "curve_literal", "curve_trig_units"),
        "curves_are_fixed": _fact(records, "curve_fixed_rebuild", "fixed_curve_follows_global"),
        "shared_ends_are_one_point": _fact(records, "curve_end_points", "line_start_is_the_curve_start_point"),
        "cut_end_condition": _cut_end_condition(records),
        "pattern_count_dim_index": _fact(records, "pattern", "pattern_count_dim_index"),
        "save_as_overwrites": (_fact(records, "save_as", "save_as3_onto_existing_file") or {}).get("flag")
        if _passed(records, "save_as") else None,
        "first_component_fixed": _fact(records, "assembly_components_and_mates", "first_component_fixed_on_insert"),
        "end_to_end": _passed(records, "end_to_end"),
        "manual_steps": manual_steps(records, recipe),
    }
