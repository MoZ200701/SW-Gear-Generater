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
from gear_generator.probe import p8_motion as p8

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
    if "units_2026_folder" in units:
        assert units["units_2026_folder"] == {"linear": findings.LENGTH_MM, "system": findings.UNIT_SYSTEM_MMGS,
                                              "path": units["units_2026_folder"]["path"]}
    else:
        # On the machine of the 34.1.1 run the default template IS the 2026 folder's Part.PRTDOT, so the probe read
        # it once, as the default: millimetres, with the unit system that template carries there (4, custom).
        assert units["units_default"]["path"].lower().endswith(r"solidworks 2026\templates\part.prtdot")
        assert units["units_default"]["linear"] == findings.LENGTH_MM
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


# -- tier 8, on both versions: W5's motion must work on 2024 and 2026 alike

# The 2024 tier-8 run, in the user's freshly restarted session; sw2024/latest.json stays the last FULL 2024 run.
SW2024_TIER8 = LATEST.parent / "sw2024" / "probe-results-20261113-223412.json"


@pytest.fixture(scope="module", params=["2026", "2024"])
def tier_eight(request):
    path = LATEST if request.param == "2026" else SW2024_TIER8
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["meta"]["version"].startswith(f"SolidWorks {request.param} ")
    records = {r["name"]: r for r in data["records"]}
    return records, decide.decide(records), request.param


def test_motion_route_and_its_enums(tier_eight):
    """Tier 8 (PLAN-WORKBOOK §4.4): PLAN-GEARBOX tier 6 items 3-5 passed, so W5 builds the gearbox to turn."""
    records, decided, _version = tier_eight
    assert decided["motion_route"] == findings.MOTION_ROUTE
    for name in decide.MOTION_NEEDS + ("motion_enums", "motion_update"):
        assert records[name]["status"] == "pass", name
    values = facts(records, "motion_enums")["motion_enum_values"]
    assert (values["concentric"], values["lock"]) == (findings.MATE_CONCENTRIC, findings.MATE_LOCK)
    assert (values["aligned"], values["anti_aligned"], values["closest"]) == \
        (findings.MATE_ALIGN_ALIGNED, findings.MATE_ALIGN_ANTI_ALIGNED, findings.MATE_ALIGN_CLOSEST)
    assert values["no_error"] == findings.ADD_MATE_NO_ERROR


def test_a_gear_held_on_its_layout_axis(tier_eight):
    """Probe shaft_axis_mates: Gear Axis coincident with the layout axis; origin a distance from the layout's Front."""
    records, decided, _version = tier_eight
    axes = facts(records, "shaft_axis_mates")
    assert decided["axis_mate_route"] == findings.AXIS_MATE_ROUTE
    assert decided["axis_concentric_refused"] is findings.AXIS_CONCENTRIC_REFUSED
    assert decided["axial_mate_route"] == findings.AXIAL_MATE_ROUTE
    assert axes["axis_cases_holding"] == {"g1": True, "g2": True, "g3": False, "g4": False, "g5": True, "g6": True}
    assert axes["axial_cases_holding"] == {"g1": True, "g2": True, "g3": True, "g4": True, "g5": False, "g6": False}
    assert all(r["status"] == 0 for r in axes["axis_mates_refused"].values())
    assert all(v["turned_over"] for v in axes["explicit_alignment"].values())
    assert all(axes["closest_keeps_the_side"].values())
    reopened = axes["axis_reopened"]
    assert not reopened["errors_on_open"] and not reopened["errors_after_rebuild"]
    entities = axes["axis_mate_entities"]
    assert (entities["g1 axis"]["alignment"], entities["g2 axis"]["alignment"]) == (0, 1)


