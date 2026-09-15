"""Crossed-axis helical pairs: the centre distance, where gear 2 goes, the solver and the assembly."""

import math

import pytest

from gear_generator import swbuild
from gear_generator.gears import KINDS, crossed, pair
from gear_generator.gears.base import AddGlobal, LinkDimension, Mate, Place
from gear_generator.spec import GearSpec, InputError, PairSpec, pair_stems

from test_swbuild import FakeSolidWorks, never_exists

HELICAL = KINDS["helical"]


def gears(beta_1="45", beta_2="45", hand="right", teeth=("20", "40"), widths=("20", "16")):
    a = GearSpec(kind="helical", module="2", teeth=teeth[0], helix_angle=beta_1, hand=hand, face_width=widths[0])
    b = GearSpec(kind="helical", module="2", teeth=teeth[1], helix_angle=beta_2, hand=hand, face_width=widths[1])
    return a, b


def test_the_pinned_centre_distances():
    assert crossed.centre_distance(2, 20, 40, 45, 45) == pytest.approx(84.852814, abs=1e-6)
    assert crossed.centre_distance(2, 20, 40, 30, 60) == pytest.approx(103.094011, abs=1e-6)
    a, b = gears()
    d1, d2 = HELICAL.derive(a).section.d, HELICAL.derive(b).section.d
    assert (d1, d2) == (pytest.approx(56.568542, abs=1e-6), pytest.approx(113.137085, abs=1e-6))


def test_the_helix_angle_that_meets_a_centre_distance_is_found_nearest_half_the_shaft():
    assert crossed.beta_1_for(2, 20, 40, 90, 60 * math.sqrt(2)) == pytest.approx(45.0, abs=1e-9)
    assert crossed.beta_1_for(2, 20, 40, 90, 40.0) is None          # closer than any pair of angles allows


@pytest.mark.parametrize("hand", ["right", "left"])
@pytest.mark.parametrize("beta_1, beta_2, shaft, teeth", [
    (45, 45, 90, (20, 40)), (30, 60, 90, (20, 40)), (25, 45, 70, (17, 31)),
])
def test_gear_two_is_placed_where_its_teeth_meet_gear_ones(hand, beta_1, beta_2, shaft, teeth):
    a, b = gears(str(beta_1), str(beta_2), hand, (str(teeth[0]), str(teeth[1])))
    g1, g2 = HELICAL.derive(a), HELICAL.derive(b)
    p = crossed.placement(g1, g2, shaft)
    assert p.centre_distance == pytest.approx(crossed.centre_distance(2, teeth[0], teeth[1], beta_1, beta_2))
    # The axes: gear 2's crosses x = C, square to X, at the shaft angle to gear 1's.
    assert p.origin[0] == pytest.approx(p.centre_distance) and abs(p.axis_2[0]) < 1e-12
    assert crossed.angle_between((0.0, 0.0, 1.0), p.axis_2) == pytest.approx(shaft)
    # The tooth lines lie along each other where the gears touch.
    d1 = crossed.tooth_direction(g1, 0.0)
    d2 = crossed.apply(p.rotation, crossed.tooth_direction(g2, 180.0 - p.spin))
    along = crossed.angle_between(d1, d2)
    assert min(along, 180.0 - along) < 1e-5
    # Gear 1 has a space centred on +X there, and gear 2 a tooth centred on the same point.
    pitch_1, pitch_2 = 360.0 / teeth[0], 360.0 / teeth[1]
    offset = crossed.twist_at(g1, p.gear_1_contact_z) % pitch_1
    assert min(offset, pitch_1 - offset) < 1e-9
    base = pitch_2 / 2.0 + crossed.twist_at(g2, p.gear_2_contact_z)
    azimuth = base + round((180.0 - p.spin - base) / pitch_2) * pitch_2
    local = (g2.rp * math.cos(math.radians(azimuth)), g2.rp * math.sin(math.radians(azimuth)), p.gear_2_contact_z)
    moved = crossed.apply(p.rotation, local)
    assert math.dist(tuple(moved[i] + p.origin[i] for i in range(3)), p.contact) < 1e-9
    assert abs(p.gear_1_contact_z - g1.face_width / 2.0) <= g1.lead / g1.teeth / 2.0 + 1e-9


def test_the_turn_about_x_follows_the_hand():
    right = crossed.placement(*(HELICAL.derive(g) for g in gears()), 90.0)
    left = crossed.placement(*(HELICAL.derive(g) for g in gears(hand="left")), 90.0)
    assert (right.tilt, left.tilt) == (-90.0, 90.0)


def test_what_would_not_mesh_is_said():
    a, b = gears("30", "45")
    problems = crossed.validate(HELICAL.derive(a), HELICAL.derive(b), 90.0)
    assert any("add up to 75" in p for p in problems)
    a, b = gears()
    b = b.with_values(hand="left")
    assert any("same hand" in p for p in crossed.validate(HELICAL.derive(a), HELICAL.derive(b), 90.0))
    with pytest.raises(ValueError, match="same hand"):
        crossed.placement(HELICAL.derive(a), HELICAL.derive(b), 90.0)


def test_a_steep_helix_is_allowed_on_one_gear_and_warned_about():
    steep = GearSpec(kind="helical", module="2", teeth="40", helix_angle="60", face_width="16")
    problems = HELICAL.validate(steep)
    assert not [p for p in problems if p.is_error]
    assert any(p.field == "helix_angle" and "usual" in p.message for p in problems)


# -- the solver ---------------------------------------------------------------


