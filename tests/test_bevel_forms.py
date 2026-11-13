"""Crown gears (δ = 90°) and internal bevel gears (δ > 90°): their forms, maths, sketches and refusals.

Nothing here has been built on SolidWorks. Which way a crown or internal bevel
gear's heel plane faces waits on probe bevel_planes_beyond_90, and until then a
build is refused; the plans below are made with the sign stubbed.
"""

import json
import math

import pytest

from gear_generator import findings
from gear_generator.gears import KINDS, bevel, internal, pair
from gear_generator.gears.base import AddGlobal, Arc, CloseSketch, Dimension, Line, LinkDimension, OpenSketch
from gear_generator.gears.equations import DEGREES, RADIANS, evaluate, evaluate_all
from gear_generator.spec import GearSpec, InputError

from test_swbuild import FakeSolidWorks, never_exists

BEVEL = KINDS["bevel"]
PATH = r"C:\Gears\Crown.SLDPRT"


def spec(teeth, mate, shaft, **values):
    base = dict(kind="bevel", module="3", teeth=teeth, mate_teeth=mate, shaft_angle=shaft, face_width="15", bore="10")
    base.update(values)
    return GearSpec(**base)


CROWN = ("40", "20", "120")          # cos Σ = −20 / 40
CROWN_PINION = ("20", "40", "120")
RING = ("40", "16", "120")           # δ 96.59°
RING_PINION = ("16", "40", "120")
STEEP_RING = ("60", "20", "150")     # δ 136.81°


@pytest.fixture
def probed(monkeypatch):
    """The signs probe bevel_planes_beyond_90 would record, as the cone's: only so a plan can be looked at."""
    monkeypatch.setattr(findings, "BEVEL_CROWN_SECTION_X_SIGN", 1)
    monkeypatch.setattr(findings, "BEVEL_INTERNAL_SECTION_X_SIGN", 1)


def plan_of(s, recipe="A"):
    return BEVEL.plan(s, BEVEL.derive(s), recipe, "", PATH)


def link_mismatches(plan):
    """Every linked sketch dimension whose expression does not evaluate to the value the sketch draws it at."""
    values = evaluate_all([(op.name, op.expression) for op in plan.ops if isinstance(op, AddGlobal)], DEGREES)
    dims, current, out = {}, [], []
    for op in plan.ops:
        if isinstance(op, OpenSketch):
            current = []
        elif isinstance(op, Dimension):
            current.append(op)
        elif isinstance(op, CloseSketch):
            dims.update({f"{d.name}@{op.name}": d for d in current})
        elif isinstance(op, LinkDimension) and op.dimension in dims:
            got, drawn = evaluate(op.expression, values, DEGREES), dims[op.dimension].value
            if abs(got - drawn) > 1e-6 * max(1.0, abs(drawn)):
                out.append((op.dimension, got, drawn))
    return out


# -- forms ------------------------------------------------------------------


def test_the_shaft_angle_decides_the_form():
    assert BEVEL.derive(spec(*CROWN)).form == bevel.FORM_CROWN
    assert BEVEL.derive(spec(*CROWN_PINION)).form == bevel.FORM_CONE
    assert BEVEL.derive(spec(*RING)).form == bevel.FORM_INTERNAL
    assert BEVEL.derive(spec(*RING_PINION)).form == bevel.FORM_CONE
    assert BEVEL.derive(spec("40", "20", "90")).form == bevel.FORM_CONE
    assert bevel.crown_shaft_angle(40, 20) == pytest.approx(120.0)
    assert bevel.crown_shaft_angle(20, 40) is None and bevel.crown_shaft_angle(20, 20) is None


def test_a_crown_gear_typed_to_three_places_is_built_as_exactly_ninety():
    g = BEVEL.derive(spec("45", "15", "109.471"))
    assert g.crown and g.delta == 90.0 and g.delta_mate == pytest.approx(19.471)
    assert g.cone_distance == pytest.approx(3 * 45 / 2)


@pytest.mark.parametrize("teeth, mate, shaft", [("40", "20", "119.5"), ("40", "20", "120.5"), ("20", "40", "120.5")])
def test_the_bands_either_side_of_a_crown_gear_are_refused_with_the_angle_that_makes_one(teeth, mate, shaft):
    with pytest.raises(Exception, match="a shaft angle of 120° makes it a crown gear"):
        BEVEL.derive(spec(teeth, mate, shaft))
    assert [d.field for d in BEVEL.validate(spec(teeth, mate, shaft))] == ["teeth"]


