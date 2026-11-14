# W5 plan review (independent, cut short at the coordinator's request)

**Verdict: go with these changes.** The topology (one anchor per shaft, locks, one gear mate per tree edge) and the
build recipe agree with tier 8's findings. Four things must change before code: the restore-put rule, a sign error
in the tests and the demonstration, the base commit, and the probe list. Two decisions should go to the user: the
front-face-at-zero rule and the fallback.

Fixture numbers are from `scratchpad/w5r_fixtures.py`, which runs `layout.frames` and `kinematics.solve` on
`tests/fixtures/excel-windows/*`. They confirm the plan's §3.2 B values: the 12 : 1 anchors G1, G2, G4 with only
`"G4 Face Z" = 17`; Risky's G2 z_front 10, G4 18, G6 50; Arc_Move's `"G4 Face Z" = 15`.

---

## Must change before implementing

**M1. The restore put skips gears that are a whole tooth off, which breaks the lock and leaves a false "out of step" behind.**
- *What:* §1.6 step 6 puts "every gear not `same_frame` with its wanted frame (modulo pitch)". D4 and §0 say "every
  gear". These differ whenever a turn lands some gears on whole teeth.
- *Why it happens:* turning the input by n of its own teeth turns every gear it meshes with by exactly n of that
  gear's teeth (z1/z2 · 360/z1 = 360/z2).
- *Scenario (12 : 1):* the user turns G1 one tooth (21.18°). G2 turns 5.29°, which is one G2 pitch. G3 also turns
  5.29° through the lock, which is not a G3 pitch. G4 turns 1.76°.
  - Then G4's At changes, so a put is needed. G1 and G2 are `same_frame` mod pitch and are skipped; G3 and G4 are put.
  - The lock now holds G3 5.29° off its built angle relative to G2. Every mesh still meshes, so post-check and
    interference pass.
  - The next Update's `train_check(found, recorded)` gives δ3 − δ2 = −p2, which is not a whole G3 pitch. It reports
    "G3 had been turned out of step with G2" and puts again. That repeats on every press, with a false sentence each
    time.
- *Second hole:* the lock relation "δf − δa a whole follower pitch" (§1.6) is neither necessary nor sufficient once
  the anchor is off by whole anchor teeth.
- *Change:*
  - When a train needs any put, put **every mated gear of that train** unconditionally (that is what D4 argues for).
  - Test locks **exactly** (δf ≡ δa, to tolerance), not modulo a pitch.
  - Keep "mod pitch" only for meshes: there it is well defined, because a's whole-tooth slack times k is ±p_b.
  - Add a fake test for this exact one-tooth scenario.

**M2. A sign error in the B tests and in the driven proof (§3.2 B, §4.2).**
- `kinematics.solve`'s speeds are about each shaft's **own** axis (`speeds[...] = value * sign`).
- The plan's `mesh_links` k is right: own speed b / own speed a.
- But the test is written `k == ω_b·σ_b / (ω_a·σ_a)`, and §4.2 expects `δ_i = 30°·(ω_i·σ_i)/(ω_in·σ_in)` with δ_i
  measured about the gear's own axis (`turn_between`). Both are world-turn ratios.
- On Risky_Placements all three meshes come out with the opposite sign: G1–G2 is +0.700 by plan k and by own
  speeds, but −0.700 by the test formula. The 12 : 1 and Arc_Move are all Z+, so they cannot show it.
- *Effect:* either B's test fails against correct code, or an implementer "fixes" `mesh_links` to match. Either way
  m3 STOPs on a correct train, or passes a wrong one.
- *Change:* `k == ω_b/ω_a` and `δ_i = 30°·ω_i/ω_in`. Pin the Risky values (+0.7, +0.636364, −0.388889).

**M3. The base commit is wrong, which puts the work split at risk.**
- The plan builds on `9aeed80`. HEAD is already `8b1ef15`.
- The working tree also holds about 900 uncommitted lines of W4 review fixes in exactly the files packages I/A/B/C
  edit: `store.py`, `swbuild.py`, `swcom.py`, `ui_text.py`, `workbook/gearbox.py`, `workbook/update.py`,
  `workbook_gui.py`, and their tests.
- *Change:* the interface commit starts only once W4-REVIEW-3's fixes are committed, on that commit. Name it in
  `W5-INTERFACES.md`. Otherwise W5 reopens W4's journal, marks and ownership work through merge conflicts.

