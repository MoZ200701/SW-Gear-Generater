# Handoff: the workbook import (branch `workbook`)

Rewritten the night of 2026-11-13, when work on the Windows host was wound down so it can carry on from
another machine. **`docs/PLAN-WORKBOOK.md` is the plan and the authority**; this note only says where things
stand within it. The working papers of the session (plans, reviews, reports) are in `docs/notes-workbook/`
and are named below where they matter. Where one of them names a script such as `w4x_….py` or `w5r_….py`,
that was a throwaway repro in a temp folder and was not kept; the fixes' regression tests replace them.

**Updated 2026-11-14**, on the Windows host again (a WSL clone, with SolidWorks 2026 and 2024 both started and
exited by the agents): W4 was closed and W5 begun. The dated paragraphs below say what changed; the user's
answers of that day and the rulings that follow from them are in `notes-workbook/W5-DECISIONS.md`.

## Where it stands

| Phase | State |
|---|---|
| W0–W1 xlsx read/write, model, schema | done, reviewed, review fixes in |
| W2 Workbook window, live link, Build parts | done, reviewed, fixes in. The batch build (`swbuild.build_many`) ran on SolidWorks 2024 and 2026 (`208712c`); logs `probe/results/w2-build-20261113-164647.log` and `probe/results/sw2024/w2-build-20261113-165706.log`. |
| W3 geometry, phases, kinematics, checks, fixes, Export, Results sheet, two-column window | done, reviewed twice, every item fixed. The Excel checks passed on Windows: the Windows-saved fixture (`aa86cc7`) reads, and exported files open in Excel with no repair prompt. |
| W4 layout part + static assembly, Update SolidWorks, build-again `_r<n>` | **closed 2026-11-14**: the rebuild fault probed and fixed, pass 4 verified, both demonstrations rerun on SolidWorks 2026 and 2024 with every check passing, each step reviewed. Details and what is left open below. |
| W5 motion | **in progress**: the user's answers recorded, probe package P0 run and reviewed (round P0b/P0c running), the interface commit in and reviewed (`2f82a0e`, `07fd66a`), packages A, B, C and D written; the demonstration on SolidWorks (package E) waits for P0b. Details below. |
| W6 right-angle, W7 planetary, W8 sleeves and modes | not started; each needs its own sub-plan. |