def test_the_gear_mate_turns_its_gears_the_way_they_mesh(tier_eight):
    """Probe gear_mate_sense: Flip False is the mesh's own sense on every pair, so every listed mesh takes it."""
    records, decided, _version = tier_eight
    sense = facts(records, "gear_mate_sense")
    assert decided["gear_mate_flip_rule"] == findings.GEAR_MATE_FLIP_RULE
    assert sense["sense_rules_consistent"] == sense["sense_rules_consistent_with_faces_too"] == ["mesh"]
    assert decided["gear_mate_sense_depends_on_entities"] is False
    assert sense["alignment_changes_sense"] is False and sense["kept_reverse_follows_the_axes"] is True
    for case in sense["sense_cases"]:
        assert case["turned_by_ratio"], case["name"]
        if not case["placement"]:
            assert case["world_same"] is (case["internal"] != case["flip"]), case["name"]
    # Where it stops: a pinion inside a ring's bore but clear of its face is read as outside it.
    assert sense["sense_boundary_cases"]["ring ++ F apart"]["world_same"] is False
    from gear_generator.probe.p8_motion import needed_flip
    for sa in (1, -1):
        for sb in (1, -1):
            for internal in (False, True):
                assert needed_flip(findings.GEAR_MATE_FLIP_RULE, sa, sb, internal) is findings.GEAR_MATE_FLIP
    assert sense["gear_mate_on_layout_axes"]["mate"]["name"] is None


def test_compound_gears_are_locked_and_an_over_definition_shows(tier_eight):
    """Probe compound_lock: a lock alone holds the placed angle; a conflicting mate is made but shows in four ways."""
    records, decided, version = tier_eight
    lock = facts(records, "compound_lock")
    assert decided["compound_lock_route"] == findings.COMPOUND_LOCK_ROUTE
    holding = lock["lock_holding"]
    for name in ("lock alone", "lock alone, Z-", "angle 37", "angle 137"):
        assert holding[name]["held"] and holding[name]["no_errors"], name
    # The codes differ by version (2026: 46 for a redundant mate, 47 for the one at fault; 2024: 51 for both),
    # the warning flag does not: the mate at fault is the one that is not a warning.
    redundant = findings.MATE_ERROR_OVER_DEFINED if version == "2026" else findings.MATE_ERROR_2024
    at_fault = findings.MATE_ERROR_ILL_DEFINED if version == "2026" else findings.MATE_ERROR_2024
    for name in ("lock, both on the shaft", "lock, both on the shaft, Z-"):          # held, but over-defined
        assert holding[name]["held"] and not holding[name]["no_errors"], name
        assert redundant in [e["code"] for e in holding[name]["errors"].values()]
        assert all(e["warning"] for e in holding[name]["errors"].values())
    over = lock["over_defined"]
    assert over["mate"]["status"] == findings.ADD_MATE_OVER_DEFINED and over["mate"]["name"]   # made all the same
    fault = over["errors"][over["mate"]["name"]]
    assert fault["code"] == at_fault and fault["warning"] is False
    assert all(e["warning"] for n, e in over["errors"].items() if n != over["mate"]["name"])
    assert over["constrained"]["q"] == findings.COMPONENT_OVER_DEFINED
    assert over["rebuild"]["returned"] is True                                                  # the rebuild says nothing
    assert over["mate"]["name"] not in over["errors_after_delete"]


def test_the_twelve_to_one_train_mated_from_w4s_state(tier_eight):
    """Probe mated_train: nine components, no jump, output 1/12 the same way, one degree of freedom, kept on reopen."""
    records, decided, _version = tier_eight
    train = facts(records, "mated_train")
    assert train["train_right_way"] == {"all Z+": True, "middle Z-": True}
    t = train["train"]
    assert t["components"] == 9 and t["rule"] == findings.GEAR_MATE_FLIP_RULE
    assert t["lock"] == findings.COMPOUND_LOCK_ROUTE
    for name, turns in list(t["turns"].items()) + list(t["reopened"]["turns"].items()):
        values = [turns[k] for k in sorted(turns)]
        assert values[0] == pytest.approx(30.0) and values[3] / values[0] == pytest.approx(1 / 12), name
    assert train["one_drive_fully_defines_the_train"] is True
    assert set(t["constrained_mated"].values()) == {findings.COMPONENT_UNDER_DEFINED}
    assert set(t["constrained_driven"].values()) == {findings.COMPONENT_FULLY_DEFINED}
    assert train["put_turns_a_gear_mated_gear_alone"] is True
    assert max(max(v.values()) for v in t["jumps_after_mating"].values()) < 1e-6


