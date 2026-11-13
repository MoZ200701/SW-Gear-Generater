r"""Check 1, part one (drives real Excel through COM): Export's files, and what Excel makes of them.

From the committed Windows fixture: S2 typed at 64 in Excel and saved; then the window's Export code path
(export.export with the report of the read with the fix made, and the read's digest) writes the
profile-shift fix and the move fix into copies, Export as… writes a new file, and New workbook…'s
write_new writes a template. Controls: the move export with fullCalcOnLoad stripped, and two files broken
on purpose (a sheet re-serialised by xml.etree; a shared-string index out of range). Pristine copies go
to <scratch>\export\pristine for user_open.py.

Each file is then opened by COM and inspected: C4's formula and recalculated value, the percentage cell,
Gears!O, the Results sheet, the template's validation lists; three are saved by Excel and read back by the
app. Note: a COM open does NOT show Excel's repair prompt — Workbooks.Open fails at once (0x800A03EC) on
the broken controls — so the repair check proper is user_open.py. Writes <scratch>\export_checks.json.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from xml.etree import ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlhelp import FIXTURE, ROOT, Excel, log  # noqa: E402

from gear_generator.workbook import checks, export, fixes, model, xlsx  # noqa: E402

OUT = os.path.join(ROOT, "export")
if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
results = {}


def sha(path):
    with open(path, "rb") as h:
        return hashlib.sha256(h.read()).hexdigest()


def p(name):
    return os.path.join(OUT, name)


def app_read(path):
    spec, diagnostics = model.from_book(xlsx.read(path))
    report = checks.check(spec)
    return spec, diagnostics, report


def part(path, name):
    with zipfile.ZipFile(path) as z:
        return z.read(name).decode("utf-8")


def cell_xml(path, sheet_part, ref):
    m = re.search(rf'<c r="{ref}"[^>]*?(?:/>|>.*?</c>)', part(path, sheet_part))
    return m.group(0) if m else None


def errors(report_or_diags):
    return [d.message for d in report_or_diags if d.is_error]


xl = Excel(visible=True)
try:
    # -- the S2 = 64.00 case, typed in Excel as a person would: C4 (=C3+68) recalculates to 132.
    s2 = p("S2-64.xlsx")
    shutil.copy(FIXTURE, s2)
    wb, rep = xl.open(s2, "s2-64-setup")
    wb.Worksheets("Shafts").Range("C3").Value = 64
    results["setup C4 after typing"] = wb.Worksheets("Shafts").Range("C4").Value
    wb.Save()
    wb.Close(SaveChanges=False)
    del wb
    spec, diagnostics, report = app_read(s2)
    results["S2-64 read"] = {"diagnostics": [d.message for d in diagnostics], "errors": errors(report.diagnostics),
                             "S2 x": spec.shaft("S2").x, "S3 x": spec.shaft("S3").x,
                             "fixes": {k: [(f.title, f.detail, [e.__dict__ for e in f.edits]) for f in v]
                                       for k, v in report.fixes.items()}}
    move, shift = report.fixes["Meshes!A2"]
    s2_digest = sha(s2)

    def window_export(path, fix, out_path=""):
        """WorkbookWindow.export's call, with the window's report: the read with the chosen fix made."""
        spec_now, _, _ = app_read(path)
        effective = fixes.apply(spec_now, fix)
        return export.export(path, spec_now, [fix], checks.check(effective), out_path=out_path,
                             expected_digest=sha(path))

    # (a) Export, in place, each fix on its own copy.
    shutil.copy(s2, p("export-shift.xlsx"))
    done = window_export(p("export-shift.xlsx"), shift)
    results["export shift"] = done.__dict__
    shutil.copy(s2, p("export-move.xlsx"))
    done = window_export(p("export-move.xlsx"), move)
    results["export move"] = done.__dict__
    # (b) Export as… a new file: the workbook itself is untouched.
    done = window_export(s2, shift, out_path=p("export-as (fixed).xlsx"))
    results["export as"] = dict(done.__dict__, source_untouched=sha(s2) == s2_digest)
    # (c) New workbook…: the template.
    xlsx.write_new(p("Gearbox.xlsx"), model.to_sheets(model.template("Gearbox")))

    # The formula cell left alone, byte for byte, in each written file.
    c4_before = cell_xml(s2, "xl/worksheets/sheet2.xml", "C4")
    for name in ("export-shift.xlsx", "export-move.xlsx", "export-as (fixed).xlsx"):
        results[f"C4 xml in {name}"] = [cell_xml(p(name), "xl/worksheets/sheet2.xml", "C4"),
                                        cell_xml(p(name), "xl/worksheets/sheet2.xml", "C4") == c4_before]
        results[f"calcPr in {name}"] = re.findall(r"<calcPr[^>]*>", part(p(name), "xl/workbook.xml"))

    # Controls.
    shutil.copy(p("export-move.xlsx"), p("control-no-fullcalc.xlsx"))
    def rewrite(path, name, change):
        with zipfile.ZipFile(path) as z:
            items = [(i, z.read(i.filename)) for i in z.infolist()]
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for info, data in items:
                z.writestr(info, change(data) if info.filename == name else data)
    rewrite(p("control-no-fullcalc.xlsx"), "xl/workbook.xml", lambda d: d.replace(b' fullCalcOnLoad="1"', b""))
    shutil.copy(p("export-shift.xlsx"), p("control-etree.xlsx"))
    rewrite(p("control-etree.xlsx"), "xl/worksheets/sheet2.xml",
            lambda d: ElementTree.tostring(ElementTree.fromstring(d), encoding="utf-8", xml_declaration=True))
    shutil.copy(p("export-shift.xlsx"), p("control-bad-string.xlsx"))
    rewrite(p("control-bad-string.xlsx"), "xl/worksheets/sheet2.xml",
            lambda d: re.sub(rb'(<c r="A2"[^>]*t="s"[^>]*><v>)\d+', rb"\g<1>9999", d, count=1))

    # Pristine copies, as Export wrote them, for opening the way a person does (user_open.py).
    os.makedirs(p("pristine"), exist_ok=True)
    for name in os.listdir(OUT):
        if name.endswith(".xlsx"):
            shutil.copy2(p(name), os.path.join(p("pristine"), name))

    # -- open each in Excel.
    opened = {}
    for name in ("control-etree.xlsx", "control-bad-string.xlsx", "export-shift.xlsx", "export-move.xlsx",
                 "export-as (fixed).xlsx", "Gearbox.xlsx", "control-no-fullcalc.xlsx"):
        wb, rep = xl.open(p(name), name.split(".")[0].replace(" ", "_"))
        opened[name] = rep
        if wb is None:
            continue
        seen = {}
        if name != "Gearbox.xlsx":
            sh, me = wb.Worksheets("Shafts"), wb.Worksheets("Meshes")
            seen["Shafts C3"] = sh.Range("C3").Value
            seen["Shafts C4 formula/value"] = [sh.Range("C4").Formula, sh.Range("C4").Value]
            seen["Gears W3 formula/value"] = [wb.Worksheets("Gears").Range("W3").Formula,
                                              wb.Worksheets("Gears").Range("W3").Value]
            seen["Meshes C2 value/text/format"] = [me.Range("C2").Value, me.Range("C2").Text,
                                                   me.Range("C2").NumberFormat]
            gears = wb.Worksheets("Gears")
            seen["Gears O1..O3"] = [gears.Range(r).Value for r in ("O1", "O2", "O3")]
            seen["sheets"] = [s.Name for s in wb.Worksheets]
            if "Results" in seen["sheets"]:
                rs = wb.Worksheets("Results")
                seen["Results"] = [[rs.Cells(r, c).Text for c in range(1, 7)] for r in range(1, 12)]
        else:
            seen["sheets"] = [s.Name for s in wb.Worksheets]
            lists = {}
            for sheet_name in ("Shafts", "Gears"):
                ws = wb.Worksheets(sheet_name)
                for col in range(1, 25):
                    header = ws.Cells(1, col).Text
                    if not header:
                        continue
                    cell = ws.Cells(2, col)
                    try:
                        v = cell.Validation
                        lists[f"{sheet_name}!{header}"] = {"type": v.Type, "list": v.Formula1,
                                                           "dropdown": v.InCellDropdown, "stop": v.ShowError}
                    except Exception:  # noqa: BLE001 - no validation on this cell
                        pass
            seen["validation"] = lists
            kind = wb.Worksheets("Gears").Range("D2")
            kind.Value = "spur"
            ok_valid = kind.Validation.Value
            kind.Value = "worm"
            bad_valid = kind.Validation.Value
            kind.ClearContents()
            seen["Kind 'spur' valid / 'worm' valid"] = [ok_valid, bad_valid]
            seen["frozen"] = None
        results[f"in Excel: {name}"] = seen
        if name in ("export-shift.xlsx", "export-move.xlsx", "Gearbox.xlsx"):
            wb.Save()                                  # Excel's own save, then the app reads it back
        wb.Close(SaveChanges=False)
        del wb
        if name in ("export-shift.xlsx", "export-move.xlsx", "Gearbox.xlsx"):
            spec2, diags2, report2 = app_read(p(name))
            results[f"app reads Excel's save of {name}"] = {
                "diagnostics": [d.message for d in diags2], "errors": errors(report2.diagnostics),
                "warnings": [d.message for d in report2.diagnostics if not d.is_error],
                "S2 x": spec2.shaft("S2").x if spec2.shaft("S2") else None,
                "S3 x": spec2.shaft("S3").x if spec2.shaft("S3") else None,
                "shifts": [g.profile_shift for g in spec2.gears],
                "C4 xml": cell_xml(p(name), "xl/worksheets/sheet2.xml", "C4"),
                "speeds": {k: str(v) for k, v in report2.motion.speeds.items()},
            }
    results["opened"] = opened
finally:
    xl.quit()

with open(os.path.join(ROOT, "export_checks.json"), "w", encoding="utf-8") as h:
    json.dump(results, h, indent=1, default=str, ensure_ascii=False)
log("wrote export_checks.json")
