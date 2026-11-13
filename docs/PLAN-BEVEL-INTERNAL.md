# Gear Generator — internal gears, crossed-axis helical pairs, and straight bevel gears

Executed like `docs/PLAN.md` and `docs/PLAN-HELICAL.md`. Read PLAN.md's "For the executing agent"
first. The conventions, the probe-first rule and the stop-and-ask triggers all carry over: UNVERIFIED
means *the probe settles it, never guess a call*. The first thing to commit is this plan, as
`docs/PLAN-BEVEL-INTERNAL.md`.

## Context

v0.2 builds spur, helical and herringbone gears, singly or as parallel-shaft pairs with an
assembly. Three things were left for later:

- **Internal gears.** `PLANNED_KINDS = ("bevel", "internal")`, greyed on the Kind row.
- **Crossed-axis helical pairs.** Deferred in PLAN-HELICAL §10 "to the bevel phase, which needs
  non-parallel axis mates too".
- **Bevel gears.** PLAN.md §3.8 sketched them as a Tredgold virtual tooth count on the back cone,
  a revolved blank and a cut-loft.

The user wants all three, built the same way: pure maths tested on Linux, a `BuildPlan` of plain ops
run by `swbuild` over COM, and every new SolidWorks member probed on a scratch part first.

### Decisions made with the user (2026-09-15)

| Question | Decision |
|---|---|
| Bevel type | **Straight bevel, any shaft angle Σ** (default 90°). Tredgold back-cone section, cut toward the apex. Spiral or zerol bevels are not planned. |
| Bevel proportions | **Gleason unequal addendum**, as in KHK's "Gleason system straight bevel gear" table. |
| Internal scope | **A Teeth `External · Internal` toggle** on spur, helical and herringbone, separate from Kind. In pair mode, Mesh `External · Internal` makes gear B the ring. |
| Bevel pair Solve | **Cone distance and ratio** replace centre distance and ratio. |
| Crossed-axis helical | In scope (the deferred item from PLAN-HELICAL §10). |

Judgement calls (change at review if wrong):
- Crossed pairs are **same hand**, with Σ = β1 + β2; opposite-hand crossed pairs are reserved.
- Gleason's thickness factor K is **0**. It comes from a chart, not a formula.
- An internal gear's default fillet is **0.15 × module**. The spur default of 0.38 × m reaches into the
  pinion's tip path.
- A bevel part's **pitch apex is at the part origin**, with the axis along +Z.
- Crown gears and internal bevels (δ = 90° or more) are refused. *Superseded 2026-09-29: both are built
  — a crown gear's section is a rack's, an internal bevel's a ring's — behind probe
  `bevel_planes_beyond_90`, which passed on 2026-11-13; see "Follow-on" at the end.*
- Phase order is **internal → crossed → bevel**, easiest first. Crossed introduces the interference
  check and non-parallel mates in the simpler setting.

---

## 0. Shared seams (no behaviour change; spur, helical and herringbone dry runs stay byte-identical)

