"""Reading and writing ``.xlsx`` with the standard library (docs/PLAN-WORKBOOK.md §2).

An ``.xlsx`` is a zip of XML parts. Three things are done with one here:

- :func:`read` takes every cell's value as text — the value Excel last saved for
  a formula, never the formula itself — so the model above it stays typed text,
  the way the strip's fields are.
- :func:`write_new` writes a fresh workbook: a header style, a frozen header
  row, column widths and drop-down lists.
- :func:`write_cells` changes named cells in a workbook the user owns. It
  edits the sheet part as *text* and copies every other part unchanged, because
  re-serialising through ``xml.etree`` renames namespace prefixes and drops the
  declarations ``mc:Ignorable`` names, and Excel then opens the file with a
  repair prompt. A cell holding a formula is never written.

Nothing here knows what a gear is; :mod:`.schema` and :mod:`.model` do.
"""

from __future__ import annotations

import io
import os
import posixpath
import shutil
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union
from xml.etree import ElementTree
from xml.sax.saxutils import escape, quoteattr

from ..store import same_file

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
STRICT_NS = "http://purl.oclc.org/ooxml/spreadsheetml/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
WORKSHEET_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
WORKSHEET_CONTENT = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"

_M = "{%s}" % MAIN_NS
_R = "{%s}" % REL_NS
_P = "{%s}" % PKG_REL_NS

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"   # an encrypted workbook is an OLE compound file, not a zip

Value = Union[str, int, float, None]


class XlsxError(Exception):
    """The file is not a workbook this module can read, said as a full sentence."""


class NotReady(XlsxError):
    """The file was caught mid-save, or briefly absent while Excel replaced it: try again shortly."""


class Locked(XlsxError):
    """Another program (Excel, on Windows) holds the file, so it cannot be written."""


# ------------------------------------------------------------------ cells


@dataclass(frozen=True)
class Cell:
    """One cell's value as text. ``formula`` says the text is a formula's saved result; ``error`` holds ``#NAME?`` and the like."""

    ref: str
    row: int
    col: int
    text: str = ""
    formula: bool = False
    error: str = ""
    percent: bool = False      # formatted as a percentage: Excel shows 0.98 as 98 %


@dataclass
class Sheet:
    name: str
    part: str
    cells: Dict[Tuple[int, int], Cell] = field(default_factory=dict)

    def cell(self, row: int, col: int) -> Optional[Cell]:
        return self.cells.get((row, col))

    def max_row(self) -> int:
        return max((r for r, _ in self.cells), default=0)

    def max_col(self) -> int:
        return max((c for _, c in self.cells), default=0)

    def row(self, row: int) -> List[Optional[Cell]]:
        """The row's cells, column 1 first, ``None`` where a cell is absent."""
        return [self.cells.get((row, col)) for col in range(1, self.max_col() + 1)]


@dataclass
class Book:
    path: str = ""
    sheets: Dict[str, Sheet] = field(default_factory=dict)   # in tab order

    def sheet(self, name: str) -> Optional[Sheet]:
        """A sheet by name, ignoring case and surrounding spaces."""
        wanted = name.strip().lower()
        for sheet_name, sheet in self.sheets.items():
            if sheet_name.strip().lower() == wanted:
                return sheet
        return None


def column_index(letters: str) -> int:
    """``A`` -> 1, ``Z`` -> 26, ``AA`` -> 27."""
    index = 0
    for ch in letters.upper():
        if not "A" <= ch <= "Z":
            raise ValueError(f"{letters!r} is not a column.")
        index = index * 26 + (ord(ch) - 64)
    return index


def column_letters(index: int) -> str:
    """1 -> ``A``, 27 -> ``AA``."""
    if index < 1:
        raise ValueError(f"Column {index} does not exist; columns start at 1.")
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


MAX_ROWS, MAX_COLS = 1048576, 16384
_REF = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")


def split_ref(ref: str) -> Tuple[int, int]:
    """``D4`` -> (4, 4): row, column."""
    match = _REF.match(ref.strip())
    if not match:
        raise ValueError(f"{ref!r} is not a cell reference.")
    row, col = int(match.group(2)), column_index(match.group(1))
    if not (1 <= row <= MAX_ROWS and 1 <= col <= MAX_COLS):
        raise ValueError(f"{ref!r} is outside a sheet: rows run 1 to {MAX_ROWS}, columns A to XFD.")
    return row, col


def make_ref(row: int, col: int) -> str:
    return f"{column_letters(col)}{row}"


