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

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from .. import store
from ..gears.base import BuildPlan, GlobalVariable
from ..spec import GearSpec
from ..store import LinkRecord, Sidecar
from ..swbuild import DocumentValues, GearboxResult
from .assess import Assessment
from .build import PartJob
from .layout import Frame, ShaftLayout


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
    """
    raise NotImplementedError("W4: Agent B, workbook.gearbox.plan_gearbox")


def replan(job: PartJob, path: str, template: str) -> PartJob:
    """The same part planned at another path (``<stem>_r<n>``): the strip's own ``plan_for`` again, so ``SaveAs``
    and any step naming the file follow; ``stem`` becomes the new file's stem."""
    raise NotImplementedError("W4: Agent B, workbook.gearbox.replan")


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
    raise NotImplementedError("W4: Agent B, workbook.gearbox.finish_build")
