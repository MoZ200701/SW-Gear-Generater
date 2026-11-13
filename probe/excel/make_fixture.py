r"""Check 2 (drives real Excel): how tests/fixtures/excel-windows/Reducer_12to1.xlsx was made.

Our writer's 12 : 1 workbook (tests/test_workbook_model.py's reducer(), repeated here so the Windows
Python needs no test imports) is opened in Excel and given the Mac fixture's edits — Shafts!C4 =C3+68, a
# comment row, a Cost column, "Double teeth" =F2*2 filled down, Meshes!C2 0.98 formatted 0% — and saved
by Excel. The result is written to <scratch>\fixture\; copying it into tests/fixtures is a manual step.
"""

import json
import os
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlhelp import ROOT, Excel, log  # noqa: E402

from gear_generator.workbook import model, xlsx  # noqa: E402
from gear_generator.workbook.model import Box, Gear, GearboxSpec, Mesh, Shaft  # noqa: E402


def reducer():      # tests/test_workbook_model.py's reducer()
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


folder = os.path.join(ROOT, "fixture")
os.makedirs(folder, exist_ok=True)
path = os.path.join(folder, "Reducer_12to1.xlsx")
if os.path.exists(path):
    os.remove(path)
xlsx.write_new(path, model.to_sheets(reducer()))
shutil.copy(path, os.path.join(folder, "ours-before-excel.xlsx"))

xl = Excel(visible=True)
try:
    wb, report = xl.open(path, "fixture-ours")
    assert wb is not None and not report["repaired"], report
    shafts, gears, meshes = wb.Worksheets("Shafts"), wb.Worksheets("Gears"), wb.Worksheets("Meshes")
    shafts.Range("C4").Formula = "=C3+68"
    shafts.Range("A6").Value = "# spare row for a third stage"
    shafts.Range("C6").Value = 200
    gears.Range("V1").Value = "Cost"
    gears.Range("V2").Value = 3.5
    gears.Range("W1").Value = "Double teeth"
    gears.Range("W2").Formula = "=F2*2"
    gears.Range("W2:W5").FillDown()
    meshes.Range("C2").Value = 0.98
    meshes.Range("C2").NumberFormat = "0%"
    wb.Worksheets("Box").Activate()
    info = {
        "excel": xl.version,
        "os": xl.app.OperatingSystem,
        "C4": [shafts.Range("C4").Formula, shafts.Range("C4").Value],
        "W5": [gears.Range("W5").Formula, gears.Range("W5").Value],
        "Meshes C2 text": meshes.Range("C2").Text,
    }
    wb.Save()
    wb.Close(SaveChanges=False)
    del wb, shafts, gears, meshes
    log("saved", json.dumps(info))
finally:
    xl.quit()

with zipfile.ZipFile(path) as z:
    parts = {n: z.read(n).decode("utf-8", "replace") for n in z.namelist()}
for n in parts:
    print("part", n, len(parts[n]))
print(parts["docProps/core.xml"])
print(parts["docProps/app.xml"])
import re  # noqa: E402
print(re.findall(r"<c r=\"W\d\".*?</c>", parts["xl/worksheets/sheet3.xml"]))
print(re.findall(r"<c r=\"C4\".*?</c>", parts["xl/worksheets/sheet2.xml"]))
print(re.findall(r"<calcPr[^>]*>|absPath[^>]*>", parts["xl/workbook.xml"]))
book = xlsx.read(path)
spec, diagnostics = model.from_book(book)
print("diagnostics", diagnostics)
print("S3 x", spec.shaft("S3").x, "mesh eff", spec.meshes[0].efficiency, "shafts", [s.id for s in spec.shafts])