Suite, measured on a clean `git archive` of `2250ceb` (WSL, 2026-11-13): `PYTHONPATH=src .venv/bin/python -m
pytest -q` → **1559 passed, 10 skipped**. On the 2026-11-14 clone (another Python, fewer skips): 1699 passed, 1
skipped at `8504856`, where W4 closed; 1759 passed, 1 skipped at the W5 interface commit `07fd66a`. At `aa9c5f0` (packages A–D in, the window and boards of D): 2079 passed, 1 skipped; the Tk tests
under Windows Python 109–110 passed of 111, the rest the known display flake, a different test each run. The window's Tk tests run under Windows Python: `python.exe -m
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

   *2026-11-14: done as far as code goes.* The probe is `assembly_rebuild_scope` (`e79e863`, `6d0b1bb`); it
   passed in a full run on 2026, now 34.1.1 (76 of 76, `latest.json`), and alone on 2024 (27 of 27,
   `sw2024/probe-results-20261114-014813`), every decision the same (`9b9f546`): every route, even no rebuild,
   showed the put, the layout move and the changed part; `ForceRebuild3(True)` marked only what changed and
   returned False on a failed component; `ForceRebuild3(False)` marked every component. Findings in `e57aca7`
   (`ASSEMBLY_REBUILD_ROUTE` and the rest). The fix is `9c39fb8`, narrowed after its review: `swcom.rebuild_call`
   is the one place that decides, and the CALLER says which of three kinds of assembly it is, refused with a
   sentence when it does not. A part rebuilds as always. STATIC (fixed components: today's workbook gearbox)
   takes `ASSEMBLY_REBUILD_ROUTE`, top-only, which it requires: unsettled, a build or Update refuses before
   changing anything. TRAIN (W5's mated workbook gearbox, any plan with a `Mate` op built outside `build_pair`;
   nothing builds one yet) takes `MATED_ASSEMBLY_REBUILD_ROUTE`, full while None (set to the top-only route by W5's probes in
   `8504856`; `notes-workbook/W5-DECISIONS.md` says what that does and does not yet cover). PAIR (everything `build_pair`
   makes, and the p5 half-pitch controls) keeps the full `ForceRebuild3(False)` probe tiers 4 and 5 ran, whatever
   the train's finding says, since that is measured on other mates; an absent `PAIR_ASSEMBLY_REBUILD_ROUTE` is
   where a later pair probe could change it. The probe tried no mate and no assembly equation. The fake
   marks what the probe saw for the static route (a full rebuild marks every component, top-only the
   assembly, a put nothing; the reads after a put or a build mark the assembly, which the fake pins on the interference check though the probe did not isolate it); it models nothing unprobed.
   Since the review of `31d1ac9` an assembly's kind must always be said, and a pair's gate is back before its
   gears. **What the SolidWorks rerun (step 3) must still confirm:** the three checks the 2026 rerun failed
   now pass under the demonstration's corrected invariant (marked modified = `GearboxUpdate.changed` ∪ the
   assembly when Update rebuilt it or ran the interference check: `changed` keeps meaning content changed);
   the new part-only Update step in b; after a fresh build no part or layout part reads `GetSaveFlag` True and
   the assembly does (the reads after its save mark it — frame reads and/or the interference check, not yet
   isolated: the rerun logs the flags after each as fact lines, and an extra probe step is to settle it — with
   nothing to lose by not saving it); a document just opened from its file reads False. Still unprobed for
   the static route, and shown only by that rerun: a put
   and its top-only rebuild under `set_rebuild_suppressed(True)` (Update places with `CommandInProgress` on); an
   assembly BUILT with the top-only route; whether the assembly still reports needing a rebuild after the
   route; and a part opened alone by path reading `GetSaveFlag` False.
2. **A brief independent verification of pass 4** (`git diff 8b1ef15..f335379`).

   *2026-11-14: verified* (`notes-workbook/W4-REVIEW-PASS4.md`). It found one fault outside the diff, of the
   same kind as review 3's item 2: Export as… could write over another file on a volume whose file ids are all
   0. Fixed in `8bd2530`.
