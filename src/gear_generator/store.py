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
from typing import Any, Callable, Dict, List, Optional

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


LINK_SCHEMA_VERSION = 2          # the link record's own schema, apart from the .gear.json's SCHEMA_VERSION


@dataclass
class PartEntry:
    """One part file built from the workbook, and what it holds as far as the app knows.

    ``revision`` is the revision whose build made the file (0 for the first
    build and for W2's Build parts; 2, 3, … for ``<Name>_r<n>``): a part
    reused by a later revision keeps the revision that made it. ``spec`` is
    ``GearSpec.to_dict()`` and ``variables`` the ``[name, expression]`` pairs
    in the document's trig units (``trig``), both as built or last updated.
    A v1 record's parts carry only ``path`` and ``gears``.
    """

    path: str = ""
    gears: List[str] = field(default_factory=list)
    revision: int = 0
    kind: str = ""
    spec: Dict[str, Any] = field(default_factory=dict)
    variables: List[List[str]] = field(default_factory=list)
    trig: str = ""


@dataclass
class ShaftEntry:
    """One shaft of a built layout part: ``workbook.layout.ShaftLayout`` field for field (``ShaftEntry(**asdict(
    shaft_layout))`` and back). Coordinates in mm from the origin; ``sigma`` +1 for Z+, -1 for Z-; a side is
    ``plus``, ``minus`` or ``base``; ``x_global`` the global's unquoted name (``S2 X``) and ``x_plane`` the plane's
    feature name (``S2 X Plane``), both ``""`` on a base coordinate; ``axis_name`` the axis feature (``S2 Axis``)."""

    shaft: str = ""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    sigma: int = 1
    x_side: str = ""
    y_side: str = ""
    x_global: str = ""
    y_global: str = ""
    x_plane: str = ""
    y_plane: str = ""
    axis_name: str = ""


@dataclass
class ComponentEntry:
    """One gear's component in the built assembly: the part it is an instance of, the ``Name2`` SolidWorks kept
    (``Gear_m1.5_N17-1``; components are never renamed), and the frame it was last placed at — rotation's 9
    numbers by rows, origin in mm."""

    gear: str = ""
    part: str = ""
    name: str = ""
    rotation: List[float] = field(default_factory=list)
    at: List[float] = field(default_factory=list)


@dataclass
class GearboxRecord:
    """The current revision's layout part and static assembly (phase W4).

    ``name`` is the revision's stem (``Reducer_12to1``, ``Reducer_12to1_r2``).
    ``layout`` and ``shafts`` are written as soon as the layout part saves,
    even if the assembly then fails (decision 4): a record with ``layout``
    set and ``assembly`` empty is a revision whose assembly is still to be
    made, and the next Build continues it, reusing the layout. ``meshes`` are
    the listed meshes as ``[a, b]``; ``layout_component`` the layout's
    ``Name2`` in the assembly. ``built`` and ``updated`` are stamps.
    """

    revision: int = 0
    name: str = ""
    layout: str = ""
    assembly: str = ""
    part_template: str = ""
    assembly_template: str = ""
    shafts: List[ShaftEntry] = field(default_factory=list)
    meshes: List[List[str]] = field(default_factory=list)
    layout_component: str = ""
    components: List[ComponentEntry] = field(default_factory=list)
    built: str = ""
    updated: str = ""


@dataclass
class EarlierRevision:
    """A revision superseded by a later build-again: its files, paths only. Never updated or reused by path
    from here — a part still in use by the current revision is in ``LinkRecord.parts``, not only here."""

    revision: int = 0
    name: str = ""
    layout: str = ""
    assembly: str = ""
    parts: List[str] = field(default_factory=list)


