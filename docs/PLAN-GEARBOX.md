# Gear Generator — the gearbox planner

Carry this out the way `docs/PLAN.md`, `PLAN-HELICAL.md` and `PLAN-BEVEL-INTERNAL.md` were carried out. Read PLAN.md's "For the executing agent" section first. Its conventions, the rule that every API call is probed before the tool relies on it, and the stop-and-ask triggers all apply. UNVERIFIED means the probe settles it; never guess a call. **The first commit is this plan, saved as `docs/PLAN-GEARBOX.md`.**

## Context

The app today builds a single gear, or a two-gear pair with an assembly. The gear kinds are spur, helical, herringbone, internal (ring), bevel and crossed-helical. The user wants a **gearbox planner**: design a whole multi-shaft gear train, then have the existing build code make every gear and one assembly in SolidWorks.

What we have to work with, from the survey:

- **Reusable as it is.** The single-mesh solver is pure: `pair.solve`, `Candidate`, `describe`, `bevel_candidate`. So is each kind's `derive`, `validate` and `plan` in `gears/*.py`. `BuildPlan.check()` has no limit on the number of components. `swcom`'s handle registry is keyed by id. `Place` with any rotation is verified: Transform2, columns.
- **Fixed at two gears.**
  - `PairSpec` has exactly `gear_a` and `gear_b`.
  - `pair.assembly_plan`, `crossed_assembly_plan` and `bevel_assembly_plan` hard-code the ids `gear1` and `gear2`, and use single global names such as `"Centre Distance"`.
  - `swbuild.build_pair` and `PairResult` have three slots.
  - `GearRecord.partner` holds one path.
  - `pair.apply` overwrites both gears.
- **Verified mates are coincident (0), distance (5) and angle (6) only.** Gear mates, concentric mates and axis-to-axis coincident mates have never been probed. Nothing has been probed with more than two components, or mated to a component that is not fixed.

### Decisions made with the user (2026-09-29)

| Question | Decision |
|---|---|
| Workflow | **Solve, then edit.** Give a target ratio and the planner suggests trains. You then edit shafts, gears and meshes by hand, with every value checked live. |
| Scope | Parallel-shaft compound reducer, idlers and reversing, right-angle stages (bevel or crossed), planetary. **Built in that order.** |
| SolidWorks output | **Gears plus shaft axes.** No shaft, bearing or housing parts. |
| Load | **Speed and torque shown per shaft.** No strength check. |
| Home | **A separate Gearbox window in the same app.** It saves `.gearbox.json` and builds through `swbuild`. The 460 px strip is left alone. |
| Editing | **Tables plus a live drawing** (end view and side view). Nothing is dragged. |
| Shaft layout | **One direction angle per mesh**, default 0° (all shafts in a line), plus a **coaxial output** option that solves a reverted train. |
| Motion | **Gear mates.** Drag the input in SolidWorks and the whole train turns at the right ratios. |
| Compound shaft | **Two parts on one shaft axis**, locked together. There is no cluster-gear part. |
| Solve input | **Total ratio, stage count, ratio tolerance, module/series, teeth min/max**, plus the direction of the output relative to the input. |

Judgement calls (change at review if wrong):
- A fixed **layout part** (`<Box>_Layout.SLDPRT`) is the skeleton. It holds a sketch with one point per shaft, construction lines whose lengths are linked to the centre-distance globals and whose angles are linked to the mesh-angle globals, and a reference axis `Shaft N Axis` through each point. Every gear is mated to its shaft axis. This is standard top-down practice, and it gives the "shaft axes" the user asked for as real features. The alternative, chaining each gear off the previous gear, would stack every error along the train.
- Every gear is its **own parametric part**, built by the existing `KINDS[kind].plan`, so every gear keeps its Equation Manager globals. The gearbox's own globals are split: the layout (centre distances, mesh angles) lives in the layout part, and axial positions live in the assembly.
- **Efficiency per mesh defaults to 98 %.** This is general knowledge, not something in the repo (a typical spur or helical mesh is 97–99 %). It can be edited, and 100 % gives ideal values.
- **Output direction** takes `either`, `same` or `opposite`. When the parity of the stage count is wrong, the solver adds one idler on the last stage. The idler has min-teeth teeth, and its mesh angle is chosen so it does not clash with other gears.
- The train must be a **tree** in v1: every gear is reached from the input by exactly one path. A second path to a gear is a loop, which is refused until the planetary phase.
- **If the gear-mate probe fails, STOP and ask.** Do not quietly fall back to a static assembly. A static assembly uses only verified mates and is the obvious fallback, but it is the user's call.

---

## 1. Data model: `src/gear_generator/gearbox/spec.py`

