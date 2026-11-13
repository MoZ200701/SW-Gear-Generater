"""Build gear pairs through the tool on SolidWorks, and turn the ones that turn.

python.exe probe/gear_pairs_check.py <repo src> <output folder under C:\\> [--only NAME ...] [--log FILE]

Probe gear_mate measured the gear mate between two plain cylinders. This builds
real pairs with the tool's own planners and ``swbuild.build_pair`` — so the
mates, flips and placements are the ones the app makes — and, for a pair built
to turn, drives gear 1 through 30° and reads both gears' turns back:

* ``spur``: 20 / 40, module 2, motion "gear mate". Gear 2 must turn half as far
  as gear 1, the other way.
* ``ring``: a 20-tooth pinion in a 60-tooth ring, module 2, motion "gear mate".
  ``pair.py`` puts the ring first and flips the gear mate the other way from an
  external pair, by reasoning alone; here the pinion must turn three times as
  far as the ring, the SAME way.
* ``crown`` and ``internal``: a crown bevel pair (20 / 40 at 120°, the 40 is the
  crown) and an internal bevel pair (16 / 40 at 120°), built fixed.

Gear 1 is driven by an angle mate between its Top plane and the assembly's,
made after the build, linked to a global and changed by an indexed put — the
route probe gear_mate drove its cylinder by. A turn is read from each
component's Transform2 as the angle of its X axis about Z. The teeth are then
checked for interference again: a gear mate flipped the wrong way turns gear 2
against gear 1, and the teeth run into each other.

Only documents this run made are closed, by exact title, the assembly first and
its modified parts saved before (SolidWorks 2024 asked about them in a modal
dialog otherwise). Nothing open before the run is touched.
"""

import dataclasses
import math
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
ONLY = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--only"]
# An experiment, never a default: build every gear mate with Flip the other way from pair.py's.
INVERT_FLIP = "--invert-flip" in sys.argv
LOG_PATH = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(OUT, "gear-pairs.log")

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from gear_generator import findings, swbuild, swcom  # noqa: E402
from gear_generator.gears import kind_for, pair  # noqa: E402
from gear_generator.spec import GearSpec  # noqa: E402
from gear_generator.store import same_path  # noqa: E402
from gear_generator.swcom import call  # noqa: E402

LOG = []
DRIVE_FROM, DRIVE_TO = 10.0, 40.0   # degrees
MATE_ANGLE, ALIGN_CLOSEST = findings.MATE_ANGLE, 2


def say(line=""):
    print(line, flush=True)
    LOG.append(line)


def run(worker, fn, timeout=2400):
    value, error = worker.submit(fn).wait(timeout=timeout)
    if error is not None:
        raise error
    return value


def documents(app):
    out, doc = [], call(app, "GetFirstDocument")
    while doc is not None:
        out.append(doc)
        doc = call(doc, "GetNext")
    return out


def titles(session):
    return [str(call(d, "GetTitle")) for d in documents(session._app)]


def by_path(app, path):
    """An open document by its file: a build reports the title it had before it was saved."""
    return next((d for d in documents(app) if same_path(str(call(d, "GetPathName") or ""), path)), None)


def turn_deg(component):
    data = call(call(component, "Transform2"), "ArrayData")
    return math.degrees(math.atan2(float(data[1]), float(data[0])))


def unwrap(delta):
    return (delta + 180.0) % 360.0 - 180.0


def planes(doc):
    out, feature = [], call(doc, "FirstFeature")
    while feature is not None:
        if str(call(feature, "GetTypeName2")) == "RefPlane":
            out.append(feature)
        feature = call(feature, "GetNextFeature")
    return out


def mates(asm):
    out, feature = [], call(asm, "FirstFeature")
    while feature is not None:
        if str(call(feature, "GetTypeName2")) == "MateGroup":
            child = call(feature, "GetFirstSubFeature")
            while child is not None:
                out.append(child)
                child = call(child, "GetNextSubFeature")
        feature = call(feature, "GetNextFeature")
    return out


