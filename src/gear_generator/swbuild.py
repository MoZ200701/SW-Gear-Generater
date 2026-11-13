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
from .gears.equations import DEGREES, EquationError, evaluate_all, split_equation
from .store import same_path
from .swcom import MINIMUM_MAJOR, DocInfo, SolidWorksError, meets_minimum, release_year

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
    def rebuild(self) -> bool: ...
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
    def place_component(self, handle: str, rotation: Sequence[float], at) -> None: ...
    # W4 (a workbook's layout part and static assembly). ``documents`` and ``feature_names`` are swcom.Session's
    # own, unchanged; the other four are new there (each docstring in swcom says what it does).
    def documents(self) -> List[DocInfo]: ...
    def feature_names(self) -> List[str]: ...
    def open_document(self, path: str) -> DocInfo: ...
    def find_component(self, handle: str, name: str) -> str: ...
    def component_frame(self, handle: str) -> Tuple[Tuple[float, ...], Tuple[float, float, float]]: ...
    def interferences(self) -> List[Tuple[Tuple[str, ...], float]]: ...


class BuildError(SolidWorksError):
    """The build could not start at all; nothing was made."""


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


def _place(sw, op: base.Place, result, trig):
    sw.place_component(op.component, op.rotation, op.at)
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


def build(sw: SolidWorks, plan: BuildPlan, exists: Callable[[str], bool] = os.path.exists) -> BuildResult:
    """Make the plan's document, run every step, rebuild once, check, and save.

    Raises :class:`BuildError` only before anything is made. After that every
    problem is a failure in the result, and the document is left open.
    """
    _gate(sw)
    problems = plan.check()
    if problems:
        raise BuildError("The build plan is not sound: " + " ".join(problems))
    first = plan.ops[0]
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
        result.trig = sw.detect_trig_units()
        result.done.append(f"trig units measured: {result.trig}")
        _run(sw, plan, result)
        result.rebuilt = bool(sw.rebuild())
        _verify(sw, plan, result)
    finally:
        sw.end_build()

    if save is not None and result.ok and result.rebuilt:
        try:
            result.saved = sw.save_as(save.path)
        except SolidWorksError as exc:
            result.failures.append(("save", str(exc)))
    return result


def _run(sw: SolidWorks, plan: BuildPlan, result: BuildResult) -> None:
    sw.set_rebuild_suppressed(True)
    try:
        for op in plan.ops[1:]:
            runner = _RUNNERS.get(type(op))
            if runner is None:  # ManualStep, Rebuild, SaveAs: counted or done around the loop
                continue
            try:
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
    pair = PairResult(gear_a=build(sw, gear_a, exists))
    if not pair.gear_a.ok:
        pair.skipped = "the second gear and the assembly, because the first gear failed"
        return pair
    pair.gear_b = build(sw, gear_b, exists)
    if not pair.gear_b.ok:
        pair.skipped = "the assembly, because the second gear failed"
        return pair
    pair.assembly = build(sw, assembly, exists)
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
               exists: Callable[[str], bool] = os.path.exists) -> ManyResult:
    """Every plan's part in order, each by :func:`build`; the first that fails stops the rest.

    Every path is checked before anything is made, so a batch either starts
    with nothing in the way or does not start: a build never overwrites a file
    (``findings.SAVE_AS_OVERWRITES`` is True, so this check is the only guard).
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
    many = ManyResult()
    for index, plan in enumerate(plans):
        result = build(sw, plan, exists)
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
                except SolidWorksError as exc:
                    result.failures.append((f"\"{name}\"", str(exc)))
        finally:
            sw.set_rebuild_suppressed(False)
        result.rebuilt = bool(sw.rebuild())
    finally:
        sw.end_build()
    return result


# -- a workbook's gearbox: parts, layout part and static assembly (phase W4) ---------
#
# docs/PLAN-WORKBOOK.md §4.2–§4.5. Pinned in one interface commit before the work was split; the bodies that
# raise NotImplementedError are Agent A's. Planning is pure and runs on the Tk thread (workbook.gearbox,
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
    """One interference in an assembly. ``components`` are the ``Name2``s SolidWorks gave (``()`` when the names
    could not be read, ``findings.INTERFERENCE_NAMES_ROUTE``); ``gears`` the workbook's gear ids for them, in
    the same order, where the caller's map knows them (else the Name2 itself). ``volume`` in mm³."""

    components: Tuple[str, ...]
    gears: Tuple[str, ...]
    volume: float


