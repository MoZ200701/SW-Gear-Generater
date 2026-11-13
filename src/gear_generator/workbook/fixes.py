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
    """One cell to change, named by the shaft or gear it belongs to, never by row: rows move when the user
    inserts, deletes or sorts in Excel, and a fix chosen before that must still land on the right item."""

    sheet: str           # "Shafts" or "Gears"
    item: str            # the shaft's or gear's name
    key: str             # the column's key (schema)
    value: str           # the new text


@dataclass(frozen=True)
class Fix:
    title: str
    detail: str
    edits: Tuple[Edit, ...]


def _text(value: float, places: int = 6) -> str:
    return number_text(repr(round(value, places)))


def _shaft_graph(spec: GearboxSpec) -> Dict[str, List[str]]:
    """Shaft -> the shafts it meshes with, once per mesh: two gear pairs between the same two shafts are two
    edges, a loop — moving either shaft mends one pair and breaks the other."""
    gears = {g.id: g for g in spec.gears}
    graph: Dict[str, List[str]] = {s.id: [] for s in spec.shafts}
    for mesh in spec.meshes:
        a, b = gears.get(mesh.a), gears.get(mesh.b)
        if a is None or b is None or a.shaft == b.shaft or a.shaft not in graph or b.shaft not in graph:
            continue
        graph[a.shaft].append(b.shaft)
        graph[b.shaft].append(a.shaft)
    return graph


def _component(graph: Dict[str, List[str]], start: str) -> Set[str]:
    seen, queue = {start}, deque([start])
    while queue:
        for other in graph[queue.popleft()]:
            if other not in seen:
                seen.add(other)
                queue.append(other)
    return seen


def _is_tree(graph: Dict[str, List[str]], start: str) -> bool:
    nodes = _component(graph, start)
    edges = sum(len(graph[n]) for n in nodes) // 2
    return edges == len(nodes) - 1


def move_fix(spec: GearboxSpec, a: Placed, b: Placed, required: float) -> Optional[Fix]:
    """Move the shaft farther from the input (and all beyond it) so ``a`` and ``b`` sit ``required`` apart."""
    graph = _shaft_graph(spec)
    if a.shaft not in graph:
        return None
    # The tree grows from the input when this train has one, else from its first shaft: a train the input does
    # not reach is mended the same way.
    component = _component(graph, a.shaft)
    order = {s.id: i for i, s in enumerate(spec.shafts)}
    inputs = [s.id for s in spec.shafts if s.role == "input" and s.id in component]
    root = inputs[0] if inputs else min(component, key=lambda s: order[s])
    if not _is_tree(graph, root):
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
            edits.append(Edit("Shafts", shaft_id, "x", _text(x)))
        if abs(dy) > 1e-12:
            edits.append(Edit("Shafts", shaft_id, "y", _text(y)))
        moves.append(f"{shaft_id} X {_text(float(shaft.x), 3)} → {_text(x, 3)}"
                     + (f", Y {_text(float(shaft.y), 3)} → {_text(y, 3)}" if abs(dy) > 1e-12 else ""))
    others = len(moving) - 1
    title = f"Move {far.shaft}" + (f" and the {others} shaft{'s' if others != 1 else ''} beyond it" if others else "") \
        + f" by {_text(required - actual, 3)} mm"
    return Fix(title, " · ".join(moves), tuple(edits))


def shift_fix(spec: GearboxSpec, a: Placed, b: Placed) -> Optional[Fix]:
    """Keep the shafts where they are: profile-shift two outside spur or helical gears to meet their distance.

    Not offered when either gear meshes with a third: shifting it moves that mesh's centre too (an idler).
    """
    if a.internal or b.internal or a.herringbone != b.herringbone:
        return None
    in_meshes = [m for m in spec.meshes if a.gear in (m.a, m.b) or b.gear in (m.a, m.b)]
    if len(in_meshes) > 1:
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
    edits = (Edit("Gears", a.gear, "profile_shift", _text(x1)), Edit("Gears", b.gear, "profile_shift", _text(x2)))
    return Fix(f"Keep your positions: profile-shift {a.gear} and {b.gear}", detail, edits)


def apply(spec: GearboxSpec, fix: Fix) -> GearboxSpec:
    """The gearbox with a fix's edits made, for checking again before anything is written."""
    shafts = list(spec.shafts)
    gears = list(spec.gears)
    for edit in fix.edits:
        items = shafts if edit.sheet == "Shafts" else gears
        for index, item in enumerate(items):
            if item.id == edit.item:
                items[index] = replace(item, **{edit.key: edit.value})
    return replace(spec, shafts=tuple(shafts), gears=tuple(gears))
