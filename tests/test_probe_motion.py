"""Probe tier 8 (PLAN-WORKBOOK §4.4, phase W5) on Linux: its registration, its pure measurements, and its decisions.

What SolidWorks does is the probe's to find; these pin how the probe reads a
measurement — a turn about a gear's own axis and about +Z, the candidate rules
for a gear mate's Flip, the 12 : 1 train's expected turns — and how its results
become decisions, so a run on the host is read the way the plan says.
"""

import math

import pytest

from gear_generator import swcom
from gear_generator.gears import crossed
from gear_generator.probe import __main__ as probe_main
from gear_generator.probe import decide, harness
from gear_generator.probe import p8_motion as p8

TIER_8 = ["motion_enums", "shaft_axis_mates", "gear_mate_sense", "compound_lock", "mated_train", "motion_update",
          "gear_mate_ratio", "gear_mate_update", "idler_update", "lock_retake_offset", "lock_mate_rename", "demonstration_drive",
          "put_on_twice_meshed_gear", "axial_datum_plane", "mated_rebuild_scope", "mates_under_command_in_progress",
          "mate_folders", "lightweight_remake", "second_assembly_beside_unsaved", "gear_mate_definition_read",
          "origin_noise", "unsaved_update_close",
          "drag_operator_turns_train", "gear_mate_definition"]


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


def test_tier_eight_is_registered_after_tier_seven_in_order(registry):
    names = [p.name for p in registry if p.tier == 8]
    assert names == TIER_8
    tiers = [p.tier for p in registry]
    assert tiers.index(8) > max(i for i, t in enumerate(tiers) if t == 7)
    assert not any(p.extra for p in registry if p.tier == 8)


def test_every_tier_eight_need_is_registered_and_documented(registry):
    known = {p.name for p in registry}
    for p in registry:
        if p.tier == 8:
            assert set(p.needs) <= known, p.name
            assert p.members and p.doc, p.name


def test_running_tier_eight_alone_pulls_in_tier_seven_the_gear_mate_and_only_the_spur_build(registry):
    # The registry's order is import order, which a test session does not control; load_probes, which the
    # host run uses, imports p8_motion last. So only the tier's own order is pinned here.
    chosen = [p.name for p in harness.select(registry, TIER_8)]
    assert [n for n in chosen if n in TIER_8] == TIER_8
    assert {"gear_mate", "layout_planes", "axis_through_named_planes", "layout_part_without_body",
            "nonparallel_mates", "equation_add"} <= set(chosen)
    # gear_mate_update (P1b) builds real gears through the app, so it needs the spur end-to-end build; no other.
    assert [p.name for p in registry if p.tier == 5 and p.name in chosen] == ["end_to_end"]


def test_only_tier_eight_stops_before_solidworks(monkeypatch):
    monkeypatch.setattr(swcom, "is_available", lambda: False)
    monkeypatch.setattr(swcom, "unavailable_reason", lambda: "not here")
    assert probe_main.main(["--only-tier", "8"]) == swcom.EXIT_NOT_AVAILABLE


# -- turns --------------------------------------------------------------------


def test_a_turn_is_read_about_the_gears_own_axis_on_either_shaft():
    for sigma in (1, -1):
        before = p8.w4_rotation(sigma, 10.0)
        after = p8.w4_rotation(sigma, 40.0)
        assert p8.own_turn(before, after) == pytest.approx(30.0)
        assert p8.world_turn(before, after) == pytest.approx(30.0 * sigma)
        assert p8.axis_z(before) == pytest.approx(sigma)


def test_a_turn_is_signed_and_unwrapped():
    before = p8.w4_rotation(1, 170.0)
    after = p8.w4_rotation(1, -170.0)
    assert p8.own_turn(before, after) == pytest.approx(20.0)
    assert p8.unwrap(350.0) == pytest.approx(-10.0)


def test_w4s_frame_on_minus_z_is_x_turned_over():
    m = p8.w4_rotation(-1, 0.0)
    assert m == ((1.0, 0.0, 0.0), (0.0, -1.0, pytest.approx(0.0)), (0.0, pytest.approx(0.0), -1.0))
    # The workbook layout's own formula, diag(1, -1, -1) · rot_z(θ), agrees.
    from gear_generator.workbook.layout import _rotation
    rows = _rotation(-1, math.radians(33.0))
    mine = p8.w4_rotation(-1, 33.0)
    assert [v for row in mine for v in row] == pytest.approx(list(rows), abs=1e-12)


def test_a_face_point_is_on_the_cylinder_half_way_along_it():
    x, y, z = p8.face_point((40.0, 30.0, 10.0), -1)
    assert math.hypot(x - 40.0, y - 30.0) == pytest.approx(p8.BLANK_R)
    assert z == pytest.approx(10.0 - p8.BLANK_W / 2.0)


# -- the flip rules -----------------------------------------------------------

CASE = dict(sigma_a=1, sigma_b=1, internal=False, bigger_first=False)


def case(flip, world_same, **kw):
    return {**CASE, **kw, "flip": flip, "world_same": world_same}


def test_the_measured_parallel_pair_fits_every_rule_that_says_flip_off_is_opposite():
    # probe gear_mate: two cylinders on parallel +Z axes, Flip off turned them opposite ways.
    rules = p8.consistent_rules([case(False, False), case(True, True)])
    assert "own axes" in rules and "plus z" in rules and "mesh" in rules


def test_anti_parallel_axes_tell_own_axes_from_plus_z():
    # Flip off, axes opposed, and the gears turned the same way about +Z: opposite about their own axes.
    cases = [case(False, False), case(False, True, sigma_b=-1)]
    assert "own axes" in p8.consistent_rules(cases)
    assert "plus z" not in p8.consistent_rules(cases)
    assert p8.needed_flip("own axes", 1, -1, internal=False) is True
    assert p8.needed_flip("own axes", 1, 1, internal=False) is False
    assert p8.needed_flip("own axes", -1, -1, internal=True) is True


