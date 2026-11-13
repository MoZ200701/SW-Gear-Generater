"""Tier 3: custom properties on a part — stamped, read back, replaced, and linked to a global.

The build would stamp a part's kind, flank and sizes as custom properties, so a
bill of materials can list them. Settled here: how
``ICustomPropertyManager.Add3`` takes its type and option; which read comes
back through late binding (``Get6`` with by-reference outs, or ``Get``); that
adding a name again replaces its value; and whether a property whose value is a
global's quoted name follows that global when the global changes — which is
what would let the sizes stay right after ``"No. of Teeth"`` is edited.

No enum value is written from memory: ``swCustomInfoType_e`` and
``swCustomPropertyAddOption_e`` are read from ``swconst.tlb``
(:func:`scaffold.swconst`), which is first made to give back a value already
settled. Written without SolidWorks; first run on SolidWorks 2026 (34.0.0) and
2024 (32.5.0) on 2026-11-13, where it passed unchanged.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from .. import findings, swcom
from ..swcom import call
from . import scaffold as sc
from .harness import Px, probe
from .p1_equations import adder


def _read(px: Px, manager: Any, name: str, label: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """``(route, value, resolved value)`` of one property, by the first read that works."""
    def get6() -> Any:
        value, resolved = swcom._out_text(), swcom._out_text()  # noqa: SLF001
        was, link = swcom._out_bool(), swcom._out_bool()  # noqa: SLF001
        status = call(manager, "Get6", name, False, value, resolved, was, link)
        return {"status": status, "value": value.value, "resolved": resolved.value}

    route, got = sc.attempts(px, f"{label}: read {name!r}", [
        ("Get6 with by-reference outs", get6),
        ("Get", lambda: {"value": call(manager, "Get", name), "resolved": None}),
    ])
    if route is None:
        return None, None, None
    if isinstance(got, tuple):          # late binding may hand the outs back as a tuple instead
        got = {"value": got[1] if len(got) > 1 else None, "resolved": got[2] if len(got) > 2 else None}
    return route, got.get("value"), got.get("resolved")


@probe("custom_properties", needs=("new_document", "equation_set"), tier=3,
       members=("IModelDocExtension.CustomPropertyManager", "ICustomPropertyManager.Add3",
                "ICustomPropertyManager.Get6", "ICustomPropertyManager.Get",
                "swconst.swCustomInfoType_e", "swconst.swCustomPropertyAddOption_e"))
def custom_properties(px: Px) -> None:
    """A text property is added and read back, replaced by a second Add3, and tried linked to a global."""
    mates = sc.swconst(px, "swMateType_e")
    px.require(mates.get("swMateDISTANCE") == findings.MATE_DISTANCE,
               "the swconst reader gives back a value already settled (swMateDISTANCE)")
    kinds = sc.swconst(px, "swCustomInfoType_e")
    options = sc.swconst(px, "swCustomPropertyAddOption_e")
    text = kinds.get("swCustomInfoText")
    replace = options.get("swCustomPropertyReplaceValue")
    px.require(text is not None and replace is not None,
               "swconst has swCustomInfoText and swCustomPropertyReplaceValue")
    px.fact("custom_info_text", text)
    px.fact("custom_property_replace", replace)

    with sc.scratch(px) as doc:
        got, manager = px.attempt("CustomPropertyManager('')",
                                  lambda: call(sc.extension(doc), "CustomPropertyManager", ""))
        px.require(got and manager is not None, "the part has a custom property manager")

        got, added = px.attempt("Add3('Gear Kind', text, 'spur', replace)",
                                lambda: call(manager, "Add3", "Gear Kind", text, "spur", replace))
        px.fact("add3_returned", added if got else "raised")
        route, value, _ = _read(px, manager, "Gear Kind", "added")
        px.fact("property_read_route", route)
        px.check(value == "spur", f"the property reads back 'spur': {value!r}")

        px.attempt("Add3('Gear Kind', text, 'helical', replace)",
                   lambda: call(manager, "Add3", "Gear Kind", text, "helical", replace))
        _, value, _ = _read(px, manager, "Gear Kind", "replaced")
        px.check(value == "helical", f"a second Add3 replaces the value: {value!r}")

        # Linked to a global: the value is the global's quoted name.
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        index = add('"No. of Teeth"= 25')
        px.require(index >= 0, "a global is added")
        call(doc, "ForceRebuild3", False)
        px.attempt("Add3('Teeth', text, '\"No. of Teeth\"', replace)",
                   lambda: call(manager, "Add3", "Teeth", text, '"No. of Teeth"', replace))
        _, value, before = _read(px, manager, "Teeth", "linked")
        sc.put_indexed(eqm, "Equation", index, '"No. of Teeth"= 40')
        call(doc, "ForceRebuild3", False)
        _, _, after = _read(px, manager, "Teeth", "linked, after the global changed")
        px.fact("linked_property", {"value": value, "resolved_before": before, "resolved_after": after})
        follows = before is not None and after is not None and _number(before) == 25 and _number(after) == 40
        # Either answer is a finding: a property that does not follow is stamped as plain text, or not at all.
        px.fact("property_links_global", follows)


def _number(text: Any) -> Optional[float]:
    try:
        return float(str(text).strip())
    except ValueError:
        return None
