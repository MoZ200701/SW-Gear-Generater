"""Print a gear's build plan without SolidWorks: ``python -m gear_generator.gears``.

::

    python -m gear_generator.gears --spec m=1.5,z=25 --recipe A

The spec keys are ``m`` (module), ``z`` (teeth), ``pa`` (pressure angle),
``b`` (face width), ``bore``, ``j`` (backlash), ``rho`` (fillet) and ``name``;
``kind`` (spur, helical, herringbone, bevel), ``beta`` and ``hand`` for the
helical kinds, ``side`` (external or internal) and ``rim`` for a ring, and
``mate`` and ``shaft`` for a bevel gear, ``x`` for a profile shift, and ``g``
for a herringbone's centre groove::

    python -m gear_generator.gears --spec kind=bevel,m=3,z=20,mate=40,b=20,bore=10
    python -m gear_generator.gears --spec side=internal,m=2,z=60
    python -m gear_generator.gears --spec m=2,z=15,x=0.12
    python -m gear_generator.gears --spec kind=herringbone,m=2,z=20,beta=30,b=40,g=8

The output is the ordered op log the build would run, globals first, with every
step a person has to do by hand counted as ``MANUAL``.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List, Optional, Sequence

from .. import findings
from ..spec import GearSpec, InputError
from . import kind_for
from .base import GeometryError
from .equations import TRIG_MODES

KEYS = {
    "m": "module", "z": "teeth", "pa": "pressure_angle", "b": "face_width",
    "bore": "bore", "j": "backlash", "rho": "fillet", "name": "name",
    "kind": "kind", "beta": "helix_angle", "hand": "hand", "side": "teeth_side", "rim": "rim",
    "mate": "mate_teeth", "shaft": "shaft_angle", "x": "profile_shift", "g": "groove",
}


def parse_spec(text: str) -> GearSpec:
    values: Dict[str, str] = {}
    for item in filter(None, (part.strip() for part in text.split(","))):
        key, sep, value = item.partition("=")
        if not sep or key.strip() not in KEYS:
            raise InputError(
                f"Spec items are key=value with keys {', '.join(KEYS)} (got {item!r})."
            )
        values[KEYS[key.strip()]] = value.strip()
    return GearSpec(**values)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m gear_generator.gears", description=__doc__.splitlines()[0])
    parser.add_argument("--spec", default="", help="comma-separated key=value, e.g. m=1.5,z=25")
    parser.add_argument("--recipe", default="", help="A (involute) or B (arcs); default from findings")
    parser.add_argument("--trig", default=findings.TRIG_DEFAULT, choices=TRIG_MODES)
    parser.add_argument("--template", default="", help="part template path")
    parser.add_argument("--out", default="C:\\Gears", help="the folder the part would be saved in")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    try:
        spec = parse_spec(args.spec)
        if args.recipe:
            spec = spec.with_values(recipe=args.recipe)
        kind = kind_for(spec)
        if kind is None:
            raise InputError(f"There is no gear kind {spec.kind!r} with {spec.teeth_side} teeth.")
        recipe = spec.recipe_or(kind.default_recipe)
    except (InputError, KeyError) as exc:
        print(f"FAIL    {exc}")
        return 1

    diagnostics = kind.validate(spec)
    for diagnostic in diagnostics:
        token = "FAIL   " if diagnostic.is_error else "warn   "
        print(f"{token} {diagnostic.message}")
    if any(d.is_error for d in diagnostics):
        return 1

    try:
        derived = kind.derive(spec)
        path = args.out.rstrip("\\/") + "\\" + spec.stem() + ".SLDPRT"
        plan = kind.plan(spec, derived, recipe, args.template, path)
    except (GeometryError, InputError) as exc:
        print(f"FAIL    {exc}")
        return 1

    lines: List[str] = plan.log_lines(args.trig)
    problems = plan.check()
    for line in lines:
        print(line)
    for problem in problems:
        print(f"FAIL    plan: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
