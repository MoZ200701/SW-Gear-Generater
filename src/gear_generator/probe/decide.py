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


def _beyond_sign(records: Records, cone: str) -> Optional[int]:
    """probe bevel_planes_beyond_90's x sign on one cone, once it has passed and read the angle meant."""
    if not _passed(records, "bevel_planes_beyond_90"):
        return None
    signs = (_fact(records, "bevel_planes_beyond_90", "beyond_signs") or {}).get(cone)
    return None if not signs else int(signs["x_along_outward"])


def bevel_mate_route(records: Records) -> Optional[str]:
    """``mates`` when a placed component held a bevel frame under its mates; otherwise nothing is decided."""
    error = _fact(records, "nonparallel_mates", "bevel_frame_error")
    if error is None:
        return None
    return "mates" if error["rotation"] < 1e-6 and error["origin_mm"] < 1e-6 else None


def custom_property_route(records: Records) -> Optional[str]:
    """``Add3`` when a property added, read back and was replaced; else nothing."""
    return "Add3" if _passed(records, "custom_properties") else None


def gear_mate_route(records: Records) -> Optional[str]:
    """``mates`` when a gear mate turned the second axis by the tooth ratio both ways round; else nothing."""
    return "mates" if _passed(records, "gear_mate") else None


def crossed_route(records: Records) -> Optional[str]:
    """``mates`` when the crossed frame held under its mates; nothing is decided off a failed probe."""
    return "mates" if _passed(records, "nonparallel_mates") else None


# Tier 7 (PLAN-WORKBOOK §4.2): items 1–4 each STOP the layout if they fail; item 5 has a fallback.
WORKBOOK_LAYOUT_NEEDS = ("layout_planes", "axis_through_named_planes", "axis_through_base_planes",
                         "layout_assembly_five", "layout_assembly_reopen", "layout_part_without_body")


def workbook_layout_route(records: Records) -> str:
    """``layout`` iff tier 7 items 1–4 passed: planes from Right and Top on a measured side that follow
    their globals, an axis through planes made in the part and through base planes, and five components
    placed, fixed, reopened, found by name and re-placed. Otherwise STOP and ask, as the plan says."""
    return "layout" if all(_passed(records, name) for name in WORKBOOK_LAYOUT_NEEDS) else STOP


def components_resolved_after_reopen(records: Records) -> Optional[bool]:
    """Whether every component came back fully resolved (swComponentFullyResolved, 2) from a reopened assembly."""
    states = _fact(records, "layout_assembly_reopen", "suppression_after_reopen")
    return None if not states else all(state == 2 for state in states.values())


# Tier 7, item 6 (phase W4's open fault): the routes of rebuilding an assembly, in order of preference.
ASSEMBLY_REBUILD_ROUTES = ("ForceRebuild3(True)", "EditRebuild3", "ForceRebuild3(False)", "none")


def first_rebuild_route(verdicts: Mapping[str, Mapping[str, Any]]) -> str:
    """The first route of ``ASSEMBLY_REBUILD_ROUTES`` whose every criterion is True, else STOP.

    Each verdict says whether, after the route, a put's new frame and the
    clash it caused showed, the layout part's moved axis showed in the
    assembly, a changed part showed, a part that failed to rebuild made the
    route return False, and only the documents changed on purpose read
    ``GetSaveFlag`` True. A criterion not reached (None) is not met.
    """
    for route in ASSEMBLY_REBUILD_ROUTES:
        verdict = verdicts.get(route)
        if verdict and all(value is True for value in verdict.values()):
            return route
    return STOP


def assembly_rebuild_route(records: Records) -> str:
    """The rebuild Update SolidWorks uses on an assembly, off probe assembly_rebuild_scope's pass; else STOP."""
    verdicts = _fact(records, "assembly_rebuild_scope", "rebuild_verdicts")
    return first_rebuild_route(verdicts) if verdicts else STOP


def assembly_rebuild_keeps_components_unmodified(records: Records) -> Optional[bool]:
    """Whether the route decided marked only the documents changed on purpose; None when nothing was decided."""
    route = assembly_rebuild_route(records)
    if route == STOP:
        return None
    return _fact(records, "assembly_rebuild_scope", "rebuild_verdicts")[route]["only_changed_marked"]