def number_text(raw: str) -> str:
    """A number as Excel stored it, as text a person would type: 15 significant digits, shortest form.

    Excel writes doubles to 17 digits, so ``1.1`` arrives as
    ``1.1000000000000001``; rounding to 15 gives back what was typed. ``17.0``
    is ``17`` and ``-0`` is ``0``.
    """
    try:
        value = float(raw)
    except ValueError:
        return raw.strip()
    if value != value or value in (float("inf"), float("-inf")):
        return raw.strip()
    text = "%.15g" % value
    if "e" in text or "E" in text:
        text = format(Decimal(text), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


# ------------------------------------------------------------------ reading


def read(path: str) -> Book:
    """Every sheet's cells, as text. Raises :class:`NotReady` for a file caught mid-save."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except FileNotFoundError:
        raise NotReady(f"{path} is not there right now.") from None
    except PermissionError:
        raise NotReady(f"{path} cannot be opened right now.") from None
    book = read_bytes(data, path)
    return book


def read_bytes(data: bytes, path: str = "") -> Book:
    name = os.path.basename(path) or "The workbook"
    if data[:8] == OLE_MAGIC:
        raise XlsxError(f"{name} is encrypted or in the old .xls format; save it from Excel as an .xlsx "
                        "workbook without a password.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise NotReady(f"{name} is not a complete workbook yet; it may be mid-save.") from None
    with archive:
        names = set(archive.namelist())
        if "xl/workbook.xml" not in names:
            if any(n.endswith("workbook.xml") for n in names):
                raise XlsxError(f"{name} keeps its workbook part somewhere unusual; save it again from Excel.")
            raise NotReady(f"{name} has no workbook part yet; it may be mid-save.")
        workbook = _parse(archive, "xl/workbook.xml", name)
        if workbook.tag == "{%s}workbook" % STRICT_NS:
            raise XlsxError(f"{name} is saved as Strict Open XML; save it again from Excel as an ordinary "
                            "Excel Workbook (.xlsx).")
        rels, types = _relationships(archive, "xl/_rels/workbook.xml.rels", "xl", name, with_types=True)
        strings_part = next((t for i, t in rels.items() if types.get(i, "").endswith("/sharedStrings")),
                            "xl/sharedStrings.xml")
        strings = _shared_strings(archive, strings_part, name) if strings_part in names else []
        styles_part = next((t for i, t in rels.items() if types.get(i, "").endswith("/styles")), "xl/styles.xml")
        percent_styles = _percent_styles(archive, styles_part, name) if styles_part in names else set()
        book = Book(path=path)
        sheets = workbook.find(_M + "sheets")
        for entry in (sheets if sheets is not None else []):
            sheet_name = entry.get("name", "")
            target = rels.get(entry.get(_R + "id", ""), "")
            if not target or target not in names:
                continue      # a chart sheet or a broken link: nothing of ours lives there
            sheet = Sheet(name=sheet_name, part=target)
            try:
                _read_cells(_parse(archive, target, name), strings, sheet, percent_styles)
            except ValueError as exc:
                raise XlsxError(f"{name}, sheet {sheet_name}: {exc} Save it again from Excel.") from None
            book.sheets[sheet_name] = sheet
        return book


def _parse(archive: zipfile.ZipFile, part: str, name: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(archive.read(part))
    except ElementTree.ParseError as exc:
        raise NotReady(f"{name}'s part {part} could not be read ({exc}); it may be mid-save.") from None
    except KeyError:
        raise NotReady(f"{name} has no part {part} yet; it may be mid-save.") from None


def _relationships(archive: zipfile.ZipFile, part: str, base: str, name: str, with_types: bool = False):
    """Relationship id -> the target's part name, resolved against ``base`` (and id -> type, if asked)."""
    try:
        root = _parse(archive, part, name)
    except NotReady:
        return ({}, {}) if with_types else {}
    out, types = {}, {}
    for rel in root.findall(_P + "Relationship"):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            continue
        resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(base, target))
        out[rel.get("Id", "")] = resolved
        types[rel.get("Id", "")] = rel.get("Type", "")
    return (out, types) if with_types else out


_ESCAPED = re.compile(r"_x([0-9A-Fa-f]{4})_")


def decode_text(text: str) -> str:
    """Excel's ``_xHHHH_`` escapes undone: ``_x000D_`` is a carriage return, ``_x005F_`` a literal underscore."""
    return _ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), text) if "_x" in text else text


_XML_INVALID = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")


def encode_text(text: str) -> str:
    """Text made safe for a cell, the way Excel does it: a character XML 1.0 forbids becomes ``_xHHHH_``,
    and text that already looks like an escape has its underscore escaped, so it reads back as typed."""
    text = _ESCAPED.sub(lambda m: "_x005F_" + m.group(0)[1:], text)
    return _XML_INVALID.sub(lambda m: "_x%04X_" % ord(m.group(0)), text)


