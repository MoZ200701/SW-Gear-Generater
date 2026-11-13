r"""Shared by the Excel checks in probe/excel: a private Excel driven by COM, with a dialog watcher.

These scripts drive REAL Microsoft Excel on Windows (and run_all.sh's tk_driver.py, the real Tk window).
They are not tests: run them with the Windows Python beside Excel (pywin32, Pillow), from WSL through
run_all.sh. Every Excel they use is one they start (DispatchEx, or EXCEL.EXE /x), and only that one is
closed or quit. Every workbook Excel opens is a copy under the scratch folder (GG_EXCEL_SCRATCH, default
%USERPROFILE%\Documents\GearGeneratorProbe\excel-checks), never a file in the repo.

The watcher lists every visible top-level window the Excel process owns other than its main window,
records its class, title and child texts, screenshots it into the scratch folder, and closes a dialog with
WM_CLOSE (Cancel / No), so a modal dialog is reported instead of hanging the run.
"""

import ctypes
import glob
import json
import os
import sys
import threading
import time

ctypes.windll.shcore.SetProcessDpiAwareness(2)

import pythoncom
import win32api
import win32con
import win32gui
import win32process
import win32com.client
from PIL import ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # probe/excel -> the repo, read through \\wsl.localhost
SRC = os.environ.get("GG_SRC") or os.path.join(REPO, "src")   # run_all.sh: a snapshot of HEAD
if SRC not in sys.path:
    sys.path.insert(0, SRC)
FIXTURE = os.path.join(REPO, "tests", "fixtures", "excel-windows", "Reducer_12to1.xlsx")
# Scratch: every file Excel opens is a copy under here, never a file in the repo.
ROOT = os.environ.get("GG_EXCEL_SCRATCH") or os.path.join(
    os.environ["USERPROFILE"], "Documents", "GearGeneratorProbe", "excel-checks")
os.makedirs(ROOT, exist_ok=True)
SHOTS = os.path.join(ROOT, "shots")
os.makedirs(SHOTS, exist_ok=True)
TEMP = os.environ.get("TEMP", "")


def log(*args):
    print(time.strftime("%H:%M:%S"), *args, flush=True)


