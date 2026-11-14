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
or one of its ``<stem>_r<k>`` (``workbook`` this workbook, or a path it had
before it was moved), hold the same part: the same plan and stem, and the
kind's variables' texts equal (fields a kind ignores — a spur gear's Hand, a
Part name equal to the default stem — are normalised first; decision 5). It
is then checked live, its globals and its features, before anything is built
(decision 3, review S6: ``swbuild.build_gearbox`` step 1).

A part Update SolidWorks changed and that is not saved (in
``record.unsaved``, or a ``.gear.json`` marked ``unsaved_since`` and not
newer since) is not reused, since the file on disk is not yet what the
record says; nor does it hold the build back (review B2, overruling W4
interface agreement 7): the part is made new at this build, and
:attr:`GearboxPlan.made_new` says so. Likewise a part the last build's
live check found not holding what the record says (``record.mismatched``,
its file no newer since): the worker would refuse it again on every press,
so it is made new instead (review B2's last corner). A new part whose own file name is
taken — by anything — gets the smallest free ``<stem>_r<k>`` (k ≥ 2), its
own suffix, whatever the gearbox's revision (review S5), and ``made_new``
says what was in the way. Only the layout part and the assembly move the
gearbox to another revision. A Part name that would be one of the gearbox's
own file names (``<Name>``, ``<Name>_Layout``, ``<Name>_r<n>`` …) is a
refusal naming its cell.

**A copied workbook** (review S1): a record written for another workbook
that is still on disk, or that the person said this one is a copy of, is
that workbook's (``store.record_owner``), so it is planned without — a
gearbox of this workbook's own, beside the other's files, sharing nothing —
and :attr:`GearboxPlan.foreign_record` names it. A record whose workbook is
gone is planned the same way until the person says this workbook was moved
or renamed from it (second review N1c; :attr:`GearboxPlan.foreign_gone`);
one the person said this session it is a copy of, while that workbook is
not there, is told apart for its sentence (:attr:`GearboxPlan.foreign_said`).

**The journal** (second review N4): a build's record gains, before the
worker starts, what it is about to make (``LinkRecord.pending``). A pending
part on disk with no ``.gear.json`` is that build's interrupted work, and
is planned for reuse like a part on record — the same plan, then checked
live — rather than called a file with no record; a pending layout part
likewise (checked live against the shafts now); a pending assembly is a
file this workbook made and never recorded, which the build goes beside.
The journal is never cleared wholesale (third review): an entry leaves it
only once it is on record or its file is not on disk
(:func:`settled_journal`), and a new build's journal is merged into the old
by path (:func:`merged_journal`), so a refused job, or a job abandoned and
then overtaken, never orphans what an interrupted build saved.
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
from . import layout, motion
from .assess import Assessment
from .build import PartJob
from .layout import REVISION_SUFFIX, Frame, ShaftLayout
from .motion import MotionPlan


@dataclass(frozen=True)
class PartReuse:
    """A part already built and unchanged, inserted again: ``variables`` (``kind.variables(spec, derived)``) are
    what it must hold exactly, and ``features`` every feature it must still have (from its ``.gear.json``; empty
    when there is none to say), both checked live; ``revision`` is the revision that made the file (this
    build's, for a part found only by its ``.gear.json``)."""

    path: str
    stem: str
    gear_ids: Tuple[str, ...]
    spec: GearSpec
    derived: Any
    variables: Tuple[GlobalVariable, ...]
    revision: int
    features: Tuple[str, ...] = ()
    journaled: bool = False        # found by the journal: no .gear.json beside it (one is written at the finish)
    recipe: str = ""               # the plan's recipe, template and manual steps, for that .gear.json
    template: str = ""
    manual: Tuple[str, ...] = ()


# Why a part is made new rather than reused, or under another name than its own (MadeNew.why).
UNSAVED = "unsaved"            # the matching part was changed by Update SolidWorks and is not saved
STALE = "stale"                # its file name holds a part built from this workbook for other values
OTHER_WORKBOOK = "other"       # its file name holds a part another workbook built
NO_RECORD = "no record"        # its file name holds a file with no record that this workbook built it
MISMATCHED = "mismatched"      # the matching part failed a live check, or lost Update's unsaved changes, and its
                               # file is no newer since


@dataclass(frozen=True)
class MadeNew:
    """A part this build makes new although a file stands in its way: ``old`` is that file — the matching part
    that is not saved (UNSAVED) or that the last build's live check found not holding what the record says
    (MISMATCHED), either of which would otherwise have been reused, or what holds the part's own file name
    (STALE, OTHER_WORKBOOK, NO_RECORD) — and ``new`` the path this build makes. ``workbook`` is the workbook the
    old file's ``.gear.json`` names (OTHER_WORKBOOK). :attr:`sentence` says it alone, for a log; the window
    words them together (``ui_text``)."""

    gear_ids: Tuple[str, ...]
    old: str
    new: str
    why: str
    workbook: str = ""

    @property
    def sentence(self) -> str:
        gears = _names(self.gear_ids)
        old, new = _file_name(self.old), _stem_of(self.new)
        where = os.path.dirname(self.old.replace("\\", "/")).replace("/", "\\")
        if self.why == UNSAVED:
            return (f"{_stem_of(self.old)} has changes from Update SolidWorks that are not saved, so its file is not "
                    f"yet the part {gears} needs: this build makes {gears}'s part new, as {new}.")
        if self.why == MISMATCHED:
            return (f"{_stem_of(self.old)} does not hold what the record says, as the last job in SolidWorks found, so "
                    f"this build makes {gears}'s part new, as {new}.")
        if self.why == STALE:
            return (f"{old} in {where} was built from this workbook for values {gears} no longer has, so {gears}'s "
                    f"part is made as {new}; nothing is overwritten.")
        if self.why == OTHER_WORKBOOK:
            return (f"{old} in {where} was built from {_file_name(self.workbook)}, so {gears}'s part is made as "
                    f"{new}; nothing is overwritten.")
        return (f"{old} is already in {where}, and there is no record that this workbook built it (a build that was "
                f"interrupted can leave such a file), so {gears}'s part is made as {new}; nothing is overwritten.")


@dataclass(frozen=True)
class LayoutReuse:
    """A layout part already saved (an assembly that failed after it), inserted again once it is checked live
    to hold ``variables`` exactly and every name in ``features`` (``layout.layout_globals`` and
    ``layout.layout_features`` of the recorded shafts)."""

    path: str
    variables: Tuple[GlobalVariable, ...]
    features: Tuple[str, ...]
    journaled: bool = False        # an interrupted build's, found by the journal rather than continued on record


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
    path, two new paths the same, a Part name that is one of the gearbox's own
    file names), in which case the plans may be partial and must not be run.
    ``revision_reason`` is ``""`` for revision 0 or a continued revision, else
    why this revision (``Reducer_12to1.SLDASM is already there, …``): only
    the layout part and the assembly move a build to another revision.
    ``made_new``: the new parts made although a file stood in the way, and
    why (:class:`MadeNew`); :attr:`unsaved_made_new` those made new because
    the matching part is not saved — a build never waits for a save.
    ``foreign_record``: the other workbook whose record sits beside this one
    (a copy), which this plan was made without; ``""`` normally.
    ``foreign_gone``: that workbook is not there any more and nobody has said
    whether this one was moved from it (``store.UNSURE``): planned as a copy
    until the person answers. ``foreign_said``: that workbook is not there
    any more and the person said this session that this one is a copy of it
    (``store.copy_by_answer``).

    W5 (Agent B fills them; W5-INTERFACES.md): ``motion`` is the turning
    assembly's :class:`~workbook.motion.MotionPlan` when ``assembly`` is the turning
    plan (``motion.motion_assembly_plan``), None when ``assembly`` is W4's
    static plan or there is no assembly. ``static_reason`` is ``""`` with a
    motion plan and in a parts-only or refused plan; with a static assembly
    planned because a W5 finding is missing (``motion.motion_reason()``), it
    is that sentence. There is no static fallback plan: a turning assembly
    SolidWorks refuses is not replaced by a static one (W5-DECISIONS,
    answer 1), so ``build_kwargs`` is as in W4. ``plan.motion`` is the one
    source of the record's ``GearboxRecord.kind``: ``finish_build`` writes
    MOTION when it is set and STATIC when not; a non-empty
    ``GearboxResult.kind`` must agree, a disagreement is a sentence in
    ``Finished.notes``, and an empty one is never written.
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
    made_new: Tuple[MadeNew, ...] = ()
    foreign_record: str = ""
    foreign_gone: bool = False
    foreign_said: bool = False
    motion: Optional[MotionPlan] = None
    static_reason: str = ""

    @property
    def parts_only(self) -> bool:
        return self.layout is None and self.assembly is None

    @property
    def unsaved_made_new(self) -> Tuple[MadeNew, ...]:
        """The parts made new because the part that matched was changed by Update SolidWorks and is not saved."""
        return tuple(m for m in self.made_new if m.why == UNSAVED)

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
            "reuse": [DocumentValues(r.path, tuple(r.variables), tuple(r.features)) for r in self.reuse],
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


