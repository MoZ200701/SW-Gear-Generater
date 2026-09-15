"""Solving a gear pair: from a centre distance and a ratio to module and teeth.

Deterministic, and exhaustive over what it looks at. For each allowed module
the tooth sum ``S = 2C / m`` is tried at both whole numbers either side of it,
and the driver count at the nearest split of that sum and one either side. Then,
for exact-ratio tooth pairs no standard module lands on, the module that *would*
land on the centre distance exactly is offered as a non-standard row.

Rows are ranked by what matters most first: hitting the centre distance, being
a module you can buy a cutter for, not being undercut, the ratio error, and
then the larger module, which is the stronger tooth.

Profile shift, which would close a small centre-distance gap, is reserved for a
later version; a gap is reported rather than hidden.

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
from . import crossed, equations, helical, internal, standards
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
)
from .spur import AXIS_NAME, contact_ratio, undercut_minimum

# Rows below this share of Min teeth are not offered at all: the undercut takes
# so much of the flank that listing them only buries the useful ones.
FLOOR_SHARE = 0.7
ABSOLUTE_FLOOR = 6
TOLERANCE = 1e-9
DEFAULT_LIMIT = 120


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
    shaft_angle: float = 0.0    # a crossed pair's shaft angle, degrees; 0 for parallel shafts

    @property
    def crossed(self) -> bool:
        return self.shaft_angle > 0.0

    @property
    def exact(self) -> bool:
        return abs(self.centre_error) <= TOLERANCE and self.ratio_error <= TOLERANCE

    @property
    def clashes(self) -> bool:
        return self.clash > internal.CLASH_TOLERANCE

    def rank(self) -> Tuple[bool, bool, bool, bool, float, float, float, int]:
        # Parallel: the smaller helix, the less axial thrust. Crossed: the nearer
        # the two helix angles are to each other, the less the sliding.
        helix = abs(self.helix_angle - self.shaft_angle / 2.0) if self.crossed else self.helix_angle
        return (
            abs(self.centre_error) > TOLERANCE,
            not self.standard,
            self.undercut,
            self.clashes,
            round(self.ratio_error, 12),
            # Among a crossed pair's near misses, the nearer the better; parallel rows keep their order.
            round(abs(self.centre_error), 9) if self.crossed else 0.0,
            -self.module,
            round(helix, 9),
            self.teeth_driver,
        )


def floor_teeth(min_teeth: int) -> int:
    return max(ABSOLUTE_FLOOR, int(math.ceil(FLOOR_SHARE * min_teeth - TOLERANCE)))


def describe(module: float, teeth_driver: int, teeth_driven: int,
             pressure_angle: float = 20.0, helix_angle: float = 0.0,
             mesh: str = MESH_EXTERNAL) -> Tuple[float, float, float]:
    """The other direction: ``(centre distance, ratio, contact ratio)`` of a pair.

    For a helical pair ``module`` and ``pressure_angle`` are the normal ones,
    the centre distance is ``mt (N1 + N2) / 2`` and the contact ratio is the
    transverse one, εα; the overlap εβ depends on the face width and is
    :func:`helical.overlap_ratio`. An internal pair's driven gear is the ring,
    and its centre distance is ``mt (N2 − N1) / 2``.
    """
    mt = module / math.cos(math.radians(helix_angle))
    alpha = helical.transverse_pressure_angle(pressure_angle, helix_angle) if helix_angle else pressure_angle
    if mesh == MESH_INTERNAL:
        centre = mt * (teeth_driven - teeth_driver) / 2.0
        epsilon = internal.contact_ratio(module, teeth_driver, teeth_driven, alpha, centre, transverse_module=mt)
    else:
        centre = mt * (teeth_driver + teeth_driven) / 2.0
        epsilon = contact_ratio(module, teeth_driver, teeth_driven, alpha, centre, transverse_module=mt)
    return centre, teeth_driven / teeth_driver, epsilon


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
          shaft_angle: float = 90.0) -> List[Candidate]:
    """Every candidate worth listing, best first.

    For the helical kinds ``module`` and ``pressure_angle`` are normal, and
    the pair's centre distance is ``mn (N1 + N2) / (2 cos β)``. A typed
    ``helix_angle`` is held, and the search is spur's with ``2C cos β`` in
    place of ``2C``. Left ``None``, every whole tooth sum whose helix angle
    lands inside ``helix_range`` is tried, and each such row meets the centre
    distance exactly: the helix angle is what takes up the difference.

    ``mesh`` internal makes the driven gear a ring round the driver: the ratio
    must then be more than one.
    """
    if mesh == MESH_INTERNAL:
        return _solve_internal(centre, ratio, pressure_angle, module, series, min_teeth, max_teeth, limit,
                               kind, helix_angle, helix_range, face_width)
    if shafts == "crossed":
        return _solve_crossed(centre, ratio, shaft_angle, pressure_angle, module, series, min_teeth, max_teeth, limit,
                              helix_angle)
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
                   helix_angle: Optional[float]) -> List[Candidate]:
    """Two helical gears on shafts ``shaft`` degrees apart, same hand, ``β1 + β2 = Σ``.

    With ``helix_angle`` (β1) typed, the tooth counts are the ones whose centre
    distance comes nearest, as a parallel pair's are. Left blank, every tooth
    pair that fits gets the β1 that meets the centre distance exactly, the one
    nearest half the shaft angle.
    """
    if centre <= 0:
        raise InputError("Centre distance must be more than zero.")
    if ratio <= 0:
        raise InputError("Ratio must be more than zero.")
    if not crossed.SHAFT_MIN <= shaft <= crossed.SHAFT_MAX:
        raise InputError(f"The shaft angle must be between {crossed.SHAFT_MIN:g}° and {crossed.SHAFT_MAX:g}° "
                         f"(got {shaft:g}°).")
    if helix_angle is not None and not (0.0 < helix_angle < 90.0 and 0.0 < shaft - helix_angle < 90.0):
        raise InputError(f"A helix angle of {helix_angle:g}° leaves the other gear {shaft - helix_angle:g}° on "
                         f"{shaft:g}° shafts; both must be between 0° and 90°.")
    floor = floor_teeth(min_teeth)
    if max_teeth < floor:
        raise InputError(f"Max teeth ({max_teeth}) is below the smallest gear the solver offers ({floor}).")
    allowed = (float(module),) if module is not None else standards.modules(series)
    found = {}

    def offer(m: float, n1: int, n2: int, standard: bool, beta_1: float) -> None:
        if not (floor <= n1 <= max_teeth and floor <= n2 <= max_teeth):
            return
        key = (round(m, 9), n1, n2, round(beta_1, 9))
        if key in found:
            return
        beta_2 = shaft - beta_1
        actual = crossed.centre_distance(m, n1, n2, beta_1, beta_2)
        limit_1 = helical.undercut_minimum(pressure_angle, beta_1)
        limit_2 = helical.undercut_minimum(pressure_angle, beta_2)
        found[key] = Candidate(
            module=m, teeth_driver=n1, teeth_driven=n2, standard=standard, ratio=n2 / n1,
            centre_distance=actual, ratio_error=abs(n2 / n1 - ratio) / ratio, centre_error=actual - centre,
            undercut=n1 < int(math.floor(limit_1 + 0.5)) or n2 < int(math.floor(limit_2 + 0.5)),
            contact_ratio=crossed.normal_contact_ratio(m, n1, n2, beta_1, beta_2, pressure_angle),
            helix_angle=beta_1, helix_angle_b=beta_2, shaft_angle=shaft,
        )

    for m in allowed:
        standard = module is None or standards.is_standard(m)
        if helix_angle is not None:
            c1 = 1.0 / math.cos(math.radians(helix_angle))
            c2 = 1.0 / math.cos(math.radians(shaft - helix_angle))
            middle = 2.0 * centre / (m * (c1 + ratio * c2))
            for n1 in range(int(math.floor(middle)) - 1, int(math.ceil(middle)) + 2):
                if n1 >= 1:
                    offer(m, n1, int(math.floor(ratio * n1 + 0.5)), standard, helix_angle)
            continue
        target = 2.0 * centre / m
        for n1 in range(floor, max_teeth + 1):
            n2 = int(math.floor(ratio * n1 + 0.5))
            if n1 + n2 > target + TOLERANCE:
                break
            beta_1 = crossed.beta_1_for(m, n1, n2, shaft, centre)
            if beta_1 is not None:
                offer(m, n1, n2, standard, beta_1)
    if helix_angle is not None and module is None:
        exact = Fraction(ratio).limit_denominator(max_teeth)
        p, q = exact.numerator, exact.denominator
        c1 = 1.0 / math.cos(math.radians(helix_angle))
        c2 = 1.0 / math.cos(math.radians(shaft - helix_angle))
        k = 1
        while k * max(p, q) <= max_teeth:
            n1, n2 = k * q, k * p
            m_star = 2.0 * centre / (n1 * c1 + n2 * c2)
            if not any(abs(m_star - m) <= TOLERANCE for m in allowed):
                offer(m_star, n1, n2, False, helix_angle)
            k += 1

    ranked = sorted(found.values(), key=Candidate.rank)
    return ranked[:limit]


def solve_spec(pair: PairSpec) -> List[Candidate]:
    kind = pair.gear_a.kind
    mesh = pair.mesh_value()
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


def apply(candidate: Candidate, gear_a: GearSpec, gear_b: GearSpec) -> Tuple[GearSpec, GearSpec]:
    """Write module and teeth into both gears — and for a helical pair the helix angle, and
    gear B the other hand from gear A (the same hand, round a ring) — and touch nothing else."""
    module = equations.literal(round(candidate.module, 6))
    a = gear_a.with_values(module=module, teeth=str(candidate.teeth_driver))
    b = gear_b.with_values(module=module, teeth=str(candidate.teeth_driven))
    if candidate.crossed:
        a = a.with_values(helix_angle=equations.literal(round(candidate.helix_angle, 6)))
        b = b.with_values(helix_angle=equations.literal(round(candidate.helix_angle_b, 6)), hand=gear_a.hand)
        return a, b
    if candidate.helix_angle:
        beta = equations.literal(round(candidate.helix_angle, 6))
        same = str(gear_a.hand).strip().lower()
        other = same if candidate.mesh == MESH_INTERNAL else (HAND_LEFT if same == HAND_RIGHT else HAND_RIGHT)
        a = a.with_values(helix_angle=beta)
        b = b.with_values(helix_angle=beta, hand=other)
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
        for identifier, plane, value, name in (("offset_y", "gear1:plane2", offset_y, OFFSET_Y),
                                               ("offset_z", "gear1:plane1", offset_z, OFFSET_Z)):
            if value < 1e-6:
                ops.append(Mate(identifier, "point", "gear2:origin", plane))
            else:
                ops.append(Mate(identifier, "point distance", "gear2:origin", plane, value, name))
                ops.append(LinkDimension(f"D1@{name}", f'"{name}"'))
        ops.extend([
            Mate("mesh", "angle", "gear2:plane2", "gear1:plane3", spin_angle, MESH_ANGLE),
            LinkDimension(f"D1@{MESH_ANGLE}", f'"{MESH_ANGLE}"'),
        ])
        notes = ()
    ops.extend([Rebuild(), SaveAs(path)])
    return BuildPlan(kind=PAIR_KIND, recipe="", ops=tuple(ops), path=path, notes=notes)


def assembly_plan(gear_a: GearSpec, gear_b: GearSpec, path_a: str, path_b: str, template: str,
                  path: str, shafts: str = "parallel", shaft_angle: float = 90.0) -> BuildPlan:
    """Both built parts in an assembly, meshing, their distance driven by ``"Centre Distance"``.

    The centre distance is the one the teeth make, m (N1 + N2) / 2, not the one
    typed into the solver: mating at any other would pull the teeth apart or
    into each other. The mates are the ones the assembly probes made on
    SolidWorks 2026 — front planes coincident, gear 2's axis on gear 1's top
    plane, a distance from gear 1's right plane, and an angle between the top
    planes that turns a tooth of gear 2 into gear 1's space.
    """
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
    if ring:
        if n2 <= n1:
            raise InputError(f"A ring must have more teeth than the pinion inside it (got {n2} round {n1}).")
        # The ring is fixed at the origin and the pinion goes inside it on +X.
        centre = mt * (n2 - n1) / 2.0
        angle = internal_mesh_angle(n1)
        path_a, path_b = path_b, path_a
    else:
        # From the helix angle the parts hold, so the mate is where their teeth are.
        centre = mt * (n1 + n2) / 2.0
        angle = mate_angle(n2)
    name = f'"{CENTRE_DISTANCE}"'
    # A herringbone's apexes must line up whatever the two face widths are, so
    # its mid-planes are mated; a helical pair's sections both sit one (shared)
    # module ahead of their Front planes, so those planes do.
    faces = f"{helical.MID_PLANE}" if gear_a.kind == KIND_HERRINGBONE else "plane1"
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
    "Candidate", "apply", "assembly_plan", "crossed_assembly_plan", "describe", "describe_crossed", "floor_teeth", "internal_mesh_angle", "mate_angle", "mesh_angle",
    "solve",
    "solve_spec", "undercut_minimum",
]
