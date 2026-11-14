"""Smoke-test W4's SolidWorks side on a real session: a strip pair, a gearbox built, reused, tampered with, updated.

python.exe probe/gearbox_smoke.py <repo src> <output folder under C:\\> --pid PID [--log FILE] [--step N ...]

Agent A wrote ``swcom``'s W4 members and ``swbuild.build_gearbox`` / ``update_gearbox`` against a fake. This runs
them, small (spur gears of 16 and 24 teeth, module 2), in a SolidWorks the caller started for it, and measures
what they did rather than trusting their own results. The layout and assembly plans are made by hand from ops
here, in the shape W4-INTERFACES pins; ``workbook.layout`` will make them later.

1. A strip spur pair through ``pair.assembly_plan`` and ``swbuild.build_pair``: ``add_component`` now reads back
   the file each component took, so this is the released path's regression check.
2. ``build_gearbox``: three new parts for four gears (one part inserted twice), a layout part with a shaft on the
   base planes and one at +X, -Y (both flips, both link forms, axes by name, Top-parallel first), and the static
   assembly. Measured: each component's frame against what was placed; each layout axis's crossing and sense;
   no interference meshed, and the right two gears named when one is turned half a pitch.
3. Everything closed (the run's own modified documents saved first), then ``build_gearbox`` again reusing the
   saved parts and layout into a new assembly; whether the live check leaves them modified; a part changed by
   hand refused; a part of the same file name open from another folder refused with ``open_document`` never
   called.
4. ``update_gearbox`` on the first assembly, one gear "dragged" first: a part's face width and the layout's S2 X
   changed, only the gears whose frames differ re-placed (one turned a whole pitch left alone), one assembly
   rebuild, ``CommandInProgress`` False after, nothing saved or closed, and the wider gear now interfering with
   its neighbour on the shaft as the maths says.

Refuses to run unless the session it attaches to is the PID given and SolidWorks 2026 (major 34). Only documents
this run made are saved and closed; nothing open before the run is touched.
"""

import math
import os
import shutil
import sys
import time

sys.path.insert(0, sys.argv[1])
OUT = sys.argv[2]
PID = int(sys.argv[sys.argv.index("--pid") + 1])
STEPS = [int(sys.argv[i + 1]) for i, a in enumerate(sys.argv) if a == "--step"] or [1, 2, 3, 4]
LOG_PATH = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(OUT, "gearbox-smoke.log")

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from gear_generator import findings, swbuild, swcom  # noqa: E402
from gear_generator.gears import base, kind_for, pair  # noqa: E402
from gear_generator.gears.base import GlobalVariable  # noqa: E402
from gear_generator.probe.p7_workbook import axis_crossing  # noqa: E402
from gear_generator.spec import GearSpec  # noqa: E402
from gear_generator.store import same_path  # noqa: E402
from gear_generator.swcom import call  # noqa: E402

LOG = []
FAILS = []
MODULE = 2.0
SPECS = {"A": GearSpec(module="2", teeth="16", face_width="8", bore="8"),
         "B": GearSpec(module="2", teeth="24", face_width="8", bore="8"),
         "C": GearSpec(module="2", teeth="16", face_width="6", bore="8")}
PARTS = {k: os.path.join(OUT, f"Smoke_{k}{s.teeth}.SLDPRT") for k, s in SPECS.items()}
LAYOUT = os.path.join(OUT, "Smoke_Layout.SLDPRT")
ASM, ASM_R2, ASM_R3 = (os.path.join(OUT, f"Smoke{s}.SLDASM") for s in ("", "_r2", "_r3"))
S2 = (32.0, -24.0)                     # 40 mm from S1 = m (16 + 24) / 2
S2_MOVED = (33.0, -24.0)
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
LAYOUT_FEATURES = ("S2 X Plane", "S2 Y Plane", "S1 Axis", "S2 Axis")


def say(line=""):
    print(line, flush=True)
    LOG.append(line)


def check(ok, what):
    say(("ok      " if ok else "FAIL    ") + what)
    if not ok:
        FAILS.append(what)
    return ok


