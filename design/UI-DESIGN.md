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

Three segmented rows: **Kind** (Spur; Bevel, Helical and Internal greyed, with
the hint *later*), **Flank** (`Involute` · `Arcs`), and **Make**
(`Single gear` · `Gear pair`).

### Pair — readout `C 60 mm · i 3 · m1.5 20:60`, and **Candidates** beside it

Centre distance, Ratio (hint *3, or 1:3 for driven over driver*), Module
(placeholder *any*, hint *blank tries every standard one*), Series (`Series 1` ·
`1 + 2` · `+ fine`), Teeth *min* to *max* (hint *under min is undercut*),
Assembly name, and **Solve** with its summary, `64 candidates · 3 exact · m1.5
20 : 60 chosen` — the last part once a candidate has been clicked, so the strip
says what was picked with the flyout closed. The readout's last part appears
then too.

**Candidates** / **Hide candidates** is in this panel's header, at the right
after the readout: the candidates belong to the solver. Going back to single
gear closes the flyout, since the button that would hide it goes with the panel.

### Gear A — readout `m1.5 · z25 · 20° · PD 37.5 mm`

Module (every ISO 54 module in a dropdown beside it, hint *ISO 54*), Teeth,
Pressure angle (14.5, 20 and 25 in a dropdown), Face width, Bore (placeholder
*none*), Backlash (placeholder *0.3 × module*, hint *ISO: 0.02–0.05 × m*), Fillet
(placeholder *0.38 × module*), and Name (placeholder: the stem the part will be
saved as, `Gear_m1.5_N25`). A dropdown writes its value into the field and lets
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
symbol, what, worked)`, tested for all fourteen fields in
`tests/test_ui_text.py`. The worked line is derived text like every readout: it
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
  placed at the centre distance the teeth make, `m (N_A + N_B) / 2`. Pitch
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

Under the picture in pair mode, three rows for the pair — Centre distance
`60 mm`, Ratio `3 · 20 : 60`, Contact ratio `1.671`, all from `pairs.describe` —
then a 1 px rule, then the table: captions `A · mm` and `B · mm`, the label
column 104 px, value columns 96 px. Values carry no unit; one `mm` caption heads
each column. Where a value came from a default it says so (`0.45 · 0.3m`).
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
what is off (*C +0.5 mm · i 1.2 % · undercut*), exact rows in `theme.OK`; and a
card for the chosen row: module and teeth, the centre distance and ratio they
make, the contact ratio, and whether the module is non-standard or the pinion
undercut. Clicking a row writes its
module and teeth onto both gears and changes nothing else on the form.

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
recipe or kind, or a bore that appears or vanishes) with a sentence saying to
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
| `design/canvas/` | the artboards this window was designed on, at <https://claude.ai/artifact/NZXpsX26vgcabs9fFryF7G>: `Main.dc.html` the strip in pair mode, `SingleGear.dc.html` in single mode, `FieldGuide.dc.html` every explainer card. `gen.py` makes them from the app's own maths — `.venv/bin/python design/canvas/gen.py` — and `ui.py` is Airfoil Converter's builders, unchanged |
| `design/renders/` | the same three artboards as PNGs, at 2× |

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
