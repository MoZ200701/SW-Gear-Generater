"""The constants in findings.py against the committed probe evidence.

``probe/results/latest.json`` is what SolidWorks did; this is what stops the
tool's constants drifting from it.
"""

import json
import math
from pathlib import Path

import pytest

from gear_generator import findings
from gear_generator.probe import decide

LATEST = Path(__file__).resolve().parents[1] / "probe" / "results" / "latest.json"


@pytest.fixture(scope="module")
def evidence():
    assert LATEST.is_file(), f"{LATEST} is the committed probe evidence and must exist"
    data = json.loads(LATEST.read_text(encoding="utf-8"))
    records = {r["name"]: r for r in data["records"]}
    return data, records, decide.decide(records)


def facts(records, name):
    assert records[name]["status"] == "pass", f"{name} did not pass"
    return records[name]["facts"]


def test_the_evidence_is_from_the_version_the_findings_name(evidence):
    data, _, _ = evidence
    assert data["meta"]["version"] == findings.VERIFIED_ON


def test_every_probe_passed_including_the_end_to_end_build(evidence):
    data, records, decided = evidence
    assert [name for name, r in records.items() if r["status"] != "pass"] == []
    assert decided["end_to_end"] is True
    assert {r["tier"] for r in records.values()} >= {0, 1, 2, 3, 4, 5}


def test_decisions(evidence):
    _, _, decided = evidence
    assert decided["flank_recipe"] == findings.DEFAULT_RECIPE
    assert decided["trig_default"] == findings.TRIG_DEFAULT
    assert decided["equation_add_call"] == findings.EQUATION_ADD_CALL
    assert decided["equation_set_route"] == findings.EQUATION_SET_ROUTE
    assert decided["set_units_mmgs_after_new"] is findings.SET_UNITS_MMGS_AFTER_NEW
    assert decided["plane_select_route"] == findings.PLANE_SELECT_ROUTE
    assert decided["equal_constraint"] == findings.RELATIONS["equal"]
    assert decided["circle_dimension"] == findings.CIRCLE_DIMENSION
    assert decided["arc_dimension"] == findings.ARC_DIMENSION
    assert decided["curve_trig"] == findings.CURVE_TRIG
    assert decided["curves_are_fixed"] is findings.CURVES_ARE_FIXED
    assert decided["shared_ends_are_one_point"] is findings.SHARED_ENDS_ARE_ONE_POINT
    assert decided["cut_end_condition"] == findings.CUT_END_CONDITION
    assert decided["pattern_count_dim_index"] == findings.PATTERN_COUNT_DIM_INDEX
    assert decided["save_as_overwrites"] is findings.SAVE_AS_OVERWRITES
    assert decided["first_component_fixed"] is findings.FIRST_COMPONENT_FIXED
    assert decided["manual_steps"] == ["material"]


def test_units(evidence):
    _, records, _ = evidence
    units = facts(records, "document_units")
    assert units["units_2026_folder"] == {"linear": findings.LENGTH_MM, "system": findings.UNIT_SYSTEM_MMGS,
                                          "path": units["units_2026_folder"]["path"]}
    if units["default_template_is_mm"]:
        # A millimetre default template leaves nothing to set (probe/results/probe-results-20260915-023929.json
        # is the run on an inch default, where setting MMGS made a part millimetres).
        assert units["units_default"]["linear"] == findings.LENGTH_MM
        assert findings.SET_UNITS_MMGS_AFTER_NEW is False
    else:
        assert units["set_mmgs_default"]["linear_after"] == findings.LENGTH_MM


INCH_DEFAULT_RUN = LATEST.parent / "probe-results-20260915-023929.json"


def test_an_inch_default_template_is_set_to_millimetres():
    """Probe document_units on the stock 2026 templates (2026-09-15), whose default part was inches.

    The machine's defaults are millimetres now, so latest.json no longer shows
    the inch route the build still takes for an inch template; this run does.
    """
    data = json.loads(INCH_DEFAULT_RUN.read_text(encoding="utf-8"))
    assert data["meta"]["version"] == "SolidWorks 2026 (revision 34.0.0)"
    units = facts({r["name"]: r for r in data["records"]}, "document_units")
    assert units["default_template_is_mm"] is False
    assert units["units_default"]["linear"] == 3          # swLengthUnit_e.swINCHES
    assert units["set_mmgs_works"] is True
    assert units["set_mmgs_default"]["linear_after"] == findings.LENGTH_MM
    assert decide.decide({r["name"]: r for r in data["records"]})["set_units_mmgs_after_new"] is True