def _file_name(path: str) -> str:
    return os.path.basename(str(path).replace("\\", "/"))


def _names(items: Sequence[str]) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


def _revised(path: str, k: int) -> str:
    """``C:\\P\\Gear_m1.5_N68.SLDPRT`` with suffix 2 -> ``C:\\P\\Gear_m1.5_N68_r2.SLDPRT``."""
    stem, ext = os.path.splitext(path)
    return f"{stem}{REVISION_SUFFIX}{k}{ext}"


def _in(path: str, paths) -> bool:
    return any(store.same_path(path, p) for p in paths)


@dataclass
class _Found:
    path: str
    revision: int
    features: Tuple[str, ...] = ()
    journaled: bool = False


class _Parts:
    """What the record and the sidecars say about the jobs' parts, asked once per revision tried.

    ``workbook`` is this workbook's path and ``former`` the paths it had
    before it was moved or renamed (``record.moved_from`` and a record's own
    old ``workbook``), each counted only while no file is there; a sidecar
    naming any of them is this workbook's (W4 review nit: after Locate…, its
    parts are still found)."""

    def __init__(self, record: Optional[LinkRecord], workbook: str, exists: Callable[[str], bool],
                 read_sidecar: Callable[[str], Optional[Sidecar]], mtime: Callable[[str], float],
                 former: Sequence[str] = (), journal: Sequence[PartEntry] = ()) -> None:
        self.record = record
        self.workbook = workbook
        self.exists = exists
        self.read_sidecar = read_sidecar
        self.mtime = mtime
        self.former = [p for p in former if p and not store.same_path(p, workbook) and not exists(p)]
        self.journal = list(journal)
        self._sidecars: Dict[str, Optional[Sidecar]] = {}
        self.unsaved = list(record.unsaved) if record is not None else []

    def sidecar(self, path: str) -> Optional[Sidecar]:
        key = path.lower()
        if key not in self._sidecars:
            self._sidecars[key] = self.read_sidecar(store.sidecar_path(path)) if self.exists(path) else None
        return self._sidecars[key]

    def ours(self, path: str) -> bool:
        """Whether the file's record beside it says this workbook built it (by its path now — or another path to
        the same file, second review N1a — or one it had before it was moved)."""
        sidecar = self.sidecar(path)
        if sidecar is None or not self.workbook:
            return False
        built_from = sidecar.record.workbook
        return store.same_file(built_from, self.workbook) or _in(built_from, self.former)

    def journaled(self, path: str) -> Optional[PartEntry]:
        """The journal's entry for a file on disk with no ``.gear.json`` beside it: an interrupted build of this
        workbook's saved it and never put it on record (``LinkRecord.pending``). None otherwise — a pending path
        not on disk is dropped, and one with a ``.gear.json`` is judged by it."""
        if not self.journal or not self.exists(path) or self.sidecar(path) is not None:
            return None
        return next((e for e in self.journal if store.same_path(e.path, path)), None)

    def not_saved(self, path: str) -> bool:
        """Whether Update SolidWorks changed the part and the file does not hold it yet: on the record's
        ``unsaved``, or its ``.gear.json`` marked ``unsaved_since`` and the file no newer than that."""
        if _in(path, self.unsaved):
            return True
        sidecar = self.sidecar(path)
        mark = sidecar.record.unsaved_since if sidecar is not None else 0.0
        return bool(mark) and not store.saved_since(path, mark, self.mtime)

    def mismatched(self, path: str) -> bool:
        """Whether the last build's live check found the file not holding what the record says
        (``record.mismatched``), and the file is no newer since."""
        then = next((t for p, t in (self.record.mismatched if self.record is not None else {}).items()
                     if store.same_path(p, path)), None)
        return then is not None and not store.saved_since(path, then, self.mtime)

    def blocked(self, path: str) -> str:
        """Why a part that matches is still not reused: UNSAVED, MISMATCHED, or ``""``."""
        return UNSAVED if self.not_saved(path) else MISMATCHED if self.mismatched(path) else ""

    def features(self, path: str) -> Tuple[str, ...]:
        """The features the part's ``.gear.json`` lists, for the live check (review S6); ``()`` without one."""
        sidecar = self.sidecar(path)
        return tuple(sidecar.record.features) if sidecar is not None else ()

    def entries(self, revision: int) -> List[PartEntry]:
        """The record's parts reuse may take (decision 2): the current revision's, and any this revision made
        already in an attempt whose assembly was not made."""
        if self.record is None:
            return []
        out = list(self.record.current_parts())
        out.extend(p for p in self.record.parts if p.revision == revision and p not in out)
        return out

    def names(self, job: PartJob) -> List[str]:
        """The job's own path, then each ``<stem>_r<k>`` (k = 2, 3, …) on disk, up to the first that is not."""
        out = [job.path]
        for k in range(2, MAX_REVISION + 1):
            path = _revised(job.path, k)
            if not self.exists(path):
                break
            out.append(path)
        return out

    def find(self, job: PartJob, revision: int) -> Tuple[Optional[_Found], Tuple[str, str]]:
        """A part this job may reuse, and — when none — the first match that may not be reused and why
        (:meth:`blocked`), else ``("", "")``."""
        held = ("", "")
        for entry in self.entries(revision):
            if not _matches(entry.spec, entry.variables, entry.trig, job) or not self.exists(entry.path):
                continue
            why = self.blocked(entry.path)
            if why:
                held = held if held[0] else (entry.path, why)
                continue
            return _Found(entry.path, entry.revision, self.features(entry.path)), ("", "")
        for path in self.names(job):
            if not self.exists(path):
                continue
            entry = self.journaled(path)
            if entry is not None:
                if entry.kind in (layout.LAYOUT_KIND, layout.ASSEMBLY_KIND) or not _matches(entry.spec, (), "", job):
                    continue
                why = self.blocked(path)
                if why:
                    held = held if held[0] else (path, why)
                    continue
                return _Found(path, entry.revision, (), journaled=True), ("", "")
            if not self.ours(path):
                continue
            record = self.sidecar(path).record
            if not _matches(record.spec, record.variables, record.trig, job):
                continue
            why = self.blocked(path)
            if why:
                held = held if held[0] else (path, why)
                continue
            on_record = next((p for p in (self.record.parts if self.record else []) if store.same_path(p.path, path)),
                             None)
            return _Found(path, on_record.revision if on_record else revision, self.features(path)), ("", "")
        return None, held

    def free_name(self, job: PartJob, claimed: Sequence[str]) -> str:
        """The job's own path if nothing is there and no other file of this build takes it, else the smallest free
        ``<stem>_r<k>`` (review S5: a part's own suffix, whatever the gearbox's revision); ``""`` if all are
        taken."""
        for path in [job.path] + [_revised(job.path, k) for k in range(2, MAX_REVISION + 1)]:
            if not self.exists(path) and not _in(path, claimed):
                return path
        return ""

    def occupant(self, path: str) -> Tuple[str, str]:
        """Why a file at a job's own path is not that job's part: (MadeNew.why, the workbook its record names). A
        file the journal names is this workbook's, made for other values (STALE)."""
        sidecar = self.sidecar(path)
        if (sidecar is not None and self.ours(path)) or self.journaled(path) is not None:
            return STALE, ""
        if sidecar is not None and sidecar.record.workbook:
            return OTHER_WORKBOOK, sidecar.record.workbook
        return NO_RECORD, ""


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


