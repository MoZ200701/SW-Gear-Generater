"""Staying linked to a workbook after import (docs/PLAN-WORKBOOK.md §5, the live link).

The window asks :meth:`Link.poll` once a second. A save in Excel changes the
file's size or modification time; the link then reads it again, checks it,
and says what changed since the last read, cell by cell. Excel saves by
writing a new file and replacing the old one, so for a moment the workbook may
be half-written or missing: that is "not ready", retried quietly for up to
five seconds before it becomes a sentence the window shows.

Nothing here touches Tk or COM, so all of it is tested headless with a fake clock.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..gears.base import Diagnostic
from . import schema, xlsx
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


def _rows_changed(sheet: str, sheet_def: schema.SheetDef, old, new, spec: GearboxSpec, noun: str) -> List[str]:
    out: List[str] = []
    old_by = {item.id: item for item in old}
    new_by = {item.id: item for item in new}
    for item in new:
        before = old_by.get(item.id)
        if before is None:
            out.append(f"{noun} {item.id} added ({sheet} row {item.row})")
            continue
        for column in sheet_def.columns:
            if column.key == "id":
                continue
            a, b = getattr(before, column.key), getattr(item, column.key)
            if a != b:
                out.append(f"{spec.cell(sheet, item.row, column.key)} {item.id} {column.header} "
                           f"{_value(a)} → {_value(b)}")
    for item in old:
        if item.id not in new_by:
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