def same_name_elsewhere_inserted(records: Records) -> Optional[bool]:
    """Whether a part of the same file name from another folder went into an assembly beside the first."""
    found = _fact(records, "add_component_same_name_elsewhere", "same_name_elsewhere")
    return None if found is None else bool(found.get("inserted"))


def update_open_route(records: Records) -> str:
    """``open and activate`` when a closed part opened by path became active and update_variables took it;
    otherwise ``ask``: Update SolidWorks asks the user to open the part (PLAN-WORKBOOK §4.2, item 5)."""
    return "open and activate" if _passed(records, "open_and_activate_part") else "ask"


# Tier 8 (PLAN-WORKBOOK §4.4, phase W5): PLAN-GEARBOX's tier 6 items 3–5 — a gear held on a layout axis,
# five or more components mated and not fixed, a lock between free gears — and the gear mate's sense on
# every kind of pair W5 builds. If any fails, motion STOPs and the static assembly stays.
MOTION_NEEDS = ("shaft_axis_mates", "gear_mate_sense", "compound_lock", "mated_train")


def motion_route(records: Records) -> str:
    """``mates`` iff a gear held on its layout axis and along its shaft on Z+ and Z−, one rule explained every gear
    mate's sense, a lock held two free gears at a placed angle, and the 12 : 1 train, mated from W4's fixed state,
    turned its output 1/12 of the input the same way on every train tried, before and after a reopen. Otherwise
    STOP and ask, as PLAN-WORKBOOK §4.4 says."""
    if not all(_passed(records, name) for name in MOTION_NEEDS):
        return STOP
    right = _fact(records, "mated_train", "train_right_way") or {}
    return "mates" if right and all(right.values()) else STOP


def axis_concentric_refused(records: Records) -> Optional[bool]:
    """Whether AddMate5 refused a concentric mate between a gear's axis and a layout axis (axis to axis)."""
    refused = _fact(records, "shaft_axis_mates", "axis_mates_refused")
    if refused is None:
        return None
    return any(key in refused for key in ("g3", "g4"))


# Package P0 (W5-PLAN §0.3): what Update, the build and the demonstration call, read off tier 8's records.
def motion_enum(records: Records, key: str) -> Optional[int]:
    """One value motion_enums read from swconst.tlb (``suppress``, ``unsuppress``, ``this_configuration``, ...)."""
    return (_fact(records, "motion_enums", "motion_enum_values") or {}).get(key)


def suppression_route(records: Records) -> Optional[str]:
    """The route motion_update suppressed and unsuppressed both its gear mate and its lock by, when it was one."""
    facts = _fact(records, "motion_update", "motion_update") or {}
    lock = facts.get("lock_moved") or {}
    routes = {facts.get("suppressed_by"), facts.get("unsuppressed_by"), lock.get("suppressed_by"),
              lock.get("unsuppressed_by")}
    return routes.pop() if len(routes) == 1 and None not in routes else None


def lock_select_route(records: Records) -> Optional[str]:
    """How compound_lock selected the two components of every lock mate it made, when it was one route."""
    results = _fact(records, "compound_lock", "lock_results") or {}
    selects = {r.get("select") for r in results.values() if str(r.get("how", "")).startswith("lock")}
    return selects.pop() if len(selects) == 1 and None not in selects else None


def mate_delete_route(records: Records) -> Optional[str]:
    """How compound_lock deleted the mate it over-defined the assembly with."""
    return (_fact(records, "compound_lock", "over_defined") or {}).get("deleted_by")


def mate_find_route(records: Records) -> Optional[str]:
    """How lock_mate_rename found every renamed mate after the reopen, once renaming worked: the MateGroup's
    sub-features by name first (the walk the probes and the app's find_mate make), else FeatureByName."""
    if _fact(records, "lock_mate_rename", "mate_rename_route") is None:
        return None
    found = _fact(records, "lock_mate_rename", "mate_find_routes") or {}
    return next((route for route in ("mate group", "FeatureByName") if found.get(route)), None)


