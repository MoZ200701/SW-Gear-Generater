"""The workbook format and the gearbox model (docs/PLAN-WORKBOOK.md §1, §3.1, §3.2)."""

import zipfile

import pytest

from gear_generator.gears import kind_for
from gear_generator.spec import GearSpec
from gear_generator.workbook import model, schema, xlsx
from gear_generator.workbook.model import Box, Gear, GearboxSpec, Mesh, Mode, Shaft

# -- the format, as the plan's §1 writes it down (canvas F lives outside the repo) --


def test_the_columns_are_the_ones_the_plan_settled():
    assert [c.title for c in schema.SHAFTS.columns] == [
        "Shaft", "Mounted on", "X (mm)", "Y (mm)", "Z (mm)", "Axis", "Role", "Copies", "Speed (rpm)",
        "Torque (N·m)", "Notes"]
    assert [c.title for c in schema.GEARS.columns] == [
        "Gear", "Shaft", "At (mm)", "Kind", "Side", "Teeth", "Module (mm)", "Pressure angle (°)",
        "Face width (mm)", "Bore (mm)", "Flank", "Helix angle (°)", "Hand", "Groove (mm)", "Profile shift (× m)",
        "Backlash (mm)", "Fillet (mm)", "Rim (mm)", "Slides", "Part name", "Notes"]
    assert [c.title for c in schema.MESHES.columns] == ["Gear A", "Gear B", "Efficiency (%)", "Notes"]
    assert [s.title for s in schema.BOX_SETTINGS] == [
        "Format", "Name", "Output folder", "Part template", "Assembly template", "Pressure angle (°)",
        "Efficiency per mesh (%)", "Units"]
    assert schema.SHEET_ORDER == ("Box", "Shafts", "Gears", "Meshes", "Modes", "Results")


def test_needed_columns():
    assert {c.key for c in schema.GEARS.columns if c.required} == {"id", "shaft", "teeth", "module", "face_width"}
    assert {c.key for c in schema.SHAFTS.columns if c.required} == {"id", "x", "y"}


@pytest.mark.parametrize("header,key", [
    ("Face width (mm)", "face width"), ("  FACE   width ", "face width"), ("Profile shift (× m)", "profile shift"),
    ("Speed (rpm)", "speed"),
])
def test_headers_match_by_name_without_the_unit(header, key):
    assert schema.header_key(header) == key


@pytest.mark.parametrize("typed,axis", [
    ("Z+", "Z+"), ("z-", "Z-"), ("+Z", "Z+"), ("-z", "Z-"), ("−Z", "Z-"), ("Z", "Z+"), ("x−", "X-"), ("Y+", "Y+"),
])
def test_axis_words(typed, axis):
    assert schema.SHAFTS.column("axis").canonical(typed) == axis


def test_kind_side_and_hand_short_forms():
    assert schema.GEARS.column("kind").canonical("Double") == "herringbone"
    assert schema.GEARS.column("side").canonical("INT") == "internal"
    assert schema.GEARS.column("hand").canonical("l") == "left"
    assert schema.GEARS.column("flank").canonical("worm") is None


# -- the 12 : 1 example -----------------------------------------------------------


def reducer() -> GearboxSpec:
    return GearboxSpec(
        box=Box(name="Reducer_12to1", output_folder="C:\\Parts\\Reducer_12to1\\", pressure_angle="20",
                efficiency="98"),
        shafts=(
            Shaft("S1", "frame", "0", "0", "0", "Z+", "input", "", "1500", "10", "motor"),
            Shaft("S2", "frame", "63.75", "0", "0", "Z+", "", "", "", "", "intermediate"),
            Shaft("S3", "frame", "131.75", "0", "0", "Z+", "output"),
        ),
        gears=(
            Gear("G1", "S1", "7.5", "spur", "external", "17", "1.5", "", "15", "8", notes="pinion"),
            Gear("G2", "S2", "7.5", "spur", "external", "68", "1.5", "", "15", "12"),
            Gear("G3", "S2", "27", "spur", "external", "17", "2", "", "20", "12", notes="turns with G2"),
            Gear("G4", "S3", "27", "spur", "external", "51", "2", "", "20", "16", part_name="OutputGear"),
        ),
        meshes=(Mesh("G1", "G2", notes="stage 1"), Mesh("G3", "G4", notes="stage 2")),
    )


def write(tmp_path, spec, name="Reducer_12to1.xlsx"):
    path = tmp_path / name
    xlsx.write_new(str(path), model.to_sheets(spec))
    return path


def read(path):
    return model.from_book(xlsx.read(path))


def test_the_example_round_trips_through_a_workbook(tmp_path):
    spec, diagnostics = read(write(tmp_path, reducer()))
    assert diagnostics == []
    assert spec.without_rows() == reducer()
    assert [g.row for g in spec.gears] == [2, 3, 4, 5]


