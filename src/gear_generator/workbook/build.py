"""From workbook rows to SolidWorks build plans (docs/PLAN-WORKBOOK.md §4.1, phase W2: parts only).

Each row is turned into the strip's own form, ``GearSpec``, and from there
into the strip's own plan, with the strip's own validation in between — so a
row builds exactly the part the strip would build from the same values, and
every rule the strip enforces holds here too. What is new is only the
bookkeeping: which rows this phase can build, which share one part file, and
where each diagnostic points in the workbook.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..gears import kind_for
from ..gears.base import ERROR, WARNING, BuildPlan, Diagnostic, GeometryError
from ..spec import GearSpec, InputError
from .model import Gear, GearboxSpec

PART_SUFFIX = ".SLDPRT"

# Kinds a later phase builds, and the sentence that says which.
LATER = {
    "bevel": "bevel gears are built in phase W6, once the right-angle stage gives them their partner",
    "sleeve": "sleeves are built in phase W8, with modes",
    "dog": "dog rings are built in phase W8, with modes",
}

# A GearSpec field's diagnostics belong to a workbook column; most share the name.
FIELD_COLUMN = {"teeth_side": "side", "recipe": "flank", "name": "part_name"}


@dataclass(frozen=True)
class PartJob:
    """One part file to build, and every workbook row it serves (identical gears share one part)."""

    stem: str
    path: str
    gear_ids: Tuple[str, ...]
    spec: GearSpec
    derived: Any
    plan: BuildPlan


@dataclass
class PartsPlan:
    jobs: List[PartJob] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)   # each names its cell
    later: List[Tuple[str, str]] = field(default_factory=list)    # (gear, why it is not built yet)

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.is_error]

    @property
    def buildable(self) -> bool:
        return bool(self.jobs) and not self.errors


def _where(spec: GearboxSpec, gear: Gear, field_name: str) -> str:
    key = FIELD_COLUMN.get(field_name, field_name)
    if field_name and key in {c for c in spec.columns.get("Gears", {})}:
        return spec.cell("Gears", gear.row, key)
    return spec.cell("Gears", gear.row, "id")


def check_gear(spec: GearboxSpec, gear: Gear) -> Tuple[Optional[GearSpec], Any, List[Diagnostic]]:
    """The strip's checks on one row: (its GearSpec, what it works out to or None, diagnostics naming cells)."""
    gear_spec = gear.gear_spec(spec.box)
    kind = kind_for(gear_spec)
    if kind is None:
        return gear_spec, None, []
    out: List[Diagnostic] = []
    try:
        for d in kind.validate(gear_spec):
            where = _where(spec, gear, d.field)
            out.append(Diagnostic(d.level, f"{where}: {gear.id}: {d.message}", where))
        if any(d.is_error for d in out):
            return gear_spec, None, out
        return gear_spec, kind.derive(gear_spec), out
    except (GeometryError, InputError, ValueError) as exc:
        where = _where(spec, gear, "")
        out.append(Diagnostic(ERROR, f"{where}: {gear.id}: {exc}", where))
        return gear_spec, None, out


def rows_with_errors(diagnostics) -> set:
    """The Gears rows a reading error already points at: the strip's checks would only repeat it."""
    rows = set()
    for d in diagnostics:
        if d.is_error:
            match = re.match(r"^Gears(?:!\$?[A-Za-z]{1,3}\$?(\d+)| row (\d+))$", d.field or "")
            if match:
                rows.add(int(match.group(1) or match.group(2)))
    return rows


def plan_parts(spec: GearboxSpec, folder: str, part_template: str = "", skip_rows=()) -> PartsPlan:
    """A plan per distinct part: each buildable row checked, identical rows sharing one file.

    Two rows that would make the same file name but are not the same gear (a
    different face width, say, which the strip's naming leaves out) are an
    error naming both, since one file cannot be both gears.
    """
    out = PartsPlan()
    template = spec.box.part_template or part_template
    by_stem: Dict[str, Tuple[GearSpec, List[Gear], Any]] = {}
    order: List[str] = []
    for gear in spec.gears:
        why = LATER.get(gear.kind_word())
        if why:
            out.later.append((gear.id, why))
            continue
        if gear.row in skip_rows:
            continue                       # its own cell is already an error; it is not built
        gear_spec, derived, diagnostics = check_gear(spec, gear)
        out.diagnostics.extend(diagnostics)
        if derived is None:
            continue
        stem = gear_spec.stem()
        if stem in by_stem:
            first_spec, gears, _ = by_stem[stem]
            if first_spec != gear_spec:
                where = _where(spec, gear, "name")
                out.diagnostics.append(Diagnostic(
                    ERROR, f"{where}: {gear.id} and {gears[0].id} would both be {stem}{PART_SUFFIX}, but they "
                           f"are not the same gear; give one of them a Part name.", where))
                continue
            gears.append(gear)
            continue
        by_stem[stem] = (gear_spec, [gear], derived)
        order.append(stem)

    if out.errors:
        return out
    for stem in order:
        gear_spec, gears, derived = by_stem[stem]
        kind = kind_for(gear_spec)
        path = os.path.join(folder, stem + PART_SUFFIX)
        plan = kind.plan(gear_spec, derived, kind.recipe_for(gear_spec), template, path)
        out.jobs.append(PartJob(stem, path, tuple(g.id for g in gears), gear_spec, derived, plan))
    return out


def gear_diagnostics(spec: GearboxSpec, skip_rows=()) -> List[Diagnostic]:
    """Every row's own checks, for the window to show as the file changes — no plans are made."""
    out: List[Diagnostic] = []
    for gear in spec.gears:
        if gear.kind_word() in LATER or gear.row in skip_rows:
            continue
        out.extend(check_gear(spec, gear)[2])
    return out
