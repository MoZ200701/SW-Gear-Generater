r"""The Workbook window against real SolidWorks and Excel: Build, Update SolidWorks, Build again (W4, and W5's footers).

python.exe probe/workbook_window_check.py <repo src> <scratch folder under C:\> --pid PID [--log FILE]
                                          [--w4-static FOLDER]

The window is opened the way Import workbook… opens it (``workbook_gui.open_workbook`` with the path) under a
unique title, in a Tk process of its own, with the strip's real SolidWorks worker: nothing is patched but
``workbook_gui.ask_yes_no`` (the Build again? question, answered Yes and logged), APPDATA (the recent list goes
into the scratch folder, not the user's) and, for stage 5 only, ``workbook_gui.wb_gearbox.plan_gearbox`` for that
one folder. The strip attaches to the newest SolidWorks, so this refuses to start unless the newest reachable
session is the PID given. An Excel of its own, on its own thread, makes every edit; the buttons are pressed by
invoking their commands. Each stage is captured from the window's own handle with PrintWindow into <scratch>\shots,
and the footer, read line and gear table are logged.

1. The 12 : 1 fixture, its Output folder cell set to the scratch folder in Excel; the window opened; Build. Since
   W5 the gearbox is built to turn: the sentence and the footer say how ("drag G1 in SolidWorks and the rest of its
   train follow"), shot as 03-built.
2. The demonstration edit in Excel (S2 X 64.5, G2 Teeth 69): the summary (since W5 it sets the gear mate G1 meshes
   G2 to 17 : 69 by the remake), then Update SolidWorks. The header then says "updated from this version, not yet
   saved", never "built from this version".
3. G1's bore cleared in Excel. Since the W4 review (B2) nothing waits for a save: Build again… and Update
   SolidWorks are both enabled, and the footer gives the structural reason, asks once for the save of
   Gear_m1.5_N68, Reducer_12to1_Layout and Reducer_12to1 (since the second review, adding "If SolidWorks closed
   them without saving, those changes are gone."), and says that while Gear_m1.5_N68's changes are not saved
   the new revision makes G2's part new, as Gear_m1.5_N69. The three are then saved in SolidWorks, as a person
   would (by this driver, through COM, on its own thread), so G2's part is reused; then Update SolidWorks asks
   Build again? and the answer is Yes, and the record ends at revision 2 with N68 reused, its journal taken
   out, and the header "built from this version".
4. ``--w4-static FOLDER``: a W4-built gearbox's workbook, opened IN PLACE (its schema-2 record names that very
   workbook, so a copy would read as another's): the footer of a static record — "It was built static, before
   gears could be mated to turn: Build again… makes a new revision whose gears turn." — shot as 09; nothing is
   pressed, and every file in that folder keeps its sha256. Skipped, and said, without the option.
5. The refused state (W5-DECISIONS answer 1): the 12 : 1 in a folder of its own, its plan given one more mate by
   this script (G3, the follower locked to G2, also on S2 Axis and along S2: over-defined, as probe compound_lock
   found); Build stops at the mate check: the sentence names the mate problems, says the assembly is left open
   and that Build is available again once the workbook changes, Build is greyed, the record holds the problems
   and their digest, and no assembly file is written. Shot as 10. The refused document is then closed by its
   title (this run's modified documents saved first, as W4's close_ours does on 2024), any dialog it raises answered
   "Don't Save" and logged: no probe closed a never-saved refused assembly on 2024 under a watch.

Afterwards the window is closed, Excel quit, and this run's SolidWorks documents saved and closed.

Run on SolidWorks 2026 on 2026-11-13 (w4-window-20261113-195843.log) before the W4 review's fixes, and again on
2026 and 2024 on 2026-11-14 (w4-window-20261114-055011.log, sw2024/w4-window-20261114-061023.log) for stages 1-3.
"""

import ctypes
import dataclasses
import json
import os
import queue
import shutil
import sys
import threading
import time