def run(worker, fn, timeout=900):
    value, error = worker.submit(fn).wait(timeout=timeout)
    if error is not None:
        raise error
    return value


class Counting:
    """The session, with every member it is asked for logged by name and first argument."""

    def __init__(self, session):
        self._session, self.calls = session, []

    def __getattr__(self, name):
        member = getattr(self._session, name)
        if not callable(member):
            return member

        def logged(*args, **kwargs):
            self.calls.append((name, args[:1]))
            return member(*args, **kwargs)
        return logged


# -- geometry ------------------------------------------------------------------------------------


def rot_z(degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0)


def follower(theta_p, zp, zq, phi):
    """PLAN-WORKBOOK §3.3, degrees: the turn of q (zq teeth) meshing p (zp, turned theta_p) seen at phi."""
    t = math.radians(theta_p)
    f = math.radians(phi)
    q = f + math.pi - math.pi / zq - (t - f) * zp / zq
    return math.degrees(q % (2 * math.pi / zq))


def gear_frames(s2):
    """handle -> (gear, part key, rotation, at, pitch): G1 A on S1, G2 B on S2, G3 C on S2, G4 B on S1."""
    phi = math.degrees(math.atan2(s2[1], s2[0]))
    return {
        "gear1": ("G1", "A", rot_z(0.0), (0.0, 0.0, 0.0), 360 / 16),
        "gear2": ("G2", "B", rot_z(follower(0.0, 16, 24, phi)), (s2[0], s2[1], 0.0), 360 / 24),
        "gear3": ("G3", "C", rot_z(follower(0.0, 24, 16, phi)), (s2[0], s2[1], 13.0), 360 / 16),
        "gear4": ("G4", "B", rot_z(0.0), (0.0, 0.0, 12.0), 360 / 24),
    }


# -- plans, by hand ----------------------------------------------------------------------------------


def part_plan(key):
    spec = SPECS[key]
    kind = kind_for(spec)
    return kind.plan(spec, kind.derive(spec), kind.recipe_for(spec), "", PARTS[key])


def part_values(key, **changes):
    spec = SPECS[key].with_values(**changes) if changes else SPECS[key]
    kind = kind_for(spec)
    return swbuild.DocumentValues(PARTS[key], tuple(kind.variables(spec, kind.derive(spec))))


def layout_values(s2):
    return swbuild.DocumentValues(LAYOUT, (GlobalVariable("S2 X", f"{s2[0]:g}"), GlobalVariable("S2 Y", f"{s2[1]:g}")),
                                  LAYOUT_FEATURES)


def layout_plan():
    """S1 on the base planes; S2 at +X on the plus side of Right, -Y on the minus side of Top, by globals."""
    plus = findings.LAYOUT_PLUS_FLIP
    return base.BuildPlan("layout", "", (
        base.NewPart(""),
        base.AddGlobal("S2 X", f"{S2[0]:g}"),
        base.AddGlobal("S2 Y", f"{S2[1]:g}"),
        base.RefPlane("x2", "S2 X Plane", 3, abs(S2[0]), flip=plus["right"] if S2[0] > 0 else not plus["right"]),
        base.LinkDimension("Offset@S2 X Plane", '"S2 X"'),
        base.RefPlane("y2", "S2 Y Plane", 2, abs(S2[1]), flip=plus["top"] if S2[1] > 0 else not plus["top"]),
        base.LinkDimension("Offset@S2 Y Plane", '- "S2 Y"'),
        base.Axis("axis1", "S1 Axis", (2, 3)),
        base.Axis("axis2", "S2 Axis", ("y2", "x2")),
        base.Rebuild(),
        base.SaveAs(LAYOUT),
    ), LAYOUT)


def assembly_plan(path):
    ops = [base.NewAssembly(""), base.AddComponent("layout", LAYOUT), base.Place("layout", IDENTITY, (0.0, 0.0, 0.0)),
           base.Fix("layout")]
    for handle, (_gear, key, rotation, at, _pitch) in gear_frames(S2).items():
        ops += [base.AddComponent(handle, PARTS[key], at), base.Place(handle, rotation, at), base.Fix(handle)]
    return base.BuildPlan("gearbox", "", tuple(ops) + (base.Rebuild(), base.SaveAs(path)), path)


