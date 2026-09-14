"""Tier 1, part one: global variables in the Equation Manager.

The whole parametric approach rests on these. If a global cannot be added from
code, read back, and made to drive something on a rebuild, nothing later is
worth running, and the decision is STOP.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..gears import KINDS
from ..gears.equations import DEGREES, RADIANS
from ..spec import GearSpec
from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe

# swInConfigurationOpts_e, from swconst.tlb on SolidWorks 2026.
THIS_CONFIGURATION = 1
ALL_CONFIGURATIONS = 2


def _add_forms(eqm: Any) -> List[Tuple[str, Callable[[str], Any]]]:
    """Ways of adding an equation, the documented one for this case first.

    The API help for ``IEquationMgr::Add3`` says it "only works for parts having
    multiple configurations" and to call ``Add2`` otherwise, and a new part has
    one configuration. The Add3 forms are still tried afterwards, only when Add2
    fails, so a document where the help is wrong is noticed.
    """
    return [
        ("Add2", lambda text: call(eqm, "Add2", -1, text, True)),
        ("Add3 all configurations, None", lambda text: call(eqm, "Add3", -1, text, True, ALL_CONFIGURATIONS, None)),
        ("Add3 all configurations, null dispatch",
         lambda text: call(eqm, "Add3", -1, text, True, ALL_CONFIGURATIONS, sc.null())),
    ]


def adder(px: Px, eqm: Any) -> Callable[[str], int]:
    """Add an equation the way the equation_add probe found works."""
    form = px.shared.get("add3_form")
    for name, fn in _add_forms(eqm):
        if name == form:
            return lambda text: int(fn(text))
    raise Require("No working way of adding an equation was found by equation_add.")


def delete_from(eqm: Any, count: int) -> None:
    """Delete every equation at or after ``count``, last first."""
    total = int(call(eqm, "GetCount"))
    for index in range(total - 1, count - 1, -1):
        call(eqm, "Delete", index)


@probe("equation_add", needs=("new_document",), tier=1,
       members=("IModelDoc2.GetEquationMgr", "IEquationMgr.Add2", "IEquationMgr.Add3", "IEquationMgr.GetCount", "IEquationMgr.Equation",
                "IEquationMgr.Value", "IEquationMgr.GlobalVariable", "IEquationMgr.Delete",
                "IEquationMgr.AngularEquationUnits"))
def equation_add(px: Px) -> None:
    """A global is added, reads back by index, and deletes again."""
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        px.require(eqm is not None, "GetEquationMgr returns an equation manager")
        got, units = px.attempt("AngularEquationUnits", lambda: call(eqm, "AngularEquationUnits"))
        px.fact("angular_equation_units_property", units if got else None)
        before = int(call(eqm, "GetCount"))
        px.fact("equations_in_new_part", before)

        text = '"Probe A"= 2.5'
        winner: Optional[str] = None
        index = -1
        for name, fn in _add_forms(eqm):
            got, value = px.attempt(name, lambda: fn(text))
            if got and isinstance(value, int) and value >= 0:
                winner, index = name, value
                break
        px.require(winner is not None, "some documented way of adding a global works")
        px.fact("add3_form", winner)
        px.shared["add3_form"] = winner
        px.check(index == before, f"{winner} at index -1 appends, returning {index}")
        px.check(int(call(eqm, "GetCount")) == before + 1, "GetCount goes up by one")

        read = str(call(eqm, "Equation", index))
        px.fact("equation_text_readback", read)
        px.check(read.replace(" ", "") == text.replace(" ", ""), f"Equation(i) reads back {read!r}")
        value = float(call(eqm, "Value", index))
        px.check(abs(value - 2.5) < 1e-12, f"Value(i) reads back {value!r}")
        px.check(bool(call(eqm, "GlobalVariable", index)), "GlobalVariable(i) says it is a global")

        result = call(eqm, "Delete", index)
        px.fact("delete_returns", result)
        px.check(int(call(eqm, "GetCount")) == before, "Delete(i) removes it again")

        # Evidence for the help's claim about Add3 on a one-configuration part.
        got, value = px.attempt("Add3 on a one-configuration part, all configurations, None",
                                lambda: call(eqm, "Add3", -1, '"Probe B"= 1', True, ALL_CONFIGURATIONS, None))
        px.fact("add3_single_configuration_returns", value if got else "raised")
        delete_from(eqm, before)


# (label, equation, value in a degree document, value in a radian document);
# None means "whatever it is, record it".
SYNTAX_CASES = [
    ("pi", '"Probe Pi"= pi', math.pi, math.pi),
    ("power", '"Probe Pow"= 2 ^ 3', 8.0, 8.0),
    ("sqr", '"Probe Sqr"= sqr ( 16 )', 4.0, 4.0),
    ("iif", '"Probe Iif"= IIF ( 1 <= 1.25 , 2.4 , 2.25 )', 2.4, 2.4),
    ("iif greater-or-equal", '"Probe Iif2"= IIF ( 1.5 >= 2 , 1 , 0 )', 0.0, 0.0),
    ("reference", '"Probe Ref"= "Probe Pi" * 2', 2 * math.pi, 2 * math.pi),
    ("cos", '"Probe Cos"= cos ( 60 )', 0.5, math.cos(60.0)),
    ("tan", '"Probe Tan"= tan ( 20 )', math.tan(math.radians(20)), math.tan(20.0)),
    ("abs", '"Probe Abs"= abs ( -2 )', 2.0, 2.0),
    ("bracketed comparison", '"Probe Bracket"= IIF ( 3 >= ( 1 + 5 ) , 1 , 0 )', 0.0, 0.0),
]

# Not asserted, only recorded: what SolidWorks makes of these. The first read
# "a >= b + c" as "( a >= b ) + c" on SolidWorks 2026.
RECORDED_CASES = [
    ("unbracketed comparison", '"Probe Unbracketed"= IIF ( 3 >= 1 + 5 , 1 , 0 )'),
    ("sqr of a ratio that is exactly one, no abs", '"Probe Unit Raw"= sqr ( ( 35.238473279 / 35.238473279 ) ^ 2 - 1 )'),
    ("unary minus squared", '"Probe Neg"= -2 ^ 2'),
    ("sqr of a ratio that is exactly one, with abs",
     '"Probe Unit"= sqr ( abs ( ( 35.238473279 / 35.238473279 ) ^ 2 - 1 ) )'),
    # How to take the involute parameter when the ratio can be exactly one.
    ("sqr of zero", '"Probe Sqr0"= sqr ( 0 )'),
    ("half power of zero", '"Probe Half0"= 0 ^ 0.5'),
    ("half power of a tiny number", '"Probe Half1"= 0.0001 ^ 0.5'),
    ("iif guarding an invalid sqr", '"Probe Lazy"= IIF ( 1 > 1 , sqr ( -1 ) , 0 )'),
    ("iif guarding sqr of zero", '"Probe Lazy0"= IIF ( 1 > 1 , sqr ( 0 ) , 0 )'),
    ("sqr of one", '"Probe Sqr1"= sqr ( 1 )'),
    ("sqr of a ratio just above one", '"Probe Unit2"= sqr ( ( 35.46 / 35.238473279 ) ^ 2 - 1 )'),
]


@probe("equation_syntax", needs=("equation_add",), tier=1,
       members=("IEquationMgr.Add2", "IEquationMgr.Value", "IEquationMgr.Status"))
def equation_syntax(px: Px) -> None:
    """pi, ^, sqr, IIF, references and trig — and what a bad equation does."""
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        before = int(call(eqm, "GetCount"))
        try:
            index = add('"Probe Sin"= sin ( 90 )')
            px.require(index >= 0, "a sin() equation is accepted")
            sine = float(call(eqm, "Value", index))
            trig = DEGREES if abs(sine - 1.0) < 1e-9 else RADIANS if abs(sine - math.sin(90.0)) < 1e-9 else "unknown"
            px.fact("trig_units", trig, f"sin ( 90 ) = {sine!r}, so trig is in {trig}")
            px.shared["trig_units"] = trig
            px.require(trig in (DEGREES, RADIANS), "trig units are recognisable")

            for label, text, in_degrees, in_radians in SYNTAX_CASES:
                expected = in_degrees if trig == DEGREES else in_radians
                index = add(text)
                if not px.check(index >= 0, f"{label}: {text} is accepted"):
                    continue
                value = float(call(eqm, "Value", index))
                px.check(abs(value - expected) < 1e-9, f"{label}: evaluates to {value!r}")

            for label, text in RECORDED_CASES:
                got, index = px.attempt(f"{label}: {text}", lambda: add(text))
                value = float(call(eqm, "Value", index)) if got and index >= 0 else None
                px.fact(label.replace(" ", "_").replace(",", ""), {"index": index if got else "raised", "value": value})

            for label, text in (("bad parse", '"Probe Bad"= ( 1 +'), ("unknown name", '"Probe Unknown"= "No Such Name" * 2')):
                got, value = px.attempt(f"Add3 {label}: {text}", lambda: add(text))
                px.fact(f"add3_{label.replace(' ', '_')}_returns", value if got else "raised")
                got, status = px.attempt("Status after it", lambda: call(eqm, "Status"))
                px.fact(f"status_after_{label.replace(' ', '_')}", status if got else None)
        finally:
            delete_from(eqm, before)


@probe("gear_globals", needs=("equation_syntax",), tier=1, members=("IEquationMgr.Add2", "IEquationMgr.Value",
                                                                   "IEquationMgr.Equation"))
def gear_globals(px: Px) -> None:
    """The tool's own 24 globals go in, in order, and SolidWorks agrees with the maths."""
    trig = px.shared.get("trig_units") or DEGREES
    spec = GearSpec()
    kind = KINDS["spur"]
    derived = kind.derive(spec)
    expected = derived.values()
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        mismatched: List[str] = []
        rewritten: Dict[str, str] = {}
        for variable in kind.variables(spec, derived):
            text = variable.text(trig)
            index = add(text)
            if not px.check(index >= 0, f"accepted: {text}"):
                mismatched.append(variable.name)
                continue
            value = float(call(eqm, "Value", index))
            if abs(value - expected[variable.name]) > 1e-6:
                mismatched.append(variable.name)
                px.fail(f"{variable.name} is {value!r} in SolidWorks and {expected[variable.name]!r} in the maths")
            read = str(call(eqm, "Equation", index))
            if read != text:
                rewritten[text] = read
        px.fact("globals_match_maths", not mismatched)
        px.fact("globals_mismatched", mismatched)
        px.fact("equation_text_rewritten", rewritten,
                f"{len(rewritten)} equation(s) read back differently from how they were written")