SRC, ROOT = sys.argv[1], sys.argv[2]
PID = int(sys.argv[sys.argv.index("--pid") + 1])
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FIXTURE = os.path.join(REPO, "tests", "fixtures", "excel-windows", "Reducer_12to1.xlsx")
os.environ["APPDATA"] = os.path.join(ROOT, "appdata")
os.environ["GG_SRC"] = SRC
os.environ["GG_EXCEL_SCRATCH"] = ROOT
os.makedirs(os.environ["APPDATA"], exist_ok=True)
sys.path.insert(0, SRC)
sys.path.insert(1, os.path.join(HERE, "excel"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
LOG_PATH = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(ROOT, "window.log")
W4_STATIC = sys.argv[sys.argv.index("--w4-static") + 1] if "--w4-static" in sys.argv else ""

import tkinter as tk  # noqa: E402

import pythoncom  # noqa: E402
import win32gui  # noqa: E402
import win32ui  # noqa: E402
from PIL import Image  # noqa: E402

from gear_generator import gui, store, swcom, theme, ui_text, workbook_gui  # noqa: E402
from gear_generator.gears import base  # noqa: E402
from gear_generator.swcom import call  # noqa: E402
from gear_generator.workbook import layout as wb_layout  # noqa: E402

UNIQUE = "GG workbook W4 check 5c21"
SHOTS = os.path.join(ROOT, "shots")
os.makedirs(SHOTS, exist_ok=True)
FOLDER = os.path.join(ROOT, "window")
os.makedirs(FOLDER)
PATH = os.path.join(FOLDER, "Reducer_12to1.xlsx")
shutil.copy(FIXTURE, PATH)
REFUSED_FOLDER = os.path.join(ROOT, "refused")
os.makedirs(REFUSED_FOLDER)
REFUSED_PATH = os.path.join(REFUSED_FOLDER, "Reducer_12to1.xlsx")
shutil.copy(FIXTURE, REFUSED_PATH)
LINES = []
FAILS = []


def log(kind, **kw):
    text = time.strftime("%H:%M:%S") + " " + kind + " " + json.dumps(kw, ensure_ascii=False, default=str)
    print(text, flush=True)
    LINES.append(text)


def check(ok, what):
    log("ok" if ok else "FAIL", what=what)
    if not ok:
        FAILS.append(what)


# -- Excel on its own thread -------------------------------------------------------------------------------

jobs: "queue.Queue" = queue.Queue()
done: "queue.Queue" = queue.Queue()


def excel_thread():
    from xlhelp import Excel, Watcher
    xl = Excel(visible=True)
    watcher = Watcher(xl.pid, "w4-window", xl.hwnd)
    watcher.start()
    wb = None
    try:
        while True:
            job = jobs.get()
            if job is None:
                break
            what, args = job
            try:
                if what == "open":
                    wb, rep = xl.open(args[0] if args else PATH, "w4-window")
                    result = rep["repaired"]
                elif what == "set-save":
                    for sheet, ref, value in args:
                        cell = wb.Worksheets(sheet).Range(ref)
                        if value is None:
                            cell.ClearContents()
                        else:
                            cell.Value = value
                    wb.Save()
                    result = "saved"
                elif what == "close":
                    wb.Close(SaveChanges=False)
                    wb = None
                    result = "closed"
                done.put((what, time.time(), result, ""))
            except Exception as exc:  # noqa: BLE001
                done.put((what, time.time(), None, f"{type(exc).__name__}: {exc}"))
    finally:
        watcher.stop.set()
        watcher.join()
        log("excel dialogs", seen=watcher.seen)
        if wb is not None:
            try:
                wb.Close(SaveChanges=False)
            except Exception:  # noqa: BLE001
                pass
        xl.quit()


# -- SolidWorks for what a person does there (saving), on its own thread --------------------------------------


def in_solidworks(work):
    """Run ``work(app)`` against the session with PID on a thread of its own; returns its value."""
    out = {}

    def body():
        pythoncom.CoInitialize()
        try:
            found = [c for c in swcom.find_candidates() if c.pid == PID]
            out["value"] = work(found[0].app)
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            pythoncom.CoUninitialize()
    t = threading.Thread(target=body)
    t.start()
    t.join(600)
    return out


def _docs(app):
    out, doc = [], call(app, "GetFirstDocument")
    while doc is not None:
        out.append(doc)
        doc = call(doc, "GetNext")
    return out


def _ours(path):
    return bool(path) and any(os.path.normcase(path).startswith(os.path.normcase(f) + os.sep)
                              for f in (FOLDER, REFUSED_FOLDER))


BEFORE_TITLES = set()        # the untitled documents open before this run: never ours to close


def save_paths(paths):
    def work(app):
        saved = []
        for doc in _docs(app):
            path = str(call(doc, "GetPathName") or "")
            if any(store.same_path(path, p) for p in paths):
                ok = call(call(doc, "Extension"), "SaveAs3", path, 0, 1, swcom._null_dispatch(),  # noqa: SLF001
                          swcom._null_dispatch(), swcom._out_long(), swcom._out_long())  # noqa: SLF001
                saved.append((os.path.basename(path), bool(ok)))
        return saved
    return in_solidworks(work)


def close_ours():
    def work(app):
        for doc in _docs(app):
            path = str(call(doc, "GetPathName") or "")
            if _ours(path) and call(doc, "GetSaveFlag"):
                call(call(doc, "Extension"), "SaveAs3", path, 0, 1, swcom._null_dispatch(),  # noqa: SLF001
                     swcom._null_dispatch(), swcom._out_long(), swcom._out_long())  # noqa: SLF001
        for kind in (2, 1):
            for doc in _docs(app):
                if _ours(str(call(doc, "GetPathName") or "")) and int(call(doc, "GetType")) == kind:
                    call(app, "CloseDoc", str(call(doc, "GetTitle")))
        return [str(call(d, "GetTitle")) for d in _docs(app) if _ours(str(call(d, "GetPathName") or ""))]
    return in_solidworks(work)


DONT_SAVE = ("&No", "No", "Do&n't Save", "Don't Save", "&Don't Save", "Don't save")


def answer_dont_save(stop, pressed):
    """While the refused assembly is closed: any SolidWorks dialog (#32770) of the PID gets its No / Don't Save
    button pressed (BM_CLICK), as a person closing a never-saved assembly unsaved would; each is logged. No probe
    closed one on 2024 under a watch, so this is what keeps a "save changes?" box from holding the close."""
    import win32process
    seen = set()
    while not stop.is_set():
        found = []

        def each(hwnd, _):
            if (win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == "#32770"
                    and win32process.GetWindowThreadProcessId(hwnd)[1] == PID):
                found.append(hwnd)
            return True
        try:
            win32gui.EnumWindows(each, None)
        except Exception:  # noqa: BLE001
            pass
        for hwnd in found:
            if hwnd in seen:
                continue
            seen.add(hwnd)
            buttons = []
            win32gui.EnumChildWindows(hwnd, lambda c, _: buttons.append(c) or True, None)
            hit = [c for c in buttons if win32gui.GetWindowText(c) in DONT_SAVE]
            pressed.append((win32gui.GetWindowText(hwnd), win32gui.GetWindowText(hit[0]) if hit else ""))
            if hit:
                win32gui.PostMessage(hit[0], 0x00F5, 0, 0)
        time.sleep(0.5)


def close_refused():
    """The refused assembly the build left open (an untitled assembly that was not open before the run): this run's
    modified documents saved first, then ``CloseDoc`` by its title, as W4's close_ours closes on 2024, with any
    dialog answered "Don't Save" and logged (``answer_dont_save``)."""
    stop, pressed = threading.Event(), []
    watcher = threading.Thread(target=answer_dont_save, args=(stop, pressed), daemon=True)
    watcher.start()
    try:
        out = _close_refused()
    finally:
        stop.set()
        watcher.join(5)
    out["dialogs"] = pressed
    return out


def _close_refused():
    def work(app):
        for doc in _docs(app):
            path = str(call(doc, "GetPathName") or "")
            if _ours(path) and call(doc, "GetSaveFlag"):
                call(call(doc, "Extension"), "SaveAs3", path, 0, 1, swcom._null_dispatch(),  # noqa: SLF001
                     swcom._null_dispatch(), swcom._out_long(), swcom._out_long())  # noqa: SLF001
        closed = []
        for doc in _docs(app):
            title = str(call(doc, "GetTitle"))
            if not str(call(doc, "GetPathName") or "") and int(call(doc, "GetType")) == 2 and title not in BEFORE_TITLES:
                call(app, "CloseDoc", title)
                closed.append(title)
        left = [str(call(d, "GetTitle")) for d in _docs(app) if not str(call(d, "GetPathName") or "")
                and str(call(d, "GetTitle")) not in BEFORE_TITLES]
        return {"closed": closed, "left": left}
    return in_solidworks(work)


newest = in_solidworks(lambda app: swcom.choose(swcom.find_candidates()).pid)
log("newest session", pid=newest)
if newest.get("value") != PID:
    print("STOP: the strip would attach to", newest, "not", PID)
    raise SystemExit(2)
BEFORE_TITLES.update(in_solidworks(lambda app: [str(call(d, "GetTitle")) for d in _docs(app)
                                                if not str(call(d, "GetPathName") or "")]).get("value", []))

XT = threading.Thread(target=excel_thread, daemon=True)
XT.start()

# -- the app --------------------------------------------------------------------------------------------------

gui._declare_dpi_aware()
theme.register_bundled_fonts()
root = tk.Tk()
root.title(UNIQUE + " strip")
scale = gui._scale_to_dpi(root)
app = gui.GearApp(root, scale=scale)
root.withdraw()
win = None
QUESTIONS = []


def answer_yes(parent, title, question):
    QUESTIONS.append(question)
    log("asked", title=title, question=question)
    return True


workbook_gui.ask_yes_no = answer_yes

# Stage 5: the plan of the refused folder's workbook given one more mate, as probe/workbook_assembly_check.py's m4
# does (W5-PLAN §4.3 m4). Only while INJECT is on, and only for that folder; every other plan is the app's own.
INJECT = {"on": False, "done": []}
_plan_gearbox = workbook_gui.wb_gearbox.plan_gearbox


def _injected(plan):
    handle_of = {g: h for h, g in plan.handles.items()}
    h3 = handle_of["G3"]
    z = plan.frames["G3"].at[2]
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
        return plan
    return dataclasses.replace(plan, assembly=dataclasses.replace(plan.assembly, ops=tuple(ops)))


def plan_gearbox(*args, **kwargs):
    plan = _plan_gearbox(*args, **kwargs)
    if (INJECT["on"] and plan is not None and not plan.refusal and plan.assembly is not None
            and store.same_path(os.path.dirname(plan.assembly_path), REFUSED_FOLDER)):
        plan = _injected(plan)
        INJECT["done"].append(plan.assembly_path)
    return plan


workbook_gui.wb_gearbox.plan_gearbox = plan_gearbox


def shoot(name):
    # Tk's own update(): the window's UpdatePlan is update_plan since the W4 review, so nothing hides it now.
    win.update_idletasks()
    win.update()
    hwnd = int(win.wm_frame(), 16)
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    w, h = right - left, bottom - top
    wdc = win32gui.GetWindowDC(hwnd)
    dc = win32ui.CreateDCFromHandle(wdc)
    mem = dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dc, w, h)
    mem.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)
    info = bmp.GetInfo()
    img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bmp.GetBitmapBits(True), "raw", "BGRX",
                           0, 1)
    path = os.path.join(SHOTS, name + ".png")
    img.save(path)
    win32gui.DeleteObject(bmp.GetHandle())
    mem.DeleteDC()
    dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, wdc)
    state(name, path=path)


