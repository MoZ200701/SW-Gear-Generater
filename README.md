# Gear Generator

Builds parametric spur gears in SolidWorks from a form, and solves gear pairs:
given a centre distance and a ratio, it finds module and tooth counts that work,
builds both gears and mates them in an assembly.

The gear it builds is parametric in SolidWorks itself. Its sizes live in the
Equation Manager as global variables, starting with the ten a person would type
(`"No. of Teeth"`, `"Module"`, `"Bore Diameter"`, `"Pressure Angle"`, …), and
every dimension in the part is driven by them. Change `"No. of Teeth"` to 40 in
SolidWorks and the part rebuilds as a 40-tooth gear; nothing refers back to this
app.

No runtime dependencies beyond Python 3.9+ with tkinter. Building into
SolidWorks needs Windows, SolidWorks 2026 or newer, and `pywin32`.

## Running

```
python main.py
```

or, installed, `gear-generator`. On a machine without SolidWorks or `pywin32`
the window still works out, checks and draws gears and solves pairs; only
**Build** needs SolidWorks.

## Using it

1. Choose **Single gear** or **Gear pair**, and the flank: **Involute** (a true
   involute, as an equation-driven curve — the default) or **Arcs** (circular
   arcs approximating it).
2. Type the gear: module, number of teeth, pressure angle, face width, and bore
   (blank for none). Backlash and fillet radius default to 0.3 × and 0.38 ×
   module; type a value to override either.
3. A card at the foot of the panel says what the field you are typing in means
   and what your value comes to: *Module · m … here m 1.5 × z 20 = PD 30 mm ·
   tooth depth 3.375*. It follows the caret.
4. The **Derived** panel draws the gear — in **Gear pair** mode both gears
   meshed, at one scale, with the centre distance dimensioned under them — and
   lists every size it comes to, with anything worth knowing: an undercut tooth
   count, a thin tip or rim. Errors, such as a bore bigger than the root circle,
   disable **Build** and say which field to change.
5. Choose an output **Folder**. The part is saved there as `Gear_m1.5_N25.SLDPRT`
   (or the name you type), with a `Gear_m1.5_N25.gear.json` record beside it.
6. With SolidWorks open, **Build**. The status line says what was built, or
   exactly where the build stopped and what SolidWorks said. A build never
   overwrites a file: an existing name is refused before anything is made.

Material is left unset, and the status line counts it as a step to do by hand.

### Changing a built gear

**Open .gear.json** puts a built gear back on the form. With its part the active
document in SolidWorks, change a value and press **Update values**: only the
globals that differ are set, in one batch, and the part rebuilds once. A change
the equations cannot carry — the other flank recipe, or adding or removing a
bore — is refused with a sentence saying to build a new part instead.

Editing the globals in SolidWorks' own Equation Manager works just as well.

## The gear in SolidWorks

One tooth space is cut from a blank the size of the outer diameter and
patterned round the gear axis:

| Feature | What it holds |
|---|---|
| `Gear Axis` | the axis the teeth are patterned about |
| `Blank Sketch`, `Blank` | the outer diameter (`OD`) and face width (`Width`) |
| `Tooth Space Sketch`, `Tooth Space` | one space: root arc, fillets, flanks, and a chord beyond the tip |
| `Teeth` | the circular pattern, its count (`Count`) linked to `"No. of Teeth"` |
| `Bore Sketch`, `Bore` | the bore, when there is one |

Every sketch is fully defined. The build measures whether the part's Equation
Manager works in degrees or radians before writing a single global, and after
the rebuild reads every global's value back and compares it with the maths.

## Helical and herringbone gears

Choose **Helical** or **Double** (herringbone) as the Kind, and two rows appear on
each gear: **Helix angle** and **Hand**. Module and pressure angle are then the
*normal* ones — what a hob is sold by — and the tool works out the transverse
module `m / cos β`, the transverse pressure angle, the pitch diameter they make,
the lead, how far a tooth turns across the face, and the overlap ratio εβ, which
it warns about below one.

