"""What every gear kind produces, and the closed set of steps a build is made of.

A build is plain data: a :class:`BuildPlan` holding a tuple of operations, each
a frozen dataclass. :mod:`swbuild` runs them against SolidWorks and a fake runs
them in the tests, through one code path whatever the kind of gear. So a bevel
gear later adds a kind and perhaps an operation or two; it does not touch the
interpreter, the store or the pair solver.

Lengths in an operation are millimetres and angles are degrees. Converting to
metres and radians is :mod:`swcom`'s job, at the one boundary where SolidWorks
is actually called.

Entities are referred to by recipe ids, never by COM pointers: ``"R"`` is the
root arc, ``"R.start"`` its start point, ``"origin"`` the sketch origin. The ids
are made on the Tk thread and resolved on the worker thread, which is the only
place a pointer may live.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, Union

from . import equations
from .equations import DEGREES, RADIANS, EquationError

Point2 = Tuple[float, float]
Point3 = Tuple[float, float, float]

ERROR = "error"
WARNING = "warning"

ORIGIN = "origin"


class GeometryError(ValueError):
    """The numbers on the form do not make a gear."""


@dataclass(frozen=True)
class Diagnostic:
    """One thing validation has to say, as a full sentence."""

    level: str
    message: str
    field: str = ""

    @property
    def is_error(self) -> bool:
        return self.level == ERROR


@dataclass(frozen=True)
class GlobalVariable:
    """One global in the Equation Manager.

    ``radian_expression`` is set only where trig is involved and the two modes
    differ; a document's trig units are measured before anything is written.
    """

    name: str
    expression: str
    radian_expression: str = ""

    def expression_for(self, trig: str) -> str:
        if trig == RADIANS and self.radian_expression:
            return self.radian_expression
        return self.expression

    def text(self, trig: str = DEGREES) -> str:
        return equations.equation_text(self.name, self.expression_for(trig))


# -- the operations ---------------------------------------------------------


@dataclass(frozen=True)
class NewPart:
    template: str


@dataclass(frozen=True)
class NewAssembly:
    template: str


@dataclass(frozen=True)
class AddGlobal:
    name: str
    expression: str
    radian_expression: str = ""

    def expression_for(self, trig: str) -> str:
        return self.radian_expression if trig == RADIANS and self.radian_expression else self.expression


@dataclass(frozen=True)
class LinkDimension:
    """``"OD@Blank Sketch"= "Outer Diameter"``, added once the dimension exists."""

    dimension: str
    expression: str
    radian_expression: str = ""

    def expression_for(self, trig: str) -> str:
        return self.radian_expression if trig == RADIANS and self.radian_expression else self.expression


PlaneRef = Union[int, str]


@dataclass(frozen=True)
class Axis:
    """A reference axis where two planes cross, selected in the order given.

    Each plane is an ``int``, the Nth reference plane in tree order (never a
    base plane's English name), or a ``str``, the id of a :class:`RefPlane`
    made earlier in the same plan — the form a workbook's layout part uses,
    one axis per shaft through the planes offset from Right and Top (probe
    tier 7, ``axis_through_named_planes`` and ``axis_through_base_planes``;
    the route that selects a plane by its kept name is
    ``findings.AXIS_PLANE_SELECT_ROUTE``). Which way the axis points follows
    the selection order (``findings.LAYOUT_AXIS_Z_SIGN``), so the order is
    part of the plan, not a detail of the runner.
    """

    id: str
    name: str
    planes: Tuple[PlaneRef, PlaneRef] = (2, 3)


@dataclass(frozen=True)
class OpenSketch:
    """A sketch on the Nth reference plane in tree order, or on a :class:`RefPlane` by its id."""

    id: str
    plane: Union[int, str] = 1


@dataclass(frozen=True)
class Circle:
    id: str
    centre: Point2
    radius: float
    construction: bool = False


@dataclass(frozen=True)
class Arc:
    """An arc from ``start`` to ``end`` about ``centre``; ``direction`` +1 is CCW."""

    id: str
    centre: Point2
    start: Point2
    end: Point2
    direction: int = 1
    construction: bool = False


@dataclass(frozen=True)
class Line:
    id: str
    start: Point2
    end: Point2
    construction: bool = False


@dataclass(frozen=True)
class Point:
    id: str
    at: Point2


@dataclass(frozen=True)
class EquationCurve:
    """A parametric curve ``x(t), y(t)`` for ``t`` from ``t1`` to ``t2``.

    ``start`` and ``end`` are where the curve is expected to begin and end, in
    millimetres: what the build checks the curve against, and what an endpoint
    is locked to if SolidWorks will not relate one.

    The expressions are in document units, and their trig is always radians.
    On SolidWorks 2026 a curve's ``cos ( t )`` took ``t`` as radians in a
    document whose Equation Manager works in degrees, and every spelling that
    converted with ``* 180 / pi`` was refused outright. The range is ordinary
    equation text and may name globals.
    """

    id: str
    x: str
    y: str
    t1: str
    t2: str
    start: Point2
    end: Point2


@dataclass(frozen=True)
class Relation:
    """A sketch relation over entities, in selection order (symmetric: the pair, then the line)."""

    kind: str
    refs: Tuple[str, ...]


@dataclass(frozen=True)
class Dimension:
    """A driving dimension, named once made. ``unit`` is ``mm`` or ``deg``."""

    name: str
    refs: Tuple[str, ...]
    at: Point2
    value: float
    unit: str = "mm"


@dataclass(frozen=True)
class CloseSketch:
    id: str
    name: str


@dataclass(frozen=True)
class Extrude:
    id: str
    sketch: str
    name: str
    depth: float
    depth_dim: str = "Width"


@dataclass(frozen=True)
class Cut:
    id: str
    sketch: str
    name: str


@dataclass(frozen=True)
class CircularPattern:
    id: str
    name: str
    axis: str
    feature: str
    count: int
    count_dim: str = "Count"


@dataclass(frozen=True)
class RefPlane:
    """A plane parallel to the Nth reference plane, ``offset`` mm from it.

    ``flip`` is SolidWorks' own flip of the distance, not a side: which side
    each flip puts the plane on is a probe finding, and the kind that plans the
    op turns the side it wants into the flag.
    """

    id: str
    name: str
    plane: int
    offset: float
    flip: bool = False
    offset_dim: str = "Offset"


@dataclass(frozen=True)
class SweepCut:
    """The ``profile`` sketch swept along the ``path`` sketch as a cut, turning uniformly.

    ``twist`` is the whole turn over the path, in degrees. ``reverse`` is
    SolidWorks' reverse-twist flag; which way either setting turns is a probe
    finding, and the kind that plans the op turns a hand into the flag.
    """

    id: str
    profile: str
    path: str
    name: str
    twist: float
    reverse: bool = False
    twist_dim: str = "Twist"


@dataclass(frozen=True)
class MirrorBody:
    """The part's body mirrored about a :class:`RefPlane` and merged into one."""

    id: str
    name: str
    plane: str


@dataclass(frozen=True)
class RefPlaneNormal:
    """A plane square to a line of a closed sketch, through a point on it (``"G.end"``).

    The plane has no dimension of its own: it follows the line, whose angle
    and length the sketch's own dimensions drive.
    """

    id: str
    name: str
    line: str
    point: str


@dataclass(frozen=True)
class Revolve:
    """A closed sketch revolved a full turn about one of its own lines, merged. ``axis`` is that line's id."""

    id: str
    sketch: str
    name: str
    axis: str


@dataclass(frozen=True)
class LoftCut:
    """A cut lofted through closed sketches, in order."""

    id: str
    name: str
    profiles: Tuple[str, ...]


@dataclass(frozen=True)
class CustomProperty:
    """A text custom property on the part: ``value`` as written, or a global's quoted name, which it then follows."""

    name: str
    value: str


@dataclass(frozen=True)
class ManualStep:
    """Something the build cannot do and a person must, counted in every log."""

    cause: str
    text: str


@dataclass(frozen=True)
class Rebuild:
    """The one rebuild, after the rebuild flag is restored."""


@dataclass(frozen=True)
class SaveAs:
    path: str


@dataclass(frozen=True)
class AddComponent:
    id: str
    path: str
    at: Point3 = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Fix:
    component: str


@dataclass(frozen=True)
class Unfix:
    """Let a component move again: the first one inserted comes in fixed."""

    component: str


@dataclass(frozen=True)
class Place:
    """Set a component's frame outright: a rotation (rows of a 3 × 3 matrix) and where its origin goes, in mm.

    Mates that can be satisfied more than one way take the nearest, so a
    component is placed where it belongs before it is mated.
    """

    component: str
    rotation: Tuple[float, ...]
    at: Point3


# The mate kinds that carry a value, and so a dimension an equation can drive.
VALUED_MATES = ("distance", "angle", "axis angle", "point distance")


@dataclass(frozen=True)
class Mate:
    """A mate between two references, ``component:plane-or-feature``.

    ``kind`` is ``coincident``, ``distance`` or ``angle`` between planes and
    axes; ``axis angle`` between two axes; ``point`` (coincident) and ``point
    distance`` from a component's origin, ``gearN:origin``, to a plane; and
    ``gear`` between two axes, turning them at ``ratio`` — the tooth counts of
    ``a`` and ``b`` — the same way or, with ``flip``, the other.
    ``asm:planeN`` is the assembly's own Nth plane.
    """

    id: str
    kind: str
    a: str
    b: str
    value: float = 0.0
    name: str = ""
    ratio: Tuple[float, float] = (1.0, 1.0)
    flip: bool = False


Op = Union[
    NewPart, NewAssembly, AddGlobal, LinkDimension, Axis, OpenSketch, Circle, Arc, Line, Point,
    EquationCurve, Relation, Dimension, CloseSketch, Extrude, Cut, CircularPattern, RefPlane, SweepCut,
    MirrorBody, RefPlaneNormal, Revolve, LoftCut, CustomProperty, ManualStep, Rebuild, SaveAs, AddComponent, Fix,
    Unfix, Place, Mate,
]
OPS = (
    NewPart, NewAssembly, AddGlobal, LinkDimension, Axis, OpenSketch, Circle, Arc, Line, Point,
    EquationCurve, Relation, Dimension, CloseSketch, Extrude, Cut, CircularPattern, RefPlane, SweepCut,
    MirrorBody, RefPlaneNormal, Revolve, LoftCut, CustomProperty, ManualStep, Rebuild, SaveAs, AddComponent, Fix,
    Unfix, Place, Mate,
)
SKETCH_ENTITIES = (Circle, Arc, Line, Point, EquationCurve)
GEOMETRY = SKETCH_ENTITIES + (Axis, OpenSketch, Relation, Dimension, CloseSketch, Extrude, Cut,
                              CircularPattern, RefPlane, SweepCut, MirrorBody, RefPlaneNormal, Revolve, LoftCut,
                              AddComponent, Fix, Unfix, Place, Mate)


# A mate reference to the assembly's own planes, ``asm:plane1``, names no component.
ASSEMBLY = "asm"


def ref_id(ref: str) -> str:
    """``"R.start"`` -> ``"R"``; ``"gear2:Front"`` -> ``"gear2"``."""
    return ref.split(":", 1)[0].split(".", 1)[0]


# -- the plan ---------------------------------------------------------------


@dataclass(frozen=True)
class BuildPlan:
    kind: str
    recipe: str
    ops: Tuple[Op, ...]
    path: str = ""
    notes: Tuple[str, ...] = ()

    def globals(self) -> List[AddGlobal]:
        return [op for op in self.ops if isinstance(op, AddGlobal)]

    def manual_steps(self) -> List[ManualStep]:
        return [op for op in self.ops if isinstance(op, ManualStep)]

    def links(self) -> List[LinkDimension]:
        return [op for op in self.ops if isinstance(op, LinkDimension)]

    def values(self, trig: str = DEGREES) -> Dict[str, float]:
        """Every global's value, by running them in order through the evaluator."""
        return equations.evaluate_all(
            ((op.name, op.expression_for(trig)) for op in self.globals()), trig
        )

    def check(self) -> List[str]:
        """What is wrong with this plan's order, as sentences. Empty when it is sound.

        * every global is defined before anything refers to it, in both trig
          modes, and all of them come before the first sketch;
        * every id is defined before it is used, and every entity sits in an
          open sketch;
        * a link names a dimension that exists and whose owner has its name;
        * exactly one rebuild, and a save, if any, is the last thing.
        """
        problems: List[str] = []
        for trig in (DEGREES, RADIANS):
            problems.extend(self._check_equations(trig))
        problems.extend(self._check_ids())
        return list(dict.fromkeys(problems))

    def _check_equations(self, trig: str) -> List[str]:
        problems: List[str] = []
        scope: Dict[str, float] = {}
        sketch_seen = False
        for op in self.ops:
            if isinstance(op, OpenSketch):
                sketch_seen = True
            if isinstance(op, AddGlobal):
                if sketch_seen:
                    problems.append(f"\"{op.name}\" is added after a sketch has been started.")
                try:
                    value = equations.evaluate(op.expression_for(trig), scope, trig)
                except EquationError as exc:
                    problems.append(f"\"{op.name}\" ({trig}): {exc}")
                    value = 0.0
                if op.name in scope:
                    problems.append(f"\"{op.name}\" is added twice.")
                scope[op.name] = value
            elif isinstance(op, LinkDimension):
                try:
                    equations.evaluate(op.expression_for(trig), scope, trig)
                except EquationError as exc:
                    problems.append(f"The link for {op.dimension} ({trig}): {exc}")
            elif isinstance(op, EquationCurve):
                for label, text in (("x", op.x), ("y", op.y)):
                    for t in ("t1", "t2"):
                        try:
                            at = equations.evaluate(getattr(op, t), scope, trig)
                            equations.evaluate(text, scope, RADIANS, {"t": at})
                        except EquationError as exc:
                            problems.append(f"Curve {op.id} {label} at {t} ({trig}): {exc}")
        return problems

    def _check_ids(self) -> List[str]:
        problems: List[str] = []
        defined = {ORIGIN, ASSEMBLY}
        open_sketch: Optional[str] = None
        sketch_names: Dict[str, str] = {}      # sketch id -> the name it was closed as
        feature_names: Dict[str, str] = {}     # feature id -> its name
        dimensions: Dict[str, List[str]] = {}  # sketch or feature id -> dimension names
        planes = set()                         # ids of RefPlanes made so far
        entity_sketch: Dict[str, str] = {}     # entity id -> the sketch it was drawn in
        rebuilds = 0

        def use(ref: str, op: object) -> None:
            if ref_id(ref) not in defined:
                problems.append(f"{type(op).__name__} uses {ref!r} before it is defined.")

        def define(identifier: str, op: object) -> None:
            if identifier in defined:
                problems.append(f"{type(op).__name__} defines {identifier!r} a second time.")
            defined.add(identifier)

        for index, op in enumerate(self.ops):
            if index == 0 and not isinstance(op, (NewPart, NewAssembly)):
                problems.append("A plan must start by making its document.")
            if isinstance(op, OpenSketch):
                if open_sketch is not None:
                    problems.append(f"Sketch {op.id!r} is opened while {open_sketch!r} is still open.")
                if isinstance(op.plane, str):
                    if op.plane not in planes:
                        problems.append(f"Sketch {op.id!r} is opened on {op.plane!r}, which is not a plane made earlier.")
                define(op.id, op)
                open_sketch = op.id
                dimensions[op.id] = []
            elif isinstance(op, SKETCH_ENTITIES):
                if open_sketch is None:
                    problems.append(f"{type(op).__name__} {op.id!r} is drawn with no sketch open.")
                define(op.id, op)
                entity_sketch[op.id] = open_sketch or ""
            elif isinstance(op, Relation):
                if open_sketch is None:
                    problems.append(f"A {op.kind} relation is added with no sketch open.")
                for ref in op.refs:
                    use(ref, op)
            elif isinstance(op, Dimension):
                if open_sketch is None:
                    problems.append(f"Dimension {op.name!r} is added with no sketch open.")
                else:
                    dimensions[open_sketch].append(op.name)
                for ref in op.refs:
                    use(ref, op)
            elif isinstance(op, CloseSketch):
                if open_sketch != op.id:
                    problems.append(f"Sketch {op.id!r} is closed but it is not the open one.")
                open_sketch = None
                sketch_names[op.id] = op.name
            elif isinstance(op, (Extrude, Cut)):
                use(op.sketch, op)
                define(op.id, op)
                feature_names[op.id] = op.name
                dimensions[op.id] = [op.depth_dim] if isinstance(op, Extrude) else []
            elif isinstance(op, CircularPattern):
                use(op.axis, op)
                use(op.feature, op)
                define(op.id, op)
                feature_names[op.id] = op.name
                dimensions[op.id] = [op.count_dim]
            elif isinstance(op, RefPlane):
                if open_sketch is not None:
                    problems.append(f"Plane {op.id!r} is made while sketch {open_sketch!r} is open.")
                define(op.id, op)
                planes.add(op.id)
                feature_names[op.id] = op.name
                dimensions[op.id] = [op.offset_dim]
            elif isinstance(op, SweepCut):
                for sketch in (op.profile, op.path):
                    use(sketch, op)
                    if sketch not in sketch_names:
                        problems.append(f"Sweep {op.id!r} uses sketch {sketch!r} before it is closed.")
                define(op.id, op)
                feature_names[op.id] = op.name
                dimensions[op.id] = [op.twist_dim]
            elif isinstance(op, (RefPlaneNormal, Revolve)):
                line = op.line if isinstance(op, RefPlaneNormal) else op.axis
                use(line, op)
                if entity_sketch.get(line) not in sketch_names:
                    problems.append(f"{type(op).__name__} {op.id!r} uses the line {line!r} of a sketch not yet closed.")
                if isinstance(op, RefPlaneNormal):
                    use(op.point, op)
                    if open_sketch is not None:
                        problems.append(f"Plane {op.id!r} is made while sketch {open_sketch!r} is open.")
                    planes.add(op.id)
                else:
                    use(op.sketch, op)
                    if op.sketch not in sketch_names:
                        problems.append(f"Revolve {op.id!r} uses sketch {op.sketch!r} before it is closed.")
                    if entity_sketch.get(line) != op.sketch:
                        problems.append(f"Revolve {op.id!r} turns about {line!r}, which is not in {op.sketch!r}.")
                define(op.id, op)
                feature_names[op.id] = op.name
                dimensions[op.id] = []
            elif isinstance(op, LoftCut):
                if len(op.profiles) < 2:
                    problems.append(f"Loft {op.id!r} needs at least two profiles.")
                for sketch in op.profiles:
                    use(sketch, op)
                    if sketch not in sketch_names:
                        problems.append(f"Loft {op.id!r} uses sketch {sketch!r} before it is closed.")
                define(op.id, op)
                feature_names[op.id] = op.name
                dimensions[op.id] = []
            elif isinstance(op, MirrorBody):
                use(op.plane, op)
                if op.plane not in planes:
                    problems.append(f"Mirror {op.id!r} is about {op.plane!r}, which is not a plane.")
                define(op.id, op)
                feature_names[op.id] = op.name
            elif isinstance(op, Axis):
                if open_sketch is not None:
                    problems.append(f"Axis {op.id!r} is made while sketch {open_sketch!r} is open.")
                for plane in op.planes:
                    if isinstance(plane, str) and plane not in planes:
                        problems.append(f"Axis {op.id!r} is through {plane!r}, which is not a plane made earlier.")
                define(op.id, op)
            elif isinstance(op, AddComponent):
                define(op.id, op)
            elif isinstance(op, (Fix, Unfix, Place)):
                use(op.component, op)
            elif isinstance(op, Mate):
                use(op.a, op)
                use(op.b, op)
                define(op.id, op)
                feature_names[op.id] = op.name or op.id
                dimensions[op.id] = ["D1"] if op.kind in VALUED_MATES else []
            elif isinstance(op, LinkDimension):
                dim, _, owner = op.dimension.partition("@")
                owners = {**sketch_names, **feature_names}
                matches = [key for key, name in owners.items() if name == owner]
                if not matches:
                    problems.append(f"{op.dimension} is linked before anything is named {owner!r}.")
                elif not any(dim in dimensions.get(key, []) for key in matches):
                    problems.append(f"{op.dimension} is linked but {owner} has no dimension {dim!r}.")
            elif isinstance(op, Rebuild):
                rebuilds += 1
                if open_sketch is not None:
                    problems.append(f"The rebuild comes while sketch {open_sketch!r} is still open.")
            elif isinstance(op, SaveAs):
                if index != len(self.ops) - 1:
                    problems.append("SaveAs must be the last step.")
                if rebuilds == 0:
                    problems.append("SaveAs comes before the rebuild.")
            if rebuilds and isinstance(op, GEOMETRY + (AddGlobal, LinkDimension)):
                problems.append(f"{type(op).__name__} comes after the rebuild.")

        if open_sketch is not None:
            problems.append(f"Sketch {open_sketch!r} is never closed.")
        if rebuilds != 1:
            problems.append(f"A plan rebuilds exactly once; this one rebuilds {rebuilds} times.")
        return problems

    def log_lines(self, trig: str = DEGREES) -> List[str]:
        """The plan as a dry run: one line per step, ``MANUAL`` for what a person does."""
        lines: List[str] = []
        manual = self.manual_steps()
        lines.append(f"plan    {self.kind} · recipe {self.recipe} · {len(self.ops)} steps")
        lines.append(f"globals {len(self.globals())}")
        if manual:
            lines.append(f"MANUAL  {len(manual)} step(s) a person must do, listed below")
        for op in self.ops:
            lines.append(describe(op, trig))
        return lines


def _fmt_point(point: Sequence[float]) -> str:
    return "(" + ", ".join(equations.literal(round(v, 6)) for v in point) + ")"


def describe(op: Op, trig: str = DEGREES) -> str:
    """One op as one log line, in the ``ok``-token idiom of the build log."""
    name = type(op).__name__
    if isinstance(op, AddGlobal):
        return f"global  {equations.equation_text(op.name, op.expression_for(trig))}"
    if isinstance(op, LinkDimension):
        return f"link    {equations.equation_text(op.dimension, op.expression_for(trig))}"
    if isinstance(op, ManualStep):
        return f"MANUAL  {op.text}"
    if isinstance(op, CustomProperty):
        return f"prop    {op.name!r} = {op.value}"
    if isinstance(op, (NewPart, NewAssembly)):
        return f"new     {name} from {op.template or '(default template)'}"
    if isinstance(op, Circle):
        extra = " construction" if op.construction else ""
        return f"circle  {op.id} at {_fmt_point(op.centre)} r {equations.literal(round(op.radius, 6))}{extra}"
    if isinstance(op, Arc):
        return f"arc     {op.id} about {_fmt_point(op.centre)} {_fmt_point(op.start)} -> {_fmt_point(op.end)}"
    if isinstance(op, Line):
        extra = " construction" if op.construction else ""
        return f"line    {op.id} {_fmt_point(op.start)} -> {_fmt_point(op.end)}{extra}"
    if isinstance(op, Point):
        return f"point   {op.id} {_fmt_point(op.at)}"
    if isinstance(op, EquationCurve):
        return f"curve   {op.id} x: {op.x} | y: {op.y} | t: {op.t1} .. {op.t2}"
    if isinstance(op, Relation):
        return f"relate  {op.kind} {' '.join(op.refs)}"
    if isinstance(op, Dimension):
        return f"dim     {op.name} = {equations.literal(round(op.value, 6))} {op.unit} on {' '.join(op.refs)}"
    if isinstance(op, OpenSketch):
        return f"sketch  {op.id} on plane {op.plane}"
    if isinstance(op, CloseSketch):
        return f"close   {op.id} as {op.name!r}"
    if isinstance(op, Axis):
        if all(isinstance(p, int) for p in op.planes):
            return f"axis    {op.name!r} through planes {op.planes[0]} and {op.planes[1]}"
        first, second = (p if isinstance(p, str) else f"plane {p}" for p in op.planes)
        return f"axis    {op.name!r} through {first} and {second}"
    if isinstance(op, RefPlane):
        flipped = ", flipped" if op.flip else ""
        return f"plane   {op.name!r} {equations.literal(round(op.offset, 6))} mm from plane {op.plane}{flipped} ({op.offset_dim})"
    if isinstance(op, SweepCut):
        reverse = ", reversed" if op.reverse else ""
        return (f"sweep   {op.name!r} of {op.profile} along {op.path}, twist "
                f"{equations.literal(round(op.twist, 6))}°{reverse} ({op.twist_dim})")
    if isinstance(op, MirrorBody):
        return f"mirror  {op.name!r} the body about {op.plane}"
    if isinstance(op, RefPlaneNormal):
        return f"plane   {op.name!r} square to {op.line} through {op.point}"
    if isinstance(op, Revolve):
        return f"revolve {op.name!r} from {op.sketch} about {op.axis}, a full turn"
    if isinstance(op, LoftCut):
        return f"loft    {op.name!r} cut through {' -> '.join(op.profiles)}"

    if isinstance(op, Extrude):
        return f"extrude {op.name!r} from {op.sketch}, depth {equations.literal(op.depth)} ({op.depth_dim})"
    if isinstance(op, Cut):
        return f"cut     {op.name!r} from {op.sketch}, through all"
    if isinstance(op, CircularPattern):
        return f"pattern {op.name!r} of {op.feature} about {op.axis}, {op.count} ({op.count_dim})"
    if isinstance(op, Rebuild):
        return "rebuild once"
    if isinstance(op, SaveAs):
        return f"save    {op.path}"
    if isinstance(op, AddComponent):
        return f"insert  {op.id} {op.path} at {_fmt_point(op.at)}"
    if isinstance(op, Fix):
        return f"fix     {op.component}"
    if isinstance(op, Unfix):
        return f"unfix   {op.component}"
    if isinstance(op, Place):
        return f"place   {op.component} at {_fmt_point(op.at)} turned {_fmt_point(op.rotation)}"
    if isinstance(op, Mate):
        value = f" {equations.literal(round(op.value, 9))}" if op.kind in VALUED_MATES else ""
        if op.kind == "gear":
            value = (f" {equations.literal(op.ratio[0])}:{equations.literal(op.ratio[1])}"
                     + (", flipped" if op.flip else ""))
        return f"mate    {op.kind}{value} {op.a} ~ {op.b}" + (f" as {op.name!r}" if op.name else "")
    return name  # pragma: no cover - every op is listed above


def op_fields(op: Op) -> Dict[str, object]:
    return {f.name: getattr(op, f.name) for f in fields(op)}


# -- the seam every kind of gear fits ---------------------------------------


class Derived(Protocol):
    def values(self) -> Mapping[str, float]: ...


class GearKind(Protocol):
    kind: str
    recipes: Mapping[str, str]
    default_recipe: str

    def derive(self, spec) -> Derived: ...
    def validate(self, spec, derived: Optional[Derived] = None) -> List[Diagnostic]: ...
    def variables(self, spec, derived: Derived, trig: str = DEGREES) -> List[GlobalVariable]: ...
    def outline(self, spec, derived: Derived, recipe: str = "") -> List[Point2]: ...
    def plan(self, spec, derived: Derived, recipe: str, template: str, path: str) -> BuildPlan: ...
