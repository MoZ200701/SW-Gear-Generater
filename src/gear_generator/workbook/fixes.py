"""What the import offers when two meshing gears are not where their teeth put them (PLAN-WORKBOOK §3.6).

A fix is a list of edits to the workbook's own cells — sheet, row, column key,
new text — so the window can apply it to the model in memory and check it
again, and Export (W3) can write exactly those cells and nothing else.

- **Move**: the shafts as a tree grown from the first input; the shaft on the
  far side of the failing mesh, with every shaft beyond it, moves by one
  vector, so the other meshes stay right. Not offered inside a loop, where a
  move that mends one mesh breaks another.
- **Profile shift**: for two outside spur or helical gears, the shifts that
  meet the typed distance (:func:`pair.shift_for_centre`), written at full
  precision.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Set, Tuple

from ..gears import pair as pairs
from .geometry import Placed, centre_distance
from .model import GearboxSpec
from .xlsx import number_text


@dataclass(frozen=True)
class Edit:
    sheet: str           # "Shafts" or "Gears"
    row: int             # the item's row in that sheet
    key: str             # the column's key (schema)
    value: str           # the new text


@dataclass(frozen=True)
class Fix:
    title: str
    detail: str
    edits: Tuple[Edit, ...]


def _text(value: float, places: int = 6) -> str:
    return number_text(repr(round(value, places)))


def _shaft_graph(spec: GearboxSpec) -> Dict[str, Set[str]]:
    gears = {g.id: g for g in spec.gears}
    graph: Dict[str, Set[str]] = {s.id: set() for s in spec.shafts}
    for mesh in spec.meshes:
        a, b = gears.get(mesh.a), gears.get(mesh.b)
        if a is None or b is None or a.shaft == b.shaft or a.shaft not in graph or b.shaft not in graph:
            continue
        graph[a.shaft].add(b.shaft)
        graph[b.shaft].add(a.shaft)
    return graph


def _is_tree(graph: Dict[str, Set[str]], start: str) -> bool:
    seen, edges, queue = {start}, 0, deque([start])
    while queue:
        node = queue.popleft()
        for other in graph[node]:
            edges += 1
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return edges // 2 == len(seen) - 1


def move_fix(spec: GearboxSpec, a: Placed, b: Placed, required: float) -> Optional[Fix]:
    """Move the shaft farther from the input (and all beyond it) so ``a`` and ``b`` sit ``required`` apart."""
    graph = _shaft_graph(spec)
    inputs = [s.id for s in spec.shafts if s.role == "input"]
    root = inputs[0] if inputs else a.shaft
    if root not in graph or not _is_tree(graph, root):
        return None
    depth = {root: 0}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for other in graph[node]:
            if other not in depth:
                depth[other] = depth[node] + 1
                queue.append(other)
    if a.shaft not in depth or b.shaft not in depth:
        return None
    near, far = (a, b) if depth[a.shaft] <= depth[b.shaft] else (b, a)
    # Everything reached from the far shaft without going back through the near one.
    moving = {far.shaft}
    queue = deque([far.shaft])
    while queue:
        node = queue.popleft()
        for other in graph[node]:
            if other != near.shaft and other not in moving:
                moving.add(other)
                queue.append(other)
    actual = centre_distance(near, far)
    if actual < 1e-9:
        return None
    ux, uy = (far.x - near.x) / actual, (far.y - near.y) / actual
    dx, dy = ux * (required - actual), uy * (required - actual)
    shafts = {s.id: s for s in spec.shafts}
    edits: List[Edit] = []
    moves: List[str] = []
    for shaft_id in sorted(moving, key=lambda s: shafts[s].row):
        shaft = shafts[shaft_id]
        x, y = float(shaft.x) + dx, float(shaft.y) + dy
        if abs(dx) > 1e-12:
            edits.append(Edit("Shafts", shaft.row, "x", _text(x)))
        if abs(dy) > 1e-12:
            edits.append(Edit("Shafts", shaft.row, "y", _text(y)))
        moves.append(f"{shaft_id} X {_text(float(shaft.x), 3)} → {_text(x, 3)}"
                     + (f", Y {_text(float(shaft.y), 3)} → {_text(y, 3)}" if abs(dy) > 1e-12 else ""))
    others = len(moving) - 1
    title = f"Move {far.shaft}" + (f" and the {others} shaft{'s' if others != 1 else ''} beyond it" if others else "") \
        + f" by {_text(required - actual, 3)} mm"
    return Fix(title, " · ".join(moves), tuple(edits))


def shift_fix(spec: GearboxSpec, a: Placed, b: Placed, a_row: int, b_row: int) -> Optional[Fix]:
    """Keep the shafts where they are: profile-shift two outside spur or helical gears to meet their distance."""
    if a.internal or b.internal or a.herringbone != b.herringbone:
        return None
    da, db = a.derived, b.derived
    beta = getattr(da, "helix_angle_deg", 0.0)
    normal = getattr(da, "normal_pressure_angle_deg", da.pressure_angle_deg)
    actual = centre_distance(a, b)
    try:
        x1, x2 = pairs.shift_for_centre(a.module, a.teeth, b.teeth, actual, normal, beta)
    except ValueError:
        return None
    centre, _, epsilon = pairs.describe(a.module, a.teeth, b.teeth, normal, beta, shift_1=x1, shift_2=x2)
    mt = a.module / math.cos(math.radians(beta))
    alpha_t = getattr(da, "pressure_angle_deg", normal)
    working = pairs.working_pressure_angle(a.module, a.teeth, b.teeth, alpha_t, x1, x2, mt)
    detail = (f"x {x1:+.6f} / {x2:+.6f} → {centre:.3f} exact · working angle {working:.2f}° · ε {epsilon:.2f}")
    edits = (Edit("Gears", a_row, "profile_shift", _text(x1)), Edit("Gears", b_row, "profile_shift", _text(x2)))
    return Fix(f"Keep your positions: profile-shift {a.gear} and {b.gear}", detail, edits)


def apply(spec: GearboxSpec, fix: Fix) -> GearboxSpec:
    """The gearbox with a fix's edits made, for checking again before anything is written."""
    shafts = list(spec.shafts)
    gears = list(spec.gears)
    for edit in fix.edits:
        items = shafts if edit.sheet == "Shafts" else gears
        for index, item in enumerate(items):
            if item.row == edit.row:
                items[index] = replace(item, **{edit.key: edit.value})
    return replace(spec, shafts=tuple(shafts), gears=tuple(gears))
