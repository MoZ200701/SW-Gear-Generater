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

Interfaces pinned in the W5 interface commit; every body that raises
NotImplementedError is Agent B's. :func:`mate_name`, :func:`face_global`,
:func:`mate_entry` and :func:`mate_ref` are written: each fixes a name or a
shape two packages share.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence, Tuple

from .. import store
from ..gears.base import BuildPlan
from ..swbuild import LockLink, MateRef, MeshLink
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


def motion_reason() -> str:
    """``""`` when every finding a turning Build needs is settled, else the sentence why the gearbox is built
    static instead (W5-PLAN D1's static-by-necessity case; ``GearboxPlan.static_reason``), naming the finding:
    e.g. *how gears are mated to turn is not settled for this version (findings.MOTION_ROUTE).* Read with
    ``getattr(findings, NAME, None)``: ``MOTION_ROUTE == "mates"``, ``AXIS_MATE_ROUTE == "axis coincident"``,
    ``AXIAL_MATE_ROUTE == "origin distance"``, ``GEAR_MATE_FLIP_RULE == "mesh"`` with ``GEAR_MATE_FLIP`` not None,
    ``GEAR_MATE_NUMERATOR_FIRST is True``, ``COMPOUND_LOCK_ROUTE == "lock alone"``, ``MATE_RENAME_ROUTE`` and
    ``MATE_FIND_ROUTE`` set, and ``MATE_LOCK``, ``MATE_GEAR``, ``ADD_MATE_NO_ERROR``, ``LOCK_SELECT_ROUTE``,
    ``COMPONENT_UNDER_DEFINED`` not None. Never a refusal of Build: the W4 static assembly is built instead."""
    raise NotImplementedError("W5: Agent B, workbook.motion.motion_reason")


def update_reason() -> str:
    """``""`` when Update SolidWorks can act on a gearbox built to turn, else the sentence refusing it (an
    ``UpdatePlan.refusal``), naming the finding: ``MESH_PHASE_ROUTE == "Transform2 put with the gear mate on"``;
    ``LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE``, ``LAYOUT_MOVE_CARRIES_MATES``, ``AXIAL_GLOBAL_MOVES_GEAR`` all True;
    ``SUPPRESSION_ROUTE``, ``FEATURE_SUPPRESS``, ``FEATURE_UNSUPPRESS``, ``THIS_CONFIGURATION``,
    ``MATE_FIND_ROUTE`` not None. Also refused: ``GEAR_MATE_RATIO_ROUTE`` set to anything but None or
    ``"remake"`` — ``"modify definition"`` leaves an assembly SolidWorks 2024 cannot close (W5-DECISIONS), and
    the sentence says so. (``GEAR_MATE_RATIO_ROUTE`` None is not a refusal: a tooth change is then structural.)"""
    raise NotImplementedError("W5: Agent B, workbook.motion.update_reason")


def motion_plan(spec: GearboxSpec, report: Report, frames: Mapping[str, Frame]) -> MotionPlan:
    """Every mate of the turning assembly (W5-PLAN §1.2 steps 1-5, with review M9 and M13), called only once
    :func:`motion_reason` is ``""`` and the assessment's ``lay_out_refusal()`` is ``""``. ``frames`` is
    ``layout.frames(report)``; an ALONG's ``z_front`` is its anchor's ``frames[g].at[2]``, and its
    ``face_global`` is set exactly when ``abs(z_front) >= layout.BASE_TOLERANCE``. Gears are those
    ``report.layout.placed`` holds; speeds are ``report.motion.speeds``."""
    raise NotImplementedError("W5: Agent B, workbook.motion.motion_plan")


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
    unfixed. ``plan.check()`` is empty."""
    raise NotImplementedError("W5: Agent B, workbook.motion.motion_assembly_plan")


def mesh_links(meshes: Sequence[Tuple[str, str]], teeth: Mapping[str, int], sigma: Mapping[str, int],
               internal: Mapping[str, bool]) -> Tuple[MeshLink, ...]:
    """A ``swbuild.MeshLink`` per mesh ``(a, b)``, in the order given: b turns ``k`` times a's turn about each
    part's own +Z, ``k = -σa·σb·za/zb`` for an outside mesh and ``+σa·σb·za/zb`` when either gear is internal
    (``σ`` the gear's shaft's +1 for Z+, -1 for Z-), so ``k == ω_b/ω_a`` with ``kinematics.solve``'s speeds
    (review M2: about each shaft's own axis); ``pitch = 360/zb`` degrees."""
    raise NotImplementedError("W5: Agent B, workbook.motion.mesh_links")


def lock_links(locks: Sequence[Tuple[str, str]], teeth: Mapping[str, int]) -> Tuple[LockLink, ...]:
    """A ``swbuild.LockLink`` per lock ``(anchor, follower)``, in the order given, ``pitch = 360/z_follower``
    degrees."""
    raise NotImplementedError("W5: Agent B, workbook.motion.lock_links")