def test_update_after_motion(tier_eight):
    """Probe motion_update: the layout's globals carry the mated gears; a put with the gear mate on re-phases it."""
    records, decided, _version = tier_eight
    assert decided["layout_move_carries_mates"] is findings.LAYOUT_MOVE_CARRIES_MATES
    assert decided["mesh_phase_route"] == findings.MESH_PHASE_ROUTE
    assert decided["lock_unsuppress_keeps_the_new_angle"] is findings.LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE
    assert decided["axial_global_moves_gear"] is findings.AXIAL_GLOBAL_MOVES_GEAR
    move = facts(records, "motion_update")["turn_on_a_shaft_move"]
    assert move["as_a_multiple_of_the_need"] == pytest.approx(-1.0)          # SolidWorks turns it the wrong way


# -- tier 7, item 6, on both versions: which rebuild Update SolidWorks gives an assembly

# assembly_rebuild_scope and what it needs on 2024, in a SolidWorks started for the run.
SW2024_REBUILD = LATEST.parent / "sw2024" / "probe-results-20261114-014813.json"


@pytest.fixture(scope="module", params=["2026", "2024"])
def rebuild_scope(request):
    path = LATEST if request.param == "2026" else SW2024_REBUILD
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["meta"]["version"].startswith(f"SolidWorks {request.param} ")
    records = {r["name"]: r for r in data["records"]}
    return records, decide.decide(records)


def test_the_assembly_rebuild_route(rebuild_scope):
    """Probe assembly_rebuild_scope: a top-only rebuild shows every change, reports a failure and marks only what changed."""
    records, decided = rebuild_scope
    scope = facts(records, "assembly_rebuild_scope")
    assert decided["assembly_rebuild_route"] == findings.ASSEMBLY_REBUILD_ROUTE
    assert findings.ASSEMBLY_REBUILD_ROUTE == f"ForceRebuild3({findings.ASSEMBLY_REBUILD_TOP_ONLY})"
    assert decided["assembly_rebuild_keeps_components_unmodified"] is findings.ASSEMBLY_REBUILD_KEEPS_COMPONENTS_UNMODIFIED
    assert decided["full_rebuild_marks_components_modified"] is findings.FULL_ASSEMBLY_REBUILD_MARKS_COMPONENTS_MODIFIED
    assert decided["put_needs_rebuild"] is findings.PUT_NEEDS_REBUILD
    assert decided["opened_reads_unmodified"] is findings.OPENED_READS_UNMODIFIED
    verdicts = scope["rebuild_verdicts"]
    # What shows does not depend on the route, not even on rebuilding at all.
    for route, verdict in verdicts.items():
        for criterion in ("frame_after_put", "interference_after_put", "layout_move_shown", "part_change_shown"):
            assert verdict[criterion] is True, (route, criterion)
    # What is marked and reported does.
    assert all(verdicts[r]["only_changed_marked"] and verdicts[r]["failure_reported"]
               for r in ("ForceRebuild3(True)", "EditRebuild3"))
    assert verdicts["ForceRebuild3(False)"]["only_changed_marked"] is False
    assert verdicts["none"]["failure_reported"] is False
    marked = scope["rebuild_marked"]
    assert marked["ForceRebuild3(False)"]["put"] == ["assembly", "layout", "G1", "G2"]
    assert (marked["none"]["put"] == ["assembly"]) is findings.PUT_MARKS_ASSEMBLY_MODIFIED
    cases = scope["rebuild_cases"]
    for route in ("ForceRebuild3(True)", "EditRebuild3", "ForceRebuild3(False)"):
        failure = cases[route]["failure"]
        assert failure["how"] == "Bore Diameter = 500" and failure["rebuild"]["returned"] is False, route
        assert failure["restored"]["rebuild"]["returned"] is True, route
        assert cases[route]["layout"]["measure"]["Distance_mm"] == pytest.approx(68.75)
        assert cases[route]["layout"]["measure_before"]["Distance_mm"] == pytest.approx(63.75)
    width = cases["ForceRebuild3(True)"]["failure"]["tried"][0]
    assert width["global"] == "Face Width" and width["part_rebuild"] is True and width["part_errors"] == {}