GEARS = {h: f[0] for h, f in gear_frames(S2).items()}


# -- documents -------------------------------------------------------------------------------------------


def documents(app):
    out, doc = [], call(app, "GetFirstDocument")
    while doc is not None:
        out.append(doc)
        doc = call(doc, "GetNext")
    return out


def titles(session):
    return [str(call(d, "GetTitle")) for d in documents(session._app)]


def ours(path):
    return bool(path) and os.path.normcase(os.path.dirname(path)).startswith(os.path.normcase(OUT))


def close_ours(session):
    """Save the run's own modified documents, then close them, assemblies first. Returns what is left open of ours."""
    app = session._app
    for doc in documents(app):
        path = str(call(doc, "GetPathName") or "")
        if ours(path) and call(doc, "GetSaveFlag"):
            call(call(doc, "Extension"), "SaveAs3", path, 0, 1, swcom._null_dispatch(), swcom._null_dispatch(),  # noqa: SLF001
                 swcom._out_long(), swcom._out_long())  # noqa: SLF001
    for kind in (2, 1):
        for doc in documents(app):
            if ours(str(call(doc, "GetPathName") or "")) and int(call(doc, "GetType")) == kind:
                call(app, "CloseDoc", str(call(doc, "GetTitle")))
    return [str(call(d, "GetTitle")) for d in documents(app) if ours(str(call(d, "GetPathName") or ""))]


def save_flags(session, paths):
    out = {}
    for doc in documents(session._app):
        path = str(call(doc, "GetPathName") or "")
        for wanted in paths:
            if same_path(path, wanted):
                out[os.path.basename(wanted)] = bool(call(doc, "GetSaveFlag"))
    return out


def frames_of(session, asm, names):
    """Each Name2's live frame in ``asm``, found and read through the app's own members."""
    session.begin_build()
    try:
        session.open_document(asm)
        out = {}
        for index, name in enumerate(names):
            session.find_component(f"m{index}", name)
            out[name] = session.component_frame(f"m{index}")
        return out
    finally:
        session.end_build()


def axes_of(session, path):
    """Each layout axis's crossing of z = 0 (mm) and its direction, from GetRefAxisParams (probe tier 7's reading)."""
    session.begin_build()
    try:
        session.open_document(path)
        doc = session._doc()  # noqa: SLF001
        out = {}
        for name in ("S1 Axis", "S2 Axis"):
            feature = session._by_name(name)  # noqa: SLF001
            out[name] = axis_crossing(call(call(feature, "GetSpecificFeature2"), "GetRefAxisParams"))
        out["globals"] = session.equation_values()
        del doc
        return out
    finally:
        session.end_build()


def clashes_turned(session, asm, name, rotation, at):
    """Turn one component, read the interferences, put it back and read them again."""
    session.begin_build()
    try:
        session.open_document(asm)
        session.find_component("turned", name)
        before = session.component_frame("turned")
        session.place_component("turned", rotation, at, kind=swcom.ASSEMBLY_STATIC)
        turned = session.interferences()
        session.place_component("turned", before[0], before[1], kind=swcom.ASSEMBLY_STATIC)
        back = session.interferences()
        return turned, back
    finally:
        session.end_build()


def attempt(fn):
    """A job that may be refused: the BuildError comes back as a value, so the worker keeps its session."""
    def job(session):
        try:
            return fn(session)
        except swbuild.BuildError as exc:
            return exc
    return job


# -- the steps ---------------------------------------------------------------------------------------------


def step_pair(worker):
    say("step 1  a strip spur pair through pair.assembly_plan and swbuild.build_pair")
    a, b = SPECS["A"], SPECS["B"]
    paths = [os.path.join(OUT, "Pair_A16.SLDPRT"), os.path.join(OUT, "Pair_B24.SLDPRT")]
    plans = [kind_for(s).plan(s, kind_for(s).derive(s), kind_for(s).recipe_for(s), "", p) for s, p in zip((a, b), paths)]
    asm = os.path.join(OUT, "Pair.SLDASM")
    result = run(worker, lambda s: swbuild.build_pair(s, plans[0], plans[1], pair.assembly_plan(a, b, paths[0], paths[1],
                                                                                                   "", asm)))
    LOG.extend("        " + line for line in result.log_lines())
    check(result.ok, f"the pair built and saved; components {result.assembly.components if result.assembly else None}")
    check(result.assembly is not None and not result.assembly.checks, "no interference in the pair")


