r"""W5's (and W4's) Windows demonstration: gearbox workbooks through the app's own code, on real SolidWorks and Excel.

python.exe probe/workbook_assembly_check.py <repo src> <output folder under C:\> --pid PID [--log FILE]
                                            [--only m1|m2|m3|m4|m5|a|a2|a3|b|c ...] [--fixtures FOLDER]
                                            [--m4-offset MM]

PLAN-WORKBOOK §6; W4 "Demonstrable" and the W4 decisions' item 10; W5-PLAN §4 with W5-DECISIONS' rulings. Every
step goes the way the Workbook window goes (``workbook_gui.WorkbookWindow``: ``_plan_solidworks_pass``,
``_start_build`` with its journal, ``press_update``, ``_build_again``, ``_finish_build``, ``_finish_update``,
``_collect_job``), with the window's Tk thread played by this script's main thread and its worker by
``swcom.Worker``: the workbook read by ``link.Link.read`` / ``Link.poll``, ``assess``, ``plan_gearbox`` or
``classify``, ``swbuild.build_gearbox(session, **plan.build_kwargs())`` or
``swbuild.update_gearbox(session, **update.update_kwargs())``, then ``finish_build`` / ``finish_update`` with the
sidecars and the record written through ``store.save`` and ``store.save_link_record``. Every sentence the footer
would show is logged (``ui_text.workbook_footer`` with the read's digest, ``gearbox_status`` with ``again``,
``gearbox_update_status`` with the finish, ``job_failed`` for a refusal, ``build_again_question``). Every edit to
a workbook is made by a real Excel saving the file: an Excel this script starts for itself
(``probe/excel/xlhelp.Excel``), never the user's, quit at the end.

Nothing is taken on the app's word: each assembly is measured.

- §4.1, every build: each gear component's live frame (``Transform2``) against ``layout.frames`` of the current
  read to 1e-6 — exactly for a gearbox built to turn (as built or put, its gears stand at the built turn), modulo
  the gear's pitch for W4's static one; the layout component at identity. Each layout axis by
  ``GetRefAxisParams``: where it crosses z = 0 and that it reads +Z. Interference: none. The mates in the
  assembly exactly the record's names, nothing else in the mate group, every error code 0, none suppressed, every
  mated gear ``GetConstrainedStatus`` 2 (``findings.COMPONENT_UNDER_DEFINED``). For every listed mesh a negative
  control: one of its gears turned half its pitch about its own axis (a put with the gear mate on,
  ``findings.MESH_PHASE_ROUTE``) must interfere, and only with its partner; put back, none again — the gear
  turned is one in no lock, or, when both are (Risky_Placements' G3–G4), every lock touching either is suppressed
  around the put and turned back on after; then the frames and the mates are read again. Saved, closed, reopened,
  every document unmodified straight after the open, the frames and the mates the same.
- §4.2, the driven proof (the script's own, never the app's): a temporary angle mate from the input anchor's Top
  plane (``gearN:plane2``) to the layout's Right plane (``layout:plane3``) at 90°, its D1 linked to an assembly
  global "Drive"; "Drive" 90 -> 120 and a top-only rebuild; each gear's turn about its own +Z
  (``swbuild.turn_between``) against the kinematics, δ_i = 30° · ω_i / ω_in with ``kinematics.solve``'s speeds
  about each shaft's own axis (W5-DECISIONS M2), to 1e-6 relative, sign included. The wrong-sense control: the
  section's chosen gear mate suppressed and a temporary one made in its place with the other Flip; driven again,
  the comparison must SEE its gear b turning the wrong way. Then, as review M12 rules: "Drive" set back to 90 before
  the control mate is deleted; the control mate deleted and the recorded one turned back on; the drive's link and
  global (``delete_equation``) and the angle mate deleted; every frame against the built frames to 1e-6; and,
  before anything is saved, no "Drive" equation, no angle or control mate left, no mate suppressed. If the 90°
  drive moves a gear when it is added, or turns the input other than findings.DEMONSTRATION_DRIVE_SENSE says, the
  whole run STOPS (W5-PLAN §4.2: stop and ask).
- The marks: SolidWorks' ``GetSaveFlag`` after a build (no part and no layout part, and the assembly) and after
  every Update (``GearboxUpdate.changed``, and the assembly when it was rebuilt). Where SolidWorks marks MORE than
  that it is a NOTE (logged, listed at the end, not a failure) for the coordinator to rule on; a document expected
  marked and not marked is a FAIL.

The sections, each in its own folder under the output folder (default order m1 m3 m2 m4 m5 a a2 a3 b c):

- ``m1`` (W5-PLAN §4.3): the Windows-saved 12 : 1 fixture (compound S2). Build turning; §4.1; §4.2 with the
  control on G3 meshes G4. M7: an angle mate the record does not know, on G4, unsuppressed -> Update refuses
  naming it; suppressed -> Update goes through and lists it; deleted. D10: "G4 along S3" suppressed -> Update turns
  it back on and says so. The user's turn, simulated: driven 37° and the drive deleted -> Update with nothing
  changed: nothing put, nothing changed, "… The gears stand where they were turned in SolidWorks."; train_check's
  residuals and each gear's origin, axis and turn residuals logged. Excel G4 At 27 -> 30 ("G4 Face Z" set; see
  AXIAL_RESTORES); G3 At 27 -> 29 (a follower: an Update under suppressed locks), frames, drive; the W4
  demonstration edit (S2 X 63.75 -> 64.5, G2 Teeth 68 -> 69, S3 X following) -> an Update by the remake: G2's
  part, the layout, the gear mate G1 meshes G2 at 17 : 69, every gear put, no lock left off; frames, drive at the
  new ratio, reopen. Then a structural edit (G1 face width 15 -> 17 moves its front face off the Front plane) ->
  Build again… builds Reducer_12to1_r2 turning; every earlier file's sha256 and mtime unchanged; §4.1; §4.2.
- ``m2``: the Arc_Move fixture (S2 placed by formulas from an angle cell). Build; §4.1; §4.2; the user's turn
  (25°) and Update with nothing changed; the angle 30 -> 40 in Excel -> Update moves the layout's shafts and puts
  the whole train back at its built turn; frames, axes, mates, interference, drive at the new place, reopen.
- ``m3``: the Risky_Placements fixture (Z- shafts, two compound shafts, a helical pinion in a helical ring on Z-,
  herringbones of unequal faces). Build; §4.1 (G3–G4's control under suppressed locks); §4.2 through the whole
  train with the control on the ring's mesh G5 meshes G6; the user's turn (20°) and Update with nothing changed.
- ``m4``: the refused mate, forced (W5-DECISIONS answer 1). The 12 : 1 plan with mates injected by the script
  (G3, the follower locked to G2, also on S2 Axis and along S2 — ``--m4-offset`` mm off where it stands, 0 by
  default). Ruled on 2026-11-14: the consistent mates first; if SolidWorks accepts them, that is logged as a finding
  and the build is forced again, in folder m4-offset1, 1 mm off; the log says which case made the refusal. Then:
  the build stops: AddMate5's statuses, the error codes and warnings, the constrained statuses and the
  app's sentences logged; the parts and the layout part saved and on record, no assembly file, the document left
  open and named, the record's mate problems and their digest; the footer never offers the same build of the
  unchanged workbook. Then a note cell changed in Excel (the plan unchanged, without the injection) -> Build makes
  the assembly at the same revision, beside the refused document left open when the P0c finding says that holds
  (else after closing it); then the refused document closed as W4's ``close_ours`` closes on 2024 (this run's
  modified documents saved first, then ``CloseDoc``).
- ``m5``: an Update lost and pressed again: the 12 : 1 built, the demonstration edit and Update, every document of
  the section closed in SolidWorks without saving (``QuitDoc``), Update pressed again on the same workbook: the
  sentence "… was not saved before … was closed, so its changes were made again", and the drive at 17 : 69 shows
  whether the gear mate holds the ratio the record says.
- ``a``: W4's section a on a turning build: build; §4.1; the demonstration edit as an Update by the remake (W4's
  "G2 at its old frame clashes" control does not hold for mated gears — the axis mate pulls a put gear back — so
  §4.2's drive at 17 : 69 stands in for it); then G1's bore cleared with Update's changes unsaved: the build-again
  plan does not wait for a save (W4 review B2), ``_r2`` built turning, earlier files unchanged.
- ``a2``: a build stopped at the assembly (a template that is not there), carried on; Build pressed again.
- ``a3`` (the second W4 review, N4 and N2): the journal of a build interrupted after two parts; then the
  demonstration edit and Update, closed unsaved; the edit typed back: Update loads every document from its file,
  finds the gear mate already at 17 : 68 (its live ratio, read in the check phase) and remakes nothing, so nothing
  is changed; the drive at 17 : 68; the sentence logged, not pinned (package C's wording, ruled on 2026-11-14).
- ``b``: a workbook written by ``write_new``, S2 placed by formulas: build; §4.1; the angle changed; a part-only
  Update (G2's bore 8 -> 10).
- ``c``: the risky placements written by ``write_new``: build; §4.1.

``--fixtures FOLDER`` copies b's and c's workbooks, as Excel saved them with a neutral Output folder, there.

Refuses to run unless the session it attaches to is the PID given. Only documents this run made are saved and
closed (its modified parts saved before an assembly is closed: SolidWorks 2024 asks about them in a modal dialog
otherwise); nothing open before the run is touched, and other documents' titles are logged as
``<user document N>``. On SolidWorks 2024 a section starts only with 3 GB of RAM free, and the run stops between
steps if it falls under 2 GB. The log ends with the step only a person can do (W5-PLAN §4.4).
"""

import ctypes
import dataclasses
import hashlib
import math
import os
import shutil
import sys
import threading
import time
import traceback

sys.path.insert(0, sys.argv[1])
SRC, OUT = sys.argv[1], sys.argv[2]
PID = int(sys.argv[sys.argv.index("--pid") + 1])
DEFAULT_ORDER = ["m1", "m3", "m2", "m4", "m5", "a", "a2", "a3", "b", "c"]
ONLY = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--only"] or DEFAULT_ORDER
LOG_PATH = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(OUT, "workbook-assembly.log")
FIXTURES = sys.argv[sys.argv.index("--fixtures") + 1] if "--fixtures" in sys.argv else ""
M4_OFFSET = float(sys.argv[sys.argv.index("--m4-offset") + 1]) if "--m4-offset" in sys.argv else 0.0
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURE_DIR = os.path.join(REPO, "tests", "fixtures", "excel-windows")
FIXTURE_12 = os.path.join(FIXTURE_DIR, "Reducer_12to1.xlsx")
FIXTURE_ARC = os.path.join(FIXTURE_DIR, "Arc_Move.xlsx")
FIXTURE_RISKY = os.path.join(FIXTURE_DIR, "Risky_Placements.xlsx")

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

os.environ["GG_SRC"] = SRC                     # xlhelp must import the same app as this script
os.environ["GG_EXCEL_SCRATCH"] = os.path.join(OUT, "excel")
sys.path.insert(1, os.path.join(HERE, "excel"))

import win32api  # noqa: E402
import win32gui  # noqa: E402
import win32process  # noqa: E402
import xlhelp  # noqa: E402

from gear_generator import __version__, findings, store, swbuild, swcom, ui_text  # noqa: E402
from gear_generator.gears import base, equations  # noqa: E402
from gear_generator.probe.p7_workbook import axis_crossing  # noqa: E402
from gear_generator.swcom import call  # noqa: E402
from gear_generator.workbook import assess as wb_assess  # noqa: E402
from gear_generator.workbook import gearbox as wb_gearbox  # noqa: E402
from gear_generator.workbook import layout as wb_layout  # noqa: E402
from gear_generator.workbook import link as wb_link  # noqa: E402
from gear_generator.workbook import model as wb_model  # noqa: E402
from gear_generator.workbook import update as wb_update  # noqa: E402
from gear_generator.workbook import xlsx  # noqa: E402
from gear_generator.workbook.model import Box, Gear, GearboxSpec, Mesh, Shaft  # noqa: E402
from gear_generator.workbook_gui import _had_assembly, _update_gate  # noqa: E402  (the window's own helpers)

LOG = []
FAILS = []
NOTES = []
LOCK = threading.Lock()
STOP = threading.Event()
WRITTEN_BY = f"gear-generator {__version__}"
TAG = {"version": "", "major": 0}
PERSON = []               # (what, path) of a plain 12 : 1 assembly built to turn, for W5-PLAN §4.4's step

# The driven proof (W5-PLAN §4.2).
DRIVE = "Drive"                      # the assembly global the angle mate's D1 is linked to
DRIVE_MATE = "Demonstration drive"   # the temporary angle mate
CONTROL = "Control "                 # prefix of the temporary gear mate of the wrong-sense control
DRIVE_FROM, DRIVE_TO = 90.0, 120.0
DRIVE_TOLERANCE = 1e-6               # relative, on each gear's turn in degrees (W5-PLAN §4.2)
FRAME_TOLERANCE = 1e-6               # on every origin coordinate (mm) and rotation entry
TURNED_SENTENCE = "The gears stand where they were turned in SolidWorks."
LOST_SENTENCE = "was not saved before Reducer_12to1.SLDASM was closed, so its changes were made again"

# W5-PLAN §4.3 m1 and the user's answer 2 ("Update returns a train the user turned to its built position whenever it
# has to move any gear") say G4 At 27 -> 30 puts the turned train back at its built turn. The app as it stands (its
# fake, 2026-11-14) sets "G4 Face Z", lets the mates carry G4 along S3 and leaves the train turned, while
# ui_text.update_summary says it will "re-place G1, G2, G3 and G4". Asked of the coordinator before the run; set
# this to follow the ruling. Either way the step logs what Update did and measures what stands.
AXIAL_RESTORES = True


class Stopped(Exception):
    """Free memory fell under the floor on SolidWorks 2024: the run stops between steps."""


class Halt(Exception):
    """The 90° drive misbehaved (W5-PLAN §4.2: stop and ask): the run stops, nothing more is driven."""


def say(line=""):
    with LOCK:
        print(line, flush=True)
        LOG.append(line)


def check(ok, what):
    say(("ok      " if ok else "FAIL    ") + what)
    if not ok:
        FAILS.append(what)
    return ok


def note(what):
    """Something SolidWorks did beyond what was expected, which is not a failure until the coordinator rules."""
    say("NOTE    " + what)
    NOTES.append(what)


def run(worker, fn, timeout=2400):
    value, error = worker.submit(fn).wait(timeout=timeout)
    if error is not None:
        raise error
    return value


def guard():
    if STOP.is_set():
        raise Stopped("free memory fell under 2 GB on SolidWorks 2024")


# -- the machine ---------------------------------------------------------------------------------------------


class _Memory(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]


def free_gb():
    m = _Memory()
    m.length = ctypes.sizeof(_Memory)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.avail / 2 ** 30


def sw_private_gb():
    try:
        handle = win32api.OpenProcess(0x1000 | 0x0010, False, PID)   # QUERY_LIMITED_INFORMATION | VM_READ
        try:
            return win32process.GetProcessMemoryInfo(handle)["PagefileUsage"] / 2 ** 30
        finally:
            win32api.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return float("nan")


def memory():
    return f"SolidWorks {sw_private_gb():.2f} GB private, {free_gb():.2f} GB free"


PROGRESS = {"Calculating Interference Detection": 0, "Updating...": 0, "Opening": 0, "Loading...": 0}


class DialogWatch(threading.Thread):
    """Logs any dialog SolidWorks shows (it would block every COM call) and, on 2024, sets STOP under 2 GB free.
    It closes nothing: a SolidWorks dialog is for a person to read."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.seen = set()

    def run(self):
        while not self.stop.is_set():
            found = []

            def each(hwnd, _):
                if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == PID \
                        and win32gui.GetClassName(hwnd) == "#32770":
                    found.append(hwnd)
                return True
            try:
                win32gui.EnumWindows(each, None)
            except Exception:  # noqa: BLE001
                pass
            for hwnd in found:
                if hwnd not in self.seen:
                    self.seen.add(hwnd)
                    title = win32gui.GetWindowText(hwnd)
                    if not title and any(t.startswith("Opening Component") for t in xlhelp.child_texts(hwnd)):
                        title = "Opening"                # the open-progress box has no title of its own
                    if title in PROGRESS:              # SolidWorks' own progress box: said once, then counted
                        PROGRESS[title] += 1
                        if PROGRESS[title] > 1:
                            continue
                    say(f"DIALOG  SolidWorks shows {title!r}: {xlhelp.child_texts(hwnd)[:8]}"
                        + (" (a progress box that closes itself; not logged again)" if title in PROGRESS else ""))
            if TAG["major"] == 32 and free_gb() < 2.0 and not STOP.is_set():
                say(f"STOP    {memory()}: under 2 GB free, the run stops at the next step")
                STOP.set()
            time.sleep(2)


# -- documents -----------------------------------------------------------------------------------------------


def documents(app):
    out, doc = [], call(app, "GetFirstDocument")
    while doc is not None:
        out.append(doc)
        doc = call(doc, "GetNext")
    return out


def ours(path):
    """Whether a document is under this run's output folder: matched with a separator, so a folder whose name
    merely starts with OUT's (asm2026b beside asm2026) is not taken for it."""
    root = os.path.normcase(os.path.abspath(OUT)).rstrip("\\/") + os.sep
    return bool(path) and os.path.normcase(os.path.abspath(path)).startswith(root)


