"""The gearbox as data, read from a workbook and written back (docs/PLAN-WORKBOOK.md §3.2).

Like :mod:`gear_generator.spec`, every value is kept as the text the user
typed: ``""`` is a blank cell, which means the column's default, and is not
``"0"``. Words are kept in their canonical form (``ext`` is stored as
``external``), so the model compares equal however a row was typed.

:func:`from_book` never raises on a bad cell. It reads what it can and returns
a diagnostic for every cell it could not use, each naming the cell —
``Gears!F4`` — so the window can say exactly where to look.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ..gears.base import ERROR, WARNING, Diagnostic
from ..spec import GearSpec
from . import schema
from .schema import FRAME, NAME_PATTERN, Column, SheetDef
from .xlsx import Book, Cell, NewSheet, Sheet, make_ref, number_text


@dataclass(frozen=True)
class Box:
    name: str = ""
    output_folder: str = ""
    part_template: str = ""
    assembly_template: str = ""
    pressure_angle: str = ""
    efficiency: str = ""
    format: str = schema.FORMAT

    def pressure_angle_text(self) -> str:
        return self.pressure_angle.strip() or "20"

    def efficiency_text(self) -> str:
        return self.efficiency.strip() or "98"


@dataclass(frozen=True)
class Shaft:
    id: str
    mounted_on: str = ""
    x: str = ""
    y: str = ""
    z: str = ""
    axis: str = ""
    role: str = ""
    copies: str = ""
    speed: str = ""
    torque: str = ""
    notes: str = ""
    row: int = 0

    def mount(self) -> str:
        """The shaft this one rides on, or ``frame`` — however ``Frame`` was typed."""
        text = self.mounted_on.strip()
        return FRAME if not text or text.lower() == FRAME else text


@dataclass(frozen=True)
class Gear:
    id: str
    shaft: str = ""
    at: str = ""
    kind: str = ""
    side: str = ""
    teeth: str = ""
    module: str = ""
    pressure_angle: str = ""
    face_width: str = ""
    bore: str = ""
    flank: str = ""
    helix_angle: str = ""
    hand: str = ""
    groove: str = ""
    profile_shift: str = ""
    backlash: str = ""
    fillet: str = ""
    rim: str = ""
    slides: str = ""
    part_name: str = ""
    notes: str = ""
    row: int = 0

    def kind_word(self) -> str:
        return self.kind or "spur"

    def gear_spec(self, box: Box) -> GearSpec:
        """The strip's form for this gear, every field set explicitly.

        A blank optional cell takes the workbook's default, never
        ``GearSpec()``'s: a blank Bore is no bore, not ``GearSpec``'s 10 mm.
        :meth:`spec_values` names every field, and a test holds it to
        ``fields(GearSpec)``, so a field added later cannot fall back unseen.
        """
        return GearSpec(**self.spec_values(box))

    def spec_values(self, box: Box) -> Dict[str, str]:
        return dict(
            kind=self.kind_word(),
            recipe=schema.FLANK_RECIPE.get(self.flank, ""),
            module=self.module,
            teeth=self.teeth,
            pressure_angle=self.pressure_angle or box.pressure_angle_text(),
            face_width=self.face_width,
            bore=self.bore,
            backlash=self.backlash,
            fillet=self.fillet,
            profile_shift=self.profile_shift or "0",
            helix_angle=self.helix_angle,
            hand=self.hand or "right",
            groove=self.groove,
            teeth_side=self.side or "external",
            rim=self.rim,
            shaft_angle="90",
            mate_teeth="",
            name=self.part_name,
        )

    def positions(self) -> Dict[str, float]:
        """``H=-10, N=0, L=+10`` -> {name: offset}. Raises ValueError with a sentence if it does not read."""
        return parse_slides(self.slides)


@dataclass(frozen=True)
class Mesh:
    a: str
    b: str
    efficiency: str = ""
    notes: str = ""
    row: int = 0


@dataclass(frozen=True)
class Mode:
    name: str
    positions: Tuple[Tuple[str, str], ...] = ()     # (sliding gear, position name), in column order
    notes: str = ""
    row: int = 0


@dataclass(frozen=True)
class GearboxSpec:
    box: Box = field(default_factory=Box)
    shafts: Tuple[Shaft, ...] = ()
    gears: Tuple[Gear, ...] = ()
    meshes: Tuple[Mesh, ...] = ()
    modes: Tuple[Mode, ...] = ()
    sliders: Tuple[str, ...] = ()                   # the Modes sheet's middle columns, in order
    source_path: str = ""
    # Where each column was found, sheet -> key -> column number, so a later check names the right cell.
    # Not part of what the gearbox *is*: two reads with columns in another order compare equal.
    columns: Mapping[str, Mapping[str, int]] = field(default_factory=dict, compare=False, hash=False)

    def cell(self, sheet: str, row: int, key: str) -> str:
        """``Gears!F3`` for a key on a row, or ``Gears row 3`` when the column is not in the workbook."""
        col = self.columns.get(sheet, {}).get(key)
        return f"{sheet}!{make_ref(row, col)}" if col and row else f"{sheet} row {row}"

    def shaft(self, name: str) -> Optional[Shaft]:
        return next((s for s in self.shafts if s.id == name), None)

    def gear(self, name: str) -> Optional[Gear]:
        return next((g for g in self.gears if g.id == name), None)

    def without_rows(self) -> "GearboxSpec":
        """The same gearbox with every row number zeroed and no source: what two reads compare on."""
        return replace(self, source_path="", columns={},
                       shafts=tuple(replace(s, row=0) for s in self.shafts),
                       gears=tuple(replace(g, row=0) for g in self.gears),
                       meshes=tuple(replace(m, row=0) for m in self.meshes),
                       modes=tuple(replace(m, row=0) for m in self.modes))


_SLIDE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=\s*([+-]?\d+(?:\.\d+)?)\s*$")


def parse_slides(text: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not text.strip():
        return out
    for piece in text.replace(";", ",").split(","):
        if not piece.strip():
            continue
        match = _SLIDE.match(piece.replace("−", "-"))
        if not match:
            raise ValueError(f"{piece.strip()!r} is not a position; write each as name=offset, e.g. H=-10, N=0, L=+10.")
        name = match.group(1)
        if name in out:
            raise ValueError(f"The position {name} is named twice.")
        out[name] = float(match.group(2))
    return out


# ------------------------------------------------------------------ reading


class _Reader:
    def __init__(self) -> None:
        self.diagnostics: List[Diagnostic] = []
        self.columns: Dict[str, Dict[str, int]] = {}    # sheet -> key -> the column it was found in
        self.slider_columns: Dict[str, int] = {}

    def at(self, sheet: str, row: int, key: str) -> str:
        """The cell a key's value came from on a row, or just the row when the column is absent."""
        col = self.columns.get(sheet, {}).get(key)
        return f"{sheet}!{make_ref(row, col)}" if col and row else f"{sheet} row {row}"

    def error(self, where: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(ERROR, f"{where}: {message}", where))

    def warning(self, where: str, message: str) -> None:
        self.diagnostics.append(Diagnostic(WARNING, f"{where}: {message}", where))


