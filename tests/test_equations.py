"""The Equation Manager text, checked by evaluating it.

The globals are the product: a name used before it is defined, a trig function
fed degrees in a radian document, or a stray bracket would all show up as a red
equation in someone's part. Evaluating the emitted list in order, in both trig
modes, and comparing every value with the maths is what catches that here.
"""

import math

import pytest

from gear_generator.gears import KINDS, equations
from gear_generator.gears.base import EquationCurve
from gear_generator.gears.equations import DEGREES, RADIANS, EquationError
from gear_generator.spec import GearSpec

SPUR = KINDS["spur"]

SPECS = [
    GearSpec(),                                            # the pinned m 1.5, z 25
    GearSpec(module="1", teeth="17", bore=""),             # the 2.4 m tooth depth branch
    GearSpec(module="1", teeth="50"),                      # base circle below the root
    GearSpec(module="2", teeth="12", bore="8"),            # undercut
    GearSpec(module="3", teeth="80", pressure_angle="14.5", backlash="0.05", fillet="1.2"),
    GearSpec(module="1.25", teeth="33", pressure_angle="25", face_width="6.5"),
]


# -- the emitted list against the maths -------------------------------------


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
@pytest.mark.parametrize("spec", SPECS, ids=lambda s: f"m{s.module}-z{s.teeth}-a{s.pressure_angle}")
def test_every_global_evaluates_to_the_derived_value(spec, trig):
    derived = SPUR.derive(spec)
    variables = SPUR.variables(spec, derived)
    values = equations.evaluate_all([(v.name, v.expression_for(trig)) for v in variables], trig)
    expected = derived.values()
    assert set(values) == set(expected)
    for name, value in expected.items():
        assert values[name] == pytest.approx(value, abs=1e-9), name


def test_the_degree_form_in_a_radian_document_would_be_wrong():
    """So the build has to measure the document, and this is why."""
    spec = GearSpec()
    variables = SPUR.variables(spec, SPUR.derive(spec))
    wrong = equations.evaluate_all([(v.name, v.expression) for v in variables], RADIANS)
    assert wrong["Base Diameter"] != pytest.approx(SPUR.derive(spec).db)


def test_every_name_is_defined_before_it_is_used():
    spec = GearSpec()
    variables = SPUR.variables(spec, SPUR.derive(spec))
    for trig in (DEGREES, RADIANS):
        assert equations.check_order([(v.name, v.expression_for(trig)) for v in variables]) == []


def test_a_typed_backlash_and_fillet_are_written_as_literals():
    spec = GearSpec(backlash="0.05", fillet="0.4")
    text = SPUR.equation_lines(spec, SPUR.derive(spec), DEGREES)
    assert '"Backlash"= 0.05' in text
    assert '"Fillet Radius"= 0.4' in text


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_the_involute_curves_start_and_end_where_the_plan_says(trig):
    spec = GearSpec(recipe="A")
    derived = SPUR.derive(spec)
    plan = SPUR.plan(spec, derived, "A", "", r"C:\g\Gear.SLDPRT")
    scope = plan.values(trig)
    curves = [op for op in plan.ops if isinstance(op, EquationCurve)]
    assert [c.id for c in curves] == ["I+", "I-"]
    for curve in curves:
        for t_name, expected in (("t1", curve.start), ("t2", curve.end)):
            t = equations.evaluate(getattr(curve, t_name), scope, trig)
            # A curve's own trig is radians in every document.
            got = (equations.evaluate(curve.x, scope, RADIANS, {"t": t}),
                   equations.evaluate(curve.y, scope, RADIANS, {"t": t}))
            assert got == pytest.approx(expected, abs=1e-9)


def test_curve_expressions_never_convert_to_degrees():
    """SolidWorks 2026 refused every curve spelling with * 180 / pi."""
    spec = GearSpec()
    plan = SPUR.plan(spec, SPUR.derive(spec), "A", "", "")
    curves = [op for op in plan.ops if isinstance(op, EquationCurve)]
    assert curves and all("180" not in c.x and "180" not in c.y for c in curves)


