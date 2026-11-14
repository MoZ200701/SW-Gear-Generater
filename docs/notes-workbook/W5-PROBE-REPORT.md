Tier 8 (W5 motion) passes on SolidWorks 2026 and 2024 with every decision the same, so nothing STOPs: `motion_route` is "mates". 2026 is a full run, 75 of 75; 2024 is tier 8 alone, 31 of 31. The one version difference is the number GetErrorCode2 gives for a mate error. One gap: no API drag reproduces a mouse drag, so W5's "drag the input" has to be seen by a person.

## What SolidWorks is left in
- Only the user's 2024 is running: PID 52548, **5.54 GB private**, none of my documents open, and none of theirs open when last checked.
- My three 2026 instances (48364, 60308, and 67012 earlier) were each emptied and exited.
- No python.exe or Excel of mine is running; the memory watcher is stopped; free RAM is 8.32 GB.

## Probes (tier 8, `src/gear_generator/probe/p8_motion.py`)
I numbered it 8 because it builds on tier 7's layout part, flips and plane selection, so it must run after tier 7. PLAN-GEARBOX's tier 6 is the planner's wider tier and stays unused.

| Probe | What it does | 2026 full run | 2024 run |
|---|---|---|---|
| `motion_enums` | Mate types, alignments and error codes read from swconst.tlb (CONCENTRIC 1, LOCK 16, ALIGNED 0 / ANTI 1 / CLOSEST 2, OverDefined 5) | pass | pass |
| `shaft_axis_mates` | Eight gears placed and fixed as W4 leaves them, unfixed, mated to their shaft axis and along it by each candidate route, pushed, saved and reopened | pass, 54 s | pass, 70 s |
| `gear_mate_sense` | 22 pairs on layout axes, five to an assembly, all driven by one global | pass, 492 s | pass, 682 s |
| `compound_lock` | Two gears on one shaft held at 37° / 137° through drives, then a deliberately conflicting mate | pass, 146 s | pass, 150 s |
| `mated_train` | 17/68 + 17/51, once all Z+ and once with the middle shaft Z−; nine components | pass, 77 s | pass, 77 s |
| `motion_update` | Shaft moved by layout globals, mesh phase restored, lock re-taken, At moved by an assembly global | pass, 16 s | pass, 19 s |

Result files:
- 2026: `probe/results/latest.json` and `probe/results/probe-results-20261113-231301.{json,txt}`, run from a `git archive` snapshot of 707bfcb.
- 2024: `probe/results/sw2024/probe-results-20261113-223412.{json,txt}`, run from a snapshot of b9ddb12 (same tier 8 code), with a README row added. `sw2024/latest.json` is still the last full 2024 run.

**Faults in my own probe, fixed during iteration:**
- Held-on-axis and held-along-shaft were judged together; now judged separately.
- EditDelete and EditSuppress2 were fetched rather than called.
- GetWhatsWrong needs its three by-reference out-parameters.
- I first used Transform2 puts as a "drag".
- The shaft-move globals were written to only six figures.
- I sped up the layout builder (FeatureByPositionReverse, Select2 on the returned planes) and batched the sense pairs (779 s down to about 260 s).

## Decisions and findings (`findings.py`, pinned in `tests/test_findings.py` against both versions)
- **Holding a gear on its shaft:**
  - `AXIS_MATE_ROUTE` "axis coincident": AddMate5(COINCIDENT, CLOSEST) between the gear's Gear Axis and the layout's "<Shaft> Axis". No jump; closest keeps a Z− gear anti-aligned (IMate2.Alignment reads 0 on Z+, 1 on Z−). A 25° turn stays; 5 mm off-axis, 5 mm along, and a 10° tilt all come back; it survives a reopen.
  - `AXIS_CONCENTRIC_REFUSED` True: concentric between two axes is **refused** (AddMate5 returns None, status 0).
  - Also tried: the cylinder's face concentric with the axis holds. Explicit ALIGNED or ANTI_ALIGNED turns the gear over.
  - Selecting the axes works by FeatureByName+Select2, by SelectByID2 `"<axis>@<component>@<assembly>"`, and by GetCorresponding+Select4.
- **Axial position:** `AXIAL_MATE_ROUTE` "origin distance": the gear's origin (`Point1@Origin`) to the layout's Front plane, distance |z|, Flip set when z < 0; coincident when z = 0. A Front-plane-to-Front-plane distance lands on the wrong side.
- **The Flip rule:** `GEAR_MATE_FLIP_RULE` "mesh", `GEAR_MATE_FLIP` False. Every mesh, external or ring, on any shafts, takes **Flip False**.
  - Evidence: with Flip False every external pair turned opposite ways about +Z for Z+Z+, Z+Z−, Z−Z+ and Z−Z−, with the bigger tooth count first or second, with axes, faces or one of each selected; Flip True reversed it.
  - An annulus round its pinion turned the same way with Flip False: ring selected first or second, ring on Z+ or Z−, axes or faces.
  - The alignment argument is ignored (IMate2.Alignment always reads 2).
  - Of six candidate rules, only "mesh" fits every case.
  - What the mate stores as IGearMateFeatureData.Reverse is a different thing: Flip XOR (axes opposed) XOR ring.
  - The layout's own two axes are refused as gear-mate entities.
  - What breaks it: a pinion inside the ring's bore but axially clear of the ring's face is read as external. W3's checks already require meshing faces to overlap. Lightweight components are untried.
- **Compound lock:** `COMPOUND_LOCK_ROUTE` "lock alone". AddMate5(LOCK=16) on the two components, each selected with Select4 and a mark-1 SelectData. The second gear is *not* also mated to the axis. It held 37° through 30° and 90° drives on Z+ and Z− with no errors.
  - Lock plus the second gear also on the axis is flagged over-defined (warnings; GetConstrainedStatus 4 on Z−).
  - An angle mate between the two Top planes at 37° or 137° also held. A 1:1 gear mate held with Flip off and slipped with it on.
