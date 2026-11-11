"""Straight bevel gears: Gleason proportions, the back-cone section, the globals and the plan."""

import math

import pytest

from gear_generator import swbuild
from gear_generator.gears import KINDS, bevel, kind_for
from gear_generator.gears.base import LinkDimension, LoftCut, RefPlaneNormal, Revolve
from gear_generator.gears.equations import DEGREES, RADIANS, evaluate_all
from gear_generator.spec import GearSpec

from test_swbuild import FakeSolidWorks, never_exists

BEVEL = KINDS["bevel"]
PATH = r"C:\Gears\Bevel_m3_N20_M40.SLDPRT"


def spec(teeth="20", mate="40", **values):
    base = dict(kind="bevel", module="3", teeth=teeth, mate_teeth=mate, shaft_angle="90", face_width="20", bore="10")
    base.update(values)
    return GearSpec(**base)


def test_the_pinned_pinion():
    g = BEVEL.derive(spec())
    assert g.delta == pytest.approx(26.565051, abs=1e-6)
    assert g.cone_distance == pytest.approx(67.082039, abs=1e-6)
    assert (g.addendum, g.dedendum) == (pytest.approx(4.035, abs=1e-9), pytest.approx(2.529, abs=1e-9))
    assert g.dedendum_angle == pytest.approx(2.159034, abs=1e-6)
    assert g.mate_dedendum_angle == pytest.approx(3.921938, abs=1e-6)
    assert g.face_angle == pytest.approx(30.486989, abs=1e-6)
    assert g.root_angle == pytest.approx(24.406017, abs=1e-6)
    assert g.da == pytest.approx(67.218027, abs=1e-6)
    assert g.crown_to_apex == pytest.approx(58.195493, abs=1e-6)
    assert g.shift == pytest.approx(0.345, abs=1e-9)
    assert g.section.s + g.section.backlash == pytest.approx(5.465807, abs=1e-6)
    assert g.virtual_teeth == pytest.approx(22.360680, abs=1e-6)
    assert g.virtual_radius == pytest.approx(33.541020, abs=1e-6)
    assert bevel.undercut_limit(20.0, g.shift) == pytest.approx(11.1987, abs=1e-4)
    assert bevel.contact_ratio(g) == pytest.approx(1.6315, abs=1e-4)
    assert g.toe_scale == pytest.approx(0.701858, abs=1e-6)
    assert g.section.d == pytest.approx(2 * g.virtual_radius)      # the section is the back cone's


def test_the_pinned_gear_is_the_pinions_mate():
    g = BEVEL.derive(spec("40", "20"))
    assert g.delta == pytest.approx(63.434949, abs=1e-6)
    assert (g.addendum, g.dedendum) == (pytest.approx(1.965, abs=1e-9), pytest.approx(4.599, abs=1e-9))
    assert g.face_angle == pytest.approx(65.593983, abs=1e-6)
    assert g.root_angle == pytest.approx(59.513011, abs=1e-6)
    assert g.da == pytest.approx(121.757549, abs=1e-6)
    assert g.crown_to_apex == pytest.approx(28.242451, abs=1e-6)
    assert g.section.s + g.section.backlash == pytest.approx(3.958971, abs=1e-6)
    pinion = BEVEL.derive(spec())
    assert pinion.addendum + g.addendum == pytest.approx(6.0)
    assert pinion.cone_distance == pytest.approx(g.cone_distance)
    assert bevel.cone_distance(3, 20, 40, 90) == pytest.approx(g.cone_distance)


def test_equal_teeth_have_the_module_as_addendum_and_the_roles_swap_at_the_mate():
    g = BEVEL.derive(spec("25", "25"))
    assert g.addendum == pytest.approx(3.0) and g.delta == pytest.approx(45.0)
    below, above = BEVEL.derive(spec("24", "25")), BEVEL.derive(spec("26", "25"))
    assert below.addendum > 3.0 > above.addendum


def test_a_shaft_angle_over_ninety_turns_the_cone_past_the_right_angle_branch():
    g = BEVEL.derive(spec("40", "25", shaft_angle="120"))
    assert g.delta + g.delta_mate == pytest.approx(120.0)
    assert g.delta == pytest.approx(math.degrees(math.atan2(math.sin(math.radians(120)), 0.625 + math.cos(math.radians(120)))))
    assert BEVEL.derive(spec("40", "16", shaft_angle="120")).form == bevel.FORM_INTERNAL    # see test_bevel_forms
    with pytest.raises(Exception, match="too near a crown gear"):
        BEVEL.derive(spec("40", "20", shaft_angle="120.5"))


@pytest.mark.parametrize("teeth, mate, shaft", [("20", "40", "90"), ("40", "20", "90"), ("25", "25", "90"),
                                                ("30", "17", "70"), ("40", "25", "120")])
