"""Helical and herringbone gears: the transverse maths, the globals, and the plan's order."""

import pytest

from gear_generator import swbuild
from gear_generator.gears import KINDS
from gear_generator.gears.base import (
    LinkDimension,
    MirrorBody,
    OpenSketch,
    RefPlane,
    SweepCut,
)
from gear_generator.gears.equations import DEGREES, RADIANS, evaluate_all
from gear_generator.gears.helical import HELIX_ANGLE, TRANSVERSE_PRESSURE_ANGLE, TWIST_ANGLE
from gear_generator.gears.spur import USER_VARIABLES
from gear_generator.spec import GearSpec, pair_stems, PairSpec

from test_swbuild import FakeSolidWorks, never_exists

HELICAL = KINDS["helical"]
HERRINGBONE = KINDS["herringbone"]
PATH = r"C:\Gears\Helical_m2_N20_15R.SLDPRT"


def spec(kind="helical", **values):
    base = dict(kind=kind, module="2", teeth="20", helix_angle="15", face_width="20", bore="10")
    base.update(values)
    return GearSpec(**base)


def test_the_pinned_transverse_values():
    g = HELICAL.derive(spec())
    s = g.section
    assert g.transverse_module == pytest.approx(2.070552, abs=1e-6)
    assert s.d == pytest.approx(41.411047, abs=1e-6)
    assert s.da == pytest.approx(45.411047, abs=1e-6)
    assert s.df == pytest.approx(36.411047, abs=1e-6)
    assert s.pressure_angle_deg == pytest.approx(20.646896, abs=1e-6)
    assert s.db == pytest.approx(38.751267, abs=1e-6)
    assert s.space == pytest.approx(3.873582, abs=1e-6)
    assert s.inv_alpha == pytest.approx(0.016453, abs=1e-6)
    assert s.phi == pytest.approx(0.077086, abs=1e-6)
    assert g.lead == pytest.approx(485.527277, abs=1e-6)
    assert g.face_twist_deg == pytest.approx(14.829239, abs=1e-6)
    assert g.overlap == pytest.approx(0.823847, abs=1e-6)
    assert g.n_min == pytest.approx(15.538, abs=1e-3)
    assert g.ra == s.ra and g.teeth == 20      # the section reads through


def test_the_end_to_end_gear_the_probe_builds():
    g = HELICAL.derive(spec(module="2", teeth="13", helix_angle="20", face_width="10", bore="8"))
    assert g.transverse_module == pytest.approx(2.128356, abs=1e-6)
    assert g.section.d == pytest.approx(27.668622, abs=1e-6)
    assert g.section.pressure_angle_deg == pytest.approx(21.172832, abs=1e-6)
    assert g.lead == pytest.approx(238.820463, abs=1e-6)
    assert g.face_twist_deg == pytest.approx(15.074085, abs=1e-6)


def test_a_tiny_helix_is_a_spur_gear_to_the_last_digit_that_matters():
    helical = HELICAL.derive(spec(helix_angle="1e-7")).section
    straight = KINDS["spur"].derive(GearSpec(module="2", teeth="20", face_width="20", bore="10"))
    for field in ("d", "da", "df", "db", "space", "s", "phi", "t1", "t2", "flank_arc_radius"):
        assert getattr(helical, field) == pytest.approx(getattr(straight, field), abs=1e-9), field


@pytest.mark.parametrize("gear", [HELICAL, HERRINGBONE])
@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_every_global_evaluates_to_the_maths(gear, trig):
    s = spec(kind=gear.kind, helix_angle="30" if gear is HERRINGBONE else "15")
    g = gear.derive(s)
    got = evaluate_all([(v.name, v.expression_for(trig)) for v in gear.variables(s, g)], trig)
    want = g.values()
    assert set(got) == set(want)
    for name, value in want.items():
        assert got[name] == pytest.approx(value, rel=1e-9, abs=1e-9), name