USERS = {}
REFUSED = []              # titles of refused, never-saved assemblies this run left open (m4), closed by title


def open_titles(session):
    """Every open document's title; one not made by this run as ``<user document N>`` (the repo is public)."""
    out = []
    for doc in documents(session._app):  # noqa: SLF001
        title, path = str(call(doc, "GetTitle")), str(call(doc, "GetPathName") or "")
        if ours(path) or (not path and title in REFUSED):
            out.append(title)
        else:
            USERS.setdefault(path or title, f"<user document {len(USERS) + 1}>")
            out.append(USERS[path or title])
    return out


def save_docs(session, paths):
    """Save the open documents at these paths, as a person would in SolidWorks; returns what was saved."""
    saved = []
    for doc in documents(session._app):  # noqa: SLF001
        path = str(call(doc, "GetPathName") or "")
        if any(store.same_path(path, p) for p in paths):
            ok = call(call(doc, "Extension"), "SaveAs3", path, 0, 1, swcom._null_dispatch(),  # noqa: SLF001
                      swcom._null_dispatch(), swcom._out_long(), swcom._out_long())  # noqa: SLF001
            saved.append((os.path.basename(path), bool(ok)))
    return saved


def close_ours(session):
    """Save this run's modified documents, then close them, assemblies first; then any refused assembly this run
    left open, by its title (it has no file). Returns what is left open of ours."""
    app = session._app  # noqa: SLF001
    saved = []
    for doc in documents(app):
        path = str(call(doc, "GetPathName") or "")
        if ours(path) and call(doc, "GetSaveFlag"):
            call(call(doc, "Extension"), "SaveAs3", path, 0, 1, swcom._null_dispatch(),  # noqa: SLF001
                 swcom._null_dispatch(), swcom._out_long(), swcom._out_long())  # noqa: SLF001
            saved.append(os.path.basename(path))
    if saved:
        say(f"        closing: saved this run's modified documents first, as a person would: {saved}")
    for doc in documents(app):
        title = str(call(doc, "GetTitle"))
        if not str(call(doc, "GetPathName") or "") and title in REFUSED:
            call(app, "CloseDoc", title)
            say(f"        closing: the refused assembly {title}, never saved, closed by its title")
    for kind in (2, 1):
        for doc in documents(app):
            if ours(str(call(doc, "GetPathName") or "")) and int(call(doc, "GetType")) == kind:
                call(app, "CloseDoc", str(call(doc, "GetTitle")))
    return [str(call(d, "GetTitle")) for d in documents(app)
            if ours(str(call(d, "GetPathName") or "")) or (not str(call(d, "GetPathName") or "")
                                                            and str(call(d, "GetTitle")) in REFUSED)]


def quit_in(folder):
    """Close the open documents under ``folder`` WITHOUT saving them (``ISldWorks::QuitDoc``), assemblies first, as
    a person closing SolidWorks and answering "Don't save" would. Returns what is left open under it."""
    def under(path):
        return bool(path) and os.path.normcase(os.path.abspath(path)).startswith(
            os.path.normcase(os.path.abspath(folder)) + os.sep)

    def work(session):
        app = session._app  # noqa: SLF001
        for kind in (2, 1):
            for doc in documents(app):
                if under(str(call(doc, "GetPathName") or "")) and int(call(doc, "GetType")) == kind:
                    call(app, "QuitDoc", str(call(doc, "GetTitle")))
        return [str(call(d, "GetTitle")) for d in documents(app) if under(str(call(d, "GetPathName") or ""))]
    return work


def save_flags(session, paths):
    out = {}
    for doc in documents(session._app):  # noqa: SLF001
        path = str(call(doc, "GetPathName") or "")
        for wanted_path in paths:
            if store.same_path(path, wanted_path):
                out[os.path.basename(wanted_path)] = bool(call(doc, "GetSaveFlag"))
    return out


def marked(flags):
    """The documents SolidWorks reads ``GetSaveFlag`` True in (one not open reads nothing, so it is not marked)."""
    return sorted(n for n, f in flags.items() if f)


def expected_marks(result, assembly):
    """What SolidWorks should mark modified after an Update: every document whose content it changed
    (``GearboxUpdate.changed``), and the assembly whenever Update rebuilt it, which also runs the interference
    check — each of which marks the assembly (probe assembly_rebuild_scope) though it holds nothing new."""
    names = {os.path.basename(p) for p in result.changed}
    if result.rebuilt:
        names.add(os.path.basename(assembly))
    return sorted(names)


def check_marks(flags, wanted_marks, label):
    """SolidWorks' marks against what the invariant expects: equal is ok; a superset is a NOTE (logged for the
    coordinator to rule, not a failure: "LOG rather than assume wherever SolidWorks marks more"); one expected
    and missing is a FAIL."""
    got = marked(flags)
    if got == sorted(wanted_marks):
        return check(True, f"{label}: SolidWorks marks modified exactly {got}")
    if set(wanted_marks) <= set(got):
        note(f"{label}: SolidWorks marks modified more than the invariant expects: marked {got}, expected "
             f"{sorted(wanted_marks)} (more: {sorted(set(got) - set(wanted_marks))})")
        return True
    return check(False, f"{label}: SolidWorks marks modified {got}, expected {sorted(wanted_marks)} (missing "
                        f"{sorted(set(wanted_marks) - set(got))})")


def check_fresh_build_marks(worker, paths, assembly, label):
    """Right after a build and its saves: no part and no layout part reads GetSaveFlag True (the assembly is rebuilt
    top-only: findings.ASSEMBLY_REBUILD_ROUTE for W4's static one, MATED_BUILD_REBUILD_ROUTE for a train, which
    probe round P0b saw mark nothing but the assembly), and the assembly does (a read after its save marks it)."""
    flags = run(worker, lambda s: save_flags(s, paths))
    say(f"        marked modified in SolidWorks right after the build: {flags}")
    check(flags.get(os.path.basename(assembly)) is True, f"{label}: the assembly is marked after the build (a read "
          "after its save)")
    check_marks(flags, [os.path.basename(assembly)], f"{label}, right after the build and its saves")


def save_assembly(worker, desk, why):
    """Save the current assembly (and every document of the gearbox SolidWorks holds modified), as a person would,
    so the marks after the next step are that step's own."""
    box = desk.record.gearbox
    paths = [box.assembly, box.layout] + sorted({c.part for c in box.components})
    saved = run(worker, lambda s: save_docs(s, paths))
    say(f"person  saved in SolidWorks ({why}): {saved}")


def sidecar_texts(folder):
    """Every .gear.json in a folder, parsed, by name: taken before a build so a rewritten one can be said field by
    field."""
    import json
    out = {}
    for name in sorted(os.listdir(folder)):
        if name.endswith(".gear.json"):
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                out[name] = json.load(handle)
    return out


