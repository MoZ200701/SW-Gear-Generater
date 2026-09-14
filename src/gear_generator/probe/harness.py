"""The probe harness: a registry of probes, run in order, each on a leash.

A probe is a function taking a :class:`Px` — the context it asserts through —
registered with ``@probe(name, needs=..., members=..., tier=...)``. The harness
runs the registry in order and:

* **skips** a probe whose ``needs`` did not pass, and says which one, so a
  failure early on shows up once rather than as a cascade of confusing ones;
* runs each probe as **one worker job with a timeout**. A modal dialog in
  SolidWorks blocks a COM call for as long as it stays open and nothing can
  cancel it, so a hung probe costs that probe and every later one is reported
  as not run — never the report itself;
* records every assertion, fact and error as plain data, with the SolidWorks
  version on every record so an entry written from it can say what it ran on.

How a probe is executed is injected, which is what lets the ordering and the
skip cascade be tested on Linux with fake probes and no COM at all.
"""

from __future__ import annotations

import queue
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .comerr import describe_error, one_line

PASS = "pass"
FAIL = "fail"
SKIP = "skip"
HUNG = "hung"
NOT_RUN = "not run"


class Require(Exception):
    """A probe cannot go on: the thing it needs to continue did not happen."""


@dataclass(frozen=True)
class Probe:
    name: str
    fn: Callable[["Px"], None]
    needs: Tuple[str, ...] = ()
    members: Tuple[str, ...] = ()
    tier: int = 0
    extra: bool = False
    doc: str = ""


@dataclass
class Line:
    """One assertion or fact. ``level`` is ok, fail, fact, attempt or note."""

    level: str
    text: str
    detail: Any = None


@dataclass
class Record:
    name: str
    tier: int
    status: str = NOT_RUN
    members: List[str] = field(default_factory=list)
    lines: List[Line] = field(default_factory=list)
    facts: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Dict[str, Any]] = None
    seconds: float = 0.0
    version: str = ""
    reason: str = ""

    @property
    def failures(self) -> List[Line]:
        return [line for line in self.lines if line.level == FAIL]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


REGISTRY: List[Probe] = []


def probe(name: str, needs: Sequence[str] = (), members: Sequence[str] = (), tier: int = 0,
          extra: bool = False) -> Callable[[Callable[["Px"], None]], Callable[["Px"], None]]:
    """Register a probe. Order of registration is order of running."""

    def register(fn: Callable[["Px"], None]) -> Callable[["Px"], None]:
        if any(existing.name == name for existing in REGISTRY):
            raise ValueError(f"A probe called {name!r} is already registered.")
        REGISTRY.append(Probe(name, fn, tuple(needs), tuple(members), tier, extra, (fn.__doc__ or "").strip()))
        return fn

    return register


class Px:
    """What a probe asserts through. COM-free itself; the COM lives in ``session``."""

    def __init__(self, record: Record, session: Any = None, shared: Optional[Dict[str, Any]] = None,
                 options: Optional[Dict[str, Any]] = None) -> None:
        self.record = record
        self.session = session
        self.shared = shared if shared is not None else {}
        self.options = options or {}

    # -- saying things ---------------------------------------------------

    def ok(self, text: str, detail: Any = None) -> None:
        self.record.lines.append(Line("ok", text, detail))

    def fail(self, text: str, detail: Any = None) -> None:
        self.record.lines.append(Line(FAIL, text, detail))

    def note(self, text: str, detail: Any = None) -> None:
        self.record.lines.append(Line("note", text, detail))

    def fact(self, key: str, value: Any, text: str = "") -> Any:
        """Record something observed that a decision will read."""
        self.record.facts[key] = value
        self.record.lines.append(Line("fact", text or f"{key} = {value!r}", value))
        return value

    def check(self, condition: bool, text: str, detail: Any = None) -> bool:
        (self.ok if condition else self.fail)(text, detail)
        return bool(condition)

    def require(self, condition: bool, text: str, detail: Any = None) -> None:
        """Like check, but a failure ends the probe."""
        if not self.check(condition, text, detail):
            raise Require(text)

    def attempt(self, label: str, fn: Callable[[], Any], expect_error: bool = False) -> Tuple[bool, Any]:
        """Call something that may raise; record either outcome as a fact.

        Returns ``(succeeded, value_or_error_dict)``. Nothing is swallowed
        silently: a raise becomes a line carrying the HRESULT and argerror.
        """
        try:
            value = fn()
        except Require:
            raise
        except Exception as exc:  # noqa: BLE001 - recording the failure is the point
            info = describe_error(exc)
            self.record.lines.append(Line("attempt", f"{label}: raised {one_line(exc)}", info))
            self.record.facts[f"attempt:{label}"] = {"ok": False, "error": info}
            return False, info
        shown = value if isinstance(value, (bool, int, float, str, type(None))) else type(value).__name__
        self.record.lines.append(Line("attempt", f"{label}: returned {shown!r}", shown))
        self.record.facts[f"attempt:{label}"] = {"ok": True, "value": shown}
        return True, value


