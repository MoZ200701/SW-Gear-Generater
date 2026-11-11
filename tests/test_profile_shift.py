"""Profile shift: the shifted tooth, its globals, the working centre distance, and the solver's shifted rows.

The pinned numbers were worked out a second time from the ISO formulas alone,
without this code, before they were written here.
"""

import math

import pytest

from gear_generator import preview, swbuild, ui_text
from gear_generator.gears import KINDS, kind_for, pair, spur
from gear_generator.gears.base import AddGlobal
from gear_generator.gears.equations import DEGREES, RADIANS, evaluate_all
from gear_generator.spec import GearSpec, PairSpec, pair_stems

from test_swbuild import FakeSolidWorks, never_exists

SPUR = KINDS["spur"]
HELICAL = KINDS["helical"]
SHIFTED = GearSpec(module="2", teeth="15", profile_shift="0.3", backlash="0")


def _texts(kind, spec, trig=DEGREES):
    return [v.text(trig) for v in kind.variables(spec, kind.derive(spec))]


# -- one shifted gear ---------------------------------------------------------


def test_the_pinned_shifted_gear():
    g = SPUR.derive(SHIFTED)
    assert g.shift == 0.3
    assert g.da == pytest.approx(35.2)                 # 2 × (15 + 2 + 0.6)
    assert g.df == pytest.approx(26.2)                 # the depth is unchanged
    assert g.d == pytest.approx(30.0) and g.db == pytest.approx(30.0 * math.cos(math.radians(20)))
    assert g.s == pytest.approx(math.pi + 1.2 * math.tan(math.radians(20)), abs=1e-9)
    assert g.tip_thickness == pytest.approx(1.003274, abs=1e-6)
    assert g.n_min == pytest.approx(spur.undercut_minimum(20.0))
    assert g.undercut_limit == pytest.approx(17 * 0.7)      # the tabled 17, times 1 − x


def test_an_unshifted_gear_is_what_it_always_was():
    before = SPUR.derive(GearSpec())
    assert before.shift == 0.0
    assert "Profile Shift" not in before.values()
    texts = _texts(SPUR, GearSpec())
    assert not any("Profile Shift" in t for t in texts) and len(texts) == 24


def test_the_shift_that_clears_undercut_is_the_one_the_form_stops_warning_at():
    """``x_min = (17 − z) / 17``, to the hundredth above: 0.1176 for 15 teeth is 0.12."""
    words = "below the undercut limit"
    assert spur.undercut_free_shift(15, spur.undercut_minimum(20.0)) == 0.12
    assert spur.undercut_free_shift(17, spur.undercut_minimum(20.0)) == 0.0
    assert not any(words in d.message for d in SPUR.validate(SHIFTED.with_values(profile_shift="0.12")))
    warned = [d.message for d in SPUR.validate(SHIFTED.with_values(profile_shift="0.11")) if words in d.message]
    assert warned and warned[0].endswith("A profile shift of 0.12 or more would clear it.")
    unshifted = [d.message for d in SPUR.validate(SHIFTED.with_values(profile_shift="0")) if words in d.message]
    assert "undercut limit of 17:" in unshifted[0]


@pytest.mark.parametrize("changes,field,words", [
    ({"profile_shift": "1.2"}, "profile_shift", "between -1 and 1"),
    ({"profile_shift": "-1.5"}, "profile_shift", "between -1 and 1"),
    ({"profile_shift": "a"}, "profile_shift", "Profile shift must be a number"),
])
def test_a_shift_out_of_range_is_refused_by_name(changes, field, words):
    errors = [d for d in SPUR.validate(SHIFTED.with_values(**changes)) if d.is_error]
    assert any(d.field == field and words in d.message for d in errors), [d.message for d in errors]


@pytest.mark.parametrize("spec,words", [
    (GearSpec(teeth_side="internal", module="2", teeth="60", profile_shift="0.2"), "A ring is cut without"),
    (GearSpec(kind="helical", helix_angle="15", teeth_side="internal", module="2", teeth="60", profile_shift="0.2"),
     "A ring is cut without"),
    (GearSpec(kind="bevel", module="3", teeth="20", mate_teeth="40", profile_shift="0.2"), "Gleason"),
])
def test_a_ring_and_a_bevel_gear_refuse_a_shift(spec, words):
    errors = [d for d in kind_for(spec).validate(spec) if d.is_error]
    assert any(d.field == "profile_shift" and words in d.message for d in errors)


def test_a_big_negative_shift_that_takes_the_root_into_the_bore_is_refused():
    spec = GearSpec(module="2", teeth="15", profile_shift="-1", bore="22")     # the root is at 21
    assert any(d.field == "bore" for d in SPUR.validate(spec) if d.is_error)


