"""The workbook gearbox that turns: which mates its assembly gets, and the plan that makes them (phase W5).

Pure, on the Tk thread. :func:`motion_plan` decides, from an assessed
workbook, each shaft's **anchor** (its first gear in Gears-sheet order, mated
to the layout's ``"<Shaft> Axis"`` and along it from the layout's Front
plane), the **locks** (every other gear on that shaft held to the anchor
alone), and a **gear mate** per listed mesh that joins two shafts not yet
joined (a mesh that closes a loop gets none: ``unmated``); gears on a fixed
shaft, or on a shaft held still by one, stay fixed. :func:`motion_assembly_plan`
turns that into the assembly's ``BuildPlan``. ``workbook.gearbox`` attaches
both; ``workbook.update.classify`` reads the record's mates back
(:func:`mate_ref`) and makes the links ``swbuild.train_check`` compares
(:func:`mesh_links`, :func:`lock_links`).

Every SolidWorks call these plans lead to rests on probe tier 8
(``findings.py``, "the workbook gearbox that turns (tier 8)" and "tier 8
items 7-13"); docs/notes-workbook/W5-PLAN.md §1.2 is the design, amended by
W5-PLAN-REVIEW.md and W5-DECISIONS.md, and W5-INTERFACES.md pins the shapes.

Interfaces pinned in the W5 interface commit (W5-INTERFACES.md), bodies by
package B. :func:`mate_name`, :func:`face_global`, :func:`mate_entry` and
:func:`mate_ref` fix a name or a shape two packages share; :func:`still_shafts`
is the one rule for which gears stay fixed, shared with ``update.classify``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .. import findings, store
from ..gears import equations
from ..gears.base import AddGlobal, BuildPlan, LinkDimension, Mate, Rebuild, SaveAs, Unfix
from ..gears.spur import AXIS_NAME
from ..swbuild import LockLink, MateRef, MeshLink
from . import layout
from .checks import Report
from .layout import Frame
from .model import GearboxSpec

AXIS, ALONG, LOCK, MESH = "axis", "along", "lock", "mesh"       # MatePlan.kind (and store.MateEntry.kind)
MATE_KINDS = (AXIS, ALONG, LOCK, MESH)
STATIC, MOTION = store.GEARBOX_STATIC, store.GEARBOX_MOTION     # GearboxRecord.kind, GearboxResult.kind
FACE_GLOBAL_SUFFIX = " Face Z"                                  # "G4 Face Z": an anchor's distance along its shaft


@dataclass(frozen=True)
class MatePlan:
    """One mate the turning assembly makes; ``store.MateEntry`` mirrors it field for field (:func:`mate_entry`).

    ``name``: its name in SolidWorks' tree (:func:`mate_name`). ``kind``:
    :data:`AXIS` (the anchor's ``Gear Axis`` coincident with its shaft's
    ``"<Shaft> Axis"``), :data:`ALONG` (the anchor's origin, its front-face
    centre, coincident with or at a distance from the layout's Front plane),
    :data:`LOCK` (a follower held to its anchor) or :data:`MESH` (a gear
    mate). ``gears``: AXIS/ALONG ``(gear,)``; LOCK ``(anchor, follower)``;
    MESH ``(a, b)`` as the Meshes row lists them, which is the gear mate's
    selection order. ``shaft``: AXIS/ALONG the shaft, else ``""``.
    ``ratio``: MESH ``(teeth of a, teeth of b)`` as made, else ``()``.
    ``face_global``: ALONG with a distance, ``"G4 Face Z"``
    (:func:`face_global`); ``""`` when the origin sits on the Front plane
    (|z_front| below ``layout.BASE_TOLERANCE``: a coincident mate, no
    distance) and for every other kind. ``z_front``: ALONG, the origin's
    signed distance from the Front plane in mm (``layout.frames``'s ``at[2]``),
    else 0.
    """

    name: str
    kind: str
    gears: Tuple[str, ...]
    shaft: str = ""
    ratio: Tuple[int, ...] = ()
    face_global: str = ""
    z_front: float = 0.0


@dataclass(frozen=True)
class MotionPlan:
    """Every mate of one turning assembly, decided (:func:`motion_plan`).

    ``anchors``: shaft -> its anchor gear, for every shaft whose gears are
    mated. ``mates``: in plan order — per shaft, in Shafts-sheet order, its
    AXIS, its ALONG, then its LOCKs in Gears-sheet order; then the MESHes in
    Meshes-sheet order. ``fixed``: gears left fixed, as W4 places them — on
    a shaft whose Role is ``fixed`` (W5-PLAN D9), or on a shaft whose solved
    speed is 0 because it meshes only a fixed one (review M9) — in
    Gears-sheet order. ``unmated``: listed meshes with no gear mate because
    their shafts were already joined (a loop: D6), ``(a, b)`` as listed.
    ``trains``: each set of shafts joined by gear mates, input shafts first
    then Shafts-sheet order. ``drag``: per train, the gear to drag in
    SolidWorks, the anchor of its first input shaft. A shaft whose gears
    are mated but that meshes nothing turns alone and is in no train.
    """

    anchors: Mapping[str, str] = field(default_factory=dict)
    mates: Tuple[MatePlan, ...] = ()
    fixed: Tuple[str, ...] = ()
    unmated: Tuple[Tuple[str, str], ...] = ()
    trains: Tuple[Tuple[str, ...], ...] = ()
    drag: Tuple[str, ...] = ()


def mate_name(kind: str, gears: Sequence[str], shaft: str = "") -> str:
    """The name a mate is given in SolidWorks' tree, and found by again (W5-PLAN D12): AXIS ``"G1 on S1 Axis"``
    (the shaft's layout axis is ``"<Shaft> Axis"``), ALONG ``"G1 along S1"``, LOCK ``"G3 locked to G2"`` (gears
    ``(anchor, follower)``: the follower is named first), MESH ``"G1 meshes G2"`` (gears ``(a, b)``). Gear and
    shaft ids are letters, digits, ``_`` and ``-`` (the schema), so no two mates share a name. A kind not in
    :data:`MATE_KINDS`, the wrong number of gears, or a shaft missing from (or given to) a kind is a ValueError."""
    gears = tuple(gears)
    if kind not in MATE_KINDS:
        raise ValueError(f"{kind!r} is not a kind of mate the turning assembly makes ({', '.join(MATE_KINDS)}).")
    wanted = 1 if kind in (AXIS, ALONG) else 2
    if len(gears) != wanted or not all(gears):
        raise ValueError(f"A {kind} mate holds {wanted} gear{'s' if wanted != 1 else ''}, not {gears!r}.")
    if (kind in (AXIS, ALONG)) != bool(shaft):
        raise ValueError(f"A {kind} mate {'needs' if kind in (AXIS, ALONG) else 'takes no'} shaft, and was given "
                         f"{shaft!r}.")
    if kind == AXIS:
        return f"{gears[0]} on {shaft} Axis"
    if kind == ALONG:
        return f"{gears[0]} along {shaft}"
    if kind == LOCK:
        return f"{gears[1]} locked to {gears[0]}"
    return f"{gears[0]} meshes {gears[1]}"


def face_global(gear: str) -> str:
    """The assembly global an anchor's distance along its shaft is linked to: ``"G4 Face Z"`` (unquoted, as
    ``GlobalVariable.name`` takes it)."""
    if not gear:
        raise ValueError("A Face Z global needs a gear's name.")
    return f"{gear}{FACE_GLOBAL_SUFFIX}"


def mate_entry(mate: MatePlan) -> store.MateEntry:
    """The record's entry for a mate made: ``store.MateEntry`` field for field, its tuples as lists (what
    ``finish_build`` writes for a turning assembly)."""
    return store.MateEntry(name=mate.name, kind=mate.kind, gears=list(mate.gears), shaft=mate.shaft,
                           ratio=[int(n) for n in mate.ratio], face_global=mate.face_global,
                           z_front=float(mate.z_front))


def mate_ref(entry: store.MateEntry) -> MateRef:
    """A recorded mate as Update's worker takes it (``swbuild.MateRef``): its name, kind, gears and shaft."""
    return MateRef(name=entry.name, kind=entry.kind, gears=tuple(entry.gears), shaft=entry.shaft)


