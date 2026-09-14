# Gear Generator — a SolidWorks spur-gear builder, sibling of Airfoil-Converter

## For the executing agent — read this first

This document is a complete, approved plan. Execute it in the phase order of §7; do not
re-open the decisions in the Context table below (the user made them). Where the plan says
UNVERIFIED, that is a fact about the SolidWorks API, not a gap in the plan: the probe phase
(§5) exists to settle it, and the rule is *record what SolidWorks did, never guess a call*.

**Before writing any code, read** (they are the template and the rulebook):
- `/home/m0obot/Airfoil-Converter/README.md`, `src/airfoil_converter/{swcom,swlink,export,store,gui,widgets,theme,ui_text}.py`, `tests/`, `pyproject.toml`, `build.bat`, `design/UI-DESIGN.md`
- `/home/m0obot/SW-Macro-Database/{AGENTS,CONTRIBUTING,GOTCHAS,API-LEDGER,INDEX}.md`, `entries/sketches/0[1-6]-*.md`, `entries/curves/08-*.md`, `entries/curves/11-*.md`, `entries/connect/02-*.md`, `entries/connect/10-*.md`, `entries/reading/07-*.md`, `entries/_TEMPLATE.md`, `tools/build_manifest.py`

**Environment:** you are on WSL2 Linux; SolidWorks 2026 runs on the Windows host. Develop
and unit-test on Linux (venv + pytest, §6). Anything that touches SolidWorks runs on Windows:
`python.exe` (Store Python 3.13 with pywin32) is on the WSL PATH, so `./probe.sh` and
`python.exe main.py` work from a WSL shell as long as SolidWorks is open on the host.
Paths handed to SolidWorks must be under `C:\`; the repo may stay on ext4.

**Definition of done per phase** is the "Demonstrable" column of §7. Do not report a phase
complete until that is observed. Phase 2's probe results (`probe/results/latest.json`) are
committed evidence; `findings.py` must agree with them (`tests/test_findings.py`).

**Stop and ask the user only when:** SolidWorks is not open on the host and a phase needs it;
the probe reaches a STOP decision (§5.2) — do not improvise a workaround; a template path or
output folder is needed and the defaults in Context do not exist; or a decision in the
Context table would have to change.

**Conventions:** typed-text spec fields; every `raise` is a full sentence naming the field or
feature and what SolidWorks said; hard-won facts as docstring paragraphs with the version they
were observed on; no runtime dependencies; pywin32 imported inside `try`; structured console
output (lowercase ok, UPPERCASE means a person must act); rebuild once, restore
`CommandInProgress` in `finally`; read every name back after setting it; never overwrite or
delete a user's file or feature. Commit messages are prose with the *why* (see
`git -C /home/m0obot/Airfoil-Converter log`), ending with the attribution lines your session
provides. Write back to SW-Macro-Database (§5.5) in its own commit under its ten rules.

## Context

The user builds parametric spur gears in SolidWorks by hand today: a set of global
variables in the Equation Manager (`"No. of Teeth"`, `"Module"`, `"Bore Diameter"`,
`"Pressure Angle"`, and derived ones like `"Outer Diameter"`, `"Pitch Diameter"`,
`"Backlash"`, `"Arc Length"`, `"Fillet Radius"`, `"Tooth Depth"` with an `IIF`),
then a sketch, an extrude, a cut, a circular pattern. They want a desktop tool,
in the mould of `/home/m0obot/Airfoil-Converter`, that does this for them from a
form, and that can also *solve* a gear pair: given a centre distance and a target
ratio, fill in module and tooth counts that work. Spur gears only for now; bevel
(and other kinds) must be able to slot in later.

Two existing assets were surveyed:

- **`/home/m0obot/Airfoil-Converter`** — the template. Stdlib-only Python +
  tkinter, pywin32 optional and late-bound, all COM in one module (`swcom.py`),
  ordering rules in a Protocol-based module (`swlink.py`) tested against a fake
  on Linux, typed-text `ExportSpec` dataclass, JSON sidecar store, hand-drawn
  widgets, PyInstaller one-file exe. It has **no SolidWorks equation handling**
  at all — everything it sends is baked point coordinates.
- **`/home/m0obot/SW-Macro-Database`** — a knowledge base (36 entries, evidence-graded
  `verified | partly-verified | unverified`), not a macro collection. Verified:
  attach via Running Object Table, curve-through-points, rebuild-once-in-`finally`,
  naming read-back, WSL→cscript bridge. **Unverified:** the entire 2D sketch API.
  **Absent:** equations, extrude, cut, circular pattern, fillet, mirror, new part
  from template, SaveAs, assemblies, mates. The repo asks that whoever verifies
  these comes back and writes them up.

Host facts confirmed from WSL during planning: Windows Store Python 3.13 is on the
PATH as `python.exe`; SolidWorks 2026 (revision major 34) default templates exist at
`C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2026\templates\Part.PRTDOT` and `Assembly.ASMDOT`;
this WSL `python3` (3.14) has neither `pytest` nor `tkinter`.

### Decisions made with the user

| Question | Decision |
|---|---|
| Behaviour inside SolidWorks | **Fully parametric.** Global variables written to the Equation Manager; every sketch dimension, extrude depth and pattern count linked to them. Changing `"No. of Teeth"` in SolidWorks rebuilds the gear. |
| Tooth flank | **Both recipes built as candidates**, the live-session probe decides the default: (A) true involute via Equation Driven Curve; (B) arc-approximation "tutorial" method. Both stay selectable in the UI. |
| What a Build produces | **A new part per gear** from a template, saved to a chosen folder, sidecar JSON beside it; **a solved pair also gets an assembly** with the two gears mated at the centre distance. |
| Runtime | **Same as Airfoil-Converter:** tkinter, pywin32 attach to the running session, PyInstaller exe; shared modules copied nearly verbatim; tests on Linux against a fake. |

Judgement calls made in this plan (change at review if wrong): new repo at
`/home/m0obot/Gear-Generator`, package `gear_generator`; shared modules are
**copied**, not extracted into a shared library (both tools are stdlib-only
single-exe apps and a cross-repo dependency would complicate `build.bat`); metric
module only; the gear is built by **cutting one tooth space from an OD blank and
circular-patterning the cut** (see §3.1); the user's `Backlash = 0.3 × Module` rule
is kept as the default equation (it is large by ISO standards — a hint next to the
field says so, not a warning on every build).

---

## 1. Repo and module map

```
/home/m0obot/Gear-Generator/
  pyproject.toml   main.py   build.bat   probe.bat   probe.sh   probe.py   .gitignore   README.md
  design/UI-DESIGN.md                      panel list of §5.5 in the idiom of Airfoil-Converter/design/UI-DESIGN.md
  probe/results/                           probe-results-<stamp>.txt/.json + latest.json (committed evidence)
  src/gear_generator/
    __init__.py  __main__.py  assets/fonts/README.md
    theme.py  widgets.py                   COPY-VERBATIM
    swcom.py                               ADAPT: keep attach/call/Worker/Call/Session core; drop curve, folder and pick members; add §5.2 members
    findings.py                            NEW: constants settled by the probe (default recipe, arities, dim names, trig default)
    spec.py                                ADAPT from export.py: GearSpec / PairSpec typed-text dataclasses, naming
    gears/base.py                          NEW: Derived, Diagnostic, Op dataclasses, BuildPlan, GearKind Protocol
    gears/equations.py                     NEW: expression strings, fmt9, a tiny evaluator of the Equation Manager grammar
    gears/spur.py                          NEW: derive / validate / outline / variables / two recipes
    gears/pair.py                          NEW: centre-distance + ratio solver
    gears/standards.py                     NEW: ISO 54 module series, pressure angles
    swbuild.py                             ADAPT shape of swlink.py: SolidWorks Protocol + op interpreter (build, build_pair, update_variables)
    store.py                               ADAPT: one GearRecord per <part>.gear.json; plus recent.json
    ui_text.py                             ADAPT: readouts
    gui.py                                 ADAPT skeleton: strip + flyout + tick loop + build flow; all panels new
    probe/  __init__.py __main__.py harness.py comerr.py report.py decide.py scaffold.py p_*.py
  tests/                                   see §7
