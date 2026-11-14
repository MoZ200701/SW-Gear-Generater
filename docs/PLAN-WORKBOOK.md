# Gear Generator — the gearbox workbook (import, export, live link)

Carry this out the way `docs/PLAN.md`, `PLAN-HELICAL.md` and `PLAN-BEVEL-INTERNAL.md` were carried out. Read
PLAN.md's "For the executing agent" section first: its conventions, the rule that every SolidWorks call is probed
before the tool relies on it, and its stop-and-ask triggers all apply here. UNVERIFIED means a probe settles it;
never guess a call. **The first commit is this plan.**

## Context

`docs/PLAN-GEARBOX.md` plans a gearbox *planner*: solve a train from a target ratio, edit it, build it. Working it
through with the user (2026-11-11) split it in two:

- **The workbook** (this plan): a gearbox that is already fully specified — every gear, every shaft position from
  one origin the user chooses, which gears mesh — written in an `.xlsx` workbook, imported, checked, and built.
- **The planner** (PLAN-GEARBOX, later): works out the gears from a target ratio and hands the result to the same
  check and build. It becomes a second way to fill the same data.

The data model, the checks, the speeds and torques and the SolidWorks build are shared, so this plan builds them
first, behind the simplest front end: a file reader. The planner then adds only a solver and an editor on top.

