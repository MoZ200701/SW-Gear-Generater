"""Running a build plan against SolidWorks, in the right order.

A :class:`~gears.base.BuildPlan` is plain data; this module is the one place
that walks it and says what happened. What SolidWorks is reached through is a
:class:`SolidWorks` protocol, so every rule below is testable against a fake
on a machine with no CAD package at all:

* **Measure the document's trig units before writing a global.** A degree
  expression in a radian document is a wrong gear with no red equation to
  show for it.
* **Suppress the rebuild for the whole batch and restore it in a ``finally``.**
  A document left suppressed looks fine and silently stops updating.
* **Stop geometry at the first failure.** A sketch that did not close cannot
  be extruded, and every later step would fail in a way that hides the first.
* **Rebuild exactly once, even after a stop,** so what is left open for
  inspection shows SolidWorks' own view of it.
* **Read names and values back.** A kept name that differs from the one asked
  for stops the build before an equation refers to it, and every global's value
  after the rebuild is compared with the maths.
* **Save only a build with no failures,** and never over an existing file.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple, Union

from . import findings
from .gears import base
from .gears.base import BuildPlan, GlobalVariable
from .gears.equations import DEGREES, RADIANS, EquationError, evaluate_all, split_equation
from .store import GEARBOX_MOTION, GEARBOX_STATIC, same_path
from .swcom import (ASSEMBLY_PAIR, ASSEMBLY_STATIC, ASSEMBLY_TRAIN, DOC_ASSEMBLY, MINIMUM_MAJOR, ComponentGone,
                    DocInfo, MateGone, MateRefused, MateState, SolidWorksError, meets_minimum, rebuild_call,
                    release_year)

VALUE_TOLERANCE = 1e-6
FULLY_DEFINED = 3


class SolidWorks(Protocol):
    """Exactly the slice of :class:`swcom.Session` a build uses."""

    revision: Tuple[int, ...]

    def active_document(self) -> Optional[DocInfo]: ...
    def begin_build(self) -> None: ...
    def end_build(self) -> None: ...
    def new_part(self, template: str = "") -> DocInfo: ...
    def new_assembly(self, template: str = "") -> DocInfo: ...
    def document_path(self) -> str: ...
    def set_rebuild_suppressed(self, suppressed: bool) -> None: ...
    def rebuild(self, kind: Optional[str] = None) -> bool: ...
    def save_as(self, path: str) -> str: ...
    def detect_trig_units(self) -> str: ...
    def add_global_variable(self, name: str, expression: str) -> int: ...
    def set_global_variable(self, name: str, expression: str) -> None: ...
    def link_dimension(self, dimension: str, expression: str) -> int: ...
    def equations(self) -> List[Tuple[str, float]]: ...
    def equation_values(self) -> Dict[str, float]: ...
    def insert_axis(self, handle: str, name: str, planes: Tuple[base.PlaneRef, base.PlaneRef]) -> str: ...
    def open_sketch(self, handle: str, plane: Union[int, str]) -> None: ...
    def close_sketch(self, handle: str, name: str) -> str: ...
    def sketch_status(self, name: str) -> int: ...
    def sketch_circle(self, handle: str, centre, radius: float, construction: bool = False) -> None: ...
    def sketch_arc(self, handle: str, centre, start, end, direction: int = 1, construction: bool = False) -> None: ...
    def sketch_line(self, handle: str, start, end, construction: bool = False) -> None: ...
    def sketch_point(self, handle: str, at) -> None: ...
    def sketch_equation_curve(self, handle: str, x: str, y: str, t1: str, t2: str, start, end) -> None: ...
    def add_relation(self, kind: str, refs: Sequence[str]) -> str: ...
    def dimension(self, name: str, refs: Sequence[str], at) -> str: ...
    def extrude(self, handle: str, sketch: str, name: str, depth: float, depth_dim: str) -> Tuple[str, str]: ...
    def cut_extrude(self, handle: str, sketch: str, name: str) -> str: ...
    def circular_pattern(self, handle: str, name: str, axis: str, feature: str, count: int,
                         count_dim: str) -> Tuple[str, str]: ...
    def ref_plane(self, handle: str, name: str, plane: int, offset: float, flip: bool,
                  offset_dim: str) -> Tuple[str, str]: ...
    def sweep_cut(self, handle: str, profile: str, path: str, name: str, twist: float, reverse: bool,
                  twist_dim: str) -> Tuple[str, str]: ...
    def mirror_body(self, handle: str, name: str, plane: str) -> str: ...
    def ref_plane_normal(self, handle: str, name: str, line: str, point: str) -> str: ...
    def revolve(self, handle: str, sketch: str, name: str, axis: str) -> str: ...
    def loft_cut(self, handle: str, name: str, profiles: Sequence[str]) -> str: ...
    def add_component(self, handle: str, path: str, at) -> str: ...
    def fix_component(self, handle: str) -> None: ...
    def unfix_component(self, handle: str) -> None: ...
    def add_mate(self, handle: str, kind: str, a: str, b: str, value: float = 0.0,
                 name: str = "", ratio: Tuple[float, float] = (1.0, 1.0), flip: bool = False) -> Tuple[str, str]: ...
    def interference_count(self) -> Tuple[int, float]: ...
    def set_custom_property(self, name: str, value: str) -> None: ...
    def place_component(self, handle: str, rotation: Sequence[float], at, kind: Optional[str] = None) -> None: ...
    # W4 (a workbook's layout part and static assembly). ``documents`` and ``feature_names`` are swcom.Session's
    # own, unchanged; the other four are new there (each docstring in swcom says what it does).
    def documents(self) -> List[DocInfo]: ...
    def feature_names(self) -> List[str]: ...
    def open_document(self, path: str) -> DocInfo: ...
    def has_unsaved_changes(self) -> bool: ...
    def find_component(self, handle: str, name: str) -> str: ...
    def component_frame(self, handle: str) -> Tuple[Tuple[float, ...], Tuple[float, float, float]]: ...
    def interferences(self) -> List[Tuple[Tuple[str, ...], float]]: ...
    # W5 (the workbook gearbox that turns): new in swcom.Session, each docstring there says what it does. ``add_mate``
    # also takes kind "lock" (bare handles, anchor first: gears.base.Mate) and keeps AddMate5's status.
    def mate_status(self, name: str) -> Optional[int]: ...
    def mate_states(self) -> List[MateState]: ...
    def constrained_status(self, handle: str) -> int: ...
    def find_mate(self, handle: str, name: str) -> str: ...
    def set_mate_suppressed(self, handle: str, suppressed: bool) -> None: ...
    def set_gear_ratio(self, handle: str, a: str, b: str, ratio: Tuple[int, int]) -> None: ...


class BuildError(SolidWorksError):
    """The build could not start at all; nothing was made."""


class NotAsBuilt(BuildError):
    """A document built earlier, opened and read, does not hold what it should: a global's text differs or is
    gone, or a feature or component named on record was renamed or deleted in SolidWorks. ``path`` is that
    document. :func:`build_gearbox` turns it into :attr:`GearboxResult.mismatched` (the finish records it, so the
    next plan makes the part new rather than reuse it: W4 review B2's last corner); :func:`update_gearbox` raises
    it from its check phase, before anything changes."""

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(message)
        self.path = path


@dataclass
class BuildResult:
    kind: str = ""
    recipe: str = ""
    document: str = ""
    path: str = ""
    trig: str = ""
    done: List[str] = field(default_factory=list)
    failures: List[Tuple[str, str]] = field(default_factory=list)
    stopped_at: str = ""
    features: List[str] = field(default_factory=list)
    dimensions: Dict[str, str] = field(default_factory=dict)   # planned "Dim@Owner" -> what SolidWorks kept
    manual: List[str] = field(default_factory=list)
    checks: List[str] = field(default_factory=list)            # things to look at that do not fail a build
    rebuilt: bool = False
    saved: str = ""
    components: Dict[str, str] = field(default_factory=dict)   # an assembly's plan handle -> the Name2 it kept
    # W5, a train's mate check (filled only for a build of kind ASSEMBLY_TRAIN; see :func:`build`): every REFUSAL
    # found, as a full sentence naming the mate or gear, each also a failure (so the assembly is not saved), and every
    # mate as SolidWorks held it when checked, for the log. Only SolidWorks' own refusals go here (MateRefused, and
    # the check's status, error code, suppressed and constrained findings); a COM or any other failure is an
    # ordinary failed build, as in W4, with no mate problem.
    mate_problems: List[str] = field(default_factory=list)
    mates: List[MateState] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def log_lines(self) -> List[str]:
        lines = [f"build   {self.document or '(no document)'} · {self.kind} · recipe {self.recipe} · trig {self.trig or '?'}"]
        lines.extend(f"ok      {line}" for line in self.done)
        for what, why in self.failures:
            lines.append(f"FAIL    {what}: {why}")
        if self.stopped_at:
            lines.append(f"STOPPED at {self.stopped_at}; the part is left open as it is")
        lines.extend(f"CHECK   {line}" for line in self.checks)
        if self.document or self.rebuilt:          # no document made (_build_in_job): nothing was rebuilt either
            lines.append("ok      rebuilt once" if self.rebuilt else "FAIL    the rebuild reported an error")
        if self.manual:
            lines.append(f"MANUAL  {len(self.manual)} step(s) to do by hand")
            lines.extend(f"MANUAL  {text}" for text in self.manual)
        lines.append(f"ok      saved {self.saved}" if self.saved else "not saved")
        return lines


@dataclass
class PairResult:
    gear_a: BuildResult
    gear_b: Optional[BuildResult] = None
    assembly: Optional[BuildResult] = None
    skipped: str = ""

    @property
    def ok(self) -> bool:
        return all(r is not None and r.ok for r in (self.gear_a, self.gear_b, self.assembly))

    def log_lines(self) -> List[str]:
        lines: List[str] = []
        for result in (self.gear_a, self.gear_b, self.assembly):
            if result is not None:
                lines.extend(result.log_lines())
        if self.skipped:
            lines.append(f"SKIPPED {self.skipped}")
        return lines


@dataclass
class UpdateResult:
    document: str = ""
    changed: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    failures: List[Tuple[str, str]] = field(default_factory=list)
    rebuilt: bool = False
    trig: str = ""

    @property
    def ok(self) -> bool:
        return not self.failures


def _gate(sw: SolidWorks) -> None:
    if not meets_minimum(sw.revision):
        raise BuildError(f"Building needs SolidWorks {release_year(MINIMUM_MAJOR)} or newer.")


def _assembly_rebuild_gate(kind: str) -> None:
    """Refuse, before anything is made or changed, a job that would rebuild an assembly of this kind while how to
    rebuild one is not settled: :func:`swcom.rebuild_call`'s sentence, as a :class:`BuildError`. Every assembly
    rebuild goes through ``rebuild_call`` (``Session.rebuild`` and ``place_component``), so without this a job
    would make or change its parts and only then refuse at the assembly. A pair or a train is refused only for a
    finding of its own this code does not know: with none, it takes the full rebuild."""
    try:
        rebuild_call(DOC_ASSEMBLY, kind)
    except SolidWorksError as exc:
        raise BuildError(str(exc)) from None


def is_mated(plan: BuildPlan) -> bool:
    """Whether an assembly plan mates its components (W5-PLAN §1's predicate)."""
    return any(isinstance(op, base.Mate) for op in plan.ops)


def workbook_assembly_kind(plan: BuildPlan) -> str:
    """The kind of a workbook gearbox's assembly, and of any assembly built outside :func:`build_pair`: a train
    when its plan mates its components (W5), else static (fixed components, W4)."""
    return ASSEMBLY_TRAIN if is_mated(plan) else ASSEMBLY_STATIC


# -- the operations ---------------------------------------------------------


def _kept(result: BuildResult, what: str, wanted: str, kept: str) -> None:
    if kept != wanted:
        raise SolidWorksError(f"SolidWorks named the {what} {kept!r} instead of {wanted!r}, "
                              "so the equations that name it would break.")
    result.features.append(kept)


def _add_global(sw, op: base.AddGlobal, result, trig):
    sw.add_global_variable(op.name, op.expression_for(trig))
    return f"global \"{op.name}\""


def _link(sw, op: base.LinkDimension, result, trig):
    # A dimension SolidWorks named for itself (a mate's D1) is linked by what it kept.
    dimension = result.dimensions.get(op.dimension, op.dimension)
    sw.link_dimension(dimension, op.expression_for(trig))
    return f"link \"{dimension}\""


def _axis(sw, op: base.Axis, result, trig):
    _kept(result, "axis", op.name, sw.insert_axis(op.id, op.name, op.planes))
    return f"axis {op.name}"


def _open(sw, op: base.OpenSketch, result, trig):
    sw.open_sketch(op.id, op.plane)
    return f"sketch {op.id} opened on plane {op.plane}"


def _circle(sw, op: base.Circle, result, trig):
    sw.sketch_circle(op.id, op.centre, op.radius, op.construction)
    return f"circle {op.id}"


def _arc(sw, op: base.Arc, result, trig):
    sw.sketch_arc(op.id, op.centre, op.start, op.end, op.direction, op.construction)
    return f"arc {op.id}"


def _line(sw, op: base.Line, result, trig):
    sw.sketch_line(op.id, op.start, op.end, op.construction)
    return f"line {op.id}"


def _point(sw, op: base.Point, result, trig):
    sw.sketch_point(op.id, op.at)
    return f"point {op.id}"


def _curve(sw, op: base.EquationCurve, result, trig):
    sw.sketch_equation_curve(op.id, op.x, op.y, op.t1, op.t2, op.start, op.end)
    return f"curve {op.id}"


def _relation(sw, op: base.Relation, result, trig):
    note = sw.add_relation(op.kind, op.refs)
    return f"{op.kind} {' '.join(op.refs)}" + (f" ({note})" if note else "")


def _dimension(sw, op: base.Dimension, result, trig):
    kept = sw.dimension(op.name, op.refs, op.at)
    if kept != op.name:
        raise SolidWorksError(f"SolidWorks named the dimension {kept!r} instead of {op.name!r}.")
    result.dimensions[op.name] = kept
    return f"dimension {op.name}"


def _close(sw, op: base.CloseSketch, result, trig):
    kept = sw.close_sketch(op.id, op.name)
    _kept(result, "sketch", op.name, kept)
    for planned in [k for k in result.dimensions if "@" not in k]:
        result.dimensions[f"{planned}@{kept}"] = f"{result.dimensions.pop(planned)}@{kept}"
    return f"sketch {op.name}"


def _extrude(sw, op: base.Extrude, result, trig):
    kept, dim = sw.extrude(op.id, op.sketch, op.name, op.depth, op.depth_dim)
    _kept(result, "extrusion", op.name, kept)
    if dim != op.depth_dim:
        raise SolidWorksError(f"The depth of {kept} kept the name {dim!r} instead of {op.depth_dim!r}.")
    result.dimensions[f"{op.depth_dim}@{op.name}"] = f"{dim}@{kept}"
    return f"extrude {op.name}"


def _cut(sw, op: base.Cut, result, trig):
    _kept(result, "cut", op.name, sw.cut_extrude(op.id, op.sketch, op.name))
    return f"cut {op.name}"


def _pattern(sw, op: base.CircularPattern, result, trig):
    kept, dim = sw.circular_pattern(op.id, op.name, op.axis, op.feature, op.count, op.count_dim)
    _kept(result, "pattern", op.name, kept)
    if dim != op.count_dim:
        raise SolidWorksError(f"The count of {kept} kept the name {dim!r} instead of {op.count_dim!r}.")
    result.dimensions[f"{op.count_dim}@{op.name}"] = f"{dim}@{kept}"
    return f"pattern {op.name} × {op.count}"


def _ref_plane(sw, op: base.RefPlane, result, trig):
    kept, dim = sw.ref_plane(op.id, op.name, op.plane, op.offset, op.flip, op.offset_dim)
    _kept(result, "plane", op.name, kept)
    if dim != op.offset_dim:
        raise SolidWorksError(f"The offset of {kept} kept the name {dim!r} instead of {op.offset_dim!r}.")
    result.dimensions[f"{op.offset_dim}@{op.name}"] = f"{dim}@{kept}"
    return f"plane {op.name}"


def _sweep(sw, op: base.SweepCut, result, trig):
    kept, dim = sw.sweep_cut(op.id, op.profile, op.path, op.name, op.twist, op.reverse, op.twist_dim)
    _kept(result, "sweep", op.name, kept)
    if dim != op.twist_dim:
        raise SolidWorksError(f"The twist of {kept} kept the name {dim!r} instead of {op.twist_dim!r}.")
    result.dimensions[f"{op.twist_dim}@{op.name}"] = f"{dim}@{kept}"
    return f"sweep {op.name}, twist {op.twist:.4f}°" + (" reversed" if op.reverse else "")


def _mirror(sw, op: base.MirrorBody, result, trig):
    _kept(result, "mirror", op.name, sw.mirror_body(op.id, op.name, op.plane))
    return f"mirror {op.name}"


def _ref_plane_normal(sw, op: base.RefPlaneNormal, result, trig):
    _kept(result, "plane", op.name, sw.ref_plane_normal(op.id, op.name, op.line, op.point))
    return f"plane {op.name}"


def _revolve(sw, op: base.Revolve, result, trig):
    _kept(result, "revolve", op.name, sw.revolve(op.id, op.sketch, op.name, op.axis))
    return f"revolve {op.name}"


def _loft_cut(sw, op: base.LoftCut, result, trig):
    _kept(result, "loft", op.name, sw.loft_cut(op.id, op.name, op.profiles))
    return f"loft {op.name}"


def _property(sw, op: base.CustomProperty, result, trig):
    sw.set_custom_property(op.name, op.value)
    return f"property {op.name!r}"


def _component(sw, op: base.AddComponent, result, trig):
    kept = sw.add_component(op.id, op.path, op.at)
    result.features.append(kept)
    result.components[op.id] = kept
    return f"component {kept}"


def _fix(sw, op: base.Fix, result, trig):
    sw.fix_component(op.component)
    return f"fixed {op.component}"


def _unfix(sw, op: base.Unfix, result, trig):
    sw.unfix_component(op.component)
    return f"unfixed {op.component}"


def _place(sw, op: base.Place, result, trig, kind):
    sw.place_component(op.component, op.rotation, op.at, kind=kind)
    return f"placed {op.component}"


def _mate(sw, op: base.Mate, result, trig):
    extra = {"ratio": op.ratio, "flip": op.flip} if op.kind == "gear" else {}
    kept, dim = sw.add_mate(op.id, op.kind, op.a, op.b, op.value, op.name, **extra)
    if op.name:
        _kept(result, "mate", op.name, kept)
    else:
        result.features.append(kept)
    if op.kind in base.VALUED_MATES:
        if not dim:
            raise SolidWorksError(f"The {op.kind} mate {kept} has no dimension with its value.")
        result.dimensions[f"D1@{op.name or op.id}"] = f"{dim}@{kept}"
    return f"mate {op.kind} {op.a} ~ {op.b}" + (f" as {kept}" if op.name else "")


_RUNNERS: Mapping[type, Callable] = {
    base.AddGlobal: _add_global,
    base.LinkDimension: _link,
    base.Axis: _axis,
    base.OpenSketch: _open,
    base.Circle: _circle,
    base.Arc: _arc,
    base.Line: _line,
    base.Point: _point,
    base.EquationCurve: _curve,
    base.Relation: _relation,
    base.Dimension: _dimension,
    base.CloseSketch: _close,
    base.Extrude: _extrude,
    base.Cut: _cut,
    base.CircularPattern: _pattern,
    base.RefPlane: _ref_plane,
    base.SweepCut: _sweep,
    base.MirrorBody: _mirror,
    base.RefPlaneNormal: _ref_plane_normal,
    base.Revolve: _revolve,
    base.LoftCut: _loft_cut,
    base.CustomProperty: _property,
    base.AddComponent: _component,
    base.Fix: _fix,
    base.Unfix: _unfix,
    base.Place: _place,
    base.Mate: _mate,
}


# -- building ---------------------------------------------------------------


def build(sw: SolidWorks, plan: BuildPlan, exists: Callable[[str], bool] = os.path.exists,
          kind: Optional[str] = None) -> BuildResult:
    """Make the plan's document, run every step, rebuild once, check, and save.

    Raises :class:`BuildError` only before anything is made. After that every
    problem is a failure in the result, and the document is left open.

    ``kind`` says what kind of assembly this is (``swcom.ASSEMBLY_KINDS``),
    for every rebuild and put of it (:func:`swcom.rebuild_call`); None reads
    it off the plan (:func:`workbook_assembly_kind`: a train if it mates its
    components, else static). :func:`build_pair` passes ``ASSEMBLY_PAIR``, so a
    pair keeps its own route whatever its plan holds, the puts before its
    mates included.

    W5 (Agent A writes it; W5-INTERFACES.md): a build whose kind, as
    resolved here, is ``ASSEMBLY_TRAIN`` runs the mate check after ``_run``,
    the rebuild and ``_verify``, before the save — every ``Mate`` op's
    ``sw.mate_status`` is ``findings.ADD_MATE_NO_ERROR``, ``sw.mate_states()``
    holds every planned mate with code 0 and not suppressed, and every mated
    gear (a handle in a ``Mate`` op whose last ``Fix``/``Unfix`` op is
    ``Unfix``) reads ``findings.COMPONENT_UNDER_DEFINED`` — each problem a
    sentence in :attr:`BuildResult.mate_problems` and a failure, so the
    document is left open, unsaved. A ``Mate`` op that raises
    ``swcom.MateRefused`` in ``_run`` puts its sentence in ``mate_problems``
    too; any other raise during a mate (a COM or RPC failure, a selection
    that did not take) is an ordinary failure, as in W4, and adds nothing to
    ``mate_problems`` — so the record holds Build back only for a refusal
    that repeats on every press. There is no ``mates=`` keyword: the
    kind decides, so a pair (``ASSEMBLY_PAIR``) and a static assembly are
    never mate-checked.
    """
    _gate(sw)
    problems = plan.check()
    if problems:
        raise BuildError("The build plan is not sound: " + " ".join(problems))
    first = plan.ops[0]
    if kind is None:
        kind = workbook_assembly_kind(plan)
    if isinstance(first, base.NewAssembly):
        _assembly_rebuild_gate(kind)
    save = next((op for op in plan.ops if isinstance(op, base.SaveAs)), None)
    if save is not None and save.path and exists(save.path):
        raise BuildError(f"{save.path} already exists, and a build never overwrites a file.")

    result = BuildResult(kind=plan.kind, recipe=plan.recipe, path=save.path if save else "")
    result.manual = [op.text for op in plan.manual_steps()]
    sw.begin_build()
    try:
        made = sw.new_part(first.template) if isinstance(first, base.NewPart) else sw.new_assembly(first.template)
        result.document = made.title
        result.done.append(f"new {'part' if isinstance(first, base.NewPart) else 'assembly'} {made.title}")
        try:
            result.trig = sw.detect_trig_units()
            result.done.append(f"trig units measured: {result.trig}")
            _run(sw, plan, result, kind)
            result.rebuilt = bool(sw.rebuild(kind=kind))
            _verify(sw, plan, result)
        except Exception as exc:  # noqa: BLE001 - the document is made: every problem is now a failure (B1)
            result.failures.append(("the build", _said(exc)))
            result.stopped_at = result.stopped_at or "the build"
    finally:
        sw.end_build()

    if save is not None and result.ok and result.rebuilt:
        try:
            result.saved = sw.save_as(save.path)
        except Exception as exc:  # noqa: BLE001 - a COM error or anything else on the save is the save's failure
            result.failures.append(("save", _said(exc)))
    return result


def _said(exc: BaseException) -> str:
    """What a raise says, for a failure line: a SolidWorks refusal (``swcom.ComError`` included) as it came, and
    anything else named, since it is not a sentence of ours."""
    if isinstance(exc, SolidWorksError):
        return str(exc)
    text = str(exc).strip().rstrip(".")
    return f"it stopped on an unexpected {type(exc).__name__}" + (f": {text}." if text else ".")


def _build_in_job(sw: SolidWorks, plan: BuildPlan, exists: Callable[[str], bool],
                  kind: Optional[str] = None) -> BuildResult:
    """:func:`build`, for one document of a job that has already saved others: what :func:`build` raises (its
    template is not there, SolidWorks would not make the document, the path was taken since the job's own check)
    comes back as a failed :class:`BuildResult` instead, so the job still reports, and the record still keeps,
    the documents saved before it.

    On SolidWorks 2026 (34.0.0, probe/workbook_assembly_check.py 2026-11-13) a workbook build whose assembly
    template was not there raised "There is no assembly template at …" out of ``build_gearbox`` after its four
    parts and its layout part had saved, so the window's finish never ran and none of the five was on record.
    Any other raise is caught too (W4 review B1: a ``pywintypes.com_error`` part-way through orphaned every file
    already saved), with its type named.
    """
    try:
        return build(sw, plan, exists, kind=kind)
    except Exception as exc:  # noqa: BLE001 - see the docstring
        first = plan.ops[0] if plan.ops else None
        what = ("new part" if isinstance(first, base.NewPart) else "new assembly"
                if isinstance(first, base.NewAssembly) else "the build")
        save = next((op for op in plan.ops if isinstance(op, base.SaveAs)), None)
        return BuildResult(kind=plan.kind, recipe=plan.recipe, path=save.path if save else "",
                           failures=[(what, _said(exc))], stopped_at=what,
                           manual=[op.text for op in plan.manual_steps()])


def _run(sw: SolidWorks, plan: BuildPlan, result: BuildResult, kind: str) -> None:
    sw.set_rebuild_suppressed(True)
    try:
        for op in plan.ops[1:]:
            runner = _RUNNERS.get(type(op))
            if runner is None:  # ManualStep, Rebuild, SaveAs: counted or done around the loop
                continue
            try:
                if runner is _place:
                    result.done.append(_place(sw, op, result, result.trig, kind))
                else:
                    result.done.append(runner(sw, op, result, result.trig))
            except SolidWorksError as exc:
                label = base.describe(op, result.trig)
                result.failures.append((label, str(exc)))
                result.stopped_at = label
                return
    finally:
        sw.set_rebuild_suppressed(False)


def _verify(sw: SolidWorks, plan: BuildPlan, result: BuildResult) -> None:
    """Every global's value against the maths, and every sketch's definition."""
    if not result.ok:
        return
    try:
        expected = plan.values(result.trig)
    except EquationError as exc:
        result.failures.append(("the maths", str(exc)))
        return
    got = sw.equation_values()
    for name, value in expected.items():
        if name not in got:
            result.failures.append((f"\"{name}\"", "is not in the Equation Manager after the rebuild."))
        elif abs(got[name] - value) > VALUE_TOLERANCE * max(1.0, abs(value)):
            result.failures.append((f"\"{name}\"", f"SolidWorks has {got[name]!r} where the maths says {value!r}."))
    if expected and result.ok:
        result.done.append(f"{len(expected)} globals read back and match the maths")
    for op in plan.ops:
        if isinstance(op, base.CloseSketch):
            status = sw.sketch_status(op.name)
            if status != FULLY_DEFINED:
                word = {2: "under-defined", 4: "over-defined"}.get(status, f"in state {status}")
                result.checks.append(f"{op.name} is {word}, not fully defined")
            else:
                result.done.append(f"{op.name} is fully defined")


def build_pair(sw: SolidWorks, gear_a: BuildPlan, gear_b: BuildPlan, assembly: BuildPlan,
               exists: Callable[[str], bool] = os.path.exists) -> PairResult:
    """Both parts, then the assembly — skipped if either part failed — then whether the teeth interfere.

    An assembly that built cleanly is checked for interference (probe
    interference): none is a line in ``done``, and any is a ``CHECK`` with the
    count and volume, which does not fail the build — the parts are still the
    gears asked for, and the sentence says where to look.
    """
    for plan in (gear_a, gear_b, assembly):
        save = next((op for op in plan.ops if isinstance(op, base.SaveAs)), None)
        if save is not None and save.path and exists(save.path):
            raise BuildError(f"{save.path} already exists, and a build never overwrites a file.")
    # Before the gears, not after them at the assembly: a bad PAIR_ASSEMBLY_REBUILD_ROUTE would otherwise leave two
    # saved gears behind, which the next Build refuses to overwrite. It never refuses while that finding is absent.
    _assembly_rebuild_gate(ASSEMBLY_PAIR)
    pair = PairResult(gear_a=build(sw, gear_a, exists))
    if not pair.gear_a.ok:
        pair.skipped = "the second gear and the assembly, because the first gear failed"
        return pair
    pair.gear_b = build(sw, gear_b, exists)
    if not pair.gear_b.ok:
        pair.skipped = "the assembly, because the second gear failed"
        return pair
    # A pair for every rebuild and put, whatever the plan holds (a crossed pair placed fixed has no mate): the full
    # rebuild every pair result on record ran (probe tiers 4 and 5), never the workbook train's route.
    pair.assembly = build(sw, assembly, exists, kind=ASSEMBLY_PAIR)
    if pair.assembly.ok and findings.INTERFERENCE_CHECKED:
        try:
            count, volume = sw.interference_count()
        except SolidWorksError as exc:
            pair.assembly.checks.append(f"interference could not be checked: {exc}")
        else:
            if count:
                pair.assembly.checks.append(
                    f"the gears interfere in {count} place{'s' if count != 1 else ''}, {volume:.3f} mm³; "
                    "look along the gear axis at the mesh")
            else:
                pair.assembly.done.append("no interference between the gears")
    return pair


@dataclass
class ManyResult:
    """A batch of parts (a workbook's, phase W2): each one's result in order, and what was not reached."""

    built: List[BuildResult] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)      # paths not attempted, after a failure

    @property
    def ok(self) -> bool:
        return bool(self.built) and all(r.ok for r in self.built) and not self.skipped

    def log_lines(self) -> List[str]:
        lines: List[str] = []
        for result in self.built:
            lines.extend(result.log_lines())
        if self.skipped:
            lines.append(f"SKIPPED {len(self.skipped)} part(s) after a failure: "
                         + ", ".join(os.path.basename(p) for p in self.skipped))
        return lines


def build_many(sw: SolidWorks, plans: Sequence[BuildPlan],
               exists: Callable[[str], bool] = os.path.exists, *,
               progress: "Optional[Callable[[Step], None]]" = None,
               into: Optional[ManyResult] = None) -> ManyResult:
    """Every plan's part in order, each by :func:`build`; the first that fails stops the rest.

    Every path is checked before anything is made, so a batch either starts
    with nothing in the way or does not start: a build never overwrites a file
    (``findings.SAVE_AS_OVERWRITES`` is True, so this check is the only guard).
    ``progress``, if given, is told ``Step(STAGE_PART, stem, i, n)`` as each
    part starts.

    ``into`` is for a job that has done its own checks first
    (:func:`build_gearbox`): each part's result is put in it as soon as it is
    known, so whatever raises later loses none of the parts already saved,
    and the first part too goes through :func:`_build_in_job`, which never
    raises. Without it, W2's batch, the first part's :class:`BuildError`
    (nothing made) still raises.
    """
    paths = []
    for plan in plans:
        save = next((op for op in plan.ops if isinstance(op, base.SaveAs)), None)
        path = save.path if save is not None else ""
        if path and exists(path):
            raise BuildError(f"{path} already exists, and a build never overwrites a file.")
        if path and any(same_path(path, p) for p in paths):
            raise BuildError(f"Two parts in this batch would both be saved as {path}.")
        paths.append(path)
    many = into if into is not None else ManyResult()
    for index, plan in enumerate(plans):
        if progress is not None:
            progress(Step(STAGE_PART, _stem(paths[index] or plan.path), index + 1, len(plans)))
        in_job = into is not None or bool(many.built)
        result = _build_in_job(sw, plan, exists) if in_job else build(sw, plan, exists)
        many.built.append(result)
        if not (result.ok and result.saved):
            many.skipped = [p for p in paths[index + 1:]]
            break
    return many


# -- changing values in a built part ----------------------------------------


STRUCTURAL = ("kind", "recipe", "hand", "teeth_side")


def structural_change(built: Mapping[str, str], wanted: Mapping[str, str]) -> str:
    """Why a change cannot go through the equations, as a sentence; empty when it can.

    The sketch's topology is fixed when it is built: another recipe or kind is
    different entities, and a bore that appears or vanishes is a feature that
    is not there.
    """
    for key in STRUCTURAL:
        # A record written before a key existed held its default: external teeth.
        default = "external" if key == "teeth_side" else ""
        if str(built.get(key, default) or default) != str(wanted.get(key, default) or default):
            return (f"The {key} changed from {built.get(key)!r} to {wanted.get(key)!r}; "
                    "build it again as a new part.")

    def has_bore(values: Mapping[str, str]) -> bool:
        text = str(values.get("bore", "")).strip()
        try:
            return bool(text) and float(text) > 0
        except ValueError:
            return False

    if has_bore(built) != has_bore(wanted):
        return ("A bore cannot be added to or removed from a built part through its values; "
                "build it again as a new part.")

    def has_shift(values: Mapping[str, str]) -> bool:
        text = str(values.get("profile_shift", "")).strip()
        try:
            return bool(text) and float(text) != 0
        except ValueError:
            return False

    # An unshifted part has no "Profile Shift" global for a new value to go into.
    if has_shift(built) != has_shift(wanted):
        return ("Profile shift cannot be added to or taken out of a built part through its values; "
                "build it again as a new part.")

    def has_groove(values: Mapping[str, str]) -> bool:
        text = str(values.get("groove", "")).strip()
        try:
            return bool(text) and float(text) != 0
        except ValueError:
            return False

    # A groove is a hub feature and a shorter blank: features, not values.
    if has_groove(built) != has_groove(wanted):
        return ("A centre groove cannot be added to or taken out of a built part through its values; "
                "build it again as a new part.")
    return ""


def planned_changes(current: Sequence[Tuple[str, float]], variables: Sequence[GlobalVariable],
                    trig: str) -> List[Tuple[str, str]]:
    """The globals whose text differs from what the part holds, as (name, expression)."""
    held: Dict[str, str] = {}
    for text, _ in current:
        try:
            name, expression = split_equation(text)
        except (ValueError, EquationError):
            continue
        held[name] = expression
    out = []
    for variable in variables:
        expression = variable.expression_for(trig)
        if variable.name not in held:
            raise BuildError(f"\"{variable.name}\" is not in this part, so it was not built by this tool "
                             "or its equations were edited.")
        if _squash(held[variable.name]) != _squash(expression):
            out.append((variable.name, expression))
    return out


def _squash(text: str) -> str:
    return "".join(text.split())


def update_variables(sw: SolidWorks, variables: Sequence[GlobalVariable], expected_path: str) -> UpdateResult:
    """Set a built part's globals from the form, in one suppressed batch, and rebuild once.

    Refuses unless the active document is the part the record describes: a
    wrong document would take the values silently where names happened to match.
    """
    _gate(sw)
    active = sw.active_document()
    if active is None:
        raise BuildError("No document is open in SolidWorks; open the gear's part first.")
    if not active.path or not same_path(active.path, expected_path):
        raise BuildError(f"The active document is {active.title}, not {os.path.basename(expected_path)}; "
                         "open the gear's part and try again.")
    result = UpdateResult(document=active.title)
    sw.begin_build()
    try:
        result.trig = sw.detect_trig_units()
        changes = planned_changes(sw.equations(), variables, result.trig)
        names = {name for name, _ in changes}
        result.unchanged = [v.name for v in variables if v.name not in names]
        try:
            evaluate_all([(v.name, v.expression_for(result.trig)) for v in variables], result.trig)
        except EquationError as exc:
            raise BuildError(f"The new values do not evaluate: {exc}") from None
        if not changes:
            return result
        sw.set_rebuild_suppressed(True)
        try:
            for name, expression in changes:
                try:
                    sw.set_global_variable(name, expression)
                    result.changed.append(name)
                except Exception as exc:  # noqa: BLE001 - what was set stays listed in ``changed`` (B1)
                    result.failures.append((f"\"{name}\"", _said(exc)))
        finally:
            sw.set_rebuild_suppressed(False)
        result.rebuilt = bool(sw.rebuild())
    finally:
        sw.end_build()
    return result


# -- a workbook's gearbox: parts, layout part and static assembly (phase W4) ---------
#
# docs/PLAN-WORKBOOK.md §4.2–§4.5. The shapes were pinned in one interface commit before the work was split;
# the worker's side is here, from probe tier 7. Planning is pure and runs on the Tk thread (workbook.gearbox,
# workbook.update); everything here that takes ``sw`` runs on the worker thread, as one job, and is given plain
# data — never a workbook type — so swbuild stays below the workbook package.

POSE_TOLERANCE = 1e-6        # mm for an origin, and per matrix entry (≈ radians) for a rotation

# What the worker is doing, for the footer (ui_text turns a Step into its sentence).
STAGE_CHECK = "check"                 # opening a document already built and checking it holds what is expected
STAGE_PART = "part"                   # building part ``index`` of ``count``
STAGE_LAYOUT = "layout"               # building the layout part
STAGE_ASSEMBLY = "assembly"           # building the assembly
STAGE_INTERFERENCE = "interference"   # checking the assembly for interference
STAGE_VALUES = "values"               # Update: setting a part's or the layout's globals
STAGE_PLACE = "place"                 # Update: re-placing components in the assembly
STAGES = (STAGE_CHECK, STAGE_PART, STAGE_LAYOUT, STAGE_ASSEMBLY, STAGE_INTERFERENCE, STAGE_VALUES, STAGE_PLACE)


@dataclass(frozen=True)
class Step:
    """One thing the worker has started. ``name`` is the document's file stem (``Gear_m1.5_N68``), or ``""``;
    ``index`` counts from 1 among ``count`` for STAGE_PART and STAGE_CHECK, and is 0 otherwise."""

    stage: str
    name: str = ""
    index: int = 0
    count: int = 0


class Progress:
    """The last :class:`Step` a worker job said, for the Tk thread's poll to read.

    One attribute, replaced whole by the worker and only read by Tk, so no
    lock is needed under the GIL. Make one per job and pass its ``say`` to
    :func:`build_gearbox` or :func:`update_gearbox`; never share one as a
    default argument (it would outlive the job and leak its last step into
    the next).
    """

    def __init__(self) -> None:
        self.step: Optional[Step] = None

    def say(self, step: Step) -> None:
        self.step = step


@dataclass(frozen=True)
class DocumentValues:
    """A saved document and the globals it should hold, in a workbook build or update.

    In :func:`build_gearbox` (a reused part or layout) it must already hold
    every one exactly — ``planned_changes(sw.equations(), variables, trig) ==
    []`` in the document's own trig units — and every name in ``features``
    (a reused layout's planes and axes); otherwise nothing is built. In
    :func:`update_gearbox` the variables are what it is to hold afterwards,
    and only those that differ are set. ``path`` is the absolute Windows path.
    """

    path: str
    variables: Tuple[GlobalVariable, ...] = ()
    features: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Placement:
    """Where one gear's component belongs in a built assembly: the rotation's 9 numbers by rows and its origin
    in mm (as :class:`gears.base.Place`), found by the ``Name2`` recorded at insertion. ``pitch`` is the gear's
    angular pitch in degrees (360 / teeth): a frame turned a whole number of pitches about the part's own axis
    is the same placement (:func:`same_frame`). 0 compares exactly."""

    gear: str
    component: str
    rotation: Tuple[float, ...]
    at: Tuple[float, float, float]
    pitch: float = 0.0


@dataclass(frozen=True)
class Clash:
    """One clash in an assembly: every interference SolidWorks found between the same components, merged
    (:func:`_clashes`). ``components`` are the ``Name2``s SolidWorks gave (``()`` when the names
    could not be read, ``findings.INTERFERENCE_NAMES_ROUTE``); ``gears`` the workbook's gear ids for them, in
    the same order, where the caller's map knows them (else the Name2 itself). ``volume`` in mm³."""

    components: Tuple[str, ...]
    gears: Tuple[str, ...]
    volume: float


def turn_between(rotation_a: Sequence[float], rotation_b: Sequence[float],
                 tolerance: float = POSE_TOLERANCE) -> Optional[float]:
    """The turn about frame a's own Z (its gear axis) that takes rotation a to rotation b, in radians in (−π, π]
    — positive the right-handed way about a's own +Z — or None when the two differ otherwise (a tilt, a gear
    turned over): ``M = Raᵀ·Rb`` must be a turn about local Z to ``tolerance`` per entry. Rotations are 9 numbers
    by rows, ``v_global = R · v_local + at``, as everywhere here. Pure (W5; :func:`same_frame` and
    :func:`train_check` both rest on it)."""
    ra = [[float(rotation_a[i * 3 + j]) for j in range(3)] for i in range(3)]
    rb = [[float(rotation_b[i * 3 + j]) for j in range(3)] for i in range(3)]
    # M = Ra^T Rb: the turn, in a's own frame, that takes a to b. It must be a turn about local Z.
    m = [[sum(ra[k][i] * rb[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    turn = math.atan2(m[1][0], m[0][0])
    c, s = math.cos(turn), math.sin(turn)
    about_z = ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
    if any(abs(m[i][j] - about_z[i][j]) > tolerance for i in range(3) for j in range(3)):
        return None
    return turn


def same_frame(rotation_a: Sequence[float], at_a: Sequence[float], rotation_b: Sequence[float],
               at_b: Sequence[float], pitch: float = 0.0, tolerance: float = POSE_TOLERANCE) -> bool:
    """Whether two component frames place the same gear the same way.

    The origins must agree to ``tolerance`` mm on each axis. The rotations
    must differ only by a turn about the part's own Z (its gear axis) of a
    whole number of ``pitch`` degrees — a gear turned one tooth is the same
    gear in the same place (review 14: comparing θ itself would call
    2.5e-14 and one whole pitch different). ``pitch`` 0 asks for the same
    rotation. Rotations are 9 numbers by rows, ``v_global = R · v_local + at``.
    The turn is :func:`turn_between`'s.
    """
    if any(abs(float(a) - float(b)) > tolerance for a, b in zip(at_a, at_b)):
        return False
    turn = turn_between(rotation_a, rotation_b, tolerance)
    if turn is None:
        return False
    if pitch <= 0:
        return abs(turn) <= tolerance
    step = math.radians(pitch)
    off = turn % step
    return min(off, step - off) <= tolerance


# -- W5: whether a mated train stands as built, up to a turn (W5-PLAN §1.6, review M1/M2) -----------------------

TRAIN_TOLERANCE = 1e-5     # radians on each relation; the demonstration logs the residuals it sees (W5-PLAN §4)


@dataclass(frozen=True)
class MeshLink:
    """One listed, gear-mated mesh (a, b) as :func:`train_check` reads it: b turns ``k`` times a's turn, each
    about its OWN part's +Z (review M2: ``k == ω_b/ω_a`` with ``kinematics.solve``'s speeds, which are about each
    shaft's own axis; ``workbook.motion.mesh_links`` makes them), and ``pitch`` is b's angular pitch in degrees
    (360 / b's teeth): the relation holds modulo it, since a whole tooth of a times k is a whole tooth of b."""

    a: str
    b: str
    k: float
    pitch: float


@dataclass(frozen=True)
class LockLink:
    """One lock mate: ``follower`` is held to ``anchor``. :func:`train_check` tests it EXACTLY (review M1: the
    follower's turn equals the anchor's, to tolerance, never modulo a pitch); ``pitch`` is the follower's angular
    pitch in degrees, kept for the log and for W8, and not used by the test."""

    anchor: str
    follower: str
    pitch: float


@dataclass(frozen=True)
class TrainCheck:
    """What :func:`train_check` found. ``off_axis``: gears not at their place or not along their axis (or not
    found at all), in ``wanted``'s order; their relations are not judged. ``out_of_step``: (a, b) meshes and
    (anchor, follower) locks whose relation does not hold, in the order given (meshes first). ``turned``: in step,
    and some gear stands turned other than by a whole number of its own pitch. ``residuals``: every relation
    judged, (a, b, residual in radians) — a mesh's distance from the nearest whole pitch of b, a lock's from no
    difference at all — meshes then locks, for the log (the demonstration reports what a real drag leaves)."""

    off_axis: Tuple[str, ...] = ()
    out_of_step: Tuple[Tuple[str, str], ...] = ()
    turned: bool = False
    residuals: Tuple[Tuple[str, str, float], ...] = ()

    @property
    def in_step(self) -> bool:
        return not (self.off_axis or self.out_of_step)


Frame9 = Tuple[Sequence[float], Sequence[float]]     # (rotation, 9 numbers by rows; origin in mm)


def _wrapped(angle: float) -> float:
    """``angle`` (radians) brought into (−π, π]."""
    out = math.remainder(angle, 2 * math.pi)
    return math.pi if out == -math.pi else out


def _off_whole(angle: float, step: float) -> float:
    """How far ``angle`` is from the nearest whole multiple of ``step`` (radians; ``step`` ≤ 0: of a full turn)."""
    if step <= 0:
        return abs(_wrapped(angle))
    off = angle % step
    return min(off, step - off)


def train_check(found: Mapping[str, Frame9], wanted: Mapping[str, Frame9], meshes: Sequence[MeshLink],
                locks: Sequence[LockLink], pitch: Mapping[str, float],
                tolerance: float = TRAIN_TOLERANCE) -> TrainCheck:
    """Whether the gears ``found`` stand as ``wanted`` does, up to a turn of each train and whole teeth (pure).

    ``found`` and ``wanted`` map a gear id to its frame (rotation 9 numbers
    by rows, origin in mm). Per gear of ``wanted``: missing from ``found``,
    an origin off by more than :data:`POSE_TOLERANCE` mm on any axis, or a
    rotation that is not ``wanted``'s turned about its own Z
    (:func:`turn_between`) is off its axis. Otherwise δ is its turn from
    wanted to found about its own +Z. Per mesh, ``δb − k·δa`` must be a whole
    number of b's pitch, to ``tolerance`` radians; per lock, ``δf − δa`` must
    be 0 (modulo a full turn), to ``tolerance`` — exactly, not modulo a pitch
    (review M1: a lock left a whole anchor tooth off is out of step). A
    relation with an off-axis gear is not judged. ``turned``: in step, and
    some gear's δ is not a whole number of its ``pitch`` (degrees; missing or
    0: any turn at all). Gears of ``found`` not in ``wanted`` are ignored.
    """
    off_axis: List[str] = []
    delta: Dict[str, float] = {}
    for gear, (rotation_w, at_w) in wanted.items():
        frame = found.get(gear)
        if frame is None:
            off_axis.append(gear)
            continue
        rotation_f, at_f = frame
        if any(abs(float(a) - float(b)) > POSE_TOLERANCE for a, b in zip(at_w, at_f)):
            off_axis.append(gear)
            continue
        turn = turn_between(rotation_w, rotation_f)
        if turn is None:
            off_axis.append(gear)
            continue
        delta[gear] = turn
    out: List[Tuple[str, str]] = []
    residuals: List[Tuple[str, str, float]] = []
    for mesh in meshes:
        if mesh.a in delta and mesh.b in delta:
            residual = _off_whole(delta[mesh.b] - mesh.k * delta[mesh.a], math.radians(mesh.pitch))
            residuals.append((mesh.a, mesh.b, residual))
            if residual > tolerance:
                out.append((mesh.a, mesh.b))
    for lock in locks:
        if lock.anchor in delta and lock.follower in delta:
            residual = abs(_wrapped(delta[lock.follower] - delta[lock.anchor]))
            residuals.append((lock.anchor, lock.follower, residual))
            if residual > tolerance:
                out.append((lock.anchor, lock.follower))
    in_step = not (off_axis or out)
    turned = in_step and any(_off_whole(turn, math.radians(pitch.get(gear, 0.0) or 0.0)) > tolerance
                             for gear, turn in delta.items())
    return TrainCheck(tuple(off_axis), tuple(out), turned, tuple(residuals))


@dataclass(frozen=True)
class MateRef:
    """A mate on record, as Update needs it: its name in SolidWorks' tree, its kind (``workbook.motion`` AXIS,
    ALONG, LOCK or MESH, the strings ``"axis"``, ``"along"``, ``"lock"``, ``"mesh"``), its gears by id (AXIS/ALONG
    ``(gear,)``; LOCK ``(anchor, follower)``; MESH ``(a, b)`` in the order the gear mate was made, its first
    selection first) and, for AXIS/ALONG, its shaft. ``store.MateEntry`` without the numbers."""

    name: str
    kind: str
    gears: Tuple[str, ...]
    shaft: str = ""


@dataclass(frozen=True)
class MotionUpdate:
    """What Update SolidWorks is given for a gearbox built to turn (``workbook.update.classify``, Agent B; the
    worker's motion path, Agent A). None in ``update_gearbox``'s ``motion`` is W4's static path, untouched.

    ``mates``: every mate on record. ``meshes``: a :class:`MeshLink` per
    recorded MESH mate with the tooth counts now wanted, in its recorded gear
    order. ``locks``: a :class:`LockLink` per recorded LOCK mate.
    ``recorded``: the frames on record (what was last put), one
    ``Placement`` per gear of the assembly, its ``pitch`` from the teeth AS
    BUILT (as ``recorded_meshes``); the frames now wanted, with the pitch
    now wanted, are ``update_gearbox``'s ``placements``.
    ``recorded_meshes``: as ``meshes``, with the tooth counts the gear mates
    hold now (the record's MESH ratios). ``face_globals``: ``(gear, its
    "<Gear> Face Z" global as now wanted)`` for every recorded ALONG mate
    with a face global, its expression the literal |z_front| in mm
    (``workbook.motion.face_global`` names it); the worker sets only those
    the assembly holds differently. ``ratios``: ``(gear mate name, numerator,
    denominator)`` for every MESH whose (za, zb) changed, in the mate's own
    gear order (review M10) — always empty while
    ``findings.GEAR_MATE_RATIO_ROUTE`` is not ``"remake"`` (W5-DECISIONS: a
    tooth change is then structural). ``fixed``: gears left fixed (on a
    fixed shaft, or held still by one: W5-PLAN D9, review M9), which Update
    re-places as W4 does, modulo pitch, with
    ``findings.REPLACE_FIXED_ROUTE``.
    """

    mates: Tuple[MateRef, ...] = ()
    meshes: Tuple[MeshLink, ...] = ()
    locks: Tuple[LockLink, ...] = ()
    recorded: Tuple["Placement", ...] = ()
    recorded_meshes: Tuple[MeshLink, ...] = ()
    face_globals: Tuple[Tuple[str, GlobalVariable], ...] = ()
    ratios: Tuple[Tuple[str, int, int], ...] = ()
    fixed: Tuple[str, ...] = ()


def same_named_elsewhere(documents: Sequence[DocInfo], paths: Sequence[str]) -> List[Tuple[str, str]]:
    """``(open document's path, wanted path)`` for every open document with the same file name as a path this
    job will build, open or insert, but in another folder (decision 7: SolidWorks keys open documents by file
    name, so it would answer with the wrong one). Unsaved documents are not compared. Pure."""
    def name(path: str) -> str:
        return os.path.basename(path.replace("\\", "/")).lower()

    out: List[Tuple[str, str]] = []
    for doc in documents:
        if not doc.path:
            continue
        for wanted in paths:
            if wanted and name(doc.path) == name(wanted) and not same_path(doc.path, wanted):
                out.append((doc.path, wanted))
    return out


def _quiet(_step: Step) -> None:
    """The progress callback when the caller gave none."""


def _stem(path: str) -> str:
    """A path's file stem (``Gear_m1.5_N68``), the only name a :class:`Step` carries."""
    return os.path.splitext(os.path.basename(str(path).replace("\\", "/")))[0]


def _file(path: str) -> str:
    return os.path.basename(str(path).replace("\\", "/"))


def _saved_path(plan: BuildPlan) -> str:
    save = next((op for op in plan.ops if isinstance(op, base.SaveAs)), None)
    return save.path if save is not None and save.path else plan.path


def _clash_line(clash: Clash) -> str:
    """``G1 and G2 interfere, 12.345 mm³; look where they meet``, or the volume alone when nothing was named.

    Not "their mesh": two gears on one shaft can clash too (on SolidWorks 2026, gearbox_smoke 2026-11-13, a
    gear widened by Update ran into its neighbour on the same shaft)."""
    names = list(clash.gears or clash.components)
    if not names:
        return (f"an interference of {clash.volume:.3f} mm³ between components SolidWorks did not name; "
                "look at each mesh")
    if len(names) == 1:
        return f"{names[0]} interferes, {clash.volume:.3f} mm³; look where it meets the others"
    listed = ", ".join(names[:-1]) + f" and {names[-1]}"
    return f"{listed} interfere, {clash.volume:.3f} mm³; look where they meet"


def _clashes(found: Sequence[Tuple[Sequence[str], float]], gear_of: Mapping[str, str]) -> List[Clash]:
    """``interferences()`` as :class:`Clash`es, each Name2 mapped to its gear id where the map knows it.

    SolidWorks gives one interference per region of contact: on 2026 (34.0.0,
    gearbox_smoke 2026-11-13) a 24-tooth gear turned half a pitch against a
    16-tooth one gave three, each between the same two components. Those are
    one clash to a reader, so interferences between the same components are
    merged, in the order first met, their volumes summed. Unnamed ones are
    kept apart: nothing says they are the same pair.
    """
    merged: Dict[object, Clash] = {}
    for index, (names, volume) in enumerate(found):
        names = tuple(names)
        key: object = frozenset(names) if names else index
        if key in merged:
            earlier = merged[key]
            merged[key] = Clash(earlier.components, earlier.gears, earlier.volume + float(volume))
        else:
            merged[key] = Clash(names, tuple(gear_of.get(n, n) for n in names), float(volume))
    return list(merged.values())


def _interference_lines(clashes: Sequence[Clash], error: str, ran: bool) -> List[str]:
    if error:
        return [f"CHECK   interference could not be checked: {error}"]
    if not ran:
        return []
    if not clashes:
        return ["ok      no interference between the gears"]
    return [f"CHECK   {_clash_line(c)}" for c in clashes]


def _held(current: Sequence[Tuple[str, float]]) -> Dict[str, str]:
    held: Dict[str, str] = {}
    for text, _ in current:
        try:
            name, expression = split_equation(text)
        except (ValueError, EquationError):
            continue
        held[name] = expression
    return held


def _read_live(sw: SolidWorks, doc: DocumentValues, verb: str,
               after_open: Optional[Callable[[str], None]] = None) -> Tuple[List[Tuple[str, float]],
                                                                            Dict[str, List[Tuple[str, str]]],
                                                                            Dict[str, float]]:
    """Open a saved document and read what it holds, writing nothing: its equations, the planned changes
    (``planned_changes``) in each trig unit, ``{DEGREES: […], RADIANS: […]}``, and the values SolidWorks
    evaluates its equations to (``equation_values``), for :func:`_held_unit`. ``after_open`` is told the path
    as soon as the document is open and still the build document (:func:`_note_opened`).

    ``open_document`` (which also refuses a same-named document from another
    folder), then ``planned_changes`` — which raises when a global is missing
    — and every name in ``doc.features`` looked for. Every refusal is a
    :class:`BuildError` naming the file, worded "<file> cannot be <verb>: …".

    Nothing here measures the trig units. ``detect_trig_units`` adds and
    deletes an equation, and on SolidWorks 2026 (34.0.0, gearbox_smoke
    2026-11-13) that alone left each document marked modified, where opening
    it, reading its equations and walking its features did not. So the
    units are read from the text: a document that holds the degree form or
    the radian form of every global holds what is asked, in those units —
    provided SolidWorks also evaluates them as that unit would (see
    :func:`_held_unit`).
    """
    name = _file(doc.path)
    sw.begin_build()
    try:
        try:
            sw.open_document(doc.path)
            if after_open is not None:
                after_open(doc.path)
            current = sw.equations()
        except BuildError as exc:
            raise BuildError(f"{name} cannot be {verb}: {exc}") from None
        except SolidWorksError as exc:
            raise BuildError(str(exc)) from None
        try:
            by_unit = {t: planned_changes(current, doc.variables, t) for t in (DEGREES, RADIANS)}
        except BuildError as exc:            # a global it should hold is not in it: not the document on record
            raise NotAsBuilt(f"{name} cannot be {verb}: {exc}", doc.path) from None
        if doc.features:
            try:
                present = set(sw.feature_names())
            except SolidWorksError as exc:
                raise BuildError(f"{name} cannot be {verb}: its features could not be read: {exc}") from None
            lost = [f for f in doc.features if f not in present]
            if lost:
                listed = ", ".join(f'"{f}"' for f in lost)
                raise NotAsBuilt(f"{name} cannot be {verb}: {listed} {'is' if len(lost) == 1 else 'are'} no "
                                 "longer in it; it was renamed or deleted in SolidWorks.", doc.path)
        try:
            values = dict(sw.equation_values())
        except SolidWorksError as exc:
            raise BuildError(f"{name} cannot be {verb}: its equations' values could not be read: {exc}") from None
        return current, by_unit, values
    finally:
        sw.end_build()


def _values_off(values: Mapping[str, float], variables: Sequence[GlobalVariable],
                trig: str) -> Optional[Tuple[str, float, float]]:
    """The first global whose value SolidWorks evaluates (``values``) differs from what ``variables`` give in
    ``trig``, as (name, SolidWorks' value, the expected value); None when every one agrees (to the build's own
    tolerance, :data:`VALUE_TOLERANCE`), or when the expected values cannot be worked out here — then the text
    alone decides, as before."""
    try:
        expected = evaluate_all([(v.name, v.expression_for(trig)) for v in variables], trig)
    except EquationError:
        return None
    for variable in variables:
        want, got = expected.get(variable.name), values.get(variable.name)
        if want is None or got is None:
            continue
        if abs(float(got) - want) > VALUE_TOLERANCE * max(1.0, abs(want)):
            return variable.name, float(got), want
    return None


def _held_unit(by_unit: Mapping[str, Sequence[Tuple[str, str]]], values: Optional[Mapping[str, float]] = None,
               variables: Sequence[GlobalVariable] = ()) -> str:
    """The trig unit in which a document already holds every global as asked (degrees first), or ``""``.

    The text decides which unit's form it holds; with ``values`` (what
    SolidWorks evaluates, ``equation_values``) that unit must also be the one
    SolidWorks evaluates in: the values ``variables`` give in it must be the
    values SolidWorks has (:func:`_values_off`). A document holding the
    degree form of ``"Pitch Diameter" * cos ( "Pressure Angle" )`` whose
    angle unit was later set to radians evaluates cos(20 rad): its text is
    right and its geometry is not, so it does not hold what is asked, and
    Update sets it (measuring the unit) rather than leave it (W4 review N5;
    before S2, Update measured the unit every time). A global with no trig
    has the same text and value in both units, so only trig globals can
    differ. The build's own read-back (:func:`_verify`) has compared
    ``equation_values`` with the maths on SolidWorks 2026 and 2024; this
    comparison on a reopened document has not yet run on real SolidWorks."""
    for trig in (DEGREES, RADIANS):
        if by_unit[trig]:
            continue
        if values is not None and _values_off(values, variables, trig) is not None:
            continue
        return trig
    return ""


def _check_live(sw: SolidWorks, doc: DocumentValues, verb: str,
                after_open: Optional[Callable[[str], None]] = None) -> str:
    """A document to be reused, opened and checked, writing nothing (:func:`_read_live`): it must hold every
    global exactly, in either trig unit, SolidWorks must evaluate them as that unit would (:func:`_held_unit`),
    and every feature named must be there; returns that unit. Otherwise a :class:`NotAsBuilt` saying what
    differs — the texts in the unit that differs less, or the first value when only the angle unit is wrong —
    (a :class:`BuildError` when it cannot be opened or read at all)."""
    current, by_unit, values = _read_live(sw, doc, verb, after_open)
    unit = _held_unit(by_unit, values, doc.variables)
    if unit:
        return unit
    written = next((t for t in (DEGREES, RADIANS) if not by_unit[t]), "")
    off = _values_off(values, doc.variables, written) if written else None
    if off is not None:
        name, got, want = off
        raise NotAsBuilt(f"{_file(doc.path)} does not hold what the workbook asks of it, so it cannot be {verb}: its "
                         f"equations are written for {written}, but SolidWorks evaluates them otherwise (\"{name}\" "
                         f"is {got:.6g} there and {want:.6g} here), so its angle unit was changed since they were "
                         "written.", doc.path)
    changes = min((by_unit[t] for t in (DEGREES, RADIANS)), key=len)
    held = _held(current)
    shown = "; ".join(f'"{n}" is {held.get(n, "?")} there and {e} here' for n, e in changes[:3])
    more = f"; and {len(changes) - 3} more" if len(changes) > 3 else ""
    raise NotAsBuilt(f"{_file(doc.path)} does not hold what the workbook asks of it, so it cannot be {verb}: "
                     f"{shown}{more}.", doc.path)


def _evaluates(sw: SolidWorks, doc: DocumentValues, verb: str) -> None:
    """The new values of a document Update will change, evaluated before anything changes. They are evaluated in
    both trig units, which needs nothing from SolidWorks; only when they evaluate in one unit and not the other is
    the document's own unit measured (``detect_trig_units``) — it is about to change anyway — to say which."""
    failed: Dict[str, EquationError] = {}
    for trig in (DEGREES, RADIANS):
        try:
            evaluate_all([(v.name, v.expression_for(trig)) for v in doc.variables], trig)
        except EquationError as exc:
            failed[trig] = exc
    if not failed:
        return
    if len(failed) == 1:
        sw.begin_build()
        try:
            sw.open_document(doc.path)
            trig = sw.detect_trig_units()
        except SolidWorksError as exc:
            raise BuildError(str(exc)) from None
        finally:
            sw.end_build()
        if trig not in failed:
            return
    else:
        trig = DEGREES
    raise BuildError(f"{_file(doc.path)} cannot be {verb}: the new values do not evaluate: {failed[trig]}")


def _refuse_paths(sw: SolidWorks, made: Sequence[str], opened: Sequence[str], verb_made: str,
                  verb_opened: str) -> List[str]:
    """The path checks of a job, each a :class:`BuildError` sentence naming the file: one path twice, two files
    of one name from two folders (SolidWorks keeps one document per file name: probe
    add_component_same_name_elsewhere), and a document of the same name already open from another folder
    (decision 7, :func:`same_named_elsewhere`). Returns the saved documents open in SolidWorks as the job
    begins (their paths), read once here for both."""
    everything = list(made) + list(opened)
    for index, path in enumerate(everything):
        for earlier in everything[:index]:
            if same_path(path, earlier):
                raise BuildError(f"{path} is named twice in this job, so one document would take the place of the "
                                 "other.")
            if _file(path).lower() == _file(earlier).lower():
                raise BuildError(f"{earlier} and {path} have the same file name, and SolidWorks keeps one document "
                                 "per file name, so they cannot both be in one job.")
    documents = sw.documents()
    clashes = same_named_elsewhere(documents, everything)
    if clashes:
        said = []
        for open_path, wanted in clashes:
            verb = verb_made if any(same_path(wanted, p) for p in made) else verb_opened
            said.append(f"{open_path} is open in SolidWorks, and it has the same file name as {wanted}, which this "
                        f"job would {verb}")
        files = [_file(p) for p, _ in clashes]
        listed = files[0] if len(files) == 1 else ", ".join(files[:-1]) + f" and {files[-1]}"
        raise BuildError(f"{'; '.join(said)}; SolidWorks keeps one document per file name, so close {listed} in "
                         "SolidWorks and try again.")
    return [d.path for d in documents if d.path]


def _from_disk(path: str, open_before: Optional[Sequence[str]]) -> bool:
    """Whether a document the job opens was not open in SolidWorks before it (``documents()`` at the pre-flight),
    so ``open_document`` loaded it from its file: what it holds in memory is then what the file holds. Never when
    what was open is not known (``open_before`` None)."""
    return open_before is not None and not any(same_path(path, p) for p in open_before)


def _note_opened(sw: SolidWorks, path: str, result: Union["GearboxResult", "GearboxUpdate"]) -> None:
    """Right after ``open_document(path)``: list ``path`` in ``result.opened`` — loaded from its file, so its
    unsaved marks may go — only when it was not open as the job began (:func:`_from_disk` on
    ``result.open_before``) and SolidWorks reads no unsaved changes in it (``has_unsaved_changes``,
    ``GetSaveFlag``). The second is the belt to the first's braces (third W4 review, item 1): a document holding
    changes not saved is never one whose mark may be cleared, whatever the list of open documents said — it was
    open before the job, so it joins ``result.open_before``, and the finishes never take it for one SolidWorks
    closed. A flag that cannot be read counts as changes."""
    if not _from_disk(path, result.open_before) or any(same_path(path, p) for p in result.opened):
        return
    try:
        unsaved = bool(sw.has_unsaved_changes())
    except SolidWorksError:
        unsaved = True
    if unsaved:
        result.open_before.append(path)
    else:
        result.opened.append(path)


@dataclass
class GearboxResult:
    """What :func:`build_gearbox` did, step by step; every part saved before a failure stays saved.

    ``checked``: documents already built (reused parts, then a reused
    layout), opened and found to hold what was expected, in order.
    ``layout`` is None when the layout was reused (``layout_reused`` is then
    its path) or not reached; ``assembly`` None when not reached or not
    planned (Build parts). ``components`` is the assembly's
    ``BuildResult.components`` (handle -> Name2, the layout's ``"layout"``
    included). ``clashes`` and ``interference_error`` are filled only after
    an assembly that built cleanly; a clash is a CHECK, not a failure.
    ``skipped`` says, as a phrase, what a failure left unattempted.
    ``parts.ok`` is False for an empty batch, so :attr:`ok` must not lean
    on it when every part was reused. ``failures`` are (what, why) for a
    raise that stopped the job between its documents (each document's own
    failures stay on its :class:`BuildResult`): after the pre-flight nothing
    escapes :func:`build_gearbox`, so what saved before it still reaches the
    finish (W4 review B1).

    ``mismatched`` are (path, why) for each document to reuse that the live
    check found not holding what it should (:class:`NotAsBuilt`); then
    nothing is made at all, and ``mtimes`` holds each such file's time as
    read at the check, so the finish can record it and the next plan make
    that part new instead of failing the same check on every press (W4
    review B2's last corner: an Update left unsaved, SolidWorks closed
    without saving, and the unchanged file saved later, so its time moved on
    while it still held the old values).

    ``held``: each document in ``checked`` and the trig unit the check found
    it holding its globals in, for the ``.gear.json`` the finish writes beside
    a part only the journal knew. ``open_before``: the saved documents open
    in SolidWorks when the job began (None when not read, as in a test's
    hand-made result), and ``opened`` the documents the job opened from disk
    — not open before it — whose state in memory is therefore their file's
    (second W4 review N2: the finish clears or re-decides their marks, and a
    document marked unsaved that was not open when the job began has lost
    its unsaved changes). That a document in memory is listed by
    ``documents()`` (``GetFirstDocument``/``GetNext``, walked to the end of
    the list) whether or not its window is open is what decision 7's
    same-name check already relies on; it has not yet been exercised for
    this on real SolidWorks. So a document is listed in ``opened`` only when
    ``GetSaveFlag`` also reads it holding no unsaved changes once opened
    (:func:`_note_opened`, third W4 review): one holding Update's changes is
    never counted as loaded from its file, and joins ``open_before``, since
    it was evidently open before the job.
    """

    parts: ManyResult = field(default_factory=ManyResult)
    checked: List[str] = field(default_factory=list)
    layout: Optional[BuildResult] = None
    layout_reused: str = ""
    assembly: Optional[BuildResult] = None
    components: Dict[str, str] = field(default_factory=dict)
    clashes: List[Clash] = field(default_factory=list)
    interference_error: str = ""
    skipped: str = ""
    failures: List[Tuple[str, str]] = field(default_factory=list)
    mismatched: List[Tuple[str, str]] = field(default_factory=list)
    mtimes: Dict[str, float] = field(default_factory=dict)
    held: Dict[str, str] = field(default_factory=dict)
    open_before: Optional[List[str]] = None
    opened: List[str] = field(default_factory=list)
    # W5: which assembly saved — GEARBOX_MOTION (its plan mates its gears: a train) or GEARBOX_STATIC (W4's fixed
    # one) — or "" when none did. A train SolidWorks refused or flagged a mate of is not saved, and nothing is
    # saved in its place (W5-DECISIONS, answer 1): ``assembly`` is then that failed BuildResult, its
    # ``mate_problems`` the sentences and its ``document`` the title it is left open under, and ``kind`` is "".
    kind: str = ""

    @property
    def ok(self) -> bool:
        """Every part planned was saved, the layout saved or reused (when planned), the assembly saved (when
        planned), and nothing stopped the job between them. Clashes do not count against it."""
        def saved(result: Optional[BuildResult]) -> bool:
            return result is None or (result.ok and bool(result.saved))

        return (all(saved(r) for r in self.parts.built) and not self.parts.skipped and saved(self.layout)
                and saved(self.assembly) and not self.skipped and not self.failures and not self.mismatched)

    def _interference_ran(self) -> bool:
        return (self.assembly is not None and self.assembly.ok and bool(self.assembly.saved)
                and bool(getattr(findings, "INTERFERENCE_CHECKED", False)))

    def log_lines(self) -> List[str]:
        """The parts' lines, the checked documents, the layout's, the assembly's, then ``ok      no interference
        between the gears`` or one ``CHECK`` per clash naming the gears, then ``SKIPPED …``."""
        lines = self.parts.log_lines()
        lines.extend(f"ok      checked {_file(p)}: it holds what the workbook asks, so it is reused"
                     for p in self.checked)
        lines.extend(f"FAIL    checked {_file(p)}: {why}" for p, why in self.mismatched)
        if self.layout is not None:
            lines.extend(self.layout.log_lines())
        elif self.layout_reused:
            lines.append(f"ok      layout {_file(self.layout_reused)} reused")
        if self.assembly is not None:
            lines.extend(self.assembly.log_lines())
        lines.extend(_interference_lines(self.clashes, self.interference_error, self._interference_ran()))
        lines.extend(f"FAIL    {what}: {why}" for what, why in self.failures)
        if self.skipped:
            lines.append(f"SKIPPED {self.skipped}")
        return lines


def build_gearbox(sw: SolidWorks, parts: Sequence[BuildPlan], reuse: Sequence[DocumentValues] = (),
                  layout: Union[BuildPlan, DocumentValues, None] = None, assembly: Optional[BuildPlan] = None,
                  gears: Optional[Mapping[str, str]] = None, *,
                  exists: Callable[[str], bool] = os.path.exists,
                  progress: Optional[Callable[[Step], None]] = None,
                  mtime: Callable[[str], float] = os.path.getmtime) -> GearboxResult:
    """A workbook's parts, its layout part and its static assembly, in one worker job (PLAN-WORKBOOK §4.2–§4.3).

    ``parts`` are the new parts' plans; ``reuse`` the parts already built and
    unchanged; ``layout`` a plan to build, a saved layout to reuse
    (:class:`DocumentValues` with its globals and its plane and axis names),
    or None with ``assembly`` None too (Build parts: W2's batch, now able to
    resume over parts already made); ``gears`` maps each assembly handle to
    its gear id, for naming clashes. Order, and what may stop it:

    1. **Before anything is made**, raise :class:`BuildError` (nothing made,
       nothing changed) if a new path exists or two are the same, a reused
       path is missing, a document of the same file name is open from another
       folder (:func:`same_named_elsewhere` over every path built, opened or
       inserted), or a reused document cannot be opened and read. Each
       reused document is opened with ``open_document`` and checked live
       (decision 3: ``planned_changes(...) == []`` and every ``features``
       name present); one that does not hold what is expected is not a
       raise but :attr:`GearboxResult.mismatched` — every one is checked,
       its file's time noted (``mtime``), and the result returned with
       nothing made, so the finish records it and the next plan makes it
       new.
    2. The new parts, by :func:`build_many`; a failure skips the rest.
    3. The layout: built (a failure skips the assembly), or the reused one
       left open from step 1.
    4. The assembly, by :func:`build`; then, if it built cleanly,
       ``sw.interferences()`` (a raise becomes ``interference_error``).

    ``progress`` is told each :class:`Step` as it starts. Nothing is closed;
    a failed document is left open, unsaved. Runs on the worker thread.

    Also refused in step 1, each with a sentence: a plan that is not sound;
    an assembly with no layout; an assembly that would insert a file this
    job neither makes nor reuses; two files of one name from two folders;
    and documents built earlier going into the assembly while
    ``findings.REUSE_ADD_ROUTE`` is neither "opened" nor "closed". With
    "opened" (probe add_component_opened_part, 2026: AddComponent5 refused a
    closed part and took one opened by OpenDoc6) the reused documents must be
    open when the assembly inserts them, and they are, from the live check;
    with "closed" they would not need to be, but the live check opens them
    anyway. A clash keeps :attr:`GearboxResult.ok` True (W4 agreement 9).

    On SolidWorks 2026 (34.0.0, probe/gearbox_smoke.py 2026-11-13) the live
    check left every reused document unmodified, but once inserted into the
    new assembly, rebuilt and saved, each part (and the layout) read
    ``GetSaveFlag`` True: SolidWorks' own doing, nothing of theirs on disk is
    stale, so it is not a reason to mark them unsaved. The cause was the
    assembly's full rebuild (``ForceRebuild3(False)``, in ``rebuild`` and in
    every ``place_component``), which probe assembly_rebuild_scope found
    marking every component modified on 2026 and 2024; the assembly is now
    rebuilt top-only (``swcom.rebuild_call``), which is enough because every
    part and the layout were built, rebuilt and saved in their own documents
    first, and a reused one is only read. Refused before anything is made: an
    assembly while ``findings.ASSEMBLY_REBUILD_ROUTE`` is not settled.

    W5 (Agent A; W5-INTERFACES.md): an assembly plan that mates its gears is
    a train (:func:`workbook_assembly_kind`) and its :func:`build` runs the
    mate check before the save. A train SolidWorks refuses or flags a mate of
    is left open, unsaved, and nothing is built in its place — no static
    fallback (W5-DECISIONS, answer 1, overruling W5-PLAN D2): the parts and
    the layout part already saved stay saved and reach the finish, which
    records them as W4's continued revision. :attr:`GearboxResult.kind` says
    which assembly saved. The signature is unchanged: no ``static=``.
    """
    say = progress or _quiet
    _gate(sw)
    gear_of_handle = dict(gears or {})
    layout_plan = layout if isinstance(layout, BuildPlan) else None
    layout_reuse = layout if isinstance(layout, DocumentValues) else None
    if assembly is not None and layout is None:
        raise BuildError("The assembly is built around its layout part, and this build has neither a layout part "
                         "to make nor one to reuse.")
    if assembly is not None:
        _assembly_rebuild_gate(workbook_assembly_kind(assembly))
    plans = list(parts) + [p for p in (layout_plan, assembly) if p is not None]
    for plan in plans:
        problems = plan.check()
        if problems:
            raise BuildError(f"The build plan for {_file(_saved_path(plan)) or plan.kind} is not sound: "
                             + " ".join(problems))
    made = [p for p in (_saved_path(plan) for plan in plans) if p]
    reused_docs = list(reuse) + ([layout_reuse] if layout_reuse is not None else [])
    reused = [d.path for d in reused_docs]
    for path in made:
        if exists(path):
            raise BuildError(f"{path} already exists, and a build never overwrites a file.")
    for path in reused:
        if not exists(path):
            raise BuildError(f"{path} is no longer there, so it cannot be reused: it was moved, renamed or deleted "
                             "since it was built.")
    open_before = _refuse_paths(sw, made, reused, "make", "reuse")
    inserted = [op.path for op in assembly.ops if isinstance(op, base.AddComponent)] if assembly is not None else []
    for path in inserted:
        if not any(same_path(path, p) for p in made + reused):
            raise BuildError(f"The assembly would insert {path}, which this build neither makes nor reuses.")
    reused_in_assembly = [p for p in reused if any(same_path(p, q) for q in inserted)]
    route = getattr(findings, "REUSE_ADD_ROUTE", None)
    if reused_in_assembly and route not in ("opened", "closed"):
        raise BuildError(f"Putting a document built earlier into a new assembly has not been settled on SolidWorks "
                         f"yet (findings.REUSE_ADD_ROUTE is {route!r}), so this build, which reuses "
                         f"{_file(reused_in_assembly[0])}, cannot start; run probe tier 7 first.")

    result = GearboxResult(open_before=list(open_before))
    for index, doc in enumerate(reused_docs, 1):
        say(Step(STAGE_CHECK, _stem(doc.path), index, len(reused_docs)))
        try:
            result.held[doc.path] = _check_live(sw, doc, "reused", lambda path: _note_opened(sw, path, result))
        except NotAsBuilt as exc:
            # Not a refusal: the finish records it, and the next plan makes that part new (review B2's last
            # corner). Every document is still checked, so one press finds them all.
            result.mismatched.append((doc.path, str(exc)))
            try:
                result.mtimes[doc.path] = float(mtime(doc.path))
            except (OSError, ValueError, TypeError):
                pass
            continue
        result.checked.append(doc.path)
    if result.mismatched:
        result.skipped = "everything, because a document to reuse does not hold what it should"
        return result

    # From here on documents are made and saved: nothing raises out (W4 review B1). Each document's own trouble
    # is a failure on its BuildResult (_build_in_job); anything else becomes a failure on the result, so what
    # SolidWorks already saved still reaches the finish and the record.
    stage = ["the parts" if parts else "the layout part" if layout_plan is not None else "the assembly"]
    try:
        _build_gearbox_body(sw, result, parts, layout_plan, layout_reuse, assembly, gear_of_handle, exists, say,
                            stage)
    except Exception as exc:  # noqa: BLE001 - see above
        if stage[0] == "the interference check":
            result.interference_error = _said(exc)        # a clash check that cannot run is a CHECK, not a failure
            return result
        result.failures.append((stage[0], _said(exc)))
        rest = {"the parts": [p for p, planned in (("the layout part", layout_plan is not None),
                                                    ("the assembly", assembly is not None)) if planned],
                "the layout part": ["the assembly"] if assembly is not None else [],
                }.get(stage[0], [])
        if rest and not result.skipped:
            result.skipped = f"{' and '.join(rest)}, because the job stopped during {stage[0]}"
    return result


def _build_gearbox_body(sw: SolidWorks, result: GearboxResult, parts: Sequence[BuildPlan],
                        layout_plan: Optional[BuildPlan], layout_reuse: Optional[DocumentValues],
                        assembly: Optional[BuildPlan], gear_of_handle: Mapping[str, str],
                        exists: Callable[[str], bool], say: Callable[[Step], None], stage: List[str]) -> None:
    """Steps 2–4 of :func:`build_gearbox`, filling ``result`` as each document finishes; ``stage[0]`` says which
    step is under way, for the failure if something raises."""
    later = [phrase for phrase, planned in (("the layout part", layout_plan is not None),
                                            ("the assembly", assembly is not None)) if planned]
    if parts:
        stage[0] = "the parts"
        build_many(sw, parts, exists, progress=say, into=result.parts)
        if not (all(r.ok and r.saved for r in result.parts.built) and not result.parts.skipped):
            if later:
                result.skipped = f"{' and '.join(later)}, because a part failed"
            return

    if layout_plan is not None:
        stage[0] = "the layout part"
        say(Step(STAGE_LAYOUT, _stem(_saved_path(layout_plan))))
        result.layout = _build_in_job(sw, layout_plan, exists)
        if not (result.layout.ok and result.layout.saved):
            if assembly is not None:
                result.skipped = "the assembly, because the layout part failed"
            return
    elif layout_reuse is not None:
        result.layout_reused = layout_reuse.path

    if assembly is None:
        return
    stage[0] = "the assembly"
    stem = _stem(_saved_path(assembly))
    say(Step(STAGE_ASSEMBLY, stem))
    # Its kind said explicitly: today's workbook gearbox is fixed (static, top-only); W5's mated one is a train, by
    # the same predicate the gate above used.
    result.assembly = _build_in_job(sw, assembly, exists, kind=workbook_assembly_kind(assembly))
    result.components = dict(result.assembly.components)
    if result.assembly.ok and result.assembly.saved and getattr(findings, "INTERFERENCE_CHECKED", False):
        stage[0] = "the interference check"
        say(Step(STAGE_INTERFERENCE, stem))
        gear_of = {name: gear_of_handle.get(handle, name) for handle, name in result.components.items()}
        try:
            result.clashes = _clashes(sw.interferences(), gear_of)
        except Exception as exc:  # noqa: BLE001 - a clash check that cannot run is a CHECK, never a failure
            result.interference_error = _said(exc)


REPLACE_ROUTES = ("Transform2 put", "UnfixComponent, Transform2 put, FixComponent")   # REPLACE_FIXED_ROUTE


@dataclass
class GearboxUpdate:
    """What :func:`update_gearbox` did. Nothing is saved: ``changed`` lists every document whose CONTENT it
    changed in SolidWorks — a part's or the layout's globals set, the assembly's components re-placed — and the
    record marks those unsaved until the app sees them saved (decision 3). A document SolidWorks marks modified
    only because it was rebuilt or read afterwards (frames, interference) is not in it: after a part-only Update the assembly is
    rebuilt (and so reads modified in SolidWorks) but holds nothing new, and listing it would tell a user who
    saved the part and closed the assembly unsaved that SolidWorks no longer holds this version. So what
    SolidWorks marks modified is ``changed`` and the assembly whenever ``rebuilt`` (it is then also read), as
    probe assembly_rebuild_scope saw.

    ``parts`` holds one result per part reached, in the order given;
    ``layout`` the layout's, if one was given and reached. ``found`` is each
    placed gear's live frame (rotation by rows, origin in mm) as read before
    anything moved — the finish compares it with the record to say a
    component the user dragged was put back. ``placed`` lists the gears
    re-placed because ``found`` differed from the wanted frame
    (:func:`same_frame`, modulo the gear's pitch). ``rebuilt`` is the
    assembly's one rebuild. ``failures`` are (what, why) in the order met.
    ``mtimes`` is each document's file time as read before the job changed
    anything (path -> ``os.path.getmtime``; a file whose time could not be
    read is left out): the finish marks a changed document unsaved at that
    time, so a save made in SolidWorks while the job was answering still
    reads as newer (W4 review nit). ``open_before`` and ``opened`` are as on
    :class:`GearboxResult`: the documents open when the job began, and those
    it opened from disk and found holding no unsaved changes (every part and
    the layout in the check phase, and the assembly when it was reached).
    """

    parts: List[UpdateResult] = field(default_factory=list)
    layout: Optional[UpdateResult] = None
    found: Dict[str, Tuple[Tuple[float, ...], Tuple[float, float, float]]] = field(default_factory=dict)
    placed: List[str] = field(default_factory=list)
    rebuilt: bool = False
    clashes: List[Clash] = field(default_factory=list)
    interference_error: str = ""
    failures: List[Tuple[str, str]] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    skipped: str = ""
    mtimes: Dict[str, float] = field(default_factory=dict)
    open_before: Optional[List[str]] = None
    opened: List[str] = field(default_factory=list)
    # W5, the motion path only (``update_gearbox(..., motion=...)``); all empty on W4's static path, and ``found``
    # and ``placed`` keep their W4 meanings on the motion path too (every gear's frame as read before anything moved;
    # every gear put, mated or fixed). Found before anything changed, against the record — ``train_check`` with both
    # maps restricted to the MATED gears (fixed ones are W4's business, never "missing" or off axis here):
    # ``turned``, ``out_of_step`` and ``off_axis`` as TrainCheck has them, and its ``residuals`` for the log.
    # ``restored``: one entry per train that was put (W5-PLAN D4 and review M1: when a train needs any put, every
    # mated gear of it is put), listing that train's gears, in ``placements`` order, whose check-phase δ was not a
    # whole number of their pitch — the gears the put turned back to the built turn; a train put with none turned
    # (a layout move alone) has no entry, and a train not put is never listed. ``unsuppressed``:
    # recorded mates found suppressed and turned back on (D10), by name. ``axial``: gears whose "<Gear> Face Z" was
    # set, in ``face_globals`` order. ``ratios``: gear mates given a new ratio, by name (empty while
    # ``findings.GEAR_MATE_RATIO_ROUTE`` is None). ``extra_mates``: mates in the assembly the record does not list,
    # found suppressed and left as they are (an unsuppressed one refuses the Update in its check phase instead:
    # review M7). ``mates``: every mate as read after the last rebuild.
    turned: bool = False
    out_of_step: List[Tuple[str, str]] = field(default_factory=list)
    off_axis: List[str] = field(default_factory=list)
    residuals: List[Tuple[str, str, float]] = field(default_factory=list)
    restored: List[Tuple[str, ...]] = field(default_factory=list)
    unsuppressed: List[str] = field(default_factory=list)
    axial: List[str] = field(default_factory=list)
    ratios: List[str] = field(default_factory=list)
    extra_mates: List[str] = field(default_factory=list)
    mates: List[MateState] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Nothing failed and nothing was left unattempted. Clashes, and an interference check that could not run,
        do not count against it (as in a build)."""
        return not self.failures and not self.skipped

    def log_lines(self) -> List[str]:
        """Each document's values, the re-placed gears, the assembly's rebuild, any failure, the interference,
        what was changed and not saved, then ``SKIPPED …``."""
        lines: List[str] = []
        for result in self.parts + ([self.layout] if self.layout is not None else []):
            lines.append(f"update  {result.document or '(no document)'} · trig {result.trig or '?'}")
            if result.changed:
                lines.append("ok      set " + ", ".join(f'"{n}"' for n in result.changed))
            elif not result.failures:
                lines.append("ok      already holds the workbook's values")
            if result.changed:
                lines.append("ok      rebuilt once" if result.rebuilt else "FAIL    the rebuild reported an error")
        if self.found:
            if self.placed:
                lines.append("ok      re-placed " + ", ".join(self.placed))
            else:
                lines.append("ok      every gear is where the workbook puts it")
        if self.rebuilt:
            lines.append("ok      assembly rebuilt once")
        lines.extend(f"FAIL    {what}: {why}" for what, why in self.failures)
        ran = self.rebuilt and not self.failures and bool(getattr(findings, "INTERFERENCE_CHECKED", False))
        lines.extend(_interference_lines(self.clashes, self.interference_error, ran))
        if self.changed:
            lines.append("not saved: " + ", ".join(_file(p) for p in self.changed)
                         + " changed in SolidWorks; save there to keep it")
        else:
            lines.append("nothing changed in SolidWorks")
        if self.skipped:
            lines.append(f"SKIPPED {self.skipped}")
        return lines


def _update_document(sw: SolidWorks, doc: DocumentValues) -> Tuple[UpdateResult, List[Tuple[str, str]]]:
    """``open_document`` then :func:`update_variables`; the result and its failures, never a raise."""
    name = _file(doc.path)
    try:
        sw.open_document(doc.path)
        result = update_variables(sw, doc.variables, doc.path)
    except Exception as exc:  # noqa: BLE001 - a raise is this document's failure, never the job's (B1)
        # Marked on the document's own result too, so the finish never takes it for one found holding its values.
        return UpdateResult(document=name, failures=[("", _said(exc))]), [(name, _said(exc))]
    failures = [(f"{name} {what}", why) for what, why in result.failures]
    if result.changed and not result.rebuilt:
        failures.append((name, f"SolidWorks reported an error rebuilding {_stem(doc.path)}."))
    return result, failures


def update_gearbox(sw: SolidWorks, parts: Sequence[DocumentValues] = (), layout: Optional[DocumentValues] = None,
                   assembly: str = "", placements: Sequence[Placement] = (), *,
                   motion: Optional[MotionUpdate] = None,
                   exists: Callable[[str], bool] = os.path.exists,
                   progress: Optional[Callable[[Step], None]] = None,
                   mtime: Callable[[str], float] = os.path.getmtime) -> GearboxUpdate:
    """Update SolidWorks from the workbook: part values, the layout's globals, and the static assembly's
    components re-placed (PLAN-WORKBOOK §4.5), in one worker job and in two phases, so a missing piece changes
    nothing.

    *Check* — raise :class:`BuildError` before any change if a path is
    missing, a same-named document is open from another folder, a document
    lacks a global it should hold (``planned_changes`` raises), or a
    component is not found by its recorded ``Name2`` — those three a
    :class:`NotAsBuilt` naming the document, since only a new revision
    (Build again…) gets past them. Each document is opened
    with ``open_document`` (decision: Update always opens and activates) and
    read, writing nothing (:func:`_read_live`); each file's time is noted
    first (``mtime``, into :attr:`GearboxUpdate.mtimes`).

    *Change* — each part, then the layout, that does not already hold what
    it should: ``open_document`` then :func:`update_variables`; the first
    failure stops. A document the check found holding every global already
    (in either trig unit, and evaluating them as that unit would:
    :func:`_held_unit`) is not touched at all: no trig units measured, no
    equation added, nothing set (W4 review S2: on SolidWorks 2026 measuring
    the units alone left every part marked modified, so every Update asked
    for saves of parts it had not changed). Then the assembly, when
    ``assembly`` is given: ``open_document``, ``find_component`` each, read
    ``component_frame``, re-place only those not :func:`same_frame` (with
    Unfix/Fix around it if ``findings.REPLACE_FIXED_ROUTE`` asks); then, if
    any document changed or any gear was re-placed (a teeth change alters
    the mesh), one ``rebuild`` and ``interferences`` — with nothing changed,
    the assembly is only read.

    Compares with SolidWorks live, never with the record, so an update the
    user never saved, or a component they dragged, is put right on the next
    press. Saves nothing and closes nothing. After the check phase nothing
    raises out: a raise becomes a failure on the result, so what was changed
    is still reported and recorded unsaved (W4 review B1). Runs on the worker
    thread.

    The check phase also refuses: placements with no assembly; one
    component recorded for two gears; a layout plane or axis no longer in
    the layout; new values that do not evaluate (:func:`_evaluates`, in both
    trig units, measuring only when they differ); re-placing while
    ``REPLACE_FIXED_ROUTE`` is not one of :data:`REPLACE_ROUTES` (probe
    layout_assembly_reopen, 2026: a Transform2 put moved a FIXED component
    and the frame survived a save and reopen, so "Transform2 put"). When
    ``findings.OPEN_PART_BESIDE_ASSEMBLY`` is not True (probe
    open_part_from_assembly, 2026: it is), values are not changed while the
    assembly is open — the user is asked to close it — and the assembly is
    opened only after the values, so a missing component is then a failure
    rather than a refusal. ``place_component`` reads each frame back after a
    rebuild of its own (probe nonparallel_mates); the assembly's one
    rebuild here is the one after every put, with ``CommandInProgress``
    restored in a ``finally``. Both are top-only (``swcom.rebuild_call``,
    probe assembly_rebuild_scope): each changed part and the layout were
    already rebuilt in their own documents by :func:`update_variables`, and a
    full rebuild of the assembly marked every part modified, those Update
    never touched among them. Refused in the check phase too: an assembly
    while ``findings.ASSEMBLY_REBUILD_ROUTE`` is not settled.

    W5: ``motion`` None is all of the above, unchanged (a W4 static
    gearbox, W5-PLAN D5). Given, the assembly is a train
    (``ASSEMBLY_TRAIN`` for every rebuild and put) and the motion path runs
    in W5-PLAN §1.6's order as W5-INTERFACES.md amends it — Agent A writes
    it; until then it is refused before anything is read.
    """
    if motion is not None:
        raise NotImplementedError("W5: Agent A, swbuild.update_gearbox's motion path")
    say = progress or _quiet
    _gate(sw)
    result = GearboxUpdate()
    documents = list(parts) + ([layout] if layout is not None else [])
    paths = [d.path for d in documents] + ([assembly] if assembly else [])
    if placements and not assembly:
        raise BuildError("Gears can only be re-placed in an assembly, and Update SolidWorks was given none.")
    if assembly:
        _assembly_rebuild_gate(ASSEMBLY_STATIC)    # the workbook's static gearbox: fixed components, no mates
    for path in paths:
        if not exists(path):
            raise BuildError(f"{path} is no longer there, so Update SolidWorks cannot change it: it was moved, "
                             "renamed or deleted since it was built.")
    open_before = _refuse_paths(sw, [], paths, "make", "change")
    result.open_before = list(open_before)
    for index, placement in enumerate(placements):
        for earlier in placements[:index]:
            if placement.component == earlier.component:
                raise BuildError(f"{placement.component} is recorded for both {earlier.gear} and {placement.gear}, "
                                 "so one of them would be placed twice.")
    route = getattr(findings, "REPLACE_FIXED_ROUTE", None)
    if placements and route not in REPLACE_ROUTES:
        raise BuildError(f"Moving a fixed component has not been settled on SolidWorks yet "
                         f"(findings.REPLACE_FIXED_ROUTE is {route!r}), so Update SolidWorks cannot re-place the "
                         "gears; run probe tier 7 first.")
    beside = getattr(findings, "OPEN_PART_BESIDE_ASSEMBLY", None) is True
    if assembly and documents and not beside and any(same_path(d.path, assembly) for d in sw.documents()):
        raise BuildError(f"Close {_file(assembly)} in SolidWorks, then press Update SolidWorks again: changing a "
                         "part while its assembly is open has not been settled on this SolidWorks "
                         "(findings.OPEN_PART_BESIDE_ASSEMBLY).")
    for path in paths:
        try:
            result.mtimes[path] = float(mtime(path))
        except (OSError, ValueError, TypeError):
            pass

    # -- check: opens and reads, writes nothing
    total = len(paths)
    holds: List[str] = []           # per document: the trig unit it already holds every global in, or ""
    for index, doc in enumerate(documents, 1):
        say(Step(STAGE_CHECK, _stem(doc.path), index, total))
        _, by_unit, values = _read_live(sw, doc, "updated", lambda path: _note_opened(sw, path, result))
        holds.append(_held_unit(by_unit, values, doc.variables))
    if assembly and (beside or not documents):
        say(Step(STAGE_CHECK, _stem(assembly), total, total))
        sw.begin_build()
        try:
            sw.open_document(assembly)
            _note_opened(sw, assembly, result)
            for index, placement in enumerate(placements, 1):
                sw.find_component(f"placed{index}", placement.component)
        except ComponentGone as exc:      # renamed or deleted in SolidWorks: only a new revision puts it back
            raise NotAsBuilt(str(exc), assembly) from None
        except SolidWorksError as exc:
            raise BuildError(str(exc)) from None
        finally:
            sw.end_build()
    for doc, unit in zip(documents, holds):
        if not unit:
            _evaluates(sw, doc, "updated")

    # -- change: values first, then the assembly. Nothing raises out from here (B1).
    stage = [_file(documents[0].path) if documents else _file(assembly)]
    try:
        _update_change(sw, result, parts, layout, documents, holds, assembly, placements, route, say, stage)
    except Exception as exc:  # noqa: BLE001 - see above
        result.failures.append((stage[0], _said(exc)))
        if not result.skipped and assembly and stage[0] != _file(assembly):
            result.skipped = f"the assembly, because the job stopped during {stage[0]}"
    finally:
        if result.placed and assembly not in result.changed:
            result.changed.append(assembly)
    return result


def _update_change(sw: SolidWorks, result: GearboxUpdate, parts: Sequence[DocumentValues],
                   layout: Optional[DocumentValues], documents: Sequence[DocumentValues], holds: Sequence[str],
                   assembly: str, placements: Sequence[Placement], route: Optional[str],
                   say: Callable[[Step], None], stage: List[str]) -> None:
    """The change phase of :func:`update_gearbox`, filling ``result`` as it goes; ``stage[0]`` names the document
    under way, for the failure if something raises."""
    for position, doc in enumerate(documents):
        stage[0] = _file(doc.path)
        in_parts = position < len(parts)
        if holds[position]:
            # It already holds every global as asked: left as it is, not even its trig units measured (S2).
            done = UpdateResult(document=_file(doc.path), unchanged=[v.name for v in doc.variables],
                                trig=holds[position])
            failures: List[Tuple[str, str]] = []
        else:
            say(Step(STAGE_VALUES, _stem(doc.path)))
            done, failures = _update_document(sw, doc)
        if in_parts:
            result.parts.append(done)
        else:
            result.layout = done
        if done.changed:
            result.changed.append(doc.path)
        if failures:
            result.failures.extend(failures)
            rest = len(parts) - position - 1 if in_parts else 0
            left = [f"{rest} more part{'s' if rest != 1 else ''}"] if rest else []
            if layout is not None and in_parts:
                left.append("the layout part")
            if assembly:
                left.append("the assembly")
            if left:
                listed = left[0] if len(left) == 1 else ", ".join(left[:-1]) + f" and {left[-1]}"
                result.skipped = f"{listed}, because {_file(doc.path)} failed"
            return

    if not assembly:
        return
    stage[0] = _file(assembly)
    stem = _stem(assembly)
    say(Step(STAGE_PLACE, stem))
    sw.begin_build()
    try:
        opened = False
        try:
            sw.open_document(assembly)
            opened = True
            _note_opened(sw, assembly, result)
            handles = [f"placed{index}" for index in range(1, len(placements) + 1)]
            for handle, placement in zip(handles, placements):
                sw.find_component(handle, placement.component)
            for handle, placement in zip(handles, placements):
                rotation, at = sw.component_frame(handle)
                result.found[placement.gear] = (tuple(rotation), tuple(at))
            moves = [(h, p) for h, p in zip(handles, placements)
                     if not same_frame(result.found[p.gear][0], result.found[p.gear][1], p.rotation, p.at, p.pitch)]
            unfix = route == REPLACE_ROUTES[1]
            sw.set_rebuild_suppressed(True)
            try:
                for handle, placement in moves:
                    if unfix:
                        sw.unfix_component(handle)
                    sw.place_component(handle, placement.rotation, placement.at, kind=ASSEMBLY_STATIC)
                    result.placed.append(placement.gear)
                    if unfix:
                        sw.fix_component(handle)
            finally:
                sw.set_rebuild_suppressed(False)
        except Exception as exc:  # noqa: BLE001 - the assembly's failure; what was placed stays listed (B1)
            result.failures.append((_file(assembly), _said(exc)))
        if opened and (result.changed or result.placed):
            result.rebuilt = bool(sw.rebuild(kind=ASSEMBLY_STATIC))
            if not result.rebuilt:
                result.failures.append((_file(assembly), f"SolidWorks reported an error rebuilding {stem}."))
        if result.rebuilt and not result.failures and getattr(findings, "INTERFERENCE_CHECKED", False):
            say(Step(STAGE_INTERFERENCE, stem))
            gear_of = {p.component: p.gear for p in placements}
            try:
                result.clashes = _clashes(sw.interferences(), gear_of)
            except Exception as exc:  # noqa: BLE001 - a clash check that cannot run is a CHECK, never a failure
                result.interference_error = _said(exc)
    finally:
        sw.end_build()