# -- its globals --------------------------------------------------------------


def test_the_shift_is_a_global_after_the_pressure_angle_and_the_other_eight_are_the_users():
    texts = _texts(SPUR, SHIFTED)
    assert texts[:6] == [
        '"No. of Teeth"= 15', '"Module"= 2', '"Bore Diameter"= 10', '"Pressure Angle"= 20',
        '"Profile Shift"= 0.3', '"Outer Diameter"= ( "No. of Teeth" + 2 + 2 * "Profile Shift" ) * "Module"',
    ]
    assert '"Arc Length"= ( ( "Module" * pi ) / 2 + "Backlash" - 2 * "Profile Shift" * "Module" * tan ( '\
           '"Pressure Angle" ) )' in texts
    assert '"Pitch Diameter"= "No. of Teeth" * "Module"' in texts
    assert len(texts) == 25


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
@pytest.mark.parametrize("spec", [
    SHIFTED,
    GearSpec(module="1.5", teeth="40", profile_shift="-0.25"),
    GearSpec(module="1", teeth="12", profile_shift="0.5", pressure_angle="25", backlash="0.05"),
    GearSpec(kind="helical", module="2", teeth="15", helix_angle="20", profile_shift="0.3", face_width="20"),
    GearSpec(kind="herringbone", module="2", teeth="18", helix_angle="30", profile_shift="-0.2", face_width="24"),
], ids=["spur+", "spur-", "spur25", "helical", "herringbone"])
def test_every_shifted_global_evaluates_to_the_derived_value(spec, trig):
    kind = kind_for(spec)
    derived = kind.derive(spec)
    variables = kind.variables(spec, derived)
    values = evaluate_all([(v.name, v.expression_for(trig)) for v in variables], trig)
    expected = derived.values()
    assert set(values) == set(expected)
    for name, value in expected.items():
        assert values[name] == pytest.approx(value, abs=1e-9), name


def test_a_helical_shift_is_a_normal_one():
    spec = GearSpec(kind="helical", module="2", teeth="15", helix_angle="20", profile_shift="0.3", backlash="0")
    g = HELICAL.derive(spec)
    mt = 2.0 / math.cos(math.radians(20))
    alpha_t = math.atan(math.tan(math.radians(20)) / math.cos(math.radians(20)))
    assert g.da == pytest.approx(15 * mt + 2 * 2 * 1.3)
    assert g.s == pytest.approx(mt * math.pi / 2 + 2 * 0.3 * 2 * math.tan(alpha_t))
    assert '"Profile Shift"= 0.3' in _texts(HELICAL, spec)


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_a_shifted_gear_plans_and_builds_against_the_fake(recipe):
    spec = GearSpec(module="2", teeth="25", profile_shift="0.3", recipe=recipe)
    assert not [d for d in SPUR.validate(spec) if d.is_error]
    g = SPUR.derive(spec)
    plan = SPUR.plan(spec, g, recipe, "", r"C:\Gears\Gear_m2_N25_x0.3.SLDPRT")
    assert plan.check() == []
    outline = SPUR.outline(spec, g)
    assert outline[0] == outline[-1] and spur.signed_area(outline[:-1]) > 0
    result = swbuild.build(FakeSolidWorks(), plan, never_exists)
    assert result.ok and result.saved, result.log_lines()


# -- a shifted pair -------------------------------------------------------------


def test_the_pinned_spur_pair():
    assert spur.working_pressure_angle(2, 15, 32, 20, 0.3, -0.1) == pytest.approx(21.252173, abs=1e-6)
    centre, ratio, epsilon = pair.describe(2, 15, 32, 20, shift_1=0.3, shift_2=-0.1)
    assert centre == pytest.approx(47.388232, abs=1e-6)
    assert epsilon == pytest.approx(1.489944, abs=1e-6)


def test_the_pinned_helical_pair():
    centre, _, epsilon = pair.describe(2, 15, 30, 20, 20, shift_1=0.3, shift_2=0.2)
    alpha_t = math.degrees(math.atan(math.tan(math.radians(20)) / math.cos(math.radians(20))))
    mt = 2 / math.cos(math.radians(20))
    assert spur.working_pressure_angle(2, 15, 30, alpha_t, 0.3, 0.2, mt) == pytest.approx(23.863851, abs=1e-6)
    assert centre == pytest.approx(48.829820, abs=1e-6)
    assert epsilon == pytest.approx(1.350894, abs=1e-6)


def test_unshifted_the_working_centre_distance_is_the_standard_one():
    assert spur.working_centre_distance(1.5, 20, 60, 20) == 60.0
    assert pair.describe(1.5, 20, 60)[2] == pytest.approx(pair.describe(1.5, 20, 60, shift_1=1e-12)[2], abs=1e-9)
    # Equal and opposite shifts leave the centre distance where it was.
    assert spur.working_centre_distance(2, 15, 45, 20, 0.1, -0.1) == 60.0