def test_the_users_ten_names_are_all_there_in_their_order_after_what_they_use():
    s = spec()
    names = [v.name for v in HELICAL.variables(s, HELICAL.derive(s))]
    positions = [names.index(n) for n in USER_VARIABLES]
    assert positions == sorted(positions)
    assert names.index(HELIX_ANGLE) < names.index("Outer Diameter")
    assert names[-1] == TWIST_ANGLE


def test_the_transverse_pressure_angle_is_written_with_atn():
    s = spec()
    text = {v.name: v.expression for v in HELICAL.variables(s, HELICAL.derive(s))}[TRANSVERSE_PRESSURE_ANGLE]
    assert text == 'atn ( tan ( "Pressure Angle" ) / cos ( "Helix Angle" ) )'


@pytest.mark.parametrize("gear", [HELICAL, HERRINGBONE])
@pytest.mark.parametrize("recipe", ["A", "B"])
def test_both_kinds_plan_soundly_with_both_recipes(gear, recipe):
    s = spec(kind=gear.kind, helix_angle="30", recipe=recipe)
    assert gear.plan(s, gear.derive(s), recipe, "", PATH).check() == []


def _ops(gear, **values):
    s = spec(kind=gear.kind, **values)
    return gear.plan(s, gear.derive(s), "A", "", PATH).ops


def test_a_helical_section_sits_one_module_ahead_of_the_front_plane_and_sweeps_past_the_far_face():
    ops = _ops(HELICAL)
    plane = next(op for op in ops if isinstance(op, RefPlane))
    assert (plane.name, plane.offset, plane.flip) == ("Profile Plane", 2.0, True)
    assert next(op for op in ops if isinstance(op, OpenSketch) and op.id == "space").plane == "plane"
    sweep = next(op for op in ops if isinstance(op, SweepCut))
    assert sweep.twist == pytest.approx((20 + 4) * 360 / 485.527277, abs=1e-6)
    assert not any(isinstance(op, MirrorBody) for op in ops)


def test_the_hand_is_the_reverse_flag_and_a_herringbone_mirrors_before_the_bore():
    right = next(op for op in _ops(HELICAL) if isinstance(op, SweepCut))
    left = next(op for op in _ops(HELICAL, hand="left") if isinstance(op, SweepCut))
    assert (right.reverse, left.reverse) == (False, True)

    ops = _ops(HERRINGBONE, helix_angle="30")
    kinds = [type(op).__name__ for op in ops]
    assert kinds.index("MirrorBody") > kinds.index("CircularPattern")
    bore = next(i for i, op in enumerate(ops) if getattr(op, "name", "") == "Bore")
    assert kinds.index("MirrorBody") < bore
    links = {op.dimension: op.expression for op in ops if isinstance(op, LinkDimension)}
    assert links["Width@Blank"] == '"Mid Width"'
    assert links["Offset@Mid Plane"] == '"Mid Width"'


def test_the_path_is_held_on_the_axis_by_relations_and_two_linked_lengths():
    ops = _ops(HELICAL)
    links = {op.dimension: op.expression for op in ops if isinstance(op, LinkDimension)}
    assert links["Lead In@Path Sketch"] == '"Overrun"'
    assert links["Length@Path Sketch"] == '"Path Length"'
    assert links["Twist@Tooth Space"] == '"Twist Angle"'


@pytest.mark.parametrize("changes, field, words", [
    ({"helix_angle": ""}, "helix_angle", "Helix angle is empty"),
    ({"helix_angle": "0"}, "helix_angle", "a spur gear"),
    ({"helix_angle": "85"}, "helix_angle", "at most 80"),
    ({"hand": "sideways"}, "hand", "Hand must be"),
])
def test_refusals_name_their_field(changes, field, words):
    problems = HELICAL.validate(spec(**changes))
    assert any(p.field == field and words in p.message for p in problems), problems


def test_warnings_for_a_short_overlap_and_an_unusual_herringbone_angle():
    assert any(p.field == "face_width" and "overlap" in p.message for p in HELICAL.validate(spec()))
    assert any(p.field == "helix_angle" for p in HERRINGBONE.validate(spec(kind="herringbone")))
    usual = HERRINGBONE.validate(spec(kind="herringbone", helix_angle="30"))
    assert not [p for p in usual if p.field in ("helix_angle", "face_width")], usual


