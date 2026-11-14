Everything is committed in two commits on `workbook`: `f335379` (code and tests) and `2250ceb` (docs and boards). Nothing is pushed and neither commit has an attribution line. I did not drive SolidWorks or Excel, and I did not touch `probe/`, `findings.py` or HANDOFF. The tree is clean apart from an untracked `docs/notes-workbook/`, which is not mine.

**Suite on a clean `git archive HEAD` copy**
- `PYTHONPATH=src pytest -q`: 1559 passed, 10 skipped (was 1536 at `9aeed80`).
- Windows `python.exe -m pytest tests/test_workbook_build.py tests/test_workbook_window.py -q`: 102 passed, 1 skipped. The skip is the "no display for Tk" flake; a rerun on the working tree hit it on a different test.
- All five `w4x_*` repros now show the fixed behaviour. I ran copies against the new tree; they are in `docs/notes-workbook/w4y/` (run with `PYTHONPATH=` that folder). The journal script there calls the new `_settle_journal` logic in place of the old wipe.

**Must fix**

1. **`documents()` cap — done (`f335379`).**
   - Both walks now share `Session._walk_documents` (`swcom.py`) and go until `GetNext` returns nothing. A list that reaches `DOCUMENT_WALK_LIMIT` (100 000) without ending raises `DocumentsUnknown` with a sentence.
   - **My ruling:** that refuses the job at the pre-flight before anything is made, so decision 7 never passes silently. So `open_before=None` is never actually reached through the guard. Still, `_from_disk` and `_note_opened` (`swbuild.py`) now count nothing as loaded from disk when it is None, and the finishes skip their rule then.
   - **The belt:** right after `open_document`, `_note_opened` reads `Session.has_unsaved_changes()` (`GetSaveFlag`, probe close_document). Only a clean document goes in `opened`. One holding unsaved changes is added to `open_before`, because it was open all along. Without that, `finish_update`'s "closed while unsaved" rule still turned its mark into a mismatched one. The fake SolidWorks models the flag.
   - Tests: `test_documents_walks_to_the_end_of_solidworks_list_however_long`, `test_a_list_of_documents_that_never_ends_is_refused_with_a_sentence`, `test_unsaved_changes_are_read_from_the_save_flag_of_the_document_just_opened`, `test_a_document_holding_unsaved_changes_is_never_counted_loaded_from_its_file_whatever_the_list_says`, `test_when_the_documents_open_are_not_known_no_document_counts_as_loaded_from_its_file`, `test_a_list_of_open_documents_that_never_ends_refuses_the_job_before_anything_is_made`.

2. **`same_file` — done.**
   - `store._file_id` stats each path itself. Two paths are the same file only when `st_ino != 0` and `(st_dev, st_ino)` match; any `OSError` means not known to be the same.
   - **Cost, what I chose:** the path text is compared first. Inside `store.one_pass()` each path is statted at most once, which is per path, so stricter than per pair. `plan_gearbox`, `update.classify`, the window's whole planning pass and `open_workbook` each run as one pass.
   - Tests: `test_a_file_id_of_zero_never_makes_two_workbooks_one`, `test_a_path_that_cannot_be_statted_is_not_known_to_be_the_same_file`, `test_within_one_pass_each_path_is_statted_once_and_text_is_compared_first`.