def _flat(value, prefix=""):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out.update(_flat(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: value}


def check_earlier_unchanged(folder, earlier, label, earlier_sidecars=None):
    """A build beside earlier files: every earlier SolidWorks file's sha256 and mtime unchanged. A .gear.json may be
    rewritten only to take off the unsaved mark an Update left on it (``finish_build`` unmarks a reused part whose
    changes were saved since; ruled on 2026-11-14); each one that changed is logged with what changed in it, and any
    other change to an earlier file is a FAIL."""
    later = stamps(folder)
    now = sidecar_texts(folder)
    for name in sorted(earlier_sidecars or {}):
        if name in now and now[name] != earlier_sidecars[name]:
            a, b = _flat(earlier_sidecars[name]), _flat(now[name])
            diff = {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
            say(f"fact    {label}: {name} rewritten: {diff}")
    touched = [n for n in earlier if later.get(n) != earlier[n]]
    solid = [n for n in touched if n.upper().endswith((".SLDPRT", ".SLDASM"))]
    check(solid == [], f"{label}: every earlier SolidWorks file's sha256 and mtime unchanged: changed {solid}")
    for name in (n for n in touched if n not in solid):
        part = os.path.join(folder, name[:-len(".gear.json")] + ".SLDPRT") if name.endswith(".gear.json") else ""
        sidecar = store.read_sidecar(part) if part else None
        check(sidecar is not None and sidecar.record.unsaved_since == 0,
              f"{label}: {name} rewritten only to take off Update's unsaved mark (unsaved_since "
              f"{sidecar and sidecar.record.unsaved_since})")
    return later


def stamps(folder, solidworks_only=False):
    """sha256 and mtime of every file in a folder but the link record and Excel's lock file (only the SolidWorks
    documents with ``solidworks_only``: the workbook is Excel's and the sidecars the app's to rewrite)."""
    out = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or name.startswith("~$") or name.endswith(store.LINK_SUFFIX):
            continue
        if solidworks_only and not name.upper().endswith((".SLDPRT", ".SLDASM")):
            continue
        with open(path, "rb") as handle:
            out[name] = (hashlib.sha256(handle.read()).hexdigest(), os.stat(path).st_mtime_ns)
    return out


# -- geometry ------------------------------------------------------------------------------------------------


def turn_about_z(rotation, degrees):
    """A frame's rotation turned about the part's own axis (its local Z): R · rot_z(degrees)."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    r = [rotation[i * 3:(i + 1) * 3] for i in range(3)]
    z = ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
    return tuple(sum(r[i][k] * z[k][j] for k in range(3)) for i in range(3) for j in range(3))


def frame_error(live, wanted_frame, pitch):
    """(largest origin difference in mm, the turn between them in degrees modulo pitch, off-axis residue)."""
    (ra, at_a), (rb, at_b) = live, wanted_frame
    origin = max(abs(float(a) - float(b)) for a, b in zip(at_a, at_b))
    a = [[float(ra[i * 3 + j]) for j in range(3)] for i in range(3)]
    b = [[float(rb[i * 3 + j]) for j in range(3)] for i in range(3)]
    m = [[sum(a[k][i] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    turn = math.degrees(math.atan2(m[1][0], m[0][0]))
    off = turn % pitch if pitch else turn
    off = min(off, pitch - off) if pitch else abs(off)
    residue = max(abs(m[2][2] - 1.0), abs(m[0][2]), abs(m[1][2]), abs(m[2][0]), abs(m[2][1]))
    return origin, off, residue


def frame_gap(a, b):
    """The largest difference between two frames, origin coordinates (mm) and rotation entries alike."""
    (ra, at_a), (rb, at_b) = a, b
    return max([abs(float(x) - float(y)) for x, y in zip(at_a, at_b)]
               + [abs(float(x) - float(y)) for x, y in zip(ra, rb)])


def frames_gap(found, wanted_frames):
    """(the largest frame_gap over the gears, the gear it is at)."""
    worst = (0.0, "")
    for gear, frame in wanted_frames.items():
        gap = frame_gap(found[gear], frame) if gear in found else float("inf")
        if gap > worst[0]:
            worst = (gap, gear)
    return worst


def turn_degrees(rotation_a, rotation_b):
    """``swbuild.turn_between`` in degrees, or None when b is not a's turned about its own Z."""
    turn = swbuild.turn_between(rotation_a, rotation_b)
    return None if turn is None else math.degrees(turn)


# -- the app's Tk-thread side, as the Workbook window has it -------------------------------------------------


class Desk:
    """The Workbook window without Tk: the same calls, in the same order, on this thread."""

    def __init__(self, path, worker):
        self.path = path
        self.link = wb_link.Link(path)
        self.worker = worker
        self.reading = None
        self.a = None
        self.record = None
        self.record_problem = ""
        self.plan = None
        self.update = None
        self.note = None
        self.error = None          # the last job's raise (a refusal before anything was made or changed)

    # reading
    def read(self):
        deadline = time.monotonic() + 10
        while True:
            try:
                self.reading = self.link.read()
                break
            except xlsx.NotReady as exc:
                if time.monotonic() > deadline:
                    raise
                say(f"        not ready yet: {exc}")
                time.sleep(0.5)
        self._after_read()

    def poll(self, timeout=30.0):
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            reading = self.link.poll()
            if reading is not None:
                if self.reading is None or reading.digest != self.reading.digest:
                    self.note = None       # as the window: the file has moved on from the last job's sentence
                self.reading = reading
                say(f"poll    a new read {time.monotonic() - started:.1f} s after asking; changes:")
                for line in reading.changes:
                    say(f"          {line}")
                self._after_read()
                return reading
            time.sleep(0.25)
        raise AssertionError(f"Link.poll saw no change in {timeout:g} s")

    def _after_read(self):
        r = self.reading
        check(r.ok, f"read {os.path.basename(self.path)}: {r.error or 'ok'}")
        spec = r.spec
        self.a = wb_assess.assess(spec, r.diagnostics, spec.box.output_folder, spec.box.part_template)
        for d in self.a.diagnostics:
            say(f"        {d.level:7} {d.message}")
        say(f"        {len(spec.shafts)} shafts · {len(spec.gears)} gears · {len(spec.meshes)} meshes; "
            f"gate {self.a.lay_out_refusal()!r}")
        self.plan_solidworks()

    def plan_solidworks(self):
        """``WorkbookWindow._plan_solidworks_pass`` (the record is always this workbook's here)."""
        newer = False
        try:
            record, problem = store.read_link_record(self.path), ""
        except store.UnknownSchema as exc:
            record, problem, newer = None, str(exc), True
        except store.StoreError as exc:
            record, problem = None, str(exc)
        if record is not None:
            store.clear_saved(record)
        self.record, self.record_problem = record, problem
        self.plan = self.update = None
        a = self.a
        if a is None or newer:
            return
        gearbox = record.gearbox if record is not None else None
        has_assembly = gearbox is not None and bool(gearbox.assembly)
        parts_only = not has_assembly and bool(a.parts.refused)
        gate = a.build_refusal() if parts_only else a.lay_out_refusal()
        if not gate:
            self.plan = wb_gearbox.plan_gearbox(a, record, parts_only=parts_only)
        if record is not None and (record.parts or gearbox is not None) and not _update_gate(a, record):
            self.update = wb_update.classify(record, a)

    def footer(self):
        folder = self.reading.spec.box.output_folder if self.reading is not None else ""
        return ui_text.workbook_footer(self.a, record=self.record, record_problem=self.record_problem,
                                       plan=self.plan, update=self.update, folder=folder,
                                       folder_exists=bool(folder) and os.path.isdir(folder), note=self.note,
                                       digest=self.reading.digest if self.reading is not None else "")

    def say_footer(self, when):
        f = self.footer()
        say(f"footer  ({when}) [{'green' if f.ok else 'red'}] {f.text}")
        say(f"        button {f.build_label!r} {'on' if f.build_enabled else 'off'}"
            f"{' primary' if f.build_primary else ''}; Update SolidWorks "
            f"{('shown ' + ('on' if f.update_enabled else 'off') + (' primary' if f.update_primary else '')) if f.update_shown else 'hidden'}")
        return f

    def say_plan(self, full=True):
        p = self.plan
        if p is None:
            say("plan    none (the gate refuses)")
            return
        say(f"plan    revision {p.revision} {p.name}: refusal {p.refusal!r}; reason {p.revision_reason!r}; "
            f"turning {p.motion is not None}; static reason {p.static_reason!r}")
        if p.refusal:
            return
        say(f"        layout {p.layout_path}; assembly {p.assembly_path}")
        for job in p.build:
            say(f"        build {job.stem} for {', '.join(job.gear_ids)} at {job.path} ({len(job.plan.ops)} ops)")
        for r in p.reuse:
            say(f"        reuse {r.stem} for {', '.join(r.gear_ids)} at {r.path} (made by revision {r.revision}, "
                f"{len(r.variables)} globals checked live)")
        if isinstance(p.layout, wb_gearbox.LayoutReuse):
            say(f"        reuse layout {p.layout.path}: {[f'{v.name} = {v.expression}' for v in p.layout.variables]}; "
                f"features {list(p.layout.features)}")
        for s in p.shafts:
            say(f"        shaft {s.shaft}: ({s.x:g}, {s.y:g}, {s.z:g}) sigma {s.sigma:+d}; X {s.x_side} "
                f"{s.x_global!r}, Y {s.y_side} {s.y_global!r}; {s.axis_name}")
        for gear, f in p.frames.items():
            say(f"        frame {gear}: R {[round(v, 9) for v in f.rotation]} at {[round(v, 9) for v in f.at]}")
        if p.motion is not None:
            m = p.motion
            say(f"        motion: trains {list(m.trains)}; drag {list(m.drag)}; fixed {list(m.fixed)}; unmated "
                f"{list(m.unmated)}")
            for mate in m.mates:
                say(f"        mate {mate.name!r}: {mate.kind} {list(mate.gears)} {mate.shaft} ratio {list(mate.ratio)} "
                    f"face {mate.face_global!r} z_front {mate.z_front:g}")
        if full:
            for plan in (p.layout, p.assembly):
                if isinstance(plan, base.BuildPlan):
                    say(f"        ops of {os.path.basename(plan.path)}:")
                    for op in plan.ops:
                        say(f"          {base.describe(op)}")

    def say_update(self):
        u = self.update
        if u is None:
            say("update  none")
            return
        say(f"classify parts changed {[os.path.basename(p.path) for p in u.changed_parts]}; moved "
            f"{list(u.moved_shafts)}; re-place {list(u.replaced)}; structural {list(u.structural)}; missing "
            f"{list(u.missing)}; unsaved {[os.path.basename(p) for p in u.unsaved]}; refusal {u.refusal!r}; "
            f"turning {u.motion is not None}; axial {list(getattr(u, 'axial', ()))}; ratios "
            f"{list(getattr(u, 'ratios', ()))}")
        if u.layout is not None:
            say(f"        layout globals wanted {[f'{v.name} = {v.expression}' for v in u.layout.variables]}")
        say(f"summary {ui_text.update_summary(u)}")

    # the jobs
    def write_journal(self, plan):
        """``WorkbookWindow._write_journal``: what the build is about to make, merged into the record's journal."""
        try:
            record = store.read_link_record(self.path)
        except Exception:  # noqa: BLE001 - as the window: left for the finish
            return False
        if record is None:
            record = store.LinkRecord(workbook=self.path)
        record.pending = wb_gearbox.merged_journal(record, wb_gearbox.journal(plan), self.path)
        record.pending_for = self.path
        try:
            store.save_link_record(record, store.link_record_path(self.path))
        except Exception:  # noqa: BLE001
            return False
        return True

    def build(self, plan=None):
        """``_start_build`` (its journal first) then, once the worker answers, ``_finish_build`` — or, for a raise,
        ``_collect_job``'s ``job_failed`` sentence. ``plan`` (m4 only): a plan the script changed, run in place of
        the window's own."""
        plan = plan or self.plan
        before = self.record                    # the record the build is planned from: Build again… if it held one
        steps = []
        kwargs = plan.build_kwargs()
        journaled = self.write_journal(plan)
        say(f"journal {'written' if journaled else 'NOT written'}: {len(wb_gearbox.journal(plan))} paths")
        started = time.monotonic()
        say(f"build   {plan.name}: {memory()}")
        result, self.error = self.worker.submit(
            lambda s: swbuild.build_gearbox(s, **kwargs, progress=steps.append)).wait(timeout=2400)
        seconds = time.monotonic() - started
        if self.error is not None:
            say(f"        raised {type(self.error).__name__}: {self.error}")
            self.note = (ui_text.job_failed(self.error, False), False)
            say(f"status  [red] {self.note[0]}")
            self.plan_solidworks()
            return plan, None
        for line in result.log_lines():
            say("        " + line)
        say(f"        in {seconds:.1f} s; {memory()}; kind {result.kind!r}")
        say(f"        steps {[(x.stage, x.name, x.index, x.count) for x in steps]}")
        say(f"        progress words {[ui_text.progress_text(x) for x in steps[:1] + steps[-1:]]}")
        self.note = self.finish_build(plan, result, again=_had_assembly(before))
        say(f"status  [{'green' if self.note[1] else 'red'}] {self.note[0]}")
        self.plan_solidworks()
        return plan, result

    def finish_build(self, plan, result, again=False):
        text, ok = ui_text.gearbox_status(plan, result, again=again)
        record, may_write, notes = self._open_record()
        finished = wb_gearbox.finish_build(plan, result, record, workbook=self.path, digest=self.reading.digest,
                                           written_by=WRITTEN_BY)
        if record is None and finished.record is not None:
            finished.record.own_digest = self.link.own_digest
        faults = self._write(finished, may_write)
        if not may_write:
            faults, notes = notes + faults, []
        return " ".join([text] + notes + faults), ok and not faults

    def update_solidworks(self):
        """``press_update`` (no new revision needed) then ``_finish_update``; a raise is ``_collect_job``'s
        ``job_failed`` sentence (``self.error``; the result and the finish are then None)."""
        update = self.update
        steps = []
        kwargs = update.update_kwargs()
        started = time.monotonic()
        say(f"update  {memory()}")
        result, self.error = self.worker.submit(
            lambda s: swbuild.update_gearbox(s, **kwargs, progress=steps.append)).wait(timeout=2400)
        seconds = time.monotonic() - started
        if self.error is not None:
            say(f"        raised {type(self.error).__name__} in {seconds:.1f} s: {self.error}")
            self.note = (ui_text.job_failed(self.error, True), False)
            say(f"status  [red] {self.note[0]}")
            self.plan_solidworks()
            return update, None, None
        for line in result.log_lines():
            say("        " + line)
        say(f"        in {seconds:.1f} s; {memory()}")
        say(f"        steps {[(x.stage, x.name, x.index, x.count) for x in steps]}")
        say(f"        loaded from disk {[os.path.basename(p) for p in result.opened]}")
        say(f"        motion: turned {result.turned}; out of step {result.out_of_step}; off axis {result.off_axis}; "
            f"restored {result.restored}; unsuppressed {result.unsuppressed}; axial {result.axial}; ratios "
            f"{result.ratios}; extra mates {result.extra_mates}")
        say(f"        train_check residuals (rad) {[(a, b, f'{r:.2e}') for a, b, r in result.residuals]}")
        record, may_write, notes = self._open_record()
        base_record = record if record is not None else self.record
        finished = wb_update.finish_update(update, result, base_record, digest=self.reading.digest,
                                           workbook=self.path)
        gearbox = self.record.gearbox if self.record is not None else None
        say(f"        finish: dragged {finished.dragged}; earlier update {getattr(finished, 'earlier_update', '')!r}")
        text, ok = ui_text.gearbox_update_status(update, result, finished.dragged,
                                                 meshes=gearbox.meshes if gearbox is not None else None,
                                                 finished=finished)
        faults = self._write(finished, may_write)
        if not may_write:
            faults, notes = notes + faults, []
        self.note = (" ".join([text] + notes + faults), ok and not faults)
        say(f"status  [{'green' if self.note[1] else 'red'}] {self.note[0]}")
        self.plan_solidworks()
        return update, result, finished

    def _open_record(self):
        try:
            return store.open_link_record(self.path), True, []
        except store.UnknownSchema as exc:
            return None, False, [str(exc)]
        except store.StoreError as exc:
            return None, True, [str(exc)]

    def _write(self, finished, may_write):
        faults = []
        for path, sidecar in finished.sidecars:
            try:
                store.save(path, sidecar)
            except OSError as exc:
                faults.append(ui_text.sidecar_unwritten(path, exc))
        if finished.record is not None and may_write:
            try:
                store.save_link_record(finished.record, store.link_record_path(self.path))
            except store.StoreError as exc:
                faults.append(str(exc))
        say(f"record  {len(finished.sidecars)} sidecar(s) written; record "
            f"{'written' if finished.record is not None and may_write else 'not written'}; notes {finished.notes}")
        return faults + list(finished.notes)

    def plan_shafts(self):
        return wb_layout.shaft_layouts(self.a.spec)


def turning(desk):
    box = desk.record.gearbox if desk.record is not None else None
    return box is not None and bool(box.assembly) and box.kind == store.GEARBOX_MOTION


def edit(desk, book, *cells):
    """Excel sets the cells and saves; the window's poll reads it, plans and classifies."""
    for sheet, ref, value in cells:
        book.set(sheet, ref, value)
    book.save()
    desk.poll()
    desk.say_update()


# -- measuring ----------------------------------------------------------------------------------------------


def in_assembly(asm, work):
    """A worker job: the assembly opened as the app opens it (``open_document``), ``work(session)``, the build
    ended whatever happened."""
    def job(session):
        session.begin_build()
        try:
            session.open_document(asm)
            return work(session)
        finally:
            session.end_build()
    return job


def live_frames(session, asm, names):
    def work(s):
        out = {}
        for index, name in enumerate(names):
            s.find_component(f"m{index}", name)
            out[name] = s.component_frame(f"m{index}")
        return out
    return in_assembly(asm, work)(session)


def live_axes(session, path, names):
    def work(s):
        out = {}
        for name in names:
            feature = s._by_name(name)  # noqa: SLF001
            out[name] = axis_crossing(call(call(feature, "GetSpecificFeature2"), "GetRefAxisParams"))
        return out, s.equation_values()
    return in_assembly(path, work)(session)


def live_globals(session, path):
    return in_assembly(path, lambda s: s.equation_values())(session)


def live_interferences(session, asm):
    return in_assembly(asm, lambda s: s.interferences())(session)


def live_mates(session, asm, components):
    """Every mate as ``mate_states`` reads it, the names of anything else in the mate group, and each gear's
    ``GetConstrainedStatus`` (``components``: (gear, Name2) pairs)."""
    def work(s):
        others = []
        states = s.mate_states(others=others)
        status = {}
        for index, (gear, name) in enumerate(components):
            s.find_component(f"k{index}", name)
            status[gear] = s.constrained_status(f"k{index}")
        return states, others, status
    return in_assembly(asm, work)(session)


def delete_mate(session, name):
    """``findings.MATE_DELETE_ROUTE`` ("Select2 then EditDelete()"), as swcom's remake deletes a gear mate: the mate
    selected alone, ``EditDelete()`` invoked, and its name read gone from the mate group."""
    feature = session._mate_feature(name)  # noqa: SLF001
    doc = session._doc()  # noqa: SLF001
    call(doc, "ClearSelection2", True)
    call(feature, "Select2", False, 0)
    swcom._guarded("EditDelete", lambda: doc.EditDelete())  # noqa: SLF001
    call(doc, "ClearSelection2", True)
    if name in session._mate_names():  # noqa: SLF001
        raise swcom.SolidWorksError(f"The mate {name} is still there after EditDelete().")


def placed_elsewhere(session, asm, name, rotation, at, kind, locks=()):
    """Put one component at another frame, read the interferences, put it back, read them again; with ``locks``
    (mate names), each suppressed around the puts and turned back on after, whatever happened."""
    def work(s):
        for index, lock in enumerate(locks):
            s.find_mate(f"lock{index}", lock)
            s.set_mate_suppressed(f"lock{index}", True)
        try:
            if locks:
                s.rebuild(kind=kind)
            s.find_component("moved", name)
            before = s.component_frame("moved")
            s.place_component("moved", rotation, at, kind=kind)
            moved = s.interferences()
            s.place_component("moved", before[0], before[1], kind=kind)
            back = s.interferences()
            return moved, back
        finally:
            for index, _ in enumerate(locks):
                s.set_mate_suppressed(f"lock{index}", False)
            if locks:
                s.rebuild(kind=kind)
    return in_assembly(asm, work)(session)


def wanted(desk):
    """Each gear's wanted frame and pitch, from the current read (what the window would place)."""
    frames = wb_layout.frames(desk.a.report)
    placed = desk.a.report.layout.placed
    return {g: (f.rotation, f.at, wb_layout.pitch(placed[g])) for g, f in frames.items()}


def measure_frames(worker, desk, label, exact=None):
    """Every gear's frame against the read's, to 1e-6: exactly for a gearbox built to turn (``exact`` None: as the
    record's kind says), modulo the gear's pitch for W4's static one."""
    box = desk.record.gearbox
    exact = turning(desk) if exact is None else exact
    names = [c.name for c in box.components] + [box.layout_component]
    started = time.monotonic()
    live = run(worker, lambda s: live_frames(s, box.assembly, names))
    want = wanted(desk)
    for c in box.components:
        rotation, at, pitch = want[c.gear]
        got = live[c.name]
        origin, off, residue = frame_error(got, (rotation, at), 0.0 if exact else pitch)
        check(swbuild.same_frame(got[0], got[1], rotation, at, 0.0 if exact else pitch),
              f"{label}: {c.gear} ({c.name}) at {tuple(round(v, 9) for v in got[1])}, origin off {origin:.1e} mm, "
              f"turn off {off:.1e}°{' (exactly)' if exact else f' modulo its pitch {pitch:.4f}°'}, axis off "
              f"{residue:.1e}")
        check(swbuild.same_frame(c.rotation, c.at, rotation, at, 0.0 if exact else pitch),
              f"{label}: {c.gear}'s frame on record is the one the workbook wants")
    lay = live[box.layout_component]
    check(swbuild.same_frame(lay[0], lay[1], wb_layout.IDENTITY, (0.0, 0.0, 0.0)),
          f"{label}: the layout ({box.layout_component}) is at identity")
    say(f"        frames read in {time.monotonic() - started:.1f} s")
    return live


def measure_axes(worker, desk, label):
    box = desk.record.gearbox
    axes, values = run(worker, lambda s: live_axes(s, box.layout, [s_.axis_name for s_ in box.shafts]))
    say(f"        {os.path.basename(box.layout)} globals {values}")
    for shaft in desk.plan_shafts():
        (x, y), u = axes[shaft.axis_name]
        check(abs(x - shaft.x) < 1e-6 and abs(y - shaft.y) < 1e-6 and u[2] > 1 - 1e-9,
              f"{label}: {shaft.axis_name} crosses z = 0 at ({x:.9f}, {y:.9f}) for ({shaft.x:g}, {shaft.y:g}), "
              f"along {tuple(round(c, 9) for c in u)}")
    return axes


def measure_clear(worker, desk, label):
    found = run(worker, lambda s: live_interferences(s, desk.record.gearbox.assembly))
    check(found == [], f"{label}: no interference in {os.path.basename(desk.record.gearbox.assembly)}: {found}")


def measure_mates(worker, desk, label):
    """§4.1's mates: exactly the record's names and nothing else in the mate group, every code 0, none suppressed,
    every mated gear under-defined (2); the fixed gears' statuses logged."""
    box = desk.record.gearbox
    want = [m.name for m in box.mates]
    states, others, status = run(worker, lambda s: live_mates(s, box.assembly,
                                                              [(c.gear, c.name) for c in box.components]))
    names = [s.name for s in states]
    say(f"        mates {[(s.name, s.code, s.warning, s.suppressed) for s in states]}; others {others}; "
        f"constrained {status}")
    check(sorted(names) == sorted(want), f"{label}: the mates are exactly the record's {len(want)}: extra "
          f"{sorted(set(names) - set(want))}, missing {sorted(set(want) - set(names))}")
    check(not others, f"{label}: nothing but mates in the mate group: {others}")
    bad = [(s.name, s.code, s.warning) for s in states if s.code]
    check(not bad, f"{label}: every mate's error code is 0: {bad}")
    off = [s.name for s in states if s.suppressed]
    check(not off, f"{label}: no mate suppressed: {off}")
    mated = [c.gear for c in box.components if c.gear not in box.fixed]
    loose = {g: status[g] for g in mated if status[g] != findings.COMPONENT_UNDER_DEFINED}
    check(not loose, f"{label}: every mated gear under-defined ({findings.COMPONENT_UNDER_DEFINED}): {status}")
    return states


def control_gear(box, a, b, count, locked):
    """The gear of mesh (a, b) a control turns, and the locks to suppress around it: W4's choice (b when it is in
    one mesh only, else a) unless that gear is in a lock; then the other, if it is in none; else W4's choice with
    every lock touching either gear suppressed (W5-PLAN §4.1: Risky_Placements' G3–G4)."""
    order = [b, a] if count[b] == 1 else [a, b]
    free = [g for g in order if g not in locked]
    if free:
        return free[0], []
    return order[0], [m.name for m in box.mates if m.kind == "lock" and (a in m.gears or b in m.gears)]


def negative_controls(worker, desk, label):
    """Every listed mesh: one of its gears turned half a pitch must clash with its partner and nothing else."""
    box = desk.record.gearbox
    name_of = {c.gear: c.name for c in box.components}
    gear_of = {c.name: c.gear for c in box.components}
    meshes = [tuple(m) for m in box.meshes]
    count = {c.gear: sum(c.gear in m for m in meshes) for c in box.components}
    moving = turning(desk)
    locked = {g for m in box.mates if m.kind == "lock" for g in m.gears} if moving else set()
    kind = swcom.ASSEMBLY_TRAIN if moving else swcom.ASSEMBLY_STATIC
    want = wanted(desk)
    for a, b in meshes:
        turned, locks = control_gear(box, a, b, count, locked)
        rotation, at, pitch = want[turned]
        started = time.monotonic()
        moved, back = run(worker, lambda s: placed_elsewhere(s, box.assembly, name_of[turned],
                                                              turn_about_z(rotation, pitch / 2), at, kind, locks))
        merged = swbuild._clashes(moved, gear_of)  # noqa: SLF001
        check(bool(merged) and all(set(c.gears) == {a, b} and c.volume > 0 for c in merged),
              f"{label}: {turned} turned half a pitch ({pitch / 2:.4f}°)"
              f"{f' with {locks} suppressed' if locks else ''}: {len(moved)} interference(s), merged "
              f"{[(c.gears, round(c.volume, 3)) for c in merged]}, all between {a} and {b}")
        check(back == [], f"{label}: {turned} put back, no interference ({time.monotonic() - started:.1f} s)")
    if moving:
        measure_frames(worker, desk, f"{label}, after the controls")
        measure_mates(worker, desk, f"{label}, after the controls")


def live_open(session, path):
    """The app's own open of a saved document (OpenDoc6 then ActivateDoc3), reading nothing else."""
    in_assembly(path, lambda s: None)(session)


def reopen(worker, desk, label):
    left = run(worker, close_ours)
    check(not left, f"{label}: saved and closed this run's documents: left {left}")
    say(f"        open now: {run(worker, open_titles)}")
    box = desk.record.gearbox
    paths = [box.assembly, box.layout] + sorted({c.part for c in box.components})
    # Read straight after the open, before any frame read (which read marks the assembly was never isolated).
    run(worker, lambda s: live_open(s, box.assembly))
    flags = run(worker, lambda s: save_flags(s, paths))
    check(len(flags) == len(paths) and not marked(flags),
          f"{label}, reopened: every document just opened from its file reads GetSaveFlag False (the record clears "
          f"a mark on that reading): {flags}")
    measure_frames(worker, desk, f"{label}, reopened")
    say(f"fact    {label}, reopened: marked modified after the frame reads (component_frame): "
        f"{marked(run(worker, lambda s: save_flags(s, paths)))}")
    if turning(desk):
        measure_mates(worker, desk, f"{label}, reopened")
        say(f"fact    {label}, reopened: marked modified after the mate reads (mate_states, GetConstrainedStatus): "
            f"{marked(run(worker, lambda s: save_flags(s, paths)))}")
    found = run(worker, lambda s: live_interferences(s, box.assembly))
    say(f"fact    {label}, reopened: marked modified after interferences() ({len(found)} found): "
        f"{marked(run(worker, lambda s: save_flags(s, paths)))}")


def measure(worker, desk, label, controls=True, again=True):
    """§4.1: frames, axes, interference, the mates (built to turn), the negative controls, and the reopen."""
    say(f"measure {label}: {memory()}; turning {turning(desk)}")
    measure_frames(worker, desk, label)
    measure_axes(worker, desk, label)
    measure_clear(worker, desk, label)
    if turning(desk):
        measure_mates(worker, desk, label)
    if controls:
        negative_controls(worker, desk, label)
    if again:
        reopen(worker, desk, label)


# -- §4.2: the drive, the user's turn, and what Update found -------------------------------------------------


def drive_job(asm, components, layout_name, input_gear, control=None, turn_by=None, fixed=()):
    """One worker job on the assembly. The angle mate DRIVE_MATE from the input's Top plane to the layout's Right at
    90°, its D1 linked to the global DRIVE. ``turn_by`` None: DRIVE 90 -> 120 -> 90; then, given ``control`` (a, b,
    the recorded gear mate's name, its ratio), that mate suppressed and CONTROL + name made in its place with the
    other Flip, driven 90 -> 120 -> 90, deleted, the recorded one turned back on. ``turn_by`` d (the user's turn):
    DRIVE 90 -> 90 + d and the drive taken away at once, leaving the train turned. Whatever happens, the cleanup
    runs in review M12's order — DRIVE set back (not for a user's turn) before the control mate is deleted; the
    recorded gear mate turned back on; the drive's equations deleted (last first) and the angle mate — each step
    on its own, its error kept. Returns every frame read and what was left."""
    def job(session):
        out = {"errors": [], "cleanup": [], "rebuilds": []}
        made = {"global": False, "drive": "", "control": "", "suppressed": False, "at": DRIVE_FROM}
        handle = {}

        def frames():
            return {g: session.component_frame(h) for g, h in handle.items()}

        def rebuild(what):
            out["rebuilds"].append((what, bool(session.rebuild(kind=swcom.ASSEMBLY_TRAIN))))

        def set_drive(value):
            session.set_global_variable(DRIVE, f"{value:g}")
            made["at"] = value
            rebuild(f"{DRIVE} {value:g}")

        def attempt(what, action):
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - kept, and the next cleanup step still runs
                out["cleanup"].append(f"{what}: {type(exc).__name__}: {exc}")

        session.begin_build()
        try:
            try:
                session.open_document(asm)
                for index, (gear, name) in enumerate(components):
                    session.find_component(f"d{index}", name)
                    handle[gear] = f"d{index}"
                session.find_component("dlay", layout_name)
                out["equations_before"] = [text for text, _ in session.equations()]
                out["mates_before"] = [s.name for s in session.mate_states()]
                out["built"] = frames()
                session.add_global_variable(DRIVE, f"{DRIVE_FROM:g}")
                made["global"] = True
                name, dim = session.add_mate("ddrive", "angle", f"{handle[input_gear]}:plane2", "dlay:plane3",
                                             DRIVE_FROM, DRIVE_MATE)
                made["drive"] = name
                out["drive_mate"] = (name, dim, session.mate_status(name))
                session.link_dimension(f"{dim}@{name}", equations.quote(DRIVE))
                rebuild("drive added")
                out["added"] = frames()
                out["states_added"] = [(s.name, s.code, s.warning, s.suppressed) for s in session.mate_states()]
                if turn_by is not None:
                    set_drive(DRIVE_FROM + turn_by)
                    out["turned"] = frames()
                else:
                    set_drive(DRIVE_TO)
                    out["driven"] = frames()
                    out["states_driven"] = [(s.name, s.code, s.warning, s.suppressed) for s in session.mate_states()]
                    set_drive(DRIVE_FROM)
                    out["back"] = frames()
                    if control:
                        a, b, mesh, ratio = control
                        session.find_mate("dmesh", mesh)
                        session.set_mate_suppressed("dmesh", True)
                        made["suppressed"] = True
                        cname, _ = session.add_mate("dctl", "gear", f"{handle[a]}:Gear Axis",
                                                    f"{handle[b]}:Gear Axis", 0.0, CONTROL + mesh,
                                                    ratio=(float(ratio[0]), float(ratio[1])),
                                                    flip=not bool(findings.GEAR_MATE_FLIP))
                        made["control"] = cname
                        out["control_mate"] = (cname, session.mate_status(cname))
                        rebuild("control added")
                        out["control_added"] = frames()
                        set_drive(DRIVE_TO)
                        out["control_driven"] = frames()
                        set_drive(DRIVE_FROM)          # M12: Drive set back before the control mate is deleted
                        out["control_back"] = frames()
            except Exception as exc:  # noqa: BLE001 - said, and the cleanup below still runs
                out["errors"].append(f"{type(exc).__name__}: {exc}")
                out["traceback"] = traceback.format_exc()
            # -- the cleanup, review M12's order
            if made["global"] and turn_by is None and made["at"] != DRIVE_FROM:
                attempt(f"{DRIVE} set back to {DRIVE_FROM:g}", lambda: set_drive(DRIVE_FROM))
            if made["control"]:
                def gone_control():
                    delete_mate(session, made["control"])
                    made["control"] = ""
                attempt("the control mate deleted", gone_control)
            if made["suppressed"]:
                def back_on():
                    session.set_mate_suppressed("dmesh", False)
                    made["suppressed"] = False
                attempt("the recorded gear mate turned back on", back_on)
            if control and turn_by is None and "control_back" in out:
                attempt("rebuilt with the recorded gear mate back", lambda: rebuild("control gone"))
                attempt("frames read", lambda: out.__setitem__("control_gone", frames()))
            if made["global"]:
                def no_equations():
                    texts = [text for text, _ in session.equations()]
                    for index in range(len(texts) - 1, -1, -1):
                        if equations.quote(DRIVE) in texts[index]:
                            session.delete_equation(index)
                attempt(f"the {DRIVE} equations deleted", no_equations)
            if made["drive"]:
                attempt("the angle mate deleted", lambda: delete_mate(session, made["drive"]))
            attempt("rebuilt with the drive gone", lambda: rebuild("drive gone"))
            attempt("the state read after", lambda: out.update(
                after=frames(), equations_after=[text for text, _ in session.equations()],
                states_after=[(s.name, s.code, s.warning, s.suppressed) for s in session.mate_states()],
                constrained_after={g: session.constrained_status(h) for g, h in handle.items() if g not in fixed}))
            return out
        finally:
            session.end_build()
    return job


def expected_turns(desk, gears, input_gear, step):
    """δ_i = step · ω_i / ω_in (W5-DECISIONS M2: speeds about each shaft's own axis), in degrees about each gear's
    own +Z, with the input's turn signed as findings.DEMONSTRATION_DRIVE_SENSE says."""
    speeds = desk.a.report.motion.speeds
    shaft_of = {g.id: g.shaft for g in desk.a.spec.gears}
    w_in = speeds[shaft_of[input_gear]]
    sense = findings.DEMONSTRATION_DRIVE_SENSE
    return {g: sense * step * float(speeds[shaft_of[g]] / w_in) for g in gears}


def say_turns(label, turns, expected):
    say(f"        {label}: " + ", ".join(f"{g} {turns[g]:+.9f}° (kinematics {expected[g]:+.9f}°)"
                                         if turns[g] is not None else f"{g} OFF ITS AXIS" for g in expected))


def close_turn(turn, expected):
    return turn is not None and abs(turn - expected) <= DRIVE_TOLERANCE * max(1.0, abs(expected))


def drive_inputs(desk):
    box = desk.record.gearbox
    components = [(c.gear, c.name) for c in box.components]
    gears = [c.gear for c in box.components]
    return box, components, gears, box.drag[0] if box.drag else ""


def drive_assumptions(desk, input_gear, label):
    """What the drive rests on (W5-PLAN §4.2, ruled on 2026-11-14), asserted before anything is added: a gear to
    drag; the input built at θ = 0 on a Z+ shaft (its Top plane then at 90° to the layout's Right, the angle the
    drive is made at); findings.DEMONSTRATION_DRIVE_SENSE 1 (the sense probe demonstration_drive measured for such an
    input). A gearbox that breaks one stops the run with the sentence, rather than drive from an angle no probe
    measured."""
    if not input_gear:
        raise Halt(f"{label}: the record names no gear to drag, so the drive has no input")
    rotation = wanted(desk)[input_gear][0]
    theta = math.degrees(math.atan2(float(rotation[3]), float(rotation[0])))
    shaft = next(g.shaft for g in desk.a.spec.gears if g.id == input_gear)
    axis = next(sh.axis for sh in desk.a.spec.shafts if sh.id == shaft)
    if abs(theta) > 1e-9 or float(rotation[8]) < 1 - 1e-12 or axis != "Z+":
        raise Halt(f"{label}: the drive is made at 90° from an input built at θ = 0 on a Z+ shaft; {input_gear} is on "
                   f"{shaft} ({axis}) at {theta:.6f}°, R33 {rotation[8]}, so it is not driven")
    if findings.DEMONSTRATION_DRIVE_SENSE != 1:
        raise Halt(f"{label}: findings.DEMONSTRATION_DRIVE_SENSE is {findings.DEMONSTRATION_DRIVE_SENSE!r}, not the 1 "
                   "this drive's expectations were ruled on")
    check(True, f"{label}: the drive's assumptions hold: {input_gear} on {shaft} (Z+) at θ = 0, "
                f"DEMONSTRATION_DRIVE_SENSE 1, tolerance {DRIVE_TOLERANCE:g} relative")


def drive_proof(worker, desk, label, control=None):
    """§4.2 on the current assembly, which must stand at its built turn with the input at θ = 0. ``control``: the
    (a, b) of the recorded gear mate to flip for the wrong-sense control, or None."""
    box, components, gears, input_gear = drive_inputs(desk)
    say(f"drive   {label}: input {input_gear}; control {control}; {memory()}")
    drive_assumptions(desk, input_gear, label)
    mesh_entry = None
    if control is not None:
        mesh_entry = next(m for m in box.mates if m.kind == "mesh" and tuple(m.gears) == tuple(control))
    started = time.monotonic()
    out = run(worker, drive_job(box.assembly, components, box.layout_component, input_gear,
                                control=(tuple(mesh_entry.gears) + (mesh_entry.name, tuple(mesh_entry.ratio)))
                                if mesh_entry is not None else None, fixed=box.fixed))
    say(f"        in {time.monotonic() - started:.1f} s; rebuilds {out['rebuilds']}; drive mate "
        f"{out.get('drive_mate')}; control mate {out.get('control_mate')}")
    for line in out.get("traceback", "").splitlines():
        say("        " + line)
    check(not out["errors"], f"{label}: the drive ran without a raise: {out['errors']}")
    check(not out["cleanup"], f"{label}: every cleanup step ran: {out['cleanup']}")
    built = out.get("built")
    if built is None:
        raise Halt(f"{label}: the drive could not even read the built frames: {out['errors']}")
    record_frames = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in box.components}
    gap, at = frames_gap(built, record_frames)
    check(gap <= FRAME_TOLERANCE, f"{label}: before the drive every gear stands at its frame on record (largest "
          f"{gap:.1e} at {at or '-'})")
    if "added" not in out:
        raise Halt(f"{label}: the 90° drive could not be added: {out['errors']}")
    gap, at = frames_gap(out["added"], built)
    say(f"        states with the drive added: {out.get('states_added')}")
    if gap > FRAME_TOLERANCE:
        raise Halt(f"{label}: adding the 90° drive moved {at} by {gap:.1e} (W5-PLAN §4.2: stop and ask)")
    check(True, f"{label}: adding the 90° drive moved nothing (largest {gap:.1e})")
    expected = expected_turns(desk, gears, input_gear, DRIVE_TO - DRIVE_FROM)
    if "driven" in out:
        turns = {g: turn_degrees(built[g][0], out["driven"][g][0]) for g in gears}
        say_turns(f"{DRIVE} {DRIVE_FROM:g} -> {DRIVE_TO:g}", turns, expected)
        if not close_turn(turns[input_gear], expected[input_gear]):
            raise Halt(f"{label}: the drive turned the input {input_gear} {turns[input_gear]}° where "
                       f"DEMONSTRATION_DRIVE_SENSE says {expected[input_gear]:+g}° (W5-PLAN §4.2: stop and ask)")
        for g in gears:
            check(close_turn(turns[g], expected[g]),
                  f"{label}: {g} turned {turns[g] if turns[g] is None else f'{turns[g]:+.9f}'}° for "
                  f"{expected[g]:+.9f}°, sign included (off "
                  f"{'-' if turns[g] is None else f'{abs(turns[g] - expected[g]):.1e}'})")
        moved = {g: frame_error(out["driven"][g], built[g], 0.0) for g in gears}
        check(all(o <= FRAME_TOLERANCE and r <= FRAME_TOLERANCE for o, _, r in moved.values()),
              f"{label}: driven, every gear stays on its axis and in its place: "
              f"{ {g: (f'{o:.1e}', f'{r:.1e}') for g, (o, _, r) in moved.items()} }")
        say(f"        states driven: {out.get('states_driven')}")
        check(not [s for s in out.get("states_driven", []) if s[1]], f"{label}: no mate in error while driven")
    if "back" in out:
        gap, at = frames_gap(out["back"], built)
        check(gap <= FRAME_TOLERANCE, f"{label}: {DRIVE} set back to {DRIVE_FROM:g}, every gear at its built frame "
              f"(largest {gap:.1e} at {at or '-'})")
    if mesh_entry is not None:
        a, b = mesh_entry.gears
        if "control_driven" in out:
            gap, at = frames_gap(out["control_added"], built)
            check(gap <= FRAME_TOLERANCE, f"{label}, control: the flipped gear mate moved nothing when made "
                  f"(largest {gap:.1e})")
            turns = {g: turn_degrees(built[g][0], out["control_driven"][g][0]) for g in gears}
            say_turns(f"control, {CONTROL + mesh_entry.name} with Flip {not findings.GEAR_MATE_FLIP}", turns, expected)
            seen = (turns[b] is not None and not close_turn(turns[b], expected[b])
                    and close_turn(turns[b], -expected[b]) and abs(expected[b]) > 1e-3)
            check(seen, f"{label}, control: a wrong sense is seen: {b} turned {turns[b]}° where the kinematics say "
                        f"{expected[b]:+.9f}° (the comparison reports it wrong, the mirror of the right turn)")
            check(close_turn(turns[a], expected[a]), f"{label}, control: {a}, before the flipped mesh, still turns "
                  f"{expected[a]:+.9f}° ({turns[a]})")
        else:
            check(False, f"{label}, control: never driven: {out['errors']}")
        for key, what in (("control_back", f"{DRIVE} set back with the control mate on"),
                          ("control_gone", "the control mate deleted and the recorded one back on")):
            if key in out:
                gap, at = frames_gap(out[key], built)
                check(gap <= FRAME_TOLERANCE, f"{label}, control: {what}: every gear at its built frame (largest "
                      f"{gap:.1e} at {at or '-'})")
    # M12, before anything is saved
    if "after" in out:
        gap, at = frames_gap(out["after"], built)
        check(gap <= FRAME_TOLERANCE, f"{label}: the drive gone, every frame against the built frames (largest "
              f"{gap:.1e} at {at or '-'})")
        check(out["equations_after"] == out["equations_before"] and not any(
            equations.quote(DRIVE) in t for t in out["equations_after"]),
              f"{label}: no {DRIVE} equation left: {[t for t in out['equations_after'] if t not in out['equations_before']]}")
        names = [s[0] for s in out["states_after"]]
        check(names == out["mates_before"] and DRIVE_MATE not in names and not any(n.startswith(CONTROL)
                                                                                   for n in names),
              f"{label}: no angle mate or control mate left; the mates as before: {names}")
        check(not [s for s in out["states_after"] if s[3]], f"{label}: no mate (no lock) left suppressed")
        check(not [s for s in out["states_after"] if s[1]], f"{label}: no mate in error after the drive")
        check(all(v == findings.COMPONENT_UNDER_DEFINED for v in out["constrained_after"].values()),
              f"{label}: every mated gear under-defined again: {out['constrained_after']}")
    else:
        check(False, f"{label}: the state after the drive could not be read: {out['cleanup']}")
    return out


def user_turn(worker, desk, label, degrees):
    """The user's turn, simulated (W5-PLAN §4.3): driven ``degrees`` and the drive deleted, as a hand drag leaves
    the train — every gear turned consistently. Returns the frames it left."""
    box, components, gears, input_gear = drive_inputs(desk)
    say(f"turn    {label}: {input_gear} by {degrees:g}° and the drive deleted")
    drive_assumptions(desk, input_gear, label)
    out = run(worker, drive_job(box.assembly, components, box.layout_component, input_gear, turn_by=degrees,
                                fixed=box.fixed))
    say(f"        rebuilds {out['rebuilds']}")
    check(not out["errors"] and not out["cleanup"], f"{label}: turned and the drive deleted: {out['errors']} "
          f"{out['cleanup']}")
    if "after" not in out or "built" not in out or "added" not in out:
        raise Halt(f"{label}: the user's turn left no frames to read: {out['errors']} {out['cleanup']}")
    gap, at = frames_gap(out["added"], out["built"])
    if gap > FRAME_TOLERANCE:
        raise Halt(f"{label}: adding the 90° drive moved {at} by {gap:.1e} (W5-PLAN §4.2: stop and ask)")
    expected = expected_turns(desk, gears, input_gear, degrees)
    turns = {g: turn_degrees(out["built"][g][0], out["after"][g][0]) for g in gears}
    say_turns("left turned", turns, expected)
    check(all(close_turn(turns[g], expected[g]) for g in gears), f"{label}: every gear left turned as the "
          "kinematics say")
    check(not any(equations.quote(DRIVE) in t for t in out.get("equations_after", [])) and DRIVE_MATE not in
          [s[0] for s in out.get("states_after", [])], f"{label}: no drive left")
    links = desk.update.motion if desk.update is not None else None
    if links is not None:
        record_frames = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in box.components}
        pitch = {p.gear: p.pitch for p in links.recorded}
        mated = [g for g in gears if g not in box.fixed]
        tc = swbuild.train_check({g: out["after"][g] for g in mated}, {g: record_frames[g] for g in mated},
                                 links.meshes, links.locks, pitch)
        say(f"        train_check after the turn: in step {tc.in_step}, turned {tc.turned}, off axis {tc.off_axis}, "
            f"out of step {tc.out_of_step}, residuals {[(a, b, f'{r:.2e}') for a, b, r in tc.residuals]}")
        check(tc.in_step and tc.turned, f"{label}: train_check reads the train in step and turned")
    return out["after"]