_SET = object()      # a finding that must merely be settled (not None)

# What a turning Build needs settled (W5-INTERFACES "workbook/motion.py"): (finding, what it says, what it must be).
_BUILD_FINDINGS: Tuple[Tuple[str, str, Any], ...] = (
    ("MOTION_ROUTE", "how a workbook's gears are made to turn", "mates"),
    ("GEAR_MATE_ROUTE", "how two meshing gears are mated", "mates"),
    ("MATED_ASSEMBLY_REBUILD_ROUTE", "how an assembly of mated gears is rebuilt", _SET),
    ("MATE_COINCIDENT", "the number SolidWorks gives a coincident mate", _SET),
    ("MATE_DISTANCE", "the number SolidWorks gives a distance mate", _SET),
    ("AXIS_MATE_ROUTE", "how a gear is mated to its shaft's axis", "axis coincident"),
    ("AXIAL_MATE_ROUTE", "how a gear is held in its place along its shaft", "origin distance"),
    ("GEAR_MATE_FLIP_RULE", "which way a gear mate turns its two gears", "mesh"),
    ("GEAR_MATE_FLIP", "the flip every gear mate is made with", _SET),
    ("GEAR_MATE_NUMERATOR_FIRST", "which gear's teeth a gear mate's ratio takes first", True),
    ("COMPOUND_LOCK_ROUTE", "how two gears on one shaft are held together", "lock alone"),
    ("MATE_RENAME_ROUTE", "how a mate is given its name", _SET),
    ("MATE_FIND_ROUTE", "how a mate is found again by its name", _SET),
    ("MATE_LOCK", "the number SolidWorks gives a lock mate", _SET),
    ("MATE_GEAR", "the number SolidWorks gives a gear mate", _SET),
    ("ADD_MATE_NO_ERROR", "the status SolidWorks gives a mate made without a problem", _SET),
    ("LOCK_SELECT_ROUTE", "how a lock mate's two gears are selected", _SET),
    ("COMPONENT_UNDER_DEFINED", "how SolidWorks says a gear is free to turn", _SET),
)