> **Superseded (2026-11-11).** The planner's data model is now the workbook's `GearboxSpec`
> (`src/gear_generator/workbook/model.py`, `docs/PLAN-WORKBOOK.md` §1 and §3.2): shafts placed by X, Y, Z and an
> axis from one origin, gears on shafts, meshes listed, modes. The planner's Solve fills one, and the workbook's
> checks, speeds and build take it from there (PLAN-WORKBOOK, end of §6). The model below is kept as the record
> of the first plan; where the two differ, PLAN-WORKBOOK holds.

Everything is typed text and frozen, in the style of `spec.py`: `""` is not `"0"`, and `to_dict` / `from_dict` drop unknown keys.

```python
Shaft(id="S1", label="Input", speed="", torque="")    # speed/torque typed on the input shaft only
Gear(id="G1", shaft="S1", z="", gear=GearSpec(...))    # z = axial position of the face-width centre, mm; "" = auto
Mesh(driver="G1", driven="G2", angle="0", mesh="external", efficiency="")  # angle: direction S(driver)→S(driven), deg
Lock(a="G2", b="G3")                                    # gears on the same shaft that turn together (compound)
GearboxSpec(name, kind="spur", recipe="", pressure_angle="20", shafts, gears, meshes,
            solve=SolveSpec(ratio, stages="2", tolerance="0.5", module="", series="1",
                            min_teeth="17", max_teeth="120", output="either", coaxial=False))
```

- Two gears in a mesh share module, pressure angle and kind. `validate` refuses any mismatch, and the solver and the table edits keep them in step.
- A lock is implied by two gears on one shaft. `Lock` is kept explicit so that a free (idler) gear on a dead shaft stays possible later.

## 2. Maths: `gearbox/train.py` (pure, tested on Linux)

`derive(spec) -> TrainDerived`:
- **Shaft positions.** Walk the meshes breadth-first from the input shaft. Each shaft's position is its parent's position plus C·(cos θ, sin θ), where C is the centre distance from `pair.describe` (internal meshes subtract).
- **Speed, torque and direction per shaft.** Speed is n·z_driver/z_driven. Direction flips on an external mesh and is kept on an internal mesh. Torque is T·i·η.
- **Per mesh:** C, ratio, contact ratio, and pitch-line speed.
- **Overall:** the overall ratio and error, and the envelope as a bounding box of every tip circle in the end view plus the axial length.
- **Default axial positions.** Stage k's mesh plane goes at the sum of the previous face widths plus a 2 mm gap each. A gear with `z` typed keeps its value.

`validate(spec, derived) -> List[Diagnostic]`: each gear's own `validate`, plus these gearbox-level checks:

- **Errors:**
  - a mesh whose gears don't match;
  - a meshing pair whose face widths don't overlap axially;
  - two gears that don't mesh, sit on different shafts, overlap axially, and whose tip circles come closer than 0.5·m;
  - a shaft reached twice (a loop);
  - a gear on no shaft.
- **Warnings:**
  - a gear whose tip circle covers another shaft's axis within its axial range, since a real shaft there would be cut;
  - undercut, from the existing check;
  - a coaxial train whose output gear and input gear overlap axially.

`mesh_phase(phi_driver, n_driver, n_driven, theta, internal) -> phi_driven`. Every part is built with a tooth *space* centred on +X, so this works out the rotation that makes the driven gear present a tooth at the pitch point along direction θ. The traversal carries each gear's phase down the tree, and compound gears on one shaft each get an independent phase. **Pinned:** with θ = 0 and φ = 0 it reproduces `pair.mesh_angle` / `internal_mesh_angle`. The outlines, rotated and placed, must not intersect (a polygon test using `spur.outline`) for random θ, N and idlers.

`gearbox/solve.py`, `solve(SolveSpec, kind, pressure_angle) -> List[TrainCandidate]`:
- For n stages, the ideal split is i^(1/n) each.
- Stage ratios are searched within ±40 % of that split, using each stage's rational approximations with z ∈ [min, max].
- The last stage takes the ratio that remains, found by a best-rational (Stern–Brocot) search that respects the teeth bounds.
- Modules come from `standards` (typed, or every standard module in the series).
- **Coaxial:** only candidates with m1(z1+z2) = m2(z3+z4) survive. With one module, that is z1+z2 = z3+z4.
- **Output direction:** when the parity is wrong, add an idler.
- **Ranking:** ratio outside tolerance, then non-standard module, then undercut, then ratio error, then envelope area, then total teeth. The first 120 are kept.

**Pinned cases:**
- ratio 12, two stages, m 1.5, series 1 → the exact trains ranked by envelope;
- ratio 10, two stages, coaxial → every row satisfies z1+z2 = z3+z4;
- ratio 5, one stage, output `same` → one idler added.

`gearbox/__main__.py` is a dry-run printer, like `gears/__main__.py`. It prints the shafts, speeds, torques and meshes, then every plan's op log.

