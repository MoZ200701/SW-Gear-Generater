"""Internal gears: a ring's section, its globals, its plan, and a pinion meshing inside it."""

import math

import pytest

from gear_generator import swbuild
from gear_generator.gears import INTERNAL_KINDS, KINDS, internal, kind_for, pair
from gear_generator.gears.base import AddComponent, CircularPattern, Cut, Extrude, LinkDimension, Mate, SweepCut
from gear_generator.gears.equations import DEGREES, RADIANS, evaluate_all
from gear_generator.gears.spur import _polar, _radius
from gear_generator.spec import GearSpec, InputError, PairSpec, pair_stems

from test_swbuild import FakeSolidWorks, never_exists

PATH = r"C:\Gears\Ring_m2_N60.SLDPRT"


def ring(kind="spur", **values):
    base = dict(kind=kind, module="2", teeth="60", teeth_side="internal", bore="", face_width="20")
    if kind != "spur":
        base["helix_angle"] = "30" if kind == "herringbone" else "15"
    base.update(values)
    return GearSpec(**base)


def test_the_pinned_section():
    g = kind_for(ring()).derive(ring())
    assert (g.d, g.da, g.df) == (120.0, 116.0, 125.0)
    assert g.db == pytest.approx(112.763114, abs=1e-6)
    assert g.flank_start_d == 114.0            # a module inside the tip circle: the base circle is further in
    assert g.tip_cap_d == 112.0 and g.rim == 137.0
    assert g.fillet == pytest.approx(0.3) and g.flank_end_d == pytest.approx(124.1)
    assert internal.contact_ratio(2, 20, 60, 20) == pytest.approx(1.949662, abs=1e-6)
    assert pair.internal_mesh_angle(20) == 9.0


def test_the_flank_crosses_the_pitch_circle_at_half_the_space_and_narrows_outward():
    g = kind_for(ring()).derive(ring())
    at_pitch = internal.flank_point(g, math.sqrt((g.d / g.db) ** 2 - 1.0))
    assert _radius(at_pitch) == pytest.approx(60.0, abs=1e-9)
    assert _polar(at_pitch) == pytest.approx(g.psi_s, abs=1e-12)
    assert internal.half_space_angle(g, 62.0) < g.psi_s < internal.half_space_angle(g, 58.0)


def test_recipe_b_osculates_the_involute_at_the_pitch_point():
    g = kind_for(ring()).derive(ring())
    f = internal.arc_flank(g)
    b = f.centre
    assert _polar(b) == pytest.approx(g.psi_s - g.alpha)
    assert _radius((f.pitch_point[0] - b[0], f.pitch_point[1] - b[1])) == pytest.approx(f.radius, abs=1e-9)
    errors = []
    for dt in (-0.02, 0.02):
        q = internal.flank_point(g, math.tan(g.alpha) + dt)
        errors.append(_radius((q[0] - b[0], q[1] - b[1])) - f.radius)
    # Osculating, not merely tangent: the error changes sign across the pitch point and is tiny.
    assert errors[0] * errors[1] < 0 and max(map(abs, errors)) < 1e-4
    assert _radius((f.fillet_centre[0] - b[0], f.fillet_centre[1] - b[1])) == pytest.approx(f.radius - g.fillet)
    assert _radius(f.fillet_centre) == pytest.approx(g.rf - g.fillet)
    assert 0.0 < _polar(f.fillet_centre) < _polar(f.cap_point)


def test_tip_clash_pins_and_its_negative_control():
    assert internal.tip_clash(1, 50, 60) <= 1e-4
    assert internal.tip_clash(1, 54, 60) == pytest.approx(0.138, abs=0.005)
    assert internal.tip_clash(2, 54, 60) == pytest.approx(2 * internal.tip_clash(1, 54, 60))
    assert internal.tip_clash(1, 20, 60) <= 1e-4
    assert internal.tip_clash(1, 20, 60, phase=math.pi / 20) == pytest.approx(0.966, abs=0.005)
    with pytest.raises(ValueError):
        internal.tip_clash(1, 60, 60)


@pytest.mark.parametrize("kind", ["spur", "helical", "herringbone"])
@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_every_global_evaluates_to_the_maths(kind, trig):
    s = ring(kind)
    gear = kind_for(s)
    g = gear.derive(s)
    got = evaluate_all([(v.name, v.expression_for(trig)) for v in gear.variables(s, g)], trig)
    want = g.values()
    assert set(got) == set(want)
    for name, value in want.items():
        assert got[name] == pytest.approx(value, rel=1e-9, abs=1e-9), name


