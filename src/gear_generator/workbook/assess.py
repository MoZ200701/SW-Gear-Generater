"""One read of a workbook, worked through once, and what may be built from it (docs/PLAN-WORKBOOK.md §3–§4).

:func:`assess` is the one pipeline the window, the design boards and SolidWorks
builds share: the read's own diagnostics, each gear through the strip's checks
(:func:`build.plan_parts`), and the gearbox checks (:func:`checks.check`) on
what is left, with any chosen fixes made first. Its answers are the gates:

- :func:`build_refusal` — may **Build parts** go ahead? Not while anything is
  an error; rows a later phase builds do not hold it back, their parts are left
  out.
- :meth:`Assessment.lay_out_refusal` — may the layout part and the assembly
  (phase W4) be built? Everything Build parts asks, and also: no fix waiting for
  Export, a gearbox that was checked at all, no row a later phase builds, and
  every gear placed and planned, so an assembly is never made without one.

Each answers with the sentence that refuses, or ``""``. Nothing here touches Tk
or COM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from ..gears.base import Diagnostic
from . import build, checks, fixes
from .build import PartsPlan
from .checks import Report
from .fixes import Fix
from .model import GearboxSpec


def _plural(count: int, one: str, many: str = "") -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _more(items: Sequence) -> str:
    return f" ({len(items) - 1} more under Checks)" if len(items) > 1 else ""


@dataclass
class Assessment:
    read: GearboxSpec                       # the workbook as read
    read_diagnostics: List[Diagnostic]      # what the read itself said, each at its cell
    spec: GearboxSpec                       # the read with the chosen fixes made
    chosen: Tuple[Fix, ...] = ()
    parts: PartsPlan = field(default_factory=PartsPlan)
    report: Report = field(default_factory=Report)
    diagnostics: List[Diagnostic] = field(default_factory=list)    # all of it, as Checks lists it

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.is_error]

    def build_refusal(self) -> str:
        """Why Build parts may not go ahead, or ``""``. A fix waiting for Export is the window's to say."""
        return build_refusal(self.parts, self.diagnostics)

    def lay_out_refusal(self) -> str:
        """Why the layout part and the static assembly (W4) may not be built from this workbook, or ``""``.

        The one gate for W4: it reads everything — the read, every gear's own
        checks, the gearbox checks, the rows a later phase builds and the fixes
        chosen but not exported. It does not know the window's own state (a
        file gone or half-saved, an Export that Excel has yet to recalculate, a
        build running): the window asks those first, as it does for Build parts.
        """
        if self.chosen:
            n = len(self.chosen)
            return (f"{_plural(n, 'fix', 'fixes')} chosen: Export writes {'it' if n == 1 else 'them'} into the "
                    "workbook first, so the workbook and the assembly agree.")
        refusal = self.build_refusal()
        if refusal:
            return refusal
        if self.report.unchecked:
            return f"The gearbox cannot be laid out yet, since it is not checked: {self.report.unchecked}"
        refused = self.parts.refused
        if refused:
            return f"The layout and assembly wait for a later phase: {refused[0].message}{_more(refused)}"
        placed = self.report.layout.placed
        planned = {g for job in self.parts.jobs for g in job.gear_ids}
        missing = [g.id for g in self.spec.gears if g.id not in placed or g.id not in planned]
        if missing:
            # Every way a gear is left out is an error or a refused row above; this says it if one ever is not.
            one = len(missing) == 1
            return (f"{', '.join(missing)} {'is' if one else 'are'} not placed, so the assembly would be built "
                    f"without {'it' if one else 'them'}; see Checks.")
        return ""


def build_refusal(parts: PartsPlan, diagnostics: Sequence[Diagnostic]) -> str:
    """Why Build parts may not go ahead, from the parts and every diagnostic, or ``""``."""
    errors = [d for d in diagnostics if d.is_error]
    if errors:
        return f"Fix the workbook before building: {errors[0].message}{_more(errors)}"
    if not parts.jobs:
        return "Nothing in this workbook can be built yet: " + (parts.later[0][1] if parts.later
                                                                else "it has no gears.")
    return ""


def assess(read: GearboxSpec, read_diagnostics: Sequence[Diagnostic], folder: str, part_template: str = "",
           chosen: Sequence[Fix] = ()) -> Assessment:
    """The read worked through: the chosen fixes made, every gear planned, the gearbox checked.

    A gear with an error of its own — from the read or the strip's checks — is
    left out of the parts and the gearbox checks (the error says where), and
    then out of the layout too (:attr:`geometry.Layout.left_out`).
    """
    spec = read
    for fix in chosen:
        spec = fixes.apply(spec, fix)
    read_diagnostics = list(read_diagnostics)
    skip_rows = build.rows_with_errors(read_diagnostics)
    parts = build.plan_parts(spec, folder, part_template, skip_rows=skip_rows)
    bad_rows = skip_rows | build.rows_with_errors(parts.diagnostics)
    report = checks.check(spec, {g.id for g in spec.gears if g.row in bad_rows})
    return Assessment(read=read, read_diagnostics=read_diagnostics, spec=spec, chosen=tuple(chosen), parts=parts,
                      report=report, diagnostics=read_diagnostics + parts.diagnostics + report.diagnostics)
