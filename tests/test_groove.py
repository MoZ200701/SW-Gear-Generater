"""A herringbone's centre groove: a shorter toothed blank, a hub under the root, and the same sweep and mirror."""

import pytest

from gear_generator import swbuild, ui_text
from gear_generator.gears import KINDS, kind_for
from gear_generator.gears.base import CloseSketch, Extrude, LinkDimension, MirrorBody
from gear_generator.gears.equations import DEGREES, RADIANS, evaluate_all
from gear_generator.gears.helical import GROOVE_DIAMETER, GROOVE_WIDTH, TOOTHED_WIDTH
from gear_generator.spec import GearSpec

from test_swbuild import FakeSolidWorks, never_exists

HERRINGBONE = KINDS["herringbone"]
GROOVED = GearSpec(kind="herringbone", module="2", teeth="20", helix_angle="30", face_width="40", groove="8")


def test_the_groove_leaves_sixteen_millimetres_of_teeth_each_side():
    g = HERRINGBONE.derive(GROOVED)
    assert (g.groove, g.toothed_width) == (8.0, 16.0)
    assert g.groove_d == pytest.approx(g.df - 4.0)
    values = g.values()
    assert (values[GROOVE_WIDTH], values[TOOTHED_WIDTH], values[GROOVE_DIAMETER]) == (8.0, 16.0, g.df - 4.0)


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_every_grooved_global_evaluates_to_the_derived_value(trig):
    g = HERRINGBONE.derive(GROOVED)
    values = evaluate_all([(v.name, v.expression_for(trig)) for v in HERRINGBONE.variables(GROOVED, g)], trig)
    assert set(values) == set(g.values())
    for name, value in g.values().items():
        assert values[name] == pytest.approx(value, abs=1e-9), name


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_the_blank_stops_at_the_groove_and_a_hub_carries_on_to_the_mid_plane(recipe):
    spec = GROOVED.with_values(recipe=recipe)
    plan = HERRINGBONE.plan(spec, HERRINGBONE.derive(spec), recipe, "", r"C:\Gears\HB.SLDPRT")
    assert plan.check() == []
    extrudes = [op for op in plan.ops if isinstance(op, Extrude)]
    assert [(op.name, op.depth) for op in extrudes] == [("Blank", 16.0), ("Hub", 20.0)]
    links = {op.dimension: op.expression for op in plan.ops if isinstance(op, LinkDimension)}
    assert links["Width@Blank"] == '"Toothed Width"'
    assert links["Width@Hub"] == '"Mid Width"' and links["Hub@Hub Sketch"] == '"Groove Diameter"'
    names = [op.name for op in plan.ops if isinstance(op, (CloseSketch, MirrorBody))]
    assert names.index("Hub Sketch") < names.index("Mirror")
    result = swbuild.build(FakeSolidWorks(), plan, never_exists)
    assert result.ok and result.saved, result.log_lines()


def test_without_a_groove_the_herringbone_is_what_it_was():
    spec = GROOVED.with_values(groove="")
    plan = HERRINGBONE.plan(spec, HERRINGBONE.derive(spec), "A", "", r"C:\Gears\HB.SLDPRT")
    assert [op.name for op in plan.ops if isinstance(op, Extrude)] == ["Blank"]
    assert not any(v.name == GROOVE_WIDTH for v in HERRINGBONE.variables(spec, HERRINGBONE.derive(spec)))


@pytest.mark.parametrize("spec,words", [
    (GROOVED.with_values(groove="40"), "leaves no teeth"),
    (GROOVED.with_values(bore="38"), "reaches the bore"),       # the floor is at 37.19, the root at 41.19
    (GROOVED.with_values(kind="helical"), "Only a herringbone gear"),
    (GROOVED.with_values(teeth_side="internal", teeth="60"), "built without a centre groove"),
    (GROOVED.with_values(groove="-2"), "must not be negative"),
])
def test_a_groove_that_cannot_be_built_is_refused_by_name(spec, words):
    errors = [d for d in kind_for(spec).validate(spec) if d.is_error]
    assert any(d.field == "groove" and words in d.message for d in errors), [d.message for d in errors]


def test_a_narrow_toothed_half_is_warned_about():
    spec = GROOVED.with_values(groove="30")
    assert any("under three modules" in d.message for d in HERRINGBONE.validate(spec))


def test_the_groove_is_in_the_name_the_readouts_and_the_structure():
    assert GROOVED.default_stem() == "Herringbone_m2_N20_30R_G8"
    assert dict(ui_text.derived_rows(HERRINGBONE.derive(GROOVED)))["Centre groove"].startswith("8 · floor ")
    worked = ui_text.explainer("groove", HERRINGBONE.derive(GROOVED))[3]
    assert worked.startswith("8 mm → 16 mm of teeth each side")
    assert "groove" in swbuild.structural_change({"kind": "herringbone", "groove": ""},
                                                 {"kind": "herringbone", "groove": "8"}).lower()
    assert swbuild.structural_change({"kind": "herringbone", "groove": "8"},
                                     {"kind": "herringbone", "groove": "10"}) == ""