def test_a_ring_that_turned_the_same_way_with_flip_off_says_the_mesh_is_read():
    cases = [case(False, False), case(False, True, internal=True, bigger_first=True)]
    rules = p8.consistent_rules(cases)
    assert "own axes" not in rules and "plus z" not in rules
    assert "mesh" in rules and "plus z, bigger first" in rules       # one more case is needed to tell these apart
    assert p8.decide_rule(cases) is None
    cases.append(case(False, False, internal=False, bigger_first=True))
    assert p8.decide_rule(cases) is None                              # all on parallel axes: mesh about +Z or own axes?
    cases.append(case(False, False, sigma_b=-1))
    assert p8.decide_rule(cases) == "mesh"
    assert p8.needed_flip("mesh", 1, -1, internal=True) is False


def test_every_rule_gives_a_flip_that_turns_a_mesh_as_it_meshes():
    for rule in p8.RULES:
        for sa in (1, -1):
            for sb in (1, -1):
                for internal in (False, True):
                    for bigger in (False, True):
                        flip = p8.needed_flip(rule, sa, sb, internal, bigger)
                        assert p8.predicted_world_same(rule, flip, sa, sb, internal, bigger) is internal


def test_cases_not_turned_are_left_out_and_nothing_measured_decides_nothing():
    assert p8.consistent_rules([{**CASE, "flip": False, "world_same": None}]) == []
    assert p8.decide_rule([]) is None
    with pytest.raises(ValueError, match="no rule"):
        p8.predicted_world_same("guess", False, 1, 1, False, False)


# -- the train ----------------------------------------------------------------


def test_the_twelve_to_one_train_turns_its_output_a_twelfth_the_same_way():
    turns = p8.train_turns(p8.TRAIN_TEETH, (1, 1, 1, 1))
    assert turns == pytest.approx([1.0, -0.25, -0.25, 1.0 / 12.0])
    with pytest.raises(ValueError):
        p8.train_turns((17, 68, 17), (1, 1, 1))


def test_each_train_sits_its_meshes_on_two_planes_whichever_way_the_middle_shaft_points():
    for _name, prefix, sigmas, origin in p8.TRAINS:
        geometry = p8.train_geometry(prefix, sigmas, origin)
        (_, x1, y1), (_, x2, y2), (_, x3, y3) = geometry["shafts"]
        assert math.hypot(x2 - x1, y2 - y1) == pytest.approx((17 + 68) / 2.0)
        assert math.hypot(x3 - x2, y3 - y2) == pytest.approx((17 + 51) / 2.0)
        mids = [g["at"][2] + g["sigma"] * p8.BLANK_W / 2.0 for g in geometry["gears"]]
        assert mids == pytest.approx([5.0, 5.0, 20.0, 20.0])
        assert [g["shaft"] for g in geometry["gears"]] == [f"{prefix}1", f"{prefix}2", f"{prefix}2", f"{prefix}3"]
        assert geometry["gears"][0]["theta"] == p8.DRIVE_FROM       # the drive starts where the input was placed


def test_a_shaft_swung_round_keeps_its_centre_distance_and_the_phase_it_needs():
    x, y = p8.swung((82.5, 40.0), 34.0, 20.0)
    assert math.hypot(x - 82.5, y - 40.0) == pytest.approx(34.0)
    assert p8.swung((0.0, 0.0), 10.0, 0.0) == pytest.approx((0.0, 10.0))
    assert p8.phase_change(20.0, 17, 51) == pytest.approx(20.0 * 4.0 / 3.0)


def test_the_sense_pairs_sit_clear_and_a_pinion_inside_its_ring():
    rows = set()
    for index, c in enumerate(p8.SENSE_CASES):
        where = p8.sense_layout(index, c)
        rows.add(where["a"][1])
        centre = math.dist(where["a"][:2], where["b"][:2])
        if where["placement"] == "outside":
            assert centre - p8.BLANK_R > p8.RING_OUTER                    # clear outside the annulus
        elif where["internal"]:
            assert centre + p8.BLANK_R < p8.RING_INNER
        else:
            assert centre > 2 * p8.BLANK_R
        for side in ("a", "b"):
            sigma = (c[1] if side == "a" else c[2])[1]
            apart = p8.SENSE_APART if side == "b" and where["placement"] == "apart" else 0.0
            assert where[side][2] + sigma * p8.BLANK_W / 2.0 == pytest.approx(p8.BLANK_W / 2.0 + apart)
    assert len(rows) == len(p8.SENSE_CASES) and p8.SENSE_ROW > 2 * p8.RING_OUTER


def test_the_sense_cases_cover_what_the_review_asked():
    names = [c[0] for c in p8.SENSE_CASES]
    sigmas = {(c[1][1], c[2][1]) for c in p8.SENSE_CASES}
    assert sigmas == {(1, 1), (1, -1), (-1, 1), (-1, -1)}
    assert any(c[1][0] == "ring" and c[1][1] == -1 for c in p8.SENSE_CASES)      # a ring on Z-
    assert {c[3] for c in p8.SENSE_CASES} == {"axis", "face", "mixed"}
    assert {c[6] for c in p8.SENSE_CASES} == {"closest", "aligned", "anti_aligned"}
    assert len(names) == len(set(names))


# -- decisions --------------------------------------------------------------

MOTION = tuple(decide.MOTION_NEEDS)
RIGHT = {"mated_train": {"train_right_way": {"all Z+": True, "middle Z-": True}}}


def test_motion_is_built_only_when_every_needed_probe_passed_and_the_train_turned_right():
    assert decide.motion_route(records(MOTION, facts=RIGHT)) == "mates"
    for name in MOTION:
        rest = tuple(n for n in MOTION if n != name)
        assert decide.motion_route(records(rest, failing=(name,), facts=RIGHT)) == "STOP", name
        assert decide.motion_route({k: v for k, v in records(rest, facts=RIGHT).items() if k != name}) == "STOP", name
    wrong = {"mated_train": {"train_right_way": {"all Z+": True, "middle Z-": False}}}
    assert decide.motion_route(records(MOTION, facts=wrong)) == "STOP"