- **How over-definition shows to the API:**
  - AddMate5's status out-parameter (`status.value`; the call returns the mate, not a tuple) is 5, **but the mate is still made**.
  - GetErrorCode2 is non-zero, and IsWarning False marks the mate at fault. 2026 gives 46/47/1; **2024 gives 51 for the same mates**. Never read meaning into the number.
  - GetConstrainedStatus is 4, and GetWhatsWrongCount rises.
  - **ForceRebuild3 still returns True.**
  - Deleting with Select2 then DeleteSelection2(0) clears it.
- **One degree of freedom:** every gear reads 2 (under-defined) until a single angle-mate drive on the input makes all of them 3 (fully defined).
- **The train:** no gear moved when mated from W4's fixed state; driven 30°, each output turned 2.5° (1/12) the same way on both trains, again after a reopen.
- **Gear mates follow the solver, not transforms:**
  - Transform2 put, SetTransformAndSolve2, and IDragOperator Drag/DragAsUI (TransformType 0/1/2, DragMode 0/1/2/3, every call returning True) turned the input alone.
  - A put on the output is kept, and the train does not follow.
- **Item 7 (Update after motion):**
  - `LAYOUT_MOVE_CARRIES_MATES` True: changing the layout part's globals moved the mated gear with its axis, and the train still turns 1/12.
  - When a shaft swings Δφ round its partner, SolidWorks turns the gear **−(1+zp/zq)·Δφ**, the opposite of the +(1+zp/zq)·Δφ that keeps it meshed.
  - `MESH_PHASE_ROUTE` "Transform2 put with the gear mate on": the put is kept, the rest of the train does not move, and the train then turns 1/12 from the new phase.
  - Suppress / put / unsuppress also works. Delete and re-add was not needed, so it is untried.
  - `LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE` True: a lock suppressed (SetSuppression2, this configuration), its second gear put 11° round, then unsuppressed, holds the new 11° through a drive.
  - `AXIAL_GLOBAL_MOVES_GEAR` True: linking the axial mate's D1 to an assembly global and changing the global moves that gear alone.

## Commits (my files only; no push; no attribution line)
- `c53bc2d` tier 8 probe, `__main__`, `decide` (motion decisions), `tests/test_probe_motion.py`
- `b9ddb12` the probe's own fixes (drag settings, exact shaft move)
- `853e91b` results: 2026 full run, 2024 tier 8, sw2024 README
- `9aeed80` findings, and tier-8 pins in `tests/test_findings.py` for both versions

The full suite is green: 1536 passed, 10 skipped. Nothing of mine is left uncommitted.

## For the W5 implementer
**Primitives:**
1. **Unfix:** `swcom.unfix_component`, as it exists.
2. **Axis mate:** `add_mate("coincident", "gearN:Gear Axis", "layout:<Shaft> Axis")`, existing. Closest alignment; never pass an explicit one.
3. **Axial mate:** `add_mate("point distance", "gearN:origin", "layout:plane1", value=z_front)`, existing (it flips negatives). Use `"point"` when z_front = 0.
4. **Gear mate:** existing `_gear_mate` with `ratio=(z_first, z_second)` (numerator goes with the first selection) and **flip=False always**.
5. **NEW lock mate:**
   - ClearSelection2.
   - For each of the two components: CreateSelectData, set Mark=1, then `Select4(append, data, False)`.
   - AddMate5(16, 2, False, 0,0,0, 1,1, 0,0,0, False, False, 0, status).
   - Read back exactly one new mate.
6. **NEW mate check after the rebuild:**
   - Read AddMate5's `status.value` and refuse anything but 1.
   - Read every mate's `GetErrorCode2(out IsWarning)` and refuse any non-zero code, naming the mates where IsWarning is False.
   - GetConstrainedStatus 4 is a further check.
7. **NEW for Update:**
   - Re-place gears with `place_component` (Transform2 put) while the gear mates stay on.
   - For a compound phase change: suppress the lock, put, unsuppress — via `IFeature.SetSuppression2(swSuppressFeature / swUnSuppressFeature, swThisConfiguration, None)`, read back with IsSuppressed2.
   - Move At either by setting the axial mate's D1 value or by linking it to an assembly global.

**Order of operations, turning W4's fixed assembly into a turning one:**
1. NewAssembly; insert the layout, place it at identity, fix it.
2. For each gear, AddComponent and Place at its W4 frame. Fixing first is optional; the probe went through fix, then unfix.
3. For each shaft, pick an anchor (the first gear on it in sheet order). Unfix it, then add the axis-coincident mate and the origin-distance mate.
4. Every other gear on that shaft: unfix it and lock it to the anchor. Do **not** mate it to the axis as well.
5. For each listed mesh, add a gear mate between the two Gear Axes at (za, zb), Flip False.
6. Rebuild, run the mate check, run the interference check, SaveAs.
7. Add no drive: the input's free turn is the one degree of freedom.

**On Update:**
- Shaft moves: set the layout globals, rebuild the layout, then the assembly.
- Then Transform2-put every gear to the frame `workbook.layout.frames` gives, gear mates left on. This is needed because SolidWorks swings the phase the wrong way on a move.
- Compound pairs: suppress the lock, put, unsuppress.
- At changes: change the axial mate's distance.
- A side change or tooth-count change stays structural, as in W4.

**Still to show:** W5's demonstrable, dragging the input in SolidWorks and seeing the output turn 1/12 the right way, has to be watched by a person on both versions; no API drag stands in for it.