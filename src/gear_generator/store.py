"""What the app remembers about a gear it built.

A SolidWorks part keeps the equations and the geometry, but not the form that
made them: which recipe, whether the backlash was typed or left to its
equation, which gear it meshes with and at what centre distance. So each part
gets a JSON file beside it, ``<part>.gear.json``, holding one record. It travels
with the part, and one part has one obvious file.

A second file, ``recent.json``, remembers the app's own state between runs —
the output folder, the templates, the last recipe and mode, the last few
records opened. That one is a convenience, so it never raises.

Nothing here touches COM.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1
SIDECAR_SUFFIX = ".gear.json"
RECENT_LIMIT = 10


class StoreError(Exception):
    """The remembered gear could not be read or written."""


class UnknownSchema(StoreError):
    """Written by a newer version of the app than this one."""


@dataclass
class GearRecord:
    """One gear as built: the form, what it came to, and what SolidWorks kept."""

    record_id: str = ""
    kind: str = "spur"
    recipe: str = ""
    spec: Dict[str, Any] = field(default_factory=dict)
    derived: Dict[str, Any] = field(default_factory=dict)
    variables: List[List[str]] = field(default_factory=list)   # [name, expression] in order
    features: List[str] = field(default_factory=list)
    dimensions: List[str] = field(default_factory=list)
    manual_steps: List[str] = field(default_factory=list)
    template: str = ""
    trig: str = ""
    parametric: str = "full"      # "full", or "partial" when names were substituted
    partner: str = ""             # the other gear's part path, in a pair
    assembly: str = ""            # the pair's assembly path
    centre_distance: str = ""
    ratio: str = ""
    created: str = ""
    last_built: str = ""
    last_updated: str = ""
    workbook: str = ""            # the .xlsx this part was built from, if it came from one
    workbook_gears: List[str] = field(default_factory=list)   # the workbook's gears it serves (identical ones share)


@dataclass
class Sidecar:
    part_path: str = ""
    part_title: str = ""
    schema_version: int = SCHEMA_VERSION
    written_by: str = ""
    record: GearRecord = field(default_factory=GearRecord)


def new_record_id() -> str:
    return f"gear-{uuid.uuid4().hex[:8]}"


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -- where it lives ---------------------------------------------------------


def sidecar_path(part_path: str) -> str:
    """``C:\\gears\\Gear_m1.5_N25.SLDPRT`` -> ``C:\\gears\\Gear_m1.5_N25.gear.json``."""
    if not part_path:
        raise StoreError(
            "This part has never been saved, so there is nowhere to keep its gear record."
        )
    stem, _ = os.path.splitext(part_path)
    return stem + SIDECAR_SUFFIX


def same_path(a: str, b: str) -> bool:
    """Windows paths compared the way Windows compares them."""
    if not a or not b:
        return False
    return os.path.normcase(a.replace("/", "\\")).lower() == os.path.normcase(b.replace("/", "\\")).lower()


# -- reading and writing ----------------------------------------------------


def to_json(sidecar: Sidecar) -> str:
    """Byte-deterministic, so an unchanged record is an unchanged file."""
    payload = {
        "schemaVersion": sidecar.schema_version,
        "writtenBy": sidecar.written_by,
        "document": {"path": sidecar.part_path, "title": sidecar.part_title},
        "gear": asdict(sidecar.record),
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _known(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {f.name for f in fields(cls)}
    return {k: v for k, v in raw.items() if k in allowed}


def from_json(text: str) -> Sidecar:
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise StoreError(f"The gear record could not be read: {exc}") from None
    if not isinstance(raw, dict):
        raise StoreError("The gear record is not an object.")

    version = raw.get("schemaVersion", 0)
    if not isinstance(version, int):
        raise StoreError("The gear record has no readable schema version.")
    if version > SCHEMA_VERSION:
        raise UnknownSchema(
            f"This gear record was written by a newer version of Gear Generator "
            f"(schema {version}, this one reads {SCHEMA_VERSION}). It is being left "
            "alone rather than overwritten."
        )

    document = raw.get("document") or {}
    gear = raw.get("gear") or {}
    if not isinstance(gear, dict):
        raise StoreError("The gear record's gear is not an object.")
    return Sidecar(
        part_path=document.get("path", ""),
        part_title=document.get("title", ""),
        schema_version=version,
        written_by=raw.get("writtenBy", ""),
        record=GearRecord(**_known(GearRecord, gear)),
    )


def load(path: str) -> Optional[Sidecar]:
    """Read a record, or None when there is not one.

    A file that cannot be parsed is moved aside rather than deleted or
    overwritten: it is the only copy of settings someone may still want.
    """
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    try:
        return from_json(text)
    except UnknownSchema:
        raise
    except StoreError:
        spoiled = f"{path}.bad-{time.strftime('%Y%m%d-%H%M%S')}"
        os.replace(path, spoiled)
        raise StoreError(
            f"The gear record {os.path.basename(path)} could not be read, so it was moved "
            f"to {os.path.basename(spoiled)} and a fresh one will be written."
        ) from None


def save(path: str, sidecar: Sidecar) -> bool:
    """Write the record if it changed. Atomic, so it is never half-written."""
    text = to_json(sidecar)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                if handle.read() == text:
                    return False
        except OSError:
            pass
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, path)
    return True


# -- the app's own memory ---------------------------------------------------


@dataclass
class Recent:
    folder: str = ""
    part_template: str = ""
    assembly_template: str = ""
    recipe: str = ""
    mode: str = ""
    sidecars: List[str] = field(default_factory=list)
    workbooks: List[str] = field(default_factory=list)   # linked .xlsx files, most recent first

    def remember(self, sidecar: str) -> None:
        """Put a record at the top of the list, once."""
        kept = [p for p in self.sidecars if not same_path(p, sidecar)]
        self.sidecars = ([sidecar] + kept)[:RECENT_LIMIT]

    def remember_workbook(self, path: str) -> None:
        """Put a linked workbook at the top of the list, once."""
        kept = [p for p in self.workbooks if not same_path(p, path)]
        self.workbooks = ([path] + kept)[:RECENT_LIMIT]


def recent_path(environ: Optional[Dict[str, str]] = None, platform: str = sys.platform) -> str:
    env = os.environ if environ is None else environ
    if platform == "win32" and env.get("APPDATA"):
        return os.path.join(env["APPDATA"], "Gear Generator", "recent.json")
    home = env.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, ".config", "gear-generator", "recent.json")


def load_recent(path: Optional[str] = None) -> Recent:
    """What the app remembered last time, or a fresh start. Never raises."""
    try:
        with open(path or recent_path(), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            return Recent()
        recent = Recent(**_known(Recent, raw))
        recent.sidecars = [str(p) for p in (recent.sidecars or []) if p][:RECENT_LIMIT]
        recent.workbooks = [str(p) for p in (recent.workbooks or []) if p][:RECENT_LIMIT]
        for name in ("folder", "part_template", "assembly_template", "recipe", "mode"):
            setattr(recent, name, str(getattr(recent, name) or ""))
        return recent
    except Exception:  # noqa: BLE001 - a convenience file must never stop the app
        return Recent()


def save_recent(recent: Recent, path: Optional[str] = None) -> bool:
    """Write the app's memory. Never raises; says whether it managed."""
    target = path or recent_path()
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        temporary = target + ".tmp"
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(recent), indent=2, sort_keys=True) + "\n")
        os.replace(temporary, target)
        return True
    except Exception:  # noqa: BLE001 - a convenience file must never stop the app
        return False


