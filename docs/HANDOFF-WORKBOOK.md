# Handoff: the workbook import (branch `workbook`)

Rewritten the night of 2026-11-13, when work on the Windows host was wound down so it can carry on from
another machine. **`docs/PLAN-WORKBOOK.md` is the plan and the authority**; this note only says where things
stand within it. The working papers of the session (plans, reviews, reports) are in `docs/notes-workbook/`
and are named below where they matter. Where one of them names a script such as `w4x_….py` or `w5r_….py`,
that was a throwaway repro in a temp folder and was not kept; the fixes' regression tests replace them.

## Where it stands

| Phase | State |
|---|---|
| W0–W1 xlsx read/write, model, schema | done, reviewed, review fixes in |
| W2 Workbook window, live link, Build parts | done, reviewed, fixes in. The batch build (`swbuild.build_many`) ran on SolidWorks 2024 and 2026 (`208712c`); logs `probe/results/w2-build-20261113-164647.log` and `probe/results/sw2024/w2-build-20261113-165706.log`. |
| W3 geometry, phases, kinematics, checks, fixes, Export, Results sheet, two-column window | done, reviewed twice, every item fixed. The Excel checks passed on Windows: the Windows-saved fixture (`aa86cc7`) reads, and exported files open in Excel with no repair prompt. |
| W4 layout part + static assembly, Update SolidWorks, build-again `_r<n>` | **built and reviewed three times; one fault found on SolidWorks is open, and the last fix pass is unverified.** Details below. |
| W5 motion | **probes passed on both versions; plan written and reviewed ("go with these changes"); no code yet.** Details below. |
| W6 right-angle, W7 planetary, W8 sleeves and modes | not started; each needs its own sub-plan. |

