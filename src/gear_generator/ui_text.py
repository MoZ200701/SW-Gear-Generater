"""The words the window puts on screen, worked out without a window.

Every panel header's readout, every derived row, candidate row and status line
is derived text: one short line standing for the state of something. Working
them out here keeps them testable on a machine with no display, and keeps
:mod:`gui` to laying out widgets and wiring handlers.

Nothing here touches tkinter, and nothing here holds state.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

from .gears import pair as pairs
from .gears.base import Diagnostic
from .gears.equations import literal
from .spec import MODE_PAIR, RECIPE_ARCS, RECIPE_INVOLUTE, GearSpec, InputError

RECIPE_WORDS = {RECIPE_INVOLUTE: "involute curve", RECIPE_ARCS: "arc flanks"}
RECIPE_LABELS = {RECIPE_INVOLUTE: "Involute", RECIPE_ARCS: "Arcs"}
KIND_LABELS = {"spur": "Spur", "bevel": "Bevel", "helical": "Helical", "internal": "Internal"}


def _n(value: float, places: int = 3) -> str:
    return literal(round(float(value), places))


# ------------------------------------------------------------- the readouts


def kind_readout(kind: str, recipe: str) -> str:
    """``Spur · involute curve``."""
    return f"{KIND_LABELS.get(kind, kind.title())} · {RECIPE_WORDS.get(recipe, recipe)}"


def gear_readout(spec: GearSpec) -> str:
    """``m1.5 · z25 · 20° · PD 37.5 mm``, or what is stopping it."""
    try:
        m = spec.module_mm()
        n = spec.teeth_count()
        alpha = spec.pressure_angle_deg()
    except InputError:
        return "check the fields"
    return f"m{_n(m)} · z{n} · {_n(alpha, 2)}° · PD {_n(m * n)} mm"


def derived_line(g) -> str:
    """``PD 37.5 · OD 40.5 · RD 33.75 · base 35.238 · p 4.712``."""
    return (
        f"PD {_n(g.d)} · OD {_n(g.da)} · RD {_n(g.df)} · base {_n(g.db)} · p {_n(g.p)}"
    )


def derived_rows(g) -> List[Tuple[str, str]]:
    """The Derived panel's label/value rows. Every value is in mm, said once above them.

    Short on purpose: in pair mode two columns of these share the width the
    preview leaves.
    """
    return [
        ("Pitch diameter", _n(g.d)),
        ("Outer diameter", _n(g.da)),
        ("Root diameter", _n(g.df)),
        ("Base diameter", _n(g.db)),
        ("Tooth depth", _n(g.h)),
        ("Circular pitch", _n(g.p)),
        ("Space at pitch", _n(g.space)),
        ("Tooth at pitch", _n(g.s)),
        ("Tip thickness", _n(g.tip_thickness)),
        ("Backlash", _n(g.backlash) + ("" if g.backlash_typed else " · 0.3m")),
        ("Fillet", _n(g.fillet) + ("" if g.fillet_typed else " · 0.38m")),
    ]


def warning_lines(diagnostics: Sequence[Diagnostic]) -> List[str]:
    """Errors first, then warnings, each once."""
    ordered = [d for d in diagnostics if d.is_error] + [d for d in diagnostics if not d.is_error]
    return list(dict.fromkeys(d.message for d in ordered))


def pair_readout(centre: str, ratio: str, chosen: Optional["pairs.Candidate"] = None) -> str:
    """``C 60 mm · i 3`` and, once one is chosen, ``· m1.5 20:60``."""
    parts = []
    if centre.strip():
        parts.append(f"C {centre.strip()} mm")
    if ratio.strip():
        parts.append(f"i {ratio.strip()}")
    if chosen is not None:
        parts.append(f"m{_n(chosen.module, 4)} {chosen.teeth_driver}:{chosen.teeth_driven}")
    return " · ".join(parts) or "centre distance and ratio"


def candidate_row(candidate: "pairs.Candidate") -> Tuple[str, str, str, str]:
    """``(MODULE, TEETH, ERROR, tag)`` for one row of the candidate list.

    The tag is ``exact`` or ``near``, which is what the row is coloured by.
    """
    module = _n(candidate.module, 4) + ("" if candidate.standard else " *")
    teeth = f"{candidate.teeth_driver} : {candidate.teeth_driven}"
    errors = []
    if abs(candidate.centre_error) > pairs.TOLERANCE:
        errors.append(f"C {'+' if candidate.centre_error > 0 else '−'}{_n(abs(candidate.centre_error))} mm")
    if candidate.ratio_error > pairs.TOLERANCE:
        errors.append(f"i {_n(candidate.ratio_error * 100, 2)} %")
    if candidate.undercut:
        errors.append("undercut")
    text = " · ".join(errors) if errors else "exact"
    return module, teeth, text, "exact" if candidate.exact else "near"


def solve_summary(candidates: Sequence["pairs.Candidate"]) -> str:
    """``12 candidates · 3 exact``."""
    if not candidates:
        return "No pair of whole tooth counts fits; widen the series or Min teeth."
    exact = sum(1 for c in candidates if c.exact and c.standard and not c.undercut)
    noun = "candidate" if len(candidates) == 1 else "candidates"
    return f"{len(candidates)} {noun} · {exact} exact"


def output_readout(folder: str, limit: int = 38) -> str:
    """The folder, shortened from the left so its last parts stay readable."""
    text = folder.strip()
    if not text:
        return "choose a folder"
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):]


def link_headline(available: bool, snapshot: Optional[dict]) -> Tuple[str, str]:
    """The SolidWorks bar's readout, and which colour its dot takes.

    Unlike Airfoil Converter this app makes its own documents, so no document
    open is a perfectly good state to build from: it is ``ok``.
    """
    if not available:
        return "pywin32 not installed", "off"
    if snapshot is None:
        return "not reachable", "bad"
    label = snapshot.get("version") or "SolidWorks"
    if snapshot.get("newer_than_tested"):
        label += " (newer than tested)"
    title = snapshot.get("title")
    if not title:
        return f"{label} — no document open", "ok"
    return f"{label} — {title}", "ok"


def mode_note(mode: str, stems: Sequence[str], update_count: int = 0, document: str = "") -> str:
    """What the primary button is about to do, in a sentence."""
    if update_count and document:
        noun = "variable" if update_count == 1 else "variables"
        return f"Update values will change {update_count} {noun} in {document}."
    if mode == MODE_PAIR and len(stems) >= 3:
        return f"Build will make {stems[0]}.SLDPRT, {stems[1]}.SLDPRT and {stems[2]}.SLDASM."
    if stems:
        return f"Build will make {stems[0]}.SLDPRT."
    return "Build will make a new part."


def manual_steps_line(steps: Iterable[str]) -> str:
    """``1 thing to do by hand: …`` — counted, so it is not a surprise."""
    listed = list(dict.fromkeys(steps))
    if not listed:
        return ""
    noun = "thing" if len(listed) == 1 else "things"
    return f"{len(listed)} {noun} to do by hand: " + "; ".join(s.rstrip(".") for s in listed) + "."


def angle_text(degrees: float) -> str:
    return f"{_n(degrees, 4)}°"


def contact_ratio_text(epsilon: float) -> str:
    return "—" if not math.isfinite(epsilon) else _n(epsilon, 3)