@pytest.mark.parametrize("kind", ["spur", "helical"])
def test_eight_of_the_users_names_in_their_order_and_no_outer_diameter_or_bore(kind):
    s = ring(kind, rim="150")
    gear = kind_for(s)
    names = [v.name for v in gear.variables(s, gear.derive(s))]
    positions = [names.index(n) for n in internal.USER_VARIABLES]
    assert positions == sorted(positions)
    assert "Outer Diameter" not in names and "Bore Diameter" not in names
    texts = {v.name: v.expression for v in gear.variables(s, gear.derive(s))}
    assert texts["Rim Diameter"] == "150"
    assert texts["Flank Offset"].startswith("0 - ")


def test_a_blank_rim_is_an_equation_on_the_root():
    s = ring()
    texts = {v.name: v.expression for v in kind_for(s).variables(s, kind_for(s).derive(s))}
    assert texts["Rim Diameter"] == '"Root Diameter" + 6 * "Module"'
    assert texts["Inner Diameter"] == '( "No. of Teeth" - 2 ) * "Module"'


@pytest.mark.parametrize("kind", ["spur", "helical", "herringbone"])
@pytest.mark.parametrize("recipe", ["A", "B"])
def test_every_ring_plans_soundly_with_both_recipes(kind, recipe):
    s = ring(kind, recipe=recipe)
    gear = kind_for(s)
    g = gear.derive(s)
    assert [d for d in gear.validate(s) if d.is_error] == []
    plan = gear.plan(s, g, recipe, "", PATH)
    assert plan.check() == []
    assert plan.kind == f"internal {kind}"
    loop = gear.outline(s, g, recipe)
    assert loop[0] == loop[-1] and len(loop) > 60 * 10


def test_the_blank_is_an_annulus_and_there_is_no_bore():
    s = ring(bore="10")
    ops = kind_for(s).plan(s, kind_for(s).derive(s), "A", "", PATH).ops
    links = {op.dimension: op.expression for op in ops if isinstance(op, LinkDimension)}
    assert links["Rim@Blank Sketch"] == '"Rim Diameter"'
    assert links["Tip@Blank Sketch"] == '"Inner Diameter"'
    assert links["Cap@Tooth Space Sketch"] == '"Tip Cap Diameter"'
    assert not any(getattr(op, "name", "") == "Bore" for op in ops)
    assert isinstance(next(op for op in ops if getattr(op, "name", "") == "Tooth Space"), Cut)


def test_a_helical_ring_sweeps_its_section_and_a_herringbone_halves_the_annulus():
    s = ring("helical")
    ops = kind_for(s).plan(s, kind_for(s).derive(s), "A", "", PATH).ops
    assert any(isinstance(op, SweepCut) for op in ops)
    h = ring("herringbone")
    ops = kind_for(h).plan(h, kind_for(h).derive(h), "A", "", PATH).ops
    assert next(op for op in ops if isinstance(op, Extrude)).depth == 10.0


def test_the_external_kinds_refuse_internal_teeth_and_the_rings_external_ones():
    problems = KINDS["spur"].validate(ring())
    assert any(p.field == "teeth_side" and "external gear's" in p.message for p in problems)
    problems = INTERNAL_KINDS["spur"].validate(ring(teeth_side="external"))
    assert any(p.field == "teeth_side" and "internal gear's" in p.message for p in problems)
    assert any(p.field == "teeth_side" for p in KINDS["spur"].validate(ring(teeth_side="sideways")))
    assert kind_for(ring(kind="bevel")) is None


@pytest.mark.parametrize("changes, field, words", [
    ({"rim": "120"}, "rim", "does not reach past the root"),
    ({"rim": "-1"}, "rim", "more than zero"),
    ({"rim": "wide"}, "rim", "Rim must be a number"),
    ({"fillet": "3"}, "fillet", "Fillet smaller"),
])
def test_ring_refusals_name_their_field(changes, field, words):
    problems = kind_for(ring(**changes)).validate(ring(**changes))
    assert any(p.field == field and words in p.message for p in problems), problems


def test_ring_warnings():
    small = kind_for(ring(teeth="30")).validate(ring(teeth="30"))
    assert any(p.field == "teeth" and "inside the base circle" in p.message for p in small)
    thin = kind_for(ring(rim="128")).validate(ring(rim="128"))
    assert any(p.field == "rim" and "thinner than two modules" in p.message for p in thin)
    reach = kind_for(ring(fillet="0.76")).validate(ring(fillet="0.76"))
    assert any(p.field == "fillet" and "pinion's tips reach" in p.message for p in reach)
    assert not [p for p in kind_for(ring()).validate(ring()) if not p.is_error]


# -- pairs ------------------------------------------------------------------


def rows(candidates):
    return [(c.module, c.teeth_driver, c.teeth_driven) for c in candidates]


def test_forty_millimetres_at_three_to_one_inside_a_ring():
    found = pair.solve(40, 3, mesh="internal")
    assert rows(found[:3]) == [(2.0, 20, 60), (1.25, 32, 96), (1.0, 40, 120)]
    assert all(c.exact and c.standard and not c.undercut and c.mesh == "internal" for c in found[:3])
    listed = rows(found)
    undercut = listed.index((2.5, 16, 48))
    assert found[undercut].undercut
    clean = [i for i, c in enumerate(found) if c.standard and not c.undercut and abs(c.centre_error) < 1e-9]
    assert max(clean) < undercut
    assert found == sorted(found, key=pair.Candidate.rank)