def test_the_undercut_limit_is_the_helical_one():
    g = HELICAL.derive(spec(teeth="16"))
    assert (g.undercut_limit, g.undercut) == (16, False)
    assert HELICAL.derive(spec(teeth="15")).undercut


def test_face_rotations_turn_the_far_face_for_a_right_hand_gear_and_both_faces_for_a_herringbone():
    g = HELICAL.derive(spec())
    assert g.face_rotations() == pytest.approx((0.0, 14.829239), abs=1e-6)
    assert HELICAL.derive(spec(hand="left")).face_rotations()[1] == pytest.approx(-14.829239, abs=1e-6)
    h = HERRINGBONE.derive(spec(kind="herringbone", helix_angle="15"))
    assert h.face_rotations() == pytest.approx((-14.829239 / 2, -14.829239 / 2), abs=1e-6)


def test_stems_carry_the_helix():
    assert spec().stem() == "Helical_m2_N20_15R"
    assert spec(kind="herringbone", helix_angle="30", hand="left").stem() == "Herringbone_m2_N20_30L"
    pair = PairSpec(mode="pair", gear_a=spec(), gear_b=spec(teeth="40", hand="left"))
    assert pair_stems(pair) == ("Pinion_m2_N20_15R", "Gear_m2_N40_15L", "Pair_m2_20T_40T_H15")
    double = PairSpec(mode="pair", gear_a=spec(kind="herringbone"), gear_b=spec(kind="herringbone", teeth="40", hand="left"))
    assert pair_stems(double) == ("Pinion_m2_N20_HB15R", "Gear_m2_N40_HB15L", "Pair_m2_20T_40T_HB15")
    solved = spec(helix_angle="18.194872")
    assert solved.stem() == "Helical_m2_N20_18.19R"


def test_a_helical_build_runs_plane_sweep_and_pattern_in_order_against_the_fake():
    s = spec(kind="herringbone", helix_angle="30")
    plan = HERRINGBONE.plan(s, HERRINGBONE.derive(s), "A", "", PATH)
    fake = FakeSolidWorks()
    result = swbuild.build(fake, plan, never_exists)
    assert result.ok, result.failures
    called = [name for name, _ in fake.calls]
    assert called.index("ref_plane") < called.index("sweep_cut") < called.index("circular_pattern") \
        < called.index("mirror_body") < called.index("save_as")
    assert result.dimensions["Twist@Tooth Space"] == "Twist@Tooth Space"
    assert "Mirror" in result.features


def test_a_sweep_that_fails_stops_the_build_before_the_pattern():
    s = spec()
    fake = FakeSolidWorks(fail_on={"sweep_cut": "InsertCutSwept5 would not sweep."})
    result = swbuild.build(fake, HELICAL.plan(s, HELICAL.derive(s), "A", "", PATH), never_exists)
    assert not result.ok and "Tooth Space" in result.stopped_at
    assert "circular_pattern" not in [name for name, _ in fake.calls]


def test_hand_is_structural():
    assert "hand" in swbuild.structural_change({"kind": "helical", "recipe": "A", "hand": "right"},
                                               {"kind": "helical", "recipe": "A", "hand": "left"})


def test_readouts_and_candidate_rows_say_the_helix():
    from gear_generator import ui_text
    from gear_generator.gears.pair import solve

    assert ui_text.gear_readout(spec()) == "m2 · z20 · 20° · β15° R · PD 41.411 mm"
    rows = dict(ui_text.derived_rows(HELICAL.derive(spec())))
    assert rows["Helix"] == "15° · right" and rows["Overlap εβ"] == "0.824"
    module, teeth, error, tag = ui_text.candidate_row(solve(60.0, 2.0, kind="helical", helix_range=(8.0, 25.0))[1])
    assert (module, teeth, error, tag) == ("2", "19 : 38", "β18.19° · exact", "exact")
    assert ui_text.KIND_BUTTON_LABELS["herringbone"] == "Double" and ui_text.KIND_LABELS["herringbone"] == "Herringbone"