1. **Section maths.** `spur.profile()` gains `addendum=None` (None = m), `whole_depth=None` (None =
   the user's IIF), `space_change=0.0` (added to the space at pitch) and `internal=False`. The tip is
   `d + 2·addendum`, the root is `tip − 2·whole_depth`, and the tip cap stays `tip + 2m`. Every
   existing caller passes nothing new.
2. **Section globals.** `spur.profile_variables(...)` takes the global names it reads as parameters:
   `pitch=PITCH, outer=OUTER, depth=DEPTH, arc_length=ARC_LENGTH, flank_offset_sign=+1`. A bevel
   section reads its back-cone globals; an internal section negates the flank offset.
3. **Section placement.** `spur.space_ops(g, recipe, plane, centre=ORIGIN, frame=None)`:
   - `centre` is the ref the root arc and radial lines are related to.
   - `frame` is a `SectionFrame(radial_is_x: bool, sx: ±1, sy: ±1, centre_x: str, scale: str)`. The
     equation-curve expressions become `centre_x + sx·scale·(…)`, and every length dimension is linked
     as `… * "scale"`.
   - Defaults reproduce today's ops exactly. Only axis-aligned frames are allowed; the probe measures
     which one a plane gives, and anything else is a STOP.
4. **Pair dispatch.** `pair.solve` and `pair.assembly_plan` branch on
   `(kind, mesh, shafts) ∈ {parallel external, parallel internal, crossed, bevel}`. Today's parallel
   external branch moves unchanged into `_solve_parallel` and `_assembly_parallel`.
5. **Ops (`gears/base.py`).** New ops, each with `describe()` and `check()` rules like `SweepCut`'s:
   - `Revolve(id, sketch, name, axis_line)`: defines `id`, uses a closed sketch.
   - `RefPlaneNormal(id, name, line, point)`: a plane normal to a sketch line through a sketch point.
     Defines a plane id; `line` and `point` are refs into a closed sketch.
   - `LoftCut(id, name, profiles: Tuple[str, ...], apex: str = "")`: uses closed sketches. `apex`,
     when set, is a sketch point loft end.
   - `Mate.kind` gains `"point"` (two component origins) and `"axis angle"`.
   - Component refs gain `gearN:origin`.
6. **Interference.** `Session.interference_count()` via `IAssemblyDoc.InterferenceDetectionManager`,
   reached through `swcom.call` (PLAN-HELICAL "As executed"). `build_pair` runs it after the
   assembly's rebuild: 0 → `done`, otherwise a `CHECK` with the count. If the probe passes, the manual
   "check the teeth mesh" step is dropped for every kind.

## 1. Internal gears — `gears/internal.py`

### 1.1 Maths (mm, degrees at the boundary; transverse values for helical kinds, as PLAN-HELICAL §1)
```
d = m·N          inner tip da = d − 2m          root df = da + 2h (h = user IIF)       db = d·cos α
space = π·m/2 + j        ψs = space/d        φi = −(ψs + inv α)   flank offset: the involute narrows outward
flank inner D = IIF(db ≥ da − m, db, da − m)     tip cap (inward) = da − 2m     flank outer D = df − 3ρ
rim D default = df + 6m (a 3m rim)   fillet default ρ = 0.15m
pair (pinion N1 inside ring N2):  C = m(N2 − N1)/2   i = N2/N1 > 1
εα = [√(ra1² − rb1²) − √(ra2² − rb2²) + C·sin α] / (π·m·cos α),   ra2 = da/2
```
**Section geometry.** The upper flank is spur's *lower* curve expression with `"Flank Offset"`
negated. Its polar angle is `φi' − t + atan t`, and it equals ψs at the pitch circle.
- **Inward end:** a radial line from the involute's start down to a construction tip-cap circle,
  closed by a chord. The closure lies inside the blank's hole, so a kink there is in air.
- **Outward end:** a radial line from the involute's end to fillets tangent to that line and the root
  arc. This is spur Recipe A's proven topology, turned inside out.
- **Recipe B:** the osculating arc's centre sits on the base circle at polar angle ψs − α, radius
  rp·sin α.

**validate** (full sentences, reusing `section_diagnostics` where it applies):
- Errors: rim ≤ root diameter; the fillets do not fit.
- Warnings:
  - tip circle below the base circle (N < 2/(1 − cos α), 33.16 at 20°);
  - rim under 2m;
  - the straight root line starts inside the reach of a standard pinion's tip (df/2 − 1.5ρ < d/2 + m).
- Pair checks:
  - Error: N2 ≤ N1. Error: the hands differ (an internal helical pair is **same hand**, same β).
  - Warning, **tip clash:** `internal.tip_clash(m, N1, N2, α)` turns the pinion's flank outline through
    two pitches against the ring's and returns the deepest intrusion in mm.

**Pinned values** (m 2, ring N 60, pinion 20, α 20°, j 0.3m):
- C 40 · d 120 · da 116 · df 125 · db 112.763114 · flank inner D 114 · εα 1.949662.
- Pinion mesh turn 9°.
- `tip_clash` at m 1, j 0, flank-only model: 50:60 → 0 · 54:60 → 0.138 mm (±0.005) · 20:60 turned
  half a pitch → 0.966 mm (the negative control).
- Helical internal: β → 0 equals internal spur to 1e-9.

### 1.2 Globals
Eight of the user's ten names are kept. `"Outer Diameter"` becomes `"Inner Diameter"=
( "No. of Teeth" - 2 ) * "Module"` (the helical form uses `"Transverse Module"`), and `"Bore Diameter"`
becomes `"Rim Diameter"` (typed → literal; blank → `"Root Diameter" + 6 * "Module"`). `"Root
Diameter"= "Inner Diameter" + 2 * "Tooth Depth"`. The rest is spur's or helical's list through the
§0.2 seam: `"Flank Offset"` negated, `"Tip Cap Diameter"= "Inner Diameter" - 2 * "Module"`,
`"Flank Start Diameter"` holding the inner IIF, and `"Flank End Diameter"= "Root Diameter" - 3 *
"Fillet Radius"`. Tests pin the order: every global before its first use.

### 1.3 Build
Axis. Then the blank sketch: circles `Rim` and `Tip`, both centred on the origin, extruded `Blank` as
an annulus, with links to `"Rim Diameter"`/`"Inner Diameter"` and `"Face Width"`. The internal tooth-space
sketch follows. For spur, `Cut` through all; for helical and herringbone, PLAN-HELICAL §3.3's plane,
path, `SweepCut` and mirror. Then pattern `Teeth`, material, rebuild, save. No bore ops. Names:
`Blank Sketch` (`Rim@`, `Tip@`), then the same as spur or helical.

### 1.4 Pair
**Solver.** `S = N2 − N1 = 2C/m` (`2C·cos β / mn` for helical), `N1 = S/(i − 1)` at floor, ceil and
±1. The non-standard tier sets `m* = 2C/(N2 − N1)`. The rank key adds `clash` after `undercut`.
- Pinned: C 40, i 3, series 1 → m2 20:60 · m1.25 32:96 · m1 40:120 · m2.5 16:48 (undercut) · then
  inexact rows.
- `"1:3"` or any ratio ≤ 1 is refused with a sentence: the ring is the larger gear.

**Assembly.** gear1 = the ring, fixed at the origin; gear2 = the pinion at (C, 0, 0). The mates are
today's, with `"Mesh Angle"` = 180/N_pinion for any parity: the pinion sits at the ring's +X space and
must present a tooth there. Helical rings mate on Front planes and herringbone on `Mid Plane`, as now.
Stems: `Ring_m2_N60`, `Ring_m2_N60_15R`, `Pair_m2_20T_60T_INT`.

## 2. Crossed-axis helical pairs

**Maths (`gears/crossed.py`).** Same mn and αn, same hand, Σ = β1 + β2.
```
C = (mn/2)·(N1/cos β1 + N2/cos β2)      i = N2/N1
```
- Pinned: mn 2, 20:40, Σ 90 → β 45/45: C 84.852814 · d1 56.568542 · d2 113.137085. β 30/60: C 103.094011.
- Validate: error hands differ; error β1 + β2 ≠ Σ; warning either β outside 10–80°.

**Solver.** The inputs are C, i, Σ and optionally β1.
- **β1 typed:** β2 = Σ − β1, and rows are ranked by C error.
- **β1 blank:** for each mn and N1 (N2 = round(i·N1)), bisect `f(β1) = N1/cos β1 + N2/cos(Σ − β1) = 2C/mn`
  on [βmin, Σ − βmin]. Keep the root nearest Σ/2, so every row is exact on C. The rank key ends with
  `|β1 − Σ/2|`.
- Pinned: C 84.852814, i 2, Σ 90, mn 2 → 20:40 at β1 45.000000, exact.
- `apply()` writes β1 into A, β2 into B, and B's hand = A's.

**Parts.** Unchanged helical parts, each with its own β. With `mesh_plane=True`, a pair build adds a
`Face Plane` RefPlane at b/2 (offset linked to `"Face Width" / 2`) for the assembly to locate on.

**Placement (pure, tested).**
- `crossed.frame(Σ)` puts gear2 at x = C with its axis `RotX(−Σ)·Z`, face centres on the common
  perpendicular. A vector test checks the two tooth directions coincide at the contact point for
  right/right and left/left.
- `crossed.mesh_angle(...)` is the spur rule on N2, plus each gear's twist at its contact section
  (hand·360·(b/2 + mn)/L), carried through the ratio. A pure test samples gear1's space centreline and
  gear2's tooth centreline at the contact point and requires them to meet.

**Assembly.** The route is decided by probe `crossed_mates`, whose oracle is gear2's `Transform2`
(1e-6) plus interference 0:
- **(M) mates:** `distance gear2:Gear Axis ~ gear1:plane3 = C` (the verified kind), `axis angle gear2:Gear
  Axis ~ gear1:Gear Axis = Σ`, and locators on both `Face Plane`s. The probe records which set gives
  the transform, and the executing agent writes it into §2 from that record.
- **(F) fixed placement:** set `Transform2` to the target, then `Fix`. The sidecar says `parametric:
  "partial"` and the status sentence says `"Centre Distance"` does not drive it.
- Neither → STOP.

Globals: `"Centre Distance"`, `"Shaft Angle"`, `"Helix Angle 1"`, `"Helix Angle 2"`, `"Mesh Angle"`.
Stem `Pair_m2_20T_40T_X90`.

## 3. Straight bevel gears — `gears/bevel.py`

### 3.1 Maths (Gleason, as KHK tabulates it; pinned against their formulas)
```
δ = atan( sin Σ / (Nmate/N + cos Σ) )  (+180° if the denominator < 0)     δmate = Σ − δ
d = m·N     R = d / (2 sin δ)     big-gear addendum = 0.540m + 0.460m / ((Nbig·cos δsmall)/(Nsmall·cos δbig))
small-gear addendum = 2.000m − big's      hf = 2.188m − ha      "Tooth Depth" = ha + hf
θf = atan(hf/R)     face angle δa = δ + θf,mate (uniform clearance)     root angle δf = δ − θf
da = d + 2·ha·cos δ      apex to crown X = R·cos δ − ha·sin δ
x = (ha − m)/m      s = π·m/2 + 2·x·m·tan α (K = 0)      space = π·m/2 + j − 2·x·m·tan α
Tredgold heel section: Nv = N/cos δ, rv = d/(2 cos δ), spur profile(Nv, m, α, addendum ha, depth ha+hf, space_change)
section at cone distance ρ is the heel section scaled k = ρ/R, centred rv·k from the sketch origin
undercut: Nv < 2(1 − x)/sin² α        εα on the virtual pair
```
**Pinned** (m 3, α 20°, Σ 90°, b 20; pinion z 20 with mate 40):
- δ 26.565051° · R 67.082039.
- ha 4.035 · hf 2.529 · θf 2.159034° · mate θf 3.921938°.
- Face angle 30.486989° · root angle 24.406017° · da 67.218027 · X 58.195493.
- x 0.345 · s 5.465807 · Nv 22.360680 · rv 33.541020 · undercut limit 11.1987 · εα 1.6315.
- The mate (z 40): δ 63.434949° · ha 1.965 · hf 4.599 · face angle 65.593983° · root angle 59.513011°
  · da 121.757549 · X 28.242451 · s 3.958971.
- Equal teeth give ha = m on both.
- Toe scale at b: k = 0.701858. A frustum cut between parallel sections A and k²A, L apart, removes
  `A·L·(1 + k + k²)/3`.

Verify these constants against a published worked example before pinning (KHK "Calculation of Gear
Dimensions — bevel gears", or the KG Gears "9.6 Gleason straight bevel" sheet). KHK lists whole depth
as `2.188m + 0.05`, but its dedendum is `2.188m − ha`; follow the dedendum. **If a source contradicts
the addendum formula, STOP and ask.**

**validate:**
- Errors: Σ outside 10–170°; mate teeth < 6; δ ≥ 89° (crown or internal bevel, reserved); b ≥ R/2;
  the heel section fails `section_diagnostics`; bore ≥ the toe root diameter.
- Warnings: b > R/3 or b > 10m (Gleason practice); undercut on Nv; toe tip thickness < 0.3 × toe module.

### 3.2 Globals (in order)
- The user's names, minus the IIF: `"No. of Teeth"`, `"Module"`, `"Bore Diameter"`, `"Pressure Angle"`.
- Bevel inputs and cone: `"Shaft Angle"`, `"Mate Teeth"`, `"Pitch Cone Angle"`, `"Mate Cone Angle"`,
  `"Pitch Diameter"`, `"Cone Distance"`.
- Addendum and depth: `"Addendum"` (an IIF on `"No. of Teeth" >= "Mate Teeth"` choosing the big or
  small formula, so editing teeth in SolidWorks swaps roles correctly), `"Mate Addendum"`,
  `"Dedendum"`, `"Mate Dedendum"`, `"Tooth Depth"`.
- Blank: `"Dedendum Angle"`, `"Mate Dedendum Angle"`, `"Face Angle"`, `"Root Angle"`,
  `"Outer Diameter"`, `"Face Width"`, `"Overrun"`= `"Module"`.
- Section: `"Backlash"`, `"Arc Length"` (with the shift term), `"Fillet Radius"`,
  `"Back Cone Pitch Diameter"`= `"Pitch Diameter" / cos ( δ )`, `"Back Cone Outer Diameter"`, then
  `profile_variables` through the §0.2 names.
- Sections and loft: `"Heel Distance"`= R + `"Overrun"`, `"Toe Distance"`= R − b − `"Overrun"`,
  `"Heel Scale"`, `"Toe Scale"`, `"Heel Virtual Radius"`= `"Heel Distance"` · tan δ, `"Toe Virtual Radius"`.

Radian forms where trig differs; atn per `findings.INVERSE_TANGENT`.

### 3.3 Build (apex at the origin, axis +Z, the space centred on +X)
```
NewPart · AddGlobal × ~45 · Axis "Gear Axis"
"Cone Sketch" on plane 2 (Top; sketch y = −Z per findings): construction centreline on the axis; construction
  generatrix G from the origin at "Pitch Cone Angle" to "Heel Distance", with toe point on it at "Toe Distance"
"Blank Sketch" on plane 2: closed polygon  front-face point on axis → toe tip → heel tip (face line at
  "Face Angle", heel tip = pitch point + "Addendum" normal) → back cone ⊥ G down to heel root − m → back face
  ⊥ axis → axis; Revolve "Blank" about the centreline; every dimension linked
RefPlaneNormal "Heel Plane" (G, G.end) · RefPlaneNormal "Toe Plane" (G, toe point)
"Heel Section Sketch" on Heel Plane: Point vc at −"Heel Virtual Radius" along the measured radial axis;
  space_ops(heel section, recipe, centre="vc", frame=findings.BEVEL_SECTION_FRAME, scale "Heel Scale")
"Toe Section Sketch" likewise
LoftCut "Tooth Space" (heel, toe)        [or LoftCut to the apex point, per findings.BEVEL_ROUTE]
CircularPattern "Teeth" + Count link · bore ops on plane 1 (through all both) · material · Rebuild · SaveAs
```
Names: `Cone Sketch`, `Blank Sketch`/`Blank`, `Heel Plane`, `Toe Plane`, `Heel Section Sketch`,
`Toe Section Sketch`, `Tooth Space`, `Teeth`, `Bore Sketch`/`Bore`.

### 3.4 Pair
**Solver.**
```
R = (m/2)·√(N1² + N2² + 2·N1·N2·cos Σ) / sin Σ
K = 2R·sin Σ / m     N1 = K / √(1 + i² + 2i·cos Σ)
```
Try N1 at floor, ceil and ±1, with N2 = round(i·N1). The exact-ratio tier sets `m* = 2R·sin Σ / √(…)`.
- Rank: `(R error > 1e-6 mm, ratio error, not standard, undercut on Nv, −m)`. R is rarely exact with
  whole teeth, so its tolerance is 1e-6 rather than spur's 1e-9.
- Pinned: R 50, ratio `4:3`, Σ 90, series 1 → m5 12:16 · m4 15:20 · m2.5 24:32 · m2 30:40 · m1.25 48:64
  · m1 60:80, all exact and none undercut. Then non-standard exact rows (m 2.857143 21:28 …), then
  inexact rows.
- `apply()` writes module and teeth, `mate_teeth` crosswise, and `shaft_angle` into both.

**Assembly.** gear2 = `RotY(Σ)`, apexes coincident, and the contact line lies on gear2's −X side, so
`"Mesh Angle"` = `pair.mate_angle(N2)` as for spur. Mates:
- `point gear2:origin ~ gear1:origin`;
- `coincident gear2:Gear Axis ~ gear1:plane2`;
- `axis angle gear2:Gear Axis ~ gear1:Gear Axis = Σ`, linked to `"Shaft Angle"`;
- `angle gear2:plane2 ~ gear1:plane2 = Mesh Angle`, linked.

Probe `bevel_mates` verifies this against `Transform2` and interference; route (F) as in §2 if the
mates will not give it. Globals: `"Cone Distance"`, `"Shaft Angle"`, `"Ratio"`, `"Mesh Angle"`.
Stems: `Bevel_m3_N20_M40`, `Pair_m3_20T_40T_B90`.

## 4. App layers

- **`spec.py`.**
  - `GearSpec`: `teeth_side="external"`, `rim=""`, `shaft_angle="90"`, `mate_teeth=""`.
  - `PairSpec`: `mesh="external"`, `shafts="parallel"`, `shaft_angle="90"`, `cone_distance=""`
    (bevel reuses the ratio, module, series and teeth fields).
  - Constants: `KIND_BEVEL`, `TEETH_SIDES`, `MESHES`, `SHAFTS`.
  - Spur and helical refuse a typed `mate_teeth`, and bevel refuses `internal`, each with a sentence
    naming the field.
  - Stems as §1.4, §2 and §3.4.
- **`gears/__init__.py`.** `KINDS` gains `"bevel"`; internal is not a kind: `KINDS[kind]` dispatches to
  `internal.for_kind(kind)` when `teeth_side == "internal"`. `PLANNED_KINDS = ()`, and
  `tests/test_gears_spur.py:160,306` change with it.
- **`findings.py` / `probe/decide.py`.**
  - New constants, each naming its probe: `REVOLVE_CALL`, `REF_PLANE_NORMAL_CALL`,
    `BEVEL_SECTION_FRAME`, `LOFT_CUT_CALL`, `BEVEL_ROUTE` (`"two sections"` | `"apex"` | STOP),
    `PATTERN_OF_LOFTS_SECONDS_24`, `INTERFERENCE_CALL`, `MATE_POINT`, `MATE_AXIS_ANGLE`,
    `CROSSED_ROUTE` / `BEVEL_MATE_ROUTE` (`"mates"` | `"fixed"`).
  - `decide.py` gains `bevel_route`, `crossed_route`, `bevel_mate_route`, `interference`.
- **`swcom.Session`.** Each written from the probe code that ran, with a docstring naming the probe
  and version: `revolve`, `ref_plane_normal`, `loft_cut`, `interference_count`, `set_component_transform`,
  `add_mate` kinds `point` and `axis angle`, `_component_ref` for `origin` (SelectByID2 type `"EXTSKETCHPOINT"`
  or what the probe finds), and `sketch_entity_ref` for selecting a closed sketch's line or point by
  handle.
- **`swbuild.py`.** Protocol and `_RUNNERS` gain `_revolve`, `_ref_plane_normal` and `_loft_cut` in the
  `_sweep` idiom (kept name read back). `STRUCTURAL = ("kind", "recipe", "hand", "teeth_side")`.
  `build_pair` runs the interference check (§0.6). `FakeSolidWorks` gets every new member.
- **`store.py`.** Additive keys, no schema bump; an old sidecar reads as external. `Update values`
  carries Σ, mate teeth, rim and β through the globals, and warns about a stale assembly as now.
- **GUI** (`gui.py`, `ui_text.py`, `preview.py`, `widgets.py`, `design/`).
  - **Gear panel:**
    - Kind `Spur · Helical · Double · Bevel`, all enabled; Internal leaves the Kind row.
    - Teeth `External · Internal`, disabled for bevel.
    - Internal shows Rim (placeholder *root + 6 × module*) and hides Bore.
    - Bevel shows Shaft angle and Mate teeth. Mate teeth is disabled in pair mode, where it mirrors
      the other gear.
  - **Pair panel:**
    - Mesh `External · Internal` for spur and helical kinds; Shafts `Parallel · Crossed` for helical only.
    - Shaft angle for crossed and bevel pairs.
    - For bevel, Centre distance relabels Cone distance. Crossed pairs show Helix angle 1 (placeholder
      *any*).
  - **Flyout:** columns as now; bevel's ERROR column reads *R +0.03 mm*; internal adds *clash 0.14 mm*.
  - **Derived:**
    - Internal rows: Inner tip, Rim, clash.
    - Bevel rows: δ, R, ha / hf, face angle / root angle, Nv, X.
    - Crossed pair rows: β1 / β2, Σ, C.
  - **Preview:**
    - Internal: the ring's toothed loop plus the rim circle, with the pinion inside at C turned 180/N1.
    - Bevel: an axial half-section of each blank with its pitch cone line; a pair meets at the apex at Σ.
    - Crossed: two transverse outlines with the Σ mark.
    - All placement goes in `preview.layout_*`, tested without Tk.
  - **Explainer cards** and `draw_diagram` / `gen.py DIAGRAMS` for `teeth_side`, `rim`, `shaft_angle`,
    `mate_teeth`, `mesh`, `shafts`, `cone_distance`, plus the helix-row cards v0.2 left out.
  - **Tables:** `GEAR_VARS` and `PAIR_VARS` gain the new fields; `test_gui_spec.py` coverage.
  - **Design:** `Internal.dc.html` and `Bevel.dc.html` from `gen.py`, renders in `design/renders/`
    (memory: headless Windows Chrome), and `design/UI-DESIGN.md` updated.

## 5. Probes (existing harness; scratch parts only; arities from `sldworks.tlb`/`argerror`, enums from `swconst`)

| Tier | Probe | Asserts | Oracle |
|---|---|---|---|
| 2 | `annulus_extrude` | two concentric circles extrude as a ring | volume π(R²−r²)w |
| 2 | `revolve` | `FeatureRevolve2` (or what the tlb gives) about a sketch centreline; angle 360; a polygon dim linked to a global follows on rebuild | revolved-triangle volume (Pappus), centroid on the axis |
| 2 | `ref_plane_normal` | `InsertRefPlane` perpendicular to a sketch line + coincident to its end point; plane follows when the line's angle/length globals change; its sketch's origin and axes in model space (`ModelToSketchTransform`) | measured origin = the line end; radial axis ∥ (cos δ, 0, −sin δ) up to sign |
| 2 | `loft_cut_sections` (decider) | `InsertCutBlend` between two similar sketches on parallel planes; one body; no twist | removed volume A·L(1+k+k²)/3 to 1e-5; centroid y 0 |
| 2 | `loft_cut_apex` | the same to a sketch point | A·L/3 |
| 2 | `pattern_loft` | pattern of a loft cut, N 24, rebuild seconds | blank − N·V |
| 4 | `interference` | `InterferenceDetectionManager` count on a meshed spur pair = 0, half pitch off > 0 | negative control |
| 4 | `nonparallel_mates` | point mate on component origins; axis–axis angle mate; the side "align closest" picks after pre-setting `Transform2`; `set_component_transform` + fix | `Transform2` rotation = RotY(Σ) / RotX(−Σ) to 1e-6 |
| 4 | `crossed_mates` | route M's mate set on two helical parts with `Face Plane`s, else F | transform + interference 0 |
| 5 | `internal_end_to_end` | ring m2 z60 spur and helical β15 R through `swbuild.build_pair` with a same-hand pinion: sketches fully defined, one body, interference 0; `"No. of Teeth"` 60→64 via `update_variables` rebuilds clean | volume = πr_rim²w − ring-free volume computed as blank − N·A_space·w (spur), fresh twin (helical) |
| 5 | `bevel_end_to_end` | pinion m3 z20 mate 40 and its gear, recipe A, bore 10: names, sketches fully defined, one body, X measured at the crown, pair interference 0; `"No. of Teeth"` 20→21 → volume equals a fresh build's to 1e-5 | pinned §3.1 values; fresh twin |
| 5 | `crossed_end_to_end` | mn2 20:40 β45/45 R pair at Σ 90 | interference 0, gear2 centre at C |

The DB write-back is its own commit under CONTRIBUTING's ten rules:
- `features/08-revolve`, `features/09-reference-plane-normal-to-a-line`, `features/10-loft-cut`;
- `assemblies/03-interference-detection`, `assemblies/04-mates-between-non-parallel-axes`;
- API-LEDGER rows via `--ledger`, then the manifest rebuilt;
- a PLAN.md §9 line that crossed-axis and bevel are done.

Failures are recorded as findings.

## 6. Tests (Linux, `.venv/bin/python -m pytest`)

| File | Pins |
|---|---|
| `test_gears_spur.py`, `test_gears_helical.py` | green after §0; `python -m gear_generator.gears` dry runs byte-identical (capture before §0, diff after) |
| `test_gears_internal.py` (new) | §1.1 values; flank polar angle ψs at pitch; tip-clash pins and control; validate sentences; plans `check()` for spur/helical/herringbone × A/B; eight user names in order; internal helical β→0 = internal spur |
| `test_gears_crossed.py` (new) | §2 C pins; frame tooth-direction vector test; mesh-angle centreline test; solver pin |
| `test_gears_bevel.py` (new) | §3.1 pins both gears; ha = m at equal teeth; IIF role swap at N = mate; Σ ≠ 90 δ (incl. the +180 branch); frustum factor; plan `check()` both recipes × both routes; §3.3 names |
| `test_equations.py` | internal, bevel and crossed globals evaluate equal to `derive()` in both trig modes |
| `test_gears_pair.py` | §1.4 and §3.4 solver pins; ratio ≤ 1 refused for internal; `apply` writes only the fields named; assembly plans' mates and mesh angles per branch |
| `test_swbuild.py` | fake revolve/plane/loft/interference; stop at a failing loft; `teeth_side` structural; interference CHECK in `PairResult` |
| `test_spec.py`, `test_store.py`, `test_ui_text.py`, `test_gui_spec.py`, `test_preview.py` | new fields round-trip; old sidecar reads external; every readout and explainer; coverage; internal/bevel/crossed layouts |
| `test_probe_decide.py`, `test_findings.py` | every new route from canned records; constants agree with `latest.json` |

## 7. Phases

| Phase | Deliverable | Demonstrable | Size |
|---|---|---|---|
| **P0 seams** | `docs/PLAN-BEVEL-INTERNAL.md`; §0.1–0.5 refactors | full suite green; spur/helical/herringbone dry runs byte-identical | S |
| **I1 internal maths + form** | `internal.py`, solver branch, spec, ui_text, preview, GUI rows, explainers | GUI: Internal m2 z60 → §1.1 values and ring outline; pair Mesh Internal C 40 i 3 → §1.4 rows → pick → pinion inside ring | M |
| **I2 probe + build** (SolidWorks open on host) | `annulus_extrude`, `interference`, `internal_end_to_end`; runners; interference in `build_pair` | Windows: ring + pinion + assembly built, interference 0, `"No. of Teeth"` edit rebuilds | M |
| **X1 crossed** | `crossed.py`, solver, `Face Plane` option, GUI Shafts row; probes `nonparallel_mates`, `crossed_mates`, `crossed_end_to_end` | Windows: β45/45 pair at Σ 90, gear2 at C, interference 0; route recorded | M |
| **B1 bevel maths + form** | `bevel.py`, solver branch, §0.3 frame use, GUI rows, axial preview, artboards | GUI: Bevel m3 z20 mate 40 → §3.1 values; pair R 50 i 4:3 → §3.4 rows; dry run prints §3.3 | L |
| **B2 bevel probe** | `revolve`, `ref_plane_normal`, `loft_cut_*`, `pattern_loft`; findings + decide | `./probe.sh --tier 2` report; `decide` names `bevel_route` (STOP → ask the user) | L |
| **B3 bevel build + pair** | runners, Session members, build flow, `bevel_end_to_end` | Windows: pinion + gear + assembly, apexes coincident, Σ from `"Shaft Angle"`, interference 0; change teeth in SolidWorks → rebuilds clean | L |
| **S ship** | README sections, UI-DESIGN as built, "As executed" appendix to the plan doc, exe v0.3 (memory: copy to C:\, `python -m PyInstaller`) | `dist\Gear Generator v0.3.exe` builds a bevel pair and an internal pair beside SolidWorks | S |

Commits are prose with the why, ending with the attribution lines. Screenshots of the Tk window follow
the memory notes: a unique title, PowerShell capture, never the user's own exe.

## 8. Verification (end-to-end)

1. **Linux:** `python -m pytest` green. The dry runs for `kind=bevel,m=3,z=20,mate=40`,
   `kind=spur,teeth_side=internal,m=2,z=60` and a crossed pair print their ops with the globals first.
2. **Probe:** `./probe.sh` exits 0 or 1 with `bevel_route`, `crossed_route`, `bevel_mate_route` and
   `interference` decided; `latest.json` is committed; `test_findings.py` is green.
3. **Internal on Windows:** the ring's inner tip measures 116 and its root 125; with pinion 20 the
   assembly's `"Centre Distance"` is 40 and interference is 0. A helical ring built with a same-hand
   pinion also shows 0.
4. **Crossed:** gear2's centre sits at 84.853 mm from gear1's axis with its axis at 90°; interference 0.
5. **Bevel:** the pinion's outside diameter measures 67.218 and its crown sits 58.195 from the apex.
   Mass equals a fresh build's. Assembly axes are at Σ with apexes coincident, and interference is 0.
   Editing `"Shaft Angle"` to 80 in the assembly and the parts (Update values) rebuilds clean.
6. Screenshot of the window in bevel pair mode and internal pair mode.

## 9. Risks and later

- **Loft correspondence.** A loft between spline sections may not connect proportionally and could
  twist the space. The volume and centroid oracles catch it; the apex loft is the alternative. Neither
  → STOP.
- **Section frame.** The heel plane's sketch axes are measured, not assumed. A non-axis-aligned frame
  → STOP rather than rotating curve expressions.
- **Parametric rebuild of bevel planes.** When teeth or Σ change, the cone line moves and the planes
  and sections follow. `bevel_end_to_end`'s fresh-twin check is the evidence. If planes lose their
  references, record it and ask.
- **Gleason constants** are verified against a published example before pinning; K = 0 is a
  simplification, noted in the derived rows' hint.
- **Crossed-axis mates** may only be achievable as fixed placement (partial parametric), reported
  honestly in the sidecar and the status sentence.
- **Tip clash** uses a flank-only model: a warning, never a refusal.
- Reserved: spiral/zerol bevels, crown and internal bevels, opposite-hand crossed pairs, profile shift
  for spur and helical, and the SolidWorks gear mate.

## As executed (2026-09-15)

Where the build differs from the plan above, and what was observed on SolidWorks 2026 (revision 34.0.0):

- **Internal gears** built as planned. `internal_end_to_end` built a spur and a helical β15° R ring with their
  pinions through `swbuild.build_pair`: every sketch fully defined, one body, no interference as mated and
  interference with the pinion half a pitch round, and after `"No. of Teeth"` 60 → 64 each ring weighed what a fresh
  build did. The spur ring's volume against *blank − 60 × one space* agreed to 2.8e-4, not 1e-5: one space's cut
  weighs about 1e-3 of itself more alone than patterned, which is mass-property resolution on a spline cut, so the
  twin tolerance (5e-4) is used.
- **Interference is checked by every pair build** (`INTERFERENCE_CHECKED`), so the manual mesh step is gone for
  every kind.
- **A helix limit of 80°** (`helical.HELIX_LIMIT`) replaces the 45° refusal for a single gear: crossed pairs need
  helix angles past 45°. The parallel solver still searches up to 45°.
- **Bevel build route.** The plan's move-body idea was dropped when `move_body_rotate` showed a Move/Copy Body
  feature records no dimension a global could drive. The blank's half section is drawn on the Top plane in the
  final frame and revolved about its centreline, selected at mark 16 because the Cone Sketch's second centreline
  otherwise confuses the revolve. `ref_plane_normal` measured the perpendicular plane's sketch frame — origin at the
  line's end, x the cone's outward radial, y +Y — and it kept that frame when the line's angle and length changed,
  so each section is the spur section translated by the virtual radius and scaled (`spur.SectionFrame`), with no
  sign flip. `loft_cut_sections` lofted heel then toe at mark 1 as a `BlendCut` that removed its frustum to 1e-4.
- **Dimensions on the Top plane** are placed in model coordinates: an angle dimension placed at a sketch point read
  the supplement, because that plane's sketch y is −Z. `Session.dimension` converts through
  `ModelToSketchTransform`.
- **Component frames.** `IMathUtility.CreateTransform` answered "member not found" to late binding and worked
  invoked as a method with a double array; put on `Transform2` with the rotation in columns it set a frame to
  1e-16. `AddComponent5` places a component's middle, not its origin, at the point given, so both assembly plans
  now set gear 1 on the identity frame before placing and mating gear 2.
- **Bevel mates** (origins coincident, gear 2's axis in gear 1's top plane, angle between the axes, angle between the
  top planes) held a placed frame to 1e-16 and 0 mm.
- **Crossed mates.** A point-to-plane distance mate is measured along the plane's normal: an origin 8 mm below Top
  moved to 8 mm above it. The crossed plan passes the offset signed and `Session.add_mate` flips a negative one.
- **Explainer diagrams for the new fields** reuse existing ones (`widgets.DIAGRAM_ALIASES`); new artboards and
  renders in `design/` were not made.
- **Gleason pinion tips.** With K = 0 the m3 20-tooth pinion's tip is 0.722 mm thick, under the 0.3 × module the
  form warns at; the warning stands.
- **Bevel end to end** (`probe/p5_bevel.py`, m3 20:40, Σ 90°, face 20, bore 10, recipe A): pinion, gear and
  assembly built with every sketch fully defined and no interference; with gear 2 half a pitch round, 4
  interferences (482.4 mm³). The pinion's `"Outer Diameter"` read 67.218027 and every global matched `derive()`;
  after `"No. of Teeth"` 20 → 21 through `update_variables` all four sketches stayed fully defined and the pinion
  weighed 43638.719830 mm³, what a fresh 21-tooth build weighs to 1e-14. The apex loft and `pattern_loft` probes
  were not needed.
- **Crossed end to end** (mn 2, 20:40, β 45°/45° R, Σ 90°): built by the mates route with no interference, and 3
  interferences (102.6 mm³) with gear 2's mesh angle half a pitch round.

## Follow-on (2026-09-29, written on a machine without SolidWorks — none of it built there)

- **Crown gears** (|δ − 90°| ≤ 0.01°) and **internal bevel gears** (δ ≥ 91°) are derived, validated,
  solved and planned. The band 89°–91° either side of a crown gear is still refused, and the message
  names the shaft angle, `acos(−z_mate / z)`, that makes the gear a crown gear exactly.
  - Crown: δ is built as exactly 90° (`"Pitch Cone Angle"` is the literal 90, since the formula's
    denominator is zero there). The section is a rack: its sketch is `Du` to the root line, `Cu` to the
    cap line, `W` across the space on the pitch line, one flank at the pressure angle, the cap line
    carrying the other flank round as its mirror, and tangent root fillets. Addenda 0.54 m and 1.46 m,
    Gleason's limit as q → ∞. The blank's rims are measured along the axis: 3 m behind the root at the
    heel, 1 m at the toe, so the web inside the toe is at least 2 m thick.
  - Internal: equal addenda of one module (Gleason tabulates nothing for them), whole depth 2.188 m,
    default fillet 0.15 m as a ring's. The section is `internal.space_ops` on the back cone's ring of
    N / |cos δ| teeth, framed with its x reversed: the ring's centre is on its tips' side. The blank is
    a conical ring 3 m behind the root cone; a typed bore is warned about and not cut.
  - εα of any bevel pair is the sum of each gear's share of the path of contact on its back cone —
    external, rack (`ha / sin α`) or ring (`rv sin α − √((rv − ha)² − rb²)`).
- **Probe `bevel_planes_beyond_90`** (tier 2, extra) makes the heel plane fresh on cones of 90° and
  120° and measures its sketch frame, as `ref_plane_normal` did at 30° and 50°. Until it passes,
  `findings.BEVEL_CROWN_SECTION_X_SIGN` and `BEVEL_INTERNAL_SECTION_X_SIGN` are None and Build refuses
  those gears with the probe's name.
  - *Passed 2026-11-13* on SolidWorks 2026 (34.0.0) and 2024 (32.5.0), the same on both: on cones of
    90° and 120° the angle read as meant, the plane's origin was the line's end, and its sketch +x
    pointed the way the tips do, as below 90°. Both signs are +1 and Build no longer refuses these
    gears. A crown bevel pair and an internal bevel pair were then built through the tool on 2026
    with no failure and no interference (commit `70e3e1b`); not yet on 2024.
- **Fixed on the way:** recipe B's bevel sections linked their pitch circle to `"Pitch Diameter"` (the
  heel's) instead of `"Back Cone Pitch Diameter"`, so SolidWorks would have rebuilt the flank arcs on
  the wrong circle. Every bevel recipe-B plan was affected; recipe A, the default and the one probe
  `bevel_end_to_end` built, was not. `spur.space_ops` and `internal.space_ops` now take the pitch global.
- **Not built:** spiral and zerol bevel gears. Their teeth curve along the face (a cutter radius and a
  spiral angle), which needs a 3D tooth trace or guide-curve loft and SolidWorks calls not yet probed.