def _cell_text(reader: _Reader, sheet: Sheet, cell: Optional[Cell], column: Optional[Column]) -> str:
    if cell is None:
        return ""
    where = f"{sheet.name}!{cell.ref}"
    if cell.error:
        if cell.error == "#NOVALUE":
            reader.error(where, "this formula has no saved value; open the workbook in Excel and save it.")
        elif column is not None and column.key == "axis" and cell.error.upper() == "#NAME?":
            reader.error(where, "shows #NAME? — Excel reads a typed +Z or -Z as a formula. Pick Z+ or Z- from "
                                "the list, or type Z+.")
        else:
            reader.error(where, f"shows {cell.error}; it needs a value.")
        return ""
    return cell.text.strip()


def _check_value(reader: _Reader, where: str, column: Column, text: str, percent: bool = False) -> str:
    """The value as the model keeps it: a canonical word, a number as typed, or "" after a diagnostic."""
    if not text:
        return ""
    if column.key == "axis":
        word = column.canonical(text)
        if word is not None:
            return word
        parts = [p for p in re.split(r"[,\s;]+", text) if p]
        try:
            values = [float(p.replace("−", "-")) for p in parts]
        except ValueError:
            values = []
        if len(values) == 3 and math.isfinite(sum(values)) and math.hypot(*values) > 1e-9:
            return ", ".join(number_text(repr(v)) for v in values)
        reader.error(where, f"Axis must be Z+, Z-, X+, X-, Y+, Y- or three numbers (got {text!r}).")
        return ""
    if column.words:
        word = column.canonical(text)
        if word is None:
            reader.error(where, f"{column.header} must be {', '.join(column.words)} (got {text!r}).")
            return ""
        return word
    if column.numeric:
        try:
            value = float(text.replace("−", "-"))
        except ValueError:
            reader.error(where, f"{column.header} must be a number (got {text!r}).")
            return ""
        if not math.isfinite(value):
            reader.error(where, f"{column.header} must be a finite number (got {text!r}).")
            return ""
        if column.whole and abs(value - round(value)) > 1e-9:
            reader.error(where, f"{column.header} must be a whole number (got {text!r}).")
            return ""
        if column.key == "efficiency":
            # A cell formatted as a percentage holds 0.98 for 98 %. Unformatted, a value under 1 is read the
            # same way: an efficiency of 0.98 % is not one anybody means.
            if percent or 0 < value < 1:
                value *= 100.0
            if not 0 < value <= 100:
                reader.error(where, f"Efficiency must be more than 0 and at most 100 % (got {text!r}).")
                return ""
            return number_text(repr(value))
        return number_text(text.replace("−", "-"))
    return text