def test_the_addenda_beside_a_crown_gear_and_in_an_internal_pair():
    crown, pinion = BEVEL.derive(spec(*CROWN)), BEVEL.derive(spec(*CROWN_PINION))
    assert (crown.addendum, pinion.addendum) == (pytest.approx(0.54 * 3), pytest.approx(1.46 * 3))
    assert crown.mate_addendum == pytest.approx(pinion.addendum)
    # Gleason's big-gear addendum tends to 0.54 m as the gear tends to a crown.
    near = bevel.addenda(3, 40, 20, 89.9, 30.1)
    assert near[0] == pytest.approx(0.54 * 3, abs=2e-3)
    ring, ring_pinion = BEVEL.derive(spec(*RING)), BEVEL.derive(spec(*RING_PINION))
    assert (ring.addendum, ring_pinion.addendum, ring.dedendum) == (3.0, 3.0, pytest.approx(1.188 * 3))
    assert ring.shift == 0.0 and ring.section.space == pytest.approx(3 * math.pi / 2 + ring.section.backlash)


# -- maths ------------------------------------------------------------------


@pytest.mark.parametrize("teeth, mate, shaft", [CROWN, CROWN_PINION, RING, RING_PINION, STEEP_RING,
                                                ("45", "15", "109.471")])
@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_every_global_evaluates_to_the_maths(teeth, mate, shaft, trig):
    s = spec(teeth, mate, shaft)
    g = BEVEL.derive(s)
    got = evaluate_all([(v.name, v.expression_for(trig)) for v in BEVEL.variables(s, g)], trig)
    want = g.values()
    assert set(got) == set(want)
    for name, value in want.items():
        assert got[name] == pytest.approx(value, rel=1e-9, abs=1e-9), name


def test_a_crown_gear_has_no_back_cone_globals_and_a_ring_its_own():
    names = {v.name for v in BEVEL.variables(spec(*CROWN), BEVEL.derive(spec(*CROWN)))}
    assert not names & {bevel.BACK_PITCH, bevel.HEEL_RADIUS, "Base Diameter"}
    names = {v.name for v in BEVEL.variables(spec(*RING), BEVEL.derive(spec(*RING)))}
    assert {bevel.BACK_INNER, bevel.HEEL_RADIUS, internal.FLANK_END} <= names
    assert not names & {bevel.BACK_OUTER, internal.RIM, internal.INNER}


def test_the_crown_pairs_contact_ratio_is_the_limit_of_the_cone_formula():
    crown = BEVEL.derive(spec(*CROWN))
    alpha = math.radians(20.0)
    # The rack's share, ha / sin α, is the external formula's as rv grows without bound.
    rv = 1e7
    external = math.sqrt((rv + crown.addendum) ** 2 - (rv * math.cos(alpha)) ** 2) - rv * math.sin(alpha)
    assert bevel._approach(bevel.FORM_CROWN, math.inf, crown.addendum, alpha) == pytest.approx(external, rel=1e-6)
    assert bevel.contact_ratio(crown) == pytest.approx(bevel.contact_ratio(BEVEL.derive(spec(*CROWN_PINION))))
    assert 1.2 < bevel.contact_ratio(crown) < 2.0


def test_the_internal_pairs_contact_ratio_is_the_virtual_rings():
    ring, pinion = BEVEL.derive(spec(*RING)), BEVEL.derive(spec(*RING_PINION))
    want = internal.contact_ratio(3, pinion.virtual_teeth, ring.virtual_teeth, 20.0,
                                  centre_distance=ring.virtual_radius - pinion.virtual_radius)
    assert bevel.contact_ratio(ring) == pytest.approx(want)
    assert bevel.contact_ratio(pinion) == pytest.approx(want)


def test_a_crown_gears_readouts_serialise_without_infinity():
    g = BEVEL.derive(spec(*CROWN))
    assert g.virtual_teeth == math.inf and not g.undercut
    data = g.to_dict()
    assert data["virtual_teeth"] is None and data["section"]["teeth"] is None
    json.dumps(data, allow_nan=False)


# -- the blank --------------------------------------------------------------


def _area(loop):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(loop, loop[1:])) / 2.0


@pytest.mark.parametrize("teeth, mate, shaft", [CROWN, RING, STEEP_RING])
def test_the_half_section_is_counter_clockwise_and_clear_of_the_axis(teeth, mate, shaft):
    g = BEVEL.derive(spec(teeth, mate, shaft))
    loop = bevel.outline(g)
    assert loop[0] == loop[-1] and _area(loop) > 0.0
    assert all(x >= g.bore / 2.0 - 1e-9 for x, _ in loop)
    if g.ring:
        assert len(loop) == 5 and min(x for x, _ in loop) > 0.0


