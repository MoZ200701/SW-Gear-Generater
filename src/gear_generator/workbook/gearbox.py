"""Planning a whole build of a workbook's gearbox, and recording what it made (docs/PLAN-WORKBOOK.md §4.2–§4.5).

Pure, on the Tk thread: :func:`plan_gearbox` turns an :class:`Assessment`
and the link record into a :class:`GearboxPlan` — which parts to make, which
to reuse, the layout part (made, or reused), the static assembly, at which
revision, or the sentence refusing it — and :func:`finish_build` turns what
the worker did (``swbuild.GearboxResult``) into the sidecars and the record
to save. The worker runs ``swbuild.build_gearbox(session,
**plan.build_kwargs())`` and nothing else. Nothing here touches COM or Tk, and
nothing here writes or moves a file: the file system is reached only through
the ``exists`` and ``read_sidecar`` callables, which tests replace (review 13:
planning never moves files).

Interfaces pinned in the W4 interface commit; every body that raises
NotImplementedError is Agent B's.

**Revisions** (decisions 2, 4, 6; §4.5). The first build is revision 0:
``<Name>_Layout.SLDPRT`` and ``<Name>.SLDASM``. A build-again is the next
revision n ≥ 2: ``<Name>_r<n>_Layout.SLDPRT`` and ``<Name>_r<n>.SLDASM``,
beside the old files, which are never overwritten. :func:`plan_gearbox`
chooses the revision itself:

- the record's gearbox with ``layout`` saved and ``assembly`` empty (the
  assembly failed last time): **continue** that revision, reusing the layout
  when the live check can pass (its shafts' sides and names equal the
  recorded ones), else the next free revision;
- otherwise the **smallest free revision**: the smallest n in 0, 2, 3, …
  whose layout and assembly paths are both free on disk and that no revision
  on the record (``gearbox`` or ``earlier``) used. So files on disk with no
  record, or a component renamed in SolidWorks, lead to a build beside them,
  never a dead end; ``revision_reason`` says why the revision is not 0.

**Parts.** A part already built is reused when the record's current parts
(``LinkRecord.current_parts()``), or the ``.gear.json`` beside the job's path
(``workbook`` equal to this workbook), hold the same part: the same plan and
stem, and the kind's variables' texts equal (fields a kind ignores — a spur
gear's Hand, a Part name equal to the default stem — are normalised first;
decision 5). It is then checked live before anything is built (decision 3:
``swbuild.build_gearbox`` step 1). A part listed in ``record.unsaved`` is not
reused: Update changed it in SolidWorks and it is not saved, so the file on
disk is not what the record says; the refusal asks for it to be saved. A job
whose path is taken by anything else gets ``<stem>_r<n>`` at this revision
(:func:`replan`); only if that is taken too is it a refusal.
"""

from __future__ import annotations

import copy
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from .. import findings, store
from ..gears import kind_for, plan_for
from ..gears.base import BuildPlan, GlobalVariable
from ..spec import GearSpec, InputError, sanitize_stem
from ..store import (ComponentEntry, EarlierRevision, GearboxRecord, LinkRecord, PartEntry, ShaftEntry, Sidecar)
from ..swbuild import BuildResult, DocumentValues, GearboxResult
from . import layout
from .assess import Assessment
from .build import PartJob
from .layout import REVISION_SUFFIX, Frame, ShaftLayout


@dataclass(frozen=True)
class PartReuse:
    """A part already built and unchanged, inserted again: ``variables`` (``kind.variables(spec, derived)``) are
    what it must hold exactly, checked live; ``revision`` is the revision that made the file."""

    path: str
    stem: str
    gear_ids: Tuple[str, ...]
    spec: GearSpec
    derived: Any
    variables: Tuple[GlobalVariable, ...]
    revision: int


@dataclass(frozen=True)
class LayoutReuse:
    """A layout part already saved (an assembly that failed after it), inserted again once it is checked live
    to hold ``variables`` exactly and every name in ``features`` (``layout.layout_globals`` and
    ``layout.layout_features`` of the recorded shafts)."""

    path: str
    variables: Tuple[GlobalVariable, ...]
    features: Tuple[str, ...]