def state(name, **kw):
    footer = win.footer()
    log("state", name=name, status=win.status.get(), read_line=win.read_line.get(),
        build=(footer.build_label, footer.build_enabled, footer.build_primary),
        update=(footer.update_shown, footer.update_enabled, footer.update_primary),
        parts=win.parts_readout.get(), changes=win.changes_readout.get(), **kw)


def excel(what, *args):
    jobs.put((what, args))


LAST = {}


def excel_done(what):
    def ok():
        try:
            item = done.get_nowait()
        except queue.Empty:
            return False
        log("excel", what=item[0], at=item[1], result=item[2], error=item[3])
        LAST["excel"] = item
        return True
    return ok


def open_window(path=PATH, title=UNIQUE):
    global win
    if win is not None and not win._closed():  # noqa: SLF001
        win.close()
    win = workbook_gui.open_workbook(app, path)
    win.title(title)


def idle():
    return win._pending is None and win._job is None  # noqa: SLF001


def status_starts(*heads):
    return lambda: idle() and win.status.get().startswith(heads)


def save_unsaved():
    record = store.read_link_record(PATH)
    paths = list(record.unsaved) if record is not None else []
    log("person saves in SolidWorks", paths=[os.path.basename(p) for p in paths], result=save_paths(paths))


def built_turning_check():
    record = store.read_link_record(PATH)
    box = record.gearbox
    drag = ui_text.drag_phrase(list(box.drag))
    check(box.kind == store.GEARBOX_MOTION, f"built to turn: kind {box.kind!r}")
    check(drag in win.status.get(), f"the built footer says how to turn it: {drag!r}")