## 3. SolidWorks plans: `gearbox/build.py`

- **`part_plans(spec, derived, folder, template)`**: one `BuildPlan` per gear, through `KINDS[kind].plan`. Stems look like `<Box>_S2_G3_m1.5_N60`, sanitised with `spec.sanitize_stem`.
- **`layout_plan(...)`**, run as a new part:
  1. Globals, in order: `"C S1-S2"`, `"Angle S1-S2"`, and so on.
  2. One sketch on plane 1 holding a point per shaft, one construction line per mesh, a length dimension linked to C and an angle dimension linked to θ. The first point is coincident with the origin, and the first line's angle is measured from the horizontal.
  3. `Shaft N Axis` for each point: point plus plane 1 through `InsertAxis2`. **UNVERIFIED.**
  4. `SaveAs`.
- **`assembly_plan(...)`**, run as a new assembly:
  1. Add the layout part and `Fix` it.
  2. Add each gear, then `Place` it at its shaft position, its z, and its `mesh_phase` rotation.
  3. **Axis mate:** gear `Gear Axis` coincident with layout `Shaft N Axis`. **UNVERIFIED** as axis to axis; the concentric mate is the fallback.
  4. **Axial mate:** distance from gear plane1 to layout plane1, linked to assembly global `"Z G3"`.
  5. **Compound lock:** angle mate between the two gears' plane2, at their placed phase difference. This is angle mate 6, but has never been tried between two components that are both free.
  6. **Gear mate per mesh:** ratio z_driver:z_driven, reversed for an internal mesh. **UNVERIFIED**, including the enum number, which is read from swconst the same way `MATE_*` were.
  7. The input gear is left free to rotate. That free rotation is the one degree of freedom, which is what the motion decision needs.
  8. One rebuild, then `interference_count` reported as a CHECK, then `SaveAs`.
- `swbuild.build_many(sw, parts, layout, assembly) -> TrainResult` generalises `build_pair`:
  - check every path up front;
  - build the parts in order and stop at the first failure;
  - skip the assembly when any part failed.

  **`build_pair` stays as it is.** It is not rebuilt on the new function, so the pair path is not put at risk.
- **Records:**
  - `<Box>.gearbox.json` goes beside the assembly. It holds the `GearboxSpec`, a derived summary, and every part's path.
  - `GearRecord` gains an optional `gearbox` path, and its `partner` stays empty for gears in a gearbox.
  - `store.py` gets a `GearboxRecord` built with the same machinery: deterministic JSON, schema refusal, atomic save.

## 4. Probe tier 6: `probe/p6_gearbox.py`

Run on scratch documents only, as the other tiers are. Results go into `probe/results/`, then `findings.py`, then `decide.py`, and `test_findings.py` pins them.

1. Layout part: points, construction lines, length and angle dimensions linked to globals; change a global, rebuild, and the points move. This needs verified ops only, so it is a sanity check.
2. `InsertAxis2` from a sketch point plus a plane. Read the axis direction back.
3. Assembly with 5 or more components: axis-to-axis coincident mate, with concentric as the alternative; a distance mate between two components that are not fixed.
4. **Gear mate:**
   - enum from swconst;
   - `AddMate5`'s ratio arguments (numerator, denominator, reverse);
   - what can be selected: axes, cylindrical faces, or edges;
   - **the oracle:** drive the input with a temporary angle mate at +10°, rebuild, then read the driven component's `Transform2` rotation. It must equal −10·z1/z2 to 1e-6, and have the opposite sign for internal.
5. An angle-mate lock between two free components that are also gear-mated: does the assembly over-define?
6. Interference with gear mates present, at the placed phases: expect 0.

**Decision:** gear mate plus axis mate pass → motion route. Otherwise **STOP and ask** (a static route is possible).

## 5. The Gearbox window: `gearbox_gui.py` (+ `ui_text`, `preview`)

It is opened from a **Gearbox…** button in the strip's Gear panel header. It is a separate `Toplevel` and shares theme, widgets and the SolidWorks worker. Build requests go through the worker's single job queue, so only one SolidWorks job runs at a time.

- **Left column, about 380 px:**
  - **Solve** panel: ratio, stages, tolerance, output direction, coaxial, kind, pressure angle, module/series, teeth min–max, **Solve** button.
  - Candidate list below it, with columns `STAGES · TEETH · RATIO · ERROR · ENVELOPE`. Clicking a row fills the tables.
- **Centre, tables:**
  - **Shafts:** input speed and torque are typed on S1. Every other shaft's speed, torque and direction is derived.
  - **Gears:** shaft, teeth, module, face width, bore, z, and a *more…* link that opens that gear's full `GearSpec` fields for backlash, fillet, flank and name.
  - **Meshes:** driver, driven, angle, internal, efficiency. The derived C, i and ε are shown read-only.
  - Buttons: **Add stage**, **Add idler**, **Remove**.