# -- packages P0 and P0b (W5-PLAN §0.3, its review's M4 and M5, the mated rebuild, the rulings), on both versions

# Items 7-14 and what they need on 2024, as round P0b left them, in a SolidWorks started fresh for them.
SW2024_P0 = LATEST.parent / "sw2024" / "probe-results-20261114-071324.json"
# gear_mate_definition alone on 2024, in another fresh SolidWorks (it strands what it changes there).
SW2024_DEFINITION = LATEST.parent / "sw2024" / "probe-results-20261114-073328.json"
# P0's first runs, kept: 2026's full run of 388c8d3, and 2024's beside an assembly the definition route stranded.
FIRST_2026 = LATEST.parent / "probe-results-20261114-034458.json"
FIRST_2024 = LATEST.parent / "sw2024" / "probe-results-20261114-040636.json"


def _records(path):
    return {r["name"]: r for r in json.loads(path.read_text(encoding="utf-8"))["records"]}


@pytest.fixture(scope="module", params=["2026", "2024"])
def package_p0(request):
    path = LATEST if request.param == "2026" else SW2024_P0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["meta"]["version"].startswith(f"SolidWorks {request.param} ")
    records = {r["name"]: r for r in data["records"]}
    return records, decide.decide(records), request.param


def test_the_six_values_w5_takes_from_tier_eights_records(tier_eight, package_p0):
    """W5-PLAN §0.3: read off motion_enums, motion_update and compound_lock, the same in every file."""
    for records, decided, _version in (tier_eight, package_p0):
        assert (decided["feature_suppress"], decided["feature_unsuppress"], decided["this_configuration"]) == \
            (findings.FEATURE_SUPPRESS, findings.FEATURE_UNSUPPRESS, findings.THIS_CONFIGURATION)
        assert decided["suppression_route"] == findings.SUPPRESSION_ROUTE
        assert decided["lock_select_route"] == findings.LOCK_SELECT_ROUTE
        assert decided["mate_delete_route"] == findings.MATE_DELETE_ROUTE
        assert facts(records, "motion_update")["motion_update"]["lock_moved"]["unsuppressed_by"] == \
            findings.SUPPRESSION_ROUTE


# gear_mate_ratio as it now runs (both routes, each copy's close recorded), alone with what it needs, on each version.
RATIO_2026 = LATEST.parent / "probe-results-20261114-052417.json"
RATIO_2024 = LATEST.parent / "sw2024" / "probe-results-20261114-051023.json"


@pytest.fixture(scope="module", params=["2026", "2024"])
def gear_ratio(request):
    path = RATIO_2026 if request.param == "2026" else RATIO_2024
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["meta"]["version"].startswith(f"SolidWorks {request.param} ")
    records = {r["name"]: r for r in data["records"]}
    return records, decide.decide(records), request.param


def test_a_saved_gear_mates_ratio_two_routes_and_the_versions_split(gear_ratio):
    """Probe gear_mate_ratio: the definition changes the ratio on both versions (its counts put in AddMate5's order,
    read back reversed), but on 2024 that copy cannot be closed; a remade gear mate works and closes on both. The
    versions decided differently then; round P0b settled it (the remake, after P1b)."""
    records, decided, version = gear_ratio
    ratio = facts(records, "gear_mate_ratio")
    tries = {t["how"]: t for t in ratio["gear_mate_ratio"]["tries"]}
    assert list(tries) == [p8.RATIO_CROSSED, "remake"]
    crossed_over = tries[p8.RATIO_CROSSED]
    assert crossed_over["definition"]["fields"] == {"GearRatioNumerator": 17.0, "GearRatioDenominator": 60.0}
    assert crossed_over["definition"]["before"]["GearRatioNumerator"] == 51.0
    assert crossed_over["definition"]["after"]["GearRatioNumerator"] == 60.0
    assert findings.GEAR_MATE_RATIO_PUT_NUMERATOR_FIRST is True
    assert ratio["definition_numerator_is_second_teeth"] is findings.GEAR_MATE_DEFINITION_READS_NUMERATOR_SECOND
    for how, attempt in tries.items():
        assert attempt["right"] is True, how
        assert attempt["turns_before"]["TG4"] == pytest.approx(2.5)
        assert attempt["turns"]["TG4"] == pytest.approx(30 * 17 / 68 * 17 / 60), how
    closes = ratio["gear_mate_ratio_closes"]
    assert closes["remake"] is True and ratio["gear_mate_ratio_routes"]["remake"] is findings.GEAR_MATE_RATIO_REMAKE_WORKS
    assert closes[p8.RATIO_CROSSED] is (True if version == "2026" else findings.MODIFIED_GEAR_MATE_CLOSES_ON_2024)
    # What that version of the item decided; decide now also needs P1b (gear_mate_update), which these files lack.
    assert ratio["gear_mate_ratio_route"] == ("modify definition" if version == "2026" else "remake")
    assert decided["gear_mate_ratio_route"] is None


