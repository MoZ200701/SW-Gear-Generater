"""Where each gear is, and how far it is turned (docs/PLAN-WORKBOOK.md §3.3; phase W3: parallel shafts).

Positions are in millimetres from the workbook's origin. Phase W3 works out
gearboxes whose shafts are all held by the frame with axes along Z+ or Z-;
anything else (a turned axis, a planet on a carrier) is a later phase's, and
:func:`layout` says so rather than guessing.

**Phase.** Every part is built with a tooth *space* centred on its own +X on
the plane its section is drawn on, its blank extruded from its front face
(local z = 0) along local +Z. A spur's space is on +X at every height. A
helical section turns ``s·360·(z − z_s)/L`` degrees about local +Z at height z
(``s`` +1 for a right hand, :data:`helical.RIGHT_HAND_TURN`; ``L`` the lead),
counted from where it is drawn, ``z_s``: for a helical gear or ring the Profile
Plane, one overrun (a normal module) *behind* the front face, ``z_s = −o``, so
even the front face is turned ``s·360·o/L``; for a herringbone the apex,
``z_s = w/2``, its far half the near half mirrored there
(:meth:`helical.HelicalDerived.turn_at`). A gear turned by θ about its own axis
has, at global height Z, a space centred on the global angle

    g(Z) = σ · (θ + s · 2π · (z_local(Z) − z_s) / L),   z_local = σ · (Z − Z_front)

where σ is +1 for an axis along Z+ and −1 for Z- (a part on a Z- axis is the
same part turned over, which mirrors its angles in the global view). Counting
from the front face instead is wrong by ``s·2π·o/L`` on every helical gear, the
same as sliding each part one overrun along its own axis: two gears facing the
same way slide together and their mesh is unchanged, but two facing opposite
ways slide apart, and that put the teeth into each other. Meshing is
a condition on these global angles at a plane both faces share:

- external, gear q at direction φ from gear p:  g_q = φ + π − π/z_q − (g_p − φ)·z_p/z_q
- a pinion p in a ring r, at direction φ from the ring's centre:
  g_p = φ − π/z_p + (g_r − φ)·z_r/z_p, and back, g_r = φ + (g_p − φ + π/z_p)·z_p/z_r

each modulo one pitch of the gear being placed. At θ_p = φ = 0 the first is
:func:`pair.mesh_angle` and the second :func:`pair.internal_mesh_angle`.
Profile shift is symmetric about the space centre and changes none of this.
The tests hold every formula to the outlines themselves, turned as the part's
build plan turns them (not by this module's own twist): placed meshed they do
not overlap, and turned half a pitch they do.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..gears import kind_for
from .model import Gear, GearboxSpec, Shaft
from .schema import FRAME

AXES = {"Z+": 1, "Z-": -1}


@dataclass(frozen=True)
class Placed:
    """One gear where the workbook puts it."""

    gear: str
    shaft: str
    x: float                 # the axis, from the origin, mm
    y: float
    z: float                 # the middle of the face, along global Z, mm
    sigma: int               # +1 for an axis along Z+, -1 for Z-
    face: float              # face width, mm
    teeth: int
    module: float
    internal: bool
    derived: object          # the strip's own derived gear (spur, helical, ring)
    hand_sign: int = 0       # +1 right, -1 left; 0 for a spur
    lead: float = 0.0        # mm per turn of the helix; 0 for a spur
    herringbone: bool = False
    spec: object = None      # the strip's GearSpec for this gear, for its outline

    @property
    def z_front(self) -> float:
        """Where the part's front face (its origin plane) sits along global Z."""
        return self.z - self.sigma * self.face / 2.0

    @property
    def z_range(self) -> Tuple[float, float]:
        return (self.z - self.face / 2.0, self.z + self.face / 2.0)

    @property
    def tip_radius(self) -> float:
        return self.derived.da / 2.0

    @property
    def outer_radius(self) -> float:
        """The farthest the part reaches from its axis: a ring's rim, any other gear's tip."""
        return getattr(self.derived, "rim", self.derived.da) / 2.0 if self.internal else self.derived.da / 2.0

    def twist(self, z_global: float) -> float:
        """The helix's turn at a global height, about the part's own axis, radians (0 for a spur).

        Counted from where the part's section is drawn, as the part is built
        (:meth:`helical.HelicalDerived.turn_at`): a helical gear's or ring's
        Profile Plane one overrun behind its front face, a herringbone's apex.
        """
        if not self.lead:
            return 0.0
        return math.radians(self.derived.turn_at(self.sigma * (z_global - self.z_front)))

    def space_angle(self, theta: float, z_global: float) -> float:
        """Global angle of a tooth space's centre at a global height, for a part turned θ about its own axis."""
        return self.sigma * (theta + self.twist(z_global))

    def theta_for(self, space: float, z_global: float) -> float:
        """The turn θ that puts a space at a global angle at a global height (the inverse of :meth:`space_angle`)."""
        return self.sigma * space - self.twist(z_global)