3. **Rerun both demonstration scripts** (`probe/workbook_assembly_check.py`,
   `probe/workbook_window_check.py`) on SolidWorks 2026, and on 2024 in a fresh session — there, for the
   first time, the structural step and `_r2`, a2, a3, b, c and the window run. Commit the logs. The 2026
   rerun went through a launcher that lets the app see only one SolidWorks process, because
   `swcom.find_candidates` asks every running SolidWorks for its version and the user's 2024 was running;
   that launcher was a scratch file on the host and has to be written again (`W4-RERUN-2026.md`, "How it
   ran"). Pass 4 added one expectation a rerun must confirm: a document just opened from its file reads
   `GetSaveFlag` False.

   *2026-11-14: rerun done, every check passed on both versions*, from a `git archive` snapshot of `9ac36c5`
   (the app as of `388c8d3`, with `findings.py` as of `8504856`, whose new values only the train kind reads and
   W4 never builds; `cross_version_open_check.py` as committed with these logs), one SolidWorks at a time, each started for the run and exited
   after it (no launcher needed). `workbook_assembly_check.py`: 322 of 322 on 2026 (34.1.1,
   `probe/results/w4-workbook-assembly-20261114-053855.log`) and 322 of 322 on 2024 (32.5.0, all five sections
   for the first time, `sw2024/w4-workbook-assembly-20261114-055924.log`), exit 0 both. `workbook_window_check.py`:
   10 of 10 on each (`w4-window-20261114-055011.log`, `sw2024/w4-window-20261114-061023.log`).
   `gear_pairs_check.py` on 2026: spur, ring, crown and internal all ok, as before the three kinds
   (`gear-pairs-20261114-055230.log`). The three checks the 2026 rerun failed now pass; after a build no part
   or layout part is marked and the assembly is; the part-only Update in b marks G2's part and the rebuilt
   assembly, the record the part alone; every document reads `GetSaveFlag` False straight after a reopen. The
   new fact lines isolate what marks the assembly: the frame reads leave every flag False, `interferences()`
   marks the assembly (six reopens on each version). A gearbox saved by 2024 and opened in 2026
   (`probe/cross_version_open_check.py`, `w4-cross-version-2024-in-2026-*.log`): every document reads False
   straight after the open and no file changes; but `QuitDoc` on each such assembly raised a modal "SOLIDWORKS
   CAM Warning: Save changes to <assembly>?" from the CAM add-in. The flag was read only straight after the
   open, not again before the close, so what it read when the prompt came up is not known. The agent running
   the script dismissed each prompt from outside it: a separate Python helper found the dialog's "&No" button
   and posted it `BM_CLICK`; nothing was saved and the files compared equal afterwards. The logs have no trace
   of the dialog (that script has no dialog watcher), and the commit message of `64f4620` calls this "answered
   No by hand". A 2026-made assembly closed by `QuitDoc` in a3 raised none. The app never closes a document,
   so it cannot meet this prompt; a person closing a 2024-saved gearbox in 2026 will. The first 2026 attempt stopped at a script fault
   (a local shadowing the new `marked()`), kept as `w4-workbook-assembly-20261114-053142-stopped-by-a-script-fault.log`.
4. Redraw the four board PNGs. Then W4 can be called closed.

   *2026-11-14: redrawn* (`41b92eb`, `3dd5ec8`).

**W4 was closed on 2026-11-14**, after an independent review of the rerun (its points on the notes and the
scripts are in `eb5dff5`). The reviews of that day found these and left them open; none blocks W4:

- **Whether the assembly still reports needing a rebuild after the top-only route** was never read, and a put
  with its top-only rebuild under `set_rebuild_suppressed(True)` was shown only by the reruns, not by a probe.
  `PUT_NEEDS_REBUILD` is False in `findings.py` but **not established**: nothing may skip a rebuild on it.
  Extra steps for probe `assembly_rebuild_scope` are planned.
- **A journaled file on a drive that is disconnected is treated as gone** (`W4-REVIEW-PASS4.md`). A design call
  for the user.
- Probe `assembly_rebuild_scope`'s own limits, from its review: its "shown" readings could not tell the routes
  apart (every route showed every change), and the failed-rebuild case was tried only on a failing part.

**Known and left:** a journaled assembly (an interrupted build that had got as far as saving the assembly)
forces a whole `_r<n>`, and its layout part and assembly stay in the journal; with two SolidWorks sessions
running, a document left unsaved in the other session cannot be seen.

## W5 in detail

*Rewritten 2026-11-14, after packages A–D.* The authority order is `PLAN-WORKBOOK.md` → `notes-workbook/W5-DECISIONS.md`
→ `W5-PLAN-REVIEW.md` → `W5-PLAN.md`; the shapes the packages share are pinned in `notes-workbook/W5-INTERFACES.md`.

**Probes.** Tier 8 (`probe/p8_motion.py`: `c53bc2d`, `b9ddb12`; results `853e91b`; findings `9aeed80`) passed on
SolidWorks 2026 (75 of 75) and 2024 (31 of 31), every decision the same. Report: `notes-workbook/W5-PROBE-REPORT.md`
(one misstatement: a mate was deleted by "Select2 then EditDelete()", not `DeleteSelection2`). A gear's axis is mated
*coincident* with the layout's shaft axis (concentric is refused); one gear per shaft, the anchor, is held that way and
along the shaft, every other gear on it by a lock mate alone; every gear mate takes Flip False; a 12 : 1 train driven
30° turned its output 2.5° the right way. No API drag reproduces a mouse drag: "drag the input" is a person's step, and
the API proof is a temporary driving mate. PLAN-WORKBOOK §4.4 now carries this as a dated note (*Readings changed by
probe tier 8*), and §6's W5 row says "once probe tier 8 has passed".

**Plan and decisions.** `notes-workbook/W5-PLAN.md`, reviewed in `W5-PLAN-REVIEW.md` (M1–M13). The user's answers of
2026-11-14 and the rulings on the review and on P0 are in `W5-DECISIONS.md` and in PLAN-WORKBOOK §4.5 as *Readings
chosen (W5)*: a refused mate stops the build (no static fallback); Update returns a turned train to its built turn
only when it must move a gear of it; no datum plane, so an anchor's Front-plane edits need Build again…; a follower's
place along its shaft is an Update; a tooth change that alters a gear mate's ratio needs Build again… until the ratio
route is probed; W4 static gearboxes stay static; a recorded mate found suppressed is turned back on.

**Probe package P0** (`0d638db` … `8504856`, rulings `0551abc`) ran tier 8 items 7–13 on both versions and was
reviewed. **Round P0b/P0c is running** (`7c48d84`, `4ced012` and the probe agent's uncommitted results): a train
*built* under the top-only rebuild, the ratio remake in a fresh 2024 session (P1b), and the tooth change as an Update
does it. The probe agent is about to commit `GEAR_MATE_RATIO_ROUTE = "remake"`; until it does, a tooth change on a
turning gearbox is Build again…. Every package's tests pin the findings they depend on, so they pass either way.

**Interface commit** `2f82a0e`, its review's rulings `07fd66a` (`W5-INTERFACES.md` §6). The packages, each reviewed:

- **A — SolidWorks** (`swcom.py`, `swbuild.py`, the fake): `e231ae3` (the train's mate members from tier 8),
  `6ffc84a` (the fake learns mates), `171a50b` (the mate check before the save; a refused mate stops the build),
  `bad8fc8` (Update's motion path); review fixes `3eba2ec`, `39ddf45`, `0459c04`, `885de1c`.
- **B — planning** (`motion.py`, `gearbox.py`, `update.py`): `e39b9d4` (the mates: anchors, locks, gear mates, loops,
  shafts held still), `84db947` (build to turn whenever the findings allow; record what was made or refused),
  `8bb1d86` (classify and finish a turning Update), `0536153` (the turning round trip on the fake), `1b1bb39` (tests
  pin the findings a probe round may change).
- **C — record and sentences** (`store.py`, `ui_text.py`): `e224e2e`, `5c25a1b`, `0110c88`, `bf3202e`.
- **D — window, boards, docs**: `f71c5c4` (the window passes the read's digest to the footer and the record to the
  Build again? question; its tests restored and the W5 states added), `aa9c5f0` (boards), and the docs commit after
  it. The window needed no new control. Its two hanging tests hung on a Build again? question no test answered; every
  window test now gets a stand-in that fails at once on an unexpected question. The four tests about W4's
  tooth-change Update run on a gearbox built as W4 built it (`built_w4`); the W5 findings are pinned in the test file.
  New boards: `WorkbookRefused`, `WorkbookTurned`, `WorkbookStatic` (no fallback board: there is no fallback); every
  board after a build is redrawn with the gears mated. Their Update boards use an edit Update carries whatever the
  ratio finding says (G3 and G4 to module 2.5 with S3 X 148.75, G4's At 27 → 30) in place of G2 68 → 69.

**What the demonstration (package E) still has to show**, on SolidWorks 2026 and then 2024 in a fresh session, and
not before P0b is committed and reviewed: W5-PLAN §4 — a turning build of the 12 : 1 (and the Risky_Placements and
Arc_Move workbooks) with every mate's status and every gear's constrained state read; the driven proof (a temporary
driving mate: input 30°, every gear's turn against `δ_i = 30°·ω_i/ω_in`, then Drive set back and the control mate
deleted, every frame back at the built frame to 1e-6, nothing left behind before any save); Update on a train turned
by hand with nothing to put (left turned) and with a put (put back, locks off around the puts and back on); an
anchor's Face Z move; a follower's At; a mate suppressed by hand turned back on; an unknown mate refusing the Update;
a refused mate stopping the build with the parts and layout kept; the tooth change both ways as the committed
finding says; and the window run through these states. The person's step: drag G1 in SolidWorks and watch the
output turn at 1/12, the right way (W5-PLAN §4.4); log every gear's origin and axis residuals after it, since
`POSE_TOLERANCE` against a mouse drag has not been measured (`W5-INTERFACES.md` §7 E).

**Open:**

- **A record whose mate Update cannot read** (a hand-edited record: a mate with no name, a gear not in the assembly):
  the footer's refusal names Build again…, and the window keeps that offer (Build again… stays on; its press asks).
  But `ui_text.build_again_question` has no sentence for an Update refusal, so the question opens with W4's *Nothing
  on record needs a new revision.*, which the footer contradicts. Package C's to word.
- **The header after a refused mate** reads *· changed since it was built* on the very read the build was refused
  from (`workbook_built_tag` sees a gearbox block whose `digest` is `""`). Package C's (or B's, if the record should
  keep the read).
- **A W4 gearbox's structural state** says "build again" twice: Update's offer, then *It was built static, before
  gears could be mated to turn: Build again… makes a new revision whose gears turn.* True, but W4's review S4.1 asked
  for it once; the window test pins both for now.
- Whether a train's Build may keep the top-only rebuild (P0b); D7's Update branch (the ratio remake) until P0b is
  committed; folders in the MateGroup are not mates (A's, done in `3eba2ec`; to be seen on SolidWorks).
- From W4: whether the assembly still reports needing a rebuild after the top-only route (`PUT_NEEDS_REBUILD` not
  established); a journaled file on a disconnected drive is treated as gone (below).

## Questions waiting for the user

Questions 1 to 5 of 2026-11-14 are answered (`notes-workbook/W5-DECISIONS.md`; PLAN-WORKBOOK §4.5, *Readings chosen
(W5)*). Still open:

1. **A journaled file on a disconnected drive is treated as gone** — keep that, or hold such entries until the drive
   is back?
2. Readings the user may overrule: Update SolidWorks does not save; a part keeps its file name after a teeth change;
   one build button; no static option in the window once W5 is in (a gearbox is built static only when a W5 finding
   is missing, and a W4 one stays static until Build again…).

## Rules carried over

- Commits and PRs carry **no Claude co-author or attribution line**. Commit by explicit path only
  (`git add <paths>`; `git commit -m "…" -- <paths>`), prose messages with the why; never `add -A`,
  `commit -a`, stash or reset. ~~Push only when the user says so.~~ Since 2026-11-14 the user wants each
  reviewed step pushed to `origin` as the work goes; the orchestrating session pushes, subagents commit only.
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
  a time. *On the user's own device (2026-11-14):* the user allows both SolidWorks 2026 and 2024 to be started,
  exited, and killed when one will not exit or memory is short; still one SolidWorks running at a time (the
  app asks every running SolidWorks for its version), and nothing the user has open is touched.
- Excel on the Windows host may be opened: use only an Excel the run starts, close only the workbook you
  opened, never quit the user's Excel.
- Screenshots on the Mac: capture by window id (`screencapture -l`), not by region, because a region
  capture picks up whatever app is in front.