def test_tier_eight_facts_become_decisions_only_off_a_pass():
    facts = {
        "shaft_axis_mates": {"axis_mate_route": "axis coincident", "axial_mate_route": "origin distance",
                             "axis_mates_refused": {"g3": {}, "g4": {}}},
        "gear_mate_sense": {"gear_mate_flip_rule": "own axes", "sense_depends_on_entities": False},
        "compound_lock": {"compound_lock_route": "lock alone"},
        "motion_update": {"layout_move_carries_mates": True, "mesh_phase_route": "x", "axial_global_moves_gear": True,
                          "lock_unsuppress_keeps_the_new_angle": True},
    }
    passed = decide.decide(records(facts=facts))
    assert (passed["axis_mate_route"], passed["axial_mate_route"], passed["axis_concentric_refused"]) == \
        ("axis coincident", "origin distance", True)
    assert passed["gear_mate_flip_rule"] == "own axes" and passed["gear_mate_sense_depends_on_entities"] is False
    assert passed["compound_lock_route"] == "lock alone"
    assert (passed["layout_move_carries_mates"], passed["mesh_phase_route"], passed["axial_global_moves_gear"],
            passed["lock_unsuppress_keeps_the_new_angle"]) == (True, "x", True, True)
    failed = records(failing=tuple(facts))
    for name, values in facts.items():
        failed[name]["facts"].update(values)
    decided = decide.decide(failed)
    for key in ("axis_mate_route", "axial_mate_route", "axis_concentric_refused", "gear_mate_flip_rule",
                "compound_lock_route", "layout_move_carries_mates", "mesh_phase_route", "axial_global_moves_gear",
                "lock_unsuppress_keeps_the_new_angle"):
        assert decided[key] is None, key
    assert decided["motion_route"] == "STOP"
    assert decide.decide({})["motion_route"] == "STOP"


def test_what_a_gear_mate_keeps_as_reverse_follows_the_axes_and_the_ring():
    # SolidWorks 2026, gear_mate_sense: Flip off kept Reverse False on parallel axes, True on opposed ones,
    # and the other way round for an annulus round its pinion.
    assert p8.stored_reverse(False, 1, 1, False) is False
    assert p8.stored_reverse(False, 1, -1, False) is True
    assert p8.stored_reverse(True, 1, 1, False) is True
    assert p8.stored_reverse(False, 1, 1, True) is True
    assert p8.stored_reverse(False, -1, 1, True) is False


def test_a_drag_is_a_turn_about_the_gears_own_axis_through_its_origin():
    r, t = p8.turn_about_point((0.0, 0.0, 1.0), 90.0, (10.0, 0.0, 5.0))
    moved = [sum(r[i][j] * v for j, v in enumerate((10.0, 0.0, 5.0))) + t[i] for i in range(3)]
    assert moved == pytest.approx([10.0, 0.0, 5.0])                     # the origin stays
    flat = lambda m: [v for row in m for v in row]   # noqa: E731
    assert flat(p8.rotation_about((0.0, 0.0, -1.0), 30.0)) == pytest.approx(flat(crossed.rot_z(-30.0)))
    assert flat(p8.rotation_about((0.0, 0.0, 1.0), 30.0)) == pytest.approx(flat(crossed.rot_z(30.0)))


# -- package P0 (W5-PLAN §0.3, the review's M4 and M5, and the mated rebuild) -----------


def test_the_new_items_run_on_mated_trains_copy_or_their_own(registry):
    by_name = {p.name: p for p in registry}
    for name in ("gear_mate_ratio", "lock_retake_offset", "lock_mate_rename", "demonstration_drive",
                 "put_on_twice_meshed_gear", "gear_mate_definition"):
        assert by_name[name].needs == ("motion_update",), name
    assert by_name["mated_rebuild_scope"].needs == ("mated_train",)
    assert by_name["axial_datum_plane"].needs == ("shaft_axis_mates",)
    # P1b builds real gears with the app's own code, as assembly_rebuild_scope does, so it needs what that needs.
    assert set(by_name["gear_mate_update"].needs) == {"motion_update", "end_to_end", "layout_assembly_reopen"}
    chosen = {p.name for p in harness.select(registry, ["axial_datum_plane"])}
    assert "gear_mate_sense" not in chosen and "mated_train" not in chosen


def test_the_definition_route_is_registered_last(registry):
    """On SolidWorks 2024 the definition route strands the assembly it changes, holding the train's layout and part,
    so it is the last probe of all: in one run nothing comes after it (the P0 review's first finding). That it is
    not run in the same session as anything else is the run's to keep (2024: a separate invocation)."""
    names = [p.name for p in registry if p.tier == 8]
    assert names[-1] == "gear_mate_definition"     # p8_motion is imported last by load_probes, so last of all
    assert names.index("gear_mate_ratio") < names.index("gear_mate_definition")


def test_a_followers_pose_against_its_anchor_reads_angle_offset_and_axis():
    for sigma in (1, -1):
        anchor = (p8.w4_rotation(sigma, 23.0), (82.5, 40.0, 10.0))
        axis = p8.column(anchor[0], 2)
        follower = (p8.w4_rotation(sigma, 23.0 + 11.0), tuple(a + 3.0 * d for a, d in zip(anchor[1], axis)))
        pose = p8.relative_pose(anchor, follower)
        assert pose["angle"] == pytest.approx(11.0) and pose["along"] == pytest.approx(3.0)
        assert pose["off_axis"] == pytest.approx(0.0, abs=1e-9) and pose["axis_off"] == pytest.approx(0.0, abs=1e-12)
        same = p8.relative_pose(anchor, anchor)
        change = p8.pose_change(same, pose)
        assert change["angle"] == pytest.approx(11.0) and change["along"] == pytest.approx(3.0)
    off = p8.relative_pose((p8.w4_rotation(1, 0.0), (0.0, 0.0, 0.0)), (p8.w4_rotation(1, 0.0), (3.0, 4.0, 2.0)))
    assert off["off_axis"] == pytest.approx(5.0) and off["along"] == pytest.approx(2.0)
    wrapped = p8.pose_change({"angle": 175.0, "along": 0.0}, {"angle": -174.0, "along": 0.0, "off_axis": 0.0,
                                                               "axis_off": 0.0})
    assert wrapped["angle"] == pytest.approx(11.0)