@dataclass
class Layout:
    placed: Dict[str, Placed] = field(default_factory=dict)
    later: List[str] = field(default_factory=list)     # sentences: what this phase does not lay out, and why
    problems: Dict[str, str] = field(default_factory=dict)   # gear -> why it could not be placed
    # each gear not in ``placed`` -> why, a few words: every gear row is either placed or here. Keyed by its
    # name, or by its row when it has none (``Gears row 5``) or shares it (``G3 on Gears row 5``).
    left_out: Dict[str, str] = field(default_factory=dict)


# The kinds no phase before W6 lays out, as a few words for a list of what was left out.
LATER_KINDS = {"bevel": "a bevel gear, phase W6", "sleeve": "a sleeve, phase W8", "dog": "a dog ring, phase W8"}


def layout(spec: GearboxSpec, skip_gears=()) -> Layout:
    """Every gear placed, when every shaft is on the frame with an axis along Z+ or Z-."""
    out = Layout()
    shafts = {s.id: s for s in spec.shafts}
    for shaft in spec.shafts:
        if shaft.mount() != FRAME:
            out.later.append(f"{shaft.id} is mounted on {shaft.mount()}: carriers are laid out in phase W7.")
        elif (shaft.axis or "Z+") not in AXES:
            out.later.append(f"{shaft.id}'s axis is {shaft.axis}: axes other than Z+ and Z- are laid out in "
                             f"phase W6.")
    names = [g.id for g in spec.gears]

    def label(gear: Gear) -> str:
        if not gear.id:
            return f"Gears row {gear.row}"
        return f"{gear.id} on Gears row {gear.row}" if names.count(gear.id) > 1 else gear.id

    if out.later:
        out.left_out = {label(g): "not laid out until a later phase" for g in spec.gears}
        return out
    for gear in spec.gears:
        if gear.kind_word() in LATER_KINDS:
            out.left_out[label(gear)] = LATER_KINDS[gear.kind_word()]
            continue
        if gear.id in skip_gears or not gear.id or names.count(gear.id) > 1:
            out.left_out[label(gear)] = "an error of its own"     # a blank or shared name is the read's error
            continue
        shaft = shafts.get(gear.shaft)
        if shaft is None:
            out.left_out[label(gear)] = "no such shaft"
            continue
        try:
            out.placed[gear.id] = _place(spec, gear, shaft)
        except (ValueError, TypeError) as exc:
            out.problems[gear.id] = str(exc)
            out.left_out[label(gear)] = "could not be placed"
    return out


def _place(spec: GearboxSpec, gear: Gear, shaft: Shaft) -> Placed:
    sigma = AXES[shaft.axis or "Z+"]
    gear_spec = gear.gear_spec(spec.box)
    kind = kind_for(gear_spec)
    derived = kind.derive(gear_spec)
    helical = gear_spec.kind in ("helical", "herringbone")
    z = float(shaft.z or 0) + sigma * float(gear.at or 0)
    return Placed(
        gear=gear.id, shaft=shaft.id, x=float(shaft.x), y=float(shaft.y), z=z, sigma=sigma,
        face=float(gear.face_width), teeth=int(float(gear.teeth)), module=float(gear.module),
        internal=gear_spec.is_internal(), derived=derived,
        hand_sign=getattr(derived, "hand_sign", 0) if helical else 0,
        lead=getattr(derived, "lead", 0.0) if helical else 0.0,
        herringbone=gear_spec.kind == "herringbone",
        spec=gear_spec,
    )


def _wrap(angle: float, pitch: float) -> float:
    return angle - pitch * math.floor(angle / pitch)


def external_space(g_p: float, z_p: int, z_q: int, phi: float) -> float:
    """Where gear q's space must be, globally, to mesh outside gear p seen at direction φ from p."""
    return _wrap(phi + math.pi - math.pi / z_q - (g_p - phi) * z_p / z_q, 2.0 * math.pi / z_q)


def pinion_space(g_ring: float, z_ring: int, z_pinion: int, phi: float) -> float:
    """Where a pinion's space must be, to mesh inside a ring whose centre sees it at direction φ."""
    return _wrap(phi - math.pi / z_pinion + (g_ring - phi) * z_ring / z_pinion, 2.0 * math.pi / z_pinion)


