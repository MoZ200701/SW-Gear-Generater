"""Export: the chosen fixes written into the workbook, and the Results sheet (PLAN-WORKBOOK §2, §5; W3)."""

import shutil

import pytest

from gear_generator.workbook import checks, export, fixes, model, schema, xlsx
from test_workbook_model import FIXTURES, reducer, write


def moved(spec, **shaft_x):
    return model.replace(spec, shafts=tuple(model.replace(s, x=shaft_x.get(s.id, s.x)) for s in spec.shafts))


def read(path):
    return model.from_book(xlsx.read(path))


def test_a_move_written_back_checks_clean_and_results_follow(tmp_path):
    path = write(tmp_path, moved(reducer(), S2="64", S3="132"))
    spec, _ = read(path)
    report = checks.check(spec)
    move, _shift = report.fixes["Meshes!A2"]
    done = export.export(str(path), spec, [move], checks.check(fixes.apply(spec, move)))
    assert sorted(done.written) == ["Shafts!C3", "Shafts!C4"] and done.refused == []
    again, diagnostics = read(path)
    assert diagnostics == [] and [s.x for s in again.shafts] == ["0", "63.75", "131.75"]
    assert [d.message for d in checks.check(again).diagnostics if d.is_error] == []
    results = xlsx.read(path).sheet(schema.RESULTS)
    assert results.cell(1, 1).text.startswith("Written by Gear Generator")
    assert [results.cell(2, c).text for c in range(1, 5)] == ["Shaft", "Speed (rpm)", "Turns, seen from +Z",
                                                              "Torque (N·m)"]
    assert [results.cell(r, 2).text for r in (3, 4, 5)] == ["1500", "-375", "125"]
    assert [results.cell(r, 3).text for r in (3, 4, 5)] == ["anticlockwise", "clockwise", "anticlockwise"]
    assert results.cell(5, 4).text == "115.248"
    assert results.cell(8, 1).text == "G1–G2" and results.cell(8, 3).text == "63.75"
    # The reader never reads Results: the gearbox is the same with it there.
    assert again.without_rows() == model.from_book(xlsx.read(path))[0].without_rows()


def results_rows(path):
    """The Results sheet as rows of cell text, row 1 (the note) first."""
    sheet = xlsx.read(path).sheet(schema.RESULTS)
    return [[sheet.cell(r, c).text if sheet.cell(r, c) else "" for c in range(1, sheet.max_col() + 1)]
            for r in range(1, max(r for r, _ in sheet.cells) + 1)]


def test_results_end_with_the_overall_ratio_and_the_box_size(tmp_path):
    """PLAN-WORKBOOK §1: Results holds "the overall ratio and box size". The 12 : 1 example's gears reach from
    G1's tip at X −14.25 (Ø28.5 at 0) to G4's at 184.75 (Ø106 at 131.75), ±53 in Y (G4), and their faces
    from Z 0 (G1, G2: 15 wide at 7.5) to 37 (G3, G4: 20 wide at 27)."""
    path = write(tmp_path, reducer())
    spec, _ = read(path)
    export.export(str(path), spec, [], checks.check(spec))
    rows = results_rows(path)
    at = [r[0] for r in rows].index("Overall")
    assert rows[at][:2] == ["Overall", "Value"]
    assert rows[at + 1][:2] == ["Worked out as", "Parallel train · 2 meshes · 12.000 : 1 · output turns the same way"]
    assert rows[at + 2][:2] == ["Overall ratio (input speed ÷ output speed)", "12"]
    box = [r[0] for r in rows].index(export.RESULTS_BOX)
    assert "outside diameters" in rows[box][0] and "faces" in rows[box][0]
    assert rows[box][1:4] == ["Size (mm)", "From (mm)", "To (mm)"]
    assert rows[box + 1][:4] == ["X", "199", "-14.25", "184.75"]
    assert rows[box + 2][:4] == ["Y", "106", "-53", "53"]
    assert rows[box + 3][:4] == ["Z", "37", "0", "37"]


def test_results_say_so_when_there_is_no_ratio_or_size(tmp_path):
    """No output shaft, and nothing laid out (a planet on a carrier is W7's): a dash, never a guess."""
    spec = reducer()
    spec = model.replace(spec, shafts=(model.replace(spec.shafts[0], mounted_on="S3"),) + spec.shafts[1:2]
                         + (model.replace(spec.shafts[2], role=""),))
    path = write(tmp_path, spec)
    spec, _ = read(path)
    report = checks.check(spec)
    assert report.layout.later and checks.overall_ratio(spec, report) == (None, "", "the gearbox is not checked yet")
    rows = export.results_sheet(spec, report, when="now").rows
    labels = [r[0] if r else "" for r in rows]
    assert rows[labels.index(export.RESULTS_RATIO)][1:] == ["—", "the gearbox is not checked yet"]
    box = labels.index(export.RESULTS_BOX)
    assert rows[box + 1:box + 4] == [[axis, "—", "—", "—"] for axis in "XYZ"]