@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_every_global_evaluates_to_the_maths(teeth, mate, shaft, trig):
    s = spec(teeth, mate, shaft_angle=shaft)
    g = BEVEL.derive(s)
    got = evaluate_all([(v.name, v.expression_for(trig)) for v in BEVEL.variables(s, g)], trig)
    want = g.values()
    assert set(got) == set(want)
    for name, value in want.items():
        assert got[name] == pytest.approx(value, rel=1e-9, abs=1e-9), name


def test_the_users_names_in_their_order():
    s = spec()
    names = [v.name for v in BEVEL.variables(s, BEVEL.derive(s))]
    positions = [names.index(n) for n in bevel.USER_VARIABLES]
    assert positions == sorted(positions)


@pytest.mark.parametrize("teeth, mate, bore", [("20", "40", "10"), ("40", "20", ""), ("25", "25", "8")])
@pytest.mark.parametrize("recipe", ["A", "B"])
def test_the_plan_is_sound(teeth, mate, bore, recipe):
    s = spec(teeth, mate, bore=bore, recipe=recipe)
    plan = BEVEL.plan(s, BEVEL.derive(s), recipe, "", PATH)
    assert plan.check() == []
    kinds = [type(op).__name__ for op in plan.ops]
    assert kinds.index("Revolve") < kinds.index("RefPlaneNormal") < kinds.index("LoftCut") < kinds.index("CircularPattern")


def test_the_plan_names_what_it_makes_and_links_the_sections():
    s = spec()
    ops = BEVEL.plan(s, BEVEL.derive(s), "A", "", PATH).ops
    names = [getattr(op, "name", "") for op in ops]
    for name in ("Gear Axis", "Blank Sketch", "Blank", "Cone Sketch", "Heel Plane", "Toe Plane", "Heel Section Sketch",
                 "Toe Section Sketch", "Tooth Space", "Teeth"):
        assert name in names, name
    links = {op.dimension: op.expression for op in ops if isinstance(op, LinkDimension)}
    assert links["Heel@Cone Sketch"] == '"Heel Distance"'
    assert links["Centre@Heel Section Sketch"] == '"Heel Virtual Radius"'
    assert links["Root@Toe Section Sketch"] == '( "Root Diameter" / 2 ) * "Toe Scale"'
    loft = next(op for op in ops if isinstance(op, LoftCut))
    assert loft.profiles == ("heel_space", "toe_space")
    revolve = next(op for op in ops if isinstance(op, Revolve))
    assert (revolve.sketch, revolve.axis) == ("blank", "A")
    planes = [op for op in ops if isinstance(op, RefPlaneNormal)]
    assert [(p.line, p.point) for p in planes] == [("c_Gh", "c_Gh.end"), ("c_Gt", "c_Gt.end")]


def test_the_half_section_is_a_closed_counter_clockwise_loop_on_the_right_side_of_the_axis():
    from gear_generator.gears.spur import signed_area

    for teeth, mate, bore in (("20", "40", "10"), ("40", "20", "")):
        g = BEVEL.derive(spec(teeth, mate, bore=bore))
        loop = bevel.outline(g)
        assert loop[0] == loop[-1]
        assert signed_area(loop[:-1]) > 0 and all(x >= g.bore / 2.0 - 1e-9 for x, _ in loop)
        p = bevel.blank_points(g)
        assert math.hypot(*p.pitch) == pytest.approx(g.cone_distance)
        assert p.heel_tip[0] == pytest.approx(g.da / 2.0)                 # the outside diameter
        assert p.heel_tip[1] == pytest.approx(g.crown_to_apex)            # apex to crown


@pytest.mark.parametrize("changes, field, words", [
    ({"mate_teeth": ""}, "mate_teeth", "Mate teeth is empty"),
    ({"mate_teeth": "4"}, "mate_teeth", "at least 6"),
    ({"shaft_angle": "5"}, "shaft_angle", "between 10"),
    ({"face_width": "40"}, "face_width", "half the cone distance"),
    ({"bore": "40"}, "bore", "within a module of the root"),
    ({"teeth_side": "internal"}, "teeth_side", "external gear's"),
])
def test_refusals_name_their_field(changes, field, words):
    problems = BEVEL.validate(spec(**changes))
    assert any(p.field == field and words in p.message for p in problems), problems


def test_a_wide_face_is_warned_about_and_a_usual_one_is_not():
    assert any(p.field == "face_width" and "Gleason" in p.message for p in BEVEL.validate(spec(face_width="25")))
    assert not [p for p in BEVEL.validate(spec("40", "20", face_width="18")) if p.field == "face_width"]


def test_the_stem_names_the_mate_and_an_unusual_shaft():
    assert spec().stem() == "Bevel_m3_N20_M40"
    assert spec(shaft_angle="80").stem() == "Bevel_m3_N20_M40_S80"
    assert kind_for(spec()) is BEVEL


