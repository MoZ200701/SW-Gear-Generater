## Third review pass on W4

**Verdict: yes, with fixes first.** The rerun can go ahead once the four items under "Must fix first" are in. Item 1 changes the code path a3 is there to demonstrate. Item 2 is a one-line guard that reopens S1 if left. Items 3 and 4 are pure Python; the rerun would not exercise them, but they are small and are holes in exactly what this pass claims to fix.

**Suite:** a clean `git archive d37ae52` with `PYTHONPATH=src` gives **1524 passed, 10 skipped**, matching the claim. I edited nothing in the repo. My scripts are under docs/notes-workbook/ as `w4x_*.py`; run them with `PYTHONPATH=<that folder>`. They use the clean tree at docs/notes-workbook/w4x_tree.

### Must fix first

**1. A mark is cleared while the document's changes are still unsaved and open (N2). Reproduced: `w4x_documents_cap.py`.**
- **What:** `open_before`/`opened` come from `Session.documents()`. Its `GetFirstDocument`/`GetNext` walk stops after 200 documents (`swcom.py:497`; `:1820` has the same cap). The user's SolidWorks is in use, and one large assembly loads more than 200.
- **Scenario:**
  1. Update leaves N68 unsaved and open.
  2. More than 200 documents are loaded, so N68 is not listed.
  3. The next job counts N68 as "loaded from disk" (`swbuild.py:1151` `_from_disk`).
  4. The finish drops the record's unsaved mark and sets the `.gear.json` to `unsaved_since` 0, while the changes are still unsaved in memory.
  - Script output: "opened (from disk) by the 2nd Update: ['Gear_m1.5_N68.SLDPRT'] … memory != saved: True … unsaved marks after: [layout, assembly only] … N68 sidecar unsaved_since: 0.0".
- **Side effect:** the same truncation also blinds decision 7's same-name check, but that is older code.
- **Fix:**
  - Walk until `None`, with only a very high runaway guard.
  - If the guard is ever hit, return `open_before=None`; the finishes already treat None as "unknown, clear nothing".
  - Cheaper belt and braces: after `open_document`, call it "from disk" only if `GetSaveFlag` is False. A document holding unsaved changes reads True.

**2. `same_file` trusts `os.path.samefile` blindly (N1a). Simulated: `w4x_samefile_ino0.py`.**
- **What:** on Windows, `st_ino` is the volume's file id. Some redirectors and virtual drives report 0 for every file; this is the cause of shutil's false SameFileError (bpo-33935, Google Drive File Stream, cited from memory).
- **Scenario:** with `st_ino` 0, two different workbooks on one such volume count as one file.
  - `record_owner(original's record, copy)` returns OURS, so the copy drives the original's files. That is S1 reopened.
  - `_Parts.ours` (`gearbox.py:420`) takes any sidecar naming any workbook on that drive as ours.
- **Evidence:** script output is "real stat: … owner: copy / st_ino = 0: same_file = True | owner: ours". I did not confirm this on a real such volume.
- **Fix:** in `store.py:116`, stat both paths yourself and return True only when `st_ino != 0` and `(st_ino, st_dev)` are equal.

**3. The journal is wiped on a raise, orphaning the files of the interrupted build it exists for (N4). Reproduced: `w4x_clear_journal_orphans.py`.**
- **What:** `_collect_job` calls `_clear_journal` (`workbook_gui.py:1035`, `:1078`) on any raise. That deletes all of `pending`, including the earlier interrupted build's entries, which the new journal carries as journaled reuses.
- **Scenario (realistic):**
  1. SolidWorks crashes mid-build, so N17 and N68 are saved with no `.gear.json`.
  2. The user restarts Gear Generator and presses Build before SolidWorks is back. The worker's connect raises, and the journal is wiped.
  - Any pre-flight raise does the same: a same-named document open elsewhere, "already exists", or `_check_live`'s BuildError.
  3. The next plan says "Gear_m1.5_N17.SLDPRT is already there, with no record…" and makes `Gear_m1.5_N17_r2` and `Gear_m1.5_N68_r2` beside them.
- **The same hole through "Close anyway":**
  1. Close anyway, then reopen and Build while the abandoned job is still queued (`_worker_free` does not look at `worker.busy()`). `_write_journal` *replaces* the old journal (`:1028`).
  2. The old job then saves its files.
  3. The new job's pre-flight raises "already exists", the journal is wiped, and the files are orphaned.
  - `close_anyway_question` (`ui_text.py:2187`) promised "the next Build finds them". It also says that when `job.journaled` was False.
- **Fix:**
  - Never clear the journal wholesale, on a raise (`_clear_journal`) or in `finish_build` (`gearbox.py:971`). Drop only entries now on record (a `.gear.json` written, or in `rec.parts`/gearbox) or not on disk.
  - Make `_write_journal` merge by path instead of replacing.
  - Optionally grey Build while `worker.busy()` with no window owning the job.
  - Nothing is ever overwritten today; the harm is orphaned files and `_r2` copies.

**4. Untrue sentence right after the user answers No (N1c/N6). Reproduced: `w4x_copy_of_gone_sentence.py`.**
- **What:** after No, `copy_of` is set and `record_owner` returns COPY even though the original is gone. `plan.foreign_gone` is then False, so both sentences say the original "is still there":
  - the footer (`ui_text.py:1691`): "This workbook is a copy of C:\Work\Reducer_12to1.xlsx, which is still there…";
  - Update's refusal (`store.py:889`).
