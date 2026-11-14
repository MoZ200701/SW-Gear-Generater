# W5 (motion): the interface commit

Package I of `W5-PLAN.md` §2. Packages A, B and C work in parallel from here, on disjoint files, reading only this
note and the code it names. **A change to a shape pinned here is a stop-and-ask**: private helpers, and
keyword-only parameters with defaults in your own module, are free.

Authority, highest first: `docs/PLAN-WORKBOOK.md` → `W5-DECISIONS.md` → `W5-PLAN-REVIEW.md` → `W5-PLAN.md`. Where
this note departs from W5-PLAN it says so (§4) and why.

## 1. Where it starts

- **Starting commit: `0551abc`** (branch `workbook`). The interface commit is `2f82a0e`; its independent review
  said go once its points were written in, which the follow-up commit after it does (rulings in §6).
- Review ruling M3 asked for the commit that *closes* W4 (the rebuild fix, its review's changes and the
  demonstration reruns on SolidWorks 2026 and 2024). W4's code is at `388c8d3` and reviewed; the W4-closing
  demonstration reruns were **still in flight on SolidWorks** when this was written. The orchestrator chose to start
  now and will reconcile if the reruns change app code.
- P0's findings (tier 8 items 7–13, `8504856`) and the rulings on them (`0551abc`) are in. Probe round P0b
  (a train *built* under the top-only rebuild; D7's remake in a fresh session) is not.
- Suite at the interface commit, clean `git archive`, Linux: **1759 passed, 1 skipped** (baseline at `8504856`:
  1699 passed, 1 skipped; +60 new tests). Windows Tk tests: 102 passed, 1 skipped.

## 2. Who edits what (from here)

| Package | May edit |
|---|---|
| A — SolidWorks | `swcom.py`, `swbuild.py`, `tests/test_swbuild.py`, `tests/test_swcom.py`; may add to `tests/test_swbuild_train.py` (never change an assertion there: it pins `turn_between`/`train_check`, which B relies on too) |
| B — planning | `workbook/motion.py`, `workbook/gearbox.py`, `workbook/update.py`, `workbook/layout.py`, `tests/test_workbook_{motion,gearbox,update,layout}.py` |
| C — record, words | `store.py`, `ui_text.py`, `tests/test_store.py`, `tests/test_ui_text.py` |
| D — window, boards, docs (after A–C) | `workbook_gui.py`, `gui.py` if needed, `tests/test_workbook_{build,window}.py`, `design/**`, `docs/**`, `README.md` |
| P0/P0b — probes | `findings.py`, `probe/**`, `src/gear_generator/probe/**`, `tests/test_findings.py`, `tests/test_probe_*.py`, `probe/results/**` |
| E — demonstration | `probe/workbook_assembly_check.py`, `probe/workbook_window_check.py`, `probe/results/**` |
| nobody | `workbook/geometry.py`, `kinematics.py`, `checks.py`, `gears/*.py` (I changed only `base.Mate`'s docstring) |

I also touched, for schema 3 only: `tests/test_workbook_window.py` (the "newer record" fixtures now say
`LINK_SCHEMA_VERSION + 1`) and `tests/test_ui_text.py` (likewise). Nothing else of D's or C's.

## 3. Pinned shapes, by module

### `swcom.py` (A writes the bodies)

- `class MateRefused(SolidWorksError)` — AddMate5 answered nothing, or not exactly one new mate appeared. A mate
  made with a non-1 status is **not** this.
- `class MateGone(ComponentGone)` — a recorded mate is not in the assembly any more. Sentence: *The mate "G1
  meshes G2" is not in Reducer_12to1.SLDASM any more: it was renamed or deleted in SolidWorks.* Update's check
  phase turns it into `swbuild.NotAsBuilt` (as `ComponentGone`).
- `@dataclass(frozen=True) class MateState: name: str; code: int = 0; warning: bool = True; suppressed: bool =
  False` — lives in swcom (it returns it); `swbuild.MateState` is the same class.
- `Session.add_mate(..., kind="lock")` dispatches to `_lock_mate(handle, a, b, name) -> (kept, "")` (stub). `a`,
  `b` are bare handles, anchor first.
- `Session.mate_status(name) -> Optional[int]` — the kept AddMate5 status; None for a mate this session did not make.
- `Session.mate_states() -> List[MateState]` — every mate in tree order (`MATE_FIND_ROUTE`); `[]` with no MateGroup.
- `Session.constrained_status(handle) -> int`.
- `Session.find_mate(handle, name) -> str` — keeps the mate as `handle`; missing → `MateGone`.
- `Session.set_mate_suppressed(handle, suppressed: bool) -> None` — `SUPPRESSION_ROUTE`, read back; does not rebuild.
- `Session.set_gear_ratio(handle, a, b, ratio: Tuple[int, int]) -> None` — `a`, `b` the gear mate's references in
  selection order (`placed1:Gear Axis`). Route `"remake"` only; None refuses ("not settled"); `"modify
  definition"` refuses whatever the finding says. Does not rebuild.
- Existing members, A's: `add_mate`/`_gear_mate` keep the status by kept name and never raise on it (pairs behave
  as before); "would not make" becomes `MateRefused`.

### `swbuild.py`

Written in full here (pure, shared by A and B; A must not change their behaviour):

- `turn_between(rotation_a, rotation_b, tolerance=POSE_TOLERANCE) -> Optional[float]` — radians in (−π, π], the
  turn about **a's own +Z** taking a to b; None for any other difference.
- `same_frame(...)` — refactored onto `turn_between`, behaviour unchanged.
- `TRAIN_TOLERANCE = 1e-5` (radians per relation).
- `MeshLink(a, b, k: float, pitch: float)` — b turns k × a's turn, each about its own +Z (`k == ω_b/ω_a`, M2);
  `pitch` = b's, degrees.
- `LockLink(anchor, follower, pitch: float)` — tested **exactly** (M1); `pitch` (follower's, degrees) is not used.
- `TrainCheck(off_axis: Tuple[str,...]=(), out_of_step: Tuple[Tuple[str,str],...]=(), turned: bool=False,
  residuals: Tuple[Tuple[str,str,float],...]=())`, `.in_step`.
- `train_check(found, wanted, meshes, locks, pitch: Mapping[str, float], tolerance=TRAIN_TOLERANCE) -> TrainCheck`.
  `found`/`wanted`: gear → (rotation 9 by rows, origin mm). Per wanted gear: missing, origin off by more than
  `POSE_TOLERANCE` mm, or not a pure turn about its own Z → `off_axis` (and its relations are not judged). δ =
  `turn_between(wanted, found)`. Mesh: `δb − k·δa` a whole number of b's pitch; lock: `δf − δa` ≡ 0 mod 2π; each to
  `tolerance`. `turned` = in step and some δ is not a whole number of that gear's `pitch` (missing/0: any turn).
  Gears found but not wanted are ignored. Tests: `tests/test_swbuild_train.py`.

Shapes (A fills them):

- `SolidWorks` protocol gains `mate_status`, `mate_states`, `constrained_status`, `find_mate`,
  `set_mate_suppressed`, `set_gear_ratio` (signatures as swcom's).
- `BuildResult.mate_problems: List[str]`, `BuildResult.mates: List[MateState]`.
- `build(sw, plan, exists, kind=None)` — **unchanged signature**. The mate check runs exactly when the resolved
  kind is `ASSEMBLY_TRAIN` (see its docstring). Each mate problem is also a failure, so the train is not saved.
- **Mate problem sentences** (A writes; C shows each as a whole sentence, never lower-cased or embedded): full
  sentences, capital first, full stop last, naming the mate by its tree name and a gear by its workbook id (the
  `gears` map `build_gearbox` is given; the Name2 only where none is known). Suggested: *SolidWorks would not make
  the mate G1 on S1 Axis.* · *The mate G3 locked to G2 over-defines the assembly.* · *SolidWorks answered 3 when
  making the mate G1 meshes G2.* · *The mate G1 meshes G2 is in error in SolidWorks.* · *The mate G4 along S3 is
  missing from the assembly.* / *… is suppressed in SolidWorks.* · *G2 is over-defined in SolidWorks.* · *G2
  cannot turn: SolidWorks reads it fully defined.* · *G2 reads 0 in SolidWorks, not free to turn.* Error-code
  numbers are logged, never interpreted. **Only real refusals** go into `mate_problems`: `MateRefused` from a
  `Mate` op, and the mate check's own findings (status, error code, missing, suppressed, constrained status). Any
  other raise during a mate (a COM or RPC failure, a selection that did not take) is an ordinary failed build as
  in W4: no mate problem, nothing recorded, Build stays enabled.
- `GearboxResult.kind: str = ""` — `GEARBOX_MOTION` if a train saved, `GEARBOX_STATIC` if a static assembly saved,
  `""` if none did. A refused train: `assembly` is that failed `BuildResult` (its `mate_problems`, and `document`
  the title it is left open under), `kind` `""`, nothing saved in its place, the parts and layout part saved
  before it stay saved.
- `build_gearbox(sw, parts, reuse, layout, assembly, gears, *, exists, progress, mtime)` — **unchanged signature**,
  no `static=`.
- `MateRef(name, kind, gears: Tuple[str,...], shaft: str = "")` — kinds `"axis"`, `"along"`, `"lock"`, `"mesh"`;
  LOCK gears `(anchor, follower)`; MESH `(a, b)` in the gear mate's selection order.
- `MotionUpdate(mates, meshes, locks, recorded: Tuple[Placement,...], recorded_meshes, face_globals:
  Tuple[Tuple[str, GlobalVariable], ...], ratios: Tuple[Tuple[str, int, int], ...], fixed: Tuple[str, ...])`, all
  defaulting to `()`. `face_globals` = (gear, its `"<Gear> Face Z"` as now wanted, literal |z_front| mm).
  `ratios` = (gear mate name, numerator, denominator) in the mate's own order; empty unless
  `GEAR_MATE_RATIO_ROUTE == "remake"`. `fixed` = gears left fixed (D9, M9), re-placed as W4 does.
- `update_gearbox(sw, parts, layout, assembly, placements, *, motion: Optional[MotionUpdate] = None, exists,
  progress, mtime)` — None is W4's static path byte for byte; given, the stub raises until A writes it.
- `MotionUpdate.recorded`: each `Placement`'s `pitch` is from the teeth **as built** (as `recorded_meshes`), not
  the pitch now wanted; `placements` carry the wanted ones.
- `GearboxUpdate` gains `turned: bool`, `out_of_step: List[Tuple[str,str]]`, `off_axis: List[str]`, `residuals:
  List[Tuple[str,str,float]]` (all from the check-phase `train_check` against the record, both maps restricted
  to the mated gears), `restored: List[Tuple[str, ...]]` (**changed from `bool` in the follow-up**: one entry per
  train that was put, its gears in `placements` order whose check-phase δ was not a whole number of their pitch —
  the gears turned back; no entry for a train put with none turned, never one for a train not put),
  `unsuppressed: List[str]` (mate names), `axial: List[str]` (**gear ids** whose Face Z was set),
  `ratios: List[str]` (mate names), `extra_mates: List[str]` (suppressed mates not on record, left alone),
  `mates: List[MateState]` (after the last rebuild). `found` and `placed` keep their W4 meanings on the motion
  path (every gear's frame as read before anything moved; every gear put, mated or fixed).
- Imported for A's use: `GEARBOX_MOTION`, `GEARBOX_STATIC` (from store), `MateGone`, `MateRefused`, `MateState`.
- No new `STAGE_*`.

**The motion path of `update_gearbox`, in order** (W5-PLAN §1.6 as the review and decisions amend it; A writes):

*Check — writes nothing:* W4's checks; the gate for `ASSEMBLY_TRAIN`; open the assembly; `find_component` each
placement; read every frame (`found`); `find_mate` every `MateRef` (`MateGone` → `NotAsBuilt`); `mate_states()` —
a mate not on record and **not suppressed** refuses the Update with a `BuildError` naming it (*… suppress Angle1
in SolidWorks and press Update SolidWorks again.*: M7), a suppressed one goes to `extra_mates`; recorded mates
found suppressed are noted; `train_check(found, recorded, recorded_meshes, locks, pitch)` with **both maps
restricted to the mated gears** (a fixed gear must never read as missing or off its axis) → `turned`,
`out_of_step`, `off_axis`, `residuals`. Counting mates for M7: a MateGroup sub-feature that is not a mate (a
folder) is not an unknown mate.
*Change — nothing raises out (B1):* 1. part and layout values (W4). 2. open/activate the assembly; a part or the
layout changed → `rebuild(kind=ASSEMBLY_TRAIN)`. 3. recorded mates found suppressed → unsuppressed (D10). 4. each
differing Face Z → `set_global_variable`, then rebuild (before any put). 5. read every frame (`live`). A train
(gears joined by meshes and locks) **needs a put** when, against `placements` (wanted), any of its gears is off
its axis or any relation is out of step, or a ratio of it is to be set; then **every mated gear of it** is put
(M1), with **every lock of that train suppressed** (the ruling: a lock does not hold against a put), rebuilt, put
(`place_component(..., kind=ASSEMBLY_TRAIN)`; ratios via `set_gear_ratio` inside this block, as P1b will run
it), the locks unsuppressed **in a `finally`** (M8: a failure there is a failure sentence naming the compound
gears not locked), rebuilt. A lone mated gear (no links) is put only when off its axis. `restored` gets an
entry per train put, from the check-phase δ's (see the field). Fixed gears: W4's rule, `same_frame` modulo pitch, `REPLACE_FIXED_ROUTE`. Nothing to put:
the train stays where the user turned it (D4). 6. Post-check: each put gear where it was put; `train_check(live
after, wanted)` in step for every train put; every recorded mate present, unsuppressed, code 0; every mated gear
`COMPONENT_UNDER_DEFINED`; each problem a failure sentence. 7. Interference (W4). `changed` gains the assembly when
steps 3–5 changed anything (a rebuild alone does not).

### `gears/base.py`

`Mate` docstring: kind `"lock"`, `a` and `b` bare handles, anchor first, no value/ratio/flip. `BuildPlan.check`
already accepts bare handles.

### `workbook/motion.py` (new; B writes the stubs)

- `AXIS, ALONG, LOCK, MESH = "axis", "along", "lock", "mesh"`; `MATE_KINDS`; `STATIC, MOTION =
  store.GEARBOX_STATIC, store.GEARBOX_MOTION`; `FACE_GLOBAL_SUFFIX = " Face Z"`.
- `MatePlan(name, kind, gears: Tuple[str,...], shaft="", ratio: Tuple[int,...]=(), face_global="", z_front=0.0)`.
- `MotionPlan(anchors: Mapping[str,str], mates, fixed, unmated: Tuple[Tuple[str,str],...], trains:
  Tuple[Tuple[str,...],...], drag: Tuple[str,...])`, all defaulted.
- Written: `mate_name(kind, gears, shaft="")` (AXIS *G1 on S1 Axis*, ALONG *G1 along S1*, LOCK gears (anchor,
  follower) → *G3 locked to G2*, MESH *G1 meshes G2*; anything else a ValueError), `face_global(gear)` → *G4 Face
  Z*, `mate_entry(MatePlan) -> store.MateEntry`, `mate_ref(store.MateEntry) -> swbuild.MateRef`.
- Stubs: `motion_reason() -> str` (its findings include `GEAR_MATE_ROUTE`, `MATE_COINCIDENT`, `MATE_DISTANCE`,
  `MATED_ASSEMBLY_REBUILD_ROUTE`), `update_reason() -> str` (does **not** read `GEAR_MATE_RATIO_ROUTE`: ruling
  c), `motion_plan(spec, report, frames) -> MotionPlan`, `motion_assembly_plan(layout_path, components,
  handle_of, motion, template, path) -> BuildPlan`, `mesh_links(meshes, teeth, sigma, internal) ->
  Tuple[MeshLink,...]`, `lock_links(locks, teeth) -> Tuple[LockLink,...]`. Each docstring is the contract.

### `workbook/gearbox.py` (B)

- `GearboxPlan.motion: Optional[MotionPlan] = None`, `GearboxPlan.static_reason: str = ""`. `build_kwargs()`
  unchanged (no `"static"`).
- `plan_gearbox`: `motion_reason() == ""` → `assembly = motion_assembly_plan(...)`, `motion = motion_plan(...)`;
  otherwise W4's `layout.assembly_plan(...)` and `static_reason` = the sentence. A continued revision likewise.
- `finish_build` writes, whenever the gearbox block is written: when the assembly saved, `gearbox.kind` =
  MOTION if `plan.motion` else STATIC — the plan is the one source; a non-empty `result.kind` must agree, a
  disagreement is a sentence in `Finished.notes`, an empty `result.kind` is never written; for `MOTION`, `mates = [mate_entry(m) for m in plan.motion.mates]`, `unmated`, `fixed`, `drag` from
  the plan, `static_reason = ""`; for `STATIC`, those empty and `static_reason = plan.static_reason`. Whenever the
  assembly was attempted (`result.assembly` not None): `mate_problems = list(result.assembly.mate_problems)` and
  `mate_problems_digest = digest` if any, else `""`. A refused train therefore leaves W4's continued revision
  (layout on record, `assembly` `""`) plus the problems and the read they came from.

### `workbook/update.py` (B)

- `UpdatePlan.motion: Optional[MotionUpdate] = None`, `axial: Tuple[str,...] = ()` (gears whose Face Z changes),
  `ratios: Tuple[str,...] = ()` (mate names). `update_kwargs()` adds `"motion"` **only when `motion` is not None**,
  so a static gearbox's call is W4's key for key.
- `classify`, `finish_update`: W5-PLAN §1.6's rules, with the rulings: refusal from `update_reason()`;
  structural — D8's cases, an anchor's front face reaching/leaving/crossing the Front plane **naming the edit**
  (*G1's face width moves its front face off the Front plane …*), and a meshed gear's tooth change while
  `GEAR_MATE_RATIO_ROUTE` is not `"remake"` (today: None; for `"modify definition"` the sentence says it leaves
  an assembly SolidWorks 2024 cannot close) — only the tooth change: Face Z changes, layout moves and turn-backs
  still go through Update (ruling c); a **follower's** At or face-width change is an Update
  (`LOCK_RETAKES_AN_OFFSET` True; read by getattr, missing → structural); M9's still shafts; M10's ratio order;
  recorded anchors never re-derived; a recorded MateEntry with a bad kind or gear count refuses with a sentence,
  never an IndexError. `finish_update`: `dragged` = `off_axis` plus W4's rule for fixed gears (a turn is never a
  drag); frames on record follow what
  was put; MESH `ratio` follows `result.ratios`, ALONG `z_front` follows `result.axial`.

### `store.py` (shapes and parse done here; C owns it from now)

- `LINK_SCHEMA_VERSION = 3`; `GEARBOX_STATIC = "static"`, `GEARBOX_MOTION = "motion"`, `GEARBOX_KINDS`.
- `MateEntry(name="", kind="", gears: List[str]=[], shaft="", ratio: List[int]=[], face_global="", z_front=0.0)`.
- `GearboxRecord` gains `kind: str = GEARBOX_STATIC`, `mates: List[MateEntry]`, `unmated: List[List[str]]`,
  `fixed: List[str]`, `drag: List[str]`, `static_reason: str`, `mate_problems: List[str]`,
  `mate_problems_digest: str`.
- Parse: `_checked` knows `List[int]` (whole floats become ints); `gearbox.mates` read with `_entries(MateEntry)`;
  a `kind` outside `GEARBOX_KINDS` is a `StoreError`. A v2 file reads as v3, kind static, no mates; a v4 file is
  refused and left byte-identical; `schema_version` on disk stays 1 for W2 builds. Tests in `tests/test_store.py`.
  C adds to the parse: a MateEntry whose `kind` is not one of the four, whose `gears` count is wrong for its kind,
  or a mesh whose `ratio` is not two numbers is a `StoreError` sentence.

### `ui_text.py` (C writes)

- `workbook_footer(..., digest: str = "")` — new keyword (D passes `self.reading.digest`). While the gearbox has no
  assembly and `mate_problems_digest == digest`, Build is **not enabled** (ruled to stay) and the sentence names the
  refused mate and says that **changing the workbook makes Build available again**. `motion_ready_line` says
  before Build when a W5 finding is missing and the gearbox will be built static (ruled to stay).
- New helpers (stubs): `drag_phrase(drag) -> str`, `motion_ready_line(plan) -> str`, `motion_done_line(plan,
  result) -> str`, `mate_refused_status(plan, result, again=False) -> Tuple[str, bool]`, `motion_record_line(record,
  digest="") -> str`, `motion_update_lines(update, result) -> List[str]`. Existing functions keep their signatures
  and call these.

## 4. Departures from W5-PLAN, and why

From **W5-DECISIONS answer 1** (a refused mate stops the build; no automatic static fallback, plan D2 gone):

- Dropped, as only the fallback needed them: `STAGE_STATIC`; `GearboxResult.motion_attempt`;
  `GearboxPlan.static_assembly`; `build_kwargs()["static"]`; `build_gearbox(static=…)` and its pre-flight checks;
  the `ok      static assembly built after the turning one was refused` log line; the fallback sentences
  (`gearbox_status`, the footer's "fallback record", `progress_text`'s); the `WorkbookFallback` board (D: make it
  `WorkbookRefused`).
- Kept for a W4-era static gearbox (D5): the whole static Update path (`motion=None`), `layout.assembly_plan`, and
  `GearboxRecord.kind` defaulting to static for a v2 record.
- Kept, but narrowed: `GearboxPlan.static_reason` / `GearboxRecord.static_reason` now mean only D1's
  *static by necessity* (a W5 finding missing at planning), never a refusal by SolidWorks.
- Added: `GearboxRecord.mate_problems` and `mate_problems_digest` (so "the footer never invites a retry of an
  unchanged workbook" can be decided from the record), and `workbook_footer(digest=)`.
- The refused document is left open and named (no probe shows closing it is safe on 2024); its title is
  `result.assembly.document`, so no new result field.

From **the review and the rulings**:

- M1: `train_check` tests locks exactly; when a train needs any put every mated gear of it is put (A's order above).
- M2: `MeshLink.k` is `ω_b/ω_a` about each gear's own axis; the tests pin the Risky signs.
- M7: Update refuses on **any unsuppressed mate not on record**, not only one "touching a gear": which components
  a mate joins has not been probed, and every component but the layout is a gear. A suppressed one is listed.
- M8: locks unsuppressed in a `finally`.
- Ruling on P0: a put is made only with every lock of its train suppressed; the fake's `place_component` takes a
  put on a locked gear silently and leaves the partner (A).
- D7 ruling, narrowed on review (§6 c): a route other than `"remake"` makes only a tooth change structural;
  `set_gear_ratio` refuses `"modify definition"` as the second guard; `ratios` stays empty today.

From **layering or clarity** (no ruling involved):

- `MateState` is in `swcom` (it returns it; `swcom` cannot import `swbuild`); `swbuild.MateState` is it.
- `build(..., *, mates=False)` is not added: the resolved kind (`ASSEMBLY_TRAIN`) decides the mate check.
- `set_gear_ratio(handle, a, b, ratio)`: the remake needs the two references; the plan had `(handle, ratio)`.
- `MotionUpdate.assembly_globals: Tuple[GlobalVariable]` became `face_globals: Tuple[(gear, GlobalVariable)]`, so
  `GearboxUpdate.axial` can name gears; `MotionUpdate.fixed` added (D9/M9 gears are re-placed W4's way).
- `MateRef` gains `shaft` (for *moved G4 along S3*).
- `motion_assembly_plan`'s `gear_of` is `handle_of` (gear id → handle), so its direction is unambiguous.
- `MatePlan.ratio` defaults to `()` (not `(0, 0)`) and `MateEntry.ratio` to `[]`: a mirror field for field.
- `TrainCheck.residuals` and `GearboxUpdate.residuals` added for the demonstration's log.
- The constants `"static"`/`"motion"` are defined once, in `store`; `motion.STATIC/MOTION` re-export them.

## 5. How each package reaches green on its own

Every command runs on a clean copy (`git archive` of your commit, `PYTHONPATH=src`), as the suite does.

- **A is green** when `pytest tests/test_swbuild.py tests/test_swcom.py tests/test_swbuild_train.py` passes **and**
  every other importer of the fake still does: `tests/test_bevel_forms.py tests/test_custom_properties.py
  tests/test_gear_mate.py tests/test_gears_bevel.py tests/test_gears_crossed.py tests/test_gears_internal.py
  tests/test_profile_shift.py tests/test_gears_helical.py tests/test_groove.py`. A owns the fake: a default
  `FakeSolidWorks()` answers clean mate states (status 1, code 0, nothing suppressed, mated gears 2) for an
  undoctored plan, and an override per test doctors it.
- **B is green** when `pytest tests/test_workbook_motion.py tests/test_workbook_gearbox.py tests/test_workbook_update.py
  tests/test_workbook_layout.py tests/test_workbook_demo_fixtures.py tests/test_probe_workbook.py` passes. Once
  `plan_gearbox` makes turning assemblies, the W4 end-to-end tests that run plan → `build_gearbox` on the fake →
  `update_gearbox` (`tests/test_workbook_update.py`'s `test_build_then_update_through_the_worker_and_nothing_is_left`,
  and those in `tests/test_workbook_gearbox.py` around lines 840, 927 and 1174) would hit A's stubs: B keeps them
  static with a fixture that monkeypatches `motion.motion_reason` to return a sentence (the G2 68 → 69 edit there
  would be structural on a turning gearbox anyway).
- **C is green** when `pytest tests/test_store.py tests/test_ui_text.py` passes (C's tests build plans and results
  by hand, never through A's or B's bodies).
- **May be red until D**: `tests/test_workbook_build.py` and `tests/test_workbook_window.py` (the window builds
  through the fake with B's turning plans); D restores them. Anything else red is a fault of the package that
  made it so.
- **The turning end-to-end round trip** (plan → fake build → finish → classify → update → finish → classify) is
  written once A's fake and motion path and B's bodies exist. I suggest **B, in a second pass** after A lands: it
  pins B's finish rules against A's results, in B's own test files; D then only wires the window.

## 6. Rulings on the review of `2f82a0e`

(a) The static build when a W5 finding is missing **stays**, said before Build. (b) Build **stays greyed** after a
refused mate for the same read, and the sentence says changing the workbook makes Build available again. (c)
**Narrowed**: a `GEAR_MATE_RATIO_ROUTE` other than None or `"remake"` makes only a tooth change structural; Face Z
changes, layout moves and turn-backs still go through Update; `set_gear_ratio` refusing `"modify definition"` is
the second guard. The follow-up's one shape change: `GearboxUpdate.restored` is a list per put train, not a bool.

## 7. Open points

**A.** Folders in the MateGroup are not mates (M7's count). The build of a train takes `MATED_ASSEMBLY_REBUILD_ROUTE` (top-only) "on probation" until P0b; if P0b says a
build needs the full rebuild, give it its own kind in `swcom.rebuild_call` — nothing else changes. Check that the
refused `Assem<n>` left open does not trip the same-name check or the journal on the next build (review: not
checked; unsaved documents are not compared today). The fake: model W5-PLAN §3.1 with the ruling above, and keep
the nine importers working. Gear names in mate problems need the `gears` map inside `build` (a private keyword is
free).

**B.** D7's Update branch is coded and fake-tested with `GEAR_MATE_RATIO_ROUTE` monkeypatched to `"remake"`; it
stays structural today. M9: decide "held still by a fixed shaft" from `report.motion.speeds` (0 through a fixed
shaft), and treat a shaft entering or leaving that state like a Role change. M13's loop test. Static by necessity
is tested by monkeypatching a finding away.

**C.** No fallback text anywhere. Every §1.8 sentence with a test that fills it from fields; the refused-build
sentence says the parts and layout part are kept, the open assembly's parts are the saved ones, and Build waits
for a changed workbook. M11's "the rest of its train follow".

**E.** After a real drag (the person's step and the drive-and-delete), log the origin and axis residuals of every
gear as well as the relation residuals: `POSE_TOLERANCE` 1e-6 mm against a mouse drag has not been measured.

**D.** Pass `digest=` to `workbook_footer`; the board `WorkbookRefused` in place of `WorkbookFallback`; PLAN-WORKBOOK
§4.4's dated note (W5-PLAN §0.4) and §4.5's W5 readings, now with answer 1 instead of D2.

The three choices flagged in the first version of this note were ruled on: §6.