@pytest.mark.parametrize("version", ["2026", "2024"])
def test_the_first_runs_of_gear_mate_ratio_on_2026_and_2024(version):
    """The full runs' gear_mate_ratio, recipes in their first order: on 2026 the first two inverted the ratio and the
    third was right; on 2024 the first one's copy could not be closed, so the item failed and decided nothing."""
    records = _records(FIRST_2026 if version == "2026" else FIRST_2024)
    decided = decide.decide(records)
    if version == "2024":
        assert records["gear_mate_ratio"]["status"] == "fail" and decided["gear_mate_ratio_route"] is None
        assert "CloseDoc" in records["gear_mate_ratio"]["reason"]
        return
    tries = {t["how"]: t for t in facts(records, "gear_mate_ratio")["gear_mate_ratio"]["tries"]}
    assert list(tries) == [p8.RATIO_ALONE, p8.RATIO_AS_READ, p8.RATIO_CROSSED]
    for how in (p8.RATIO_ALONE, p8.RATIO_AS_READ):      # each turned the output 60/17 of its partner, not 17/60
        assert tries[how]["turns"]["TG4"] == pytest.approx(7.5 * 60 / 17) and not tries[how]["right"]
        assert tries[how]["definition"]["after"]["GearRatioNumerator"] == 17.0
    assert tries[p8.RATIO_CROSSED]["right"] is True


def test_a_lock_re_takes_an_offset_along_the_shaft_and_mates_keep_new_names(package_p0):
    """Probes lock_retake_offset and lock_mate_rename."""
    records, decided, _version = package_p0
    assert decided["lock_retakes_an_offset"] is findings.LOCK_RETAKES_AN_OFFSET
    for case in facts(records, "lock_retake_offset")["lock_retake_offset"]["cases"].values():
        for step in ("after_unsuppress", "after_drive"):
            assert case[step]["angle"] == pytest.approx(11.0) and case[step]["along"] == pytest.approx(3.0)
        assert case["anchor_turned"] == pytest.approx(-7.5)
    assert decided["mate_rename_route"] == findings.MATE_RENAME_ROUTE
    assert decided["mate_find_route"] == findings.MATE_FIND_ROUTE
    renamed = facts(records, "lock_mate_rename")["lock_mate_rename"]
    assert all(renamed["reopened"]["old_gone"].values())
    assert {n: s["suppressed"] for n, s in renamed["reopened"]["states"].items()} == {
        "TG3 locked to TG2": False, "TG3 meshes TG4": False, "TG4 on T3 Axis": False, "TG4 along T3": False,
        "UG3 locked to UG2": True}


def test_the_demonstrations_drive_and_a_put_on_a_twice_meshed_gear(package_p0):
    """Probes demonstration_drive and put_on_twice_meshed_gear."""
    records, decided, _version = package_p0
    assert decided["demonstration_drive_holds"] is findings.DEMONSTRATION_DRIVE_HOLDS
    drive = facts(records, "demonstration_drive")
    assert drive["demonstration_drive_sense"] == {"all Z+": findings.DEMONSTRATION_DRIVE_SENSE,
                                                  "middle Z-": findings.DEMONSTRATION_DRIVE_SENSE}
    turns = drive["demonstration_drive"]["turns"]
    assert (turns["TG1"], turns["TG4"]) == (pytest.approx(30.0), pytest.approx(2.5))
    assert decided["put_on_twice_meshed_gear_holds"] is findings.PUT_ON_TWICE_MESHED_GEAR_HOLDS
    twice = facts(records, "put_on_twice_meshed_gear")
    assert twice["lock_on_put_turns"]["TG2"] == pytest.approx(7.0) and twice["lock_on_put_turns"]["TG3"] == 0.0


