"""Equation Manager text, and a small evaluator of the grammar it is written in.

The gear is parametric inside SolidWorks: every size is a global variable in
the Equation Manager and every dimension is an equation over them. Those
strings are the product, so they are built here and nowhere else — and so they
can be checked without SolidWorks, this module can also *evaluate* them. A test
runs the emitted list in order and compares every value with the maths in
:mod:`gears.spur`; a name used before it is defined, a missing bracket or a
trig function fed degrees in a radian document all fail there rather than as a
red equation in someone's part.

The grammar covered is the part this tool writes: quoted names, numbers,
``+ - * / ^``, brackets, comparisons, ``IIF``, ``pi``, the trig functions and
``sqr``. **Trig units are a per-document setting.** In a degree document
``sin ( 90 )`` is 1; in a radian one it is not. The evaluator takes the mode as
an argument, and the build measures the document's mode before it writes
anything.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

DEGREES = "degrees"
RADIANS = "radians"
TRIG_MODES = (DEGREES, RADIANS)


class EquationError(ValueError):
    """An equation could not be read or evaluated."""


# -- number and name hygiene ------------------------------------------------


def fmt9(value: float) -> str:
    """Fixed point, nine decimals, no negative zero; refuses non-finite values.

    Nine decimals of a metre is a tenth of a micron and is what the SolidWorks
    macro recorder itself emits. The sign is stripped *after* formatting, so
    ``-1e-12`` does not print as ``-0.000000000``.
    """
    value = float(value)
    if not math.isfinite(value):
        raise EquationError(f"Refusing to write a non-finite number ({value!r}).")
    text = f"{value:.9f}"
    if text.startswith("-") and float(text) == 0.0:
        text = text[1:]
    return text


def literal(value: float) -> str:
    """A number as an equation literal: ``fmt9`` without the trailing zeros.

    ``25`` stays ``25`` and ``1.5`` stays ``1.5``, which is how the user's own
    variables read in the Equation Manager.
    """
    text = fmt9(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def quote(name: str) -> str:
    if '"' in name:
        raise EquationError(f"A name cannot contain a double quote (got {name!r}).")
    return f'"{name}"'


def equation_text(name: str, expression: str) -> str:
    """``"Module"= 1.5`` — the spacing the Equation Manager itself writes."""
    return f"{quote(name)}= {expression}"


def split_equation(text: str) -> Tuple[str, str]:
    """``'"Module"= 1.5'`` -> ``("Module", "1.5")``."""
    match = re.match(r'^\s*"([^"]+)"\s*=\s*(.*)$', text)
    if match is None:
        raise EquationError(f"Not an equation of the form \"name\"= expression: {text!r}.")
    return match.group(1), match.group(2)


def names_in(expression: str) -> List[str]:
    """Every quoted name an expression refers to, in order of first use."""
    seen: List[str] = []
    for name in re.findall(r'"([^"]+)"', expression):
        if name not in seen:
            seen.append(name)
    return seen


# -- the evaluator ----------------------------------------------------------

_TOKEN = re.compile(
    r"""\s*(?:
        (?P<number>\d+(?:\.\d*)?(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?)
      | "(?P<name>[^"]+)"
      | (?P<word>[A-Za-z_][A-Za-z_0-9]*)
      | (?P<op><=|>=|<>|[-+*/^(),<>=])
    )""",
    re.VERBOSE,
)


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str


def _tokens(expression: str) -> List[_Token]:
    out: List[_Token] = []
    position = 0
    text = expression.rstrip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            raise EquationError(
                f"Cannot read {expression!r} at character {position + 1}: {text[position:position + 12]!r}."
            )
        position = match.end()
        for kind in ("number", "name", "word", "op"):
            value = match.group(kind)
            if value is not None:
                out.append(_Token(kind, value))
                break
    return out


def _trig(mode: str) -> Dict[str, Callable[[float], float]]:
    to_rad = math.radians if mode == DEGREES else (lambda x: x)
    from_rad = math.degrees if mode == DEGREES else (lambda x: x)
    return {
        "sin": lambda x: math.sin(to_rad(x)),
        "cos": lambda x: math.cos(to_rad(x)),
        "tan": lambda x: math.tan(to_rad(x)),
        "atn": lambda x: from_rad(math.atan(x)),
        "arcsin": lambda x: from_rad(math.asin(x)),
        "arccos": lambda x: from_rad(math.acos(x)),
    }


_PLAIN: Dict[str, Callable[[float], float]] = {
    "sqr": math.sqrt,
    "abs": abs,
    "exp": math.exp,
    "log": math.log,
    "int": lambda x: float(math.floor(x)),
    "sgn": lambda x: float((x > 0) - (x < 0)),
}


class _Parser:
    def __init__(self, expression: str, scope: Mapping[str, float], mode: str,
                 variables: Mapping[str, float]) -> None:
        if mode not in TRIG_MODES:
            raise EquationError(f"Trig mode must be {DEGREES} or {RADIANS} (got {mode!r}).")
        self.expression = expression
        self.tokens = _tokens(expression)
        self.i = 0
        self.scope = scope
        self.variables = variables
        self.functions = dict(_PLAIN)
        self.functions.update(_trig(mode))

    def peek(self) -> Optional[_Token]:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, text: Optional[str] = None) -> _Token:
        token = self.peek()
        if token is None:
            raise EquationError(f"{self.expression!r} ends too soon.")
        if text is not None and token.text.lower() != text:
            raise EquationError(f"{self.expression!r}: expected {text!r}, found {token.text!r}.")
        self.i += 1
        return token

    def run(self) -> float:
        if not self.tokens:
            raise EquationError("An empty expression has no value.")
        value = self.comparison()
        if self.peek() is not None:
            raise EquationError(f"{self.expression!r}: unexpected {self.peek().text!r}.")
        return value

    def comparison(self) -> float:
        left = self.sum()
        token = self.peek()
        if token is not None and token.kind == "op" and token.text in ("<", ">", "<=", ">=", "=", "<>"):
            self.take()
            right = self.sum()
            result = {
                "<": left < right, ">": left > right, "<=": left <= right,
                ">=": left >= right, "=": left == right, "<>": left != right,
            }[token.text]
            return 1.0 if result else 0.0
        return left

    def sum(self) -> float:
        value = self.product()
        while True:
            token = self.peek()
            if token is None or token.text not in ("+", "-"):
                return value
            self.take()
            right = self.product()
            value = value + right if token.text == "+" else value - right

    def product(self) -> float:
        value = self.unary()
        while True:
            token = self.peek()
            if token is None or token.text not in ("*", "/"):
                return value
            self.take()
            right = self.unary()
            if token.text == "*":
                value *= right
            else:
                if right == 0:
                    raise EquationError(f"{self.expression!r} divides by zero.")
                value /= right

    def unary(self) -> float:
        token = self.peek()
        if token is not None and token.text in ("-", "+"):
            self.take()
            value = self.unary()
            return -value if token.text == "-" else value
        return self.power()

    def power(self) -> float:
        base = self.atom()
        token = self.peek()
        if token is not None and token.text == "^":
            self.take()
            return base ** self.unary()
        return base

    def atom(self) -> float:
        token = self.take()
        if token.kind == "number":
            return float(token.text)
        if token.kind == "name":
            if token.text not in self.scope:
                raise EquationError(
                    f"{self.expression!r} uses \"{token.text}\" before it is defined."
                )
            return float(self.scope[token.text])
        if token.text == "(":
            value = self.comparison()
            self.take(")")
            return value
        if token.kind == "word":
            word = token.text.lower()
            if word == "pi":
                return math.pi
            if word in self.variables:
                return float(self.variables[word])
            if word == "iif":
                self.take("(")
                condition = self.comparison()
                self.take(",")
                when_true = self.comparison()
                self.take(",")
                when_false = self.comparison()
                self.take(")")
                return when_true if condition != 0 else when_false
            if word in self.functions:
                self.take("(")
                argument = self.comparison()
                self.take(")")
                try:
                    return float(self.functions[word](argument))
                except (ValueError, OverflowError) as exc:
                    raise EquationError(f"{self.expression!r}: {word} of {argument!r} fails ({exc}).") from None
            raise EquationError(f"{self.expression!r}: {token.text!r} is not a function this grammar knows.")
        raise EquationError(f"{self.expression!r}: unexpected {token.text!r}.")


def evaluate(expression: str, scope: Mapping[str, float] = None, mode: str = DEGREES,
             variables: Mapping[str, float] = None) -> float:
    """The value of one expression. ``variables`` holds bare words such as ``t``."""
    return _Parser(expression, scope or {}, mode, {k.lower(): v for k, v in (variables or {}).items()}).run()


def evaluate_all(equations: Iterable[Tuple[str, str]], mode: str = DEGREES,
                 scope: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
    """Run ``(name, expression)`` pairs in order, each seeing only those before it.

    That ordering is exactly the Equation Manager's rule for globals, so a list
    that evaluates here in order is a list whose every name is defined before it
    is used.
    """
    values: Dict[str, float] = dict(scope or {})
    for name, expression in equations:
        if name in values:
            raise EquationError(f"\"{name}\" is defined twice.")
        values[name] = evaluate(expression, values, mode)
    return values


def substitute(expression: str, values: Mapping[str, float]) -> str:
    """Replace every quoted name with its value, for when names are refused.

    The result is still an expression over any bare variable such as ``t``, so
    a curve keeps its true shape; it simply stops following the globals.
    """
    def replace(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in values:
            raise EquationError(f"Cannot substitute \"{name}\": it has no value.")
        text = literal(values[name])
        return f"( {text} )" if text.startswith("-") else text

    return re.sub(r'"([^"]+)"', replace, expression)


def check_order(equations: Sequence[Tuple[str, str]], known: Iterable[str] = ()) -> List[str]:
    """Names used before they are defined, as sentences. Empty when all is well."""
    defined = set(known)
    problems: List[str] = []
    for name, expression in equations:
        for used in names_in(expression):
            if used not in defined:
                problems.append(f"\"{name}\" refers to \"{used}\" before \"{used}\" is defined.")
        defined.add(name)
    return problems