```

Reuse, with the pattern each one carries:

| From Airfoil-Converter | Pattern | Goes to |
|---|---|---|
| `swcom.py:46-56` guarded pywin32 import; `:235-278` ROT attach; `:209-232` `call`, `_null_dispatch`, `_out_long`; `:539-560` feature walk; `:650-676` diff-tree-then-rename-then-read-back; `:767-779` suppress/rebuild; `:818-895` `Worker`/`Call` | the COM idioms | `swcom.py` (kept) |
| `swlink.py:34-49` Protocol; `:180-219` suppress → try → `finally` restore → rebuild once | ordering testable with a fake | `swbuild.py` |
| `export.py:10-15, 65-73, 76-122` typed-text spec, `InputError`, `parse_float`, `to_dict`/`from_dict` filtering unknown keys | the form as data | `spec.py` |
| `store.py:142-262` sidecar path, deterministic JSON, schema refusal, move-aside, atomic save | persistence | `store.py` |
| `writer.py:30-40` no negative zero, `:72-77` `sanitize` | number/name hygiene | `gears/equations.py::fmt9`, `spec.py::sanitize_stem` |
| `geometry.py:698-717` `signed_area`, `clean_loop`; `:502-511` `auto_close` | outline validation | `gears/spur.py` |
| `gui.py:76-97` `SPEC_VARS` table + `:1160-1168` `_spec()`; `:310-417` strip; `:1193-1223` `_tick`; `:1988-2177` export→push→collect flow; `:2296-2379` `main()` | window skeleton | `gui.py` |
| `tests/test_swlink.py:18-96` `FakeSolidWorks`; `tests/test_gui_spec.py:18-33, 64-80` coverage + AST guard | test idioms | `tests/` |
| SW-Macro-Database `connect/10` lowercase/UPPERCASE output; `reading/07` `GetTypeName2` first; `sketches/05` metres/radians/9 decimals; `sketches/06` counted `SW-MANUAL` steps; `GOTCHAS` §4 §5 §8 §9 §11 | conventions | everywhere |

`pyproject.toml`, `main.py`, `build.bat`, `.gitignore` mirror Airfoil-Converter's byte-for-byte
except names (`gear-generator`, `gear_generator.gui:main`, `"Gear Generator v0.1"`); keep the
four load-bearing hidden imports and the header comments explaining them.

---

## 2. Domain: gear maths and the pair solver (pure, Linux-tested)

### 2.1 `gears/spur.py` — derived values (mm and degrees at the boundary, radians inside)

```
d  = m·N                 pitch          da = (N+2)·m              outer (user's expression)
h  = 2.4m if m ≤ 1.25 else 2.25m         tooth depth (user's IIF)
df = da − 2h             root           db = d·cos α              base
p  = π·m                 circular pitch
space = π·m/2 + j        "Arc Length" = tooth SPACE width at the pitch circle (settled interpretation)
s  = p − space           tooth thickness at pitch = π·m/2 − j
ψs = space / d           half-space angle at pitch (rad);   ψt = s / d
inv α = tan α − α        φ = ψs − inv α                     flank rotation offset (rad)
t_max = sqrt((da/db)² − 1)                                 involute parameter at the tip
N_min = 2 / sin²α        undercut threshold (17.10 at 20°) — warn, do not refuse
base above root ⇔ N·(1 − cos α) < 2h/m − 2   (N ≤ 41 at 20°, h = 2.25m; N ≤ 46 for h = 2.4m)
contact ratio (pair) ε = [√(ra1²−rb1²) + √(ra2²−rb2²) − C·sin α] / (π·m·cos α)
```

Involute of the upper flank of the space centred on +X, then `(x, −y)` for the lower:
`x = rb(cos(t+φ) + t·sin(t+φ))`, `y = rb(sin(t+φ) − t·cos(t+φ))`. `outline(spec)` walks one
space CCW — root arc → fillet → radial line → involute → tip arc — rotates it N times,
closes with `auto_close`, asserts `signed_area > 0`. Recipe B's preview swaps the involute
for its osculating arc (centre on the base circle at polar angle ψs + α, radius rp·sin α)
and `flank_deviation()` reports the max radial error (tens of µm at m ≈ 1.5).

**Pinned test values** (m = 1.5, N = 25, α = 20°, j = 0.45, ρ = 0.57): d 37.5 · da 40.5 ·
h 3.375 · df 33.75 · db 35.238473 · p 4.712389 · space 2.806194 · s 1.906194 · ψs 0.074832 rad ·
inv α 0.014904 · φ 0.059927 · t_max 0.566496 · N_min 17.097 · ε(self-mesh at C 37.5) 1.6117.
Also m 1 N 17 (no undercut warning at exactly 17), m 1 N 50 (base below root), m 2 N 12
(undercut warning, still a closed outline); the outline crosses the pitch circle 2N times and
each space's angular width at rp equals space/rp to 1e-9.

**`validate(spec) -> list[Diagnostic]`**, full sentences. Errors: module ≤ 0; teeth < 6 or not
integer; pressure angle outside 10–35°; face width ≤ 0; backlash ≥ p/2; bore ≥ root diameter;
fillets that do not both fit in the root space; profile shift ≠ 0 (reserved for v2). Warnings:
undercut (N < N_min); bore rim thinner than one module; tip thickness < 0.3m; Recipe A flank
start above the form diameter; Recipe B's deviation for this gear.

### 2.2 `gears/pair.py` — the solver

Inputs: centre distance C, ratio text (`"3"`, `"3:1"`, `"1:3"`, `"0.333"` → N_driven/N_driver),
pressure angle, module (blank = any standard), series (ISO 54 series 1 by default, 1+2, plus a
DIN 780 fine series off by default), `min_teeth` (17), `max_teeth` (200).

Algorithm, deterministic: for each allowed m, S = 2C/m; for S′ ∈ {⌊S⌋, ⌈S⌉}: N1 = round(S′/(1+i))
and ±1, N2 = S′ − N1. Then a non-standard tier: for exact-ratio integer pairs no standard
module hits, m* = 2C/(N1+N2), flagged `standard=False`. Each candidate carries actual ratio,
actual C, ratio error, C error, undercut flag, contact ratio. **Ranking key:**
`(C_error ≠ 0, not standard, undercut, ratio_error, −m)`. Reverse direction `describe(m, N1, N2)`
→ (C, i, ε). Profile shift to close a small C gap is reserved for v2 (report the gap only).

Pinned cases: C 60, i 3 → m 1.5 20/60 · m 1.25 24/72 · m 1 30/90 · then undercut exact rows
(m 2 15/45, m 2.5 12/36) · then nearest-C rows. C 45, i 2 → m 1.5 20/40 · m 1.25 24/48 · m 1 30/60.
`"1:3"` yields N1 > N2. `apply(candidate, a, b)` writes `module`/`teeth` text into both specs and
touches nothing else.

`gears/standards.py`: `ISO_MODULES_1 = (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32, 40, 50)`,
`ISO_MODULES_2 = (1.125, 1.375, 1.75, 2.25, 2.75, 3.5, 4.5, 5.5, 7, 9, 11, 14, 18, 22, 28, 36, 45)`,
`FINE = (0.5, 0.6, 0.7, 0.8, 0.9)`, `PRESSURE_ANGLES = ("14.5", "20", "25")`.

---

## 3. The SolidWorks build recipe (data, executed by `swbuild`)

### 3.1 Topology: cut one tooth space from an OD blank, pattern the cut

Chosen over "extrude one tooth + root disc": the blank is always a valid solid so a bad
profile shows as one red feature; a space closed *beyond* the OD (tip cap at da + 2m) needs no
exact coincidence with the OD edge, so N/m changes cannot leave slivers; it is the topology the
user's own `"Arc Length"` (a space width) was written for.

### 3.2 Global variables — exact strings, in this order (`gears/spur.py::variables`)

The first ten are the user's, byte-for-byte; the rest are what the sketch needs. Every name is
defined before anything references it.

```
"No. of Teeth"= 25
"Module"= 1.5
"Bore Diameter"= 10
"Pressure Angle"= 20
"Outer Diameter"= ( "No. of Teeth" + 2 ) * "Module"
"Pitch Diameter"= "No. of Teeth" * "Module"
"Backlash"= 0.3 * "Module"                       (typed override → literal value instead)
"Arc Length"= ( ( "Module" * pi ) / 2 + "Backlash" )
"Fillet Radius"= 0.38 * "Module"                 (typed override → literal)
"Tooth Depth"= IIF ( "Module" <= 1.25 , "Module" * 2.4 , "Module" * 2.25 )
"Face Width"= 10
"Root Diameter"= "Outer Diameter" - 2 * "Tooth Depth"
"Base Diameter"= "Pitch Diameter" * cos ( "Pressure Angle" )            [degree form; radian form if detected]
"Base Radius"= "Base Diameter" / 2
"Tooth Thickness"= "Module" * pi - "Arc Length"
"Half Space Angle"= ( "Arc Length" / "Pitch Diameter" ) * 180 / pi      [always degrees: it drives an angular dim]
"Involute Fn"= tan ( "Pressure Angle" ) - "Pressure Angle" * pi / 180   [value in rad]
"Flank Offset"= "Arc Length" / "Pitch Diameter" - "Involute Fn"         [rad]
"Tip Cap Diameter"= "Outer Diameter" + 2 * "Module"
"Flank Start Diameter"= IIF ( "Base Diameter" >= "Root Diameter" + 3 * "Fillet Radius" , "Base Diameter" , "Root Diameter" + 3 * "Fillet Radius" )
"Involute t1"= sqr ( ( "Flank Start Diameter" / "Base Diameter" ) ^ 2 - 1 )      [Recipe A]
"Involute t2"= sqr ( ( "Tip Cap Diameter" / "Base Diameter" ) ^ 2 - 1 )          [Recipe A]
"Flank Arc Radius"= ( "Pitch Diameter" / 2 ) * sin ( "Pressure Angle" )          [Recipe B]
"Flank Centre Angle"= "Half Space Angle" + "Pressure Angle"                       [Recipe B, degrees]
```

**Trig units** are a per-document Equation Manager setting (degrees by default). The build
detects them at runtime — add `"__gearprobe"= sin ( 90 )`, read `Value`, delete — and
`equations(spec, trig)` emits the degree or radian form. `gears/equations.py` holds a ~60-line
evaluator of this grammar (quoted names, `IIF`, `sqr`, `pi`, `^`, both trig modes);
`test_equations.py` evaluates the emitted list in order and asserts every value equals
`derive()` to 1e-9 in both modes. The same evaluator produces numeric substitutions for the
partial-parametric fallback (§3.4).

### 3.3 Ordered operations for one part (mm/degrees in the Op; `swcom` converts to m/rad)

| # | Op | Backing API (UNVERIFIED unless noted) |
|---|---|---|
| i | `NewPart(template)` | `ISldWorks.NewDocument(template, 0, 0, 0)`; default template via `GetDocumentTemplate(1, "", 0,0,0)` or `GetUserPreferenceStringValue` — probe decides; known-good fallback path in Context |
| ii | `AddGlobal(name, expr)` × ~24 | `IModelDoc2.GetEquationMgr` → `IEquationMgr.Add3(-1, text, True, configOpt, configNames)`; −1 return = stop with the offending string |
| — | suppress rebuild | `CommandInProgress = True` (verified), restored in `finally` |
| iii-a | `Axis("Gear Axis")` | select Top + Right (the 2nd and 3rd `RefPlane` in tree order, never English names) → `IFeatureManager.InsertAxis2(True)` → diff names → rename → read back |
| iii-b | `OpenSketch` on the 1st `RefPlane` | `Select2` → `ISketchManager.InsertSketch(True)`; `AddToDB = True`, `DisplayWhenAdded = False` for the duration (no inference snapping) |
| iii-c..e | `Circle("od")`, `Relation(coincident, centre, origin)`, `Dimension("OD")` | `CreateCircleByRadius`; `Select4` + `AddConstraint("sgCOINCIDENT")`; `AddDimension2` → `.Dimension.Name = "OD"` read back |
| iii-f | `CloseSketch("Blank Sketch")` | `InsertSketch(True)` again; capture `ActiveSketch` before; diff → rename |
| iii-g | `Extrude("Blank", depth = Face Width)` | `IFeatureManager.FeatureExtrusion3(…23 args…)` — take the list from a recorded macro; blind end condition |
| iii-h | `LinkDimension("OD@Blank Sketch", "Outer Diameter")`, `LinkDimension(<depth>@Blank, "Face Width")` | `Add3` of `"OD@Blank Sketch"= "Outer Diameter"`; the depth dimension is **found by value** via `GetFirstDisplayDimension/GetNextDisplayDimension`, renamed `Width`, then linked — never assume `D1` |
| iv | tooth-space sketch, Recipe A (§3.4) or B (§3.5) → `CloseSketch("Tooth Space Sketch")` | |
| v | `Cut("Tooth Space", through all)` | `FeatureCut4` (fallback `FeatureCut3`) |
| vi | `CircularPattern("Teeth", axis, cut, count = N)` | axis `Select2(False, 1)`, cut `Select2(True, 4)` → `FeatureCircularPattern5` (fallback `…4`), 360° equal spacing; count dim found by value → renamed `Count` → `"Count@Teeth"= "No. of Teeth"` |
| vii | bore (skipped when bore blank/0) | second sketch on plane 1: `Circle("bore")` → `Dimension("Bore")` → `Cut("Bore")` → `"Bore@Bore Sketch"= "Bore Diameter"` |
| viii | restore flag (`finally`); `Rebuild()` once; verify | `ForceRebuild3(False)` (verified); read back `IEquationMgr.Value(i)` for every global and compare with `derive()` — catches a trig-mode mistake before the user sees it |
| ix | `SaveAs(folder/Gear_m1.5_N25.SLDPRT)` | `IModelDocExtension.SaveAs3(path, 0, 1, null, null, out, out)` (fallback `SaveAs`); refuse if the file exists |

Link equations (iii-h, vi, vii) are added **after** the dimension exists and its owner is
renamed; globals (ii) come before any sketch because Recipe A's curve expressions reference
them at creation. Every set name is read back; a mismatch aborts before the equation that
would reference it (`swlink.py:196-201` idiom).

### 3.4 Recipe A — true involute (`ISketchManager.CreateEquationSpline2`)

Entities, space centred on +X: root arc **R** (centre at origin, radius dim `Root` →
`"Root Diameter" / 2`); flanks **I+**/**I−** as two equation curves (I− has Y negated —
an explicit second curve, not `SketchMirror`); radial lines **L±** from each curve's start
inward (coincident with origin ⇒ radial); explicit root fillet arcs **F±** with `sgTANGENT` +
`sgCOINCIDENT` to L and R and a radius dim `Fillet` → `"Fillet Radius"`; a tip chord **T**
between the curves' end points (beyond the OD, so nothing has to meet the OD edge).
DOF count: 27 unknowns, 27 constraints — fully defined without `CreateFillet` or trimming.

Expressions (degree-mode engine; `t` in radians):
```
X: "Base Radius" * ( cos ( ( t + "Flank Offset" ) * 180 / pi ) + t * sin ( ( t + "Flank Offset" ) * 180 / pi ) )
Y: "Base Radius" * ( sin ( ( t + "Flank Offset" ) * 180 / pi ) - t * cos ( ( t + "Flank Offset" ) * 180 / pi ) )
range: "Involute t1" .. "Involute t2"
```
The involute starts at `Flank Start Diameter = max(db, df + 3ρ)` and a radial line bridges to
the fillet, so one sketch topology serves both the N ≤ 41 (base above root) and N ≥ 42
regimes — a sketch cannot change topology on rebuild. Cost: for 25 ≤ N ≤ 41 the involute
may start ~0.1 mm above the base circle; the "flank start above form diameter" warning
reports if that intrudes on the active flank.

Fallbacks, decided by the probe: expressions refuse global names → numeric substitution
via the evaluator (true involute, but N/m changes no longer move the flanks; the UI says
"Parametric: partial" and a custom property records it); relations refuse curve endpoints →
lock endpoints numerically; curves unusable → Recipe B.

### 3.5 Recipe B — arc approximation (circles, arcs, lines, relations only)

Construction: pitch circle (`Pitch` → `"Pitch Diameter"`), base circle (`Base`), tip-cap circle
(`Cap`), horizontal centreline, radial line to a point **A+** on the pitch circle with an
**angular dimension** `HalfSpace` → `"Half Space Angle"` (replaces the tutorial's arc-length
dimension: same information, a standard two-line `AddDimension2`; if the probe shows the
arc-length dimension works, offer it as the literal-tutorial variant). Profile: root arc R;
flank arc **E+** with centre `sgCOINCIDENT` to the base circle, passing through A+, outer end on
the cap circle, radius `Flank` → `"Flank Arc Radius"`; fillet F+ tangent to E+ and R; E−/F− by
`sgSYMMETRIC` about the centreline; tip chord. Every entity is created at its exact solved
position so the solver keeps the intended branch. No regime problem: an arc continues
inside the base circle harmlessly, valid for every N ≥ 6.

### 3.6 Names the tool sets (and reads back)

`Gear Axis` · `Blank Sketch` / `Blank` (`"OD@Blank Sketch"`, `"Width@Blank"`) ·
`Tooth Space Sketch` / `Tooth Space` (`"Root@…"`, `"Fillet@…"`, `"HalfSpace@…"`, `"Flank@…"`,
`"Pitch@…"`, `"Base@…"`, `"Cap@…"`) · `Teeth` (`"Count@Teeth"`) · `Bore Sketch` / `Bore`.

### 3.7 Assembly for a pair (both parts still open)

| # | Op | API (UNVERIFIED) |
|---|---|---|
| 1 | `NewAssembly(template)` | `NewDocument(asmTemplate, 0,0,0)` |
| 2 | globals `"Centre Distance"= C`, `"Ratio"= i`, `"Mesh Angle"= 0 or 180/N2` | `Add3` |
| 3 | `AddComponent(gear1, origin)`, `AddComponent(gear2, (C, 0, 0))` | `IAssemblyDoc.AddComponent5(path, 0, "", False, "", x, y, z)` |
| 4 | `Fix(gear1)` | `FixComponent` |
| 5 | mate Front@2 ↔ Front@1 coincident | `IAssemblyDoc.AddMate5(type, align, …, _out_long())` — entities via `IComponent2.FeatureByName(...).Select2(append, 1)`, planes by tree order; enum numbers read from the `swconst` type library by the probe, never from memory |
| 6 | mate `Gear Axis`@2 ↔ Top@1 coincident | |
| 7 | mate `Gear Axis`@2 ↔ Right@1 **distance = C** → rename `Centre Distance` → dim found by value → `"D1@Centre Distance"= "Centre Distance"` | the number the user asked for, live in the assembly |
| 8 | mate Top@2 ↔ Top@1 **angle = Mesh Angle** → linked | locks gear 2 so the teeth mesh: parts are built with a *space* on +X, so gear 2 must present a tooth toward gear 1: 0° for odd N2, 180/N2° for even N2 |
| 9 | optional gear mate with ratio N1:N2 (v1.1) | `swMateGEAR` |
| 10 | rebuild once; `SaveAs(Pair_m1.5_20T_60T.SLDASM)` | |

Fallback route if `AddMate5`'s by-ref misbehaves through late binding: `CreateMateData` +
`IFeatureManager.CreateMate`.

### 3.8 `GearKind` seam (`gears/base.py`)

```python
class GearKind(Protocol):
    kind: str; recipes: Mapping[str, Recipe]; default_recipe: str
    def derive(self, spec) -> Derived
    def validate(self, spec, derived) -> List[Diagnostic]
    def variables(self, spec, derived, trig) -> List[GlobalVariable]
    def outline(self, spec, derived) -> List[Point2]
    def plan(self, spec, derived, recipe, template, path) -> BuildPlan
```
`KINDS = {"spur": SpurGear()}`, `PLANNED_KINDS = ("bevel", "helical", "internal")` for greyed UI
options. Ops are a closed set of frozen dataclasses (`NewPart, AddGlobal, LinkDimension, Axis,
OpenSketch, Circle, Arc, Line, Point, EquationCurve, Relation, Dimension, CloseSketch, Extrude,
Cut, CircularPattern, ManualStep, SaveAs, NewAssembly, AddComponent, Fix, Mate`), so `swbuild`
and the fake handle every kind with one code path. `BuildPlan.check()` verifies globals precede
references (via the evaluator), ids are defined before use, exactly one rebuild, `SaveAs` last.
Bevel later: Tredgold virtual tooth count on the back cone, revolved blank, cut-loft — adds
`Revolve`/`Loft` ops and touches nothing in `swbuild`, `store` or `pair`.

---

## 4. App layers

### 4.1 `spec.py`

```python
@dataclass(frozen=True)
class GearSpec:                     # every field as typed ("" ≠ "0"; export.py:10-15)
    kind: str = "spur"; recipe: str = ""          # "" = findings.DEFAULT_RECIPE
    module: str = "1.5"; teeth: str = "25"; pressure_angle: str = "20"
    face_width: str = "10"; bore: str = "10"      # "" = no bore feature
    backlash: str = ""                            # "" = the 0.3×Module equation; typed = literal
    fillet: str = ""                              # "" = the 0.38×Module equation; typed = literal
    profile_shift: str = "0"                      # reserved; must parse to 0 in v1
    name: str = ""                                # "" = default_stem() → "Gear_m1.5_N25"
    # parse methods raising InputError sentences; to_dict/from_dict ignoring unknown keys

@dataclass(frozen=True)
class PairSpec:
    mode: str = "single"; centre_distance: str = ""; ratio: str = ""
    series: str = "1"; min_teeth: str = "17"
    gear_a: GearSpec = GearSpec(); gear_b: GearSpec = GearSpec(); assembly_name: str = ""
```
Plus `sanitize_stem`, `default_stem`, `pair_stems` (`Pinion_…`, `Gear_…`, `Pair_…`). Output
folder and templates are app state (`Recent`), not spec, as `out_folder` is in the template.

### 4.2 `swcom.Session` additions

Keep attach, `call`, typed nulls, `Worker`, `Call`, `active_document`, `features`,
`feature_names`, `rename_feature`, `set_rebuild_suppressed`, `rebuild`. Add a **handle
registry** (`self._handles: Dict[str, Any]`, recipe id → COM pointer, cleared at
`begin_build`/`end_build`) because ops are plain data made on the Tk thread and no COM object
may cross the queue. New members, each taking mm/degrees and returning plain data:
`new_part`, `new_assembly`, `default_template`, `save_as`, `close_document`, `equations`,
`add_global_variable`, `set_global_variable`, `delete_equation`, `link_dimension`,
`detect_trig_units`, `select_plane_by_order`, `insert_axis`, `open_sketch`, `close_sketch`,
`sketch_circle`, `sketch_line`, `sketch_arc`, `sketch_point`, `sketch_equation_curve`,
`add_relation`, `dimension`, `feature_dimensions`, `extrude`, `cut_extrude`,
`circular_pattern`, `add_component`, `fix_component`, `add_mate`, `equation_values`.
Every raise names the feature and its `GetTypeName2` (default `"?"`) and what SolidWorks said.
Exact signatures come from Phase 2; docstring paragraphs record what was observed and on
which version. `python -m gear_generator.swcom [--templates|--equations]` keeps the
diagnostic layout of `swcom.py:960-1037`.

### 4.3 `swbuild.py`

`SolidWorks` Protocol listing exactly the §4.2 members. `build(sw, plan) -> BuildResult`:
version gate; refuse an existing output file; `new_part`; `begin_build`; suppress; run each op
through `_RUNNERS[type(op)]`, **stopping geometry ops at the first failure** (a sketch that did
not close cannot be extruded — unlike independent curves); `finally` restore + `end_build`;
rebuild once even after a stop; `save_as` only with no failures (a half-built part is left open
for inspection). `build_pair` runs `build` twice then the assembly block under its own
suppress/finally/rebuild, skipping the assembly if a part failed. `update_variables(sw, vars,
expected_path)` refuses unless the active document's path matches, sets values in one
suppress block, rebuilds once. `BuildResult`: `done`, `failures`, `stopped_at`, `features` and
`dimensions` (names SolidWorks *kept*), `manual` (counted `ManualStep`s), `log_lines()` in the
`ok`/`FAIL`/`MANUAL` token style.

### 4.4 `store.py`

`<part>.gear.json` beside each part: `GearRecord(record_id, kind, recipe, spec, derived,
variables, features, dimensions, manual_steps, template, partner, assembly, centre_distance,
ratio, created, last_built, last_updated)` inside a `Sidecar(part_path, part_title,
schema_version, written_by)`. Deterministic JSON, schema refusal, move-aside, atomic save —
all from `store.py:142-262`. `recent.json` (`%APPDATA%\Gear Generator` / `~/.config/gear-generator`):
folder, templates, recipe, mode, last ten sidecar paths; never raises.

### 4.5 `gui.py` — panels top to bottom (460 px strip + 360 px flyout, Airfoil idiom)

1. **Gear** — readout `Spur · involute curve`. Kind segmented (Spur; Bevel/Helical/Internal disabled with hint *later*); Recipe segmented `Involute · Arcs`; Mode segmented `Single gear · Gear pair`.
2. **Gear A** — readout `m1.5 · z25 · 20° · PD 37.5 mm`. Fields: Module (with ISO dropdown), Teeth, Pressure angle, Face width, Bore (placeholder *none*), Backlash (placeholder *0.3 × module*, hint that ISO practice is ~0.02–0.05 × m), Fillet (placeholder *0.38 × module*), Name.
3. **Gear B** — identical, `grid_remove`d in single mode.
4. **Derived** — readout `PD 37.5 · OD 40.5 · RD 33.75 · base 35.238 · p 4.712`; a 120×120 `widgets.Outline` gear preview (two at shared scale in pair mode) beside label/value rows; warnings in `theme.ERROR`. Live via `trace_add` debounced 120 ms; a `GeometryError` disables Build.
5. **Pair** — Centre distance, Ratio (hint *3 or 1:3*), Series, Min teeth, **Solve** button + summary; disabled in single mode. Candidates fill the flyout (columns MODULE · TEETH · ERROR, tagged exact/near); choosing a row calls `pair.apply` and fills both gears.
6. **Output** — Folder + Browse, Part template, Assembly template (pair only), **Open .gear.json**.
7. **SolidWorks bar** — dot, headline (no document open is fine here), Candidates button, mode note (*Build will make Gear_m1.5_N25.SLDPRT* / *Update values will change 3 variables in …*).
8. **Footer** — status line, primary **Build**; secondary **Update values** shown only when a loaded sidecar matches the active document.

Tables `GEAR_VARS`, `GEAR_COMPOUND`, `PAIR_VARS`, `PAIR_COMPOUND` with coverage tests; per-side
variable dicts `gear_vars["a"|"b"]`. Build flow mirrors `_export → _export_unsafe → _begin_push
→ _collect_push`: plans are computed on the Tk thread, submitted as one worker job, collected
by `_tick`, sidecars written, `Recent` updated, status set from `ui_text.build_status`.
"Update values" is the v1 modify path: value edits flow through the equations; recipe/kind or
bore 0↔non-zero changes are structural and refused with a sentence ("build it again as a new part").

### 4.6 `ui_text.py`

`gear_readout`, `derived_line`, `derived_rows`, `warning_lines`, `pair_readout`, `candidate_row`,
`solve_summary`, `output_readout`, `link_headline` (adapted), `build_status`, `pair_status`,
`mode_note`, `manual_steps_line`. All tkinter-free, all unit-tested.

---

## 5. Probe phase — verifying the API before the tool depends on it

Principle: **probes call COM members raw on a scratch part; `Session` methods are written
afterwards quoting the probe code that ran.** Nothing the user has open is touched.

### 5.1 Harness (`src/gear_generator/probe/`)

`python -m gear_generator.probe [--only NAME] [--tier N] [--extras] [--keep] [--flank A|B]
[--timeout 120] [--scratch DIR] [--out DIR] [--ledger]`. A `@probe(name, needs=(), members=(),
tier=)` registry; each probe runs as one `Worker` job with a timeout (a modal dialog costs one
probe, not the report); `Px` context gives `ok/fail/check/fact/attempt/require`, `type_name`
(`GetTypeName2` first), `new_features(before)` diff, selection helpers, `put_indexed` (setting
`Equation(i)` needs an indexed property put in late binding), `volume_mm3` via mass properties
as an oracle. `comerr.describe_error` turns `com_error` into `{hresult, name, text, argerror}`
— `argerror` is what settles arity questions. Scratch docs under
`C:\Users\<user>\Documents\GearGeneratorProbe\<stamp>\`; `CloseDoc` only on titles the probe
created; open-document set re-checked at exit (`CLEANUP` + exit 6 on mismatch); flag restored
in `finally`; attach only, never launch. Exit codes reuse `swcom.EXIT_*` (0 all pass, 1 findings,
2–5 as swcom, 6 cleanup failed, 7 hung).

Output: one line per assertion, lowercase ok / UPPERCASE act, version string on every record
for `verified_on`; `probe-results-<stamp>.txt` + `.json` + `latest.json` committed under
`probe/results/`; `decide.py` (pure) maps results → `flank_recipe`, arities, dim names, manual
steps.

### 5.2 Probe list (tiers; `needs` chains skip dependents)

- **0 scaffold**: attach; templates (`GetDocumentTemplate` / `GetUserPreferenceStringValue`, existence, `.prtdot`); `NewDocument` (+ verified `NewPart` fallback); `CloseDoc` without prompt; `ActivateDoc2`.
- **1 flank decision**: `Add3` global (index, `GetCount`, read-back, `Value`, `Delete`; which `configNames` marshalling works); syntax (`pi`, `cos`, `IIF`, bad parse → −1?, unknown name; **measured** trig units); link-before-dimension ordering; `Equation(i)` set + rebuild propagation; sketch open/close (plane by `SelectByID2` or tree walk); entities (`CreateCircleByRadius`, `CreateCircle`, `CreateArc` ±dir, `Create3PointArc`, `CreateLine`/`CreateLine2`, `CreateCenterLine`, `CreatePoint`, `ConstructionGeometry`, endpoints read back in metres); relations (`sgCOINCIDENT`, `sgTANGENT`, `sgSYMMETRIC`, `sgHORIZONTAL2D`, `sgFIXED`, …, checked geometrically); `AddDimension2` on circle / arc / two lines / arc-length → `.Dimension.Name` set, `FullName` read, `SystemValue` units, linked by equation and rebuilt; `GetConstrainedStatus` calibrated; `CreateEquationSpline2` literal (expression units: metres or document mm; `t` radians?), with quoted global names, with global change + rebuild, with a bad expression.
  **Decision:** A iff literal + globals + rebuild pass; else B iff entities + relations + dimension-link pass; else STOP (no guessed workaround).
- **2 solid**: `FeatureExtrusion3` (arity from a recorded macro; volume oracle; depth dim found by value; linked to `Face Width`); `FeatureCut4`/`3`; `InsertAxis2`; `FeatureCircularPattern5`/`4` with axis mark 1 / feature mark 4 (which dim is the count); pattern count linked to a global; batching under `CommandInProgress`; `FeatureFillet3` (extra).
- **3 files**: `GetPathName`; `SaveAs3` (both interfaces' arities, out-param shape, silent option; UNC target as a guarded extra); custom properties (nice to have).
- **4 assembly**: `NewDocument(asm)`; `AddComponent5` (part open vs closed; `Name2` pattern); `AddMate5` coincident / distance / angle (or `CreateMateData` route), enum values via `swconst` gencache; distance mate dim found and linked to an assembly global; gear mate (extra).
- **5 end-to-end**: 12-tooth m 2 mini gear with the decided recipe: feature list, fully-defined sketches, volume between root and OD cylinders, then `Teeth` 12→13 and `Module` 2→2.5 + rebuild → count 13, OD 33.75, volume changed; `SaveAs3`.

### 5.3 WSL ↔ Windows round trip

Repo stays on ext4; Windows sees it as `\\wsl.localhost\Ubuntu\home\m0obot\Gear-Generator`.
`probe.bat` (`pushd "%~dp0"` maps the UNC path; `python "%~dp0probe.py" --out "%~dp0probe\results" %*`);
`probe.sh` runs the same via `python.exe "$(wslpath -w …)"` with CRs stripped, so a WSL-side
agent can run it in one command. Every path handed to SolidWorks (templates, SaveAs,
AddComponent) is under `C:\`; results are written back through the UNC path (plain file I/O).

### 5.4 How findings reach the tool

`src/gear_generator/findings.py` — hand-updated constants (`DEFAULT_RECIPE`, `EXTRUDE_CALL`,
`CUT_CALL`, `PATTERN_CALL`, `PATTERN_COUNT_DIM_INDEX`, `PLANE_SELECT_ROUTE`, `TRIG_DEFAULT`,
`SAVE_AS_CALL`, `MATE_CALL`, mate enum numbers) each with a comment naming the probe result
and version. `tests/test_findings.py` asserts they agree with `probe/results/latest.json`
through `decide.py`, so the constants cannot drift from the evidence. Not runtime JSON: the exe
must behave identically for someone who never ran the probe.

### 5.5 Writing back to SW-Macro-Database (its own commit, per CONTRIBUTING's ten rules)

New entries (one question each): `documents/01-new-part-from-template`,
`documents/02-save-as-and-close`, `equations/01-global-variables-from-code`,
`equations/02-link-a-dimension-to-a-global`, `sketches/07-equation-driven-curve`,
`sketches/08-sketch-fillet` and `09-sketch-mirror` (only if probed), `sketches/10-is-the-sketch-fully-defined`,
`features/01-boss-extrude`, `features/02-cut-extrude`, `features/03-circular-pattern`,
`features/04-read-a-features-dimensions`, `assemblies/01-new-assembly-and-insert-components`,
`assemblies/02-mates-from-code`, `reading/08-mass-properties-as-an-oracle`,
`connect/11-probe-an-api-member-on-a-live-session`. Status flips: `sketches/01` → partly-verified,
`sketches/03` → verified for exercised constants, `sketches/04` → verified. Extend `connect/02`
(indexed property put; which exception a missing member raises) and `connect/10` (Windows
Python from WSL against an ext4 checkout). New API-LEDGER rows (generated by `--ledger`),
GOTCHAS candidates only where confirmed (equation units, curve expression units, out-param
tuples, `Equation(i)` put, UNC save target, count dim not `D1`), README/INDEX tables,
See-also links both ways, probe harness + `p_*.py` + results JSON under `code/`, then
`python3 tools/build_manifest.py` and commit `manifest.json`. Failures are recorded as
findings, never dropped.

### 5.6 Always-manual steps (counted in every build log, per `sketches/06`)

Material assignment (1 per part); visual mesh check in the assembly (1 per pair); plus any
step a negative probe turns into a `ManualStep` (e.g. "link `Count@Teeth` in Equations",
"add three mates"), emitted by `decide.py` and pinned per recipe by a test.

---

## 6. Testing

Linux, `pytest` with `pythonpath = ["src"]`; this box needs a venv:
```
cd /home/m0obot/Gear-Generator && python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]" && python -m pytest
```
(`sudo apt install python3-tk` only to run the GUI on Linux; no test needs it.)

| File | Pins |
|---|---|
| `test_spec.py` | dict round trip; `"1.5"` stays text; `""` ≠ `"0"`; every parse refusal names the field; ratio parsing; stems |
| `test_gears_spur.py` | the §2.1 values; undercut flag edges; outline closed/CCW/2N pitch crossings; both recipes' plans pass `check()`; the user's ten variables present verbatim and in order before any reference; manual-step count per recipe |
| `test_equations.py` | evaluator vs `derive()` in both trig modes; `fmt9` (9 decimals, no `-0`, refuses non-finite) |
| `test_gears_pair.py` | §2.2 cases; ranking; `"1:3"` direction; `apply` touches only module/teeth |
| `test_standards.py` | series sorted; nearest module |
| `test_swbuild.py` | `FakeSolidWorks` recording calls: suppress before first op; exactly one rebuild, before save; flag restored when an op raises; build stops at the failing op with its name and SolidWorks' text; no `SaveAs` after a failure; globals before links; kept names are the reported names; `update_variables` refuses the wrong document; `build_pair` skips the assembly on a part failure |
| `test_swcom.py` | the pure helpers, copied |
| `test_store.py` | sidecar and recent round trips, deterministic bytes, schema refusal, move-aside |
| `test_ui_text.py` | every readout |
| `test_gui_spec.py` | table coverage and the `_pending*` guard, **parsing `gui.py` by path with `ast`** so it runs without tkinter |
| `test_probe_harness.py`, `test_probe_decide.py`, `test_findings.py` | registry order and skip cascade with fake probes; decisions from canned results; constants agree with `latest.json` |

---

## 7. Phases

| Phase | Deliverable | Demonstrable | Size |
|---|---|---|---|
| **0 scaffold** | repo, pyproject, main.py, build.bat, .gitignore, theme/widgets/fonts copied, swcom copied and cut, empty `gears/`, README headings, venv | `python -m pytest` green on copied tests; `python -m gear_generator.swcom` says pywin32 is unavailable on Linux | S |
| **1 maths + form** | `gears/*`, `spec.py`, `ui_text.py`, `store.py`, `gui.py` with all panels and live derivation, `python -m gear_generator.gears` dry-run printer of a plan's op log | GUI on Linux: type m1.5 z25 → derived values, warnings, outline; pair mode: Solve 60 mm 1:3 → candidates → pick → both gears filled; dry run prints the op list; all Phase-1 tests green | L |
| **2 probe** | `probe/` package, `probe.bat`/`probe.sh`, run against SolidWorks 2026 (needs SolidWorks **open on the Windows host**; runnable from WSL via `./probe.sh` through `python.exe`, no user documents touched), results committed, `findings.py` filled, `Session` members written from the probe code, SW-Macro-Database entries + manifest | `probe.sh` prints the report; `decide` names the flank recipe; `--ledger` table pasted into the DB; DB manifest builds | L (can run alongside Phase 1) |
| **3 single gear** | `swbuild.py` + fake tests; gui build flow; sidecar; Recent; Open .gear.json; Update values | Windows: Build → new part rebuilt and saved, globals in the Equation Manager, every dimension linked; change `"No. of Teeth"` in SolidWorks → gear rebuilds; Update values from the tool → pattern follows | L |
| **4 pair + assembly** | `build_pair`, assembly ops and mates, mesh angle, pair sidecar fields, candidate flyout wired to Build | Solve → choose → Build → two parts + assembly mated at C, distance driven by `"Centre Distance"` | M |
| **5 ship** | README, UI-DESIGN "as built", exe via build.bat, tag v0.1 | `dist\Gear Generator v0.1.exe` runs beside SolidWorks | S |

Commits as prose with the why, ending with the `Co-Authored-By` / `Claude-Session` lines.

---

## 8. Verification (end-to-end)

1. **Linux:** `python -m pytest` green; `python -m gear_generator.gears --spec m=1.5,z=25 --recipe A` prints the ordered op log with the 24 globals first and `MANUAL` lines counted; GUI (`python3-tk`) shows derived values matching the pinned table and the outline.
2. **Probe on Windows:** `./probe.sh` exits 0 or 1 with `decide flank_recipe = A|B`; `probe/results/latest.json` committed; `test_findings.py` green; SW-Macro-Database `python3 tools/build_manifest.py` succeeds.
3. **Single gear on Windows:** run the exe (or `python main.py`) beside SolidWorks 2026 → Build m 1.5 / z 25 / bore 10 → the part opens with Equation Manager showing the user's ten variables verbatim; sketches fully defined; measure OD = 40.5 mm, root = 33.75 mm; edit `"No. of Teeth"` to 40 in SolidWorks → 40 teeth, OD 63 mm, no rebuild errors; `.gear.json` beside the part.
4. **Pair:** C 60, ratio 3 → choose m 1.5 20/60 → two parts and `Pair_m1.5_20T_60T.SLDASM`; the distance mate reads 60; change `"Centre Distance"` → the component moves; teeth visibly mesh (the counted manual check).
5. **Regression guard:** every `verified` entry written to the DB quotes what was observed and the version string from the probe output.

## 9. Risks and open items

- The whole parametric approach rests on `IEquationMgr.Add3` and `AddDimension2`+`FullName`
  behaving as believed; the probe's tier 1 settles that first and the plan says STOP rather
  than improvise if they do not.
- `CreateEquationSpline2` expression units and global-name support decide Recipe A; Recipe B
  is the safety net and is itself only circles/arcs/lines/relations.
- Late-bound arities of `FeatureExtrusion3` / `FeatureCut4` / `FeatureCircularPattern5` /
  `AddMate5` are taken from recorded macros and `argerror`, never from memory.
- Plane names are locale-dependent: the tool selects planes by tree order, not by "Front Plane".
- Profile shift, helical/bevel/internal kinds, gear mate, custom-property stamping: reserved,
  seams in place, not built in v1.
