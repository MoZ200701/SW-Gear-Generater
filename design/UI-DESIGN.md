# Gear Generator — UI design, as built

The window as it stands, written for whoever changes it next. The look is
Airfoil Converter's, unchanged: `theme.py` is a copy of that app's and
`widgets.py` is too but for the explainer card and its diagrams (§2), so its
`design/UI-DESIGN.md` §3–§5 (graphite colour, Libre Franklin and JetBrains Mono,
the controls) hold here word for word and are not repeated. What is new is the
arrangement, and the build flow behind the buttons.

`docs/PLAN.md` §4.5 is the plan this was built to; where the window differs
from it, §7 below says so.

## 1. The window

A portrait **460 px** strip beside SolidWorks (scaled by `_scale_to_dpi`), with
a **360 px** flyout docked to its right for the pair candidates. Opening the
flyout grows the window sideways and closing it shrinks it back; the strip
never reflows. Nothing inside the strip scrolls on its own; when the screen is
shorter than the strip, the whole page scrolls.

Every value on the form is typed text and goes into a `GearSpec` or `PairSpec`
as typed: `"1.5"` stays `"1.5"`, and a blank field is not a zero.
`GEAR_VARS` and `PAIR_VARS` in `gui.py` map every spec field to its variable,
and `tests/test_gui_spec.py` proves they cover the dataclasses exactly.

## 2. The strip, top to bottom

The order follows the work: what kind of gear, the solver that fills the gears
in, the gears themselves, what they come to, where they go, and SolidWorks.

| Mode | Top to bottom |
|---|---|
| Gear pair | Gear · Pair · Gear A · Gear B · Derived · Output · SolidWorks · footer |
| Single gear | Gear · Gear · Derived · Output · SolidWorks · footer |

It is the `order` list in `_build_strip`. In single mode the Pair panel is not
disabled but **taken out of the grid**, as Gear B is: one gear has no pair to
solve, and a greyed panel is only clutter.

### Gear — readout `Spur · involute curve`

Three segmented rows: **Kind** (`Spur` · `Helical` · `Double` · `Bevel`),
**Flank** (`Involute` · `Arcs`), and **Make** (`Single gear` · `Gear pair`).
`Double` is the herringbone: the whole word does not fit its share of the row,
so the readout says it (`Herringbone · involute curve`). Internal is not a kind:
it is the gear panel's **Teeth side**. Choosing a kind shows or hides the rows
below that only some kinds have — `_show_helix_rows` decides all of them (§2,
*Rows by kind*).

### Rows by kind