@dataclass(frozen=True)
class GearboxPlan:
    """One press of Build (or Build parts, or Build again…), planned whole.

    ``revision`` 0 or n ≥ 2 and ``name`` its assembly stem; ``folder`` where
    new files go. ``build`` are the parts to make, each planned at its final
    path; ``reuse`` the parts inserted as they are. ``layout`` is the layout's
    plan, a :class:`LayoutReuse`, or None in a parts-only plan (Build parts,
    W2's fallback while rows a later phase builds hold the layout back,
    decision 9); ``assembly`` likewise a plan or None. ``layout_path`` and
    ``assembly_path`` are ``""`` in a parts-only plan. ``shafts`` and
    ``frames`` (gear -> :class:`Frame`) are what the layout and assembly
    were planned from; ``handles`` maps each assembly handle to its gear
    (``"layout"`` is not in it); ``part_of`` maps each gear to its part's
    path. ``refusal`` is ``""`` to go, else the sentence (an existing new
    path, two new paths the same, a reused file gone, a reused part unsaved),
    in which case the plans may be partial and must not be run.
    ``revision_reason`` is ``""`` for revision 0 or a continued revision, else
    why this revision (``Reducer_12to1.SLDASM is already there, …``).
    """

    revision: int
    name: str
    folder: str
    layout_path: str
    assembly_path: str
    build: Tuple[PartJob, ...]
    reuse: Tuple[PartReuse, ...]
    shafts: Tuple[ShaftLayout, ...]
    frames: Mapping[str, Frame]
    layout: Union[BuildPlan, LayoutReuse, None]
    assembly: Optional[BuildPlan]
    handles: Mapping[str, str]
    part_of: Mapping[str, str]
    part_template: str = ""
    assembly_template: str = ""
    refusal: str = ""
    revision_reason: str = ""
    meshes: Tuple[Tuple[str, str], ...] = ()     # the listed meshes (a, b), for the record (Agent B, additive)

    @property
    def parts_only(self) -> bool:
        return self.layout is None and self.assembly is None

    def build_kwargs(self) -> Dict[str, Any]:
        """The arguments of ``swbuild.build_gearbox(session, **plan.build_kwargs())``: plain data the worker can
        take across threads. Never called on a plan with a refusal."""
        if self.refusal:
            raise ValueError(f"This build is refused, so it cannot be run: {self.refusal}")
        layout: Union[BuildPlan, DocumentValues, None]
        if isinstance(self.layout, LayoutReuse):
            layout = DocumentValues(self.layout.path, tuple(self.layout.variables), tuple(self.layout.features))
        else:
            layout = self.layout
        return {
            "parts": [job.plan for job in self.build],
            "reuse": [DocumentValues(r.path, tuple(r.variables)) for r in self.reuse],
            "layout": layout,
            "assembly": self.assembly,
            "gears": dict(self.handles),
        }


