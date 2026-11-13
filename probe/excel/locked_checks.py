r"""Check 3 (drives real Excel through COM): the workbook held open in Excel.

With a copy of the fixture open in Excel: whether the ~$ lock file appears, whether xlsx.read and
Link.read still read it, that Export refuses with the plan's sentence (and what the replace itself meets
with the lock-file check bypassed), and that Export as… still writes. Then the live link's timing: Excel
saves the file 10 times while poller.py runs Link.poll every 1 s (the window's poll), then 15 times at a
20 ms poll to catch the mid-save gap. Writes <scratch>\locked_checks.json and poll-*.jsonl.
"""

import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xlhelp import FIXTURE, HERE, ROOT, Excel, Watcher, log  # noqa: E402

from gear_generator.workbook import checks, export, fixes, link as wb_link, model, xlsx  # noqa: E402

OUT = os.path.join(ROOT, "locked")
if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
path = os.path.join(OUT, "Reducer_12to1.xlsx")
shutil.copy(FIXTURE, path)
res = {}

xl = Excel(visible=True)
try:
    res["lock before open"] = os.path.exists(xlsx.lock_file(path))
    wb, rep = xl.open(path, "locked")
    session = Watcher(xl.pid, "locked-session", xl.hwnd)
    session.start()
    time.sleep(1)
    res["lock file"] = [xlsx.lock_file(path), os.path.exists(xlsx.lock_file(path))]
    res["folder while open"] = sorted(os.listdir(OUT))
    try:
        book = xlsx.read(path)
        spec, diags = model.from_book(book)
        res["xlsx.read while open"] = {"ok": True, "S2 x": spec.shaft("S2").x, "diagnostics": len(diags)}
    except Exception as exc:  # noqa: BLE001
        res["xlsx.read while open"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    lk = wb_link.Link(path)
    try:
        reading = lk.read()
        res["Link.read while open"] = {"ok": reading.ok, "error": reading.error, "open_in_excel": lk.open_in_excel}
    except Exception as exc:  # noqa: BLE001
        res["Link.read while open"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # Export into the open file: the S2 = 64 case typed in Excel and saved, then a fix exported.
    wb.Worksheets("Shafts").Range("C3").Value = 64
    wb.Save()
    spec, _ = model.from_book(xlsx.read(path))
    report = checks.check(spec)
    move, shift = report.fixes["Meshes!A2"]
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    before = open(path, "rb").read()
    try:
        export.export(path, spec, [shift], checks.check(fixes.apply(spec, shift)), expected_digest=digest)
        res["Export while open"] = {"refused": False}
    except xlsx.XlsxError as exc:
        res["Export while open"] = {"refused": True, "class": type(exc).__name__, "sentence": str(exc),
                                    "file untouched": open(path, "rb").read() == before}
    # And with the lock file hidden from the check, to see what the replace itself meets on Windows.
    real = xlsx.is_open_in_excel
    xlsx.is_open_in_excel = lambda p: False
    try:
        export.export(path, spec, [shift], checks.check(fixes.apply(spec, shift)), expected_digest=digest)
        res["Export while open, lock file ignored"] = {"refused": False,
                                                       "file changed": open(path, "rb").read() != before}
    except Exception as exc:  # noqa: BLE001
        res["Export while open, lock file ignored"] = {"refused": True, "class": type(exc).__name__,
                                                       "sentence": str(exc),
                                                       "file untouched": open(path, "rb").read() == before,
                                                       "temp files left": [n for n in os.listdir(OUT)
                                                                           if n.startswith(".~gear-")]}
    finally:
        xlsx.is_open_in_excel = real
    out = os.path.join(OUT, "Reducer_12to1 (fixed).xlsx")
    done = export.export(path, spec, [shift], checks.check(fixes.apply(spec, shift)), out_path=out,
                         expected_digest=digest)
    res["Export as while open"] = {"written": done.written, "results": done.results, "exists": os.path.exists(out)}

    # The live link's timing: a 1 s poll (the window's), then a 20 ms poll to catch mid-save states.
    for label, interval, saves in (("poll 1s", 1.0, 10), ("poll 20ms", 0.02, 15)):
        logfile = os.path.join(ROOT, f"poll-{label.replace(' ', '')}.jsonl")
        span = saves * 4.5 + 6
        poller = subprocess.Popen([sys.executable, os.path.join(HERE, "poller.py"), path, str(interval), logfile,
                                   str(span)])
        time.sleep(3)
        marks = []
        for i in range(saves):
            value = 63.75 if i % 2 == 0 else 64
            wb.Worksheets("Shafts").Range("C3").Value = value
            t0 = time.time()
            try:
                wb.Save()
            except Exception as exc:  # noqa: BLE001
                log("SAVE FAILED", i, exc)
                res.setdefault("save failures", []).append([label, i, str(exc)])
            t1 = time.time()
            marks.append({"i": i, "value": value, "save_start": t0, "save_end": t1})
            time.sleep(3 + random.random())
        poller.wait(span + 30)
        events = [json.loads(line) for line in open(logfile, encoding="utf-8")]
        rows = []
        for m in marks:
            hit = next((e for e in events if e["kind"] == "reading" and e["t"] >= m["save_start"]), None)
            notready = [e for e in events if e["kind"] in ("notready", "absent")
                        and m["save_start"] - 0.5 <= e["t"] <= (hit["t"] if hit else m["save_end"] + 6)]
            rows.append({"i": m["i"], "save took": round(m["save_end"] - m["save_start"], 3),
                         "seen after save end": round(hit["t"] - m["save_end"], 3) if hit else None,
                         "seen after save start": round(hit["t"] - m["save_start"], 3) if hit else None,
                         "changes": hit["changes"] if hit else None, "error": hit["error"] if hit else None,
                         "not ready on the way": [e.get("why", e["kind"]) for e in notready]})
        res[label] = rows
        res[label + " other events"] = [e for e in events if e["kind"] not in ("reading", "first", "end")]
        log(label, json.dumps(rows))
    session.stop.set()
    session.join()
    res["dialogs while open"] = session.seen
    wb.Close(SaveChanges=False)
    del wb
    time.sleep(1)
    res["lock after close"] = os.path.exists(xlsx.lock_file(path))
finally:
    xl.quit()

with open(os.path.join(ROOT, "locked_checks.json"), "w", encoding="utf-8") as h:
    json.dump(res, h, indent=1, default=str, ensure_ascii=False)
log("wrote locked_checks.json")