# -- records from a build ---------------------------------------------------


def built_sidecar(
    part_path: str,
    part_title: str,
    *,
    kind: str,
    recipe: str,
    spec: Dict[str, Any],
    derived: Dict[str, Any],
    variables: List[List[str]],
    features: List[str],
    dimensions: List[str],
    manual_steps: List[str],
    template: str,
    trig: str,
    written_by: str,
    previous: Optional[Sidecar] = None,
    partner: str = "",
    assembly: str = "",
    centre_distance: str = "",
    ratio: str = "",
    stamp: Optional[str] = None,
    workbook: str = "",
    workbook_gears: Optional[List[str]] = None,
) -> Sidecar:
    """The record for a part a build just saved.

    A record already beside that path keeps its id and creation time, so the
    history of one file stays one history.
    """
    stamp = stamp or now()
    kept = previous.record if previous is not None and same_path(previous.part_path, part_path) else None
    record = GearRecord(
        record_id=kept.record_id if kept else new_record_id(),
        kind=kind, recipe=recipe, spec=dict(spec), derived=dict(derived),
        variables=[list(v) for v in variables], features=list(features), dimensions=list(dimensions),
        manual_steps=list(manual_steps), template=template, trig=trig,
        partner=partner, assembly=assembly, centre_distance=centre_distance, ratio=ratio,
        workbook=workbook, workbook_gears=list(workbook_gears or []),
        created=kept.created if kept and kept.created else stamp, last_built=stamp,
        last_updated=kept.last_updated if kept else "",
    )
    return Sidecar(part_path=part_path, part_title=part_title, written_by=written_by, record=record)


