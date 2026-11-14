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

import contextlib
import functools
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Dict, List, Optional, Tuple

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
    # The part file's modification time when Update SolidWorks changed the document without saving it (0: what
    # this record says is what the file holds). The values above are then what SolidWorks holds, not yet the file:
    # they are the file's only once it is newer than this (:func:`saved_since`). A workbook's Update writes it.
    unsaved_since: float = 0.0


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


_PASS = threading.local()          # within one_pass(): normalised path -> its file id, or None (see _file_id)


@contextlib.contextmanager
def one_pass():
    """Within it, each path :func:`same_file` stats is statted once, and its answer kept until the pass ends: a
    planning pass on the Tk thread asks about the same few paths again and again (each sidecar's workbook, the
    journal's, the record's), and against a network path that is offline each stat can wait out the network's
    timeout (third W4 review). Nested passes share the outermost; per thread."""
    if getattr(_PASS, "ids", None) is not None:
        yield
        return
    _PASS.ids = {}
    try:
        yield
    finally:
        _PASS.ids = None


def in_one_pass(function: Callable) -> Callable:
    """``function`` run inside :func:`one_pass`."""
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with one_pass():
            return function(*args, **kwargs)
    return wrapper


def _file_id(path: str) -> Optional[Tuple[int, int]]:
    """``(st_dev, st_ino)`` of the file at ``path``, or None when it cannot be statted or its file id is 0 — some
    network redirectors and virtual drives report 0 for every file, so 0 says nothing about which file it is (the
    cause of shutil's false SameFileError). Kept for the rest of a :func:`one_pass`."""
    ids = getattr(_PASS, "ids", None)
    key = os.path.normcase(path.replace("/", "\\")).lower()
    if ids is not None and key in ids:
        return ids[key]
    try:
        st = os.stat(path)
        found: Optional[Tuple[int, int]] = (st.st_dev, st.st_ino) if st.st_ino else None
    except (OSError, ValueError):
        found = None
    if ids is not None:
        ids[key] = found
    return found


def same_file(a: str, b: str) -> bool:
    """Whether two paths name one file: :func:`same_path` (the text, compared first, statting nothing), or — when
    both can be statted and each has a file id that is not 0 — the same ``(st_dev, st_ino)``, so a mapped drive
    and its UNC path, a ``subst`` drive, a junction, a symlink or an 8.3 name are one file (W4 review N1a). A path
    that cannot be statted, or a file id of 0, is not known to be the same file: compared as text alone (third
    review). Within :func:`one_pass` each path is statted at most once."""
    if same_path(a, b):
        return True
    if not a or not b:
        return False
    first = _file_id(a)
    if first is None:
        return False
    return _file_id(b) == first


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
                    variables: List[List[str]], stamp: Optional[str] = None,
                    unsaved_since: Optional[float] = None) -> Sidecar:
    """The same record after Update values: new form and values, same everything else. ``unsaved_since``, when
    given, marks the new values as SolidWorks' and not yet the file's (:attr:`GearRecord.unsaved_since`); None
    keeps the mark the record had."""
    changes: Dict[str, Any] = {"spec": dict(spec), "derived": dict(derived),
                               "variables": [list(v) for v in variables], "last_updated": stamp or now()}
    if unsaved_since is not None:
        changes["unsaved_since"] = float(unsaved_since)
    record = GearRecord(**{**asdict(sidecar.record), **changes})
    return Sidecar(part_path=sidecar.part_path, part_title=sidecar.part_title,
                   schema_version=sidecar.schema_version, written_by=sidecar.written_by, record=record)


def unmarked(sidecar: Sidecar) -> Sidecar:
    """The same record with its unsaved mark taken off (:attr:`GearRecord.unsaved_since` 0): what it says is what
    the file holds — a job found the document, loaded from its file, holding it (W4 second review N2)."""
    record = GearRecord(**{**asdict(sidecar.record), "unsaved_since": 0.0})
    return Sidecar(part_path=sidecar.part_path, part_title=sidecar.part_title,
                   schema_version=sidecar.schema_version, written_by=sidecar.written_by, record=record)


# -- a linked workbook's record ----------------------------------------------

LINK_SUFFIX = ".workbook.json"


def link_record_path(workbook_path: str) -> str:
    """``C:\\gears\\Reducer.xlsx`` -> ``C:\\gears\\Reducer.workbook.json``, beside the workbook it describes."""
    stem, _ = os.path.splitext(workbook_path)
    return stem + LINK_SUFFIX