def test_the_inverse_involute_undoes_the_involute():
    for degrees in (5.0, 14.5, 20.0, 25.0, 35.0, 50.0):
        angle = math.radians(degrees)
        assert spur.inv_inverse(spur.inv(angle)) == pytest.approx(angle, abs=1e-12)


def test_the_solver_closes_a_centre_distance_gap_with_shift():
    found = pair.solve(47.5, 32 / 15, module=2)
    row = next(c for c in found if c.shifted and (c.teeth_driver, c.teeth_driven) == (15, 32))
    assert row.shift_1 + row.shift_2 == pytest.approx(0.259684, abs=1e-6)
    assert row.centre_distance == pytest.approx(47.5, abs=1e-9) and row.exact
    unshifted = next(c for c in found if not c.shifted and (c.teeth_driver, c.teeth_driven) == (15, 32))
    assert unshifted.centre_error == pytest.approx(-0.5)
    assert found.index(row) < found.index(unshifted)


def test_the_split_gives_an_undercut_pinion_what_it_needs_first():
    limit = spur.undercut_minimum(20.0)
    assert pair.split_shift(0.4, 20, 40, limit, limit) == (0.2, 0.2)
    x1, x2 = pair.split_shift(0.1, 14, 40, limit, limit)
    assert x1 == spur.undercut_free_shift(14, limit) and x1 + x2 == pytest.approx(0.1)


def test_an_exact_undercut_row_is_offered_again_with_equal_and_opposite_shifts():
    found = pair.solve(60, 3)
    plain = next(c for c in found if (c.module, c.teeth_driver, c.teeth_driven) == (2.0, 15, 45) and not c.shifted)
    cured = next(c for c in found if (c.module, c.teeth_driver, c.teeth_driven) == (2.0, 15, 45) and c.shifted)
    assert plain.undercut and not cured.undercut
    assert (cured.shift_1, cured.shift_2) == (0.12, -0.12)
    assert cured.centre_distance == pytest.approx(60.0) and cured.exact
    assert found.index(cured) < found.index(plain)


def test_a_shifted_row_never_has_a_tip_the_form_would_warn_about():
    for candidate in pair.solve(47, 2.2, series="1+2", limit=1000):
        if candidate.shifted:
            for teeth, shift in ((candidate.teeth_driver, candidate.shift_1), (candidate.teeth_driven, candidate.shift_2)):
                tip = pair.tip_thickness(candidate.module, teeth, 20.0, candidate.helix_angle, shift)
                assert tip >= spur.TIP_THICKNESS_WARNING * candidate.module
            assert pair.tip_clearance(candidate.module, candidate.teeth_driver, candidate.teeth_driven, 20.0,
                                      candidate.helix_angle, candidate.shift_1, candidate.shift_2) \
                >= pair.CLEARANCE_MIN * candidate.module


def test_a_helical_pair_with_a_typed_helix_is_shifted_too():
    found = pair.solve(47.5, 2, kind="helical", helix_angle=15, module=2)
    shifted = [c for c in found if c.shifted]
    assert shifted and all(abs(c.centre_distance - 47.5) < 1e-9 for c in shifted if abs(c.shift_1 + c.shift_2) > 0)


def test_rings_crossed_and_bevel_pairs_are_never_shifted():
    assert not any(c.shifted for c in pair.solve(41, 3, mesh="internal"))
    assert not any(c.shifted for c in pair.solve(61, 2, kind="helical", shafts="crossed", shaft_angle=90))
    assert not any(c.shifted for c in pair.solve(51, 2, kind="bevel", shaft_angle=90))


def test_applying_a_row_writes_both_shifts_and_clears_a_stale_one():
    found = pair.solve(60, 3)
    cured = next(c for c in found if c.shifted)
    a, b = pair.apply(cured, GearSpec(), GearSpec())
    assert (a.profile_shift, b.profile_shift) == (ui_text._n(cured.shift_1, 9), ui_text._n(cured.shift_2, 9))
    a, b = pair.apply(found[0], a, b)
    assert (a.profile_shift, b.profile_shift) == ("0", "0")


def test_the_assembly_mates_a_shifted_pair_at_its_working_centre_distance():
    a = GearSpec(module="2", teeth="15", profile_shift="0.3")
    b = GearSpec(module="2", teeth="32", profile_shift="-0.1")
    plan = pair.assembly_plan(a, b, r"C:\a.SLDPRT", r"C:\b.SLDPRT", "", r"C:\p.SLDASM")
    centre = next(op for op in plan.ops if isinstance(op, AddGlobal) and op.name == "Centre Distance")
    assert float(centre.expression) == pytest.approx(47.388232, abs=1e-6)
    assert plan.check() == []