def test_substituting_the_values_keeps_the_curve():
    spec = GearSpec()
    derived = SPUR.derive(spec)
    plan = SPUR.plan(spec, derived, "A", "", "")
    scope = plan.values(DEGREES)
    curve = next(op for op in plan.ops if isinstance(op, EquationCurve))
    numeric = equations.substitute(curve.x, scope)
    assert '"' not in numeric
    for t in (0.1, 0.4):
        assert equations.evaluate(numeric, {}, RADIANS, {"t": t}) == pytest.approx(
            equations.evaluate(curve.x, scope, RADIANS, {"t": t}), abs=1e-7
        )


# -- formatting -------------------------------------------------------------


@pytest.mark.parametrize(
    "value,text",
    [(1.5, "1.500000000"), (0.0, "0.000000000"), (-1e-12, "0.000000000"), (-0.0, "0.000000000"),
     (-2.25, "-2.250000000"), (0.0000004, "0.000000400"), (123456.7890123, "123456.789012300")],
)
def test_fmt9_is_fixed_point_nine_decimals_with_no_negative_zero(value, text):
    assert equations.fmt9(value) == text


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_fmt9_refuses_what_is_not_finite(value):
    with pytest.raises(EquationError, match="non-finite"):
        equations.fmt9(value)


@pytest.mark.parametrize("value,text", [(25, "25"), (1.5, "1.5"), (0.3, "0.3"), (-0.0, "0"), (2.0000000001, "2")])
def test_a_literal_is_as_short_as_the_user_would_type_it(value, text):
    assert equations.literal(value) == text


def test_equation_text_uses_the_equation_managers_spacing():
    assert equations.equation_text("Module", "1.5") == '"Module"= 1.5'
    assert equations.split_equation('"Module"= 1.5') == ("Module", "1.5")


def test_a_name_with_a_quote_in_it_is_refused():
    with pytest.raises(EquationError, match="double quote"):
        equations.quote('say "hi"')


# -- the grammar ------------------------------------------------------------


@pytest.mark.parametrize(
    "expression,value",
    [
        ("1 + 2 * 3", 7.0),
        ("( 1 + 2 ) * 3", 9.0),
        ("2 ^ 3 ^ 2", 512.0),
        ("-2 + 5", 3.0),
        ("10 / 4", 2.5),
        ("sqr ( 16 )", 4.0),
        ("pi", math.pi),
        ("IIF ( 1 <= 1.25 , 2.4 , 2.25 )", 2.4),
        ("IIF ( 1.5 <= 1.25 , 2.4 , 2.25 )", 2.25),
        ("IIF ( 3 <> 3 , 1 , 0 )", 0.0),
        ("iif ( 2 >= 3 , 1 , 0 )", 0.0),
    ],
)
def test_the_grammar(expression, value):
    assert equations.evaluate(expression) == pytest.approx(value)


def test_trig_follows_the_documents_units():
    assert equations.evaluate("sin ( 90 )", mode=DEGREES) == pytest.approx(1.0)
    assert equations.evaluate("sin ( pi / 2 )", mode=RADIANS) == pytest.approx(1.0)
    assert equations.evaluate("atn ( 1 )", mode=DEGREES) == pytest.approx(45.0)


def test_quoted_names_are_looked_up_and_an_undefined_one_is_named():
    assert equations.evaluate('"Module" * 2', {"Module": 1.5}) == 3.0
    with pytest.raises(EquationError, match='"Module" before it is defined'):
        equations.evaluate('"Module" * 2', {})


@pytest.mark.parametrize("expression", ["1 +", "( 1 + 2", "1 2", "foo ( 1 )", "1 / 0", "", "1 $ 2"])
def test_what_is_not_an_expression_is_refused(expression):
    with pytest.raises(EquationError):
        equations.evaluate(expression)


def test_evaluate_all_refuses_a_name_defined_twice():
    with pytest.raises(EquationError, match="twice"):
        equations.evaluate_all([("a", "1"), ("a", "2")])


def test_check_order_finds_a_forward_reference():
    problems = equations.check_order([("b", '"a" + 1'), ("a", "1")])
    assert problems == ['"b" refers to "a" before "a" is defined.']
