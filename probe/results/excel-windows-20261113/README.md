# The workbook in Excel on Windows (W1–W3's Windows checks), 2026-11-13

PLAN-WORKBOOK's Windows checks for phases W1–W3, which were written and tested on a Mac: an exported
workbook opens in Excel with no repair prompt (W3), a fixture saved by Excel on Windows (§2), the
workbook held open by Excel, and the live link's timing (§5). SolidWorks was not involved.

- **Excel:** Microsoft 365 Apps for enterprise, Excel 16.0.20430.20146 (Current Channel), 64-bit, on
  Windows (NT 10.0). Through COM: `Version` 16.0, `Build` 20430.
- **App:** commit `acf5687`. `run_all.sh` exports HEAD's `src/` into the scratch folder and imports
  it from there, so uncommitted edits in the tree could not leak into the run.
- **Scripts:** `probe/excel/`. Each says what it drives at its top. Rerun with
  `probe/excel/run_all.sh <scratch folder>`.
- **Scratch:** `C:\Users\M0obo\Documents\GearGeneratorProbe\excel-20261113-rerun2\`. Every file
  Excel opened was a copy there.
- **Excel instances:** every Excel the scripts used was one they started, and each was quit.

The record here is the full rerun from the committed scripts at 17:28–17:32. An earlier run from the
same scripts in a scratch folder (16:26–16:34) gave the same results. `make_fixture.log` is from that
earlier run: it made the committed fixture.

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

**The COM caveat.** Opened through COM (`DispatchEx` + `Workbooks.Open`, alerts on), Excel does
**not** show the repair prompt. On both broken controls, `Open` fails at once with 0x800A03EC ("Open
method of Workbooks class failed"). So a COM open that succeeds is weaker evidence; the `EXCEL.EXE`
open is the check.

Opening by `EXCEL.EXE` adds the file to Excel's recent-files list, as a person's open would.

**Inside Excel** (COM, after the open; `export_checks.json`):

- **Formula cells left alone.**
  - In every written file, Shafts!C4's XML is byte-identical to the source:
    `<c r="C4"><f>C3+68</f><v>132</v></c>`.
  - In Excel, C4 is still `=C3+68` and the shared formula Gears!W3 is still `=F3*2`.
- **Recalculation on open comes from `fullCalcOnLoad`.**
  - Every written file has `<calcPr calcId="191029" fullCalcOnLoad="1"/>`.
  - In `export-move.xlsx`, C3 is 63.75 and C4 still holds Excel's last value, 132. On opening, C4
    showed **131.75**.
  - A control copy with only `fullCalcOnLoad` removed (`control-no-fullcalc.xlsx`) showed the stale
    **132**. The attribute is what recalculates.
- **Percentage cell:** Meshes!C2 is value 0.98, number format `0%`, and shows "98%".
- **Profile shift:** Gears!O2 and O3 read 0.08455 under the header "Profile shift (× m)".
- **Results sheet** (shift exports): it is present in Excel and reads as written:
  - speeds 1500 / −375 / 125 rpm, turning anticlockwise / clockwise / anticlockwise;
  - torques 10 / 39.2 / 115.248 N·m;
  - G1–G2: 64 needed, 64 placed, contact ratio 1.6185; G3–G4: 68, 68, 1.6364;
  - then an Overall section (the script reads only the first 11 rows, so its lines are not recorded).
- **Template drop-downs:**
  - Shafts Axis and Role, and Gears Kind, Side, Flank and Hand each carry a list validation (`Type`
    3, in-cell drop-down, no stop alert) with the schema's words.
  - In Kind, "spur" validates as true and "worm" as false.
- **Excel's own save, read back by the app:** `export-shift`, `export-move` and the template were
  saved by Excel, then read by the app (`xlsx.read`, `model.from_book`, `checks.check`):
  - `export-shift`: no diagnostics and no errors; shifts 0.08455 / 0.08455; S2 64, S3 132; speeds
    1500 / −375 / 125.
  - `export-move`: also clean, because Excel recalculated C4 to 131.75. The move fix's refused cell
    came right through its formula.
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
| 1 s (the window's) | 10 | 0.01–0.94 s | none |
| 20 ms | 15 | within ±0.02 s | once: "cannot be opened right now" (`PermissionError`), then briefly absent, then read cleanly on the next poll |

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
6. Exported: "Exported 2 cells and the Results sheet. Open and save the workbook in Excel so its
   formulas recalculate…".
7. An outside save, which clears that wait.
8. G2 to 70 teeth.
9. The file made unreadable: Export and Export as… disabled, and "Nothing was exported: …".
10. Restored.

**Latency in the window:** 0.07–0.97 s from save to change list.

The window screenshots stay in the scratch folder. Those of Excel's main window are left out too:
they show the account and the add-ins installed on this machine.
