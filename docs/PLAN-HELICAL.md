# Gear Generator — helical and herringbone gears

Approved 2026-09-14. Executed like `docs/PLAN.md`: read its "For the executing agent" section
first; the same conventions, the same probe-first rule (UNVERIFIED means the probe settles it,
never guess a call), and the same stop-and-ask triggers apply here.


## Context

The spur tool is built (v0.1): `docs/PLAN.md` is its approved plan, `design/UI-DESIGN.md` the
window as built, `probe/results/latest.json` the SolidWorks 2026 evidence it stands on. The user
now wants **helical** and **herringbone (double-helical)** gears in the same app, built the same
way: a `BuildPlan` of plain ops run by `swbuild` over COM, every new API member probed on the
live session before the tool relies on it. `PLAN.md` §3.8 left the seam for this (`GearKind`,
`PLANNED_KINDS = ("bevel", "helical", "internal")`).

First deliverable of execution: commit this plan as `docs/PLAN-HELICAL.md`. It is executed like
`PLAN.md` — same conventions ("For the executing agent"), UNVERIFIED means *the probe settles it,
never guess a call*, same stop-and-ask triggers.

### Decisions made with the user (2026-09-14)

| Question | Decision |
|---|---|
| "Macros" | The app's own COM build. No macro files are produced. |
| Module for a helical gear | **Normal module** `mn` (ISO, what a hob is sold by); transverse `mt = mn / cos β` is derived. |
| Pair Solve and β | A typed β stays fixed; a **blank β is solved** inside a min–max range so rows land exactly on the centre distance. |
| Scope | Helical and herringbone, **parallel shafts**. Crossed-axis helical is deferred to the bevel work (§10). |

Judgement calls (change at review if wrong): pressure angle is the **normal** pressure angle;
hand is per gear and gear B is forced opposite in a pair; a herringbone's hand names the half
nearest the Front plane; no herringbone centre groove in v1.

---

## 1. Maths — `gears/helical.py` (pure, Linux-tested)

The tooth-space sketch is the **transverse section**, so spur's profile code is reused. First
refactor `spur.py` with no behaviour change:

- `SpurGear.derive` → module-level `profile(n, mt, mn, alpha_t, backlash_t, fillet, face_width, bore) -> SpurDerived`.
  Spur calls it with `mt = mn`, `alpha_t = α`. **Tooth sizes read `mn`**: `da = d + 2mn`, the
  depth IIF, tip cap `da + 2mn`, backlash/fillet defaults, and the form-diameter reach
  `rp·sin αt − mn / sin αt` (`spur.py:535`). **Circumferential sizes read `mt`/`αt`**: d, p,
  space, s, ψs, inv α, db.
- `contact_ratio(mn, mt, n1, n2, alpha_t, C)`: `ra = d/2 + mn`, divisor `π·mt·cos αt`.
- `SpurGear.variables` split so the tail from `"Face Width"` on is one function taking the
  pressure-angle and module global names.
- `_field_errors`' `kind != "spur"` refusal moves into each kind.

Helical values (mm; degrees at the boundary):
```
mt = mn / cos β               d = mt·N          da = d + 2mn         h = user IIF on mn     df = da − 2h
αt = atan(tan αn / cos β)     db = d·cos αt     space_t = π·mt/2 + j / cos β   (j normal, default 0.3·mn)
lead L = π·d / tan β          twist over a path of length s: θ = 360·s / L degrees
N_min = 2·cos β / sin² αt     εβ = b·sin β / (π·mn)            εγ = εα + εβ
```
Sign convention, stated once in `helical.py` and `findings.py`: +Z is the direction the blank
extrudes from the Front plane; a **right-hand** gear's section at z is turned by `+2·z·tan β / d`
about +Z (right-hand rule). SolidWorks' Front view looks from +Z, so its visible face is the
*far* one — the preview labels faces rather than relying on "front/back".

`HelicalDerived` = the `SpurDerived` profile + `beta, hand, mt, alpha_t, lead, overrun,
twist, overlap`. `HerringboneGear(HelicalGear)` changes kind, default β range and the plan (§3.3).
`KINDS` gains both; `PLANNED_KINDS = ("bevel", "internal")`.

**validate** adds: error β ≤ 0 (Lead divides by tan 0; a zero twist cannot be found by value) or
β > 45°; error unknown hand; warning εβ < 1 (helical only); warning β outside 8–30° helical /
20–45° herringbone; warning twist > 360°; undercut judged by `N_min`; a note that
`"Fillet Radius"` is applied in the transverse section (the true transverse fillet is ρ/cos²β at
the root bottom).

