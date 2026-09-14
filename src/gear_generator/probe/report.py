"""Printing probe results and writing them down.

One line per assertion, in the idiom the SW-Macro-Database uses: lowercase for
what went as expected, UPPERCASE for what a person has to look at. Every run
writes ``probe-results-<stamp>.txt`` and ``.json`` and overwrites
``latest.json``, which is the committed evidence the tool's findings are
checked against.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List, Sequence

from .harness import FAIL, HUNG, NOT_RUN, PASS, SKIP, Record

SCHEMA = 1

TOKENS = {
    "ok": "  ok     ",
    FAIL: "  FAIL   ",
    "fact": "  fact   ",
    "attempt": "  try    ",
    "note": "  note   ",
}
STATUS_TOKENS = {PASS: "pass", FAIL: "FAIL", SKIP: "SKIP", HUNG: "HUNG", NOT_RUN: "NOT RUN"}


def record_lines(record: Record) -> List[str]:
    head = f"{STATUS_TOKENS.get(record.status, record.status.upper()):<7} {record.name}"
    if record.seconds:
        head += f"  ({record.seconds:.1f} s)"
    if record.reason and record.status != PASS:
        head += f" — {record.reason}"
    lines = [head]
    for line in record.lines:
        lines.append(TOKENS.get(line.level, "  " + line.level.ljust(7)) + line.text)
    return lines


def summary(records: Sequence[Record]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    return counts


def summary_line(records: Sequence[Record]) -> str:
    counts = summary(records)
    order = (PASS, FAIL, SKIP, HUNG, NOT_RUN)
    return "done    " + ", ".join(f"{counts[s]} {STATUS_TOKENS[s]}" for s in order if counts.get(s))


def to_payload(records: Sequence[Record], meta: Dict[str, Any], decisions: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "meta": meta,
        "summary": summary(records),
        "decisions": decisions,
        "records": [r.to_dict() for r in records],
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def write(folder: str, records: Sequence[Record], meta: Dict[str, Any], decisions: Dict[str, Any],
          text_lines: Iterable[str]) -> Dict[str, str]:
    """Write the three files. Returns their paths by role."""
    os.makedirs(folder, exist_ok=True)
    stamp = meta.get("stamp") or time.strftime("%Y%m%d-%H%M%S")
    payload = _jsonable(to_payload(records, meta, decisions))
    text = "\n".join(text_lines) + "\n"
    paths = {
        "text": os.path.join(folder, f"probe-results-{stamp}.txt"),
        "json": os.path.join(folder, f"probe-results-{stamp}.json"),
        "latest": os.path.join(folder, "latest.json"),
    }
    body = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with open(paths["text"], "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    with open(paths["json"], "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    with open(paths["latest"], "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return paths


def load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def ledger_rows(records: Sequence[Record], version: str) -> List[str]:
    """API-LEDGER.md table rows: one per member a probe exercised, with its outcome.

    A member is Verified when a probe that lists it passed, Verified not to work
    when every probe that lists it failed on it, and otherwise left for a person
    to read the report.
    """
    outcome: Dict[str, List[str]] = {}
    for record in records:
        for member in record.members:
            outcome.setdefault(member, []).append(record.status)
    rows = ["| Member | Probe outcome | Status |", "|---|---|---|"]
    for member in sorted(outcome):
        statuses = outcome[member]
        if PASS in statuses:
            status = f"Verified, {version}"
        elif all(s == FAIL for s in statuses):
            status = f"Failed in probe, {version} — see the report"
        else:
            status = "Not reached"
        rows.append(f"| `{member}` | {', '.join(sorted(set(statuses)))} | {status} |")
    return rows