def step_build(worker):
    say("step 2  build_gearbox: 3 new parts for 4 gears, a layout part, a static assembly")
    steps = []
    started = time.monotonic()
    result = run(worker, lambda s: swbuild.build_gearbox(s, [part_plan(k) for k in "ABC"], layout=layout_plan(),
                                                         assembly=assembly_plan(ASM), gears=GEARS,
                                                         progress=steps.append))
    LOG.extend("        " + line for line in result.log_lines())
    say(f"        in {time.monotonic() - started:.1f} s; steps {[(x.stage, x.name, x.index, x.count) for x in steps]}")
    check(result.ok, "the gearbox built: parts, layout and assembly saved")
    say(f"        components {result.components}")
    names = {GEARS.get(h, h): n for h, n in result.components.items()}
    check(names.get("G2", "").rsplit("-", 1)[0] == names.get("G4", "").rsplit("-", 1)[0]
          and names.get("G2") != names.get("G4"), f"one part inserted twice: G2 {names.get('G2')}, G4 {names.get('G4')}")
    check(result.clashes == [] and not result.interference_error, f"no interference meshed: {result.clashes}")

    live = run(worker, lambda s: frames_of(s, ASM, list(result.components.values())))
    for handle, (gear, _key, rotation, at, _pitch) in gear_frames(S2).items():
        name = result.components[handle]
        got = live[name]
        check(swbuild.same_frame(got[0], got[1], rotation, at),
              f"{gear} ({name}) is where it was placed: origin {tuple(round(v, 9) for v in got[1])}")
    layout_name = result.components["layout"]
    check(swbuild.same_frame(live[layout_name][0], live[layout_name][1], IDENTITY, (0, 0, 0)),
          f"the layout ({layout_name}) is at identity")

    axes = run(worker, lambda s: axes_of(s, LAYOUT))
    for name, where in (("S1 Axis", (0.0, 0.0)), ("S2 Axis", S2)):
        (x, y), u = axes[name]
        check(abs(x - where[0]) < 1e-6 and abs(y - where[1]) < 1e-6 and u[2] > 1 - 1e-9,
              f"{name} crosses at ({x:.9f}, {y:.9f}) along {tuple(round(c, 9) for c in u)}")

    g2 = gear_frames(S2)["gear2"]
    turned, back = run(worker, lambda s: clashes_turned(s, ASM, result.components["gear2"],
                                                         rot_z(math.degrees(math.atan2(g2[2][3], g2[2][0])) + 7.5), g2[3]))
    say(f"        G2 turned half a pitch: {turned}; put back: {back}")
    want = {result.components["gear1"], result.components["gear2"]}
    merged = swbuild._clashes(turned, {n: GEARS.get(h, h) for h, n in result.components.items()})  # noqa: SLF001
    check(bool(turned) and all(set(names) == want and volume > 0 for names, volume in turned),
          f"half a pitch: {len(turned)} interference(s), every one between G1 and G2, none naming the layout; "
          f"merged {[(c.gears, round(c.volume, 3)) for c in merged]}")
    check(back == [], "put back, no interference")
    return result


