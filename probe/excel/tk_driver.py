r"""Check 4 (drives real Excel and the app's real Tk window; never SolidWorks).

The Workbook window is opened the way Import workbook… opens it (workbook_gui.open_workbook with the
path, no file dialog) under a unique title, and walked through its states while an Excel of its own saves
the file: clean; open in Excel; S2 typed at 64 (the error and both fixes, the change list); the shift
fix chosen; Export refused while Excel has the file; Export; an outside save; G2 to 70 teeth; the file made
unreadable (Export and Export as… disabled); restored. Each state is captured from the window's own
handle with PrintWindow into <scratch>\shots\window\.

SolidWorks is never touched: swcom.is_available is patched to False, so the strip starts no worker.
APPDATA points into the scratch folder, so the user's recent list is not changed.
"""

import ctypes
import json
import os
import queue
import shutil
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ROOT = os.environ.get("GG_EXCEL_SCRATCH") or os.path.join(
    os.environ["USERPROFILE"], "Documents", "GearGeneratorProbe", "excel-checks")    # as xlhelp.ROOT
FIXTURE = os.path.join(REPO, "tests", "fixtures", "excel-windows", "Reducer_12to1.xlsx")
os.environ["APPDATA"] = os.path.join(ROOT, "appdata")     # the app's recent list goes here, not the user's
os.makedirs(os.environ["APPDATA"], exist_ok=True)
sys.path.insert(0, os.environ.get("GG_SRC") or os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import tkinter as tk  # noqa: E402

import win32gui  # noqa: E402
import win32ui  # noqa: E402
from PIL import Image  # noqa: E402

from gear_generator import gui, swcom, theme, workbook_gui  # noqa: E402
from gear_generator.workbook import xlsx  # noqa: E402

UNIQUE = "GG workbook check 7f3a"
SHOTS = os.path.join(ROOT, "shots", "window")
os.makedirs(SHOTS, exist_ok=True)
OUT = os.path.join(ROOT, "window")
if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
PATH = os.path.join(OUT, "Reducer_12to1.xlsx")
shutil.copy(FIXTURE, PATH)
LOG = open(os.path.join(ROOT, "tk_driver.jsonl"), "w", encoding="utf-8")


def log(kind, **kw):
    kw.update(kind=kind, t=time.time())
    LOG.write(json.dumps(kw, ensure_ascii=False, default=str) + "\n")
    LOG.flush()
    print(time.strftime("%H:%M:%S"), kind, json.dumps({k: v for k, v in kw.items() if k not in ("kind", "t")},
                                                      ensure_ascii=False, default=str)[:400], flush=True)


# -- Excel on its own thread -------------------------------------------------------------------------------

jobs: "queue.Queue" = queue.Queue()
done: "queue.Queue" = queue.Queue()


def excel_thread():
    from xlhelp import Excel, Watcher
    xl = Excel(visible=True)
    watcher = Watcher(xl.pid, "window-session", xl.hwnd)
    watcher.start()
    wb = None
    try:
        while True:
            job = jobs.get()
            if job is None:
                break
            what, args = job
            t0 = time.time()
            try:
                if what == "open":
                    wb, rep = xl.open(PATH, "window")
                    result = rep["repaired"]
                elif what == "set-save":
                    for sheet, ref, value in args:
                        wb.Worksheets(sheet).Range(ref).Value = value
                    t0 = time.time()
                    wb.Save()
                    result = "saved"
                elif what == "close":
                    wb.Close(SaveChanges=False)
                    wb = None
                    result = "closed"
                done.put((what, t0, time.time(), result, ""))
            except Exception as exc:  # noqa: BLE001
                done.put((what, t0, time.time(), None, f"{type(exc).__name__}: {exc}"))
    finally:
        watcher.stop.set()
        watcher.join()
        log("excel dialogs", seen=watcher.seen)
        if wb is not None:
            del wb
        xl.quit()


XT = threading.Thread(target=excel_thread, daemon=True)
XT.start()

# -- the app --------------------------------------------------------------------------------------------------

swcom.is_available = lambda: False
gui._declare_dpi_aware()
theme.register_bundled_fonts()
root = tk.Tk()
root.title(UNIQUE + " strip")
scale = gui._scale_to_dpi(root)
app = gui.GearApp(root, scale=scale)
root.withdraw()
win = workbook_gui.open_workbook(app, PATH)
win.title(UNIQUE)
log("opened", scale=scale, tk_scaling=float(root.tk.call("tk", "scaling")),
    dpi=ctypes.windll.user32.GetDpiForWindow(int(win.wm_frame(), 16)))

shows = []
real_show = win._show


def show(reading):
    shows.append((time.time(), reading.changes, reading.error, reading.own))
    try:
        log("show", changes=reading.changes, error=reading.error, own=reading.own)
    finally:
        real_show(reading)


win._show = show


def shoot(name):
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
    log("shot", path=path, size=(w, h), status=win.status.get(), read_line=win.read_line.get(),
        checks=win.checks_readout.get(), changes=win.changes, chosen=[f.title for f in win.chosen],
        export_enabled=win.export_button._enabled, export_as_enabled=win.export_as_button._enabled)


# -- the steps ------------------------------------------------------------------------------------------------

def excel(what, *args):
    jobs.put((what, args))


def wait_done(what):
    def check():
        try:
            item = done.get_nowait()
        except queue.Empty:
            return False
        log("excel", what=item[0], start=item[1], end=item[2], result=item[3], error=item[4])
        state["last_excel"] = item
        return True
    return check


def shows_since(t):
    return [s for s in shows if s[0] >= t]


state = {}


def seen_change(text):
    def check():
        start = state["last_excel"][2] if state.get("last_excel") else 0
        for when, changes, error, own in shows_since(start - 0.05):
            if any(text in c for c in changes):
                log("latency", text=text, seconds_after_save=round(when - start, 3))
                return True
        return False
    return check


def seen_any_show_after_excel():
    start = state["last_excel"][2]
    return bool(shows_since(start - 0.05))


fix = {}
STEPS = [
    ("wait", lambda: time.time() - T0 > 2.5),
    ("do", lambda: shoot("01-clean")),
    ("do", lambda: excel("open")),
    ("wait", wait_done("open")),
    ("wait", lambda: "open in Excel" in win.read_line.get()),
    ("do", lambda: shoot("02-open-in-excel")),
    ("do", lambda: excel("set-save", ("Shafts", "C3", 64))),
    ("wait", wait_done("set-save")),
    ("wait", seen_change("Shafts!C3")),
    ("pause", 0.6),
    ("do", lambda: shoot("03-s2-64-error-both-fixes")),
    ("do", lambda: fix.update(move=win.report.fixes["Meshes!A2"][0], shift=win.report.fixes["Meshes!A2"][1])),
    ("do", lambda: win.choose(fix["shift"])),
    ("do", lambda: shoot("04-shift-chosen")),
    ("do", lambda: win.export()),                         # Excel holds the file: refused
    ("do", lambda: shoot("05-export-while-open-in-excel")),
    ("do", lambda: excel("close")),
    ("wait", wait_done("close")),
    ("wait", lambda: not xlsx.is_open_in_excel(PATH)),
    ("pause", 1.2),
    ("do", lambda: win.export()),
    ("pause", 0.5),
    ("do", lambda: shoot("06-exported")),
    ("do", lambda: excel("open")),
    ("wait", wait_done("open")),
    ("do", lambda: excel("set-save", ("Shafts", "K4", "output shaft"))),
    ("wait", wait_done("set-save")),
    ("wait", seen_change("Shafts!K4")),
    ("pause", 0.6),
    ("do", lambda: shoot("07-after-excel-save")),
    ("do", lambda: excel("set-save", ("Gears", "F3", 70))),
    ("wait", wait_done("set-save")),
    ("wait", seen_change("Gears!F3")),
    ("pause", 0.6),
    ("do", lambda: shoot("08-teeth-70-change-list")),
    ("do", lambda: excel("set-save", ("Gears", "F3", 68))),
    ("wait", wait_done("set-save")),
    ("wait", seen_change("Gears!F3")),
    ("do", lambda: excel("close")),
    ("wait", wait_done("close")),
    ("wait", lambda: not xlsx.is_open_in_excel(PATH)),
    ("pause", 1.5),
    # No good read: the file becomes something that is not a workbook.
    ("do", lambda: (shutil.copy(PATH, PATH + ".keep"), open(PATH, "wb").write(xlsx.OLE_MAGIC + b"\0" * 600))),
    ("wait", lambda: bool(win.error)),
    ("do", lambda: win.export(out_path=os.path.join(OUT, "as.xlsx"))),   # what Export as… does after its dialog
    ("do", lambda: shoot("09-no-good-read-export-as")),
    ("do", lambda: log("export as wrote", exists=os.path.exists(os.path.join(OUT, "as.xlsx")))),
    ("do", lambda: os.replace(PATH + ".keep", PATH)),
    ("wait", lambda: not win.error),
    ("pause", 0.8),
    ("do", lambda: shoot("10-back")),
]
T0 = time.time()
DEADLINE = T0 + 240


def step():
    if time.time() > DEADLINE:
        log("TIMEOUT", left=len(STEPS))
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
        elif kind == "wait":
            if arg():
                STEPS.pop(0)
        elif kind == "pause":
            STEPS.pop(0)
            root.after(int(arg * 1000), step)
            return
    except Exception as exc:  # noqa: BLE001
        import traceback
        log("STEP FAILED", step=kind, error=traceback.format_exc())
        STEPS.pop(0)
    root.after(100, step)


def finish():
    jobs.put(None)
    log("finish", shows=len(shows))
    try:
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
time.sleep(1)
log("exit")