def _percent_styles(archive: zipfile.ZipFile, part: str, name: str) -> set:
    """The indexes of the cell formats (``s``) that show a number as a percentage."""
    try:
        root = _parse(archive, part, name)
    except NotReady:
        return set()
    codes = {9: "0%", 10: "0.00%"}
    formats = root.find(_M + "numFmts")
    for fmt in (formats if formats is not None else []):
        try:
            codes[int(fmt.get("numFmtId", "-1"))] = fmt.get("formatCode", "")
        except ValueError:
            continue
    xfs = root.find(_M + "cellXfs")
    out = set()
    for index, xf in enumerate(xfs if xfs is not None else []):
        try:
            code = codes.get(int(xf.get("numFmtId", "0")), "")
        except ValueError:
            continue
        if "%" in re.sub(r'"[^"]*"|\\.', "", code):     # a % outside quoted text or an escape
            out.add(index)
    return out


def _shared_strings(archive: zipfile.ZipFile, part: str, name: str) -> List[str]:
    root = _parse(archive, part, name)
    return [_string_item(si) for si in root.findall(_M + "si")]


def _string_item(item: ElementTree.Element) -> str:
    """The text of an ``<si>`` or ``<is>``: its ``<t>``, or its runs' ``<t>``s joined — never the phonetic ``<rPh>``."""
    direct = item.find(_M + "t")
    if direct is not None:
        return decode_text(direct.text or "")
    return decode_text("".join((run.find(_M + "t").text or "") for run in item.findall(_M + "r")
                               if run.find(_M + "t") is not None))


def _read_cells(root: ElementTree.Element, strings: Sequence[str], sheet: Sheet,
                percent_styles: frozenset = frozenset()) -> None:
    data = root.find(_M + "sheetData")
    if data is None:
        return
    row_number = 0
    for row in data.findall(_M + "row"):
        try:
            row_number = int(row.get("r", row_number + 1))
        except ValueError:
            raise ValueError(f"a row is numbered {row.get('r')!r}, which is not a row number.") from None
        col_number = 0
        for c in row.findall(_M + "c"):
            ref = c.get("r")
            if ref:
                try:
                    row_number_c, col_number = split_ref(ref)
                except ValueError:
                    raise ValueError(f"a cell is addressed {ref!r}, which is not one cell.") from None
            else:
                row_number_c, col_number = row_number, col_number + 1
                ref = make_ref(row_number_c, col_number)
            kind = c.get("t", "n")
            formula = c.find(_M + "f") is not None
            value = c.find(_M + "v")
            raw = value.text if value is not None and value.text is not None else ""
            text, error = "", ""
            if kind == "s":
                try:
                    text = strings[int(raw)] if raw else ""
                except (ValueError, IndexError):
                    text = ""
            elif kind == "inlineStr":
                inline = c.find(_M + "is")
                text = _string_item(inline) if inline is not None else ""
            elif kind == "str":
                text = decode_text(raw)
            elif kind == "b":
                text = "TRUE" if raw.strip() == "1" else ("FALSE" if raw.strip() else "")
            elif kind == "e":
                error = raw.strip() or "#ERROR"
            elif kind == "d":
                text = raw.strip()
            else:
                text = number_text(raw) if raw.strip() else ""
            if formula and value is None and kind != "inlineStr":
                error = error or "#NOVALUE"
            if not (text or error or formula):
                continue
            try:
                percent = int(c.get("s", "0")) in percent_styles
            except ValueError:
                percent = False
            sheet.cells[(row_number_c, col_number)] = Cell(ref, row_number_c, col_number, text, formula, error,
                                                           percent)


# ------------------------------------------------------------------ writing a new workbook


@dataclass(frozen=True)
class NewSheet:
    """A sheet for :func:`write_new`: rows of values (row 1 the header), widths, and drop-down lists by column."""

    name: str
    rows: Sequence[Sequence[Value]]
    widths: Sequence[float] = ()
    lists: Mapping[int, Sequence[str]] = field(default_factory=dict)   # column -> words, applied below the header
    header: bool = True
    note: str = ""                                                      # Results: a first-row note, unstyled


LIST_ROWS = 500   # how far down a drop-down list reaches in a new workbook


def write_new(path: str, sheets: Sequence[NewSheet]) -> None:
    """A complete new workbook. Refuses to overwrite: a file the user owns is only ever changed by :func:`write_cells`."""
    if os.path.exists(path):
        raise XlsxError(f"{path} already exists, and a new workbook never overwrites a file.")
    names = [s.name for s in sheets]
    if len(set(n.lower() for n in names)) != len(names):
        raise XlsxError("Two sheets share a name.")
    for n in names:
        check_sheet_name(n)
    parts: List[Tuple[str, bytes]] = [
        ("[Content_Types].xml", _content_types(len(sheets))),
        ("_rels/.rels", _root_rels()),
        ("xl/workbook.xml", _workbook_xml(names)),
        ("xl/_rels/workbook.xml.rels", _workbook_rels(len(sheets))),
        ("xl/styles.xml", _STYLES.encode("utf-8")),
    ]
    for index, sheet in enumerate(sheets, start=1):
        parts.append((f"xl/worksheets/sheet{index}.xml", sheet_xml(sheet).encode("utf-8")))
    _write_zip_atomically(path, parts)