# What Update SolidWorks needs settled for a gearbox built to turn (GEAR_MATE_RATIO_ROUTE is not one: ruling c).
_UPDATE_FINDINGS: Tuple[Tuple[str, str, Any], ...] = (
    ("MESH_PHASE_ROUTE", "how a meshed gear is turned back to its place", "Transform2 put with the gear mate on"),
    ("LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE", "whether a lock turned back on keeps its gears' new angle", True),
    ("LAYOUT_MOVE_CARRIES_MATES", "whether a moved shaft carries its mated gears with it", True),
    ("AXIAL_GLOBAL_MOVES_GEAR", "whether a gear moves along its shaft with its Face Z global", True),
    ("SUPPRESSION_ROUTE", "how a mate is suppressed and turned back on", _SET),
    ("FEATURE_SUPPRESS", "the number SolidWorks takes to suppress a mate", _SET),
    ("FEATURE_UNSUPPRESS", "the number SolidWorks takes to turn a mate back on", _SET),
    ("THIS_CONFIGURATION", "the number SolidWorks takes for this configuration", _SET),
    ("MATE_FIND_ROUTE", "how a mate is found again by its name", _SET),
)


def _unsettled(table: Sequence[Tuple[str, str, Any]]) -> Optional[Tuple[str, str, Any]]:
    """The first finding of ``table`` that is missing or not what it must be: (name, what it says, its value)."""
    for name, what, wanted in table:
        value = getattr(findings, name, None)
        if value is None:
            return name, what, None
        if wanted is _SET:
            continue
        if (value is not True) if wanted is True else (value != wanted):
            return name, what, value
    return None


