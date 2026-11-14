"""Probe tier 7 (PLAN-WORKBOOK §4.2) on Linux: its registration, its pure measurements, and its decisions.

Nothing here has run on SolidWorks; what SolidWorks does is the probe's to find.
These pin what the probe makes of a measurement and how its results become
decisions, so a run on the host is read the way the plan says.
"""

import math

import pytest

from gear_generator import swcom
from gear_generator.probe import __main__ as probe_main
from gear_generator.probe import decide, harness
from gear_generator.probe import p7_workbook as p7

TIER_7 = ["layout_planes", "axis_through_named_planes", "axis_through_base_planes", "layout_assembly_five",
          "layout_assembly_reopen", "open_and_activate_part", "open_part_from_assembly", "layout_part_without_body",
          "add_component_opened_part", "assembly_rebuild_scope", "layout_plane_negative_global",
          "interference_components", "add_component_same_name_elsewhere"]
EXTRAS = ["layout_plane_negative_global", "interference_components", "add_component_same_name_elsewhere"]
REQUIRED = [name for name in TIER_7 if name not in EXTRAS]


@pytest.fixture(scope="module")
def registry():
    probe_main.load_probes()
    return list(harness.REGISTRY)


def records(passing=(), failing=(), facts=None):
    out = {name: {"status": "pass", "facts": {}} for name in passing}
    out.update({name: {"status": "fail", "facts": {}} for name in failing})
    for name, values in (facts or {}).items():
        out.setdefault(name, {"status": "pass", "facts": {}})["facts"].update(values)
    return out


# -- registration -----------------------------------------------------------


def test_tier_seven_is_registered_in_the_plans_order_with_the_extra_last(registry):
    # The registry's order is import order: load_probes imports p7_workbook last, so on the host
    # tier 7 runs after everything else and its extra after the rest of it.
    names = [p.name for p in registry if p.tier == 7]
    assert names == TIER_7
    assert [p.name for p in registry if p.tier == 7 and p.extra] == EXTRAS
    assert names[-len(EXTRAS):] == EXTRAS


def test_every_tier_seven_need_is_a_registered_probe(registry):
    known = {p.name for p in registry}
    for p in registry:
        if p.tier == 7:
            assert set(p.needs) <= known, p.name
            assert p.members and p.doc, p.name


def test_running_tier_seven_alone_pulls_in_only_what_it_needs(registry):
    only = [p.name for p in registry if p.tier == 7 and not p.extra]
    chosen = [p.name for p in harness.select(registry, only)]
    assert [n for n in chosen if n in TIER_7] == REQUIRED
    # The scaffolding it stands on; from tier 5 only the spur build that assembly_rebuild_scope builds its
    # gearboxes with, and nothing from the bevel and helical probes.
    assert {"attach", "templates", "equation_add", "ref_plane_offset", "nonparallel_mates", "save_as"} <= set(chosen)
    assert [p.name for p in registry if p.name in chosen and p.tier == 5] == ["end_to_end"]
    assert "sweep_twist" not in chosen and "revolve" not in chosen


def test_only_tier_selects_the_tier_and_stops_before_solidworks(monkeypatch, capsys):
    monkeypatch.setattr(swcom, "is_available", lambda: False)
    monkeypatch.setattr(swcom, "unavailable_reason", lambda: "not here")
    assert probe_main.main(["--only-tier", "7"]) == swcom.EXIT_NOT_AVAILABLE
    assert probe_main.main(["--only-tier", "9"]) == probe_main.EXIT_FINDINGS
    assert "no probes in tier 9" in capsys.readouterr().out


# -- pure measurements --------------------------------------------------------


def test_the_plus_flip_is_read_off_where_each_flip_put_the_plane():
    assert p7.plus_flip({"False": 7.0, "True": -7.0}) is False
    assert p7.plus_flip({"False": -7.0, "True": 7.0}) is True


