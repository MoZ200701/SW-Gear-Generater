"""Solving a gear pair: from a centre distance and a ratio to module and teeth.

Deterministic, and exhaustive over what it looks at. For each allowed module
the tooth sum ``S = 2C / m`` is tried at both whole numbers either side of it,
and the driver count at the nearest split of that sum and one either side. Then,
for exact-ratio tooth pairs no standard module lands on, the module that *would*
land on the centre distance exactly is offered as a non-standard row.

Rows are ranked by what matters most first: hitting the centre distance, being
a module you can buy a cutter for, not being undercut, needing no profile
shift, the ratio error, and then the larger module, which is the stronger tooth.

**Profile shift** closes a small centre-distance gap. For a parallel pair of
external spur or helical gears at a standard module, a row that misses the
centre distance is offered again with the shifts ``x1 + x2`` that move its
working centre distance ``a0 · cos α / cos αw`` onto it, and an exact row whose
pinion undercuts is offered again with ``x1 = −x2`` (the centre distance does
not move) just big enough to clear it. The sum is split evenly unless that
leaves a gear undercut, in which case that gear takes what it needs and the
other the rest. A shifted row is dropped if either tip, before backlash, would
be thinner than the form warns about, or the tip clearance under 0.1 module; the
form still warns when a gear's backlash thins its tip past that.

A **bevel** pair is solved from its cone distance, ``R = (m / 2) √(N1² + N2² +
2 N1 N2 cos Σ) / sin Σ``, in place of a centre distance.

An **internal** pair is a pinion inside a ring: the tooth *difference* is
``2C / m``, the pinion ``S / (i − 1)``, and a row whose teeth would clash as they
mesh is ranked after the clean ones, as an undercut row is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import List, Optional, Tuple

from .. import findings
from ..spec import (
    HANDS_OPPOSITE,
    MOTION_FIXED,
    MOTION_GEAR_MATE,
    KIND_BEVEL,
    HAND_LEFT,
    HAND_RIGHT,
    HELICAL_KINDS,
    KIND_HERRINGBONE,
    KIND_SPUR,
    MESH_EXTERNAL,
    MESH_INTERNAL,
    GearSpec,
    InputError,
    PairSpec,
)
from . import bevel, crossed, equations, helical, internal, standards
from .base import (
    AddComponent,
    AddGlobal,
    BuildPlan,
    Fix,
    LinkDimension,
    ManualStep,
    Mate,
    NewAssembly,
    Place,
    Rebuild,
    SaveAs,
    Unfix,
)
from .spur import (
    AXIS_NAME,
    TIP_THICKNESS_WARNING,
    contact_ratio,
    inv,
    tooth_depth,
    undercut_free_shift,
    undercut_minimum,
    undercut_teeth,
    working_centre_distance,
    working_pressure_angle,
)

# Rows below this share of Min teeth are not offered at all: the undercut takes
# so much of the flank that listing them only buries the useful ones.
FLOOR_SHARE = 0.7
ABSOLUTE_FLOOR = 6
TOLERANCE = 1e-9
DEFAULT_LIMIT = 120
SHIFT_SUM_LIMIT = 1.0    # the most x1 + x2 the solver offers, either way
SHIFT_LIMIT = 1.0        # and the most either gear takes
CLEARANCE_MIN = 0.1      # × module: a shifted row whose tips come nearer the other gear's root is not offered


@dataclass(frozen=True)
class Candidate:
    module: float
    teeth_driver: int
    teeth_driven: int
    standard: bool
    ratio: float
    centre_distance: float
    ratio_error: float        # relative: |actual − wanted| / wanted
    centre_error: float       # mm, actual − wanted
    undercut: bool
    contact_ratio: float
    helix_angle: float = 0.0  # degrees; 0 for a spur pair
    overlap: float = 0.0      # εβ, from gear A's face width; nan when it cannot be read
    mesh: str = MESH_EXTERNAL
    clash: float = 0.0        # mm the teeth of an internal pair run into each other; 0 when they clear
    helix_angle_b: float = 0.0  # a crossed pair's second helix angle, degrees; 0 otherwise
    shaft_angle: float = 0.0    # a crossed or bevel pair's shaft angle, degrees; 0 for parallel shafts
    cone: bool = False          # a bevel pair: centre_distance is the cone distance
    shift_1: float = 0.0        # profile shift coefficients; centre_distance is then the working one
    shift_2: float = 0.0
    opposite: bool = False      # a crossed pair of opposite hands: shaft_angle = |β1 − β2|

    @property
    def crossed(self) -> bool:
        return self.shaft_angle > 0.0 and not self.cone

    @property
    def shifted(self) -> bool:
        return bool(self.shift_1 or self.shift_2)

    @property
    def exact(self) -> bool:
        return abs(self.centre_error) <= TOLERANCE and self.ratio_error <= TOLERANCE

    @property
    def clashes(self) -> bool:
        return self.clash > internal.CLASH_TOLERANCE

    def rank(self) -> tuple:
        # Parallel: the smaller helix, the less axial thrust. Crossed, same hand: the
        # nearer the two helix angles are to each other, the less the sliding;
        # opposite hands: the gentler the steeper of the two.
        if self.crossed:
            helix = max(self.helix_angle, self.helix_angle_b) if self.opposite else \
                abs(self.helix_angle - self.shaft_angle / 2.0)
        else:
            helix = self.helix_angle
        return (
            abs(self.centre_error) > TOLERANCE,
            not self.standard,
            self.undercut,
            self.clashes,
            self.shifted,
            round(self.ratio_error, 12),
            # Among a crossed pair's near misses, the nearer the better; parallel rows keep their order.
            round(abs(self.centre_error), 9) if self.crossed else 0.0,
            -self.module,
            round(helix, 9),
            # Of two shifted rows otherwise alike, the smaller shifts.
            round(abs(self.shift_1) + abs(self.shift_2), 9),
            self.teeth_driver,
        )


def floor_teeth(min_teeth: int) -> int:
    return max(ABSOLUTE_FLOOR, int(math.ceil(FLOOR_SHARE * min_teeth - TOLERANCE)))


def describe(module: float, teeth_driver: int, teeth_driven: int,
             pressure_angle: float = 20.0, helix_angle: float = 0.0,
             mesh: str = MESH_EXTERNAL, shift_1: float = 0.0, shift_2: float = 0.0) -> Tuple[float, float, float]:
    """The other direction: ``(centre distance, ratio, contact ratio)`` of a pair.

    For a helical pair ``module`` and ``pressure_angle`` are the normal ones,
    the centre distance is ``mt (N1 + N2) / 2`` and the contact ratio is the
    transverse one, εα; the overlap εβ depends on the face width and is
    :func:`helical.overlap_ratio`. An internal pair's driven gear is the ring,
    and its centre distance is ``mt (N2 − N1) / 2``. Shifted external gears
    sit at their working centre distance.
    """
    mt = module / math.cos(math.radians(helix_angle))
    alpha = helical.transverse_pressure_angle(pressure_angle, helix_angle) if helix_angle else pressure_angle
    if mesh == MESH_INTERNAL:
        if shift_1 or shift_2:
            raise ValueError("A pinion inside a ring is built without profile shift here.")
        centre = mt * (teeth_driven - teeth_driver) / 2.0
        epsilon = internal.contact_ratio(module, teeth_driver, teeth_driven, alpha, centre, transverse_module=mt)
    else:
        centre = working_centre_distance(module, teeth_driver, teeth_driven, alpha, shift_1, shift_2, mt)
        epsilon = contact_ratio(module, teeth_driver, teeth_driven, alpha, centre, transverse_module=mt,
                                shift_1=shift_1, shift_2=shift_2)
    return centre, teeth_driven / teeth_driver, epsilon


def tip_clearance(module: float, teeth_1: int, teeth_2: int, pressure_angle: float = 20.0,
                  helix_angle: float = 0.0, shift_1: float = 0.0, shift_2: float = 0.0) -> float:
    """The smaller gap between one gear's tip and the other's root, mm, at the working centre distance.

    Unshifted it is the depth less two addenda, a quarter of a module above
    module 1.25; shifts that add up to more than the centre distance grows by
    eat into it.
    """
    mt = module / math.cos(math.radians(helix_angle))
    alpha = helical.transverse_pressure_angle(pressure_angle, helix_angle) if helix_angle else pressure_angle
    centre = working_centre_distance(module, teeth_1, teeth_2, alpha, shift_1, shift_2, mt)
    depth = tooth_depth(module)
    tip_1 = teeth_1 * mt / 2.0 + module * (1.0 + shift_1)
    tip_2 = teeth_2 * mt / 2.0 + module * (1.0 + shift_2)
    return min(centre - tip_1 - (tip_2 - depth), centre - tip_2 - (tip_1 - depth))


def tip_thickness(module: float, teeth: int, pressure_angle: float = 20.0, helix_angle: float = 0.0,
                  shift: float = 0.0) -> float:
    """A gear's transverse tooth thickness at its tip circle, mm, with no backlash.

    ``s_a = d_a (s / d + inv αt − inv α_a)``, ``cos α_a = d_b / d_a``, where
    ``s = mt π / 2 + 2 x mn tan αt`` at the pitch circle.
    """
    mt = module / math.cos(math.radians(helix_angle))
    alpha = math.radians(helical.transverse_pressure_angle(pressure_angle, helix_angle)
                         if helix_angle else pressure_angle)
    d = teeth * mt
    da = d + 2.0 * module * (1.0 + shift)
    db = d * math.cos(alpha)
    s = mt * math.pi / 2.0 + 2.0 * shift * module * math.tan(alpha)
    return da * (s / d + inv(alpha) - inv(math.acos(min(1.0, db / da))))


def _undercut(teeth: int, limit: float, shift: float) -> bool:
    """Below the unshifted ``limit`` as the whole number it is quoted as (17 at 20°), times ``1 − x``."""
    return teeth < undercut_teeth(limit, shift) - 1e-9


def split_shift(total: float, teeth_1: int, teeth_2: int, limit_1: float, limit_2: float) -> Tuple[float, float]:
    """``x1 + x2 = total`` shared out: evenly, unless that leaves a gear undercut.

    A gear whose half would undercut takes the least shift that clears it (to
    the hundredth), and the other gear the rest. ``limit_n`` is the tooth count
    gear n needs unshifted.
    """
    x1 = x2 = total / 2.0
    need_1 = undercut_free_shift(teeth_1, limit_1) if _undercut(teeth_1, limit_1, x1) else None
    need_2 = undercut_free_shift(teeth_2, limit_2) if _undercut(teeth_2, limit_2, x2) else None
    if need_1 is not None and (need_2 is None or teeth_1 <= teeth_2):
        x1 = need_1
        x2 = total - x1
    elif need_2 is not None:
        x2 = need_2
        x1 = total - x2
    return x1, x2


def _shifted(row: Candidate, centre: float, pressure_angle: float, limit_1: float,
             limit_2: float) -> Optional[Candidate]:
    """``row`` again with profile shift, or None when shifting does not help or cannot be done cleanly.

    A row that misses ``centre`` gets the shifts that move it onto it; an
    exact row that undercuts gets equal and opposite ones that clear it.
    """
    m, n1, n2, beta = row.module, row.teeth_driver, row.teeth_driven, row.helix_angle
    alpha_t = helical.transverse_pressure_angle(pressure_angle, beta) if beta else pressure_angle
    if abs(row.centre_error) > TOLERANCE:
        cosine = row.centre_distance * math.cos(math.radians(alpha_t)) / centre
        if not 0.0 < cosine < 1.0:
            return None
        tan_normal = math.tan(math.radians(pressure_angle))
        total = (n1 + n2) * (inv(math.acos(cosine)) - inv(math.radians(alpha_t))) / (2.0 * tan_normal)
        if abs(total) > SHIFT_SUM_LIMIT:
            return None
        x1, x2 = split_shift(total, n1, n2, limit_1, limit_2)
    elif _undercut(n1, limit_1, 0.0):
        x1 = undercut_free_shift(n1, limit_1)
        x2 = -x1
    elif _undercut(n2, limit_2, 0.0):
        x2 = undercut_free_shift(n2, limit_2)
        x1 = -x2
    else:
        # Exact and cut clean: nothing to shift. (A row under Min teeth but above
        # the rack's limit is a preference no shift can meet.)
        return None
    if max(abs(x1), abs(x2)) > SHIFT_LIMIT:
        return None
    if min(tip_thickness(m, n1, pressure_angle, beta, x1),
           tip_thickness(m, n2, pressure_angle, beta, x2)) < TIP_THICKNESS_WARNING * m:
        return None
    if tip_clearance(m, n1, n2, pressure_angle, beta, x1, x2) < CLEARANCE_MIN * m:
        return None
    actual, _, epsilon = describe(m, n1, n2, pressure_angle, beta, shift_1=x1, shift_2=x2)
    return Candidate(
        module=m, teeth_driver=n1, teeth_driven=n2, standard=row.standard, ratio=row.ratio,
        centre_distance=actual, ratio_error=row.ratio_error, centre_error=actual - centre,
        undercut=_undercut(n1, limit_1, x1) or _undercut(n2, limit_2, x2), contact_ratio=epsilon,
        helix_angle=beta, overlap=row.overlap, mesh=row.mesh, shift_1=x1, shift_2=x2,
    )


def shift_for_centre(module: float, teeth_1: int, teeth_2: int, centre: float, pressure_angle: float = 20.0,
                     helix_angle: float = 0.0) -> Tuple[float, float]:
    """The profile shifts ``(x1, x2)`` that put an outside pair exactly at ``centre``, or a sentence why not.

    The same sum the solver's shifted rows use, shared out by :func:`split_shift`
    against each gear's undercut limit, and refused past the same limits: a
    shift sum or a shift over 1, a tip thinner than the warning, or tips too
    near the other gear's root. Used where a centre distance is given rather
    than solved for: a workbook's shafts (PLAN-WORKBOOK §3.6). Full precision is
    returned; rounding it to look tidy moves the centre (x 0.085 instead of
    0.084550 misses 64 mm by 0.0013 mm).
    """
    m, z1, z2, beta = module, teeth_1, teeth_2, helix_angle
    alpha_t = helical.transverse_pressure_angle(pressure_angle, beta) if beta else pressure_angle
    plain = module / math.cos(math.radians(beta)) * (z1 + z2) / 2.0
    cosine = plain * math.cos(math.radians(alpha_t)) / centre
    if not 0.0 < cosine < 1.0:
        raise ValueError(f"No profile shift brings these teeth to {_num(centre)} mm; their plain centre distance "
                         f"is {_num(plain)} mm.")
    total = (z1 + z2) * (inv(math.acos(cosine)) - inv(math.radians(alpha_t))) / (2.0 * math.tan(math.radians(pressure_angle)))
    if abs(total) > SHIFT_SUM_LIMIT:
        raise ValueError(f"Meeting {_num(centre)} mm needs shifts adding up to {total:+.3f}, past the ±{SHIFT_SUM_LIMIT:g} "
                         f"this tool offers; move the shaft instead.")
    if beta:
        limit_1 = limit_2 = helical.undercut_minimum(pressure_angle, beta)
    else:
        limit_1 = limit_2 = undercut_minimum(pressure_angle)
    x1, x2 = split_shift(total, z1, z2, limit_1, limit_2)
    if max(abs(x1), abs(x2)) > SHIFT_LIMIT:
        raise ValueError(f"Meeting {_num(centre)} mm needs a shift of {max(abs(x1), abs(x2)):.3f} on one gear, past "
                         f"the {SHIFT_LIMIT:g} this tool offers; move the shaft instead.")
    if min(tip_thickness(m, z1, pressure_angle, beta, x1),
           tip_thickness(m, z2, pressure_angle, beta, x2)) < TIP_THICKNESS_WARNING * m:
        raise ValueError(f"The shifts that meet {_num(centre)} mm leave a tooth tip too thin; move the shaft instead.")
    if tip_clearance(m, z1, z2, pressure_angle, beta, x1, x2) < CLEARANCE_MIN * m:
        raise ValueError(f"The shifts that meet {_num(centre)} mm bring the tips too near the other gear's root; "
                         "move the shaft instead.")
    return x1, x2


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _offer_shifted(found: dict, centre: float, pressure_angle: float) -> None:
    """Add a shifted row for every standard row that misses the centre distance or undercuts.

    Undercut here is the rack's own limit, ``2 cos β (1 − x) / sin² αt``, which
    is what the form warns by, so a shift the solver says clears it does.
    """
    for row in list(found.values()):
        if not row.standard or row.shifted:
            continue
        if row.helix_angle:
            limit = helical.undercut_minimum(pressure_angle, row.helix_angle)
        else:
            limit = undercut_minimum(pressure_angle)
        made = _shifted(row, centre, pressure_angle, limit, limit)
        if made is not None:
            found[(round(made.module, 9), made.teeth_driver, made.teeth_driven, round(made.helix_angle, 9),
                   round(made.shift_1, 9), round(made.shift_2, 9))] = made


def _candidate(module: float, n1: int, n2: int, centre: float, ratio: float, pressure_angle: float,
               min_teeth: int, standard: bool, helix_angle: float = 0.0,
               face_width: Optional[float] = None, mesh: str = MESH_EXTERNAL) -> Candidate:
    actual_centre, actual_ratio, epsilon = describe(module, n1, n2, pressure_angle, helix_angle, mesh)
    if helix_angle:
        limit = int(math.floor(helical.undercut_minimum(pressure_angle, helix_angle) + 0.5))
        overlap = helical.overlap_ratio(module, helix_angle, face_width) if face_width else math.nan
    else:
        limit, overlap = min_teeth, 0.0
    clash = 0.0
    if mesh == MESH_INTERNAL and n2 - n1 < internal.CLASH_CHECK_BELOW:
        alpha = helical.transverse_pressure_angle(pressure_angle, helix_angle) if helix_angle else pressure_angle
        clash = internal.tip_clash(module / math.cos(math.radians(helix_angle)), n1, n2, alpha)
    return Candidate(
        module=module,
        teeth_driver=n1,
        teeth_driven=n2,
        standard=standard,
        ratio=actual_ratio,
        centre_distance=actual_centre,
        ratio_error=abs(actual_ratio - ratio) / ratio,
        centre_error=actual_centre - centre,
        # A ring is not generated by a rack: only its pinion can undercut.
        undercut=(n1 if mesh == MESH_INTERNAL else min(n1, n2)) < limit,
        contact_ratio=epsilon,
        helix_angle=helix_angle,
        overlap=overlap,
        mesh=mesh,
        clash=clash,
    )


def solve(centre: float, ratio: float, pressure_angle: float = 20.0, module: Optional[float] = None,
          series: str = standards.SERIES_1, min_teeth: int = 17, max_teeth: int = 200,
          limit: int = DEFAULT_LIMIT, kind: str = KIND_SPUR, helix_angle: Optional[float] = None,
          helix_range: Tuple[float, float] = helical.DEFAULT_RANGE[helical.KIND_HELICAL],
          face_width: Optional[float] = None, mesh: str = MESH_EXTERNAL, shafts: str = "parallel",
          shaft_angle: float = 90.0, opposite: bool = False) -> List[Candidate]:
    """Every candidate worth listing, best first.

    For the helical kinds ``module`` and ``pressure_angle`` are normal, and
    the pair's centre distance is ``mn (N1 + N2) / (2 cos β)``. A typed
    ``helix_angle`` is held, and the search is spur's with ``2C cos β`` in
    place of ``2C``. Left ``None``, every whole tooth sum whose helix angle
    lands inside ``helix_range`` is tried, and each such row meets the centre
    distance exactly: the helix angle is what takes up the difference.

    ``mesh`` internal makes the driven gear a ring round the driver: the ratio
    must then be more than one. ``opposite`` makes a crossed pair's hands
    opposite, so its shaft angle is the helix angles' difference.
    """
    if kind == KIND_BEVEL:
        return _solve_bevel(centre, ratio, shaft_angle, pressure_angle, module, series, min_teeth, max_teeth, limit)
    if mesh == MESH_INTERNAL:
        return _solve_internal(centre, ratio, pressure_angle, module, series, min_teeth, max_teeth, limit,
                               kind, helix_angle, helix_range, face_width)
    if shafts == "crossed":
        return _solve_crossed(centre, ratio, shaft_angle, pressure_angle, module, series, min_teeth, max_teeth, limit,
                              helix_angle, opposite)
    if kind in HELICAL_KINDS:
        return _solve_helical(centre, ratio, pressure_angle, module, series, min_teeth, max_teeth, limit,
                              helix_angle, helix_range, face_width)
    if centre <= 0:
        raise InputError("Centre distance must be more than zero.")
    if ratio <= 0:
        raise InputError("Ratio must be more than zero.")
    floor = floor_teeth(min_teeth)
    if max_teeth < floor:
        raise InputError(f"Max teeth ({max_teeth}) is below the smallest gear the solver offers ({floor}).")

    allowed = (float(module),) if module is not None else standards.modules(series)
    found = {}

    def offer(m: float, n1: int, n2: int, standard: bool) -> None:
        if not (floor <= n1 <= max_teeth and floor <= n2 <= max_teeth):
            return
        key = (round(m, 9), n1, n2)
        if key not in found:
            found[key] = _candidate(m, n1, n2, centre, ratio, pressure_angle, min_teeth, standard)

    for m in allowed:
        total = 2.0 * centre / m
        sums = {int(math.floor(total + TOLERANCE)), int(math.ceil(total - TOLERANCE))}
        for s in sorted(sums):
            middle = int(math.floor(s / (1.0 + ratio) + 0.5))
            for n1 in (middle - 1, middle, middle + 1):
                offer(m, n1, s - n1, standard=module is None or standards.is_standard(m))

    if module is None:
        exact = Fraction(ratio).limit_denominator(max_teeth)
        p, q = exact.numerator, exact.denominator
        k = 1
        while k * max(p, q) <= max_teeth:
            n1, n2 = k * q, k * p
            m_star = 2.0 * centre / (n1 + n2)
            if not any(abs(m_star - m) <= TOLERANCE for m in allowed):
                offer(m_star, n1, n2, standard=False)
            k += 1

    _offer_shifted(found, centre, pressure_angle)
    ranked = sorted(found.values(), key=Candidate.rank)
    return ranked[:limit]


def _solve_helical(centre: float, ratio: float, pressure_angle: float, module: Optional[float], series: str,
                   min_teeth: int, max_teeth: int, limit: int, helix_angle: Optional[float],
                   helix_range: Tuple[float, float], face_width: Optional[float]) -> List[Candidate]:
    if centre <= 0:
        raise InputError("Centre distance must be more than zero.")
    if ratio <= 0:
        raise InputError("Ratio must be more than zero.")
    if helix_angle is not None and not 0.0 < helix_angle <= helical.HELIX_MAX:
        raise InputError(f"Helix angle must be more than 0° and at most {helical.HELIX_MAX:g}° (got {helix_angle:g}°).")
    floor = floor_teeth(min_teeth)
    if max_teeth < floor:
        raise InputError(f"Max teeth ({max_teeth}) is below the smallest gear the solver offers ({floor}).")
    allowed = (float(module),) if module is not None else standards.modules(series)
    found = {}

    def offer(m: float, n1: int, n2: int, standard: bool, beta: float) -> None:
        if not (floor <= n1 <= max_teeth and floor <= n2 <= max_teeth):
            return
        key = (round(m, 9), n1, n2, round(beta, 9))
        if key not in found:
            found[key] = _candidate(m, n1, n2, centre, ratio, pressure_angle, min_teeth, standard, beta, face_width)

    def splits(total: int):
        middle = int(math.floor(total / (1.0 + ratio) + 0.5))
        return ((n1, total - n1) for n1 in (middle - 1, middle, middle + 1))

    if helix_angle is not None:
        cos_beta = math.cos(math.radians(helix_angle))
        for m in allowed:
            total = 2.0 * centre * cos_beta / m
            for s in sorted({int(math.floor(total + TOLERANCE)), int(math.ceil(total - TOLERANCE))}):
                for n1, n2 in splits(s):
                    offer(m, n1, n2, module is None or standards.is_standard(m), helix_angle)
        if module is None:
            exact = Fraction(ratio).limit_denominator(max_teeth)
            p, q = exact.numerator, exact.denominator
            k = 1
            while k * max(p, q) <= max_teeth:
                n1, n2 = k * q, k * p
                m_star = 2.0 * centre * cos_beta / (n1 + n2)
                if not any(abs(m_star - m) <= TOLERANCE for m in allowed):
                    offer(m_star, n1, n2, False, helix_angle)
                k += 1
    else:
        low, high = helix_range
        if not 0.0 < low <= high <= helical.HELIX_MAX:
            raise InputError(f"The helix range must run upward from above 0° to at most {helical.HELIX_MAX:g}° "
                             f"(got {low:g} to {high:g}).")
        for m in allowed:
            first = int(math.ceil(2.0 * centre * math.cos(math.radians(high)) / m - TOLERANCE))
            last = int(math.floor(2.0 * centre * math.cos(math.radians(low)) / m + TOLERANCE))
            for s in range(max(first, 2 * floor), last + 1):
                cosine = min(1.0, m * s / (2.0 * centre))
                beta = math.degrees(math.acos(cosine))
                for n1, n2 in splits(s):
                    offer(m, n1, n2, module is None or standards.is_standard(m), beta)

    _offer_shifted(found, centre, pressure_angle)
    ranked = sorted(found.values(), key=Candidate.rank)
    return ranked[:limit]


def _solve_internal(centre: float, ratio: float, pressure_angle: float, module: Optional[float], series: str,
                    min_teeth: int, max_teeth: int, limit: int, kind: str, helix_angle: Optional[float],
                    helix_range: Tuple[float, float], face_width: Optional[float]) -> List[Candidate]:
    """A pinion inside a ring: every whole tooth difference ``S`` near ``2C cos β / m``, the pinion at ``S / (i − 1)``."""
    if centre <= 0:
        raise InputError("Centre distance must be more than zero.")
    if ratio <= 1.0:
        raise InputError(f"An internal pair's ring is the bigger gear, so the ratio must be more than one "
                         f"(got {ratio:g}); type it as 3, or 3:1.")
    helical_kind = kind in HELICAL_KINDS
    if helical_kind and helix_angle is not None and not 0.0 < helix_angle <= helical.HELIX_MAX:
        raise InputError(f"Helix angle must be more than 0° and at most {helical.HELIX_MAX:g}° (got {helix_angle:g}°).")
    floor = floor_teeth(min_teeth)
    if max_teeth < floor:
        raise InputError(f"Max teeth ({max_teeth}) is below the smallest gear the solver offers ({floor}).")
    allowed = (float(module),) if module is not None else standards.modules(series)
    found = {}

    def offer(m: float, n1: int, n2: int, standard: bool, beta: float) -> None:
        if not (floor <= n1 and n1 < n2 <= max_teeth):
            return
        key = (round(m, 9), n1, n2, round(beta, 9))
        if key not in found:
            found[key] = _candidate(m, n1, n2, centre, ratio, pressure_angle, min_teeth, standard, beta, face_width,
                                    MESH_INTERNAL)

    def splits(difference: int):
        middle = int(math.floor(difference / (ratio - 1.0) + 0.5))
        return ((n1, n1 + difference) for n1 in (middle - 1, middle, middle + 1))

    if not helical_kind or helix_angle is not None:
        beta = helix_angle if helical_kind else 0.0
        cos_beta = math.cos(math.radians(beta))
        for m in allowed:
            total = 2.0 * centre * cos_beta / m
            for s in sorted({int(math.floor(total + TOLERANCE)), int(math.ceil(total - TOLERANCE))}):
                if s < 1:
                    continue
                for n1, n2 in splits(s):
                    offer(m, n1, n2, module is None or standards.is_standard(m), beta)
        if module is None:
            exact = Fraction(ratio).limit_denominator(max_teeth)
            p, q = exact.numerator, exact.denominator
            k = 1
            while k * p <= max_teeth:
                n1, n2 = k * q, k * p
                m_star = 2.0 * centre * cos_beta / (n2 - n1)
                if not any(abs(m_star - m) <= TOLERANCE for m in allowed):
                    offer(m_star, n1, n2, False, beta)
                k += 1
    else:
        low, high = helix_range
        if not 0.0 < low <= high <= helical.HELIX_MAX:
            raise InputError(f"The helix range must run upward from above 0° to at most {helical.HELIX_MAX:g}° "
                             f"(got {low:g} to {high:g}).")
        for m in allowed:
            first = int(math.ceil(2.0 * centre * math.cos(math.radians(high)) / m - TOLERANCE))
            last = int(math.floor(2.0 * centre * math.cos(math.radians(low)) / m + TOLERANCE))
            for s in range(max(first, 1), last + 1):
                beta = math.degrees(math.acos(min(1.0, m * s / (2.0 * centre))))
                for n1, n2 in splits(s):
                    offer(m, n1, n2, module is None or standards.is_standard(m), beta)

    ranked = sorted(found.values(), key=Candidate.rank)
    return ranked[:limit]


def _solve_crossed(centre: float, ratio: float, shaft: float, pressure_angle: float, module: Optional[float],
                   series: str, min_teeth: int, max_teeth: int, limit: int,
                   helix_angle: Optional[float], opposite: bool = False) -> List[Candidate]:
    """Two helical gears on shafts ``shaft`` degrees apart: the same hand, ``β1 + β2 = Σ``, or
    opposite hands, ``|β1 − β2| = Σ``.

    With ``helix_angle`` (β1) typed, the tooth counts are the ones whose centre
    distance comes nearest, as a parallel pair's are. Left blank, every tooth
    pair that fits gets the helix angles that meet the centre distance exactly:
    of the same hand the β1 nearest half the shaft angle, of opposite hands the
    pair whose steeper angle is gentlest.
    """
    if centre <= 0:
        raise InputError("Centre distance must be more than zero.")
    if ratio <= 0:
        raise InputError("Ratio must be more than zero.")
    if not crossed.SHAFT_MIN <= shaft <= crossed.SHAFT_MAX:
        raise InputError(f"The shaft angle must be between {crossed.SHAFT_MIN:g}° and {crossed.SHAFT_MAX:g}° "
                         f"(got {shaft:g}°).")
    typed_2 = crossed.partner_beta(helix_angle, shaft, opposite) if helix_angle is not None else None
    if helix_angle is not None and not (0.0 < helix_angle < 90.0 and 0.0 < typed_2 < 90.0):
        raise InputError(f"A helix angle of {helix_angle:g}° leaves the other gear {typed_2:g}° on "
                         f"{shaft:g}° shafts; both must be between 0° and 90°.")
    floor = floor_teeth(min_teeth)
    if max_teeth < floor:
        raise InputError(f"Max teeth ({max_teeth}) is below the smallest gear the solver offers ({floor}).")
    allowed = (float(module),) if module is not None else standards.modules(series)
    found = {}

    def offer(m: float, n1: int, n2: int, standard: bool, beta_1: float, beta_2: float) -> None:
        if not (floor <= n1 <= max_teeth and floor <= n2 <= max_teeth):
            return
        key = (round(m, 9), n1, n2, round(beta_1, 9))
        if key in found:
            return
        actual = crossed.centre_distance(m, n1, n2, beta_1, beta_2)
        limit_1 = helical.undercut_minimum(pressure_angle, beta_1)
        limit_2 = helical.undercut_minimum(pressure_angle, beta_2)
        found[key] = Candidate(
            module=m, teeth_driver=n1, teeth_driven=n2, standard=standard, ratio=n2 / n1,
            centre_distance=actual, ratio_error=abs(n2 / n1 - ratio) / ratio, centre_error=actual - centre,
            undercut=n1 < int(math.floor(limit_1 + 0.5)) or n2 < int(math.floor(limit_2 + 0.5)),
            contact_ratio=crossed.normal_contact_ratio(m, n1, n2, beta_1, beta_2, pressure_angle),
            helix_angle=beta_1, helix_angle_b=beta_2, shaft_angle=shaft, opposite=opposite,
        )

    for m in allowed:
        standard = module is None or standards.is_standard(m)
        if helix_angle is not None:
            c1 = 1.0 / math.cos(math.radians(helix_angle))
            c2 = 1.0 / math.cos(math.radians(typed_2))
            middle = 2.0 * centre / (m * (c1 + ratio * c2))
            for n1 in range(int(math.floor(middle)) - 1, int(math.ceil(middle)) + 2):
                if n1 >= 1:
                    offer(m, n1, int(math.floor(ratio * n1 + 0.5)), standard, helix_angle, typed_2)
            continue
        target = 2.0 * centre / m
        for n1 in range(floor, max_teeth + 1):
            n2 = int(math.floor(ratio * n1 + 0.5))
            if n1 + n2 > target + TOLERANCE:
                break
            angles = crossed.helix_pair_for(m, n1, n2, shaft, centre, opposite)
            if angles is not None:
                offer(m, n1, n2, standard, *angles)
    if helix_angle is not None and module is None:
        exact = Fraction(ratio).limit_denominator(max_teeth)
        p, q = exact.numerator, exact.denominator
        c1 = 1.0 / math.cos(math.radians(helix_angle))
        c2 = 1.0 / math.cos(math.radians(typed_2))
        k = 1
        while k * max(p, q) <= max_teeth:
            n1, n2 = k * q, k * p
            m_star = 2.0 * centre / (n1 * c1 + n2 * c2)
            if not any(abs(m_star - m) <= TOLERANCE for m in allowed):
                offer(m_star, n1, n2, False, helix_angle, typed_2)
            k += 1

    ranked = sorted(found.values(), key=Candidate.rank)
    return ranked[:limit]


def bevel_forms(n1: int, n2: int, shaft: float) -> Tuple[str, str]:
    """What each gear of a bevel pair is: ``cone``, ``crown`` or ``internal`` (:func:`bevel.form_of`)."""
    delta_1 = bevel.pitch_cone_angle(n1, n2, shaft)
    return bevel.form_of(delta_1), bevel.form_of(shaft - delta_1)


def bevel_candidate(module: float, n1: int, n2: int, shaft: float, pressure_angle: float = 20.0,
                    cone_distance: Optional[float] = None, ratio: Optional[float] = None,
                    standard: bool = True) -> Optional[Candidate]:
    """A bevel pair's row: its cone distance, whether either gear undercuts on its back cone, and εα.

    Either gear may be a crown gear (δ = 90°) or an internal bevel (δ > 90°);
    None when one is too near a crown gear to be built as either. An internal
    bevel pair's ``clash`` is the tip clash of the virtual pair on the back
    cones, worked out with their tooth counts rounded: a warning, as a ring's.
    """
    delta_1 = bevel.pitch_cone_angle(n1, n2, shaft)
    delta_2 = shaft - delta_1
    forms = bevel.form_of(delta_1), bevel.form_of(delta_2)
    if not all(forms) or min(delta_1, delta_2) <= 0.0:
        return None
    if forms[0] == bevel.FORM_CROWN:
        delta_1, delta_2 = 90.0, shaft - 90.0
    elif forms[1] == bevel.FORM_CROWN:
        delta_1, delta_2 = shaft - 90.0, 90.0
    radius = bevel.cone_distance(module, n1, n2, shaft)
    ha_1, ha_2 = bevel.addenda(module, n1, n2, delta_1, delta_2)
    undercut = False
    for n, delta, ha, form in ((n1, delta_1, ha_1, forms[0]), (n2, delta_2, ha_2, forms[1])):
        if form == bevel.FORM_CONE:
            undercut |= n / math.cos(math.radians(delta)) < bevel.undercut_limit(pressure_angle, (ha - module) / module)
    epsilon = bevel.pair_contact_ratio(module, pressure_angle, n1, n2, delta_1, delta_2, ha_1, ha_2)
    clash = 0.0
    if bevel.FORM_INTERNAL in forms:
        ring = 0 if forms[0] == bevel.FORM_INTERNAL else 1
        teeth = [int(round(2.0 * bevel.virtual_radius(module, n, d) / module)) for n, d in ((n1, delta_1), (n2, delta_2))]
        pinion_v, ring_v = teeth[1 - ring], teeth[ring]
        if ring_v - pinion_v < internal.CLASH_CHECK_BELOW:
            clash = internal.tip_clash(module, pinion_v, ring_v, pressure_angle) if ring_v > pinion_v else math.inf
    wanted_ratio = n2 / n1 if ratio is None else ratio
    return Candidate(
        module=module, teeth_driver=n1, teeth_driven=n2, standard=standard, ratio=n2 / n1,
        centre_distance=radius, ratio_error=abs(n2 / n1 - wanted_ratio) / wanted_ratio,
        centre_error=radius - (radius if cone_distance is None else cone_distance), undercut=undercut,
        contact_ratio=epsilon, shaft_angle=shaft, cone=True, clash=clash,
    )


def _solve_bevel(cone_distance: float, ratio: float, shaft: float, pressure_angle: float, module: Optional[float],
                 series: str, min_teeth: int, max_teeth: int, limit: int) -> List[Candidate]:
    """Straight bevel gears on shafts ``shaft`` degrees apart, from the cone distance and the ratio.

    For each module the pinion is ``K / √(1 + i² + 2 i cos Σ)`` with ``K = 2 R sin Σ / m``,
    tried at the whole numbers either side and one beyond; then, for exact-ratio
    tooth pairs, the module that lands on the cone distance exactly.
    """
    if cone_distance <= 0:
        raise InputError("Cone distance must be more than zero.")
    if ratio <= 0:
        raise InputError("Ratio must be more than zero.")
    if not bevel.SHAFT_MIN <= shaft <= bevel.SHAFT_MAX:
        raise InputError(f"The shaft angle must be between {bevel.SHAFT_MIN:g}° and {bevel.SHAFT_MAX:g}° "
                         f"(got {shaft:g}°).")
    floor = floor_teeth(min_teeth)
    if max_teeth < floor:
        raise InputError(f"Max teeth ({max_teeth}) is below the smallest gear the solver offers ({floor}).")
    allowed = (float(module),) if module is not None else standards.modules(series)
    s = math.radians(shaft)
    spread = math.sqrt(1.0 + ratio ** 2 + 2.0 * ratio * math.cos(s))
    found = {}

    def offer(m: float, n1: int, n2: int, standard: bool) -> None:
        if not (floor <= n1 <= max_teeth and floor <= n2 <= max_teeth):
            return
        key = (round(m, 9), n1, n2)
        if key not in found:
            row = bevel_candidate(m, n1, n2, shaft, pressure_angle, cone_distance, ratio, standard)
            if row is not None:
                found[key] = row

    for m in allowed:
        middle = 2.0 * cone_distance * math.sin(s) / m / spread
        for n1 in range(int(math.floor(middle)) - 1, int(math.ceil(middle)) + 2):
            if n1 >= 1:
                offer(m, n1, int(math.floor(ratio * n1 + 0.5)), module is None or standards.is_standard(m))
    if module is None:
        exact = Fraction(ratio).limit_denominator(max_teeth)
        p, q = exact.numerator, exact.denominator
        k = 1
        while k * max(p, q) <= max_teeth:
            n1, n2 = k * q, k * p
            m_star = 2.0 * cone_distance * math.sin(s) / math.sqrt(n1 ** 2 + n2 ** 2 + 2.0 * n1 * n2 * math.cos(s))
            if not any(abs(m_star - m) <= TOLERANCE for m in allowed):
                offer(m_star, n1, n2, False)
            k += 1

    ranked = sorted(found.values(), key=Candidate.rank)
    return ranked[:limit]


def solve_spec(pair: PairSpec) -> List[Candidate]:
    kind = pair.gear_a.kind
    mesh = pair.mesh_value()
    if kind == KIND_BEVEL:
        return solve(
            centre=pair.cone_distance_mm(),
            ratio=pair.ratio_value(),
            pressure_angle=pair.gear_a.pressure_angle_deg(),
            module=pair.module_mm(),
            series=pair.series or standards.SERIES_1,
            min_teeth=pair.min_teeth_count(),
            max_teeth=pair.max_teeth_count(),
            kind=kind,
            shaft_angle=pair.shaft_angle_deg(),
        )
    if kind in HELICAL_KINDS and pair.shafts_value() == "crossed":
        return solve(
            centre=pair.centre_distance_mm(),
            ratio=pair.ratio_value(),
            pressure_angle=pair.gear_a.pressure_angle_deg(),
            module=pair.module_mm(),
            series=pair.series or standards.SERIES_1,
            min_teeth=pair.min_teeth_count(),
            max_teeth=pair.max_teeth_count(),
            kind=kind,
            helix_angle=pair.helix_angle_deg(),
            shafts="crossed",
            shaft_angle=pair.shaft_angle_deg(),
            opposite=pair.hands_value() == HANDS_OPPOSITE,
        )
    if mesh == MESH_INTERNAL:
        try:
            width: Optional[float] = pair.gear_a.face_width_mm()
        except InputError:
            width = None
        helical_kind = kind in HELICAL_KINDS
        return solve(
            centre=pair.centre_distance_mm(),
            ratio=pair.ratio_value(),
            pressure_angle=pair.gear_a.pressure_angle_deg(),
            module=pair.module_mm(),
            series=pair.series or standards.SERIES_1,
            min_teeth=pair.min_teeth_count(),
            max_teeth=pair.max_teeth_count(),
            kind=kind,
            helix_angle=pair.helix_angle_deg() if helical_kind else None,
            helix_range=pair.helix_range(helical.DEFAULT_RANGE[kind]) if helical_kind else (8.0, 25.0),
            face_width=width,
            mesh=MESH_INTERNAL,
        )
    if kind in HELICAL_KINDS:
        try:
            width: Optional[float] = pair.gear_a.face_width_mm()
        except InputError:
            width = None
        return solve(
            centre=pair.centre_distance_mm(),
            ratio=pair.ratio_value(),
            pressure_angle=pair.gear_a.pressure_angle_deg(),
            module=pair.module_mm(),
            series=pair.series or standards.SERIES_1,
            min_teeth=pair.min_teeth_count(),
            max_teeth=pair.max_teeth_count(),
            kind=kind,
            helix_angle=pair.helix_angle_deg(),
            helix_range=pair.helix_range(helical.DEFAULT_RANGE[kind]),
            face_width=width,
        )
    return solve(
        centre=pair.centre_distance_mm(),
        ratio=pair.ratio_value(),
        pressure_angle=pair.gear_a.pressure_angle_deg(),
        module=pair.module_mm(),
        series=pair.series or standards.SERIES_1,
        min_teeth=pair.min_teeth_count(),
        max_teeth=pair.max_teeth_count(),
    )


def partner_hand(hand_a: str, ring: bool = False, crossed_shafts: bool = False, opposite: bool = False) -> str:
    """The hand gear B must have to mesh with gear A: the other one on parallel shafts, the same
    round a ring, and on crossed shafts the same or, with ``opposite``, the other."""
    same = str(hand_a).strip().lower()
    other = HAND_LEFT if same == HAND_RIGHT else HAND_RIGHT
    if ring:
        return same
    if crossed_shafts:
        return other if opposite else same
    return other


def apply(candidate: Candidate, gear_a: GearSpec, gear_b: GearSpec) -> Tuple[GearSpec, GearSpec]:
    """Write module, teeth and profile shift into both gears — and for a helical pair the helix
    angle, and gear B the other hand from gear A (the same hand, round a ring); for a bevel pair
    each gear's mate teeth and the shaft angle — and touch nothing else.

    The shift is written whether the row has one or not: a shift left over from
    an earlier row would move the pair off the centre distance this one meets.
    """
    module = equations.literal(round(candidate.module, 6))
    a = gear_a.with_values(module=module, teeth=str(candidate.teeth_driver),
                           profile_shift=equations.literal(round(candidate.shift_1, 9)))
    b = gear_b.with_values(module=module, teeth=str(candidate.teeth_driven),
                           profile_shift=equations.literal(round(candidate.shift_2, 9)))
    if candidate.cone:
        shaft = equations.literal(round(candidate.shaft_angle, 6))
        a = a.with_values(mate_teeth=str(candidate.teeth_driven), shaft_angle=shaft)
        b = b.with_values(mate_teeth=str(candidate.teeth_driver), shaft_angle=shaft)
        return a, b
    if candidate.crossed:
        a = a.with_values(helix_angle=equations.literal(round(candidate.helix_angle, 6)))
        b = b.with_values(helix_angle=equations.literal(round(candidate.helix_angle_b, 6)),
                          hand=partner_hand(gear_a.hand, crossed_shafts=True, opposite=candidate.opposite))
        return a, b
    if candidate.helix_angle:
        beta = equations.literal(round(candidate.helix_angle, 6))
        a = a.with_values(helix_angle=beta)
        b = b.with_values(helix_angle=beta, hand=partner_hand(gear_a.hand, ring=candidate.mesh == MESH_INTERNAL))
    return a, b


def mesh_angle(teeth_driven: int) -> float:
    """How far gear 2 turns so a tooth faces gear 1's space, in degrees.

    Both parts are built with a tooth *space* centred on +X. Gear 2 sits on +X of
    gear 1 facing back along −X, so for its teeth to mesh it must present a
    tooth there: already true for an odd count, half a tooth pitch away for an
    even one.
    """
    return 0.0 if teeth_driven % 2 else 180.0 / teeth_driven


def mate_angle(teeth_driven: int) -> float:
    """The mesh angle as the assembly's angle mate holds it: never zero.

    An odd count meshes one whole tooth pitch round just as it does at zero,
    and a zero-degree angle mate is not something the probe exercised — nor is
    a zero a value a dimension can be told apart by.
    """
    return mesh_angle(teeth_driven) or 360.0 / teeth_driven


def internal_mesh_angle(pinion_teeth: int) -> float:
    """How far a pinion inside a ring turns so a tooth faces the ring's space, in degrees.

    The ring sits at the origin with a tooth space centred on +X, and the pinion
    at +X inside it meshes on its own +X side, where it too was built with a
    space: half a tooth pitch turns a tooth there, whatever its count.
    """
    return 180.0 / pinion_teeth


def _turning_ops(first: GearSpec, second: GearSpec, path_1: str, path_2: str, template: str, path: str,
                 centre: float, spin: float, beta: float, ratio: float, ring: bool, faces: str) -> tuple:
    """A pair that turns: gear 1 free about its axis, and a gear mate turning gear 2 with it.

    Gear 1 is unfixed and held on the assembly's own planes — its front on the
    assembly's front, its axis in the top and right planes — so it can only
    turn. Gear 2's faces are mated to gear 1's as before, but its axis to the
    assembly's planes, since gear 1's turn. Its spin is not mated at all: it is
    placed turned ``spin`` degrees, a tooth in gear 1's space, and the gear mate
    keeps it there as gear 1 turns, at the tooth ratio, the other way round for
    an external pair and the same way round a ring.

    The gear mate, ``UnfixComponent`` and mating to the assembly's own planes
    are probe gear_mate's; without its findings this refuses rather than build
    on a guess.
    """
    if findings.GEAR_MATE_ROUTE is None or findings.GEAR_MATE_EXTERNAL_FLIP is None:
        raise InputError("A gear mate has not been settled on SolidWorks yet: run the gear_mate probe on the "
                         "host (probe.sh --only gear_mate) and record its findings first, or build the pair fixed.")
    teeth_1, teeth_2 = first.teeth_count(), second.teeth_count()
    # The same Flip round a ring as outside one. SolidWorks takes a gear mate's sense
    # from where the gears sit: built through this plan and driven 30°, a 20-tooth
    # pinion in a 60-tooth ring turned the same way as the ring at 3 : 1, clear of
    # it, with Flip False, and against it, clashing, with Flip True (SolidWorks
    # 2026 and 2024, probe/gear_pairs_check.py). Flip was inverted for a ring here
    # once, by reasoning from probe gear_mate's two cylinders alone.
    flip = findings.GEAR_MATE_EXTERNAL_FLIP
    # Gear 2's origin sits level with gear 1's, or, for a herringbone, where its mid-plane meets gear 1's.
    z = (first.face_width_mm() - second.face_width_mm()) / 2.0 if faces != "plane1" else 0.0
    return (
        NewAssembly(template),
        AddGlobal(CENTRE_DISTANCE, equations.literal(round(centre, 9))),
        AddGlobal(RATIO, equations.literal(round(ratio, 9))),
        *((AddGlobal(helical.HELIX_ANGLE, equations.literal(beta)),) if beta else ()),
        AddComponent("gear1", path_1, (0.0, 0.0, 0.0)),
        AddComponent("gear2", path_2, (centre, 0.0, z)),
        # AddComponent5 puts a part's middle at the point given (probe nonparallel_mates),
        # and a gear mate keeps whatever spin gear 2 has when it is made.
        Place("gear1", IDENTITY, (0.0, 0.0, 0.0)),
        Place("gear2", tuple(value for row in crossed.rot_z(spin) for value in row), (centre, 0.0, z)),
        Unfix("gear1"),
        Mate("front", "coincident", "gear1:plane1", "asm:plane1"),
        Mate("axis_top", "coincident", f"gear1:{AXIS_NAME}", "asm:plane2"),
        Mate("axis_right", "coincident", f"gear1:{AXIS_NAME}", "asm:plane3"),
        Mate("faces", "coincident", f"gear2:{faces}", f"gear1:{faces}"),
        Mate("axis", "coincident", f"gear2:{AXIS_NAME}", "asm:plane2"),
        Mate("centre", "distance", f"gear2:{AXIS_NAME}", "asm:plane3", centre, CENTRE_DISTANCE),
        LinkDimension(f"D1@{CENTRE_DISTANCE}", f'"{CENTRE_DISTANCE}"'),
        Mate("gear", "gear", f"gear1:{AXIS_NAME}", f"gear2:{AXIS_NAME}", name=GEAR_MATE,
             ratio=(float(teeth_1), float(teeth_2)), flip=flip),
        *(() if findings.INTERFERENCE_CHECKED else
          (ManualStep("mesh", "Look along the gear axis and check the teeth mesh without clashing."),)),
        Rebuild(),
        SaveAs(path),
    )


def centre_of(g1, g2) -> float:
    """The centre distance two derived external gears' teeth mesh at: the working one when either is shifted.

    ``g1`` and ``g2`` are :class:`spur.SpurDerived` or :class:`helical.HelicalDerived`.
    """
    beta = getattr(g1, "helix_angle_deg", 0.0)
    normal = getattr(g1, "normal_pressure_angle_deg", g1.pressure_angle_deg)
    return describe(g1.module, g1.teeth, g2.teeth, normal, beta,
                    shift_1=getattr(g1, "shift", 0.0), shift_2=getattr(g2, "shift", 0.0))[0]


def mesh_warnings(g1, g2) -> List[str]:
    """What is worth knowing about how two derived external gears mesh, as sentences.

    Only shifted pairs have anything to say: the tip clearance their shifts leave.
    """
    x1, x2 = getattr(g1, "shift", 0.0), getattr(g2, "shift", 0.0)
    if not (x1 or x2):
        return []
    beta = getattr(g1, "helix_angle_deg", 0.0)
    normal = getattr(g1, "normal_pressure_angle_deg", g1.pressure_angle_deg)
    try:
        clearance = tip_clearance(g1.module, g1.teeth, g2.teeth, normal, beta, x1, x2)
    except ValueError as exc:
        return [str(exc)]
    if clearance <= 0.0:
        return [f"With these shifts a tooth tip reaches the other gear's root ({clearance:.3f} mm of clearance), "
                "so the pair cannot be built; make the shifts add up to less."]
    if clearance < CLEARANCE_MIN * g1.module:
        return [f"The tip clearance is {clearance:.3f} mm, under a tenth of a module: the tips run close to "
                "the other gear's root fillets."]
    return []


def _helix_for_pair(gear_a: GearSpec, gear_b: GearSpec, same_hand: bool = False) -> float:
    """The pair's helix angle, 0 for spur, refusing gears that would not mesh on parallel shafts.

    Round a ring (``same_hand``) the two hands are the same; outside, opposite.
    """
    if gear_a.kind != gear_b.kind:
        raise InputError(f"Both gears of a pair must be the same kind (got {gear_a.kind} and {gear_b.kind}).")
    if gear_a.kind not in HELICAL_KINDS:
        return 0.0
    beta_a, beta_b = gear_a.helix_angle_deg(), gear_b.helix_angle_deg()
    if abs(beta_a - beta_b) > 1e-9:
        raise InputError(f"Helical gears on parallel shafts mesh only with the same helix angle "
                         f"(got {beta_a:g}° and {beta_b:g}°).")
    if same_hand and gear_a.hand_value() != gear_b.hand_value():
        raise InputError(f"A helical pinion meshes inside a ring only with the same hand "
                         f"(got {gear_a.hand_value()} and {gear_b.hand_value()}).")
    if not same_hand and gear_a.hand_value() == gear_b.hand_value():
        raise InputError(f"Helical gears on parallel shafts mesh only with opposite hands; both are {gear_a.hand_value()}.")
    return beta_a


PAIR_KIND = "pair"
CENTRE_DISTANCE = "Centre Distance"
RATIO = "Ratio"
MESH_ANGLE = "Mesh Angle"
SHAFT_ANGLE = "Shaft Angle"
HELIX_ANGLE_1 = "Helix Angle 1"
HELIX_ANGLE_2 = "Helix Angle 2"
OFFSET_Y = "Offset Y"
OFFSET_Z = "Offset Z"
CONE_DISTANCE = "Cone Distance"
GEAR_MATE = "Gear Mate"
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
ROUTE_MATES = "mates"
ROUTE_FIXED = "fixed"


def describe_crossed(module: float, teeth_1: int, teeth_2: int, beta_1: float, beta_2: float,
                     pressure_angle: float = 20.0) -> Tuple[float, float, float]:
    """``(centre distance, ratio, normal contact ratio)`` of a crossed pair."""
    return (crossed.centre_distance(module, teeth_1, teeth_2, beta_1, beta_2), teeth_2 / teeth_1,
            crossed.normal_contact_ratio(module, teeth_1, teeth_2, beta_1, beta_2, pressure_angle))


def crossed_assembly_plan(gear_a: GearSpec, gear_b: GearSpec, path_a: str, path_b: str, template: str, path: str,
                          shaft_angle: float, route: Optional[str] = None) -> BuildPlan:
    """Two helical gears on crossed shafts, gear 1 fixed and gear 2 placed by :func:`crossed.placement`.

    ``route`` (default: ``findings.CROSSED_ROUTE``) is how gear 2 is held there.
    ``mates``: gear 2 is first placed, then mated — its axis at the centre
    distance from gear 1's right plane, at the shaft angle to gear 1's axis, its
    origin at two distances from gear 1's top and front planes, and its top plane
    at an angle to gear 1's right plane that fixes its spin — with the centre
    distance and shaft angle driven by globals. ``fixed``: gear 2 is placed and
    fixed there, and no global drives it.
    """
    route = route or getattr(findings, "CROSSED_ROUTE", None)
    if route not in (ROUTE_MATES, ROUTE_FIXED):
        raise InputError("How to hold crossed-axis gears in an assembly has not been settled on SolidWorks yet.")
    for gear in (gear_a, gear_b):
        if gear.kind != helical.KIND_HELICAL or gear.is_internal():
            raise InputError("Only external helical gears go on crossed shafts.")
    module = gear_a.module_mm()
    if abs(gear_b.module_mm() - module) > 1e-9:
        raise InputError(f"Two gears only mesh with the same module (got {gear_a.module.strip()} and "
                         f"{gear_b.module.strip()}).")
    kind = helical.HelicalGear()
    g1, g2 = kind.derive(gear_a), kind.derive(gear_b)
    problems = crossed.validate(g1, g2, shaft_angle)
    if problems:
        raise InputError(problems[0])
    placed = crossed.placement(g1, g2, shaft_angle)
    rotation = tuple(value for row in placed.rotation for value in row)
    # Gear 2's top plane contains its axis; its angle to gear 1's right plane is gear 2's spin.
    spin_angle = crossed.angle_between(crossed.apply(placed.rotation, (0.0, 1.0, 0.0)), (1.0, 0.0, 0.0))
    offset_y, offset_z = abs(placed.origin[1]), abs(placed.origin[2])
    n1, n2 = g1.teeth, g2.teeth

    def literal(value: float) -> str:
        return equations.literal(round(value, 9))

    ops: List = [
        NewAssembly(template),
        AddGlobal(CENTRE_DISTANCE, literal(placed.centre_distance)),
        AddGlobal(SHAFT_ANGLE, literal(shaft_angle)),
        AddGlobal(HELIX_ANGLE_1, literal(g1.helix_angle_deg)),
        AddGlobal(HELIX_ANGLE_2, literal(g2.helix_angle_deg)),
        AddGlobal(RATIO, literal(n2 / n1)),
        AddGlobal(MESH_ANGLE, literal(spin_angle)),
        *((AddGlobal(OFFSET_Y, literal(offset_y)), AddGlobal(OFFSET_Z, literal(offset_z)))
          if route == ROUTE_MATES else ()),
        AddComponent("gear1", path_a, (0.0, 0.0, 0.0)),
        AddComponent("gear2", path_b, placed.origin),
        # AddComponent5 puts a part's middle at the point, not its origin (probe
        # nonparallel_mates): gear 1 is set on the assembly's frame first, so
        # gear 2's frame is where the mates would take it.
        Place("gear1", IDENTITY, (0.0, 0.0, 0.0)),
        Place("gear2", rotation, placed.origin),
        Fix("gear1"),
    ]
    if route == ROUTE_FIXED:
        ops.append(Fix("gear2"))
        notes = ("Gear 2 is placed and fixed: the centre distance and shaft angle globals record the pair "
                 "but do not move it.",)
    else:
        ops.extend([
            Mate("centre", "distance", f"gear2:{AXIS_NAME}", "gear1:plane3", placed.centre_distance, CENTRE_DISTANCE),
            LinkDimension(f"D1@{CENTRE_DISTANCE}", f'"{CENTRE_DISTANCE}"'),
            Mate("shaft", "axis angle", f"gear2:{AXIS_NAME}", f"gear1:{AXIS_NAME}", shaft_angle, SHAFT_ANGLE),
            LinkDimension(f"D1@{SHAFT_ANGLE}", f'"{SHAFT_ANGLE}"'),
        ])
        for identifier, plane, signed, name in (("offset_y", "gear1:plane2", placed.origin[1], OFFSET_Y),
                                                ("offset_z", "gear1:plane1", placed.origin[2], OFFSET_Z)):
            value = abs(signed)
            if value < 1e-6:
                ops.append(Mate(identifier, "point", "gear2:origin", plane))
            else:
                # Signed: a point on the plane's negative side is mated with the distance flipped.
                ops.append(Mate(identifier, "point distance", "gear2:origin", plane, signed, name))
                ops.append(LinkDimension(f"D1@{name}", f'"{name}"'))
        ops.extend([
            Mate("mesh", "angle", "gear2:plane2", "gear1:plane3", spin_angle, MESH_ANGLE),
            LinkDimension(f"D1@{MESH_ANGLE}", f'"{MESH_ANGLE}"'),
        ])
        notes = ()
    ops.extend([Rebuild(), SaveAs(path)])
    return BuildPlan(kind=PAIR_KIND, recipe="", ops=tuple(ops), path=path, notes=notes)


def bevel_assembly_plan(gear_a: GearSpec, gear_b: GearSpec, path_a: str, path_b: str, template: str,
                        path: str) -> BuildPlan:
    """Two bevel gears with their pitch apexes together and their axes at the shaft angle.

    Gear 1 is fixed on the assembly's frame. Gear 2 is set turned ``Σ`` about Y —
    so the pitch cones touch along gear 1's +X side and gear 2's −X side — spun
    about its own axis to put a tooth in gear 1's space, and then mated there:
    origins coincident, its axis in gear 1's top plane, the angle between the two
    axes driven by ``"Shaft Angle"``, and the angle between the top planes by
    ``"Mesh Angle"``.
    """
    for gear in (gear_a, gear_b):
        if gear.kind != KIND_BEVEL:
            raise InputError(f"Both gears of a bevel pair must be bevel gears (got {gear_a.kind} and {gear_b.kind}).")
    module = gear_a.module_mm()
    if abs(gear_b.module_mm() - module) > 1e-9:
        raise InputError(f"Two gears only mesh with the same module (got {gear_a.module.strip()} and "
                         f"{gear_b.module.strip()}).")
    n1, n2 = gear_a.teeth_count(), gear_b.teeth_count()
    if gear_a.mate_teeth_count() != n2 or gear_b.mate_teeth_count() != n1:
        raise InputError(f"Each bevel gear's mate teeth must be the other gear's teeth (got {n1} with mate "
                         f"{gear_a.mate_teeth_count()}, and {n2} with mate {gear_b.mate_teeth_count()}).")
    shaft = gear_a.shaft_angle_deg()
    if abs(gear_b.shaft_angle_deg() - shaft) > 1e-9:
        raise InputError(f"Both bevel gears must be cut for the same shaft angle (got {gear_a.shaft_angle.strip()}° "
                         f"and {gear_b.shaft_angle.strip()}°).")
    radius = bevel.cone_distance(module, n1, n2, shaft)
    angle = mate_angle(n2)
    rotation = crossed.multiply(crossed.rot_y(shaft), crossed.rot_z(angle))
    ops = (
        NewAssembly(template),
        AddGlobal(CONE_DISTANCE, equations.literal(round(radius, 9))),
        AddGlobal(SHAFT_ANGLE, equations.literal(round(shaft, 9))),
        AddGlobal(RATIO, equations.literal(round(n2 / n1, 9))),
        AddGlobal(MESH_ANGLE, equations.literal(round(angle, 9))),
        AddComponent("gear1", path_a, (0.0, 0.0, 0.0)),
        AddComponent("gear2", path_b, (0.0, 0.0, 0.0)),
        Place("gear1", IDENTITY, (0.0, 0.0, 0.0)),
        Place("gear2", tuple(value for row in rotation for value in row), (0.0, 0.0, 0.0)),
        Fix("gear1"),
        Mate("apex", "point", "gear2:origin", "gear1:origin"),
        Mate("axis", "coincident", f"gear2:{AXIS_NAME}", "gear1:plane2"),
        Mate("shaft", "axis angle", f"gear2:{AXIS_NAME}", f"gear1:{AXIS_NAME}", shaft, SHAFT_ANGLE),
        LinkDimension(f"D1@{SHAFT_ANGLE}", f'"{SHAFT_ANGLE}"'),
        Mate("mesh", "angle", "gear2:plane2", "gear1:plane2", angle, MESH_ANGLE),
        LinkDimension(f"D1@{MESH_ANGLE}", f'"{MESH_ANGLE}"'),
        Rebuild(),
        SaveAs(path),
    )
    return BuildPlan(kind=PAIR_KIND, recipe="", ops=ops, path=path)


def assembly_plan(gear_a: GearSpec, gear_b: GearSpec, path_a: str, path_b: str, template: str,
                  path: str, shafts: str = "parallel", shaft_angle: float = 90.0,
                  motion: str = MOTION_FIXED) -> BuildPlan:
    """Both built parts in an assembly, meshing, their distance driven by ``"Centre Distance"``.

    The centre distance is the one the teeth make, m (N1 + N2) / 2, not the one
    typed into the solver: mating at any other would pull the teeth apart or
    into each other. The mates are the ones the assembly probes made on
    SolidWorks 2026 — front planes coincident, gear 2's axis on gear 1's top
    plane, a distance from gear 1's right plane, and an angle between the top
    planes that turns a tooth of gear 2 into gear 1's space.

    ``motion`` ``gear mate`` builds the pair to turn instead: see
    :func:`_turning_ops`. Only gears on parallel shafts are built that way.
    """
    if motion not in (MOTION_FIXED, MOTION_GEAR_MATE):
        raise InputError(f"Assembly must be {MOTION_FIXED} or {MOTION_GEAR_MATE} (got {motion!r}).")
    if motion == MOTION_GEAR_MATE and (gear_a.kind == KIND_BEVEL or gear_b.kind == KIND_BEVEL or shafts == "crossed"):
        raise InputError("A gear mate is built only for gears on parallel shafts so far; build this pair fixed.")
    if gear_a.kind == KIND_BEVEL or gear_b.kind == KIND_BEVEL:
        return bevel_assembly_plan(gear_a, gear_b, path_a, path_b, template, path)
    if shafts == "crossed":
        return crossed_assembly_plan(gear_a, gear_b, path_a, path_b, template, path, shaft_angle)
    module = gear_a.module_mm()
    if abs(gear_b.module_mm() - module) > 1e-9:
        raise InputError(f"Two gears only mesh with the same module (got {gear_a.module.strip()} and "
                         f"{gear_b.module.strip()}).")
    if gear_a.is_internal():
        raise InputError("Gear A is the pinion of a pair, so its teeth must be external; make gear B the ring.")
    ring = gear_b.is_internal()
    n1, n2 = gear_a.teeth_count(), gear_b.teeth_count()
    beta = _helix_for_pair(gear_a, gear_b, same_hand=ring)
    mt = module / math.cos(math.radians(beta))
    shift_1, shift_2 = gear_a.profile_shift_value(), gear_b.profile_shift_value()
    if ring:
        if n2 <= n1:
            raise InputError(f"A ring must have more teeth than the pinion inside it (got {n2} round {n1}).")
        if shift_1 or shift_2:
            raise InputError("A pinion inside a ring is built without profile shift here; set both shifts to 0.")
        # The ring is fixed at the origin and the pinion goes inside it on +X.
        centre = mt * (n2 - n1) / 2.0
        angle = internal_mesh_angle(n1)
        path_a, path_b = path_b, path_a
    else:
        # From the helix angle and shifts the parts hold, so the mate is where their teeth are.
        alpha = gear_a.pressure_angle_deg()
        if abs(gear_b.pressure_angle_deg() - alpha) > 1e-9:
            raise InputError(f"Two gears only mesh with the same pressure angle (got {gear_a.pressure_angle.strip()}° "
                             f"and {gear_b.pressure_angle.strip()}°).")
        try:
            clearance = tip_clearance(module, n1, n2, alpha, beta, shift_1, shift_2)
            centre = working_centre_distance(module, n1, n2, helical.transverse_pressure_angle(alpha, beta)
                                             if beta else alpha, shift_1, shift_2, mt)
        except ValueError as exc:
            raise InputError(str(exc)) from None
        if clearance <= 0.0:
            raise InputError(f"With profile shifts {shift_1:g} and {shift_2:g} a tooth tip reaches the other gear's "
                             f"root ({clearance:.3f} mm of clearance); make the shifts add up to less.")
        # The two parts are symmetric about their X axes whatever the shift, so the
        # tooth that faces gear 1 is the same one it would be unshifted.
        angle = mate_angle(n2)
    name = f'"{CENTRE_DISTANCE}"'
    # A herringbone's apexes must line up whatever the two face widths are, so
    # its mid-planes are mated; a helical pair's sections both sit one (shared)
    # module ahead of their Front planes, so those planes do.
    faces = f"{helical.MID_PLANE}" if gear_a.kind == KIND_HERRINGBONE else "plane1"
    if motion == MOTION_GEAR_MATE:
        first, second = (gear_b, gear_a) if ring else (gear_a, gear_b)
        return BuildPlan(kind=PAIR_KIND, recipe="", path=path, ops=_turning_ops(
            first, second, path_a, path_b, template, path, centre, angle, beta, n2 / n1, ring, faces))
    ops = (
        NewAssembly(template),
        AddGlobal(CENTRE_DISTANCE, equations.literal(round(centre, 9))),
        AddGlobal(RATIO, equations.literal(round(n2 / n1, 9))),
        AddGlobal(MESH_ANGLE, equations.literal(round(angle, 9))),
        *((AddGlobal(helical.HELIX_ANGLE, equations.literal(beta)),) if beta else ()),
        AddComponent("gear1", path_a, (0.0, 0.0, 0.0)),
        AddComponent("gear2", path_b, (centre, 0.0, 0.0)),
        Fix("gear1"),
        Mate("faces", "coincident", f"gear2:{faces}", f"gear1:{faces}"),
        Mate("axis", "coincident", f"gear2:{AXIS_NAME}", "gear1:plane2"),
        Mate("centre", "distance", f"gear2:{AXIS_NAME}", "gear1:plane3", centre, CENTRE_DISTANCE),
        LinkDimension(f"D1@{CENTRE_DISTANCE}", name),
        Mate("mesh", "angle", "gear2:plane2", "gear1:plane2", angle, MESH_ANGLE),
        LinkDimension(f"D1@{MESH_ANGLE}", f'"{MESH_ANGLE}"'),
        # The build checks interference itself once that has been probed, so a person need not look.
        *(() if findings.INTERFERENCE_CHECKED else
          (ManualStep("mesh", "Look along the gear axis and check the teeth mesh without clashing."),)),
        Rebuild(),
        SaveAs(path),
    )
    return BuildPlan(kind=PAIR_KIND, recipe="", ops=ops, path=path)


__all__ = [
    "Candidate", "apply", "assembly_plan", "bevel_assembly_plan", "bevel_candidate", "bevel_forms", "crossed_assembly_plan", "describe", "describe_crossed", "floor_teeth", "internal_mesh_angle", "mate_angle", "mesh_angle",
    "solve",
    "solve_spec", "undercut_minimum", "shift_for_centre",
]