def test_a_ratio_of_one_or_less_is_refused_inside_a_ring():
    with pytest.raises(InputError, match="more than one"):
        pair.solve(40, 1 / 3, mesh="internal")


def test_clashing_rows_rank_after_clean_ones():
    found = pair.solve(3, 60 / 54, module=1.0, min_teeth=17, mesh="internal")
    clash = next(c for c in found if (c.teeth_driver, c.teeth_driven) == (54, 60))
    assert clash.clash == pytest.approx(0.138, abs=0.005) and clash.clashes


def test_a_helical_ring_pair_solves_its_helix_on_the_centre_distance():
    found = pair.solve(40, 3, kind="helical", helix_range=(8.0, 25.0), mesh="internal")
    assert found and all(abs(c.centre_error) < 1e-9 for c in found[:5])
    best = found[0]
    centre, ratio, _ = pair.describe(best.module, best.teeth_driver, best.teeth_driven, 20.0, best.helix_angle,
                                     "internal")
    assert centre == pytest.approx(40.0) and ratio == pytest.approx(3.0, rel=0.05)


def test_apply_keeps_the_hand_round_a_ring():
    a = GearSpec(kind="helical", hand="left")
    b = GearSpec(kind="helical", hand="right", teeth_side="internal")
    chosen = pair.solve(40, 3, kind="helical", helix_range=(8.0, 25.0), mesh="internal")[0]
    new_a, new_b = pair.apply(chosen, a, b)
    assert new_a.hand == new_b.hand == "left"
    assert new_b.teeth_side == "internal"


def test_the_solve_spec_reads_the_mesh():
    spec = PairSpec(mode="pair", mesh="internal", centre_distance="40", ratio="3",
                    gear_a=GearSpec(), gear_b=GearSpec(teeth_side="internal"))
    assert rows(pair.solve_spec(spec)[:1]) == [(2.0, 20, 60)]


def test_the_ring_is_fixed_at_the_origin_and_the_pinion_meshes_inside_it():
    a = GearSpec(module="2", teeth="20")
    b = ring()
    plan = pair.assembly_plan(a, b, r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "", r"C:\G\p.SLDASM")
    assert plan.check() == []
    components = [op for op in plan.ops if isinstance(op, AddComponent)]
    assert [(c.id, c.path, c.at) for c in components] == [
        ("gear1", r"C:\G\b.SLDPRT", (0.0, 0.0, 0.0)), ("gear2", r"C:\G\a.SLDPRT", (40.0, 0.0, 0.0))]
    mates = {op.id: op for op in plan.ops if isinstance(op, Mate)}
    assert mates["centre"].value == 40.0 and mates["mesh"].value == 9.0


@pytest.mark.parametrize("change, words", [
    ({"hand": "left"}, "same hand"),
    ({"teeth": "20"}, "more teeth"),
])
def test_a_helical_ring_pair_refuses_what_would_not_mesh(change, words):
    a = GearSpec(kind="helical", module="2", teeth="20", helix_angle="15", hand="right")
    b = ring("helical", **{"hand": "right", **change})
    with pytest.raises(InputError, match=words):
        pair.assembly_plan(a, b, r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "", r"C:\G\p.SLDASM")
    with pytest.raises(InputError, match="pinion"):
        pair.assembly_plan(b, a, r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "", r"C:\G\p.SLDASM")


def test_stems_call_the_ring_a_ring():
    assert ring().stem() == "Ring_m2_N60"
    assert ring("helical").stem() == "Ring_m2_N60_15R"
    assert ring("herringbone").stem() == "Ring_m2_N60_HB30R"
    spec = PairSpec(mode="pair", mesh="internal", gear_a=GearSpec(module="2", teeth="20"), gear_b=ring())
    assert pair_stems(spec) == ("Pinion_m2_N20", "Ring_m2_N60", "Pair_m2_20T_60T_INT")


def test_a_ring_builds_against_the_fake_and_its_teeth_are_structural():
    s = ring()
    gear = kind_for(s)
    result = swbuild.build(FakeSolidWorks(), gear.plan(s, gear.derive(s), "A", "", PATH), never_exists)
    assert result.ok, result.failures
    assert result.dimensions["Rim@Blank Sketch"] == "Rim@Blank Sketch"
    assert "teeth_side" in swbuild.structural_change({"kind": "spur", "recipe": "A"},
                                                     {"kind": "spur", "recipe": "A", "teeth_side": "internal"})
    assert swbuild.structural_change({"kind": "spur", "recipe": "A"},
                                     {"kind": "spur", "recipe": "A", "teeth_side": "external"}) == ""