def test_a_crown_gears_blank_is_a_disc_with_a_web_two_modules_thick():
    g = BEVEL.derive(spec(*CROWN))
    p = bevel.blank_points(g)
    assert p.heel_tip == pytest.approx((g.cone_distance, -g.addendum))
    assert p.heel_rim == pytest.approx((g.cone_distance, g.dedendum + 3 * g.module))
    assert p.heel_rim[1] - p.toe_rim[1] >= 2 * g.module
    assert p.back_bore[1] == p.heel_rim[1] and p.front_bore[1] == p.toe_rim[1]


def test_an_internal_bevels_teeth_point_in_and_its_rim_out():
    g = BEVEL.derive(spec(*RING))
    p = bevel.blank_points(g)
    axis_distance = lambda point: point[0]  # noqa: E731
    assert axis_distance(p.heel_tip) < axis_distance(p.pitch) < axis_distance(p.heel_rim)
    assert g.da < g.d                                               # its tip circle is inside its pitch circle
    assert [d.field for d in BEVEL.validate(spec(*RING)) if d.level == "warning"].count("bore") == 1


# -- the plan ---------------------------------------------------------------


@pytest.mark.parametrize("teeth, mate, shaft", [CROWN, RING])
def test_a_build_is_refused_while_the_probe_is_unsettled(monkeypatch, teeth, mate, shaft):
    monkeypatch.setattr(findings, "BEVEL_CROWN_SECTION_X_SIGN", None)
    monkeypatch.setattr(findings, "BEVEL_INTERNAL_SECTION_X_SIGN", None)
    assert bevel.section_sign(BEVEL.derive(spec(teeth, mate, shaft)).form) is None
    with pytest.raises(InputError, match="bevel_planes_beyond_90"):
        plan_of(spec(teeth, mate, shaft))
    plan_of(spec(*CROWN_PINION))                                    # its pinion is a cone, and builds


@pytest.mark.parametrize("teeth, mate, shaft", [CROWN, RING])
def test_the_probed_signs_let_a_crown_and_an_internal_bevel_plan(teeth, mate, shaft):
    """Probe bevel_planes_beyond_90 found the cone's sign carries on past 90°, so both forms plan as findings stand."""
    assert bevel.section_sign(BEVEL.derive(spec(teeth, mate, shaft)).form) == findings.BEVEL_SECTION_X_SIGN == 1
    assert plan_of(spec(teeth, mate, shaft)).check() == []


@pytest.mark.parametrize("teeth, mate, shaft", [CROWN, ("45", "15", "109.471"), RING, STEEP_RING])
@pytest.mark.parametrize("recipe", ["A", "B"])
def test_the_plan_is_sound_and_every_link_agrees_with_its_sketch(probed, teeth, mate, shaft, recipe):
    s = spec(teeth, mate, shaft, recipe=recipe)
    if recipe == "B" and any(d.level == "error" for d in BEVEL.validate(s)):
        pytest.skip("recipe B is refused on this ring")
    plan = plan_of(s, recipe)
    assert plan.check() == []
    assert link_mismatches(plan) == []
    kinds = [type(op).__name__ for op in plan.ops]
    assert kinds.index("Revolve") < kinds.index("RefPlaneNormal") < kinds.index("LoftCut") < kinds.index("CircularPattern")


def test_the_crown_gears_section_is_the_same_rack_for_either_recipe(probed):
    a, b = plan_of(spec(*CROWN, recipe="A"), "A"), plan_of(spec(*CROWN, recipe="B"), "B")
    sketch = lambda plan: [op for op in plan.ops if isinstance(op, (Line, Arc)) and op.id.startswith("h_")]  # noqa: E731
    assert sketch(a) == sketch(b) and sketch(a)


def _near(point, line, tol=1e-9):
    (x0, y0), (x1, y1) = line.start, line.end
    return abs((x1 - x0) * (point[1] - y0) - (y1 - y0) * (point[0] - x0)) / math.hypot(x1 - x0, y1 - y0) < tol