def test_a_pair_that_is_not_one_offset_mirrored_decides_nothing():
    assert p7.plus_flip({"False": 7.0, "True": 7.0}) is None          # flip did nothing
    assert p7.plus_flip({"False": 0.007, "True": -0.007}) is None    # metres read as mm
    assert p7.plus_flip({"False": 7.0}) is None                      # one flip failed


def test_an_axis_is_read_as_where_it_crosses_the_front_plane():
    # Two points in metres on the line x = 20, y = -8 mm, along -Z.
    (x, y), direction = p7.axis_crossing([0.020, -0.008, 0.05, 0.020, -0.008, -0.01])
    assert (x, y) == pytest.approx((20.0, -8.0), abs=1e-12)
    assert direction == pytest.approx((0.0, 0.0, -1.0))
    assert p7.along_z(direction)


def test_a_tilted_axis_crosses_where_it_crosses_and_is_not_along_z():
    (x, y), direction = p7.axis_crossing([0.0, 0.0, 0.0, 0.01, 0.0, 0.01])
    assert (x, y) == pytest.approx((0.0, 0.0), abs=1e-12) and not p7.along_z(direction)


def test_an_axis_in_the_front_plane_or_of_one_point_is_refused():
    with pytest.raises(ValueError, match="lies in the Front plane"):
        p7.axis_crossing([0.0, 0.0, 0.0, 0.01, 0.0, 0.0])
    with pytest.raises(ValueError, match="same point"):
        p7.axis_crossing([0.01, 0.0, 0.0, 0.01, 0.0, 0.0])


def test_a_moved_shaft_keeps_its_side_of_each_base_plane():
    assert p7.moved_away(20.0, 12.0) == (26.0, 9.0)
    assert p7.moved_away(-15.0, 30.0) == (-21.0, 27.0)
    assert p7.moved_away(35.0, -8.0) == (41.0, -5.0)


def test_every_named_shaft_and_its_move_stay_off_the_base_planes():
    # A shaft that crossed zero would need the other flip, which item 3 says is a structural change.
    for _shaft, x, y in p7.NAMED_SHAFTS:
        mx, my = p7.moved_away(x, y)
        assert x * mx > 0 and y * my > 0


def test_instances_of_one_part_are_grouped_by_their_stem():
    grouped = p7.instance_stems(["Probe W7 Layout-1", "Probe W7 C-1", "Probe W7 C-2", "Odd"])
    assert grouped == {"Probe W7 Layout": ["Probe W7 Layout-1"], "Probe W7 C": ["Probe W7 C-1", "Probe W7 C-2"],
                       "Odd": ["Odd"]}


def test_a_re_placed_gear_turns_about_its_own_axis_even_on_minus_z():
    flipped = p7.COMPONENTS[-1][1]
    again = p7.turned(flipped, 7.0)
    axis = [again[i][2] for i in range(3)]
    assert axis == pytest.approx([0.0, 0.0, -1.0], abs=1e-12)      # still on -Z
    x_before = [flipped[i][0] for i in range(3)]
    x_after = [again[i][0] for i in range(3)]
    assert math.degrees(math.acos(sum(a * b for a, b in zip(x_before, x_after)))) == pytest.approx(7.0)


def test_the_assembly_has_five_components_one_part_twice():
    stems = [stem for stem, _m, _at in p7.COMPONENTS]
    assert len(stems) >= 5 and len(set(stems)) == len(stems) - 1 and stems[0] == p7.LAYOUT_STEM


def test_what_goes_in_the_report_is_plain_json():
    class Com:
        def __repr__(self):
            return "<COMObject>"

    assert p7.plain({"a": (1, Com()), 2: None}) == {"a": [1, "<COMObject>"], "2": None}


# -- decisions --------------------------------------------------------------


LAYOUT = tuple(decide.WORKBOOK_LAYOUT_NEEDS)


def test_the_layout_is_built_only_when_items_one_to_four_all_pass():
    assert decide.workbook_layout_route(records(LAYOUT)) == "layout"
    for name in LAYOUT:
        rest = tuple(n for n in LAYOUT if n != name)
        assert decide.workbook_layout_route(records(rest, failing=(name,))) == "STOP", name
        assert decide.workbook_layout_route(records(rest)) == "STOP", name     # not run is not passed


