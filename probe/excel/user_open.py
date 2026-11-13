r"""Check 1, part two (drives real Excel): open each file the way a person does, and look for a repair.

EXCEL.EXE /x <file> starts Excel in its own process, as a double-click would; for 10 s every window that
process shows is recorded (a repair prompt is a dialog, screenshotted and answered No by WM_CLOSE), with
the main window's caption ("[Repaired]") and any new %TEMP%\error*.xml recovery log. Then Excel's own
object model is reached through its EXCEL7 window, the workbook closed unsaved and Excel quit.

Opening this way puts the file in Excel's recent-files list, as a person's open would.

usage: python user_open.py [<file> ...]   (default: export_checks.py's pristine files and controls)
Writes <scratch>\user_open.json.
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlhelp import ROOT, TEMP, Watcher, log, shoot_rect, windows_of  # noqa: E402

import glob  # noqa: E402

import pythoncom  # noqa: E402
import win32com.client  # noqa: E402
import win32con  # noqa: E402
import win32gui  # noqa: E402

EXCEL = r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE"


def find_child(hwnd, cls):
    found = []

    def each(child, _):
        if win32gui.GetClassName(child) == cls:
            found.append(child)
        return True

    try:
        win32gui.EnumChildWindows(hwnd, each, None)
    except win32gui.error:
        pass
    return found


def application_of(main):
    for child in find_child(main, "EXCEL7"):
        try:
            _, result = win32gui.SendMessageTimeout(child, win32con.WM_GETOBJECT, 0, 0xFFFFFFF0,
                                                    win32con.SMTO_ABORTIFHUNG, 5000)
            if result:
                obj = pythoncom.ObjectFromLresult(result, pythoncom.IID_IDispatch, 0)
                return win32com.client.Dispatch(obj).Application
        except Exception as exc:  # noqa: BLE001
            log("attach trouble", exc)
    return None


def one(path, tag, settle=10):
    before = set(glob.glob(os.path.join(TEMP, "error*.xml")))
    proc = subprocess.Popen([EXCEL, "/x", path])
    pid = proc.pid
    main = None
    for _ in range(100):
        mains = [h for h in windows_of(pid) if win32gui.GetClassName(h) == "XLMAIN"]
        if mains:
            main = mains[0]
            break
        time.sleep(0.2)
    watcher = Watcher(pid, tag, main)
    watcher.start()
    time.sleep(settle)
    caption = win32gui.GetWindowText(main) if main else ""
    shot = shoot_rect(main, f"user-open-{tag}.png") if main else ""
    watcher.stop.set()
    watcher.join()
    report = {"path": path, "pid": pid, "caption": caption, "shot": shot, "dialogs": watcher.seen,
              "new_error_logs": sorted(set(glob.glob(os.path.join(TEMP, "error*.xml"))) - before)}
    pythoncom.CoInitialize()
    app = application_of(main) if main else None
    if app is not None:
        try:
            report["workbooks"] = [wb.Name for wb in app.Workbooks]
            report["window_captions"] = [w.Caption for w in app.Windows]
            report["dirty_after_open"] = [not wb.Saved for wb in app.Workbooks]
            for wb in list(app.Workbooks):
                wb.Close(SaveChanges=False)
            app.DisplayAlerts = False
            app.Quit()
        except Exception as exc:  # noqa: BLE001
            report["close_trouble"] = str(exc)
        del app
    else:
        report["attached"] = False
        if main:
            win32gui.PostMessage(main, win32con.WM_CLOSE, 0, 0)
    try:
        proc.wait(20)
        report["exited"] = True
    except subprocess.TimeoutExpired:
        report["exited"] = False
        log("STILL RUNNING", pid, [(win32gui.GetClassName(h), win32gui.GetWindowText(h)) for h in windows_of(pid)])
        for h in windows_of(pid):
            shoot_rect(h, f"user-open-stuck-{tag}-{h}.png")
    report["repaired"] = bool([d for d in watcher.seen]) or bool(report["new_error_logs"]) or "Repaired" in caption
    log("user-open", json.dumps(report, default=str))
    return report


if __name__ == "__main__":
    out = {}
    paths = sys.argv[1:]
    if not paths:                  # export_checks.py's files, as Export wrote them, before Excel saw them
        pristine = os.path.join(ROOT, "export", "pristine")
        names = ["control-etree.xlsx", "control-bad-string.xlsx", "export-shift.xlsx", "export-move.xlsx",
                 "export-as (fixed).xlsx", "Gearbox.xlsx", "export-add-column.xlsx", "export-calcpr-inserted.xlsx"]
        paths = [os.path.join(pristine, n) for n in names]
    for path in paths:
        tag = os.path.splitext(os.path.basename(path))[0].replace(" ", "_")
        out[path] = one(path, tag)
    with open(os.path.join(ROOT, "user_open.json"), "w", encoding="utf-8") as h:
        json.dump(out, h, indent=1, default=str, ensure_ascii=False)