def test_a_bevel_gear_builds_against_the_fake():
    s = spec()
    fake = FakeSolidWorks()
    result = swbuild.build(fake, BEVEL.plan(s, BEVEL.derive(s), "A", "", PATH), never_exists)
    assert result.ok, result.failures
    called = [name for name, _ in fake.calls]
    assert called.index("revolve") < called.index("ref_plane_normal") < called.index("loft_cut") \
        < called.index("circular_pattern") < called.index("save_as")


# -- pairs -------------------------------------------------------------------


def test_the_pinned_bevel_pair_rows():
    from gear_generator.gears import pair

    rows = pair.solve(50, 4 / 3, kind="bevel", shaft_angle=90)
    head = [(round(r.module, 6), r.teeth_driver, r.teeth_driven) for r in rows[:7]]
    assert head == [(5.0, 12, 16), (4.0, 15, 20), (2.5, 24, 32), (2.0, 30, 40), (1.25, 48, 64), (1.0, 60, 80),
                    (3.333333, 18, 24)]
    assert all(r.cone and not r.crossed and r.exact and not r.undercut for r in rows[:6])
    assert not rows[6].standard
    assert rows[1].centre_distance == pytest.approx(bevel.cone_distance(4, 15, 20, 90))


def test_a_bevel_pair_row_agrees_with_the_gear_it_would_build():
    from gear_generator.gears import pair

    row = pair.bevel_candidate(3, 20, 40, 90)
    g = BEVEL.derive(spec())
    assert row.centre_distance == pytest.approx(g.cone_distance)
    assert row.contact_ratio == pytest.approx(bevel.contact_ratio(g))
    assert pair.bevel_candidate(3, 40, 20, 120.5) is None                 # too near a crown gear to be offered


def test_solving_a_bevel_pair_from_the_form_and_applying_a_row():
    from gear_generator.gears import pair
    from gear_generator.spec import PairSpec

    a, b = spec(teeth="", mate=""), spec(teeth="", mate="")
    form = PairSpec(gear_a=a, gear_b=b, centre_distance="", ratio="4:3", cone_distance="50", shaft_angle="90")
    rows = pair.solve_spec(form)
    new_a, new_b = pair.apply(rows[1], a, b)
    assert (new_a.module, new_a.teeth, new_a.mate_teeth, new_a.shaft_angle) == ("4", "15", "20", "90")
    assert (new_b.teeth, new_b.mate_teeth) == ("20", "15")
    assert new_a.face_width == a.face_width and new_a.bore == a.bore


def test_the_bevel_assembly_mates_apexes_and_drives_the_shaft_angle():
    from gear_generator.gears import crossed, pair
    from gear_generator.gears.base import Mate, Place

    a, b = spec(), spec("40", "20")
    plan = pair.assembly_plan(a, b, r"C:\p.SLDPRT", r"C:\g.SLDPRT", "", r"C:\a.SLDASM")
    assert plan.check() == []
    mates = [(m.kind, m.a, m.b, m.value) for m in plan.ops if isinstance(m, Mate)]
    assert mates == [("point", "gear2:origin", "gear1:origin", 0.0),
                     ("coincident", "gear2:Gear Axis", "gear1:plane2", 0.0),
                     ("axis angle", "gear2:Gear Axis", "gear1:Gear Axis", 90.0),
                     ("angle", "gear2:plane2", "gear1:plane2", pair.mate_angle(40))]
    placed = [op for op in plan.ops if isinstance(op, Place)]
    assert placed[0].component == "gear1" and placed[0].rotation == pair.IDENTITY
    axis = crossed.apply(tuple(tuple(placed[1].rotation[i * 3:i * 3 + 3]) for i in range(3)), (0.0, 0.0, 1.0))
    assert axis == pytest.approx((1.0, 0.0, 0.0), abs=1e-12)
    with pytest.raises(Exception, match="mate teeth"):
        pair.assembly_plan(a, spec("40", "21"), r"C:\p.SLDPRT", r"C:\g.SLDPRT", "", r"C:\a.SLDASM")


def test_the_dry_run_prints_a_bevel_gear_and_a_ring(capsys):
    from gear_generator.gears.__main__ import main

    assert main(["--spec", "kind=bevel,m=3,z=20,mate=40,b=20,bore=10"]) == 0
    printed = capsys.readouterr().out
    assert "plan    bevel · recipe A" in printed and "Bevel_m3_N20_M40.SLDPRT" in printed
    assert main(["--spec", "side=internal,m=2,z=60"]) == 0
    assert "Ring_m2_N60.SLDPRT" in capsys.readouterr().out
    assert main(["--spec", "kind=bevel,side=internal,m=3,z=20,mate=40"]) == 1