def check_sheet_name(name: str) -> None:
    """Excel's limits on a sheet's name: 1–31 characters, none of ``[]:*?/\\``, not starting or ending with ``'``."""
    if not name or len(name) > 31 or re.search(r"[\[\]:*?/\\]", name) or name.startswith("'") or name.endswith("'"):
        raise XlsxError(f"{name!r} cannot name a sheet: Excel allows 1 to 31 characters, without [ ] : * ? / \\ "
                        "and not starting or ending with an apostrophe.")


def _write_zip_atomically(path: str, parts: Iterable[Tuple[Union[str, zipfile.ZipInfo], bytes]]) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    handle, temp = tempfile.mkstemp(prefix=".~gear-", suffix=".xlsx", dir=folder)
    os.close(handle)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as out:
            for info, data in parts:
                if isinstance(info, zipfile.ZipInfo):
                    out.writestr(info, data, compress_type=info.compress_type)
                else:
                    out.writestr(info, data)
        # mkstemp makes the file private (0600); give it the original's mode, or a new file's usual one.
        if os.path.exists(path):
            shutil.copymode(path, temp)
        else:
            mask = os.umask(0)
            os.umask(mask)
            os.chmod(temp, 0o666 & ~mask)
        try:
            os.replace(temp, path)
        except PermissionError:
            raise Locked(f"{os.path.basename(path)} is open in another program (Excel, most likely), so it "
                         "could not be saved. Close it there, or use Export as… to write a new file.") from None
    finally:
        if os.path.exists(temp):
            os.remove(temp)


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f'<styleSheet xmlns="{MAIN_NS}">'
    '<fonts count="3"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
    '<font><i/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts>'
    '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
    '<fill><patternFill patternType="solid"><fgColor rgb="FFE8EEF7"/><bgColor indexed="64"/></patternFill></fill></fills>'
    '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
    '<border><left/><right/><top/><bottom style="medium"><color rgb="FF2B2B2B"/></bottom><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>'
    '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
    '</styleSheet>'
)
HEADER_STYLE, NOTE_STYLE = 1, 2


def _content_types(count: int) -> bytes:
    sheets = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{WORKSHEET_CONTENT}"/>'
                     for i in range(1, count + 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Types xmlns="{CT_NS}">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f'{sheets}</Types>').encode("utf-8")


def _root_rels() -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Relationships xmlns="{PKG_REL_NS}">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>').encode("utf-8")


def _workbook_xml(names: Sequence[str]) -> bytes:
    sheets = "".join(f'<sheet name={quoteattr(n)} sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<workbook xmlns="{MAIN_NS}" xmlns:r="{REL_NS}">'
            f'<bookViews><workbookView/></bookViews><sheets>{sheets}</sheets>'
            '<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>').encode("utf-8")


def _workbook_rels(count: int) -> bytes:
    rels = "".join(f'<Relationship Id="rId{i}" Type="{WORKSHEET_TYPE}" Target="worksheets/sheet{i}.xml"/>'
                   for i in range(1, count + 1))
    styles = (f'<Relationship Id="rId{count + 1}" '
              'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
              'Target="styles.xml"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Relationships xmlns="{PKG_REL_NS}">{rels}{styles}</Relationships>').encode("utf-8")


def cell_xml(ref: str, value: Value, style: int = 0) -> str:
    """One ``<c>``: a number as a number, anything else as an inline string; ``None`` or ``""`` as nothing."""
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>' if style else ""
    if isinstance(value, bool):
        return f'<c r="{ref}"{s} t="b"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        if value != value or value in (float("inf"), float("-inf")):
            raise XlsxError(f"{ref} cannot hold {value!r}: a cell holds finite numbers only.")
        return f'<c r="{ref}"{s}><v>{_number_out(value)}</v></c>'
    text = encode_text(str(value))
    space = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
    return f'<c r="{ref}"{s} t="inlineStr"><is><t{space}>{escape(text)}</t></is></c>'


def _number_out(value: Union[int, float]) -> str:
    if isinstance(value, int):
        return str(value)
    return repr(float(value))


