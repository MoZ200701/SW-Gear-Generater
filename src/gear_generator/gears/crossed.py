"""Crossed-axis helical pairs: two helical gears on shafts at an angle, touching at one point.

The parts are ordinary helical gears (:mod:`gears.helical`), each with its own
helix angle; only how they are placed differs. Both have the same normal module
and normal pressure angle. Of the **same hand**, the shaft angle is
``Σ = β1 + β2``; of **opposite hands**, ``Σ = |β1 − β2|`` — a small shaft angle
from two steep helices. Either way the centre distance, measured along the
common perpendicular of the two axes, is

    C = (mn / 2) · (N1 / cos β1 + N2 / cos β2)

The ratio is the tooth ratio ``N2 / N1``, not the ratio of the pitch diameters.

Placement, worked out here and tested without SolidWorks:

* gear 1 sits as built, its axis on +Z;
* gear 2's axis crosses the X axis at ``x = C``, turned about X by
  ``−(s1 β1 + s2 β2)``, ``s`` +1 for a right hand and −1 for a left — the turn
  that lays gear 2's tooth line along gear 1's at the point where they touch
  (gear 1's leans ``s1 β1`` off its axis toward +Y there, gear 2's, facing back
  along −X, ``−s2 β2``). Same hands give ``∓Σ``, opposite ones ``∓(β1 − β2)``;
* that point is on gear 1's pitch cylinder on +X, at the place along its face
  nearest the middle where one of its tooth spaces is centred on +X, so gear 1
  needs no turning; gear 2 is slid so the point is the middle of its own face,
  and spun so a tooth is centred there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .helical import HelicalDerived

Vector = Tuple[float, float, float]
Matrix = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]

SHAFT_MIN = 10.0        # degrees; a pair closer to parallel than this is a parallel pair
SHAFT_MAX = 170.0
BETA_MIN = 5.0          # the smallest helix angle the solver gives either gear
BETA_WARNING = (10.0, 80.0)
ROOT_SCAN = 120          # samples of β1 when looking for the angles that meet a centre distance
ANGLE_TOLERANCE = 1e-6


def shaft_of(beta_1: float, beta_2: float, opposite: bool = False) -> float:
    """The shaft angle two helix angles make: their sum of the same hand, their difference of opposite hands."""
    return abs(beta_1 - beta_2) if opposite else beta_1 + beta_2


def partner_beta(beta_1: float, shaft: float, opposite: bool = False) -> float:
    """Gear 2's helix angle for gear 1's on shafts ``shaft`` apart: ``Σ − β1``, or of opposite
    hands ``β1 − Σ`` when that is above zero and ``β1 + Σ`` when it is not."""
    if not opposite:
        return shaft - beta_1
    return beta_1 - shaft if beta_1 > shaft else beta_1 + shaft


def centre_distance(module: float, teeth_1: int, teeth_2: int, beta_1: float, beta_2: float) -> float:
    """``(mn / 2) · (N1 / cos β1 + N2 / cos β2)``, angles in degrees."""
    return module / 2.0 * (teeth_1 / math.cos(math.radians(beta_1)) + teeth_2 / math.cos(math.radians(beta_2)))


def beta_1_for(module: float, teeth_1: int, teeth_2: int, shaft: float, centre: float,
               beta_min: float = BETA_MIN) -> Optional[float]:
    """The helix angle of gear 1 that makes the centre distance, nearest half the shaft angle; None if none does.

    ``N1 / cos β1 + N2 / cos (Σ − β1)`` is scanned across ``[β min, Σ − β min]``
    (both angles under 90°) and every crossing of ``2C / mn`` is bisected.
    """
    roots = _roots(module, teeth_1, teeth_2, centre, lambda beta: shaft - beta,
                   max(beta_min, shaft - 90.0 + 1e-6), min(shaft - beta_min, 90.0 - 1e-6))
    if not roots:
        return None
    return min(roots, key=lambda beta: (abs(beta - shaft / 2.0), beta))


def helix_pair_for(module: float, teeth_1: int, teeth_2: int, shaft: float, centre: float, opposite: bool = False,
                   beta_min: float = BETA_MIN) -> Optional[Tuple[float, float]]:
    """``(β1, β2)`` that make the centre distance on shafts ``shaft`` apart; None if no pair does.

    Of the same hand it is :func:`beta_1_for`'s. Of opposite hands both
    families are scanned — ``β2 = β1 − Σ`` and ``β2 = β1 + Σ``, each angle
    between ``β min`` and 90° — and the root with the smaller steeper angle
    wins, since the steeper a helix the more it pushes along its shaft.
    """
    if not opposite:
        beta_1 = beta_1_for(module, teeth_1, teeth_2, shaft, centre, beta_min)
        return None if beta_1 is None else (beta_1, shaft - beta_1)
    found: List[Tuple[float, float]] = []
    top = 90.0 - 1e-6
    for other, low, high in ((lambda beta: beta - shaft, shaft + beta_min, top),
                             (lambda beta: beta + shaft, beta_min, top - shaft)):
        found.extend((beta, other(beta)) for beta in _roots(module, teeth_1, teeth_2, centre, other, low, high))
    if not found:
        return None
    return min(found, key=lambda pair: (max(pair), pair[0]))


def _roots(module: float, teeth_1: int, teeth_2: int, centre: float, other, low: float, high: float) -> List[float]:
    """Every β1 in ``[low, high]`` where ``N1 / cos β1 + N2 / cos other(β1)`` crosses ``2C / mn``, bisected."""
    target = 2.0 * centre / module
    if low >= high:
        return []

    def f(beta: float) -> float:
        return (teeth_1 / math.cos(math.radians(beta)) + teeth_2 / math.cos(math.radians(other(beta)))) - target

    roots: List[float] = []
    step = (high - low) / ROOT_SCAN
    previous_x, previous = low, f(low)
    if previous == 0.0:
        roots.append(low)
    for i in range(1, ROOT_SCAN + 1):
        x = low + step * i
        value = f(x)
        if value == 0.0:
            roots.append(x)
        elif (value > 0.0) != (previous > 0.0) and previous != 0.0:
            a, b, fa = previous_x, x, previous
            for _ in range(80):
                middle = (a + b) / 2.0
                fm = f(middle)
                if (fm > 0.0) == (fa > 0.0):
                    a, fa = middle, fm
                else:
                    b = middle
            roots.append((a + b) / 2.0)
        previous_x, previous = x, value
    return roots


def normal_contact_ratio(module: float, teeth_1: int, teeth_2: int, beta_1: float, beta_2: float,
                         normal_pressure_angle: float) -> float:
    """The contact ratio of the two virtual spur gears in the normal plane, ``zv = z / cos³ β``.

    A crossed pair touches at a point, so this is the figure quoted for it
    rather than a transverse εα.
    """
    alpha = math.radians(normal_pressure_angle)
    total = 0.0
    radii = []
    for teeth, beta in ((teeth_1, beta_1), (teeth_2, beta_2)):
        rv = module * teeth / math.cos(math.radians(beta)) ** 3 / 2.0
        radii.append(rv)
        ra, rb = rv + module, rv * math.cos(alpha)
        total += math.sqrt(max(0.0, ra * ra - rb * rb))
    total -= (radii[0] + radii[1]) * math.sin(alpha)
    return total / (math.pi * module * math.cos(alpha))


# -- placement --------------------------------------------------------------


def rot_x(degrees: float) -> Matrix:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def rot_z(degrees: float) -> Matrix:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def rot_y(degrees: float) -> Matrix:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def apply(matrix: Matrix, v: Sequence[float]) -> Vector:
    return tuple(sum(matrix[i][j] * v[j] for j in range(3)) for i in range(3))  # type: ignore[return-value]


def multiply(a: Matrix, b: Matrix) -> Matrix:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore


@dataclass(frozen=True)
class Placement:
    """Where gear 2 goes, in gear 1's frame (mm, degrees)."""

    rotation: Matrix          # gear 2's frame: the turn about X, then its spin about its own axis
    origin: Vector            # gear 2's part origin
    contact: Vector           # the point the two pitch cylinders touch
    gear_1_contact_z: float   # along gear 1's axis
    gear_2_contact_z: float   # along gear 2's own axis
    spin: float               # gear 2 about its own axis, degrees, in [0, 360 / N2)
    tilt: float               # the turn about X: −Σ right-hand, +Σ left-hand
    centre_distance: float

    @property
    def axis_2(self) -> Vector:
        return apply(self.rotation, (0.0, 0.0, 1.0))


