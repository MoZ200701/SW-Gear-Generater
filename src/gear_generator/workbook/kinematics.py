"""Speeds and torques, for any layout of meshes (docs/PLAN-WORKBOOK.md §3.5; phase W3: frame shafts).

One linear system, not a walk along the train, so a train with an idler, a
compound shaft or a loop is the same problem. Unknowns are each shaft's speed
ω, signed about its own Axis (the workbook's convention), projected onto the
first input's axis n — ω̃ = ω · (a · n) — so a shaft on Z- keeps its sense. A
mesh between gears on shafts p and q, whose axes ride on shaft c (the frame
until W7's carriers, ω̃_c = 0), says

    (ω̃_p − ω̃_c) · z_p = ∓ (ω̃_q − ω̃_c) · z_q        − outside, + a pinion in a ring

Inputs are their typed speed and fixed shafts zero. The system is solved in
exact fractions, since teeth are whole numbers: its rank then says, without a
tolerance, whether every shaft is settled, which ones a second input would
settle (a differential), or that the box is jammed.

Torque (W3) follows the power from the input along the meshes, losing each
mesh's efficiency: ``T_q = T_p · z_q / z_p · η``. Where power splits (one shaft
driving two meshes) the share each takes depends on the loads, so torque past
the split is not given.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

from .model import GearboxSpec
from .schema import FRAME

AXIS_SIGN = {"Z+": 1, "Z-": -1}


@dataclass
class Motion:
    speeds: Dict[str, Fraction] = field(default_factory=dict)     # rpm, about the reference axis n
    torques: Dict[str, float] = field(default_factory=dict)       # N·m, magnitude
    free: List[str] = field(default_factory=list)                 # shafts no input settles
    jammed: str = ""                                              # a sentence, when the meshes contradict
    later: str = ""                                               # a sentence, when this phase cannot say
    reference: str = "Z+"                                         # n: the first input's axis
    axis_sign: Dict[str, int] = field(default_factory=dict)       # each shaft's own axis: +1 Z+, -1 Z-

    @property
    def settled(self) -> bool:
        return not (self.free or self.jammed or self.later)

    def turns(self, shaft: str) -> str:
        """``anticlockwise`` or ``clockwise`` seen from +Z (looking back down it), or ``still``.

        A speed is about the shaft's *own* axis, so a shaft on Z- turning −125 rpm turns anticlockwise seen
        from +Z, the same way as an input on Z+ turning +1500.
        """
        speed = self.speeds.get(shaft)
        if speed is None:
            return ""
        about_plus_z = speed * self.axis_sign.get(shaft, 1)
        return "still" if about_plus_z == 0 else ("anticlockwise" if about_plus_z > 0 else "clockwise")


def _fraction(text: str) -> Fraction:
    return Fraction(str(text).strip().replace("−", "-"))


def solve(spec: GearboxSpec, skip_gears=()) -> Motion:
    """Every shaft's speed and torque, or why they cannot be said."""
    motion = Motion()
    shafts = [s for s in spec.shafts if s.id]
    if any(s.mount() != FRAME for s in shafts):
        motion.later = "Speeds through a carrier (a planetary) are worked out in phase W7."
        return motion
    if any((s.axis or "Z+") not in AXIS_SIGN for s in shafts):
        motion.later = "Speeds through a turned axis (a right-angle stage) are worked out in phase W6."
        return motion
    inputs = [s for s in shafts if s.role == "input" and s.speed]
    if not inputs:
        motion.free = [s.id for s in shafts]
        return motion
    reference = inputs[0].axis or "Z+"
    motion.reference = reference
    n = AXIS_SIGN[reference]
    index = {s.id: i for i, s in enumerate(shafts)}
    sign = {s.id: AXIS_SIGN[s.axis or "Z+"] * n for s in shafts}
    motion.axis_sign = {s.id: AXIS_SIGN[s.axis or "Z+"] for s in shafts}
    gears = {g.id: g for g in spec.gears if g.id not in skip_gears}

    rows: List[List[Fraction]] = []          # each row: coefficients for every shaft, then the right-hand side
    width = len(shafts)

    def row() -> List[Fraction]:
        return [Fraction(0)] * (width + 1)

    for shaft in shafts:
        if shaft.role == "input" and shaft.speed:
            r = row()
            r[index[shaft.id]] = Fraction(1)
            r[width] = _fraction(shaft.speed) * sign[shaft.id]
            rows.append(r)
        elif shaft.role == "fixed":
            r = row()
            r[index[shaft.id]] = Fraction(1)
            rows.append(r)
    meshes = []
    for mesh in spec.meshes:
        a, b = gears.get(mesh.a), gears.get(mesh.b)
        if a is None or b is None or a.shaft not in index or b.shaft not in index or a.shaft == b.shaft:
            continue
        za, zb = int(_fraction(a.teeth)), int(_fraction(b.teeth))
        internal = (a.side == "internal") != (b.side == "internal")
        r = row()
        r[index[a.shaft]] += za
        r[index[b.shaft]] += -zb if internal else zb      # outside: za ωa + zb ωb = 0; in a ring: za ωa − zb ωb = 0
        rows.append(r)
        meshes.append((mesh, a, b, za, zb))

    solution, free, consistent = _reduce(rows, width)
    if not consistent:
        motion.jammed = ("The meshes and the fixed or input shafts contradict each other: as written the box "
                         "cannot turn at all (it is jammed).")
        return motion
    for shaft in shafts:
        value = solution.get(index[shaft.id])
        if value is None:
            motion.free.append(shaft.id)
        else:
            motion.speeds[shaft.id] = value * sign[shaft.id]   # back to each shaft's own axis
    _torques(spec, motion, inputs, meshes)
    return motion