def test_update_opens_the_part_only_when_item_five_passed_and_asks_otherwise():
    assert decide.update_open_route(records(("open_and_activate_part",))) == "open and activate"
    assert decide.update_open_route(records(failing=("open_and_activate_part",))) == "ask"
    assert decide.update_open_route({}) == "ask"


def test_tier_seven_facts_become_decisions_only_off_a_pass():
    facts = {
        "layout_planes": {"layout_plus_flip": {"right": False, "top": False}, "negated_global_link_form": "minus"},
        "axis_through_named_planes": {"axis_plane_select_route": "SelectByID2 by name"},
        "layout_assembly_reopen": {"component_find_route": "GetComponentByName", "replace_fixed_route": "Transform2 put",
                                   "open_assembly_route": "OpenDoc6"},
        "open_and_activate_part": {"open_doc_route": "OpenDoc6", "open_doc_makes_active": True},
        "layout_plane_negative_global": {"crosses_zero": False},
    }
    passed = decide.decide(records(("axis_through_base_planes", "open_part_from_assembly"), facts=facts))
    assert passed["layout_plus_flip"] == {"right": False, "top": False}
    assert passed["layout_negated_link"] == "minus"
    assert passed["axis_plane_select_route"] == "SelectByID2 by name"
    assert passed["axis_through_base_plane"] is True
    assert (passed["component_find_route"], passed["replace_fixed_route"], passed["open_assembly_route"]) == \
        ("GetComponentByName", "Transform2 put", "OpenDoc6")
    assert (passed["open_doc_route"], passed["open_doc_makes_active"]) == ("OpenDoc6", True)
    assert passed["open_part_beside_assembly"] is True
    assert passed["offset_global_crosses_zero"] is False
    assert passed["update_open_route"] == "open and activate"

    failed = records(failing=tuple(facts) + ("axis_through_base_planes", "open_part_from_assembly"))
    for name, values in facts.items():
        failed[name]["facts"].update(values)
    decided = decide.decide(failed)
    for key in ("layout_plus_flip", "layout_negated_link", "axis_plane_select_route", "axis_through_base_plane",
                "component_find_route", "replace_fixed_route", "open_assembly_route", "open_doc_route",
                "open_doc_makes_active", "open_part_beside_assembly", "offset_global_crosses_zero"):
        assert decided[key] is None, key
    assert decided["workbook_layout_route"] == "STOP" and decided["update_open_route"] == "ask"


def test_with_nothing_run_tier_seven_stops_the_layout_and_asks_for_the_part():
    decided = decide.decide({})
    assert decided["workbook_layout_route"] == "STOP"
    assert decided["update_open_route"] == "ask"
    for key in ("layout_plus_flip", "axis_plane_select_route", "component_find_route", "open_doc_route"):
        assert decided[key] is None, key


def test_a_global_is_found_by_its_name_whatever_the_spacing():
    # Probe fault found on the first run (SolidWorks 2026): a name with spaces was never found.
    assert p7._names_global('"Probe S1 X" = 7', "Probe S1 X")
    assert p7._names_global('"Probe S1 X"= 23', "Probe S1 X")
    assert not p7._names_global('"Probe S1 X Plane"= 7', "Probe S1 X")
    assert not p7._names_global('"Offset@Probe S1 X Plane"= "Probe S1 X"', "Probe S1 X")


