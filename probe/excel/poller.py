r"""The live link, headless: Link.poll every <interval> s, as the window's _tick does, logging each event
(each reading with its change list, each mid-save NotReady) to a JSON-lines file. Used by locked_checks.py.

usage: python poller.py <workbook> <interval> <log.jsonl> <seconds>
"""

import json
import os
import sys
import time

sys.path.insert(0, os.environ.get("GG_SRC")
                or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from gear_generator.workbook import link as wb_link, xlsx  # noqa: E402

path, interval, out, seconds = sys.argv[1], float(sys.argv[2]), sys.argv[3], float(sys.argv[4])
lk = wb_link.Link(path)
log = open(out, "w", encoding="utf-8")


def emit(**kw):
    kw["t"] = time.time()
    log.write(json.dumps(kw, ensure_ascii=False) + "\n")
    log.flush()


real_read = lk.read


def read():
    try:
        return real_read()
    except xlsx.NotReady as exc:
        emit(kind="notready", why=str(exc))
        raise
    except Exception as exc:  # noqa: BLE001
        emit(kind="raise", why=f"{type(exc).__name__}: {exc}")
        raise


lk.read = read
first = lk.read()
emit(kind="first", ok=first.ok, error=first.error)
end = time.time() + seconds
while time.time() < end:
    stamp = lk._stat()
    try:
        reading = lk.poll()
    except Exception as exc:  # noqa: BLE001
        emit(kind="poll-raise", why=f"{type(exc).__name__}: {exc}")
        reading = None
    if reading is not None:
        emit(kind="reading", ok=reading.ok, error=reading.error, changes=reading.changes, stamp=stamp)
    elif stamp is None:
        emit(kind="absent")
    time.sleep(interval)
emit(kind="end")
