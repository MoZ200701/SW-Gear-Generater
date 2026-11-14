r"""W4's Windows demonstration: three gearbox workbooks through the app's own code, on real SolidWorks and Excel.

python.exe probe/workbook_assembly_check.py <repo src> <output folder under C:\> --pid PID [--log FILE]
                                            [--only a|a2|a3|b|c ...] [--fixtures FOLDER]

PLAN-WORKBOOK §6, W4 "Demonstrable", and the W4 decisions' item 10. Every step goes the way the Workbook window
goes (``workbook_gui.WorkbookWindow``: ``_plan_solidworks``, ``_start_build``, ``press_update``,
``_build_again``, ``_finish_build``, ``_finish_update``), with the window's Tk thread played by this script's
main thread and its worker by ``swcom.Worker``: the workbook read by ``link.Link.read`` / ``Link.poll``,
``assess``, ``plan_gearbox`` or ``classify``, ``swbuild.build_gearbox(session, **plan.build_kwargs())`` or
``swbuild.update_gearbox(session, **update.update_kwargs())``, then ``finish_build`` / ``finish_update`` with
the sidecars and the record written through ``store.save`` and ``store.save_link_record``. Every sentence the
footer would show is logged (``ui_text.workbook_footer``, ``gearbox_status``, ``gearbox_update_status``,
``build_again_question``). Every edit to a workbook is made by a real Excel saving the file: an Excel this
script starts for itself (``probe/excel/xlhelp.Excel``), never the user's, quit at the end.

Nothing is taken on the app's word: each assembly is measured.

- Each gear component's live frame (``Transform2``) against ``layout.frames`` of the current read, to 1e-6 mm,
  the turn compared modulo the gear's pitch; the layout component at identity.
- Each layout axis by ``GetRefAxisParams``: where it crosses z = 0 against the shaft's (X, Y), and that it reads
  +Z, as each part's Gear Axis does.
- Interference: none as built, and for every listed mesh a negative control: one gear of the mesh turned half
  its pitch about its own axis must interfere, and only with its partner; put back, none again.
- The assembly saved and closed (this run's documents only), reopened by path, every component found again by
  the name on record, and the frames read again.

The sections, each in its own folder under the output folder:

- ``a``: the Windows-saved 12 : 1 fixture. Build; measure. Then Excel sets Shafts!C3 S2 X 63.75 -> 64.5 and
  Gears!F3 G2 Teeth 68 -> 69 (S3 X follows by its formula to 132.5); ``Link.poll``; ``classify`` (no structural
  change); Update SolidWorks; measure, including that G2's part holds 69 teeth and that the ASSEMBLY shows the
  69-tooth gear (back at its old frame it now clashes with G1). Nothing saved by Update, the record marks the
  documents unsaved, and SolidWorks marks modified only the documents Update changed and the assembly it
  rebuilt (W4 review S2: the parts it did not change are left unmodified; the assembly is rebuilt top-only,
  ``findings.ASSEMBLY_REBUILD_ROUTE``). Right after the build, no part and no layout part reads modified and the
  assembly does (a read after its save marks it); after every reopen, every document reads unmodified straight
  after the open, and the flags are logged again after the frame reads and after ``interferences()``, as fact
  lines, to show which read marks the assembly. Then a structural edit (G1's bore cleared) with those documents still
  unsaved: the build-again plan does not wait for a save (review B2) — G2's part, changed by Update and not
  saved, is made new as Gear_m1.5_N69 instead of reused, G1's as Gear_m1.5_N17_r2 — and ``_r2`` is built
  without saving anything, reusing G3's and G4's parts; every earlier file's sha256 and mtime are compared with
  what they were (Gear_m1.5_N68.SLDPRT still holds 68 teeth on disk).
- ``a2``: the same fixture, built with an assembly template that is not there, so the build stops after the
  parts and the layout; the cell cleared in Excel, Build carries on reusing them; then Build pressed again with
  nothing changed.
- ``a3`` (the second W4 review, N4 and N2): the journal and the marks. The 12 : 1 fixture planned, its journal
  written as the window writes it before a job, then only two of its parts built and the job's answer never
  collected — as when the app is killed, or closed with "Quit anyway?", after SolidWorks saved them. The next
  plan reuses those two from the journal (revision 0, no suffix, nothing called a file with no record), the
  build checks them live first, and its finish writes their ``.gear.json`` and takes the journal out. Then
  the demonstration edit (S2 X 64.5, G2 Teeth 69) and Update, left unsaved; this section's documents closed in
  SolidWorks without saving (``QuitDoc``, assumed to discard without asking: DialogWatch logs any dialog it
  shows); the edit typed back (63.75, 68), which is what the files hold; Update loads every document from its
  file, changes nothing, and the record's unsaved marks and Gear_m1.5_N68.gear.json's mark are gone, so a
  build-again plan reuses Gear_m1.5_N68.
- ``b``: a workbook written by the app's own ``write_new``, opened and saved in Excel with S2 placed by formulas
  from an angle cell, off both axes, and S3 following S2 by formula. Built; the angle changed in Excel; Update
  moves the shafts and re-places the gears without touching a part. Then a part-only Update (G2's bore 8 ->
  10, no gear re-placed): SolidWorks marks G2's part, and the assembly only because Update rebuilt it; the
  record marks the part alone (``GearboxUpdate.changed`` is what Update changed the content of).
- ``c``: the risky placements: a helical pair across Z+ and Z-, herringbones of unequal face widths on Z- and
  Z+, and a helical pinion in a helical ring whose shaft is Z-. Built, measured, every mesh's negative control.

``--fixtures FOLDER`` copies b's and c's workbooks, as Excel saved them with a neutral Output folder, there.

Refuses to run unless the session it attaches to is the PID given. Only documents this run made are saved and
closed (its modified parts saved before an assembly is closed: SolidWorks 2024 asks about them in a modal dialog
otherwise); nothing open before the run is touched, and other documents' titles are logged as
``<user document N>``. On SolidWorks 2024 a section starts only with 3 GB of RAM free, and the run stops between
steps if it falls under 2 GB.
"""