def _folder_stamps(folder):
    import hashlib
    out = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                out[name] = (hashlib.sha256(handle.read()).hexdigest(), os.stat(path).st_mtime_ns)
    return out


STATIC = {}


def open_static():
    workbook = next((os.path.join(W4_STATIC, n) for n in sorted(os.listdir(W4_STATIC)) if n.endswith(".xlsx")
                     and not n.startswith("~$")), "")
    STATIC["path"], STATIC["before"] = workbook, _folder_stamps(W4_STATIC)
    raw = json.load(open(store.link_record_path(workbook), encoding="utf-8"))
    log("the W4 static record's source", folder=W4_STATIC, workbook=os.path.basename(workbook),
        schema=raw.get("schema"), built=(raw.get("gearbox") or {}).get("built"), kind=(raw.get("gearbox") or {}).get(
            "kind", "(none: schema 2)"), written_by=raw.get("written_by"))
    open_window(workbook, UNIQUE + " static")


def static_check():
    text = win.status.get()
    check("It was built static, before gears could be mated to turn: Build again… makes a new revision whose gears "
          "turn." in text, "the W4 static record's footer says it was built static and Build again… turns")
    win.close()
    after = _folder_stamps(W4_STATIC)
    check(after == STATIC["before"], f"nothing in the W4 folder changed: "
          f"{[n for n in after if after.get(n) != STATIC['before'].get(n)]}")