- **Right, drawing:**
  - **End view:** every outline at its phase, dashed pitch circles, shaft crosses labelled S1…, and the centre distances dimensioned.
  - **Side view:** each gear as a rectangle (face width × tip diameter) at its z, with the shaft axes.
  - Both are laid out by `preview.layout_gearbox` with no tkinter, so they can be tested headless.
- **Footer:** errors and warnings; Output (folder, part/assembly templates); **Save .gearbox.json**, **Open…**, **Build**.
- The debounce is 120 ms, the same as the strip. Any error disables Build.
- `design/UI-DESIGN.md` gets a §9 for this window, drawn first as an artboard in `design/canvas/` (`gen.py`), as the strip was.

## 6. Phases

| Phase | Deliverable | Demonstrable |
|---|---|---|
| **G0** | `docs/PLAN-GEARBOX.md` committed | — |
| **G1 maths** | `gearbox/{spec,train,solve,__main__}.py` + tests | `python -m gear_generator.gearbox --ratio 12 --stages 2` prints ranked trains and one op log. The `mesh_phase` polygon test is green. |
| **G2 window** | `gearbox_gui.py`, `preview.layout_gearbox`, `ui_text` readouts, `.gearbox.json` save/load | On Mac/Linux: Solve 12:1 → pick a row → the tables and both views fill; add an idler → the output direction flips; mistyped values disable Build. Screenshots checked by eye. |
| **G3 probe** | `p6_gearbox.py`, results committed, `findings.py`, `Session` members (`add_mate` gains `gear`/`concentric`), probe scaffolding for axes | `probe.bat --tier 6` on Windows; `decide` names the route |
| **G4 build** | `gearbox/build.py`, `swbuild.build_many`, records, window Build flow | Windows: a 2-stage reducer plus idler → N parts, the layout part and the assembly. Dragging the input turns the train; the output speed matches the table; interference is 0. Changing `"C S1-S2"` in the layout part moves shaft 2. |
| **G5 right-angle** | Shafts get a direction; bevel and crossed meshes in a train; the layout gets a second sketch plane or a 3D sketch; `mesh_phase` for Σ ≠ 0 | A bevel input stage feeding a parallel stage builds and turns |
| **G6 planetary** | A planetary stage: the carrier as a shaft, assembly condition (z_s+z_r)/n integer, the neighbour clearance, Willis ratios, planets as a pattern, and the loop allowed only inside a planetary block | A 4:1 single planetary builds and turns with the ring fixed |

G5 and G6 each get their own short sub-plan and questions at the time. Their data-model hooks go in during G1: `Shaft.direction`, and a `Mesh.kind` that is not limited to spur and helical.

## 7. Verification

- **Linux/Mac:** `.venv/bin/python -m pytest` green, including new `tests/test_gearbox_{spec,train,solve,build,store,ui_text,preview}.py`:
  - `BuildPlan.check()` passes on every plan;
  - the ids of a 6-gear box are unique;
  - `build_many` against `FakeSolidWorks` stops at the first failure and skips the assembly.
- The dry-run printer's shaft speeds agree with a hand calculation for the pinned 12:1 case. The answer key is checked by an independent subagent, as the workspace rule on answer keys requires.
- Window: launch it, drive Solve and the edits, and **look at the screenshots** (outlines meshing, labels readable, nothing clipped).
- Windows: the probe tier 6 report, then a G4 build. In SolidWorks, rotate the input 360° and read the output rotation (motion study or drag); check `.gearbox.json` round-trips through **Open…**.

## Critical files

- **New:**
  - `src/gear_generator/gearbox/{__init__,spec,train,solve,build,__main__}.py`
  - `src/gear_generator/gearbox_gui.py`
  - `src/gear_generator/probe/p6_gearbox.py`
  - `docs/PLAN-GEARBOX.md`
- **Changed:**
  - `swbuild.py`: `build_many`, `TrainResult`
  - `swcom.py`: `add_mate` kinds, axis-from-point
  - `findings.py` and `probe/decide.py`
  - `store.py`: `GearboxRecord`, and `GearRecord.gearbox`
  - `preview.py`: `layout_gearbox`
  - `ui_text.py`
  - `gui.py`: the **Gearbox…** button
  - `design/UI-DESIGN.md`, `README.md`
- **Reused unchanged:**
  - `pair.solve` / `describe` / `mesh_angle` / `internal_mesh_angle`
  - `KINDS[kind].derive` / `validate` / `plan`
  - `BuildPlan.check`, the ops in `gears/base.py`
  - `swcom.place_component` / `add_component` / `fix_component` / `interference_count`
  - `standards`, `spec.sanitize_stem`