def gear_mate_ratio_route(records: Records) -> Optional[str]:
    """How a saved gear mate's ratio is changed, for an Update (W5-PLAN D7): ``"remake"`` only when probe
    gear_mate_ratio's remake held and probe gear_mate_update carried a whole tooth change in the shape an Update
    needs; otherwise None. Never ``"modify definition"``: on SolidWorks 2024 an assembly whose gear mate
    ModifyDefinition changed could not be closed (W5-DECISIONS, "Rulings on package P0's findings")."""
    if _fact(records, "gear_mate_ratio", "gear_mate_ratio_route") != "remake":
        return None
    return "remake" if _fact(records, "gear_mate_update", "gear_mate_update_holds") is True else None


def modified_gear_mate_closes(records: Records) -> Optional[bool]:
    """Whether every copy probe gear_mate_definition changed through its definition could be closed afterwards."""
    closes = _fact(records, "gear_mate_definition", "definition_closes")
    return None if not closes else all(closes.values())


def mated_assembly_rebuild_route(records: Records) -> Optional[str]:
    """The rebuild a mated assembly needs, off probe mated_rebuild_scope's verdicts; None when no route met them all
    (a decision, not a STOP: W5 then accepts the full rebuild's marks, which is the user's call)."""
    return _fact(records, "mated_rebuild_scope", "mated_assembly_rebuild_route")


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
        "bevel_crown_section_x_sign": _beyond_sign(records, "90"),
        "bevel_internal_section_x_sign": _beyond_sign(records, "120"),
        "loft_cut_route": _fact(records, "loft_cut_sections", "loft_cut_route"),
        "loft_cut_type": _fact(records, "loft_cut_sections", "loft_cut_type"),
        "place_route": _fact(records, "nonparallel_mates", "place_route"),
        "transform_array_order": _fact(records, "nonparallel_mates", "transform_array_order"),
        "origin_select_route": _fact(records, "nonparallel_mates", "origin_select_route"),
        "bevel_mate_route": bevel_mate_route(records),
        "crossed_route": crossed_route(records),
        "custom_property_route": custom_property_route(records),
        "custom_info_text": _fact(records, "custom_properties", "custom_info_text"),
        "custom_property_replace": _fact(records, "custom_properties", "custom_property_replace"),
        "property_read_route": _fact(records, "custom_properties", "property_read_route"),
        "property_links_globals": _fact(records, "custom_properties", "property_links_global"),
        "gear_mate_route": gear_mate_route(records),
        "mate_gear_type": _fact(records, "gear_mate", "mate_gear_type"),
        "gear_mate_numerator_first": _fact(records, "gear_mate", "gear_mate_numerator_first"),
        "gear_mate_external_flip": _fact(records, "gear_mate", "gear_mate_external_flip"),
        "bevel_end_to_end": _passed(records, "bevel_end_to_end"),
        "crossed_end_to_end": _passed(records, "crossed_end_to_end"),
        "workbook_layout_route": workbook_layout_route(records),
        "layout_plus_flip": _fact(records, "layout_planes", "layout_plus_flip"),
        "layout_negated_link": _fact(records, "layout_planes", "negated_global_link_form"),
        "axis_plane_select_route": _fact(records, "axis_through_named_planes", "axis_plane_select_route"),
        "axis_through_base_plane": _passed(records, "axis_through_base_planes") or None,
        "component_find_route": _fact(records, "layout_assembly_reopen", "component_find_route"),
        "replace_fixed_route": _fact(records, "layout_assembly_reopen", "replace_fixed_route"),
        "open_assembly_route": _fact(records, "layout_assembly_reopen", "open_assembly_route"),
        "update_open_route": update_open_route(records),
        "open_doc_route": _fact(records, "open_and_activate_part", "open_doc_route"),
        "open_doc_makes_active": _fact(records, "open_and_activate_part", "open_doc_makes_active"),
        "open_part_beside_assembly": _passed(records, "open_part_from_assembly") or None,
        "offset_global_crosses_zero": _fact(records, "layout_plane_negative_global", "crosses_zero"),
        "components_resolved_after_reopen": components_resolved_after_reopen(records),
        "reuse_add_route": _fact(records, "add_component_opened_part", "reuse_add_route"),
        "interference_names_route": _fact(records, "interference_components", "interference_components_route"),
        "same_name_elsewhere_inserted": same_name_elsewhere_inserted(records),
        "assembly_rebuild_route": assembly_rebuild_route(records),
        "assembly_rebuild_keeps_components_unmodified": assembly_rebuild_keeps_components_unmodified(records),
        "put_needs_rebuild": _fact(records, "assembly_rebuild_scope", "put_needs_rebuild"),
        "full_rebuild_marks_components_modified": _fact(records, "assembly_rebuild_scope",
                                                        "full_rebuild_marks_components_modified"),
        "opened_reads_unmodified": _fact(records, "assembly_rebuild_scope", "opened_reads_unmodified"),
        "motion_route": motion_route(records),
        "axis_mate_route": _fact(records, "shaft_axis_mates", "axis_mate_route"),
        "axis_concentric_refused": axis_concentric_refused(records),
        "axial_mate_route": _fact(records, "shaft_axis_mates", "axial_mate_route"),
        "gear_mate_flip_rule": _fact(records, "gear_mate_sense", "gear_mate_flip_rule"),
        "gear_mate_sense_depends_on_entities": _fact(records, "gear_mate_sense", "sense_depends_on_entities"),
        "compound_lock_route": _fact(records, "compound_lock", "compound_lock_route"),
        "layout_move_carries_mates": _fact(records, "motion_update", "layout_move_carries_mates"),
        "mesh_phase_route": _fact(records, "motion_update", "mesh_phase_route"),
        "axial_global_moves_gear": _fact(records, "motion_update", "axial_global_moves_gear"),
        "lock_unsuppress_keeps_the_new_angle": _fact(records, "motion_update", "lock_unsuppress_keeps_the_new_angle"),
        "feature_suppress": motion_enum(records, "suppress"),
        "feature_unsuppress": motion_enum(records, "unsuppress"),
        "this_configuration": motion_enum(records, "this_configuration"),
        "suppression_route": suppression_route(records),
        "lock_select_route": lock_select_route(records),
        "mate_delete_route": mate_delete_route(records),
        "gear_mate_ratio_route": gear_mate_ratio_route(records),
        "gear_mate_update_holds": _fact(records, "gear_mate_update", "gear_mate_update_holds"),
        "gear_mate_definition_recipe": _fact(records, "gear_mate_definition", "definition_recipe"),
        "gear_mate_definition_numerator_is_second": _fact(records, "gear_mate_definition",
                                                          "definition_numerator_is_second_teeth"),
        "modified_gear_mate_closes": modified_gear_mate_closes(records),
        "remake_on_twice_meshed_gear_holds": _fact(records, "put_on_twice_meshed_gear",
                                                   "remake_on_twice_meshed_gear_holds"),
        "lock_retakes_an_offset": _fact(records, "lock_retake_offset", "lock_retakes_an_offset"),
        "mate_rename_route": _fact(records, "lock_mate_rename", "mate_rename_route"),
        "mate_find_route": mate_find_route(records),
        "demonstration_drive_holds": _fact(records, "demonstration_drive", "demonstration_drive_holds"),
        "put_on_twice_meshed_gear_holds": _fact(records, "put_on_twice_meshed_gear", "put_on_twice_meshed_gear_holds"),
        "axial_datum_route": _fact(records, "axial_datum_plane", "axial_datum_route"),
        "axial_datum_flip": _fact(records, "axial_datum_plane", "axial_datum_flip"),
        "mated_assembly_rebuild_route": mated_assembly_rebuild_route(records),
        "mated_rebuild_keeps_components_unmodified": _fact(records, "mated_rebuild_scope",
                                                           "mated_rebuild_keeps_components_unmodified"),
        "mated_build_rebuild_route": _fact(records, "mated_rebuild_scope", "mated_build_rebuild_route"),
        "mated_build_keeps_components_unmodified": _fact(records, "mated_rebuild_scope",
                                                         "mated_build_keeps_components_unmodified"),
        "manual_steps": manual_steps(records, recipe),
    }