def test_constrained_status(evidence):
    _, records, _ = evidence
    status = facts(records, "constrained_status")
    assert status["status_free_line"] == findings.UNDER_CONSTRAINED
    assert status["status_defined_line"] == findings.FULLY_CONSTRAINED


def test_pattern_and_extrude_dimensions(evidence):
    _, records, _ = evidence
    pattern = facts(records, "pattern")
    assert pattern["pattern_call"].startswith(findings.PATTERN_CALL.split(".")[-1])
    name, value = pattern["pattern_dimensions"][findings.PATTERN_COUNT_DIM_INDEX]
    assert name == findings.PATTERN_COUNT_DIM_NAME and value == 6.0
    assert any(math.isclose(v, 2 * math.pi) for _, v in pattern["pattern_dimensions"])


def test_mates(evidence):
    _, records, _ = evidence
    mates = facts(records, "assembly_components_and_mates")
    assert [kind for _, kind in mates["mates"]] == ["MateCoincident", "MateCoincident", "MateDistanceDim",
                                                    "MatePlanarAngleDim"]
    assert mates["distance_mate_dimensions"][0][0] == findings.MATE_DISTANCE_DIM_NAME
    link = facts(records, "assembly_distance_link")
    assert link["component_b_translation_mm_after_global_70"][0] == pytest.approx(70.0)


def test_save_as_returns_a_plain_flag(evidence):
    _, records, _ = evidence
    assert facts(records, "save_as")["save_as3_result_is_tuple"] is False


def test_helical_decisions(evidence):
    _, records, decided = evidence
    assert decided["helix_route"] == "twist"
    assert decided["herringbone_route"] == "mirror"
    assert decided["inverse_tangent"] == findings.INVERSE_TANGENT
    assert decided["extrude_z_sign"] == findings.EXTRUDE_Z_SIGN
    assert decided["top_sketch_y_is_minus_z"] is findings.TOP_SKETCH_Y_IS_MINUS_Z
    assert decided["ref_plane_unflipped_is_plus_z"] is findings.REF_PLANE_UNFLIPPED_IS_PLUS_Z
    assert decided["twist_turn"] == findings.TWIST_TURN
    assert decided["twist_reverse_flips"] is True
    assert decided["mirror_body_route"] == (f"body mark {findings.MIRROR_BODY_MARK}, "
                                            f"plane mark {findings.MIRROR_PLANE_MARK}")
    assert decided["helical_end_to_end"] is True
    assert "overrun " + findings.SWEEP_CUT_CALL.split(".")[-1] in facts(records, "sweep_cut_ends")["sweep_cut_routes"]
    assert facts(records, "equation_inverse_trig")["inverse_trig_accepted"]["atn"] == findings.INVERSE_TRIG_UNITS


def test_bevel_decisions(evidence):
    _, records, decided = evidence
    assert decided["revolve_axis_mark"] == findings.REVOLVE_AXIS_MARK
    assert facts(records, "revolve")["revolve_selected_type"] == findings.REVOLVE_TYPE
    assert decided["bevel_section_x_sign"] == findings.BEVEL_SECTION_X_SIGN
    assert decided["loft_cut_route"] == f"heel then toe, mark {findings.LOFT_PROFILE_MARK}"
    assert decided["loft_cut_type"] == findings.LOFT_CUT_TYPE
    assert decided["bevel_end_to_end"] is True


def test_bevel_beyond_ninety_decisions(evidence):
    """Probe bevel_planes_beyond_90: a crown's and an internal bevel's heel planes face as a cone's does."""
    _, records, decided = evidence
    assert decided["bevel_crown_section_x_sign"] == findings.BEVEL_CROWN_SECTION_X_SIGN
    assert decided["bevel_internal_section_x_sign"] == findings.BEVEL_INTERNAL_SECTION_X_SIGN
    beyond = facts(records, "bevel_planes_beyond_90")
    assert beyond["beyond_cone_dimension_90"] == pytest.approx(90.0)
    assert beyond["beyond_cone_dimension_120"] == pytest.approx(120.0)
    for cone in ("90", "120"):
        assert beyond["beyond_signs"][cone] == {"x_along_outward": 1, "y_along_plus_y": 1, "normal_along_line": 1}


def test_non_parallel_assembly_decisions(evidence):
    _, records, decided = evidence
    assert decided["place_route"] == findings.PLACE_ROUTE
    assert decided["transform_array_order"] == findings.TRANSFORM_ARRAY_ORDER
    assert decided["origin_select_route"] == f"SelectByID2 EXTSKETCHPOINT {findings.ORIGIN_POINT}@Origin"
    assert decided["bevel_mate_route"] == findings.BEVEL_MATE_ROUTE
    assert decided["crossed_route"] == findings.CROSSED_ROUTE
    assert decided["crossed_end_to_end"] is True