- **Fix:** pass "exists" into both sentences, or give `record_owner` a fourth state for COPY by answer, and word it "which you said this workbook is a copy of".

### Can ride along / note for later
- **No way back from No (`store.py:866`).** No (the default, so a reflexive Enter) is permanent: `copy_of` sticks, Locate raises NotCarried, and the first Build replaces the record. Also, the question does not mention "or on a drive that is not connected now". A Yes given while a share is offline makes two workbooks drive the same files once it returns.
- **`same_file` now does I/O on the Tk thread.** `ours` per sidecar, `_journal_of`, `adopt` and the finish all stat; against an offline UNC path in `moved_from` (exactly the moved-from-a-share case) each call can block for the SMB timeout.
- **Two windows on one workbook.** `open_workbook` matches the existing window by `same_path` (`workbook_gui.py:1276`), so a UNC path and a mapped drive open two windows on one workbook, each journalling into the same record. Use `same_file`.
- **Journaled files in edge states:**
  - A journaled part that fails its live check gets a mismatched mark, but is cleared from the journal, so the next footer calls it "no record that this workbook built it".
  - A journaled assembly forces a whole `_r2` even when the interrupted build had finished everything. This is conservative, but leaves a complete orphan gearbox.
- **The strip's close sentences.**
  - `app_closes_when_done(strip=True)` ends "it stays open if something needs saying" (`ui_text.py:2163`). For the strip that is untrue: `check()` quits after the strip's build whatever it says.
  - It also says "the strip's build … what it saved" during a strip update.
- **"from now" in both escape questions.** The quit and close questions say "Files SolidWorks saves from now … are not put on record". Nothing that job saved before the close reaches the record either; the journal covers a build, not an update. Say "by this job".
- **A second SolidWorks session.** With 2024 and 2026 both running, a document left unsaved in the other session reads as "from disk" here, and its mark goes.

### The three departures
- **Locate carrying an unanswered record unchanged: sound.** The pair key changes with the path, so the question is asked at the new place, and a COPY raises NotCarried; `w4v_locate_launders_copy` now raises. It adds nothing to `moved_from`, which is fine because sidecars name the record's workbook.
- **The save sentence hedged rather than detected: sound.** The variants are true in each state I dumped ("press Update SolidWorks to make them again" only when Update would carry the workbook again; otherwise "those changes are gone").
- **`finish_build` not restructured; `finish_update` all-or-nothing: acceptable.** A failed finish leaves the journal, so parts are reused, but a journaled assembly forces `_r2` (the "reuses what it can" hedge covers this). Two caveats:
  - This leans on a journal that item 3 shows can be wiped.
  - The `finish_update` failure sentence "Its changes are in SolidWorks, not saved" is untrue when the update changed nothing (rare).

### Checked and found sound
- **N3:** `w4v_suffix_vs_part_name` now gives G4 its typed name and G1 `_r3`, independent of row order, and the footer is true.
- **N1a/b:** `w4v_same_file_two_paths` returns OURS.
- **The answer's session state:**
  - `_VERDICTS`/`_ASKED` are keyed per (workbook, other), so no answer leaks across pairs.
  - If the gone original returns, the record is judged COPY. That is conservative, including after a session-only Yes.
  - When the answer's write fails, the plan (settled in memory) and the finish (raw disk record) still agree, for both Yes and No.
  - Re-plans while the question is open do not ask again.
  - Window close and CloseGuard both wait on `_asking`.
- **N2 on the fake:**
  - `w4x_marks_after_close.py`: Update, SolidWorks closed, an unrelated Update. Nothing is cleared or converted wrongly, and the tag is right.
  - The earlier-revision filter works (`w4v_after_build_again_unsaved`).
  - The same-name pre-flight stops the UNC-vs-mapped case from passing as "from disk".
- **The journal:**
  - Another workbook's file in a shared folder is judged by its `.gear.json`, and gets no reuse.
  - A copy's journal is keyed by `pending_for`; the original's journal is ignored by a copy.
  - A journaled part with other values is STALE.
  - A part is only ever saved after `_verify`, so reusing one with no features recorded is safe.
- **`swcom._put`/`_guarded` on real pywin32:**
  - `setattr` is exactly what `obj.X = v` did, and non-COM exceptions pass through unchanged.
  - `_put_indexed`'s `Invoke` is unchanged.
  - No caller catches a bare `com_error` around these calls.
- **`gui.py`:** the only change is CloseGuard and `strip=self`.
- **An older W4 build (01b889e) reading a new record:** it reads it and keeps parts (`w4x_old_reader.py`), dropping the new keys on rewrite. v0.3.1 has no workbook record at all.
- **a3 and the window check:**
  - The assertions match what the fake shows. `spec["teeth"]` is the string "68".
  - The only hang risk is `QuitDoc` prompting; I believe it closes without a prompt, and DialogWatch would log it.
  - The window check's new assertions are consistent with the state-06 sentences.

### Not checked
- I did not run the Windows Tk window tests: they open windows on the in-use host, and Tk is not importable in the Linux venv.
- Anything that needs real SolidWorks:
  - `documents()` listing component documents loaded without a window;
  - `equation_values` on a reopened document (N5);
  - `QuitDoc` closing without a prompt.
- I did not review `gen.py`, the boards or the docs.