def _gearbox_named(a: Assessment, jobs: Sequence[PartJob]) -> str:
    """The refusal for a Part name that would be one of the gearbox's own file names, naming each cell (review
    S5, S4.9: such a gear was built as ``Reducer_12to1_Layout.SLDPRT`` beside the next revision's layout), or
    ``""``. Any revision's names count — ``<Name>``, ``<Name>_Layout``, ``<Name>_r<n>``, ``<Name>_r<n>_Layout`` —
    and the assembly's too: SolidWorks may title a part and an assembly of one stem alike."""
    spec = a.spec
    name0, layout0 = layout.stems(spec.box.name, 0)
    pattern = re.compile(re.escape(name0) + "(" + re.escape(REVISION_SUFFIX) + r"\d+)?("
                         + re.escape(layout.LAYOUT_SUFFIX) + ")?", re.IGNORECASE)
    found = []
    for job in jobs:
        if not pattern.fullmatch(job.stem):
            continue
        for gear_id in job.gear_ids:
            gear = spec.gear(gear_id)
            column = "part_name" if "part_name" in spec.columns.get("Gears", {}) else "id"
            cell = spec.cell("Gears", gear.row, column) if gear is not None else f"Gears {gear_id}"
            found.append(f"{cell}: {gear_id}'s part would be {job.stem}{layout.PART_EXTENSION}")
    if not found:
        return ""
    what = "the layout part's" if any(f.lower().endswith(layout.LAYOUT_SUFFIX.lower() + layout.PART_EXTENSION.lower())
                                      for f in found) else "the assembly's"
    them = "it" if len(found) == 1 else "them"
    return (f"{'; '.join(found)}, which is a name of the gearbox's own files ({name0}{layout.ASSEMBLY_EXTENSION}, "
            f"{layout0}{layout.PART_EXTENSION} and their revisions; here {what}), so nothing is built: give {them} "
            f"another Part name.")


