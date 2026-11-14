# Handoff: the workbook import (branch `workbook`)

Written 2026-11-13 when work paused on the Mac, so it can carry on from
another machine. **`docs/PLAN-WORKBOOK.md` is the plan and the authority**;
this note only says where things stand within it.

## Where it stands

| Phase | State |
|---|---|
| W0–W1 xlsx read/write, model, schema | done, reviewed by a Fable subagent, review fixes in |
| W2 Workbook window, live link, Build parts | done, reviewed, fixes in. The batch build (`swbuild.build_many`) ran on SolidWorks 2024 and 2026 (`208712c`): the 12 : 1 reducer's four parts built, matching strip-built twins; logs `probe/results/w2-build-20261113-164647.log` and `probe/results/sw2024/w2-build-20261113-165706.log`. |
| W3 geometry, phases, kinematics, checks, fixes, Export, Results sheet, two-column window | done, reviewed twice, every review item fixed. The Excel checks passed on Windows: the Windows-saved fixture (`aa86cc7`) reads, and exported files open in Excel with no repair prompt. |
| W4 layout part + static assembly, Update SolidWorks, build-again `_r2` | **built, demonstrated on 2026, reviewed, review fixed (tested on the fake only); the 2024 remainder and a rerun on SolidWorks are open** — see below. Probe tier 7 passed on SolidWorks 2026 (a full run of every probe, 69 of 69, `probe/results/latest.json`) and 2024 (32 of 32, `probe/results/sw2024/`), every decision the same; findings set in `bfc9ef5`. Then the interfaces (`a93d6d9`), the record's schema 2 (`1f0548b`), the planning (`cb7e042` layout, `17f4bce` gearbox, `a623610` update), the worker (`afb0c00`, `7ce7a26`, `d0203cd`), the footer and every sentence (`4b128a6`, `8fa0216`), and the window (`ccef692`); the helical phase across Z+/Z− fixed first (`119da25`). A smoke test of the gearbox build, its reuse and Update passed on 2026 (`66fed74`, `probe/results/gearbox-smoke-20261113-191036.log`). Boards and docs brought up to W4: `b215dee`, `649d8db`, `47e4648`. The demonstration (`5154de1` and before): **SolidWorks 2026 — all of it, 244 checks, 0 failed** (`probe/results/w4-workbook-assembly-20261113-194228.log`, `…-200255-a2.log`, `w4-window-20261113-195843.log`); **SolidWorks 2024 — tier 7, the 12 : 1 build, its measurements and controls, the Excel edit and Update** (`probe/results/sw2024/w4-workbook-assembly-20261113-200555.log`); **not yet on 2024: the structural step and `_r2`, the continued build (a2), the pure-move and risky-placement workbooks (b, c), the window run** — the user's 2024 session ran out of memory; they are to be run in a fresh session. The independent review's fixes followed in two passes: pass 1, worker, planning and record (`042f276`, `9c64960`, `88385f1`, `a6abd5d`, `2b752a1`); pass 2, the window, every sentence and these documents (`a8bb817`, `7dc0d90`, `571cf1a`, `2a4653e`, `94c85d7`, `01b889e`). A second review pass found N1–N6, all fixed (2026-11-13): a part's own name claimed before any suffix (`45173e0`); the held-values check compares evaluated values for the angle unit (`a9d20ab`); every COM action through `swcom._guarded` (`707bfcb`); whose a record is by `samefile`, asked once when its workbook is gone, never laundered by Locate; marks a job can prove cleared; a build's journal (`7de851a`, `d5eecb2`); close anyway / quit anyway, questions and the strip's own build guarded (`d5eecb2`); the demonstration scripts, with a new section `a3` (`fb3bbdc`); the boards (`ae1d208`, `d2cd2d6`). All of these are tested against the fake SolidWorks only and await a rerun of `probe/workbook_assembly_check.py` and `probe/workbook_window_check.py` on SolidWorks. |
| W5 motion | **next.** Its precondition `gear_mate` has passed on both versions, and pairs built by the app were driven through it (`probe/gear_pairs_check.py`): the ring pair's Flip was measured, found wrong, and corrected in `4c8a73a`. PLAN-WORKBOOK §4.4 also needs PLAN-GEARBOX's probe tier 6 items 3–5 (axis-to-axis mates, five or more components, a lock between free components); no tier 6 is written yet (tier 7 inserted five components, but placed and fixed, not mated). |

