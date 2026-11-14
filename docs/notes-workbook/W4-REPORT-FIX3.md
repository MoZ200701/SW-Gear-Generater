## Second review pass on W4: N1–N6 all fixed

All six findings are fixed in 9 commits on `workbook`: `45173e0`, `a9d20ab`, `707bfcb`, `7de851a`, `d5eecb2`, `fb3bbdc`, `ae1d208`, `d2cd2d6`, `d37ae52`. Nothing is pushed and no commit has an attribution line. I did not drive SolidWorks or Excel. The probe agent's files are untouched (`findings.py`, `probe/results/sw2024/README.md` and its new `probe-results-*` files).

**Suites**
- Linux live tree: 1524 passed, 10 skipped.
- Clean `git archive` of `d2cd2d6` with `PYTHONPATH=src`: 1524 passed, 10 skipped (was 1494).
- Windows `python.exe -m pytest tests/test_workbook_build.py tests/test_workbook_window.py -q`: 100 passed, 1 skipped. The skip is the known "no display for Tk" flake; it hits a different test each run.

The findings share functions, so the code went in as two layered commits:
- `7de851a`: record, plan and worker (`store`, `swbuild`, `gearbox`, `update`, `layout` and their tests).
- `d5eecb2`: window and sentences (`ui_text`, `workbook_gui`, `gui` and their tests).

Each commit message says which finding each change serves.

### N3: a suffix took another row's typed Part name
- **Reproduced.**
- **Change (`45173e0`):** `_try` now claims every reused path and every new part's own free name before any suffix is handed out. The result no longer depends on row order. Two gears of one file name were already a refusal naming the cell.
- **Test:** `test_a_suffix_never_takes_another_rows_typed_part_name_whatever_the_row_order`, four cases.

### N5: held values judged by text alone
- **Not reproduced, as you said:** argued only.
- **Change (`a9d20ab`):** `_read_live` now also reads `equation_values()`. `_held_unit` accepts a unit only if the values in the matched unit agree to `VALUE_TOLERANCE`.
- **New refusal sentence:** *"X.SLDPRT does not hold what the workbook asks of it, so it cannot be reused: its equations are written for degrees, but SolidWorks evaluates them otherwise ("…" is a there and b here), so its angle unit was changed since they were written."*
- **Update** now measures the unit and writes the radian forms in that case.
- **The fake** needed nothing new: its `equation_values` already evaluates in `fake.trig`. The docstring says this comparison has not run on real SolidWorks.
- **Tests:** `test_a_part_whose_text_is_the_degree_form_but_whose_unit_is_radians_does_not_hold_its_values`, `test_a_part_whose_unit_and_text_agree_is_still_left_alone_in_either_unit`.

### N4.1: COM calls outside `call`
- **Read from code** (no repro script).
- **Change (`707bfcb`):** a new `swcom._guarded(member, action)` is the body of `call`. It now also wraps `_put_indexed`, the `CreateTransform` Invoke and its Dispatch, and every plain property put through a new `_put`. Example sentence: *"SolidWorks did not complete setting Equation(3): …"*.
- **Beyond the ruling:** I also routed the other ~13 puts (`feature.Name =`, `Transform2`, `Silent`, …) through `_put`. They are the same attribute puts, now with a sentence on error.
- **Tests:** `test_an_indexed_put_goes_through_the_same_wrapper_as_call`, `test_placing_a_component_goes_through_the_same_wrapper_as_call`, `test_a_property_put_goes_through_the_same_wrapper_as_call`.