def ring_space(g_pinion: float, z_pinion: int, z_ring: int, phi: float) -> float:
    """Where a ring's space must be, to mesh with a pinion inside it at direction φ from the ring's centre."""
    return _wrap(phi + (g_pinion - phi + math.pi / z_pinion) * z_pinion / z_ring, 2.0 * math.pi / z_ring)


def mesh_plane(a: Placed, b: Placed) -> float:
    """The global height the two faces share: the middle of their overlap."""
    lo = max(a.z_range[0], b.z_range[0])
    hi = min(a.z_range[1], b.z_range[1])
    return (lo + hi) / 2.0


def phases(spec: GearboxSpec, placed: Dict[str, Placed], with_conflicts: bool = False):
    """θ for every gear reachable through the meshes, radians; with ``with_conflicts``, also the loops that
    do not close.

    Each train starts from a gear on an input shaft when it has one (θ = 0),
    else its first gear. Gears on one shaft turn together but each part keeps
    its own θ: a compound pair's second gear is placed by the mesh it is in,
    since nothing fixes one to the other until W5's lock. A gear reached a
    second way must agree, to a hundredth of its pitch; one that does not is
    a loop that does not close, reported as ``(gear, the gear asking otherwise)``.
    """
    meshes: Dict[str, List[str]] = {}
    for mesh in spec.meshes:
        if mesh.a in placed and mesh.b in placed:
            meshes.setdefault(mesh.a, []).append(mesh.b)
            meshes.setdefault(mesh.b, []).append(mesh.a)
    inputs = {s.id for s in spec.shafts if s.role == "input"}
    starts = [g for g in placed if placed[g].shaft in inputs] + list(placed)
    theta: Dict[str, float] = {}
    conflicts: List[Tuple[str, str]] = []
    for start in starts:
        if start in theta:
            continue
        theta[start] = 0.0
        queue = deque([start])
        while queue:
            p = queue.popleft()
            for q in meshes.get(p, []):
                wanted = place_against(placed[p], theta[p], placed[q])
                if q in theta:
                    pitch = 2.0 * math.pi / placed[q].teeth
                    off = (wanted - theta[q]) % pitch
                    if min(off, pitch - off) > pitch / 100.0 and (q, p) not in conflicts and (p, q) not in conflicts:
                        conflicts.append((q, p))
                    continue
                theta[q] = wanted
                queue.append(q)
    return (theta, conflicts) if with_conflicts else theta


def place_against(p: Placed, theta_p: float, q: Placed) -> float:
    """θ for gear q so it meshes with gear p, already turned θ_p."""
    plane = mesh_plane(p, q)
    g_p = p.space_angle(theta_p, plane)
    if q.internal and not p.internal:          # p is the pinion, q the ring around it
        phi = math.atan2(p.y - q.y, p.x - q.x)
        g_q = ring_space(g_p, p.teeth, q.teeth, phi)
    elif p.internal and not q.internal:        # q is the pinion inside ring p
        phi = math.atan2(q.y - p.y, q.x - p.x)
        g_q = pinion_space(g_p, p.teeth, q.teeth, phi)
    else:
        phi = math.atan2(q.y - p.y, q.x - p.x)
        g_q = external_space(g_p, p.teeth, q.teeth, phi)
    return q.theta_for(g_q, plane)


def centre_distance(a: Placed, b: Placed) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def faces_overlap(a: Placed, b: Placed) -> float:
    """How much two faces share along Z, mm (negative: the gap between them)."""
    return min(a.z_range[1], b.z_range[1]) - max(a.z_range[0], b.z_range[0])


def extent(placed: Dict[str, Placed]) -> Optional[Tuple[Tuple[float, float], ...]]:
    """The box the placed gears fill, ``((x from, x to), (y from, y to), (z from, z to))`` in mm from the origin,
    or None.

    Across X and Y it is each gear's outside diameter — the tip circle, or a
    ring's rim — and along Z its face. Shafts, bores and a housing are not in it,
    nor any gear not placed (:attr:`Layout.left_out`): a caller saying it as the
    gearbox's size says what that leaves out.
    """
    if not placed:
        return None
    gears = list(placed.values())
    return ((min(g.x - g.outer_radius for g in gears), max(g.x + g.outer_radius for g in gears)),
            (min(g.y - g.outer_radius for g in gears), max(g.y + g.outer_radius for g in gears)),
            (min(g.z_range[0] for g in gears), max(g.z_range[1] for g in gears)))