def drive(session, asm_path, path_1, path_2):
    """Gear 1 turned DRIVE_FROM -> DRIVE_TO by an angle mate on a global; both turns, and interference after."""
    app = session._app
    asm = by_path(app, asm_path)
    if asm is None:
        raise RuntimeError(f"{asm_path} is not open")
    components = list(call(asm, "GetComponents", True) or ())
    first = next(c for c in components if same_path(str(call(c, "GetPathName")), path_1))
    second = next(c for c in components if same_path(str(call(c, "GetPathName")), path_2))
    out = {"gear1": str(call(first, "Name2")), "gear2": str(call(second, "Name2")),
           "gear1_fixed": bool(call(first, "IsFixed")), "as_built": (turn_deg(first), turn_deg(second))}
    top = str(call(planes(call(first, "GetModelDoc2"))[1], "Name"))
    call(asm, "ClearSelection2", True)
    feature = call(first, "FeatureByName", top)
    if not (call(feature, "Select2", False, 1) and call(planes(asm)[1], "Select2", True, 1)):
        raise RuntimeError("gear 1's Top plane and the assembly's could not both be selected")
    before = [str(call(m, "Name")) for m in mates(asm)]
    call(asm, "AddMate5", MATE_ANGLE, ALIGN_CLOSEST, False, 0.0, 0.0, 0.0, 1.0, 1.0, math.radians(DRIVE_FROM),
         math.radians(DRIVE_FROM), math.radians(DRIVE_FROM), False, False, 0, swcom._out_long())  # noqa: SLF001
    call(asm, "ClearSelection2", True)
    made = [m for m in mates(asm) if str(call(m, "Name")) not in before]
    if len(made) != 1:
        raise RuntimeError(f"the drive angle mate made {len(made)} mates")
    made[0].Name = "Drive"
    dims = []
    display = call(made[0], "GetFirstDisplayDimension")
    while display is not None:
        dims.append(call(display, "GetDimension2", 0))
        display = call(made[0], "GetNextDisplayDimension", display)
    dim = next(d for d in dims if abs(float(call(d, "SystemValue")) - math.radians(DRIVE_FROM)) < 1e-9)
    eqm = call(asm, "GetEquationMgr")
    index = int(call(eqm, "Add2", -1, f'"Drive"= {DRIVE_FROM:g}', True))
    link = int(call(eqm, "Add2", -1, f'"{call(dim, "Name")}@Drive"= "Drive"', True))
    if index < 0 or link < 0:
        raise RuntimeError(f"the drive global or its link was refused ({index}, {link})")
    call(asm, "ForceRebuild3", False)
    a0, b0 = turn_deg(first), turn_deg(second)
    session._build_doc = asm  # noqa: SLF001 - interference_count reads the build's document
    out["interference_at_drive_from"] = session.interference_count()
    swcom._put_indexed(eqm, "Equation", index, f'"Drive"= {DRIVE_TO:g}')  # noqa: SLF001
    call(asm, "ForceRebuild3", False)
    a1, b1 = turn_deg(first), turn_deg(second)
    out["turn"] = {"gear1": unwrap(a1 - a0), "gear2": unwrap(b1 - b0)}
    out["interference_at_drive_to"] = session.interference_count()
    return out


CASES = {
    "spur": dict(specs=(GearSpec(module="2", teeth="20", face_width="10", bore="8"),
                        GearSpec(module="2", teeth="40", face_width="10", bore="8")), motion="gear mate"),
    "ring": dict(specs=(GearSpec(module="2", teeth="20", face_width="10", bore="8"),
                        GearSpec(module="2", teeth="60", face_width="10", teeth_side="internal")), motion="gear mate"),
    "crown": dict(specs=(GearSpec(kind="bevel", module="3", teeth="20", mate_teeth="40", shaft_angle="120",
                                  face_width="15", bore="10"),
                         GearSpec(kind="bevel", module="3", teeth="40", mate_teeth="20", shaft_angle="120",
                                  face_width="15", bore="10")), motion="fixed"),
    "internal": dict(specs=(GearSpec(kind="bevel", module="3", teeth="16", mate_teeth="40", shaft_angle="120",
                                     face_width="15", bore="10"),
                            GearSpec(kind="bevel", module="3", teeth="40", mate_teeth="16", shaft_angle="120",
                                     face_width="15", bore="10")), motion="fixed"),
}


def expected_turn(name, specs):
    """How far gear 2 turns per degree of gear 1, signed: the assembly's gear 1 is the ring in a ring pair."""
    a, b = (int(s.teeth) for s in specs)
    if name == "ring":
        return 60 / 20          # gear 1 is the 60-tooth ring, gear 2 the 20-tooth pinion, the same way round
    return -a / b


def close_made(session, made):
    """Save the run's modified parts, then close what it made, assemblies first."""
    app = session._app
    docs = [d for d in documents(app) if str(call(d, "GetTitle")) in made]
    for doc in docs:
        if int(call(doc, "GetType")) == 1 and call(doc, "GetPathName") and call(doc, "GetSaveFlag"):
            call(call(doc, "Extension"), "SaveAs3", str(call(doc, "GetPathName")), 0, 1, swcom._null_dispatch(),  # noqa: SLF001
                 swcom._null_dispatch(), swcom._out_long(), swcom._out_long())  # noqa: SLF001
    for kind in (2, 1):
        for doc in [d for d in documents(app) if str(call(d, "GetTitle")) in made]:
            if int(call(doc, "GetType")) == kind:
                call(app, "CloseDoc", str(call(doc, "GetTitle")))
    return titles(session)


