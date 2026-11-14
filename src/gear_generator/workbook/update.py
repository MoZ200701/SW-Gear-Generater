"""What Update SolidWorks would change, and recording what it did (docs/PLAN-WORKBOOK.md §4.5, phase W4).

Pure, on the Tk thread: :func:`classify` compares the linked file's latest
read with the link record and says what Update SolidWorks carries — part
values, the layout's globals, components re-placed — or why a new revision is
needed instead; :func:`finish_update` turns what the worker did
(``swbuild.GearboxUpdate``) into the sidecars and record to save. The worker
runs ``swbuild.update_gearbox(session, **plan.update_kwargs())`` and nothing
else. No COM, no Tk; the file system only through injected callables.

Interfaces pinned in the W4 interface commit; every body that raises
NotImplementedError is Agent B's.

**What is structural** (a new revision, offered after asking): a gear, shaft
or mesh added, removed or renamed; a coordinate that changes side or reaches
or leaves 0 (a layout plane cannot follow a global across its base plane); a
built part whose gears now want different parts (a split); a part whose
resulting stem changes; and ``swbuild.structural_change`` on what is left,
once the plans and stems have been compared and the fields a kind ignores
normalised (decision 5: a spur gear's Hand, a Part name equal to the default
stem, are not). **A value update**: the kind's variable texts differ. **A
move**: X or Y on the same side (the layout's globals), Z, Z± or At (while the
assembly is static). Speeds, torques and efficiencies change nothing in
SolidWorks. A part keeps its file name after a value update (N68 holding 69
teeth).

The record is compared for the sentence before the press; the worker compares
with SolidWorks live, so Update stays enabled even when the record says
nothing differs (an unsaved or lost update is put right).
"""

from __future__ import annotations

import copy
import os
from dataclasses import asdict, dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import store
from ..gears import equations, kind_for
from ..gears.base import GlobalVariable
from ..spec import GearSpec, InputError
from ..store import LinkRecord, PartEntry, ShaftEntry, Sidecar
from ..swbuild import POSE_TOLERANCE, DocumentValues, GearboxUpdate, Placement, same_frame, structural_change
from . import gearbox, layout
from .assess import Assessment
from .build import PartJob
from .gearbox import Finished
from .layout import ShaftLayout


@dataclass(frozen=True)
class PartUpdate:
    """One part of the current revision and what it should hold now. ``variables`` is every global as it should
    be (``kind.variables(spec, derived)``; the worker sets only those SolidWorks holds differently). ``changed``:
    the record's variables differ from these — for the sentence only."""

    path: str
    gear_ids: Tuple[str, ...]
    spec: GearSpec
    derived: Any
    variables: Tuple[GlobalVariable, ...]
    changed: bool = False