@dataclass
class LinkRecord:
    """What the app built in SolidWorks from a workbook, beside it as ``<Name>.workbook.json`` (schema 2).

    It records what SolidWorks holds — the parts, the layout part and the
    assembly, and the values and frames last put into them — not the
    workbook's cells: the workbook is the gearbox, and this says how far
    SolidWorks has caught up with it.

    - ``digest``: the workbook's sha256 that SolidWorks was last built or
      updated from; ``own_digest``/``recalc``: the app's own last Export.
    - ``parts``: the parts the current revision uses (with no ``gearbox``,
      the parts Build parts made). Merged across builds, never replaced by
      one batch. Update and reuse act only on :meth:`current_parts`
      (decision 2); a part a build-again supersedes moves to ``earlier``.
    - ``assembly``: kept a string for v1; it mirrors ``gearbox.assembly``.
    - ``gearbox``: the current revision, or None before W4 has built one.
    - ``earlier``: superseded revisions, oldest first, paths only.
    - ``unsaved``: path -> the file's modification time (``os.path.getmtime``)
      when Update SolidWorks changed that document without saving it; an
      entry goes once the file on disk is newer (:func:`clear_saved`).

    A v1 file (W2) reads as v2 with ``gearbox`` None; a newer one raises
    :class:`UnknownSchema` and is left alone.
    """

    workbook: str = ""
    digest: str = ""
    parts: List[PartEntry] = field(default_factory=list)
    assembly: str = ""
    last_built: str = ""
    schema_version: int = LINK_SCHEMA_VERSION
    written_by: str = ""
    own_digest: str = ""              # the workbook as the app last wrote it (Export)
    recalc: bool = False              # that write left formulas for Excel to recalculate before Build
    last_updated: str = ""
    gearbox: Optional[GearboxRecord] = None
    earlier: List[EarlierRevision] = field(default_factory=list)
    unsaved: Dict[str, float] = field(default_factory=dict)

    def current_parts(self) -> List[PartEntry]:
        """The parts Update and reuse may act on: those the current revision's components name, or every part
        when no gearbox is recorded (decision 2)."""
        if self.gearbox is None:
            return list(self.parts)
        named = [c.part for c in self.gearbox.components]
        return [p for p in self.parts if any(same_path(p.path, n) for n in named)]


def link_record_to_json(record: LinkRecord) -> str:
    """Byte-deterministic, always written as the current schema."""
    payload = asdict(record)
    payload["schema_version"] = LINK_SCHEMA_VERSION
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _entries(cls, raw: Any) -> list:
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise TypeError(f"{cls.__name__} entries are not a list of objects")
    return [cls(**_known(cls, item)) for item in raw]


def link_record_from_json(text: str) -> LinkRecord:
    """Parse a link record of any schema up to :data:`LINK_SCHEMA_VERSION`; a v1 record is read as v2.

    Raises :class:`UnknownSchema` for a newer schema and :class:`StoreError`
    for anything else wrong; never touches a file.
    """
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise StoreError(f"it is not JSON ({exc})") from None
    if not isinstance(raw, dict):
        raise StoreError("it is not an object")
    version = raw.get("schema_version", 0)
    if isinstance(version, bool) or not isinstance(version, int):
        raise StoreError("it has no readable schema version")
    if version > LINK_SCHEMA_VERSION:
        raise UnknownSchema(f"it was written by a newer Gear Generator (schema {version}, this one reads "
                            f"{LINK_SCHEMA_VERSION})")
    try:
        record = LinkRecord(**_known(LinkRecord, raw))
        record.parts = _entries(PartEntry, raw.get("parts", []))
        if not all(isinstance(p.path, str) and isinstance(p.gears, list) for p in record.parts):
            raise TypeError("a part has no path or gears")
        gearbox = raw.get("gearbox")
        if gearbox is not None:
            if not isinstance(gearbox, dict):
                raise TypeError("gearbox is not an object")
            record.gearbox = GearboxRecord(**_known(GearboxRecord, gearbox))
            record.gearbox.shafts = _entries(ShaftEntry, gearbox.get("shafts", []))
            record.gearbox.components = _entries(ComponentEntry, gearbox.get("components", []))
        record.earlier = _entries(EarlierRevision, raw.get("earlier", []))
        unsaved = raw.get("unsaved", {}) or {}
        if not isinstance(unsaved, dict):
            raise TypeError("unsaved is not an object")
        record.unsaved = {str(k): float(v) for k, v in unsaved.items()}
    except (TypeError, ValueError) as exc:
        raise StoreError(f"its contents are not a link record ({exc})") from None
    if not all(isinstance(getattr(record, k), str) for k in ("workbook", "digest", "assembly", "last_built",
                                                             "own_digest", "last_updated", "written_by")):
        raise StoreError("a field that holds text does not")
    record.recalc = bool(record.recalc)
    record.schema_version = LINK_SCHEMA_VERSION
    return record