@pytest.mark.parametrize("sign", [1, -1])
def test_the_rack_is_drawn_as_its_relations_say(monkeypatch, sign):
    monkeypatch.setattr(findings, "BEVEL_CROWN_SECTION_X_SIGN", sign)
    g = BEVEL.derive(spec(*CROWN))
    ops = {op.id: op for op in plan_of(spec(*CROWN)).ops if isinstance(op, (Line, Arc)) and op.id.startswith("h_")}
    k = g.heel_distance / g.cone_distance
    r = g.section
    root, flank, cap, width = ops["h_R"], ops["h_E+"], ops["h_T"], ops["h_W"]
    assert root.start[0] == pytest.approx(-sign * k * r.dedendum) == root.end[0]
    assert cap.start[0] == pytest.approx(sign * k * r.cap) and cap.start[1] == pytest.approx(-cap.end[1])
    assert width.start[0] == width.end[0] == 0.0 and width.end[1] - width.start[1] == pytest.approx(k * r.space)
    assert _near(width.end, flank) and _near(width.start, ops["h_E-"])
    slope = math.degrees(math.atan2(flank.end[1] - flank.start[1], sign * (flank.end[0] - flank.start[0])))
    assert slope == pytest.approx(g.pressure_angle_deg)
    for fillet, line in ((ops["h_F+"], flank), (ops["h_F-"], ops["h_E-"])):
        radius = math.dist(fillet.centre, fillet.start)
        assert radius == pytest.approx(k * r.fillet) == math.dist(fillet.centre, fillet.end)
        assert abs(fillet.centre[0] - root.start[0]) == pytest.approx(radius)               # tangent to the root
        (x0, y0), (x1, y1) = line.start, line.end
        distance = abs((x1 - x0) * (fillet.centre[1] - y0) - (y1 - y0) * (fillet.centre[0] - x0)) / math.dist(
            line.start, line.end)
        assert distance == pytest.approx(radius)                                             # and to its flank


@pytest.mark.parametrize("teeth, mate, shaft", [CROWN, RING, CROWN_PINION])
def test_every_sections_root_is_on_the_far_side_from_the_tips(probed, teeth, mate, shaft):
    """The sketch's +x is the tips' way (sign 1): the root, where the space is deepest, is at −k·hf on the x axis."""
    g = BEVEL.derive(spec(teeth, mate, shaft))
    k = g.heel_distance / g.cone_distance
    ops = [op for op in plan_of(spec(teeth, mate, shaft)).ops if getattr(op, "id", "") == "h_R"]
    root = ops[0]
    if isinstance(root, Arc):
        radius = math.dist(root.centre, root.start)
        x = min((root.centre[0] + radius, root.centre[0] - radius), key=abs)
    else:
        x = root.start[0]
    assert x == pytest.approx(-k * g.dedendum)


def test_a_crown_gear_builds_against_the_fake(probed):
    from gear_generator import swbuild

    fake = FakeSolidWorks()
    result = swbuild.build(fake, plan_of(spec(*CROWN)), never_exists)
    assert result.ok, result.failures
    called = [name for name, _ in fake.calls]
    assert called.index("revolve") < called.index("ref_plane_normal") < called.index("loft_cut") \
        < called.index("circular_pattern") < called.index("save_as")


# -- the pair ---------------------------------------------------------------


def test_the_solver_offers_a_crown_pair_and_an_internal_one_and_names_them():
    from gear_generator import ui_text

    row = pair.bevel_candidate(3, 20, 40, 120)
    assert row is not None and row.contact_ratio == pytest.approx(bevel.contact_ratio(BEVEL.derive(spec(*CROWN))))
    assert "B crown" in ui_text.candidate_row(row)[2]
    row = pair.bevel_candidate(3, 16, 40, 120)
    assert row is not None and row.contact_ratio == pytest.approx(bevel.contact_ratio(BEVEL.derive(spec(*RING))))
    assert "B internal" in ui_text.candidate_row(row)[2] and not row.clashes
    assert pair.bevel_candidate(3, 20, 40, 120.5) is None                    # too near a crown gear
    assert pair.bevel_forms(20, 40, 90) == (bevel.FORM_CONE, bevel.FORM_CONE)


def test_the_readouts_say_what_the_gear_is():
    from gear_generator import ui_text

    crown, ring = BEVEL.derive(spec(*CROWN)), BEVEL.derive(spec(*RING))
    assert dict(ui_text.derived_rows(crown))["Virtual teeth"] == "∞ · a rack"
    assert dict(ui_text.derived_rows(ring))["Virtual teeth"].endswith(" · a ring")
    assert "Tip diameter" in dict(ui_text.derived_rows(ring))
    assert ui_text.derived_line(crown).endswith(" · crown") and ui_text.derived_line(ring).endswith(" · internal")


@pytest.mark.parametrize("gears", [(CROWN_PINION, CROWN), (RING_PINION, RING)])
def test_the_assembly_mates_the_apexes_at_the_shaft_angle(gears):
    a, b = spec(*gears[0]), spec(*gears[1])
    plan = pair.assembly_plan(a, b, r"C:\a.SLDPRT", r"C:\b.SLDPRT", "", r"C:\p.SLDASM")
    assert plan.check() == []
    shaft = next(op for op in plan.ops if getattr(op, "id", "") == "shaft")
    assert shaft.value == pytest.approx(120.0)
