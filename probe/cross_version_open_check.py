r"""A gearbox saved by one SolidWorks, opened in another: does every document read GetSaveFlag False straight after?

python.exe probe/cross_version_open_check.py <repo src> <assembly path> --pid PID [--log FILE]

The W4 pass-4 review carried this forward: the app clears an unsaved mark on a document it opened from its file
only when ``GetSaveFlag`` reads False (``swbuild._note_opened``), and a file saved by an older release, opened in
a newer one, might read True as SolidWorks converts it in memory. So the assembly is opened with the app's own
``Session.open_document`` (OpenDoc6, then ActivateDoc3) and nothing else is called before every document under its
folder is asked for ``GetSaveFlag``; then each document's ``IModelDocExtension.GetVersionHistory`` is logged as a
fact line, if it answers. Nothing is saved: the documents this run opened are closed with ``QuitDoc`` (on 2026 it
closed modified documents without a dialog, W4-RERUN-2026), assembly first, and the files' sha256 and mtime are
compared before and after. Refuses unless the session attached is the PID given; documents open before the run
are left alone and logged as ``<user document N>``.
"""

import hashlib
import os
import sys
import time

sys.path.insert(0, sys.argv[1])
ASM = sys.argv[2]
PID = int(sys.argv[sys.argv.index("--pid") + 1])
LOG_PATH = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(os.path.dirname(ASM),
                                                                                       "cross-version-open.log")
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from gear_generator import __version__, swcom  # noqa: E402
from gear_generator.swcom import call  # noqa: E402

LOG, FAILS = [], []
FOLDER = os.path.dirname(os.path.abspath(ASM))


def say(line=""):
    print(line, flush=True)
    LOG.append(line)


def check(ok, what):
    say(("ok      " if ok else "FAIL    ") + what)
    if not ok:
        FAILS.append(what)
    return ok


def documents(app):
    out, doc = [], call(app, "GetFirstDocument")
    while doc is not None:
        out.append(doc)
        doc = call(doc, "GetNext")
    return out


def ours(path):
    return bool(path) and os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(FOLDER))


def stamps():
    out = {}
    for name in sorted(os.listdir(FOLDER)):
        if name.lower().endswith((".sldprt", ".sldasm")):
            path = os.path.join(FOLDER, name)
            with open(path, "rb") as handle:
                out[name] = (hashlib.sha256(handle.read()).hexdigest(), os.path.getmtime(path))
    return out


def work(session):
    users = {}
    before = []
    for doc in documents(session._app):  # noqa: SLF001
        path = str(call(doc, "GetPathName") or "")
        before.append(str(call(doc, "GetTitle")) if ours(path) else users.setdefault(path, f"<user document {len(users) + 1}>"))
    say(f"open    before: {before}")
    check(not any(ours(str(call(d, "GetPathName") or "")) for d in documents(session._app)),  # noqa: SLF001
          "none of the gearbox's documents is open before the run")
    session.begin_build()
    try:
        info = session.open_document(ASM)
    finally:
        session.end_build()
    say(f"opened  {info.title} ({info.path}) by the app's open_document")
    flags = {}
    for doc in documents(session._app):  # noqa: SLF001
        path = str(call(doc, "GetPathName") or "")
        if ours(path):
            flags[os.path.basename(path)] = bool(call(doc, "GetSaveFlag"))
    say(f"flags   GetSaveFlag straight after the open: {flags}")
    check(bool(flags) and not any(flags.values()),
          f"every document of a gearbox saved by another release reads GetSaveFlag False straight after the open: "
          f"marked {[n for n, f in flags.items() if f]}")
    for doc in documents(session._app):  # noqa: SLF001
        path = str(call(doc, "GetPathName") or "")
        if ours(path):
            try:
                history = list(call(call(doc, "Extension"), "GetVersionHistory") or ())
            except Exception as exc:  # noqa: BLE001 - evidence only
                history = [f"raised {exc}"]
            say(f"fact    {os.path.basename(path)} version history: {history}")

    for kind in (swcom.DOC_ASSEMBLY, swcom.DOC_PART):
        for doc in documents(session._app):  # noqa: SLF001
            path = str(call(doc, "GetPathName") or "")
            if ours(path) and int(call(doc, "GetType")) == kind:
                call(session._app, "QuitDoc", str(call(doc, "GetTitle")))  # noqa: SLF001
    left = [str(call(d, "GetTitle")) for d in documents(session._app) if ours(str(call(d, "GetPathName") or ""))]  # noqa: SLF001
    return flags, left


def main():
    say(f"run     {time.strftime('%Y-%m-%d %H:%M:%S')}; app gear-generator {__version__}; assembly {ASM}")
    found = [c for c in swcom.find_candidates() if c.pid == PID]
    if not found:
        say(f"STOP    no SolidWorks session with PID {PID} is reachable")
        return 2
    worker = swcom.Worker(lambda: swcom.Session(found[0].app, found[0].revision, found[0].pid))
    try:
        (label, pid), error = worker.submit(lambda s: (s.label, s.pid)).wait(timeout=120)
        if error is not None:
            raise error
        say(f"attach  {label}, PID {pid}")
        disk_before = stamps()
        (flags, left), error = worker.submit(work).wait(timeout=600)
        if error is not None:
            raise error
        check(not left, f"closed without saving (QuitDoc): left {left}")
        disk_after = stamps()
        check(disk_before == disk_after, f"no file of the gearbox changed on disk ({len(disk_before)} files, sha256 "
                                         "and mtime)")
    finally:
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