def test_an_anchor_held_from_a_datum_plane_far_behind_front(package_p0):
    """Probe axial_datum_plane: the distance never reaches zero, so no Flip changes as the gear passes Front."""
    records, decided, _version = package_p0
    assert decided["axial_datum_route"] == findings.AXIAL_DATUM_ROUTE
    assert decided["axial_datum_flip"] is findings.AXIAL_DATUM_FLIP
    datum = facts(records, "axial_datum_plane")["axial_datum_plane"]
    for step in datum["steps"]:
        assert [r["z"] for r in step["read"].values()] == pytest.approx([step["z"]] * 2)
    assert [s["z"] for s in datum["steps"]] == [17.0, 0.0, -5.0, 17.0]
    assert [r["z"] for r in datum["reopened"]["read"].values()] == pytest.approx([8.0, 8.0])


def test_the_rebuild_a_mated_train_needs_to_be_built_and_changed(package_p0):
    """Probe mated_rebuild_scope (P0b): each route built its own train with itself as the only rebuild and changed
    it; the top-only rebuild did everything the full one did, frame for frame, and marked only what changed."""
    records, decided, _version = package_p0
    assert decided["mated_assembly_rebuild_route"] == findings.MATED_ASSEMBLY_REBUILD_ROUTE == findings.ASSEMBLY_REBUILD_ROUTE
    assert decided["mated_rebuild_keeps_components_unmodified"] is findings.MATED_REBUILD_KEEPS_COMPONENTS_UNMODIFIED
    assert decided["mated_build_rebuild_route"] == findings.MATED_BUILD_REBUILD_ROUTE
    assert decided["mated_build_keeps_components_unmodified"] is findings.MATED_BUILD_KEEPS_COMPONENTS_UNMODIFIED
    scope = facts(records, "mated_rebuild_scope")
    assert all(all(v.values()) for v in scope["mated_build_verdicts"].values())
    assert scope["mated_build_marked"]["ForceRebuild3(False)"]["before_save"] == ["layout", "part"]
    assert scope["mated_build_marked"]["ForceRebuild3(True)"]["before_save"] == []
    for route, verdict in scope["mated_rebuild_verdicts"].items():
        for criterion in p8.MATED_EVIDENCE:
            if not (route == "ForceRebuild3(False)" and criterion == "only_changed_marked"):
                assert verdict[criterion] is True, (route, criterion)
        assert verdict["put_held"] is True
        # Shown before any route, so not evidence for one: the layout move, the part change, the mate error.
        assert {c for c in p8.MATED_RECORDED if verdict[c] == p8.BEFORE} == \
            {"layout_shown", "part_shown", "failure_shown", "failure_cleared"}, route
    assert scope["mated_rebuild_verdicts"]["ForceRebuild3(False)"]["only_changed_marked"] is False
    assert all(max(d.values()) < 1e-6 for d in scope["mated_frames_against_reference"].values())
    for case in scope["mated_rebuild_cases"].values():
        assert case["axial"]["before_route_mm"] == 0.0 and case["axial"]["moved_mm"] == pytest.approx(4.0)
        assert case["drive"]["before_route"]["TG1"] == 0.0
        # The P0 file's 2024 differences did not recur in a clean session: the move shows after ActivateDoc3.
        assert case["layout"]["before_activate_mm"] == 0.0 and case["layout"]["before_route_mm"] == pytest.approx(5.0)
        assert case["layout"]["status_before_route"]["IModelDocExtension.NeedsRebuild2"] == 0
    assert all(r["failure"] is True for r in scope["mated_rebuild_returned"].values())


