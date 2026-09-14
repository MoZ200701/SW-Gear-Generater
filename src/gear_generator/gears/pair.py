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
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import List, Optional, Tuple

from ..spec import GearSpec, InputError, PairSpec
from . import equations, standards
from .base import AddComponent, AddGlobal, BuildPlan, Fix, LinkDimension, ManualStep, Mate, NewAssembly, Rebuild, SaveAs
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

    @property
    def exact(self) -> bool:
        return abs(self.centre_error) <= TOLERANCE and self.ratio_error <= TOLERANCE

    def rank(self) -> Tuple[bool, bool, bool, float, float, int]:
        return (
            abs(self.centre_error) > TOLERANCE,
            not self.standard,
            self.undercut,
            round(self.ratio_error, 12),
            -self.module,
            self.teeth_driver,
        )


def floor_teeth(min_teeth: int) -> int:
    return max(ABSOLUTE_FLOOR, int(math.ceil(FLOOR_SHARE * min_teeth - TOLERANCE)))


def describe(module: float, teeth_driver: int, teeth_driven: int,
             pressure_angle: float = 20.0) -> Tuple[float, float, float]:
    """The other direction: ``(centre distance, ratio, contact ratio)`` of a pair."""
    centre = module * (teeth_driver + teeth_driven) / 2.0
    return centre, teeth_driven / teeth_driver, contact_ratio(module, teeth_driver, teeth_driven, pressure_angle, centre)


def _candidate(module: float, n1: int, n2: int, centre: float, ratio: float, pressure_angle: float,
               min_teeth: int, standard: bool) -> Candidate:
    actual_centre, actual_ratio, epsilon = describe(module, n1, n2, pressure_angle)
    return Candidate(
        module=module,
        teeth_driver=n1,
        teeth_driven=n2,
        standard=standard,
        ratio=actual_ratio,
        centre_distance=actual_centre,
        ratio_error=abs(actual_ratio - ratio) / ratio,
        centre_error=actual_centre - centre,
        undercut=min(n1, n2) < min_teeth,
        contact_ratio=epsilon,
    )


def solve(centre: float, ratio: float, pressure_angle: float = 20.0, module: Optional[float] = None,
          series: str = standards.SERIES_1, min_teeth: int = 17, max_teeth: int = 200,
          limit: int = DEFAULT_LIMIT) -> List[Candidate]:
    """Every candidate worth listing, best first."""
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


def solve_spec(pair: PairSpec) -> List[Candidate]:
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
    """Write module and teeth into both gears, and touch nothing else."""
    module = equations.literal(round(candidate.module, 6))
    return (
        gear_a.with_values(module=module, teeth=str(candidate.teeth_driver)),
        gear_b.with_values(module=module, teeth=str(candidate.teeth_driven)),
    )


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


PAIR_KIND = "pair"
CENTRE_DISTANCE = "Centre Distance"
RATIO = "Ratio"
MESH_ANGLE = "Mesh Angle"


def assembly_plan(gear_a: GearSpec, gear_b: GearSpec, path_a: str, path_b: str, template: str,
                  path: str) -> BuildPlan:
    """Both built parts in an assembly, meshing, their distance driven by ``"Centre Distance"``.

    The centre distance is the one the teeth make, m (N1 + N2) / 2, not the one
    typed into the solver: mating at any other would pull the teeth apart or
    into each other. The mates are the ones the assembly probes made on
    SolidWorks 2026 — front planes coincident, gear 2's axis on gear 1's top
    plane, a distance from gear 1's right plane, and an angle between the top
    planes that turns a tooth of gear 2 into gear 1's space.
    """
    module = gear_a.module_mm()
    if abs(gear_b.module_mm() - module) > 1e-9:
        raise InputError(f"Two gears only mesh with the same module (got {gear_a.module.strip()} and "
                         f"{gear_b.module.strip()}).")
    n1, n2 = gear_a.teeth_count(), gear_b.teeth_count()
    centre = module * (n1 + n2) / 2.0
    angle = mate_angle(n2)
    name = f'"{CENTRE_DISTANCE}"'
    ops = (
        NewAssembly(template),
        AddGlobal(CENTRE_DISTANCE, equations.literal(round(centre, 9))),
        AddGlobal(RATIO, equations.literal(round(n2 / n1, 9))),
        AddGlobal(MESH_ANGLE, equations.literal(round(angle, 9))),
        AddComponent("gear1", path_a, (0.0, 0.0, 0.0)),
        AddComponent("gear2", path_b, (centre, 0.0, 0.0)),
        Fix("gear1"),
        Mate("faces", "coincident", "gear2:plane1", "gear1:plane1"),
        Mate("axis", "coincident", f"gear2:{AXIS_NAME}", "gear1:plane2"),
        Mate("centre", "distance", f"gear2:{AXIS_NAME}", "gear1:plane3", centre, CENTRE_DISTANCE),
        LinkDimension(f"D1@{CENTRE_DISTANCE}", name),
        Mate("mesh", "angle", "gear2:plane2", "gear1:plane2", angle, MESH_ANGLE),
        LinkDimension(f"D1@{MESH_ANGLE}", f'"{MESH_ANGLE}"'),
        ManualStep("mesh", "Look along the gear axis and check the teeth mesh without clashing."),
        Rebuild(),
        SaveAs(path),
    )
    return BuildPlan(kind=PAIR_KIND, recipe="", ops=ops, path=path)


__all__ = [
    "Candidate", "apply", "assembly_plan", "describe", "floor_teeth", "mate_angle", "mesh_angle", "solve",
    "solve_spec", "undercut_minimum",
]