@dataclass
class _Attempt:
    revision: int
    obstacle: str = ""
    refusal: str = ""
    layout_path: str = ""
    assembly_path: str = ""
    layout_reuse: Optional[LayoutReuse] = None
    parts: List[Tuple[PartJob, Optional[_Found], str]] = field(default_factory=list)   # job, reuse, new path
    made_new: List[MadeNew] = field(default_factory=list)


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
            journaled = not continued and parts.journaled(attempt.layout_path) is not None
            if continued and parts.mismatched(attempt.layout_path):
                attempt.obstacle = (f"{layout_name} was saved by a build whose assembly was not made, but the last "
                                    "build found it no longer holds what was recorded, so it is not reused.")
                return attempt
            if journaled and parts.mismatched(attempt.layout_path):
                attempt.obstacle = (f"{layout_name} was saved by a build that was interrupted before it was put on "
                                    "record, but the last build found it does not hold this workbook's layout, so it is "
                                    "not reused.")
                return attempt
            if continued and _same_layout(_recorded_shafts(continuing), shafts):
                attempt.layout_reuse = LayoutReuse(attempt.layout_path, layout.layout_globals(shafts),
                                                   layout.layout_features(shafts))
            elif journaled:
                # An interrupted build's own layout part: what it holds is not on record, so the live check decides
                # whether it is the layout the shafts now want (every global and every plane and axis).
                attempt.layout_reuse = LayoutReuse(attempt.layout_path, layout.layout_globals(shafts),
                                                   layout.layout_features(shafts), journaled=True)
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
            if parts.journaled(attempt.assembly_path) is not None:
                attempt.obstacle = (f"{os.path.basename(attempt.assembly_path)} was saved by a build that was "
                                    "interrupted before it was put on record, and a build never overwrites a file.")
            else:
                attempt.obstacle = (f"{os.path.basename(attempt.assembly_path)} is already in {folder}, and a build "
                                    "never overwrites a file.")
            return attempt
        new_paths.append(attempt.assembly_path)
    full = []
    # Every part to reuse, then every new part's own file name, is claimed before any suffix is handed out (W4
    # review N3): a suffix never takes the name another row's Part name asks for, and which part gets which name
    # does not depend on the order of the rows. Own names are distinct (plan_parts refuses two gears of one file
    # name, naming the cell), and a name of the gearbox's own was refused above.
    found_of = {id(job): parts.find(job, n) for job in jobs}
    claimed = list(new_paths) + [f.path for f, _ in found_of.values() if f is not None]
    claimed += [job.path for job in jobs if found_of[id(job)][0] is None and not exists(job.path)
                and not _in(job.path, claimed)]
    for job in jobs:
        found, (held, why) = found_of[id(job)]
        if found is not None:
            attempt.parts.append((job, found, found.path))
            continue
        path = job.path if not exists(job.path) else parts.free_name(job, claimed)
        if not path:
            full.append(job)
            continue
        if held:
            attempt.made_new.append(MadeNew(tuple(job.gear_ids), held, path, why))
        elif not store.same_path(path, job.path):
            why, workbook = parts.occupant(job.path)
            attempt.made_new.append(MadeNew(tuple(job.gear_ids), job.path, path, why, workbook))
        attempt.parts.append((job, None, path))
        if not _in(path, claimed):
            claimed.append(path)
        new_paths.append(path)
    if full:
        last = [_file_name(_revised(j.path, MAX_REVISION)) for j in full]
        attempt.refusal = (f"{_names([_file_name(j.path) for j in full])} and every name after "
                           f"{'it' if len(full) == 1 else 'them'} up to {_names(last)} are already in {folder}, so "
                           "nothing is built: change the output folder.")
        return attempt
    clashes = sorted({_file_name(p) for i, p in enumerate(new_paths)
                      if any(store.same_path(p, other) for other in new_paths[:i])})
    if clashes:
        attempt.refusal = (f"Two of the files this build would make would both be {_names(clashes)}, so nothing is "
                           "built: give the gears Part names that are not the gearbox's.")
    return attempt