def test_a_row_builds_the_strips_gear():
    """Each workbook row becomes exactly the GearSpec the strip would hold for the same values."""
    g1 = reducer().gears[0]
    assert g1.gear_spec(reducer().box) == GearSpec(
        kind="spur", recipe="", module="1.5", teeth="17", pressure_angle="20", face_width="15", bore="8",
        backlash="", fillet="", profile_shift="0", helix_angle="", hand="right", groove="",
        teeth_side="external", rim="", shaft_angle="90", mate_teeth="", name="")
    spec = g1.gear_spec(reducer().box)
    kind = kind_for(spec)
    plan = kind.plan(spec, kind.derive(spec), kind.recipe_for(spec), "", "C:\\Parts\\Gear_m1.5_N17.SLDPRT")
    assert plan.check() == []
    assert spec.stem() == "Gear_m1.5_N17"
    assert reducer().gears[3].gear_spec(reducer().box).stem() == "OutputGear"


def test_blank_cells_take_the_workbooks_defaults_not_gearspecs():
    gear = Gear("G9", "S1", teeth="20", module="2", face_width="10")
    spec = gear.gear_spec(Box(name="B", pressure_angle="25"))
    assert spec.bore == ""                      # no bore — GearSpec() would say 10
    assert spec.pressure_angle == "25"          # the Box's
    assert spec.hand == "right" and spec.teeth_side == "external" and spec.profile_shift == "0"
    assert Gear("G", "S", flank="arcs").gear_spec(Box()).recipe == "B"
    assert Gear("G", "S").gear_spec(Box()).pressure_angle == "20"


# -- reading what a person types --------------------------------------------------


def edit(path, sheet, cells):
    """Change cells the way a person would in Excel: through the in-place writer."""
    xlsx.write_cells(str(path), {sheet: cells})


def messages(diagnostics):
    return [d.message for d in diagnostics]


def test_a_bad_cell_is_named(tmp_path):
    path = write(tmp_path, reducer())
    edit(path, "Gears", {"F3": 68.5, "G4": "two"})
    _, diagnostics = read(path)
    assert "Gears!F3: Teeth must be a whole number (got '68.5')." in messages(diagnostics)
    assert "Gears!G4: Module must be a number (got 'two')." in messages(diagnostics)
    assert all(d.field.startswith("Gears!") for d in diagnostics)


def test_columns_may_be_in_any_order_and_extra_ones_are_ignored(tmp_path):
    sheets = model.to_sheets(reducer())
    gears = sheets[2]
    rows = [list(r) for r in gears.rows]
    for r in rows:                     # Teeth (F) moved to the far right, a Cost column added before it
        r.append("Cost" if r is rows[0] else 3.5)
        r.append(r.pop(5))
    sheets[2] = xlsx.NewSheet("Gears", rows)
    path = tmp_path / "moved.xlsx"
    xlsx.write_new(str(path), sheets)
    spec, diagnostics = read(path)
    assert diagnostics == []
    assert [g.teeth for g in spec.gears] == ["17", "68", "17", "51"]
    edit(path, "Gears", {"V2": 17.5})       # Teeth is now column V, the 22nd
    _, diagnostics = read(path)
    assert messages(diagnostics) == ["Gears!V2: Teeth must be a whole number (got '17.5')."]


def test_comment_and_blank_rows_are_skipped(tmp_path):
    path = write(tmp_path, reducer())
    edit(path, "Shafts", {"A7": "# S4 at 200, 0 for a third stage later", "C7": 200, "A9": "S5", "C9": 1, "D9": 2})
    spec, diagnostics = read(path)
    assert [s.id for s in spec.shafts] == ["S1", "S2", "S3", "S5"]
    assert diagnostics == []


def test_a_formula_reads_as_its_saved_value(tmp_path):
    """Excel stores the result beside the formula; the model only ever sees the result."""
    path = write(tmp_path, reducer())
    text_parts = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            text_parts[info.filename] = archive.read(info.filename)
    sheet = text_parts["xl/worksheets/sheet2.xml"].decode()
    sheet = sheet.replace('<c r="C4"><v>131.75</v></c>', '<c r="C4"><f>C3+68</f><v>131.75</v></c>')
    text_parts["xl/worksheets/sheet2.xml"] = sheet.encode()
    path.unlink()
    with zipfile.ZipFile(path, "w") as out:
        for name, data in text_parts.items():
            out.writestr(name, data)
    spec, diagnostics = read(path)
    assert diagnostics == [] and spec.shaft("S3").x == "131.75"


