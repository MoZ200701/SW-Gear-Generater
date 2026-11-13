# The workbook in Excel on Windows (W1–W3's Windows checks), 2026-11-13

PLAN-WORKBOOK's Windows checks for phases W1–W3, which were written and tested on a Mac: an exported
workbook opens in Excel with no repair prompt (W3), a fixture saved by Excel on Windows (§2), the
workbook held open by Excel, and the live link's timing (§5). SolidWorks was not involved.

- **Excel:** Microsoft 365 Apps for enterprise, Excel 16.0.20430.20146 (Current Channel), 64-bit, on
  Windows (NT 10.0). Through COM: `Version` 16.0, `Build` 20430.
- **App:** commit `43524fb`. `run_all.sh` exports HEAD's `src/` into the scratch folder and imports
  it from there, so uncommitted edits in the tree could not leak into the run.
- **Scripts:** `probe/excel/`. Each says what it drives at its top. Rerun with
  `probe/excel/run_all.sh <scratch folder>`.
- **Scratch:** `C:\Users\M0obo\Documents\GearGeneratorProbe\excel-20261113-rerun3\`. Every file
  Excel opened was a copy there.
- **Excel instances:** every Excel the scripts used was one they started, and each was quit.

The record here is the full rerun from the committed scripts at 17:45–17:50. Two earlier runs gave the
same results for everything they shared: 16:26–16:34 in a scratch folder, and 17:28–17:32 from the
committed scripts at `acf5687`. This run adds two write paths, Export adding a column and Export
inserting a `calcPr`. `make_fixture.log` is from the first run: it made the committed fixture.

| File | What it is |
|---|---|
| `run_all.log` | The whole run, as printed |
| `export_checks.json` | Check 1, part one: the exports, then each opened through COM and inspected |
| `user_open.json` | Check 1, part two: each file opened with `EXCEL.EXE /x`, watched for a repair |
| `repair-prompt-control-*.png` | The repair prompt the two broken controls raised. Only Excel's dialog is shown. |
| `locked_checks.json`, `poll-*.jsonl` | Check 3: the file held open by Excel, and the live link's timing |
| `tk_driver.jsonl` | Check 4: the Workbook window's states, as logged |
| `make_fixture.log` | Check 2: how `tests/fixtures/excel-windows/Reducer_12to1.xlsx` was made |

## 1. Exported files open with no repair prompt: passed

**What was exported, and by which code path.**

- The committed Windows fixture was copied, and S2's X was typed as 64 into Shafts!C3 in Excel and
  saved there. Excel recalculated Shafts!C4 (`=C3+68`) to 132.
- The app then read one error, `Meshes!A2: G1 and G2 are 64 apart; their teeth make 63.75
  (+0.25 mm)`, with both fixes on offer:
  - **Move:** "Move S2 and S3 beyond it by -0.25 mm".
  - **Profile shift:** "x +0.084550 / +0.084550 → 64.000 exact · working angle 20.61° · ε 1.62".
- Each export below is the call `WorkbookWindow.export` makes: `export.export(path, read spec,
  [fix], checks.check(read spec with the fix made), out_path, expected_digest=the read's digest)`.

| File | Export | Written | Refused | Results |
|---|---|---|---|---|
| `export-shift.xlsx` | profile-shift fix, in place | Gears!O2, O3 (0.08455) | — | yes |
| `export-move.xlsx` | move fix, in place | Shafts!C3 (63.75) | Shafts!C4, "it holds a formula" | no, by design |
| `export-as (fixed).xlsx` | profile-shift fix, Export as… | Gears!O2, O3 | — | yes; the source file's hash unchanged |
| `Gearbox.xlsx` | New workbook…: `write_new(model.to_sheets(model.template("Gearbox")))` | — | — | — |
| `export-add-column.xlsx` | profile-shift fix into a sheet with no Profile shift column (see below) | **Gears!W1 header "Profile shift (× m)"**, W2, W3 (0.08455) | — | yes |
| `export-calcpr-inserted.xlsx` | move fix into a workbook with no `calcPr` (see below) | Shafts!C3 (63.75), and a `calcPr` inserted | Shafts!C4, "it holds a formula" | no, by design |

**The two extra write paths, and how their sources were made.**

- **Adding a column.** Export writes a missing optional column's header at the end of row 1 before its
  cells (PLAN-WORKBOOK §2).
  - Source: in Excel, the Profile shift column (O) was deleted from a copy of the fixture, S2 typed at
    64, and the file saved. The Gears sheet is therefore Excel's own XML, columns A–V, with Double
    teeth now in V.
  - Export reported `added_headers = ["Gears!W1 Profile shift (× m)"]` and wrote W1, W2 and W3.
  - The dimension widened to `A1:W5`.
  - W1 is an unstyled inline string, `<c r="W1" t="inlineStr">…`, like the user's own added headers
    V1 and U1 beside it. The schema's header cells A1–T1 carry the template's header style, which
    Export does not copy.
- **Inserting a `calcPr`.** Excel always writes a `calcPr`, and so does LibreOffice
  (`tests/fixtures/libreoffice/` has `<calcPr iterateCount="100" …/>`).
  - Source: the absent case was made by a text edit. Excel's own S2-64 file had its
    `<calcPr calcId="191029"/>` cut out of `xl/workbook.xml`, and nothing else changed.
  - The move fix then wrote Shafts!C3, which C4 (`=C3+68`) depends on.
  - Export inserted `<calcPr fullCalcOnLoad="1"/>` at its schema position: after `</sheets>`, before
    `<extLst>`.

**How each was opened, and how "no repair" is known.** Each file was opened as written, before any
Excel had touched it, the way a person opens one: `EXCEL.EXE /x <file>`, a new Excel process of its
own. For 10 s, every top-level window that process showed was recorded. A repair shows up three ways:
the dialog *"We found a problem with some content in '…'. Do you want us to try to recover as much as
we can?"*, "[Repaired]" in the caption, and a new `%TEMP%\error*.xml` recovery log.

The detection is proven by two files broken on purpose, copies of `export-shift.xlsx`:

- `control-etree`: the Shafts sheet re-serialised through `xml.etree`. This is the plan's stated
  reason for splicing the sheet as text, and it does make Excel repair.
- `control-bad-string`: one cell pointing at a shared string that does not exist.

| File (`EXCEL.EXE /x`) | Dialogs | Caption | New recovery log |
|---|---|---|---|
| control-etree | **the repair prompt** (`repair-prompt-control-etree.png`), answered No | Excel | none |
| control-bad-string | **the repair prompt** (`repair-prompt-control-bad-string.png`), answered No | Excel | none |
| export-shift | none | export-shift.xlsx - Excel | none |
| export-move | none | export-move.xlsx - Excel | none |
| export-as (fixed) | none | export-as (fixed).xlsx - Excel | none |
| Gearbox (template) | none | Gearbox.xlsx - Excel | none |
| export-add-column | none | export-add-column.xlsx - Excel | none |
| export-calcpr-inserted | none | export-calcpr-inserted.xlsx - Excel | none |

**The COM caveat.** Opened through COM (`DispatchEx` + `Workbooks.Open`, alerts on), Excel does
**not** show the repair prompt. On both broken controls, `Open` fails at once with 0x800A03EC ("Open
method of Workbooks class failed"). So a COM open that succeeds is weaker evidence; the `EXCEL.EXE`
open is the check.

Opening by `EXCEL.EXE` adds the file to Excel's recent-files list, as a person's open would.

**Inside Excel** (COM, after the open; `export_checks.json`):

- **Formula cells left alone.**
  - In every written file, Shafts!C4's XML is byte-identical to the source:
    `<c r="C4"><f>C3+68</f><v>132</v></c>`.
  - In Excel, C4 is still `=C3+68` and the Double teeth formula in row 3 is still `=F3*2`.
- **Recalculation on open.** C3 was written as 63.75 while C4 still held Excel's last value, 132.

  | File (COM open) | `calcPr` in the file | C4 on opening |
  |---|---|---|
  | `export-move.xlsx` | `<calcPr calcId="191029" fullCalcOnLoad="1"/>`, set in place by Export | **131.75** |
  | `control-no-fullcalc.xlsx` | `<calcPr calcId="191029"/>` (the attribute taken out) | 132, stale |
  | `export-calcpr-inserted.xlsx` | `<calcPr fullCalcOnLoad="1"/>`, inserted by Export | **131.75** |
  | `control-calcpr-calcid-only.xlsx` | `<calcPr calcId="191029"/>` in place of the inserted one | 132, stale |
  | `control-calcpr-removed.xlsx` | none (the inserted one taken out again) | 131.75 |

  - Where the file names this Excel's calc engine (`calcId` 191029, which every Excel-saved file
    does), `fullCalcOnLoad` is what makes the dependent formula recalculate.
  - With no `calcPr` at all, Excel recalculates on opening anyway: it treats a missing `calcId` as an
    older engine. So the inserted element is right, but the absent case would not have gone stale
    without it.
- **Percentage cell:** Meshes!C2 is value 0.98, number format `0%`, and shows "98%" in every file.
  - This is a percent cell *read*. A percent cell *write* is not exercised in Excel: no fix writes
    an efficiency, so Export never reaches one today.
  - That write is covered by unit tests only:
    - `tests/test_workbook_export.py::test_a_percentage_cell_takes_a_fraction`: 97 % is written as
      0.97 into a percent cell;
    - `tests/test_workbook_xlsx.py::test_a_styled_cell_keeps_its_style`: a written cell keeps its `s`
      style, so the format stays.
- **Profile shift:** in `export-shift` and Export as…, Gears!O2 and O3 read 0.08455 under "Profile
  shift (× m)". In `export-add-column`, Excel shows the added column W headed "Profile shift (× m)",
  with 0.08455 in W2 and W3.
- **Results sheet** (shift exports): it is present in Excel and reads as written:
  - speeds 1500 / −375 / 125 rpm, turning anticlockwise / clockwise / anticlockwise;
  - torques 10 / 39.2 / 115.248 N·m;
  - G1–G2: 64 needed, 64 placed, contact ratio 1.6185; G3–G4: 68, 68, 1.6364;
  - Overall: "Worked out as: Parallel train · 2 meshes · 12.000 : 1 · output turns the same way";
    "Overall ratio (input speed ÷ output speed): 12, S1 to S3";
  - box size X 199.3768 (−14.3768 to 185), Y 106 (−53 to 53), Z 37 (0 to 37).
- **Template drop-downs:**
  - Shafts Axis and Role, and Gears Kind, Side, Flank and Hand each carry a list validation (`Type`
    3, in-cell drop-down, no stop alert) with the schema's words.
  - In Kind, "spur" validates as true and "worm" as false.
- **Excel's own save, read back by the app:** `export-shift`, `export-move`, `export-add-column`,
  `export-calcpr-inserted` and the template were saved by Excel, then read by the app (`xlsx.read`,
  `model.from_book`, `checks.check`):
  - `export-shift`: no diagnostics and no errors; shifts 0.08455 / 0.08455; S2 64, S3 132; speeds
    1500 / −375 / 125.
  - `export-add-column`: the same, with the shifts read from the added column W.
  - `export-move` and `export-calcpr-inserted`: also clean, because Excel recalculated C4 to 131.75.
    The move fix's refused cell came right through its formula.
  - The template: no diagnostics.

## 2. A workbook saved by Excel on Windows: committed

`tests/fixtures/excel-windows/Reducer_12to1.xlsx` (`make_fixture.log`) started as our writer's 12 : 1
workbook. In Excel it was given the Mac fixture's edits and saved:

- Shafts!C4 `=C3+68`;
- Shafts row 6 a `#` comment row;
- a Cost column V in Gears;
- "Double teeth" `=F2*2` filled down W2:W5;
- Meshes!C2 0.98 formatted `0%`.

Windows Excel stored the filled-down column as a plain formula in W2 plus one shared formula over
W3:W5; Excel for Mac stored one shared formula over W2:W5. `tests/test_workbook_model.py` and
`tests/test_workbook_export.py` read both fixtures.

## 3. The workbook held open by Excel: passed

All from `locked_checks.json`.

**Reading and writing while Excel has the file:**

- **Lock file:** `~$Reducer_12to1.xlsx` appears beside the workbook while it is open, and is gone
  after Excel closes it.
- **Reading:** `xlsx.read` and `Link.read` both read it with no error; Excel's share mode allows
  reading. `Link.open_in_excel` is True.
- **Export refuses** with the plan's sentence: *"Reducer_12to1.xlsx is open in Excel, so it cannot be
  saved from here. Close it there, or use Export as… to write a new file."* The file is untouched.
- **With the lock-file check bypassed,** the replace itself fails with `PermissionError`, raised as
  `Locked` ("…is open in another program (Excel, most likely)…"). The file is untouched and no temp
  file is left behind.
- **Export as…** writes a new file while the workbook is open.

**The live link's timing.** Excel saved the open workbook repeatedly, toggling Shafts!C3 between
63.75 and 64. `Link.poll` ran in another process:

| Poll | Saves | Change seen after Excel's save returned | Mid-save states caught |
|---|---|---|---|
| 1 s (the window's) | 10 | under 1 s (0.00–0.98 s) | none |
| 20 ms | 15 | within ±0.02 s | none in this run (see below) |

- The 20 ms poll is there to catch Excel mid-save. In this run it caught nothing. Each earlier run
  caught one mid-save state, and each was read cleanly on the next poll:
  - 16:3x: the file briefly absent (`FileNotFoundError`);
  - 17:3x: "cannot be opened right now" (`PermissionError`), then absent.
- A reading can land a few milliseconds before COM's `Save` call returns.
- Each reading's change list was `Shafts!C3 S2 X … → …` and `Shafts!C4 S3 X … → …`.
- Excel's saves took about 0.03 s each.
- No save failed and Excel showed no dialog, so the app's reads never got in the way of Excel's save.
- The plan's "normally within two seconds" holds with room to spare.

## 4. The Workbook window (logged here; screenshots not committed)

`tk_driver.jsonl` is the real Workbook window, opened as Import workbook… opens it, at 96 DPI (Tk
scaling 1.33). An Excel of the script's own saved the file throughout. Each logged state carries the
footer and the button states.

**The states, in order:**

1. Clean.
2. Open in Excel.
3. S2 typed at 64: the error and both fixes, with the change list `Shafts!C3 S2 X 63.75 → 64` and
   `Shafts!C4 S3 X 131.75 → 132`.
4. The shift fix chosen.
5. Export refused while Excel holds the file.
6. Exported: "Exported 2 cells and the Results sheet. Export wrote cells that formulas in the workbook
   may depend on: open and save it in Excel so they recalculate; Build waits for that save.".
7. An outside save, which clears that wait.
8. G2 to 70 teeth.
9. The file made unreadable: Export and Export as… disabled, and "Nothing was exported: …".
10. Restored.

**Latency in the window:** 0.00–0.86 s from save to change list.

The window screenshots stay in the scratch folder. Those of Excel's main window are left out too:
they show the account and the add-ins installed on this machine.