Suite, measured on a clean `git archive` of `d2cd2d6` (WSL, 2026-11-13): `PYTHONPATH=src
.venv/bin/python -m pytest -q` → 1524 passed, 10 skipped. The window's Tk tests run under Windows Python:
`python.exe -m pytest tests/test_workbook_build.py tests/test_workbook_window.py -q` → 101 (100 passed and 1
"no display for Tk" skip, a known flake that hits a different test each run; rerun). The `PYTHONPATH` matters in a copy: the venv's
editable install otherwise imports the working tree's `src`, uncommitted edits and all.

## What the last two commits did

- `c9a072e` — the W3 review fixes:
  - fixes are keyed by the shaft or gear they edit, not by row
  - Export refuses if the file changed since the last read
  - the move fix works on a multigraph
  - the herringbone hand rule handles mixed axes
  - ring rim clearance, needs-input and free-shaft errors, loop-conflict warnings
  - an idler shaft carries 0 torque
  - **the herringbone phase counts from the apex**, where the part's section is drawn (`helical.face_rotations`). It used to count from the front face, which was wrong for unequal face widths; there is a geometry test that fails on the old twist.
- The commit after it:
  - the design boards are redrawn as the W3 two-column window. `design/canvas/gen.py` now imports the window's own sizes from `workbook_gui`, and adds two new boards, `WorkbookFix` and `WorkbookChosen`.
  - the Speeds lines and the end-view readout moved into `ui_text` (`workbook_speed_lines`, `end_view_readout`), so the window and the boards share them.
  - the move fix's title now names a single onward shaft: "Move S2 and S3 beyond it".

## Small loose ends (Mac-side, optional)

- ~~`design/UI-DESIGN.md` §9 still describes the W2 single-column window plus a "W3 adds" list. Rewrite it for the two-column window and mention the `WorkbookFix` and `WorkbookChosen` boards (renders in `design/renders/`).~~ Done in `dd39d41`.
- ~~In the end view, a shaft label can sit on top of the origin arrows (the S1 label in the renders). This is cosmetic, and the app draws it the same way.~~ Done in `6716126`: `preview.layout_gearbox` places each name clear of the arrows, for the window and the boards.
- ~~README.md and `docs/PLAN-GEARBOX.md` §1 do not mention the workbook (PLAN-WORKBOOK, Critical files).~~ Done in `af59668` and `d2b82a9`.

## Next

W1–W3 are closed and reviewed. For W4, in order:

1. **Rerun the demonstration on SolidWorks** with both reviews' fixes in: `probe/workbook_assembly_check.py`
   (now sections a, a2, a3, b, c) and `probe/workbook_window_check.py` on 2026, and on 2024 in a fresh session —
   there, for the first time, the structural step and `_r2`, a2, a3, b, c and the window run. Commit the logs
   under `probe/results/`. Three things only a rerun shows: that `ISldWorks::QuitDoc` closes a modified
   document without a dialog (a3 relies on it; DialogWatch logs one if not), that `documents()` lists every
   document SolidWorks holds in memory (the marks a job settles rely on it), and that `equation_values` of a
   reopened document agrees with the maths (the held-values check: section a's "marks modified exactly the
   documents Update changed" fails if it does not).
2. **W5 motion** (PLAN-WORKBOOK §4.4): probe tier 8 (`p8_motion`, `c53bc2d`) is written; its findings wait for
   a full run. **If it fails, STOP and ask** — the static assembly stays. The review's notes for W5: the
   gear-mate Flip was measured only on parallel, same-direction axes (Z+/Z− pairs and rings on Z− need their
   own probe before relying on `GEAR_MATE_EXTERNAL_FLIP`), and gears on one shaft keep independent turns in the
   static assembly, so W5's lock between them holds the placed relative angle, not 0.

Both items once listed here as known are fixed: the footer's sentence wraps in the room the buttons leave, so
the window keeps 1080 px with four buttons (`8453348`), and Build again… is no longer greyed for an unsaved
part at all — such a part is made new (review B2, `88385f1`), and the footer says so (`7dc0d90`).

## Rules carried over

- Commits and PRs carry **no Claude co-author or attribution line**.
- Ask before driving GUI windows or Excel, because they steal focus. If Excel is already running, close only the workbook you opened; never quit Excel.
- Each phase's plan and result gets reviewed by a Fable subagent before moving on.
- Screenshots on the Mac: capture by window id (`screencapture -l`), not by region, because a region capture picks up whatever app is in front.
