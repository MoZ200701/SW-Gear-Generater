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
| Assembly (`Fixed` · `Gear mate`, hint *not yet probed* while `Gear mate` is greyed) | Pair | every pair on parallel shafts; bevel and crossed pairs are built fixed |

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
| `ui_text.py` | every readout, status sentence and explainer |
| `preview.py` | where the Derived panel's gears, and the dimension under them, go |
| `theme.py` | Airfoil Converter's, unchanged |
| `widgets.py` | Airfoil Converter's, plus `Explainer` and `draw_diagram` |
| `swbuild.py` | the build, run against the `SolidWorks` protocol |
| `store.py` | `.gear.json` records and `recent.json` |
| `design/canvas/` | the artboards, one strip each: `Main` (a spur pair), `SingleGear`, `ShiftedPair` (a solved row with profile shift), `HelicalPair` (gear B's hand following A's), `Herringbone` (grooved), `RingPair`, `CrossedPair` (opposite hands), `BevelPair`, and `FieldGuide` (every explainer card, each worked for a gear that has the field). `gen.py` writes them — `.venv/bin/python design/canvas/gen.py` — taking every word from `ui_text`, every picture from `preview.layout` and which field borrows which diagram from `widgets.py`, so they cannot drift from the window; only the HTML and the SVG diagrams are its own. `ui.py` is Airfoil Converter's builders, unchanged. The first three once lived at <https://claude.ai/artifact/NZXpsX26vgcabs9fFryF7G>, which has not been republished since |
| `design/renders/` | each artboard as a PNG at 2×, `<Board>.png`, made by `.venv/bin/python design/canvas/render.py` with headless Chrome (no window opens; a throwaway profile) and trimmed of the empty window ground |

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
  or internal bevel gear starts *B crown ·* or *B internal ·*. Build refuses
  those two until probe `bevel_planes_beyond_90` has run, in the status line,
  as the gear mate does; nothing on the form is greyed for it.
- **Preview** (`preview.layout_internal`, `preview.layout_bevel`): a pinion is
  drawn inside its ring, the rim a plain circle, the pinion turned half its
  pitch; a bevel gear is its axial section, both halves, with the pitch cone and
  axis dashed, and a bevel pair is the two sections meeting at the apex with
  gear B turned Σ, dimensioned `R 67.082 mm · Σ 90°`. A crossed pair is drawn as
  a parallel one with `· Σ 90°` after the centre distance.

## 9. The Workbook window (W2, docs/PLAN-WORKBOOK.md §5)

A second window, opened by **Import workbook…** in the Gear panel's header (a
file dialog first), and by **New workbook…**, which writes a blank template from
the schema and opens it in Excel. It is a `Toplevel` 720 px wide, sharing the
strip's theme, widgets and SolidWorks worker; the strip is untouched. Artboards
`WorkbookReady` and `WorkbookError`, drawn by `gen.py` from a real workbook
written, read, checked and planned by the app, with every line from `ui_text`.

Top to bottom:

- **Header**: the file's name; `linked · read 14:02:31 · open in Excel`
  (`ui_text.workbook_read_line`), the dot green while linked, red when the file
  has gone or will not read; **Open in Excel** and **Re-read**.
- **Workbook** (readout `3 shafts · 4 gears · 2 meshes · no modes`): the file's
  path, the Box's Name and the output folder, with where it came from (*from the
  Box sheet*, or *the strip's Output* when the Box leaves it blank).
- **Gears** (readout `4 parts to build · 1 later`): one row per gear — gear,
  shaft, kind, teeth, module, face, the part's name, and a dot with what will
  happen: *to build*, *the same part as G1*, *later · phase W6*, or *see
  Checks* in red. Values are shown as typed, a bad one included (`68.5`).
- **Checks** (readout `1 error · 1 warning`): errors first, in red, then the
  strip's own warnings, each beginning with the cell it names (`Gears!F3: …`).
  *No problems: every row reads, and every gear works out.* when clean.
- **Since the last read** (readout `3 changes · 14:02:31`): what the last save
  changed, one line per cell, in the mono face (`Gears!F3 G2 Teeth 68 → 68.5`).
- **Footer**: one sentence (`ui_text.workbook_status`, then `many_status` after
  a build), green when Build can go ahead, and **Build parts**, disabled while
  there is an error or nothing to build.

The live link polls once a second, as the strip's SolidWorks link does; a
change appears within about two seconds of a save. Nothing reaches SolidWorks
until Build parts is pressed.

What the footer says and whether Build parts is enabled is one decision,
`ui_text.workbook_state`, asked after every read, failed read, build start and
build end: Build waits for a good current read, an existing output folder and
no errors, and a save during a build is reported after it (*Built 4 parts.
Since then: …*). The header adds *· parts built from this version* or *·
changed since its parts were built* from the `.workbook.json` beside the file.
A workbook that has gone shows **Locate…**. The window will not close while a
build is running, and the strip will not start one while a workbook's is.

The end view, the "worked out as" line, Export and the fixes come in W3.
