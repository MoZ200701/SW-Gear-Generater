"""Reading and writing .xlsx with the standard library (docs/PLAN-WORKBOOK.md §2).

``excel_like`` builds a workbook the way Excel writes one — shared strings,
styles, a formula with its saved value, a shared formula, an array formula,
``mc:Ignorable`` namespaces, row spans, a dimension and a calcPr — so the
in-place writer is tested against the shape it will meet, not against our own
writer's output. A workbook actually saved by Excel joins it as a fixture in
W1 (tests/fixtures/excel/), and is read by test_workbook_model.py.
"""

import io
import os
import sys
import zipfile

import pytest

from gear_generator.workbook import xlsx

MAIN = xlsx.MAIN_NS
REL = xlsx.REL_NS

SHEET1 = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<worksheet xmlns="{MAIN}" xmlns:r="{REL}" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="x14ac xr" '
    'xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac" '
    'xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision" '
    'xr:uid="{00000000-0001-0000-0000-000000000000}">'
    '<dimension ref="A1:D4"/>'
    '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    '<sheetFormatPr defaultRowHeight="15" x14ac:dyDescent="0.25"/>'
    '<sheetData>'
    '<row r="1" spans="1:4" x14ac:dyDescent="0.25"><c r="A1" s="1" t="s"><v>0</v></c><c r="B1" s="1" t="s"><v>1</v></c>'
    '<c r="C1" s="1" t="s"><v>2</v></c><c r="D1" s="1" t="s"><v>3</v></c></row>'
    '<row r="2" spans="1:4" x14ac:dyDescent="0.25"><c r="A2" t="s"><v>4</v></c><c r="B2"><v>63.75</v></c>'
    '<c r="C2"><f>B2*2</f><v>127.5</v></c><c r="D2" s="2"><v>1.1000000000000001</v></c></row>'
    '<row r="3" spans="1:4" x14ac:dyDescent="0.25"><c r="A3" t="s"><v>5</v></c><c r="B3"><v>131.75</v></c>'
    '<c r="C3"><f t="shared" ref="C3:C4" si="0">B3*2</f><v>263.5</v></c></row>'
    '<row r="4" spans="1:4" x14ac:dyDescent="0.25"><c r="A4" t="s"><v>6</v></c>'
    '<c r="C4"><f t="shared" si="0"/><v>0</v></c>'
    '<c r="D4"><f t="array" ref="D4:D5">TRANSPOSE(B2:B3)</f><v>63.75</v></c></row>'
    '<row r="5"><c r="D5"><v>131.75</v></c></row>'
    '</sheetData>'
    '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
    '</worksheet>'
)

SHARED = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<sst xmlns="{MAIN}" count="7" uniqueCount="7">'
    '<si><t>Shaft</t></si><si><t>X (mm)</t></si><si><t>Double</t></si>'
    '<si><r><t>Ra</t></r><r><rPr><b/></rPr><t>tio</t></r><rPh sb="0" eb="1"><t>ignored</t></rPh></si>'
    '<si><t>S1</t></si><si><t>S2</t></si><si><t xml:space="preserve"> S3 </t></si>'
    '</sst>'
)

WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<workbook xmlns="{MAIN}" xmlns:r="{REL}" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="x15">'
    '<fileVersion appName="xl" lastEdited="7"/><workbookPr defaultThemeVersion="166925"/>'
    '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800" windowHeight="12300"/></bookViews>'
    '<sheets><sheet name="Shafts" sheetId="1" r:id="rId1"/><sheet name="Notes" sheetId="3" r:id="rId2"/></sheets>'
    '<calcPr calcId="191029"/>'
    '<extLst><ext uri="{140A7094-0E35-4892-8432-C4D2E57EDEB5}"/></extLst>'
    '</workbook>'
)

WORKBOOK_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<Relationships xmlns="{xlsx.PKG_REL_NS}">'
    f'<Relationship Id="rId1" Type="{xlsx.WORKSHEET_TYPE}" Target="worksheets/sheet1.xml"/>'
    f'<Relationship Id="rId2" Type="{xlsx.WORKSHEET_TYPE}" Target="/xl/worksheets/sheet2.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/>'
    '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
    'Target="sharedStrings.xml"/>'
    '</Relationships>'
)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<Types xmlns="{xlsx.CT_NS}">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    f'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="{xlsx.WORKSHEET_CONTENT}"/>'
    f'<Override PartName="/xl/worksheets/sheet2.xml" ContentType="{xlsx.WORKSHEET_CONTENT}"/>'
    '</Types>'
)