**Pinned** (mn 2, N 20, αn 20°, β 15°, b 20, j 0.6): mt 2.070552 · d 41.411047 · da 45.411047 ·
df 36.411047 · αt 20.646896° · db 38.751267 · space_t 3.873582 · inv αt 0.016453 · φ 0.077086 ·
lead 485.527277 · twist over b 14.829239° · εβ 0.823847 · N_min 15.538. Pair 20/40: C 62.116571,
εα 1.5609. As β → 0 every value equals spur's to 1e-9.

## 2. Global variables

All ten of the user's names are kept (a helical part reads like their spur parts); they are no
longer contiguous, since what they reference must come first. Tests pin their relative order.
```
"No. of Teeth"= 20
"Module"= 2                                                      normal
"Bore Diameter"= 10
"Pressure Angle"= 20                                             normal
"Helix Angle"= 15
"Transverse Module"= "Module" / cos ( "Helix Angle" )
"Transverse Pressure Angle"= atn ( tan ( "Pressure Angle" ) / cos ( "Helix Angle" ) )   [spelling/unit: probe]
"Outer Diameter"= "No. of Teeth" * "Transverse Module" + 2 * "Module"
"Pitch Diameter"= "No. of Teeth" * "Transverse Module"
"Backlash"= 0.3 * "Module"
"Arc Length"= ( ( "Transverse Module" * pi ) / 2 + "Backlash" / cos ( "Helix Angle" ) )
"Fillet Radius"= 0.38 * "Module"
"Tooth Depth"= IIF ( "Module" <= 1.25 , "Module" * 2.4 , "Module" * 2.25 )
"Face Width"= 20
spur's tail from "Root Diameter" on, with "Transverse Pressure Angle" for the pressure angle and
  "Tooth Thickness"= "Transverse Module" * pi - "Arc Length"
"Lead"= pi * "Pitch Diameter" / tan ( "Helix Angle" )
"Overrun"= "Module"
helical:     "Path Length"= "Face Width" + 2 * "Overrun"
herringbone: "Mid Width"= "Face Width" / 2      "Path Length"= "Mid Width" + "Overrun"
"Twist Angle"= "Path Length" * 360 / "Lead"
```
Radian-document forms as today. `gears/equations.py` already evaluates `atn`/`arcsin`/`arccos`
in both modes; `findings.INVERSE_TRIG` picks the spelling SolidWorks accepts. If none is accepted:
**STOP and ask** (a literal αt would make β edits in SolidWorks silently wrong).

Hand is not a global: twist direction is a flag, not a signed dimension, so hand is structural.

## 3. Build recipe

### 3.1 Why a twisted sweep

A profile swept along a straight line with **constant twist along path** is an exact helicoid. A
loft between two turned sections is not (off by `r·(1 − cos θ/2)` mid-face, ≈ 0.17 mm at r 20,
θ 15°). If the twist value turns out not to be linkable, the fallback is a helix curve
(`InsertHelix`) as a guide curve for the same sweep; if neither works, STOP.

### 3.2 New ops (`gears/base.py`)

| Op | Fields | `check()` |
|---|---|---|
| `RefPlane` | `id, name, plane: int, offset, flip: bool, offset_dim="Offset"` | defines `id`; owns `offset_dim` |
| `SweepCut` | `id, profile, path, name, twist, flip: bool, twist_dim="Twist"` | uses two closed sketches; defines `id`; owns `twist_dim` |
| `MirrorBody` | `id, name, plane` (a `RefPlane` id), merge | uses the plane; defines `id` |
| `OpenSketch.plane` | `Union[int, str]` — int is tree order, str a `RefPlane` id | str must be defined |

`describe()`/`log_lines` get a line each. `Mate` refs keep `component:target`; `gear2:Mid Plane`
is a named plane.

### 3.3 Ordered ops