@store.in_one_pass
def plan_gearbox(a: Assessment, record: Optional[LinkRecord], *, part_template: str = "",
                 assembly_template: str = "", parts_only: bool = False,
                 exists: Callable[[str], bool] = os.path.exists,
                 read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar,
                 mtime: Callable[[str], float] = os.path.getmtime) -> GearboxPlan:
    """Plan the next build from an assessment that passed its gate, at the revision the module docstring picks.

    The caller has already checked the window's own state and
    ``a.lay_out_refusal()`` (or, with ``parts_only``, ``a.build_refusal()``);
    this adds only what the file system and the record decide, as
    ``refusal``. Templates: the Box sheet's, else the given (the strip's).
    ``record`` is the planning read (``store.read_link_record``), or None.
    The worker repeats every existence check against the race. ``mtime``
    reads a part file's time, to tell whether a ``.gear.json`` marked
    unsaved is saved since.

    A revision is tried in turn — the one a failed assembly left to continue,
    then 0, 2, 3, … less those on record — until its layout part and
    assembly are free, with a sentence saying why (``revision_reason``),
    never a dead end (decision 6). Each new part takes its own file name or,
    when that is taken, its own smallest free ``<stem>_r<k>``
    (``made_new``).
    """
    spec = a.spec
    folder = a.folder
    part_tpl = spec.box.part_template or part_template
    asm_tpl = spec.box.assembly_template or assembly_template
    here = str(a.read.source_path or spec.source_path or "")
    owner, other = store.record_owner(record, here, exists)
    foreign = other if owner != store.OURS else ""
    said = bool(foreign) and store.copy_by_answer(record, here, exists)
    journal = _journal_of(record, here, ours=not foreign)
    if foreign:
        record = None                       # a copy: the record and its files are the other workbook's (S1, N1)
    former = ([record.workbook] + list(record.moved_from)) if record is not None else []
    workbook = here or (record.workbook if record is not None else "")
    jobs = list(a.parts.jobs)
    meshes = tuple((m.a, m.b) for m in spec.meshes)
    empty = dict(folder=folder, layout_path="", assembly_path="", build=(), reuse=(), shafts=(), frames={},
                 layout=None, assembly=None, handles={}, part_of={}, part_template=part_tpl,
                 assembly_template=asm_tpl, meshes=meshes, foreign_record=foreign,
                 foreign_gone=owner == store.UNSURE, foreign_said=said)
    name0 = layout.stems(spec.box.name, 0)[0]

    named = _gearbox_named(a, jobs)
    if named:
        return GearboxPlan(revision=0, name=name0, refusal=named, **empty)

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

    parts = _Parts(record, workbook, exists, read_sidecar, mtime, former, journal)
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
                                   _variables_of(job), found.revision, found.features, found.journaled,
                                   job.plan.recipe, _template_of(job.plan),
                                   tuple(op.text for op in job.plan.manual_steps())))
        elif store.same_path(path, job.path):
            build_jobs.append(job)
        else:
            build_jobs.append(replan(job, path, _template_of(job.plan)))

    clash = _same_file_name([j.path for j in build_jobs] + [r.path for r in reuse]
                            + [p for p in (chosen.layout_path, chosen.assembly_path) if p])
    if clash:
        return GearboxPlan(revision=n, name=name, refusal=clash, **empty)

    fields = dict(empty, build=tuple(build_jobs), reuse=tuple(reuse), part_of=part_of,
                  made_new=tuple(chosen.made_new))
    if parts_only:
        return GearboxPlan(revision=n, name=name, revision_reason=reason, **fields)

    handles: Dict[str, str] = {}
    components = []
    for index, gear in enumerate(spec.gears, 1):
        if gear.id in part_of and gear.id in frames:
            handle = f"{layout.GEAR_HANDLE}{index}"
            handles[handle] = gear.id
            components.append((handle, part_of[gear.id], frames[gear.id]))
    # W5: the turning assembly whenever every finding it needs is settled; else W4's static one, and why (D1's
    # static-by-necessity case, said before Build). A continued revision is planned the same way.
    static_reason = motion.motion_reason()
    turning: Optional[MotionPlan] = None
    try:
        layout_item: Union[BuildPlan, LayoutReuse] = chosen.layout_reuse or layout.layout_plan(
            shafts, part_tpl, chosen.layout_path)
        if static_reason:
            assembly = layout.assembly_plan(chosen.layout_path, components, asm_tpl, chosen.assembly_path)
        else:
            turning = motion.motion_plan(spec, a.report, frames)
            assembly = motion.motion_assembly_plan(chosen.layout_path, components,
                                                   {gear: handle for handle, gear in handles.items()}, turning,
                                                   asm_tpl, chosen.assembly_path)
    except ValueError as exc:
        return GearboxPlan(revision=n, name=name, refusal=str(exc), **empty)
    fields.update(layout_path=chosen.layout_path, assembly_path=chosen.assembly_path, shafts=shafts,
                  frames=frames, layout=layout_item, assembly=assembly, handles=handles, motion=turning,
                  static_reason=static_reason)
    return GearboxPlan(revision=n, name=name, revision_reason=reason, **fields)


def _journal_of(record: Optional[LinkRecord], here: str, ours: bool) -> List[PartEntry]:
    """The journal a plan may use: ``record.pending`` when this workbook's build wrote it (``pending_for`` this
    workbook, or — the record being this workbook's — a path it had before it was moved)."""
    if record is None or not record.pending:
        return []
    names = [here] + (list(record.moved_from) + [record.workbook] if ours else [])
    return list(record.pending) if any(store.same_file(record.pending_for, n) for n in names if n) else []