The exact workbook format was settled with the user on the design canvas
(<https://claude.ai/artifact/XQ4UL6FgR1BH6a15g1ArJj>, section **F**, boards F1–F5). §1 below is that format in
words; where the two differ, the canvas is what the user approved — raise it rather than choosing.

### Decisions made with the user (2026-11-11)

| Question | Decision |
|---|---|
| Order | **Workbook import first**, then the planner on top of it. |
| Format | **`.xlsx`**: sheets Box · Shafts · Gears · Meshes · Modes · Results (canvas F). A **separate Shafts sheet**; gears name their shaft. |
| Scope of the format | **One format for every gearbox type** — parallel, idlers, right-angle, planetary, sleeves and modes. There is no type cell: the app works out the type. Rows a later phase builds are read, checked, and refused at Build with the phase that builds them. |
| Origin | The workbook's (0, 0, 0) is the **origin of the layout part and of the assembly**. X and Y lie in the Front plane; +Z points out of it. |
| Round trip | The workbook sits **alongside** the app: import a workbook written or edited in Excel, and **export** to `.xlsx`. |
| Live link | After import the app **stays linked to the file**: a save in Excel is re-read and re-checked automatically. |
| SolidWorks on a live edit | **Only on Update SolidWorks.** The file is re-read on every save; SolidWorks is never changed without a press. |
| Writing the user's file | **Only on Export**, only the cells named, **never over a formula**; everything else in the workbook stays as it was. |
| Assembly before gear mates | **A static assembly is fine** until the `gear_mate` probe has passed: gears placed meshed, not turning. |
| Where it lives | An **Import workbook…** button in the strip's Gear panel header, opening a **Workbook** window. |

Judgement calls (change at review if wrong):

- **No runtime dependency.** PLAN.md's convention is a stdlib-only app. `.xlsx` is a zip of XML parts, so it is
  read and written with `zipfile` and `xml.etree`. This is also what makes "change only the named cells" possible:
  the writer rewrites one sheet part's cells and copies every other zip entry byte for byte. openpyxl would
  rewrite the whole workbook and drop what it does not model.
- **Formulas are read as the value Excel last saved** (`<v>` beside `<f>`). A formula cell with no saved value
  (a file written by a tool that does not calculate) is an error naming the cell, never a guess.
- **Meshes are listed, never inferred.** Two gears that sit at mesh distance with overlapping faces but are not
  listed get a warning.
- **Identical gears share one part file**: rows with equal specs and the same part name build one `.SLDPRT`,
  inserted as often as it appears. Planet copies rely on this.
- **W1–W3 need no SolidWorks probe; W4 does.** Batch parts (W2) run the strip's own verified plans. The layout part
  and the static assembly (W4) look close to verified ops but are not: `ref_plane_offset` was probed from the Front
  plane only, `Axis` selects planes by tree order (`swcom.insert_axis`), and nothing has been probed with more than
  two components, opening a document by path, or finding a component in a reopened assembly. So W4 opens with a
  small probe tier (§4.2). Mating gears to the layout's axes, and gear mates, wait for theirs (W5).
- **New workbook…** writes a blank template from the schema and opens it — added here, not asked for; drop it at
  review if unwanted.
- The axis words are **`Z+ Z- X+ X- Y+ Y-`**, not canvas F's `+Z −Z …`: a cell typed `+Z` or `-Z` is a formula to
  Excel and reads `#NAME?`. `+Z`, `−Z` (U+2212) and `-Z` are still accepted when they arrive as text, and a
  `#NAME?` in the Axis column says why.

---

## 1. The format (canvas F, in words)

**Every sheet.** Row 1 is the header; each row below is one item. Headers are matched by name, case-insensitively,
ignoring a trailing `(unit)`, so columns may be in any order. A blank cell takes the app's default — the same
default the strip's blank field takes. Columns the app does not know are kept and ignored. A row whose first cell
starts with `#` is a comment; blank rows are skipped. Names in the Shaft and Gear columns are unique, of letters,
digits, `_` and `-`. Units are fixed: mm, degrees, rpm, N·m.

**Box** — two columns, *Setting* and *Value* (a third, *Notes*, is the user's). Settings: `Format` (1),
`Name` (needed), `Output folder` (blank: the strip's), `Part template`, `Assembly template` (blank: SolidWorks'
default), `Pressure angle (°)` (20), `Efficiency per mesh (%)` (98), `Units` (written for the reader, ignored).

**Shafts** — one row per body that turns as one piece.

| Column | Blank means | Meaning |
|---|---|---|
| Shaft | needed | Unique name. Its axis in SolidWorks is `"<name> Axis"`. |
| Mounted on | `frame` | `frame`, or another shaft it rides round with (a planet on its carrier); X Y Z are then measured on that shaft at its starting turn. |
| X (mm), Y (mm) | needed | A point on the axis, from the origin. |
| Z (mm) | 0 | |
| Axis | `Z+` | `Z+ Z- X+ X- Y+ Y-` (see the judgement call above), or three numbers `dx, dy, dz`, kept as typed and normalised where they are used (W6). |
| Role | turns as the gears make it | `input`, `output`, `fixed`. At least one input. |
| Copies | 1 | Only on a shaft mounted on another: that many, evenly round it. |
| Speed (rpm), Torque (N·m) | — | Input rows only. Positive speed turns anticlockwise seen from the tip of Axis looking back (right-hand rule). |
| Notes | — | The user's. |

**Gears** — one row per gear, fixed to its shaft. Columns in canvas order: `Gear`, `Shaft`, `At (mm)`, `Kind`,
`Side`, `Teeth`, `Module (mm)`, `Pressure angle (°)`, `Face width (mm)`, `Bore (mm)`, `Flank`, `Helix angle (°)`,
`Hand`, `Groove (mm)`, `Profile shift (× m)`, `Backlash (mm)`, `Fillet (mm)`, `Rim (mm)`, `Slides`, `Part name`,
`Notes`. Needed: Gear, Shaft, Teeth, Module, Face width; Helix angle on the helical kinds.

- `At` is the distance along the shaft's Axis from its X Y Z point to the middle of the face — to the **cone tip**
  for a bevel gear (the canvas flags this as to be confirmed).
- `Kind` (blank: `spur`): `spur helical herringbone bevel sleeve dog`; `double` reads as herringbone. `Side`
  (blank: `external`): `external internal` (`ext`, `int`). `Hand` (blank: `right`): `right left` (`R`, `L`).
  `Flank` (blank: involute): `involute arcs` → recipes A and B.
- Each column after Shaft and At maps one-to-one onto a `GearSpec` field, so a row builds exactly the part the
  strip builds from the same values. **The reader sets every field explicitly** — a blank optional cell becomes the
  canvas's default, never `GearSpec()`'s (whose bore, teeth and face width are `"10"`, `"25"`, `"10"`): blank Bore
  is `""`, no bore. `Pressure angle` blank takes the Box's. `Part name` blank takes `default_stem`.
- Not columns: a gear's turn (§3.3), and a bevel gear's `shaft_angle` and `mate_teeth` (from its partner and the
  two axes).

**Meshes** — `Gear A`, `Gear B`, `Efficiency (%)` (blank: the Box's), `Notes`. Order does not matter.

**Modes** — `Mode`, then one column per sliding gear headed with its Gear name, holding one of its `Slides`
positions (blank: its position at 0), then `Notes`. Each mode becomes an assembly configuration; the first row is
the one the assembly opens in. No sliders: the sheet may be empty or absent. Sliders but no Modes rows: one
configuration, every slider at 0.

**Results** — written by the app on Export, ignored on import: a first-row note saying so, per shaft speed /
turning sense / torque, per mesh ratio / centres needed / centres placed / off by / contact ratio, and the overall
ratio and box size.

---

## 2. Reading and writing `.xlsx`: `workbook/xlsx.py` (stdlib, pure, Linux-tested)

**Reading** `read(path) -> Book` (sheets by name → rows of `Cell(ref, text, formula: bool)`):

- `xl/workbook.xml` + `xl/_rels/workbook.xml.rels` give sheet names → parts; `xl/sharedStrings.xml` the strings
  (rich-text runs joined).
- Cell types: `s` shared string (rich-text runs joined, `<rPh>` phonetic runs skipped), `inlineStr`, `str` (a
  formula's string result), `b`, `e` (an error value — reported with its cell, e.g. `#DIV/0! in Gears!D4`; a
  `#NAME?` in the Axis column gets the `Z+` sentence), and numbers. A `<c>` without `r` takes the next position.
- Numbers become typed text: Excel writes doubles to 17 digits (`1.1000000000000001`), so a number is rounded to
  15 significant digits and printed shortest (`63.75`, `17`, `1.1`). `GearSpec` fields stay typed text.
- An `Efficiency (%)` value of 1 or less is read as a fraction (a cell formatted as a percentage arrives as
  `0.98`).
- A `<f>` with no `<v>` is an error naming the cell. Merged cells, styles, column widths are not read.
- A file mid-save (Excel writes a temp file and replaces the original) can be caught half-written or briefly
  absent: `BadZipFile`, a missing part, `PermissionError` or `FileNotFoundError` mean "try again on the next tick"
  for up to five seconds, and only then an error or *"The workbook is no longer at …"*. A file that is not a zip at
  all (an encrypted workbook) or uses Strict OOXML namespaces gets its own sentence.
- Excel's `~$Name.xlsx` lock file beside the workbook is ignored as a file, and used as the sign that Excel has it
  open (§2, writing).

**Writing a new workbook** `write_new(path, book)`: the minimum valid package — `[Content_Types].xml`, rels,
`workbook.xml`, `styles.xml` (one header style: bold, fill, bottom border), one sheet part per sheet with inline
strings, a frozen header row, column widths, and **data validation lists** for every column with fixed words
(Kind, Side, Hand, Flank, Axis, Role, and each Modes slider column's positions).

**Changing cells in a user's workbook** `write_cells(path, sheet, {ref: value}, replace_sheet=None)`:

- **A text splice, not a re-serialisation.** `xml.etree` renames namespace prefixes and drops declarations used
  only in `mc:Ignorable`, which makes Excel open the file with a repair prompt. So the sheet part is edited as
  text: the `<sheetData>` cells are located with a small scanner, a changed `<c>` is replaced in place keeping its
  `s` (style) attribute, and a new cell is inserted in column order within its row (a new row in row order).
  Everything outside the touched cells is byte-identical; `etree` is used only to *read*.
- A number is written as a number, text as an inline string; a character XML 1.0 forbids is written as Excel's
  `_xHHHH_` escape. `write_cells` knows nothing of headers: **Export (W3)** finds each target's column by header and,
  for a column the sheet lacks (columns are optional — e.g. Profile shift), writes the header at the end of row 1
  first.
- **A percentage-formatted cell** (`Cell.percent`, read from the cell's number format) holds a fraction: Export
  writes 0.97 into it for 97 %, never 97, which Excel would show as 9700 %.
- **A formula cell is never written** — including a shared-formula child (`<f t="shared" si="…"/>`) and any cell
  inside an array formula's `ref` range. Such targets come back in a list for the window to show.
- **The safety net:** after splicing, the sheet part is parsed and every cell not asked for is compared with the
  original; any difference, or a part that no longer parses, refuses the whole write and leaves the file untouched.
  Shapes Excel never writes (comments, CDATA, a row twice, anything between rows) are refused up front.
- `calcPr`: an existing element gets `fullCalcOnLoad="1"` set on it in place; if absent it is inserted at its
  schema position in `workbook.xml`. Formulas that depend on a changed cell then recalculate when Excel opens it.
- `replace_sheet` rewrites the whole Results part (added, with its rels and content-type entries, if absent). It
  is unstyled, so the user's `styles.xml` is never touched.
- Every other zip entry is copied content-identical, in the original order, with its `ZipInfo` (name, date,
  compression). `zipfile` cannot copy raw compressed bytes, so "identical" means the content, not the bytes.
- Writes to a temp file beside the original and replaces it. If the `~$` lock file is present, or the replace
  raises `PermissionError` (Excel holds the file open on Windows), the window says so in a sentence offering
  *Export as…* a new file.

**After an Export** the app's own write is recognised (it keeps the hash of what it wrote), so the live link does
not report it as an outside change. But formula cells that depend on a written cell still hold Excel's old values
until Excel recalculates and saves. So if the workbook has any formula, the window says *"Open and save the
workbook in Excel so its formulas recalculate"*, and Build and Update SolidWorks wait for the next outside save.
A fix that was chosen but not yet exported is held in memory; when the file changes first, each held fix is
re-checked against the new read, and one that no longer applies is dropped with a note.

**Fixtures.** Our own writer's output is not evidence that Excel's files read correctly. *(Done in W1 with Excel
for Mac 16.03, driven on the user's Mac; LibreOffice's copy is a fixture too. A Windows-saved copy joins it when W2
reaches Windows.)* The user saves one workbook **in Excel** on Windows (`tests/fixtures/excel/Reducer_12to1.xlsx`, with a formula, a shared formula, a
percentage-formatted efficiency, a comment row, an extra column) and it is committed; tests read it, and
`write_cells` is run on it and the result read back. **Ask the user for it at the start of W1; W1 is not done
until it is committed.** Opening an exported file in Excel without a repair prompt is a Windows check in W3.

## 3. The model, checks and maths: `workbook/` (pure, Linux-tested)

### 3.1 `schema.py` — the format as data

One table per sheet: header text, unit, required, default, allowed words and aliases, and the `GearSpec` field it
fills. The reader, the template writer, the data-validation lists and the window's column help are all generated
from it, so the format is written down once. A test checks it against §1's column lists (canvas F lives outside
the repo, so §1 is the copy of record).

### 3.2 `model.py` — `GearboxSpec`

Typed text and frozen, in the style of `spec.py`:

```python
Box(name, output_folder, part_template, assembly_template, pressure_angle="20", efficiency="98", format="1")
Shaft(id, mounted_on="frame", x, y, z="0", axis="+Z", role="", copies="1", speed="", torque="", row=3)
Gear(id, shaft, at="0", spec: GearSpec, slides="", row=4)       # spec carries every GearSpec field
Mesh(a, b, efficiency="", row=2)
Mode(name, positions: Dict[gear_id, str], row=2)
GearboxSpec(box, shafts, gears, meshes, modes, source_path="")
```

Every item keeps its sheet row, so every diagnostic names a cell: *"Gears!F4: Teeth must be a whole number (got
17.5)."* `from_book(book) -> (GearboxSpec, diagnostics)` and `to_book(spec) -> Book` are inverses
(round-trip-tested).

### 3.3 `geometry.py` — positions, axes, phases

- Each shaft's axis as a point and unit direction in the origin's frame; `mounted on` composes frames.
- Each gear's face centre (`point + at × axis`).
- **Phase**: the angle θ each gear is turned about its axis so its teeth sit in its partner's spaces. Every part is
  built with a tooth *space* centred on +X. Walk the meshes outward from the first input (phase 0); for an external
  mesh where gear p (phase θp, zp teeth) sees gear q (zq teeth) at direction φ in the common plane, rolling contact
  gives

  `θq = φ + π − π/zq − (θp − φ)·zp/zq   (mod 2π/zq)`

  which at θp = 0, φ = 0 is `pair.mesh_angle` (0 for odd zq, half a pitch for even) — a test pins that. An
  internal mesh is derived the same way with both gears turning the same sense, pinned by
  `pair.internal_mesh_angle` at φ = 0. Further terms, each with its own test:
  - **Helical gears whose face centres are offset axially** by Δ: a twist of Δ·tan β / r on the follower.
  - **Shafts on −Z:** the angle is measured about the gear's own axis, so φ and θ are mirrored.
  - **Profile shift** is symmetric about the space centre and changes nothing here, which is checked rather than
    assumed.

  A gear reached twice (a loop: planetary) must agree both ways, or the planetary assembly condition has failed.
  **Test:** for every mesh, the two `preview.layout` outlines, turned and placed, do not overlap (polygon
  intersection), and do overlap when one is turned half a pitch. For an internal mesh the ring's outline is
  treated as the region outside its tooth line.

  *Correction (2026-11-13):* "a tooth space centred on +X" holds only on the plane the part's section is drawn
  on. A spur's is on +X at every height and a herringbone's at its apex, but a plain helical gear or ring draws
  its section on the Profile Plane one overrun (a normal module) *behind* its front face, so its front face is
  already turned `hand·360·overrun/L`. W3 counted the twist from the front face, in `geometry.Placed.twist`,
  `helical.face_rotations` and the test's own model alike: harmless for gears facing the same way (it is a
  common axial slide), but across Z+ and Z− every helical mesh, outside or in a ring, put teeth into teeth.
  The twist now counts from where the section is drawn (`HelicalDerived.turn_at`), and the tests turn each
  outline as the part's build plan sweeps it, read from the plan's own ops, not from `geometry`. The pair
  assemblies (`pair.assembly_plan`) never used either and are unchanged.

### 3.4 `checks.py` — `check(spec) -> List[Diagnostic]`

Each gear's own `kind_for(spec).validate` (so every rule the strip enforces holds). `kind_for` returns None for
`sleeve` and `dog`, which skip it and are refused at Build (W8). A bevel gear's validation needs `mate_teeth` and
`shaft_angle`, which come from its partner and the axes, so a bevel row is validated once those are known and is
refused at Build before W6. Then:

- **Errors:** an unknown shaft or gear name; a duplicate name; a missing needed cell; a word not in the column's
  list; a mesh between gears with different module, pressure angle, or (parallel helical) helix angle, or the same
  hand where opposite is needed; **centres not where the teeth put them**, by more than **0.005 mm** (half the last
  digit of a value typed to two decimals; a shaft at an angle should be placed by formula, and the message says
  so) — with the fixes of §3.6;
  meshing faces that do not overlap along the axis; two gears on different shafts, not meshing, whose faces
  overlap axially and whose tips come within 0.5 × the larger module; a gear tip passing through another shaft's
  axis within its face; a box that needs more inputs than it has, or is jammed (§3.5); a speed or torque on a
  non-input row.
- **Warnings:** two gears at mesh distance with overlapping faces but not listed in Meshes; an unused shaft; a
  gear on an `output` shaft that nothing drives in some mode.
- **Refused at Build, not errors:** rows a later phase builds (bevel, carriers and copies, turned axes, sleeves,
  dogs, modes) — "*G5 is a bevel gear: right-angle stages are built in phase W6.*"

### 3.5 `kinematics.py` — speeds and torques, any layout

One linear system, not a walk along the train. Unknowns: each shaft's speed ω, signed about **its own** Axis
(the workbook's convention). For shafts whose axes are parallel or anti-parallel (everything before W6), each is
projected onto the first input's axis n: ω̃ = ω · (a · n), so a −Z shaft's sense is not lost. Each mesh between
gears on shafts `p`, `q` whose axes are carried by shaft `c` (`frame` → 0):

`(ω̃_p − ω̃_c) · z_p = ∓(ω̃_q − ω̃_c) · z_q`   (− external, + internal)

- **Which `c` a mesh belongs to.** Each gear's shaft must be mounted on `c` or be coaxial with it, which a sun on the
  frame and a planet on the carrier are. This is checked, and a mesh that fits no carrier is an error.
- **Inputs and fixed shafts:** fixed shafts are 0, and inputs are their typed speed.
- **Solving.** The system is solved in `fractions.Fraction`, exactly, since teeth are whole numbers. Rank then
  tells the rest without float tolerance: fully determined gives speeds; under-determined gives *"needs another
  input"* with the free shafts named (a differential); inconsistent gives *"jammed"*.
- **Results.** The column "Turns, seen from +Z" uses ω̃ against +Z.
- **Torque** is limited to parallel trains in W3, where it is `T · i · η` per stage along the power path. Loops
  wait for W7.

Results are pinned for the 12 : 1 example: S1 1500 / 10.00, S2 −375 / 39.20, S3 125 / 115.25. They are
**checked by an independent subagent from the problem statement alone** before the test is committed.

### 3.6 `fixes.py` — what the import offers

For "centres not where the teeth put them", in this order:

- **Move.** Treat the meshes as a tree grown from the first input. The fix moves the shaft on the far side of the
  failing mesh, together with every shaft beyond it in that tree, by one vector, so the other meshes stay right. It
  is given as their new X, Y. It is not offered inside a loop, where moving one shaft breaks another mesh.
- **Profile shift.** For external spur and helical gears on parallel shafts, shift both gears to meet the typed
  distance. The solver's centre-distance shift is the private `pair._shifted` (`pair.py:248`). W3 makes the piece
  it needs public, as `pair.shift_for_centre(m, z1, z2, α, β, centre)`, using the same `split_shift` undercut limits
  and the same tip-thickness and clearance refusals. The shifts are written at full precision (x to 1e-6, e.g.
  `0.084550`), never rounded to look tidy: `0.085` lands 0.0013 mm off. The S2 = 64.00 example is pinned at
  x = 0.084550 each, working angle 20.61°, 64.000 mm.
- **On parts already built**, a shift is a structural change (`swbuild.structural_change`), so it rebuilds by §4.5.

A chosen fix changes the model in memory, and Export writes it to the cells it names.

## 4. SolidWorks: `workbook/build.py` and `swbuild.build_many`

### 4.1 Parts (phase W2)

For each distinct part: `kind_for(spec).plan(spec, derive(spec), recipe, template, path)` — the strip's own
planner, unchanged. Bevel, sleeve and dog rows are refused here (W6, W8). `swbuild.build_many(sw, plans)` builds
them in order: a part that fails stops the batch, and the result names what was made and what was skipped. Every
path is checked before anything is made: a build never overwrites a file (and `findings.SAVE_AS_OVERWRITES` is
True, so the check is the only guard). Each part gets its `.gear.json` as today; `GearRecord` gains `workbook`
(the file) and `workbook_gears` (every row it serves: identical gears share one part).

**"Identical to the strip's" is a test:** for each row, the `BuildPlan` (ops and globals) equals the one
`gui._plan_single` makes from the same `GearSpec`, and on Windows the `.gear.json` variables of a workbook part and
a strip part of the same values match.

### 4.2 The layout part (phase W4)

**W4 opens with probe tier 7, `p7_workbook.py`**, run on scratch documents like every tier, its results committed
and read into `findings.py` / `decide.py` and pinned by `test_findings.py`:

1. `InsertRefPlane` offset from the **Right** and **Top** planes: which side each flip puts the plane, and that
   the offset follows a global (only the Front plane was probed).
2. `InsertAxis2` through two planes **made in this build**, selected by name or handle. This is a new
   `Axis` op form: today it takes tree-order plane indices only.
3. A shaft at X = 0 or Y = 0: the base plane itself is used, with no offset plane. A global cannot carry a plane
   across zero, because `flip` is a flag, so a shaft that changes side of the origin is a structural change.
4. Five or more components inserted, `Place`d and `Fix`ed; and, in that assembly saved, closed and reopened,
   finding each component again by name and re-`Place`-ing it.
5. Opening a part by path and making it the active document (`OpenDoc6` / `ActivateDoc3`), for Update
   SolidWorks: `update_variables` refuses any part that is not active.

**If any of 1–4 fails, STOP and ask.** If 5 fails, Update SolidWorks asks the user to open the part.

Then `<Name>_Layout.SLDPRT`: for each `frame` shaft with axis ±Z, the plane offset from Right by X and the one
from Top by Y (or the base plane at 0), and an `Axis` through them named `"<Shaft> Axis"`. Globals `"<Shaft> X"`
and `"<Shaft> Y"` drive the offsets. The ±X / ±Y and arbitrary axes, and carriers, wait for W6/W7, since they need
a plane at an angle, or an axis from a point and a direction (probe tier 6, item 2, of PLAN-GEARBOX).

*Reading chosen (2026-11-13, W4):* a global exists only for a non-zero coordinate; at 0 the base plane is used
and there is no `"<Shaft> X"` to set. Tier 7 found a global set below zero is accepted and the plane silently
stays put, so a coordinate that changes side, or reaches or leaves 0, is structural, not a move; a minus-side
plane is linked to the global as `- "S2 X"`. Components are not renamed: the record maps each gear to the
`Name2` SolidWorks gave it (`Gear_m1.5_N68-1`), and they are found again by that. A revision's files are
`<Name>_r<n>_Layout.SLDPRT` beside `<Name>_r<n>.SLDASM`.

### 4.3 The static assembly (phase W4)

`<Name>.SLDASM`: the layout part inserted and fixed at the origin; each gear inserted, `Place`d at its face centre
with its axis along its shaft's and turned to its phase (§3.3), and `Fix`ed. Interference is checked as for a pair
(no interference is a `done` line; any is a CHECK naming the gears). Positions do not follow the layout's globals
yet: Update SolidWorks re-`Place`s the components, found again by name (tier 7, item 4).

### 4.4 Motion (phase W5)

Once `gear_mate` has passed on the host: each gear is unfixed and mated concentric to its shaft axis and to its
axial position, and each listed mesh becomes a gear mate at the tooth ratio with the probe's flip. Compound gears
are locked by an angle mate. This needs probe tier 6 items 3–5 of PLAN-GEARBOX (axis-to-axis mates, five or more
components, a lock between free components): **if they fail, STOP and ask** — the static assembly stays.

### 4.5 Update SolidWorks

From the linked file's latest read, against what was built (`GearRecord`s and the assembly's record):

- **A change the part's globals carry** (teeth, module, face, bore size …, as `swbuild.structural_change`
  decides today): `update_variables` on that part, opened and activated first (tier 7, item 5).
- **A moved shaft:** the layout part's globals and, while static, the components re-`Place`d. A shaft crossing
  the origin's plane is structural (tier 7, item 3).
- **A structural change, or a gear or mesh added or removed:** swapping one component in an assembly is unprobed.
  So the app says which parts changed and offers, **after asking**, to *build again* as `<Name>_r2` — new part
  files for the changed rows, unchanged parts reused, and a new layout part and assembly. The next revision is
  `_r3`, and so on. Nothing is overwritten (`SAVE_AS_OVERWRITES` is True, so the existence check is the guard),
  and the old files are left alone.

*Readings chosen (2026-11-13, W4):* **Update SolidWorks does not save**, as the strip's Update values does not;
the record marks each document it changed as unsaved until the file on disk is newer, and the window asks for a
save in SolidWorks. Reuse and Update both compare with SolidWorks live, not with the record alone, so an update
lost or not saved is put right by the next press. A part keeps its file name after a value update
(`Gear_m1.5_N68` holding 69 teeth), and a Part name change is structural only when the file name it makes
changes. A Z, Z± or At change is a move while the assembly is static. A build-again takes the smallest revision
whose layout and assembly paths are free and that no recorded revision used (so `_r2` may be `_r3` if `_r2`'s
files are already there); a new part whose file name is taken is `<stem>_r<n>`. The question says that reused
parts are shared, so a later Update that changes one also changes the earlier revision's assembly. There is one
build button, Build / Build parts / Build again…, with Update SolidWorks beside it.

*Readings changed by the W4 review (2026-11-13):* **an unsaved part is made new.** A part Update left unsaved
never holds a build back (overruling W4's agreement 7): it is not reusable, so the build makes that part new at
this revision, and the window says so and asks for the save once; its `.gear.json` is marked `unsaved_since`, so
it never claims values the file may not hold. Likewise a part a build's live check found not holding what the
record says (an update lost when SolidWorks closed unsaved and the unchanged file saved later): the build makes
nothing, the record notes the part (`mismatched`, with the file's time), and the next press makes it new rather
than fail the same check. **A part's suffix is its own:** a new part whose file name is taken gets the smallest
free `<stem>_r<k>` whatever the gearbox's revision, so a file in one part's way no longer moves a first build to
`_r2`; only the layout part and the assembly move the revision, and a Part name that would be one of the
gearbox's own file names is refused. **A copied workbook's record is not its own:** the record is found by its
file name beside the workbook, so a folder copied whole brings the original's; while the workbook it names is
still on disk, the copy's Update is not offered and its Build makes a gearbox of its own beside the original's
files, sharing and overwriting nothing; when that workbook is gone, it was moved, and the record is adopted.
Update touches only a document it changes. These were tested against the fake SolidWorks; they await a rerun of
the demonstration on SolidWorks.

*Readings changed by the second W4 review (2026-11-13):* **whose a record is, decided by the file and asked
when it cannot be known.** Two paths to one workbook (a mapped drive and its UNC path, `subst`, a junction) are
one workbook (`os.path.samefile` when both exist), never a copy of itself. A record whose workbook is gone is no
longer adopted silently — it may be one of two copies of a deleted original — but planned as a copy's until the
window has asked, once and default No, whether this workbook was moved or renamed from it; Yes adopts it, No
keeps it the other's (`copy_of`), and the answer is kept in the record. Locate… never carries a copy's record.
**Marks a job can prove are cleared.** A job reports which documents were open when it began and which it
loaded from disk; one loaded from disk holds what its file holds, so its unsaved marks go and what the job
found decides the rest (an Update that finds it holding the workbook clears its mismatched mark), and one
marked unsaved that was not open when a job began lost Update's changes and becomes mismatched. The header and
the save asked for count only the current revision's documents, and the save is said so that it is true if
SolidWorks has closed them since (nothing on the Tk thread can see SolidWorks). **A build keeps a journal:**
before its job starts, the record gains what it is about to make (`pending`); the finish takes it out; a pending
part on disk with no `.gear.json` is the interrupted build's own and is reused once checked live, a pending
layout part likewise, a pending assembly is gone beside. With it, a second close while SolidWorks does not
answer may quit anyway (default No), and a finish that raises still leaves what was saved reusable. **A
document holds its values** only if SolidWorks evaluates them as the unit its text matches would (a degree-form
part set to radians is updated, not reused). **Every new part's own name is claimed before any suffix**, so a
suffix never takes a typed Part name. Tested against the fake SolidWorks; the assembly check's new section `a3`
shows the journal and the marks on SolidWorks once rerun.

## 5. The Workbook window: `workbook_gui.py` (+ `ui_text`)

Opened from **Import workbook…** in the Gear panel header (a file dialog, then the window), or **New workbook…**
which writes a template (`write_new`, Box and headers filled, data validation set) and opens it in Excel. It is a
`Toplevel` sharing theme, widgets and the SolidWorks worker, as PLAN-GEARBOX §5 describes for its window. Laid out
as canvas board E2:

- **Header:** the linked path, when it was read, counts (*3 shafts · 4 gears · 2 meshes · no modes*), and what
  the box was worked out as (*Parallel reducer, 2 stages*).
- **Checks:** errors first, each naming its cell; an error with fixes shows them as choices (E2's two radio rows).
  Then the passed checks, one line each.
- **Speeds:** one line per shaft (W3).
- **End view** from the origin, with the origin's X and Y marked: `preview.layout_gearbox`, headless and tested,
  drawing each gear's outline at its phase (W3).
- **Footer:** Re-read · Export · Export as… · Build (disabled while there is an error) · Update SolidWorks (once
  built).

**The live link.** The window polls the file's size and modification time every second (the strip's link poll is
the pattern: `POLL_MS`).
- **On a change** it re-reads, re-checks, and shows *what changed* since the last read, cell by cell, e.g.
  *"Gears!F3 Teeth 68 → 70 · G1–G2 now 1.50 off"*. That normally appears within two seconds of the save: one poll,
  plus the mid-save retry of §2.
- **The link record** is `<Name>.workbook.json` beside the workbook: the path, the last read's hash, the hash of
  the app's own last write, and the built parts and assembly. The name avoids PLAN-GEARBOX's `.gearbox.json`,
  which is for the planner's own save.
- **Reopening.** `store.Recent` gains `workbooks`, the linked files most recent first. Import workbook… offers them
  first, so reopening the app re-links in one click.
- **A file that vanishes or is renamed** shows *"The workbook is no longer at …"* with a Locate… button, and
  nothing is lost.

## 6. Phases

| Phase | Deliverable | Demonstrable |
|---|---|---|
| **W0** | This plan committed | — |
| **W1 format** | `xlsx.py` (read, `write_new`, `write_cells`), `schema.py`, `model.py` + tests; **ask the user for the Excel-saved fixture first** | The Excel fixture reads into a `GearboxSpec`; `to_book` → `write_new` → `read` round-trips; `write_cells` on the fixture changes only its cells and refuses a formula cell; a bad cell's diagnostic names it. |
| **W2 batch parts** | The window's artboard and `UI-DESIGN.md` §9 first (drawn in `design/canvas/` by `gen.py`, as the strip was); then `build_many`, the Workbook window (header, gear list, per-gear errors), Import / New workbook…, the live link and change list, `Recent.workbooks` | Mac: each row's plan equals the strip's for the same `GearSpec`; the window updates within two seconds of a scripted save (screenshots). Windows: a workbook of 4 gears builds 4 parts whose `.gear.json` variables match strip-built twins. |
| **W3 positions and checks** | `geometry.py`, `checks.py`, `kinematics.py` (parallel), `fixes.py`, `pair.shift_for_centre`, Results, Export / Export as…, `preview.layout_gearbox` | Mac: the 12 : 1 workbook checks clean and its speeds match the pinned values; S2 typed at 64.00 shows E2's error and both fixes (shift x = 0.084550 each); Export writes the fix and Results and leaves a formula cell alone; screenshots checked by eye. Windows: the exported file opens in Excel with no repair prompt. |
| **W4 layout and static assembly** | Probe tier 7 (§4.2) and its findings; the `Axis`-by-name op; §4.2, §4.3; Update SolidWorks for values and positions; build-again `_r2` | Windows: tier 7 passes; layout part + 4 parts + assembly, gears meshed, no interference; change `S2 X` in Excel → Update SolidWorks moves it. *(2026-11-13: in the 12 : 1 reducer S3 X is a formula on S2 X, so S2 X alone moves S3 with it and leaves G1–G2 0.75 mm off its centres: the gearbox fails its checks and Update waits. The demonstration edit is S2 X 63.75 → 64.5 with G2's teeth 68 → 69, which puts G1–G2 back on centres at 64.5. Shown on SolidWorks 2026 in full, 244 checks, 0 failed; on 2024 tier 7, the build, its measurements and controls, the Excel edit and Update — the structural step and `_r2`, the continued build, the pure-move and risky-placement workbooks and the window run are still to run on 2024, in a fresh session. The W4 review's fixes since, and the second review's, are tested on the fake only and await a rerun on SolidWorks.)* |
| **W5 motion** | §4.4, after `gear_mate` and tier-6 items 3–5 have passed | Drag the input in SolidWorks: the output turns at 1/12 the input's angle, the right way. |
| **W6 right-angle** | Turned axes, bevel and crossed meshes | A bevel stage feeding a parallel stage builds; sub-plan and questions at the time. |
| **W7 planetary** | Carriers, copies, loops in kinematics and phases | A 4 : 1 planetary with the ring fixed builds; own sub-plan. |
| **W8 sleeves and modes** | Sleeve and dog kinds, Slides, Modes → configurations | The E4 transfer case's four modes; own sub-plan and probes (per-configuration mate suppression). |

The planner (PLAN-GEARBOX) starts after W5 and reuses W1–W5 whole: its data model becomes `GearboxSpec`
(superseding PLAN-GEARBOX §1), and its Solve fills one.

## 7. Verification

- **Mac/Linux:** `.venv/bin/python -m pytest` green, including `tests/test_workbook_{xlsx,schema,model,geometry,
  checks,kinematics,fixes,build}.py`. The Excel fixture is read in CI as committed bytes.
- The 12 : 1 example's speeds, torques, centre distances and the S2 = 64.00 shift (x = 0.084550 each → 64.000,
  working angle 20.61°) are pinned, and the answer key is checked by an independent subagent.
- The window: launch it, import the fixture, edit and save the file from a script while it watches, and **look at
  the screenshots** (change list readable, the end view meshing, nothing clipped).
- Windows: W2's batch build and W4's assembly, with the build logs committed under `probe/results/` the way probe
  runs are.

## Critical files

- **New:** `src/gear_generator/workbook/{__init__,xlsx,schema,model,geometry,checks,kinematics,fixes,build}.py`,
  `src/gear_generator/workbook_gui.py`, `src/gear_generator/probe/p7_workbook.py`, `tests/test_workbook_*.py`,
  `tests/fixtures/excel/`.
- **Changed:** `swbuild.py` (`build_many`), `store.py` (`GearRecord.workbook`, `workbook_gear`; the
  `.workbook.json` link record; `Recent.workbooks`), `pair.py` (`shift_for_centre`, public), `gears/base.py` and
  `swcom.py` (`Axis` through planes by name; open and activate a part by path; find a component by name — W4,
  after tier 7), `findings.py` and `probe/decide.py` (tier 7), `preview.py` (`layout_gearbox`), `ui_text.py`,
  `gui.py` (the Import workbook… and New workbook… buttons), `design/UI-DESIGN.md`, `README.md`,
  `docs/PLAN-GEARBOX.md` (§1 points here).
- **Reused unchanged:** `KINDS` / `kind_for` and each kind's `derive`, `validate`, `plan`; `pair.mesh_angle`,
  `internal_mesh_angle`, `split_shift`, `describe`; `swbuild.build`, `update_variables`, `structural_change`;
  `spec.GearSpec`, `default_stem`, `sanitize_stem`.