LINK_SCHEMA_VERSION = 3          # the link record's own schema, apart from the .gear.json's SCHEMA_VERSION
# Schema 3 (W5): the gearbox block says which kind of assembly it is and, for one built to turn, its mates. A schema 2
# record reads as 3 with ``kind`` GEARBOX_STATIC (a W4 gearbox: its gears placed and fixed). A W4-era build reading
# a schema 3 record refuses it and leaves it byte-identical (it reads ``link_schema_version`` 3 > 2), so it never
# drops ``kind`` and ``mates`` by rewriting the file (W5-PLAN D11).

GEARBOX_STATIC = "static"        # GearboxRecord.kind: the assembly's gears are placed and fixed (W4's gearbox)
GEARBOX_MOTION = "motion"        # GearboxRecord.kind: its gears are mated to their shafts and each other (W5)
GEARBOX_KINDS = (GEARBOX_STATIC, GEARBOX_MOTION)


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
class MateEntry:
    """One mate of an assembly built to turn (W5): ``workbook.motion.MatePlan`` field for field, its tuples as
    lists (``workbook.motion.mate_entry`` makes one). ``name`` is the mate's name in SolidWorks' tree (``G1 on S1
    Axis``, ``G1 along S1``, ``G3 locked to G2``, ``G1 meshes G2``), by which Update finds it; ``kind`` ``axis``,
    ``along``, ``lock`` or ``mesh``; ``gears`` the gear ids it holds (axis and along ``[gear]``; lock ``[anchor,
    follower]``; mesh ``[a, b]``, the gear mate's first selection first); ``shaft`` the shaft of an axis or along
    mate, else ``""``; ``ratio`` a mesh's ``[teeth of a, teeth of b]`` as the gear mate now holds it, else ``[]``;
    ``face_global`` an along mate's assembly global (``G4 Face Z``), ``""`` when the gear's origin sits on the
    Front plane (a coincident mate, with no distance) and for every other kind; ``z_front`` an along mate's origin's
    signed distance from the Front plane in mm, as made or last updated, else 0. The parse (C) refuses, with a
    ``StoreError`` sentence, an entry whose ``kind`` is not one of the four or whose ``gears`` are not as many as
    its kind holds (1 for axis and along, 2 for lock and mesh), and a mesh whose ``ratio`` is not two numbers;
    ``workbook.update.classify`` (B) guards the same with a refusal sentence, never an IndexError."""

    name: str = ""
    kind: str = ""
    gears: List[str] = field(default_factory=list)
    shaft: str = ""
    ratio: List[int] = field(default_factory=list)
    face_global: str = ""
    z_front: float = 0.0