def same_frame(rotation_a: Sequence[float], at_a: Sequence[float], rotation_b: Sequence[float],
               at_b: Sequence[float], pitch: float = 0.0, tolerance: float = POSE_TOLERANCE) -> bool:
    """Whether two component frames place the same gear the same way.

    The origins must agree to ``tolerance`` mm on each axis. The rotations
    must differ only by a turn about the part's own Z (its gear axis) of a
    whole number of ``pitch`` degrees — a gear turned one tooth is the same
    gear in the same place (review 14: comparing θ itself would call
    2.5e-14 and one whole pitch different). ``pitch`` 0 asks for the same
    rotation. Rotations are 9 numbers by rows, ``v_global = R · v_local + at``.
    """
    if any(abs(float(a) - float(b)) > tolerance for a, b in zip(at_a, at_b)):
        return False
    ra = [[float(rotation_a[i * 3 + j]) for j in range(3)] for i in range(3)]
    rb = [[float(rotation_b[i * 3 + j]) for j in range(3)] for i in range(3)]
    # M = Ra^T Rb: the turn, in a's own frame, that takes a to b. It must be a turn about local Z.
    m = [[sum(ra[k][i] * rb[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    turn = math.atan2(m[1][0], m[0][0])
    c, s = math.cos(turn), math.sin(turn)
    about_z = ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
    if any(abs(m[i][j] - about_z[i][j]) > tolerance for i in range(3) for j in range(3)):
        return False
    if pitch <= 0:
        return abs(turn) <= tolerance
    step = math.radians(pitch)
    off = turn % step
    return min(off, step - off) <= tolerance


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
    on it when every part was reused.
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

    @property
    def ok(self) -> bool:
        """Every part planned was saved, the layout saved or reused (when planned), the assembly saved (when
        planned). Clashes do not count against it."""
        raise NotImplementedError("W4: Agent A, swbuild.GearboxResult.ok")

    def log_lines(self) -> List[str]:
        """The parts' lines, the checked documents, the layout's, the assembly's, then ``ok      no interference
        between the gears`` or one ``CHECK`` per clash naming the gears, then ``SKIPPED …``."""
        raise NotImplementedError("W4: Agent A, swbuild.GearboxResult.log_lines")


def build_gearbox(sw: SolidWorks, parts: Sequence[BuildPlan], reuse: Sequence[DocumentValues] = (),
                  layout: Union[BuildPlan, DocumentValues, None] = None, assembly: Optional[BuildPlan] = None,
                  gears: Optional[Mapping[str, str]] = None, *,
                  exists: Callable[[str], bool] = os.path.exists,
                  progress: Optional[Callable[[Step], None]] = None) -> GearboxResult:
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
       inserted), or a reused document does not hold what is expected
       (decision 3: each is opened with ``open_document`` and checked live —
       ``planned_changes(...) == []`` and every ``features`` name present —
       the sentence naming the file and what differs).
    2. The new parts, by :func:`build_many`; a failure skips the rest.
    3. The layout: built (a failure skips the assembly), or the reused one
       left open from step 1.
    4. The assembly, by :func:`build`; then, if it built cleanly,
       ``sw.interferences()`` (a raise becomes ``interference_error``).

    ``progress`` is told each :class:`Step` as it starts. Nothing is closed;
    a failed document is left open, unsaved. Runs on the worker thread.
    """
    raise NotImplementedError("W4: Agent A, swbuild.build_gearbox")


@dataclass
class GearboxUpdate:
    """What :func:`update_gearbox` did. Nothing is saved: ``changed`` lists every document it changed in
    SolidWorks (the record marks them unsaved until the app sees them saved, decision 3).

    ``parts`` holds one result per part reached, in the order given;
    ``layout`` the layout's, if one was given and reached. ``found`` is each
    placed gear's live frame (rotation by rows, origin in mm) as read before
    anything moved — the finish compares it with the record to say a
    component the user dragged was put back. ``placed`` lists the gears
    re-placed because ``found`` differed from the wanted frame
    (:func:`same_frame`, modulo the gear's pitch). ``rebuilt`` is the
    assembly's one rebuild. ``failures`` are (what, why) in the order met.
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

    @property
    def ok(self) -> bool:
        raise NotImplementedError("W4: Agent A, swbuild.GearboxUpdate.ok")

    def log_lines(self) -> List[str]:
        raise NotImplementedError("W4: Agent A, swbuild.GearboxUpdate.log_lines")


def update_gearbox(sw: SolidWorks, parts: Sequence[DocumentValues] = (), layout: Optional[DocumentValues] = None,
                   assembly: str = "", placements: Sequence[Placement] = (), *,
                   exists: Callable[[str], bool] = os.path.exists,
                   progress: Optional[Callable[[Step], None]] = None) -> GearboxUpdate:
    """Update SolidWorks from the workbook: part values, the layout's globals, and the static assembly's
    components re-placed (PLAN-WORKBOOK §4.5), in one worker job and in two phases, so a missing piece changes
    nothing.

    *Check* — raise :class:`BuildError` before any change if a path is
    missing, a same-named document is open from another folder, a document
    lacks a global it should hold (``planned_changes`` raises), or a
    component is not found by its recorded ``Name2``. Each document is opened
    with ``open_document`` (decision: Update always opens and activates).

    *Change* — each part, then the layout: ``open_document`` then
    :func:`update_variables`; the first failure stops. Then the assembly
    (when ``assembly`` is given, even with nothing to move: a teeth change
    alters the mesh): ``open_document``, ``find_component`` each, read
    ``component_frame``, re-place only those not :func:`same_frame` (with
    Unfix/Fix around it if ``findings.REPLACE_FIXED_ROUTE`` asks), one
    ``rebuild``, then ``interferences``.

    Compares with SolidWorks live, never with the record, so an update the
    user never saved, or a component they dragged, is put right on the next
    press. Saves nothing and closes nothing. Runs on the worker thread.
    """
    raise NotImplementedError("W4: Agent A, swbuild.update_gearbox")