def motion_reason() -> str:
    """``""`` when every finding a turning Build needs is settled, else the sentence why the gearbox is built
    static instead (W5-PLAN D1's static-by-necessity case; ``GearboxPlan.static_reason``), naming the finding:
    e.g. *how gears are mated to turn is not settled for this version (findings.MOTION_ROUTE).* Read with
    ``getattr(findings, NAME, None)``: ``MOTION_ROUTE == "mates"``, ``GEAR_MATE_ROUTE == "mates"``,
    ``MATED_ASSEMBLY_REBUILD_ROUTE`` set, ``MATE_COINCIDENT`` and ``MATE_DISTANCE`` not None,
    ``AXIS_MATE_ROUTE == "axis coincident"``,
    ``AXIAL_MATE_ROUTE == "origin distance"``, ``GEAR_MATE_FLIP_RULE == "mesh"`` with ``GEAR_MATE_FLIP`` not None,
    ``GEAR_MATE_NUMERATOR_FIRST is True``, ``COMPOUND_LOCK_ROUTE == "lock alone"``, ``MATE_RENAME_ROUTE`` and
    ``MATE_FIND_ROUTE`` set, and ``MATE_LOCK``, ``MATE_GEAR``, ``ADD_MATE_NO_ERROR``, ``LOCK_SELECT_ROUTE``,
    ``COMPONENT_UNDER_DEFINED`` not None. Never a refusal of Build: the W4 static assembly is built instead, and
    the sentence before Build says so (``ui_text.motion_ready_line``; ruled to stay, review of 2f82a0e).

    The sentence is a whole one, capital first: *How a gear is mated to its shaft's axis is not settled by the
    probes for this version (findings.AXIS_MATE_ROUTE).*, or for a value this version does not build, *The
    probes found 'x' for how a gear is mated to its shaft's axis (findings.AXIS_MATE_ROUTE), which this version
    does not build.*"""
    found = _unsettled(_BUILD_FINDINGS)
    if found is None:
        return ""
    name, what, value = found
    if value is None:
        return f"{what[0].upper()}{what[1:]} is not settled by the probes for this version (findings.{name})."
    return f"The probes found {value!r} for {what} (findings.{name}), which this version does not build."


def update_reason() -> str:
    """``""`` when Update SolidWorks can act on a gearbox built to turn, else the sentence refusing it (an
    ``UpdatePlan.refusal``), naming the finding: ``MESH_PHASE_ROUTE == "Transform2 put with the gear mate on"``;
    ``LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE``, ``LAYOUT_MOVE_CARRIES_MATES``, ``AXIAL_GLOBAL_MOVES_GEAR`` all True;
    ``SUPPRESSION_ROUTE``, ``FEATURE_SUPPRESS``, ``FEATURE_UNSUPPRESS``, ``THIS_CONFIGURATION``,
    ``MATE_FIND_ROUTE`` not None. ``GEAR_MATE_RATIO_ROUTE`` is NOT read here (review of 2f82a0e, ruling c): any
    value but ``"remake"`` makes only a meshed gear's tooth change structural in ``classify`` — its sentence says
    why, and for ``"modify definition"`` that it leaves an assembly SolidWorks 2024 cannot close — while Face Z
    changes, layout moves and turn-backs still go through Update; ``swcom.Session.set_gear_ratio`` refusing
    ``"modify definition"`` is the second guard."""
    found = _unsettled(_UPDATE_FINDINGS)
    if found is None:
        return ""
    name, what, value = found
    lead = "Update SolidWorks cannot change a gearbox built to turn with this version"
    if value is None:
        return f"{lead}: {what} is not settled by the probes (findings.{name})."
    return f"{lead}: the probes found {value!r} for {what} (findings.{name}), which it does not follow."