def save_link_record(record: LinkRecord, path: Optional[str] = None) -> str:
    """Write it beside the workbook; returns where. Raises OSError, which the window turns into a sentence.

    Callers read the file with :func:`open_link_record` first, so a newer
    record is refused before a write (W4, Agent C: also refuse here, raising
    :class:`UnknownSchema`, if the file on disk is newer than this app reads).
    """
    target = path or link_record_path(record.workbook)
    payload = link_record_to_json(record)
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    os.replace(temporary, target)
    return target


def read_link_record(workbook_path: str) -> Optional[LinkRecord]:
    """The record beside a workbook, for planning: None when there is none. **Never moves or writes a file**, so
    the Tk thread may call it on every refresh (review 13).

    Raises :class:`UnknownSchema` (a newer record: Build, Update SolidWorks and
    the record's writes wait, and the file is left alone) and
    :class:`StoreError` (a broken one: left where it is; :func:`open_link_record`
    moves it aside when the app next writes), each a sentence naming the file.
    """
    target = link_record_path(workbook_path)
    if not os.path.exists(target):
        return None
    name = os.path.basename(target)
    try:
        with open(target, "r", encoding="utf-8") as handle:
            text = handle.read()
        return link_record_from_json(text)
    except UnknownSchema as exc:
        raise UnknownSchema(f"The record of what was built, {name}, cannot be read: {exc}. It is left alone, so "
                            "Build and Update SolidWorks wait.") from None
    except (StoreError, OSError, UnicodeDecodeError) as exc:
        raise StoreError(f"The record of what was built, {name}, cannot be read: {exc}.") from None


def open_link_record(workbook_path: str) -> Optional[LinkRecord]:
    """The record beside a workbook, read just before the app writes it (a build's or an update's finish,
    Export): None when there is none.

    A newer record raises :class:`UnknownSchema` and the file is left
    byte-identical. A broken one is moved aside to ``<name>.bad-<stamp>``, as
    :func:`load` does a sidecar, and :class:`StoreError` is raised with a
    sentence saying where it went; the caller then starts a fresh record.
    Runs on the Tk thread, never during planning.
    """
    raise NotImplementedError("W4: Agent C, store.open_link_record")


def clear_saved(record: LinkRecord, mtime: Callable[[str], float] = os.path.getmtime) -> bool:
    """Drop every ``unsaved`` entry whose file on disk is now newer than when Update changed it (the user saved
    it in SolidWorks), or is gone. Changes ``record`` in place; returns whether anything was dropped. Pure but
    for ``mtime``, which tests inject."""
    raise NotImplementedError("W4: Agent C, store.clear_saved")


def read_sidecar(path: str) -> Optional[Sidecar]:
    """A part's ``.gear.json`` for planning: None when there is none, or it cannot be read, or it is newer than
    this app. **Never moves or writes a file** (unlike :func:`load`), so reuse can be planned on every refresh."""
    raise NotImplementedError("W4: Agent C, store.read_sidecar")


def load_link_record(workbook_path: str) -> Optional[LinkRecord]:
    """The record beside a workbook, or None when there is none or it cannot be read.

    Kept for the window as it stands before W4 is wired (its Export and
    Build parts paths), and for nothing new: it hides a newer record as None,
    which a write would then overwrite. The window wiring moves to
    :func:`read_link_record` and :func:`open_link_record` and removes this.
    """
    try:
        return read_link_record(workbook_path)
    except Exception:  # noqa: BLE001 - a missing or broken record means "not built from here yet"
        return None