def test_the_two_trains_joined_by_one_more_gear_mate_turn_as_one():
    turns = p8.joined_turns()
    assert turns[:4] == pytest.approx([1.0, -0.25, -0.25, 1 / 12])
    # The first output (51 teeth) drives the second input (17): -3 times it, and the second train 1/12 of that.
    assert turns[4] == pytest.approx(-0.25) and turns[7] == pytest.approx(-0.25 / 12)
    # The first train's second gear mate remade at 17 : 60, the joining mate still 51 : 17, the second train as built.
    remade = p8.joined_turns((17, 68, 17, 60), (51, 17), second=p8.TRAIN_TEETH)
    assert remade[3] == pytest.approx(17 / 68 * 17 / 60) and remade[4] == pytest.approx(-remade[3] * 3)
    assert remade[7] == pytest.approx(remade[4] / 12)


def test_a_datum_plane_far_behind_front_keeps_every_distance_positive():
    assert [p8.datum_distance(z) for z in (17.0, 0.0, -5.0, 8.0)] == [1017.0, 1000.0, 995.0, 1008.0]
    assert all(p8.datum_distance(z) > 0 for z in p8.DATUM_STEPS)
    assert {g[4] for g in p8.DATUM_GEARS} == {1, -1}             # a Z+ and a Z- anchor
    assert min(p8.DATUM_STEPS) < 0 < max(p8.DATUM_STEPS) and 0.0 in p8.DATUM_STEPS   # through where Front is


def test_mates_are_renamed_to_the_names_w5_gives_them():
    info = {"trains": {name: p8.train_geometry(prefix, sigmas, origin) for name, prefix, sigmas, origin in p8.TRAINS},
            "mates": {"TG4": ["Coincident5", "Distance1"], "TG3-TG4": {"name": "GearMate2"},
                      "all Z+ lock": "Lock1", "middle Z- lock": "Lock2"}}
    plan = p8.rename_plan(info)
    assert [(k, new) for k, _old, new in plan] == [
        ("lock", "TG3 locked to TG2"), ("gear", "TG3 meshes TG4"), ("axis", "TG4 on T3 Axis"),
        ("along", "TG4 along T3"), ("suppressed lock", "UG3 locked to UG2")]
    assert [old for _k, old, _new in plan] == ["Lock1", "GearMate2", "Coincident5", "Distance1", "Lock2"]


def test_the_worst_frame_error_is_the_largest_of_either_kind():
    assert p8.worst({}) == 0.0
    assert p8.worst({"a": {"rotation": 1e-9, "origin_mm": 2e-3}, "b": {"rotation": 0.5, "origin_mm": 0.0}}) == 0.5


def _mated_case(**changes):
    case = {"matches_reference": True}
    for step, wanted in p8.MATED_WANTED.items():
        marks = {d: d in wanted for d in p8.MATED_DOCS}
        case[step] = {"shown": True, "drive_right": True, "flags": dict(marks), "flags_after_reads": dict(marks)}
    case["failure"]["cleared"] = True
    for step, values in changes.items():
        if isinstance(values, dict):
            case[step].update(values)
        else:
            case[step] = values
    return case


def test_a_step_shown_before_its_route_is_recorded_and_is_not_evidence():
    assert p8.shown(False, True) is True and p8.shown(False, False) is False
    assert p8.shown(True, True) == p8.BEFORE and p8.shown(True, False) is False


def test_a_mated_rebuild_route_must_show_what_only_it_can_and_mark_only_what_changed():
    good = p8.mated_verdict(_mated_case())
    assert all(good[c] is True for c in p8.MATED_CRITERIA)
    # SolidWorks showing a put, a layout move, a part change or a mate error before any route is not held against
    # a route, and not counted for it.
    before = p8.mated_verdict(_mated_case(put={"shown": p8.BEFORE}, layout={"shown": p8.BEFORE},
                                          part={"shown": p8.BEFORE}, failure={"shown": p8.BEFORE, "cleared": p8.BEFORE}))
    assert p8.first_mated_route({"ForceRebuild3(True)": before}) == "ForceRebuild3(True)"
    # The axial global and the drive must be shown by the route itself; before it is not enough.
    for step, criterion in (("axial", "axial_shown"), ("drive", "drive_shown")):
        early = p8.mated_verdict(_mated_case(**{step: {"shown": p8.BEFORE}}))
        assert early[criterion] == p8.BEFORE and p8.first_mated_route({"EditRebuild3": early}) is None
    # The drive after a put, a layout move or a part change, and the frames against the full rebuild's, must hold.
    for step in ("put", "layout", "part"):
        undriven = p8.mated_verdict(_mated_case(**{step: {"drive_right": False}}))
        assert p8.first_mated_route({"ForceRebuild3(True)": undriven}) is None, step
    elsewhere = p8.mated_verdict({**_mated_case(), "matches_reference": False})
    assert elsewhere["matches_reference"] is False and p8.first_mated_route({"ForceRebuild3(True)": elsewhere}) is None
    every = {d: True for d in p8.MATED_DOCS}
    full = p8.mated_verdict(_mated_case(axial={"flags": every}))
    assert full["only_changed_marked"] is False and full["axial_shown"] is True
    unread = p8.mated_verdict(_mated_case(part={"flags": {"assembly": True, "layout": True, "part": None}}))
    assert unread["only_changed_marked"] is None
    missed = p8.mated_verdict(_mated_case(drive={"shown": False}))
    verdicts = {"ForceRebuild3(True)": missed, "EditRebuild3": good, "ForceRebuild3(False)": full}
    assert p8.first_mated_route(verdicts) == "EditRebuild3"
    assert p8.first_mated_route({"ForceRebuild3(True)": missed, "ForceRebuild3(False)": full}) is None
    assert p8.mated_marked({"assembly": True, "layout": False, "part": False}, ("assembly",)) is True
    assert p8.mated_marked({"assembly": True, "layout": True, "part": False}, ("assembly",)) is False