def _table(reader: _Reader, sheet: Sheet, sheet_def: SheetDef) -> List[Tuple[int, Dict[str, str]]]:
    """Each data row as {key: value}, with its row number; comment and blank rows skipped."""
    headers = {col: cell.text for (row, col), cell in sheet.cells.items() if row == 1 and cell.text}
    found, _unknown, problems = schema.match_headers(sheet_def, headers)
    for col, message in problems:
        reader.error(f"{sheet.name}!{make_ref(1, col)}", message)
    reader.columns[sheet_def.name] = found
    for column in sheet_def.columns:
        if column.required and column.key not in found:
            reader.error(f"{sheet.name}!1", f"the {column.title} column is missing.")
    rows = []
    for row in range(2, sheet.max_row() + 1):
        first = sheet.cell(row, 1)
        if first is not None and first.text.lstrip().startswith("#"):
            continue
        values: Dict[str, str] = {}
        reported = set()             # keys already given a diagnostic on this row: one message per cell
        for column in sheet_def.columns:
            col = found.get(column.key)
            cell = sheet.cell(row, col) if col else None
            before = len(reader.diagnostics)
            text = _cell_text(reader, sheet, cell, column)
            where = f"{sheet.name}!{make_ref(row, col)}" if col else f"{sheet.name}!{row}"
            values[column.key] = _check_value(reader, where, column, text, bool(cell and cell.percent))
            if len(reader.diagnostics) > before:
                reported.add(column.key)
        if not any(v for k, v in values.items() if k != "notes"):
            continue
        for column in sheet_def.columns:
            col = found.get(column.key)
            if column.required and col and not values[column.key] and column.key not in reported:
                reader.error(f"{sheet.name}!{make_ref(row, col)}", f"{column.title} is needed.")
        rows.append((row, values))
    return rows