@dataclass(frozen=True)
class UpdatePlan:
    """What Update SolidWorks would do, from the record and the latest read.

    ``parts``: every part of the current revision (``record.current_parts()``),
    with its wanted values. ``layout``: the layout part and every layout
    global as wanted (``features`` its planes and axes, checked live), or None
    when no layout is recorded (W2 parts only). ``assembly``: its path, or
    ``""``. ``placements``: every gear's wanted frame, by the component
    ``Name2`` on record, with its pitch. For the sentence, against the record:
    ``moved_shafts`` (X, Y, Z or Z± changed), ``replaced`` (gears whose frame
    differs, modulo pitch). ``structural``: sentences, each a reason a new
    revision is needed (Update is then not run; the window offers to build
    again). ``missing``: recorded files no longer on disk (likewise).
    ``unsaved``: documents an earlier Update changed and that are not yet
    saved. ``refusal``: ``""``, or why there is nothing Update can act on
    (no record, a record with no parts).
    """

    parts: Tuple[PartUpdate, ...] = ()
    layout: Optional[DocumentValues] = None
    assembly: str = ""
    placements: Tuple[Placement, ...] = ()
    moved_shafts: Tuple[str, ...] = ()
    replaced: Tuple[str, ...] = ()
    structural: Tuple[str, ...] = ()
    missing: Tuple[str, ...] = ()
    unsaved: Tuple[str, ...] = ()
    refusal: str = ""
    shafts: Tuple[ShaftLayout, ...] = ()       # the shafts as now wanted, for the record (Agent B, additive)

    @property
    def changed_parts(self) -> Tuple[PartUpdate, ...]:
        return tuple(p for p in self.parts if p.changed)

    @property
    def needs_new_revision(self) -> bool:
        """Update cannot carry it: the window asks whether to build again instead."""
        return bool(self.structural or self.missing)

    @property
    def record_matches(self) -> bool:
        """Nothing on record differs from the workbook (the worker still compares live)."""
        return not (self.changed_parts or self.moved_shafts or self.replaced or self.needs_new_revision)

    def update_kwargs(self) -> Dict[str, Any]:
        """The arguments of ``swbuild.update_gearbox(session, **plan.update_kwargs())``. Never called on a plan
        that is refused or needs a new revision."""
        if self.refusal or self.needs_new_revision:
            raise ValueError("Update SolidWorks cannot carry this change: "
                             + " ".join((self.refusal,) + self.structural + self.missing).strip())
        return {
            "parts": [DocumentValues(p.path, tuple(p.variables)) for p in self.parts],
            "layout": self.layout,
            "assembly": self.assembly,
            "placements": list(self.placements),
        }


MOVE_TOLERANCE = POSE_TOLERANCE         # mm: a shaft coordinate that changed less than this has not moved