@dataclass
class Finished:
    """What a finish asks the Tk thread to write: ``store.save`` each ``(sidecar path, Sidecar)`` in order, then
    ``store.save_link_record(record)`` unless it is None (nothing reached disk). ``notes`` are sentences about the
    records themselves (a sidecar left alone because it is newer, …) for the footer. ``dragged`` (an update's
    finish only): gears whose live frame differed from the recorded one while the recorded one was what the
    workbook wanted — the user moved them in SolidWorks, and Update put them back."""

    record: Optional[LinkRecord] = None
    sidecars: List[Tuple[str, Sidecar]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    dragged: List[str] = field(default_factory=list)


MAX_REVISION = 99                 # the last revision plan_gearbox tries before it says every one is taken
_PROBE_PATH = "C:\\same-part-probe.SLDPRT"     # one path for both plans when only their parts are compared
_PLAN_ERRORS = (InputError, ValueError, ArithmeticError, TypeError, KeyError, AttributeError)


# -- the same part ---------------------------------------------------------------------------------


def _template_of(plan: BuildPlan) -> str:
    first = plan.ops[0] if plan.ops else None
    return getattr(first, "template", "")


def _plan_of(spec: GearSpec, template: str, path: str = _PROBE_PATH) -> Optional[BuildPlan]:
    """The strip's plan for a form, or None when the form does not plan (a record from an older version)."""
    try:
        kind = kind_for(spec)
        if kind is None:
            return None
        return plan_for(spec, kind.derive(spec), template, path)
    except _PLAN_ERRORS:
        return None


def _custom_name(spec: GearSpec) -> str:
    """The Part name as typed, or ``""`` when blank or the same as the default stem (decision 5)."""
    typed = spec.name.strip()
    if not typed:
        return ""
    stem = sanitize_stem(typed)
    return "" if stem.lower() == spec.default_stem().lower() else stem


def name_changed(built: GearSpec, wanted: GearSpec) -> bool:
    """Whether the Part name asks for another file name than the built part's.

    Only a typed Part name decides it: a default stem that drifts with the
    values (``Gear_m1.5_N68`` holding 69 teeth) is a value change and the file
    keeps its name; a Part name typed equal to the default stem is no name at
    all; and a name that differs only in case is one file to Windows.
    """
    if wanted.stem().lower() == built.stem().lower():
        return False
    return bool(_custom_name(built) or _custom_name(wanted))


def same_part(built: GearSpec, wanted: GearSpec, template: str = "") -> bool:
    """Whether the part built from ``built`` is the part ``wanted`` asks for: the strip's two plans equal at one
    path and template, and the same file name (:func:`name_changed`). Fields a kind ignores — a spur gear's
    Hand, a recipe left blank or typed as the default, ``17`` and ``17.0`` — leave the plans equal (decision 5)."""
    if name_changed(built, wanted):
        return False
    a, b = _plan_of(built, template), _plan_of(wanted, template)
    return a is not None and a == b


def _squash(text: str) -> str:
    return "".join(str(text).split())


def _variables_match(recorded: Sequence[Sequence[str]], trig: str, wanted: Sequence[GlobalVariable]) -> bool:
    """Every wanted global's text as recorded (in the recorded trig units); an empty record says nothing."""
    if not recorded:
        return True
    held = {str(pair[0]): str(pair[1]) for pair in recorded if len(pair) >= 2}
    return all(v.name in held and _squash(held[v.name]) == _squash(v.expression_for(trig)) for v in wanted)


def _matches(spec_dict: Mapping[str, Any], variables: Sequence[Sequence[str]], trig: str, job: PartJob) -> bool:
    if not spec_dict:
        return False                       # a v1 record's part says only its path and gears
    try:
        built = GearSpec.from_dict(dict(spec_dict))
    except (TypeError, ValueError):
        return False
    if not same_part(built, job.spec, _template_of(job.plan)):
        return False
    return _variables_match(variables, trig, _variables_of(job))


def _variables_of(job: PartJob) -> Tuple[GlobalVariable, ...]:
    return tuple(kind_for(job.spec).variables(job.spec, job.derived))


# -- finding what can be reused ---------------------------------------------------------------------


def _stem_of(path: str) -> str:
    return os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]


def _revised(path: str, revision: int) -> str:
    """``C:\\P\\Gear_m1.5_N68.SLDPRT`` at revision 2 -> ``C:\\P\\Gear_m1.5_N68_r2.SLDPRT``."""
    stem, ext = os.path.splitext(path)
    return f"{stem}{REVISION_SUFFIX}{revision}{ext}"