def still_shafts(spec: GearboxSpec, report: Report) -> Dict[str, str]:
    """Every shaft whose gears stay fixed in a turning assembly, in Shafts-sheet order, mapped to why: ``""`` for a
    shaft whose Role is ``fixed`` (W5-PLAN D9), else the fixed shaft it is held still through — a shaft the
    meshes join, shaft by shaft, to a fixed one and whose solved speed (``report.motion.speeds``) is 0 (review
    M9: kinematics settles such a shaft to 0 without a word, and a gear left free on it would spin in SolidWorks
    against the workbook). Shared by :func:`motion_plan` and ``workbook.update.classify``, so the two never
    disagree on which gears are held."""
    order = [s.id for s in spec.shafts if s.id]
    rank = {s: i for i, s in enumerate(order)}
    placed = report.layout.placed
    joins: Dict[str, Set[str]] = {}
    for mesh in spec.meshes:
        a, b = placed.get(mesh.a), placed.get(mesh.b)
        if a is None or b is None or a.shaft == b.shaft:
            continue
        joins.setdefault(a.shaft, set()).add(b.shaft)
        joins.setdefault(b.shaft, set()).add(a.shaft)
    out: Dict[str, str] = {s.id: "" for s in spec.shafts if s.id and s.role == "fixed"}
    todo = list(out)
    speeds = report.motion.speeds
    while todo:
        shaft = todo.pop(0)
        for other in sorted(joins.get(shaft, ()), key=lambda s: rank.get(s, len(rank))):
            if other in out or speeds.get(other) is None or speeds[other] != 0:
                continue
            out[other] = out[shaft] or shaft
            todo.append(other)
    return {s: out[s] for s in order if s in out}


def motion_plan(spec: GearboxSpec, report: Report, frames: Mapping[str, Frame]) -> MotionPlan:
    """Every mate of the turning assembly (W5-PLAN §1.2 steps 1-5, with review M9 and M13), called only once
    :func:`motion_reason` is ``""`` and the assessment's ``lay_out_refusal()`` is ``""``. ``frames`` is
    ``layout.frames(report)``; an ALONG's ``z_front`` is its anchor's ``frames[g].at[2]``, and its
    ``face_global`` is set exactly when ``abs(z_front) >= layout.BASE_TOLERANCE``. Gears are those
    ``report.layout.placed`` holds; speeds are ``report.motion.speeds``.

    Gears on a shaft :func:`still_shafts` names go to ``fixed`` and get no
    mate, nor does a mesh with a gear among them. Every other shaft with
    gears is mated through its anchor. A mesh whose two shafts the gear mates
    so far already join (one internal mesh closing a loop, or a second mesh
    between the same two shafts) goes to ``unmated``: its ratio follows from
    the others (D6). A placed gear with no frame is a ValueError."""
    placed = report.layout.placed
    order = [s for s in spec.shafts if s.id]
    still = still_shafts(spec, report)
    gears = [g.id for g in spec.gears if g.id in placed]
    on: Dict[str, List[str]] = {s.id: [g for g in gears if placed[g].shaft == s.id] for s in order}
    fixed = tuple(g for g in gears if placed[g].shaft in still)

    anchors: Dict[str, str] = {}
    shaft_mates: List[MatePlan] = []
    for shaft in order:
        if shaft.id in still or not on[shaft.id]:
            continue
        anchor = on[shaft.id][0]
        if anchor not in frames:
            raise ValueError(f"{anchor} is placed but has no frame, so it cannot be mated to {shaft.id}.")
        anchors[shaft.id] = anchor
        z_front = float(frames[anchor].at[2])
        shaft_mates.append(MatePlan(mate_name(AXIS, (anchor,), shaft.id), AXIS, (anchor,), shaft.id))
        shaft_mates.append(MatePlan(mate_name(ALONG, (anchor,), shaft.id), ALONG, (anchor,), shaft.id,
                                    face_global=face_global(anchor) if abs(z_front) >= layout.BASE_TOLERANCE else "",
                                    z_front=z_front))
        for follower in on[shaft.id][1:]:
            shaft_mates.append(MatePlan(mate_name(LOCK, (anchor, follower)), LOCK, (anchor, follower)))

    parent: Dict[str, str] = {}

    def root(shaft: str) -> str:
        while parent.setdefault(shaft, shaft) != shaft:
            parent[shaft] = parent[parent[shaft]]
            shaft = parent[shaft]
        return shaft

    meshes: List[MatePlan] = []
    unmated: List[Tuple[str, str]] = []
    joined: Set[str] = set()
    for mesh in spec.meshes:
        a, b = placed.get(mesh.a), placed.get(mesh.b)
        if a is None or b is None or mesh.a in fixed or mesh.b in fixed or a.shaft == b.shaft:
            continue
        if root(a.shaft) == root(b.shaft):
            unmated.append((mesh.a, mesh.b))
            continue
        parent[root(a.shaft)] = root(b.shaft)
        joined.update((a.shaft, b.shaft))
        meshes.append(MatePlan(mate_name(MESH, (mesh.a, mesh.b)), MESH, (mesh.a, mesh.b),
                               ratio=(int(a.teeth), int(b.teeth))))

    trains: List[Tuple[str, ...]] = []
    seen: Set[str] = set()
    for shaft in order:
        if shaft.id not in joined or root(shaft.id) in seen:
            continue
        seen.add(root(shaft.id))
        members = [s for s in order if s.id in joined and root(s.id) == root(shaft.id)]
        trains.append(tuple(s.id for s in members if s.role == "input")
                      + tuple(s.id for s in members if s.role != "input"))
    drag = tuple(anchors[train[0]] for train in trains)
    return MotionPlan(anchors=anchors, mates=tuple(shaft_mates + meshes), fixed=fixed, unmated=tuple(unmated),
                      trains=tuple(trains), drag=drag)


