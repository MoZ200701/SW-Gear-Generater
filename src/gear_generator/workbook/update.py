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

**A gearbox built to turn** (W5, ``GearboxRecord.kind`` MOTION) is classified
from the record's own mates (:func:`_turning`): more is structural — a mated
shaft's Z± flipped, a mated gear on another shaft, a shaft starting or ceasing
to stand still (its Role ``fixed``, or held still through a fixed shaft), an
anchor's front face reaching, leaving or crossing the Front plane, a meshed
gear's tooth change while ``findings.GEAR_MATE_RATIO_ROUTE`` is not
``"remake"``, and a follower's place along its shaft unless
``findings.LOCK_RETAKES_AN_OFFSET`` — and what is left goes to the worker's
motion path as a ``swbuild.MotionUpdate``. A static gearbox keeps W4's path
untouched (W5-PLAN D5).
"""

from __future__ import annotations

import copy
import math
import os
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import findings, store
from ..gears import equations, kind_for
from ..gears.base import GlobalVariable
from ..spec import GearSpec, InputError
from ..store import GearboxRecord, LinkRecord, MateEntry, PartEntry, ShaftEntry, Sidecar
from ..swbuild import (POSE_TOLERANCE, DocumentValues, GearboxUpdate, MotionUpdate, Placement, same_frame,
                       structural_change)
from . import gearbox, layout, motion, schema
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
    ``unsaved``: documents of the current revision an earlier Update changed
    and that are not yet saved (an earlier revision's are left out: second
    review N2). ``refusal``: ``""``, or why there is nothing Update can act on
    (no record, a record with no parts, a record that is another workbook's).
    ``foreign_record``: that other workbook, when the record beside this one
    was written for a workbook still on disk, or one the person said this is
    a copy of — and Update leaves that workbook's files alone (review S1) —
    or for a workbook that is gone, until the person says this one was moved
    or renamed from it (second review N1c, ``store.record_owner``).

    W5 (Agent B fills them; W5-INTERFACES.md): ``motion`` is what the worker's
    motion path is given for a gearbox on record as turning
    (``GearboxRecord.kind == motion.MOTION``), None for a static one (W4's
    path, unchanged: W5-PLAN D5). For the sentence: ``axial`` the gears whose
    ``"<Gear> Face Z"`` changes, ``ratios`` the gear mates (by name) whose
    ratio changes — empty while ``findings.GEAR_MATE_RATIO_ROUTE`` is not
    ``"remake"``, a tooth change being structural then.
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
    foreign_record: str = ""
    motion: Optional[MotionUpdate] = None
    axial: Tuple[str, ...] = ()
    ratios: Tuple[str, ...] = ()
    drag: Tuple[str, ...] = ()                 # a turning gearbox's drag gear per train, now (Agent B, additive)

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
        that is refused or needs a new revision. ``"motion"`` is there only for a turning gearbox, so a static
        one's call is W4's, key for key."""
        if self.refusal or self.needs_new_revision:
            raise ValueError("Update SolidWorks cannot carry this change: "
                             + " ".join((self.refusal,) + self.structural + self.missing).strip())
        kwargs: Dict[str, Any] = {
            "parts": [DocumentValues(p.path, tuple(p.variables)) for p in self.parts],
            "layout": self.layout,
            "assembly": self.assembly,
            "placements": list(self.placements),
        }
        if self.motion is not None:
            kwargs["motion"] = self.motion
        return kwargs


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


# The fields swbuild.structural_change names by their field name, as the Gears sheet calls them (second W4 review
# N6: the footer said "The recipe changed from 'A' to 'B'" where the person had typed Flank = arcs, and "The
# teeth_side changed" for Side). Bore, profile shift and groove it already says in words.
_COLUMNS = (("kind", "Kind"), ("recipe", "Flank"), ("hand", "Hand"), ("teeth_side", "Side"))
_FLANK_OF_RECIPE = {recipe: flank for flank, recipe in schema.FLANK_RECIPE.items()}


def _structural(built: Dict[str, Any], wanted: Dict[str, Any]) -> str:
    """``swbuild.structural_change`` in the workbook's words: *Flank changed from involute to arcs, which its values
    cannot carry; build it again as a new part.* (``ui_text`` turns the tail into the footer's). The strip keeps
    ``structural_change``'s own sentence, in its own words."""
    for key, column in _COLUMNS:
        default = "external" if key == "teeth_side" else ""
        was, now = (str(values.get(key, default) or default) for values in (built, wanted))
        if was != now:
            word = (lambda v: _FLANK_OF_RECIPE.get(v, v)) if key == "recipe" else (lambda v: v)
            return (f"{column} changed from {word(was) or 'blank'} to {word(now) or 'blank'}, which its values cannot "
                    "carry; build it again as a new part.")
    return structural_change(built, wanted)


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
    why = _structural(b, w)
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