def _names(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _is(items: Sequence[str]) -> str:
    return "is" if len(items) == 1 else "are"


def _number(value: float) -> str:
    return equations.literal(round(value, 6))


def _side_change(shaft: str, coordinate: str, old: float, new: float) -> str:
    """Why a coordinate that changed side of its base plane needs a new layout part, or ``""`` (decision: any
    change between plus, minus and base is structural — findings.OFFSET_GLOBAL_CROSSES_ZERO is False, and a
    global set below zero was taken without a word while its plane stayed where it was)."""
    was, now = layout.side(old), layout.side(new)
    if was == now:
        return ""
    move = f"{_number(old)} → {_number(new)}"
    if was == layout.BASE:
        return (f"{shaft}'s {coordinate} moves off 0 ({move}): the layout part has no plane for {shaft} {coordinate}, "
                "so it needs a new layout part.")
    if now == layout.BASE:
        return (f"{shaft}'s {coordinate} moves to 0 ({move}): its layout plane cannot reach the base plane, so it "
                "needs a new layout part.")
    return (f"{shaft}'s {coordinate} crosses 0 ({move}): a layout plane cannot follow a global across its base "
            "plane, so it needs a new layout part.")


def _ignored_fields_as_built(built: GearSpec, wanted: GearSpec, template: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Both forms as dicts, with every field the wanted part's kind ignores set to the built value (decision 5):
    a field is ignored when giving it the built value leaves the wanted plan as it is. ``name`` is never compared
    here (:func:`gearbox.name_changed` decides it)."""
    b, w = built.to_dict(), wanted.to_dict()
    b.pop("name", None)
    w.pop("name", None)
    for form, values in ((built, b), (wanted, w)):     # a blank recipe is the kind's default: say which
        try:
            values["recipe"] = kind_for(form).recipe_for(form)
        except (AttributeError, InputError, ValueError):
            pass
    plan = gearbox._plan_of(wanted, template)
    for key in list(w):
        if str(b.get(key, "")) == str(w[key]):
            continue
        try:
            trial = wanted.with_values(**{key: str(b.get(key, ""))})
        except (TypeError, ValueError):
            continue
        if plan is not None and gearbox._plan_of(trial, template) == plan:
            w[key] = b.get(key, "")
    return b, w


def _part(entry: PartEntry, job: PartJob, exists: Callable[[str], bool]) -> Tuple[PartUpdate, str]:
    """What Update does to one built part, and the sentence if it cannot (``""``)."""
    variables = gearbox._variables_of(job)
    label = f"{gearbox._stem_of(entry.path)} ({_names(entry.gears)})"
    update = PartUpdate(entry.path, tuple(entry.gears), job.spec, job.derived, variables, changed=True)
    if not entry.spec:
        return update, ""                  # a v1 record: what it holds is known only live
    try:
        built = GearSpec.from_dict(entry.spec)
    except (TypeError, ValueError):
        return update, ""
    template = gearbox._template_of(job.plan)
    if gearbox.name_changed(built, job.spec):
        return update, (f"{label}: its Part name now makes {job.spec.stem()}{layout.PART_EXTENSION}, and a built "
                        "part's file is never renamed, so it needs a new part.")
    unchanged = gearbox._variables_match(entry.variables, entry.trig, variables)
    if gearbox.same_part(built, job.spec, template):
        return replace(update, changed=not unchanged or not entry.variables), ""
    b, w = _ignored_fields_as_built(built, job.spec, template)
    why = structural_change(b, w)
    if why:
        return update, f"{label}: {why}"
    held = {str(pair[0]) for pair in entry.variables if pair}
    if held:
        lacking = [v.name for v in variables if v.name not in held]
        if lacking:
            return update, (f"{label}: its new values need the global \"{lacking[0]}\", which the built part does "
                            "not have, so it needs a new part.")
        if unchanged:
            return update, (f"{label}: it would now be built differently in a way its values do not carry, so it "
                            "needs a new part.")
    return update, ""


def classify(record: Optional[LinkRecord], a: Assessment, *,
             exists: Callable[[str], bool] = os.path.exists) -> UpdatePlan:
    """What Update SolidWorks would change, from the planning read of the record (``store.read_link_record``) and
    an assessment that passed ``a.lay_out_refusal()`` (or ``a.build_refusal()`` when only parts are recorded).
    Acts only on ``record.current_parts()`` (decision 2). Pure but for ``exists``.

    Plans and stems are compared before ``structural_change``, and the
    fields a kind ignores are normalised first (decision 5), so an edit the
    part cannot see is no change at all. The gears to re-place are those
    whose wanted frame (``layout.frames``) is not the recorded one modulo the
    gear's pitch (``swbuild.same_frame``, review 14), whatever moved them:
    a shaft, an At, a face width, a tooth count, a mesh's phase, the input.
    """
    if record is None:
        return UpdatePlan(refusal="Nothing has been built from this workbook yet, so Update SolidWorks has nothing "
                                  "to change.")
    box = record.gearbox
    if box is not None and not box.assembly:
        return UpdatePlan(refusal=(f"{os.path.basename(box.layout)} was saved but its assembly was not made: Build "
                                   "carries on with it, and Update SolidWorks waits until it has."))
    entries = record.current_parts()
    if not entries:
        return UpdatePlan(refusal="The record of what was built lists no parts, so Update SolidWorks has nothing "
                                  "to change.")
    spec = a.spec
    job_of: Dict[str, PartJob] = {g: job for job in a.parts.jobs for g in job.gear_ids}
    structural: List[str] = []
    missing: List[str] = []

    # Gears, shafts and meshes added, removed or renamed.
    if box is not None:
        recorded = [c.gear for c in box.components]
        current = [g.id for g in spec.gears]
    else:
        recorded = [g for p in entries for g in p.gears]
        current = [g.id for g in spec.gears if g.id in job_of]
    gone = [g for g in recorded if g not in current]
    new = [g for g in current if g not in recorded]
    if gone:
        structural.append(f"{_names(gone)} {_is(gone)} no longer in the workbook, and Update SolidWorks cannot take "
                          f"a part out of what was built.")
    if new:
        structural.append(f"{_names(new)} {_is(new)} new, and Update SolidWorks cannot add a part to what was built.")

    shafts: Tuple[ShaftLayout, ...] = ()
    moved: List[str] = []
    layout_values: Optional[DocumentValues] = None
    if box is not None:
        try:
            shafts = layout.shaft_layouts(spec)
        except ValueError as exc:
            return UpdatePlan(refusal=str(exc))
        before = {s.shaft: s for s in box.shafts}
        now = {s.shaft: s for s in shafts}
        gone_s = [s for s in before if s not in now]
        new_s = [s for s in now if s not in before]
        if gone_s:
            structural.append(f"Shaft {_names(gone_s)} {_is(gone_s)} no longer in the workbook, and its axis cannot "
                              "be taken out of the layout part.")
        if new_s:
            structural.append(f"Shaft {_names(new_s)} {_is(new_s)} new, and the layout part has no axis for it.")
        for shaft in shafts:
            old = before.get(shaft.shaft)
            if old is None:
                continue
            for coordinate, was, value in (("X", old.x, shaft.x), ("Y", old.y, shaft.y)):
                why = _side_change(shaft.shaft, coordinate, was, value)
                if why:
                    structural.append(why)
            if (any(abs(p - q) > MOVE_TOLERANCE for p, q in ((old.x, shaft.x), (old.y, shaft.y), (old.z, shaft.z)))
                    or old.sigma != shaft.sigma):
                moved.append(shaft.shaft)
        listed = lambda pairs: {frozenset(p) for p in pairs}           # noqa: E731
        was_meshed, meshed = listed(tuple(m) for m in box.meshes), listed((m.a, m.b) for m in spec.meshes)
        for pair in sorted(meshed - was_meshed, key=sorted):
            structural.append(f"The mesh {'–'.join(sorted(pair))} is new, and Update SolidWorks cannot add one.")
        for pair in sorted(was_meshed - meshed, key=sorted):
            structural.append(f"The mesh {'–'.join(sorted(pair))} is no longer listed, and Update SolidWorks cannot "
                              "take one out.")
        try:
            layout_values = DocumentValues(box.layout, layout.layout_globals(shafts), layout.layout_features(shafts))
        except ValueError as exc:
            return UpdatePlan(refusal=str(exc))
        if not exists(box.layout):
            missing.append(box.layout)

    # The parts, each against the part its gears now want.
    parts: List[PartUpdate] = []
    for entry in entries:
        if not exists(entry.path):
            missing.append(entry.path)
        jobs = []
        for gear in entry.gears:
            job = job_of.get(gear)
            if job is not None and job not in jobs:
                jobs.append(job)
        if not jobs:
            continue                        # every gear it served is gone: said above
        if len(jobs) > 1:
            first = jobs[0].gear_ids[0]
            others = [g for j in jobs[1:] for g in j.gear_ids if g in entry.gears]
            structural.append(f"{_names(entry.gears)} share {os.path.basename(entry.path)}, but {_names(others)} "
                              f"now {'differs' if len(others) == 1 else 'differ'} from {first}, so they need parts "
                              "of their own.")
            continue
        update, why = _part(entry, jobs[0], exists)
        if why:
            structural.append(why)
        parts.append(update)

    # The assembly: every gear's wanted frame, by the Name2 on record.
    placements: List[Placement] = []
    replaced: List[str] = []
    assembly = ""
    if box is not None:
        assembly = box.assembly
        if not exists(assembly):
            missing.append(assembly)
        wanted = layout.frames(a.report)
        placed = a.report.layout.placed
        for c in box.components:
            if c.gear not in wanted:
                continue
            f, step = wanted[c.gear], layout.pitch(placed[c.gear])
            placements.append(Placement(c.gear, c.name, f.rotation, f.at, step))
            if not (c.rotation and c.at and same_frame(c.rotation, c.at, f.rotation, f.at, step)):
                replaced.append(c.gear)

    return UpdatePlan(parts=tuple(parts), layout=layout_values, assembly=assembly, placements=tuple(placements),
                      moved_shafts=tuple(moved), replaced=tuple(replaced), structural=tuple(structural),
                      missing=tuple(dict.fromkeys(missing)), unsaved=tuple(record.unsaved), shafts=shafts)


def finish_update(plan: UpdatePlan, result: GearboxUpdate, record: LinkRecord, *, digest: str,
                  read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar,
                  mtime: Callable[[str], float] = os.path.getmtime,
                  stamp: Optional[str] = None) -> Finished:
    """The sidecars and record an update leaves (Tk thread, after the worker).

    ``record`` is the record as read just before writing
    (``store.open_link_record``). For each part whose values changed in
    SolidWorks (``result.parts[i].changed``): ``store.updated_sidecar`` and its
    ``PartEntry`` spec and variables. The re-placed gears' component frames.
    ``last_updated`` set when anything changed. Every path in
    ``result.changed`` goes into ``record.unsaved`` with ``mtime(path)``: Update
    does not save (decision 3). ``dragged`` lists the gears whose live frame
    (``result.found``) differed from the recorded one while the recorded one
    was already the wanted one: moved by hand in SolidWorks, and put back.
    Pure but for ``read_sidecar`` and ``mtime``.

    A part reached without a failure is recorded as holding the wanted values
    even when nothing in it changed: SolidWorks was found to hold them already
    (an earlier update, or values set by hand), and the record follows
    SolidWorks. ``digest`` is the read SolidWorks wholly matches, so it is set
    only when the update ran with no failure and nothing skipped. An update
    that stopped part-way keeps the digest it had, even though it changed
    something: the header would otherwise say "built from this version" of a
    gearbox whose layout, say, was never moved (found by the window wiring,
    2026-11-13). What it did change is still recorded, part by part.
    """
    stamp = stamp or store.now()
    rec = copy.deepcopy(record)
    out = Finished(record=rec)
    changed = bool(result.changed or result.placed)

    for update, done in zip(plan.parts, result.parts):
        if done.failures:
            continue
        entry = next((p for p in rec.parts if store.same_path(p.path, update.path)), None)
        trig = done.trig or (entry.trig if entry is not None else "")
        variables = [[v.name, v.expression_for(trig)] for v in update.variables]
        spec = update.spec.to_dict()
        if entry is not None and entry.spec == spec and entry.variables == variables and not done.changed:
            continue
        if entry is not None:
            entry.spec, entry.variables, entry.trig, entry.kind = spec, variables, trig, update.spec.kind
        sidecar_path = store.sidecar_path(update.path)
        sidecar = read_sidecar(sidecar_path)
        if sidecar is None:
            out.notes.append(f"{os.path.basename(sidecar_path)} could not be read, so it was left as it is; the "
                             "workbook's record says what the part now holds.")
            continue
        out.sidecars.append((sidecar_path, store.updated_sidecar(sidecar, spec, update.derived.to_dict(), variables,
                                                                 stamp)))

    box = rec.gearbox
    if box is not None:
        if plan.layout is not None and result.layout is not None and not result.layout.failures and plan.shafts:
            box.shafts = [ShaftEntry(**asdict(s)) for s in plan.shafts]
        wanted = {p.gear: p for p in plan.placements}
        for component in box.components:
            p = wanted.get(component.gear)
            if p is None:
                continue
            found = result.found.get(component.gear)
            recorded_is_wanted = bool(component.rotation and component.at) and same_frame(
                component.rotation, component.at, p.rotation, p.at, p.pitch)
            if found is not None and recorded_is_wanted and not same_frame(
                    component.rotation, component.at, found[0], found[1], p.pitch):
                out.dragged.append(component.gear)
            if component.gear in result.placed or (found is not None and same_frame(found[0], found[1], p.rotation,
                                                                                     p.at, p.pitch)):
                component.rotation, component.at = list(p.rotation), list(p.at)
        if changed:
            box.updated = stamp

    for path in result.changed:
        try:
            rec.unsaved[path] = float(mtime(path))
        except OSError:
            out.notes.append(f"{os.path.basename(path)} could not be found on disk to note that it is changed but "
                             "not saved.")
    if changed:
        rec.last_updated = stamp
    if not (result.failures or result.skipped):
        rec.digest = digest
    return out