| Row | Panel | Shown for |
|---|---|---|
| Helix angle, Hand | Gear A/B | helical, double |
| Groove (placeholder *none*, hint *between the two helices*) | Gear A/B | double with external teeth; not a ring |
| Profile shift (unit *× m*, placeholder *0*, hint *+ cures undercut*) | Gear A/B | spur, helical, double with external teeth; in a pair only on parallel shafts with an external mesh. Hidden, it goes to the spec as 0 |
| Teeth side (`External` · `Internal`) | Gear | spur, helical, double in single mode; in a pair the Pair panel's Mesh decides |
| Rim (placeholder *root + 6 × module*) | Gear A/B | a ring — and Bore is hidden for it |
| Shaft angle, Mate teeth | Gear | bevel in single mode; in a pair they come from the Pair panel's shaft angle and the other gear's teeth |
| Cone distance (in Centre distance's place, hint *apex to heel*) | Pair | bevel |
| Mesh (`External` · `Internal`) | Pair | every kind but bevel; Internal makes gear B the ring |
| Shafts (`Parallel` · `Crossed`) | Pair | helical and double, external mesh |
| Shaft angle | Pair | bevel, and crossed pairs |
| Hands (`Same` · `Opposite`) | Pair | crossed pairs |
| Helix range | Pair | helical pairs on parallel shafts |
| Assembly (`Fixed` · `Gear mate`; `Gear mate` greyed, hint *not yet probed*, only while `findings.GEAR_MATE_ROUTE` is unset — it has been set since probe `gear_mate` passed) | Pair | every pair on parallel shafts; bevel and crossed pairs are built fixed |

Each new field has an explainer card; its diagram is, for now, an existing
field's (`widgets.DIAGRAM_ALIASES`): Teeth side and Mate teeth draw the teeth
and ratio glyphs, Rim the bore, both shaft angles the pressure angle, and Mesh,
Shafts and Cone distance the centre distance. Profile shift has its own: a
tooth, its pitch line and the cutting rack's datum line x·m further out; and
Assembly its own, a pinion and its wheel with arrows turning opposite ways.

### Pair — readout `C 60 mm · i 3 · m1.5 20:60`, and **Candidates** beside it

Centre distance, Ratio (hint *3, or 1:3 for driven over driver*), Module
(placeholder *any*, hint *blank tries every standard one*), Series (`Series 1` ·
`1 + 2` · `+ fine`), Teeth *min* to *max* (hint *under min is undercut*), for a
helical kind Helix angle (placeholder *any*, hint *blank solves it in the
range*) and Helix range *min* to *max* (placeholders the kind's range, 8–25° or
20–40°), Assembly name, and **Solve** with its summary, `69 candidates · 3 exact · 2 with
shift · m1.5 20 : 60 chosen` — *with shift* counting the clean rows that need a
profile shift, and the last part once a candidate has been clicked, so the strip
says what was picked with the flyout closed. The readout's last part appears
then too.

**Candidates** / **Hide candidates** is in this panel's header, at the right
after the readout: the candidates belong to the solver. Going back to single
gear closes the flyout, since the button that would hide it goes with the panel.

### Gear A — readout `m1.5 · z25 · 20° · PD 37.5 mm`

Module (every ISO 54 module in a dropdown beside it, hint *ISO 54*), Teeth,
Pressure angle (14.5, 20 and 25 in a dropdown), Face width, Bore (placeholder
*none*), Backlash (placeholder *0.3 × module*, hint *ISO: 0.02–0.05 × m*), Fillet
(placeholder *0.38 × module*), for a helical kind Helix angle (10–30 in a
dropdown, hint *normal module, α*) and Hand (`Right` · `Left`), and Name
(placeholder: the stem the part will be saved as, `Gear_m1.5_N25`, or
`Helical_m2_N20_15R` with the helix angle to two decimals). For a helical gear
Module and Pressure angle are the normal ones, and the readout adds the helix:
`m2 · z20 · 20° · β15° R · PD 41.411 mm`, and a shifted gear its shift, `m2 · z15 · 20° · x+0.12 ·
PD 30 mm`, whose Name placeholder ends `_x0.12`. Profile shift sits under Fillet. A dropdown writes its value into the field and lets
go, so the field stays the one source. A half-typed gear reads out *check the
fields*. At the foot of the panel, the explainer card.

### Gear B

The same panel for the second gear, shown only in pair mode.

### The explainer card — what the number being typed means

One card, at the foot of the panel whose field has the caret: Gear A's, Gear B's
or the Pair panel's, the other two `grid_remove`d. Every `Field`'s entry brings
its own up on `<FocusIn>`; at launch it sits in Gear A showing Module. It is
`widgets.Explainer`: the pick tracker's block — `#fafafa`, 1 px `#cfcfcf`, 8 × 10
px padding, 10 px between its two columns — with a 56 px stroke diagram at the
left and three lines at the right:

1. the field's name in 12.5 px 600, then ` · ` and its symbol in mono `#6e6e6e`
   (`Module · m`);
2. what it is, two or three sentences in 12 px `#505050`, wrapped to the column;
3. the worked line: `here` in 11.5 px `#8f8f8f`, then what the typed value comes
   to in mono 11.5 px ink. A blank field says what blank means.

The words are `ui_text.explainer(field, derived, stem, pair, folder) -> (name,
symbol, what, worked)`, tested for every field in `tests/test_ui_text.py`. The worked line is derived text like every readout: it
is filled in again on every `_derive_now`, not only when the caret moves, and a
gear that does not work out says *check the fields*, as the gear readout does.
The diagrams are `widgets.draw_diagram`, stroke drawings on a 56 px grid the way
`draw_icon` draws the 16 px icons, translated from `design/canvas/gen.py`'s
`DIAGRAMS` — a change to one belongs in both.

### Derived — readout `C 60 mm · i 3 · contact ratio 1.671` in pair mode

A **434 × 210 px** picture across the panel body, above the values:

- **Pair mode.** Both outlines at one scale, gear B turned half a turn plus the
  mesh angle the assembly is mated at (`pair.mesh_angle`: half a pitch for an
  even count, nothing for an odd one) so a tooth points at A's centre, and
  placed at the centre distance the teeth make, `m (N_A + N_B) / 2` — or,
  shifted, the working one, `pair.centre_of`, so the pitch circles stand a
  little apart. Pitch
  circles dashed `#d8d8d8`, touching at the pitch point, which is what says
  "meshed"; outlines and bores `#505050`; a 10 px cross and the gear's letter at
  each centre in `#8f8f8f`. Below, the centre distance: extension lines
  `#c6c6c6` from each centre, the line itself with arrowheads, and `C 60 mm` in
  mono 11.5 px centred above it.
- **Single mode.** One gear the same way, the dimension spanning its pitch
  circle: `PD 37.5 mm`.
- No gear that works out: `no gear` in `#9c9c9c`.

Where all of that goes is `preview.layout`, in design pixels and millimetres,
with no tkinter in it, so `tests/test_preview.py` can check the scale, the
centres, the turn and the dimension without a display; `_draw_preview` only
turns those into the screen's pixels and strokes them.

A helical gear is drawn as its transverse section, the one its sketch cuts.
Under the picture in pair mode, three rows for the pair — Centre distance
`60 mm`, Ratio `3 · 20 : 60`, Contact ratio `1.671` (the transverse one for a
helical pair), all from `pairs.describe`, and for a shifted pair a fourth,
Working α `21.252°` —
then a 1 px rule, then the table: captions `A · mm` and `B · mm`, the label
column 104 px, value columns 96 px. Values carry no unit; one `mm` caption heads
each column. Where a value came from a default it says so (`0.45 · 0.3m`). A
helical gear's column starts with six more: Helix `15° · right`, Transverse m,
Transverse α, Lead, Twist on face (face to apex for a herringbone), and
Overlap εβ. A shifted gear's starts with Profile shift `+0.3 · 0.6`, the
coefficient and what it comes to in mm. A shifted pair whose tips come within a
tenth of a module of the other gear's root says so under the table, and one
whose tips reach it is an error.
Errors come first, then warnings, each once, in `theme.ERROR`. The form is
worked out again **120 ms** after the last keystroke. An error disables
**Build**.

### Output — readout: the folder, shortened from the left

Folder with **Browse**; Part template and Assembly template (the second only in
pair mode), each blank for SolidWorks' default; **Open .gear.json** with a hint
naming the record that is open.

### SolidWorks bar — readout is the connection: `● SolidWorks 2026 (revision 34.0.0) — Part1`

The dot and the headline (no document open is a good state here: this app makes
its own documents). Below, what the primary button is about to do (*Build will
make Gear_m1.5_N25.SLDPRT.*, or *Update values will change 2 variables in
Gear_m1.5_N25.SLDPRT.*), and a line counting what is left to do by hand.

### Footer

The status dot and line — one sentence for whatever last happened — then
**Update values** (secondary) and **Build** (primary). **Update values** shows
only while an opened record's part is the active document in SolidWorks and
the form differs from what that part holds.

## 3. The flyout

`PAIR CANDIDATES` with **Hide**; the solve summary; a table `MODULE · TEETH ·
ERROR` — a non-standard module marked ` *`, the error column reading *exact* or
what is off (*C +0.5 mm · i 1.2 % · undercut*), and for a helical pair starting
with the row's helix angle (*β18.19° · exact*) and a shifted row with its shifts
(*x +0.12/−0.12 · exact*), exact rows in `theme.OK`; and a
card for the chosen row: module and teeth, the centre distance and ratio they
make, the contact ratio, and whether the module is non-standard, the pinion
undercut, or the gears shifted. Clicking a row writes its
module, teeth and profile shifts onto both gears — a row without shift writes 0,
so an earlier row's shift is not left behind — and for a helical pair the helix
angle, and gear B the other hand from gear A, and changes nothing else on the
form.

## 4. The build flow

A build is planned on the Tk thread from the form as it stands — a
`BuildPlan` is plain data — and submitted to the SolidWorks worker as **one**
job: `swbuild.build` for a single gear, `swbuild.build_pair` for a pair (both
parts, then the assembly). While it runs, **Build** and **Update values** are
disabled and the SolidWorks poll stops asking, so nothing else reaches
SolidWorks. The poll collects the result, writes a `.gear.json` beside each
saved part (a record already there keeps its id and creation time), remembers
the folder, templates, recipe and mode in `recent.json`, and sets the status
from `ui_text.build_status` / `pair_status`. The full build log goes to the
console when there is one.

A build is refused before anything is made when the folder does not exist or a
file it would write already does.

**Update values** refuses a change the equations cannot carry (the other
recipe or kind, a bore that appears or vanishes, or a shift that does — an
unshifted part has no `"Profile Shift"` global) with a sentence saying to
build a new part, and otherwise runs `swbuild.update_variables`, which checks
the active document is the record's part, sets only the globals that differ in
one suppressed batch, and rebuilds once.

## 5. Status sentences

All in `ui_text.py`, tested without a window:

| After | Reads |
|---|---|
| a clean build | *Built Gear_m1.5_N25.SLDPRT. 1 thing to do by hand: Assign a material to Gear_m1.5_N25; the build leaves it unset.* |
| a failed step | *Part1 was left open, unsaved. cut 'Tooth Space' from space, through all: …what SolidWorks said…* |
| a sketch not fully defined | the built sentence with *Check: Tooth Space Sketch is under-defined, not fully defined.*, dot red |
| a pair | *Built Pinion_m1.5_N20.SLDPRT, Gear_m1.5_N60.SLDPRT and Pair_m1.5_20T_60T.SLDASM.* and the counted manual steps |
| Update values | *Changed 2 variables in Gear_m1.5_N25.SLDPRT and rebuilt it.* / *Nothing to update: …* |

## 6. Files

| File | Holds |
|---|---|
| `gui.py` | layout, the variable tables, the poll, the build and update flow |
| `workbook_gui.py` | the Workbook window (§9): its layout, the live link's poll, Export, and the build and update jobs and their finishes |
| `workbook/` | everything the window decides: `assess` (the one pipeline the window and the boards share), `gearbox` (what Build makes and reuses, revisions, the record a build leaves), `update` (what Update carries, and the record it leaves), `layout` (the layout part, the assembly, each gear's frame) |
| `ui_text.py` | every readout, status sentence and explainer |
| `preview.py` | where the Derived panel's gears, and the dimension under them, go; and the Workbook window's end view (`layout_gearbox`) |
| `theme.py` | Airfoil Converter's, unchanged |
| `widgets.py` | Airfoil Converter's, plus `Explainer` and `draw_diagram` |
| `swbuild.py` | the build, run against the `SolidWorks` protocol |
| `store.py` | `.gear.json` records and `recent.json` |
| `design/canvas/` | the artboards, one strip each: `Main` (a spur pair), `SingleGear`, `ShiftedPair` (a solved row with profile shift), `HelicalPair` (gear B's hand following A's), `Herringbone` (grooved), `RingPair`, `CrossedPair` (opposite hands), `BevelPair`, and `FieldGuide` (every explainer card, each worked for a gear that has the field); and the Workbook window, 1080 px wide, as `WorkbookReady`, `WorkbookError`, `WorkbookFix`, `WorkbookChosen`, `WorkbookBuilt`, `WorkbookUpdate`, `WorkbookUpdated`, `WorkbookAgain`, `WorkbookUnsaved`, `WorkbookCopy`, `WorkbookMoved` and `WorkbookCloseAnyway` (§9); the built ones run the worker against `tests/test_swbuild.py`'s fake SolidWorks, so `gen.py` needs the tests folder beside it. `gen.py` writes them — `.venv/bin/python design/canvas/gen.py` — taking every word from `ui_text`, every picture from `preview.layout` and which field borrows which diagram from `widgets.py`, so they cannot drift from the window; only the HTML and the SVG diagrams are its own. `ui.py` is Airfoil Converter's builders, unchanged. The first three once lived at <https://claude.ai/artifact/NZXpsX26vgcabs9fFryF7G>, which has not been republished since |
| `design/renders/` | each artboard as a PNG at 2×, `<Board>.png`, made by `.venv/bin/python design/canvas/render.py` with headless Chrome (no window opens; a throwaway profile) and trimmed of the empty window ground. Its `CHROME` is the Mac's path; on Windows or WSL point it at `chrome.exe` and add `--disable-lcd-text`, or the text comes out with colour fringes |

## 7. Where it differs from the plan

- The pair's assembly is mated at the centre distance its teeth make,
  m (N1 + N2) / 2, not the one typed into Solve: any other would pull the teeth
  apart or into each other. A candidate that misses the typed distance says so
  in its ERROR column before it is chosen.
- The mesh angle mate is never zero. An odd tooth count meshes one whole tooth
  pitch round (360 / N2) just as it does at 0°, and a zero-degree angle mate was
  not something the probe exercised.
- A sketch that comes out under-defined is reported (*Check: …*) rather than
  failing the build: the part is still the right gear, and the sentence says
  what to look at.

- Helix angle and Hand have their cards (a slab with its teeth leaning β, and a
  right- and a left-hand gear). Hand takes no caret, so choosing a hand shows
  it. In a pair gear B's Hand follows gear A's — `pair.partner_hand`: the other
  on parallel shafts, the same round a ring, and on crossed shafts as Hands
  says — with the wrong segment turned off and the hint *follows gear A*.

And where the window differs from the artboards, because Tk would not do it:

- The Derived picture is **434 px** wide, not the 436 the artboard gives it:
  434 is what the panel body actually is (460 less the panel's border and its
  12 px padding either side), and 436 overflowed it on the artboard too.
- The explainer's worked line is two labels, `here` and the value, so a line
  long enough to wrap carries on under the value rather than under `here`. Tk
  has no first-line indent, and a single label cannot hold two faces.
- Series takes no caret — a segmented row is not a text field — so its card
  comes up when a series is *chosen*, which is the nearest thing to putting the
  caret in it. Every other field's card comes up on `<FocusIn>`.
- The diagrams are the artboard's SVG paths redrawn as canvas strokes: arcs are
  given as a centre, a start and an extent, and the fillet's quadratic is
  sampled, since a Tk line is either straight or a spline through all of it. At
  100 % scale a 1.2 px stroke lands on 1 px, so what separates the drawing from
  the dimension it is about is the accent colour and its 2 px stroke.
- Going back to Single gear closes the candidates flyout: **Hide candidates** is
  in the Pair panel's header now, and the flyout would otherwise be left open
  with nothing to close it.

## 8. Rings, crossed pairs and bevel gears (v0.3)

- **Derived** for a ring lists its rim first and calls the tip *Inner tip*; its
  fillet note is *0.15m*. A bevel gear's rows are its own: pitch cone δ, cone
  distance, pitch and outer diameters, apex to crown, addendum, dedendum, face
  and root angles, virtual teeth, toe scale, tooth at pitch and backlash. The
  readout reads `δ 26.565° · R 67.082 · OD 67.218 · X 58.195`. A crown gear's
  readout ends `· crown` and its virtual teeth read *∞ · a rack*; an internal
  bevel's ends `· internal`, its *Outer diameter* row becomes *Tip diameter*
  and its virtual teeth end *· a ring*. The Teeth row's worked line says which
  side the cone puts the teeth, and Shaft angle's names the form.
- **Pair readout and rows** say `R` and *Cone distance* for a bevel pair.
- **Candidates**: a bevel row's error is *R +0.03 mm*, an internal row adds
  *clash 0.14 mm*, a crossed row starts *β45°/45°*. A bevel row with a crown
  or internal bevel gear starts *B crown ·* or *B internal ·*. Build makes
  those two like any bevel gear now that probe `bevel_planes_beyond_90` has
  passed; before, it refused them in the status line, with nothing on the form
  greyed for it.
- **Preview** (`preview.layout_internal`, `preview.layout_bevel`): a pinion is
  drawn inside its ring, the rim a plain circle, the pinion turned half its
  pitch; a bevel gear is its axial section, both halves, with the pitch cone and
  axis dashed, and a bevel pair is the two sections meeting at the apex with
  gear B turned Σ, dimensioned `R 67.082 mm · Σ 90°`. A crossed pair is drawn as
  a parallel one with `· Σ 90°` after the centre distance.

## 9. The Workbook window (W2–W4, docs/PLAN-WORKBOOK.md §4.2–§4.5, §5)

A second window for a whole gearbox written in an `.xlsx` workbook, linked to
the file: it reads it, checks it, re-reads it on every save, and builds it in
SolidWorks — its parts, a layout part with an axis per shaft and a static
assembly with the gears placed meshed — then carries later edits of the
workbook into what it built (**Update SolidWorks**), or builds the next
revision beside it (**Build again…**). It is a `Toplevel`, `Workbook —
Reducer_12to1.xlsx`, sharing the strip's theme, widgets and SolidWorks worker;
the strip is untouched.

**Opening one.** **Import workbook…** in the Gear panel's header opens a menu:
*Open a workbook…* (a file dialog), *New workbook…*, and below a rule the last
five workbooks that are still where they were (`Recent.workbooks`), so
reopening the app re-links in one click. *New workbook…* asks where to save
(`Gearbox.xlsx`), refuses a file that exists, writes a blank workbook from the
schema — the Box sheet filled, its Name the file's, every other sheet a header
row with drop-down lists for the fixed words — opens it in Excel and links it.
Opening a workbook whose window is already open brings that window forward.

Artboards, each with its render in `design/renders/`: `WorkbookReady` (after
a save that made G4 wider), `WorkbookError` (a save that broke a cell and added
a bevel gear), `WorkbookFix` (S2 and S3 typed 0.25 mm on, so G1–G2 is off its
centres, both fixes offered), `WorkbookChosen` (the move chosen, waiting for
Export), `WorkbookBuilt` (Build pressed: the build's sentence, **Build again…**
and **Update SolidWorks**), `WorkbookUpdate` (PLAN-WORKBOOK §6's edit, S2 X
63.75 → 64.5 with G2's teeth 68 → 69 and S3 X following to 132.5, before the
press), `WorkbookUpdated` (after it, not yet saved), `WorkbookAgain` (G1's
flank changed to arcs, which needs a new part, with the *Build again?*
question), `WorkbookUnsaved` (after the update, still not saved, G1's bore
cleared: the demonstration's structural step), `WorkbookCopy` (the
reducer's folder copied whole, workbook and record, the original still
there; each part under the `_r2` name the build will give it),
`WorkbookMoved` (the folder moved by hand, the record's workbook gone: the
window asks whether it was moved or is a copy) and `WorkbookCloseAnyway` (the
window closed a second time while SolidWorks has not answered its build). `gen.py` draws them from a real workbook written, read and worked
through by the app, with the window's own sizes and colours from
`workbook_gui`, the end view from `preview.layout_gearbox` and every line from
`ui_text` — the footer is `workbook_footer` whole. The built boards run
`swbuild.build_gearbox` and `update_gearbox` against the test suite's fake
SolidWorks and finish into a real record, on a disk that is a set of paths;
nothing is saved anywhere real.

### The layout

**1080 px** wide, in two columns under a header and over a footer that both
span the width: on the left (at least 610 px, taking any spare width)
**Workbook**, **Gears**, **Checks** and **Since the last read**; on the right
**End view, from your origin** and **Speeds**. The window keeps that width —
paths are shortened in the middle (`ui_text.short_path`, 52 characters, the
folder 32) so nothing pushes it wider — and grows taller when a save brings
more lines, never shrinking below what the user dragged it to. Grown, it moves
left or up rather than off the screen.

- **Header.** The file's name in bold (13 px; the artboards draw it at 15);
  under it a dot and `linked · read 14:02:31 · open in Excel`
  (`ui_text.workbook_read_line`; *open in Excel* while
  Excel's `~$` lock file is beside it), then the record's word on what is built
  (`ui_text.workbook_built_tag`): *· built from this version* or *· changed
  since it was built* once a layout part or assembly is on record, *· parts
  built from this version* / *· changed since its parts were built* for parts
  alone, nothing before anything is built (nor for a copied workbook, whose
  record is the original's). *This version* is the read the record
  says SolidWorks was last built or updated from; a build that stopped part-way
  leaves it as it was, so the header then says changed. While documents Update
  SolidWorks changed are not saved it says *· updated from this version, not
  yet saved* (*· parts updated …* for parts alone), never *built from this
  version*: that version is in SolidWorks only until the save. The dot is green, red
  while the file is gone or will not read. At the right **Open in Excel** and **Re-read**, and **Locate…** before
  them only while the file has gone.
- **Workbook** (readout `3 shafts · 4 gears · 2 meshes · no modes`): File, Name,
  Output folder with where it came from (*from the Box sheet*, *the strip's
  Output*, or *set one on the Box sheet*), and **Worked out as**, what the rows
  add up to: *Parallel train · 2 meshes · 12.000 : 1 · output turns the same
  way*, or for a layout this phase does not do, *Not laid out yet: P1 is mounted
  on C*. When the meshes give no ratio it says why rather than leaving it out:
  *Parallel train · 1 mesh · no overall ratio: G2 meshes but is not laid out*
  (the reasons are the Results sheet's; a box with no input and output says
  nothing).
- **Gears** (readout `4 parts to build · 1 later`, once built `4 parts built`
  or `3 parts built · 1 to build`): Gear, Shaft, Kind, Teeth, Module, Face, Part
  (the file's stem, the recorded file's once built; this column takes the room
  left; the others are as wide as they need, at least their minimum), and a
  dot with what will happen (`ui_text.workbook_gear_rows`, given the record and
  what Update would do):

  | State | Dot | Words |
  |---|---|---|
  | to build | green | *to build* |
  | the same part as another row | green | *the same part as G1* (identical rows share one file) |
  | a later phase builds it | grey `#8f8f8f` | *later · phase W6* |
  | an error of its own | red | *see Checks*, in red |
  | built, and Update leaves it | green | *built* |
  | built, and Update changes its values | near-black `#2b2b2b` | *built · changes on Update* |
  | built, but its change needs a new part, or its file is gone | red | *needs a new part*, in red |

  Values are shown as typed, a bad one included (`68.5`); a ring's kind reads
  *Ring*. No gears: *No gears yet: add rows to the Gears sheet and save.*
- **Checks** (readout `1 error · 2 warnings`, or *no problems*): first any fix
  chosen and not yet written, *Chosen, not yet written: Move S2 and S3 beyond it
  by -0.25 mm* with **Undo**; then the errors in red and the warnings in grey,
  each beginning with the cell it names (`Gears!F3: …`, `Meshes!A2: …`). Under an
  error that has fixes, indented 14 px, one button per fix with what it changes
  beneath in mono: **Move S2 and S3 beyond it by -0.25 mm** over `S2 X 64 →
  63.75 · S3 X 132 → 131.75`, and **Keep your positions: profile-shift G1 and
  G2** over `x +0.084550 / +0.084550 → 64.000 exact · working angle 20.61° · ε
  1.62` (`workbook.fixes`, for centres that are off; the move is not offered
  inside a loop of meshes, nor the shift where it does not apply). Each row a
  later phase builds is a grey line at its cell, naming the row and the phase
  (`workbook.build.later_rows`): *Gears!A7: G6 is a bevel gear: right-angle
  stages are built in phase W6.*, *Shafts!A4: P1 is mounted on C, with 3 copies
  round it: carriers and copies are laid out in phase W7, and the gearbox is not
  checked until then.*, *Shafts!A4: S3's axis is X+: turned axes are laid out in
  phase W6, and the gearbox is not checked until then.*, *Gears!A5: G4 slides:
  sliding gears are placed in phase W8, with modes, and it is checked only at
  its At until then.*, *Modes!A2: 2H, 4H, N and 4L are modes: they become the
  assembly's configurations in phase W8.* (sleeves and dog rings as the bevel
  gear, with W8). Clean: *No problems: every row reads, and every gear works out.*
  **While Excel has yet to recalculate an Export** (the footer's recalculation
  wait) the read is provisional: Checks opens with *Provisional: the workbook's
  formulas still hold Excel's old values, so these checks may change once Excel
  recalculates and saves it, and no fixes are offered until then.*, its readout
  reads `provisional · 1 error`, the Speeds and end-view readouts end `·
  provisional`, and no fix button is shown — one worked from an old formula
  value would land wrong once Excel recalculates.
- **Since the last read** (readout `2 changes · 14:02:31`, or *nothing changed ·
  …*): what the last outside save changed, one line per cell in mono, `Shafts!C3
  S2 X 63.75 → 64`, and rows that came or went, `gear G5 added (Gears row 6)`.
  Then what that did to the checks (`ui_text.workbook_change_lines`, from
  `workbook.link.consequence`): a mesh that moved off its centres or back,
  `G1–G2 now 0.25 mm off` / `G1–G2 now on centres`, and the problems the checks
  did not have before and those now gone, by the cells they name, `3 new errors
  (Gears!F3, Shafts!A3, Shafts!A4) · 1 new warning (Gears!A7) · 1 cleared
  (Gears!Q3)` (three cells named,
  then `…`). A problem is matched by the item and column it is about, not by
  its cell, so a problem whose numbers moved, or whose row moved when rows were
  inserted, deleted or sorted, is the same problem, not a new one; it is named
  by the cell it is in now. A name typed over in its own row, the old name gone
  from the sheet, is a rename, `Gears!A5 G4b Gear G4 → G4b`, and G4's problems
  are G4b's. One cell changed, it follows that cell on its line,
  `Gears!F3 G2 Teeth 68 → 70 · G1–G2 now 1.5 mm off`; several, it is a line of
  its own after them. It is read against the file as it was, as the cells are,
  not with a chosen fix made; but a mesh it says is off that a chosen fix puts
  back on centres reads `G1–G2 now 0.25 mm off, covered by the chosen fix`.
  Nothing follows when the checks say what they said before. The readout counts
  the cells only. *Nothing changed.* when nothing has.
- **End view, from your origin** (readout `z 7.5 · z 27 · origin`, or *origin off
  view*): a 392 × 300 px white canvas. Every placed gear's own outline at its
  phase, seen from +Z as SolidWorks' Front view (+X right, +Y up), each at the
  middle of its face so a helical gear shows its section there; a ring adds its
  rim as a circle. One colour per face height, nearest +Z drawn last: ink
  `#3c3c3c`, then blue `#2f6db5`, orange `#b35c00`, purple `#6a3d9a`, green
  `#1a7f37`. Each shaft a 10 px cross with its name in mono below right, or on
  the first side clear of the origin's arrows when that would sit on them (a
  shaft at the origin has it below left). The origin: X a red arrow and Y a
  green one, 26 px, and a dot. All of where is `preview.layout_gearbox`, headless
  and tested; the window only strokes it. A gearbox this phase does not lay out
  (a carrier, a turned axis) shows that sentence in grey instead, and no readout.
- **Speeds** (readout *seen from +Z*, or *no input*): one mono line per shaft,
  `S2    375.0 rpm clockwise · 39.20 N·m` (`ui_text.workbook_speed_lines`),
  turning as seen from +Z, torque where the power path gives one; *not driven*
  for a shaft nothing reaches. A gearbox a later phase drives gets one grey
  sentence instead.
- **Footer.** A dot and one sentence, green when all is well, wrapped in the
  room the dot and the buttons showing leave (never narrower than 400 px), so
  the window keeps its 1080 px with all four buttons and grows taller instead;
  then **Export**, **Export as…**, the build button and, once anything is
  on record, **Update SolidWorks**. The build button is one button whose label
  follows the record and the read: **Build** (primary), **Build parts**
  (primary) while rows a later phase builds hold the layout back, or **Build
  again…** (secondary) once an assembly is on record — Update SolidWorks is then
  the primary. A button that changes weight is made again, since a
  `widgets.Button`'s weight is set when it is made; a disabled primary is grey
  `#b5b5b5` with white text.

### What the footer says, and what is enabled

The sentence, its colour, and what both buttons say and allow are one
decision, `ui_text.workbook_footer`, asked on every re-plan (a read, a failed
read, a fix chosen or undone, an export, a press, each poll while a job runs,
a job collected). In order, the first that holds:

| State | Sentence | Build button | Update SolidWorks |
|---|---|---|---|
| a build running | *Building in SolidWorks: part 2 of 4, Gear_m1.5_N68…* (§9, *A job in SolidWorks*) | off | off |
| an update running | *Updating SolidWorks: Gear_m1.5_N68…* | off | off |
| the file gone or unreadable, or planning failed | the read's own sentence, red | off | off |
| a refused Export, a fix still chosen | the refusal, red | off | off |
| a fix chosen | *1 fix chosen: Export writes it into the workbook, and Build and Update SolidWorks wait for that, so the workbook and SolidWorks agree.* (*Build waits* when nothing is on record) | off | off |
| after Export wrote cells into a workbook with formulas | *Export wrote cells that formulas in the workbook may depend on: open and save it in Excel so they recalculate; Build and Export wait for that save.* (with a record: *Build, Update SolidWorks and Export wait*) | off | off |
| a record from a newer Gear Generator | *The record of what was built, Reducer_12to1.workbook.json, cannot be read: it was written by a newer Gear Generator (schema 3, this one reads 2). It is left alone, so Build and Update SolidWorks wait.*, red | off | hidden |
| an error, a gearbox not checked, or a gear not placed | *Fix the workbook before building: Gears!F3: … (2 more under Checks)*, or the gate's own sentence, red | off | off |
| nothing buildable | *Nothing in this workbook can be built yet: InDog is a dog ring: dog rings are built in phase W8, with modes.* | off | — |
| no output folder, or one that does not exist | *Choose an output folder …* / *The output folder C:\Parts\Reducer_12to1 does not exist; make it, or change it on the Box sheet.*, red | off | not held by it |
| the plan refused | its sentence, red (a file in the way of every revision up to `_r99`; two files of one name; a Part name that is one of the gearbox's own file names, naming its cell) | off | — |
| ready | *Ready: Build makes 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM in C:\Parts\Reducer_12to1.* | **Build**, on | hidden |
| ready, parts already built | *Ready: Build makes Reducer_12to1_Layout and Reducer_12to1.SLDASM in …, reusing the 4 parts already built.* (and *reusing Reducer_12to1_Layout and …* after an assembly that failed) | **Build**, on | shown |
| ready at a later revision | the ready sentence and why: *Reducer_12to1.SLDASM is already in C:\Parts\Reducer_12to1, and a build never overwrites a file. So this build is Reducer_12to1_r2, beside it; nothing is overwritten.* | **Build**, on | — |
| ready, a part's own file name taken | the ready sentence and, one sentence per reason, whose file it is: *Gear_m1.5_N17.SLDPRT is already there, with no record that this workbook built it (a build that was interrupted can leave such a file), so G1's part is made as Gear_m1.5_N17_r2.* · *OutputGear.SLDPRT is already there, built from Box.xlsx, so …* · *… built from this workbook for values G2 no longer has, so …*, the last ending *; nothing is overwritten.* | **Build**, on | — |
| a copied workbook (its record names another workbook still on disk) | *Ready: Build makes 4 parts, Reducer_12to1_r2_Layout and Reducer_12to1_r2.SLDASM in C:\Parts\Reducer_12to1. This workbook is a copy of C:\Parts\Reducer_12to1.xlsx, which is still there, so the record that came with it is that workbook's, and so are the SolidWorks files it lists: Build makes this workbook's own gearbox beside them, sharing and overwriting nothing.*, green | **Build**, on | hidden |
| rows a later phase builds | *Ready: Build parts makes 2 parts in …; the layout and assembly wait for a later phase: Shafts!A4: P1 is mounted on C, …* (*The 4 parts are built already, so Build parts has nothing to make; …* when all are) | **Build parts**, on (off when nothing to make) | shown once parts are |
| parts on record, the layout part saved, no assembly | the ready sentence, then Update's reason: *Reducer_12to1_Layout.SLDPRT was saved but its assembly was not made: Build carries on with it, and Update SolidWorks waits until it has.* | **Build**, on | shown, off |
| parts from Build parts, and a change only a new part takes | the ready sentence, then *Gear_m1.5_N17 (G1): Flank changed from involute to arcs, which its values cannot carry, so it needs a new part. Update SolidWorks waits until Build has made what that needs.* (nothing is assembled yet, so Update never offers a build-again) | **Build** / **Build parts**, on | shown, off |
| built, the workbook changed since | *Update SolidWorks will change G2's values (Gear_m1.5_N68), move S2 and S3 in Reducer_12to1_Layout, and re-place G2, G3 and G4.* | **Build again…**, on | on, primary |
| built, nothing on record differs | *SolidWorks already matches the workbook on record; Update SolidWorks checks it live and puts right anything changed there.* | **Build again…**, on | on, primary |
| built, a change Update cannot carry | *Gear_m1.5_N17 (G1): Flank changed from involute to arcs, which its values cannot carry, so it needs a new part. Update SolidWorks offers to build again as Reducer_12to1_r2.* (*(and 1 other change Update SolidWorks cannot carry)* with more) | **Build again…**, on | on, primary |
| … and the build it needs cannot go | *Gear_m1.5_N17 (G1): …, so it needs a new part. The new revision it needs, Reducer_12to1_r2, cannot be built yet:* and why, red | off | off |
| built, a recorded file gone | *Gear_m1.5_N68.SLDPRT is no longer in C:\Parts\Reducer_12to1: it was moved, renamed or deleted since it was built, so Update SolidWorks offers to build again as Reducer_12to1_r2.*, red | **Build again…**, on | on |

Every row is decided from the plans' and the record's fields, never from the
words of another sentence. A greyed button always has its reason on screen —
after a job's sentence too — and no sentence offers what a greyed button would
do. A part whose file name is taken by the very part a change Update cannot
carry replaces is not said again: the change's own sentence says it.

A record that cannot be read (broken, not newer) adds its sentence, red, to
whichever of the last rows holds — *… The next Build sets it aside and starts a
new one.* — with Build on and Update hidden; the next build's finish moves it to
`Reducer_12to1.workbook.json.bad-<stamp>` and starts a fresh one.

**What Update left unsaved.** Documents of the current revision that Update
SolidWorks changed and that are not saved add, once, while no job's sentence
is showing (or after an answer): *Gear_m1.5_N68, Reducer_12to1_Layout and
Reducer_12to1 have changes from Update SolidWorks that are not saved: save
them in SolidWorks to keep them. If SolidWorks closed them without saving,
press Update SolidWorks to make them again.* (*it* for one; where Update
would build again instead, the last sentence is *If SolidWorks closed them
without saving, those changes are gone.*). Nothing on the Tk thread can see
whether SolidWorks still has them open, so the sentence is true either way
(second review N2); a job that finds them closed settles it (below). An
earlier revision's documents, left behind by a build-again, are never
counted. Nothing waits for that save (W4 review B2): a part Update left
unsaved is not what its file holds, so it is not reused, and a build that
would have reused it makes that part new instead. Where the state offers that
build, the next sentence says so: *While Gear_m1.5_N68's changes are not
saved, the new revision makes G2's part new, as Gear_m1.5_N69, rather than
reuse it.* (*Build makes …* before anything is assembled). Saved in
SolidWorks, the part is reused again. The poll looks at those files' times
every second, so both sentences go once SolidWorks saves them. A part marked
mismatched is said the same way: *Gear_m1.5_N68 does not hold what the record
says, as the last job in SolidWorks found, so the new revision makes G2's part
new, as Gear_m1.5_N69, rather than reuse it.*

**Marks a job settles** (second review N2). Each job says which documents
were open in SolidWorks when it began and which it loaded from their files.
One loaded from its file holds in memory what the file holds, so its unsaved
marks go (the record's and its `.gear.json`'s) and what the job found decides
the rest: an Update that finds it holding the workbook's values clears its
mismatched mark too; one it changes is marked unsaved again. A document marked
unsaved that was not open when a job began lost Update's changes when it was
closed: its mark becomes a mismatched one (its file does not hold what the
record says), unless the file was saved since. So an Update left unsaved and
lost with SolidWorks never holds a part back for ever: the next Update reads
the files and settles it. While a document of the current revision is marked
mismatched the header reads *· SolidWorks no longer holds all of this
version*.

An Export that left the Results sheet out for a formula cell adds, once Excel
has saved since, *Export again to write the Results sheet: it waited for Excel
to recalculate.* to whichever sentence then shows.

The window's own last sentence is a note with a kind (`ui_text.Note`), kept
until the file next changes. A finished job's sentence — the build's, the
update's, or what went wrong — takes the state's place, in its own colour (a
clash is red); while a row a later phase builds is there it is followed by
*Left for a later phase: …*. If the state has gone wrong since, the two are
joined: *Built 4 parts, … Since then: Fix the workbook before building: …*.
What an Export, a Locate… or a save did marks no moment, so a state gone
wrong follows it plainly: *Exported 2 cells and the Results sheet. Fix the
workbook before building: …*. An answer to *Build again?* is always followed,
plainly, by the state it answered, which still stands: *Nothing was changed
in SolidWorks. Gear_m1.5_N17 (G1): The recipe changed …, so it needs a new
part. Update SolidWorks offers to build again as Reducer_12to1_r2.*

Warnings never hold Build back, and nor do rows a later phase builds (bevel
gears, shafts on a carrier and their copies, turned axes, sleeves, dog rings,
sliding gears, modes) for **Build parts**: a bevel, sleeve or dog row's part is
left out and listed as *later*; a gear on a carrier, on a turned axis or that
slides is an ordinary part and builds. The layout part and assembly wait for
every such row's phase: `workbook.assess.Assessment.lay_out_refusal()` refuses,
with its sentence, a provisional read, a fix not yet exported, any error, no
output folder, a gearbox not checked, any row a later phase builds, and any gear
not placed and planned, and `build_refusal()` is Build parts' gate.

**Export** is enabled whenever a good read is on screen, no job is running in
SolidWorks, and Excel is not yet to recalculate an Export, and **Export as…** with it: both
are greyed otherwise, since anything written from a provisional read — Results
included — would be worked out from old formula values. If a read fails, or the
wait starts, while Export as…'s file dialog is open, it writes nothing and the
footer says why (*Nothing was exported: …*, for the wait *Nothing was exported:
the workbook's formulas still hold Excel's old values; open and save it in
Excel first, so what is exported is worked out from what they now give.*). Export writes the
chosen fixes' cells and the Results sheet (each shaft's speed, turning and
torque; each mesh's ratio, centres needed and placed, how far off, contact
ratio; what the box was worked out as; its overall ratio from the first input
to the first output the meshes join to it, naming both, or a dash and why — not
checked, a meshing gear not laid out, a box whose modes change it, no output
joined to the input — and its size in X, Y and Z over the gears' outside
diameters and faces, with a *Not in the box size* row naming any gear it does
not count, by its row when it has no name or shares one: *G3 on Gears row 5 (an
error of its own)*) into the workbook, and says so: *Exported 2 cells and the Results
sheet. Added the column Profile shift.* A formula cell is never written, and
when it is a fix's target the sentence says what to look for rather than
asking for the formula to be typed over: *Shafts!C4 (S3 X) holds a formula, so
it was not written (the fix would make it 131.75): once Excel has recalculated,
Checks will say whether S3 sits where its meshes need it. The Results sheet was
left out until then: Export again after Excel's save to write it.* When every
cell the fix names holds a formula nothing reaches the file, so nothing a
formula reads has changed and recalculating cannot help: the sentence is a
fault, *Nothing was written: every cell the fix would change holds a formula —
Shafts!C3 (S2 X, the fix would make it 63.75); … — and Excel recalculating
cannot move them, since nothing they read has changed. Change the formula, or a
cell it reads, in Excel; the fix stays chosen until then.*, the fix stays chosen
with **Undo**, and nothing waits for Excel. Any other
cell not written is listed, *Not written: …*, and Results are left out too. The
cells and Results are two writes: if Results then fail, the cells stand, the
sentence says so (*The Results sheet could not be written: … Export again to
write it.*), and the write is still known as the app's own. Export refuses, and
re-reads, if the file was saved since the window last read it. **Export as…** writes the same to
a copy (*Reducer_12to1 (fixed).xlsx*) and leaves the fixes chosen, since the
linked workbook still lacks them.

### The live link

The window polls the file's size and modification time once a second; a save
in Excel shows within about two seconds. A file caught mid-save is retried
quietly for up to five seconds before it becomes a sentence. While the file is
in trouble the last good read stays on screen, and nothing is built from it. A
file that has gone reads *The workbook is no longer at C:\…\Reducer_12to1.xlsx.*,
the dot red, with **Locate…** to point the window at it again; nothing in the
window is lost.

The window's own Export is recognised (by the hash of what it wrote) and not
listed as an outside change. Build and Export wait for Excel only after an
Export wrote cells into a workbook that has formulas, since those may depend on
the cells written and hold Excel's old values until it recalculates and saves
(the read between is provisional; see Checks); whether it
is waiting is kept in the `.workbook.json`, so it survives a restart (the
prompt to Export Results again does not). An outside save
re-checks any fix still chosen against the new read: one no longer offered
exactly as chosen is set aside, *The workbook changed, so the fix you chose no
longer applies as it was and was set aside; choose again from Checks.* Nothing
reaches SolidWorks until a footer button is pressed: the poll plans what a press
would do, but never asks SolidWorks.

### A job in SolidWorks: Build, Build parts, Update SolidWorks, Build again…

Each press is planned again first (the strip's output folder or templates may
have changed, or a file on disk), and then submitted as **one** job to the
strip's worker: `swbuild.build_gearbox` for Build, Build parts and Build
again…, `swbuild.update_gearbox` for Update. Refused before anything is made,
in the footer: no SolidWorks to reach (*SolidWorks cannot be reached from here,
so nothing was built.* and why), or the strip mid-build (*The strip is building
in SolidWorks; build the workbook when it has finished.*); and the strip will
not start a build while a workbook's job runs. The worker itself refuses,
naming both paths, a document of the same file name already open in
SolidWorks from another folder (*C:\Old\Gear_m1.5_N68.SLDPRT is open in
SolidWorks, and it has the same file name as …; SolidWorks keeps one document
per file name, so close Gear_m1.5_N68.SLDPRT in SolidWorks and try again.*).

**While it runs** both footer buttons, Export and Export as… are off, and the
footer gives the worker's last step each second (`ui_text.progress_text`):
*Building in SolidWorks: checking Gear_m1.5_N17 (1 of 3 already built)…*,
*… part 2 of 4, Gear_m1.5_N68…*, *… the layout part, Reducer_12to1_Layout…*,
*… the assembly, Reducer_12to1…*, *… checking interference…*;
*Updating SolidWorks: checking Gear_m1.5_N17 (1 of 4)…*, *… Gear_m1.5_N68…*,
*… placing the gears in Reducer_12to1…*. **Closing the window** then does not stop the job or
drop what it saves: the window stays, adds *This window closes once the build
has finished and what it saved is on record; it stays open if something needs
saying.*, collects the answer, writes the sidecars and the record, and closes —
unless the job's sentence is a fault, which it stays open to show.
**Closing the strip's window** while any Workbook window has a job pending
is guarded the same way (`gui.CloseGuard`; the worker is a daemon thread, so
the app ending mid-job would leave what SolidWorks saved off the record):
each such window is closed as above, the strip says *Gear Generator closes
once a workbook's job in SolidWorks has finished and what it saved is on
record; it stays open if something needs saying.*, and the app closes once
no job is pending and every one of those windows has closed. If one stayed
open to show a fault, the app stays too: *Gear Generator stayed open: a
workbook's job has something to say in its window. Close this window again to
quit.* With nothing pending it closes at once. Since the second review the
strip's own build is waited for the same way (*Gear Generator closes once the
strip's build in SolidWorks has finished and what it saved is on record; it
stays open if something needs saying.*): its poll collects it and writes its
`.gear.json`, then the app closes. A Workbook window with a question open —
*Build again?*, or *Moved, or a copy?* — is never destroyed under it: *Gear
Generator closes once the question open in a Workbook window is answered.*,
and the window closes once the answer is acted on (after a job, if the answer
started one).

**When SolidWorks does not answer** — held by a modal dialog, say; nothing
can cancel a call it does not answer — closing a window a second time asks,
titled *Close anyway?*, defaulting to No: *SolidWorks has not answered yet:
the build is still running there, perhaps held up by a dialog open in
SolidWorks. Close this window anyway? Files SolidWorks saves from now are not
put on record by this window, and nothing will be overwritten: the next Build
finds them, checks them in SolidWorks and reuses what it can.* (for an
update: *… What it changes from now is not put on record, so this window will
not ask for those documents to be saved, and nothing will be overwritten.*).
Closing the strip's window a second time asks *Quit anyway?*: *SolidWorks has
not answered yet: a job is still running there, perhaps held up by a dialog
open in SolidWorks. Quit anyway? Files SolidWorks saves from now, and
documents it changes, are not put on record by this session, and nothing will
be overwritten.* (adding *The workbook's next Build finds the files its build
saved, checks them in SolidWorks and reuses what it can.* when a workbook's
build is among the jobs). Yes closes; No goes on waiting.

**The journal.** Before a build's job is submitted, the record gains what it
is about to make (`pending`: each new part with its gears and form, the
layout part, the assembly), written through the same guarded write as a
finish; the finish takes it out, and so does collecting a job the worker
refused. So a build interrupted after SolidWorks saved some of it — the app
killed, a crash, a power cut, or *Close anyway?* — leaves files the next plan
knows: a pending part on disk with no `.gear.json` is planned for reuse when
it is the same part (the same plan), checked live like any reused part, and
given its `.gear.json` at the finish; a pending layout part is reused once the
live check finds it holding the shafts' globals, planes and axes; a pending
assembly is gone beside, with *Reducer_12to1.SLDASM was saved by a build that
was interrupted before it was put on record, and a build never overwrites a
file. So this build is Reducer_12to1_r2, beside it; nothing is overwritten.*
A pending path that is not on disk is dropped. A finish that raises writes
nothing, but the journal is still on record: *What the build saved could not
all be put on record — …. What SolidWorks saved stays on disk, and the next
Build finds it from the journal written before the build, checks it in
SolidWorks and reuses what it can.*

**The finish** writes what it can whatever raises: each part's `.gear.json`
and the record stand alone, so one that cannot be written stops neither the
others nor the record, and the sentence says what was not written (*The
part's record Gear_m1.5_N68.gear.json could not be written beside it: …*,
*The record of what was built, …, could not be written: …*, or *What the build
saved could not all be put on record — …*). A job the worker answered with a
raise is a refusal before anything was made or changed (its own checks, or
the connection), said as it came; anything else is named (*The build stopped
before it made anything — KeyError: …*).

**Build** makes, in this order, reusing whatever is already built:

1. Each part (the strip's own plan for its row; one file for identical rows).
   A part already built — on record, or a `.gear.json` beside its path naming
   this workbook (or a path it had before it was moved) — is reused only after
   it is opened and found, live, to hold exactly the values the row asks and
   every feature its `.gear.json` lists. Otherwise nothing is made, every
   document to reuse is still checked, and the record notes what was found
   (`mismatched`, with the file's time), so the next press makes that part new
   rather than fail the same check again: *Nothing was built.
   Gear_m1.5_N68.SLDPRT does not hold what the workbook asks of it, so it
   cannot be reused: "No. of Teeth" is 68 there and 69 here. The next press of
   Build again… makes G2's part new rather than reuse Gear_m1.5_N68; nothing
   is overwritten.* (An update lost when SolidWorks closed unsaved, the
   unchanged file saved later, leaves exactly that.) A part Update left
   unsaved is not reused either, and is made new at once.
2. The layout part, `Reducer_12to1_Layout.SLDPRT`: for each shaft, the planes
   offset from Right by X and from Top by Y — the base plane itself at 0 — and an
   axis through them named `S2 Axis`. Only a non-zero coordinate gets a plane
   and a global (`"S2 X"`, signed); the shafts' sides are recorded. A layout
   saved by a build whose assembly then failed is reused, checked live.
3. The assembly, `Reducer_12to1.SLDASM` (both named for the Box's Name): the
   layout part inserted and fixed at the origin, then each gear inserted,
   placed with its face's middle on its shaft and turned to its phase, and
   fixed. It is static: nothing turns until W5. SolidWorks names the components
   (`Gear_m1.5_N68-1`); the record maps each gear to the name SolidWorks kept,
   and they are never renamed.
4. Interference, as for a pair: *…; no interference between the gears.*, or a
   red *Check: G1 and G2 interfere, 12.345 mm³; look at their mesh in
   Reducer_12to1.SLDASM.* — *at their mesh* only when the two are a listed mesh,
   else *look where they meet* (a widened gear touching its neighbour on the
   same shaft); *an interference of 1.2 mm³ that SolidWorks could not name*;
   or *Interference could not be checked: … Look at each mesh in
   Reducer_12to1.SLDASM by eye.*

The sentence after (`ui_text.gearbox_status`): *Built 4 parts,
Reducer_12to1_Layout and Reducer_12to1.SLDASM; no interference between the
gears. 1 thing to do by hand: Assign a material to each of the 4 parts; the
build leaves it unset.* A step that fails leaves what was saved saved, and says
how to carry on: *… The layout and assembly were not attempted. Press Build to
carry on: what was built is reused.*, *Built 4 parts and Reducer_12to1_Layout;
the assembly Assem1 was left open, unsaved; place G2: …. Press Build to try
the assembly again: the parts and layout are reused.* A document SolidWorks
never made asks for what to change first rather than for a press that would
fail the same way: *Built 4 parts and Reducer_12to1_Layout; SolidWorks did not
make the assembly. There is no assembly template at C:\T\A.asmdot. Set an
assembly template SolidWorks can use (the Box sheet's Assembly template, else
the strip's), then press Build: the parts and layout are reused.* A job that
stopped between documents (a COM error, SolidWorks gone) says where, and what
was not attempted: *Built 2 parts. The job stopped during the layout part:
SolidWorks did not complete SaveAs3: … The assembly was not attempted. Press
Build to carry on: what was built is reused.* A build again that stopped
before its layout part saved names **Build again…**, which the button still
reads. **Build parts** is the same job with no layout or assembly, through the
same reuse, so it resumes a batch that stopped.

**Update SolidWorks** carries the latest read into what the current revision
built (`workbook.update.classify`, then the worker): the values of each part
whose variables changed (it opens the part and sets only the globals
SolidWorks holds differently, in one rebuild), the layout part's globals for a
shaft that moved on the same side of the origin's planes, and every gear whose
frame changed re-placed in the assembly (a Z, Z± or At change is a move while
the assembly is static); then interference again. It compares with SolidWorks
live, so it stays enabled when the record says nothing differs, and puts right
an update lost or a component dragged by hand (*G4 had been moved in
SolidWorks; put back where the workbook has it*). It writes nothing into the
output folder, so a missing folder does not hold it. **It does not save**, as
the strip's Update values does not: *Updated SolidWorks: changed 1 variable in
Gear_m1.5_N68 (it now has 69 teeth; its file keeps its name), moved S2 and S3
in Reducer_12to1_Layout, re-placed G2, G3 and G4; no interference between the
gears. Save Gear_m1.5_N68, Reducer_12to1_Layout and Reducer_12to1 in SolidWorks
to keep them.* (the documents named, so the save is asked once). Only a
document that does not already hold what it should is touched, so the others
are not left modified in SolidWorks. A part keeps its file name after a value
update — N68 holding 69 teeth — and the sentence says so; a Part name of the
user's own never goes stale. The record marks each document it changed as
unsaved, with the file's time, until the file on disk is newer. "Already
holds what it should" means the text of every global in one trig unit and,
since the second review (N5), SolidWorks evaluating them as that unit would:
a part holding the degree form whose angle unit was set to radians is
updated, and is not reused. Stopped part
way, it says what it had already changed, not saved, and that pressing it
again once that is put right finishes the job (*Nothing was changed.* if
nothing had). Speeds, torques and efficiencies change nothing in SolidWorks.
A component, feature or global renamed or deleted in SolidWorks is not
something Update can put back, and its check says the way on: *Gear_m1.5_N68-1
is not in Reducer_12to1.SLDASM any more: it was renamed or deleted in
SolidWorks. Update SolidWorks cannot put that back; Build again… builds the
next revision beside it, with an assembly of its own, and leaves this one as
it is.* (a part missing a global is noted in the record, so that build makes
it new).

**A change Update cannot carry** needs the next revision: a gear, shaft or mesh
added, removed or renamed; a coordinate that changes side, or reaches or
leaves 0 (a layout plane cannot follow a global across its base plane); a part
whose stem changes (a built part's file is never renamed); a structural change
to a part (`swbuild.structural_change`: another recipe or kind, a bore or a
shift that appears or goes, …), once fields a kind ignores are set aside (a
spur gear's Hand, a Part name equal to the default); two rows that shared a
part and now differ; a recorded file no longer on disk. Such a gear's row
reads *needs a new part*. Update SolidWorks then asks instead of updating, and
**Build again…** always asks: a `messagebox.askyesno` titled *Build again?*,
defaulting to No (`ui_text.build_again_question`):

*Gear_m1.5_N17 (G1): Flank changed from involute to arcs, which its values
cannot carry, so it needs a new part. Build again as Reducer_12to1_r2? That makes a new part for G1
(Gear_m1.5_N17_r2), reuses 3 parts that have not changed and makes a new layout
part and assembly (Reducer_12to1_r2_Layout and Reducer_12to1_r2.SLDASM).
Nothing is overwritten, and Reducer_12to1.SLDASM stays as it is on disk, but it
shares the 3 reused parts: a later Update SolidWorks that changes one of them
changes Reducer_12to1.SLDASM too.*

A part made new although one was built says why: *G2's part is new because
Gear_m1.5_N68 has changes from Update SolidWorks that are not saved; to reuse
it instead, answer No and save it in SolidWorks first (if SolidWorks has
closed it since without saving, those changes are gone, and it cannot be
reused).* (or *… does not hold what the record says, as the last job in
SolidWorks found.*), and a part whose own
file name is taken by something else says whose it is, as the ready sentence
does. Pressed with nothing Update cannot carry, it opens *Nothing on record
needs a new revision.* With no earlier assembly (parts from Build parts — the
question is not reached then, but never says otherwise) it ends *Nothing is
overwritten, and what is already built is left as it is.* No leaves
everything as it was, and the footer gives the answer followed by the reason
it was asked (*Nothing was changed in SolidWorks. …*); Yes builds, unless what
would be built is no longer what the question described — the workbook saved,
or a part file come or gone, while it was open (*The workbook changed while
the question was open, so nothing was built; press Build again… once more if
it still applies.*).

**Revisions.** The first build is revision 0, `<Name>_Layout.SLDPRT` and
`<Name>.SLDASM`; the next is 2, `<Name>_r2_Layout.SLDPRT` and `<Name>_r2.SLDASM`
beside them, then 3, and so on. A build takes the smallest revision whose
layout and assembly paths are both free on disk and that no revision on record
used — so a layout or assembly on disk with no record, or left by hand,
moves the build to `_r2` with the reason in the ready sentence, never to a
dead end — except that a revision whose assembly failed is carried on (unless
the last build found its layout part not as recorded). Only the layout part
and the assembly move a build to another revision. A part's suffix is its
own (W4 review S5): a new part whose file name is taken by anything else is
the smallest free `<stem>_r<k>` (`Gear_m1.5_N17_r2`), whatever the gearbox's
revision, and the ready sentence says whose the file in the way is. A Part
name that would be one of the gearbox's own file names (`<Name>`,
`<Name>_Layout`, `<Name>_r<n>`, …) is refused, naming its cell. Nothing is
ever overwritten: the earlier revision's files stay, and its record moves to
`earlier`.

**A copied or moved workbook.** The record is found by its file name beside
the workbook, so a folder copied whole brings the original's record, whose
output folder is absolute. While the workbook that record names is still on
disk, this one is a copy: the record and the files it lists are the
original's, so nothing is shown as built, Update SolidWorks is hidden, and
Build makes the copy's own gearbox beside those files (at `_r2` and with
`_r2` parts when the original built into the same folder), sharing and
overwriting nothing; its first build starts a record of its own. Paths are
compared as files (second review N1a): a mapped drive and its UNC path, a
`subst` drive or a junction are one workbook, never a copy of itself. When the
named workbook is gone, the window does not adopt the record silently — it
may be one of two copies of an original since deleted, renamed or offline —
but asks once, after the plan that found it, titled *Moved, or a copy?*,
defaulting to No: *The record of what was built beside this workbook was
written for C:\Parts\Reducer_12to1.xlsx, which is not there any more. Was
this workbook moved or renamed from it? Yes: the record is this workbook's,
and Update SolidWorks and Build carry on from what it lists. No: this workbook
is a copy, so Build makes its own gearbox beside those files, sharing and
overwriting nothing. The answer is kept in the record.* Until it is answered
the record is planned as a copy's, and the footer says so (*The record that
came with this workbook was written for …, which is not there any more: until
you say whether this workbook was moved or renamed from it, Build makes this
workbook's own gearbox beside the files it lists, sharing and overwriting
nothing.*). Yes adopts the record — the old path kept in `moved_from`, so the
parts' `.gear.json`, which name it, are still this workbook's; No keeps it the
other workbook's (`copy_of`). The answer holds for the session even if the
record cannot be written. The Gears table shows each part to build under the
name the build will give it (`plan.part_of`).

### The record, `Reducer_12to1.workbook.json`

Beside the workbook, named for its file (`store.link_record_path`): what
SolidWorks holds, not the workbook's cells — the read it was last built or
updated from (`digest`), each part of the current revision with its gears, the
revision that made it, its spec and the variables last put in it; the current
revision's name, layout part, assembly, each shaft's position and side and its
globals, planes and axis, the listed meshes, and each gear's component name and
frame; earlier revisions (paths only); the documents Update left unsaved, with
their times; the documents found not as recorded — by a live check, or
marked unsaved and found closed — (`mismatched`, with their times); the
workbook's earlier paths (`moved_from`); the answer *No: a copy* (`copy_of`);
a build's journal (`pending`, and `pending_for`, the workbook whose build wrote
it); and the app's own last Export (`own_digest`, `recalc`). Each
part also gets its `.gear.json`, naming the workbook and the rows it serves;
Update marks the one of a part it changed `unsaved_since`, so it never claims
values the file may not hold.

Nothing trusts it alone: planning checks every path exists, reuse and Update
compare with SolidWorks live, and *unsaved* and *mismatched* are cleared by
the files' times. It
is read on every re-plan without ever being moved or written; just before a
job's finish writes it, it is read again, and written atomically. A record
from a newer Gear Generator is left byte for byte as it is (both buttons wait);
one that cannot be read is set aside as `.bad-<stamp>` by the next build, never
deleted. On disk `schema_version` stays 1, with the real schema in
`link_schema_version` (2), so a build from before W4 that rewrites the file
keeps its parts (it reads only the keys it knows, so the new ones are dropped,
never a fault). **Locate…** carries the record: a copy is written beside the
workbook's new place with its `workbook` updated, unless one is already there,
and the old one is left where it was (*The record of what was built stays
beside the workbook's old place: …* when it cannot be carried). A copy's
record is never carried (*… it was written for C:\Parts\Reducer_12to1.xlsx,
so it is that workbook's record and lists that workbook's files, not this
one's.*); one whose workbook is gone and unanswered is carried as it is, not
adopted, so the question is asked at the new place.

### Where it differs from PLAN-WORKBOOK §5

- A fix is a button that takes it at once (checked straight away, listed with
  **Undo**), not one of E2's radio rows.
- Checks lists problems only; the plan's *passed checks, one line each* are
  not shown, and a clean workbook says so in one line.
- **Re-read** is in the header beside **Open in Excel**, not in the footer, and
  the counts are the Workbook panel's readout rather than the header's.
- The change list's *what it did* gives a distance as the checks do, `G1–G2 now
  1.5 mm off`, not the plan's `1.50 off`; with several cells changed it is a line
  of its own rather than following one cell; and it also counts new and cleared
  problems by cell, which the plan's example does not show.
- "Refused at Build" (§3.4) is read against what Build makes: with parts
  only, a bevel, sleeve or dog row's part is refused and the other parts
  build, a planet's and a sliding gear's included; the footer names the first
  refused row with its phase rather than a bare *Ready*. The layout part and
  assembly refuse such a workbook outright.
- **One build button** (§5's Build and the build-again of §4.5): its label
  follows the gate and the record — Build, Build parts, Build again… — with
  Update SolidWorks beside it, primary once an assembly is built.
- **Update SolidWorks does not save** (§4.5 does not say): as the strip's Update
  values does not; the record marks what it changed as unsaved, the footer asks
  for a save in SolidWorks once, and since reuse and Update compare with
  SolidWorks live, an update lost or not saved is put right by the next press.
  Nothing waits for that save: a part Update left unsaved is made new by the
  next build rather than reused (W4 review B2, overruling W4's agreement 7),
  and so is one a build's live check found not as recorded.
- **A copied workbook** (the record beside it written for another workbook
  still on disk) builds a gearbox of its own and never touches the
  original's files; one whose record's workbook is gone asks once whether it
  was moved (and then adopts the record) or is a copy (W4 review S1, second
  review N1; §5 does not say).
- **Closing the strip's window** waits for any Workbook window's job, and the
  strip's own build, to be on record, as a Workbook window's own close does,
  and for any question open over a window; a second close while SolidWorks
  does not answer offers to quit anyway.
- **A build keeps a journal** in the record while it runs (`pending`), so what
  an interrupted build saved is reused, once checked, by the next.
- **A part keeps its file name after a value update** (`Gear_m1.5_N68` holding
  69 teeth); the sentence says so. A Part name change is structural only when
  the file name it makes changes.
- **Components are not renamed** (§4.3 finds them "by name"): SolidWorks names
  them, and the record maps each gear to the name it kept.
- **Layout globals only for non-zero coordinates** (§4.2): a shaft at X = 0 or
  Y = 0 uses the base plane, with no global, so a coordinate that changes side
  or reaches or leaves 0 is structural; a Z, Z± or At change is a move while the
  assembly is static. The revision's files are `<Name>_r<n>_Layout.SLDPRT`
  beside `<Name>_r<n>.SLDASM`.
- **§6's demonstration edit** is S2 X 63.75 → 64.5 *with* G2's teeth 68 → 69
  (and S3 X following by its formula). S2 X alone, with S3 following, fails the
  checks: G3–G4 stays on centres, but G1–G2 is then 0.75 mm off, and the window
  will not update a gearbox that does not check.