def _build(**changes):
    out = {"placed_off": 0.0, "moved_by_mating": 0.0, "turns_right": True, "matches_reference": True,
           "check": {"statuses": [1, 1, 1], "errors": {}, "constrained": {"TG1": 2, "TG2": 2}},
           "constrained_driven": {"TG1": 3, "TG2": 3}}
    out.update(changes)
    return out


def test_a_train_built_under_a_route_must_pass_w5s_mate_check_and_turn_as_the_full_rebuilds_does():
    assert all(p8.build_verdict(_build()).values())
    bad = {"over-defined": _build(check={"statuses": [1, 5], "errors": {}, "constrained": {"TG1": 2}}),
           "a mate error": _build(check={"statuses": [1], "errors": {"Lock1": {"code": 46}}, "constrained": {"TG1": 2}}),
           "fully defined undriven": _build(check={"statuses": [1], "errors": {}, "constrained": {"TG1": 3}}),
           "jumped": _build(moved_by_mating=0.1), "misplaced": _build(placed_off=0.1),
           "two freedoms": _build(constrained_driven={"TG1": 2}), "wrong ratio": _build(turns_right=False),
           "elsewhere": _build(matches_reference=False)}
    for label, build in bad.items():
        verdict = p8.build_verdict(build)
        assert not all(verdict.values()), label
        assert p8.first_build_route({"ForceRebuild3(True)": verdict}) is None, label
    assert p8.first_build_route({"ForceRebuild3(True)": p8.build_verdict(_build(turns_right=False)),
                                 "ForceRebuild3(False)": p8.build_verdict(_build())}) == "ForceRebuild3(False)"


def test_frame_tables_compare_gear_by_gear():
    a = {"G1": [p8.w4_rotation(1, 10.0), [0.0, 0.0, 0.0]], "G2": [p8.w4_rotation(-1, 5.0), [1.0, 2.0, 3.0]]}
    assert p8.frame_table_diff(a, a) == 0.0
    b = {**a, "G2": [p8.w4_rotation(-1, 5.0), [1.0, 2.0, 3.5]]}
    assert p8.frame_table_diff(a, b) == pytest.approx(0.5)
    assert p8.frame_table_diff(a, {"G1": a["G1"]}) == math.inf and p8.frame_table_diff({}, {}) == math.inf


def test_the_update_fixture_keeps_its_centre_distance_and_changes_its_ratio():
    old = p8.update_spec("C:\\X")
    new = p8.update_spec("C:\\X", p8.UPDATE_TEETH)
    teeth = lambda spec: {g.id: int(g.teeth) for g in spec.gears}   # noqa: E731
    assert teeth(old) == {"G1": 17, "G2": 68, "G3": 17, "G4": 51}
    assert teeth(new)["G3"] + teeth(new)["G4"] == teeth(old)["G3"] + teeth(old)["G4"]      # module 2: still 68 mm apart
    assert p8.update_turns(teeth(old))[3] == pytest.approx(1 / 12)
    assert p8.update_turns(teeth(new))[3] == pytest.approx(17 / 68 * 18 / 50)
    frames_old, frames_new = p8.update_frames("C:\\X"), p8.update_frames("C:\\X", p8.UPDATE_TEETH)
    assert frames_old["G1"] == frames_new["G1"] and frames_old["G2"] == frames_new["G2"]
    assert frames_old["G4"][1] == frames_new["G4"][1] and frames_old["G4"][0] != frames_new["G4"][0]   # a new phase
    assert p8.frames_identity(frames_old["G1"][0])                  # the input at its built phase: the 90° drive holds
    assert [a for a, _s in p8.UPDATE_ANCHORS] == ["G1", "G2", "G4"] and p8.UPDATE_LOCKS == (("G2", "G3"),)


def _update_pass(**changes):
    p = {"teeth": {"G3": {"ok": True, "changed": ["No. of Teeth"]}, "G4": {"ok": True, "changed": ["No. of Teeth"]}},
         "remake": {"name": "G3 meshes G4"}, "off_built": {"G1": {"rotation": 0.0, "origin_mm": 0.0}},
         "check": {"statuses": {"G3 meshes G4": 1}, "errors": {}, "constrained": {"G1": 2}},
         "moved_by_the_full_rebuild": 0.0,
         "drive": {"turns": {"G1": 30.0, "G2": -7.5, "G3": -7.5, "G4": 7.5 * 18 / 50}, "back_at_built": 0.0},
         "interference": {"count": 0}}
    p.update(changes)
    return p


def test_an_update_pass_holds_only_when_every_step_did():
    teeth = {"G1": 17, "G2": 68, "G3": 18, "G4": 50}
    assert p8.update_pass_holds(_update_pass(), teeth)
    for label, change in {
            "teeth refused": {"teeth": {"G3": {"ok": False, "changed": []}}},
            "renamed otherwise": {"remake": {"name": "GearMate5"}},
            "off its frame": {"off_built": {"G4": {"rotation": 0.01, "origin_mm": 0.0}}},
            "a mate error": {"check": {"statuses": {}, "errors": {"Lock1": {"code": 51}}, "constrained": {}}},
            "the full rebuild moves it": {"moved_by_the_full_rebuild": 0.1},
            "the old ratio": {"drive": {"turns": {"G1": 30.0, "G2": -7.5, "G3": -7.5, "G4": 2.5}, "back_at_built": 0.0}},
            "not back": {"drive": {"turns": {"G1": 30.0, "G2": -7.5, "G3": -7.5, "G4": 7.5 * 18 / 50},
                                   "back_at_built": 0.1}},
            "interference": {"interference": {"count": 2}}}.items():
        assert not p8.update_pass_holds(_update_pass(**change), teeth), label