def test_a_tooth_change_is_an_update_by_the_remake(package_p0):
    """Probes gear_mate_ratio (the remake, alone) and gear_mate_update (P1b): GEAR_MATE_RATIO_ROUTE is "remake"."""
    records, decided, _version = package_p0
    assert decided["gear_mate_ratio_route"] == findings.GEAR_MATE_RATIO_ROUTE == "remake"
    assert decided["gear_mate_update_holds"] is findings.GEAR_MATE_UPDATE_HOLDS
    ratio = facts(records, "gear_mate_ratio")
    remade = ratio["gear_mate_ratio"]
    assert remade["turns_before"]["TG4"] == pytest.approx(2.5) and remade["turns"]["TG4"] == pytest.approx(30 * 17 / 68 * 17 / 60)
    assert remade["close"]["closed"] and remade["reopened"]["close"]["closed"]
    assert remade["reopened"]["turns"]["TG4"] == pytest.approx(30 * 17 / 68 * 17 / 60)
    position = ratio["remade_mate_position"]
    assert (position["after"] == position["count"] - 1 and position["before"] < position["after"]) is \
        findings.REMADE_GEAR_MATE_GOES_LAST
    update = facts(records, "gear_mate_update")["gear_mate_update"]
    for label in ("unsaved", "saved"):
        p = update[label]
        assert p8.update_pass_holds(p, update["teeth_after"]), label
        assert p["drive"]["turns"]["G4"] == pytest.approx(30 * 17 / 68 * 18 / 50)
    assert update["unsaved"]["moved_by_the_full_rebuild"] < 1e-6
    assert update["unsaved"]["reopened"]["definition"] == update["definition_saved"]
    assert update["unsaved"]["reopened"]["teeth"] == {"G3": 17.0, "G4": 51.0}
    assert update["saved"]["reopened"]["teeth"] == {"G3": 18.0, "G4": 50.0}
    assert update["saved"]["reopened"]["interference"]["count"] == 0


@pytest.mark.parametrize("version", ["2026", "2024"])
def test_the_definition_route_is_recorded_and_never_chosen(version):
    """Probe gear_mate_definition, last: the right ratio on both versions; on 2024 the copy cannot be closed."""
    records = _records(LATEST if version == "2026" else SW2024_DEFINITION)
    decided = decide.decide(records)
    assert decided["gear_mate_definition_numerator_is_second"] is findings.GEAR_MATE_DEFINITION_READS_NUMERATOR_SECOND
    tries = facts(records, "gear_mate_definition")["gear_mate_definition"]["tries"]
    assert [t["how"] for t in tries] == [p8.RATIO_CROSSED] and tries[0]["right"] is True
    assert tries[0]["definition"]["fields"] == {"GearRatioNumerator": 17.0, "GearRatioDenominator": 60.0}
    assert findings.GEAR_MATE_RATIO_PUT_NUMERATOR_FIRST is True
    assert decided["modified_gear_mate_closes"] is (True if version == "2026" else findings.MODIFIED_GEAR_MATE_CLOSES_ON_2024)
    assert decided["gear_mate_ratio_route"] != "modify definition"


def test_a_lock_after_a_put_and_the_remake_on_a_twice_meshed_gear(package_p0):
    """Probe put_on_twice_meshed_gear (P0b): driven after a put made with the lock on, the pair turns together at
    the angle the put left; the remake on a gear carrying two gear mates holds and is found by name."""
    records, decided, _version = package_p0
    twice = facts(records, "put_on_twice_meshed_gear")
    after = twice["lock_on_put_after_drive"]
    assert after["relative_angle_change"] == pytest.approx(0.0) and not after["errors"]
    assert (after["anchor_turned"] == pytest.approx(after["follower_turned"]) == pytest.approx(-2.5)) is \
        findings.LOCK_RETAKES_AFTER_A_PUT
    assert decided["remake_on_twice_meshed_gear_holds"] is findings.REMAKE_ON_TWICE_MESHED_GEAR_HOLDS
    e = twice["put_on_twice_meshed_gear"]["remake_on_twice_meshed"]
    assert e["mates_after"][-1] == "GearMate2" and e["mates_before"].index("GearMate2") < len(e["mates_before"]) - 1
    assert e["turns"]["UG1"] == pytest.approx(-10 * 17 / 68 * 17 / 60 * 51 / 17)