def twist_at(g: HelicalDerived, z: float) -> float:
    """How far gear ``g``'s section at ``z`` is turned from the one drawn on its profile plane, in degrees."""
    return g.hand_sign * 360.0 * (z + g.overrun) / g.lead


def placement(gear_1: HelicalDerived, gear_2: HelicalDerived, shaft: float) -> Placement:
    """Gear 2's frame, and where the gears touch, for a crossed pair at shaft angle ``shaft``, either hands."""
    tilt = -(gear_1.hand_sign * gear_1.helix_angle_deg + gear_2.hand_sign * gear_2.helix_angle_deg)
    if abs(abs(tilt) - shaft) > ANGLE_TOLERANCE:
        raise ValueError(f"Helix angles of {gear_1.helix_angle_deg:g}° and {gear_2.helix_angle_deg:g}°, "
                         f"{'the same hand' if gear_1.hand == gear_2.hand else 'opposite hands'}, put the shafts "
                         f"{abs(tilt):g}° apart, not {shaft:g}°.")
    r1, r2 = gear_1.rp, gear_2.rp
    centre = r1 + r2
    # Gear 1's space centres cross +X every axial pitch; take the crossing nearest its face's middle.
    axial_pitch = gear_1.lead / gear_1.teeth
    middle = gear_1.face_width / 2.0
    z1 = -gear_1.overrun + round((middle + gear_1.overrun) / axial_pitch) * axial_pitch
    z2 = gear_2.face_width / 2.0
    # Gear 2's tooth centre at its face's middle must point back at gear 1, azimuth 180°.
    pitch_2 = 360.0 / gear_2.teeth
    spin = (180.0 - pitch_2 / 2.0 - twist_at(gear_2, z2)) % pitch_2
    turn = rot_x(tilt)
    rotation = multiply(turn, rot_z(spin))
    contact = (r1, 0.0, z1)
    local = apply(turn, (-r2, 0.0, z2))
    origin = (contact[0] - local[0], contact[1] - local[1], contact[2] - local[2])
    return Placement(rotation=rotation, origin=origin, contact=contact, gear_1_contact_z=z1, gear_2_contact_z=z2,
                     spin=spin, tilt=tilt, centre_distance=centre)