def test_package_p0_decisions_come_off_a_pass_only():
    facts = {
        "motion_enums": {"motion_enum_values": {"suppress": 0, "unsuppress": 1, "this_configuration": 1}},
        "motion_update": {"motion_update": {"suppressed_by": "S", "unsuppressed_by": "S",
                                            "lock_moved": {"suppressed_by": "S", "unsuppressed_by": "S"}}},
        "compound_lock": {"lock_results": {"a": {"how": "lock alone", "select": "M"}, "b": {"how": "lock both",
                                                                                         "select": "M"},
                                           "c": {"how": "angle", "select": True}},
                          "over_defined": {"deleted_by": "D"}},
        "gear_mate_ratio": {"gear_mate_ratio_route": "remake"},
        "gear_mate_update": {"gear_mate_update_holds": True},
        "gear_mate_definition": {"definition_numerator_is_second_teeth": True, "definition_recipe": "r",
                                 "definition_closes": {"r": True, "s": False}},
        "lock_retake_offset": {"lock_retakes_an_offset": True},
        "lock_mate_rename": {"mate_rename_route": "IFeature.Name put",
                             "mate_find_routes": {"mate group": True, "FeatureByName": True}},
        "demonstration_drive": {"demonstration_drive_holds": True},
        "put_on_twice_meshed_gear": {"put_on_twice_meshed_gear_holds": True, "remake_on_twice_meshed_gear_holds": True},
        "axial_datum_plane": {"axial_datum_route": "origin distance from a datum plane", "axial_datum_flip": False},
        "mated_rebuild_scope": {"mated_assembly_rebuild_route": "ForceRebuild3(True)",
                                "mated_rebuild_keeps_components_unmodified": True,
                                "mated_build_rebuild_route": "ForceRebuild3(True)",
                                "mated_build_keeps_components_unmodified": True},
    }
    passed = decide.decide(records(facts=facts))
    assert (passed["feature_suppress"], passed["feature_unsuppress"], passed["this_configuration"]) == (0, 1, 1)
    assert (passed["suppression_route"], passed["lock_select_route"], passed["mate_delete_route"]) == ("S", "M", "D")
    assert passed["gear_mate_ratio_route"] == "remake" and passed["gear_mate_update_holds"] is True
    assert passed["gear_mate_definition_recipe"] == "r" and passed["modified_gear_mate_closes"] is False
    assert passed["remake_on_twice_meshed_gear_holds"] is True
    assert (passed["mated_build_rebuild_route"], passed["mated_build_keeps_components_unmodified"]) == \
        ("ForceRebuild3(True)", True)
    assert passed["gear_mate_definition_numerator_is_second"] is True
    assert passed["lock_retakes_an_offset"] is True
    assert (passed["mate_rename_route"], passed["mate_find_route"]) == ("IFeature.Name put", "mate group")
    assert passed["demonstration_drive_holds"] is True and passed["put_on_twice_meshed_gear_holds"] is True
    assert (passed["axial_datum_route"], passed["axial_datum_flip"]) == ("origin distance from a datum plane", False)
    assert passed["mated_assembly_rebuild_route"] == "ForceRebuild3(True)"
    assert passed["mated_rebuild_keeps_components_unmodified"] is True
    failed = records(failing=tuple(facts))
    for name, values in facts.items():
        failed[name]["facts"].update(values)
    decided = decide.decide(failed)
    for key in ("feature_suppress", "feature_unsuppress", "this_configuration", "suppression_route",
                "lock_select_route", "mate_delete_route", "gear_mate_ratio_route", "gear_mate_definition_recipe",
                "gear_mate_update_holds", "modified_gear_mate_closes", "remake_on_twice_meshed_gear_holds",
                "mated_build_rebuild_route", "mated_build_keeps_components_unmodified", "lock_retakes_an_offset",
                "mate_rename_route", "mate_find_route", "demonstration_drive_holds", "put_on_twice_meshed_gear_holds",
                "axial_datum_route", "axial_datum_flip", "mated_assembly_rebuild_route",
                "mated_rebuild_keeps_components_unmodified"):
        assert decided[key] is None, key
    # Two routes where one is wanted decide nothing.
    split = records(facts={**facts, "motion_update": {"motion_update": {"suppressed_by": "S", "unsuppressed_by": "T"}}})
    assert decide.decide(split)["suppression_route"] is None
    renamed_not = records(facts={**facts, "lock_mate_rename": {"mate_rename_route": None,
                                                               "mate_find_routes": {"mate group": True}}})
    assert decide.decide(renamed_not)["mate_find_route"] is None
    # The remake is the route only once P1b has carried a whole tooth change; "modify definition" never is.
    no_update = records(facts={**facts, "gear_mate_update": {"gear_mate_update_holds": False}})
    assert decide.decide(no_update)["gear_mate_ratio_route"] is None
    definition = records(facts={**facts, "gear_mate_ratio": {"gear_mate_ratio_route": "modify definition"}})
    assert decide.decide(definition)["gear_mate_ratio_route"] is None


def test_each_ratio_recipe_puts_what_it_says():
    read = {"GearRatioNumerator": 51.0, "GearRatioDenominator": 17.0, "Reverse": False}
    one, both, crossed_over = p8.RATIO_ALONE, p8.RATIO_AS_READ, p8.RATIO_CROSSED
    assert p8.RATIO_RECIPES[0] == crossed_over and set(p8.RATIO_RECIPES) == {one, both, crossed_over}
    assert p8.ratio_fields(one, read, 51, 60) == {"GearRatioNumerator": 60.0}
    assert p8.ratio_fields(both, read, 51, 60) == {"GearRatioNumerator": 60.0, "GearRatioDenominator": 17.0}
    assert p8.ratio_fields(crossed_over, read, 51, 60) == {"GearRatioNumerator": 17.0, "GearRatioDenominator": 60.0}
    assert p8.ratio_fields(one, read, 68, 60) == {}                     # the old count is in neither field
    assert p8.ratio_fields(one, {"GearRatioNumerator": 17.0, "GearRatioDenominator": 17.0}, 17, 20) == {}
    with pytest.raises(ValueError):
        p8.ratio_fields("guess", read, 51, 60)