def say_found(result, recorded, label):
    """Each gear's origin, axis and turn residuals as Update found it (``result.found``, read before anything moved)
    against the frames on record before the press (``recorded``)."""
    for gear, (rotation, at) in recorded.items():
        found = result.found.get(gear)
        if found is None:
            say(f"        {label}: {gear} not read")
            continue
        origin, _, residue = frame_error(found, (rotation, at), 0.0)
        say(f"        {label}: {gear} found with its origin off {origin:.2e} mm and its axis off {residue:.2e}, "
            f"turned {turn_degrees(rotation, found[0])}° from its frame on record")


def update_marks(worker, desk, result, label, folder):
    paths = [os.path.join(folder, n) for n in os.listdir(folder) if n.upper().endswith((".SLDPRT", ".SLDASM"))]
    flags = run(worker, lambda s: save_flags(s, paths))
    say(f"        marked modified in SolidWorks right after the update: {flags}")
    check_marks(flags, expected_marks(result, desk.record.gearbox.assembly), label)


def all_mated(desk):
    box = desk.record.gearbox
    return sorted(c.gear for c in box.components if c.gear not in box.fixed)


def update_nothing_turned(worker, desk, label, folder):
    """Update pressed with nothing changed on a train the user turned: no put, nothing changed, the sentence."""
    desk.say_update()
    desk.say_footer(f"{label}, before the press")
    recorded = frames_on_record(desk)
    guard()
    _, result, _ = desk.update_solidworks()
    if result is None:
        return check(False, f"{label}: Update refused: {desk.note[0]}")
    say_found(result, recorded, label)
    check(result.ok and result.placed == [] and result.turned and not result.restored and result.changed == [],
          f"{label}: nothing put, nothing changed, the train found turned: placed {result.placed}, turned "
          f"{result.turned}, restored {result.restored}, changed {[os.path.basename(p) for p in result.changed]}")
    check(desk.record.unsaved == {}, f"{label}: the record marks nothing unsaved: {list(desk.record.unsaved)}")
    check(TURNED_SENTENCE in desk.note[0], f"{label}: the sentence ends {TURNED_SENTENCE!r}")
    update_marks(worker, desk, result, label, folder)
    desk.say_footer(f"{label}, after the press")
    return result


