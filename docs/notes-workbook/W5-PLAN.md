# W5 (motion): the implementation plan

**Authority and reading order.** `docs/PLAN-WORKBOOK.md` (§4.4, §6) is the authority. This plan builds on the W4
code as committed on `workbook` (`9aeed80`) and on probe tier 8 (`findings.py`, "the workbook gearbox that turns").
Before writing code, read: `W5-PROBE-REPORT.md` (this folder), `findings.py` from "-- the workbook gearbox that
turns (tier 8)" to the end, `probe/p8_motion.py` (`mount`, `select_components`, `add_mate`, `suppress`,
`delete_mate`, `drive_mate`, `mated_train`, `motion_update`), then this plan. Every SolidWorks call below names
the finding it rests on. **A call with no finding is not made**: §0.3 lists the two probes to add first.

Rules carried over from W4, unchanged: commits by explicit path only, prose messages with the why, **no Claude
co-author or attribution line**, no push, never `add -A` / `commit -a` / stash / reset; findings only from committed
`findings.py`, read with `getattr(findings, NAME, None)` and refused with a sentence when missing; every raise a
full sentence; the repo is public (no user document titles in committed logs: `<user document N>`); SolidWorks 2024
on the host is the user's live session — close only what you created, never exit it.

---

## 0. Summary

Build makes a **turning assembly** for every workbook W4 can lay out (all shafts on the frame, axes Z±). Each
shaft's first gear (its **anchor**) is unfixed and mated to its `"<Shaft> Axis"` (coincident, closest) and along it
(its origin at a distance from the layout's Front plane, the distance linked to an assembly global
`"<Gear> Face Z"`); every other gear on that shaft is unfixed and **locked** to the anchor and nothing else; every
listed mesh is a **gear mate** at its tooth ratio with Flip False — except a mesh that closes a loop, whose ratio
already follows from the others. Then one rebuild, a **mate check** (AddMate5 status, every mate's error code and
suppression, every gear under-defined), save, interference. If SolidWorks refuses or flags a mate, the same job
builds the W4 static assembly at the same path instead and says why. Update SolidWorks compares positions, axes
and the meshes' relative phase — not each gear's turn — so a train the user turned is not "moved by hand"; when it
must put any gear it puts every gear back to the built turn, with the locks suppressed around the puts.

### 0.1 Decisions the user may overrule (each with its reason)

| # | Decision | Why |
|---|---|---|
| D1 | **Build always makes the turning assembly**; there is no "static" choice in the window. | PLAN's own decision row made the static assembly a stand-in "until the gear_mate probe has passed"; it has, on both versions. A choice would add a control and a state to every footer for no use found yet. |
| D2 | **Automatic static fallback.** If any mate is refused or flagged, the job builds the W4 static assembly at the same path in a new document, saves it, records `kind: static` with the reason, and leaves the refused document **open and unsaved** with its title in the sentence. | The plan says "the static assembly stays". Closing the refused document from the job is not safe: on 2024, `CloseDoc` of an assembly whose saved parts changed opened a modal dialog and hung the probe (`probe/scaffold.py:120`). Nothing half-made is saved; nothing is overwritten (the path was free). |
| D3 | **Build does not drive the train.** The app claims only what it checked: the mates were made, SolidWorks reports none in error, and every turning gear is under-defined. The driven proof (output turns 1/12, the right way) is made by the demonstration script, with a wrong-sense negative control. | "One degree of freedom" cannot be read without a drive (every gear reads 2 until a drive makes all 3). A drive from the input's built phase (θ = 0, an angle of 0 between Top planes) is outside what tier 8 drove (10° → 40°); a drive left behind would be a mate the user did not ask for; it costs a rebuild per step. The topology (one gear mate per tree edge, one lock per extra gear, one axis + one axial mate per anchor) gives exactly one freedom per train by construction, and that is pure and tested. |
| D4 | **Update returns the train to its built turn whenever it has to put any gear**; with nothing to put, it leaves the train where the user turned it. | A put turns one gear alone (`MESH_PHASE_ROUTE`, mated_train): putting only the moved gears back to their planned frames while the rest stand turned would break their meshes. Putting every gear restores every mesh and keeps the record's frames true. |
| D5 | **W4's static gearboxes stay static.** Update keeps W4's path for them. The footer says they were built before gears could turn and that **Build again…** makes a turning revision; it is never forced. | Changing a saved assembly's kind in place (unfix + mate in a reopened assembly) is unprobed; a build-again is the W4 route for anything Update cannot carry. |
| D6 | **A mesh that closes a loop gets no gear mate** (recorded as `unmated`). | Its ratio is implied: W3's kinematics solves the loop exactly (a contradiction is already a "jammed" error). A redundant gear mate would be redundant constraint in SolidWorks, which the fake treats as over-definition and SolidWorks has not been asked about. No W5 fixture has a loop; W7's planetary will. |
| D7 | **A tooth change the part's globals carry** (68 → 69) is an Update *if* probe P1 finds a way to change a gear mate's ratio in a saved assembly; otherwise it is **structural** (Build again…). | The ratio lives in the gear mate; no finding covers changing it. Both branches are coded and tested against the fake; P1's finding picks one. |
| D8 | **Structural in a turning gearbox** (W4 called some of these moves): a shaft's Z± flipped; a gear moved to another shaft; a shaft's Role becoming or ceasing to be `fixed`; an anchor's front face reaching, leaving or crossing the Front plane; a follower's place along its shaft changing *if* probe P2 fails. | The axis mate keeps the alignment it was made with (`IMate2.Alignment` 0 on Z+, 1 on Z−); mates name the shaft; a coincident axial mate has no distance to set and a distance mate keeps its flip (as `OFFSET_GLOBAL_CROSSES_ZERO` for planes). |
| D9 | **Gears on a shaft whose Role is `fixed` stay fixed**, as W4 placed them, unmated. | It is what "fixed" says; in a W5 train a fixed shaft that meshes a turning one is already a "jammed" error, so this only touches unmeshed fixed shafts now, and keeps W7's fixed ring possible. |
| D10 | **Update turns back on a recorded mate it finds suppressed**, and says so. | The record says what the assembly is; W4 likewise put back a gear dragged off its frame. |
| D11 | **The link record's schema becomes 3.** A W4-era build refuses a W5 record (its newer-schema sentence) and leaves it byte-identical; W5 reads a v2 record as `kind: static`. | A W4 build reading a W5 record would drop `kind` and `mates` on its next write, and a later W5 would take a turning assembly for a static one. `schema_version` stays 1 on disk for W2 builds, as now. |
| D12 | **Mate names the user sees** in the FeatureManager tree: `G1 on S1 Axis`, `G1 along S1`, `G3 locked to G2`, `G1 meshes G2`; assembly globals `"G4 Face Z"`. | Gear and shaft names are letters, digits, `_` and `-` (schema), so the names are unique and legal; Update finds mates by these names (§1.6). |

### 0.2 What the probes established (tier 8; do not re-probe)