def test_the_assembly_refuses_shifts_whose_tips_hit_the_other_root():
    a = GearSpec(module="2", teeth="20", profile_shift="1")
    b = GearSpec(module="2", teeth="20", profile_shift="1")
    assert pair.tip_clearance(2, 20, 20, 20.0, 0.0, 1.0, 1.0) < 0
    with pytest.raises(Exception, match="reaches the other gear's root"):
        pair.assembly_plan(a, b, r"C:\a.SLDPRT", r"C:\b.SLDPRT", "", r"C:\p.SLDASM")
    assert "cannot be built" in pair.mesh_warnings(SPUR.derive(a), SPUR.derive(b))[0]


def test_a_ring_pair_and_a_crossed_pair_refuse_a_shift():
    pinion = GearSpec(module="2", teeth="20", profile_shift="0.2")
    ring = GearSpec(module="2", teeth="60", teeth_side="internal")
    with pytest.raises(Exception, match="without profile shift"):
        pair.assembly_plan(pinion, ring, r"C:\a.SLDPRT", r"C:\b.SLDPRT", "", r"C:\p.SLDASM")
    one = GearSpec(kind="helical", module="2", teeth="20", helix_angle="45", profile_shift="0.2")
    two = GearSpec(kind="helical", module="2", teeth="40", helix_angle="45")
    with pytest.raises(Exception, match="without profile shift"):
        pair.crossed_assembly_plan(one, two, r"C:\a.SLDPRT", r"C:\b.SLDPRT", "", r"C:\p.SLDASM", 90.0,
                                   route=pair.ROUTE_MATES)


def test_the_preview_puts_a_shifted_pair_at_its_working_centre_distance():
    a = SPUR.derive(GearSpec(module="2", teeth="15", profile_shift="0.3"))
    b = SPUR.derive(GearSpec(module="2", teeth="32", profile_shift="-0.1"))
    made = preview.layout([a, b])
    assert made.centre_distance == pytest.approx(47.388232, abs=1e-6)
    assert made.dimension.text == "C 47.388 mm"


# -- names, records and words -----------------------------------------------------


def test_a_shifted_gear_and_pair_are_named_for_their_shifts():
    assert SHIFTED.default_stem() == "Gear_m2_N15_x0.3"
    assert GearSpec(profile_shift="-0.050501234").default_stem() == "Gear_m1.5_N25_x-0.051"
    assert GearSpec(kind="bevel", mate_teeth="40", profile_shift="0.2").default_stem() == "Bevel_m1.5_N25_M40"
    pair_spec = PairSpec(mode="pair", gear_a=GearSpec(teeth="15", profile_shift="0.1"),
                         gear_b=GearSpec(teeth="45", profile_shift="-0.1"))
    assert pair_stems(pair_spec) == ("Pinion_m1.5_N15_x0.1", "Gear_m1.5_N45_x-0.1", "Pair_m1.5_15T_45T_x0.1_-0.1")


@pytest.mark.parametrize("built,wanted,refused", [
    ({"profile_shift": "0"}, {"profile_shift": "0.2"}, True),
    ({"profile_shift": "0.2"}, {"profile_shift": ""}, True),
    ({"profile_shift": "0.2"}, {"profile_shift": "0.35"}, False),
    ({}, {"profile_shift": "0"}, False),
])
def test_adding_or_removing_a_shift_is_structural(built, wanted, refused):
    text = swbuild.structural_change({"kind": "spur", **built}, {"kind": "spur", **wanted})
    assert ("Profile shift" in text) == refused


def test_the_readouts_carry_the_shift():
    assert ui_text.gear_readout(SHIFTED) == "m2 · z15 · 20° · x+0.3 · PD 30 mm"
    rows = dict(ui_text.derived_rows(SPUR.derive(SHIFTED)))
    assert rows["Profile shift"] == "+0.3 · 0.6"
    assert "Profile shift" not in dict(ui_text.derived_rows(SPUR.derive(GearSpec())))
    worked = ui_text.explainer("profile_shift", SPUR.derive(SHIFTED))[3]
    assert worked.startswith("x +0.3 → OD 35.2 mm · root 26.2") and worked.endswith("undercut below 11.9 teeth")
    rows = ui_text.pair_derived_rows(47.388, 2.133, 1.49, 15, 32, working_angle=21.252173)
    assert rows[-1] == ("Working α", "21.252°")


def test_a_shifted_candidate_row_says_its_shifts():
    cured = next(c for c in pair.solve(60, 3) if c.shifted)
    assert ui_text.candidate_row(cured)[2].startswith("x +0.3/−0.3 · exact")