In SolidWorks the part carries the same ten globals as a spur gear, with
`"Helix Angle"`, `"Transverse Module"` and `"Transverse Pressure Angle"` ahead of
the ones that now depend on them, and `"Lead"`, `"Overrun"`, `"Path Length"` and
`"Twist Angle"` after. The tooth space is the spur sketch drawn in the transverse
plane on a **Profile Plane** one module in front of the part, swept as a cut
along a **Path Sketch** on the axis to one module past the far face, turning at a
constant rate, then patterned. A herringbone is half a gear so built from a **Mid
Plane**, patterned, and its body **Mirror**ed about that plane, so its apex is
exactly the section drawn. Change `"Helix Angle"` or `"Face Width"` in SolidWorks
and the teeth re-twist; the hand is structural, and changing it means building a
new part.

In **Gear pair** mode the two gears must share module, helix angle and kind, and
have opposite hands. Leave the Pair panel's **Helix angle** blank and **Solve**
finds, for every standard module, each tooth sum whose helix angle falls within
**Helix range**, so every exact-ratio row meets the centre distance exactly
(*β18.19° · exact*). Choosing a row writes the helix angle into both gears and
makes gear B the other hand. The assembly is mated at the transverse centre
distance, with a herringbone pair's mid-planes coincident so the apexes line up.

## Solving a pair

In **Gear pair** mode the **Pair** panel sits above the two gears, since solving
is what fills them in. Type the **Centre distance** and the **Ratio**, driven
over driver: `3` (or `3:1`) makes the second gear three times the first, and
`1:3` makes it a third. Choose a module series and **Solve**. The candidates
open beside the form — **Candidates**, in the Pair panel's own header, shows and
hides them — best first: hitting the centre distance exactly, a standard module,
no undercut, the smallest ratio error, then the larger module. Click one to put
its module and tooth counts on both gears; nothing else on the form changes, and
the Solve line then reads `64 candidates · 3 exact · m1.5 20 : 60 chosen`.

**Build** then makes both parts and an assembly, `Pair_m1.5_20T_60T.SLDASM`. The
second gear is mated at the centre distance its teeth make, turned so a tooth
meets the first gear's space, and the distance is driven by the assembly global
`"Centre Distance"`. Checking the mesh by eye is counted as a step to do by hand.

## Driving SolidWorks

The app attaches to a SolidWorks that is already running — it never starts one
— through the Running Object Table, so with several versions installed it uses
the one on screen. It needs SolidWorks 2026 (revision 34) or newer.

It only ever works in documents it made. Nothing you have open is touched.

Every SolidWorks call the build makes was first run by the probe against a live
session, and the results are committed under `probe/results/`:

```
./probe.sh                 from WSL, through the Windows Python beside SolidWorks
probe.bat                  from Windows
python -m gear_generator.probe --list
```

The probe works in scratch documents under `Documents\GearGeneratorProbe` and
closes only what it created. Its last tier builds a whole gear through this
app's own code and changes it through its equations. What it settled is in
`src/gear_generator/findings.py`, and `tests/test_findings.py` holds those
constants to the committed results.

`python -m gear_generator.swcom [--templates] [--equations]` prints what this
machine's SolidWorks looks like from here: the sessions found, the default
templates, the open documents, and the active document's equations.

## Building the executable

```
pip install pyinstaller pywin32
build.bat
```

makes `dist\Gear Generator v0.2.exe`.

## Development

```
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

The tests need no SolidWorks and no display. The build runs against a fake
SolidWorks in `tests/test_swbuild.py`.

`python -m gear_generator.gears --spec m=1.5,z=25 --recipe A` prints the build
plan for a gear — every global and every step — without SolidWorks.

`docs/PLAN.md` is the design the app was built to.