def test_the_new_tier_seven_decisions_come_off_a_pass_only():
    reopened = {"suppression_after_reopen": {"A-1": 2, "B-1": 2}}
    passed = decide.decide(records(facts={
        "layout_assembly_reopen": reopened,
        "add_component_opened_part": {"reuse_add_route": "closed"},
        "interference_components": {"interference_components_route": "Components (property)"},
        "add_component_same_name_elsewhere": {"same_name_elsewhere": {"inserted": False}},
    }))
    assert passed["components_resolved_after_reopen"] is True
    assert passed["reuse_add_route"] == "closed"
    assert passed["interference_names_route"] == "Components (property)"
    assert passed["same_name_elsewhere_inserted"] is False
    light = decide.decide(records(facts={"layout_assembly_reopen": {"suppression_after_reopen": {"A-1": 1}}}))
    assert light["components_resolved_after_reopen"] is False
    for key in ("components_resolved_after_reopen", "reuse_add_route", "interference_names_route",
                "same_name_elsewhere_inserted"):
        assert decide.decide({})[key] is None, key


def test_a_body_less_layout_part_is_one_of_the_layouts_needs():
    assert "layout_part_without_body" in decide.WORKBOOK_LAYOUT_NEEDS


# -- item 6: which assembly rebuild Update SolidWorks uses ---------------------------


FLAGS_PUT = {"assembly": True, "layout": False, "G1": False, "G2": False}
FLAGS_LAYOUT = dict(FLAGS_PUT, layout=True)
FLAGS_PART = dict(FLAGS_LAYOUT, G2=True)
EVERY = {name: True for name in p7.REBUILD_DOCS}


def good_case():
    """What a route that meets every criterion leaves in its case."""
    return {
        "flags_on_open": {name: False for name in p7.REBUILD_DOCS},
        "put": {"frame_shown": True, "clash_shown": True, "flags": FLAGS_PUT, "flags_after_reads": FLAGS_PUT},
        "put_back": {"clean": True, "flags": FLAGS_PUT, "flags_after_reads": FLAGS_PUT},
        "layout": {"shown": True, "flags": FLAGS_LAYOUT, "flags_after_reads": FLAGS_LAYOUT},
        "part": {"shown": True, "flags": FLAGS_PART, "flags_after_reads": FLAGS_PART},
        "failure": {"part_failed": True, "rebuild": {"returned": False}, "flags": FLAGS_PART,
                    "flags_after_reads": FLAGS_PART},
    }


def test_the_rebuild_probe_is_tier_seven_and_needs_the_reopen_and_the_end_to_end_build(registry):
    found = next(p for p in registry if p.name == "assembly_rebuild_scope")
    assert (found.tier, found.extra, found.needs) == (7, False, ("layout_assembly_reopen", "end_to_end"))
    assert p7.REBUILD_ROUTES == decide.ASSEMBLY_REBUILD_ROUTES and len(p7.REBUILD_FOLDERS) == len(p7.REBUILD_ROUTES)
    assert p7.REBUILD_ROUTES[-1] == "none"          # tried, to see whether a put needs a rebuild, and never chosen first


def test_marked_as_wanted_means_exactly_the_documents_changed_on_purpose():
    assert p7.marked_as_wanted(FLAGS_PUT, ("assembly",)) is True
    assert p7.marked_as_wanted(EVERY, ("assembly",)) is False                    # the fault the W4 rerun found
    assert p7.marked_as_wanted(dict(FLAGS_PUT, assembly=False), ("assembly",)) is False   # a change not marked
    assert p7.marked_as_wanted(dict(FLAGS_PUT, G1=None), ("assembly",)) is None  # a document not in memory
    assert p7.marked_as_wanted({}, ("assembly",)) is None


def test_a_route_meeting_every_criterion_is_chosen():
    verdict = p7.rebuild_verdict(good_case())
    assert set(verdict) == set(p7.REBUILD_CRITERIA) and all(v is True for v in verdict.values())
    assert p7.rebuild_route({"EditRebuild3": good_case(), "ForceRebuild3(True)": good_case()}) == "ForceRebuild3(True)"