@store.in_one_pass
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

    A gearbox on record as turning is refused while :func:`motion.update_reason`
    says so, or while a recorded mate cannot be read (:func:`_bad_mates`);
    otherwise W4's rules run first and :func:`_turning` adds its structural
    cases, ``motion``, ``axial`` and ``ratios``.
    """
    if record is None:
        return UpdatePlan(refusal="Nothing has been built from this workbook yet, so Update SolidWorks has nothing "
                                  "to change.")
    here = str(a.read.source_path or a.spec.source_path or "")
    owner, foreign = store.record_owner(record, here, exists)
    if owner != store.OURS:
        return UpdatePlan(refusal=store.foreign_record_sentence(here, foreign, gone=owner == store.UNSURE,
                                                                said=store.copy_by_answer(record, here, exists)),
                          foreign_record=foreign)
    box = record.gearbox
    if box is not None and not box.assembly:
        return UpdatePlan(refusal=(f"{os.path.basename(box.layout)} was saved but its assembly was not made: Build "
                                   "carries on with it, and Update SolidWorks waits until it has."))
    turning = box is not None and box.kind == motion.MOTION
    if turning:
        why = motion.update_reason() or _bad_mates(box)
        if why:
            return UpdatePlan(refusal=why)
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

    turn = _Turning()
    if turning:
        turn = _turning(box, entries, a, shafts)
        structural.extend(turn.structural)

    return UpdatePlan(parts=tuple(parts), layout=layout_values, assembly=assembly, placements=tuple(placements),
                      moved_shafts=tuple(moved), replaced=tuple(replaced), structural=tuple(structural),
                      missing=tuple(dict.fromkeys(missing)), unsaved=tuple(record.current_marks(record.unsaved)),
                      shafts=shafts, motion=turn.motion, axial=turn.axial, ratios=turn.ratios, drag=turn.drag)


# -- a gearbox built to turn (W5-PLAN §1.6's classify, as W5-DECISIONS and W5-INTERFACES amend it) ------------------

_REBUILD = "so the gearbox needs building again"


def _axis_word(sigma: int) -> str:
    return "Z+" if sigma > 0 else "Z-"


def _plural(items: Sequence[str], one: str, many: str) -> str:
    return one if len(items) == 1 else many


def _number_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _bad_mates(box: GearboxRecord) -> str:
    """A refusal sentence for the first mate on record Update cannot act on — a kind the app does not make, the
    wrong number of gears for its kind, no name, an axis or along mate with no shaft, a mesh whose ratio is not
    two whole tooth counts, an along mate whose distance is not a number, or a gear not in the assembly on record
    — else ``""``. A hand-edited or damaged record is refused with a sentence, never an IndexError."""
    known = {c.gear for c in box.components}
    tail = (", so Update SolidWorks cannot act on the gearbox the record describes: Build again… makes a new revision "
            "from the workbook instead.")
    for entry in box.mates:
        name = entry.name if isinstance(entry.name, str) else ""
        label = f"The record of what was built lists the mate \"{name}\"" if name else (
            "The record of what was built lists a mate with no name")
        kind = entry.kind
        if kind not in motion.MATE_KINDS:
            article = "an" if str(kind)[:1].lower() in "aeiou" else "a"
            return f"{label} as {article} {kind!r} mate, which is not a kind of mate the app makes{tail}"
        want = 1 if kind in (motion.AXIS, motion.ALONG) else 2
        gears = list(entry.gears) if isinstance(entry.gears, (list, tuple)) else []
        if len(gears) != want or not all(isinstance(g, str) and g for g in gears):
            return (f"{label} with {len(gears)} gear{'' if len(gears) == 1 else 's'} where a {kind} mate holds "
                    f"{want}{tail}")
        if not name:
            return f"{label}, and Update SolidWorks finds each mate by its name{tail}"
        if kind in (motion.AXIS, motion.ALONG) and not (isinstance(entry.shaft, str) and entry.shaft):
            return f"{label} with no shaft, where a {kind} mate names the shaft it holds its gear to{tail}"
        if kind == motion.ALONG and _number_or_none(entry.z_front) is None:
            return f"{label} with the distance {entry.z_front!r}, which is not a number{tail}"
        if kind == motion.MESH:
            ratio = list(entry.ratio) if isinstance(entry.ratio, (list, tuple)) else []
            counts = [_number_or_none(n) for n in ratio]
            if len(counts) != 2 or not all(n is not None and n > 0 and n == int(n) for n in counts):
                return f"{label} with the ratio {entry.ratio!r}, where a gear mate holds two tooth counts{tail}"
        strangers = [g for g in gears if g not in known]
        if strangers:
            return (f"{label} on {_names(strangers)}, which {_is(strangers)} not in the assembly on "
                    f"record{tail}")
    return ""


@dataclass
class _Turning:
    """What :func:`_turning` found: sentences for a new revision, and what the worker's motion path is given."""

    structural: List[str] = field(default_factory=list)
    motion: Optional[MotionUpdate] = None
    axial: Tuple[str, ...] = ()
    ratios: Tuple[str, ...] = ()
    drag: Tuple[str, ...] = ()