def sheet_xml(sheet: NewSheet) -> str:
    rows_xml = []
    offset = 1
    if sheet.note:
        rows_xml.append(f'<row r="1">{cell_xml("A1", sheet.note, NOTE_STYLE)}</row>')
        offset = 2
    for index, values in enumerate(sheet.rows):
        r = index + offset
        style = HEADER_STYLE if sheet.header and index == 0 else 0
        cells = "".join(cell_xml(make_ref(r, c), v, style) for c, v in enumerate(values, start=1))
        rows_xml.append(f'<row r="{r}">{cells}</row>')
    header_row = offset if sheet.header and sheet.rows else 0
    views = ""
    if header_row:
        top = make_ref(header_row + 1, 1)
        views = (f'<sheetViews><sheetView workbookViewId="0"><pane ySplit="{header_row}" topLeftCell="{top}" '
                 'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
    cols = ""
    if sheet.widths:
        cols = "<cols>" + "".join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
                                  for i, w in enumerate(sheet.widths, start=1)) + "</cols>"
    validations = ""
    if sheet.lists:
        items = []
        first = header_row + 1 if header_row else 1
        for col, words in sorted(sheet.lists.items()):
            joined = ",".join(words)
            if len(joined) > 255:
                continue      # longer than Excel allows in a list: the column simply has no drop-down
            sqref = f"{column_letters(col)}{first}:{column_letters(col)}{first + LIST_ROWS - 1}"
            # No error alert: the list offers the canonical words, but the format also accepts short forms
            # (ext, R, double) and an axis as three numbers, which a stop-style alert would refuse.
            items.append(f'<dataValidation type="list" allowBlank="1" sqref="{sqref}">'
                         f'<formula1>{escape(_quote_list(joined))}</formula1></dataValidation>')
        validations = (f'<dataValidations count="{len(items)}">{"".join(items)}</dataValidations>'
                       if items else "")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<worksheet xmlns="{MAIN_NS}" xmlns:r="{REL_NS}">{views}{cols}'
            f'<sheetData>{"".join(rows_xml)}</sheetData>{validations}</worksheet>')


def _quote_list(joined: str) -> str:
    return '"' + joined.replace('"', '""') + '"'


# ------------------------------------------------------------------ changing cells in a user's workbook


@dataclass
class CellWrite:
    """What :func:`write_cells` did: the cells it wrote, and the ones it would not (each with why)."""

    written: List[str] = field(default_factory=list)
    refused: List[Tuple[str, str]] = field(default_factory=list)


def lock_file(path: str) -> str:
    """Excel's owner file beside an open workbook: ``~$Name.xlsx``."""
    folder, name = os.path.split(path)
    return os.path.join(folder, "~$" + name[2:] if name.startswith("~$") else "~$" + name)


def is_open_in_excel(path: str) -> bool:
    return os.path.exists(lock_file(path))