def test_a_typed_module_finds_twenty_to_forty_at_forty_five_degrees_first():
    found = pair.solve(60 * math.sqrt(2), 2, module=2.0, shafts="crossed", shaft_angle=90.0, kind="helical")
    best = found[0]
    assert (best.module, best.teeth_driver, best.teeth_driven) == (2.0, 20, 40)
    assert best.helix_angle == pytest.approx(45.0, abs=1e-6) and best.helix_angle_b == pytest.approx(45.0, abs=1e-6)
    assert best.exact and best.crossed
    assert all(abs(c.helix_angle + c.helix_angle_b - 90.0) < 1e-9 for c in found)
    assert all(abs(c.centre_error) < 1e-9 for c in found)
    assert found == sorted(found, key=pair.Candidate.rank)


def test_a_typed_helix_angle_is_held_and_the_nearest_teeth_are_offered():
    found = pair.solve(crossed.centre_distance(2, 20, 40, 30, 60), 2, module=2.0, helix_angle=30.0,
                       shafts="crossed", shaft_angle=90.0)
    best = found[0]
    assert (best.teeth_driver, best.teeth_driven, best.helix_angle, best.helix_angle_b) == (20, 40, 30.0, 60.0)
    assert best.exact
    # Typed a hair off, the nearest miss still comes first.
    near = pair.solve(103.094011, 2, module=2.0, helix_angle=30.0, shafts="crossed", shaft_angle=90.0)[0]
    assert (near.teeth_driver, near.teeth_driven) == (20, 40)


def test_the_crossed_solve_spec_and_apply():
    a, b = gears("15", "15")
    spec = PairSpec(mode="pair", shafts="crossed", shaft_angle="90", centre_distance=str(60 * math.sqrt(2)),
                    ratio="2", module="2", gear_a=a, gear_b=b)
    chosen = pair.solve_spec(spec)[0]
    new_a, new_b = pair.apply(chosen, a, b.with_values(hand="left"))
    assert (new_a.teeth, new_b.teeth, new_a.helix_angle, new_b.helix_angle) == ("20", "40", "45", "45")
    assert new_b.hand == new_a.hand == "right"


def test_crossed_shafts_are_refused_outside_their_range():
    with pytest.raises(InputError, match="shaft angle"):
        pair.solve(80, 2, shafts="crossed", shaft_angle=5.0)
    with pytest.raises(InputError, match="both must be between"):
        pair.solve(80, 2, shafts="crossed", shaft_angle=90.0, helix_angle=95.0)


def test_describe_crossed():
    centre, ratio, epsilon = pair.describe_crossed(2, 20, 40, 45, 45)
    assert centre == pytest.approx(84.852814, abs=1e-6) and ratio == 2.0 and 1.0 < epsilon < 3.0


# -- the assembly -------------------------------------------------------------


@pytest.mark.parametrize("route", [pair.ROUTE_MATES, pair.ROUTE_FIXED])
def test_both_routes_plan_soundly(route):
    a, b = gears()
    plan = pair.crossed_assembly_plan(a, b, r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "", r"C:\G\p.SLDASM", 90.0, route)
    assert plan.check() == []
    place = [op for op in plan.ops if isinstance(op, Place)][-1]
    assert place.component == "gear2" and place.at[0] == pytest.approx(84.852814, abs=1e-6)
    globals_ = {op.name: op.expression for op in plan.ops if isinstance(op, AddGlobal)}
    assert globals_["Shaft Angle"] == "90" and globals_["Helix Angle 2"] == "45"
    if route == pair.ROUTE_MATES:
        kinds = [(op.id, op.kind) for op in plan.ops if isinstance(op, Mate)]
        assert kinds == [("centre", "distance"), ("shaft", "axis angle"), ("offset_y", "point distance"),
                         ("offset_z", "point distance"), ("mesh", "angle")]
        links = [op.dimension for op in plan.ops if isinstance(op, LinkDimension)]
        assert links == ["D1@Centre Distance", "D1@Shaft Angle", "D1@Offset Y", "D1@Offset Z", "D1@Mesh Angle"]
    else:
        assert not any(isinstance(op, Mate) for op in plan.ops) and plan.notes


def test_a_crossed_assembly_builds_against_the_fake():
    a, b = gears()
    plan = pair.crossed_assembly_plan(a, b, r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "", r"C:\G\p.SLDASM", 90.0,
                                      pair.ROUTE_MATES)
    fake = FakeSolidWorks()
    result = swbuild.build(fake, plan, never_exists)
    assert result.ok, result.failures
    called = [name for name, _ in fake.calls]
    assert called.index("place_component") < called.index("add_mate")


def test_crossed_assemblies_refuse_what_is_not_a_crossed_pair():
    a, b = gears()
    with pytest.raises(InputError, match="helical"):
        pair.crossed_assembly_plan(a.with_values(kind="spur"), b, "a", "b", "", "p", 90.0, pair.ROUTE_MATES)
    with pytest.raises(InputError, match="add up"):
        pair.crossed_assembly_plan(a, b, "a", "b", "", "p", 80.0, pair.ROUTE_MATES)
    with pytest.raises(InputError, match="settled"):
        pair.crossed_assembly_plan(a, b, "a", "b", "", "p", 90.0, "guess")


def test_a_crossed_pair_is_named_for_its_shaft_angle():
    a, b = gears()
    spec = PairSpec(mode="pair", shafts="crossed", shaft_angle="90", gear_a=a, gear_b=b)
    assert pair_stems(spec) == ("Pinion_m2_N20_45R", "Gear_m2_N40_45R", "Pair_m2_20T_40T_X90")