def tooth_direction(g: HelicalDerived, azimuth: float) -> Vector:
    """The tooth line's direction on ``g``'s pitch cylinder at ``azimuth`` degrees, in its own frame, per mm of z."""
    rate = math.radians(twist_at(g, 1.0) - twist_at(g, 0.0))
    a = math.radians(azimuth)
    return (-g.rp * math.sin(a) * rate, g.rp * math.cos(a) * rate, 1.0)


def angle_between(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / norm))))


def validate(gear_1: HelicalDerived, gear_2: HelicalDerived, shaft: float) -> List[str]:
    """What stops two helical gears meshing on crossed shafts, as sentences. Empty when they do."""
    problems: List[str] = []
    if not SHAFT_MIN <= shaft <= SHAFT_MAX:
        problems.append(f"The shaft angle must be between {SHAFT_MIN:g}° and {SHAFT_MAX:g}° (got {shaft:g}°).")
    opposite = gear_1.hand != gear_2.hand
    if abs(gear_1.module - gear_2.module) > 1e-9:
        problems.append(f"Both gears need the same normal module (got {gear_1.module:g} and {gear_2.module:g}).")
    if abs(gear_1.normal_pressure_angle_deg - gear_2.normal_pressure_angle_deg) > 1e-9:
        problems.append("Both gears need the same normal pressure angle.")
    if getattr(gear_1, "shift", 0.0) or getattr(gear_2, "shift", 0.0):
        problems.append("Crossed helical gears are built without profile shift here; set both shifts to 0.")
    made = shaft_of(gear_1.helix_angle_deg, gear_2.helix_angle_deg, opposite)
    if abs(made - shaft) > ANGLE_TOLERANCE:
        if opposite:
            problems.append(f"Of opposite hands the two helix angles differ by {made:g}°, not the shaft angle of "
                            f"{shaft:g}°.")
        else:
            problems.append(f"Of the same hand the two helix angles add up to {made:g}°, not the shaft angle of "
                            f"{shaft:g}°.")
    return problems


__all__ = [
    "Placement", "angle_between", "apply", "beta_1_for", "centre_distance", "helix_pair_for", "multiply",
    "normal_contact_ratio", "partner_beta", "placement", "rot_x", "rot_y", "rot_z", "shaft_of", "tooth_direction",
    "twist_at", "validate",
]
