# W4: the independent verification of fix pass 4

Written 2026-11-14 from the reviewer's report of that day. The review read `git diff 8b1ef15..f335379`
(pass 4, with `2250ceb`) against `W4-REVIEW-3.md` and `W4-REPORT-FIX4.md`. It edited nothing.

**Verdict: pass 4 verified.** Each of the four must-fix items of review 3 closes its failure scenario, the
ride-alongs are correct from the code, and no new fault of real severity was found inside the diff.

## How it was checked

- The affected test files that need no Tk (store, swcom, swbuild, workbook_gearbox, ui_text, workbook_update,
  workbook_build) on HEAD: 606 passed.
- The tests pass 4 added, run against the source before it (`8b1ef15`): 16 failed, 1 passed (the "cannot be
  statted" test, which guards against a regression). The documents-cap test fails on the behaviour itself;
  the rest fail on members that did not exist yet and, read through, would fail on behaviour too.

## The four items

1. **The 200-document cap that could clear an unsaved mark: fixed.** The walk of open documents goes until
   `GetNext` returns nothing, and the check before a build uses the same walk. A path joins `opened` only
   when it was not open before and `GetSaveFlag` reads False; a flag that cannot be read counts as unsaved
   changes.
2. **A file id of 0 making two workbooks one: fixed.** `store.same_file` compares the path text first and
   takes a file id of 0, or any error reading it, as no answer. Every false answer left leans the safe way.
3. **The journal wiped by any refused job: fixed.** Entries are dropped only when they are on record, have
   a sidecar, or are not on disk; a new entry wins over an old one on the same path; another workbook's
   journal is never taken in.
4. **The false sentence after "No": fixed.** No other "still there" sentence remains.

## What it found, and what became of each

- **`workbook/xlsx.py` still used `os.path.samefile`** (W1 code, outside the diff): on a volume reporting a
  file id of 0, Export as… onto another existing file took it for the source and wrote over it. Confirmed
  by simulation. **Fixed in `8bd2530`** (`store.same_file`, with a test that fails on the old code).
- **A file that cannot be seen right now is treated as gone** (`gearbox.settled_journal`): with the output
  folder on a share or a drive that is disconnected when a job is refused or finishes, an interrupted
  build's entries are dropped, and when the drive returns the next build goes beside those files as `_r2`.
  Read from the code, not run. Nothing is overwritten; the harm is files with no record. It follows review
  3's own rule ("or not on disk"). **Left as it is; a design call for the user.**
- **The unsaved-mark rule assumes `GetSaveFlag` reads False on a document just opened from its file**,
  including a file saved by 2024 and opened in 2026. **Confirmed on SolidWorks** by the 2026-11-14 reruns
  (`w4-workbook-assembly-20261114-053855.log`, `sw2024/w4-workbook-assembly-20261114-055924.log`: every
  document reads False straight after each reopen, on both versions) and by
  `probe/cross_version_open_check.py` (`w4-cross-version-2024-in-2026-*.log`: a gearbox saved by 2024 reads
  False on every document straight after it is opened in 2026).
- **Some of pass 4's unit tests restate the implementation** rather than exercise the failure. The window
  tests do cover the real paths. Left.