**M4. Probes the plan relies on but does not list (§0.3).** "Code does not wait, both branches written" is sound
for P1 and P2, because each has a safe structural branch. It is not sound for the following, which have no safe
branch:
- **Renaming a lock mate.** Tier 8 never renamed a lock, and §5 admits it. The plan's response to a failure is D2's
  fallback, so a failure would make **every compound gearbox build static, every time**. Add it to P0: rename the
  lock in `mated_train`'s saved train, then reopen and `find_mate` by the new name.
- **The demonstration's drive** (input Top plane to layout Right plane at 90°, driven 90 → 120). This is geometry
  tier 8 never drove. Probe it once in P0 on the scratch train, or drive as tier 8 did from a 10° offset. Do not
  first meet it inside E.
- **Puts in an undriven train on a gear that is in two gear mates** (an anchor such as G2). The record covers a put
  on the driven output, on a follower under a suppressed lock, and on the input with the drive suppressed (the
  `dragged["Transform2 put"]` route; I did not read its values, see "not checked"). Confirm from the record before
  relying on it, or add it to P2.
- Whatever M5's answer needs (a distance mate at 0, or a datum plane).

---

## Decide during implementation (several are for the user)

**M5. A front face on the Front plane makes common edits a Build again (D8). Ask the user.**
- `z_front = z − σ·face/2`, where z is mid-face.
- Anchors at z_front = 0: 12 : 1 G1 and G2, Arc_Move G1 and G2, Risky G1.
- With D8, **any face-width or At change on those gears** moves the front face off the plane and becomes structural.
  So "make the pinion wider" on the headline fixture needs a new revision, where W4 handled it as an Update.
- The sentence also blames "the front face moves off the Front plane" when the user changed a face width.
- Alternative: one datum plane in the layout part, far behind the Front plane (say 1000 mm), with every anchor's
  distance measured from it, so the distance never reaches 0 or changes sign. That removes all three D8 Front-plane
  cases. It needs a small probe (a distance mate from an offset plane).
- If D8 is kept, the sentence must name the edit, e.g. "G1's face width puts its front face …".

**M6. Fallback D2: ask the user whether to stop and say instead.**
- Mate problems are deterministic for a given workbook. So "Build again… tries again as a new revision" promises a
  retry that will fail the same way, and each press makes another static `_rN`.
- The refused `Assem<n>` is left open and unsaved, sharing the parts. If the user saves it from SolidWorks, they get
  a second assembly the record does not know.
- Option A (my preference): save no assembly. Keep the parts and layout, as W4's continued revision does (layout
  saved, assembly not). Say why, and let the next Build make the assembly once something changes.
- Option B: keep the fallback, but word the footer so it does not invite a retry unless the workbook changed.
- Either way, the job should try to close the refused document itself only if a probe shows that is safe on 2024;
  `scaffold.py:120` shows the hang.

**M7. Mates the user added by hand break every Update (§1.6 step 7).**
- *Scenario:* a mechanical user adds their own angle mate to drive or animate the train.
- Every turning gear then reads constrained status 3, so every Update fails the post-check with a sentence that is
  not true.
- A put on a driven gear is also unprobed, and is likely to fail `place_component`'s read-back.
- *Change:* in the check phase, look at `extra_mates` that touch a gear. Either refuse before changing anything,
  naming the mate ("suppress Angle1 and press again"), or skip the puts and the constrained check for that train and
  say so.

**M8. Locks left suppressed by an interrupted Update.**
- Step 6 suppresses every lock. A failure between the suppress and the unsuppress leaves them off, and B1 means
  nothing raises out.
- *Change:* unsuppress in a `finally`. If that fails, add the failure sentence "the compound gears G2 and G3 are not
  locked; press Update again". The next Update's D10 heals it anyway.

**M9. A free shaft held only by a fixed shaft.**
- The plan's claim "a fixed–turning mesh is jammed" (§1.2 step 4, D9) is false. `kinematics` settles a non-input
  shaft that meshes only a fixed shaft to speed 0, with no error.
- The plan leaves that shaft's anchor free to spin in SolidWorks, against the workbook.
- *Change:* also leave fixed every gear on a shaft whose solved speed is 0 through a fixed shaft. Fix the claim's
  wording.

**M10. Ratio orientation.**
- `ratios` must be computed in the **record's** gear order for each MESH entry, with the pair matched unordered to
  the new Meshes rows.
- Otherwise a row rewritten as G2–G1 reads as a change, and `set_gear_ratio` puts 68 : 17 on a mate whose first
  selection is G1.

**M11. Sentences that are not true in every state.**
- *"drag G1 in SolidWorks and the rest follow"* is false when the workbook also has a lone gear on an unmeshed
  shaft, or fixed-shaft gears. Say "the rest of its train follow", or list the trains.