# -- execution --------------------------------------------------------------

Executor = Callable[[Callable[[], None], float], Tuple[bool, Optional[BaseException]]]
"""Runs one probe body with a timeout. Returns ``(finished, error)``."""


def inline_executor(body: Callable[[], None], timeout: float) -> Tuple[bool, Optional[BaseException]]:
    """Run on this thread with no timeout: for tests, and never for COM."""
    try:
        body()
    except BaseException as exc:  # noqa: BLE001
        return True, exc
    return True, None


def worker_executor(worker: Any) -> Executor:
    """Run each probe as one job on the COM worker thread, with a timeout."""

    def execute(body: Callable[[], None], timeout: float) -> Tuple[bool, Optional[BaseException]]:
        call = worker.submit(lambda _session: body())
        try:
            _value, error = call.wait(timeout=timeout)
        except queue.Empty:
            return False, None
        return True, error

    return execute


def select(registry: Sequence[Probe], only: Sequence[str] = (), tier: Optional[int] = None,
           extras: bool = False) -> List[Probe]:
    """The probes to run, in registry order, pulling in what ``only`` needs."""
    by_name = {p.name: p for p in registry}
    for name in only:
        if name not in by_name:
            raise KeyError(f"There is no probe called {name!r}.")
    wanted = set()

    def want(name: str) -> None:
        if name in wanted:
            return
        wanted.add(name)
        for need in by_name[name].needs:
            if need in by_name:
                want(need)

    if only:
        for name in only:
            want(name)
    else:
        for p in registry:
            if (tier is None or p.tier <= tier) and (extras or not p.extra):
                want(p.name)
    return [p for p in registry if p.name in wanted]


def run(probes: Sequence[Probe], make_px: Callable[[Record], Px], execute: Executor = inline_executor,
        timeout: float = 120.0, version: str = "",
        on_record: Optional[Callable[[Record], None]] = None) -> List[Record]:
    """Run probes in order. A hang stops the run; everything after it is not run."""
    records: List[Record] = []
    status: Dict[str, str] = {}
    hung = False
    for p in probes:
        record = Record(name=p.name, tier=p.tier, members=list(p.members), version=version)
        records.append(record)
        if hung:
            record.status = NOT_RUN
            record.reason = "the worker is still stuck in an earlier probe"
        else:
            missing = [need for need in p.needs if status.get(need) != PASS]
            if missing:
                record.status = SKIP
                record.reason = "needs " + ", ".join(
                    f"{need} ({status.get(need, NOT_RUN)})" for need in missing
                )
            else:
                px = make_px(record)
                started = time.monotonic()
                finished, error = execute(lambda: p.fn(px), timeout)
                record.seconds = round(time.monotonic() - started, 3)
                if not finished:
                    record.status = HUNG
                    record.reason = f"no answer in {timeout:g} s; a dialog may be open in SolidWorks"
                    hung = True
                elif error is not None:
                    record.status = FAIL
                    if not isinstance(error, Require):
                        record.error = describe_error(error)
                        record.error["traceback"] = "".join(
                            traceback.format_exception(type(error), error, error.__traceback__)
                        )[-2000:]
                        record.lines.append(Line(FAIL, f"raised {one_line(error)}", record.error))
                    record.reason = str(error)
                else:
                    record.status = FAIL if record.failures else PASS
        status[p.name] = record.status
        if on_record is not None:
            on_record(record)
    return records


def by_name(records: Iterable[Record]) -> Dict[str, Record]:
    return {r.name: r for r in records}
