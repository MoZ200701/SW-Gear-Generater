"""Staying linked to a workbook after import (docs/PLAN-WORKBOOK.md §5, the live link).

The window asks :meth:`Link.poll` once a second. A save in Excel changes the
file's size or modification time; the link then reads it again, and says what
changed since the last read, cell by cell (:func:`describe_changes`), and what
that did to the checks (:func:`consequence`). Excel saves by writing a new file
and replacing the old one, so for a moment the workbook may be half-written or
missing: that is "not ready", retried quietly for up to five seconds before it
becomes a sentence the window shows.

Nothing here touches Tk or COM, so all of it is tested headless with a fake clock.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..gears.base import Diagnostic
from . import schema, xlsx
from .checks import CENTRE_TOLERANCE, Report
from .model import GearboxSpec, from_book

RETRY_SECONDS = 5.0


@dataclass
class Reading:
    """One read of the file: the gearbox (or why there is none), its diagnostics, and what changed."""

    spec: Optional[GearboxSpec] = None
    diagnostics: List[Diagnostic] = field(default_factory=list)
    changes: List[str] = field(default_factory=list)
    error: str = ""
    digest: str = ""
    own: bool = False          # the file is what the app itself last wrote (Export, W3)

    @property
    def ok(self) -> bool:
        return self.spec is not None and not self.error


class Link:
    def __init__(self, path: str, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self.clock = clock
        self.spec: Optional[GearboxSpec] = None
        self.digest = ""
        self.own_digest = ""
        self._stamp: Optional[Tuple[int, int]] = None
        self._waiting_since: Optional[float] = None
        self._gone_said = False        # "no longer at" has been said, and is not said again until it comes back

    # -- reading

    def _stat(self) -> Optional[Tuple[int, int]]:
        try:
            info = os.stat(self.path)
        except OSError:
            return None
        return info.st_size, info.st_mtime_ns

    def read(self) -> Reading:
        """Read the file now. Raises :class:`xlsx.NotReady` when it is mid-save; the caller decides to wait."""
        stamp = self._stat()
        try:
            with open(self.path, "rb") as handle:
                data = handle.read()
        except FileNotFoundError:
            raise xlsx.NotReady(f"The workbook is not at {self.path} right now.") from None
        except PermissionError:
            raise xlsx.NotReady(f"{os.path.basename(self.path)} cannot be opened right now.") from None
        digest = hashlib.sha256(data).hexdigest()
        try:
            book = xlsx.read_bytes(data, self.path)
        except xlsx.NotReady:
            raise
        except xlsx.XlsxError as exc:
            self._stamp, self.digest = stamp, digest
            return Reading(error=str(exc), digest=digest)
        spec, diagnostics = from_book(book)
        changes = describe_changes(self.spec, spec) if self.spec is not None else []
        self.spec, self.digest, self._stamp = spec, digest, stamp
        return Reading(spec, diagnostics, changes, digest=digest, own=bool(self.own_digest) and digest == self.own_digest)

    def poll(self) -> Optional[Reading]:
        """A new :class:`Reading` when the file has changed and can be read, else None.

        A file caught mid-save, or briefly missing while Excel replaces it, is
        tried again on the next poll; only after :data:`RETRY_SECONDS` of that
        does it come back as a reading with an error.
        """
        stamp = self._stat()
        if stamp is None and self._gone_said:
            return None
        if stamp is not None:
            self._gone_said = False
        if stamp is not None and stamp == self._stamp and self._waiting_since is None:
            return None
        try:
            reading = self.read()
        except xlsx.NotReady as exc:
            now = self.clock()
            if self._waiting_since is None:
                self._waiting_since = now
            if now - self._waiting_since < RETRY_SECONDS:
                return None
            self._waiting_since = None
            self._stamp = stamp
            missing = stamp is None
            self._gone_said = missing
            message = (f"The workbook is no longer at {self.path}." if missing
                       else f"{exc} It has not settled for {RETRY_SECONDS:g} seconds.")
            return Reading(error=message)
        self._waiting_since = None
        return reading

    @property
    def open_in_excel(self) -> bool:
        return xlsx.is_open_in_excel(self.path)


# ------------------------------------------------------------------ what changed


def _value(text: str) -> str:
    return text if text != "" else "blank"


def renamed(old, new) -> Dict[str, str]:
    """Rows whose name changed and nothing else about where they are: old name -> new name.

    A row is taken as renamed when the name it had is gone from the sheet and
    the name now on its row is new to it — G4 typed over as G4b, or cleared.
    Inserting a row above it is not a rename: the name it pushed down is still
    there."""
    old_ids = {item.id for item in old}
    new_ids = {item.id for item in new}
    old_at = {item.row: item.id for item in old}
    out: Dict[str, str] = {}
    for item in new:
        was = old_at.get(item.row)
        if was is not None and was != item.id and was not in new_ids and item.id not in old_ids:
            out[was] = item.id
    return out


def _rows_changed(sheet: str, sheet_def: schema.SheetDef, old, new, spec: GearboxSpec, noun: str) -> List[str]:
    out: List[str] = []
    names = renamed(old, new)
    old_by = {names.get(item.id, item.id): item for item in old}
    new_by = {item.id: item for item in new}
    for item in new:
        before = old_by.get(item.id)
        if before is None:
            out.append(f"{noun} {item.id} added ({sheet} row {item.row})")
            continue
        for column in sheet_def.columns:
            a, b = getattr(before, column.key), getattr(item, column.key)
            if a != b:
                out.append(f"{spec.cell(sheet, item.row, column.key)} {item.id or before.id} {column.header} "
                           f"{_value(a)} → {_value(b)}")
    for item in old:
        if names.get(item.id, item.id) not in new_by:
            out.append(f"{noun} {item.id} removed")
    return out


def describe_changes(old: Optional[GearboxSpec], new: GearboxSpec) -> List[str]:
    """What changed between two reads, one line per cell: ``Gears!F3 G2 Teeth 68 → 70``."""
    if old is None:
        return []
    out: List[str] = []
    for setting in schema.BOX_SETTINGS:
        if setting.key == "units":
            continue
        a, b = getattr(old.box, setting.key, ""), getattr(new.box, setting.key, "")
        if a != b:
            out.append(f"Box {setting.name} {_value(a)} → {_value(b)}")
    out += _rows_changed("Shafts", schema.SHAFTS, old.shafts, new.shafts, new, "shaft")
    out += _rows_changed("Gears", schema.GEARS, old.gears, new.gears, new, "gear")

    def pair(mesh) -> frozenset:
        return frozenset((mesh.a, mesh.b))

    old_meshes: Dict[frozenset, object] = {pair(m): m for m in old.meshes}
    new_meshes: Dict[frozenset, object] = {pair(m): m for m in new.meshes}
    for key, mesh in new_meshes.items():
        before = old_meshes.get(key)
        if before is None:
            out.append(f"mesh {mesh.a}–{mesh.b} added (Meshes row {mesh.row})")
        elif before.efficiency != mesh.efficiency:
            out.append(f"{new.cell('Meshes', mesh.row, 'efficiency')} {mesh.a}–{mesh.b} Efficiency "
                       f"{_value(before.efficiency)} → {_value(mesh.efficiency)}")
    for key, mesh in old_meshes.items():
        if key not in new_meshes:
            out.append(f"mesh {mesh.a}–{mesh.b} removed")

    old_modes = {m.name: m for m in old.modes}
    new_modes = {m.name: m for m in new.modes}
    for name, mode in new_modes.items():
        before = old_modes.get(name)
        if before is None:
            out.append(f"mode {name} added (Modes row {mode.row})")
        elif dict(before.positions) != dict(mode.positions):
            picks = ", ".join(f"{s} {p or 'blank'}" for s, p in mode.positions
                              if dict(before.positions).get(s) != p)
            out.append(f"mode {name}: {picks}")
    for name in old_modes:
        if name not in new_modes:
            out.append(f"mode {name} removed")
    return out


# ------------------------------------------------------------------ what that did


@dataclass
class Consequence:
    """What a save did to the checks: the one line after the changed cells (PLAN-WORKBOOK §5,
    *Gears!F3 Teeth 68 → 70 · G1–G2 now 1.50 off*). The Checks panel has the full sentences; this names
    only what is new or gone. Each problem is listed by the cell it names now (a cleared one by the cell it
    named), once per problem."""

    meshes: List[Tuple[str, str, Optional[float]]] = field(default_factory=list)   # (a, b, mm off now; None: on centres)
    new_errors: List[str] = field(default_factory=list)
    new_warnings: List[str] = field(default_factory=list)
    cleared: List[str] = field(default_factory=list)       # problems gone, from items that now have none

    def __bool__(self) -> bool:
        return bool(self.meshes or self.new_errors or self.new_warnings or self.cleared)


# A number standing alone (64.25, +0.25, −375), not one inside a name or a cell (G1, Gears!F3).
_NUMBER = re.compile(r"(?<![\w.])[-+−]?\d+(?:\.\d+)?(?![\w.])")
# A cell or a row a message names: Gears!F3, Gears!$F$3, Shafts row 4, Shafts rows 2 and 3.
_CELL = re.compile(r"\b[A-Z][A-Za-z]*!\$?[A-Z]{1,3}\$?\d+\b|\b[A-Z][A-Za-z]* rows? \d+(?: and \d+)?")
_FIELD = re.compile(r"^([A-Za-z]+)(?:!\$?([A-Z]{1,3})\$?(\d+)| row (\d+))$")


def _where(spec: GearboxSpec, place: str, names: Optional[Dict[str, str]] = None) -> Tuple[str, ...]:
    """A diagnostic's cell as what it is about, so moving rows does not move it: ``Gears!F3`` on G2's row is
    ``("Gears", "G2", "teeth")``. A sheet-level field (``Meshes``), or a row that names nothing, stays as it is."""
    match = _FIELD.match(place or "")
    if not match:
        return (place,)
    sheet, letters, row = match.group(1), match.group(2), int(match.group(3) or match.group(4))
    items = {"Shafts": [(s.row, s.id) for s in spec.shafts], "Gears": [(g.row, g.id) for g in spec.gears],
             "Meshes": [(m.row, f"{m.a}–{m.b}") for m in spec.meshes], "Modes": [(m.row, m.name) for m in spec.modes]}
    item = next((name for r, name in items.get(sheet, []) if r == row), None)
    if item is None:
        return (place,)
    if names:
        item = names.get(item, item) if sheet != "Meshes" else "–".join(names.get(g, g) for g in item.split("–"))
    if letters is None:
        return sheet, item, ""
    column = xlsx.column_index(letters)
    key = next((k for k, c in spec.columns.get(sheet, {}).items() if c == column), letters)
    return sheet, item, key


def _problem(spec: GearboxSpec, d: Diagnostic, names: Optional[Dict[str, str]] = None) -> Tuple:
    """A problem as the same problem however its row or its numbers moved: G2's teeth from 68.5 to 68.7 is
    still the one error on G2's Teeth, and so is it after a row was inserted above G2's. ``names`` maps an
    old read's renamed rows to their new names, so G4's bore error is G4b's once G4 is renamed G4b."""
    message = d.message
    for was, now in (names or {}).items():
        if was:
            message = re.sub(rf"(?<![\w-]){re.escape(was)}(?![\w-])", now, message)
    return d.level, _where(spec, d.field, names), _NUMBER.sub("#", _CELL.sub("@", message))