def windows_of(pid):
    out = []

    def each(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        _, owner = win32process.GetWindowThreadProcessId(hwnd)
        if owner == pid:
            out.append(hwnd)
        return True

    win32gui.EnumWindows(each, None)
    return out


def child_texts(hwnd):
    texts = []

    def each(child, _):
        t = win32gui.GetWindowText(child)
        if t:
            texts.append(t)
        return True

    try:
        win32gui.EnumChildWindows(hwnd, each, None)
    except win32gui.error:
        pass
    return texts


def shoot_rect(hwnd, name):
    try:
        rect = win32gui.GetWindowRect(hwnd)
        img = ImageGrab.grab(bbox=rect, all_screens=True)
        path = os.path.join(SHOTS, name)
        img.save(path)
        return path
    except Exception as exc:  # noqa: BLE001
        return f"(screenshot failed: {exc})"


DIALOG_CLASSES = {"#32770", "NUIDialog", "bosa_sdm_XL9", "bosa_sdm_Microsoft Office Excel 11.0"}


class Watcher(threading.Thread):
    """Records and closes any dialog the Excel process shows."""

    IGNORE_CLASSES = {"XLMAIN", "MsoCommandBar", "EXCEL7", "XLDESK", "_WwB", "MsoSplash",
                      "Net UI Tool Window", "Net UI Tool Window Layered", "MSO_BORDEREFFECT_WINDOW_CLASS",
                      "MsoWorkPane", "NUIPane"}

    def __init__(self, pid, tag, main_hwnd):
        super().__init__(daemon=True)
        self.pid, self.tag, self.main = pid, tag, main_hwnd
        self.seen = []
        self.stop = threading.Event()
        self.close_dialogs = True

    def run(self):
        handled = set()
        while not self.stop.is_set():
            for hwnd in windows_of(self.pid):
                if hwnd == self.main or hwnd in handled:
                    continue
                cls = win32gui.GetClassName(hwnd)
                if cls in self.IGNORE_CLASSES:
                    continue
                title = win32gui.GetWindowText(hwnd)
                rect = win32gui.GetWindowRect(hwnd)
                if rect[2] - rect[0] < 40 or rect[3] - rect[1] < 30:
                    continue
                time.sleep(0.4)          # let it paint
                shot = shoot_rect(hwnd, f"dialog-{self.tag}-{len(self.seen)}.png")
                entry = {"class": cls, "title": title, "texts": child_texts(hwnd), "rect": rect, "shot": shot,
                         "at": time.time()}
                self.seen.append(entry)
                log("DIALOG", json.dumps(entry))
                handled.add(hwnd)
                if self.close_dialogs and cls in DIALOG_CLASSES:
                    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            time.sleep(0.2)


class Excel:
    def __init__(self, visible=True):
        pythoncom.CoInitialize()
        self.app = win32com.client.DispatchEx("Excel.Application")
        self.app.Visible = visible
        self.app.DisplayAlerts = True
        self.hwnd = self.app.Hwnd
        _, self.pid = win32process.GetWindowThreadProcessId(self.hwnd)
        self.version = f"{self.app.Version} build {self.app.Build}"
        log("excel started", self.pid, self.version)

    def error_logs(self):
        return set(glob.glob(os.path.join(TEMP, "error*.xml")))

    def open(self, path, tag, timeout=60):
        """Open ``path``; returns (workbook or None, report dict). Dialogs are recorded and closed."""
        before = self.error_logs()
        watcher = Watcher(self.pid, tag, self.hwnd)
        watcher.start()
        killer = threading.Timer(timeout, self._stuck, args=(tag,))
        killer.start()
        report = {"path": path, "tag": tag}
        wb = None
        t0 = time.time()
        try:
            wb = self.app.Workbooks.Open(Filename=path, UpdateLinks=0, AddToMru=False)
            report["opened"] = True
        except pythoncom.com_error as exc:
            report["opened"] = False
            report["error"] = str(exc)
        finally:
            killer.cancel()
        report["seconds"] = round(time.time() - t0, 2)
        time.sleep(1.5)                     # a post-repair summary dialog comes after Open returns
        watcher.stop.set()
        watcher.join()
        report["dialogs"] = watcher.seen
        report["new_error_logs"] = sorted(self.error_logs() - before)
        logs = {}
        for p in report["new_error_logs"]:
            try:
                logs[p] = open(p, encoding="utf-8", errors="replace").read()
            except OSError as exc:
                logs[p] = str(exc)
        report["error_log_text"] = logs
        if wb is not None:
            report["caption"] = win32gui.GetWindowText(self.hwnd)
            report["window_caption"] = self.app.ActiveWindow.Caption if self.app.ActiveWindow else ""
            report["name"] = wb.Name
        report["repaired"] = bool(watcher.seen) or bool(report["new_error_logs"]) or \
            "Repaired" in report.get("caption", "") or "Repaired" in report.get("window_caption", "")
        log("open", tag, json.dumps({k: v for k, v in report.items() if k != "error_log_text"}))
        return wb, report

    def _stuck(self, tag):
        log("STUCK", tag, "windows:", [(win32gui.GetClassName(h), win32gui.GetWindowText(h))
                                       for h in windows_of(self.pid)])
        for h in windows_of(self.pid):
            if h != self.hwnd:
                shoot_rect(h, f"stuck-{tag}-{h}.png")
                win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)

    def quit(self):
        try:
            for wb in list(self.app.Workbooks):
                wb.Close(SaveChanges=False)
        except Exception as exc:  # noqa: BLE001
            log("close-all trouble", exc)
        try:
            self.app.DisplayAlerts = False
            self.app.Quit()
        except Exception as exc:  # noqa: BLE001
            log("quit trouble", exc)
        self.app = None
        pythoncom.CoUninitialize()
        import win32event
        try:
            handle = win32api.OpenProcess(0x00100000 | 0x1000, False, self.pid)   # SYNCHRONIZE | QUERY_LIMITED
        except win32api.error:
            log("excel gone", self.pid)
            return
        gone = win32event.WaitForSingleObject(handle, 15000) == win32event.WAIT_OBJECT_0
        win32api.CloseHandle(handle)
        if gone:
            log("excel gone", self.pid)
            return
        log("excel still running after quit; killing our own pid", self.pid)
        os.system(f"taskkill /PID {self.pid} /F")