def test_gear_mate_decisions(evidence):
    """Probe gear_mate: a 20 : 40 gear mate turned the second axis half as far, opposite ways with Flip off."""
    _, records, decided = evidence
    mate = facts(records, "gear_mate")
    for run, opposite in (("plain", True), ("flipped", False)):
        turned = mate[f"gear_mate_turn_{run}"]
        assert abs(turned["a"]) == pytest.approx(30.0)
        assert turned["b"] / turned["a"] == pytest.approx(-0.5 if opposite else 0.5)
    assert decided["gear_mate_route"] == findings.GEAR_MATE_ROUTE
    assert decided["mate_gear_type"] == findings.MATE_GEAR
    assert decided["gear_mate_numerator_first"] is findings.GEAR_MATE_NUMERATOR_FIRST
    assert decided["gear_mate_external_flip"] is findings.GEAR_MATE_EXTERNAL_FLIP


def test_custom_property_decisions(evidence):
    """Probe custom_properties: Add3 and Get6 work; a global's quoted name stays text, so sizes are not stamped."""
    _, records, decided = evidence
    linked = facts(records, "custom_properties")["linked_property"]
    assert linked["resolved_after"] == '"No. of Teeth"'
    assert decided["custom_property_route"] == findings.CUSTOM_PROPERTY_ROUTE
    assert decided["custom_info_text"] == findings.CUSTOM_INFO_TEXT
    assert decided["custom_property_replace"] == findings.CUSTOM_PROPERTY_REPLACE
    assert decided["property_read_route"] == findings.PROPERTY_READ_ROUTE
    assert decided["property_links_globals"] is findings.PROPERTY_LINKS_GLOBALS


# -- tier 7, on both versions: W4's layout and assembly must build on 2024 and 2026 alike

# The 2024 tier-7 run, in the user's own session; sw2024/latest.json stays that folder's last FULL run.
SW2024 = LATEST.parent / "sw2024" / "probe-results-20261113-184353.json"


@pytest.fixture(scope="module", params=["2026", "2024"])
def tier_seven(request):
    path = LATEST if request.param == "2026" else SW2024
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["meta"]["version"].startswith(f"SolidWorks {request.param} ")
    records = {r["name"]: r for r in data["records"]}
    return records, decide.decide(records)


def test_layout_planes_from_right_and_top(tier_seven):
    """Probes layout_planes and layout_plane_negative_global: unflipped is the plus side; a global cannot cross zero."""
    records, decided = tier_seven
    planes = facts(records, "layout_planes")
    assert decided["layout_plus_flip"] == findings.LAYOUT_PLUS_FLIP
    for base, axis in (("right", 0), ("top", 1)):
        plus = str(findings.LAYOUT_PLUS_FLIP[base])
        assert planes["layout_plane_positions"][base][plus]["origin_mm"][axis] == pytest.approx(7.0)
        assert planes["layout_offset_follows_global"][base]["plane_at_mm"] == pytest.approx(23.0)
        assert planes["layout_offset_dim_default_names"][base] == findings.LAYOUT_OFFSET_DIM
    assert decided["layout_negated_link"] == findings.LAYOUT_NEGATED_LINK
    assert planes["negated_global_link"][findings.LAYOUT_NEGATED_LINK]["plane_at_mm"] == pytest.approx(-11.0)
    if "layout_plane_negative_global" in records:     # an extra, left off in the user's 2024 session
        assert decided["offset_global_crosses_zero"] is findings.OFFSET_GLOBAL_CROSSES_ZERO
        dropped = facts(records, "layout_plane_negative_global")["negative_global"]
        assert dropped["global_value"] == -9.0 and dropped["rebuild"] is True and dropped["error_code"] == 0
        assert dropped["plane_x_mm"] == pytest.approx(7.0)            # silently left where it was


def test_layout_axes(tier_seven):
    """Probes axis_through_named_planes and axis_through_base_planes: every route made the axis where the planes cross."""
    records, decided = tier_seven
    assert decided["axis_plane_select_route"] == findings.AXIS_PLANE_SELECT_ROUTE
    named = facts(records, "axis_through_named_planes")
    assert all(named["axis_plane_select_routes"].values())
    assert named["named_axes_after_globals"]["S1"]["at_mm"] == pytest.approx([26.0, 9.0])
    base = facts(records, "axis_through_base_planes")
    assert decided["axis_through_base_plane"] is findings.AXIS_THROUGH_BASE_PLANE
    assert base["base_plane_axes_after_globals"]["B1"]["at_mm"] == pytest.approx([0.0, 18.0])
    assert base["base_plane_axes_after_globals"]["B2"]["at_mm"] == pytest.approx([31.0, 0.0])
    for axis in list(named["named_axes"].values()) + list(base["base_plane_axes"].values()):
        assert axis["direction"] == pytest.approx([0.0, 0.0, float(findings.LAYOUT_AXIS_Z_SIGN)])