def _built_part(entries: Sequence[PartEntry], gear: str) -> Dict[str, Any]:
    """The spec (``GearSpec.to_dict``) of the part on record that holds ``gear``, or ``{}``."""
    entry = next((p for p in entries if gear in p.gears and p.spec), None)
    return dict(entry.spec) if entry is not None else {}


def _axial_edit(gear: str, shaft: str, z_front: float, sigma: int, built_shaft_z: Optional[float],
                shaft_z: float, built_face: Optional[float], face: float, at: float) -> Tuple[str, str]:
    """``(subject and verb, object)`` naming the edit that moves ``gear`` along its shaft (W5-DECISIONS answer 3:
    the sentence names the edit, never only the plane): *G1's face width (15 → 20) moves* / *its front face*;
    *G4's At (27 → 30) and S3's Z (0 → 5) move* / *G4's front face*. The built At is worked back from the
    built front face, the shaft's built Z and the part's built face width; an edit that cannot be told is left
    out, and with none told the subject is the gear's front face itself."""
    gear_edits: List[str] = []
    if built_face is not None and abs(built_face - face) > MOVE_TOLERANCE:
        gear_edits.append(f"face width ({_number(built_face)} → {_number(face)})")
    if built_face is not None and built_shaft_z is not None:
        built_at = (z_front - built_shaft_z) * sigma + built_face / 2.0
        if abs(built_at - at) > MOVE_TOLERANCE:
            gear_edits.append(f"At ({_number(built_at)} → {_number(at)})")
    moved = built_shaft_z is not None and abs(built_shaft_z - shaft_z) > MOVE_TOLERANCE
    parts = ([f"{gear}'s " + " and ".join(gear_edits)] if gear_edits else []) + (
        [f"{shaft}'s Z ({_number(built_shaft_z)} → {_number(shaft_z)})"] if moved else [])
    if not parts:
        return f"{gear}'s front face moves", ""
    verb = "moves" if len(gear_edits) + moved == 1 else "move"
    return f"{' and '.join(parts)} {verb}", ("its front face" if not moved else f"{gear}'s front face")


def _drag(spec: Any, of_kind: Mapping[str, Sequence[MateEntry]], built_on: Mapping[str, str]) -> Tuple[str, ...]:
    """Each train's drag gear as the workbook now has it, from the record's mates (``motion.motion_plan``'s rule:
    the shafts the gear mates join, input shafts first then Shafts-sheet order, the trains in the order of their
    first shaft; the anchor of each train's first shaft). Moving the input to another shaft is an Update, and the
    footer's drag gear follows it."""
    order = {s.id: i for i, s in enumerate(spec.shafts)}
    role = {s.id: s.role for s in spec.shafts}
    anchor_of = {m.shaft: m.gears[0] for m in of_kind[motion.AXIS]}
    parent: Dict[str, str] = {}

    def root(x: str) -> str:
        while parent.setdefault(x, x) != x:
            x = parent[x]
        return x
    joined: List[str] = []
    for m in of_kind[motion.MESH]:
        a, b = (built_on.get(g) for g in m.gears)
        if a and b:
            parent[root(a)] = root(b)
            joined += [s for s in (a, b) if s not in joined]
    joined.sort(key=lambda s: order.get(s, len(order)))
    out: List[str] = []
    seen = set()
    for shaft in joined:
        if root(shaft) in seen:
            continue
        seen.add(root(shaft))
        members = [s for s in joined if root(s) == root(shaft)]
        first = next((s for s in members if role.get(s) == "input"), members[0])
        if first in anchor_of:
            out.append(anchor_of[first])
    return tuple(out)