def _read_box(reader: _Reader, sheet: Optional[Sheet]) -> Box:
    if sheet is None:
        reader.error("Box", "the workbook has no Box sheet.")
        return Box()
    settings = {schema.header_key(s.name): s for s in schema.BOX_SETTINGS}
    values: Dict[str, str] = {}
    rows: Dict[str, int] = {}
    for row in range(2, sheet.max_row() + 1):
        label = sheet.cell(row, 1)
        if label is None or label.text.lstrip().startswith("#"):
            continue
        setting = settings.get(schema.header_key(label.text))
        if setting is None:
            continue
        where = f"Box!{make_ref(row, 2)}"
        value_cell = sheet.cell(row, 2)
        text = _cell_text(reader, sheet, value_cell, None)
        if setting.numeric and text:
            column = Column(setting.key, setting.name, setting.unit, numeric=True)
            text = _check_value(reader, where, column, text, bool(value_cell and value_cell.percent))
        values[setting.key] = text
        rows[setting.key] = row

    def at(key: str) -> str:
        return f"Box!{make_ref(rows[key], 2)}" if key in rows else "Box"

    if not values.get("name"):
        reader.error(at("name"), "Name is needed: it names the assembly and the layout part.")
    elif re.search(r'[<>:"/\\|?*@]', values["name"]) or values["name"] != values["name"].strip(". "):
        reader.error(at("name"), f"Name becomes file names, so it may not use < > : \" / \\ | ? * @ or end in a "
                                 f"dot (got {values['name']!r}).")
    fmt = values.get("format", "") or schema.FORMAT
    if fmt != schema.FORMAT:
        reader.error(at("format"), f"this workbook is format {fmt}; this version of the app reads format "
                                   f"{schema.FORMAT}.")
    return Box(name=values.get("name", ""), output_folder=values.get("output_folder", ""),
               part_template=values.get("part_template", ""),
               assembly_template=values.get("assembly_template", ""),
               pressure_angle=values.get("pressure_angle", ""), efficiency=values.get("efficiency", ""),
               format=fmt)


def from_book(book: Book) -> Tuple[GearboxSpec, List[Diagnostic]]:
    """The gearbox in a workbook, and a diagnostic for every cell that could not be used."""
    reader = _Reader()
    box = _read_box(reader, book.sheet("Box"))

    shafts: List[Shaft] = []
    sheet = book.sheet("Shafts")
    if sheet is None:
        reader.error("Shafts", "the workbook has no Shafts sheet.")
    else:
        for row, v in _table(reader, sheet, schema.SHAFTS):
            shafts.append(Shaft(row=row, **v))

    gears: List[Gear] = []
    sheet = book.sheet("Gears")
    if sheet is None:
        reader.error("Gears", "the workbook has no Gears sheet.")
    else:
        for row, v in _table(reader, sheet, schema.GEARS):
            gears.append(Gear(row=row, **v))

    meshes: List[Mesh] = []
    sheet = book.sheet("Meshes")
    if sheet is not None:
        for row, v in _table(reader, sheet, schema.MESHES):
            meshes.append(Mesh(row=row, **v))

    modes, sliders = _read_modes(reader, book.sheet("Modes"))
    spec = GearboxSpec(box=box, shafts=tuple(shafts), gears=tuple(gears), meshes=tuple(meshes),
                       modes=tuple(modes), sliders=tuple(sliders), source_path=book.path,
                       columns={k: dict(v) for k, v in reader.columns.items()})
    _check_references(reader, spec)
    return spec, reader.diagnostics


def _read_modes(reader: _Reader, sheet: Optional[Sheet]) -> Tuple[List[Mode], List[str]]:
    if sheet is None:
        return [], []
    headers = {col: cell.text.strip() for (row, col), cell in sheet.cells.items() if row == 1 and cell.text.strip()}
    if not headers:
        return [], []
    name_col = next((c for c, t in headers.items() if schema.header_key(t) == "mode"), None)
    notes_col = next((c for c, t in headers.items() if schema.header_key(t) == "notes"), None)
    if name_col is None:
        reader.error("Modes!1", "the Mode column is missing.")
        return [], []
    slider_cols = []
    for c, t in sorted(headers.items()):
        if c in (name_col, notes_col):
            continue
        if t in [name for _, name in slider_cols]:
            reader.error(f"Modes!{make_ref(1, c)}", f"a second {t} column; only the first is read.")
            continue
        slider_cols.append((c, t))
    reader.columns["Modes"] = {"name": name_col}
    reader.slider_columns = {t: c for c, t in slider_cols}
    modes = []
    for row in range(2, sheet.max_row() + 1):
        first = sheet.cell(row, 1)
        if first is not None and first.text.lstrip().startswith("#"):
            continue
        name = _cell_text(reader, sheet, sheet.cell(row, name_col), None)
        picks = tuple((t, _cell_text(reader, sheet, sheet.cell(row, c), None)) for c, t in slider_cols)
        notes = _cell_text(reader, sheet, sheet.cell(row, notes_col), None) if notes_col else ""
        if not name and not any(p for _, p in picks):
            continue
        if not name:
            reader.error(f"Modes!{make_ref(row, name_col)}", "Mode is needed.")
        modes.append(Mode(name=name, positions=picks, notes=notes, row=row))
    return modes, [t for _, t in slider_cols]


