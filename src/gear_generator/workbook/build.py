"""From workbook rows to SolidWorks build plans (docs/PLAN-WORKBOOK.md §4.1, phase W2: parts only).

Each row is turned into the strip's own form, ``GearSpec``, and from there
into the strip's own plan, with the strip's own validation in between — so a
row builds exactly the part the strip would build from the same values, and
every rule the strip enforces holds here too. What is new is only the
bookkeeping: which rows this phase can build, which share one part file, and
where each diagnostic points in the workbook.

**Rows a later phase builds** (§3.4: bevel gears, carriers and copies, turned
axes, sleeves, dogs, sliding gears, modes) are read, and refused at Build with
the phase that builds them — not errors. :func:`later_rows` names each one.
Build parts leaves out the parts of bevel, sleeve and dog rows and builds the
rest, since a planet or a sliding gear is an ordinary part; but none of these
rows is laid out, checked or placed before its phase, so the layout part and
assembly (W4) are refused whole while any is there (:attr:`PartsPlan.can_lay_out`).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..gears import kind_for, plan_for
from ..gears.base import ERROR, WARNING, BuildPlan, Diagnostic, GeometryError
from ..spec import GearSpec, InputError
from .geometry import AXES
from .model import Gear, GearboxSpec
from .schema import FRAME

PART_SUFFIX = ".SLDPRT"

# Kinds a later phase builds: what such a row is, and the phase that builds it (PLAN-WORKBOOK §6).
LATER = {
    "bevel": ("a bevel gear", "right-angle stages are built in phase W6"),
    "sleeve": ("a sleeve", "sleeves are built in phase W8, with modes"),
    "dog": ("a dog ring", "dog rings are built in phase W8, with modes"),
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
    diagnostics: List[Diagnostic] = field(default_factory=list)   # each names its cell; ``refused`` among them
    later: List[Tuple[str, str]] = field(default_factory=list)    # (gear, why its part is not built yet)
    refused: List[Diagnostic] = field(default_factory=list)       # every row a later phase builds (later_rows)

    @property
    def errors(self) -> List[Diagnostic]:
        return [d for d in self.diagnostics if d.is_error]

    @property
    def buildable(self) -> bool:
        return bool(self.jobs) and not self.errors

    @property
    def can_lay_out(self) -> bool:
        """Whether the layout part and the assembly (phase W4) may be built from these rows: not while any row is
        a later phase's, since none of those is laid out, checked or placed yet. W4 refuses with ``refused[0]``."""
        return self.buildable and not self.refused


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

    Two rows share a file when they would build the same part: their plans are
    compared, not their forms, so a Part name typed as the default, or a Hand
    on a spur gear, does not make two identical gears different. Two rows that
    would make the same file name — ignoring case, as Windows does — but not
    the same part (a different face width, which the name leaves out) are an
    error naming both, since one file cannot be both gears.

    A gear with an error is not planned, but the others still are: the window
    shows what each good gear will become, and Build waits for the errors.
    """
    out = PartsPlan()
    template = spec.box.part_template or part_template
    jobs: Dict[str, PartJob] = {}          # by the file name in lower case
    order: List[str] = []
    out.refused = later_rows(spec)
    for gear in spec.gears:
        if gear.kind_word() in LATER:
            out.later.append((gear.id, _later_kind(gear)))
            continue
        if gear.row in skip_rows:
            continue                       # its own cell is already an error; it is not built
        gear_spec, derived, diagnostics = check_gear(spec, gear)
        out.diagnostics.extend(diagnostics)
        if derived is None:
            continue
        stem = gear_spec.stem()
        key = stem.lower()
        if key in jobs:
            first = jobs[key]
            if plan_for(gear_spec, derived, template, first.path) != first.plan:
                where = _where(spec, gear, "name")
                same = "" if stem == first.stem else f" ({first.stem} and {stem} are one name to Windows)"
                out.diagnostics.append(Diagnostic(
                    ERROR, f"{where}: {gear.id} and {first.gear_ids[0]} would both be {first.stem}{PART_SUFFIX}"
                           f"{same}, but they are not the same gear; give one of them a Part name.", where))
                continue
            jobs[key] = PartJob(first.stem, first.path, first.gear_ids + (gear.id,), first.spec, first.derived,
                                first.plan)
            continue
        path = os.path.join(folder, stem + PART_SUFFIX)
        jobs[key] = PartJob(stem, path, (gear.id,), gear_spec, derived, plan_for(gear_spec, derived, template, path))
        order.append(key)
    out.jobs = [jobs[key] for key in order]
    out.diagnostics.extend(out.refused)          # listed under Checks with the rest, each at its cell
    return out


def _later_kind(gear: Gear) -> str:
    """``G5 is a bevel gear: right-angle stages are built in phase W6.``"""
    what, phase = LATER[gear.kind_word()]
    return f"{gear.id} is {what}: {phase}."


def later_rows(spec: GearboxSpec) -> List[Diagnostic]:
    """Every row a later phase builds, each a warning naming its cell, the row and the phase that builds it.

    Shafts first, as they decide the most: a carrier or a turned axis means no
    gearbox check runs at all yet (:func:`checks.check` stops at the layout).
    Then the gears whose own part waits (bevel, sleeve, dog), the gears that
    slide, and the modes.
    """
    out: List[Diagnostic] = []

    def refuse(where: str, sentence: str) -> None:
        out.append(Diagnostic(WARNING, f"{where}: {sentence}", where))

    for shaft in spec.shafts:
        where = spec.cell("Shafts", shaft.row, "id")
        if shaft.mount() != FRAME:
            copies = shaft.copies.strip()
            if copies and copies != "1":
                refuse(where, f"{shaft.id} is mounted on {shaft.mount()}, with {copies} copies round it: carriers "
                              "and copies are laid out in phase W7, and the gearbox is not checked until then.")
            else:
                refuse(where, f"{shaft.id} is mounted on {shaft.mount()}: carriers are laid out in phase W7, and "
                              "the gearbox is not checked until then.")
        elif (shaft.axis or "Z+") not in AXES:
            refuse(where, f"{shaft.id}'s axis is {shaft.axis}: turned axes are laid out in phase W6, and the "
                          "gearbox is not checked until then.")
    for gear in spec.gears:
        where = spec.cell("Gears", gear.row, "id")
        if gear.kind_word() in LATER:
            refuse(where, _later_kind(gear))
        elif gear.slides.strip():
            refuse(where, f"{gear.id} slides: sliding gears are placed in phase W8, with modes, and it is checked "
                          "only at its At until then.")
    if spec.modes:
        names = [m.name for m in spec.modes]
        listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
        one = len(names) == 1
        refuse(spec.cell("Modes", spec.modes[0].row, "name"),
               f"{listed} {'is a mode: it becomes' if one else 'are modes: they become'} the assembly's "
               f"configuration{'' if one else 's'} in phase W8.")
    return out


def gear_diagnostics(spec: GearboxSpec, skip_rows=()) -> List[Diagnostic]:
    """Every row's own checks, for the window to show as the file changes — no plans are made."""
    out: List[Diagnostic] = []
    for gear in spec.gears:
        if gear.kind_word() in LATER or gear.row in skip_rows:
            continue
        out.extend(check_gear(spec, gear)[2])
    return out