def test_a_shift_into_a_workbook_without_the_column_adds_its_header(tmp_path):
    sheets = model.to_sheets(moved(reducer(), S2="64", S3="132"))
    gears = sheets[2]
    shift_col = [c.key for c in schema.GEARS.columns].index("profile_shift")
    sheets[2] = xlsx.NewSheet("Gears", [r[:shift_col] + r[shift_col + 1:] for r in gears.rows])
    path = tmp_path / "no-shift.xlsx"
    xlsx.write_new(str(path), sheets)
    spec, _ = read(path)
    _move, shift = checks.check(spec).fixes["Meshes!A2"]
    done = export.export(str(path), spec, [shift], None)
    assert done.added_headers == ["Gears!U1 Profile shift (× m)"]
    again, diagnostics = read(path)
    assert diagnostics == [] and [g.profile_shift for g in again.gears[:2]] == ["0.08455", "0.08455"]
    assert [d.message for d in checks.check(again).diagnostics if d.is_error] == []


@pytest.mark.parametrize("folder", ["excel", "excel-windows"])
def test_a_formula_is_listed_not_written_and_excel_must_recalculate(tmp_path, folder):
    """The Excel fixtures' S3 X is =C3+68: a move writes S2 and leaves S3 to its formula."""
    path = tmp_path / "excel.xlsx"
    shutil.copy(FIXTURES / folder / "Reducer_12to1.xlsx", path)
    xlsx.write_cells(str(path), {"Shafts": {"C3": 64}})            # S2 off by 0.25; S3 follows by formula...
    spec, _ = read(path)                                           # ...once Excel recalculates — until then 131.75
    report = checks.check(spec)
    move = report.fixes["Meshes!A2"][0]
    done = export.export(str(path), spec, [move], report)
    assert "Shafts!C3" in done.written
    assert ("Shafts!C4", "it holds a formula") in done.refused
    assert done.has_formulas


def test_export_as_leaves_the_workbook_untouched(tmp_path):
    path = write(tmp_path, moved(reducer(), S2="64", S3="132"))
    before = path.read_bytes()
    spec, _ = read(path)
    move = checks.check(spec).fixes["Meshes!A2"][0]
    copy = tmp_path / "copy.xlsx"
    done = export.export(str(path), spec, [move], None, out_path=str(copy))
    assert path.read_bytes() == before and done.path == str(copy)
    assert read(copy)[0].shaft("S2").x == "63.75"


def test_the_digest_is_of_the_file_as_written(tmp_path):
    import hashlib
    path = write(tmp_path, reducer())
    spec, _ = read(path)
    done = export.export(str(path), spec, [], checks.check(spec))
    assert done.digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_percentage_cell_takes_a_fraction():
    column = schema.MESHES.column("efficiency")
    assert export._value(column, "97", percent=True) == pytest.approx(0.97)
    assert export._value(column, "97", percent=False) == 97
    assert export._value(schema.GEARS.column("part_name"), "007", percent=False) == "007"


def without_shift_column(spec, path):
    sheets = model.to_sheets(spec)
    shift_col = [c.key for c in schema.GEARS.columns].index("profile_shift")
    sheets[2] = xlsx.NewSheet("Gears", [r[:shift_col] + r[shift_col + 1:] for r in sheets[2].rows])
    xlsx.write_new(str(path), sheets)
    return path


def test_two_fixes_needing_the_same_missing_column_add_one_header(tmp_path):
    path = without_shift_column(moved(reducer(), S2="64", S3="132.5"), tmp_path / "two.xlsx")
    spec, _ = read(path)
    report = checks.check(spec)
    shifts = [report.fixes[m][1] for m in ("Meshes!A2", "Meshes!A3")]
    assert all(shifts)
    done = export.export(str(path), spec, shifts, None)
    assert done.added_headers == ["Gears!U1 Profile shift (× m)"] and done.refused == []
    again, diagnostics = read(path)
    assert diagnostics == [] and all(g.profile_shift for g in again.gears)
    assert [d.message for d in checks.check(again).diagnostics if d.is_error] == []


