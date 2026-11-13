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
| W4 layout part + static assembly | **in progress on Windows**: probe tier 7 (`p7_workbook.py`, `8ef3943`) is written and being run; no results are committed yet. Its gate is built: `workbook.assess.Assessment.lay_out_refusal()`. |

Suite (WSL, 2026-11-13): `.venv/bin/python -m pytest -q` → 942 passed, 7 skipped; the 4 tier-7 tests in
`tests/test_findings.py` fail until that run's findings are committed.

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

## Next: W4 (on Windows)

Read PLAN-WORKBOOK §4.2–§4.3 and the W4 row in §6:

1. **Finish probe tier 7** (`p7_workbook.py`, being run now), on scratch documents like every tier, and commit its results and findings. **If any of items 1–4 fails, STOP and ask the user.**
2. Then build the layout part, the `Axis`-by-name op, the static assembly, Update SolidWorks, and build-again `_r2`. Gate the W4 button on `Assessment.lay_out_refusal()` (after the window's own state: a file gone, Excel yet to recalculate, a build running), never on the parts alone.

## Rules carried over

- Commits and PRs carry **no Claude co-author or attribution line**.
- Ask before driving GUI windows or Excel, because they steal focus. If Excel is already running, close only the workbook you opened; never quit Excel.
- Each phase's plan and result gets reviewed by a Fable subagent before moving on.
- Screenshots on the Mac: capture by window id (`screencapture -l`), not by region, because a region capture picks up whatever app is in front.