def write_cells(path: str, changes: Mapping[str, Mapping[str, Value]],
                replace_sheets: Sequence[NewSheet] = (), out_path: str = "") -> CellWrite:
    """Change the named cells, ``{sheet: {ref: value}}``, and replace (or add) whole sheets of our own.

    Only the touched cells change; every other part of the workbook is copied
    with the same content, name, order, date and compression. A cell that holds
    a formula, a shared formula's child, or lies inside an array formula is
    never written: it comes back in ``refused``. Writes ``out_path`` if given,
    else the workbook itself, through a temporary file and a replace.
    """
    source = os.path.realpath(path)          # through a symlink: the workbook is the file it points at
    target = os.path.realpath(out_path) if out_path else source
    # store.same_file, not os.path.samefile: a volume that reports a file id of 0 for every file made any
    # existing file "the source", and Export as… then wrote over it (third W4 review, item 2, met again here).
    writing_source = target == source or same_file(target, source)
    if writing_source and is_open_in_excel(path):
        raise Locked(f"{os.path.basename(path)} is open in Excel, so it cannot be saved from here. Close it "
                     "there, or use Export as… to write a new file.")
    if out_path and not writing_source and os.path.exists(target):
        raise XlsxError(f"{out_path} already exists, and Export as… never overwrites a file.")
    with open(source, "rb") as handle:
        data = handle.read()
    book = read_bytes(data, path)
    result = CellWrite()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        contents = {info.filename: archive.read(info.filename) for info in infos}
    edited: Dict[str, bytes] = {}

    for sheet_name, cells in changes.items():
        sheet = book.sheet(sheet_name)
        if sheet is None:
            for ref in cells:
                result.refused.append((f"{sheet_name}!{ref}", f"there is no sheet called {sheet_name}"))
            continue
        try:
            text = contents[sheet.part].decode("utf-8")
        except UnicodeDecodeError:
            raise XlsxError(f"The {sheet.name} sheet is not stored as UTF-8, so its cells cannot be changed "
                            "safely. Save the workbook again from Excel.") from None
        try:
            text, done, refused = _splice_cells(text, cells)
        except ValueError as exc:
            raise XlsxError(f"{sheet.name}: {exc}") from None
        if done:
            _check_splice(contents[sheet.part], text, done, sheet.name)
        result.written += [f"{sheet.name}!{ref}" for ref in done]
        result.refused += [(f"{sheet.name}!{ref}", why) for ref, why in refused]
        if done:
            edited[sheet.part] = text.encode("utf-8")

    new_parts: List[Tuple[str, bytes]] = []
    workbook_text = contents["xl/workbook.xml"].decode("utf-8")
    rels_text = contents["xl/_rels/workbook.xml.rels"].decode("utf-8")
    types_text = contents["[Content_Types].xml"].decode("utf-8")
    for new_sheet in replace_sheets:
        existing = book.sheet(new_sheet.name)
        body = sheet_xml(NewSheet(new_sheet.name, new_sheet.rows, new_sheet.widths, {}, False, new_sheet.note))
        body = body.replace(f' s="{NOTE_STYLE}"', "")     # unstyled: the user's styles.xml is never touched
        if existing is not None:
            edited[existing.part] = body.encode("utf-8")
            continue
        part = _free_sheet_part(contents)
        rel_id = _free_rel_id(rels_text)
        rels_text = rels_text.replace(
            "</Relationships>",
            f'<Relationship Id="{rel_id}" Type="{WORKSHEET_TYPE}" Target="{part[len("xl/"):]}"/></Relationships>')
        workbook_text = _add_sheet_entry(workbook_text, new_sheet.name, rel_id)
        types_text = types_text.replace(
            "</Types>", f'<Override PartName="/{part}" ContentType="{WORKSHEET_CONTENT}"/></Types>')
        new_parts.append((part, body.encode("utf-8")))
        contents[part] = b""          # reserve the name for a second added sheet

    if edited or new_parts:
        workbook_text = set_full_calc_on_load(workbook_text)
        edited["xl/workbook.xml"] = workbook_text.encode("utf-8")
        if new_parts:
            edited["xl/_rels/workbook.xml.rels"] = rels_text.encode("utf-8")
            edited["[Content_Types].xml"] = types_text.encode("utf-8")
    if not edited and not out_path:
        return result

    parts: List[Tuple[Union[str, zipfile.ZipInfo], bytes]] = []
    for info in infos:
        parts.append((info, edited.get(info.filename, contents[info.filename])))
    parts += new_parts
    for part in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml"):
        if part in edited:
            try:
                ElementTree.fromstring(edited[part])
            except ElementTree.ParseError as exc:
                raise XlsxError(f"Changing {part} would have left it unreadable ({exc}); nothing was written.") \
                    from None
    _write_zip_atomically(target, parts)
    return result