def resave(path, spec):
    """The workbook saved again as Excel saves: a new file renamed over the old."""
    new = path.with_name("~resave.xlsx")
    xlsx.write_new(str(new), model.to_sheets(spec))
    new.replace(path)


def test_a_fix_lands_on_its_shaft_after_the_rows_are_sorted(tmp_path):
    """Chosen against one read, exported after the user sorted the Shafts sheet in Excel: the edit names S2,
    and S2 is found where it is now."""
    spec = moved(reducer(), S2="64", S3="132")
    path = write(tmp_path, spec)
    first, _ = read(path)
    move = checks.check(first).fixes["Meshes!A2"][0]
    resave(path, model.replace(spec, shafts=tuple(reversed(spec.shafts))))         # S3, S2, S1
    now, _ = read(path)
    assert [s.id for s in now.shafts] == ["S3", "S2", "S1"]
    done = export.export(str(path), now, [move], None)
    assert sorted(done.written) == ["Shafts!C2", "Shafts!C3"]
    again, _ = read(path)
    assert again.shaft("S1").x == "0" and again.shaft("S2").x == "63.75" and again.shaft("S3").x == "131.75"


def test_a_fix_for_an_item_since_deleted_is_refused_and_results_not_written(tmp_path):
    spec = moved(reducer(), S2="64", S3="132")
    path = write(tmp_path, spec)
    first, _ = read(path)
    move = checks.check(first).fixes["Meshes!A2"][0]
    resave(path, model.replace(spec, shafts=spec.shafts[:2]))                       # S3 deleted
    now, _ = read(path)
    done = export.export(str(path), now, [move], checks.check(now))
    assert ("Shafts S3", "S3 is no longer on the Shafts sheet") in done.refused
    assert not done.results and xlsx.read(path).sheet(schema.RESULTS) is None