def step_reuse(worker):
    say("step 3  close, then build_gearbox again reusing the saved parts and layout")
    left = run(worker, close_ours)
    check(not left, f"the run's documents are closed: left {left}")
    reuse = [part_values(k) for k in "ABC"]
    counted = {}

    def build(session, path):
        counted["sw"] = Counting(session)
        return swbuild.build_gearbox(counted["sw"], [], reuse=reuse, layout=layout_values(S2),
                                     assembly=assembly_plan(path), gears=GEARS)

    def checked_alone(session):
        for doc in reuse + [layout_values(S2)]:
            swbuild._check_live(session, doc, "reused")  # noqa: SLF001 - the build's own check, nothing else
        return save_flags(session, list(PARTS.values()) + [LAYOUT])

    flags = run(worker, attempt(checked_alone))
    check(isinstance(flags, dict) and not any(flags.values()),
          f"the live check alone leaves the reused documents unmodified: {flags}")
    result = run(worker, attempt(lambda s: build(s, ASM_R2)))
    if isinstance(result, Exception):
        check(False, f"the reuse build was refused: {result}")
        return
    LOG.extend("        " + line for line in result.log_lines())
    check(result.ok and result.checked == [r.path for r in reuse] + [LAYOUT] and result.layout_reused == LAYOUT,
          f"reused and checked: {[os.path.basename(p) for p in result.checked]}")
    opened = [os.path.basename(a[0]) for n, a in counted["sw"].calls if n == "open_document"]
    check(len(opened) == 4, f"each reused document opened once before the build: {opened}")
    check(result.clashes == [], f"no interference: {result.clashes}")
    flags = run(worker, lambda s: save_flags(s, list(PARTS.values()) + [LAYOUT]))
    say(f"        marked modified after AddComponent5 and the assembly's rebuild and save: {flags}")

    def tamper(session):
        session.begin_build()
        try:
            session.open_document(PARTS["A"])
            session.set_global_variable("No. of Teeth", "17")
            session.rebuild()
        finally:
            session.end_build()
        before = titles(session)
        refused = attempt(lambda s: build(s, ASM_R3))(session)
        after = titles(session)
        session.begin_build()
        try:
            session.open_document(PARTS["A"])
            session.set_global_variable("No. of Teeth", "16")
            session.rebuild()
        finally:
            session.end_build()
        return refused, before == after

    refused, unchanged = run(worker, tamper)
    say(f"        tampered: {refused}")
    check(isinstance(refused, swbuild.BuildError) and '"No. of Teeth" is 17 there and 16 here' in str(refused)
          and unchanged and not os.path.exists(ASM_R3), "a part changed by hand is refused by name, nothing made")

    left = run(worker, close_ours)
    check(not left, f"closed again: left {left}")
    other = os.path.join(OUT, "other", os.path.basename(PARTS["A"]))
    os.makedirs(os.path.dirname(other), exist_ok=True)
    shutil.copy2(PARTS["A"], other)

    def same_name(session):
        session.begin_build()
        try:
            session.open_document(other)
        finally:
            session.end_build()
        return attempt(lambda s: build(s, ASM_R3))(session)

    refused = run(worker, same_name)
    say(f"        same name elsewhere: {refused}")
    check(isinstance(refused, swbuild.BuildError) and "has the same file name as" in str(refused)
          and not any(n == "open_document" for n, _ in counted["sw"].calls) and not os.path.exists(ASM_R3),
          "a same-named part open from another folder is refused, open_document never called")
    left = run(worker, close_ours)
    run(worker, lambda s: [call(s._app, "CloseDoc", str(call(d, "GetTitle"))) for d in documents(s._app)  # noqa: SLF001
                           if same_path(str(call(d, "GetPathName") or ""), other)])
    check(not left, f"closed: left {left}")