def main():
    os.makedirs(OUT, exist_ok=True)
    worker = swcom.Worker()
    label = run(worker, lambda s: (s.label, s.pid), 120)
    say(f"attach  {label[0]}, PID {label[1]}")
    say(f"findings gear mate {findings.GEAR_MATE_ROUTE}/{findings.MATE_GEAR} numerator first "
        f"{findings.GEAR_MATE_NUMERATOR_FIRST} external flip {findings.GEAR_MATE_EXTERNAL_FLIP}; "
        f"crown {findings.BEVEL_CROWN_SECTION_X_SIGN} internal {findings.BEVEL_INTERNAL_SECTION_X_SIGN}")
    before = run(worker, titles, 120)
    say(f"open    before: {len(before)} documents")
    ok_all = True
    try:
        for name, case in CASES.items():
            if ONLY and name not in ONLY:
                continue
            specs = case["specs"]
            paths = [os.path.join(OUT, f"{name} gear {i + 1}.SLDPRT") for i in range(2)]
            path_pair = os.path.join(OUT, f"{name} pair.SLDASM")
            plans = []
            for s, p in zip(specs, paths):
                g = kind_for(s)
                plans.append(g.plan(s, g.derive(s), g.recipe_for(s), "", p))
            assembly = pair.assembly_plan(specs[0], specs[1], paths[0], paths[1], "", path_pair, motion=case["motion"])
            gear = next((op for op in assembly.ops if getattr(op, "kind", "") == "gear"), None)
            if gear is not None and INVERT_FLIP:
                swapped = dataclasses.replace(gear, flip=not gear.flip)
                assembly = dataclasses.replace(assembly, ops=tuple(swapped if op is gear else op for op in assembly.ops))
                gear = swapped
                say(f"EXPERIMENT {name}: the gear mate's Flip is inverted from pair.py's")
            say(f"case    {name}: {' / '.join(f'{s.kind} {s.teeth_side} {s.teeth}' for s in specs)}, "
                f"motion {case['motion']}" + (f", gear mate ratio {gear.ratio} flip {gear.flip}" if gear else ""))
            started = time.monotonic()
            result = run(worker, lambda s: swbuild.build_pair(s, plans[0], plans[1], assembly))
            for line in result.log_lines():
                LOG.append("        " + line)
            say(f"build   {name}: ok={result.ok} in {time.monotonic() - started:.1f} s; skipped={result.skipped!r}")
            built = bool(result.ok and result.assembly is not None and result.assembly.ok)
            if result.assembly is not None:
                say(f"  asm   {result.assembly.document}: failures={result.assembly.failures} "
                    f"checks={result.assembly.checks} done={[d for d in result.assembly.done if 'interfer' in d]}")
            clean = built and not result.assembly.checks
            if built and case["motion"] == "gear mate":
                # The assembly's gear 1 is the ring in a ring pair (pair.assembly_plan).
                first, second = (paths[1], paths[0]) if name == "ring" else (paths[0], paths[1])
                seen = run(worker, lambda s: drive(s, path_pair, first, second), 600)
                ratio = seen["turn"]["gear2"] / seen["turn"]["gear1"] if seen["turn"]["gear1"] else math.nan
                want = expected_turn(name, specs)
                say(f"  drive {name}: {seen['gear1']} turned {seen['turn']['gear1']:.6f}°, "
                    f"{seen['gear2']} {seen['turn']['gear2']:.6f}°: ratio {ratio:.6f} (want {want:.6f}); "
                    f"gear 1 fixed {seen['gear1_fixed']}")
                say(f"  clash {name}: interference at {DRIVE_FROM:g}° {seen['interference_at_drive_from']}, "
                    f"at {DRIVE_TO:g}° {seen['interference_at_drive_to']}")
                clean &= (abs(abs(seen["turn"]["gear1"]) - (DRIVE_TO - DRIVE_FROM)) < 1e-6
                          and abs(ratio - want) < 1e-6
                          and seen["interference_at_drive_to"][0] == 0 and not seen["gear1_fixed"])
            say(f"result  {name}: {'ok' if clean else 'NOT OK'}")
            ok_all &= clean
    finally:
        made = [t for t in run(worker, titles, 120) if t not in before]
        say(f"close   this run made {made}")
        after = run(worker, lambda s: close_made(s, made), 600)
        say(f"open    after: stray={[t for t in after if t not in before]} lost={[t for t in before if t not in after]}")
        worker.shutdown()
    say(f"done    all ok={ok_all}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        with open(LOG_PATH, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(LOG) + "\n")
    raise SystemExit(code)
