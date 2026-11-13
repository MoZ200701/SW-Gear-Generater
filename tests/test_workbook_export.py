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


def test_a_formula_is_listed_not_written_and_excel_must_recalculate(tmp_path):
    """The Excel fixture's S3 X is =C3+68: a move writes S2 and leaves S3 to its formula."""
    path = tmp_path / "excel.xlsx"
    shutil.copy(FIXTURES / "excel" / "Reducer_12to1.xlsx", path)
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