3. **The journal — done.**
   - New `gearbox.settled_journal`: an entry leaves only when it is on record or its file is gone. On record means listed in parts, a gearbox or an earlier revision, or a `.gear.json` written now or already there.
   - New `gearbox.merged_journal`: merges by path, and never takes in another workbook's journal (by `pending_for`).
   - `finish_build` settles the journal instead of clearing it, and takes a new `exists` parameter. `_clear_journal` is replaced by `_settle_journal`.
   - A reused part that is not on record and was not checked live is no longer put on record. So a journaled part that fails its live check stays in the journal with its mismatched mark.
   - A job left running by Close anyway is kept in `_UNOWNED`. `_worker_free` holds Build and Update with `ui_text.unowned_job_busy`. `close_anyway_question(updating, journaled)` promises "the next Build finds them" only when the journal was written.
   - Tests: `test_a_refused_job_never_orphans_what_an_interrupted_build_saved`, `test_a_new_journal_is_merged_by_path_into_the_old_never_replacing_it`, `test_a_journaled_part_that_fails_its_live_check_stays_this_workbooks_with_its_mismatched_mark`, `test_a_finish_takes_out_only_what_is_on_record_or_gone`. In the window: `test_a_build_refused_after_an_interrupted_one_keeps_what_that_build_saved_in_the_journal`, and the extended close-anyway test, which now checks the hold.
   - Changed expectation in that close-anyway test: after the next build, the abandoned job's revision-0 layout part and assembly stay in the journal (on disk, on no record). This is the known "journaled assembly forces `_r<n>`" item, still not fixed.

4. **Wording after No — done.**
   - New `plan.foreign_said` and `store.copy_by_answer`.
   - The footer and Update's refusal now say "which you said this workbook is a copy of".
   - Test: `test_after_no_with_the_original_gone_nothing_says_it_is_still_there`, and in ui_text, `test_a_copy_by_answer_whose_original_is_gone_is_never_said_to_be_still_there`.

**Ride-alongs, all done**
- **Way back from No:** `copy_of` is now in memory only and never written; it is dropped on read and on write. So No holds for the session, and a new session asks again until the copy's first build writes its own record. The footer says how: quit Gear Generator and open this workbook again before you build. The window writes only a Yes. Tests: `test_a_no_is_never_written_so_a_new_session_asks_again_until_the_copy_builds`, the updated No-answer window test, and the updated Locate tests. An unanswered record is now carried as it is, and the question is asked at the new place.
- **The question** now names a drive that is not connected and says No is safe then. It also says Yes is kept in the record and No is asked again until the copy has built.
- **`open_workbook`** finds an already-open window by `same_file`.
- **Strip close sentence:** "…once the strip's job in SolidWorks has finished and the strip has collected it." The workbook part now says "what it did is on record". `gui.py` is untouched.
- **Escape questions:** no "from now"; "Nothing that job saves or changes is put on record by this session". The update variant has no journal promise. The quit variant's promise is hedged ("unless the record cannot be written"), because `gui.py` cannot pass whether a journal was written.
- **`finish_update` failure** passes `changed`; with nothing changed it says "It changed nothing in SolidWorks."
- **UI-DESIGN §9:** the two-sessions limit is noted, and every sentence that changed is updated. README is updated.
- **Your Gears-table item 1 is done:** a built gear whose part the next build makes new reads "built · new part on Build". Tests: `test_a_built_gear_the_next_build_makes_new_is_never_shown_as_simply_built`, and a check added to the window's state-06 test.
- **Rebuild item: not started**, as you said.

**For whoever carries on**
- **Boards:** `WorkbookCloseAnyway`, `WorkbookMoved`, `WorkbookUnsaved` and `WorkbookUpdated` `.dc.html` are regenerated and committed. Their PNGs in `design/renders/` are not redrawn. `gen.py` needs Windows Python run with `PYTHONUTF8=1 WSLENV=PYTHONUTF8 python.exe gen.py`, and its CRLF output has to be put back to LF.
- **Demonstration scripts:** I left both untouched. `workbook_assembly_check.py`'s `write_journal` still replaces the journal rather than merging it, and its a3 expectations still hold ("journal taken out" ends empty, since everything ends on record).
- **One expectation a rerun must confirm:** a3's "it loaded every document from its file" now also needs `GetSaveFlag` to read False on freshly opened documents. Your rerun says opening alone marks nothing, so it should hold.
- **Rebuild item:** a3's "opened" check may interact with the coming `ForceRebuild3` change.
- **Still known, not fixed:** a journaled assembly forces a whole `_r<n>`, and its orphaned layout part and assembly now stay in the journal indefinitely.