def motion_assembly_plan(layout_path: str, components: Sequence[Tuple[str, str, Frame]],
                         handle_of: Mapping[str, str], motion: MotionPlan, template: str, path: str) -> BuildPlan:
    """The turning assembly's ``BuildPlan`` (``BuildPlan.kind`` ``layout.ASSEMBLY_KIND``), in W5-PLAN §1.2's op
    order: ``NewAssembly``; an ``AddGlobal`` per ALONG with a face global (``literal(round(abs(z_front), 9))``),
    in plan order; the layout and every gear inserted, placed and fixed exactly as ``layout.assembly_plan``
    does it; then per shaft, ``Unfix`` of its anchor immediately before its AXIS (``Mate`` kind
    ``"coincident"``, ``"<h>:Gear Axis"`` to ``"layout:<Shaft> Axis"``) and its ALONG (``"point"`` to
    ``"layout:plane1"`` at 0, else ``"point distance"`` with value ``z_front`` and a ``LinkDimension`` of its
    ``D1`` to the face global), then each LOCK (``Unfix`` of the follower, ``Mate`` kind ``"lock"`` with bare
    handles, anchor first); then each MESH (``Mate`` kind ``"gear"`` between the two ``Gear Axis``, ratio
    ``(za, zb)``, ``flip=findings.GEAR_MATE_FLIP``); ``Rebuild``; ``SaveAs(path)``. Mate ids by index
    (``axis1``, ``along1``, ``lock1``, ``mesh1``), names from :func:`mate_name`. ``components`` are
    ``(handle, part path, frame)`` as ``layout.assembly_plan`` takes them; ``handle_of`` maps a gear id to its
    handle (``gear<index>``; the reverse of ``GearboxPlan.handles``). Gears in ``motion.fixed`` are never
    unfixed. ``plan.check()`` is empty.

    A mate naming a gear with no handle, or a gear in ``motion.fixed``, or a kind this module does not make,
    is a ValueError with a sentence: the plan would otherwise fail in SolidWorks half made."""
    static = layout.assembly_plan(layout_path, components, template, path)
    if not (len(static.ops) >= 3 and isinstance(static.ops[-2], Rebuild) and isinstance(static.ops[-1], SaveAs)):
        raise ValueError("The static assembly's plan does not end with its rebuild and save, so the turning "
                         "assembly cannot be planned from it.")
    inserted = list(static.ops[1:-2])            # the layout and every gear, inserted, placed and fixed, as W4 does
    flip = getattr(findings, "GEAR_MATE_FLIP", None)
    if flip is None:
        raise ValueError("findings.GEAR_MATE_FLIP, which says the flip every gear mate takes, is not settled, so "
                         "the turning assembly is not planned.")
    held = set(motion.fixed)

    def handle(gear: str, mate: MatePlan) -> str:
        if gear in held:
            raise ValueError(f"{gear} is to stay fixed, so the mate {mate.name} cannot be made on it.")
        if gear not in handle_of:
            raise ValueError(f"{gear} is not in the assembly, so the mate {mate.name} cannot be made on it.")
        return handle_of[gear]

    globals_: List[Any] = []
    mates: List[Any] = []
    gear_mates: List[Any] = []
    count = {AXIS: 0, ALONG: 0, LOCK: 0, MESH: 0}
    lead = layout.LAYOUT_HANDLE
    for mate in motion.mates:
        if mate.kind not in count:
            raise ValueError(f"{mate.kind!r} is not a kind of mate the turning assembly makes, so the mate "
                             f"{mate.name} is not planned.")
        count[mate.kind] += 1
        ident = f"{mate.kind}{count[mate.kind]}"
        if mate.kind == AXIS:
            h = handle(mate.gears[0], mate)
            mates.append(Unfix(h))
            mates.append(Mate(ident, "coincident", f"{h}:{AXIS_NAME}", f"{lead}:{mate.shaft} Axis", name=mate.name))
        elif mate.kind == ALONG:
            h = handle(mate.gears[0], mate)
            if mate.face_global:
                globals_.append(AddGlobal(mate.face_global, equations.literal(round(abs(mate.z_front), 9))))
                mates.append(Mate(ident, "point distance", f"{h}:origin", f"{lead}:plane1", mate.z_front,
                                  name=mate.name))
                mates.append(LinkDimension(f"D1@{mate.name}", equations.quote(mate.face_global)))
            else:
                mates.append(Mate(ident, "point", f"{h}:origin", f"{lead}:plane1", name=mate.name))
        elif mate.kind == LOCK:
            a, b = handle(mate.gears[0], mate), handle(mate.gears[1], mate)
            mates.append(Unfix(b))
            mates.append(Mate(ident, "lock", a, b, name=mate.name))
        else:
            a, b = handle(mate.gears[0], mate), handle(mate.gears[1], mate)
            ratio = tuple(float(n) for n in mate.ratio)
            if len(ratio) != 2 or not all(n > 0 for n in ratio):
                raise ValueError(f"The gear mate {mate.name} needs two tooth counts for its ratio, not "
                                 f"{mate.ratio!r}.")
            gear_mates.append(Mate(ident, "gear", f"{a}:{AXIS_NAME}", f"{b}:{AXIS_NAME}", ratio=ratio, flip=flip,
                                   name=mate.name))
    ops = [static.ops[0]] + globals_ + inserted + mates + gear_mates + [Rebuild(), SaveAs(path)]
    return BuildPlan(layout.ASSEMBLY_KIND, "", tuple(ops), path=path)