### N1: whose record is it
- **Reproduced a, b and c.**
- **(a)** New `store.same_file`: `same_path`, or `os.path.samefile` when both files exist. `adopt` never moves a record to another path of the same file, and `_Parts.ours` uses it too.
- **(b) and (c)** New `store.record_owner` returns OURS, COPY or UNSURE.
  - UNSURE means the record's workbook is gone and nobody has answered. It is planned as a copy (new `plan.foreign_gone`).
  - The window asks once with a timer (`after(0)`), never from inside planning or painting. I first used `after_idle`, but `_fit`'s `update_idletasks` would have opened the dialog mid-paint.
  - Asked pairs go into a module-level `_ASKED` set, and answers into a session-wide `_VERDICTS` dict.
  - Title *"Moved, or a copy?"*, default No. Question: *"The record of what was built beside this workbook was written for X, which is not there any more. Was this workbook moved or renamed from it? Yes: the record is this workbook's, and Update SolidWorks and Build carry on from what it lists. No: this workbook is a copy, so Build makes its own gearbox beside those files, sharing and overwriting nothing. The answer is kept in the record."*
  - **How the answer is kept, the simplest sound way I found: in the record beside the workbook.** Yes runs `store.settle_owner`, which adopts the record and keeps the old path in `moved_from`. No sets a new field `copy_of`.
  - The session dict covers a failed write; the window then says *"Your answer holds until Gear Generator closes, but it could not be kept in the record of what was built: …"*.
  - Two copies of a deleted original each carry their own record file, so each asks.
  - Footer while unanswered: *"The record that came with this workbook was written for X, which is not there any more: until you say whether this workbook was moved or renamed from it, Build makes this workbook's own gearbox beside the files it lists, sharing and overwriting nothing."*
  - Update's refusal while unanswered: *"… which is not there any more, and whether this workbook was moved or renamed from it has not been answered: until it is, Update SolidWorks leaves the files that record lists alone."*
- **Locate:** a COPY record raises a new `store.NotCarried`. The window shows *"The record of what was built stays beside the workbook's old place: it was written for X, so it is that workbook's record and lists that workbook's files, not this one's."*
- **Tests:**
  - Store: `test_one_workbook_reached_by_two_paths_is_its_own_record_not_a_copy`, `test_locate_never_carries_a_copys_record_into_its_own`, `test_locate_carries_an_unanswered_record_as_it_is_so_the_question_is_asked_again`, plus the updated foreign test.
  - Gearbox: `test_one_workbook_reached_by_another_path_keeps_its_record_through_a_build`, plus the updated moved test.
  - Window: `test_a_record_whose_workbook_is_gone_is_asked_about_once_and_yes_adopts_it`, `test_no_keeps_a_record_whose_workbook_is_gone_another_workbooks_and_builds_beside_it`, `test_two_copies_of_one_deleted_original_are_each_asked_never_adopt_silently`, `test_locate_on_a_copy_never_takes_the_originals_record_for_its_own`.

### N2: marks that never cleared
- **Reproduced.** The `w4v_` script hand-fakes the worker, so the regression tests run the real `update_gearbox` on the fake instead.
- **Worker:** `GearboxResult` and `GearboxUpdate` gain `open_before` (from the pre-flight `documents()` call, which `_refuse_paths` now returns) and `opened` (documents loaded from disk). `GearboxResult` also gains `held` (the unit each reused document was found in).
- **Both finishes:**
  - A document loaded from disk loses its unsaved marks, both the record's and the `.gear.json`'s (new `store.unmarked`).
  - An Update that finds such a document holding the workbook's values also clears its mismatched mark. A document Update changes loses any mismatched mark.
  - A document marked unsaved that was not open when the job began, and not saved since, has lost Update's changes; its mark becomes a mismatched mark.
  - `finish_update` no longer records values for a part it failed to reach (a bug I found: `_update_document` failures had empty `UpdateResult.failures`).
- **Scope:** new `LinkRecord.current_documents()` and `current_marks()`. The header and the save request count only the current revision's documents. `clear_saved` now also drops mismatched marks whose file is newer (in memory only).
- **Sentences:**
  - Save request: *"…have changes from Update SolidWorks that are not saved: save them in SolidWorks to keep them. If SolidWorks closed them without saving, press Update SolidWorks to make them again."* Where Update would build again instead, the last sentence is *"…those changes are gone."*
  - Held-back line: *"While Gear_m1.5_N68's changes are not saved, the new revision makes …"*
  - Mismatched line: *"…does not hold what the record says, as the last job in SolidWorks found, so …"* (also in `MadeNew.sentence`).
  - Question tail: *"…answer No and save it in SolidWorks first (if SolidWorks has closed it since without saving, those changes are gone, and it cannot be reused)."*
  - New header tag: *" · SolidWorks no longer holds all of this version"*.
