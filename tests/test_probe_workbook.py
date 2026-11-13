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
          "add_component_opened_part", "layout_plane_negative_global", "interference_components",
          "add_component_same_name_elsewhere"]
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
    # The scaffolding it stands on, and nothing from tier 5 or the bevel and helical probes.
    assert {"attach", "templates", "equation_add", "ref_plane_offset", "nonparallel_mates", "save_as"} <= set(chosen)
    assert not any(p.tier == 5 for p in registry if p.name in chosen)
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