**Helical** — one sweep, profile ahead of the part so no sweep end lies on a blank face:
```
NewPart · AddGlobal × ~31 · Axis "Gear Axis" · spur blank ops (depth "Face Width")
RefPlane("profile", "Profile Plane", 1, overrun, flip=True) · Link "Offset@Profile Plane"= "Overrun"
spur tooth-space ops on OpenSketch("space", "profile") → "Tooth Space Sketch" + links
OpenSketch("path", 2): construction line origin → −e along the axis, path line −e → b + e;
  origin/axis relations per findings.TOP_SKETCH_AXIS; dims "Lead In" (e), "Length" (b + 2e)
  → "Path Sketch"; links to "Overrun" and "Path Length"
SweepCut("space_cut", "space", "path", "Tooth Space", twist, flip = hand flag) · Link "Twist@Tooth Space"= "Twist Angle"
CircularPattern "Teeth" of space_cut · Link "Count@Teeth" · bore ops · ManualStep material · Rebuild · SaveAs
```
**Herringbone** — half a gear, mirrored (N sweeps, not 2N; the mirror reverses the hand by
geometry, so there is no second twist sign to get right; the apex is the profile itself):
```
… blank ops with depth "Mid Width" (Link "Width@Blank"= "Mid Width")
RefPlane("mid", "Mid Plane", 1, b/2) · Link "Offset@Mid Plane"= "Mid Width"
tooth-space ops on "mid"
path sketch on plane 2: construction line origin → b/2, path line b/2 → −e (toward the Front plane);
  dims "Mid" and "Length" → links "Mid Width", "Path Length"
SweepCut (flip = hand flag for a −Z path, per probe sweep_dir) · twist link · CircularPattern "Teeth"
MirrorBody("mirror", "Mirror", "mid") · bore ops (through all both, after the mirror) · material · Rebuild · SaveAs
```
Herringbone fallback, if `mirror_body_merge` fails: full-width blank, two sweep cuts from the
mid-plane profile with opposite hand flags, one pattern of both (`CircularPattern.features`
becomes a tuple only then).

Every sketch's fully-defined status is reported as today.

### 3.4 Names set and read back

`Gear Axis` · `Blank Sketch`/`Blank` · `Profile Plane` or `Mid Plane` (`Offset@`) ·
`Tooth Space Sketch` · `Path Sketch` (`Lead In@`/`Mid@`, `Length@`) · `Tooth Space` (`Twist@`) ·
`Teeth` (`Count@`) · `Mirror` · `Bore Sketch`/`Bore`.

## 4. Pairs

### 4.1 Solver (`gears/pair.py`)

`solve(…, kind="spur", helix_angle=None, helix_range=(lo, hi))`; spur unchanged. Helical kinds
mesh with the same `mn`, the same β and **opposite hands**, at `C = mn·(N1 + N2) / (2·cos β)`:

- **β typed:** spur's algorithm with `S = 2C·cos β / mn`; non-standard tier `mn* = 2C·cos β / S`.
- **β blank:** for each allowed `mn`, every whole `S` in `[⌈2C·cos hi / mn⌉, ⌊2C·cos lo / mn⌋]`
  (lo > 0), `N1` at the nearest split of `S` and ±1, `β = acos(mn·S / 2C)`. Every row is exact on C.

