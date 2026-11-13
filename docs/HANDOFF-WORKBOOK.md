# Handoff: the workbook import (branch `workbook`)

Written 2026-11-13 when work paused on the Mac, so it can carry on from
another machine. **`docs/PLAN-WORKBOOK.md` is the plan and the authority**;
this note only says where things stand within it.

## Where it stands

| Phase | State |
|---|---|
| W0–W1 xlsx read/write, model, schema | done, reviewed by a Fable subagent, review fixes in |
| W2 Workbook window, live link, Build parts | done, reviewed, fixes in. **The SolidWorks batch build (`swbuild.build_many`) has never run on Windows.** |
| W3 geometry, phases, kinematics, checks, fixes, Export, Results sheet, two-column window | done, reviewed, every review item fixed (commit `c9a072e` and the one after it) |
| W4 layout part + static assembly | **next — needs the Windows machine** |

Suite: `.venv/bin/python -m pytest -q` → 881 passed, 1 skipped (Mac).

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

- `design/UI-DESIGN.md` §9 still describes the W2 single-column window plus a "W3 adds" list. Rewrite it for the two-column window and mention the `WorkbookFix` and `WorkbookChosen` boards (renders in `design/renders/`).
- In the end view, a shaft label can sit on top of the origin arrows (the S1 label in the renders). This is cosmetic, and the app draws it the same way.

## Next: W4 (on Windows)

Read PLAN-WORKBOOK §4.2–§4.3 and the W4 row in §6:

1. **Probe tier 7 first** (`p7_workbook.py`), on scratch documents like every tier, and commit its results. **If any of items 1–4 fails, STOP and ask the user.**
2. While on Windows, also run W2's untested batch build: import `tests/fixtures/excel/Reducer_12to1.xlsx` via **Import workbook…** and press **Build parts**.
3. Then build the layout part, the `Axis`-by-name op, the static assembly, Update SolidWorks, and build-again `_r2`.

## Rules carried over

- Commits and PRs carry **no Claude co-author or attribution line**.
- Ask before driving GUI windows or Excel, because they steal focus. If Excel is already running, close only the workbook you opened; never quit Excel.
- Each phase's plan and result gets reviewed by a Fable subagent before moving on.
- Screenshots on the Mac: capture by window id (`screencapture -l`), not by region, because a region capture picks up whatever app is in front.
