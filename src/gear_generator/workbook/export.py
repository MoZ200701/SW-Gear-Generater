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

from . import schema, xlsx
from .checks import Report
from .fixes import Fix
from .model import GearboxSpec
from .xlsx import NewSheet, make_ref

SHEET_DEFS = {"Shafts": schema.SHAFTS, "Gears": schema.GEARS, "Meshes": schema.MESHES}


@dataclass
class Exported:
    path: str = ""
    written: List[str] = field(default_factory=list)
    refused: List[Tuple[str, str]] = field(default_factory=list)    # (cell, why) — formulas, mostly
    added_headers: List[str] = field(default_factory=list)
    digest: str = ""                       # the file as written, so the live link knows its own write
    has_formulas: bool = False             # Excel must recalculate and save before the values can be trusted


def results_sheet(spec: GearboxSpec, report: Report, when: Optional[str] = None) -> NewSheet:
    """The Results sheet: speeds, turning, torque per shaft; ratio, centres and contact ratio per mesh."""
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
    rows.append(["Overall", report.worked_out_as])
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
           out_path: str = "") -> Exported:
    """Write the chosen fixes' cells and the Results sheet into ``path`` (or a copy at ``out_path``)."""
    book = xlsx.read(path)
    changes: Dict[str, Dict[str, object]] = {}
    out = Exported(path=out_path or path)
    for fix in chosen:
        for edit in fix.edits:
            sheet = book.sheet(edit.sheet)
            sheet_def = SHEET_DEFS[edit.sheet]
            column = sheet_def.column(edit.key)
            if sheet is None:
                out.refused.append((f"{edit.sheet}!{edit.row}", f"there is no {edit.sheet} sheet"))
                continue
            headers = {col: cell.text for (row, col), cell in sheet.cells.items() if row == 1 and cell.text}
            found, _, _ = schema.match_headers(sheet_def, headers)
            col = found.get(edit.key)
            cells = changes.setdefault(sheet.name, {})
            if col is None:
                # The column is optional and this workbook has none: add its header after the last one.
                col = max([sheet.max_col()] + [xlsx.split_ref(r)[1] for r in cells]) + 1
                cells[make_ref(1, col)] = column.title
                out.added_headers.append(f"{sheet.name}!{make_ref(1, col)} {column.title}")
                sheet.cells[(1, col)] = xlsx.Cell(make_ref(1, col), 1, col, column.title)
            existing = sheet.cell(edit.row, col)
            cells[make_ref(edit.row, col)] = _value(column, edit.value, bool(existing and existing.percent))
    replace = [results_sheet(spec, report)] if report is not None else []
    written = xlsx.write_cells(path, changes, replace_sheets=replace, out_path=out_path)
    out.written, out.refused = written.written, out.refused + written.refused
    target = out_path or path
    with open(target, "rb") as handle:
        out.digest = hashlib.sha256(handle.read()).hexdigest()
    out.has_formulas = any(cell.formula for name, sheet in book.sheets.items() if name != schema.RESULTS
                           for cell in sheet.cells.values())
    return out