# -- Excel ----------------------------------------------------------------------------------------------------


OPEN_BOOKS = []            # every Workbook opened and not yet closed, so main closes what a section left open


class Workbook:
    """One workbook open in this run's own Excel."""

    def __init__(self, excel, path, tag):
        self.path = path
        self.wb, report = excel.open(path, tag)
        if self.wb is not None:
            OPEN_BOOKS.append(self)
        check(self.wb is not None and not report["repaired"],
              f"Excel opened {os.path.basename(path)} with no dialog or repair: {report.get('dialogs')}")

    def set(self, sheet, ref, value):
        cell = self.wb.Worksheets(sheet).Range(ref)
        if value is None:
            cell.ClearContents()
        elif isinstance(value, str) and value.startswith("="):
            cell.Formula = value
        else:
            cell.Value = value
        say(f"excel   {sheet}!{ref} := {value!r}")

    def get(self, sheet, ref):
        return self.wb.Worksheets(sheet).Range(ref).Value

    def save(self):
        self.wb.Save()
        say(f"excel   saved {os.path.basename(self.path)}")

    def close(self):
        self.wb.Close(SaveChanges=False)
        self.wb = None
        if self in OPEN_BOOKS:
            OPEN_BOOKS.remove(self)


def close_books():
    """Close, unsaved, every workbook a section left open (Excel keeps one workbook per file name, so the next
    section could not open its own beside it). Returns the names closed."""
    closed = []
    for book in list(OPEN_BOOKS):
        try:
            book.close()
            closed.append(os.path.basename(book.path))
        except Exception as exc:  # noqa: BLE001 - logged; the next section's own open check says what follows
            say(f"excel   could not close {os.path.basename(book.path)}: {exc}")
            if book in OPEN_BOOKS:
                OPEN_BOOKS.remove(book)
    return closed


def fresh_folder(name):
    folder = os.path.join(OUT, name)
    if os.path.exists(folder):
        raise SystemExit(f"{folder} exists already; give a fresh output folder")
    os.makedirs(folder)
    return folder


def fixture_desk(worker, excel, section, fixture):
    """A fixture copied into the section's folder, its Output folder set in Excel, read and planned."""
    folder = fresh_folder(section)
    path = os.path.join(folder, os.path.basename(fixture))
    shutil.copy2(fixture, path)
    book = Workbook(excel, path, section)
    book.set("Box", "B4", folder + "\\")
    book.save()
    desk = Desk(path, worker)
    desk.read()
    check(desk.a.lay_out_refusal() == "", "the gate is \"\"")
    return folder, path, book, desk


def build_turning(worker, desk, label, parts):
    """Build, and the checks every turning build gets before §4.1: saved, turning, no interference, the marks, the
    footer with the drag instruction."""
    desk.say_footer(f"{label}, read")
    desk.say_plan()
    check(desk.plan is not None and desk.plan.motion is not None and not desk.plan.static_reason,
          f"{label}: the plan turns (W5): static reason {desk.plan.static_reason if desk.plan else None!r}")
    guard()
    plan, result = desk.build()
    if result is None:
        raise AssertionError(f"{label}: the build was refused: {desk.note[0]}")
    check(result.ok and result.kind == store.GEARBOX_MOTION and len(result.parts.built) == parts,
          f"{label}: {parts} parts, the layout part and the assembly built and saved, turning: ok {result.ok}, "
          f"parts {len(result.parts.built)}, kind {result.kind!r}")
    check(result.clashes == [] and not result.interference_error, f"{label}: no interference: {result.clashes}")
    box = desk.record.gearbox
    check(box is not None and box.kind == store.GEARBOX_MOTION and box.assembly and desk.record.digest
          == desk.reading.digest, f"{label}: the record holds a turning gearbox built from this read")
    check(len(box.mates) == len(plan.motion.mates) and [m.name for m in box.mates] == [m.name for m in plan.motion.mates],
          f"{label}: the record's mates are the plan's: {[m.name for m in box.mates]}")
    drag = ui_text.drag_phrase(list(box.drag))
    check(drag in desk.note[0], f"{label}: the build's sentence says how to turn it: {drag!r}")
    f = desk.say_footer(f"{label}, built")
    check(drag in f.text, f"{label}: the footer says how to turn it: {drag!r}")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    paths = [box.layout, box.assembly] + sorted({c.part for c in box.components})
    check(all(os.path.isfile(p) for p in paths), f"{label}: {len(paths)} files on disk")
    check_fresh_build_marks(worker, paths, box.assembly, label)
    return plan, result


def frames_on_record(desk):
    return {c.gear: (tuple(c.rotation), tuple(c.at)) for c in desk.record.gearbox.components}


# -- the workbooks of b and c ------------------------------------------------------------------------------


def _f(v):
    return repr(round(v, 12))


ARC_R = 2 * (18 + 22) / 2           # stage 1: 18 / 22 teeth, module 2: 40 mm; stage 2: 17 / 23, also 40 mm


def spec_arc(folder, angle=30.0):
    x, y = ARC_R * math.cos(math.radians(angle)), ARC_R * math.sin(math.radians(angle))
    return GearboxSpec(
        box=Box(name="Arc_Move", output_folder=folder),
        shafts=(Shaft("S1", "frame", "0", "0", "0", "Z+", "input", speed="1000", torque="5"),
                Shaft("S2", "frame", _f(x), _f(y), "0", "Z+"),
                Shaft("S3", "frame", _f(x + 40), _f(y), "0", "Z+", "output")),
        gears=(Gear("G1", "S1", "5", "spur", "external", "18", "2", face_width="10", bore="6"),
               Gear("G2", "S2", "5", "spur", "external", "22", "2", face_width="10", bore="8"),
               Gear("G3", "S2", "20", "spur", "external", "17", "2", face_width="10", bore="8"),
               Gear("G4", "S3", "20", "spur", "external", "23", "2", face_width="10", bore="8")),
        meshes=(Mesh("G1", "G2"), Mesh("G3", "G4")))


def spec_risky(folder):
    """A helical pair across Z+ (S1) and Z- (S2); herringbones of 16 and 12 mm face on Z- (S2) and Z+ (S3); a
    helical pinion on Z+ (S3) in a helical ring whose shaft is Z- (S4). Small tooth counts, modest faces."""
    beta, beta_h = 20.0, 25.0
    a12 = 2 * (14 + 20) / (2 * math.cos(math.radians(beta)))
    a34 = 2 * (14 + 22) / (2 * math.cos(math.radians(beta_h)))
    a56 = 2 * (36 - 14) / (2 * math.cos(math.radians(beta)))
    s2, s3 = (a12, 0.0), (a12, -a34)
    s4 = (a12 + a56, -a34)
    return GearboxSpec(
        box=Box(name="Risky_Placements", output_folder=folder),
        shafts=(Shaft("S1", "frame", "0", "0", "0", "Z+", "input", speed="1000", torque="5"),
                Shaft("S2", "frame", _f(s2[0]), _f(s2[1]), "0", "Z-"),
                Shaft("S3", "frame", _f(s3[0]), _f(s3[1]), "0", "Z+"),
                Shaft("S4", "frame", _f(s4[0]), _f(s4[1]), "0", "Z-", "output")),
        gears=(Gear("G1", "S1", "5", "helical", "external", "14", "2", face_width="10", bore="6",
                    helix_angle=str(beta), hand="right"),
               Gear("G2", "S2", "-5", "helical", "external", "20", "2", face_width="10", bore="8",
                    helix_angle=str(beta), hand="left"),
               Gear("G3", "S2", "-24", "herringbone", "external", "14", "2", face_width="16", bore="8",
                    helix_angle=str(beta_h), hand="right"),
               Gear("G4", "S3", "24", "herringbone", "external", "22", "2", face_width="12", bore="8",
                    helix_angle=str(beta_h), hand="right"),
               Gear("G5", "S3", "45", "helical", "external", "14", "2", face_width="10", bore="8",
                    helix_angle=str(beta), hand="left"),
               Gear("G6", "S4", "-45", "helical", "internal", "36", "2", face_width="10",
                    helix_angle=str(beta), hand="left")),
        meshes=(Mesh("G1", "G2"), Mesh("G3", "G4"), Mesh("G5", "G6")))


def keep_fixture(book, name, neutral):
    """Save the workbook in Excel with a neutral Output folder and copy that file out as a fixture."""
    if not FIXTURES:
        return
    book.set("Box", "B4", neutral)
    book.save()
    os.makedirs(FIXTURES, exist_ok=True)
    shutil.copy2(book.path, os.path.join(FIXTURES, name))
    say(f"fixture {name} copied, as Excel saved it, with Output folder {neutral!r}")


# -- the W5 sections ------------------------------------------------------------------------------------------


def m7_unknown_mate(worker, desk, folder):
    """Review M7: an angle mate the record does not know, touching G4, unsuppressed -> Update refuses in its check
    phase naming it; suppressed -> Update goes through and lists it as left alone. Then deleted."""
    say("-- m1  M7: an angle mate Gear Generator did not make, on G4")
    box = desk.record.gearbox
    g4 = next(c.name for c in box.components if c.gear == "G4")

    def add(s):
        s.find_component("u4", g4)
        s.find_component("ulay", box.layout_component)
        name, _ = s.add_mate("user", "angle", "u4:plane2", "ulay:plane3", DRIVE_FROM)
        s.rebuild(kind=swcom.ASSEMBLY_TRAIN)
        return name, s.mate_status(name)
    name, status = run(worker, in_assembly(box.assembly, add))
    say(f"        made {name!r} (SolidWorks' own name), AddMate5 status {status}")
    desk.plan_solidworks()
    desk.say_update()
    guard()
    _, result, _ = desk.update_solidworks()
    check(result is None and desk.error is not None and name in desk.note[0],
          f"M7: Update refuses before changing anything, naming {name}: {desk.note[0]!r}")

    def suppress(s):
        s.find_mate("um", name)
        s.set_mate_suppressed("um", True)
        s.rebuild(kind=swcom.ASSEMBLY_TRAIN)
    run(worker, in_assembly(box.assembly, suppress))
    say(f"        {name} suppressed in SolidWorks, as the sentence asks")
    desk.plan_solidworks()
    guard()
    _, result, _ = desk.update_solidworks()
    check(result is not None and result.ok and result.extra_mates == [name],
          f"M7: suppressed, Update goes through and lists it: extra mates {result and result.extra_mates}")
    check(result is not None and name in " ".join(result.log_lines()), f"M7: the log names {name} as left alone")
    run(worker, in_assembly(box.assembly, lambda s: (delete_mate(s, name), s.rebuild(kind=swcom.ASSEMBLY_TRAIN))))
    say(f"        {name} deleted")
    measure_mates(worker, desk, "m1 after M7")
    save_assembly(worker, desk, "after M7")
    desk.plan_solidworks()


def d10_suppressed_mate(worker, desk, folder):
    """D10: a recorded mate suppressed in SolidWorks -> Update turns it back on and says so."""
    say("-- m1  D10: G4 along S3 suppressed in SolidWorks")
    box = desk.record.gearbox
    mate = next(m.name for m in box.mates if m.kind == "along" and m.gears == ["G4"])

    def suppress(s):
        s.find_mate("dm", mate)
        s.set_mate_suppressed("dm", True)
        s.rebuild(kind=swcom.ASSEMBLY_TRAIN)
    run(worker, in_assembly(box.assembly, suppress))
    save_assembly(worker, desk, f"with {mate} suppressed, so Update's own marks show")
    desk.plan_solidworks()
    desk.say_update()
    guard()
    _, result, _ = desk.update_solidworks()
    check(result is not None and result.ok and result.unsuppressed == [mate],
          f"D10: Update turned {mate} back on: unsuppressed {result and result.unsuppressed}")
    check(result is not None and mate in desk.note[0], f"D10: the sentence names {mate}: {desk.note[0]!r}")
    if result is not None:
        update_marks(worker, desk, result, "D10", folder)
    measure_frames(worker, desk, "m1 after D10")
    measure_mates(worker, desk, "m1 after D10")
    save_assembly(worker, desk, "after D10")
    desk.plan_solidworks()


