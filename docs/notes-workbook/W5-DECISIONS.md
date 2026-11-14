# W5: the user's answers and the orchestrator's rulings on the plan and its review

Read in this order: `docs/PLAN-WORKBOOK.md` (the authority), `W5-PLAN.md` (the implementation plan),
`W5-PLAN-REVIEW.md` (its independent review), then this file. Where they disagree, this file wins over the
review, the review over W5-PLAN, and PLAN-WORKBOOK over all three unless this file says a reading was chosen.
Written 2026-11-14 while the probe batch the review asked for (package P0) was still running; what depended on
its findings is ruled on in the last two sections, added the same day once they were committed and reviewed.

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

## Open until probe round P0b is committed

- D7's Update branch (above). Until then the user is told a tooth change needs Build again….
- Whether a train's Build may use the top-only rebuild (above).