@probe("equation_set", needs=("equation_add",), tier=1,
       members=("IEquationMgr.Equation", "IEquationMgr.SetEquationAndConfigurationOption", "IEquationMgr.EvaluateAll",
                "IModelDoc2.ForceRebuild3"))
def equation_set(px: Px) -> None:
    """Changing a global's value from code propagates to what refers to it."""
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        base = add('"Probe Base"= 3')
        twice = add('"Probe Twice"= "Probe Base" * 2')
        px.require(base >= 0 and twice >= 0, "two linked globals are added")

        routes = (
            ("indexed put Equation(i)", lambda text: sc.put_indexed(eqm, "Equation", base, text)),
            ("SetEquationAndConfigurationOption",
             lambda text: call(eqm, "SetEquationAndConfigurationOption", base, text, ALL_CONFIGURATIONS, None)),
        )
        working = []
        for number, (label, fn) in enumerate(routes):
            new_value = 5.0 + number
            got, _ = px.attempt(label, lambda: fn(f'"Probe Base"= {new_value:g}'))
            call(doc, "ForceRebuild3", False)
            read = float(call(eqm, "Value", twice))
            follows = got and abs(read - 2 * new_value) < 1e-9
            # Only the first route is the one the build uses; the others are evidence.
            if number == 0:
                px.check(follows, f"{label}: the dependent global follows to {read!r}")
            else:
                px.note(f"{label}: the dependent global reads {read!r} ({'follows' if follows else 'does not follow'})")
            if follows:
                working.append(label)
        px.fact("equation_set_routes", working)
        px.require(bool(working), "at least one way of changing a global's value works")
        px.shared["equation_set_route"] = working[0]