def section_m1(worker, excel):
    say("== m1  the 12 : 1 fixture built to turn: §4.1, §4.2, M7, D10, the user's turn, At edits, the tooth change "
        "by the remake, Build again…")
    folder, path, book, desk = fixture_desk(worker, excel, "m1", FIXTURE_12)
    build_turning(worker, desk, "m1", 4)
    measure(worker, desk, "m1 built")
    drive_proof(worker, desk, "m1 built", control=("G3", "G4"))
    save_assembly(worker, desk, "after the drive, which left nothing behind")
    desk.plan_solidworks()
    m7_unknown_mate(worker, desk, folder)
    d10_suppressed_mate(worker, desk, folder)

    say("-- m1  the user's turn, simulated: 37°; then Update with nothing changed")
    user_turn(worker, desk, "m1", 37.0)
    save_assembly(worker, desk, "after the turn, as a person might")
    desk.plan_solidworks()
    update_nothing_turned(worker, desk, "m1 turned 37°", folder)

    say("-- m1  Excel: G4 At 27 -> 30")
    edit(desk, book, ("Gears", "C5", 30))
    u = desk.update
    check(u is not None and not u.needs_new_revision and list(u.axial) == ["G4"],
          f"classify: an Update moving G4 along S3: axial {u and list(u.axial)}, structural {u and list(u.structural)}")
    recorded = frames_on_record(desk)
    guard()
    _, result, _ = desk.update_solidworks()
    if result is not None:
        say_found(result, recorded, "G4 At")
        check(result.ok and result.axial == ["G4"], f"G4 At: \"G4 Face Z\" set: axial {result.axial}")
        restored = bool(result.restored)
        say(f"fact    G4 At: Update {'put the turned train back at its built turn' if restored else 'left the train turned'}"
            f": placed {result.placed}, restored {result.restored}, turned {result.turned}")
        check(restored == AXIAL_RESTORES, f"G4 At: the train {'is' if AXIAL_RESTORES else 'is not'} put back at its "
              f"built turn, as AXIAL_RESTORES expects (W5-PLAN §4.3, answer 2; asked of the coordinator)")
        face = run(worker, lambda s: live_globals(s, desk.record.gearbox.assembly)).get("G4 Face Z")
        check(face is not None and abs(face - 20.0) < 1e-9, f"G4 At: the assembly's \"G4 Face Z\" reads {face} "
              "for 20 (At 30, face width 20)")
        update_marks(worker, desk, result, "G4 At", folder)
        check(result.clashes == [] and not result.interference_error, f"G4 At: no interference {result.clashes}")
        if restored:
            measure_frames(worker, desk, "m1 G4 At")
            measure_mates(worker, desk, "m1 G4 At")
            drive_proof(worker, desk, "m1 G4 At")
        else:
            measure_frames_turned(worker, desk, "m1 G4 At")
            say("        left turned: the drive waits for the train at its built turn (G3 At puts it back)")
            measure_mates(worker, desk, "m1 G4 At")
    save_assembly(worker, desk, "after G4 At")
    desk.plan_solidworks()

    say("-- m1  Excel: G3 At 27 -> 29 (a follower: an Update under suppressed locks)")
    edit(desk, book, ("Gears", "C4", 29))
    u = desk.update
    check(u is not None and not u.needs_new_revision and "G3" in u.replaced,
          f"classify: an Update re-placing G3 (LOCK_RETAKES_AN_OFFSET): structural {u and list(u.structural)}")
    guard()
    _, result, _ = desk.update_solidworks()
    if result is not None:
        check(result.ok and sorted(result.placed) == all_mated(desk), f"G3 At: every mated gear put (review M1): "
              f"placed {result.placed}")
        update_marks(worker, desk, result, "G3 At", folder)
        measure_frames(worker, desk, "m1 G3 At")
        measure_mates(worker, desk, "m1 G3 At")
        measure_clear(worker, desk, "m1 G3 At")
        drive_proof(worker, desk, "m1 G3 At")
    save_assembly(worker, desk, "after G3 At")
    desk.plan_solidworks()

    say("-- m1  Excel: the W4 demonstration edit: S2 X 63.75 -> 64.5, G2 Teeth 68 -> 69 (S3 X follows)")
    edit(desk, book, ("Shafts", "C3", 64.5), ("Gears", "F3", 69))
    u = desk.update
    check(u is not None and not u.needs_new_revision and [p.gear_ids for p in u.changed_parts] == [("G2",)]
          and u.moved_shafts == ("S2", "S3") and list(u.ratios) == ["G1 meshes G2"],
          "classify: an Update by the remake: G2's values, S2 and S3 moved, the gear mate G1 meshes G2 at 17 : 69")
    guard()
    before = stamps(folder, solidworks_only=True)
    _, result, _ = desk.update_solidworks()
    if result is not None:
        check(result.ok and result.ratios == ["G1 meshes G2"] and sorted(result.placed) == all_mated(desk),
              f"tooth change: the gear mate remade, every gear put: ratios {result.ratios}, placed {result.placed}")
        changed = sorted(os.path.basename(p) for p in result.changed)
        check(changed == ["Gear_m1.5_N68.SLDPRT", "Reducer_12to1.SLDASM", "Reducer_12to1_Layout.SLDPRT"],
              f"tooth change: changed {changed}")
        after = stamps(folder, solidworks_only=True)
        check([n for n in before if before[n] != after.get(n)] == [], "tooth change: Update saved nothing")
        entry = next(m for m in desk.record.gearbox.mates if m.name == "G1 meshes G2")
        check(list(entry.ratio) == [17, 69], f"tooth change: the record's G1 meshes G2 ratio {entry.ratio}")
        g2 = next(c for c in desk.record.gearbox.components if c.gear == "G2")
        teeth = run(worker, lambda s: live_globals(s, g2.part)).get("No. of Teeth")
        check(teeth is not None and abs(teeth - 69) < 1e-9, f"tooth change: G2's part holds \"No. of Teeth\" = {teeth}")
        update_marks(worker, desk, result, "tooth change", folder)
        measure_frames(worker, desk, "m1 tooth change")
        measure_mates(worker, desk, "m1 tooth change")
        measure_axes(worker, desk, "m1 tooth change")
        measure_clear(worker, desk, "m1 tooth change")
        drive_proof(worker, desk, "m1 at 17 : 69")
        reopen(worker, desk, "m1 tooth change")
    desk.plan_solidworks()

    say("-- m1  Excel: G1 face width 15 -> 17: its front face leaves the Front plane, so Build again…")
    edit(desk, book, ("Gears", "I2", 17))
    u = desk.update
    check(u is not None and u.needs_new_revision and any("G1's face width" in s and "Front plane" in s
                                                         for s in u.structural),
          f"classify: structural, the sentence naming the edit: {u and list(u.structural)}")
    desk.say_plan(full=False)
    p = desk.plan
    say(f"question {ui_text.build_again_question(desk.update, p, record=desk.record)}")
    check(p is not None and not p.refusal and p.revision == 2 and p.motion is not None,
          f"the plan: Reducer_12to1_r2, turning: revision {p and p.revision}")
    earlier, earlier_sidecars = stamps(folder), sidecar_texts(folder)
    guard()
    _, result = desk.build()
    later = check_earlier_unchanged(folder, earlier, "m1 build again", earlier_sidecars)
    say(f"        new files {sorted(n for n in later if n not in earlier)}")
    if result is not None:
        check(result.ok and result.kind == store.GEARBOX_MOTION and desk.record.gearbox.revision == 2,
              f"Reducer_12to1_r2 built turning: kind {result.kind!r}, revision {desk.record.gearbox.revision}")
        desk.say_footer("m1 _r2 built")
        measure(worker, desk, "m1 _r2")
        drive_proof(worker, desk, "m1 _r2", control=("G3", "G4"))
    book.close()


def measure_frames_turned(worker, desk, label):
    """A train left turned: every gear on its axis at its place (origins and axes against the read's frames), and
    in step (train_check against the read's frames)."""
    box = desk.record.gearbox
    names = [c.name for c in box.components]
    live = run(worker, lambda s: live_frames(s, box.assembly, names))
    want = wanted(desk)
    found = {c.gear: live[c.name] for c in box.components}
    for c in box.components:
        origin, _, residue = frame_error(found[c.gear], want[c.gear][:2], 0.0)
        check(origin <= FRAME_TOLERANCE and residue <= FRAME_TOLERANCE,
              f"{label}: {c.gear} on its axis at its place: origin off {origin:.1e} mm, axis off {residue:.1e}; turned "
              f"{turn_degrees(want[c.gear][0], found[c.gear][0])}°")
    links = desk.update.motion if desk.update is not None else None
    if links is not None:
        mated = [c.gear for c in box.components if c.gear not in box.fixed]
        tc = swbuild.train_check({g: found[g] for g in mated}, {g: want[g][:2] for g in mated}, links.meshes,
                                 links.locks, {g: want[g][2] for g in mated})
        say(f"        train_check: in step {tc.in_step}, turned {tc.turned}, residuals "
            f"{[(a, b, f'{r:.2e}') for a, b, r in tc.residuals]}")
        check(tc.in_step, f"{label}: the train in step")
    return found


def section_m2(worker, excel):
    say("== m2  Arc_Move built to turn: §4.1, §4.2, the user's turn, then S2 moved along its arc")
    folder, path, book, desk = fixture_desk(worker, excel, "m2", FIXTURE_ARC)
    build_turning(worker, desk, "m2", 4)
    measure(worker, desk, "m2 built", again=False)
    drive_proof(worker, desk, "m2 built", control=("G1", "G2"))
    save_assembly(worker, desk, "after the drive")
    desk.plan_solidworks()
    say("-- m2  the user's turn, simulated: 25°; then Update with nothing changed")
    user_turn(worker, desk, "m2", 25.0)
    save_assembly(worker, desk, "after the turn")
    desk.plan_solidworks()
    update_nothing_turned(worker, desk, "m2 turned 25°", folder)
    say("-- m2  Excel: the angle 30 -> 40 (S2 and S3 move along the arc by formula)")
    edit(desk, book, ("Shafts", "L3", 40))
    u = desk.update
    check(u is not None and not u.needs_new_revision and not u.changed_parts and u.moved_shafts == ("S2", "S3"),
          "classify: no part values, S2 and S3 moved")
    recorded = frames_on_record(desk)
    guard()
    _, result, _ = desk.update_solidworks()
    if result is not None:
        say_found(result, recorded, "arc move")
        check(result.ok and result.layout is not None and sorted(result.layout.changed) == ["S2 X", "S2 Y", "S3 X",
                                                                                           "S3 Y"],
              f"arc move: the layout's S2 X, S2 Y, S3 X, S3 Y set: {result.layout and result.layout.changed}")
        check(sorted(result.placed) == all_mated(desk) and result.restored,
              f"arc move: the whole train put back at its built turn: placed {result.placed}, restored "
              f"{result.restored}")
        update_marks(worker, desk, result, "arc move", folder)
        measure_frames(worker, desk, "m2 moved")
        measure_axes(worker, desk, "m2 moved")
        measure_mates(worker, desk, "m2 moved")
        measure_clear(worker, desk, "m2 moved")
        drive_proof(worker, desk, "m2 moved")
        reopen(worker, desk, "m2 moved")
    book.close()


def section_m3(worker, excel):
    say("== m3  Risky_Placements built to turn: Z- shafts, compound shafts, a ring; §4.1, §4.2 with the control on "
        "the ring's mesh")
    folder, path, book, desk = fixture_desk(worker, excel, "m3", FIXTURE_RISKY)
    build_turning(worker, desk, "m3", 6)
    measure(worker, desk, "m3 built")
    drive_proof(worker, desk, "m3 built", control=("G5", "G6"))
    save_assembly(worker, desk, "after the drive")
    desk.plan_solidworks()
    say("-- m3  the user's turn, simulated: 20°; then Update with nothing changed")
    user_turn(worker, desk, "m3", 20.0)
    save_assembly(worker, desk, "after the turn")
    desk.plan_solidworks()
    update_nothing_turned(worker, desk, "m3 turned 20°", folder)
    book.close()


def injected(plan, offset):
    """The m4 plan: the turning assembly's ops with G3 — the follower locked to G2 — also mated on S2 Axis and along
    S2 (``offset`` mm off where it stands), right after its lock (W5-PLAN §4.3 m4: over-defined, as probe
    compound_lock found)."""
    handle_of = {g: h for h, g in plan.handles.items()}
    h3 = handle_of["G3"]
    z = plan.frames["G3"].at[2] + offset
    ops, done = [], False
    for op in plan.assembly.ops:
        ops.append(op)
        if not done and isinstance(op, base.Mate) and op.kind == "lock" and op.b == h3:
            ops.append(base.Mate("inject1", "coincident", f"{h3}:Gear Axis", f"{wb_layout.LAYOUT_HANDLE}:S2 Axis",
                                 name="G3 on S2 Axis"))
            ops.append(base.Mate("inject2", "point distance", f"{h3}:origin", f"{wb_layout.LAYOUT_HANDLE}:plane1", z,
                                 name="G3 along S2"))
            done = True
    if not done:
        raise AssertionError("m4: the plan has no lock on G3 to inject beside")
    return dataclasses.replace(plan, assembly=dataclasses.replace(plan.assembly, ops=tuple(ops)))


def p0c_findings():
    """What probe round P0c set, by name (read when it is committed; logged whatever it is)."""
    keys = ("SECOND_ASSEMBLY", "COMMAND_IN_PROGRESS", "LIGHTWEIGHT", "MATE_FOLDER", "FOLDER", "IDLER",
            "UNSUPPRESS_ON", "SUPPRESSED_MATE", "RENAME_AT_ONCE", "TWICE_MESHED")
    return {name: getattr(findings, name) for name in dir(findings) if name.isupper() and any(k in name for k in keys)}


def refused_state(session, title):
    """The refused, never-saved assembly ``title``: its components' constrained statuses and its mates' states,
    read in place (it has no file to open), changing nothing."""
    app = session._app  # noqa: SLF001
    doc = next((d for d in documents(app) if str(call(d, "GetTitle")) == title), None)
    if doc is None:
        return None
    comps = call(doc, "GetComponents", True) or ()
    status = {str(call(c, "Name2")): swcom._read(c, "GetConstrainedStatus") for c in comps}  # noqa: SLF001
    session.begin_build()
    try:
        session._build_doc = doc  # noqa: SLF001 - read the refused document's mate group in place
        others = []
        states = session.mate_states(others=others)
    finally:
        session.end_build()
    return {"path": str(call(doc, "GetPathName") or ""), "modified": bool(call(doc, "GetSaveFlag")),
            "constrained": status, "mates": [(s.name, s.code, s.warning, s.suppressed) for s in states],
            "others": others}


def m4_attempt(worker, excel, section, offset):
    """One forced build: the 12 : 1 in its own folder, G3 given the extra mates ``offset`` mm off where it stands.
    Logs everything SolidWorks reported; returns (folder, book, desk, result, refused)."""
    folder, path, book, desk = fixture_desk(worker, excel, section, FIXTURE_12)
    desk.say_plan(full=False)
    plan = injected(desk.plan, offset)
    say(f"        injected ({offset:g} mm off): "
        f"{[base.describe(op) for op in plan.assembly.ops if getattr(op, 'id', '').startswith('inject')]}")
    guard()
    _, result = desk.build(plan)
    if result is None:
        raise AssertionError(f"{section}: the build raised: {desk.note[0]}")
    asm = result.assembly
    names = [op.name for op in plan.assembly.ops if isinstance(op, base.Mate)]
    statuses = run(worker, lambda s: {n: s.mate_status(n) for n in names})
    say(f"        AddMate5 statuses {statuses}")
    say(f"        mate states {[(s.name, s.code, s.warning, s.suppressed) for s in (asm.mates if asm else [])]}")
    say(f"        mate problems {asm.mate_problems if asm else None}; failures {asm.failures if asm else None}")
    say(f"        left open as {asm.document if asm else None!r}; saved {asm.saved if asm else None!r}")
    refused = bool(asm is not None and asm.mate_problems and not asm.saved)
    if refused and asm.document:
        REFUSED.append(asm.document)
        state = run(worker, lambda s: refused_state(s, asm.document))
        say(f"        the refused document as it stands (constrained statuses, mates): {state}")
        check(state is not None and not state["path"], f"{section}: {asm.document} is open, never saved")
    elif not refused and desk.record is not None and desk.record.gearbox is not None and desk.record.gearbox.assembly:
        box = desk.record.gearbox
        states, others, status = run(worker, lambda s: live_mates(s, box.assembly,
                                                                  [(c.gear, c.name) for c in box.components]))
        say(f"        the assembly SolidWorks saved: mates {[(x.name, x.code, x.warning, x.suppressed) for x in states]}; "
            f"others {others}; constrained {status}")
    return folder, book, desk, result, refused