def on_record(record: Optional[LinkRecord], path: str) -> bool:
    """Whether ``record`` lists ``path``: among its parts, or as a gearbox's layout part or assembly, this
    revision's or an earlier one's."""
    if record is None or not path:
        return False
    listed = [p.path for p in record.parts] + [record.assembly]
    if record.gearbox is not None:
        listed += [record.gearbox.layout, record.gearbox.assembly]
    for earlier in record.earlier:
        listed += [earlier.layout, earlier.assembly] + list(earlier.parts)
    return _in(path, [p for p in listed if p])


def settled_journal(entries: Sequence[PartEntry], record: Optional[LinkRecord], *,
                    exists: Callable[[str], bool] = os.path.exists,
                    read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar,
                    written: Sequence[str] = ()) -> List[PartEntry]:
    """What stays in a journal: every entry whose file is on disk and not yet on record (third W4 review). An
    entry leaves only once it is on record — ``record`` lists it (:func:`on_record`), or its ``.gear.json`` is
    written (``written``: the sidecar paths a finish is about to write) or already beside it — or once its file is
    not on disk. A file saved by an interrupted build therefore stays this workbook's however many jobs are
    refused, fail their live check or are abandoned after it."""
    out = []
    for entry in entries:
        if not entry.path or not exists(entry.path) or on_record(record, entry.path):
            continue
        sidecar = store.sidecar_path(entry.path)
        if _in(sidecar, written) or read_sidecar(sidecar) is not None:
            continue
        out.append(entry)
    return out


def merged_journal(record: Optional[LinkRecord], entries: Sequence[PartEntry], workbook: str, *,
                   exists: Callable[[str], bool] = os.path.exists,
                   read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar) -> List[PartEntry]:
    """The journal a build writes before it starts: its own ``entries`` (:func:`journal`), then every entry of
    this workbook's journal already in ``record`` for another path that is still unsettled (:func:`settled_journal`)
    — merged by path, never replacing the old journal (third W4 review). A journal another workbook's build wrote
    (``pending_for``) is not this one's, and is not carried into it."""
    ours = record is not None and store.record_owner(record, workbook, exists)[0] == store.OURS
    old = settled_journal(_journal_of(record, workbook, ours), record, exists=exists, read_sidecar=read_sidecar)
    return list(entries) + [e for e in old if not any(store.same_path(e.path, n.path) for n in entries)]


def journal(plan: GearboxPlan) -> List[PartEntry]:
    """What a build is about to make, for ``LinkRecord.pending`` (written before the worker starts): each new
    part (path, gears, revision, kind, spec), the new layout part and the assembly (``kind`` ``layout`` and
    ``assembly``), and what it reuses that only the journal knows (no ``.gear.json`` yet), so a build interrupted
    again keeps them."""
    out = [PartEntry(path=j.path, gears=list(j.gear_ids), revision=plan.revision, kind=j.spec.kind,
                     spec=j.spec.to_dict()) for j in plan.build]
    out += [PartEntry(path=r.path, gears=list(r.gear_ids), revision=r.revision, kind=r.spec.kind,
                      spec=r.spec.to_dict()) for r in plan.reuse if r.journaled]
    if plan.layout is not None and (not isinstance(plan.layout, LayoutReuse) or plan.layout.journaled):
        out.append(PartEntry(path=plan.layout_path, revision=plan.revision, kind=layout.LAYOUT_KIND))
    if plan.assembly is not None and plan.assembly_path:
        out.append(PartEntry(path=plan.assembly_path, revision=plan.revision, kind=layout.ASSEMBLY_KIND))
    return out


def _same_file_name(paths: Sequence[str]) -> str:
    """A sentence naming every pair of different paths of one build that share a file name, else ``""``.

    SolidWorks keeps one open document per file name: a part of the same name
    from another folder is refused (``findings.SAME_NAME_OPEN_ERROR``, probe
    tier 7 ``add_component_same_name_elsewhere``, 2026 and 2024), so such a
    build could not insert both. It happens when a reused part sits in the
    folder of an earlier build and a part of the same name is to be made in
    the output folder now.
    """
    pairs = []
    for i, a in enumerate(paths):
        for b in paths[:i]:
            if _file_name(a).lower() == _file_name(b).lower() and not store.same_path(a, b):
                pairs.append(f"both {b} and {a}")
    if not pairs:
        return ""
    return (f"This build would use {'; '.join(pairs)}, and SolidWorks cannot have two documents of one file name "
            "open at once: give the gear a Part name, or change the output folder.")


def replan(job: PartJob, path: str, template: str) -> PartJob:
    """The same part planned at another path (``<stem>_r<n>``): the strip's own ``plan_for`` again, so ``SaveAs``
    and any step naming the file follow; ``stem`` becomes the new file's stem."""
    return PartJob(_stem_of(path), path, tuple(job.gear_ids), job.spec, job.derived,
                   plan_for(job.spec, job.derived, template, path))


# -- what a build leaves ----------------------------------------------------------------------------


def _saved(result: Optional[BuildResult]) -> str:
    return result.saved if result is not None and result.ok and result.saved else ""


def _drop(marks: Dict[str, float], path: str) -> bool:
    """Take every entry for ``path`` out of a path -> time mark; whether there was one."""
    keys = [k for k in marks if store.same_path(k, path)]
    for key in keys:
        del marks[key]
    return bool(keys)


def _merge(record: LinkRecord, entry: PartEntry) -> None:
    for i, old in enumerate(record.parts):
        if store.same_path(old.path, entry.path):
            record.parts[i] = entry
            return
    record.parts.append(entry)


