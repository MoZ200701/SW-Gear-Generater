"""Writing back to the workbook: the fixes chosen in the app, and the Results sheet (PLAN-WORKBOOK §2, §5; W3).

Only on Export, only the cells a fix names, and never over a formula
(:func:`xlsx.write_cells` refuses those and they come back to be listed). A fix
may name a column the sheet does not have — columns are optional, so a
workbook without Profile shift is ordinary — and Export then writes that
column's header at the end of row 1 first. A cell formatted as a percentage
gets a fraction (0.97 for 97), as Excel holds one.

The Results sheet is the app's own and is replaced whole each time; the reader
never reads it. Whatever else is in the workbook is left exactly as it was.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import checks, geometry, schema, xlsx
from .checks import Report
from .fixes import Fix
from .model import GearboxSpec, from_book as model_from_book
from .xlsx import NewSheet, make_ref

SHEET_DEFS = {"Shafts": schema.SHAFTS, "Gears": schema.GEARS, "Meshes": schema.MESHES}
RESULTS_RATIO = "Overall ratio (input speed ÷ output speed)"
RESULTS_BOX = "Box size, over the gears' outside diameters (X, Y) and faces (Z)"


@dataclass
class Exported:
    path: str = ""
    written: List[str] = field(default_factory=list)
    refused: List[Tuple[str, str]] = field(default_factory=list)    # (cell, why) — formulas, mostly
    added_headers: List[str] = field(default_factory=list)
    digest: str = ""                       # the file as written, so the live link knows its own write
    has_formulas: bool = False             # Excel must recalculate and save before the values can be trusted
    results: bool = False                  # the Results sheet was written (not when a cell was refused)


def results_sheet(spec: GearboxSpec, report: Report, when: Optional[str] = None) -> NewSheet:
    """The Results sheet: speeds, turning, torque per shaft; ratio, centres and contact ratio per mesh; what the
    box was worked out as, its overall ratio, and the room its gears take (:func:`geometry.extent`)."""
    when = when or time.strftime("%Y-%m-%d %H:%M")
    motion = report.motion
    rows: List[List] = [["Shaft", "Speed (rpm)", "Turns, seen from +Z", "Torque (N·m)"]]
    for shaft in spec.shafts:
        speed = motion.speeds.get(shaft.id)
        torque = motion.torques.get(shaft.id)
        rows.append([shaft.id, round(float(speed), 6) if speed is not None else "—", motion.turns(shaft.id) or "—",
                     round(torque, 6) if torque is not None else "—"])
    rows.append([])
    rows.append(["Mesh", "Ratio", "Centres needed (mm)", "Centres placed (mm)", "Off by (mm)", "Contact ratio"])
    gears = {g.id: g for g in spec.gears}
    for (a, b), (needed, placed) in report.centres.items():
        ratio = float(gears[b].teeth) / float(gears[a].teeth)
        rows.append([f"{a}–{b}", round(ratio, 6), round(needed, 6), round(placed, 6), round(placed - needed, 6),
                     round(report.contact.get((a, b), 0.0), 4)])
    rows.append([])
    rows.append(["Overall", "Value"])
    rows.append(["Worked out as", report.worked_out_as or "—"])
    ratio = checks.overall_ratio(spec, motion)
    rows.append([RESULTS_RATIO, round(ratio, 6) if ratio is not None else "—"])
    rows.append([])
    rows.append([RESULTS_BOX, "Size (mm)", "From (mm)", "To (mm)"])
    box = geometry.extent(report.layout.placed)
    for axis, span in zip("XYZ", box or ((None, None),) * 3):
        lo, hi = span
        rows.append([axis] + ([round(hi - lo, 6), round(lo, 6), round(hi, 6)] if lo is not None else ["—"] * 3))
    note = schema.RESULTS_NOTE.format(when=when)
    return NewSheet(schema.RESULTS, rows, header=False, note=note)


def _value(column: Optional[schema.Column], text: str, percent: bool):
    """A model value as a cell value: numbers as numbers (a fraction in a percentage cell), text as text."""
    if column is not None and column.numeric and text:
        try:
            value = float(text)
        except ValueError:
            return text
        if percent:
            return value / 100.0
        return int(value) if value == int(value) and abs(value) < 1e15 else value
    return text


def export(path: str, spec: GearboxSpec, chosen: Sequence[Fix], report: Optional[Report],
           out_path: str = "", expected_digest: str = "") -> Exported:
    """Write the chosen fixes' cells and the Results sheet into ``path`` (or a copy at ``out_path``).

    Each edit names a shaft or gear, and its row is found in the file as it is
    now, so rows inserted or sorted since the fix was chosen do not misdirect
    it. ``expected_digest`` is the file as the window last read it: a save in
    Excel since then (inside the one-second poll) is refused rather than
    written over. If any cell is refused (a formula), the Results sheet is not
    written: the fix is then only partly in the workbook, and Results would
    describe a gearbox the file does not hold.
    """
    with open(path, "rb") as handle:
        data = handle.read()
    if expected_digest and hashlib.sha256(data).hexdigest() != expected_digest:
        raise xlsx.XlsxError("The workbook changed since it was last read, so nothing was written; it is read "
                             "again now. Choose the fix again if it still applies.")
    book = xlsx.read_bytes(data, path)
    current, _ = model_from_book(book)
    rows = {("Shafts", s.id): s.row for s in current.shafts}
    rows.update({("Gears", g.id): g.row for g in current.gears})
    changes: Dict[str, Dict[str, object]] = {}
    out = Exported(path=out_path or path)
    for fix in chosen:
        for edit in fix.edits:
            sheet = book.sheet(edit.sheet)
            sheet_def = SHEET_DEFS[edit.sheet]
            column = sheet_def.column(edit.key)
            row = rows.get((edit.sheet, edit.item))
            if sheet is None or row is None:
                out.refused.append((f"{edit.sheet} {edit.item}", f"{edit.item} is no longer on the {edit.sheet} "
                                                                 "sheet"))
                continue
            headers = {col: cell.text for (r, col), cell in sheet.cells.items() if r == 1 and cell.text}
            found, _, _ = schema.match_headers(sheet_def, headers)
            col = found.get(edit.key)
            cells = changes.setdefault(sheet.name, {})
            if col is None:
                # The column is optional and this workbook has none: add its header after the last one.
                col = max([sheet.max_col()] + [xlsx.split_ref(r)[1] for r in cells]) + 1
                cells[make_ref(1, col)] = column.title
                out.added_headers.append(f"{sheet.name}!{make_ref(1, col)} {column.title}")
                sheet.cells[(1, col)] = xlsx.Cell(make_ref(1, col), 1, col, column.title)
            existing = sheet.cell(row, col)
            cells[make_ref(row, col)] = _value(column, edit.value, bool(existing and existing.percent))
    written = xlsx.write_cells(path, changes, out_path=out_path)
    out.written, out.refused = written.written, out.refused + written.refused
    if report is not None and not out.refused:
        target = out_path or path
        xlsx.write_cells(target, {}, replace_sheets=[results_sheet(spec, report)])
        out.results = True
    target = out_path or path
    with open(target, "rb") as handle:
        out.digest = hashlib.sha256(handle.read()).hexdigest()
    out.has_formulas = any(cell.formula for name, sheet in book.sheets.items() if name != schema.RESULTS
                           for cell in sheet.cells.values())
    return out