def section_m4(worker, excel):
    say("== m4  a refused mate, forced: G3 also on S2 Axis and along S2 -> the build stops")
    say(f"findings P0c {p0c_findings()}")
    # Ruled on 2026-11-14: the consistent extra mates first; if SolidWorks accepts them (nothing the app's mate check
    # flags), that is a finding, and the build is forced again with the along mate 1 mm off.
    offsets = [M4_OFFSET] + ([1.0] if M4_OFFSET == 0.0 else [])
    for index, offset in enumerate(offsets):
        section = "m4" if index == 0 else f"m4-offset{offset:g}"
        say(f"-- {section}  the extra mates {offset:g} mm off where G3 stands")
        folder, book, desk, result, refused = m4_attempt(worker, excel, section, offset)
        if refused:
            say(f"fact    m4: the refusal was made by the extra mates {offset:g} mm off "
                f"({'consistent with where G3 stands' if offset == 0.0 else 'conflicting with the lock'})")
            break
        say(f"fact    m4: FINDING: SolidWorks accepted the extra mates {offset:g} mm off — no AddMate5 status, error "
            "code, warning or constrained status the app's mate check flags — and the assembly was saved: kind "
            f"{result.kind!r}")
        left = run(worker, close_ours)
        say(f"        {section} closed: left {left}")
        book.close()
    else:
        check(False, f"m4: no case made the refusal (offsets {offsets})")
        return
    asm = result.assembly
    check(asm.mate_problems and not asm.saved and asm.document,
          f"{section}: the build stopped at the mate check, the assembly not saved, left open as {asm.document!r}")
    check(not os.path.exists(os.path.join(folder, "Reducer_12to1.SLDASM")), f"{section}: no assembly file")
    check(result.kind == "", f"{section}: nothing saved in its place: kind {result.kind!r}")
    rec = desk.record
    check(rec is not None and len(rec.parts) == 4 and rec.gearbox.layout and not rec.gearbox.assembly
          and all(os.path.isfile(e.path) for e in rec.parts) and os.path.isfile(rec.gearbox.layout),
          "m4: the parts and the layout part saved and on record, no assembly on record")
    check(rec is not None and rec.gearbox.mate_problems == list(asm.mate_problems)
          and rec.gearbox.mate_problems_digest == desk.reading.digest,
          f"m4: the record's mate problems and their digest: {rec and rec.gearbox.mate_problems}")
    f = desk.say_footer("refused")
    check(not f.build_enabled and "Build is available again once the workbook changes" in f.text,
          "m4: the footer never offers the same build of the unchanged workbook")
    check(any(p in desk.note[0] for p in asm.mate_problems), "m4: the sentence names the mate SolidWorks refused or "
          "flagged")

    say("-- m4  a note cell changed in Excel (the plan unchanged, without the injection): Build again")
    edit(desk, book, ("Meshes", "D3", "stage 2, refused once"))
    f = desk.say_footer("the workbook changed")
    desk.say_plan(full=False)
    p = desk.plan
    check(f.build_enabled and p is not None and p.revision == 0 and not p.build and len(p.reuse) == 4
          and isinstance(p.layout, wb_gearbox.LayoutReuse),
          "m4: Build on again; the same revision, the parts and the layout reused, only the assembly to make")
    beside = next((v for k, v in p0c_findings().items() if "SECOND_ASSEMBLY" in k and isinstance(v, bool)), None)
    if beside is not True and asm is not None and asm.document:
        say(f"        P0c's finding on a second assembly beside an unsaved one is {beside!r}: the refused one is "
            "closed first")
        left = run(worker, close_ours)
        check(not left, f"m4: closed: left {left}")
    else:
        say(f"        the refused {asm.document if asm else ''} stays open beside the new build (P0c: {beside!r})")
    guard()
    _, result = desk.build()
    if result is not None:
        check(result.ok and result.kind == store.GEARBOX_MOTION and desk.record.gearbox.revision == 0
              and os.path.isfile(os.path.join(folder, "Reducer_12to1.SLDASM")),
              f"m4: the assembly made at the same revision, turning: kind {result.kind!r}")
        check(desk.record.gearbox.mate_problems == [] and desk.record.gearbox.mate_problems_digest == "",
              "m4: the record's mate problems emptied once an assembly saved")
        say(f"open    {run(worker, open_titles)}")
        measure(worker, desk, "m4 built after the refusal", controls=False, again=False)
        PERSON.append(("m4", desk.record.gearbox.assembly))
    say("-- m4  the refused document closed, as W4's close_ours closes on 2024 (modified documents saved first)")
    left = run(worker, close_ours)
    check(not left, f"m4: closed, the refused one by its title: left {left}")
    book.close()


def section_m5(worker, excel):
    say("== m5  an Update lost and pressed again: the demonstration edit, every document closed without saving, "
        "Update pressed on the same workbook")
    folder, path, book, desk = fixture_desk(worker, excel, "m5", FIXTURE_12)
    build_turning(worker, desk, "m5", 4)
    measure(worker, desk, "m5 built", controls=False, again=False)
    edit(desk, book, ("Shafts", "C3", 64.5), ("Gears", "F3", 69))
    guard()
    _, result, _ = desk.update_solidworks()
    check(result is not None and result.ok and result.ratios == ["G1 meshes G2"], "m5: the first Update remade the "
          "gear mate at 17 : 69")
    left = run(worker, quit_in(folder))
    check(not left, f"m5: every document of the section closed in SolidWorks without saving: left {left}")
    desk.plan_solidworks()
    desk.say_update()
    desk.say_footer("documents closed unsaved")
    guard()
    _, result, _ = desk.update_solidworks()
    if result is not None:
        check(result.ok and LOST_SENTENCE in desk.note[0], f"m5: the sentence says the lost Update was made again: "
              f"{desk.note[0]!r}")
        check(result.ratios == ["G1 meshes G2"], f"m5: the gear mate, back at 17 : 68 in the file, is remade at "
              f"17 : 69 (ratios {result.ratios}; the app's fake leaves it, 2026-11-14)")
        measure_frames(worker, desk, "m5 pressed again")
        measure_mates(worker, desk, "m5 pressed again")
        drive_proof(worker, desk, "m5 pressed again, at the record's 17 : 69")
    book.close()


# -- W4's sections, on turning builds -------------------------------------------------------------------------


def section_a(worker, excel):
    say("== a   the 12 : 1 fixture: build, measure, Update SolidWorks (the tooth change by the remake), build again "
        "as _r2")
    folder, path, book, desk = fixture_desk(worker, excel, "a", FIXTURE_12)
    desk.say_footer("read")
    desk.say_plan()
    check(desk.plan is not None and desk.plan.revision == 0 and len(desk.plan.build) == 4 and not desk.plan.reuse,
          "the plan: revision 0, four parts to make, nothing to reuse")
    say(f"open    before: {run(worker, open_titles)}")
    guard()
    plan, result = desk.build()
    made = [os.path.join(folder, n) for n in ("Gear_m1.5_N17.SLDPRT", "Gear_m1.5_N68.SLDPRT", "Gear_m2_N17.SLDPRT",
                                              "OutputGear.SLDPRT", "Reducer_12to1_Layout.SLDPRT",
                                              "Reducer_12to1.SLDASM")]
    check(result.ok and all(os.path.isfile(p) for p in made), "4 parts, the layout part and the assembly saved")
    check(result.kind == store.GEARBOX_MOTION, f"built turning: kind {result.kind!r}")
    check(result.clashes == [] and not result.interference_error, f"no interference: {result.clashes}")
    check_fresh_build_marks(worker, made, made[-1], "a")
    check(desk.record is not None and desk.record.digest == desk.reading.digest and desk.record.gearbox.assembly,
          "the record holds the gearbox, built from this read")
    desk.say_footer("after the build")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    guard()
    measure(worker, desk, "a built")
    first = frames_on_record(desk)

    say("-- a   the demonstration edit in Excel: S2 X 63.75 -> 64.5, G2 Teeth 68 -> 69")
    guard()
    before_update = stamps(folder, solidworks_only=True)
    book.set("Shafts", "C3", 64.5)
    book.set("Gears", "F3", 69)
    book.save()
    say(f"excel   Shafts!C4 now reads {book.get('Shafts', 'C4')!r} by its formula")
    reading = desk.poll()
    for line in ("Shafts!C3 S2 X 63.75 → 64.5", "Shafts!C4 S3 X 131.75 → 132.5", "Gears!F3 G2 Teeth 68 → 69"):
        check(line in reading.changes, f"the change list says {line}")
    check(desk.a.lay_out_refusal() == "", "the gate is still \"\"")
    desk.say_update()
    u = desk.update
    check(u is not None and not u.needs_new_revision and [p.gear_ids for p in u.changed_parts] == [("G2",)]
          and u.moved_shafts == ("S2", "S3") and set(u.replaced) == {"G2", "G3", "G4"}
          and list(u.ratios) == ["G1 meshes G2"],
          "classify: an Update (the remake): G2's values, S2 and S3 moved, G2, G3 and G4 re-placed, G1 meshes G2 "
          "at 17 : 69")
    desk.say_footer("after the edit")
    guard()
    _, update_result, _ = desk.update_solidworks()
    after_update = stamps(folder, solidworks_only=True)
    changed_files = [n for n in before_update if before_update[n] != after_update.get(n)]
    check(changed_files == [], f"Update SolidWorks saved nothing: SolidWorks files changed on disk {changed_files} "
          f"(of {len(before_update)})")
    check(update_result.ratios == ["G1 meshes G2"] and sorted(update_result.placed) == all_mated(desk),
          f"the gear mate remade and every gear put: ratios {update_result.ratios}, placed {update_result.placed}")
    unsaved = sorted(os.path.basename(p) for p in desk.record.unsaved)
    check(unsaved == ["Gear_m1.5_N68.SLDPRT", "Reducer_12to1.SLDASM", "Reducer_12to1_Layout.SLDPRT"],
          f"the record marks them unsaved: {unsaved}")
    n68 = desk.record.parts[1].path
    sidecar = store.read_sidecar(n68)
    check(sidecar is not None and sidecar.record.unsaved_since > 0 and sidecar.record.spec.get("teeth") == "69",
          f"Gear_m1.5_N68.gear.json says 69 teeth, marked unsaved since {sidecar and sidecar.record.unsaved_since}")
    flags = run(worker, lambda s: save_flags(s, [os.path.join(folder, n) for n in before_update]))
    say(f"        marked modified in SolidWorks right after the update: {flags}")
    check_marks(flags, expected_marks(update_result, desk.record.gearbox.assembly), "a, after the update")
    desk.say_footer("after the update")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    measure_frames(worker, desk, "a updated")
    axes = measure_axes(worker, desk, "a updated")
    check(abs(axes["S2 Axis"][0][0] - 64.5) < 1e-6 and abs(axes["S3 Axis"][0][0] - 132.5) < 1e-6,
          "S2 Axis at x 64.5 and S3 Axis at x 132.5")
    g1 = next(c for c in desk.record.gearbox.components if c.gear == "G1")
    check(swbuild.same_frame(first["G1"][0], first["G1"][1], g1.rotation, g1.at), "G1 unchanged")
    g2 = next(c for c in desk.record.gearbox.components if c.gear == "G2")
    _, off, _ = frame_error((g2.rotation, g2.at), (wb_layout.IDENTITY, g2.at), 360 / 69)
    check(off < 1e-6, f"G2's turn is now 0 modulo its pitch (69 teeth, odd): off {off:.1e}°")
    values = run(worker, lambda s: live_globals(s, g2.part))
    check(abs(values.get("No. of Teeth", 0) - 69) < 1e-9, f"G2's part {os.path.basename(g2.part)} holds "
          f"\"No. of Teeth\" = {values.get('No. of Teeth')}")
    measure_clear(worker, desk, "a updated")
    measure_mates(worker, desk, "a updated")
    say("        W4's control (G2 put back at its old frame, where the 69-tooth gear clashed with G1) does not hold for "
        "a gear mated to S2 Axis: the axis mate pulls the put back on the next rebuild. The drive at 17 : 69 stands in "
        "for it, showing the assembly turning the 69-tooth G2 (ruled on 2026-11-14)")
    drive_proof(worker, desk, "a updated, at 17 : 69")
    negative_controls(worker, desk, "a updated")

    say("-- a   a structural edit in Excel: G1's bore 8 -> blank")
    guard()
    book.set("Gears", "J2", None)
    book.save()
    desk.poll()
    desk.say_update()
    check(desk.update is not None and desk.update.needs_new_revision, "classify: a new revision is needed")
    check(sorted(os.path.basename(p) for p in desk.record.unsaved) == unsaved,
          "the documents Update changed are still unsaved (nothing saved them)")
    desk.say_plan()
    p = desk.plan
    for m in (p.made_new if p is not None else ()):
        say(f"        made new: {m.why}: {m.sentence}")
    check(p is not None and not p.refusal and p.revision == 2
          and [j.stem for j in p.build] == ["Gear_m1.5_N17_r2", "Gear_m1.5_N69"]
          and sorted(r.stem for r in p.reuse) == ["Gear_m2_N17", "OutputGear"],
          "the plan, with Update's changes unsaved: Reducer_12to1_r2, new parts for G1 (Gear_m1.5_N17_r2) and G2 "
          "(Gear_m1.5_N69), G3 and G4 reused")
    check(p is not None and [(m.gear_ids, os.path.basename(m.old), os.path.basename(m.new))
                             for m in p.unsaved_made_new] == [(("G2",), "Gear_m1.5_N68.SLDPRT", "Gear_m1.5_N69.SLDPRT")],
          "review B2: G2's part is made new because Gear_m1.5_N68 is not saved, and nothing waits for a save")
    say(f"question {ui_text.build_again_question(desk.update, desk.plan, record=desk.record)}")
    f = desk.say_footer("structural, unsaved")
    check(f.build_enabled and f.update_enabled, "neither Build again… nor Update SolidWorks is held by the unsaved "
          "documents")
    guard()
    earlier, earlier_sidecars = stamps(folder), sidecar_texts(folder)
    say(f"stamps  {len(earlier)} earlier files: " + ", ".join(sorted(earlier)))
    _, result = desk.build()
    later = check_earlier_unchanged(folder, earlier, "a build again", earlier_sidecars)
    new = sorted(n for n in later if n not in earlier)
    check(new == ["Gear_m1.5_N17_r2.SLDPRT", "Gear_m1.5_N17_r2.gear.json", "Gear_m1.5_N69.SLDPRT",
                  "Gear_m1.5_N69.gear.json", "Reducer_12to1_r2.SLDASM", "Reducer_12to1_r2_Layout.SLDPRT"],
          f"new files only where needed: {new}")
    check(result is not None and result.kind == store.GEARBOX_MOTION, f"_r2 built turning: "
          f"{result and result.kind!r}")
    rec = desk.record
    check(rec.gearbox.revision == 2 and [e.revision for e in rec.earlier] == [0]
          and [os.path.basename(p) for e in rec.earlier for p in e.parts] == ["Gear_m1.5_N17.SLDPRT",
                                                                              "Gear_m1.5_N68.SLDPRT"],
          "the record: revision 2 current; revision 0 earlier, with the G1 and G2 parts it no longer uses")
    flags = run(worker, lambda s: save_flags(s, [os.path.join(folder, n) for n in earlier if n.endswith(
        (".SLDPRT", ".SLDASM"))]))
    say(f"        marked modified in SolidWorks now (not saved): {flags}")
    check(flags.get("Gear_m1.5_N17.SLDPRT") is False, "the superseded G1 part, which Update never changed, is not "
          "marked modified")
    desk.say_footer("after build again")
    measure(worker, desk, "a _r2")
    book.close()
    return desk


def section_a2(worker, excel):
    say("== a2  a build stopped after the parts and layout, carried on; then Build pressed with nothing changed")
    folder = fresh_folder("a2")
    path = os.path.join(folder, "Reducer_12to1.xlsx")
    shutil.copy2(FIXTURE_12, path)
    book = Workbook(excel, path, "a2")
    book.set("Box", "B4", folder + "\\")
    missing = os.path.join(folder, "No such template.asmdot")
    book.set("Box", "B6", missing)
    book.save()
    desk = Desk(path, worker)
    desk.read()
    desk.say_plan(full=False)
    guard()
    plan, result = desk.build()
    check(not result.ok and result.layout is not None and result.layout.saved and len(result.parts.built) == 4
          and result.assembly is not None and not result.assembly.saved,
          "the build stopped at the assembly: 4 parts and the layout saved, the assembly not made")
    rec = desk.record
    check(rec is not None and rec.gearbox.layout and not rec.gearbox.assembly and rec.digest == "",
          "the record holds the parts and the layout, no assembly, and no digest (it is not built from this read)")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    desk.say_footer("after the stopped build")
    say(f"open    {run(worker, open_titles)}")
    book.set("Box", "B6", None)
    book.save()
    desk.poll()
    desk.say_plan(full=False)
    p = desk.plan
    check(p is not None and p.revision == 0 and not p.build and len(p.reuse) == 4
          and isinstance(p.layout, wb_gearbox.LayoutReuse), "Build carries on: revision 0, 4 parts and the layout "
          "reused, only the assembly to make")
    desk.say_footer("cell cleared")
    guard()
    plan, result = desk.build()
    check(result.ok and len(result.checked) == 5 and result.clashes == [] and result.kind == store.GEARBOX_MOTION,
          f"carried on: checked {[os.path.basename(c) for c in result.checked]}, assembly saved turning, no "
          "interference")
    check(desk.record.digest == desk.reading.digest, "the record now claims this read")
    measure(worker, desk, "a2 carried on", controls=False, again=False)
    PERSON.append(("a2", desk.record.gearbox.assembly))
    desk.say_footer("after carrying on")
    say("-- a2  Build pressed again, nothing changed")
    desk.say_update()
    desk.say_plan(full=False)
    p = desk.plan
    say(f"question {ui_text.build_again_question(desk.update, p, record=desk.record)}")
    check(p is not None and p.revision == 2 and not p.build and len(p.reuse) == 4,
          "the plan: Reducer_12to1_r2 beside it, reusing all 4 parts, a new layout and assembly")
    earlier = stamps(folder)
    guard()
    desk.build()
    later = stamps(folder)
    touched = [n for n in earlier if later.get(n) != earlier[n]]
    check(touched == [], f"every earlier file's sha256 and mtime unchanged: changed {touched}")
    measure(worker, desk, "a2 _r2", controls=False, again=False)
    left = run(worker, close_ours)
    check(not left, f"closed: left {left}")
    book.close()