def _reduce(rows: List[List[Fraction]], width: int) -> Tuple[Dict[int, Fraction], List[int], bool]:
    """Gauss-Jordan in fractions: (settled unknowns, free columns, whether the rows agree)."""
    matrix = [r[:] for r in rows]
    pivots: List[int] = []
    r = 0
    for col in range(width):
        pick = next((i for i in range(r, len(matrix)) if matrix[i][col] != 0), None)
        if pick is None:
            continue
        matrix[r], matrix[pick] = matrix[pick], matrix[r]
        lead = matrix[r][col]
        matrix[r] = [v / lead for v in matrix[r]]
        for i in range(len(matrix)):
            if i != r and matrix[i][col] != 0:
                factor = matrix[i][col]
                matrix[i] = [a - factor * b for a, b in zip(matrix[i], matrix[r])]
        pivots.append(col)
        r += 1
    consistent = all(any(v != 0 for v in m[:width]) or m[width] == 0 for m in matrix)
    free = [c for c in range(width) if c not in pivots]
    settled: Dict[int, Fraction] = {}
    for i, col in enumerate(pivots):
        if all(matrix[i][f] == 0 for f in free):
            settled[col] = matrix[i][width]
    return settled, free, consistent


def _torques(spec: GearboxSpec, motion: Motion, inputs, meshes) -> None:
    """Torque along the power path from the first input, through each mesh's efficiency; none past a split."""
    first = inputs[0]
    if not first.torque:
        return
    efficiency = {}
    box_eta = float(spec.box.efficiency_text())
    for mesh, a, b, za, zb in meshes:
        eta = float(mesh.efficiency) if mesh.efficiency else box_eta
        efficiency[(a.id, b.id)] = efficiency[(b.id, a.id)] = eta / 100.0
    by_shaft: Dict[str, List] = {}
    for mesh, a, b, za, zb in meshes:
        by_shaft.setdefault(a.shaft, []).append((a, b, za, zb))
        by_shaft.setdefault(b.shaft, []).append((b, a, zb, za))
    torque = {first.id: abs(float(_fraction(first.torque)))}
    queue = deque([first.id])
    came_from: Dict[str, str] = {first.id: ""}
    while queue:
        shaft = queue.popleft()
        onward = [(g, h, zg, zh) for g, h, zg, zh in by_shaft.get(shaft, []) if h.shaft != came_from[shaft]]
        if len(onward) > 1:
            continue                        # power splits here: each branch's share depends on its load
        for g, h, zg, zh in onward:
            if h.shaft in torque:
                continue
            torque[h.shaft] = torque[shaft] * zh / zg * efficiency[(g.id, h.id)]
            came_from[h.shaft] = shaft
            queue.append(h.shaft)
    motion.torques = torque