def test_each_criterion_alone_can_rule_a_route_out():
    breaks = {
        "frame_after_put": lambda c: c["put"].update(frame_shown=False),
        "interference_after_put": lambda c: c["put_back"].update(clean=False),
        "layout_move_shown": lambda c: c["layout"].update(shown=False),
        "part_change_shown": lambda c: c["part"].update(shown=None),
        "failure_reported": lambda c: c["failure"].update(rebuild={"returned": True}),
        "only_changed_marked": lambda c: c["part"].update(flags_after_reads=EVERY),
    }
    for criterion, spoil in breaks.items():
        case = good_case()
        spoil(case)
        verdict = p7.rebuild_verdict(case)
        assert verdict[criterion] is not True, criterion
        assert [k for k, v in verdict.items() if v is not True] == [criterion], criterion
        assert p7.rebuild_route({"ForceRebuild3(True)": case}) == "STOP", criterion


def test_no_rebuild_at_all_never_reports_a_failure_and_a_part_that_did_not_fail_decides_nothing():
    case = good_case()
    case["failure"]["rebuild"] = {"returned": None}               # route "none"
    assert p7.rebuild_verdict(case)["failure_reported"] is False
    case["failure"] = {"part_failed": False}
    assert p7.rebuild_verdict(case)["failure_reported"] is None
    assert p7.rebuild_verdict({})["only_changed_marked"] is None


def test_the_rebuild_route_is_decided_off_a_pass_only_and_otherwise_stops():
    verdicts = {"ForceRebuild3(True)": dict.fromkeys(p7.REBUILD_CRITERIA, True),
                "ForceRebuild3(False)": dict(dict.fromkeys(p7.REBUILD_CRITERIA, True), only_changed_marked=False)}
    facts = {"assembly_rebuild_scope": {"rebuild_verdicts": verdicts, "put_needs_rebuild": False,
                                        "full_rebuild_marks_components_modified": True,
                                        "opened_reads_unmodified": True}}
    passed = decide.decide(records(facts=facts))
    assert passed["assembly_rebuild_route"] == "ForceRebuild3(True)"
    assert passed["assembly_rebuild_keeps_components_unmodified"] is True
    assert (passed["put_needs_rebuild"], passed["full_rebuild_marks_components_modified"]) == (False, True)
    assert passed["opened_reads_unmodified"] is True
    failed = records(failing=("assembly_rebuild_scope",))
    failed["assembly_rebuild_scope"]["facts"].update(facts["assembly_rebuild_scope"])
    decided = decide.decide(failed)
    assert decided["assembly_rebuild_route"] == "STOP"
    for key in ("assembly_rebuild_keeps_components_unmodified", "put_needs_rebuild",
                "full_rebuild_marks_components_modified", "opened_reads_unmodified"):
        assert decided[key] is None, key
    only_full = {"ForceRebuild3(False)": verdicts["ForceRebuild3(False)"]}
    assert decide.first_rebuild_route(only_full) == "STOP"
    assert decide.decide({})["assembly_rebuild_route"] == "STOP"


def test_the_rebuild_gearbox_lays_out_with_the_app_and_its_g2_is_where_the_probe_moves_it():
    from gear_generator.workbook import assess as wb_assess
    from gear_generator.workbook import gearbox as wb_gearbox

    spec = p7.rebuild_spec(1, "C:\\probe\\rebuild\\edit")
    assert spec.box.output_folder == "C:\\probe\\rebuild\\edit\\"
    assessed = wb_assess.assess(spec, [], spec.box.output_folder, "")
    assert assessed.lay_out_refusal() == ""
    plan = wb_gearbox.plan_gearbox(assessed, None)
    assert not plan.refusal
    assert sorted(job.gear_ids[0] for job in plan.build) == ["G1", "G2"]
    assert all("Probe W7 Rebuild 2" in job.stem for job in plan.build)       # names of their own, route by route
    s2 = next(s for s in plan.shafts if s.shaft == "S2")
    assert (s2.x, s2.x_global, s2.axis_name) == (p7.REBUILD_CENTRE, "S2 X", "S2 Axis")
    assert plan.frames["G2"].at == pytest.approx((p7.REBUILD_CENTRE, 0.0, 0.0))
    matrix = p7.rows_matrix(plan.frames["G2"].rotation)
    assert [matrix[i][2] for i in range(3)] == pytest.approx([0.0, 0.0, 1.0])
