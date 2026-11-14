## Wound down: the rebuild-route probe was not started on SolidWorks

The follow-up probe does not exist yet. I was still reading the probe code when your wind-down came, so no probe code was written and no probe ran on 2026 or 2024. Nothing is committed for this task, and there is no patch.

**What exists so far** is only the rerun's evidence: commit `8b1ef15` and its repro on 2026, on this run's own saved `b\Arc_Move.SLDASM`. These are the documents marked modified after each call:

| Call | Frame after a put | Interference after a put | Layout move shown | Part change shown | Marked modified |
|---|---|---|---|---|---|
| open (`OpenDoc6` + `ActivateDoc3`) | – | – | – | – | none |
| `interferences()` | – | – | – | – | the assembly only |
| `ForceRebuild3(True)` | not measured | not measured | not measured | not measured | the assembly only |
| `EditRebuild3` | not measured | not measured | not measured | not measured | the assembly only |
| `ForceRebuild3(False)` | not measured | not measured | not measured | not measured | the assembly and every part |

Those flag readings were taken with no put, no layout move and no part change before them. The return values of the rebuilds were not recorded. So questions 1, 2, 3 and 5 are still open on 2026, and nothing has been seen on 2024.

### What the next person must do
1. **Where the probe goes.** Make it a new tier 7 item in `src/gear_generator/probe/p7_workbook.py`, for example `assembly_rebuild_scope`, with `needs=("layout_assembly_reopen", "end_to_end")`. It is about the static assembly that W4's Update changes, so tier 7 keeps the tiers in order; tier 8 builds on tier 7 and needs nothing from it.
2. **The assembly.** Build one per route in its own subfolder, with the app's own code. The quickest route is the demonstration's path: a `GearboxSpec` written in code, then `assess`, `plan_gearbox`, and `swbuild.build_gearbox(px.session, **plan.build_kwargs())`.
   - Use two gears: 17 teeth on S1 at 0, and 68 teeth on S2 at 63.75, module 1.5.
   - Routes: `ForceRebuild3(True)`, `EditRebuild3`, `ForceRebuild3(False)`, plus a fourth with no rebuild at all, to show whether a rebuild is needed after a put.
3. **The steps, per route.** Close and reopen the assembly first, and read every `GetSaveFlag` as the baseline. Then:
   - **(a) A put.** Use a raw `Transform2` put, not `Session.place_component`, which calls `ForceRebuild3(False)` itself. Turn G2 half a pitch, apply the route, read `component_frame` and `interferences()` (G1–G2 must clash), then put it back and apply the route again (clean).
   - **(b) A layout move.** Open the layout by path, set "S2 X" plus 5, and rebuild it in its own document. Read the flags, then activate the assembly and apply the route. Measure S2 Axis in the assembly with `Extension.CreateMeasure` between `S2 Axis@<layout>-1@<asm>` and the assembly's Right Plane.
   - **(c) A part change.** Open G2, set "No. of Teeth" to 69, rebuild it in its own document, then apply the route on the assembly. At its unchanged frame G2 must now clash with G1; the demonstration measured 180.6 mm³. Also compare the assembly's mass-property volume before and after.
   - **(d) A failed rebuild.** Make G2's rebuild fail, for example a face width of 0 if that is a global. Record the route's return value and what is wrong in the assembly, then restore it.
   - Read the flags after every step. The wanted answer: the assembly plus only what was changed on purpose; G1 must stay False.
4. **Closing on 2024.** `scaffold.save_created_parts` saves the probe's own modified documents before `CloseDoc`. On 2024, closing an assembly whose components are modified opened a modal dialog before.
5. **The rest of the pattern.** Copy tier 8's handling (commits `853e91b`, `9aeed80`):
   - a decide function, and a key in `decide.decide`;
   - a constant in `findings.py`, for example `ASSEMBLY_REBUILD_ROUTE` and `ASSEMBLY_REBUILD_KEEPS_COMPONENTS_UNMODIFIED`;
   - a pin in `tests/test_findings.py`, and pure-function tests in `tests/test_probe_workbook.py`.
6. **2026 run.** Start your own 2026 (`C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS (3)\SLDWORKS.exe`). Run the FULL probe for `latest.json` (`--extras --tier 8 --timeout 900`) from a `git archive` snapshot, through `C:\Users\M0obo\Documents\GearGeneratorProbe\w4-rerun-sw2026-20261113-231855\isolate.py`. That launcher keeps the app from seeing any SolidWorks but the given PID; drive it the way `runsnap.sh` runs `probe.py`.
7. **2024 run.** Run only this item and what it needs, with `--only assembly_rebuild_scope`, in the user's session. 2024 is reachable only once your 2026 has exited. Write a timestamped file and a README row in `probe/results/sw2024/`.
8. **Linux suite.** Run it on a clean `git archive HEAD` copy, because the working tree has another agent's uncommitted edits.

### Machine state
- **SolidWorks:** only the user's 2024 is running (PID 52548, 5.54 GB, untouched). My 2026 (PID 11148) was emptied and exited earlier.
- **Other processes:** no Excel and no python.exe of mine; the memory watcher is stopped. 8.1 GB of RAM is free.
- **Git:** HEAD is `8b1ef15`, not pushed. I have nothing untracked or staged; the modified files in the tree are the other agent's.
- **Scratch files:** under `C:\Users\M0obo\Documents\GearGeneratorProbe\w4-rerun-sw2026-20261113-231855\`, which holds `isolate.py`, `mine.py`, `dirty_repro.py` and the run folders.