@dataclass
class GearboxRecord:
    """The current revision's layout part and assembly (phase W4; schema 3 adds W5's turning assembly).

    ``name`` is the revision's stem (``Reducer_12to1``, ``Reducer_12to1_r2``).
    ``layout`` and ``shafts`` are written as soon as the layout part saves,
    even if the assembly then fails (decision 4): a record with ``layout``
    set and ``assembly`` empty is a revision whose assembly is still to be
    made, and the next Build continues it, reusing the layout. ``meshes`` are
    the listed meshes as ``[a, b]``; ``layout_component`` the layout's
    ``Name2`` in the assembly. ``built`` and ``updated`` are stamps.

    Schema 3 (W5): ``kind`` is the kind of the assembly on record,
    :data:`GEARBOX_STATIC` (a schema 2 record's, W4's) or
    :data:`GEARBOX_MOTION`; it is written when an assembly saves and means
    nothing while ``assembly`` is ``""``. For a turning one: ``mates``,
    every mate made (and updated: a mesh's ratio, an along mate's
    ``z_front``); ``unmated``, meshes listed but not gear-mated because they
    close a loop, ``[a, b]`` (W5-PLAN D6); ``fixed``, gears left fixed (on a
    fixed shaft, or held still by one: D9, review M9); ``drag``, per train
    the gear to drag, for the footer. ``static_reason``: why a gearbox
    planned while a W5 finding was missing was built static — the planning
    sentence (``GearboxPlan.static_reason``) — and ``""`` for W4's own and
    for a turning one. ``mate_problems``: the sentences the last build's
    mate check found (``BuildResult.mate_problems``) when SolidWorks refused
    or flagged a mate and no assembly was saved (W5-DECISIONS, answer 1),
    and ``mate_problems_digest`` the workbook's sha256 that build came from,
    so the window never offers the same build of an unchanged workbook
    again; both are emptied when an assembly saves.
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
    kind: str = GEARBOX_STATIC
    mates: List[MateEntry] = field(default_factory=list)
    unmated: List[List[str]] = field(default_factory=list)
    fixed: List[str] = field(default_factory=list)
    drag: List[str] = field(default_factory=list)
    static_reason: str = ""
    mate_problems: List[str] = field(default_factory=list)
    mate_problems_digest: str = ""


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
    """What the app built in SolidWorks from a workbook, beside it as ``<Name>.workbook.json`` (schema 3).

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
    - ``mismatched``: path -> the file's modification time when a build's
      live check found the document not holding what this record says (a
      change never saved, a feature renamed or deleted in SolidWorks):
      planning does not reuse it while the file is no newer, but makes that
      part new (W4 review B2's last corner), and a later build that reuses
      it, checked live, drops the entry.
    - ``moved_from``: the paths this workbook had before it was moved or
      renamed (Locate…, or a record adopted after a move: :func:`record_owner`),
      oldest first. Its parts' ``.gear.json`` name the path they were built
      from, so planning still recognises them as this workbook's — while the
      file at that path is gone (a workbook there now is another one).
    - ``copy_of``: in memory only, never written: set (to ``workbook``)
      when the person said this session that the workbook beside this
      record is not the one it was written for, which is gone — a copy
      (:func:`record_owner`). It is not kept in the file, so the answer
      holds for the session, and until this workbook's first build writes a
      record of its own over the one that came with it; a workbook opened
      again in a new session before that is asked again (the way back from
      a mistaken No, third W4 review).
    - ``pending``: a build's journal (W4 review N4): the parts, layout part
      and assembly a build is about to make (``kind`` ``layout`` or
      ``assembly`` for those two), written before the worker starts and
      taken out entry by entry, only once an entry is on record (its
      ``.gear.json`` written, or listed in ``parts`` or a gearbox) or its
      file is not on disk (third W4 review). A pending path that exists when a
      later build is planned, with no ``.gear.json`` beside it, is that
      build's interrupted work — SolidWorks saved it, the app never put it
      on record (a crash, a kill, a power cut, or quitting while SolidWorks
      did not answer) — and is reused once checked live, never called a file
      with no record. ``pending_for`` is the workbook whose build wrote it,
      so a copy's journal, written into the record that came with it, is
      still its own.

    A v1 file (W2) reads as v3 with ``gearbox`` None, a v2 file (W4) with a
    static gearbox (``GearboxRecord.kind``); a newer one raises
    :class:`UnknownSchema` and is left alone. On disk the schema is
    ``link_schema_version``, and ``schema_version`` stays 1 so a build from
    before schema 2 keeps the parts when it rewrites the file
    (:data:`LINK_SCHEMA_FOR_OLD_READERS`).

    The record and the disk can disagree — a file moved, renamed or saved by
    hand since — so nothing trusts it alone: planning checks each path
    exists, reuse and Update compare with SolidWorks live (decision 3), and
    ``unsaved`` is cleared from the files' times, not from the record.
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
    moved_from: List[str] = field(default_factory=list)   # the workbook's earlier paths, oldest first
    mismatched: Dict[str, float] = field(default_factory=dict)
    copy_of: str = ""                 # this session's "a copy" answer: in memory only, never written (see above)
    pending: List[PartEntry] = field(default_factory=list)   # a build's journal: what it is about to make
    pending_for: str = ""             # the workbook whose build wrote ``pending``

    def current_parts(self) -> List[PartEntry]:
        """The parts Update and reuse may act on: those the current revision's components name, or every part
        when no gearbox is recorded or its assembly is not made yet (decision 2). With no components there is
        nothing to filter by, and a build-again has already moved the parts it stopped using to ``earlier``."""
        if self.gearbox is None or not self.gearbox.components:
            return list(self.parts)
        named = [c.part for c in self.gearbox.components]
        return [p for p in self.parts if any(same_path(p.path, n) for n in named)]

    def current_documents(self) -> List[str]:
        """Every document of the current revision: its parts (:meth:`current_parts`), its layout part and its
        assembly."""
        out = [p.path for p in self.current_parts()]
        if self.gearbox is not None:
            out += [d for d in (self.gearbox.layout, self.gearbox.assembly) if d]
        return out

    def current_marks(self, marks: Dict[str, float]) -> List[str]:
        """The paths in ``marks`` (``unsaved`` or ``mismatched``) that are documents of the current revision: an
        earlier revision's documents, left behind by a build-again, are not nagged about (W4 second review N2)."""
        current = self.current_documents()
        return [path for path in marks if any(same_path(path, d) for d in current)]


def merge_parts(parts: List[PartEntry], new: List[PartEntry]) -> List[PartEntry]:
    """``parts`` with ``new`` merged in, never replaced by one batch: an entry for a path already listed takes its
    place (the same file, now holding what ``new`` says), any other is added at the end. Paths compare as Windows
    compares them. Returns a new list; neither argument is changed."""
    merged = list(parts)
    for entry in new:
        at = next((i for i, p in enumerate(merged) if same_path(p.path, entry.path)), None)
        if at is None:
            merged.append(entry)
        else:
            merged[at] = entry
    return merged


LINK_SCHEMA_KEY = "link_schema_version"
# What ``schema_version`` says on disk, for a build of the app from before schema 2 (W2): it refuses anything
# above 1 by reading "no record", and then writes a fresh record over the file on Export or Build parts, losing
# every part. Shown 1, it reads the file as its own, keeps ``parts`` whole (it holds them as plain objects,
# revision, spec and all), ``digest`` and ``assembly``, and drops only what it does not know: the gearbox block,
# ``earlier`` and ``unsaved``. This app reads the real schema from ``link_schema_version``, so a newer file
# (schema 3, 4, …) is still refused here, and a file that comes back without it was rewritten by an old build:
# it reads as schema 1, parts only, and a later Build goes beside the files on disk (the smallest free
# revision), never over them.
LINK_SCHEMA_FOR_OLD_READERS = 1


def link_record_to_json(record: LinkRecord) -> str:
    """Byte-deterministic, always written as the current schema (with ``schema_version`` shown as 1 to a build
    from before schema 2: :data:`LINK_SCHEMA_FOR_OLD_READERS`)."""
    payload = asdict(record)
    payload.pop("copy_of", None)          # this session's answer only: never kept (LinkRecord)
    payload["schema_version"] = LINK_SCHEMA_FOR_OLD_READERS
    payload[LINK_SCHEMA_KEY] = LINK_SCHEMA_VERSION
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _version(raw: Dict[str, Any], key: str) -> int:
    version = raw.get(key, 0)
    if isinstance(version, bool) or not isinstance(version, int):
        raise StoreError(f"its {key} is not a whole number")
    return version


_NUMBER = (int, float)


def _entries(cls, raw: Any) -> list:
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise TypeError(f"{cls.__name__} entries are not a list of objects")
    return [cls(**_known(cls, item)) for item in raw]


def _checked(item: Any) -> Any:
    """``item`` (a link-record dataclass) with every field the type its annotation names, numbers made floats where
    a float is asked; raises TypeError naming the field otherwise. Annotations are read as text (``from __future__
    import annotations``), and only the forms these dataclasses use are known."""
    name = type(item).__name__
    for f in fields(item):
        value, kind = getattr(item, f.name), str(f.type)
        where = f"{name}.{f.name}"
        if kind == "str":
            ok = isinstance(value, str)
        elif kind == "int":
            if isinstance(value, float) and value.is_integer():
                value = int(value)
                setattr(item, f.name, value)
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif kind == "float":
            ok = isinstance(value, _NUMBER) and not isinstance(value, bool)
            if ok:
                setattr(item, f.name, float(value))
        elif kind == "bool":
            ok = isinstance(value, (bool, int))
            if ok:
                setattr(item, f.name, bool(value))
        elif kind == "List[str]":
            ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
        elif kind == "List[int]":
            ok = isinstance(value, list) and all(
                not isinstance(v, bool) and (isinstance(v, int) or (isinstance(v, float) and v.is_integer()))
                for v in value)
            if ok:
                setattr(item, f.name, [int(v) for v in value])
        elif kind == "List[float]":
            ok = isinstance(value, list) and all(isinstance(v, _NUMBER) and not isinstance(v, bool) for v in value)
            if ok:
                setattr(item, f.name, [float(v) for v in value])
        elif kind == "List[List[str]]":
            ok = isinstance(value, list) and all(isinstance(v, list) and all(isinstance(s, str) for s in v)
                                                 for v in value)
        elif kind.startswith("Dict["):
            ok = isinstance(value, dict)
        else:
            continue                  # the nested entries, checked one by one where they are read
        if not ok:
            raise TypeError(f"{where} is not {kind}")
    return item


def link_record_from_json(text: str) -> LinkRecord:
    """Parse a link record of any schema up to :data:`LINK_SCHEMA_VERSION`; a v1 or v2 record is read as v3.

    The schema is ``link_schema_version`` when the file has it, else
    ``schema_version`` (a W2 file, or one an old build rewrote; see
    :data:`LINK_SCHEMA_FOR_OLD_READERS`), and the larger of the two counts. A v1
    record has parts with ``path`` and ``gears`` only, and no gearbox; a v2
    record's gearbox has no ``kind``, so it reads as :data:`GEARBOX_STATIC`,
    with no mates. Every
    field is checked against its type. Raises :class:`UnknownSchema` for a
    newer schema and :class:`StoreError` for anything else wrong, each a phrase
    to follow "cannot be read: "; never touches a file.
    """
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise StoreError(f"it is not JSON ({exc})") from None
    if not isinstance(raw, dict):
        raise StoreError("it is not an object")
    version = max(_version(raw, "schema_version"), _version(raw, LINK_SCHEMA_KEY))
    if version > LINK_SCHEMA_VERSION:
        raise UnknownSchema(f"it was written by a newer Gear Generator (schema {version}, this one reads "
                            f"{LINK_SCHEMA_VERSION})")
    try:
        record = LinkRecord(**{k: v for k, v in _known(LinkRecord, raw).items() if k != "copy_of"})
        record.parts = [_checked(p) for p in _entries(PartEntry, raw.get("parts", []))]
        gearbox = raw.get("gearbox")
        if gearbox is not None:
            if not isinstance(gearbox, dict):
                raise TypeError("gearbox is not an object")
            record.gearbox = _checked(GearboxRecord(**_known(GearboxRecord, gearbox)))
            record.gearbox.shafts = [_checked(s) for s in _entries(ShaftEntry, gearbox.get("shafts", []))]
            record.gearbox.components = [_checked(c) for c in _entries(ComponentEntry,
                                                                        gearbox.get("components", []))]
            record.gearbox.mates = [_checked(m) for m in _entries(MateEntry, gearbox.get("mates", []))]
            if record.gearbox.kind not in GEARBOX_KINDS:
                raise ValueError(f"gearbox.kind is {record.gearbox.kind!r}, not one of {', '.join(GEARBOX_KINDS)}")
        record.earlier = [_checked(e) for e in _entries(EarlierRevision, raw.get("earlier", []))]
        record.pending = [_checked(p) for p in _entries(PartEntry, raw.get("pending", []) or [])]
        for key in ("unsaved", "mismatched"):
            times = raw.get(key, {}) or {}
            if not isinstance(times, dict):
                raise TypeError(f"{key} is not an object")
            if any(isinstance(v, bool) or not isinstance(v, _NUMBER) for v in times.values()):
                raise TypeError(f"a {key} file's time is not a number")
            setattr(record, key, {str(k): float(v) for k, v in times.items()})
        record.recalc = bool(record.recalc)
        record.schema_version = LINK_SCHEMA_VERSION
        _checked(record)
    except (TypeError, ValueError) as exc:
        raise StoreError(f"its contents are not a link record ({exc})") from None
    return record


def _record_name(target: str) -> str:
    return os.path.basename(target)


def _newer(target: str, exc: Exception) -> UnknownSchema:
    return UnknownSchema(f"The record of what was built, {_record_name(target)}, cannot be read: {exc}. "
                         f"{LINK_WAITS}")


LINK_WAITS = "It is left alone, so Build and Update SolidWorks wait."
# The last words of every "this record is newer than the app" sentence. ``ui_text.workbook_footer`` tells a newer
# record (nothing may write it: Build and Update wait) from a broken one (Build goes ahead and the finish sets the
# file aside) by them, so they stay one constant.


def _read_text(target: str) -> str:
    with open(target, "r", encoding="utf-8") as handle:
        return handle.read()


def _set_aside(target: str) -> str:
    """Move a record that cannot be read to ``<name>.bad-<stamp>`` beside it (never deleted: it may be the only
    copy of something someone wants); returns where it went."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    spoiled, n = f"{target}.bad-{stamp}", 2
    while os.path.exists(spoiled):
        spoiled, n = f"{target}.bad-{stamp}-{n}", n + 1
    os.replace(target, spoiled)
    return spoiled


def save_link_record(record: LinkRecord, path: Optional[str] = None) -> str:
    """Write it beside the workbook, atomically (a temporary file, then a replace); returns where.

    Callers read the file with :func:`open_link_record` first. This looks
    again at what is on disk just before writing, against another copy of the
    app writing in between: a record newer than this app reads raises
    :class:`UnknownSchema` and is left byte-identical, and one that cannot be
    read is set aside to ``.bad-<stamp>`` (as :func:`open_link_record` does)
    rather than written over. An unchanged record leaves the file alone. Raises
    OSError when the disk refuses, which the window turns into a sentence.
    """
    target = path or link_record_path(record.workbook)
    payload = link_record_to_json(record)
    if os.path.exists(target):
        try:
            text = _read_text(target)
        except (OSError, UnicodeDecodeError):
            text = None                        # unreadable as text: the write below says whether the disk allows it
        if text == payload:
            return target
        if text is not None:
            try:
                link_record_from_json(text)
            except UnknownSchema as exc:
                raise _newer(target, exc) from None
            except StoreError:
                _set_aside(target)
    temporary = target + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            try:
                os.remove(temporary)
            except OSError:
                pass
    return target


def read_link_record(workbook_path: str) -> Optional[LinkRecord]:
    """The record beside a workbook, for planning: None when there is none. **Never moves or writes a file**, so
    the Tk thread may call it on every refresh (review 13).

    The record is the one named after the workbook beside it, whatever its
    ``workbook`` field says, so a folder copied whole keeps its record.
    Raises :class:`UnknownSchema` (a newer record: Build, Update SolidWorks and
    the record's writes wait, and the file is left alone; the sentence ends
    with :data:`LINK_WAITS`) and :class:`StoreError` (a broken one: left where
    it is; :func:`open_link_record` sets it aside when the app next writes),
    each a sentence naming the file.
    """
    target = link_record_path(workbook_path)
    if not os.path.exists(target):
        return None
    try:
        return link_record_from_json(_read_text(target))
    except UnknownSchema as exc:
        raise _newer(target, exc) from None
    except (StoreError, OSError, UnicodeDecodeError) as exc:
        raise StoreError(f"The record of what was built, {_record_name(target)}, cannot be read: {exc}. The next "
                         "Build sets it aside and starts a new one.") from None


def open_link_record(workbook_path: str) -> Optional[LinkRecord]:
    """The record beside a workbook, read just before the app writes it (a build's or an update's finish,
    Export): None when there is none.

    A newer record raises :class:`UnknownSchema` and the file is left
    byte-identical. A broken one is moved aside to ``<name>.bad-<stamp>``, as
    :func:`load` does a sidecar, and :class:`StoreError` is raised with a
    sentence saying where it went; the caller then starts a fresh record. A
    file the disk will not let be read raises :class:`StoreError` and stays
    where it is. Runs on the Tk thread, never during planning.
    """
    target = link_record_path(workbook_path)
    if not os.path.exists(target):
        return None
    name = _record_name(target)
    try:
        text = _read_text(target)
    except UnicodeDecodeError as exc:
        text, why = None, f"it is not text ({exc})"
    except OSError as exc:
        raise StoreError(f"The record of what was built, {name}, cannot be read: {exc}. It is left where it "
                         "is.") from None
    if text is not None:
        try:
            return link_record_from_json(text)
        except UnknownSchema as exc:
            raise _newer(target, exc) from None
        except StoreError as exc:
            why = str(exc)
    spoiled = _set_aside(target)
    raise StoreError(f"The record of what was built, {name}, could not be read ({why}), so it was moved to "
                     f"{os.path.basename(spoiled)} and a new one is started.")


def _file_name(path: str) -> str:
    """A path's file name, Windows or POSIX, wherever this runs."""
    return os.path.basename(str(path).replace("\\", "/"))


OURS, COPY, UNSURE = "ours", "copy", "unsure"     # whose a record beside a workbook is (record_owner)


def record_owner(record: Optional[LinkRecord], workbook: str, exists: Callable[[str], bool] = os.path.exists,
                 same: Callable[[str, str], bool] = same_file) -> Tuple[str, str]:
    """Whose the record beside ``workbook`` is: ``(OURS, "")``, or ``(COPY, other)`` / ``(UNSURE, other)`` with
    the other workbook it was written for (W4 review S1, second review N1).

    :func:`read_link_record` finds a record by its file name beside the
    workbook, so a project folder copied whole (workbook and record) brings
    the original's record along, and the output folder in it is absolute:
    the copy would drive the original's SolidWorks files. So:

    - OURS: ``workbook`` in the record is empty, or names this file — by
      text, or (``same``, :func:`same_file`) through another path to the
      same file: a mapped drive and its UNC path are one workbook, not a
      copy of itself;
    - COPY: it names another file that still exists, or the person said
      this session that this workbook is a copy (``copy_of``, in memory
      only): that workbook's record, and its files. Update waits, and Build
      makes a gearbox of this workbook's own beside them;
    - UNSURE: it names a file that is gone, and nobody has said. The
      workbook may have been moved or renamed — or it may be one of several
      copies of an original since deleted, renamed, or on a drive that is
      offline now — so the record is not adopted silently: the window asks
      once, and until it is answered the record is treated as not this
      workbook's (as a COPY). "Yes" is kept by adopting the record
      (:func:`adopt`), "No" by ``copy_of`` for the session
      (:func:`copy_by_answer` tells that COPY from one whose workbook is
      there).

    Pure but for ``exists`` and ``same``."""
    other = record.workbook if record is not None else ""
    workbook = str(workbook or "")
    if not other or not workbook or same(other, workbook):
        return OURS, ""
    if record.copy_of and same_path(record.copy_of, other):
        return COPY, other
    return (COPY if exists(other) else UNSURE), other


def foreign_workbook(record: Optional[LinkRecord], workbook: str, exists: Callable[[str], bool] = os.path.exists,
                     same: Callable[[str, str], bool] = same_file) -> str:
    """The other workbook a record beside ``workbook`` was written for, when the record is not to be taken as
    this workbook's (:func:`record_owner`: a COPY, or UNSURE until the person answers); ``""`` when it is
    this workbook's."""
    owner, other = record_owner(record, workbook, exists, same)
    return "" if owner == OURS else other


def copy_by_answer(record: Optional[LinkRecord], workbook: str,
                   exists: Callable[[str], bool] = os.path.exists) -> bool:
    """Whether the record beside ``workbook`` is another workbook's only because the person said so this session
    (``copy_of``): that workbook is not there, so no sentence may say it is (third W4 review, item 4)."""
    if record is None or not record.copy_of or not same_path(record.copy_of, record.workbook):
        return False
    return record_owner(record, workbook, exists)[0] == COPY and not exists(record.workbook)


def foreign_record_sentence(workbook: str, other: str, gone: bool = False, said: bool = False) -> str:
    """Why a copied workbook's record is not used (:func:`record_owner`), as a sentence naming both files; ``gone``
    for a record whose workbook is not there any more and nobody has said whether this one was moved from it;
    ``said`` for one whose workbook is not there and which the person said this workbook is a copy of
    (:func:`copy_by_answer`)."""
    record = _file_name(link_record_path(workbook))
    if said:
        return (f"The record of what was built beside this workbook, {record}, was written for {other}, which you "
                f"said this workbook is a copy of: the SolidWorks files that record lists are {_file_name(other)}'s, "
                "so Update SolidWorks leaves them alone, and Build makes this workbook's own gearbox beside them, "
                "sharing and overwriting nothing.")
    if gone:
        return (f"The record of what was built beside this workbook, {record}, was written for {other}, which is not "
                "there any more, and whether this workbook was moved or renamed from it has not been answered: until "
                "it is, Update SolidWorks leaves the files that record lists alone.")
    return (f"The record of what was built beside this workbook, {record}, was "
            f"written for {other}, which is still there: this workbook is a copy of it, and the SolidWorks files "
            f"that record lists are {_file_name(other)}'s. Update SolidWorks leaves them alone, and Build makes this "
            "workbook's own gearbox beside them, sharing and overwriting nothing.")


def settle_owner(record: LinkRecord, workbook: str, moved: bool) -> None:
    """The person's answer to "was this workbook moved or renamed from …?" (an UNSURE record), made in the record
    in place: Yes adopts it (:func:`adopt`), and written, is kept; No marks it another workbook's (``copy_of``),
    which is never written, so it holds for the session only (until a build of this workbook's own replaces the
    record)."""
    if moved:
        adopt(record, workbook)
    else:
        record.copy_of = record.workbook


def adopt(record: LinkRecord, workbook: str) -> None:
    """Point a record at the path its workbook has now (moved or renamed), keeping the old one in ``moved_from``.
    Changes ``record`` in place; nothing when it already names ``workbook`` — by text or as the same file
    (:func:`same_file`: another path to one workbook is not a move, W4 review N1a)."""
    old = record.workbook
    if not workbook or same_file(old, workbook):
        return
    if old and not any(same_path(old, p) for p in record.moved_from):
        record.moved_from.append(old)
    record.moved_from = [p for p in record.moved_from if not same_path(p, workbook)]
    record.workbook = workbook


def saved_since(path: str, then: float, mtime: Callable[[str], float] = os.path.getmtime) -> bool:
    """Whether the file at ``path`` is newer than ``then`` (saved since). A file whose time cannot be read is not."""
    try:
        return float(mtime(path)) > then
    except (OSError, ValueError, TypeError):
        return False


def clear_saved(record: LinkRecord, mtime: Callable[[str], float] = os.path.getmtime) -> bool:
    """Drop every ``unsaved`` entry whose file on disk is now newer than when Update changed it (the user saved
    it in SolidWorks), or is gone, and likewise every ``mismatched`` entry whose file is newer than when it was
    found (planning tries such a file again, checked live). Changes ``record`` in place; returns whether
    anything was dropped. Pure but for ``mtime``, which tests inject. The window runs it on its planning read,
    in memory, never on a record it writes.

    A file whose time is the same, or older (an older copy put back), is
    still unsaved: the update is in SolidWorks only."""
    dropped = False
    for marks in (record.unsaved, record.mismatched):
        for path, then in list(marks.items()):
            try:
                now_ = mtime(path)
            except OSError:
                now_ = None
            if now_ is None or now_ > then:
                del marks[path]
                dropped = True
    return dropped


def read_sidecar(path: str) -> Optional[Sidecar]:
    """A part's ``.gear.json`` for planning: None when there is none, or it cannot be read, or it is newer than
    this app. **Never moves or writes a file** (unlike :func:`load`), so reuse can be planned on every refresh.

    ``path`` is the sidecar's own path or the part's (``….SLDPRT``): the
    sidecar beside the part is read either way."""
    if not path:
        return None
    target = path if path.lower().endswith(SIDECAR_SUFFIX) else sidecar_path(path)
    if not os.path.exists(target):
        return None
    try:
        return from_json(_read_text(target))
    except (StoreError, OSError, UnicodeDecodeError, TypeError, ValueError):
        return None


class NotCarried(StoreError):
    """Locate…: the record beside the workbook's old place is another workbook's, so it is not carried."""


def carry_link_record(old_workbook: str, new_workbook: str,
                      exists: Callable[[str], bool] = os.path.exists) -> Optional[str]:
    """Locate…: the workbook was moved or renamed, and the window now points at ``new_workbook``. If no record sits
    beside the new path but one sits beside the old, a copy is written beside the new one with ``workbook`` set to
    the new path, and its path returned; the old record is left alone (the old folder may be someone's backup).
    None when there is nothing to carry: no record beside the old path, one already beside the new, or the same
    file. The old path joins ``moved_from``, so the parts' ``.gear.json``, which name it, are still recognised as
    this workbook's. Raises what :func:`read_link_record` raises for the old record (a newer one is not carried:
    copied, it would be written as this schema), and OSError when the copy cannot be written.

    Only a record that was this workbook's at the old path is adopted (W4
    review N1b: Locate… must not launder a copy's record into its own, and
    then drive the original's files). One judged another workbook's (a
    COPY, :func:`record_owner`) is not carried: :class:`NotCarried`, a
    sentence. One whose workbook is gone and unanswered (UNSURE) is carried
    as it is, not adopted, so the question is asked at the new place."""
    if same_file(old_workbook, new_workbook) or os.path.exists(link_record_path(new_workbook)):
        return None
    record = read_link_record(old_workbook)
    if record is None:
        return None
    owner, other = record_owner(record, old_workbook, exists)
    if owner == COPY:
        raise NotCarried(f"it was written for {other}, so it is that workbook's record and lists that workbook's "
                         "files, not this one's.")
    if owner == UNSURE:
        return save_link_record(record, link_record_path(new_workbook))
    adopt(record, new_workbook)
    if not any(same_path(old_workbook, p) for p in record.moved_from):
        record.moved_from.append(old_workbook)     # the window's path, if the record named some other
    return save_link_record(record, link_record_path(new_workbook))