def refused_check():
    text, footer = win.status.get(), win.footer()
    record = store.read_link_record(REFUSED_PATH)
    box = record.gearbox
    check(bool(INJECT["done"]), f"the plan was given the extra mates: {INJECT['done']}")
    check(box is not None and not box.assembly and box.mate_problems and box.mate_problems_digest
          == win.reading.digest, f"the record: no assembly, the mate problems and their digest: "
          f"{box and box.mate_problems}")
    check(not os.path.exists(os.path.join(REFUSED_FOLDER, "Reducer_12to1.SLDASM")), "no assembly file")
    check("no assembly was saved" in text and "Build is available again once the workbook changes" in text,
          "the sentence: no assembly saved, and Build waits for a changed workbook")
    check(any(p in text for p in box.mate_problems), "the sentence names the mate problems")
    check("left open in SolidWorks as" in text, "the sentence names the document left open")
    check(not footer.build_enabled, "Build greyed for the unchanged workbook")
    INJECT["on"] = False


def record_check():
    record = store.read_link_record(PATH)
    check(record.gearbox.revision == 2 and [e.revision for e in record.earlier] == [0],
          f"the record: revision {record.gearbox.revision}, earlier {[e.revision for e in record.earlier]}")
    check(record.pending == [], f"the build's journal taken out: {[os.path.basename(e.path) for e in record.pending]}")
    check(win.read_line.get().endswith(" · built from this version"), f"the header: {win.read_line.get()!r}")
    parts = sorted(os.path.basename(c.part) for c in record.gearbox.components)
    check("Gear_m1.5_N68.SLDPRT" in parts and "Gear_m1.5_N69.SLDPRT" not in parts,
          f"G2's part reused once saved: {parts}")


def updated_check():
    check(win.read_line.get().endswith(" · updated from this version, not yet saved"),
          f"the header after Update: {win.read_line.get()!r}")


def structural_unsaved_check():
    text, footer = win.status.get(), win.footer()
    check(footer.build_enabled and footer.update_enabled, "both buttons on with Update's changes unsaved")
    check(text.count("save them in SolidWorks") == 1 and text.lower().count("build again") == 1,
          "the save asked once, and build again said once")
    check("Gear_m1.5_N68, Reducer_12to1_Layout and Reducer_12to1 have changes from Update SolidWorks" in text,
          "the three unsaved documents named")
    check("While Gear_m1.5_N68's changes are not saved, the new revision makes G2's part new, as Gear_m1.5_N69"
          in text, "the part made new while unsaved said")
    check("If SolidWorks closed them without saving, those changes are gone." in text,
          "the save asked as what may no longer be possible (second review N2)")


