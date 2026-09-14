"""From probe results to decisions. Pure: it reads records, it never calls COM.

The decisions are what the tool is allowed to rely on, so the rules here are
the plan's, spelled out: the flank recipe is A only if an Equation Driven Curve
works literally, with global names, and follows a rebuild; otherwise B only if
plain entities, relations and a linked dimension work; otherwise STOP, and
nothing is improvised.

``tests/test_probe_decide.py`` pins the rules against canned results, and
``tests/test_findings.py`` checks :mod:`findings` against the committed
``latest.json`` through this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

PASS = "pass"

RECIPE_A_NEEDS = ("curve_literal", "curve_globals", "curve_rebuild")
RECIPE_B_NEEDS = ("sketch_entities", "relations", "dimension_link")
PARAMETRIC_NEEDS = ("equation_add", "equation_syntax")

STOP = "STOP"


def _passed(records: Mapping[str, Mapping[str, Any]], name: str) -> bool:
    return (records.get(name) or {}).get("status") == PASS


def _fact(records: Mapping[str, Mapping[str, Any]], probe: str, key: str, default: Any = None) -> Any:
    return ((records.get(probe) or {}).get("facts") or {}).get(key, default)


def flank_recipe(records: Mapping[str, Mapping[str, Any]]) -> str:
    if not all(_passed(records, name) for name in PARAMETRIC_NEEDS):
        return STOP
    if all(_passed(records, name) for name in RECIPE_A_NEEDS):
        return "A"
    if all(_passed(records, name) for name in RECIPE_B_NEEDS):
        return "B"
    return STOP


def manual_steps(records: Mapping[str, Mapping[str, Any]], recipe: str) -> List[str]:
    """Steps a negative probe turns into something a person does, by cause."""
    steps: List[str] = ["material"]
    if recipe == "A" and not _passed(records, "curve_globals") and _passed(records, "curve_literal"):
        steps.append("partial-parametric flanks")
    if _passed(records, "pattern") and not _passed(records, "pattern_count_link"):
        steps.append("link Count@Teeth in Equations")
    return steps


def decide(records: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    recipe = flank_recipe(records)
    decisions: Dict[str, Any] = {"flank_recipe": recipe}
    if _passed(records, "equation_syntax"):
        decisions["trig_default"] = _fact(records, "equation_syntax", "trig_units")
    if _passed(records, "equation_add"):
        decisions["add3_form"] = _fact(records, "equation_add", "add3_form")
    if _passed(records, "equation_set"):
        decisions["equation_set_route"] = (_fact(records, "equation_set", "equation_set_routes") or [None])[0]
    if _passed(records, "templates"):
        decisions["part_template_route"] = _fact(records, "templates", "part_template_route")
    decisions["manual_steps"] = manual_steps(records, recipe)
    return decisions