- **The fake SolidWorks** now keeps each file apart from what is open in memory (`saved` vs `memory`). A saved document stays open, and `close_all()` empties memory and restores the saved frames.
- **Tests:**
  - Gearbox: `test_an_update_lost_when_solidworks_closed_is_cleared_by_the_next_update_that_reads_the_files`, `test_an_update_put_back_after_solidworks_closed_marks_it_unsaved_again_and_clears_mismatched`, `test_a_part_proved_to_match_by_a_later_update_loses_its_mismatched_mark`, `test_a_build_that_finds_an_unsaved_document_closed_marks_it_mismatched_not_unsaved`.
  - ui_text: `test_an_earlier_revisions_unsaved_documents_are_never_nagged_about`, `test_a_document_found_not_holding_what_the_record_says_is_not_called_built_from_this_version`, `test_the_save_is_never_asked_as_if_it_were_certain_to_be_possible`.

### N4.2, 4.3, 4.4, 4.5: finishes, escape, journal, close guard
- **New record fields:** `pending` (a list of `PartEntry`; layout and assembly have `kind` "layout" or "assembly") and `pending_for` (the workbook whose build wrote it).
- **Journal:**
  - `gearbox.journal(plan)` is written by `_write_journal` before submit.
  - The finish takes it out, even when nothing was made; for a copy it is taken out of the other workbook's record. A refused job's journal is cleared on collection.
  - In planning, a pending part on disk with no `.gear.json` and the same plan is reused (`PartReuse.journaled`) and checked live. Its `.gear.json` is written at the finish in `result.held`'s unit, with recipe, template and manual steps but no features.
  - A pending layout is reused once checked against the current shafts.
  - A pending assembly is gone beside: *"Reducer_12to1.SLDASM was saved by a build that was interrupted before it was put on record, and a build never overwrites a file."*
  - A journaled file planned for other values is called STALE.
- **Old reader:** I ran the actual pre-schema-2 `load_link_record` (from `a93d6d9^`) on a new record. It reads it and keeps the parts, since unknown keys are dropped.
- **N4.2, how I applied it:** I did not restructure `finish_build`. A finish that raises writes nothing, and the journal stays, so the next plan reuses what was saved. `finish_failed` now says *"…the next Build finds it from the journal written before the build, checks it in SolidWorks and reuses what it can."* `finish_update` stays all-or-nothing; its sentence wrongly said "What SolidWorks saved" and now reads *"…Its changes are in SolidWorks, not saved: save them there to keep them."*
- **Escape:**
  - A second window close while the job is pending asks *"Close anyway?"*: *"SolidWorks has not answered yet: the build is still running there, perhaps held up by a dialog open in SolidWorks. Close this window anyway? Files SolidWorks saves from now are not put on record by this window, and nothing will be overwritten: the next Build finds them, checks them in SolidWorks and reuses what it can."* There is a variant for an update.
  - `CloseGuard`'s second request asks *"Quit anyway?"*: *"SolidWorks has not answered yet: a job is still running there, perhaps held up by a dialog open in SolidWorks. Quit anyway? Files SolidWorks saves from now, and documents it changes, are not put on record by this session, and nothing will be overwritten."* When a workbook build is pending it adds *"The workbook's next Build finds the files its build saved, checks them in SolidWorks and reuses what it can."*
- **N4.4:** windows get an `_asking` flag. `CloseGuard` waits on asking windows and says *"Gear Generator closes once the question open in a Workbook window is answered."*; the window closes after the answer (or after the job the answer started).
- **N4.5, the strip:** the only change is that `CloseGuard` is given `strip=self` and waits while `strip._pending_build` is set. The strip's own poll collects the build and writes its `.gear.json`; then the app quits. It says *"Gear Generator closes once the strip's build in SolidWorks has finished and what it saved is on record; …"*. A second close offers Quit anyway. The strip does not stay open to show a failed build's sentence.
- **Tests:**
  - Journal (gearbox): `test_the_journal_makes_an_interrupted_builds_parts_reusable_once_checked_live`, `test_a_journaled_part_for_other_values_is_ours_and_stale_and_one_not_on_disk_is_dropped`, `test_a_journaled_layout_is_reused_once_checked_and_a_journaled_assembly_is_gone_beside`, `test_a_finish_that_made_nothing_still_takes_the_journal_out`.
  - Store: `test_the_journal_round_trips_and_an_old_build_ignores_it`.
  - Window: `test_closing_a_window_twice_while_solidworks_does_not_answer_offers_to_close_anyway_and_the_journal_reuses`, `test_a_question_open_over_a_window_keeps_it_and_the_app_until_it_is_answered`, `test_closing_the_strips_window_twice_while_a_job_has_not_answered_offers_to_quit_anyway`, `test_closing_the_strips_window_waits_for_the_strips_own_build`, plus extended `test_a_finish_that_raises_still_answers_and_frees_the_window`.