def section_a3(worker, excel):
    say("== a3  the journal: a build interrupted after two parts saved; then an Update lost when its documents "
        "closed unsaved, typed back")
    folder = fresh_folder("a3")
    path = os.path.join(folder, "Reducer_12to1.xlsx")
    shutil.copy2(FIXTURE_12, path)
    book = Workbook(excel, path, "a3")
    book.set("Box", "B4", folder + "\\")
    book.save()
    desk = Desk(path, worker)
    desk.read()
    plan = desk.plan
    check(plan is not None and plan.revision == 0 and len(plan.build) == 4 and not plan.reuse,
          "the plan: revision 0, four parts to make")

    say("-- a3  the journal written; the job then saves two parts and is never collected")
    check(desk.write_journal(plan), "the journal is on record before the job, as the window writes it")
    say(f"journal {[(os.path.basename(e.path), e.kind) for e in store.read_link_record(path).pending]}")
    two = plan.build[:2]
    guard()
    interrupted = run(worker, lambda s: swbuild.build_many(s, [j.plan for j in two], os.path.exists))
    for line in interrupted.log_lines():
        say("        " + line)
    check(interrupted.ok and all(os.path.isfile(j.path) and store.read_sidecar(j.path) is None for j in two),
          f"SolidWorks saved {[os.path.basename(j.path) for j in two]}, and no .gear.json is beside either: the "
          "finish never ran")
    desk.plan_solidworks()
    desk.say_plan(full=False)
    p = desk.plan
    check(p is not None and p.revision == 0 and p.made_new == ()
          and [r.stem for r in p.reuse] == [j.stem for j in two] and all(r.journaled for r in p.reuse)
          and [j.stem for j in p.build] == [j.stem for j in plan.build[2:]],
          "the next plan reuses the two the journal names, to be checked live, and makes the other two: revision 0, "
          "no suffix, nothing called a file with no record")
    desk.say_footer("after the interrupted build")
    guard()
    _, result = desk.build()
    check(result.ok and result.checked[:2] == [r.path for r in p.reuse] and result.kind == store.GEARBOX_MOTION,
          f"built turning, the two checked live first: {[os.path.basename(c) for c in result.checked]}")
    for r in p.reuse:
        sidecar = store.read_sidecar(r.path)
        check(sidecar is not None and store.same_path(sidecar.record.workbook, path)
              and sidecar.record.trig == result.held.get(r.path) and sidecar.record.variables,
              f"{r.stem}.gear.json written at the finish, for this workbook, in {result.held.get(r.path)!r}")
    check(store.read_link_record(path).pending == [] and len(desk.record.parts) == 4,
          "the journal is taken out, and the four parts are on record")
    measure(worker, desk, "a3 built", controls=False, again=False)

    say("-- a3  S2 X 64.5 and G2 Teeth 69, and Update, left unsaved; then the documents closed without saving")
    n68 = next(e.path for e in desk.record.parts if e.gears == ["G2"])
    book.set("Shafts", "C3", 64.5)
    book.set("Gears", "F3", 69)
    book.save()
    desk.poll()
    desk.say_update()
    guard()
    desk.update_solidworks()
    unsaved = sorted(os.path.basename(x) for x in desk.record.unsaved)
    check("Gear_m1.5_N68.SLDPRT" in unsaved, f"the record marks what Update changed unsaved: {unsaved}")
    check(store.read_sidecar(n68).record.unsaved_since > 0, "Gear_m1.5_N68.gear.json is marked unsaved")
    left = run(worker, quit_in(folder))
    check(not left, f"this section's documents closed in SolidWorks without saving: left {left}")
    desk.plan_solidworks()
    check(sorted(os.path.basename(x) for x in desk.record.unsaved) == unsaved,
          "the marks stay: the files were not saved, and nothing on the Tk thread can see SolidWorks")
    desk.say_footer("documents closed unsaved")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    book.set("Shafts", "C3", 63.75)
    book.set("Gears", "F3", 68)
    book.save()
    desk.poll()
    desk.say_update()
    guard()
    _, result, _ = desk.update_solidworks()
    current = [e.path for e in desk.record.current_parts()] + [desk.record.gearbox.layout,
                                                               desk.record.gearbox.assembly]
    # Ruled on 2026-11-14 (with package A's fix: the check phase reads each recorded gear mate's live ratio): the
    # reopened gear mate already reads 17 : 68, what the workbook now wants, so it is not remade; the parts, the layout
    # and the frames all hold what the file holds, so nothing is changed. The sentence for "the earlier Update was
    # lost and nothing needed making again" is package C's to write after A's fix: logged, not pinned.
    changed = sorted(os.path.basename(x) for x in result.changed)
    check(result.ratios == [] and changed == [],
          f"Update found the gear mate already at 17 : 68 and every document holding the workbook's values: no remake, "
          f"nothing changed: ratios {result.ratios}, changed {changed}")
    check(sorted(os.path.basename(x) for x in result.opened) == sorted(os.path.basename(x) for x in current),
          f"it loaded every document from its file: {[os.path.basename(x) for x in result.opened]}")
    say(f"fact    the sentence after the lost Update typed back (not pinned until package C's wording): "
        f"{desk.note[0]!r}")
    say(f"fact    the marks: unsaved {[os.path.basename(p) for p in desk.record.unsaved]}, mismatched "
        f"{[os.path.basename(p) for p in desk.record.mismatched]}")
    sidecar = store.read_sidecar(n68)
    check(sidecar.record.unsaved_since == 0 and sidecar.record.spec.get("teeth") == "68",
          f"Gear_m1.5_N68.gear.json says 68 teeth, unmarked ({sidecar.record.unsaved_since})")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    drive_proof(worker, desk, "a3 typed back, the gear mate's live ratio 17 : 68")
    book.set("Gears", "J2", None)
    book.save()
    desk.poll()
    desk.say_plan(full=False)
    q = desk.plan
    check(q is not None and n68 in [r.path for r in q.reuse] and not any(store.same_path(m.old, n68)
                                                                       for m in q.made_new),
          "a build-again plan now reuses Gear_m1.5_N68")
    desk.say_footer("structural")
    book.close()


def section_b(worker, excel):
    say("== b   a pure move: S2 placed by formulas from an angle cell, moved along its arc")
    folder = fresh_folder("b")
    path = os.path.join(folder, "Arc_Move.xlsx")
    xlsx.write_new(path, wb_model.to_sheets(spec_arc(folder + "\\")))
    say(f"write   {os.path.basename(path)} by the app's own write_new")
    book = Workbook(excel, path, "b")
    book.set("Shafts", "L1", "Angle (°)")
    book.set("Shafts", "L3", 30)
    book.set("Shafts", "C3", f"={ARC_R:g}*COS(RADIANS(L3))")
    book.set("Shafts", "D3", f"={ARC_R:g}*SIN(RADIANS(L3))")
    book.set("Shafts", "C4", "=C3+40")
    book.set("Shafts", "D4", "=D3")
    keep_fixture(book, "Arc_Move.xlsx", "C:\\Parts\\Arc_Move\\")
    book.set("Box", "B4", folder + "\\")
    book.save()
    desk = Desk(path, worker)
    desk.read()
    check(desk.a.lay_out_refusal() == "", "the gate is \"\"")
    shafts = {s.shaft: s for s in desk.plan_shafts()}
    check(all(shafts[s].x_side == wb_layout.PLUS and shafts[s].y_side == wb_layout.PLUS for s in ("S2", "S3")),
          "S2 and S3 are off both base planes: four layout planes, four globals")
    build_turning(worker, desk, "b", 4)
    measure(worker, desk, "b built")
    guard()
    before = stamps(folder, solidworks_only=True)
    edit(desk, book, ("Shafts", "L3", 40))
    u = desk.update
    check(u is not None and not u.needs_new_revision and not u.changed_parts and u.moved_shafts == ("S2", "S3"),
          "classify: no part values, S2 and S3 moved (layout globals only), and re-places")
    desk.say_footer("after the angle edit")
    guard()
    _, result, _ = desk.update_solidworks()
    check(result.ok and not any(r.changed for r in result.parts) and result.layout is not None
          and sorted(result.layout.changed) == ["S2 X", "S2 Y", "S3 X", "S3 Y"],
          f"Update: no part touched; the layout's S2 X, S2 Y, S3 X, S3 Y set: {result.layout and result.layout.changed}; "
          f"re-placed {result.placed}")
    flags = run(worker, lambda s: save_flags(s, [os.path.join(folder, n) for n in before]))
    say(f"        marked modified in SolidWorks right after the update: {flags}")
    check_marks(flags, ["Arc_Move.SLDASM", "Arc_Move_Layout.SLDPRT"], "b, the move: only the layout and the assembly "
                "(Update left every part as it was)")
    check(result.clashes == [] and not result.interference_error, f"no interference after the move: {result.clashes}")
    after = stamps(folder, solidworks_only=True)
    check([n for n in before if before[n] != after.get(n)] == [], f"Update saved nothing ({len(before)} SolidWorks "
          "files, sha256 and mtime)")
    measure(worker, desk, "b moved")

    say("-- b   a part-only Update, no gear re-placed: G2's bore 8 -> 10")
    guard()
    before = stamps(folder, solidworks_only=True)
    edit(desk, book, ("Gears", "J3", 10))
    u = desk.update
    check(u is not None and not u.needs_new_revision and [p.gear_ids for p in u.changed_parts] == [("G2",)]
          and not u.moved_shafts and not u.replaced,
          "classify: G2's values alone, no shaft moved, no gear re-placed")
    guard()
    _, result, _ = desk.update_solidworks()
    g2_part = next(c.part for c in desk.record.gearbox.components if c.gear == "G2")
    check(result.ok and result.placed == [] and [os.path.basename(p) for p in result.changed]
          == [os.path.basename(g2_part)],
          f"Update: G2's part changed and nothing else: changed {[os.path.basename(p) for p in result.changed]}, "
          f"re-placed {result.placed}")
    unsaved = sorted(os.path.basename(p) for p in desk.record.unsaved)
    check(unsaved == [os.path.basename(g2_part)], f"the record marks G2's part unsaved and not the assembly, which "
          f"holds nothing new: {unsaved}")
    flags = run(worker, lambda s: save_flags(s, [os.path.join(folder, n) for n in before]))
    say(f"        marked modified in SolidWorks right after the update: {flags}")
    check_marks(flags, expected_marks(result, desk.record.gearbox.assembly),
                f"b, part only: G2's part, and the assembly only if Update rebuilt it (rebuilt {result.rebuilt})")
    after = stamps(folder, solidworks_only=True)
    check([n for n in before if before[n] != after.get(n)] == [], "Update saved nothing")
    measure(worker, desk, "b bore", controls=False)
    book.close()


def section_c(worker, excel):
    say("== c   the risky placements: helical across Z+/Z-, herringbones of unequal faces, a helical ring on Z-")
    folder = fresh_folder("c")
    path = os.path.join(folder, "Risky_Placements.xlsx")
    xlsx.write_new(path, wb_model.to_sheets(spec_risky(folder + "\\")))
    say(f"write   {os.path.basename(path)} by the app's own write_new")
    book = Workbook(excel, path, "c")
    keep_fixture(book, "Risky_Placements.xlsx", "C:\\Parts\\Risky_Placements\\")
    book.set("Box", "B4", folder + "\\")
    book.save()
    desk = Desk(path, worker)
    desk.read()
    check(desk.a.lay_out_refusal() == "", "the gate is \"\"")
    build_turning(worker, desk, "c", 6)
    measure(worker, desk, "c built")
    book.close()


SECTIONS = {"m1": section_m1, "m2": section_m2, "m3": section_m3, "m4": section_m4, "m5": section_m5,
            "a": section_a, "a2": section_a2, "a3": section_a3, "b": section_b, "c": section_c}


def connect_pid():
    found = [c for c in swcom.find_candidates() if c.pid == PID]
    if not found:
        raise swcom.NotRunning(f"No SolidWorks session with PID {PID} is reachable.")
    return swcom.Session(found[0].app, found[0].revision, found[0].pid)


def person_step():
    """W5-PLAN §4.4: the step only a person can do, with the assembly to open."""
    where = next((p for what, p in PERSON if what == "a2"), "") or next((p for _, p in PERSON), "")
    say("person  W5-PLAN §4.4, the step only a person can do (for 2026, then 2024):")
    say(f"person  In SolidWorks, open {where or 'the Reducer_12to1.SLDASM a section built (a2 or m4)'}. Click gear "
        "G1 — the small gear on S1, at the origin — and drag it round its axis by about a quarter turn. Watch G4, the "
        "large gear on S3: it turns the same way as G1, much more slowly — a quarter turn of G1 turns G4 about 7.5°. "
        "G2 and G3, on S2, turn together the other way. No gear should leave its axis, slide along it, or pass "
        "through another. Then, in the Workbook window, press Update SolidWorks with nothing changed: the footer "
        "should say the gears stand where they were turned. Tell us what you saw, on each version.")


def main():
    os.makedirs(OUT, exist_ok=True)
    say(f"run     {time.strftime('%Y-%m-%d %H:%M:%S')}; app {WRITTEN_BY} from {SRC}; sections {ONLY}")
    unknown = [n for n in ONLY if n not in SECTIONS]
    if unknown:
        say(f"STOP    no such section {unknown}; there are {list(SECTIONS)}")
        return 2
    worker = swcom.Worker(connect_pid)
    label, pid, revision = run(worker, lambda s: (s.label, s.pid, s.revision), 120)
    TAG["major"] = revision[0]
    say(f"attach  {label}, PID {pid}; {memory()}")
    if pid != PID:
        say(f"STOP    attached to PID {pid}, not {PID}")
        worker.shutdown()
        return 2
    before = run(worker, open_titles, 120)
    say(f"open    before: {before}")
    say(f"findings LAYOUT_PLUS_FLIP {findings.LAYOUT_PLUS_FLIP}, LAYOUT_NEGATED_LINK {findings.LAYOUT_NEGATED_LINK!r}, "
        f"LAYOUT_AXIS_Z_SIGN {findings.LAYOUT_AXIS_Z_SIGN}, REPLACE_FIXED_ROUTE {findings.REPLACE_FIXED_ROUTE!r}")
    say(f"findings W5: GEAR_MATE_RATIO_ROUTE {findings.GEAR_MATE_RATIO_ROUTE!r}, MATED_ASSEMBLY_REBUILD_ROUTE "
        f"{findings.MATED_ASSEMBLY_REBUILD_ROUTE!r}, MATED_BUILD_REBUILD_ROUTE {findings.MATED_BUILD_REBUILD_ROUTE!r}, "
        f"GEAR_MATE_FLIP {findings.GEAR_MATE_FLIP}, DEMONSTRATION_DRIVE_SENSE {findings.DEMONSTRATION_DRIVE_SENSE}, "
        f"MESH_PHASE_ROUTE {findings.MESH_PHASE_ROUTE!r}, LOCK_RETAKES_AN_OFFSET {findings.LOCK_RETAKES_AN_OFFSET}; "
        f"P0c {p0c_findings()}; AXIAL_RESTORES {AXIAL_RESTORES}; m4 offset {M4_OFFSET:g} mm")
    watch = DialogWatch()
    watch.start()
    excel = xlhelp.Excel(visible=True)
    say(f"excel   started our own Excel, PID {excel.pid}, {excel.version}")
    try:
        for name in ONLY:
            if TAG["major"] == 32 and free_gb() < 3.0:
                say(f"SKIP    section {name}: {memory()}, under the 3 GB a 2024 section starts with")
                continue
            started = time.monotonic()
            halted = False
            try:
                SECTIONS[name](worker, excel)
            except Stopped as exc:
                check(False, f"section {name} stopped: {exc}")
                halted = True
            except Halt as exc:
                check(False, f"section {name} HALTED, the run stops here (W5-PLAN §4.2): {exc}")
                halted = True
            except Exception as exc:  # noqa: BLE001 - logged, and the documents still closed below
                check(False, f"section {name} raised {type(exc).__name__}: {exc}")
                for line in traceback.format_exc().splitlines():
                    say("        " + line)
            finally:
                books = close_books()
                if books:
                    say(f"excel   section {name} left {books} open in Excel: closed without saving")
                left = run(worker, close_ours, 600)
                say(f"close   section {name}: left of ours {left}; {time.monotonic() - started:.0f} s; {memory()}")
            if halted:
                break
    finally:
        try:
            excel.quit()
            say("excel   quit our own Excel")
        except Exception as exc:  # noqa: BLE001
            say(f"excel   quit trouble: {exc}")
        left = run(worker, close_ours, 600)
        after = run(worker, open_titles, 120)
        say(f"close   left of ours {left}; stray {[t for t in after if t not in before]}; "
            f"lost {[t for t in before if t not in after]}; {memory()}")
        watch.stop.set()
        say(f"dialogs progress boxes seen {PROGRESS}; other dialogs are logged above as DIALOG")
        worker.shutdown()
    for line in NOTES:
        say(f"noted   {line}")
    person_step()
    say(f"done    {len(FAILS)} failed: {FAILS}; {len(NOTES)} noted for a ruling")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        with open(LOG_PATH, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(LOG) + "\n")
    raise SystemExit(code)