def mesh_links(meshes: Sequence[Tuple[str, str]], teeth: Mapping[str, int], sigma: Mapping[str, int],
               internal: Mapping[str, bool]) -> Tuple[MeshLink, ...]:
    """A ``swbuild.MeshLink`` per mesh ``(a, b)``, in the order given: b turns ``k`` times a's turn about each
    part's own +Z, ``k = -σa·σb·za/zb`` for an outside mesh and ``+σa·σb·za/zb`` when either gear is internal
    (``σ`` the gear's shaft's +1 for Z+, -1 for Z-), so ``k == ω_b/ω_a`` with ``kinematics.solve``'s speeds
    (review M2: about each shaft's own axis); ``pitch = 360/zb`` degrees."""
    out = []
    for a, b in meshes:
        za, zb = int(teeth[a]), int(teeth[b])
        if za <= 0 or zb <= 0:
            raise ValueError(f"The mesh {a}–{b} needs a tooth count above 0 on each gear, not {za} and {zb}.")
        sense = 1 if (internal.get(a, False) or internal.get(b, False)) else -1
        out.append(MeshLink(a, b, sense * int(sigma[a]) * int(sigma[b]) * za / zb, 360.0 / zb))
    return tuple(out)


def lock_links(locks: Sequence[Tuple[str, str]], teeth: Mapping[str, int]) -> Tuple[LockLink, ...]:
    """A ``swbuild.LockLink`` per lock ``(anchor, follower)``, in the order given, ``pitch = 360/z_follower``
    degrees."""
    out = []
    for anchor, follower in locks:
        z = int(teeth[follower])
        if z <= 0:
            raise ValueError(f"{follower} needs a tooth count above 0 to be locked to {anchor}, not {z}.")
        out.append(LockLink(anchor, follower, 360.0 / z))
    return tuple(out)