### N6: sentences and the table
- A new `update._structural` maps the field names: *"Flank changed from involute to arcs, which its values cannot carry, so it needs a new part."*; Kind, Side and Hand likewise. Bore, profile shift and groove were already in words. The strip's own `structural_change` sentence is unchanged.
- The Gears table shows `plan.part_of`.
- A missing file is now "moved, renamed or deleted".
- After "No" to Build again?, the unsaved and made-new lines stay with the reason.
- **Tests:** `test_every_field_a_structural_change_names_is_said_in_the_workbooks_words`, parametrised side and kind cases, `test_the_gear_table_shows_the_part_the_build_would_make`, `test_after_no_to_build_again_the_unsaved_and_made_new_lines_stay_with_the_reason`.

### Where I departed from a ruling
- **Unanswered record and Locate:** a record whose workbook is gone and unanswered is carried by Locate unchanged, not adopted, so the question is asked at the new place. Only COPY records are refused.
- **The save sentence is hedged, not detected:** nothing on the Tk thread can see SolidWorks, so the save request is worded to be true either way. A job's `open_before` settles it at the next job.
- **N4.2:** degrades via the journal instead of restructuring `finish_build`; `finish_update` stays all-or-nothing.

### Boards and docs
- **gen.py:** passes the plan to the table, takes any dialog, shows a job in flight and greys Export while one runs. Its reads of one workbook (each written to its own temp file) are adopted as one workbook; without that the boards hit the new UNSAVED rule.
- **Boards:** regenerated in a throwaway worktree at HEAD.
  - Changed: WorkbookAgain (Flank words), WorkbookCopy (`_r2` names), WorkbookUnsaved (new sentences).
  - New: WorkbookMoved, WorkbookCloseAnyway.
  - Every strip board is byte-identical after line-ending normalisation.
  - All five are rendered with Windows Chrome at 2×, 1080 px, and I looked at each: nothing is clipped.
- **Docs:** UI-DESIGN §6 and §9 (marks, questions, journal, record fields, boards, differs list), README, HANDOFF (count above, commits, what only a rerun can show), and a dated note in PLAN-WORKBOOK §4.5.

### What the SolidWorks reruns should now show
**`workbook_assembly_check.py`**
- Each build logs `journal written: N paths`, and each update logs `loaded from disk [...]`.
- Section a passes as before. Its "marks modified exactly the documents Update changed" check now also confirms N5's value comparison on real SolidWorks: it fails if `equation_values` disagrees falsely.
- New section a3:
  - two parts saved and never collected, then reused from the journal (revision 0, no suffix), checked first, with their `.gear.json` written and the journal taken out;
  - the demonstration edit and Update left unsaved, then `QuitDoc` on the section's documents;
  - the edit typed back and Update run: `changed == []`, `opened` is all six documents, the marks are gone, the sidecar is unmarked with 68 teeth, the header reads "built from this version", and a build-again plan reuses N68.
- Logged footers carry the new wording.

**`workbook_window_check.py`**
- State 06 has one save request containing *"If SolidWorks closed them without saving, those changes are gone."* and *"While Gear_m1.5_N68's changes are not saved…"*.
- The final step checks that the journal is empty and the header reads "built from this version".

### Found that the reviews missed
- `finish_update` recorded the wanted values for a part whose open or update raised (fixed).
- The other ~13 property puts in `swcom` also bypassed `call` (fixed).
- **Assumptions only a rerun can confirm:**
  - a3 assumes `QuitDoc` closes a modified document without a dialog. If it does not, the run blocks; `DialogWatch` will log the dialog.
  - N2 relies on `documents()` listing every document held in memory. If it misses an open one, a mark could be cleared wrongly.
  - The journal's reuse writes a `.gear.json` with no feature names, so later reuse checks of those parts check fewer features.

Repro and simulation scripts are in docs/notes-workbook/ (`w4v_*.py`, `a3_sim.py`).