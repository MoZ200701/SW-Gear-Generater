"""The gearbox-level checks (docs/PLAN-WORKBOOK.md §3.4; phase W3: shafts on the frame along Z+ or Z-).

Each gear's own checks are the strip's (:mod:`workbook.build`); these are the
ones only a whole gearbox has: meshing gears that agree with each other and
sit exactly where their teeth put them, faces that meet, gears that do not
clash, tips that miss other shafts, and speeds every shaft can be given.
Every message names the cell to look at, and a centre distance that is off
comes with the fixes of :mod:`workbook.fixes`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List, Optional, Tuple

from ..gears import pair as pairs
from ..gears.base import ERROR, WARNING, Diagnostic
from . import fixes as fixes_mod, geometry, kinematics
from .fixes import Fix
from .geometry import Layout, Placed
from .model import GearboxSpec

CENTRE_TOLERANCE = 0.005      # mm: half the last digit of a distance typed to two decimals
NEAR_MESH = 0.5               # × module: two unlisted gears this close to their mesh distance would mesh
CLASH_GAP = 0.5               # × module: the least room between gears that do not mesh


@dataclass
class Report:
    diagnostics: List[Diagnostic] = field(default_factory=list)
    fixes: Dict[str, List[Fix]] = field(default_factory=dict)   # by the diagnostic's field (its cell)
    layout: Layout = field(default_factory=Layout)
    theta: Dict[str, float] = field(default_factory=dict)       # each placed gear's turn, radians
    motion: kinematics.Motion = field(default_factory=kinematics.Motion)
    centres: Dict[Tuple[str, str], Tuple[float, float]] = field(default_factory=dict)   # mesh -> (needed, placed)
    contact: Dict[Tuple[str, str], float] = field(default_factory=dict)                # mesh -> εα at the needed centre
    worked_out_as: str = ""


def _error(report: Report, where: str, message: str) -> None:
    report.diagnostics.append(Diagnostic(ERROR, f"{where}: {message}", where))


def _warning(report: Report, where: str, message: str) -> None:
    report.diagnostics.append(Diagnostic(WARNING, f"{where}: {message}", where))


def _n(value: float, places: int = 3) -> str:
    return f"{value:.{places}f}".rstrip("0").rstrip(".")


def check(spec: GearboxSpec, skip_gears=()) -> Report:
    """Every gearbox-level check for what this phase lays out. ``skip_gears``: gears with errors of their own."""
    report = Report()
    report.layout = lay = geometry.layout(spec, skip_gears)
    for sentence in lay.later:
        _warning(report, "Shafts", f"not checked yet: {sentence}")
    report.motion = kinematics.solve(spec, skip_gears)
    if lay.later:
        report.worked_out_as = "Not laid out yet: " + lay.later[0].split(":")[0]
        return report
    gears = {g.id: g for g in spec.gears}
    placed = lay.placed
    for gear_id, why in lay.problems.items():
        _error(report, spec.cell("Gears", gears[gear_id].row, "id"), f"{gear_id} could not be placed: {why}")

    listed = set()
    for mesh in spec.meshes:
        a, b = placed.get(mesh.a), placed.get(mesh.b)
        listed.add(frozenset((mesh.a, mesh.b)))
        if a is None or b is None:
            continue
        where = spec.cell("Meshes", mesh.row, "a")
        _check_mesh(report, spec, mesh, a, b, where)

    _check_clearances(report, spec, placed, listed)
    _check_shafts(report, spec, placed)
    _check_motion(report, spec)
    report.theta = geometry.phases(spec, placed)
    report.worked_out_as = _worked_out_as(spec, report)
    return report


def _check_mesh(report: Report, spec: GearboxSpec, mesh, a: Placed, b: Placed, where: str) -> None:
    gears = {g.id: g for g in spec.gears}
    ga, gb = gears[a.gear], gears[b.gear]
    if a.shaft == b.shaft:
        _error(report, where, f"{a.gear} and {b.gear} are on the same shaft, {a.shaft}; gears that mesh turn on "
                              "different shafts.")
        return
    kind_a, kind_b = ga.kind_word(), gb.kind_word()
    if kind_a != kind_b:
        _error(report, where, f"{a.gear} is {kind_a} and {b.gear} is {kind_b}; meshing gears are the same kind.")
        return
    if abs(a.module - b.module) > 1e-9:
        _error(report, where, f"{a.gear} has module {_n(a.module)} and {b.gear} {_n(b.module)}; meshing gears "
                              "share one module.")
        return
    pa_a = float(ga.pressure_angle or spec.box.pressure_angle_text())
    pa_b = float(gb.pressure_angle or spec.box.pressure_angle_text())
    if abs(pa_a - pa_b) > 1e-9:
        _error(report, where, f"{a.gear}'s pressure angle is {_n(pa_a)}° and {b.gear}'s {_n(pa_b)}°; meshing "
                              "gears share one.")
        return
    if a.internal and b.internal:
        _error(report, where, f"{a.gear} and {b.gear} are both rings; a ring meshes with a gear inside it.")
        return
    beta = 0.0
    if kind_a in ("helical", "herringbone"):
        beta = float(ga.helix_angle)
        if abs(beta - float(gb.helix_angle)) > 1e-9:
            _error(report, where, f"{a.gear}'s helix angle is {_n(beta)}° and {b.gear}'s {_n(float(gb.helix_angle))}°;"
                                  " gears on parallel shafts mesh at one helix angle.")
            return
        ring = a.internal or b.internal
        same = (ga.hand or "right") == (gb.hand or "right")
        if ring and not same:
            _error(report, where, f"{a.gear} and {b.gear} have opposite hands; a pinion in a ring takes the same "
                                  "hand as the ring.")
            return
        if not ring and same:
            _error(report, where, f"{a.gear} and {b.gear} are both {ga.hand or 'right'}-handed; gears on parallel "
                                  "shafts take opposite hands.")
            return

    pinion, other = (a, b) if not a.internal else (b, a)
    try:
        if a.internal or b.internal:
            if other.teeth <= pinion.teeth:
                _error(report, where, f"the ring {other.gear} has {other.teeth} teeth and {pinion.gear} "
                                      f"{pinion.teeth}; a ring needs more teeth than the gear inside it.")
                return
            needed, _, epsilon = pairs.describe(a.module, pinion.teeth, other.teeth, pa_a, beta, mesh="internal")
        else:
            needed, _, epsilon = pairs.describe(a.module, a.teeth, b.teeth, pa_a, beta,
                                                shift_1=getattr(a.derived, "shift", 0.0),
                                                shift_2=getattr(b.derived, "shift", 0.0))
    except ValueError as exc:
        _error(report, where, f"{a.gear} and {b.gear}: {exc}")
        return
    placed_at = geometry.centre_distance(a, b)
    report.centres[(a.gear, b.gear)] = (needed, placed_at)
    report.contact[(a.gear, b.gear)] = epsilon
    off = placed_at - needed
    if abs(off) > CENTRE_TOLERANCE:
        shafts = {s.id: s for s in spec.shafts}
        report.diagnostics.append(Diagnostic(
            ERROR, f"{where}: {a.gear} and {b.gear} are {_n(placed_at)} apart; their teeth make {_n(needed)} "
                   f"({'+' if off > 0 else '−'}{_n(abs(off))} mm). Check the X and Y of {a.shaft} and {b.shaft} "
                   f"(Shafts rows {shafts[a.shaft].row} and {shafts[b.shaft].row}); a shaft at an angle is "
                   "best placed by formula.", where))
        offered = []
        move = fixes_mod.move_fix(spec, a, b, needed)
        if move is not None:
            offered.append(move)
        shift = fixes_mod.shift_fix(spec, a, b, {g.id: g.row for g in spec.gears}[a.gear],
                                    {g.id: g.row for g in spec.gears}[b.gear])
        if shift is not None:
            offered.append(shift)
        if offered:
            report.fixes[where] = offered
    overlap = geometry.faces_overlap(a, b)
    if overlap <= 0:
        _error(report, where, f"{a.gear} and {b.gear} do not meet along the axis: their faces are {_n(-overlap)} mm "
                              "apart. Check their At.")
    elif a.herringbone and abs(a.z - b.z) > CENTRE_TOLERANCE:
        _error(report, where, f"{a.gear} and {b.gear} are herringbones whose middles are {_n(abs(a.z - b.z))} mm "
                              "apart along the axis; a herringbone pair meshes middle to middle.")


def _check_clearances(report: Report, spec: GearboxSpec, placed: Dict[str, Placed], listed) -> None:
    """Gears on different shafts that do not mesh, and share some height: they must not touch."""
    gears = {g.id: g for g in spec.gears}
    for a, b in combinations(placed.values(), 2):
        if a.shaft == b.shaft or frozenset((a.gear, b.gear)) in listed:
            continue
        if geometry.faces_overlap(a, b) <= 0:
            continue
        d = geometry.centre_distance(a, b)
        gap = CLASH_GAP * max(a.module, b.module)
        where = spec.cell("Gears", gears[b.gear].row, "shaft")
        if a.internal and b.internal:
            continue
        if a.internal or b.internal:
            ring, g = (a, b) if a.internal else (b, a)
            if d - g.outer_radius >= ring.outer_radius:
                continue                                    # wholly outside the ring
            near = abs(d - (ring.derived.d - g.derived.d) / 2.0) < NEAR_MESH * g.module
            if near and abs(ring.module - g.module) < 1e-9:
                _warning(report, where, f"{g.gear} sits where it would mesh inside {ring.gear}: list them on "
                                        "Meshes, or move one.")
            elif d + g.outer_radius > ring.tip_radius - gap:
                _error(report, where, f"{g.gear} reaches {ring.gear}'s teeth: there is less than {_n(gap)} mm "
                                      f"between them.")
            continue
        near = abs(d - (a.derived.d + b.derived.d) / 2.0) < NEAR_MESH * max(a.module, b.module)
        if near and abs(a.module - b.module) < 1e-9:
            _warning(report, where, f"{a.gear} and {b.gear} sit where they would mesh: list them on Meshes, or "
                                    "move one.")
        elif d < a.outer_radius + b.outer_radius + gap:
            _error(report, where, f"{a.gear} and {b.gear} clash: {_n(d)} mm apart, with tips reaching "
                                  f"{_n(a.outer_radius + b.outer_radius)} mm and less than {_n(gap)} mm to spare.")


def _check_shafts(report: Report, spec: GearboxSpec, placed: Dict[str, Placed]) -> None:
    gears_on: Dict[str, List[Placed]] = {}
    for p in placed.values():
        gears_on.setdefault(p.shaft, []).append(p)
    for shaft in spec.shafts:
        if shaft.id and not any(g.shaft == shaft.id for g in spec.gears):
            _warning(report, spec.cell("Shafts", shaft.row, "id"), f"{shaft.id} carries no gear.")
    # A gear whose metal passes over another shaft's line, within the height that shaft's gears span.
    for g in placed.values():
        for shaft_id, on in gears_on.items():
            if shaft_id == g.shaft:
                continue
            lo = min(p.z_range[0] for p in on)
            hi = max(p.z_range[1] for p in on)
            if min(g.z_range[1], hi) - max(g.z_range[0], lo) <= 0:
                continue
            other = on[0]
            d = ((other.x - g.x) ** 2 + (other.y - g.y) ** 2) ** 0.5
            inside_metal = (g.tip_radius <= d <= g.outer_radius) if g.internal else d < g.outer_radius
            if inside_metal:
                row = {x.id: x.row for x in spec.gears}[g.gear]
                _warning(report, spec.cell("Gears", row, "id"),
                         f"{g.gear} passes over {shaft_id}'s axis, {_n(d)} mm from its own: a real shaft there "
                         "would be cut.")


def _check_motion(report: Report, spec: GearboxSpec) -> None:
    motion = report.motion
    if motion.later:
        _warning(report, "Shafts", f"not worked out yet: {motion.later}")
        return
    if motion.jammed:
        _error(report, "Meshes", motion.jammed)
        return
    for shaft in spec.shafts:
        if shaft.id in motion.free and shaft.role == "output":
            _warning(report, spec.cell("Shafts", shaft.row, "id"),
                     f"nothing drives {shaft.id}: no input reaches it through the meshes.")


def _worked_out_as(spec: GearboxSpec, report: Report) -> str:
    """``Parallel train · 2 meshes · 12.000 : 1`` — what the rows add up to."""
    meshes = len(report.centres)
    pieces = ["Parallel train", f"{meshes} mesh{'es' if meshes != 1 else ''}"]
    if any(p.internal for p in report.layout.placed.values()):
        pieces[0] = "Parallel train with a ring"
    motion = report.motion
    inputs = [s for s in spec.shafts if s.role == "input" and s.id in motion.speeds]
    outputs = [s for s in spec.shafts if s.role == "output" and s.id in motion.speeds]
    if inputs and outputs and motion.speeds[outputs[0].id] != 0:
        ratio = float(motion.speeds[inputs[0].id] / motion.speeds[outputs[0].id])
        pieces.append(f"{abs(ratio):.3f} : 1")
        same = motion.turns(inputs[0].id) == motion.turns(outputs[0].id)   # as seen from +Z, whatever each axis
        pieces.append("output turns the same way" if same else "output turns the other way")
    return " · ".join(pieces)