def step_update(worker, built):
    say("step 4  update_gearbox on the first assembly, G1 dragged first")
    names = {GEARS.get(h, h): n for h, n in built.components.items()}
    files = list(PARTS.values()) + [LAYOUT, ASM]
    stamps = {p: os.path.getmtime(p) for p in files}

    def drag(session):
        session.begin_build()
        try:
            session.open_document(ASM)
            session.find_component("dragged", names["G1"])
            session.place_component("dragged", rot_z(10.0), (2.0, 1.0, 0.0), kind=swcom.ASSEMBLY_STATIC)
        finally:
            session.end_build()
        return titles(session)

    open_before = run(worker, drag)
    frames = gear_frames(S2_MOVED)
    g4 = frames["gear4"]
    placements = [swbuild.Placement(gear, names[gear], rotation, at, pitch)
                  for gear, _key, rotation, at, pitch in frames.values() if gear != "G4"]
    placements.append(swbuild.Placement("G4", names["G4"], rot_z(g4[4]), g4[3], g4[4]))   # a whole pitch on
    counted = {}

    def update(session):
        counted["sw"] = Counting(session)
        out = swbuild.update_gearbox(counted["sw"], [part_values("A", face_width="14"), part_values("B"),
                                                     part_values("C")], layout_values(S2_MOVED), ASM, placements)
        return out, bool(call(session._app, "CommandInProgress")), titles(session)  # noqa: SLF001

    result, in_progress, open_after = run(worker, update)
    LOG.extend("        " + line for line in result.log_lines())
    say(f"        found {[(g, tuple(round(v, 6) for v in f[1])) for g, f in result.found.items()]}")
    check(result.ok, "the update ran without a failure")
    check(sorted(result.placed) == ["G1", "G2", "G3"], f"re-placed G1 (dragged), G2, G3 (moved), not G4: {result.placed}")
    check(abs(result.found["G1"][1][0] - 2.0) < 1e-6, "G1 was found where it had been dragged")
    calls = counted["sw"].calls
    last = max(i for i, (n, a) in enumerate(calls) if n == "open_document" and a and same_path(a[0], ASM))
    check([n for n, _ in calls[last:]].count("rebuild") == 1, "exactly one assembly rebuild")
    check(in_progress is False, f"CommandInProgress afterwards: {in_progress}")
    check([os.path.getmtime(p) for p in files] == [stamps[p] for p in files], "nothing saved: every file's mtime unchanged")
    check(all(t in open_after for t in open_before), "nothing closed")
    check(sorted(os.path.basename(p) for p in result.changed) == sorted(
        os.path.basename(p) for p in (PARTS["A"], LAYOUT, ASM)), f"changed: {[os.path.basename(p) for p in result.changed]}")
    check([c.gears for c in result.clashes] in ([("G1", "G4")], [("G4", "G1")]),
          f"the 14 mm G1 now runs into G4 on S1, and nothing else interferes: {result.clashes}")
    live = run(worker, lambda s: frames_of(s, ASM, [names[g] for g in ("G1", "G2", "G3", "G4")]))
    for gear, _key, rotation, at, pitch in frames.values():
        got = live[names[gear]]
        check(swbuild.same_frame(got[0], got[1], rotation, at, pitch), f"{gear} is where the update wants it")
    axes = run(worker, lambda s: axes_of(s, LAYOUT))
    (x, y), _u = axes["S2 Axis"]
    check(abs(x - S2_MOVED[0]) < 1e-6 and abs(y - S2_MOVED[1]) < 1e-6, f"S2 Axis followed S2 X: ({x:.9f}, {y:.9f})")


def main():
    os.makedirs(OUT, exist_ok=True)
    worker = swcom.Worker()
    label, pid, revision = run(worker, lambda s: (s.label, s.pid, s.revision), 120)
    say(f"attach  {label}, PID {pid}")
    if pid != PID or revision[0] != 34:
        say(f"STOP    attached to PID {pid} {revision}, not the 2026 session {PID} this run was started for")
        worker.shutdown()
        return 2
    before = run(worker, titles, 120)
    say(f"open    before: {len(before)} documents")
    built = None
    try:
        if 1 in STEPS:
            step_pair(worker)
            check(not run(worker, close_ours), "the pair's documents closed")
        if 2 in STEPS:
            built = step_build(worker)
        if 3 in STEPS and built is not None:
            step_reuse(worker)
        if 4 in STEPS and built is not None and built.ok:
            step_update(worker, built)
    except Exception as exc:  # noqa: BLE001 - logged, and the documents still closed below
        check(False, f"raised {type(exc).__name__}: {exc}")
    finally:
        left = run(worker, close_ours, 600)
        after = run(worker, titles, 120)
        say(f"close   left of ours {left}; stray {[t for t in after if t not in before]}; "
            f"lost {[t for t in before if t not in after]}")
        worker.shutdown()
    say(f"done    {len(FAILS)} failed: {FAILS}")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        with open(LOG_PATH, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(LOG) + "\n")
    raise SystemExit(code)