def _check_references(reader: _Reader, spec: GearboxSpec) -> None:
    at = reader.at
    """Names, and every reference from one sheet to another. Geometry and maths are checks.py's (W3)."""
    seen: Dict[str, int] = {}
    for shaft in spec.shafts:
        where = at("Shafts", shaft.row, "id")
        if shaft.id and not NAME_PATTERN.match(shaft.id):
            reader.error(where, f"Shaft names may use letters, digits, _ and - only (got {shaft.id!r}).")
        if shaft.id.lower() in seen:
            reader.error(where, f"the shaft {shaft.id} is also on row {seen[shaft.id.lower()]}; names must be "
                                "unique, and S1 and s1 are the same name to SolidWorks and Windows.")
        elif shaft.id:
            seen[shaft.id.lower()] = shaft.row
        if shaft.id.lower() == FRAME:
            reader.error(where, "frame is the housing's name and cannot name a shaft.")
    shaft_ids = {s.id for s in spec.shafts if s.id}
    for shaft in spec.shafts:
        mount = shaft.mount()
        if mount != FRAME and mount not in shaft_ids:
            reader.error(at("Shafts", shaft.row, "mounted_on"), f"{mount} is not a shaft on the Shafts sheet, nor frame.")
        if mount == shaft.id:
            reader.error(at("Shafts", shaft.row, "mounted_on"), f"{shaft.id} cannot be mounted on itself.")
        if shaft.copies and shaft.copies != "1" and mount == FRAME:
            reader.error(at("Shafts", shaft.row, "copies"), "Copies is for a shaft mounted on another shaft, "
                                                 "spaced round it; a shaft on the frame is one shaft.")
        if (shaft.speed or shaft.torque) and shaft.role != "input":
            reader.error(at("Shafts", shaft.row, "role"), f"{shaft.id} has a speed or torque but is not an input; "
                                                 "set Role to input, or clear them.")
        if shaft.role == "input" and not shaft.speed:
            reader.error(at("Shafts", shaft.row, "speed"), f"{shaft.id} is an input and needs a speed.")
    if spec.shafts and not any(s.role == "input" for s in spec.shafts):
        reader.warning("Shafts", "no shaft is an input, so speeds and torques cannot be worked out.")

    seen = {}
    for gear in spec.gears:
        where = at("Gears", gear.row, "id")
        if gear.id and not NAME_PATTERN.match(gear.id):
            reader.error(where, f"Gear names may use letters, digits, _ and - only (got {gear.id!r}).")
        if gear.id.lower() in seen:
            reader.error(where, f"the gear {gear.id} is also on row {seen[gear.id.lower()]}; names must be "
                                "unique, and G1 and g1 are the same name to SolidWorks and Windows.")
        elif gear.id:
            seen[gear.id.lower()] = gear.row
        if gear.shaft and gear.shaft not in shaft_ids:
            reader.error(at("Gears", gear.row, "shaft"), f"{gear.shaft} is not a shaft on the Shafts sheet.")
        if gear.kind_word() in ("helical", "herringbone") and not gear.helix_angle:
            reader.error(at("Gears", gear.row, "helix_angle"),
                         f"{gear.id} is {gear.kind_word()} and needs a helix angle.")
        if gear.slides:
            try:
                gear.positions()
            except ValueError as exc:
                reader.error(at("Gears", gear.row, "slides"), str(exc))
    gear_ids = {g.id for g in spec.gears if g.id}

    pairs: Dict[frozenset, int] = {}
    for mesh in spec.meshes:
        for key, name in (("a", mesh.a), ("b", mesh.b)):
            if name and name not in gear_ids:
                reader.error(at("Meshes", mesh.row, key),
                             f"{name} is not a gear on the Gears sheet.")
        if mesh.a and mesh.a == mesh.b:
            reader.error(at("Meshes", mesh.row, "a"), f"{mesh.a} cannot mesh with itself.")
        pair = frozenset((mesh.a, mesh.b))
        if pair in pairs:
            reader.error(at("Meshes", mesh.row, "a"), f"{mesh.a} and {mesh.b} are already listed on row {pairs[pair]}.")
        else:
            pairs[pair] = mesh.row

    gears_by_id = {g.id: g for g in spec.gears}
    for index, slider in enumerate(spec.sliders):
        gear = gears_by_id.get(slider)
        col = reader.slider_columns.get(slider, index + 2)
        if gear is None:
            reader.error(f"Modes!{make_ref(1, col)}", f"{slider} is not a gear on the Gears sheet.")
        elif not gear.slides:
            reader.error(f"Modes!{make_ref(1, col)}", f"{slider} has no Slides positions on the Gears sheet.")
    names: Dict[str, int] = {}
    for mode in spec.modes:
        if mode.name in names:
            reader.error(at("Modes", mode.row, "name"), f"the mode {mode.name} is also on row {names[mode.name]}.")
        elif mode.name:
            names[mode.name] = mode.row
        for index, (slider, pick) in enumerate(mode.positions):
            gear = gears_by_id.get(slider)
            if gear is None or not gear.slides or not pick:
                continue
            try:
                positions = gear.positions()
            except ValueError:
                continue
            if pick not in positions:
                reader.error(f"Modes!{make_ref(mode.row, reader.slider_columns.get(slider, index + 2))}",
                             f"{slider} has no position {pick}; it has {', '.join(positions)}.")