def _off_by(report: Optional[Report]) -> Dict[frozenset, Tuple[str, str, float]]:
    if report is None:
        return {}
    return {frozenset(pair): (pair[0], pair[1], placed - needed) for pair, (needed, placed) in report.centres.items()}


def consequence(before, after) -> Consequence:
    """What the checks say after a save that they did not before, and what they no longer say.

    ``before`` and ``after`` are each read worked through by
    :func:`workbook.assess.assess` *without* the chosen fixes — the file as it
    is, as the cell list reads it. A mesh that moved off its centres, or back
    onto them, or by more than the tolerance while off, is said as its
    distance; that mesh's own "not where the teeth put them" error is then not
    said twice. Problems are matched by the item and column they are about, not
    by their cell, so inserting, deleting or sorting rows does not make them new.
    """
    out = Consequence()
    old_off, new_off = _off_by(before.report), _off_by(after.report)
    for key, (a, b, off) in new_off.items():
        was = old_off.get(key)
        now_off = abs(off) > CENTRE_TOLERANCE
        if was is None:
            moved = now_off
        else:
            moved = abs(off - was[2]) > CENTRE_TOLERANCE and (now_off or abs(was[2]) > CENTRE_TOLERANCE)
        if moved:
            out.meshes.append((a, b, abs(off) if now_off else None))
    said = list(before.report.off_centre) + list(after.report.off_centre)
    names = {**renamed(before.read.shafts, after.read.shafts), **renamed(before.read.gears, after.read.gears)}
    old = [(d, _problem(before.read, d, names)) for d in before.diagnostics if d not in said]
    new = [(d, _problem(after.read, d)) for d in after.diagnostics if d not in said]
    old_keys = {key for _, key in old}
    new_keys = {key for _, key in new}
    seen = set()
    for d, key in new:
        if key in old_keys or key in seen:
            continue
        seen.add(key)
        (out.new_errors if d.is_error else out.new_warnings).append(d.field)
    still = {_where(after.read, d.field) for d in after.diagnostics}
    for d, key in old:
        if key in new_keys or key in seen or key[1] in still:
            continue
        seen.add(key)
        out.cleared.append(d.field)
    return out


def covered_by_fix(consequence: Optional[Consequence], effective: Optional[Report]) -> List[Tuple[str, str]]:
    """The meshes the change list says are off that the chosen fixes put back on centres (``effective`` is the
    report with them made), so the line can say the fix covers them."""
    if not consequence or effective is None:
        return []
    now = _off_by(effective)
    out = []
    for a, b, off in consequence.meshes:
        fixed = now.get(frozenset((a, b)))
        if off is not None and fixed is not None and abs(fixed[2]) <= CENTRE_TOLERANCE:
            out.append((a, b))
    return out