import ctypes
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
ONLY = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--only"] or ["a", "a2", "a3", "b", "c"]
LOG_PATH = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(OUT, "workbook-assembly.log")
FIXTURES = sys.argv[sys.argv.index("--fixtures") + 1] if "--fixtures" in sys.argv else ""
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURE_12 = os.path.join(REPO, "tests", "fixtures", "excel-windows", "Reducer_12to1.xlsx")

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
from gear_generator.gears import base  # noqa: E402
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
from gear_generator.workbook_gui import _update_gate  # noqa: E402  (the window's own gate for classify)

LOG = []
FAILS = []
LOCK = threading.Lock()
STOP = threading.Event()
WRITTEN_BY = f"gear-generator {__version__}"
TAG = {"version": "", "major": 0}


class Stopped(Exception):
    """Free memory fell under the floor on SolidWorks 2024: the run stops between steps."""


def say(line=""):
    with LOCK:
        print(line, flush=True)
        LOG.append(line)


def check(ok, what):
    say(("ok      " if ok else "FAIL    ") + what)
    if not ok:
        FAILS.append(what)
    return ok


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
    return bool(path) and os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(os.path.abspath(OUT)))


USERS = {}


def open_titles(session):
    """Every open document's title; one not made by this run as ``<user document N>`` (the repo is public)."""
    out = []
    for doc in documents(session._app):  # noqa: SLF001
        title, path = str(call(doc, "GetTitle")), str(call(doc, "GetPathName") or "")
        if ours(path):
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
    """Save this run's modified documents, then close them, assemblies first. Returns what is left open of ours."""
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
    for kind in (2, 1):
        for doc in documents(app):
            if ours(str(call(doc, "GetPathName") or "")) and int(call(doc, "GetType")) == kind:
                call(app, "CloseDoc", str(call(doc, "GetTitle")))
    return [str(call(d, "GetTitle")) for d in documents(app) if ours(str(call(d, "GetPathName") or ""))]


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
        for wanted in paths:
            if store.same_path(path, wanted):
                out[os.path.basename(wanted)] = bool(call(doc, "GetSaveFlag"))
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


