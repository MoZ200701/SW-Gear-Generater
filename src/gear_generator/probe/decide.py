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
HELIX_TWIST_NEEDS = ("sweep_twist", "sweep_twist_link", "sweep_cut_ends")

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


def helix_route(records: Records) -> str:
    """How a helical tooth space is swept: ``twist`` iff a constant-twist sweep cuts
    exactly and its twist follows a global; else ``guide`` iff the helix-guide
    fallback passed; else STOP. Nothing works without atn for the transverse
    pressure angle."""
    if not _passed(records, "equation_inverse_trig"):
        return STOP
    if all(_passed(records, name) for name in HELIX_TWIST_NEEDS):
        return "twist"
    if _passed(records, "helix_guide"):
        return "guide"
    return STOP


def herringbone_route(records: Records) -> str:
    """A herringbone is a helical half mirrored: ``mirror`` iff the helix has a route and
    the body mirrors into one; the two-sweep alternative has no probe, so otherwise STOP."""
    if helix_route(records) == STOP or not _passed(records, "mirror_body_merge"):
        return STOP
    return "mirror"


def _twist_turn(records: Records) -> Optional[Dict[str, int]]:
    turns = _fact(records, "sweep_twist", "twist_about_plus_z") or {}
    if "plus z" not in turns or "minus z" not in turns:
        return None
    return {"plus z": turns["plus z"], "minus z": turns["minus z"]}


def _top_sketch_y_is_minus_z(records: Records) -> Optional[bool]:
    axes = _fact(records, "center_of_mass", "top_sketch_axes_in_model")
    if not axes:
        return None
    return list(axes["y"]) == [0.0, 0.0, -1.0]


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


def _revolve_axis_mark(records: Records) -> Optional[int]:
    routes = _fact(records, "revolve", "revolve_routes") or []
    marked = [r for r in routes if "mark" in r]
    return int(marked[-1].rsplit(" ", 1)[-1]) if marked else None


def _bevel_section_x_sign(records: Records) -> Optional[int]:
    signs = _fact(records, "ref_plane_normal", "ref_plane_normal_signs")
    return None if not signs else int(signs["x_along_outward"])


def bevel_mate_route(records: Records) -> Optional[str]:
    """``mates`` when a placed component held a bevel frame under its mates; otherwise nothing is decided."""
    error = _fact(records, "nonparallel_mates", "bevel_frame_error")
    if error is None:
        return None
    return "mates" if error["rotation"] < 1e-6 and error["origin_mm"] < 1e-6 else None


def crossed_route(records: Records) -> Optional[str]:
    """``mates`` when the crossed frame held under its mates; nothing is decided off a failed probe."""
    return "mates" if _passed(records, "nonparallel_mates") else None


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
        "helix_route": helix_route(records),
        "herringbone_route": herringbone_route(records),
        "inverse_tangent": _fact(records, "equation_inverse_trig", "inverse_trig_tangent"),
        "extrude_z_sign": _fact(records, "center_of_mass", "extrude_z_sign"),
        "top_sketch_y_is_minus_z": _top_sketch_y_is_minus_z(records),
        "ref_plane_unflipped_is_plus_z": (not plus) if (plus := _fact(records, "ref_plane_offset",
                                                                        "ref_plane_plus_z_flip")) is not None else None,
        "twist_turn": _twist_turn(records),
        "twist_reverse_flips": _fact(records, "sweep_twist", "reverse_flag_flips"),
        "mirror_body_route": (_fact(records, "mirror_body_merge", "mirror_body_routes") or [None])[0],
        "helical_end_to_end": _passed(records, "helical_end_to_end"),
        "annulus_extrudes": _passed(records, "annulus_extrude") or None,
        "interference_route": _fact(records, "interference", "interference_route"),
        "internal_end_to_end": _passed(records, "internal_end_to_end"),
        "revolve_axis_mark": _revolve_axis_mark(records),
        "bevel_section_x_sign": _bevel_section_x_sign(records),
        "loft_cut_route": _fact(records, "loft_cut_sections", "loft_cut_route"),
        "loft_cut_type": _fact(records, "loft_cut_sections", "loft_cut_type"),
        "place_route": _fact(records, "nonparallel_mates", "place_route"),
        "transform_array_order": _fact(records, "nonparallel_mates", "transform_array_order"),
        "origin_select_route": _fact(records, "nonparallel_mates", "origin_select_route"),
        "bevel_mate_route": bevel_mate_route(records),
        "crossed_route": crossed_route(records),
        "bevel_end_to_end": _passed(records, "bevel_end_to_end"),
        "crossed_end_to_end": _passed(records, "crossed_end_to_end"),
        "manual_steps": manual_steps(records, recipe),
    }