def _check_splice(before: bytes, after_text: str, written: Sequence[str], sheet_name: str) -> None:
    """The safety net: the edited sheet must parse, and every cell not written must read exactly as before.

    The splice works on text, so a shape it does not expect (a comment, CDATA,
    a row twice) could cut or invent cells. Rather than trust it, read both
    versions and compare; a difference refuses the whole write, and the
    workbook on disk is never touched.
    """
    try:
        old_root = ElementTree.fromstring(before)
        new_root = ElementTree.fromstring(after_text.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise XlsxError(f"The {sheet_name} sheet could not be changed safely ({exc}); nothing was written.") \
            from None
    old, new = Sheet(sheet_name, ""), Sheet(sheet_name, "")
    _read_cells(old_root, [], old)
    _read_cells(new_root, [], new)
    touched = {split_ref(ref) for ref in written}

    def same(a: Optional[Cell], b: Optional[Cell]) -> bool:
        if a is None or b is None:
            return a is b
        return (a.text, a.formula, a.error) == (b.text, b.formula, b.error)

    for key in set(old.cells) | set(new.cells):
        if key not in touched and not same(old.cells.get(key), new.cells.get(key)):
            raise XlsxError(f"The {sheet_name} sheet could not be changed safely: {make_ref(*key)} would have "
                            "changed too, though it was not asked to. Nothing was written; save the workbook "
                            "again from Excel and retry.")


_CELL = re.compile(r"<(?:\w+:)?c\b[^>]*?(?:/>|>.*?</(?:\w+:)?c>)", re.S)
_ROW = re.compile(r"<(?:\w+:)?row\b[^>]*?(?:/>|>.*?</(?:\w+:)?row>)", re.S)
_ATTR = re.compile(r'(\w+(?::\w+)?)\s*=\s*("[^"]*"|\'[^\']*\')')


def _attrs(tag_open: str) -> Dict[str, str]:
    return {k: v[1:-1] for k, v in _ATTR.findall(tag_open)}


def _array_ranges(text: str) -> List[Tuple[int, int, int, int]]:
    ranges = []
    for match in re.finditer(r"<(?:\w+:)?f\b([^>]*)>", text):
        attrs = _attrs(match.group(1))
        if attrs.get("t") in ("array", "dataTable") and attrs.get("ref"):
            first, _, last = attrs["ref"].partition(":")
            r1, c1 = split_ref(first)
            r2, c2 = split_ref(last or first)
            ranges.append((r1, c1, r2, c2))
    return ranges


def _splice_cells(text: str, cells: Mapping[str, Value]) -> Tuple[str, List[str], List[Tuple[str, str]]]:
    """The sheet XML with the named cells set; (new text, refs written, (ref, why) refused)."""
    open_match = re.search(r"<((?:\w+:)?)sheetData\b[^>]*?(/?)>", text)
    if open_match is None:
        return text, [], [(ref, "the sheet has no cell data") for ref in cells]
    prefix = open_match.group(1)
    if open_match.group(2) == "/":
        text = text[:open_match.start()] + f"<{prefix}sheetData></{prefix}sheetData>" + text[open_match.end():]
        open_match = re.search(r"<((?:\w+:)?)sheetData\b[^>]*?>", text)
    close_at = text.index(f"</{prefix}sheetData>", open_match.end())
    data = text[open_match.end():close_at]
    arrays = _array_ranges(data)

    if "<!--" in data or "<![CDATA[" in data:
        return text, [], [(ref, "the sheet holds XML comments or CDATA, which Excel never writes; save it "
                                "again from Excel") for ref in cells]
    rows: Dict[int, str] = {}
    order: List[int] = []
    last_end = 0
    for match in _ROW.finditer(data):
        if data[last_end:match.start()].strip():
            return text, [], [(ref, "the sheet has something between its rows that is not a row; save it "
                                    "again from Excel") for ref in cells]
        last_end = match.end()
        attrs = _attrs(match.group(0)[:match.group(0).index(">") + 1])
        if "r" not in attrs:
            return text, [], [(ref, "the sheet's rows are not numbered, so cells cannot be placed safely")
                              for ref in cells]
        number = int(attrs["r"])
        if number in rows:
            return text, [], [(ref, f"the sheet has row {number} twice; save it again from Excel")
                              for ref in cells]
        rows[number] = match.group(0)
        order.append(number)

    written, refused = [], []
    for ref, value in cells.items():
        row_number, col_number = split_ref(ref)
        ref = make_ref(row_number, col_number)
        if any(r1 <= row_number <= r2 and c1 <= col_number <= c2 for r1, c1, r2, c2 in arrays):
            refused.append((ref, "it is part of an array formula or a data table"))
            continue
        row_xml = rows.get(row_number)
        if row_xml is None:
            new_cell = cell_xml(ref, value)
            if not new_cell:
                written.append(ref)
                continue
            rows[row_number] = f"<{prefix}row r=\"{row_number}\">{_prefixed(new_cell, prefix)}</{prefix}row>"
            order.append(row_number)
            written.append(ref)
            continue
        new_row, why = _set_in_row(row_xml, row_number, col_number, ref, value, prefix)
        if why:
            refused.append((ref, why))
        else:
            rows[row_number] = new_row
            written.append(ref)

    if data[last_end:].strip():
        return text, [], [(ref, "the sheet has something after its rows that is not a row; save it again "
                                "from Excel") for ref in cells]
    if not written:
        return text, [], refused
    rebuilt = "".join(rows[r] for r in sorted(set(order)))
    # Nothing sits between the rows (checked above), so the rows, in order, are the whole of sheetData.
    new_text = text[:open_match.end()] + rebuilt + text[close_at:]
    new_text = _widen_dimension(new_text, [split_ref(r) for r in written])
    return new_text, written, refused


def _prefixed(cell: str, prefix: str) -> str:
    if not prefix:
        return cell
    return re.sub(r"<(/?)(c|is|t|v)\b", lambda m: f"<{m.group(1)}{prefix}{m.group(2)}", cell)


def _set_in_row(row_xml: str, row_number: int, col_number: int, ref: str, value: Value,
                prefix: str) -> Tuple[str, str]:
    head_end = row_xml.index(">") + 1
    head = row_xml[:head_end]
    if head.endswith("/>"):
        head, body, tail = head[:-2] + ">", "", f"</{prefix}row>"
    else:
        tail_at = row_xml.rindex("</")
        body, tail = row_xml[head_end:tail_at], row_xml[tail_at:]
    head = re.sub(r"""\s+spans=("[^"]*"|'[^']*')""", "", head)   # a hint Excel recomputes; stale once a column is added

    cells = []
    for match in _CELL.finditer(body):
        attrs = _attrs(match.group(0)[:match.group(0).index(">") + 1])
        if "r" not in attrs:
            return row_xml, "the row's cells are not addressed, so a cell cannot be placed safely"
        cells.append((split_ref(attrs["r"])[1], match.group(0), attrs))

    new_cell = cell_xml(ref, value)
    out, placed = [], False
    for col, xml, attrs in cells:
        if col == col_number:
            if re.search(r"<(?:\w+:)?f\b", xml):
                return row_xml, "it holds a formula"
            if attrs.get("s"):
                new_cell = cell_xml(ref, value, int(attrs["s"])) or f'<c r="{ref}" s="{attrs["s"]}"/>'
            if new_cell:
                out.append(_prefixed(new_cell, prefix))
            placed = True
            continue
        if col > col_number and not placed:
            if new_cell:
                out.append(_prefixed(new_cell, prefix))
            placed = True
        out.append(xml)
    if not placed and new_cell:
        out.append(_prefixed(new_cell, prefix))
    return head + "".join(out) + tail, ""


def _widen_dimension(text: str, cells: Sequence[Tuple[int, int]]) -> str:
    match = re.search(r"""(<(?:\w+:)?dimension\b[^>]*\bref=(["']))(.*?)(\2)""", text)
    if not match or not cells:
        return text
    first, _, last = match.group(3).partition(":")
    try:
        r1, c1 = split_ref(first)
        r2, c2 = split_ref(last or first)
    except ValueError:
        return text
    r1 = min([r1] + [r for r, _ in cells]); c1 = min([c1] + [c for _, c in cells])
    r2 = max([r2] + [r for r, _ in cells]); c2 = max([c2] + [c for _, c in cells])
    ref = f"{make_ref(r1, c1)}:{make_ref(r2, c2)}"
    return text[:match.start(3)] + ref + text[match.end(3):]


# The elements that follow calcPr in CT_Workbook, in schema order.
_AFTER_CALC = ("oleSize", "customWorkbookViews", "pivotCaches", "smartTagPr", "smartTagTypes", "webPublishing",
               "fileRecoveryPr", "webPublishObjects", "extLst")


def set_full_calc_on_load(workbook_text: str) -> str:
    """``fullCalcOnLoad="1"`` on ``calcPr``, set in place, or a ``calcPr`` inserted where the schema puts it."""
    match = re.search(r"<((?:\w+:)?)calcPr\b([^>]*?)(/?)>", workbook_text)
    if match:
        attrs = match.group(2)
        quoted = r"""\bfullCalcOnLoad=("[^"]*"|'[^']*')"""
        if re.search(quoted, attrs):
            attrs = re.sub(quoted, 'fullCalcOnLoad="1"', attrs)
        else:
            attrs = attrs + ' fullCalcOnLoad="1"'
        tag = f"<{match.group(1)}calcPr{attrs}{match.group(3)}>"
        return workbook_text[:match.start()] + tag + workbook_text[match.end():]
    prefix_match = re.search(r"<((?:\w+:)?)workbook\b", workbook_text)
    prefix = prefix_match.group(1) if prefix_match else ""
    for name in _AFTER_CALC:
        found = re.search(rf"<{re.escape(prefix)}{name}\b", workbook_text)
        if found:
            return workbook_text[:found.start()] + f'<{prefix}calcPr fullCalcOnLoad="1"/>' + workbook_text[found.start():]
    close = workbook_text.rindex(f"</{prefix}workbook>")
    return workbook_text[:close] + f'<{prefix}calcPr fullCalcOnLoad="1"/>' + workbook_text[close:]


def _free_sheet_part(contents: Mapping[str, bytes]) -> str:
    n = 1
    while f"xl/worksheets/sheet{n}.xml" in contents:
        n += 1
    return f"xl/worksheets/sheet{n}.xml"


def _free_rel_id(rels_text: str) -> str:
    used = set(re.findall(r'Id="([^"]+)"', rels_text))
    n = 1
    while f"rId{n}" in used:
        n += 1
    return f"rId{n}"


def _add_sheet_entry(workbook_text: str, name: str, rel_id: str) -> str:
    prefix_match = re.search(r"<((?:\w+:)?)sheets\b", workbook_text)
    prefix = prefix_match.group(1) if prefix_match else ""
    rel_prefix = re.search(r'xmlns:(\w+)="' + re.escape(REL_NS) + '"', workbook_text)
    r = rel_prefix.group(1) if rel_prefix else None
    if r is None:
        workbook_text = re.sub(r"(<(?:\w+:)?workbook\b)", rf'\1 xmlns:r="{REL_NS}"', workbook_text, count=1)
        r = "r"
    ids = [int(x) for x in re.findall(r'\bsheetId="(\d+)"', workbook_text)]
    entry = f'<{prefix}sheet name={quoteattr(name)} sheetId="{max(ids, default=0) + 1}" {r}:id="{rel_id}"/>'
    close = workbook_text.index(f"</{prefix}sheets>")
    return workbook_text[:close] + entry + workbook_text[close:]