STEPS = [
    ("do", lambda: excel("open")),
    ("wait", excel_done("open")),
    ("do", lambda: excel("set-save", ("Box", "B4", FOLDER + "\\"))),
    ("wait", excel_done("set-save")),
    ("do", open_window),
    ("wait", lambda: win.reading is not None and win.reading.ok and win.footer().build_enabled),
    ("pause", 1.0),
    ("do", lambda: shoot("01-ready")),
    ("do", lambda: win.build_button.command()),
    ("pause", 2.0),
    ("do", lambda: shoot("02-building")),
    ("wait", status_starts("Built", "Check", "Update SolidWorks stopped", "SolidWorks cannot")),
    ("pause", 1.5),
    ("do", lambda: shoot("03-built")),
    ("do", built_turning_check),
    ("do", lambda: excel("set-save", ("Shafts", "C3", 64.5), ("Gears", "F3", 69))),
    ("wait", excel_done("set-save")),
    ("wait", status_starts("Update SolidWorks will")),
    ("pause", 1.0),
    ("do", lambda: shoot("04-demonstration-edit")),
    ("do", lambda: win.update_button.command()),
    ("wait", status_starts("Updated SolidWorks", "Update SolidWorks stopped", "SolidWorks already")),
    ("pause", 1.5),
    ("do", lambda: shoot("05-updated")),
    ("do", updated_check),
    ("do", lambda: excel("set-save", ("Gears", "J2", None))),
    ("wait", excel_done("set-save")),
    ("wait", lambda: idle() and "build again" in win.status.get().lower()),
    ("pause", 1.0),
    ("do", lambda: shoot("06-structural-unsaved")),
    ("do", structural_unsaved_check),
    ("do", save_unsaved),
    ("wait", lambda: idle() and "not saved" not in win.status.get() and win.footer().build_enabled),
    ("pause", 1.0),
    ("do", lambda: shoot("07-structural-saved")),
    ("do", lambda: win.update_button.command()),
    ("wait", lambda: bool(QUESTIONS) and idle() and win.status.get().startswith(("Built", "Check"))),
    ("pause", 1.5),
    ("do", lambda: shoot("08-built-again")),
    ("do", record_check),
] + ([
    ("do", open_static),
    ("wait", lambda: win.reading is not None and win.reading.ok and idle()),
    ("pause", 1.5),
    ("do", lambda: shoot("09-w4-static-record")),
    ("do", static_check),
] if W4_STATIC else [("do", lambda: log("skipped", what="the W4 static record's footer: no --w4-static folder"))]) + [
    ("do", lambda: excel("close")),
    ("wait", excel_done("close")),
    ("do", lambda: excel("open", REFUSED_PATH)),
    ("wait", excel_done("open")),
    ("do", lambda: excel("set-save", ("Box", "B4", REFUSED_FOLDER + "\\"))),
    ("wait", excel_done("set-save")),
    ("do", lambda: INJECT.update(on=True)),
    ("do", lambda: open_window(REFUSED_PATH, UNIQUE + " refused")),
    ("wait", lambda: win.reading is not None and win.reading.ok and win.footer().build_enabled),
    ("do", lambda: win.build_button.command()),
    ("wait", status_starts("Built", "No assembly", "Check", "SolidWorks cannot")),
    ("pause", 1.5),
    ("do", lambda: shoot("10-refused")),
    ("do", refused_check),
    ("do", lambda: log("refused document", result=close_refused())),
]
T0 = time.time()
DEADLINE = T0 + 2400


def step():
    if time.time() > DEADLINE:
        log("TIMEOUT", left=[s[0] for s in STEPS][:3])
        FAILS.append("timeout")
        finish()
        return
    if not STEPS:
        finish()
        return
    kind, arg = STEPS[0]
    try:
        if kind == "do":
            STEPS.pop(0)
            arg()
            if win is not None:
                log("status", now=win.status.get())
        elif kind == "wait":
            if arg():
                STEPS.pop(0)
                log("waited", status=win.status.get() if win is not None else "")
            elif win is not None and time.time() - LAST.get("said", 0) > 15:
                LAST["said"] = time.time()
                log("waiting", status=win.status.get())
        elif kind == "pause":
            STEPS.pop(0)
            root.after(int(arg * 1000), step)
            return
    except Exception:  # noqa: BLE001
        import traceback
        log("STEP FAILED", step=kind, error=traceback.format_exc())
        FAILS.append("step failed")
        STEPS.pop(0)
    root.after(200, step)


def finish():
    jobs.put(None)
    try:
        if win is not None:
            state("final")
            win.close()
    finally:
        end = time.time() + 40

        def later():
            if XT.is_alive() and time.time() < end:
                root.after(250, later)
            else:
                log("excel thread", alive=XT.is_alive())
                root.destroy()
        root.after(250, later)


root.after(500, step)
root.mainloop()
log("closed in SolidWorks", left=close_ours())
log("done", fails=FAILS)
with open(LOG_PATH, "w", encoding="utf-8", newline="\n") as handle:
    handle.write("\n".join(LINES) + "\n")
raise SystemExit(1 if FAILS else 0)
