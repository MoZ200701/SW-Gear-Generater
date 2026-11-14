# W5: the user's answers and the orchestrator's rulings on the plan and its review

Read in this order: `docs/PLAN-WORKBOOK.md` (the authority), `W5-PLAN.md` (the implementation plan),
`W5-PLAN-REVIEW.md` (its independent review), then this file. Where they disagree, this file wins over the
review, the review over W5-PLAN, and PLAN-WORKBOOK over all three unless this file says a reading was chosen.
Written 2026-11-14 while the probe batch the review asked for (package P0) was still running; what depended on
its findings is ruled on in the later sections, added the same day as each probe round was committed and reviewed.

## The user's answers (2026-11-14)

1. **A refused mate stops the build and says why** (review M6, option A; overrules D2). No static assembly is
   made in its place. The parts and the layout part the job built are kept and recorded, as W4's continued
   revision keeps them; no assembly is saved; the sentence names the mate SolidWorks refused or flagged. The
   next Build makes the assembly once the workbook has changed. The footer never invites a retry of an
   unchanged workbook. The refused document: closed by the job only if a probe shows that is safe on 2024
   (`probe/scaffold.py:120` shows the hang); otherwise left open and named, with the sentence saying its parts
   are the saved ones.
2. **Update returns a train the user turned to its built position whenever it has to move any gear** (D4
   stands, with M1's rule below). With nothing to put, the train stays where the user turned it. The footer
   says so plainly when it happens.
3. **No datum plane: the first gear's place along its shaft is measured from the Front plane** (D8 stands;
   review M5's alternative is declined — an extra plane in the layout part is not wanted for geometry that is
   not part of the specified gear train). So an anchor's front face reaching, leaving or crossing the Front
   plane is structural (Build again…), which includes a face-width or `At` change on an anchor whose front face
   sits on the Front plane, as G1 and G2 of the 12 : 1 do. The sentence names the edit ("G1's face width
   moves its front face off the Front plane…"), never only the plane. Probe `axial_datum_plane` is recorded
   for the record and nothing is built on it.
4. **The Checks panel stays as built: problems only**, a clean workbook saying so in one line
   (`design/UI-DESIGN.md`, "Where it differs from PLAN-WORKBOOK §5"). PLAN-WORKBOOK §5's "then the passed
   checks, one line each" is not built.
5. **Document titles in old probe results are scrubbed going forward** (`ee46d20`); history is left as it is.

## Rulings on the review

- **M1 accepted.** When a train needs any put, every mated gear of that train is put, unconditionally. Locks are
  tested exactly (δ_follower ≡ δ_anchor, to tolerance), never modulo a pitch; "modulo pitch" stays for meshes
  only. A fake test covers the one-tooth scenario the review describes.
- **M2 accepted.** `k == ω_b/ω_a` and `δ_i = 30°·ω_i/ω_in`, speeds about each shaft's own axis. The Risky
  values (+0.7, +0.636364, −0.388889) are pinned.
- **M3 accepted.** The interface commit starts on the commit that closes W4 (the rebuild fix, its review's
  changes, and the demonstration reruns on SolidWorks 2026 and 2024), named in `W5-INTERFACES.md`.
- **M4 accepted**, and widened: package P0 probes the ratio change (P1), the lock re-taken after a move along
  the shaft (P2), renaming each kind of mate and finding it by name, the demonstration's drive, a put on a gear
  in two gear mates, the datum plane (probed before answer 3 was given; not used), and — from the review of probe `assembly_rebuild_scope` — which rebuild a
  mated assembly needs and what it marks modified (`MATED_ASSEMBLY_REBUILD_ROUTE`). Until that last finding
  is set, every mated assembly rebuilds in full (`ForceRebuild3(False)`), as tiers 4, 5 and 8 proved it.
- **M6** is answer 1. **M5** is answer 3: declined, with its last point kept (the sentence names the edit).
- **M7 accepted:** in the check phase, a mate the record does not know that touches a gear refuses the Update
  before anything is changed, naming the mate ("suppress Angle1 and press again").
- **M8 accepted:** locks are unsuppressed in a `finally`; if that fails, the failure sentence says which
  compound gears are not locked.
- **M9 accepted:** a gear on a shaft whose solved speed is 0 through a fixed shaft is left fixed; the plan's
  "a fixed–turning mesh is jammed" claim is reworded.
- **M10 accepted:** ratios are computed in the record's gear order for each mesh entry, the pair matched
  unordered to the new Meshes rows.
- **M11 accepted:** "the rest of its train follow"; the fallback sentence no longer exists (answer 1).
- **M12 accepted** as written (set Drive back before deleting the control mate; check every frame against the
  built frames to 1e-6; before any save, assert no Drive global, angle mate or control mate is left and no lock
  is suppressed).
- **M13 accepted:** the loop test uses one internal mesh, or two meshes between the same two shafts.

## Rulings on package P0's findings (2026-11-14, after their independent review)

P0 is commits `0d638db` to `8504856`; the findings are in `findings.py` from "tier 8 items 7–13".

- **D8's follower case: an Update.** `LOCK_RETAKES_AN_OFFSET` is True on both versions, and the measurement
  tells a working lock from a dead one (11° and 3 mm kept through a drive; a dead lock would have read 18.5°).
  A follower's `At` or face-width change is carried by Update. The anchor's Front-plane cases stay structural
  (answer 3).
- **D7: a tooth change stays structural (Build again…) until probe P1b passes.** `GEAR_MATE_RATIO_ROUTE` is
  None. Changing the gear mate's definition in place works on 2026 and leaves an assembly SolidWorks 2024
  cannot close, so it is never used on either version. Deleting the gear mate and adding it again ("remake")
  gave the right ratio in the right sense on both, but on 2024 it has only run in a session that already held
  an assembly it could not close, and never in the shape an Update needs. P1b, in a fresh session on each
  version with the remake first: the part's teeth changed through its globals; locks suppressed, the gear mate
  remade and renamed, every gear put to its built frame; locks on, rebuild, drive at the new ratio,
  interference; close without saving and reopen; and the same on a gear that carries two gear mates. Both
  branches of D7 are coded and tested against the fake, as W5-PLAN says; only `"remake"` or None can be the
  finding, and code refuses `"modify definition"` with a sentence.
- **A lock does not hold against a put.** With the lock on, a `Transform2` put moved one gear, its locked
  partner did not follow, and SolidWorks reported nothing (both versions). This agrees with M1 and M8 — the
  app only ever puts with every lock of the train suppressed — and it changes the fake: its `place_component`
  must take a put on a locked gear silently and leave the partner where it was, as SolidWorks does, so a test
  can catch a put made with a lock on. What the lock does on its next solve after such a put was not measured
  (no drive followed); nothing may be built on it.
- **The train's rebuild: top-only (`ForceRebuild3(True)`) for Update, on probation for Build.**
  `MATED_ASSEMBLY_REBUILD_ROUTE` re-solved a changed global and a drive on a built, saved, reopened train and
  marked only the assembly, on both versions. Not yet shown: a train *built* under the top-only rebuild (the
  probe's train was built with the full one), a drive after a layout move under it, and 2024 in a session with
  no stuck assembly holding the shared layout and part. Probe round P0b adds those. Code passes the train kind
  for Build and Update alike; if P0b shows the build needs the full rebuild, the build gets its own kind in
  `swcom.rebuild_call` (package A's file) and nothing else changes. The demonstration (package E) does not run
  before P0b is committed and reviewed.
- **Mates are found by walking the mate group** (`MATE_FIND_ROUTE`), named by an `IFeature.Name` put
  (`MATE_RENAME_ROUTE`), all four kinds, both versions. The demonstration's drive holds and returns every gear
  to its built frame (M12 stands as written). A put on a gear in two gear mates holds.

## Rulings on probe round P0b (2026-11-14, after its independent review)

P0b is commits `10fb0d4`, `61d390e`, `4ced012`, `771c8eb` (results) and `4f865d8` (findings). Its review found
no must-fix: the 2024 evidence now comes from fresh sessions in which the remake ran first and nothing was
stranded beside it (`sw2024/probe-results-20261114-071324`), with the definition route alone in its own session
(`…-073328`), and the two differences between the versions that P0 had read are gone.

- **D7: a tooth change the globals carry is an Update, by the remake.** `GEAR_MATE_RATIO_ROUTE` is `"remake"`.
  Probe `gear_mate_update` carried it in an Update's shape on both versions: teeth changed through the part's
  globals, every lock suppressed, the gear mate deleted, made again at the new ratio and renamed, every gear put
  to its built frame, locks on, a top-only rebuild, the mate checks, a drive at the new ratio and sense (2.7°
  for 30°, where the old ratio gives 2.5° and the inverse about 20.8°), no interference, an unsaved close that
  left the file as saved, and a save, reopen and drive. `"modify definition"` is never used on either version.
  **Accepted with one gap:** on a gear that carries two gear mates the remake was driven and measured
  (`put_on_twice_meshed_gear`) but not in the whole Update shape (no tooth change in the parts, no puts, no
  interference, no unsaved close). A probe step on a train with an idler is asked of round P0c; until it is
  committed the demonstration's tooth change is on the 12 : 1, which has no such gear.
- **A train's Build may use the top-only rebuild.** `MATED_BUILD_REBUILD_ROUTE` is `"ForceRebuild3(True)"`: a
  train built with it as its only rebuild matched the full rebuild's train frame for frame and drove at its
  ratio, and its build marks nothing but the assembly, where the full rebuild leaves the layout and the part
  marked. The app has one route for the train kind (`swcom.rebuild_call` reads
  `MATED_ASSEMBLY_REBUILD_ROUTE`), so a train build refuses, before anything is made, when the two findings
  differ (package A's gate).
- **The lock against a put, measured:** after a put with the lock on, a drive turned both gears together with
  the relative angle the put left — the lock took the new angle and held it. The app still never puts with a
  lock on (M1, M8).

## Rulings on probe rounds P0c and P0d (2026-11-14, after their independent review)

P0c is commits `59910e0` to `c66d321`; its review found no must-fix and asked for three things to be read
again and four comments reworded, which round P0d did (`5667999`, `ed2fdc4`, `b2162a5`, `26cbf9c`). Both rounds
ran on SolidWorks 2026 and 2024, each started fresh, and read the same on both.

- **A tooth change on a gear that carries two gear mates is an Update** (`IDLER_UPDATE_HOLDS`). This closes the
  gap P0b's ruling left: on a train with an idler, the teeth changed through the parts' globals, both of the
  idler's gear mates were deleted, made again and renamed, every gear put, and the train drove at the new ratios,
  closed unsaved as saved, and reopened saved with the new teeth. Package A's Update refuses such a remake,
  before anything changes, while that finding is missing.
- **Interference is judged against a control.** At the old phase a changed train can happen to show no clash, so
  the demonstration's control is a gear put half a pitch off its new phase (`UPDATE_INTERFERENCE_CONTROL_HOLDS`).
- **The Update check may read every gear mate's ratio.** Reading a gear mate's definition marks no document
  (`GEAR_MATE_DEFINITION_READ_MARKS`), so an Update with nothing to do still changes nothing. The check reads it
  only while that finding says "nothing".
- **Mates may sit in folders.** A folder shows in the mate group's walk as two entries of type "FtrFolder" with
  the mates between them as ordinary entries, found by name; this held with a folder inside a folder, after a
  save and reopen, and with the folder suppressed (which suppresses the mates inside). A turning Update skips
  entries of that type and still refuses any other entry that is not a mate. A remade mate lands at the end of
  the mate group, outside its folder, and is left there. Not probed: turning a mate back on by itself while its
  folder is suppressed; the app must stop with a sentence if the mate still reads suppressed.
- **A turning Update refuses while a gear is loaded lightweight.** Forced lightweight, a train's first drive
  turned one gear wrongly and only then were its components resolved (`LIGHTWEIGHT_FIRST_DRIVE_RIGHT`,
  `LIGHTWEIGHT_RESOLVED_BY`). The app does not resolve components itself; it reads each gear
  (`COMPONENT_RESOLVED_ROUTE`, `COMPONENT_FULLY_RESOLVED_STATES`) in the check phase and says how to resolve
  them in SolidWorks. A plain open on this machine reads every gear resolved.
- **Mates are made with `CommandInProgress` on and renamed straight after they are made**
  (`MATES_UNDER_COMMAND_IN_PROGRESS`, `MATE_RENAME_AT_ONCE`); a train Build reads both findings first.
- **A lock that already reads on is never turned on again:** the call marks the assembly modified
  (`UNSUPPRESS_ON_LOCK_ALREADY_ON_MARKS_MODIFIED`). A suppressed mate reads error code 0 whatever it would
  report when on, so nothing judges a suppressed mate by its code.
- **The refused assembly stays open and is named** (answer 1 as built). A second new assembly beside it holds
  (`SECOND_ASSEMBLY_BESIDE_UNSAVED_HOLDS`), but no probe closed a new, never-saved, refused assembly on 2024
  under a watch for a dialog, so the job does not close it.
- **An unsaved Update can be closed without a question on both versions** (`UNSAVED_UPDATE_CLOSE_ASKS`), with
  the changed parts open in their own windows as Update leaves them. The app still closes nothing itself.
- **The "moved" tolerance of 1e-6 mm stands:** origins read 0.0 mm apart around a top-only rebuild and 2.8e-14 mm
  across a temporary drive (`ORIGIN_NOISE_MM`).
- **The demonstration keeps its temporary driving mate.** The drag operator, called as the macro database's
  entry calls it, turned only the dragged gear on these trains (`DRAG_OPERATOR_TURNS_TRAIN`); what differs from
  that entry's own success (the mate kind holding each gear, an internal mesh, the angle) was not varied. The
  person's drag in SolidWorks remains the check that a mouse turns the train (W5-PLAN §4.4).