_KIND_WORDS = {motion.MOTION: "to turn", motion.STATIC: "static"}


def _record_kind(gearbox: GearboxRecord, plan: GearboxPlan, result: GearboxResult, out: Finished) -> None:
    """A saved assembly's kind and mates, from the plan alone (W5-INTERFACES ``finish_build``): MOTION with the
    plan's mates, unmated meshes, fixed gears and drag gears when ``plan.motion`` is set, else STATIC with the
    plan's ``static_reason``. A non-empty ``result.kind`` that disagrees is a note; an empty one says nothing."""
    turning = plan.motion
    kind = motion.MOTION if turning is not None else motion.STATIC
    gearbox.kind = kind
    if turning is not None:
        gearbox.mates = [motion.mate_entry(m) for m in turning.mates]
        gearbox.unmated = [list(pair) for pair in turning.unmated]
        gearbox.fixed = list(turning.fixed)
        gearbox.drag = list(turning.drag)
        gearbox.static_reason = ""
    else:
        gearbox.mates, gearbox.unmated, gearbox.fixed, gearbox.drag = [], [], [], []
        gearbox.static_reason = plan.static_reason
    reported = getattr(result, "kind", "") or ""
    if reported and reported != kind:
        said = _KIND_WORDS.get(reported, repr(reported))
        out.notes.append(f"The job reported the assembly as built {said}, but it was planned {_KIND_WORDS[kind]}; "
                         "the record keeps what was planned.")