def test_p1b_plans_w4s_static_gearbox_whatever_w5_would_choose(monkeypatch):
    """gear_mate_update mates W4's static assembly itself: while it plans, workbook.motion.motion_reason gives a
    sentence, so a plan_gearbox that would plan a turning assembly plans the static one; one that still plans motion
    is refused with a sentence; and motion_reason is put back afterwards."""
    from types import SimpleNamespace

    from gear_generator.workbook import gearbox, motion

    original = motion.motion_reason
    seen = []

    def planner(assessed, record):
        seen.append(motion.motion_reason())
        return SimpleNamespace(refusal="", motion=None if motion.motion_reason() else "turning", static_reason="s")

    monkeypatch.setattr(gearbox, "plan_gearbox", planner)
    px = harness.Px(harness.Record("gear_mate_update", 8))
    assert p8.static_plan(px, object()).motion is None
    assert seen == [p8.STATIC_FOR_THE_PROBE] and motion.motion_reason is original
    monkeypatch.setattr(gearbox, "plan_gearbox", lambda a, r: SimpleNamespace(refusal="", motion="turning"))
    with pytest.raises(harness.Require, match="static assembly"):
        p8.static_plan(px, object())
    assert motion.motion_reason is original


def test_no_probe_shadows_a_helper_of_the_same_name():
    """A probe body named like a helper replaces it in the module (the first P0b run on 2026 found
    gear_mate_definition, the probe, shadowing gear_mate_definition, the reader of a gear mate's ratio)."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(p8))
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert len(names) == len(set(names)), sorted({n for n in names if names.count(n) > 1})
    assert p8.gear_mate_definition.__code__.co_argcount == 3      # the reader: (px, asm, name)


def test_the_command_in_progress_train_takes_w5s_names():
    trains = {name: p8.train_geometry(prefix, sigmas, origin) for name, prefix, sigmas, origin in p8.TRAINS}
    names = p8.cip_names(trains)
    assert names["TG1"] == ("TG1 on T1 Axis", "TG1 along T1") and names["UG4"] == ("UG4 on U3 Axis", "UG4 along U3")
    assert names["TG3-TG4"] == "TG3 meshes TG4" and names["all Z+ lock"] == "TG3 locked to TG2"
    assert "TG3" not in names                                        # a follower is held by its lock alone
    flat = [n for v in names.values() for n in (v if isinstance(v, tuple) else (v,))]
    assert len(flat) == len(set(flat)) == 2 * (3 * 2 + 2 + 1)


def test_package_p0c_decisions_come_off_a_pass_only():
    facts = {"mates_under_command_in_progress": {"mates_under_command_in_progress_hold": True,
                                                 "mate_rename_at_once_holds": True},
             "mate_folders": {"mate_group_walk_sees_mates_in_a_folder": False},
             "lightweight_remake": {"lightweight_remake_holds": None},
             "second_assembly_beside_unsaved": {"second_assembly_beside_unsaved_holds": True}}
    passed = decide.decide(records(facts=facts))
    assert passed["mates_under_command_in_progress"] is True and passed["mate_rename_at_once"] is True
    assert passed["mate_group_walk_sees_mates_in_a_folder"] is False and passed["lightweight_remake"] is None
    assert passed["second_assembly_beside_unsaved"] is True
    failed = records(failing=tuple(facts))
    for name, values in facts.items():
        failed[name]["facts"].update(values)
    decided = decide.decide(failed)
    for key in ("mates_under_command_in_progress", "mate_rename_at_once", "mate_group_walk_sees_mates_in_a_folder",
                "second_assembly_beside_unsaved"):
        assert decided[key] is None, key


def test_the_idler_fixture_remakes_both_of_the_idlers_gear_mates_and_moves_no_shaft():
    fx = p8.IDLER
    old, new = fx.spec("C:\\X"), fx.spec("C:\\X", dict(fx.change))
    teeth = lambda spec: {g.id: int(g.teeth) for g in spec.gears}   # noqa: E731
    assert teeth(old) == fx.old_teeth() and teeth(new) == fx.new_teeth() == {"G1": 15, "G2": 32, "G3": 38}
    for a, b in fx.meshes:                                            # module 2: every centre distance holds
        assert teeth(new)[a] + teeth(new)[b] == teeth(old)[a] + teeth(old)[b]
    assert fx.remade() == [("G1", "G2"), ("G2", "G3")]               # the idler is in both
    assert fx.turns(fx.old_teeth()) == pytest.approx([1, -17 / 30, 17 / 40])
    assert fx.turns(fx.new_teeth()) == pytest.approx([1, -15 / 32, 15 / 38])
    frames_old, frames_new = p8.update_frames("C:\\X", fx=fx), p8.update_frames("C:\\X", dict(fx.change), fx=fx)
    assert all(frames_old[g][1] == frames_new[g][1] for g in fx.gears)
    assert frames_old["G2"][0] != frames_new["G2"][0] and p8.frames_identity(frames_new["G1"][0])
    # The reducer's turns by the general rule are the compound train's.
    assert p8.REDUCER.turns(p8.REDUCER.old_teeth()) == pytest.approx(p8.update_turns(p8.REDUCER.old_teeth()))
    assert p8.REDUCER.remade() == [("G3", "G4")] and p8.update_spec("C:\\X").box.name == p8.UPDATE_TAG


def test_an_idler_update_holds_only_with_both_gear_mates_remade_by_name():
    teeth = p8.IDLER.new_teeth()
    turns = {g: 30.0 * t for g, t in zip(p8.IDLER.gears, p8.IDLER.turns(teeth))}
    both = {"G1 meshes G2": {"name": "G1 meshes G2"}, "G2 meshes G3": {"name": "G2 meshes G3"}}
    p = _update_pass(teeth={g: {"ok": True, "changed": ["No. of Teeth"]} for g in p8.IDLER.gears}, remakes=both,
                     drive={"turns": turns, "back_at_built": 0.0})
    p.pop("remake")
    assert p8.update_pass_holds(p, teeth, p8.IDLER)
    assert not p8.update_pass_holds({**p, "remakes": {"G1 meshes G2": both["G1 meshes G2"]}}, teeth, p8.IDLER)
    assert not p8.update_pass_holds({**p, "remakes": {**both, "G2 meshes G3": {"name": "GearMate4"}}}, teeth, p8.IDLER)
    assert p8.remakes_of({"remake": {"name": "G3 meshes G4"}}) == {"G3 meshes G4": {"name": "G3 meshes G4"}}
    assert p8.interference_control({"interference_before_put": {"count": 0}, "interference_half_pitch": {"count": 3},
                                    "interference": {"count": 0}}) == {"before_put": 0, "half_pitch": 3, "after": 0}
    assert p8.IDLER.control == "G2" and p8.REDUCER.control == "G4"   # a gear whose teeth change
    assert all(fx.control in dict(fx.change) for fx in (p8.IDLER, p8.REDUCER))


def test_a_mate_not_made_is_said_in_a_sentence():
    said = p8.not_made("G1 on S1 Axis", {"returned": None, "status": 5, "status_name": "swAddMateError_x",
                                         "made": [], "name": None})
    assert said.endswith(".") and "{" not in said and "status 5" in said


def test_the_dialog_watch_is_made_on_linux_and_touches_no_window_until_entered():
    watch = p8.DialogWatch(1234)
    assert watch.report() == {"windows": [], "watch_error": None}


def test_the_round_p0c_review_additions_decide_off_a_pass_only():
    facts = {"idler_update": {"idler_update_holds": True, "idler_interference_control_discriminates": True},
             "gear_mate_update": {"gear_mate_update_holds": True, "update_interference_control_discriminates": False},
             "unsaved_update_close": {"unsaved_update_close_asks": {"CloseDoc": False, "QuitDoc": False},
                                      "unsaved_update_close_discards": {"CloseDoc": True, "QuitDoc": True}}}
    passed = decide.decide(records(facts=facts))
    assert passed["idler_update_holds"] is True and passed["update_interference_control_discriminates"] is False
    assert passed["unsaved_update_close_asks"] == {"CloseDoc": False, "QuitDoc": False}
    failed = records(failing=tuple(facts))
    for name, values in facts.items():
        failed[name]["facts"].update(values)
    decided = decide.decide(failed)
    for key in ("idler_update_holds", "idler_interference_control_discriminates", "unsaved_update_close_asks",
                "unsaved_update_close_discards"):
        assert decided[key] is None, key


def test_a_drag_follows_only_when_the_whole_train_turns_its_share_in_place():
    keys = ["TG1", "TG2", "TG3", "TG4"]
    expected = p8.train_turns(p8.TRAIN_TEETH, (1, 1, 1, 1))
    before = {k: (p8.crossed.rot_z(0.0), (10.0 * i, 0.0, 0.0)) for i, k in enumerate(keys)}
    asked = p8.DRAG_DEGREES
    assert abs(asked / expected[3]) < 180.0                           # the input's turn must read as itself
    turned = {k: (p8.crossed.rot_z(asked * e / expected[3]), before[k][1]) for k, e in zip(keys, expected)}
    res = p8.drag_residuals(before, turned, keys, expected, "TG4")
    assert res["turns"]["TG4"] == pytest.approx(asked) and max(res["residual_deg"].values()) < 1e-6
    assert p8.drag_follows(res, "TG4", asked)
    alone = {**before, "TG4": turned["TG4"]}                         # only the dragged gear turned (tier 8's reading)
    assert not p8.drag_follows(p8.drag_residuals(before, alone, keys, expected, "TG4"), "TG4", asked)
    assert p8.DRAG_CASES[0][1:] == (3, 10)                            # the entry's success comes first, as given


def test_what_a_definition_read_marks_is_read_off_the_flags_around_it():
    clean = {"A.SLDASM": False, "L.SLDPRT": False}
    read = lambda before, after: {"flags_before": before, "marked": p8.newly_marked(before, after)}  # noqa: E731
    assert p8.read_marks([read(clean, clean), read(clean, clean)], "A.SLDASM") == "nothing"
    assert p8.read_marks([read(clean, {**clean, "A.SLDASM": True})], "A.SLDASM") == "the assembly"
    assert p8.read_marks([read(clean, {"A.SLDASM": True, "L.SLDPRT": True})], "A.SLDASM").startswith("more")
    assert p8.read_marks([read({**clean, "A.SLDASM": True}, {**clean, "A.SLDASM": True})],
                         "A.SLDASM").startswith("undetermined")


def test_origin_noise_leaves_out_the_gears_meant_to_move():
    before = {"G1": (0.0, 0.0, 0.0), "G4": (131.75, 0.0, 17.0)}
    after = {"G1": (1e-9, 0.0, 0.0), "G4": (132.75, 0.0, 17.0)}
    assert p8.origin_spread(before, after)["largest_mm"] == pytest.approx(1.0)
    assert p8.origin_spread(before, after, ["G4"])["largest_mm"] == pytest.approx(1e-9)


def test_the_first_fully_resolved_stage_and_folders_holding_in_every_case():
    stages = {"after the open": {"TG1": [1, "swComponentLightweight"], "TG2": [2, "swComponentFullyResolved"]},
              "after the first drive": {"TG1": [2, "swComponentFullyResolved"], "TG2": [2, "swComponentFullyResolved"]}}
    assert p8.resolved_stage(stages, 2) == "after the first drive"
    assert p8.resolved_stage({"after the open": stages["after the open"]}, 2) is None
    ok = {"sibling": {"Lock1": True}, "found": {"Lock1": True}, "types": ["MateLock"]}
    assert p8.folders_hold({"one folder": ok, "reopened": ok})
    assert not p8.folders_hold({"one folder": ok, "reopened": {**ok, "sibling": {"Lock1": False}}})
    assert not p8.folders_hold({})
