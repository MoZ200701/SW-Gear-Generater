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
| W4 layout part + static assembly, Update SolidWorks, build-again `_r2` | **built and wired; demonstration in progress, review pending.** Probe tier 7 passed on SolidWorks 2026 (a full run of every probe, 69 of 69, `probe/results/latest.json`) and 2024 (32 of 32, `probe/results/sw2024/`), every decision the same; findings set in `bfc9ef5`. Then the interfaces (`a93d6d9`), the record's schema 2 (`1f0548b`), the planning (`cb7e042` layout, `17f4bce` gearbox, `a623610` update), the worker (`afb0c00`, `7ce7a26`, `d0203cd`), the footer and every sentence (`4b128a6`, `8fa0216`), and the window (`ccef692`); the helical phase across Z+/Z− fixed first (`119da25`). A smoke test of the gearbox build, its reuse and Update passed on 2026 (`66fed74`, `probe/results/gearbox-smoke-20261113-191036.log`). The full demonstration (PLAN-WORKBOOK §6's W4 row, on both versions) is running now. Boards and docs brought up to W4: `b215dee`, `649d8db`, `47e4648`. |
| W5 motion | **next.** Its precondition `gear_mate` has passed on both versions, and pairs built by the app were driven through it (`probe/gear_pairs_check.py`): the ring pair's Flip was measured, found wrong, and corrected in `4c8a73a`. PLAN-WORKBOOK §4.4 also needs PLAN-GEARBOX's probe tier 6 items 3–5 (axis-to-axis mates, five or more components, a lock between free components); no tier 6 is written yet (tier 7 inserted five components, but placed and fixed, not mated). |

Suite, measured on a clean `git archive` of `bdc7647` (WSL, 2026-11-13): `PYTHONPATH=src
.venv/bin/python -m pytest -q` → 942 passed, 9 skipped. The `PYTHONPATH` matters in a copy: the venv's
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

1. **Finish the demonstration** (W4-DECISIONS item 10, PLAN-WORKBOOK §6's W4 row) on SolidWorks 2026 and 2024,
   logs committed under `probe/results/`: (a) the 12 : 1 fixture built, the Excel edit S2 X 63.75 → 64.5 with
   G2's teeth 68 → 69 (S3 X following by its formula), Update SolidWorks, measured, then a structural step and
   `_r2` with every earlier file's sha256 and mtime unchanged, and a control that the assembly shows G2's 69
   teeth; (b) a pure move, S2 off the X axis so a move alone keeps every mesh; (c) the risky placements —
   helical across Z+/Z−, herringbones of unequal faces, a ring on a Z− shaft — each mesh with the half-pitch
   negative control. Then update README's "under way and not yet reported" sentence and its versions line.
2. **Review W4** (plan and result) by a Fable subagent, as every phase has been, and fix what it finds.
3. **W5 motion** (PLAN-WORKBOOK §4.4): write and run the tier 6 items it needs first; **if they fail, STOP
   and ask** — the static assembly stays.

Known, not yet acted on (from the W4 boards, 2026-11-13):

- With four footer buttons (Export, Export as…, Build again…, Update SolidWorks) and a sentence long enough to
  wrap, the footer asks Tk for 1095 px, so the window grows to 1119 px instead of 1080: the sentence wraps at a
  fixed 660 px whatever the buttons take. The boards do not show it (HTML lets the sentence narrow).
- After Update, while its changes are unsaved, Build again… is greyed with no word why: the plan's refusal (save
  the part first) is not in the footer when nothing Update cannot carry is pending.

## Rules carried over

- Commits and PRs carry **no Claude co-author or attribution line**.
- Ask before driving GUI windows or Excel, because they steal focus. If Excel is already running, close only the workbook you opened; never quit Excel.
- Each phase's plan and result gets reviewed by a Fable subagent before moving on.
- Screenshots on the Mac: capture by window id (`screencapture -l`), not by region, because a region capture picks up whatever app is in front.