def test_a_typed_plus_z_is_explained(tmp_path):
    path = write(tmp_path, reducer())
    text_parts = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            text_parts[info.filename] = archive.read(info.filename)
    sheet = text_parts["xl/worksheets/sheet2.xml"].decode()
    sheet = sheet.replace('<c r="F2" t="inlineStr"><is><t>Z+</t></is></c>', '<c r="F2" t="e"><f>+Z</f><v>#NAME?</v></c>')
    text_parts["xl/worksheets/sheet2.xml"] = sheet.encode()
    path.unlink()
    with zipfile.ZipFile(path, "w") as out:
        for name, data in text_parts.items():
            out.writestr(name, data)
    _, diagnostics = read(path)
    assert len(diagnostics) == 1
    assert diagnostics[0].field == "Shafts!F2" and "Pick Z+ or Z- from the list" in diagnostics[0].message


def test_short_words_and_a_percentage_are_read(tmp_path):
    path = write(tmp_path, reducer())
    edit(path, "Gears", {"D2": "Double", "E2": "ext", "L2": 20, "M2": "L"})
    edit(path, "Meshes", {"C2": 0.97})          # a cell formatted as a percentage holds 0.97
    edit(path, "Shafts", {"F3": "-z"})          # arrived as text (typed with a leading apostrophe)
    spec, diagnostics = read(path)
    assert diagnostics == []
    assert (spec.gears[0].kind, spec.gears[0].side, spec.gears[0].hand) == ("herringbone", "external", "left")
    assert spec.meshes[0].efficiency == "97"
    assert spec.shafts[1].axis == "Z-"


def test_an_axis_may_be_three_numbers(tmp_path):
    path = write(tmp_path, reducer())
    edit(path, "Shafts", {"F3": "0, 0.5, 0.866"})
    spec, diagnostics = read(path)
    assert diagnostics == [] and spec.shafts[1].axis == "0, 0.5, 0.866"
    edit(path, "Shafts", {"F3": "sideways"})
    _, diagnostics = read(path)
    assert messages(diagnostics) == ["Shafts!F3: Axis must be Z+, Z-, X+, X-, Y+, Y- or three numbers (got 'sideways')."]


def test_references_between_sheets_are_checked(tmp_path):
    path = write(tmp_path, reducer())
    edit(path, "Gears", {"B5": "S9", "A3": "G1"})
    edit(path, "Meshes", {"B3": "G7"})
    edit(path, "Shafts", {"B3": "S2", "J3": 5})
    _, diagnostics = read(path)
    found = messages(diagnostics)
    assert "Gears!B5: S9 is not a shaft on the Shafts sheet." in found
    assert "Gears!A3: the gear G1 is also on row 2; names must be unique." in found
    assert "Meshes!B3: G7 is not a gear on the Gears sheet." in found
    assert "Shafts!B3: S2 cannot be mounted on itself." in found
    assert any(m.startswith("Shafts!G3: S2 has a speed or torque but is not an input") for m in found)


def test_needed_cells_and_missing_sheets(tmp_path):
    path = write(tmp_path, reducer())
    edit(path, "Gears", {"I3": None})
    edit(path, "Gears", {"K2": None})
    _, diagnostics = read(path)
    assert "Gears!I3: Face width (mm) is needed." in messages(diagnostics)
    _, diagnostics = model.from_book(xlsx.Book())
    assert {d.field for d in diagnostics} >= {"Box", "Shafts", "Gears"}


def test_a_helical_gear_needs_its_helix_angle(tmp_path):
    path = write(tmp_path, reducer())
    edit(path, "Gears", {"D2": "helical"})
    _, diagnostics = read(path)
    assert messages(diagnostics) == ["Gears!L2: G1 is helical and needs a helix angle."]


# -- modes --------------------------------------------------------------------------


def transfer_case() -> GearboxSpec:
    shafts = (Shaft("In", "frame", "0", "0", role="input", speed="1500", torque="10"),
              Shaft("Carrier", "frame", "0", "0"), Shaft("Rear", "frame", "0", "0", role="output"),
              Shaft("FrontDrv", "frame", "0", "0"))
    gears = (Gear("InDog", "In", "50", "dog", teeth="30", module="1.5", face_width="6"),
             Gear("LoDog", "Carrier", "70", "dog", teeth="30", module="1.5", face_width="6"),
             Gear("RangeSlv", "Rear", "60", "sleeve", teeth="30", module="1.5", face_width="8",
                  slides="H=-10, N=0, L=+10"),
             Gear("FrontDog", "FrontDrv", "110", "dog", teeth="30", module="1.5", face_width="6"),
             Gear("ModeSlv", "Rear", "100", "sleeve", teeth="30", module="1.5", face_width="8",
                  slides="2WD=0, 4WD=+10"))
    modes = (Mode("2H", (("RangeSlv", "H"), ("ModeSlv", "2WD")), "road"),
             Mode("4H", (("RangeSlv", "H"), ("ModeSlv", "4WD"))),
             Mode("N", (("RangeSlv", "N"), ("ModeSlv", "2WD")), "towing"),
             Mode("4L", (("RangeSlv", "L"), ("ModeSlv", "4WD")), "crawl"))
    return GearboxSpec(box=Box(name="TransferCase"), shafts=shafts, gears=gears, modes=modes,
                       sliders=("RangeSlv", "ModeSlv"))