# ------------------------------------------------------------------ writing


def _out(column: Column, text: str):
    """A model value as a cell value: a number as a number, so Excel treats it as one."""
    if column.numeric and text:
        try:
            value = float(text)
        except ValueError:
            return text
        if not math.isfinite(value):
            return text                     # kept as text: a cell holds finite numbers only
        if value == int(value) and abs(value) < 1e15:
            return int(value)
        return value
    return text


def to_sheets(spec: GearboxSpec) -> List[NewSheet]:
    """The gearbox as the workbook's sheets, for :func:`xlsx.write_new` (Results is written by Export, W3)."""
    box_rows: List[List] = [[c.header for c in schema.BOX.columns]]
    box_values = {"format": spec.box.format or schema.FORMAT, "name": spec.box.name,
                  "output_folder": spec.box.output_folder, "part_template": spec.box.part_template,
                  "assembly_template": spec.box.assembly_template, "pressure_angle": spec.box.pressure_angle,
                  "efficiency": spec.box.efficiency}
    for setting in schema.BOX_SETTINGS:
        value = box_values.get(setting.key, setting.default if setting.key == "units" else "")
        if setting.numeric and value:
            value = _out(Column(setting.key, setting.name, numeric=True), value)
        box_rows.append([setting.title, value, setting.note])
    sheets = [NewSheet("Box", box_rows, [c.width for c in schema.BOX.columns])]

    for sheet_def, items in ((schema.SHAFTS, spec.shafts), (schema.GEARS, spec.gears),
                             (schema.MESHES, spec.meshes)):
        rows: List[List] = [[c.title for c in sheet_def.columns]]
        for item in items:
            rows.append([_out(c, getattr(item, c.key)) for c in sheet_def.columns])
        lists = {i: list(c.words) for i, c in enumerate(sheet_def.columns, start=1) if c.words}
        sheets.append(NewSheet(sheet_def.name, rows, [c.width for c in sheet_def.columns], lists))

    gears_by_id = {g.id: g for g in spec.gears}
    mode_rows: List[List] = [[schema.MODE_NAME.header] + list(spec.sliders) + [schema.MODE_NOTES.header]]
    for mode in spec.modes:
        picks = dict(mode.positions)
        mode_rows.append([mode.name] + [picks.get(s, "") for s in spec.sliders] + [mode.notes])
    lists = {}
    for index, slider in enumerate(spec.sliders, start=2):
        gear = gears_by_id.get(slider)
        if gear is not None and gear.slides:
            try:
                lists[index] = list(gear.positions())
            except ValueError:
                pass
    widths = [schema.MODE_NAME.width] + [12.0] * len(spec.sliders) + [schema.MODE_NOTES.width]
    sheets.append(NewSheet("Modes", mode_rows, widths, lists))
    return sheets


def template(name: str = "Gearbox") -> GearboxSpec:
    """A blank workbook's model: the Box filled, every other sheet a header only."""
    return GearboxSpec(box=Box(name=name))