Suite, measured on a clean `git archive` of `2250ceb` (WSL, 2026-11-13): `PYTHONPATH=src .venv/bin/python -m
pytest -q` → **1559 passed, 10 skipped**. The window's Tk tests run under Windows Python: `python.exe -m
pytest tests/test_workbook_build.py tests/test_workbook_window.py -q` → 102 passed, 1 skipped (a "no display
for Tk" skip is a known flake that moves between tests; rerun). The `PYTHONPATH` matters in a copy: the
venv's editable install otherwise imports the working tree's `src`, uncommitted edits and all.

## W4 in detail

**What exists.** Probe tier 7 passed on SolidWorks 2026 (a full run, `probe/results/latest.json` at the time)
and 2024 (`probe/results/sw2024/`), every decision the same; findings set in `bfc9ef5`. Then the interfaces
(`a93d6d9`), the record's schema 2 (`1f0548b`), the planning (`cb7e042` layout, `17f4bce` gearbox, `a623610`
update), the worker (`afb0c00`, `7ce7a26`, `d0203cd`), the footer and every sentence (`4b128a6`, `8fa0216`),
the window (`ccef692`), boards and docs (`b215dee`, `649d8db`, `47e4648`); the helical phase across Z+/Z−
was fixed first (`119da25`), and the ring pair's gear-mate Flip in `4c8a73a`.

**Demonstrated before the reviews** (`5154de1` and before): SolidWorks 2026 — all of it, 244 checks, 0
failed (`probe/results/w4-workbook-assembly-20261113-194228.log`, `…-200255-a2.log`,
`w4-window-20261113-195843.log`); SolidWorks 2024 — tier 7, the 12 : 1 build, its measurements and
controls, the Excel edit and Update only (`probe/results/sw2024/w4-workbook-assembly-20261113-200555.log`).
The user's 2024 session ran out of memory then; they have restarted it since.

**Reviews and fixes.** Three independent reviews, four fix passes:

- review 1 → pass 1, worker, planning and record (`042f276`, `9c64960`, `88385f1`, `a6abd5d`, `2b752a1`),
  and pass 2, the window, every sentence and the docs (`a8bb817`, `7dc0d90`, `571cf1a`, `2a4653e`,
  `94c85d7`, `01b889e`). Rulings: `notes-workbook/W4-DECISIONS.md`, `W4-REVIEW-RULINGS.md`.
- review 2 (N1–N6) → pass 3 (`45173e0`, `a9d20ab`, `707bfcb`, `7de851a`, `d5eecb2`, `fb3bbdc`, `ae1d208`,
  `d2cd2d6`, `d37ae52`): a part's own name claimed before any suffix; the held-values check compares
  evaluated values; every COM action through `swcom._guarded`; whose a record is, by the file, and asked
  once when its workbook is gone; marks a job can prove cleared; a build's journal; close anyway / quit
  anyway; the demonstration's new section a3. Report: `notes-workbook/W4-REPORT-FIX3.md`.
- review 3 (`notes-workbook/W4-REVIEW-3.md`: the 200-document cap that could clear an unsaved mark, a file
  id of 0 making two workbooks one, the journal wiped by any refused job, a false sentence after "No") →
  pass 4 (`f335379`, `2250ceb`). Report: `notes-workbook/W4-REPORT-FIX4.md`. **Pass 4 has not been verified
  by a reviewer**, and it was wound down early: its code and tests are complete and green, but four boards'
  `.dc.html` were regenerated without redrawing their PNGs in `design/renders/` (`WorkbookCloseAnyway`,
  `WorkbookMoved`, `WorkbookUnsaved`, `WorkbookUpdated`).

**The rerun on SolidWorks 2026** (code at `9aeed80`, that is pass 3 without pass 4; logs in `8b1ef15`;
report `notes-workbook/W4-RERUN-2026.md`): **292 checks passed, 3 failed, all three from one fault in the
app.** After an Update, SolidWorks marks every part modified, including parts Update never changed, because
the app rebuilds an assembly with `ForceRebuild3(False)` (`swcom.py`: `rebuild()` and the re-place of a
component), which rebuilds every component. So SolidWorks would ask to save parts nothing changed, parts
shared with earlier revisions among them. A repro on a saved assembly showed `ForceRebuild3(True)` and
`EditRebuild3` marking the assembly only. The fake SolidWorks does not model this. What only SolidWorks
could confirm did hold: `QuitDoc` closed modified documents without a dialog, `documents()` listed every
document in memory, and the value comparison never disagreed falsely. Journal reuse and the marks clearing
(section a3) passed.

**Open for W4, in order:**

1. **The rebuild fault.** Probe first (the house rule): which assembly rebuild still shows a put's new
   frame, the layout's moved axes and a changed part, while leaving unchanged components unmodified. Nothing
   of this probe is written; `notes-workbook/W4-REBUILD-PROBE-TODO.md` says exactly what to build and run
   (a new tier-7 item, on 2026 and 2024). Then change the two rebuild sites, teach the fake that a full
   rebuild marks every component modified, and add the regression test.
2. **A brief independent verification of pass 4** (`git diff 8b1ef15..f335379`).
3. **Rerun both demonstration scripts** (`probe/workbook_assembly_check.py`,
   `probe/workbook_window_check.py`) on SolidWorks 2026, and on 2024 in a fresh session — there, for the
   first time, the structural step and `_r2`, a2, a3, b, c and the window run. Commit the logs. The 2026
   rerun went through a launcher that lets the app see only one SolidWorks process, because
   `swcom.find_candidates` asks every running SolidWorks for its version and the user's 2024 was running;
   that launcher was a scratch file on the host and has to be written again (`W4-RERUN-2026.md`, "How it
   ran"). Pass 4 added one expectation a rerun must confirm: a document just opened from its file reads
   `GetSaveFlag` False.
4. Redraw the four board PNGs. Then W4 can be called closed.

**Known and left:** a journaled assembly (an interrupted build that had got as far as saving the assembly)
forces a whole `_r<n>`, and its layout part and assembly stay in the journal; with two SolidWorks sessions
running, a document left unsaved in the other session cannot be seen.

## W5 in detail

**Probes.** Tier 8 (`probe/p8_motion.py`: `c53bc2d`, `b9ddb12`; results `853e91b`; findings `9aeed80`)
passed on SolidWorks 2026 (a full run of every probe, 75 of 75, `probe/results/latest.json`) and 2024 (tier
8 alone, 31 of 31), every decision the same; no STOP trigger fired. Report:
`notes-workbook/W5-PROBE-REPORT.md` (one misstatement in it: a mate was deleted by "Select2 then
EditDelete()", as the results record, not by `DeleteSelection2`). In short: a gear's axis is mated
*coincident* with the layout's shaft axis (concentric is refused); one gear per shaft is held that way and
along the shaft, and every other gear on the shaft is held to it by a lock mate alone; every gear mate
takes Flip False; a 12 : 1 train driven 30° turned its output 2.5° the right way, all Z+ and with a Z−
middle shaft. **No API drag reproduces a mouse drag**, so W5's "drag the input" has to be watched by a
person; the API-side proof is a temporary driving mate.

**Plan.** `notes-workbook/W5-PLAN.md`, reviewed in `notes-workbook/W5-PLAN-REVIEW.md` (the review was cut
short; it lists what it did not check). Verdict: go with these changes. Before any code:

- M1: when Update puts gears back, put every mated gear of the train and test locks exactly (the plan's
  "modulo pitch" skip leaves a lock holding the wrong angle after the user turns the input by whole teeth);
- M2: a sign error in the planned tests and the driven proof (`k == ω_b/ω_a`, `δ_i = 30°·ω_i/ω_in`: speeds
  are about each shaft's own axis);
- M3: the plan names `9aeed80` as its base; it builds on the W4 fixes above, so the interface commit comes
  after them;
- M4: probes to add to the plan's two (changing a saved gear mate's ratio; a lock re-taken after a move
  along the shaft): renaming a lock mate, the demonstration's drive geometry, and a put on a gear in two
  gear mates of an undriven train.

M5–M13 are to be decided while implementing or by the user (below). PLAN-WORKBOOK §4.4 still says
"concentric", "locked by an angle mate" and "each gear mated to its axis", and names PLAN-GEARBOX tier 6;
the probes found otherwise. W5-PLAN §0.4 has the text for a dated note; it is not yet added.

## Questions waiting for the user

1. **W5, when SolidWorks refuses a mate:** fall back to the static assembly automatically (the plan), or
   stop and say why (the review: a refusal repeats every time, so the fallback would be permanent)?
2. **W5, Update returns a train the user turned to its built position** whenever it has to move any gear.
   Acceptable?
3. **W5, face-width and At changes on a shaft's first gear** would need Build again… where W4 took an
   Update, because in the fixtures that gear's front face sits on the layout's Front plane. The review
   offers a datum plane far behind in the layout part so the distance never reaches zero (it needs a small
   probe). Which?
4. List passed checks in the Checks panel as the plan says, or keep problems only?
5. Scrub the old document title from `probe/results/probe-results-20260914-180426.*` (it is already in
   public history)?
6. Readings the user may overrule: Update SolidWorks does not save; a part keeps its file name after a
   teeth change; one build button; no static option in the window once W5 is in.

## Rules carried over

- Commits and PRs carry **no Claude co-author or attribution line**. Commit by explicit path only
  (`git add <paths>`; `git commit -m "…" -- <paths>`), prose messages with the why; never `add -A`,
  `commit -a`, stash or reset. Push only when the user says so.
- **The repo is public**: no user document titles in committed logs (`<user document N>`), no other
  personal data.
- Each phase's plan and result is reviewed by a separate subagent before moving on. In the 2026-11-13
  session the user asked for Opus subagents only, with no cap on their number.
- Every SolidWorks call is probed before the app depends on it; findings are read from committed
  `findings.py` only. The plan's STOP-and-ask triggers apply.
- **SolidWorks runs only on the Windows host.** SolidWorks 2024 there is the user's live session: record
  the open titles before a run, close only documents the run created, never save, close or modify theirs,
  never exit it, stop under 2 GB of free RAM, and prefer a freshly restarted session for long runs (one
  long probe run grew it by about 5 GB). An agent may start and exit its own SolidWorks 2026. One driver at
  a time.
- Excel on the Windows host may be opened: use only an Excel the run starts, close only the workbook you
  opened, never quit the user's Excel.
- Screenshots on the Mac: capture by window id (`screencapture -l`), not by region, because a region
  capture picks up whatever app is in front.