def updated_sidecar(sidecar: Sidecar, spec: Dict[str, Any], derived: Dict[str, Any],
                    variables: List[List[str]], stamp: Optional[str] = None) -> Sidecar:
    """The same record after Update values: new form and values, same everything else."""
    record = GearRecord(**{**asdict(sidecar.record), "spec": dict(spec), "derived": dict(derived),
                           "variables": [list(v) for v in variables], "last_updated": stamp or now()})
    return Sidecar(part_path=sidecar.part_path, part_title=sidecar.part_title,
                   schema_version=sidecar.schema_version, written_by=sidecar.written_by, record=record)


# -- a linked workbook's record ----------------------------------------------

LINK_SUFFIX = ".workbook.json"


def link_record_path(workbook_path: str) -> str:
    """``C:\\gears\\Reducer.xlsx`` -> ``C:\\gears\\Reducer.workbook.json``, beside the workbook it describes."""
    stem, _ = os.path.splitext(workbook_path)
    return stem + LINK_SUFFIX


@dataclass
class LinkRecord:
    """What the app built from a workbook: the parts (each with the gears it serves), and when.

    Kept beside the workbook so it travels with it, and so the window can say
    whether SolidWorks is up to date with the file. The file's own contents are
    never copied here: the workbook is the gearbox.
    """

    workbook: str = ""
    digest: str = ""                  # the workbook's sha256 when it was last built from
    parts: List[Dict[str, Any]] = field(default_factory=list)   # {"path": ..., "gears": [...]}
    assembly: str = ""
    last_built: str = ""
    schema_version: int = SCHEMA_VERSION
    written_by: str = ""


def save_link_record(record: LinkRecord, path: Optional[str] = None) -> str:
    """Write it beside the workbook; returns where. Raises OSError, which the window turns into a sentence."""
    target = path or link_record_path(record.workbook)
    payload = json.dumps(asdict(record), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    os.replace(temporary, target)
    return target


def load_link_record(workbook_path: str) -> Optional[LinkRecord]:
    """The record beside a workbook, or None when there is none or it cannot be read (it is only a convenience)."""
    try:
        with open(link_record_path(workbook_path), "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict) or int(raw.get("schema_version", 0)) > SCHEMA_VERSION:
            return None
        return LinkRecord(**_known(LinkRecord, raw))
    except Exception:  # noqa: BLE001 - a missing or broken record means "not built from here yet"
        return None
