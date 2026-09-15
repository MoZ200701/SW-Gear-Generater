"""``python -m gear_generator.probe`` — verify the SolidWorks API before relying on it.

Attaches to the running SolidWorks (never launches one), runs the registered
probes in order on scratch documents it makes and closes itself, prints a line
per assertion, and writes the results. Nothing the user has open is touched: the
set of open documents is checked at the end, and a mismatch is reported as
CLEANUP with exit code 6.

Exit codes: 0 every probe passed, 1 findings (something failed or was
skipped), 2–5 as ``python -m gear_generator.swcom``, 6 cleanup failed, 7 a
probe hung.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

from .. import swcom
from . import decide, harness, report
from .harness import HUNG, PASS, Px, Record

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CLEANUP = 6
EXIT_HUNG = 7


def load_probes() -> None:
    """Import every probe module, which registers its probes in order."""
    from . import p0_session, p1_equations, p1_sketch, p1_curves, p2_solid, p2_helical, p2_internal, p2_bevel  # noqa: F401
    from . import p3_files, p4_assembly, p4_interference, p4_nonparallel, p5_end_to_end, p5_helical  # noqa: F401
    from . import p5_internal, p5_bevel  # noqa: F401


def default_scratch() -> str:
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return os.path.join(home, "Documents", "GearGeneratorProbe", time.strftime("%Y%m%d-%H%M%S"))


def parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m gear_generator.probe", description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", default=[], help="run this probe (and what it needs); repeatable")
    parser.add_argument("--tier", type=int, default=None, help="run tiers up to and including this one")
    parser.add_argument("--extras", action="store_true", help="include the probes marked extra")
    parser.add_argument("--keep", action="store_true", help="leave scratch documents open")
    parser.add_argument("--flank", choices=("A", "B"), default=None, help="force the end-to-end recipe")
    parser.add_argument("--timeout", type=float, default=120.0, help="seconds per probe before it counts as hung")
    parser.add_argument("--scratch", default="", help="folder for files the probes save (under C:\\)")
    parser.add_argument("--out", default="", help="where the results are written")
    parser.add_argument("--ledger", action="store_true", help="print API-LEDGER rows for what ran")
    parser.add_argument("--list", action="store_true", help="list the probes and exit")
    return parser.parse_args(list(argv))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # a Windows console is cp1252, and the report is not
        except (AttributeError, ValueError):
            pass
    load_probes()
    if args.list:
        for p in harness.REGISTRY:
            extra = " (extra)" if p.extra else ""
            needs = f" needs {', '.join(p.needs)}" if p.needs else ""
            print(f"tier {p.tier}  {p.name}{extra}{needs}")
        return EXIT_OK

    try:
        probes = harness.select(harness.REGISTRY, args.only, args.tier, args.extras)
    except KeyError as exc:
        print(f"FAIL    {exc.args[0]}")
        return EXIT_FINDINGS

    if not swcom.is_available():
        print(f"pywin32 is not usable here: {swcom.unavailable_reason()}")
        return swcom.EXIT_NOT_AVAILABLE

    worker = swcom.Worker()
    try:
        session = worker.submit(lambda s: (s.label, s.revision, s.pid)).wait(timeout=60)
    except Exception as exc:  # noqa: BLE001 - queue.Empty or a wait problem
        print(f"HUNG    attaching to SolidWorks: {exc}")
        return EXIT_HUNG
    value, error = session
    if error is not None:
        print(f"FAIL    attach: {error}")
        if isinstance(error, swcom.NotRunning):
            return swcom.EXIT_NOT_RUNNING
        if isinstance(error, swcom.WrongVersion):
            return swcom.EXIT_WRONG_VERSION
        return swcom.EXIT_COM_ERROR
    label, revision, pid = value
    print(f"attach  {label}, PID {pid}")

    scratch = args.scratch or default_scratch()
    shared: Dict[str, Any] = {"created": []}
    options = {"keep": args.keep, "flank": args.flank, "scratch": scratch}

    from . import scaffold  # noqa: PLC0415 - COM helpers, only once attached

    before_titles = worker.submit(lambda s: scaffold.open_titles(Px(Record("", 0), s))).wait(timeout=60)[0] or []

    def make_px(record: Record) -> Px:
        # The session is the worker's own; the probe body only ever runs there.
        return Px(record, session=_SessionProxy(worker), shared=shared, options=options)

    lines: List[str] = [f"attach  {label}, PID {pid}", f"scratch {scratch}"]

    def on_record(record: Record) -> None:
        for line in report.record_lines(record):
            print(line, flush=True)
            lines.append(line)

    records = harness.run(probes, make_px, harness.worker_executor(worker), args.timeout, label, on_record)

    exit_code = EXIT_OK
    if any(r.status == HUNG for r in records):
        exit_code = EXIT_HUNG
    else:
        after = worker.submit(lambda s: scaffold.open_titles(Px(Record("", 0), s))).wait(timeout=60)[0] or []
        stray = [t for t in after if t not in before_titles and not args.keep]
        lost = [t for t in before_titles if t not in after]
        if stray or lost:
            line = f"CLEANUP left open: {stray}; closed that were open before: {lost}"
            print(line)
            lines.append(line)
            exit_code = EXIT_CLEANUP
        elif any(r.status != PASS for r in records):
            exit_code = EXIT_FINDINGS

    decisions = decide.decide({r.name: r.to_dict() for r in records})
    for key, val in decisions.items():
        line = f"decide  {key} = {val}"
        print(line)
        lines.append(line)
    lines.append(report.summary_line(records))
    print(report.summary_line(records))

    if args.out:
        meta = {
            "stamp": time.strftime("%Y%m%d-%H%M%S"),
            "version": label,
            "revision": ".".join(str(n) for n in revision),
            "argv": list(sys.argv[1:] if argv is None else argv),
            "exit_code": exit_code,
        }
        paths = report.write(args.out, records, meta, decisions, lines)
        print(f"wrote   {paths['text']}")
        print(f"wrote   {paths['latest']}")
    if args.ledger:
        for row in report.ledger_rows(records, label):
            print(row)
    worker.shutdown()
    return exit_code


class _SessionProxy:
    """Stands in for the worker's session inside a probe body.

    The body runs on the worker thread, where the real session lives; this
    only reaches for it at call time so no COM pointer is ever held elsewhere.
    """

    def __init__(self, worker: swcom.Worker) -> None:
        self._worker = worker

    def __getattr__(self, name: str) -> Any:
        return getattr(self._worker._session, name)  # noqa: SLF001


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