def check_fresh_build_marks(worker, paths, assembly, label):
    """Right after a build and its saves: no part and no layout part reads GetSaveFlag True (the assembly is rebuilt
    top-only, findings.ASSEMBLY_REBUILD_ROUTE), and the assembly does: a read after its save marks it — its frame
    reads and/or its interference check, not yet isolated (``reopen`` logs which) — with nothing to lose by not
    saving it."""
    flags = run(worker, lambda s: save_flags(s, paths))
    say(f"        marked modified in SolidWorks right after the build: {flags}")
    others = [os.path.basename(p) for p in paths if not store.same_path(p, assembly)]
    check(all(flags.get(n) is False for n in others) and flags.get(os.path.basename(assembly)) is True,
          f"{label}: after the build and its saves no part and no layout part is marked modified, and the assembly "
          f"is (a read after its save): marked {marked(flags)}")


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


def frame_error(live, wanted, pitch):
    """(largest origin difference in mm, the turn between them in degrees modulo pitch, off-axis residue)."""
    (ra, at_a), (rb, at_b) = live, wanted
    origin = max(abs(float(a) - float(b)) for a, b in zip(at_a, at_b))
    a = [[float(ra[i * 3 + j]) for j in range(3)] for i in range(3)]
    b = [[float(rb[i * 3 + j]) for j in range(3)] for i in range(3)]
    m = [[sum(a[k][i] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    turn = math.degrees(math.atan2(m[1][0], m[0][0]))
    off = turn % pitch if pitch else turn
    off = min(off, pitch - off) if pitch else abs(off)
    residue = max(abs(m[2][2] - 1.0), abs(m[0][2]), abs(m[1][2]), abs(m[2][0]), abs(m[2][1]))
    return origin, off, residue


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
        """``WorkbookWindow._plan_solidworks``."""
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
                                       folder_exists=bool(folder) and os.path.isdir(folder), note=self.note)

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
        say(f"plan    revision {p.revision} {p.name}: refusal {p.refusal!r}; reason {p.revision_reason!r}")
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
            f"{list(u.missing)}; unsaved {[os.path.basename(p) for p in u.unsaved]}; refusal {u.refusal!r}")
        if u.layout is not None:
            say(f"        layout globals wanted {[f'{v.name} = {v.expression}' for v in u.layout.variables]}")
        say(f"summary {ui_text.update_summary(u)}")

    # the jobs
    def write_journal(self, plan):
        """``WorkbookWindow._write_journal``: what the build is about to make, in the record, before the job."""
        try:
            record = store.read_link_record(self.path)
        except Exception:  # noqa: BLE001 - as the window: left for the finish
            return False
        if record is None:
            record = store.LinkRecord(workbook=self.path)
        record.pending, record.pending_for = wb_gearbox.journal(plan), self.path
        try:
            store.save_link_record(record, store.link_record_path(self.path))
        except Exception:  # noqa: BLE001
            return False
        return True

    def build(self):
        """``_start_build`` (its journal first) then, once the worker answers, ``_finish_build``."""
        plan = self.plan
        steps = []
        kwargs = plan.build_kwargs()
        journaled = self.write_journal(plan)
        say(f"journal {'written' if journaled else 'NOT written'}: {len(wb_gearbox.journal(plan))} paths")
        started = time.monotonic()
        say(f"build   {plan.name}: {memory()}")
        result = run(self.worker, lambda s: swbuild.build_gearbox(s, **kwargs, progress=steps.append))
        seconds = time.monotonic() - started
        for line in result.log_lines():
            say("        " + line)
        say(f"        in {seconds:.1f} s; {memory()}")
        say(f"        steps {[(x.stage, x.name, x.index, x.count) for x in steps]}")
        say(f"        progress words {[ui_text.progress_text(x) for x in steps[:1] + steps[-1:]]}")
        self.note = self.finish_build(plan, result)
        say(f"status  [{'green' if self.note[1] else 'red'}] {self.note[0]}")
        self.plan_solidworks()
        return plan, result

    def finish_build(self, plan, result):
        text, ok = ui_text.gearbox_status(plan, result)
        record, may_write, notes = self._open_record()
        finished = wb_gearbox.finish_build(plan, result, record, workbook=self.path, digest=self.reading.digest,
                                           written_by=WRITTEN_BY)
        faults = self._write(finished, may_write)
        return " ".join([text] + notes + faults), ok and not faults

    def update_solidworks(self):
        """``press_update`` (no new revision needed) then ``_finish_update``."""
        update = self.update
        steps = []
        kwargs = update.update_kwargs()
        started = time.monotonic()
        say(f"update  {memory()}")
        result = run(self.worker, lambda s: swbuild.update_gearbox(s, **kwargs, progress=steps.append))
        seconds = time.monotonic() - started
        for line in result.log_lines():
            say("        " + line)
        say(f"        in {seconds:.1f} s; {memory()}")
        say(f"        steps {[(x.stage, x.name, x.index, x.count) for x in steps]}")
        say(f"        loaded from disk {[os.path.basename(p) for p in result.opened]}")
        record, may_write, notes = self._open_record()
        base_record = record if record is not None else self.record
        finished = wb_update.finish_update(update, result, base_record, digest=self.reading.digest,
                                           workbook=self.path)
        gearbox = self.record.gearbox if self.record is not None else None
        text, ok = ui_text.gearbox_update_status(update, result, finished.dragged,
                                                 meshes=gearbox.meshes if gearbox is not None else None)
        faults = self._write(finished, may_write)
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


# -- measuring ----------------------------------------------------------------------------------------------


def live_frames(session, asm, names):
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


def live_axes(session, path, names):
    session.begin_build()
    try:
        session.open_document(path)
        out = {}
        for name in names:
            feature = session._by_name(name)  # noqa: SLF001
            out[name] = axis_crossing(call(call(feature, "GetSpecificFeature2"), "GetRefAxisParams"))
        return out, session.equation_values()
    finally:
        session.end_build()


def live_globals(session, path):
    session.begin_build()
    try:
        session.open_document(path)
        return session.equation_values()
    finally:
        session.end_build()


def live_interferences(session, asm):
    session.begin_build()
    try:
        session.open_document(asm)
        return session.interferences()
    finally:
        session.end_build()


def placed_elsewhere(session, asm, name, rotation, at):
    """Put one component at another frame, read the interferences, put it back, read them again."""
    session.begin_build()
    try:
        session.open_document(asm)
        session.find_component("moved", name)
        before = session.component_frame("moved")
        session.place_component("moved", rotation, at, kind=swcom.ASSEMBLY_STATIC)
        moved = session.interferences()
        session.place_component("moved", before[0], before[1], kind=swcom.ASSEMBLY_STATIC)
        back = session.interferences()
        return moved, back
    finally:
        session.end_build()


def wanted(desk):
    """Each gear's wanted frame and pitch, from the current read (what the window would place)."""
    frames = wb_layout.frames(desk.a.report)
    placed = desk.a.report.layout.placed
    return {g: (f.rotation, f.at, wb_layout.pitch(placed[g])) for g, f in frames.items()}


def measure_frames(worker, desk, label):
    box = desk.record.gearbox
    names = [c.name for c in box.components] + [box.layout_component]
    started = time.monotonic()
    live = run(worker, lambda s: live_frames(s, box.assembly, names))
    want = wanted(desk)
    for c in box.components:
        rotation, at, pitch = want[c.gear]
        got = live[c.name]
        origin, off, residue = frame_error(got, (rotation, at), pitch)
        check(swbuild.same_frame(got[0], got[1], rotation, at, pitch),
              f"{label}: {c.gear} ({c.name}) at {tuple(round(v, 9) for v in got[1])}, origin off {origin:.1e} mm, "
              f"turn off {off:.1e}° modulo its pitch {pitch:.4f}°, axis off {residue:.1e}")
        check(swbuild.same_frame(c.rotation, c.at, rotation, at, pitch), f"{label}: {c.gear}'s frame on record is "
              "the one the workbook wants")
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


def negative_controls(worker, desk, label):
    """Every listed mesh: one of its gears turned half a pitch must clash with its partner and nothing else."""
    box = desk.record.gearbox
    name_of = {c.gear: c.name for c in box.components}
    gear_of = {c.name: c.gear for c in box.components}
    meshes = [tuple(m) for m in box.meshes]
    count = {g: sum(g in m for m in meshes) for c in box.components for g in [c.gear]}
    want = wanted(desk)
    for a, b in meshes:
        turned = b if count[b] == 1 else a
        rotation, at, pitch = want[turned]
        started = time.monotonic()
        moved, back = run(worker, lambda s: placed_elsewhere(s, box.assembly, name_of[turned],
                                                              turn_about_z(rotation, pitch / 2), at))
        merged = swbuild._clashes(moved, gear_of)  # noqa: SLF001
        check(bool(merged) and all(set(c.gears) == {a, b} and c.volume > 0 for c in merged),
              f"{label}: {turned} turned half a pitch ({pitch / 2:.4f}°): {len(moved)} interference(s), merged "
              f"{[(c.gears, round(c.volume, 3)) for c in merged]}, all between {a} and {b}")
        check(back == [], f"{label}: {turned} put back, no interference ({time.monotonic() - started:.1f} s)")


def live_open(session, path):
    """The app's own open of a saved document (OpenDoc6 then ActivateDoc3), reading nothing else."""
    session.begin_build()
    try:
        session.open_document(path)
    finally:
        session.end_build()


def reopen(worker, desk, label):
    left = run(worker, close_ours)
    check(not left, f"{label}: saved and closed this run's documents: left {left}")
    say(f"        open now: {run(worker, open_titles)}")
    box = desk.record.gearbox
    paths = [box.assembly, box.layout] + sorted({c.part for c in box.components})
    # Read straight after the open, before any frame read: the probe never isolated WHICH read after a put or a
    # build marks the assembly (all False after the put; True after the frame reads and interferences() together).
    run(worker, lambda s: live_open(s, box.assembly))
    flags = run(worker, lambda s: save_flags(s, paths))
    check(len(flags) == len(paths) and not marked(flags),
          f"{label}, reopened: every document just opened from its file reads GetSaveFlag False (the record clears "
          f"a mark on that reading): {flags}")
    measure_frames(worker, desk, f"{label}, reopened")
    say(f"fact    {label}, reopened: marked modified after the frame reads (component_frame): "
        f"{marked(run(worker, lambda s: save_flags(s, paths)))}")
    found = run(worker, lambda s: live_interferences(s, box.assembly))
    say(f"fact    {label}, reopened: marked modified after interferences() ({len(found)} found): "
        f"{marked(run(worker, lambda s: save_flags(s, paths)))}")


def measure(worker, desk, label, controls=True, again=True):
    say(f"measure {label}: {memory()}")
    measure_frames(worker, desk, label)
    measure_axes(worker, desk, label)
    measure_clear(worker, desk, label)
    if controls:
        negative_controls(worker, desk, label)
    if again:
        reopen(worker, desk, label)


def _plan_shafts(self):
    return wb_layout.shaft_layouts(self.a.spec)


Desk.plan_shafts = _plan_shafts


# -- Excel ----------------------------------------------------------------------------------------------------


class Workbook:
    """One workbook open in this run's own Excel."""

    def __init__(self, excel, path, tag):
        self.path = path
        self.wb, report = excel.open(path, tag)
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


def fresh_folder(name):
    folder = os.path.join(OUT, name)
    if os.path.exists(folder):
        raise SystemExit(f"{folder} exists already; give a fresh output folder")
    os.makedirs(folder)
    return folder


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


# -- the sections --------------------------------------------------------------------------------------------


def section_a(worker, excel):
    say("== a   the 12 : 1 fixture: build, measure, Update SolidWorks, build again as _r2")
    folder = fresh_folder("a")
    path = os.path.join(folder, "Reducer_12to1.xlsx")
    shutil.copy2(FIXTURE_12, path)
    book = Workbook(excel, path, "a")
    book.set("Box", "B4", folder + "\\")
    book.save()
    desk = Desk(path, worker)
    desk.read()
    check(desk.a.lay_out_refusal() == "", "the gate is \"\"")
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
    check(result.clashes == [] and not result.interference_error, f"no interference: {result.clashes}")
    check_fresh_build_marks(worker, made, made[-1], "a")
    check(desk.record is not None and desk.record.digest == desk.reading.digest and desk.record.gearbox.assembly,
          "the record holds the gearbox, built from this read")
    desk.say_footer("after the build")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    guard()
    measure(worker, desk, "a built")
    first = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in desk.record.gearbox.components}

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
          and u.moved_shafts == ("S2", "S3") and set(u.replaced) == {"G2", "G3", "G4"},
          "classify: no structural change; G2's values, S2 and S3 moved, G2, G3 and G4 re-placed")
    desk.say_footer("after the edit")
    guard()
    _, update_result, _ = desk.update_solidworks()
    after_update = stamps(folder, solidworks_only=True)
    changed_files = [n for n in before_update if before_update[n] != after_update.get(n)]
    check(changed_files == [], f"Update SolidWorks saved nothing: SolidWorks files changed on disk {changed_files} "
          f"(of {len(before_update)})")
    unsaved = sorted(os.path.basename(p) for p in desk.record.unsaved)
    check(unsaved == ["Gear_m1.5_N68.SLDPRT", "Reducer_12to1.SLDASM", "Reducer_12to1_Layout.SLDPRT"],
          f"the record marks them unsaved: {unsaved}")
    n68 = desk.record.parts[1].path
    sidecar = store.read_sidecar(n68)
    check(sidecar is not None and sidecar.record.unsaved_since > 0 and sidecar.record.spec.get("teeth") == "69",
          f"Gear_m1.5_N68.gear.json says 69 teeth, marked unsaved since {sidecar and sidecar.record.unsaved_since}")
    flags = run(worker, lambda s: save_flags(s, [os.path.join(folder, n) for n in before_update]))
    say(f"        marked modified in SolidWorks right after the update: {flags}")
    wanted_marks = expected_marks(update_result, desk.record.gearbox.assembly)
    check(marked(flags) == wanted_marks,
          "SolidWorks marks modified exactly the documents Update changed and the assembly it rebuilt (review S2, "
          f"and the top-only rebuild): marked {marked(flags)}, expected {wanted_marks}")
    desk.say_footer("after the update")
    say(f"tag     {ui_text.workbook_built_tag(desk.record, desk.reading.digest)!r}")
    measure_frames(worker, desk, "a updated")
    axes = measure_axes(worker, desk, "a updated")
    check(abs(axes["S2 Axis"][0][0] - 64.5) < 1e-6 and abs(axes["S3 Axis"][0][0] - 132.5) < 1e-6,
          "S2 Axis at x 64.5 and S3 Axis at x 132.5")
    g1 = next(c for c in desk.record.gearbox.components if c.gear == "G1")
    check(swbuild.same_frame(first["G1"][0], first["G1"][1], g1.rotation, g1.at, 360 / 17), "G1 unchanged")
    g2 = next(c for c in desk.record.gearbox.components if c.gear == "G2")
    _, off, _ = frame_error((g2.rotation, g2.at), (wb_layout.IDENTITY, g2.at), 360 / 69)
    check(off < 1e-6, f"G2's turn is now 0 modulo its pitch (69 teeth, odd): off {off:.1e}°")
    values = run(worker, lambda s: live_globals(s, g2.part))
    check(abs(values.get("No. of Teeth", 0) - 69) < 1e-9, f"G2's part {os.path.basename(g2.part)} holds "
          f"\"No. of Teeth\" = {values.get('No. of Teeth')}")
    measure_clear(worker, desk, "a updated")
    say("        control: the assembly shows G2 with 69 teeth: put back at its old frame (63.75, 68-tooth turn)")
    old_rotation, old_at = first["G2"]
    moved, back = run(worker, lambda s: placed_elsewhere(s, desk.record.gearbox.assembly, g2.name, old_rotation,
                                                          old_at))
    merged = swbuild._clashes(moved, {c.name: c.gear for c in desk.record.gearbox.components})  # noqa: SLF001
    check(bool(merged) and all(set(c.gears) == {"G1", "G2"} for c in merged),
          f"at its old frame the 69-tooth G2 runs into G1 (a 68-tooth gear sat there clean): "
          f"{[(c.gears, round(c.volume, 3)) for c in merged]}")
    check(back == [], "put back where the update put it, no interference")
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
    say(f"question {ui_text.build_again_question(desk.update, desk.plan)}")
    f = desk.say_footer("structural, unsaved")
    check(f.build_enabled and f.update_enabled, "neither Build again… nor Update SolidWorks is held by the unsaved "
          "documents")
    guard()
    earlier = stamps(folder)
    say(f"stamps  {len(earlier)} earlier files: " + ", ".join(sorted(earlier)))
    desk.build()
    later = stamps(folder)
    touched = [n for n in earlier if later.get(n) != earlier[n]]
    new = sorted(n for n in later if n not in earlier)
    check(touched == [], f"build again: every earlier file's sha256 and mtime unchanged: changed {touched}")
    check(new == ["Gear_m1.5_N17_r2.SLDPRT", "Gear_m1.5_N17_r2.gear.json", "Gear_m1.5_N69.SLDPRT",
                  "Gear_m1.5_N69.gear.json", "Reducer_12to1_r2.SLDASM", "Reducer_12to1_r2_Layout.SLDPRT"],
          f"new files only where needed: {new}")
    rec = desk.record
    check(rec.gearbox.revision == 2 and [e.revision for e in rec.earlier] == [0]
          and [os.path.basename(p) for e in rec.earlier for p in e.parts] == ["Gear_m1.5_N17.SLDPRT",
                                                                              "Gear_m1.5_N68.SLDPRT"],
          f"the record: revision 2 current; revision 0 earlier, with the G1 and G2 parts it no longer uses")
    flags = run(worker, lambda s: save_flags(s, [os.path.join(folder, n) for n in earlier if n.endswith(
        (".SLDPRT", ".SLDASM"))]))
    say(f"        marked modified in SolidWorks now (not saved): {flags}")
    check(flags.get("Gear_m1.5_N17.SLDPRT") is False, "the superseded G1 part, which Update never changed, is not "
          "marked modified (it read True before review S2)")
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
    check(result.ok and len(result.checked) == 5 and result.clashes == [],
          f"carried on: checked {[os.path.basename(c) for c in result.checked]}, assembly saved, no interference")
    check(desk.record.digest == desk.reading.digest, "the record now claims this read")
    measure(worker, desk, "a2 carried on", controls=False, again=False)
    desk.say_footer("after carrying on")
    say("-- a2  Build pressed again, nothing changed")
    desk.say_update()
    desk.say_plan(full=False)
    p = desk.plan
    say(f"question {ui_text.build_again_question(desk.update, p)}")
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
        "closed unsaved")
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
    check(result.ok and result.checked[:2] == [r.path for r in p.reuse],
          f"built, the two checked live first: {[os.path.basename(c) for c in result.checked]}")
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
    check(result.changed == [], f"Update found every document holding the workbook's values: changed "
          f"{[os.path.basename(x) for x in result.changed]}")
    check(sorted(os.path.basename(x) for x in result.opened) == sorted(os.path.basename(x) for x in current),
          f"it loaded every document from its file: {[os.path.basename(x) for x in result.opened]}")
    check(desk.record.unsaved == {} and desk.record.mismatched == {},
          f"the marks are gone: unsaved {list(desk.record.unsaved)}, mismatched {list(desk.record.mismatched)}")
    sidecar = store.read_sidecar(n68)
    check(sidecar.record.unsaved_since == 0 and sidecar.record.spec.get("teeth") == "68",
          f"Gear_m1.5_N68.gear.json says 68 teeth, unmarked ({sidecar.record.unsaved_since})")
    tag = ui_text.workbook_built_tag(desk.record, desk.reading.digest)
    check(tag == " · built from this version", f"the header: {tag!r}")
    book.set("Gears", "J2", None)
    book.save()
    desk.poll()
    desk.say_plan(full=False)
    q = desk.plan
    check(q is not None and n68 in [r.path for r in q.reuse] and not any(store.same_path(m.old, n68)
                                                                       for m in q.made_new),
          "a build-again plan now reuses Gear_m1.5_N68 (it made it new for ever before the second review)")
    desk.say_footer("structural, nothing unsaved")
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
    desk.say_plan()
    guard()
    plan, result = desk.build()
    check(result.ok and result.clashes == [], f"built: parts, layout, assembly, no interference {result.clashes}")
    box = desk.record.gearbox
    check_fresh_build_marks(worker, [box.layout, box.assembly] + sorted({c.part for c in box.components}),
                            box.assembly, "b")
    measure(worker, desk, "b built")
    guard()
    before = stamps(folder, solidworks_only=True)
    book.set("Shafts", "L3", 40)
    book.save()
    desk.poll()
    desk.say_update()
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
    check(marked(flags) == ["Arc_Move.SLDASM", "Arc_Move_Layout.SLDPRT"]
          and marked(flags) == expected_marks(result, desk.record.gearbox.assembly),
          "SolidWorks marks modified only the layout and the assembly: Update left every part as it was (review "
          f"S2, and the top-only rebuild): {marked(flags)}")
    check(result.clashes == [] and not result.interference_error, f"no interference after the move: {result.clashes}")
    after = stamps(folder, solidworks_only=True)
    check([n for n in before if before[n] != after.get(n)] == [], f"Update saved nothing ({len(before)} SolidWorks "
          "files, sha256 and mtime)")
    measure(worker, desk, "b moved")

    say("-- b   a part-only Update, no gear re-placed: G2's bore 8 -> 10")
    guard()
    before = stamps(folder, solidworks_only=True)
    book.set("Gears", "J3", 10)
    book.save()
    desk.poll()
    desk.say_update()
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
    wanted_marks = expected_marks(result, desk.record.gearbox.assembly)
    check(marked(flags) == wanted_marks,
          f"SolidWorks marks modified G2's part, and the assembly only if Update rebuilt it (rebuilt "
          f"{result.rebuilt}): marked {marked(flags)}, expected {wanted_marks}")
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
    desk.say_plan()
    guard()
    plan, result = desk.build()
    check(result.ok, "built: 6 parts, the layout part and the assembly saved")
    check(result.clashes == [] and not result.interference_error,
          f"no interference between correctly placed gears: {[(c.gears, round(c.volume, 3)) for c in result.clashes]}")
    measure(worker, desk, "c built")
    book.close()


SECTIONS = {"a": section_a, "a2": section_a2, "a3": section_a3, "b": section_b, "c": section_c}


def connect_pid():
    found = [c for c in swcom.find_candidates() if c.pid == PID]
    if not found:
        raise swcom.NotRunning(f"No SolidWorks session with PID {PID} is reachable.")
    return swcom.Session(found[0].app, found[0].revision, found[0].pid)


def main():
    os.makedirs(OUT, exist_ok=True)
    say(f"run     {time.strftime('%Y-%m-%d %H:%M:%S')}; app {WRITTEN_BY} from {SRC}; sections {ONLY}")
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
            try:
                SECTIONS[name](worker, excel)
            except Stopped as exc:
                check(False, f"section {name} stopped: {exc}")
                break
            except Exception as exc:  # noqa: BLE001 - logged, and the documents still closed below
                check(False, f"section {name} raised {type(exc).__name__}: {exc}")
                for line in traceback.format_exc().splitlines():
                    say("        " + line)
            finally:
                left = run(worker, close_ours, 600)
                say(f"close   section {name}: left of ours {left}; {time.monotonic() - started:.0f} s; {memory()}")
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