`Candidate` gains `helix_angle` and `overlap` (from gear A's face width; `nan` if unreadable).
Undercut is per row against `N_min(β)`. Rank: `(C error ≠ 0, not standard, undercut, ratio
error, −mn, β)` — larger module, then the smaller helix angle (axial thrust ∝ tan β). `apply()`
writes `module`, `teeth`, `helix_angle` (6 decimals) into both gears and sets B's hand opposite
A's. `describe()` returns εα and εβ for helical kinds.

Pinned (C 60, i 2, β blank, 8–25°, series 1): m2.5 15/30 β 20.3641 · m2 19/38 β 18.1949 ·
m1.5 26/52 β 12.8386 · m1.5 25/50 β 20.3641 · m1.25 31/62 β 14.3615 · m1.25 30/60 β 20.3641 ·
m1 39/78 · 38/76 · 37/74 · then m3 13/26 β 12.8386 (undercut). β typed 15°, C 62.116571, i 2 →
m2 20/40 first, exact.

### 4.2 Assembly (`assembly_plan`)

Centre distance is `mt·(N1+N2)/2` computed from the β **literal the parts hold**. Mesh angle is
spur's formula on N2, applied at each gear's unrotated reference section:

- **Helical:** unchanged mates. Both profiles sit `"Overrun"` = mn ahead of their Front planes,
  and mn is shared, so Front-plane coincidence puts both reference sections at the same z for
  any pair of face widths; opposite hands are then the conjugate rotation all along the face.
- **Herringbone:** `gear2:Mid Plane ~ gear1:Mid Plane` coincident replaces the front-plane mate,
  so the apexes line up when face widths differ.

`"Helix Angle"` is added as an assembly global. `swcom._component_ref`'s `SelectByID2` fallback
must use `"PLANE"` for a named plane, not `"AXIS"`. If the interference probe passes, `build_pair`
checks interference after the rebuild (0 → `done`, else `CHECK` with the volume) and the manual
"check the teeth mesh" step is dropped.

## 5. App layers

### 5.1 `spec.py`
`GearSpec`: `helix_angle: str = ""`, `hand: str = "right"` (spur refuses a non-zero β with a
sentence pointing at Kind). `KIND_HELICAL`, `KIND_HERRINGBONE`, `HANDS`. `PairSpec`:
`helix_angle` (blank = solve), `helix_min`, `helix_max` (blank = the kind's default). Stems:
`Helical_m2_N20_15R`, `Herringbone_m2_N20_30L`; pinion/gear stems take the same suffix; pair
`Pair_m2_20T_40T_H15`. **`tests/test_spec.py:34` and `tests/test_store.py:99` use `helix_angle`
as their "unknown key from a later version" — change them to another key.**

### 5.2 `swbuild.py`
Protocol + `_RUNNERS`: `ref_plane`, `sweep_cut`, `mirror_body`, in the `_extrude`/`_pattern`
idiom (kept name and dimension name read back into `result`). `open_sketch` takes a plane handle.
`STRUCTURAL = ("kind", "recipe", "hand")`. `update_variables` on a record with a `partner`/
`assembly` warns in its result that β, module or teeth changes leave the assembly's
`"Centre Distance"` stale. `FakeSolidWorks` gets the new members.

### 5.3 `swcom.Session`
`ref_plane`, `sweep_cut`, `mirror_body`, `open_sketch` by handle, `center_of_mass` (probe
oracle), and `interference_volume` if probed — each written from the probe code that ran, with a
docstring naming the probe and version.

### 5.4 `findings.py` and `probe/decide.py`
New constants, each naming its probe: `INVERSE_TRIG`, `INVERSE_TRIG_UNITS`, `EXTRUDE_DIRECTION`,
`REF_PLANE_CALL`, `REF_PLANE_FLIP_IS_MINUS_Z`, `TOP_SKETCH_AXIS`, `SWEEP_CALL`,
`SWEEP_PROFILE_MARK`, `SWEEP_PATH_MARK`, `TWIST_FLIP_FOR_RIGHT_HAND` (per path direction),
`TWIST_DIM_NAME`, `SWEEP_ENDS` (`"overrun"` confirmed), `PATTERN_GEOMETRY`, `MIRROR_BODY_CALL`,
`HELIX_ROUTE` (`"twist"` | `"guide"` | `STOP`), `HERRINGBONE_ROUTE` (`"mirror"` | `"two sweeps"`),
`INTERFERENCE_CALL` or `None`. `decide.py` gains `helix_route` and `herringbone_route`;
`test_findings.py` covers them.

### 5.5 GUI (`gui.py`, `ui_text.py`, `preview.py`, `widgets.py`, `design/`)
- **Gear:** Kind `Spur · Helical · Herringbone · Bevel · Internal` (last two greyed *later*). Check
  five labels fit the segmented row on the canvas first; if not, `Double` with the full word in the readout.
- **Gear A/B:** after Pressure angle, `grid_remove`d for spur: **Helix angle** (°, dropdown
  10/15/20/25/30) and **Hand** (`Right · Left`). In pair mode both mirror the Pair panel's β and
  B's hand shows opposite A's, disabled. Module and Pressure angle hints say *normal*.
- **Pair:** Helix angle (placeholder *any*, hint *blank solves it*) and Helix *min* to *max*, shown for
  helical kinds. Flyout columns `MODULE · TEETH · β · ERROR`; ERROR adds *overlap 0.82* under 1.
- **Derived:** rows β · hand, mt, αt, lead, twist over the face, overlap. Pair rows: *Contact ratio
  1.561 + 0.824 overlap*. Readout `Helical 15° R · involute curve`.
- **Preview:** helical — the front-face section solid, the far face faint (`#d8d8d8`) turned by
  the twist over b; herringbone — the apex section solid, the faces faint. `preview.layout`
  carries per-gear `face_rotations`; pair mode turns B by the mesh angle as now.
- **Explainers:** `helix_angle`, `hand`, `helix_range` with diagrams in both `widgets.draw_diagram`
  and `design/canvas/gen.py` `DIAGRAMS`; `module`/`pressure_angle` copy gains a helical sentence.
- **Tables:** `GEAR_VARS` + `helix_angle`, `hand`; `PAIR_VARS` + three pair fields.
- **Design:** `Helical.dc.html` artboard (pair mode) from `gen.py`, renders in `design/renders/`
  (memory: headless Windows Chrome), `design/UI-DESIGN.md` updated.

### 5.6 `store.py` / Update values
No schema bump: new spec keys are additive, `from_dict` ignores unknown ones, an old sidecar
reads as spur. β, face width, teeth and module flow through the globals; kind and hand changes
are refused with the existing sentence.

## 6. Probes (existing harness; scratch parts only; arities from recorded macros and `argerror`, enum values from `swconst`)

| Tier | Probe | Asserts | Oracle |
|---|---|---|---|
| 1 | `equation_inverse_trig` | `atn`/`arctan`/`arcsin`/`arccos` accepted; units in degree and radian documents; `cos ( "β" )` with a degree global | `atn(1)` = 45 or π/4 |
| 1 | `helical_globals` | every §2 global accepted in order, both kinds | values = `derive()` to 1e-9 |
| 1 | `line_length_dimension` | `AddDimension2` on one line measures length; renames; links | read back in metres |
| 2 | `center_of_mass` | `IMassProperty.CenterOfMass` shape and units; extrude goes +Z | boss at x 15 → (15, 0, b/2) |
| 2 | `ref_plane_offset` | `InsertRefPlane` distance ± flip; renamed; offset dim found by value, linked, rebuild follows | centroid of a boss sketched on it |
| 2 | `path_sketch` | Top-plane sketch axis ↔ model Z and its sign | `ModelToSketchTransform` (DB reading/05) |
| 2 | `sweep_twist_boss` (decider) | sweep routes (`InsertProtrusionSwept*`/`InsertCutSwept*`, `CreateDefinition` + `ISweepFeatureData`); twist along path, plain and flipped; marks 1 profile / 4 path; twist dim found by value, renamed `Twist`, linked, rebuild | circle r0 at (15, 0) swept L 20, θ 90°: volume A·L; centroid `15·(sin θ/θ, ±(1−cos θ)/θ)`, z L/2 — sign **and** linear twist |
| 2 | `sweep_dir` | same with the path toward −Z | sign of centroid y |
| 2 | `sweep_cut_ends` | overrun ends vs coplanar start (herringbone starts on the half blank's face) | one body, removed volume A·b |
| 2 | `pattern_sweep` | pattern of a sweep cut, geometry pattern off/on, rebuild seconds at N 24 and 60 | volume = blank − N·A·b |
| 2 | `mirror_body_merge` | mirror body about a ref plane, merged | one body, 2× volume, centroid z = offset |
| 2 extra | `helix_guide` | fallback route (H) — run only if the twist link fails | as `sweep_twist_boss` |
| 4 | `midplane_mate` | coincident mate on a named RefPlane inside components | component z offset |
| 4 extra | `interference` | right pair → 0; same hand or half-pitch off → > 0 | negative controls |
| 5 | `helical_e2e`, `herringbone_e2e` | m2 z13 β20° R b10 bore 8, Recipe A through `swbuild.build`: names, sketches fully defined; volume = a twin plan with `Cut` for `SweepCut` (Cavalieri, 1e-5 relative); `"Helix Angle"` 20 → 25 and `"Face Width"` 10 → 12 via `update_variables` → matches the twin again | twin spur part |

Pinned for the e2e gear (mn 2, N 13, β 20°, b 10): mt 2.128356 · d 27.668622 · da 31.668622 ·
αt 21.172832° · db 25.800856 · lead 238.820463 · twist over b 15.074085°.

DB write-back in its own commit (CONTRIBUTING rules): `features/05-reference-plane-offset`,
`features/06-sweep-with-twist`, `features/07-mirror-body`, `equations/03-inverse-trig`,
`reading/11-centre-of-mass-as-an-oracle`, `assemblies/03-interference-detection` (if probed),
API-LEDGER rows via `--ledger`, manifest rebuilt. Failures recorded as findings.

## 7. Tests (Linux, `.venv/bin/python -m pytest`)

| File | Pins |
|---|---|
| `test_gears_spur.py` | green after the refactor, untouched except `PLANNED_KINDS` (line ~306) |
| `test_gears_helical.py` (new) | §1 values; β → 0 equals spur; N_min, εβ; validate sentences; plans pass `check()` for both kinds × both recipes; ten user names in relative order, every global before its first use; flip flags per hand/kind; §3.4 names; herringbone op order (mirror before bore) |
| `test_equations.py` | §2 list evaluates equal to `derive()` in both trig modes, each inverse-trig spelling |
| `test_gears_pair.py` | §4.1 cases; `apply` writes β and flips B's hand; C from the β literal; helical uses Front planes, herringbone `Mid Plane` |
| `test_swbuild.py` | fake new members; stop at a failing sweep; `hand` structural; partner warning on update |
| `test_spec.py`, `test_store.py`, `test_ui_text.py`, `test_gui_spec.py`, `test_preview.py` | new fields round-trip (unknown-key tests moved off `helix_angle`); old sidecar reads as spur; every readout/explainer; table coverage; face rotations |
| `test_probe_decide.py`, `test_findings.py` | both routes from canned results; constants agree with `latest.json` |

## 8. Phases

| Phase | Deliverable | Demonstrable | Size |
|---|---|---|---|
| **H0 refactor** | `docs/PLAN-HELICAL.md`; `spur.profile()`, `contact_ratio` signature, variables tail, `OpenSketch` plane handle | full suite green; spur dry run (`python -m gear_generator.gears`) byte-identical to before | S |
| **H1 maths + form** | `helical.py`, solver, spec, ui_text, preview, GUI rows, explainers, artboard + UI-DESIGN | GUI: Helical m2 z20 β15 → §1 values and face outlines; pair C 60 i 2 β blank → §4.1 rows → pick → both gears filled, B left; dry run prints §3.3 for both kinds | L |
| **H2 probe** (SolidWorks open on host; can run beside H1) | §6 probes, results committed, findings + decide, Session members, DB write-back | `./probe.sh --tier 2` report; `decide` names `helix_route` and `herringbone_route` (a STOP → ask the user) | L |
| **H3 build** | runners, build flow for both kinds, Update values | Windows: Build helical m2 z20 β15 R → saved part, sketches fully defined; edit `"Helix Angle"` in SolidWorks → re-twists cleanly; herringbone the same, symmetric about `Mid Plane` | M |
| **H4 pair** | assembly changes, interference check if probed | Solve → Build → two opposite-hand parts + assembly at C; interference 0 or the counted manual check | M |
| **H5 ship** | README section, UI-DESIGN as built, exe v0.2 (memory: copy to C:\, `python -m PyInstaller`) | `dist\Gear Generator v0.2.exe` builds a helical pair beside SolidWorks | S |

## 9. Verification (end-to-end)

1. Linux: `python -m pytest` green; the gears dry run for `kind=helical,m=2,z=20,beta=15` prints §3.3 with globals first.
2. Probe: `./probe.sh` exits 0/1 with both routes decided; `latest.json` committed; `test_findings.py` green.
3. Single helical on Windows: OD 45.411; `Twist@Tooth Space` = (20 + 4)·360 / 485.527277 ≈ 17.795°; mass = the twin spur of the same transverse profile; `"Helix Angle"` → 20 rebuilds clean.
4. Herringbone: one body, centroid at z = b/2, apex on `Mid Plane`.
5. Pair: C 60 i 2 β blank → m2 19/38 β 18.1949 → two parts + assembly, distance mate 60; interference 0; screenshot the Tk window per memory (unique title, PowerShell capture; never match the user's v0.1 exe).

## 10. Risks and later

- **Twist not linkable** → helix-guide route; neither → STOP (no literal twist that ignores β edits).
- **Rebuild time:** twisted sweeps of equation-curve profiles are spline surfaces; the probe records seconds at N 60 and tries geometry pattern. A slow result is reported to the user, not worked around. Watch the probe's 120 s timeout.
- **Inverse trig** spelling/units unverified; STOP if none works.
- **Volume oracle** loosens to ~1e-5 on spline surfaces.
- **Path on the axis** must be held by relations, not coordinates, or the teeth wobble.
- **Crossed-axis helical** (shaft angle Σ = β1 ± β2, same hands at 90°): the parts are §3's; only the assembly differs (non-parallel axis mates, C from each gear's own mt). Deferred to the bevel phase, which needs non-parallel axis mates too; add a line to `PLAN.md` §9.
- Herringbone centre groove, profile shift, SolidWorks gear mate: reserved.