SHEET2 = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n<worksheet xmlns="{MAIN}"><sheetData>'
          '<row r="2"><c r="B2" t="inlineStr"><is><t>keep me</t></is></c></row></sheetData></worksheet>')


def excel_like(path):
    parts = [
        ("[Content_Types].xml", CONTENT_TYPES),
        ("_rels/.rels", f'<Relationships xmlns="{xlsx.PKG_REL_NS}"><Relationship Id="rId1" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                        'Target="xl/workbook.xml"/></Relationships>'),
        ("xl/workbook.xml", WORKBOOK),
        ("xl/_rels/workbook.xml.rels", WORKBOOK_RELS),
        ("xl/worksheets/sheet1.xml", SHEET1),
        ("xl/worksheets/sheet2.xml", SHEET2),
        ("xl/sharedStrings.xml", SHARED),
        ("xl/styles.xml", f'<styleSheet xmlns="{MAIN}"/>'),
        ("docProps/app.xml", "<Properties/>"),
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for name, text in parts:
            out.writestr(name, text.encode("utf-8"))
    return path


def parts_of(path):
    with zipfile.ZipFile(path) as archive:
        return [(i.filename, archive.read(i.filename)) for i in archive.infolist()]


# ------------------------------------------------------------------ helpers


@pytest.mark.parametrize("letters,index", [("A", 1), ("Z", 26), ("AA", 27), ("AZ", 52), ("BA", 53), ("XFD", 16384)])
def test_columns_convert_both_ways(letters, index):
    assert xlsx.column_index(letters) == index
    assert xlsx.column_letters(index) == letters


@pytest.mark.parametrize("raw,text", [
    ("17", "17"), ("17.0", "17"), ("63.75", "63.75"), ("1.1000000000000001", "1.1"),
    ("0.30000000000000004", "0.3"), ("-0", "0"), ("1E-05", "0.00001"), ("-375", "-375"), ("2.5E+3", "2500"),
])
def test_a_stored_number_reads_as_it_was_typed(raw, text):
    assert xlsx.number_text(raw) == text


# ------------------------------------------------------------------ reading


def test_an_excel_like_workbook_reads_values_not_formulas(tmp_path):
    book = xlsx.read(excel_like(tmp_path / "w.xlsx"))
    assert list(book.sheets) == ["Shafts", "Notes"]
    sheet = book.sheet("shafts")
    assert [c.text for c in sheet.row(1)] == ["Shaft", "X (mm)", "Double", "Ratio"]
    assert sheet.cell(2, 2).text == "63.75" and not sheet.cell(2, 2).formula
    assert sheet.cell(2, 3).text == "127.5" and sheet.cell(2, 3).formula
    assert sheet.cell(2, 4).text == "1.1"
    assert sheet.cell(4, 1).text == " S3 "
    assert sheet.cell(4, 3).formula             # a shared formula's child is a formula too
    assert book.sheet("Notes").cell(2, 2).text == "keep me"   # an absolute rels target resolves


def test_errors_cells_without_refs_and_unsaved_formulas(tmp_path):
    sheet = (f'<worksheet xmlns="{MAIN}"><sheetData><row r="1"><c t="e"><v>#NAME?</v></c><c><v>5</v></c>'
             '<c><f>A1</f></c><c t="str"><f>"x"</f><v>x</v></c><c t="b"><v>1</v></c></row></sheetData></worksheet>')
    path = tmp_path / "e.xlsx"
    with zipfile.ZipFile(path, "w") as out:
        out.writestr("xl/workbook.xml", f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>'
                                        '<sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
        out.writestr("xl/_rels/workbook.xml.rels",
                     f'<Relationships xmlns="{xlsx.PKG_REL_NS}"><Relationship Id="rId1" '
                     f'Type="{xlsx.WORKSHEET_TYPE}" Target="worksheets/s.xml"/></Relationships>')
        out.writestr("xl/worksheets/s.xml", sheet)
    cells = xlsx.read(path).sheet("S")
    assert cells.cell(1, 1).error == "#NAME?"
    assert cells.cell(1, 2).text == "5" and cells.cell(1, 2).ref == "B1"
    assert cells.cell(1, 3).error == "#NOVALUE"
    assert cells.cell(1, 4).text == "x"
    assert cells.cell(1, 5).text == "TRUE"


def test_a_file_caught_mid_save_is_not_ready(tmp_path):
    path = tmp_path / "half.xlsx"
    full = excel_like(tmp_path / "full.xlsx").read_bytes()
    path.write_bytes(full[: len(full) // 2])
    with pytest.raises(xlsx.NotReady):
        xlsx.read(path)
    with pytest.raises(xlsx.NotReady):
        xlsx.read(tmp_path / "absent.xlsx")


def test_an_encrypted_workbook_is_a_named_error_not_a_retry(tmp_path):
    path = tmp_path / "locked.xlsx"
    path.write_bytes(xlsx.OLE_MAGIC + b"\0" * 512)
    with pytest.raises(xlsx.XlsxError) as caught:
        xlsx.read(path)
    assert not isinstance(caught.value, xlsx.NotReady)
    assert "encrypted" in str(caught.value)


def test_strict_open_xml_is_a_named_error(tmp_path):
    path = tmp_path / "strict.xlsx"
    with zipfile.ZipFile(path, "w") as out:
        out.writestr("xl/workbook.xml", '<workbook xmlns="http://purl.oclc.org/ooxml/spreadsheetml/main"/>')
    with pytest.raises(xlsx.XlsxError, match="Strict"):
        xlsx.read(path)


# ------------------------------------------------------------------ a new workbook


def new_book(path):
    xlsx.write_new(str(path), [
        xlsx.NewSheet("Shafts", [["Shaft", "X (mm)", "Axis"], ["S1", 0, "Z+"], ["S2", 63.75, "Z+"]],
                      widths=[10, 10, 8], lists={3: ["Z+", "Z-"]}),
        xlsx.NewSheet("Gears", [["Gear", "Teeth"], ["G1", 17], [" padded ", None]]),
    ])
    return path


def test_a_new_workbook_reads_back(tmp_path):
    book = xlsx.read(new_book(tmp_path / "n.xlsx"))
    assert [c.text for c in book.sheet("Shafts").row(3)] == ["S2", "63.75", "Z+"]
    assert book.sheet("Gears").cell(2, 2).text == "17"
    assert book.sheet("Gears").cell(3, 1).text == " padded "


def test_a_new_workbook_has_a_styled_frozen_header_and_lists(tmp_path):
    path = new_book(tmp_path / "n.xlsx")
    with zipfile.ZipFile(path) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
    assert 'state="frozen"' in sheet and 'ySplit="1"' in sheet
    assert f's="{xlsx.HEADER_STYLE}"' in sheet
    assert '<dataValidation type="list"' in sheet and "C2:C501" in sheet and "<formula1>\"Z+,Z-\"</formula1>" in sheet


def test_a_new_workbook_never_overwrites(tmp_path):
    path = new_book(tmp_path / "n.xlsx")
    with pytest.raises(xlsx.XlsxError, match="never overwrites"):
        new_book(path)


# ------------------------------------------------------------------ changing cells in place


def test_only_the_named_cells_change(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    before = parts_of(path)
    result = xlsx.write_cells(str(path), {"Shafts": {"B2": 64, "B3": "131.75 "}})
    assert sorted(result.written) == ["Shafts!B2", "Shafts!B3"] and not result.refused
    after = parts_of(path)
    assert [n for n, _ in after] == [n for n, _ in before]          # same parts, same order
    changed = {n for (n, a), (_, b) in zip(before, after) if a != b}
    assert changed == {"xl/worksheets/sheet1.xml", "xl/workbook.xml"}
    sheet = dict(after)["xl/worksheets/sheet1.xml"].decode()
    for declaration in ('xmlns:mc=', 'mc:Ignorable="x14ac xr"', 'xmlns:x14ac=', 'xr:uid=', 'x14ac:dyDescent'):
        assert declaration in sheet                                  # nothing Excel would "repair"
    assert '<c r="B2"><v>64</v></c>' in sheet
    book = xlsx.read(path)
    assert book.sheet("Shafts").cell(2, 2).text == "64"
    assert book.sheet("Shafts").cell(3, 2).text == "131.75 "
    assert book.sheet("Shafts").cell(2, 4).text == "1.1"            # its neighbour untouched


def test_a_formula_is_never_written_over(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    result = xlsx.write_cells(str(path), {"Shafts": {"C2": 1, "C4": 2, "D5": 3, "B2": 70}})
    reasons = dict(result.refused)
    assert reasons["Shafts!C2"] == "it holds a formula"
    assert reasons["Shafts!C4"] == "it holds a formula"             # the shared formula's child
    assert reasons["Shafts!D5"] == "it is part of an array formula or a data table"
    assert result.written == ["Shafts!B2"]
    sheet = xlsx.read(path).sheet("Shafts")
    assert sheet.cell(2, 3).formula and sheet.cell(2, 3).text == "127.5"


def test_a_new_cell_goes_in_column_order_and_keeps_its_row(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    xlsx.write_cells(str(path), {"Shafts": {"B4": 200, "F2": "note", "A9": "S9"}})
    text = dict(parts_of(path))["xl/worksheets/sheet1.xml"].decode()
    row4 = text[text.index('<row r="4"'):text.index("</row>", text.index('<row r="4"'))]
    assert row4.index('r="A4"') < row4.index('r="B4"') < row4.index('r="C4"')
    assert 'spans=' not in text[text.index('<row r="2"'):text.index('<row r="3"')]
    assert text.index('<row r="5"') < text.index('<row r="9"')
    assert '<dimension ref="A1:F9"/>' in text
    sheet = xlsx.read(path).sheet("Shafts")
    assert sheet.cell(4, 2).text == "200" and sheet.cell(2, 6).text == "note" and sheet.cell(9, 1).text == "S9"


def test_a_styled_cell_keeps_its_style(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    xlsx.write_cells(str(path), {"Shafts": {"D2": 2.5}})
    assert '<c r="D2" s="2"><v>2.5</v></c>' in dict(parts_of(path))["xl/worksheets/sheet1.xml"].decode()


def test_calc_on_load_is_set_in_place(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    xlsx.write_cells(str(path), {"Shafts": {"B2": 64}})
    workbook = dict(parts_of(path))["xl/workbook.xml"].decode()
    assert '<calcPr calcId="191029" fullCalcOnLoad="1"/>' in workbook
    assert workbook.count("calcPr") == 1


def test_calc_pr_is_inserted_where_the_schema_puts_it():
    text = f'<workbook xmlns="{MAIN}"><sheets/><definedNames/><extLst/></workbook>'
    out = xlsx.set_full_calc_on_load(text)
    assert out.index("<definedNames/>") < out.index("<calcPr") < out.index("<extLst/>")


def test_results_is_added_as_a_sheet_of_its_own(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    results = xlsx.NewSheet("Results", [["Shaft", "Speed (rpm)"], ["S1", 1500]], header=False, note="Written by us.")
    xlsx.write_cells(str(path), {}, replace_sheets=[results])
    book = xlsx.read(path)
    assert list(book.sheets) == ["Shafts", "Notes", "Results"]
    assert book.sheet("Results").cell(1, 1).text == "Written by us."
    assert book.sheet("Results").cell(3, 2).text == "1500"
    parts = dict(parts_of(path))
    assert parts["xl/styles.xml"] == f'<styleSheet xmlns="{MAIN}"/>'.encode()   # never touched
    assert 'sheetId="4"' in parts["xl/workbook.xml"].decode()                 # after the highest, 3
    # Replacing it again rewrites the same part rather than adding another.
    xlsx.write_cells(str(path), {}, replace_sheets=[xlsx.NewSheet("Results", [["Shaft"], ["S2"]], header=False)])
    book = xlsx.read(path)
    assert list(book.sheets) == ["Shafts", "Notes", "Results"]
    assert book.sheet("Results").cell(2, 1).text == "S2"


def test_an_open_workbook_is_not_written(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    (tmp_path / "~$w.xlsx").write_bytes(b"owner")
    before = path.read_bytes()
    with pytest.raises(xlsx.Locked, match="Export as"):
        xlsx.write_cells(str(path), {"Shafts": {"B2": 64}})
    assert path.read_bytes() == before
    # Export as… a new file still works while it is open.
    out = tmp_path / "copy.xlsx"
    xlsx.write_cells(str(path), {"Shafts": {"B2": 64}}, out_path=str(out))
    assert xlsx.read(out).sheet("Shafts").cell(2, 2).text == "64"
    assert path.read_bytes() == before


def test_no_temp_file_is_left_behind(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    xlsx.write_cells(str(path), {"Shafts": {"B2": 64}})
    assert sorted(os.listdir(tmp_path)) == ["w.xlsx"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes; Windows keeps only a read-only flag")
def test_files_keep_ordinary_permissions(tmp_path):
    """The temporary file is private (0600); the workbook must not end up that way."""
    path = new_book(tmp_path / "n.xlsx")
    mask = os.umask(0)
    os.umask(mask)
    assert os.stat(path).st_mode & 0o777 == 0o666 & ~mask
    os.chmod(path, 0o640)
    xlsx.write_cells(str(path), {"Gears": {"B2": 18}})
    assert os.stat(path).st_mode & 0o777 == 0o640


# -- found in review (W1) ----------------------------------------------------------------


def one_sheet(tmp_path, sheet_body, name="o.xlsx"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as out:
        out.writestr("[Content_Types].xml", CONTENT_TYPES.replace(
            f'<Override PartName="/xl/worksheets/sheet2.xml" ContentType="{xlsx.WORKSHEET_CONTENT}"/>', ""))
        out.writestr("xl/workbook.xml", f'<workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>'
                                        "<sheet name='S' sheetId='1' r:id='rId1'/></sheets>"
                                        "<calcPr calcId='1' fullCalcOnLoad='0'/></workbook>")
        out.writestr("xl/_rels/workbook.xml.rels",
                     f'<Relationships xmlns="{xlsx.PKG_REL_NS}"><Relationship Id="rId1" '
                     f'Type="{xlsx.WORKSHEET_TYPE}" Target="worksheets/sheet1.xml"/></Relationships>')
        out.writestr("xl/worksheets/sheet1.xml", f"<worksheet xmlns='{MAIN}'>{sheet_body}</worksheet>")
    return path


def test_control_characters_are_escaped_and_read_back(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    xlsx.write_cells(str(path), {"Shafts": {"B2": "a\x0bb\x00c _x0041_"}})
    with zipfile.ZipFile(path) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml")
    __import__("xml.etree.ElementTree").etree.ElementTree.fromstring(sheet)     # still XML
    assert xlsx.read(path).sheet("Shafts").cell(2, 2).text == "a\x0bb\x00c _x0041_"


def test_a_non_finite_number_is_refused(tmp_path):
    with pytest.raises(xlsx.XlsxError, match="finite"):
        xlsx.write_new(str(tmp_path / "n.xlsx"), [xlsx.NewSheet("S", [["A"], [float("nan")]])])


def test_single_quoted_attributes(tmp_path):
    path = one_sheet(tmp_path, "<dimension ref='A1:A1'/><sheetData><row r='1' spans='1:1'><c r='A1'><v>1</v></c>"
                               "</row></sheetData>")
    xlsx.write_cells(str(path), {"S": {"C1": 3}})
    parts = dict(parts_of(path))
    workbook, sheet = parts["xl/workbook.xml"].decode(), parts["xl/worksheets/sheet1.xml"].decode()
    assert workbook.count("fullCalcOnLoad") == 1 and 'fullCalcOnLoad="1"' in workbook
    assert "spans" not in sheet and "ref='A1:C1'" in sheet


@pytest.mark.parametrize("body,why", [
    ("<sheetData><row r='1'><c r='A1'><v>1</v></c></row><row r='1'><c r='B1'><v>2</v></c></row></sheetData>",
     "row 1 twice"),
    ("<sheetData><row r='1'><c r='A1'><v>1</v></c></row><!-- <row r='2'><c r='A2'><v>9</v></c></row> -->"
     "</sheetData>", "comments or CDATA"),
    ("<sheetData><row r='1'><c r='A1' t='inlineStr'><is><t><![CDATA[</c>]]></t></is></c></row></sheetData>",
     "comments or CDATA"),
    ("<sheetData><row r='1'><c r='A1'><v>1</v></c></row><junk/></sheetData>", "not a row"),
])
def test_shapes_excel_never_writes_are_refused_not_mangled(tmp_path, body, why):
    path = one_sheet(tmp_path, body)
    before = path.read_bytes()
    result = xlsx.write_cells(str(path), {"S": {"C1": 3}})
    assert result.written == [] and why in result.refused[0][1]
    assert path.read_bytes() == before


def test_the_safety_net_refuses_a_splice_that_changes_other_cells(tmp_path, monkeypatch):
    path = excel_like(tmp_path / "w.xlsx")
    before = path.read_bytes()
    real = xlsx._splice_cells

    def careless(text, cells):                 # a splice bug: B3 gets lost along the way
        new_text, done, refused = real(text, cells)
        return new_text.replace('<c r="B3"><v>131.75</v></c>', ""), done, refused

    monkeypatch.setattr(xlsx, "_splice_cells", careless)
    with pytest.raises(xlsx.XlsxError, match="B3 would have changed too"):
        xlsx.write_cells(str(path), {"Shafts": {"B2": 64}})
    assert path.read_bytes() == before


def test_a_data_table_range_is_protected(tmp_path):
    path = one_sheet(tmp_path, "<sheetData><row r='1'><c r='A1'><f t='dataTable' ref='A1:B2' dt2D='0' "
                               "dtr='0' r1='C1'/><v>1</v></c></row><row r='2'><c r='B2'><v>2</v></c></row></sheetData>")
    result = xlsx.write_cells(str(path), {"S": {"B2": 5}})
    assert result.written == [] and "data table" in result.refused[0][1]


def test_bad_input_raises_the_modules_own_errors(tmp_path):
    path = one_sheet(tmp_path, "<sheetData><row r='x'><c r='A1'><v>1</v></c></row></sheetData>")
    with pytest.raises(xlsx.XlsxError, match="not a row number"):
        xlsx.read(path)
    path = excel_like(tmp_path / "w.xlsx")
    with pytest.raises(xlsx.XlsxError):
        xlsx.write_cells(str(path), {"Shafts": {"A0": 1}})


def test_saving_over_the_open_workbook_by_its_own_name_is_refused(tmp_path):
    path = excel_like(tmp_path / "w.xlsx")
    (tmp_path / "~$w.xlsx").write_bytes(b"owner")
    with pytest.raises(xlsx.Locked):
        xlsx.write_cells(str(path), {"Shafts": {"B2": 64}}, out_path=str(path))


@pytest.mark.skipif(sys.platform == "win32", reason="a symlink needs a privilege Windows rarely grants")
def test_writing_through_a_symlink_keeps_the_link(tmp_path):
    real = excel_like(tmp_path / "real.xlsx")
    link = tmp_path / "link.xlsx"
    link.symlink_to(real)
    xlsx.write_cells(str(link), {"Shafts": {"B2": 64}})
    assert link.is_symlink()
    assert xlsx.read(real).sheet("Shafts").cell(2, 2).text == "64"


def test_drop_downs_suggest_without_refusing(tmp_path):
    path = new_book(tmp_path / "n.xlsx")
    with zipfile.ZipFile(path) as archive:
        sheet = archive.read("xl/worksheets/sheet1.xml").decode()
    assert '<dataValidation type="list"' in sheet and "showErrorMessage" not in sheet


def test_sheet_names_follow_excels_rules(tmp_path):
    with pytest.raises(xlsx.XlsxError, match="cannot name a sheet"):
        xlsx.write_new(str(tmp_path / "s.xlsx"), [xlsx.NewSheet("Gears/Shafts", [["A"]])])


def test_shared_strings_are_found_through_the_workbooks_links(tmp_path):
    path = tmp_path / "moved.xlsx"
    with zipfile.ZipFile(excel_like(tmp_path / "w.xlsx")) as src, zipfile.ZipFile(path, "w") as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "xl/sharedStrings.xml":
                out.writestr("xl/strings/shared.xml", data)
                continue
            if info.filename == "xl/_rels/workbook.xml.rels":
                data = data.replace(b'Target="sharedStrings.xml"', b'Target="strings/shared.xml"')
            out.writestr(info, data)
    assert xlsx.read(path).sheet("Shafts").cell(2, 1).text == "S1"
