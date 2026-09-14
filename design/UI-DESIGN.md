# Gear Generator — UI design, as built

The window as it stands in v0.1, written for whoever changes it next. The look
is Airfoil Converter's, unchanged: `theme.py` and `widgets.py` are copies of
that app's, so its `design/UI-DESIGN.md` §3–§5 (graphite colour, Libre Franklin
and JetBrains Mono, the controls) hold here word for word and are not repeated.
What is new is the arrangement, and the build flow behind the buttons.

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

### Gear — readout `Spur · involute curve`

Three segmented rows: **Kind** (Spur; Bevel, Helical and Internal greyed, with
the hint *later*), **Flank** (`Involute` · `Arcs`), and **Make**
(`Single gear` · `Gear pair`).

### Gear A — readout `m1.5 · z25 · 20° · PD 37.5 mm`

Module (every ISO 54 module in a dropdown beside it, hint *ISO 54*), Teeth,
Pressure angle (14.5, 20 and 25 in a dropdown), Face width, Bore (placeholder
*none*), Backlash (placeholder *0.3 × module*, hint *ISO: 0.02–0.05 × m*), Fillet
(placeholder *0.38 × module*), and Name (placeholder: the stem the part will be
saved as, `Gear_m1.5_N25`). A dropdown writes its value into the field and lets
go, so the field stays the one source. A half-typed gear reads out *check the
fields*.

### Gear B

The same panel for the second gear, shown only in pair mode.

### Derived — readout `PD 37.5 · OD 40.5 · RD 33.75 · base 35.238 · p 4.712`

A **120 px** outline preview of the gear — two, at a shared scale, in pair mode
— beside label and value rows. Values carry no unit; one `mm` caption heads the
column, so a long value never clips. Where a value came from a default it says
so (`0.45 · 0.3m`). Errors come first, then warnings, each once, in
`theme.ERROR`. The form is worked out again **120 ms** after the last keystroke.
An error disables **Build**.

### Pair — readout `C 60 mm · i 3 · m1.5 20:60`

Centre distance, Ratio (hint *3, or 1:3 for driven over driver*), Module
(placeholder *any*, hint *blank tries every standard one*), Series (`Series 1` ·
`1 + 2` · `+ fine`), Teeth *min* to *max* (hint *under min is undercut*),
Assembly name, and **Solve** with its summary, `12 candidates · 3 exact`. The
readout's last part appears once a candidate is chosen. Disabled in single mode.

### Output — readout: the folder, shortened from the left

Folder with **Browse**; Part template and Assembly template (the second only in
pair mode), each blank for SolidWorks' default; **Open .gear.json** with a hint
naming the record that is open.

### SolidWorks bar — readout is the connection: `● SolidWorks 2026 (revision 34.0.0) — Part1`

The dot, the headline (no document open is a good state here: this app makes
its own documents), and **Candidates** / **Hide candidates** for the flyout.
Below, what the primary button is about to do (*Build will make
Gear_m1.5_N25.SLDPRT.*, or *Update values will change 2 variables in
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
| `ui_text.py` | every readout and status sentence |
| `theme.py`, `widgets.py` | Airfoil Converter's, unchanged |
| `swbuild.py` | the build, run against the `SolidWorks` protocol |
| `store.py` | `.gear.json` records and `recent.json` |

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