def _turning(box: GearboxRecord, entries: Sequence[PartEntry], a: Assessment,
             shafts: Sequence[ShaftLayout]) -> _Turning:
    """Classify an edit of a gearbox built to turn, from the record's own mates (anchors are never worked out
    again: a reordered Gears sheet keeps them) and the new read. Called once :func:`_bad_mates` passed.

    **Structural** (each a sentence naming the edit): a mated shaft's Z±
    flipped; a mated gear now on another shaft; a gear built fixed whose
    shaft now turns, or one built mated whose shaft's Role is now ``fixed``
    or that now stands still through a fixed shaft (review M9, as a Role
    change); an anchor's front face reaching, leaving or crossing the
    Front plane (W5-DECISIONS answer 3); a meshed gear's tooth change while
    ``findings.GEAR_MATE_RATIO_ROUTE`` is not ``"remake"`` (ruling c); a
    follower's place along its shaft changing unless
    ``findings.LOCK_RETAKES_AN_OFFSET`` is True. **An Update**: an anchor's
    move along its shaft on one side of the Front plane (its Face Z), a
    follower's (the lock re-takes it), layout moves, turn-backs, and a tooth
    change by remake (a ratio, in the record's gear order: review M10)."""
    spec = a.spec
    placed = a.report.layout.placed
    wanted = layout.frames(a.report)
    out = _Turning()
    now = {s.shaft: s for s in shafts}
    before = {s.shaft: s for s in box.shafts}
    gear_of = {g.id: g for g in spec.gears}
    components = {c.gear: c for c in box.components}
    order = {s.id: i for i, s in enumerate(spec.shafts)}
    mates = list(box.mates)
    of_kind = {kind: [m for m in mates if m.kind == kind] for kind in motion.MATE_KINDS}
    built_on: Dict[str, str] = {}                  # each mated gear's shaft as built
    for m in of_kind[motion.AXIS] + of_kind[motion.ALONG]:
        built_on[m.gears[0]] = m.shaft
    for m in of_kind[motion.LOCK]:
        if m.gears[0] in built_on:
            built_on[m.gears[1]] = built_on[m.gears[0]]
    told: set = set()                              # gears an edit was said for: one edit, one sentence

    flipped = set()
    for m in of_kind[motion.AXIS]:
        old, new = before.get(m.shaft), now.get(m.shaft)
        if old is None or new is None or old.sigma == new.sigma:
            continue
        flipped.add(m.shaft)
        told.update(g for g, s in built_on.items() if s == m.shaft)
        out.structural.append(f"{m.shaft}'s axis is now {_axis_word(new.sigma)} where it was built "
                              f"{_axis_word(old.sigma)}: the mate {m.name} keeps the direction it was made with, "
                              f"{_REBUILD}.")

    for gear, shaft in built_on.items():
        row = gear_of.get(gear)
        if row is None or row.shaft == shaft or gear in told:
            continue
        if shaft not in now:
            told.add(gear)                         # its shaft is gone or renamed, which is said already
            continue
        holding = [m.name for m in mates if (m.kind in (motion.AXIS, motion.ALONG) and m.gears[0] == gear)
                   or (m.kind == motion.LOCK and m.gears[1] == gear)]
        told.add(gear)
        out.structural.append(f"{gear} is now on {row.shaft} where it was built on {shaft}: the "
                              f"{_plural(holding, 'mate', 'mates')} {_names(holding)} "
                              f"{_plural(holding, 'holds', 'hold')} it to {shaft}, {_REBUILD}.")

    still = motion.still_shafts(spec, a.report)
    fixed_now = {g for g, p in placed.items() if p.shaft in still}
    was_fixed = set(box.fixed)
    in_box = [c.gear for c in box.components if c.gear in placed and c.gear not in told]
    freed: Dict[str, List[str]] = {}
    held: Dict[str, List[str]] = {}
    for gear in in_box:
        if gear in was_fixed and gear not in fixed_now:
            freed.setdefault(placed[gear].shaft, []).append(gear)
        elif gear not in was_fixed and gear in fixed_now:
            held.setdefault(placed[gear].shaft, []).append(gear)
    for shaft in sorted(freed, key=lambda s: order.get(s, len(order))):
        names = freed[shaft]
        told.update(names)
        out.structural.append(f"{_names(names)} {_plural(names, 'was', 'were')} built fixed, but {shaft} now turns "
                              "(its Role is not fixed and no fixed shaft holds it still), so the gearbox needs "
                              f"building again to mate {_plural(names, 'it', 'them')} to turn.")
    for shaft in sorted(held, key=lambda s: order.get(s, len(order))):
        names = held[shaft]
        told.update(names)
        why = (f"{shaft}'s Role is now fixed" if not still.get(shaft) else
               f"{shaft} now stands still, held through the fixed shaft {still[shaft]}")
        out.structural.append(f"{why}, but {_names(names)} {_plural(names, 'was', 'were')} built mated to turn, so "
                              f"the gearbox needs building again to hold {_plural(names, 'it', 'them')} fixed.")

    def edit(gear: str, shaft: str, z_front: float) -> Tuple[str, str]:
        old, new = before.get(shaft), now.get(shaft)
        sigma = new.sigma if new is not None else placed[gear].sigma
        built_face = _number_or_none(_built_part(entries, gear).get("face_width"))
        return _axial_edit(gear, shaft, z_front, sigma, old.z if old is not None else None,
                           new.z if new is not None else placed[gear].z, built_face, placed[gear].face,
                           _number_or_none(gear_of[gear].at or 0) or 0.0)

    face_globals: List[Tuple[str, GlobalVariable]] = []
    axial: List[str] = []
    for m in of_kind[motion.ALONG]:
        gear = m.gears[0]
        if gear not in wanted or gear not in gear_of:
            continue
        old_z, new_z = float(m.z_front), float(wanted[gear].at[2])
        if m.face_global:
            face_globals.append((gear, GlobalVariable(m.face_global, equations.literal(round(abs(new_z), 9)))))
        if gear in told:
            continue
        was, is_ = layout.side(old_z), layout.side(new_z)
        if was == is_:
            if m.face_global and abs(new_z - old_z) > MOVE_TOLERANCE:
                axial.append(gear)
            continue
        told.add(gear)
        subject, what = edit(gear, m.shaft, old_z)
        if was == layout.BASE:
            where, why = "off the Front plane", f"the mate {m.name} holds it on that plane and cannot take a distance"
        elif is_ == layout.BASE:
            where, why = ("onto the Front plane", f"the mate {m.name} holds it at a distance from that plane and "
                          "cannot reach it")
        else:
            where, why = "across the Front plane", f"the mate {m.name} cannot carry its distance across that plane"
        out.structural.append(f"{subject} {what + ' ' if what else ''}{where} (z {_number(old_z)} → "
                              f"{_number(new_z)}): {why}, {_REBUILD}.")

    retakes = getattr(findings, "LOCK_RETAKES_AN_OFFSET", None)
    for m in of_kind[motion.LOCK]:
        anchor, follower = m.gears
        c = components.get(follower)
        if follower in told or follower not in wanted or follower not in gear_of or c is None or len(c.at) < 3:
            continue
        old_z, new_z = float(c.at[2]), float(wanted[follower].at[2])
        if abs(old_z - new_z) <= MOVE_TOLERANCE or retakes is True:
            continue
        told.add(follower)
        shaft = built_on.get(follower, placed[follower].shaft)
        subject, what = edit(follower, shaft, old_z)
        if retakes is None:
            why = (f"whether its lock to {anchor} takes a new place along the shaft is not settled "
                   "(findings.LOCK_RETAKES_AN_OFFSET)")
        else:
            why = (f"the probes found that its lock to {anchor} does not take a new place along the shaft "
                   "(findings.LOCK_RETAKES_AN_OFFSET)")
        out.structural.append(f"{subject} {what + ' ' if what else ''}along {shaft} (z {_number(old_z)} → "
                              f"{_number(new_z)}), and {why}, {_REBUILD}.")

    route = getattr(findings, "GEAR_MATE_RATIO_ROUTE", None)
    teeth = {g: int(p.teeth) for g, p in placed.items()}
    ratios: List[Tuple[str, int, int]] = []
    for m in of_kind[motion.MESH]:
        a_, b_ = m.gears
        if a_ not in teeth or b_ not in teeth:
            continue
        built = (int(m.ratio[0]), int(m.ratio[1]))
        new = (teeth[a_], teeth[b_])
        if built == new or built[0] * new[1] == built[1] * new[0]:
            continue                               # the gear mate already turns the train at this ratio
        if route == "remake":
            ratios.append((m.name, new[0], new[1]))
            continue
        changed = [f"{g}'s teeth ({old} → {n})" for g, old, n in zip(m.gears, built, new) if old != n]
        if route is None:
            why = ("and a gear mate's ratio cannot be changed in a built assembly until the probes settle how "
                   "(findings.GEAR_MATE_RATIO_ROUTE)")
        elif route == "modify definition":
            why = ("and the only way found to change a gear mate's ratio in place leaves an assembly SolidWorks 2024 "
                   "cannot close")
        else:
            why = (f"and findings.GEAR_MATE_RATIO_ROUTE is {route!r}, which this version does not know how to "
                   "follow")
        out.structural.append(f"{_names(changed)} change the gear mate {m.name} from {built[0]} : {built[1]} to "
                              f"{new[0]} : {new[1]}, {why}, {_REBUILD}.")
    out.axial = tuple(axial)
    out.ratios = tuple(name for name, _, _ in ratios)
    out.drag = _drag(spec, of_kind, built_on)

    mated = {g for m in mates for g in m.gears}
    if not all(g in placed for g in mated):
        return out                                 # a mated gear is gone: said above, and there is nothing to give
    sigma = {g: p.sigma for g, p in placed.items()}
    internal = {g: p.internal for g, p in placed.items()}

    def built_teeth(gear: str) -> int:
        value = _number_or_none(_built_part(entries, gear).get("teeth"))
        if value is None:
            value = next((float(m.ratio[m.gears.index(gear)]) for m in of_kind[motion.MESH] if gear in m.gears),
                         None)
        return int(value) if value else teeth.get(gear, 0)

    recorded = []
    for c in box.components:
        z = built_teeth(c.gear)
        if len(c.rotation) == 9 and len(c.at) == 3:
            recorded.append(Placement(c.gear, c.name, tuple(float(v) for v in c.rotation),
                                      tuple(float(v) for v in c.at), 360.0 / z if z > 0 else 0.0))
    meshes = [tuple(m.gears) for m in of_kind[motion.MESH]]
    out.motion = MotionUpdate(
        mates=tuple(motion.mate_ref(m) for m in mates),
        meshes=motion.mesh_links(meshes, teeth, sigma, internal),
        locks=motion.lock_links([tuple(m.gears) for m in of_kind[motion.LOCK]], teeth),
        recorded=tuple(recorded),
        recorded_meshes=tuple(motion.mesh_links([tuple(m.gears)], {m.gears[0]: int(m.ratio[0]),
                                                                    m.gears[1]: int(m.ratio[1])}, sigma, internal)[0]
                              for m in of_kind[motion.MESH]),
        face_globals=tuple(face_globals),
        ratios=tuple(ratios),
        fixed=tuple(box.fixed))
    return out