def _revision_in(path: str, stem: str) -> int:
    match = re.fullmatch(re.escape(stem) + re.escape(REVISION_SUFFIX) + r"(\d+)", _stem_of(path), re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _in(path: str, paths) -> bool:
    return any(store.same_path(path, p) for p in paths)


@dataclass
class _Found:
    path: str
    revision: int


class _Parts:
    """What the record and the sidecars say about one job's part, asked once per revision tried."""

    def __init__(self, record: Optional[LinkRecord], workbook: str, exists: Callable[[str], bool],
                 read_sidecar: Callable[[str], Optional[Sidecar]]) -> None:
        self.record = record
        self.workbook = workbook
        self.exists = exists
        self.read_sidecar = read_sidecar
        self._sidecars: Dict[str, Optional[Sidecar]] = {}
        self.unsaved = list(record.unsaved) if record is not None else []

    def sidecar(self, path: str) -> Optional[Sidecar]:
        key = path.lower()
        if key not in self._sidecars:
            self._sidecars[key] = self.read_sidecar(store.sidecar_path(path)) if self.exists(path) else None
        return self._sidecars[key]

    def ours(self, path: str) -> bool:
        """Whether the file's record beside it says this workbook built it."""
        sidecar = self.sidecar(path)
        return sidecar is not None and bool(self.workbook) and store.same_path(sidecar.record.workbook, self.workbook)

    def entries(self, revision: int) -> List[PartEntry]:
        """The record's parts reuse may take (decision 2): the current revision's, and any this revision made
        already in an attempt whose assembly was not made."""
        if self.record is None:
            return []
        out = list(self.record.current_parts())
        out.extend(p for p in self.record.parts if p.revision == revision and p not in out)
        return out

    def find(self, job: PartJob, revision: int) -> Tuple[Optional[_Found], str]:
        """A part this job may reuse, and the path of a match that is unsaved (``""`` if none)."""
        unsaved = ""
        for entry in self.entries(revision):
            if not _matches(entry.spec, entry.variables, entry.trig, job) or not self.exists(entry.path):
                continue
            if _in(entry.path, self.unsaved):
                unsaved = unsaved or entry.path
                continue
            return _Found(entry.path, entry.revision), ""
        candidates = [job.path] + ([_revised(job.path, revision)] if revision else [])
        for path in candidates:
            if not self.exists(path) or not self.ours(path):
                continue
            record = self.sidecar(path).record
            if not _matches(record.spec, record.variables, record.trig, job):
                continue
            if _in(path, self.unsaved):
                unsaved = unsaved or path
                continue
            on_record = next((p for p in (self.record.parts if self.record else []) if store.same_path(p.path, path)),
                             None)
            return _Found(path, on_record.revision if on_record else _revision_in(path, job.stem)), ""
        return None, unsaved

    def occupant(self, path: str) -> str:
        """Why a taken path cannot be this job's, as the end of a sentence."""
        if self.ours(path):
            return "was built from this workbook for values its row no longer has"
        return "was not built from this workbook"


# -- planning ---------------------------------------------------------------------------------------


def _layout_refusal() -> str:
    route = getattr(findings, "WORKBOOK_LAYOUT_ROUTE", None)
    if route == "layout":
        return ""
    if route is None:
        return ("The layout part and assembly wait for probe tier 7, whose findings are not committed yet, so only "
                "the parts can be built.")
    return (f"The layout part and assembly are not built by this version, since probe tier 7 found {route!r} "
            "(findings.WORKBOOK_LAYOUT_ROUTE), so only the parts can be built.")


def _same_layout(recorded: Sequence[ShaftLayout], current: Sequence[ShaftLayout]) -> bool:
    """The saved layout part is the one the current shafts would build: the same globals and the same planes and
    axes (Z and Z± are not in the layout part)."""
    return (layout.layout_globals(recorded) == layout.layout_globals(current)
            and layout.layout_features(recorded) == layout.layout_features(current))


def _recorded_shafts(gearbox: GearboxRecord) -> Tuple[ShaftLayout, ...]:
    return tuple(ShaftLayout(**asdict(entry)) for entry in gearbox.shafts)


@dataclass
class _Attempt:
    revision: int
    obstacle: str = ""
    refusal: str = ""
    layout_path: str = ""
    assembly_path: str = ""
    layout_reuse: Optional[LayoutReuse] = None
    parts: List[Tuple[PartJob, Optional[_Found], str]] = field(default_factory=list)   # job, reuse, new path


def _try(n: int, a: Assessment, jobs: Sequence[PartJob], parts: _Parts, shafts: Sequence[ShaftLayout],
         continuing: Optional[GearboxRecord], parts_only: bool) -> _Attempt:
    exists = parts.exists
    folder = a.folder
    name, layout_stem = layout.stems(a.spec.box.name, n)
    attempt = _Attempt(n)
    new_paths: List[str] = []
    if not parts_only:
        attempt.layout_path = os.path.join(folder, layout_stem + layout.PART_EXTENSION)
        attempt.assembly_path = os.path.join(folder, name + layout.ASSEMBLY_EXTENSION)
        layout_name = os.path.basename(attempt.layout_path)
        if exists(attempt.layout_path):
            continued = continuing is not None and continuing.revision == n and store.same_path(
                continuing.layout, attempt.layout_path)
            if continued and _same_layout(_recorded_shafts(continuing), shafts):
                attempt.layout_reuse = LayoutReuse(attempt.layout_path, layout.layout_globals(shafts),
                                                   layout.layout_features(shafts))
            elif continued:
                attempt.obstacle = (f"{layout_name} was saved by a build whose assembly was not made, but the shafts "
                                    "have moved since, so it is not the layout part this workbook needs.")
                return attempt
            else:
                attempt.obstacle = f"{layout_name} is already in {folder}, and a build never overwrites a file."
                return attempt
        else:
            new_paths.append(attempt.layout_path)
        if exists(attempt.assembly_path):
            attempt.obstacle = (f"{os.path.basename(attempt.assembly_path)} is already in {folder}, and a build never "
                                "overwrites a file.")
            return attempt
        new_paths.append(attempt.assembly_path)
    for job in jobs:
        found, unsaved = parts.find(job, n)
        if unsaved:
            attempt.refusal = (f"{os.path.basename(unsaved)} was changed in SolidWorks by Update SolidWorks and has "
                               "not been saved since, so the file is not yet the part this build would use: save it "
                               "in SolidWorks, then build again.")
            return attempt
        if found is not None:
            attempt.parts.append((job, found, found.path))
            continue
        path = job.path
        if exists(path):
            revised = _revised(job.path, n) if n else ""
            if not revised:
                attempt.obstacle = (f"{os.path.basename(path)} is already in {folder} and {parts.occupant(path)}, "
                                    "and a build never overwrites a file.")
                return attempt
            if exists(revised):
                attempt.obstacle = (f"{os.path.basename(path)} and {os.path.basename(revised)} are already in "
                                    f"{folder}, and {os.path.basename(revised)} {parts.occupant(revised)}.")
                return attempt
            path = revised
        attempt.parts.append((job, None, path))
        new_paths.append(path)
    for i, path in enumerate(new_paths):
        if any(store.same_path(path, other) for other in new_paths[:i]):
            attempt.obstacle = (f"Two of the files this build would make are both {os.path.basename(path)}; give the "
                                "gear a Part name that is not the gearbox's.")
            return attempt
    return attempt


def plan_gearbox(a: Assessment, record: Optional[LinkRecord], *, part_template: str = "",
                 assembly_template: str = "", parts_only: bool = False,
                 exists: Callable[[str], bool] = os.path.exists,
                 read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar) -> GearboxPlan:
    """Plan the next build from an assessment that passed its gate, at the revision the module docstring picks.

    The caller has already checked the window's own state and
    ``a.lay_out_refusal()`` (or, with ``parts_only``, ``a.build_refusal()``);
    this adds only what the file system and the record decide, as
    ``refusal``. Templates: the Box sheet's, else the given (the strip's).
    ``record`` is the planning read (``store.read_link_record``), or None.
    The worker repeats every existence check against the race.

    A revision is tried in turn — the one a failed assembly left to continue,
    then 0, 2, 3, … less those on record — until every file it would make is
    free: its layout and assembly, and each new part at its own stem or, if
    that is taken, ``<stem>_r<n>``. So a file in the way, ours or not, moves
    the build to the next revision with a sentence saying why
    (``revision_reason``), never to a dead end (decision 6).
    """
    spec = a.spec
    folder = a.folder
    part_tpl = spec.box.part_template or part_template
    asm_tpl = spec.box.assembly_template or assembly_template
    workbook = (record.workbook if record is not None and record.workbook else "") or a.read.source_path \
        or spec.source_path
    jobs = list(a.parts.jobs)
    meshes = tuple((m.a, m.b) for m in spec.meshes)
    empty = dict(folder=folder, layout_path="", assembly_path="", build=(), reuse=(), shafts=(), frames={},
                 layout=None, assembly=None, handles={}, part_of={}, part_template=part_tpl,
                 assembly_template=asm_tpl, meshes=meshes)
    name0 = layout.stems(spec.box.name, 0)[0]

    shafts: Tuple[ShaftLayout, ...] = ()
    frames: Dict[str, Frame] = {}
    if not parts_only:
        refusal = _layout_refusal()
        if not refusal:
            try:
                shafts = layout.shaft_layouts(spec)
                frames = layout.frames(a.report)
                layout.layout_globals(shafts)
            except ValueError as exc:
                refusal = str(exc)
        if refusal:
            return GearboxPlan(revision=0, name=name0, refusal=refusal, **empty)

    gearbox = record.gearbox if record is not None else None
    used = set()
    if gearbox is not None:
        used.add(gearbox.revision)
    if record is not None:
        used.update(e.revision for e in record.earlier)
    continuing = gearbox if gearbox is not None and gearbox.layout and not gearbox.assembly else None
    order = [continuing.revision] if continuing is not None else []
    order += [n for n in [0] + list(range(2, MAX_REVISION + 1)) if n not in used and n not in order]

    parts = _Parts(record, workbook, exists, read_sidecar)
    first_obstacle = ""
    chosen: Optional[_Attempt] = None
    for n in order:
        attempt = _try(n, a, jobs, parts, shafts, continuing, parts_only)
        if attempt.refusal:
            return GearboxPlan(revision=n, name=layout.stems(spec.box.name, n)[0], refusal=attempt.refusal,
                               **empty)
        if not attempt.obstacle:
            chosen = attempt
            break
        first_obstacle = first_obstacle or attempt.obstacle
    if chosen is None:
        last = layout.stems(spec.box.name, MAX_REVISION)[0]
        return GearboxPlan(revision=0, name=name0, refusal=(
            f"{first_obstacle} Every revision up to {last} is taken in {folder} too, so nothing is built: change "
            "the output folder."), **empty)

    n = chosen.revision
    name = layout.stems(spec.box.name, n)[0]
    reason = ""
    if n != 0 and not (continuing is not None and n == continuing.revision):
        why = first_obstacle
        if not why and gearbox is not None:
            built = os.path.basename(gearbox.assembly or gearbox.layout) or gearbox.name
            why = f"{built} was built from this workbook already."
        if not why:
            why = "The revisions before it are on the record of what was built."
        reason = f"{why} So this build is {name}, beside it; nothing is overwritten."

    build_jobs: List[PartJob] = []
    reuse: List[PartReuse] = []
    part_of: Dict[str, str] = {}
    for job, found, path in chosen.parts:
        for gear in job.gear_ids:
            part_of[gear] = path
        if found is not None:
            reuse.append(PartReuse(path, _stem_of(path), tuple(job.gear_ids), job.spec, job.derived,
                                   _variables_of(job), found.revision))
        elif store.same_path(path, job.path):
            build_jobs.append(job)
        else:
            build_jobs.append(replan(job, path, _template_of(job.plan)))

    clash = _same_file_name([j.path for j in build_jobs] + [r.path for r in reuse]
                            + [p for p in (chosen.layout_path, chosen.assembly_path) if p])
    if clash:
        return GearboxPlan(revision=n, name=name, refusal=clash, **empty)

    fields = dict(empty, build=tuple(build_jobs), reuse=tuple(reuse), part_of=part_of)
    if parts_only:
        return GearboxPlan(revision=n, name=name, revision_reason=reason, **fields)

    handles: Dict[str, str] = {}
    components = []
    for index, gear in enumerate(spec.gears, 1):
        if gear.id in part_of and gear.id in frames:
            handle = f"{layout.GEAR_HANDLE}{index}"
            handles[handle] = gear.id
            components.append((handle, part_of[gear.id], frames[gear.id]))
    try:
        layout_item: Union[BuildPlan, LayoutReuse] = chosen.layout_reuse or layout.layout_plan(
            shafts, part_tpl, chosen.layout_path)
        assembly = layout.assembly_plan(chosen.layout_path, components, asm_tpl, chosen.assembly_path)
    except ValueError as exc:
        return GearboxPlan(revision=n, name=name, refusal=str(exc), **empty)
    fields.update(layout_path=chosen.layout_path, assembly_path=chosen.assembly_path, shafts=shafts,
                  frames=frames, layout=layout_item, assembly=assembly, handles=handles)
    return GearboxPlan(revision=n, name=name, revision_reason=reason, **fields)


def _same_file_name(paths: Sequence[str]) -> str:
    """A sentence if two different paths of one build share a file name, else ``""``.

    SolidWorks keeps one open document per file name: a part of the same name
    from another folder is refused (``findings.SAME_NAME_OPEN_ERROR``, probe
    tier 7 ``add_component_same_name_elsewhere``, 2026 and 2024), so such a
    build could not insert both. It happens when a reused part sits in the
    folder of an earlier build and a part of the same name is to be made in
    the output folder now.
    """
    for i, a in enumerate(paths):
        for b in paths[:i]:
            if os.path.basename(a.replace("\\", "/")).lower() == os.path.basename(b.replace("\\", "/")).lower() \
                    and not store.same_path(a, b):
                return (f"This build would use both {b} and {a}, and SolidWorks cannot have two documents of one "
                        "file name open at once: give the gear a Part name, or change the output folder.")
    return ""


def replan(job: PartJob, path: str, template: str) -> PartJob:
    """The same part planned at another path (``<stem>_r<n>``): the strip's own ``plan_for`` again, so ``SaveAs``
    and any step naming the file follow; ``stem`` becomes the new file's stem."""
    return PartJob(_stem_of(path), path, tuple(job.gear_ids), job.spec, job.derived,
                   plan_for(job.spec, job.derived, template, path))


# -- what a build leaves ----------------------------------------------------------------------------


def _saved(result: Optional[BuildResult]) -> str:
    return result.saved if result is not None and result.ok and result.saved else ""


def _merge(record: LinkRecord, entry: PartEntry) -> None:
    for i, old in enumerate(record.parts):
        if store.same_path(old.path, entry.path):
            record.parts[i] = entry
            return
    record.parts.append(entry)


def finish_build(plan: GearboxPlan, result: GearboxResult, record: Optional[LinkRecord], *, workbook: str,
                 digest: str, written_by: str,
                 read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar,
                 stamp: Optional[str] = None) -> Finished:
    """The sidecars and record a build leaves, from what actually saved (Tk thread, after the worker).

    ``record`` is the record as read just before writing
    (``store.open_link_record``), or None for a fresh one. For each new part
    saved: a ``.gear.json`` by ``store.built_sidecar`` (keeping a previous
    one's id, read with ``read_sidecar``), and a ``PartEntry`` at this
    revision; reused parts keep their entries. As soon as the layout saved,
    the ``gearbox`` block is this revision's with ``layout`` and ``shafts``
    (decision 4), and ``assembly``, ``components`` (gear, part, the Name2
    from ``result.components``, its frame) once the assembly saved. A
    build-again moves the previous gearbox to ``earlier`` and its parts the
    new revision no longer uses with it. Parts are merged, never replaced by
    one batch. ``digest`` (the read this build came from) and ``last_built``
    are set only if something saved. Pure but for ``read_sidecar``.
    """
    stamp = stamp or store.now()
    out = Finished()
    rec = copy.deepcopy(record) if record is not None else LinkRecord(workbook=workbook)
    rec.workbook = workbook or rec.workbook
    saved_any = False

    for job, built in zip(plan.build, result.parts.built):
        path = _saved(built)
        if not path:
            continue
        saved_any = True
        kind = kind_for(job.spec)
        variables = [[v.name, v.expression_for(built.trig)] for v in kind.variables(job.spec, job.derived)]
        previous = read_sidecar(store.sidecar_path(path))
        out.sidecars.append((store.sidecar_path(path), store.built_sidecar(
            path, os.path.basename(path), kind=job.spec.kind, recipe=job.plan.recipe, spec=job.spec.to_dict(),
            derived=job.derived.to_dict(), variables=variables, features=list(built.features),
            dimensions=sorted(built.dimensions.values()), manual_steps=list(built.manual),
            template=_template_of(job.plan), trig=built.trig, written_by=written_by, previous=previous, stamp=stamp,
            workbook=workbook, workbook_gears=list(job.gear_ids))))
        _merge(rec, PartEntry(path=path, gears=list(job.gear_ids), revision=plan.revision, kind=job.spec.kind,
                              spec=job.spec.to_dict(), variables=variables, trig=built.trig))

    # Reused parts were checked live before anything was built (decision 3): they are this revision's too.
    for reused in plan.reuse:
        old = next((p for p in rec.parts if store.same_path(p.path, reused.path)), None)
        if old is not None:
            trig = old.trig
        else:
            sidecar = read_sidecar(store.sidecar_path(reused.path))
            trig = sidecar.record.trig if sidecar is not None else ""
        _merge(rec, PartEntry(path=old.path if old is not None else reused.path, gears=list(reused.gear_ids),
                              revision=old.revision if old is not None else reused.revision, kind=reused.spec.kind,
                              spec=reused.spec.to_dict(),
                              variables=[[v.name, v.expression_for(trig)] for v in reused.variables], trig=trig))

    layout_path = "" if plan.parts_only else (_saved(result.layout) or result.layout_reused)
    assembly_path = _saved(result.assembly) if layout_path else ""
    if _saved(result.layout) or assembly_path:
        saved_any = True
    if layout_path:
        old = rec.gearbox
        if old is not None and old.revision != plan.revision:
            in_use = list(plan.part_of.values())
            gone = [p for p in rec.parts if not _in(p.path, in_use)]
            rec.earlier.append(EarlierRevision(revision=old.revision, name=old.name, layout=old.layout,
                                               assembly=old.assembly, parts=[p.path for p in gone]))
            rec.parts = [p for p in rec.parts if _in(p.path, in_use)]
            old = None
        gearbox = old or GearboxRecord(revision=plan.revision, name=plan.name)
        gearbox.name = plan.name
        gearbox.layout = layout_path
        gearbox.part_template = plan.part_template
        gearbox.assembly_template = plan.assembly_template
        gearbox.shafts = [ShaftEntry(**asdict(s)) for s in plan.shafts]
        gearbox.meshes = [list(m) for m in plan.meshes]
        gearbox.built = stamp
        if assembly_path:
            gearbox.assembly = assembly_path
            gearbox.layout_component = result.components.get(layout.LAYOUT_HANDLE, "")
            gearbox.components = [
                ComponentEntry(gear=gear, part=plan.part_of[gear], name=result.components.get(handle, ""),
                               rotation=list(plan.frames[gear].rotation), at=list(plan.frames[gear].at))
                for handle, gear in plan.handles.items()]
            rec.assembly = assembly_path
            missing = [gear for handle, gear in plan.handles.items() if not result.components.get(handle)]
            if missing:
                out.notes.append(f"SolidWorks did not say what it named {', '.join(missing)} in the assembly, so "
                                 "Update SolidWorks cannot find them; build again to replace it.")
        rec.gearbox = gearbox

    if not saved_any:
        return out
    rec.digest = digest
    rec.last_built = stamp
    rec.written_by = written_by
    out.record = rec
    return out