def test_layout_assembly(tier_seven):
    """Probes layout_assembly_five and layout_assembly_reopen: found by name after a reopen, re-placed while fixed."""
    records, decided = tier_seven
    assert decided["workbook_layout_route"] == findings.WORKBOOK_LAYOUT_ROUTE
    assert decided["component_find_route"] == findings.COMPONENT_FIND_ROUTE
    assert decided["replace_fixed_route"] == findings.REPLACE_FIXED_ROUTE
    assert decided["open_assembly_route"] == findings.OPEN_ASSEMBLY_ROUTE
    five = facts(records, "layout_assembly_five")
    assert five["component_instances"]["Probe W7 C"] == ["Probe W7 C-1", "Probe W7 C-2"]
    assert all(five["fixed_after_fix_component"].values())
    reopened = facts(records, "layout_assembly_reopen")
    assert all(v["fixed"] for v in reopened["frames_after_reopen"].values())
    assert all(v["origin_mm"] < 1e-6 for v in reopened["replaced_frames_after_second_open"].values())


def test_opening_a_part_for_update(tier_seven):
    """Probes open_and_activate_part and open_part_from_assembly: OpenDoc6, then ActivateDoc3, then update_variables."""
    records, decided = tier_seven
    assert decided["update_open_route"] == findings.UPDATE_OPEN_ROUTE
    assert decided["open_doc_route"] == findings.OPEN_DOC_ROUTE
    assert decided["open_part_beside_assembly"] is findings.OPEN_PART_BESIDE_ASSEMBLY
    opened = facts(records, "open_and_activate_part")
    assert opened["open Probe W7 Open.SLDPRT"]["errors"] == 0
    again = opened["open_doc_on_open_part"]
    assert again["same_title"] is True and again["made_active"] is False       # so ActivateDoc3 always follows
    assert facts(records, "open_part_from_assembly")["open Probe W7 A.SLDPRT"]["warnings"] == \
        findings.OPEN_DOC_ALREADY_OPEN_WARNING
    assert opened["update_after_reactivate"]["changed"] == ["Probe Teeth"]


def test_layout_part_and_reused_parts(tier_seven):
    """Probes layout_part_without_body and add_component_opened_part: a body-less part works; a closed one is opened first."""
    records, decided = tier_seven
    bodiless = facts(records, "layout_part_without_body")
    assert bodiless["bodiless_solid_bodies"] == 0 and findings.LAYOUT_PART_WITHOUT_BODY is True
    assert (bodiless["bodiless_insert"]["landed_mm"] == bodiless["bodiless_insert"]["asked_mm"]) is \
        findings.BODILESS_LANDS_ORIGIN_AT_POINT
    assert bodiless["bodiless_interference"]["count"] == 0
    assert bodiless["bodiless_save"] == {"returned": True, "errors": 0, "warnings": 0}
    after = bodiless["bodiless_after_reopen"]
    assert after["fixed"] is True and after["origin_mm"] < 1e-6 and after["rotation"] < 1e-6
    assert all(all(routes.values()) for routes in bodiless["bodiless_axes_reachable"].values())
    reuse = facts(records, "add_component_opened_part")
    assert decided["reuse_add_route"] == findings.REUSE_ADD_ROUTE
    assert reuse["add_component_routes"] == {"closed": False, "opened": True}
    assert reuse["same_file_twice_names"] == ["Probe W7 Reuse-1", "Probe W7 Reuse-2"]
    assert decided["components_resolved_after_reopen"] is findings.COMPONENTS_RESOLVED_AFTER_REOPEN
    if "add_component_same_name_elsewhere" in records:     # extras
        assert decided["same_name_elsewhere_inserted"] is findings.SAME_NAME_ELSEWHERE_INSERTED
        clash = facts(records, "add_component_same_name_elsewhere")["same_name_open"]
        assert clash["returned"] is False and clash["errors"] == findings.SAME_NAME_OPEN_ERROR
    if "interference_components" in records:
        entries = facts(records, "interference_components")["interference_entries"]
        assert decided["interference_names_route"] == findings.INTERFERENCE_NAMES_ROUTE
        assert [e["names"] for e in entries] == [["Probe W7 Clash A-1", "Probe W7 Clash B-1"]]