- The fallback sentence's "close it without saving" asks the user to clean up after the app. Fine if D2 stays, but
  it should say the parts it shares are the saved ones.

**M12. Demonstration hygiene (§4.1, §4.2).**
- The wrong-sense control drives G4 the wrong way and then unsuppresses the original gear mate. That leaves G4
  about 5° out of phase with G3.
- m1's next step expects an Update to find nothing to put, so it will either STOP or "pass" for the wrong reason.
- Fix: set Drive back to its start value before deleting the control mate, and check every frame against the built
  frames to 1e-6. Put the half-pitch interference control back and check it the same way.
- Before any save the script makes, assert that no `Drive` global, angle mate or control mate is left, and that no
  lock is suppressed.

**M13. An impossible test.** §3.2 B's loop of "S1–S2, S2–S3, S3–S1 at consistent ratios" cannot be all external: three
external meshes in a triangle are always jammed. Make one of them internal, or use two meshes between the same
two shafts.

---

## Note for later

- D6's unmated loop-closing mesh rests on kinematics: inconsistent loop ratios are a "jammed" **error**, not a
  warning. W3 only *warns* about loop **phase** (`checks.py:97`: "a loop of meshes that does not close"). With D6
  such a mesh is placed teeth-in-teeth, and only the interference CHECK shows it. Acceptable; W7 must probe a
  gear-mate loop.
- The footer's `drag` gear goes stale if the user changes which shaft is the input. Harmless, since every gear in a
  train turns it.
- W6–W8 doors look open:
  - `MatePlan.kind` and the record's `mates` are open lists, and `train_check` links are per edge.
  - The "axis coincident" rule assumes ±Z layout axes; W6 needs its own probe anyway.
  - The anchor rule "first gear in Gears-sheet order" is frozen in the record, which is right. W8's per-mode
    suppression will want mate names that never depend on sheet order, and they don't.

---

## D1–D12

| | View | Ask the user? |
|---|---|---|
| D1 always turning | Agree: §6's static stand-in was conditional on the probe. | no |
| D2 automatic fallback | Disagree as worded: deterministic causes, a misleading retry, a stray open document (M6). | **yes** |
| D3 Build does not drive | Agree: leaves no mate behind, and the topology is pure and testable. | no |
| D4 restore every gear | Agree in principle; the §1.6 implementation contradicts it (M1). It is a surprise to say plainly. | **yes** (keep the user's turn?) |
| D5 W4 static stays static | Agree. | no |
| D6 no mate on a loop closer | Agree for W5 (no fixture has one); W7 probes it. | no |
| D7 ratio change by P1 | Agree: both branches are safe. | no |
| D8 new structural cases | Each is necessary given the mates, but the Front-plane cases bite the main fixture (M5). | **yes** (datum plane?) |
| D9 fixed shafts stay fixed | Agree; extend it to zero-speed shafts (M9). | no |
| D10 turn suppressed mates back on | Agree. | no |
| D11 schema 3 | Agree. Checked: the W4 reader takes max(schema_version 1, link_schema_version 3) = 3 > 2, raises UnknownSchema, and leaves the file alone (`store.py:722-725`). W2 builds still drop the gearbox block, as they do today. | no |
| D12 mate names | Agree: the ids cannot contain spaces, so the patterns never collide. | no |

## Checked and found sound

- The k sign formula in `mesh_links`.
- The z_front and anchor values for all three fixtures.
- The axial route and Flip for Z−: the sign of the origin's z decides, and the shaft sense does not matter.
- The DOF count: 4 + 1 constraints per anchor, a lock per follower, one gear mate per tree edge, so one freedom per
  train.
- Mesh relation modulo pitch_b is well defined.
- The W4-era reader's refusal of a schema-3 record.
- The report's misstated delete route, which the plan corrects (taken from the plan, not re-read from JSON).
- The tier-8 order of operations, against `p8_motion.mated_train` and `motion_update`.
- `place_component`'s read-back, which makes a put that does not hold a failure rather than silence.

## Not checked (stopped early)

- The recorded values of `mated_train.dragged["Transform2 put"]` and of the `motion_update` facts on both versions.
- P1/P2 call details against the type library.
- The fake's design, beyond reading §3.1.
- Every `ui_text` sentence against its states. Whether the window enables Build again… for a static record with
  nothing changed (needed for D5's footer).
- `SAME_NAME_OPEN_ERROR` and the journal and marks with a refused `Assem<n>` open.
- The 2024 memory budget of E.
- Package sizing.
- The Arc_Move restore after a swing, by hand.
