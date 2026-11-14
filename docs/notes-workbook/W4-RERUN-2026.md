## W4 rerun on SolidWorks 2026: report

**Verdict: 292 checks passed and 3 failed. All three failures have one cause, and it is in the app, not the scripts.** I changed no script, so there is no script-fix commit.

| Script / section | ok | FAIL |
|---|---|---|
| assembly a | 102 | 2 |
| assembly a2 | 37 | 0 |
| assembly a3 (new) | 36 | 0 |
| assembly b | 64 | 1 |
| assembly c | 43 | 0 |
| **workbook_assembly_check.py** | **282** | **3** |
| **workbook_window_check.py** | **10** | **0** |

Your brief says the earlier window log had 244 checks. That number was the assembly run's; the earlier window log has 1 check. This window run has 10, all passing.

**How it ran**
- Code: a clean `git archive 9aeed80`, copied to `C:\Users\M0obo\Documents\GearGeneratorProbe\w4-rerun-sw2026-20261113-231855\snap`, with the scripts given `snap\src`.
- SolidWorks: 2026 (34.0.0, SP0.0, the `SOLIDWORKS (3)` install), PID 11148, started by me. Excel 16.0 build 20430, PID 59864, the script's own.
- Timings: a 321 s, a2 140 s, a3 151 s, b 149 s, c 236 s, window about 3.5 min.
- **One difference from the earlier method.** The app's `swcom.find_candidates` binds to every SolidWorks it finds and asks each for `RevisionNumber` and `ActiveDoc`. That would have sent calls to your 2024 session. So both scripts ran through a launcher, `...\w4-rerun-sw2026-20261113-231855\isolate.py`, which only lets the app see PID 11148. Nothing else was patched. Both logs show the attach to PID 11148, 2026.
- **Commit** `8b1ef15`: `probe/results/w4-workbook-assembly-20261113-232041.log` and `probe/results/w4-window-20261113-233808.log`. Not pushed, no attribution line.
  - No user document titles appear in either log (the documents open before the run were `[]`), and no name, email or `/home` path. The paths read `C:\Users\M0obo…` as in the earlier committed logs.

### The 3 failures: the app's fault (from review S2's promise)
1. **a:** "SolidWorks marks modified exactly the documents Update changed".
   - After the demonstration Update, all 6 documents were modified, although Update logged "already holds the workbook's values" for Gear_m1.5_N17, Gear_m2_N17 and OutputGear and set only N68 and the layout.
2. **a:** "the superseded G1 part, which Update never changed, is not marked modified". Gear_m1.5_N17 still read True after `_r2`.
3. **b:** "SolidWorks marks modified only the layout and the assembly". Update changed no part, yet all 4 gear parts were marked modified.

**The cause.** `swcom` re-places each component with a `Transform2` put followed by `ForceRebuild3(False)` (about line 1660), and `rebuild()` (line 587) also calls `ForceRebuild3(False)`. With `False`, SolidWorks rebuilds every component, and that marks each one modified.

**Minimal repro** (`...\dirty_repro.py`, run on this run's own saved `b\Arc_Move.SLDASM`, then closed without saving). Documents marked modified after each step:

| Step | Marked modified |
|---|---|
| open the assembly (`OpenDoc6` + `ActivateDoc3`) | none |
| `interferences()` | the assembly only |
| `ForceRebuild3(True)` | the assembly only |
| `EditRebuild3` | the assembly only |
| `ForceRebuild3(False)` | the assembly and all 5 parts |

The earlier `gearbox_smoke` log (20261113-191036) shows the same thing after a build.

**What it means for the user:** after any Update, SolidWorks will ask to save parts that Update never changed. Saving them rewrites those files, including parts that earlier revisions share. The record's own unsaved marks are right: it marks only the 3 documents Update changed.

**Possible fix for the fix agent:** a top-only rebuild (`ForceRebuild3(True)` or `EditRebuild3`) on the assembly, since Update already rebuilds the changed parts and the layout one by one first. I have not checked that a top-only rebuild still picks up the new frames and the layout's changes. That needs a rerun.

### The three assumptions
- **`QuitDoc` in a3:** it closed all six modified documents (assembly first) with no dialog and nothing left open. The check "closed in SolidWorks without saving: left []" passed.
  - The next Update then logged `loaded from disk` with all six documents, `changed == []`, the marks gone, N68's `.gear.json` unmarked at 68 teeth, and the header "built from this version". The build-again plan reused N68.
- **`documents()` lists every document in memory:** it held on real SolidWorks.
  - In a and b, the parts were loaded only as components of the reopened assembly, and Update logged `loaded from disk []`, so every one was listed.
  - After `QuitDoc` it listed none of them, so all six were reported as loaded from disk.
- **N5, the `equation_values` comparison:** no false disagreement.
  - 15 "already holds the workbook's values" across the Updates, and 30 live checks across builds and reuse (including the journal reuse in a3) all agreed, in degrees.
  - The new "evaluates them otherwise" refusal never appeared.

### What else the logs show, as W4-REPORT-FIX3 said they should
- Every build logged `journal written: N paths`, and every Update logged `loaded from disk [...]`.
- a3's journal half passed: two parts were reused at revision 0 with no suffix and checked live first, their `.gear.json` was written at the finish, and the journal was taken out.
- Window state 06 had one save request, with "If SolidWorks closed them without saving, those changes are gone." and "While Gear_m1.5_N68's changes are not saved…", and both buttons on.
- At the end the record was at revision 2 with revision 0 under earlier, the journal empty, the header "built from this version", and N68 reused.
- The screenshots (01–08) are in `...\w4-rerun-sw2026-20261113-231855\window-20261113-233808\shots\`. I looked at 06 and 08 and nothing was clipped.
  - A minor thing for whoever owns the window: in 06 the Gears table shows G2 as "built" while the footer says G2's part will be made new as N69.

### What real SolidWorks did that the fake does not model
- `ForceRebuild3(False)` marking every component modified (the failures above). In the fake, only the documents a call changes are marked.
- SolidWorks 2026 shows small boxes with no title ("Opened 5 Components / Updating Assembly…", and once a template box "Title/Description/Button1…") during opens and builds.
  - DialogWatch logs them as `DIALOG` lines, because it recognises the open-progress box only by its "Opening Component" text.
  - They closed themselves and blocked nothing.

### State left
- **SolidWorks 2026 (PID 11148):** I checked it had no documents open, then sent `ExitApp`. It is gone, and the ROT lists only `SolidWorks_PID_52548`.
- **SolidWorks 2024 (PID 52548):** no COM calls were sent to it, and nothing in it was closed. Its private memory read 5.54 GB throughout.
- **Processes:** no Excel and no python.exe of mine are running. My memory watcher and monitors are stopped.
- **RAM:** free RAM never fell below 6.4 GB; 8.4 GB free at the end. My 2026 instance peaked at 2.02 GB.
- **Scratch files:** under `C:\Users\M0obo\Documents\GearGeneratorProbe\w4-rerun-sw2026-20261113-231855\` (snapshot, run folders, `isolate.py`, `mine.py`, `dirty_repro.py`), plus `...\GearGeneratorProbe\rot_names.py`.
- **Working tree:** it now has uncommitted changes in `src/` and `tests/` (store, swbuild, swcom, ui_text, gearbox, update, workbook_gui and their tests). They are not mine and appeared during my run. I committed only my two log paths, and the snapshot predates them.