def test_modes_round_trip_and_get_their_lists(tmp_path):
    path = write(tmp_path, transfer_case(), "tc.xlsx")
    spec, diagnostics = read(path)
    assert diagnostics == []
    assert spec.without_rows() == transfer_case()
    with zipfile.ZipFile(path) as archive:
        modes = archive.read("xl/worksheets/sheet5.xml").decode()
    assert '<formula1>"H,N,L"</formula1>' in modes and '<formula1>"2WD,4WD"</formula1>' in modes


def test_a_mode_must_pick_a_real_position(tmp_path):
    path = write(tmp_path, transfer_case(), "tc.xlsx")
    edit(path, "Modes", {"B3": "M"})
    _, diagnostics = read(path)
    assert messages(diagnostics) == ["Modes!B3: RangeSlv has no position M; it has H, N, L."]


def test_slides_must_read():
    assert model.parse_slides("H=-10, N=0, L=+10") == {"H": -10.0, "N": 0.0, "L": 10.0}
    assert model.parse_slides("A=−2.5; B=2.5") == {"A": -2.5, "B": 2.5}
    with pytest.raises(ValueError, match="name=offset"):
        model.parse_slides("H -10")
    with pytest.raises(ValueError, match="named twice"):
        model.parse_slides("H=1, H=2")


def test_a_template_reads_back_clean_but_says_there_is_no_input(tmp_path):
    path = write(tmp_path, model.template("NewBox"), "t.xlsx")
    spec, diagnostics = read(path)
    assert spec.box.name == "NewBox" and spec.box.format == "1"
    assert diagnostics == []          # no shafts yet: nothing to warn about


# -- workbooks written by other programs ---------------------------------------------

FIXTURES = __import__("pathlib").Path(__file__).resolve().parent / "fixtures"


def test_a_workbook_saved_by_libreoffice_reads_the_same(tmp_path):
    """tests/fixtures/libreoffice/Reducer_12to1.xlsx: our writer's workbook, opened and saved by LibreOffice
    Calc (headless, `soffice --convert-to xlsx`). Shared strings, a theme, LibreOffice's own namespaces."""
    path = FIXTURES / "libreoffice" / "Reducer_12to1.xlsx"
    spec, diagnostics = read(path)
    assert diagnostics == []
    assert spec.without_rows() == reducer()
    out = tmp_path / "edited.xlsx"
    result = xlsx.write_cells(str(path), {"Shafts": {"C3": 64}, "Gears": {"F3": 70}}, out_path=str(out))
    assert sorted(result.written) == ["Gears!F3", "Shafts!C3"] and not result.refused
    edited, diagnostics = read(out)
    assert diagnostics == [] and edited.shaft("S2").x == "64" and edited.gear("G2").teeth == "70"


def test_a_workbook_saved_by_excel_reads_the_same(tmp_path):
    """tests/fixtures/excel/Reducer_12to1.xlsx: our writer's workbook, opened in Microsoft Excel for Mac 16.03
    and saved after three edits a person would make — Shafts!C4 became the formula =C3+68, Meshes!C2 became
    0.98 formatted as a percentage, and a Cost column was added to Gears (V).

    Checked by hand on 2026-11-13: this file, edited by write_cells (S2 to 64, G2 to 70 teeth, a Results
    sheet added), opened in that Excel with no repair prompt, and C4 recalculated to 132 on opening.
    """
    path = FIXTURES / "excel" / "Reducer_12to1.xlsx"
    book = xlsx.read(path)
    assert book.sheet("Shafts").cell(4, 3).formula and book.sheet("Shafts").cell(4, 3).text == "131.75"
    spec, diagnostics = model.from_book(book)
    assert diagnostics == []
    expected = reducer()
    expected = model.replace(expected, meshes=(model.replace(expected.meshes[0], efficiency="98"),) + expected.meshes[1:])
    assert spec.without_rows() == expected

    out = tmp_path / "edited.xlsx"
    result = xlsx.write_cells(str(path), {"Shafts": {"C3": 64, "C4": 132}, "Gears": {"F3": 70}}, out_path=str(out))
    assert result.refused == [("Shafts!C4", "it holds a formula")]
    edited, diagnostics = read(out)
    assert diagnostics == [] and edited.shaft("S2").x == "64" and edited.gear("G2").teeth == "70"
    assert edited.shaft("S3").x == "131.75"      # the formula's old value, until Excel recalculates and saves