def test_a_save_since_the_last_read_is_not_written_over(tmp_path):
    import hashlib
    path = write(tmp_path, moved(reducer(), S2="64", S3="132"))
    spec, _ = read(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    move = checks.check(spec).fixes["Meshes!A2"][0]
    xlsx.write_cells(str(path), {"Box": {"B2": "Edited in Excel"}})                 # a save inside the poll
    saved = path.read_bytes()
    with pytest.raises(xlsx.XlsxError, match="changed since it was last read"):
        export.export(str(path), spec, [move], None, expected_digest=digest)
    assert path.read_bytes() == saved


def test_export_as_without_a_good_read_is_disabled_and_says_why(tmp_path):
    """Found on Windows: with the workbook unreadable, Export as… still opened its file dialog and then wrote
    nothing, without a word. It is now disabled with Export, and if a read fails while its dialog is open, the
    footer says why nothing was written. Needs Tk and a display (run on Windows); skipped where there is none."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display for Tk")
    root.withdraw()
    from gear_generator import theme, workbook_gui
    theme.setup(root)

    class App:
        out_folder = tk.StringVar(root, "")
        part_template = tk.StringVar(root, "")

    path = write(tmp_path, reducer())
    window = workbook_gui.WorkbookWindow(root, App(), str(path), poll_ms=10 ** 6)
    try:
        assert window.export_as_button._enabled and window.export_button._enabled
        path.write_bytes(xlsx.OLE_MAGIC + b"\0" * 600)          # no longer a workbook
        window.reread()
        assert window.error
        assert not window.export_as_button._enabled and not window.export_button._enabled
        copy = tmp_path / "copy.xlsx"
        window.export(out_path=str(copy))                         # what Export as… does once its dialog returns
        assert not copy.exists()
        assert window.status.get().startswith("Nothing was exported: ") and "encrypted" in window.status.get()
    finally:
        window.close()
        root.destroy()


# -- the review of W1–W3 (2026-11-13) ----------------------------------------------------------------------


def test_the_box_size_names_what_it_leaves_out(tmp_path):
    """Review repro r3: a bevel gear and a sleeve are not laid out before W6 and W8, so the size cannot count
    them — it says so rather than giving 37 mm in Z as the whole box. A sleeve also makes the ratio depend on
    the modes, so it is withheld."""
    spec = reducer()
    gears = spec.gears + (model.Gear("G5", "S3", "80", "bevel", "external", "40", "3", "", "25", "16"),
                          model.Gear("G6", "S1", "-60", "sleeve", "external", "30", "2", "", "30", ""))
    spec, _ = read(write(tmp_path, model.replace(spec, gears=gears)))
    rows = export.results_sheet(spec, checks.check(spec), when="now").rows
    labels = [r[0] if r else "" for r in rows]
    assert rows[labels.index(export.RESULTS_LEFT_OUT)] == [export.RESULTS_LEFT_OUT,
                                                           "G5 (a bevel gear, phase W6), G6 (a sleeve, phase W8)"]
    assert rows[labels.index(export.RESULTS_RATIO)][1:] == ["—", "it changes with the modes, worked out in phase W8"]


def test_a_meshing_gear_with_an_error_withholds_the_ratio_and_is_named(tmp_path):
    spec = reducer()
    spec = model.replace(spec, gears=(spec.gears[0], model.replace(spec.gears[1], teeth="68.5")) + spec.gears[2:])
    spec, diagnostics = read(write(tmp_path, spec))
    from gear_generator.workbook import assess
    state = assess.assess(spec, diagnostics, "C:\\Parts")
    rows = export.results_sheet(state.spec, state.report, when="now").rows
    labels = [r[0] if r else "" for r in rows]
    assert rows[labels.index(export.RESULTS_RATIO)][1:] == ["—", "G2 meshes but is not laid out"]
    assert rows[labels.index(export.RESULTS_LEFT_OUT)][1] == "G2 (an error of its own)"


def test_the_ratio_names_its_shafts_and_a_whole_box_leaves_nothing_out(tmp_path):
    path = write(tmp_path, reducer())
    spec, _ = read(path)
    rows = export.results_sheet(spec, checks.check(spec), when="now").rows
    labels = [r[0] if r else "" for r in rows]
    assert rows[labels.index(export.RESULTS_RATIO)][1:] == [12.0, "S1 to S3"]
    assert export.RESULTS_LEFT_OUT not in labels


def test_results_failing_after_the_cells_still_says_what_was_written(tmp_path, monkeypatch):
    """Review item 4: two writes. The first stands when the second fails, and the digest is of the file as it
    now is, so the live link knows the write was the app's own."""
    import hashlib
    from gear_generator import ui_text
    from gear_generator.workbook import link
    path = write(tmp_path, moved(reducer(), S2="64", S3="132"))
    spec, _ = read(path)
    move = checks.check(spec).fixes["Meshes!A2"][0]
    real = xlsx.write_cells

    def results_fail(target, changes, replace_sheets=(), out_path=""):
        if replace_sheets:
            raise xlsx.Locked("Reducer_12to1.xlsx is open in Excel, so it cannot be saved from here.")
        return real(target, changes, replace_sheets=replace_sheets, out_path=out_path)

    monkeypatch.setattr(xlsx, "write_cells", results_fail)
    done = export.export(str(path), spec, [move], checks.check(fixes.apply(spec, move)))
    assert sorted(done.written) == ["Shafts!C3", "Shafts!C4"] and not done.results
    assert done.results_error.startswith("Reducer_12to1.xlsx is open in Excel")
    assert done.digest == hashlib.sha256(path.read_bytes()).hexdigest()
    watch = link.Link(str(path))
    watch.own_digest = done.digest
    assert watch.read().own
    text, ok = ui_text.export_note(done)
    assert not ok and text == ("Exported 2 cells. The Results sheet could not be written: Reducer_12to1.xlsx is "
                               "open in Excel, so it cannot be saved from here. Export again to write it.")


@pytest.mark.parametrize("folder", ["excel", "excel-windows"])
def test_a_formula_target_is_named_with_the_value_the_fix_wants(tmp_path, folder):
    """Review item 7a: the formula may land on the fix's value by itself once Excel recalculates; the sentence
    says what to look for, never to type over it, and that Results wait for that save."""
    from gear_generator import ui_text
    path = tmp_path / "excel.xlsx"
    shutil.copy(FIXTURES / folder / "Reducer_12to1.xlsx", path)
    xlsx.write_cells(str(path), {"Shafts": {"C3": 64}})
    spec, _ = read(path)
    report = checks.check(spec)
    done = export.export(str(path), spec, [report.fixes["Meshes!A2"][0]], report)
    assert done.formulas == [("Shafts!C4", "S3", "X", "131.5")] and not done.results
    assert ui_text.export_note(done) == (
        "Exported 1 cell. Shafts!C4 (S3 X) holds a formula, so it was not written (the fix would make it 131.5): "
        "once Excel has recalculated, Checks will say whether S3 sits where its meshes need it. The Results sheet "
        "was left out until then: Export again after Excel's save to write it.", True)