`AXIS_MATE_ROUTE` "axis coincident" (concentric refused: `AXIS_CONCENTRIC_REFUSED`); `AXIAL_MATE_ROUTE` "origin
distance" (|z|, Flip when z < 0; coincident at 0); `GEAR_MATE_FLIP_RULE` "mesh", `GEAR_MATE_FLIP` False for every
mesh, ring or not, any shafts; `GEAR_MATE_NUMERATOR_FIRST`; `COMPOUND_LOCK_ROUTE` "lock alone" (`MATE_LOCK` 16,
both components by Select4 with a mark-1 select data); over-definition shows in AddMate5's status
(`ADD_MATE_OVER_DEFINED` 5, mate still made), any non-zero `GetErrorCode2` (numbers differ by version: never read
meaning into them), `GetConstrainedStatus` 4; `ForceRebuild3` still True; `MOTION_ROUTE` "mates" (12 : 1 train,
all Z+ and with a Z− middle shaft, driven 30° → output 2.5° the same way, also after a reopen); no API drag
reproduces a mouse drag; `LAYOUT_MOVE_CARRIES_MATES` (but SolidWorks swings the phase the wrong way);
`MESH_PHASE_ROUTE` "Transform2 put with the gear mate on"; `LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE`;
`AXIAL_GLOBAL_MOVES_GEAR` (the axial mate's D1 linked to an assembly global). Mates were found by `Name` in a
reopened assembly (motion_update: `GearMate2`, `Lock1`, `Distance1`). Renaming a mate by `Name` put is what
`pair.py`'s turning plan does (`Gear Mate`, `Centre Distance`), built on both versions by
`probe/gear_pairs_check.py`, and p8's `drive_mate` renamed its drives.

**One correction to the report:** it says a mate was deleted by "Select2 then DeleteSelection2(0)"; the recorded
fact (`compound_lock` → `over_defined.deleted_by`) is **"Select2 then EditDelete()"**. Only P1's remake route and
the demonstration delete mates.

### 0.3 Probes to add first (package P0)

Both go into `probe/p8_motion.py` as tier-8 items 7 and 8, run after `motion_update` on its saved train, on
SolidWorks 2026 and on 2024 in a fresh session. Code does not wait for them (both branches are coded and
fake-tested); the demonstration does.

| Probe | Calls | Why no finding covers it | Feeds |
|---|---|---|---|
| **P1 `gear_mate_ratio`** | In the reopened train: (a) `IFeature.GetDefinition` of `G3 meshes G4`'s gear mate → `IGearMateFeatureData.GearRatioNumerator` / `GearRatioDenominator` put → `IFeature.ModifyDefinition(data, doc, None)` (the pattern of `TWIST_REVERSE_ROUTE`); read back; drive 30° and measure the new ratio; save, reopen, drive again. (b) only if (a) fails: delete the gear mate ("Select2 then EditDelete()"), `AddMate5(MATE_GEAR, …)` between the two components found by `GetComponentByName`, new ratio, Flip False; same measurements. | Tier 8 read `GearRatioNumerator`/`Denominator` but never set them, and never made a mate in a reopened assembly. | `findings.GEAR_MATE_RATIO_ROUTE` = `"modify definition"`, `"remake"` or `None` → D7: Update or structural. |
| **P2 `lock_retake_offset`** | In the reopened train: suppress the compound lock (`SetSuppression2`, this configuration), put its second gear 3 mm along its axis and 11° round (`Transform2` put), unsuppress, rebuild, drive; measure the relative frame (angle **and** axial offset) before and after the drive. | `LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE` measured the angle only. | `findings.LOCK_RETAKES_AN_OFFSET` True/False → a follower's At / face-width change is an Update or structural (D8). |

P0 also commits, **from the existing tier-8 results** (no new run; values in `probe/results/latest.json`,
`motion_enums` → `motion_enum_values`, and `motion_update` → `suppressed_by`), with `decide.py` entries and
`test_findings.py` pins against both versions' files:

```python
FEATURE_SUPPRESS = 0        # swFeatureSuppressionAction_e.swSuppressFeature
FEATURE_UNSUPPRESS = 1      # swFeatureSuppressionAction_e.swUnSuppressFeature
THIS_CONFIGURATION = 1      # swInConfigurationOpts_e.swThisConfiguration
SUPPRESSION_ROUTE = "SetSuppression2 this configuration, None"   # motion_update: suppressed_by / unsuppressed_by
LOCK_SELECT_ROUTE = "Select4 with a mark-1 select data"          # compound_lock: lock_results[*].select
MATE_DELETE_ROUTE = "Select2 then EditDelete()"                  # compound_lock: over_defined.deleted_by
```

### 0.4 PLAN-WORKBOOK §4.4 against the probes (for a dated note)

§4.4 says "mated **concentric** to its shaft axis" — concentric between two axes is **refused**
(`AXIS_CONCENTRIC_REFUSED`); the route is **coincident**, closest alignment. It says "compound gears are locked
**by an angle mate**" — the route is a **lock mate alone** (`COMPOUND_LOCK_ROUTE`); an angle mate between Top planes
also held, but the lock needs no angle and no planes. It says "unfixed and mated … to its axial position" for
**each gear** — only each shaft's anchor is; a locked gear also on its axis over-defines. It names PLAN-GEARBOX's
**tier 6 items 3–5** — they were settled as **tier 8** (`p8_motion`), which stands on tier 7. It does not say that
SolidWorks swings a gear's phase the wrong way when its shaft moves, so Update puts every gear back. Package D
writes this as *Readings changed by probe tier 8 (2026-11-13)* under §4.4, and §6's W5 row precondition as "probe
tier 8 has passed".

### 0.5 STOP and ask (implementers)

- Any SolidWorks call this plan does not tie to a finding, or a finding read differently from §0.2/§0.3
  (`MOTION_ROUTE` not "mates", `GEAR_MATE_FLIP_RULE` not "mesh", `COMPOUND_LOCK_ROUTE` not "lock alone", …).
- Changing a shape the interface commit pins (a field, a parameter, a return type). Private helpers and
  keyword-only parameters with defaults in your own module are free.
- On SolidWorks (package E): a gear moving more than 1e-6 mm / 1e-6 when mated; any mate error, status other than
  1, or a gear not reading 2 on a clean fixture; a driven ratio off by more than 1e-6 or the wrong sense; the
  wrong-sense control **not** caught; an Update after a turn reporting "out of step" (the tolerance, §1.6, is
  wrong); interference at the built phase; the demonstration's drive (§4.2) behaving otherwise than a drive.
- P1 finding neither route, or P2 failing, is **not** a stop: the structural branch stands, and the user is told.

---

## 1. Design

### 1.1 Who decides what

- **Planning (pure, Tk thread)**: `workbook/motion.py` (new) decides anchors, locks, gear mates, loops, trains,
  names and globals, and makes the turning assembly's `BuildPlan`. `gearbox.plan_gearbox` attaches it and the
  static fallback plan. `update.classify` turns the record's mates and the new read into a `MotionUpdate`.
- **Worker (`swbuild`)**: runs the plans; checks mates; falls back; in Update, compares by `train_check` (pure, in
  `swbuild`, since `swbuild` must not import `workbook`) and puts.
- **`swcom`**: the COM calls.
- **Record (`store`)** and **words (`ui_text`)**.

### 1.2 `workbook/motion.py` (new, pure)

```python
AXIS, ALONG, LOCK, MESH = "axis", "along", "lock", "mesh"       # MatePlan.kind
STATIC, MOTION = "static", "motion"                             # GearboxRecord.kind, GearboxResult.kind

@dataclass(frozen=True)
class MatePlan:
    """One mate the turning assembly makes; store.MateEntry mirrors it field for field."""
    name: str                       # its name in SolidWorks' tree (mate_name)
    kind: str                       # AXIS | ALONG | LOCK | MESH
    gears: Tuple[str, ...]          # AXIS/ALONG (gear,); LOCK (anchor, follower); MESH (a, b) as the Meshes row lists them
    shaft: str = ""                 # AXIS/ALONG: the shaft
    ratio: Tuple[int, int] = (0, 0) # MESH: (teeth of a, teeth of b) as made
    face_global: str = ""           # ALONG: "G4 Face Z", or "" when the origin sits on the Front plane (coincident)
    z_front: float = 0.0            # ALONG: the origin's signed distance from the Front plane, mm, as made

@dataclass(frozen=True)
class MotionPlan:
    anchors: Mapping[str, str]                  # shaft -> its anchor gear (first on it in Gears-sheet order)
    mates: Tuple[MatePlan, ...]                 # in plan order: per shaft AXIS, ALONG, LOCKs; then MESHes
    fixed: Tuple[str, ...] = ()                 # gears left fixed (on a Role = fixed shaft), D9
    unmated: Tuple[Tuple[str, str], ...] = ()   # meshes that close a loop: listed, no gear mate (D6)
    trains: Tuple[Tuple[str, ...], ...] = ()    # each train's shafts joined by gear mates, input shaft first
    drag: Tuple[str, ...] = ()                  # per train, the gear to drag: the anchor of its first input shaft

def mate_name(kind: str, gears: Sequence[str], shaft: str = "") -> str:
    # AXIS "G1 on S1 Axis" · ALONG "G1 along S1" · LOCK "G3 locked to G2" (follower, anchor) · MESH "G1 meshes G2"
def face_global(gear: str) -> str:              # "G4 Face Z"
def motion_reason() -> str:
    """"" when every finding Build needs is settled, else the sentence (D1's static-by-necessity case):
    MOTION_ROUTE == "mates", AXIS_MATE_ROUTE == "axis coincident", AXIAL_MATE_ROUTE == "origin distance",
    GEAR_MATE_FLIP_RULE == "mesh", GEAR_MATE_NUMERATOR_FIRST is True, COMPOUND_LOCK_ROUTE == "lock alone",
    MATE_LOCK, MATE_GEAR, ADD_MATE_NO_ERROR, LOCK_SELECT_ROUTE, COMPONENT_UNDER_DEFINED not None."""
def update_reason() -> str:
    """Likewise for Update of a turning gearbox: MESH_PHASE_ROUTE == "Transform2 put with the gear mate on",
    LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE, LAYOUT_MOVE_CARRIES_MATES, AXIAL_GLOBAL_MOVES_GEAR all True,
    SUPPRESSION_ROUTE, FEATURE_SUPPRESS, FEATURE_UNSUPPRESS, THIS_CONFIGURATION not None."""
def motion_plan(spec: GearboxSpec, report: Report, frames: Mapping[str, Frame]) -> MotionPlan
def motion_assembly_plan(layout_path: str, components: Sequence[Tuple[str, str, Frame]],
                         gear_of: Mapping[str, str], motion: MotionPlan, template: str, path: str) -> BuildPlan
def mesh_links(meshes: Sequence[Tuple[str, str]], teeth: Mapping[str, int], sigma: Mapping[str, int],
               internal: Mapping[str, bool]) -> Tuple[swbuild.MeshLink, ...]
def lock_links(locks: Sequence[Tuple[str, str]], teeth: Mapping[str, int]) -> Tuple[swbuild.LockLink, ...]
```

**`motion_plan`** (called only after `motion_reason() == ""` and `a.lay_out_refusal() == ""`):

1. `on[shaft]` = placed gears (`report.layout.placed`) on each shaft, in Gears-sheet order.
2. Shafts with `role == "fixed"`: their gears go to `fixed`, no mates.
3. Every other shaft with gears, in Shafts-sheet order: anchor `on[s][0]`; `MatePlan(AXIS)`; `MatePlan(ALONG,
   z_front=frames[anchor].at[2], face_global=face_global(anchor) if abs(z_front) >= layout.BASE_TOLERANCE else "")`;
   for each further gear `f`, `MatePlan(LOCK, gears=(anchor, f))`.
4. Meshes in Meshes-sheet order, union-find over shafts: a mesh with either gear on a fixed shaft gets no mate (in a
   buildable W5 workbook both are then fixed: a fixed–turning mesh is "jammed"); a mesh whose shafts are already
   joined goes to `unmated`; otherwise join them and add `MatePlan(MESH, gears=(a, b), ratio=(za, zb))`.
5. `trains`: the joined shaft sets that hold at least one gear mate, each ordered input shafts first then Shafts
   order; `drag`: per train, the anchor of its first input shaft (every train has one: a meshed shaft no input
   settles is already an error, `checks._check_motion`). An unmeshed, non-fixed shaft's gears turn alone and are in
   no train.

**`motion_assembly_plan`** — the op order; `h(g)` is the gear's handle (`gear<index>`, as W4), `L` is
`layout.LAYOUT_HANDLE`, `AX` is `pair.AXIS_NAME` ("Gear Axis"):

```
NewAssembly(template)
AddGlobal("G4 Face Z", literal(round(abs(z_front), 9)))     for every ALONG with face_global, in plan order
AddComponent(L) · Place(L, IDENTITY, origin) · Fix(L)        exactly as layout.assembly_plan (incl. its
AddComponent(h) · Place(h, frame) · Fix(h)   for each gear    REPLACE_FIXED_ROUTE Unfix wrapping)
for each shaft (plan order of AXIS mates):
    Unfix(h(anchor))
    Mate(id, "coincident", f"{h}:{AX}", f"{L}:{S} Axis", name="G1 on S1 Axis")
    Mate(id, "point", f"{h}:origin", f"{L}:plane1", name="G1 along S1")                       when z_front == 0
    Mate(id, "point distance", f"{h}:origin", f"{L}:plane1", value=z_front, name="G4 along S3")  otherwise
    LinkDimension("D1@G4 along S3", '"G4 Face Z"')                                              with it
    for each LOCK (anchor a, follower f): Unfix(h(f)) · Mate(id, "lock", h(a), h(f), name="G3 locked to G2")
for each MESH: Mate(id, "gear", f"{h(a)}:{AX}", f"{h(b)}:{AX}", ratio=(za, zb), flip=findings.GEAR_MATE_FLIP,
                    name="G1 meshes G2")
Rebuild()
SaveAs(path)
```

Gears are placed and fixed first, then each is unfixed **immediately before its own mates** — the sequence
`mated_train` ran ("no gear moved when mated from W4's fixed state"). This also absorbs the first-component
difference (fixed on 2024, floating on 2026): the layout is the first component and is fixed by `Fix`, which reads
`IsFixed` first; `Unfix` reads it too. `plan.check()` must be empty (a test). Mate ids are by index
(`axis1`, `along1`, `lock1`, `mesh1`) so no gear name can collide.

**`mesh_links`**: for a listed mesh (a, b), b turns `k` times a's turn about each part's own +Z:
`k = -σa·σb·za/zb` outside, `k = +σa·σb·za/zb` when either gear is internal; `pitch = 360/zb`.
**`lock_links`**: `(anchor, follower, pitch = 360/z_follower)`. (Derivation: a gear on Z− turned θ about its own
axis turns −θ about +Z, `layout.frame`'s `F₋`; outside, world turns are opposite and scaled by za/zb; a pinion and
its ring turn the same way, `GEAR_MATE_FLIP` evidence.)

### 1.3 Where the motion plan goes in `gearbox.plan_gearbox`

`GearboxPlan` gains (additive, defaults keep every W4 construction working):

```python
motion: Optional[motion.MotionPlan] = None         # None: the assembly is static (static_reason says why)
static_assembly: Optional[BuildPlan] = None        # W4's layout.assembly_plan at the same path: the fallback (D2)
static_reason: str = ""                            # "" with a motion plan, or a parts-only plan
```

Where W4 makes `assembly = layout.assembly_plan(...)`: if `motion.motion_reason()` is `""`, `assembly =
motion_assembly_plan(...)`, `static_assembly = layout.assembly_plan(...)` (unchanged W4 plan, same path) and
`motion = motion_plan(...)`; else `assembly` is W4's plan and `static_reason` the sentence.
`build_kwargs()` adds `"static": self.static_assembly` (None when there is no motion plan). A continued revision
(layout saved, assembly not) is planned the same way. Nothing else in planning changes.

### 1.4 The worker: `swbuild.build_gearbox` with mates

New and changed shapes (interface commit):

```python
@dataclass(frozen=True)
class MateState:
    """One mate as SolidWorks holds it after a rebuild."""
    name: str
    code: int = 0             # IFeature.GetErrorCode2; any non-zero is a problem, whatever the number (2024 ≠ 2026)
    warning: bool = True      # its IsWarning; False marks the mate at fault
    suppressed: bool = False  # IFeature.IsSuppressed2(THIS_CONFIGURATION)

BuildResult  += mate_problems: List[str]   # sentences; non-empty ⇒ the document is not saved and a fallback may run
             += mates: List[MateState]     # as read by the mate check
GearboxResult += kind: str = ""            # motion.MOTION or motion.STATIC: which assembly saved ("" none)
              += motion_attempt: Optional[BuildResult] = None   # the turning assembly refused, left open unsaved

def build(sw, plan, exists=os.path.exists, *, mates: bool = False) -> BuildResult
def build_gearbox(sw, parts, reuse=(), layout=None, assembly=None, gears=None, *, static: Optional[BuildPlan] = None,
                  exists=..., progress=None, mtime=...) -> GearboxResult
STAGE_STATIC = "static"      # building the static assembly after the turning one was refused (Step.name: its stem)
```

Order, against W4's steps (only what is new is described):

1. **Pre-flight**: also `static.check()`; `static`'s `SaveAs` path must equal `assembly`'s; `static` given without
   `assembly` is a `BuildError`.
2. Parts, then the layout: unchanged.
3. The assembly: `_build_in_job(sw, assembly, exists, mates=any(isinstance(op, base.Mate) for op in
   assembly.ops))`. Inside `build`, after `_run`, `rebuild` and `_verify`, and **before the save**, `_check_mates`:
   - A failure raised by a `Mate` op in `_run` (refused, not made, renamed otherwise, no dimension) is copied into
     `mate_problems` too (`_run` knows the op).
   - For every `Mate` op's name: `sw.mate_status(name)` must be `findings.ADD_MATE_NO_ERROR` (1); 5 is "over-defines
     the assembly", anything else "answered <n>".
   - `sw.mate_states()`: every planned mate present, `code == 0`, not suppressed. A non-zero code names the mates
     whose `warning` is False as at fault, else all of them; the number is logged, never interpreted.
   - Each mated gear — a handle in a `Mate` op whose last `Fix`/`Unfix` op is `Unfix` (the layout's last is `Fix`) —
     `sw.constrained_status(handle)` must be `COMPONENT_UNDER_DEFINED` (2): 4 is "over-defined", 3 is "cannot turn:
     SolidWorks reads it fully defined", anything else "reads <n>".
   - Each problem is a sentence in `mate_problems` and a failure; the save is skipped (`build` saves only when
     `result.ok`). `mates` keeps what was read, for the log.
4. **Fallback (D2)**: if the assembly did not save **and** `assembly_result.mate_problems` is non-empty **and**
   `static` is given: `say(Step(STAGE_STATIC, stem))`, `result.motion_attempt = <that result>`, `result.assembly =
   _build_in_job(sw, static, exists)` (a new document, same path, still free). Any other assembly failure (template
   missing, a part refused) does not fall back: the static plan would fail the same way.
5. `result.kind` = `MOTION` if the turning assembly saved, `STATIC` if a static one did; then interference as W4, on
   whichever saved (the gears stand at the built phase either way).

**Time:** tier 8 made 16 mates with selections in 21.8 s; the 12 : 1 reducer makes 9 (3 axis, 3 along, 1 lock, 2
gear), so ~10–15 s more than W4's build, plus a few hundred ms for the check.

### 1.5 `swcom.Session`: new and changed members

| Member | COM, in order | Finding |
|---|---|---|
| `add_mate(..., kind="lock")` → `_lock_mate(handle, a, b, name)` | `ClearSelection2`; for `a` (anchor) then `b`: `SelectionManager.CreateSelectData`, `Mark = 1`, `IComponent2.Select4(append, data, False)`, selected count read back; `AddMate5(MATE_LOCK, MATE_ALIGN_CLOSEST, False, 0,0,0, 1,1, 0,0,0, False, False, 0, status)`; exactly one new mate in the MateGroup; rename if named. | `COMPOUND_LOCK_ROUTE`, `LOCK_SELECT_ROUTE`, `MATE_LOCK` |
| `add_mate` / `_gear_mate` (all kinds) | unchanged calls; **also** read `status.value` (or the tuple's second item, as p8's `add_mate` does) and keep it by the kept name. **Does not raise on it** (the strip's pairs keep their behaviour); `None` / no new mate still raises, now as `MateRefused`. | `ADD_MATE_NO_ERROR`, `ADD_MATE_OVER_DEFINED` |
| `mate_status(name) -> Optional[int]` | the kept status, or None | — |
| `mate_states() -> List[MateState]` | walk `FirstFeature` → `MateGroup` → `GetFirstSubFeature` / `GetNextSubFeature`: `Name`; `GetErrorCode2(_out_bool())` (tuple or `.value`); `IsSuppressed2(THIS_CONFIGURATION, null dispatch)` (tuple/list → first item) | p8 `mate_errors`, `suppress().state` |
| `constrained_status(handle) -> int` | `IComponent2.GetConstrainedStatus`, read and called if a method comes back (p4's `member`) | `COMPONENT_*_DEFINED` |
| `find_mate(handle, name) -> str` | the MateGroup walk by `Name`; registers the feature under `handle`; missing → `MateGone` (a `ComponentGone`): *"The mate "G1 meshes G2" is not in Reducer_12to1.SLDASM any more: it was renamed or deleted in SolidWorks."* | motion_update (found by name after reopen) |
| `set_mate_suppressed(handle, suppressed: bool)` | `IFeature.SetSuppression2(FEATURE_SUPPRESS or FEATURE_UNSUPPRESS, THIS_CONFIGURATION, None)`; read back `IsSuppressed2`; raise with a sentence if it did not take | `SUPPRESSION_ROUTE` |
| `set_gear_ratio(handle, ratio)` | per `GEAR_MATE_RATIO_ROUTE` (P1): "modify definition" → `GetDefinition`, put `GearRatioNumerator`/`Denominator` (numerator with the first selection: `GEAR_MATE_NUMERATOR_FIRST`), `ModifyDefinition(data, doc, None)`, read back; "remake" → `MATE_DELETE_ROUTE` then `_gear_mate` with the same name and Flip; None → raise "not settled" | P1 |
| `MateRefused(SolidWorksError)`, `MateGone(ComponentGone)` | exceptions | — |

All through `swcom.call` / `_guarded` / `_put` as W4's N3 requires. `SolidWorks` protocol in `swbuild` gains
`mate_status`, `mate_states`, `constrained_status`, `find_mate`, `set_mate_suppressed`, `set_gear_ratio`.

### 1.6 Update SolidWorks on a turning gearbox

**What is compared.** Per gear: position (origin to `POSE_TOLERANCE` mm) and axis (the rotation differs only by a
turn about the part's own Z, as `same_frame`'s test). **Not** each gear's turn: per listed, mated mesh (a, b), with
`δ` each gear's own turn from one frame to the other, `δb − k·δa` must be a whole number of `pitch_b`; per lock,
`δf − δa` a whole number of the follower's pitch. That is: the same gearbox up to a turn of each train and whole
teeth. Pure, in `swbuild`:

```python
TRAIN_TOLERANCE = 1e-5     # radians on each relation; the demonstration logs the residuals it sees (§4)

@dataclass(frozen=True)
class MeshLink:  a: str; b: str; k: float; pitch: float          # degrees
@dataclass(frozen=True)
class LockLink:  anchor: str; follower: str; pitch: float          # the follower's pitch, degrees
@dataclass(frozen=True)
class TrainCheck:
    off_axis: Tuple[str, ...] = ()                    # gears not at their place or not along their axis
    out_of_step: Tuple[Tuple[str, str], ...] = ()     # (a, b) meshes and (anchor, follower) locks out of step
    turned: bool = False                              # in step, and some gear turned other than by whole teeth
    @property
    def in_step(self) -> bool: return not (self.off_axis or self.out_of_step)

def turn_between(rotation_a, rotation_b, tolerance=POSE_TOLERANCE) -> Optional[float]
    """The turn about a's own Z (radians) taking a to b, or None when they differ otherwise (same_frame's M)."""
def train_check(found: Mapping[str, Tuple[rot, at]], wanted: Mapping[str, Tuple[rot, at]],
                meshes: Sequence[MeshLink], locks: Sequence[LockLink], pitch: Mapping[str, float],
                tolerance=TRAIN_TOLERANCE) -> TrainCheck
```

`same_frame` is refactored onto `turn_between`, behaviour unchanged (its tests stay).

**What Update is given** — `update_gearbox(..., motion: Optional[MotionUpdate] = None)`; None is W4's static path,
untouched:

```python
@dataclass(frozen=True)
class MateRef:     name: str; kind: str; gears: Tuple[str, ...]     # a recorded mate, by gear ids
@dataclass(frozen=True)
class MotionUpdate:
    mates: Tuple[MateRef, ...]                       # every mate on record
    meshes: Tuple[MeshLink, ...]                     # with the tooth counts now wanted
    locks: Tuple[LockLink, ...]
    recorded: Tuple[Placement, ...]                  # the frames on record (what was last put)
    recorded_meshes: Tuple[MeshLink, ...]            # with the tooth counts the gear mates hold now
    assembly_globals: Tuple[GlobalVariable, ...]     # every "<Gear> Face Z" as now wanted
    ratios: Tuple[Tuple[str, float, float], ...] = ()   # (gear mate name, numerator, denominator) to set (D7)
```

`GearboxUpdate` gains: `turned: bool`, `out_of_step: List[Tuple[str, str]]`, `off_axis: List[str]` (all as found
before any change, against the record), `restored: bool` (the train had been turned and was put back), `unsuppressed:
List[str]`, `axial: List[str]` (globals set), `ratios: List[str]` (mates set), `extra_mates: List[str]` (mates in the
assembly the record does not list), `mates: List[MateState]` (after the last rebuild).

**The order, motion path** (check phase writes nothing; after it nothing raises out — W4's B1):

*Check:* as W4 for parts and the layout; then open the assembly (`OpenDoc6` + `ActivateDoc3`, `UPDATE_OPEN_ROUTE`),
`find_component` each (`COMPONENT_FIND_ROUTE`), **read every frame now** (`found`, before anything changes; W4's
static path still reads them later), `find_mate` every recorded mate (missing → `NotAsBuilt`, so the window offers
Build again…, as for a missing component), `mate_states()` (suppressed ones noted; names not on record →
`extra_mates`), the assembly's `equations()`. `train_check(found, recorded, recorded_meshes, locks)` → `turned`,
`out_of_step`, `off_axis`.

*Change:*
1. Parts' values, then the layout's (W4, unchanged).
2. Open and activate the assembly. If a part or the layout changed: `rebuild()` — the mates carry the gears with
   their axes (`LAYOUT_MOVE_CARRIES_MATES`); SolidWorks also swings their phase the wrong way, put right in 6.
3. Each recorded mate found suppressed: `set_mate_suppressed(…, False)` (D10) → `unsuppressed`.
4. Each `"<Gear> Face Z"` that differs: `set_global_variable` (indexed `Equation(i)` put, `EQUATION_SET_ROUTE`;
   assembly globals, `AXIAL_GLOBAL_MOVES_GEAR`) → `axial`; then `rebuild()`. Must come before the puts:
   `place_component` reads the frame back after its own `ForceRebuild3`, and an axial mate still at the old
   distance would pull the gear back.
5. Each `ratios` entry: `set_gear_ratio` (only when `GEAR_MATE_RATIO_ROUTE` is set; `classify` never asks otherwise).
6. Read every frame (`live`). **Puts** are needed when `train_check(live, wanted, meshes, locks)` is not in step
   (a shaft moved, an At or face changed, a tooth count changed the phases, or the user turned a mesh out of step).
   Then: every lock `set_mate_suppressed(True)`; `rebuild()`; `place_component` **every gear not `same_frame`
   with its wanted frame** (modulo pitch, W4's rule; in a turned train that is every gear: D4); every lock
   `set_mate_suppressed(False)`; `rebuild()`. (Order as motion_update ran it: suppress, rebuild, put,
   unsuppress, rebuild. Puts with the gear mates on: `MESH_PHASE_ROUTE`. A follower's put changes its angle — and,
   with `LOCK_RETAKES_AN_OFFSET`, its place along the shaft — under the suppressed lock.) If `live` is in step,
   nothing is put: the train stays where the user turned it.
7. **Post-check:** every frame again against wanted (`same_frame`; one off is a failure *"G4 is not where Update
   SolidWorks put it once the assembly rebuilt: a mate holds it elsewhere."*); `mate_states()`: every recorded mate
   unsuppressed, code 0; every mated gear `constrained_status` 2. This makes any surprise from an unprobed
   combination a sentence, never silence.
8. Interference (W4).

`result.changed` gains the assembly when 2–6 changed anything. With nothing changed anywhere and a turned train,
nothing is touched (W4's S2): the sentence says the gears stand where they were turned.

**`update.classify` on a turning record** (`box.kind == MOTION`; W4's rules otherwise):

- Refusal when `motion.update_reason()` is not `""`.
- Structural, in addition to W4's: D8's cases; and, while `GEAR_MATE_RATIO_ROUTE` is None, a meshed gear whose tooth
  count changes (its gear mate's ratio). Sentences in §1.8.
- A shaft's X/Y/Z change, an At, a face width, a tooth count (with the route): a move or value change, as W4; the
  record's mates are kept (Update never re-derives anchors: a reordered Gears sheet keeps the recorded anchors).
- `MotionUpdate` from the record's `mates` (names, kinds, gears), the new read's teeth / sigma / internal
  (`mesh_links`, `lock_links`), the record's components (`recorded`), the record's mate ratios
  (`recorded_meshes`), `assembly_globals` for every recorded ALONG with a `face_global` (value |new z_front|), and
  `ratios` for every MESH whose (za, zb) changed. `UpdatePlan` gains `motion: Optional[MotionUpdate] = None`,
  `axial: Tuple[str, ...] = ()` (gears whose Face Z changes) and `ratios: Tuple[str, ...] = ()` (mates whose ratio
  changes), for the sentence; `update_kwargs()` adds `"motion"`.
- `finish_update`: for a turning record, `dragged` is only `off_axis` gears put back (a turn is not a drag); the
  recorded frames follow what was put, as W4; MESH entries' `ratio` follow `result.ratios`; ALONG entries' `z_front`
  follow `result.axial`.

### 1.7 The record (`store.py`, schema 3)

```python
LINK_SCHEMA_VERSION = 3

@dataclass
class MateEntry:                      # motion.MatePlan field for field: MateEntry(**asdict(mate_plan))
    name: str = ""
    kind: str = ""
    gears: List[str] = field(default_factory=list)
    shaft: str = ""
    ratio: List[int] = field(default_factory=list)
    face_global: str = ""
    z_front: float = 0.0

GearboxRecord += kind: str = "static"                     # "static" | "motion"; a v2 record reads as static
              += mates: List[MateEntry] = []              # a turning assembly's mates, as made or last updated
              += unmated: List[List[str]] = []            # meshes listed but not gear-mated (D6)
              += fixed: List[str] = []                    # gears left fixed (D9)
              += drag: List[str] = []                     # per train, the gear to drag (for the footer)
              += static_reason: str = ""                  # why a build meant to turn is static ("" for W4's)
```

`_checked` learns `List[int]`; `link_record_from_json` reads `gearbox.mates` with `_entries(MateEntry, …)`. A v2
file reads as v3 with `kind = "static"`; a v3 file is refused by W4's reader (D11); the `schema_version: 1` shown to
W2 builds is unchanged. `finish_build` writes `kind = result.kind`, and for `MOTION` the plan's mates, unmated,
fixed and drag; for a fallback, `static_reason` = the first of `result.motion_attempt.mate_problems`, for a static
plan `plan.static_reason`. **Journal and marks:** unchanged — the journal's assembly entry is the same path whichever
assembly saves; an Update that changes the assembly (globals, ratios, unsuppress, puts) marks it unsaved as W4 does;
a turned-only Update changes nothing and marks nothing.

### 1.8 The window and its sentences (`ui_text.py`)

House style: full sentences, the workbook's words, true in every state; no sentence claims a check that was not
made. New text (exact; `{…}` filled from fields, never from another sentence):

**Before Build** (`_ready_build`, appended):
- motion: *"Its gears are mated to their shafts and to each other, so they turn together in SolidWorks."*
- static by necessity: *"Its gears are placed meshed and fixed, not mated to turn: {static_reason}"* with
  `motion_reason()`'s sentence, e.g. *"how gears are mated to turn is not settled for this version
  (findings.MOTION_ROUTE)."*

**After Build** (`gearbox_status`; the interference ending for a turning assembly reads *"; no interference between
the gears where they stand"*):
- one train: *"Its gears are mated to turn together, and SolidWorks reports no mate in error: drag {G1} in
  SolidWorks and the rest follow."*
- two trains: *"Its gears are mated to turn in 2 trains, and SolidWorks reports no mate in error: drag {G1} to turn
  one and {G5} to turn the other."* · three or more: *"… in {n} trains, …: drag {G1, G5 and G9}, one for each."*
- no train (no meshes): *"Its gears are each mated to their shaft, free to turn, and SolidWorks reports no mate in
  error."*
- fallback (ok False): *"They are placed meshed and fixed, not turning: SolidWorks would not mate them ({problem}).
  The assembly it could not mate is left open in SolidWorks as {title}, not saved: close it without saving."*
  `{problem}` is `mate_problems[0]` without its full stop, e.g. *"the lock G3 locked to G2 over-defines the
  assembly"*, *"the mate G1 meshes G2 is in error in SolidWorks"*, *"G2 cannot turn: SolidWorks reads it fully
  defined"*, *"SolidWorks would not make the mate G1 on S1 Axis"*.

**Footer, a gearbox on record** (`workbook_footer`, appended in Build again… states whose sentence is not an error):
- motion: *"It was built with its gears mated to turn: drag {G1} in SolidWorks to turn the gearbox."* (two trains:
  *"… drag {G1} or {G5} to turn its trains."*)
- W4's static record (`static_reason == ""`): *"It was built static, before gears could be mated to turn: Build
  again… makes a new revision whose gears turn."*
- fallback record: *"It was built static because SolidWorks would not mate its gears ({static_reason}): Build
  again… tries again as a new revision."*

**Build again? question** (`build_again_question`), in place of "Nothing on record needs a new revision." for a
static record: *"{Reducer_12to1.SLDASM} was built static; the new revision's gears are mated to turn."*

**Update summary** (`update_summary`), new pieces: *"move {G4} along {S3}"* (from `axial`), *"set the gear mate
{G1 meshes G2} to {17 : 69}"* (from `ratios`). W4's *"re-place {G2, G3 and G4}"* stays.

**After Update** (`gearbox_update_status`), new pieces and sentences:
- *"moved {G4} along {S3}"* · *"set the gear mate {G1 meshes G2} to {17 : 69}"* · *"turned the mate {G1 meshes G2}
  back on"* followed later by *" ({it was} suppressed in SolidWorks)"*.
- `restored`: *"The gears had been turned in SolidWorks; they are back at the turn they were built at."*
- `out_of_step`: *"{G4} had been turned out of step with {G3} in SolidWorks; {it is} back in mesh."*
- `off_axis`: W4's *"… had been moved in SolidWorks; put back where the workbook has it"* (unchanged words).
- nothing changed and `turned`: `ALREADY_MATCHES` + *" The gears stand where they were turned in SolidWorks."*
- `extra_mates`: *"{Reducer_12to1.SLDASM} also has mates the app did not make ({Angle1}); Update SolidWorks left
  them as they are."*
- Post-check failures arrive as worker failures (W4's *"Update SolidWorks stopped. …"*): *"{G4} is not where Update
  SolidWorks put it once the assembly rebuilt: a mate holds it elsewhere."*, *"The mate {G1 meshes G2} is in error
  in SolidWorks after the update."*, *"{G2} is over-defined in SolidWorks after the update."*

**Structural** (`update.classify`, folded by `_reason` as W4's):
- *"{S2}'s axis turned from {Z+} to {Z-}, and the mates hold each gear on it the way it faced when built, so it
  needs a new revision."*
- *"{G3} moved from {S2} to {S3}, and its mates hold it to {S2}, so it needs a new revision."*
- *"{S3} is now fixed, and its gears were built mated to turn, so it needs a new revision."* /
  *"{S3} is no longer fixed, and its gears were built fixed, so it needs a new revision."*
- *"{G1}'s front face moves off the Front plane ({0} → {2} mm), and its mate along {S1} has no distance to set, so
  it needs a new revision."* · *"… moves onto the Front plane ({2} → {0} mm), and its mate along {S1} cannot reach
  it, …"* · *"… crosses the Front plane ({2} → {-3} mm), and its mate along {S1} cannot follow a distance across it,
  …"*
- without P1's route: *"{G2}'s teeth changed from {68} to {69}, and the gear mate {G1 meshes G2} still turns at {17
  : 68}: Update SolidWorks cannot change a gear mate's ratio, so it needs a new revision."*
- without P2's finding: *"{G3} moves along {S2}, and its lock to {G2} has not been shown to take a new place along
  the shaft, so it needs a new revision."*

**Progress** (`progress_text`, `STAGE_STATIC`): *"SolidWorks would not mate the gears to turn; building
{Reducer_12to1} static instead…"*

**Boards** (`design/canvas/gen.py`, rendered by Windows Chrome as `render-artboards-with-windows-chrome`):
`WorkbookBuilt` and `WorkbookUpdated` regenerate by themselves (the fake now builds turning assemblies; `Updated`
follows P1's finding — with no route the W4 demonstration edit becomes a Build again… board, and the board title
says so). New: **`WorkbookStatic`** (a v2 record: the footer offering a turning revision), **`WorkbookFallback`**
(the fake refusing the lock: the fallback done-line), **`WorkbookTurned`** (Arc_Move's angle changed after the train
was turned in SolidWorks: Update's *"back at the turn they were built at"*). `UI-DESIGN.md` §9 gains the turning
assembly, the three boards and the sentences; the footer table its new rows.

---

## 2. The order of work

```
P0 (probe: findings from tier 8 + P1, P2)  ─────────────────────────────┐
I  (interface commit) ──► A (SolidWorks) ─┐                              ├──► E (Windows demonstration)
                          B (planning)  ──┼──► D (window, boards, docs) ─┘
                          C (record, words)┘
```

P0 and I start together (code reads findings by `getattr` and refuses when missing, as W4 did). A, B and C run in
parallel after I. D after A–C. E after D and P0. An independent review between I and A–C, and after E, as before.

### I — the interface commit (one agent)

Files: `swbuild.py` (`MateState`, `MeshLink`, `LockLink`, `TrainCheck`, `MateRef`, `MotionUpdate`,
`TRAIN_TOLERANCE`, `STAGE_STATIC`, the new result fields, the new keyword parameters, the protocol members;
**`turn_between` and `train_check` written in full with tests** — pure and shared by A and B; `same_frame`
refactored onto `turn_between`), `swcom.py` (exception classes; method stubs raising `NotImplementedError("W5: Agent
A …")`), `gears/base.py` (`Mate` docstring: kind `lock`, `a` and `b` bare handles, anchor first), new
`workbook/motion.py` (dataclasses, constants, signatures, docstrings; `mate_name` and `face_global` written),
`gearbox.py` / `update.py` (fields only), `store.py` (`MateEntry`, the record fields, schema 3 and its parse — shapes
done, as W4's interface did), `ui_text.py` (new helper signatures). A scratchpad `W5-INTERFACES.md` with the
ownership table below. **Done:** suite green apart from `NotImplementedError` bodies nobody calls yet;
`train_check` tests pass (a train turned by consistent δ's is in step and `turned`; one gear turned alone is out of
step; whole-teeth turns are not `turned`; a tilted or shifted gear is `off_axis`; Z− and ring signs).

### A — SolidWorks (`swcom.py`, `swbuild.py`, `tests/test_swbuild.py`, `tests/test_swcom.py`)

`swcom` members of §1.5; `build(..., mates=)` and `_check_mates`; the fallback in `build_gearbox`; the motion path of
`update_gearbox` (§1.6, order exactly); log lines (`mate    …` per mate, `ok      every mate sound, every gear free
to turn` / `CHECK`/`FAIL` lines, `ok      static assembly built after the turning one was refused`); the fake
(§3.1), backward-compatible for the nine files that import it. **Done:** every behaviour in §3.2's A list tested
against the fake; `tests/test_swcom.py` covers the lock selection and status read with a mocked COM object as it
does for existing members.

### B — planning (`workbook/motion.py`, `gearbox.py`, `update.py`, `layout.py` only if needed; their tests, new `tests/test_workbook_motion.py`)

§1.2, §1.3, §1.6's classify and finish rules, §1.7's `finish_build` fields. W4 tests that pin the static
assembly's ops now pin `plan.static_assembly`; new tests pin the turning plan. **Done:** §3.2's B list.

### C — record and words (`store.py`, `ui_text.py`, `tests/test_store.py`, `tests/test_ui_text.py`)

§1.7 and §1.8. Tests build plans and results directly (as W4's C did). **Done:** every sentence of §1.8 has a test
that fills it from fields and checks it reads as written; v2 → v3 read, v3 round-trip byte-deterministic, a v4 file
refused and untouched, `MateEntry` type errors refused.

### D — window, boards, docs (serial)

`workbook_gui.py` (passes the new fields; no new control — the window should need little), `tests/test_workbook_build.py`,
`tests/test_workbook_window.py` (under Windows Python, as W4), `design/canvas/gen.py` + renders, `design/UI-DESIGN.md`
§9, `docs/PLAN-WORKBOOK.md` (the dated notes of §0.4, and §4.5's *Readings chosen (W5)*: D4, D5, D7, D8, D10),
`docs/HANDOFF-WORKBOOK.md`, `README.md`. **Done:** the five boards rendered and looked at; the window launched on
the 12 : 1 fixture against the fake, footer read in each state.

### P0 — probe agent (`findings.py`, `probe/p8_motion.py`, `probe/decide.py`, `tests/test_findings.py`, `tests/test_probe_motion.py`, `probe/results/**`)

§0.3. **Done:** the six constants and P1/P2's findings committed and pinned against 2026 and 2024 result files.

### E — the Windows demonstration (`probe/workbook_assembly_check.py`, `probe/workbook_window_check.py`, `probe/results/**`)

§4. **Done:** logs committed for 2026 and 2024, 0 failed; the person's step handed to the user (§4.4).

### Who edits what

| Package | May edit |
|---|---|
| I | everything listed under I, once, then hands over |
| A | `swcom.py`, `swbuild.py`, `tests/test_swbuild.py`, `tests/test_swcom.py` |
| B | `workbook/motion.py`, `workbook/gearbox.py`, `workbook/update.py`, `workbook/layout.py`, `tests/test_workbook_{motion,gearbox,update,layout}.py` |
| C | `store.py`, `ui_text.py`, `tests/test_store.py`, `tests/test_ui_text.py` |
| D | `workbook_gui.py`, `gui.py` if needed, `tests/test_workbook_{build,window}.py`, `design/**`, `docs/**`, `README.md` |
| P0 | `findings.py`, `probe/p8_motion.py`, `probe/decide.py`, `probe/__main__.py` registry, `tests/test_findings.py`, `tests/test_probe_motion.py`, `probe/results/**` |
| E | `probe/workbook_assembly_check.py`, `probe/workbook_window_check.py`, `probe/results/**` |
| nobody | `workbook/geometry.py`, `kinematics.py`, `checks.py`, `gears/*.py` but `base.py`'s docstring |

---

## 3. Tests

### 3.1 The fake SolidWorks (`tests/test_swbuild.py`, package A)

The smallest model that makes a test fail for the right reason. Mates are kept per document (saved with it, back on
`open_document`, lost by `close_all` unless saved), keyed by the components' Name2s:

- `add_mate` records `FakeMate(name, kind, a, b, ratio, flip, value, link)`. **Status 5 and code 46** (warning False
  on the new mate, True on those it fights) when: a lock's follower already has an axis or along mate, or an axis /
  along mate is added to a lock follower; a second axis mate on one component; a gear mate whose two components'
  bodies (components joined by locks are one body; an anchor's shaft from its axis mate) are already joined through
  gear mates (a loop). Otherwise status 1. `mate_status`, `mate_states`, `constrained_status` (4 if in an
  over-defined mate, 3 if fixed, else 2), overrides `mate_codes={name: (code, warning)}` and
  `constrained={name: n}`, and `fail_on` as today.
- `find_mate` (raises `MateGone`), `set_mate_suppressed`, `set_gear_ratio`.
- `link_dimension` remembers `"D1@G4 along S3" → "G4 Face Z"`.
- **Rebuild of an assembly with mates:** each anchor with an unsuppressed axis mate is moved to its shaft's axis as
  the layout document's globals now say (the layout's path from `add_component`), and to its Face Z global (or 0 for
  a coincident along mate); if its X/Y moved it is also turned **13° the wrong way** about its own axis (standing in
  for SolidWorks' swing); followers under an unsuppressed lock keep their frame relative to the anchor.
- **`place_component`** raises `SolidWorksError("… did not take its frame …")` — as `swcom.place_component`'s read-back
  would — when the frame disagrees with the gear's unsuppressed axis or along mate, or when any lock on that
  component is unsuppressed (conservative: a put with a lock on is not probed, and the plan never does it).
- `turn(name, degrees)`: a test helper turning one component about its own axis (`R · rot_z`).

**What the fake does not model, so only SolidWorks shows it:** a gear mate turning anything (no solver, no drive,
no drag); the sense and ratio of a turn; SolidWorks' real swing on a move; real over-definition, redundancy and
constrained-status semantics; error-code numbers; selection failures; interference geometry; a closed loop of gear
mates (the fake calls it over-defined, SolidWorks is untried); version differences.

### 3.2 What each package's tests must show

**A (against the fake):**
- A turning build makes the ops in order, saves once, reads `mate_states` and constrained statuses before the save;
  `kind == "motion"`.
- A follower also mated to its axis (a plan doctored in the test) → status 5 → not saved → static plan built at the
  same path → `kind == "static"`, `motion_attempt` set with its document title, interference run on the static one.
- A mate with a non-zero code but status 1 (override) → fallback; a gear reading 3 → fallback; a missing template →
  **no** fallback (W4's failure).
- Pair builds (`build_pair`) unchanged: no mate check, status never raises (existing tests untouched).
- Update, motion path: turned-only → no puts, nothing changed, `turned` True; out of step → every gear not
  `same_frame` put, locks suppressed before and unsuppressed after (call order asserted), `restored` True; layout
  move → rebuild, the fake's wrong turn put right, post-check clean; a Face Z change → `set_global_variable` before
  any put (a put first would raise in the fake); a missing mate → `NotAsBuilt` in the check phase, nothing changed;
  a suppressed mate → turned back on and listed; an extra mate → listed, untouched; a put that does not hold (fake
  override) → post-check failure sentence; static records → W4's path, byte-for-byte the same calls as before.
- Every raise after the check phase becomes a failure (W4's B1 tests extended to the new steps).

**B (pure):**
- `motion_plan` for the three Windows fixtures: 12 : 1 → anchors S1:G1, S2:G2, S3:G4; lock G3→G2; meshes G1–G2
  17:68, G3–G4 17:51; only `"G4 Face Z" = 17`; drag (G1,). Risky_Placements → anchors G1 (coincident), G2 (Z−,
  z_front 10), G4 (18), G6 (ring on Z−, z_front 50); globals `"G2 Face Z" = 10`, `"G4 Face Z" = 18`, `"G6 Face Z" =
  50`; locks G3→G2, G5→G4; three gear mates; one train, drag G1. Arc_Move → anchors G1, G2, G4; `"G4 Face Z" = 15`.
  (Values from `layout.frames` on the committed fixtures. No fixture has a front face below z = 0, so the flipped
  distance is pinned by a made-up workbook here and rests on tier 8's z = −12 case on SolidWorks.)
- A loop (a made-up workbook: S1–S2, S2–S3, S3–S1 at consistent ratios) → one mesh `unmated`; two meshes between
  the same two shafts → the second `unmated`; a fixed shaft's gears in `fixed`; two independent trains → two drag
  gears; a gear meshing nothing alone on a shaft → anchor, in no train.
- `motion_assembly_plan(...).check() == []`; the exact op sequence for the 12 : 1 pinned (golden list); every gear
  `Unfix`ed after its `Fix` and before its first `Mate`; no axis/along mate names a follower; each `LinkDimension`
  after its `Mate`; every `AddGlobal` before any `LinkDimension`; every kind W5 builds (spur, helical, herringbone,
  ring) plans an `Axis` named `pair.AXIS_NAME`.
- `mesh_links` signs for outside/ring × Z+/Z− (four cases each), checked against `kinematics.solve`'s speeds: for
  each mesh, `k == ω_b·σ_b / (ω_a·σ_a)`.
- `plan_gearbox`: a turning plan with `static_assembly` equal to W4's plan at the same path; `static_reason` when a
  finding is missing (monkeypatched); `build_kwargs()["static"]`.
- `classify` on a turning record: every structural case of D8 with its sentence; teeth change with and without
  `GEAR_MATE_RATIO_ROUTE` (monkeypatched); follower At with and without `LOCK_RETAKES_AN_OFFSET`; a Face Z change;
  a reordered Gears sheet keeps the recorded anchors; `MotionUpdate` contents for the W4 demonstration edit.
- `finish_build`: `kind`, mates (`MateEntry(**asdict(m))` round-trip), unmated, fixed, drag; fallback →
  `static_reason`. `finish_update`: `dragged` only for `off_axis`; ratios and z_front follow the result.

**C, D:** as in §2.

**Suite:** `PYTHONPATH=src .venv/bin/python -m pytest -q` on a clean `git archive` (baseline 1536 passed, 10
skipped), and `python.exe -m pytest tests/test_workbook_build.py tests/test_workbook_window.py -q` under Windows.

---

## 4. The demonstration on SolidWorks 2026 and 2024 (package E)

Through the app's own code as W4's script does (`plan_gearbox` → `build_gearbox(session, **plan.build_kwargs())` →
`finish_build`; `classify` → `update_gearbox` → `finish_update`; every footer sentence logged), Excel driven by the
script's own Excel, logs committed under `probe/results/` (2024 under `sw2024/`), no user titles. New sections in
`probe/workbook_assembly_check.py`; W4's sections a, a2, a3, b, c rerun on W5's code (their assemblies now turn:
adapt their expectations — section a's Update edit follows P1's finding) — which is also the W4 rerun HANDOFF still
lists. 2026 in full; 2024 in a fresh session with the 3 GB guard, `m1`, `m3`, `m2`, `m4` first.

### 4.1 Measurements every turning build gets

W4's (frames to 1e-6 against `layout.frames`, axes, interference) plus: the mates in the assembly are exactly the
record's names; every `mate_states` code 0, none suppressed; every mated gear `GetConstrainedStatus` 2; saved,
closed, reopened, the same. W4's half-pitch negative control per mesh (a put with the gear mate on, kept:
`MESH_PHASE_ROUTE`), turning a gear of the mesh that is not in a lock, or suppressing the lock around the put when
both are (Risky_Placements' G3–G4).

### 4.2 The driven proof (the script's, never the app's)

A temporary **angle mate** between the input anchor's Top plane (`gearN:plane2`) and the layout's **Right** plane
(`layout:plane3`) at 90° (at the built phase θ = 0 the two Top planes are parallel, which tier 8 never drove from),
its D1 linked to an assembly global `"Drive"` (`add_global_variable`, `link_dimension`), then `"Drive"` 90 → 120
(`set_global_variable`) and a rebuild. Each gear's turn about its own axis (`turn_between`) against the
kinematics: `δ_i = 30° · (ω_i·σ_i)/(ω_in·σ_in)` from `kinematics.solve`, to 1e-6 relative, sign included (12 : 1:
output +2.5° for +30°). **Negative control (wrong sense):** suppress `G3 meshes G4`, add a temporary gear mate
G3–G4 with **Flip True** (gear_mate_sense made these), drive again: the script's comparison must report the output
turning the wrong way (logged `ok      control: a wrong sense is seen`); then delete the temporary gear mate
(`MATE_DELETE_ROUTE`), unsuppress the original. Then delete the drive's link equation, the `"Drive"` global
(`delete_equation`) and the angle mate. If the 90° drive misbehaves, STOP and ask.

### 4.3 Sections

- **m1 — the 12 : 1 fixture** (compound S2): build; §4.1; §4.2. **The user's turn, simulated:** drive 37° and delete
  the drive as above — the solver leaves every gear turned consistently, as a hand drag does. Update with nothing
  changed: no put, nothing changed, the sentence *"… The gears stand where they were turned in SolidWorks."*;
  `train_check`'s residuals logged. Excel: **G4 At 27 → 30** → Update: `"G4 Face Z"` set, every gear back at the
  built turn (`restored`), frames to 1e-6, drive again: 1/12. Excel: **G3 At 27 → 29** (a follower) → Update under a
  suppressed lock (P2's case on a real gearbox), frames, drive. Excel: **the W4 demonstration edit** (S2 X 64.5, G2
  69, S3 X following) → with P1's route: Update (part values, layout, ratio 17 : 69, every gear put), frames,
  invariants, drive: output turns `30·17/69·17/51` the same way; without it: the structural sentence, Build again…,
  `_r2` built turning, measured, earlier files' sha256 and mtime unchanged.
- **m2 — Arc_Move** (the pure move): build; turn (drive and delete); Excel moves S2 along its arc → Update: layout
  globals, the mates carry the gears, SolidWorks' wrong swing logged, every gear put back, frames, drive: the ratio
  holds after the move.
- **m3 — Risky_Placements** (Z− shafts, two compound shafts, a helical pinion in a helical ring on Z−, herringbones
  of unequal widths): build turning; §4.1; §4.2 through the whole train (ring turns the same way as its pinion), the
  negative control on the ring's mesh.
- **m4 — the fallback, forced:** the 12 : 1 plan with one extra `Mate` op injected by the script (G3 also on S2
  Axis: over-defined, as compound_lock found) → the turning assembly not saved, left open as its `Assem<n>`; the
  static one saved at the path; `kind: static` with the reason; the sentence logged; the script then closes the
  refused document (saving this run's modified parts first, as W4's `close_ours` does on 2024).
- **window** (`workbook_window_check.py`, 2026): screenshots of the built footer with the drag instruction, and of
  the static-record footer.

### 4.4 The step only a person can do (hand to the user, for 2026 and then 2024)

> In SolidWorks, open the `Reducer_12to1.SLDASM` the demonstration built (its folder is in the log). Click gear G1 —
> the small gear on S1, at the origin — and drag it round its axis by about a quarter turn. **Watch G4**, the large
> gear on S3: it turns **the same way as G1**, much more slowly — a quarter turn of G1 turns G4 about 7.5°. G2 and G3,
> on S2, turn together the other way. No gear should leave its axis, slide along it, or pass through another. Then,
> in the Workbook window, press **Update SolidWorks** with nothing changed: the footer should say the gears stand
> where they were turned. Tell us what you saw, on each version.

---

## 5. Risks and open questions

- **Hand-drag tolerance.** `TRAIN_TOLERANCE` (1e-5 rad per relation) is a guess about a mouse drag's solver residual;
  the drive-and-delete in m1 logs real residuals, and the person's Update after a drag is the check. Too tight shows
  as "out of step" after a drag (a STOP).
- **Unmated loops (D6)** rest on reasoning only; no fixture has a loop. W7 must probe a loop of gear mates.
- **A lock renamed** has not been seen on SolidWorks (gear and distance mates have); a refusal falls back (D2).
- **`GetConstrainedStatus` 2 does not prove one freedom**; the topology does (D3). A missing mate would leave a
  gear under-defined too: the "every planned mate present, none suppressed" check covers that.
- **Lightweight components** are untried (as tier 8 notes); the build opens every part, so none should be.
- **2024 memory**: nine more mates and a static fallback build per press; the guard stays.
- **The demonstration's 90° drive** differs from tier 8's 10° → 40°.
- **W4's own rerun is still open** (HANDOFF "Next 1"); E folds it in, so a W4 regression may surface in E first.
- **Assemblies with many gears**: about a second per mate; not measured beyond nine components.
- Open: should Update ever keep the user's turn when it must put gears (D4)? Should a front face at the Front plane
  get a distance mate that can later move off it (D8) — it needs AddMate5 in a reopened assembly, which P1's remake
  branch would also show?

## 6. What W5 leaves for W6–W8 (and keeps open for them)

- **W6 right-angle:** gear mates between non-parallel axes need their own Flip probe; axis mates to turned axes need
  layout axes from a point and a direction. `MatePlan.kind` and the record's `mates` are open lists; a bevel mesh
  becomes another kind, not a change of these.
- **W7 planetary:** carriers (gears mounted on a turning shaft: axis mates to a carrier's axis), copies, loops of
  gear mates as a real need (D6's `unmated` is the hook), a fixed ring (D9 already leaves fixed-shaft gears fixed).
  `train_check`'s links are per mesh and per lock, not per shaft, so a carrier adds a link kind.
- **W8 sleeves and modes:** per-configuration mate suppression (the lock and `SetSuppression2` with
  `THIS_CONFIGURATION` are the stepping stone), sliding gears (an ALONG mate per position), dog clutches as locks
  suppressed per mode.
- The planner (PLAN-GEARBOX) reuses all of it unchanged.