def finish_build(plan: GearboxPlan, result: GearboxResult, record: Optional[LinkRecord], *, workbook: str,
                 digest: str, written_by: str,
                 read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar,
                 stamp: Optional[str] = None,
                 mtime: Callable[[str], float] = os.path.getmtime,
                 exists: Callable[[str], bool] = os.path.exists) -> Finished:
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
    one batch. ``last_built`` is set if something saved; ``digest`` (the read
    this build came from) only if everything planned saved (``result.ok``):
    it says SolidWorks wholly matches that read, and a build that stopped
    after its parts, or after its layout, has no assembly to match it, so the
    record keeps the digest it had (``""`` for a first build) and the header
    says the workbook changed since it was built rather than "built from this
    version". A clash leaves ``ok`` True: what was built is this read's.

    A plan made for a copied workbook (``plan.foreign_record``) finishes into
    a fresh record, keeping only the copy's own Export state: the record that
    came with the copy is the other workbook's, and is written over only now,
    when this workbook has built something of its own (review S1). A record
    whose ``workbook`` is an older path of this workbook is adopted: the
    field is set and the old path kept in ``moved_from``.

    A build that stopped at the live check (``result.mismatched``: nothing
    made) still leaves a record: each such document goes into
    ``record.mismatched`` with its file's time as the worker read it
    (``result.mtimes``; else ``mtime(path)`` now), so the next plan makes
    that part new rather than fail the same check on every press (review
    B2's last corner). A document a build checked and reused drops out of it.
    Pure but for ``read_sidecar`` and ``mtime``.

    Second review: a document the job loaded from its file
    (``result.opened``) loses its unsaved marks, record and ``.gear.json``
    (N2); one marked unsaved that was not open when the job began
    (``result.open_before``) lost Update's changes and becomes mismatched.
    The journal (``record.pending``, N4) keeps only what is still not on
    record and on disk (:func:`settled_journal`, third review: never
    cleared wholesale; ``exists`` reads the disk) — written back even when
    nothing was made — and a reused part only the journal knew gets its
    ``.gear.json`` now, in the unit the live check found (``result.held``).
    A journaled part that failed its live check stays in the journal, so it
    stays known as this workbook's, with its mismatched mark. The record of a copy is told by ``store.same_file``,
    so another path to this workbook is never taken for a copy (N1a). The
    window writes ``finished.record`` beside this workbook — even when it is
    the other workbook's record with the journal taken out.

    W5 (W5-INTERFACES ``finish_build``): once the assembly saved, the
    gearbox's ``kind`` comes from the plan alone — MOTION with the plan's
    mates, unmated meshes, fixed gears and drag gears when ``plan.motion``
    is set, else STATIC with ``plan.static_reason`` — and a non-empty
    ``result.kind`` that disagrees is a sentence in ``notes``. Whenever the
    assembly was attempted, ``mate_problems`` are what SolidWorks refused or
    flagged (``result.assembly.mate_problems``) and ``mate_problems_digest``
    the read they came from (``""`` with none). A refused train thus leaves
    W4's continued revision — parts and layout on record, ``assembly``
    ``""`` — with the problems; one refused again with nothing made changes
    only those two fields, and is written only when they change.
    """
    stamp = stamp or store.now()
    out = Finished()
    other = None                           # the other workbook's record a copy's build was planned without
    if record is not None and plan.foreign_record and store.same_file(record.workbook, plan.foreign_record):
        other = record
        record = LinkRecord(workbook=workbook, own_digest=record.own_digest, recalc=record.recalc)
    rec = copy.deepcopy(record) if record is not None else LinkRecord(workbook=workbook)
    store.adopt(rec, workbook)
    saved_any = False
    # This workbook's journal (N4): in its own record, or — a copy's — in the record that came with it. Settled at
    # the end, entry by entry, against what this finish puts on record (third review).
    source = other if other is not None else rec
    mine = _journal_of(source, workbook, ours=other is None)

    marked_any = False
    for path in result.checked:            # found, live, to hold what it should: reusable again
        for marked in [p for p in rec.mismatched if store.same_path(p, path)]:
            del rec.mismatched[marked]
            marked_any = True
    # A document loaded from its file holds in memory what the file holds: changes Update left unsaved in it are
    # gone, so its unsaved marks go, and what the check found decides (N2). A document marked unsaved that was not
    # open when the job began lost those changes when it was closed; this build did not open it, so its file still
    # holds what it held before Update, not what the record says: the mark becomes a mismatched one.
    unmark = list(result.opened)
    for path in result.opened:
        marked_any = _drop(rec.unsaved, path) or marked_any
    if result.open_before is not None:
        for path, then in list(rec.unsaved.items()):
            if _in(path, result.open_before):
                continue
            del rec.unsaved[path]
            marked_any = True
            if store.saved_since(path, then, mtime):
                continue                   # saved since: the mark goes, as store.clear_saved would take it
            _drop(rec.mismatched, path)
            rec.mismatched[path] = then
            unmark.append(path)
    for path in unmark:
        sidecar = read_sidecar(store.sidecar_path(path))
        if sidecar is not None and sidecar.record.unsaved_since:
            out.sidecars.append((store.sidecar_path(path), store.unmarked(sidecar)))
    for path, _why in result.mismatched:
        then = next((t for p, t in result.mtimes.items() if store.same_path(p, path)), None)
        if then is None:
            try:
                then = float(mtime(path))
            except (OSError, ValueError, TypeError):
                out.notes.append(f"{os.path.basename(path)} could not be found on disk to note that it does not "
                                 "hold what was recorded.")
                continue
        for marked in [p for p in rec.mismatched if store.same_path(p, path)]:
            del rec.mismatched[marked]
        rec.mismatched[path] = then
        marked_any = True

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
        if old is None and not _in(reused.path, result.checked):
            # Not on record, and not found live to hold what it should (it failed the check, or the job never
            # reached it): not put on record now. A journaled one stays in the journal, this workbook's (third
            # review), and its mismatched mark, if any, decides the next plan.
            continue
        sidecar = None if old is not None else read_sidecar(store.sidecar_path(reused.path))
        held = next((t for p, t in result.held.items() if store.same_path(p, reused.path)), "")
        if old is not None:
            trig = old.trig or held
        else:
            trig = (sidecar.record.trig if sidecar is not None else "") or held
        if old is None and sidecar is None and _in(reused.path, result.checked):
            # Known only to the journal (an interrupted build saved it, its .gear.json never written): checked live
            # now, so it gets one, as a part this build made would (N4).
            out.sidecars.append((store.sidecar_path(reused.path), store.built_sidecar(
                reused.path, os.path.basename(reused.path), kind=reused.spec.kind, recipe=reused.recipe,
                spec=reused.spec.to_dict(), derived=reused.derived.to_dict(),
                variables=[[v.name, v.expression_for(trig)] for v in reused.variables], features=[], dimensions=[],
                manual_steps=list(reused.manual), template=reused.template, trig=trig, written_by=written_by,
                stamp=stamp, workbook=workbook, workbook_gears=list(reused.gear_ids))))
        _merge(rec, PartEntry(path=old.path if old is not None else reused.path, gears=list(reused.gear_ids),
                              revision=old.revision if old is not None else reused.revision, kind=reused.spec.kind,
                              spec=reused.spec.to_dict(),
                              variables=[[v.name, v.expression_for(trig)] for v in reused.variables], trig=trig))

    layout_path = "" if plan.parts_only else (_saved(result.layout) or result.layout_reused)
    assembly_path = _saved(result.assembly) if layout_path else ""
    if _saved(result.layout) or assembly_path:
        saved_any = True
    problems_noted = False
    before: Optional[GearboxRecord] = None
    if layout_path:
        old = rec.gearbox
        before = copy.deepcopy(old) if old is not None and old.revision == plan.revision else None
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
            _record_kind(gearbox, plan, result, out)
        if result.assembly is not None:
            # The assembly was attempted: what SolidWorks refused or flagged, and the read it came from, so the
            # footer never invites a retry of an unchanged workbook (W5-DECISIONS answer 1).
            problems = list(getattr(result.assembly, "mate_problems", []) or [])
            noted = (problems, digest if problems else "")
            problems_noted = noted != (gearbox.mate_problems, gearbox.mate_problems_digest)
            gearbox.mate_problems, gearbox.mate_problems_digest = noted
            if before is not None:
                before.mate_problems, before.mate_problems_digest = noted
        rec.gearbox = gearbox

    left = settled_journal(mine, rec, exists=exists, read_sidecar=read_sidecar, written=[p for p, _ in out.sidecars])
    settled = len(left) != len(mine)
    if other is not None:
        rec.pending, rec.pending_for = left, (workbook if left else "")    # the copy's own record from now
    elif mine:
        rec.pending, rec.pending_for = left, (rec.pending_for if left else "")

    if not saved_any:
        if marked_any:
            out.record = rec               # nothing made, but what the checks found is on record for the next plan
        elif problems_noted:
            # Nothing made (a continued revision whose assembly SolidWorks refused again): only what it refused, and
            # the read it came from, change on record.
            if before is not None:
                rec.gearbox = before
            out.record = rec
        elif settled and other is not None:
            kept = copy.deepcopy(other)    # a copy's journal, written into the record that came with it: settled
            kept.pending, kept.pending_for = left, (other.pending_for if left else "")
            out.record = kept
        elif settled:
            out.record = rec               # nothing made: what is not on disk leaves the journal
        return out
    if result.ok:
        rec.digest = digest
    rec.last_built = stamp
    rec.written_by = written_by
    out.record = rec
    return out
