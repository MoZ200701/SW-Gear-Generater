# W4 review: the orchestrator's rulings

Read `W4-REVIEW.md` (the independent review, with repro scripts `w4r_*.py` in this folder) first. Every finding is
accepted. Where the review offers a choice, or a fix touches a reading chosen earlier, this file decides.
Run the repro scripts with `PYTHONPATH=<this folder> .venv/bin/python <script>` from the repo root; each becomes a
regression test.

## Pass 1 — worker, planning, record
Files: `swbuild.py`, `swcom.py`, `workbook/{gearbox,update,layout}.py`, `store.py`, and their tests.

- **B1 (worker half).** After the pre-flight, nothing escapes `build_gearbox` or `update_gearbox` as an exception:
  any `Exception` (a `pywintypes.com_error`, an RPC failure, anything unexpected) becomes a failure on the partial
  result that is returned, so what SolidWorks already saved reaches the finish. Decide where `swcom.call` should
  wrap COM errors into `SolidWorksError` with a full sentence, and keep the outer catch as the net.
  The sentence for a file found on disk with no record must be true: it must not say "was not built from this
  workbook" when the app cannot know; say there is no record that this workbook built it, and that an interrupted
  build can leave such a file.
- **B2.** A part marked `unsaved` never refuses a build. It is simply not reusable: the build makes that part new
  at this revision. Overrules interface agreement 7. The plan carries which parts were made new for that reason
  (a field the footer and the question can word), and no sentence is parsed to learn it.
  The `.gear.json` beside a part must not claim values the file on disk may not hold: either write it only once
  the save is seen, or mark it unsaved and have reuse-by-sidecar skip a marked one — choose the simpler correct
  one and say which. After B2 there must be no state in which both Build again… and Update SolidWorks are held
  because of an unsaved document.
- **S1.** A record whose `workbook` field is not the linked file:
  if that other workbook file still exists, this is a copy — the record is not this workbook's: Update is held with
  a sentence saying whose files those are, and Build plans a fresh gearbox (its own revision beside them, nothing
  shared, nothing overwritten); the copied record is not written over until the user builds.
  If the other workbook file no longer exists, the workbook was moved or renamed: adopt the record and update the
  field (what Locate… does today).
- **S2.** Update measures trig units and touches a document only when it will change that document. A part the
  check phase finds unchanged is left unmodified in SolidWorks. The reuse check's read-only route is the pattern.
- **S3 (plan half).** `GearboxPlan` exposes structurally what the footer needs (parts made new because unsaved;
  anything else the window now learns by parsing a sentence). Refusals that concern several files name all of them.
- **S5.** A part's collision suffix is its own: the smallest free `<stem>_r<k>`, independent of the gearbox
  revision, so one foreign or stale file at one part's path no longer moves a first build to `_r2`. A Part name
  whose file would be the layout's or the assembly's is a refusal naming the cell, not a build.
- **S6.** Reused parts are checked for their features as well as their globals (the sidecar lists them).
- **Nits here:** the unsaved marker's time is taken so that a save in the second after the job is not missed;
  after Locate, reuse by sidecar still recognises the workbook's own parts (the record knows the old path).

## Pass 2 — window, sentences, docs
Files: `ui_text.py`, `workbook_gui.py`, `gui.py`, `design/**`, `README.md`, `docs/**`, and their tests. Runs after
pass 1 and consumes its fields.

- **B1 (window half).** The finish in `_collect_job` writes what it can even if part of it raises. Closing the
  strip's main window while a Workbook job is pending is guarded the way the Workbook window's own close is.
  `job_failed`'s sentence and docstring say only what is true.
- **S3 / S4.** Every sentence in S4 (1–9) is put right, each with a test; the footer branches on plan fields, never
  on the text of a sentence. No footer shows a disabled button without its reason. No footer offers through a
  disabled button. "Build again" is said once per sentence. The header never says "built from this version" while
  the record marks an update unsaved.
- **Nits here:** `WorkbookWindow.update` → `update_plan`; the note becomes a small dataclass with a kind instead of
  a tuple subclass; `_build_again` compares what would be built and reused, not only the digest and name; after
  "No" the footer keeps the reason.
- **S7.** README, HANDOFF and UI-DESIGN §9 say what is true now, including the demonstration's results:
  SolidWorks 2026 — all of it, 244 checks, 0 failed; SolidWorks 2024 — tier 7, the 12 : 1 build, its measurements
  and controls, the Excel edit and Update; NOT yet on 2024 — the structural step and `_r2`, the continued build,
  the pure-move and risky-placement workbooks, the window run (the user's 2024 session ran out of memory; they
  are to be run in a fresh session).

## For W5 (recorded, not part of this fix)
- The gear-mate Flip was measured only on parallel, same-direction axes. Z+/Z− pairs and rings on Z− need their
  own probe before W5 relies on `GEAR_MATE_EXTERNAL_FLIP`.
- Gears on one shaft keep independent turns in the static assembly; W5's lock between them holds the placed
  relative angle, not 0.

## Rules
Commits by explicit path only (`git add <paths>`; `git commit -m "…" -- <paths>`), prose messages with the why,
**no Claude co-author or attribution line**, no push. Never `add -A`, `commit -a`, stash or reset.