def finish_update(plan: UpdatePlan, result: GearboxUpdate, record: LinkRecord, *, digest: str,
                  read_sidecar: Callable[[str], Optional[Sidecar]] = store.read_sidecar,
                  mtime: Callable[[str], float] = os.path.getmtime,
                  stamp: Optional[str] = None, workbook: str = "") -> Finished:
    """The sidecars and record an update leaves (Tk thread, after the worker).

    ``record`` is the record as read just before writing
    (``store.open_link_record``). For each part whose values changed in
    SolidWorks (``result.parts[i].changed``): ``store.updated_sidecar`` and its
    ``PartEntry`` spec and variables. The re-placed gears' component frames.
    ``last_updated`` set when anything changed. Every path in
    ``result.changed`` goes into ``record.unsaved`` with the file's time as
    the worker read it before changing anything (``result.mtimes``; else
    ``mtime(path)`` now), so a save made in SolidWorks while the job was
    answering still reads as newer: Update does not save (decision 3). The
    ``.gear.json`` of a part it changed is marked ``unsaved_since`` that same
    time, so it never claims, to a later plan, values the file may not hold
    (review B2): reuse by ``.gear.json`` skips a marked one until the file is
    newer. ``workbook``, when given, is this workbook's path now, and a
    record that names an older one is adopted (``store.adopt``).
    ``dragged`` lists the gears whose live frame
    (``result.found``) differed from the recorded one while the recorded one
    was already the wanted one: moved by hand in SolidWorks, and put back.
    Pure but for ``read_sidecar`` and ``mtime``.

    A gearbox built to turn (``plan.motion`` set): a mated gear is dragged
    only when the worker found it off its axis (a turn is never a drag),
    fixed gears by W4's rule; mated gears' frames go on record a whole
    train at a time (:func:`_follow_trains`); the record's mates follow the
    ratios and Face Z globals set, and a ratio the parts now hold at the
    same proportion (:func:`_follow_mates`); ``drag`` follows the workbook
    (``plan.drag``).

    Marks (second W4 review N2): a document the job loaded from its file
    (``result.opened``) and found holding what the workbook asks is neither
    unsaved nor mismatched any more — both its entries and its
    ``.gear.json``'s mark go; before, an Update left unsaved and lost when
    SolidWorks closed was marked for ever, and every later build made that
    part new. A document Update changes now loses any mismatched mark (it
    holds the values in memory; the save its unsaved mark asks for clears
    both). A document marked unsaved that was not open when the job began
    (``result.open_before``) and that the job did not change lost Update's
    changes when it was closed: its mark becomes a ``mismatched`` one at
    the same time, since its file does not hold what the record says.

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
    if workbook:
        store.adopt(rec, workbook)
    out = Finished(record=rec)
    changed = bool(result.changed or result.placed)
    settled = _settled(plan, result)
    marks: Dict[str, float] = {}
    for path in result.changed:
        then = next((t for p, t in getattr(result, "mtimes", {}).items() if store.same_path(p, path)), None)
        if then is None:
            try:
                then = float(mtime(path))
            except OSError:
                out.notes.append(f"{os.path.basename(path)} could not be found on disk to note that it is changed "
                                 "but not saved.")
                continue
        marks[path] = then

    written = []
    for update, done in zip(plan.parts, result.parts):
        if done.failures or not (done.changed or done.unchanged):
            continue                        # not reached, or it failed: what it holds is not known
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
        if done.changed:
            mark = next((t for p, t in marks.items() if store.same_path(p, update.path)), None)
        else:
            mark = 0.0 if _in(update.path, settled) else None
        out.sidecars.append((sidecar_path, store.updated_sidecar(sidecar, spec, update.derived.to_dict(), variables,
                                                                 stamp, unsaved_since=mark)))
        written.append(update.path)

    box = rec.gearbox
    if box is not None:
        if plan.layout is not None and result.layout is not None and not result.layout.failures and plan.shafts:
            box.shafts = [ShaftEntry(**asdict(s)) for s in plan.shafts]
        wanted = {p.gear: p for p in plan.placements}
        turning = plan.motion is not None
        held = set(plan.motion.fixed) if turning else set()
        off_axis = set(getattr(result, "off_axis", []) or []) if turning else set()
        for component in box.components:
            p = wanted.get(component.gear)
            if p is None:
                continue
            found = result.found.get(component.gear)
            recorded_is_wanted = bool(component.rotation and component.at) and same_frame(
                component.rotation, component.at, p.rotation, p.at, p.pitch)
            if turning and component.gear not in held:
                # A mated gear the user turned is not a drag (W5-PLAN D4): only one found off its axis or place.
                if component.gear in off_axis:
                    out.dragged.append(component.gear)
            elif found is not None and recorded_is_wanted and not same_frame(
                    component.rotation, component.at, found[0], found[1], p.pitch):
                out.dragged.append(component.gear)
            if turning and component.gear not in held:
                continue                    # a mated gear's frame follows its whole train (below)
            if component.gear in result.placed or (found is not None and same_frame(found[0], found[1], p.rotation,
                                                                                     p.at, p.pitch)):
                component.rotation, component.at = list(p.rotation), list(p.at)
        if turning:
            _follow_trains(box, plan, result, held)
            _follow_mates(box, plan, result)
            box.drag = list(plan.drag)
        out.earlier_update = _earlier_update(record, plan, result, mtime)
        if out.earlier_update:
            out.off_after_update, out.dragged = out.dragged, []
            out.out_of_step_after_update = [tuple(pair) for pair in getattr(result, "out_of_step", []) or []]
        if changed:
            box.updated = stamp

    # The marks (second W4 review N2). A document the job loaded from its file and found holding what the workbook
    # asks holds it in memory and on disk alike: neither unsaved nor mismatched any more. A document marked unsaved
    # that was not open when the job began lost what Update had changed in it when it was closed unsaved, and the
    # job did not put it back: its file does not hold what the record says, which is what ``mismatched`` means.
    for path in settled:
        _drop(rec.unsaved, path)
        _drop(rec.mismatched, path)
    unmark = [p for p in settled if not _in(p, written)]
    open_before = getattr(result, "open_before", None)
    if open_before is not None:
        for path, then in list(rec.unsaved.items()):
            if _in(path, open_before) or _in(path, result.changed):
                continue
            del rec.unsaved[path]
            if store.saved_since(path, then, mtime):
                continue                    # saved since: the mark goes, as store.clear_saved would take it
            _drop(rec.mismatched, path)
            rec.mismatched[path] = then
            unmark.append(path)
    for path in unmark:
        sidecar = read_sidecar(store.sidecar_path(path))
        if sidecar is not None and sidecar.record.unsaved_since:
            out.sidecars.append((store.sidecar_path(path), store.unmarked(sidecar)))
    for path, then in marks.items():
        _drop(rec.unsaved, path)
        _drop(rec.mismatched, path)          # held in memory now: the save the unsaved mark asks for clears both
        rec.unsaved[path] = then
    if changed:
        rec.last_updated = stamp
    if not (result.failures or result.skipped):
        rec.digest = digest
    return out


def _earlier_update(record: LinkRecord, plan: UpdatePlan, result: GearboxUpdate,
                    mtime: Callable[[str], float]) -> str:
    """Whether the record as read shows an earlier Update's change to the assembly that was never saved
    (``gearbox.UPDATE_LOST``, ``gearbox.UPDATE_NOT_SAVED`` or ``""``; see ``Finished``). Read from the record's
    ``unsaved`` mark on the assembly (the earlier finish marks every path of that Update's ``changed``), the
    assembly's file time as this job read it before changing anything (``result.mtimes``, else ``mtime``), and
    ``result.open_before``."""
    asm = plan.assembly
    if not asm:
        return ""
    then = next((t for p, t in record.unsaved.items() if store.same_path(p, asm)), None)
    if then is None:
        return ""
    now = next((t for p, t in (getattr(result, "mtimes", {}) or {}).items() if store.same_path(p, asm)), None)
    if (now is not None and now > then) or (now is None and store.saved_since(asm, then, mtime)):
        return ""                            # saved since: the file holds that Update's changes
    open_before = getattr(result, "open_before", None)
    if open_before is not None and not _in(asm, open_before):
        return gearbox.UPDATE_LOST
    return gearbox.UPDATE_NOT_SAVED


def _follow_trains(box: GearboxRecord, plan: UpdatePlan, result: GearboxUpdate, held: set) -> None:
    """A turning gearbox's mated gears take their wanted frames on record a whole train at a time, or not at all
    (review M1's spirit: a record mixing new and old frames within one train reads out of step next time). A train
    every gear of which was put takes them; so does every train when the update ran to its end with no failure,
    since the worker then left a train unput only because it already stood in step with its wanted frames. Trains
    are the mated gears joined by the meshes and locks given to the worker."""
    wanted = {p.gear: p for p in plan.placements}
    mated = [c.gear for c in box.components if c.gear in wanted and c.gear not in held]
    parent = {g: g for g in mated}

    def root(g: str) -> str:
        while parent[g] != g:
            g = parent[g]
        return g
    links = [(m.a, m.b) for m in plan.motion.meshes] + [(k.anchor, k.follower) for k in plan.motion.locks]
    for a, b in links:
        if a in parent and b in parent:
            parent[root(a)] = root(b)
    whole = not (result.failures or result.skipped)
    placed = set(result.placed)
    trains: Dict[str, List[str]] = {}
    for g in mated:
        trains.setdefault(root(g), []).append(g)
    take = {g for train in trains.values() if whole or all(g in placed for g in train) for g in train}
    for component in box.components:
        if component.gear in take:
            p = wanted[component.gear]
            component.rotation, component.at = list(p.rotation), list(p.at)


def _teeth_held(plan: UpdatePlan, result: GearboxUpdate) -> Dict[str, int]:
    """Each gear's teeth as its part now holds them: the parts the update reached without a failure."""
    out: Dict[str, int] = {}
    for update, done in zip(plan.parts, result.parts):
        if done.failures or not (done.changed or done.unchanged):
            continue
        teeth = _number_or_none(getattr(update.spec, "teeth", None))
        if teeth:
            out.update({g: int(teeth) for g in update.gear_ids})
    return out


def _follow_mates(box: GearboxRecord, plan: UpdatePlan, result: GearboxUpdate) -> None:
    """The record's mates follow what Update set: a MESH entry's ``ratio`` for each gear mate in
    ``result.ratios`` or ``result.ratios_already`` that the plan asked to change (the ratio given, in the mate's
    own gear order), and an ALONG entry's ``z_front`` for each
    gear in ``result.axial`` (where its wanted frame puts its front face). A MESH whose gears' parts now hold teeth
    at the same ratio as the mate (17 : 68 → 34 : 136: no remake needed) takes those counts too, so a later
    classify does not read it as a change, and its pitch is the teeth the parts hold."""
    teeth = _teeth_held(plan, result)
    for entry in box.mates:
        if entry.kind != motion.MESH or len(entry.gears) != 2 or len(entry.ratio) != 2:
            continue
        a, b = entry.gears
        if a in teeth and b in teeth and (teeth[a], teeth[b]) != tuple(entry.ratio) and \
                entry.ratio[0] * teeth[b] == entry.ratio[1] * teeth[a]:
            entry.ratio = [teeth[a], teeth[b]]
    # A gear mate remade (``ratios``), or one the plan asked to change that SolidWorks already held at the wanted
    # ratio and so was not remade (``ratios_already``: a lost Update's record typed back, say), takes the plan's
    # ratio. One found at another ratio and remade though the plan asked no change (``ratios_found``, also in
    # ``ratios``) is not in the plan's ratios: the record already holds the wanted ratio for it.
    set_ratios = set(getattr(result, "ratios", []) or []) | set(getattr(result, "ratios_already", []) or [])
    moved = set(getattr(result, "axial", []) or [])
    given = {name: [int(n), int(d)] for name, n, d in plan.motion.ratios}
    at = {p.gear: p.at for p in plan.placements}
    for entry in box.mates:
        if entry.kind == motion.MESH and entry.name in set_ratios and entry.name in given:
            entry.ratio = list(given[entry.name])
        elif entry.kind == motion.ALONG and entry.gears and entry.gears[0] in moved and entry.gears[0] in at:
            entry.z_front = float(at[entry.gears[0]][2])


def _in(path: str, paths) -> bool:
    return any(store.same_path(path, p) for p in paths)


def _drop(marks: Dict[str, float], path: str) -> None:
    for key in [k for k in marks if store.same_path(k, path)]:
        del marks[key]


def _settled(plan: UpdatePlan, result: GearboxUpdate) -> List[str]:
    """The documents this update loaded from their files (``result.opened``) and found holding what the workbook
    asks, changing nothing in them: each part and the layout reached without a failure and left as it was, and
    the assembly reached, unchanged, with no failure of its own."""
    opened = list(getattr(result, "opened", []) or [])
    out: List[str] = []
    for update, done in zip(plan.parts, result.parts):
        if _in(update.path, opened) and done.unchanged and not done.changed and not done.failures:
            out.append(update.path)
    done = result.layout
    if (plan.layout is not None and done is not None and _in(plan.layout.path, opened) and done.unchanged
            and not done.changed and not done.failures):
        out.append(plan.layout.path)
    asm = plan.assembly
    if (asm and _in(asm, opened) and not _in(asm, result.changed) and not result.placed
            and not any(what == os.path.basename(asm.replace("\\", "/")) for what, _ in result.failures)
            and not result.skipped):
        out.append(asm)
    return out
