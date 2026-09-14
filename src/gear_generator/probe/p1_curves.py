"""Tier 1, part three: Equation Driven Curves, which decide Recipe A.

Four questions, in order: what units a literal curve's expressions and ``t``
are in; whether global names are accepted in the expressions and the range;
whether the curve follows a global when it changes and the part rebuilds; and
whether a line's end can be related to a curve's end. Recipe A needs the first
three; the fourth decides whether endpoints are related or locked numerically.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from ..swcom import call
from . import scaffold as sc
from .harness import Px, probe
from .p1_equations import adder

Point = Tuple[float, float]


def _near(a: Optional[Point], b: Point, tol: float = 1e-4) -> bool:
    return a is not None and abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def _curve(px: Px, manager: Any, label: str, x: str, y: str, t1: str, t2: str, lock: bool = True) -> Any:
    got, curve = px.attempt(
        f'{label}: CreateEquationSpline2("{x}", "{y}", "", "{t1}", "{t2}", False, 0, 0, 0, {lock}, {lock})',
        lambda: call(manager, "CreateEquationSpline2", x, y, "", t1, t2, False, 0.0, 0.0, 0.0, lock, lock),
    )
    return curve if got else None


def _ends(px: Px, label: str, curve: Any) -> Optional[Tuple[Point, Point]]:
    got, ends = px.attempt(f"{label}: GetPoints2 ends", lambda: sc.spline_ends_mm(curve))
    return ends if got else None


@probe("curve_literal", needs=("sketch_open_close",), tier=1,
       members=("ISketchManager.CreateEquationSpline2", "ISketchSpline.GetPoints2", "ISketchSegment.GetType"))
def curve_literal(px: Px) -> None:
    """A literal parametric curve: its units, and whether t and trig are radians."""
    with sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)

        straight = _curve(px, manager, "straight", "t", "2*t", "0", "10")
        px.require(straight is not None, "CreateEquationSpline2 makes a curve from literal expressions")
        px.fact("equation_curve_segment_type", int(call(straight, "GetType")))
        ends = _ends(px, "straight", straight)
        px.fact("straight_curve_ends_mm", ends)
        units = "?"
        if ends and _near(ends[1], (10.0, 20.0)):
            units = "document units (mm)"
        elif ends and _near(ends[1], (10000.0, 20000.0), 1.0):
            units = "metres"
        px.fact("curve_expression_units", units)
        px.check(units == "document units (mm)", f"expressions are in document units: t = 10 ends at {ends and ends[1]}")

        quarter = _curve(px, manager, "quarter", "10*cos(t)", "10*sin(t)", "0", "pi/2")
        ends = _ends(px, "quarter", quarter) if quarter is not None else None
        px.fact("quarter_circle_ends_mm", ends)
        trig = "radians" if ends and _near(ends[1], (0.0, 10.0)) else "degrees" if ends and _near(
            ends[1], (10 * math.cos(math.radians(math.pi / 2)), 10 * math.sin(math.radians(math.pi / 2)))) else "?"
        px.fact("curve_trig_units", trig, f"cos(t) from 0 to pi/2 ends at {ends and ends[1]}: trig is in {trig}")

        sc.close_sketch(px, doc, "Probe Curves", before)

        # Spellings, one sketch each so a refusal cannot be blamed on a neighbour.
        spellings = {}
        for label, x, y, t2 in (
            ("spaces", "10 * cos ( t )", "10 * sin ( t )", "pi / 2"),
            ("degree conversion, no spaces", "10*cos(t*180/pi)", "10*sin(t*180/pi)", "pi/2"),
            ("degree conversion, spaces", "10 * cos ( t * 180 / pi )", "10 * sin ( t * 180 / pi )", "pi / 2"),
            ("bracketed t with conversion", "10*cos((t)*180/pi)", "10*sin((t)*180/pi)", "pi/2"),
            ("bracketed sum", "10*cos((t+0.1)-0.1)", "10*sin((t+0.1)-0.1)", "pi/2"),
        ):
            before = sc.feature_names(doc)
            manager = sc.open_sketch(px, doc, 1)
            curve = _curve(px, manager, label, x, y, "0", t2)
            ends = _ends(px, label, curve) if curve is not None else None
            spellings[label] = {"made": curve is not None, "end": ends[1] if ends else None}
            sc.close_sketch(px, doc, f"Probe Spelling {len(spellings)}", before, allow_empty=True)
        px.fact("curve_spellings", spellings)

        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        single = _curve(px, manager, "status", "10*cos(t)", "10*sin(t)", "0", "pi/2")
        sketch = call(manager, "ActiveSketch")
        px.fact("status_one_locked_curve", int(call(sketch, "GetConstrainedStatus")))
        if single is not None:
            got, _ = px.attempt("sgFIXED on the curve", lambda: sc.relate(doc, "sgFIXED", single))
            px.fact("status_one_fixed_curve", int(call(sketch, "GetConstrainedStatus")))
        sc.close_sketch(px, doc, "Probe Status Curve", before)

        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        unlocked = _curve(px, manager, "unlocked", "t", "t*t", "0", "5", lock=False)
        if unlocked is not None:
            px.fact("status_with_one_unlocked_curve", int(call(call(manager, "ActiveSketch"), "GetConstrainedStatus")))
        sc.close_sketch(px, doc, "Probe Unlocked", before)


@probe("curve_globals", needs=("curve_literal", "equation_set"), tier=1,
       members=("ISketchManager.CreateEquationSpline2",))
def curve_globals(px: Px) -> None:
    """Quoted global names are accepted in a curve's expressions and in its range."""
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add('"Probe R"= 10') >= 0 and add('"Probe End"= pi / 2') >= 0, "the globals are added")
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)

        accepted = {}
        for label, x, y, t1, t2 in (
            ("name in expression", '"Probe R" * cos ( t )', '"Probe R" * sin ( t )', "0", "pi / 2"),
            ("name in range", "10 * cos ( t )", "10 * sin ( t )", "0", '"Probe End"'),
            ("names in both", '"Probe R" * cos ( t )', '"Probe R" * sin ( t )', "0", '"Probe End"'),
        ):
            curve = _curve(px, manager, label, x, y, t1, t2)
            ends = _ends(px, label, curve) if curve is not None else None
            accepted[label] = {"made": curve is not None, "ends": ends}
            px.check(curve is not None and _near(ends[1] if ends else None, (0.0, 10.0), 1e-3),
                     f"{label}: the curve is made and ends at {ends and ends[1]}")
        px.fact("curve_globals", accepted)
        sc.close_sketch(px, doc, "Probe Curve Globals", before)


@probe("curve_rebuild", needs=("curve_globals",), tier=1,
       members=("ISketchManager.CreateEquationSpline2", "IModelDoc2.ForceRebuild3", "ISketch.GetSketchSegments"))
def curve_rebuild(px: Px) -> None:
    """A curve over a global follows the global when it changes and the part rebuilds."""
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        radius = add('"Probe R"= 10')
        add('"Probe End"= pi / 2')
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        curve = _curve(px, manager, "follows", '"Probe R" * cos ( t )', '"Probe R" * sin ( t )', "0", '"Probe End"')
        px.require(curve is not None, "the curve over globals is made")
        name = sc.close_sketch(px, doc, "Probe Curve Rebuild", before)

        sc.put_indexed(eqm, "Equation", radius, '"Probe R"= 20')
        call(doc, "ForceRebuild3", False)
        segments = call(sc.sketch_of(doc, name), "GetSketchSegments") or ()
        splines = [s for s in segments if int(call(s, "GetType")) == sc.SW_SKETCH_SPLINE]
        px.require(len(splines) == 1, f"the rebuilt sketch still holds one curve ({len(splines)})")
        ends = _ends(px, "after rebuild", splines[0])
        px.fact("ends_after_global_change_mm", ends)
        px.check(_near(ends[1] if ends else None, (0.0, 20.0), 1e-3),
                 f"after R goes from 10 to 20 the curve ends at {ends and ends[1]}")


@probe("curve_relations", needs=("curve_literal", "relations"), tier=1,
       members=("ISketch.GetSketchPoints2", "IModelDoc2.SketchAddConstraints"))
def curve_relations(px: Px) -> None:
    """A line's end can be made coincident with a curve's end, found as a sketch point."""
    with sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        curve = _curve(px, manager, "target", "10*cos(t)", "10*sin(t)", "0", "pi/2")
        px.require(curve is not None, "the target curve is made")
        sketch = call(manager, "ActiveSketch")
        px.fact("sketch_points_with_curve", [xy for _, xy in sc.points_mm(sketch)])
        got, start_point = px.attempt("the curve's start as a sketch point", lambda: sc.point_at(sketch, (10.0, 0.0)))
        px.require(got, "the curve's start point is a selectable sketch point")
        line = call(manager, "CreateLine", 0.003, -0.004, 0.0, 0.008, 0.001, 0.0)
        got, _ = px.attempt("sgCOINCIDENT line end to curve start",
                            lambda: sc.relate(doc, "sgCOINCIDENT", call(line, "GetEndPoint2"), start_point))
        end = sc.point_mm(call(line, "GetEndPoint2"))
        ends = _ends(px, "target after relation", curve)
        px.fact("line_end_after_relation_mm", end)
        px.fact("curve_ends_after_relation_mm", ends)
        px.check(got and _near(end, (10.0, 0.0), 1e-6), f"the line's end is on the curve's start: {end}")
        px.check(bool(ends) and _near(ends[0], (10.0, 0.0), 1e-6), "the locked curve did not move to meet the line")
        sc.close_sketch(px, doc, "Probe Curve Relations", before)


@probe("curve_bad", needs=("curve_literal",), tier=1, members=("ISketchManager.CreateEquationSpline2",))
def curve_bad(px: Px) -> None:
    """What a curve with a broken expression does: nothing, an exception, or a dialog."""
    with sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        curve = _curve(px, manager, "broken", "t *", "t", "0", "1")
        px.fact("broken_expression_makes", "nothing" if curve is None else type(curve).__name__)
        px.ok("a broken expression came back without a hang")
        sc.close_sketch(px, doc, "Probe Bad Curve", before, allow_empty=True)


@probe("curve_fixed_rebuild", needs=("curve_rebuild", "relations"), tier=1,
       members=("IModelDoc2.SketchAddConstraints", "ISketch.GetConstrainedStatus"))
def curve_fixed_rebuild(px: Px) -> None:
    """A curve made fully defined with sgFIXED: does it still follow its global on a rebuild?

    A locked Equation Driven Curve leaves its sketch under-defined, and sgFIXED
    makes it fully defined. If fixing it also froze it, Recipe A would have to
    choose between a fully defined sketch and a parametric flank.
    """
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        radius = add('"Probe R"= 10')
        add('"Probe End"= pi / 2')
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        curve = _curve(px, manager, "fixed", '"Probe R" * cos ( t )', '"Probe R" * sin ( t )', "0", '"Probe End"')
        px.require(curve is not None, "the curve over globals is made")
        sc.relate(doc, "sgFIXED", curve)
        px.fact("status_fixed_curve_over_globals", int(call(call(manager, "ActiveSketch"), "GetConstrainedStatus")))
        name = sc.close_sketch(px, doc, "Probe Fixed Curve", before)

        sc.put_indexed(eqm, "Equation", radius, '"Probe R"= 20')
        call(doc, "ForceRebuild3", False)
        sketch = sc.sketch_of(doc, name)
        splines = [s for s in (call(sketch, "GetSketchSegments") or ()) if int(call(s, "GetType")) == sc.SW_SKETCH_SPLINE]
        px.require(len(splines) == 1, "the rebuilt sketch still holds the curve")
        ends = _ends(px, "fixed after rebuild", splines[0])
        follows = _near(ends[1] if ends else None, (0.0, 20.0), 1e-3)
        px.fact("fixed_curve_follows_global", follows, f"after R 10 to 20 the fixed curve ends at {ends and ends[1]}")
        px.fact("status_fixed_curve_after_rebuild", int(call(sketch, "GetConstrainedStatus")))
        px.check(True, "the fixed curve's behaviour on a rebuild is recorded")


def _near_points(sketch: Any, where: Point, tol: float = 1e-4) -> List[Any]:
    return [point for point, xy in sc.points_mm(sketch) if abs(xy[0] - where[0]) + abs(xy[1] - where[1]) <= tol]


def _selects_alone(doc: Any, point: Any) -> Dict[str, Any]:
    """Select one point on its own with Select4, and say what that did."""
    call(doc, "ClearSelection2", True)
    try:
        returned = call(point, "Select4", False, sc.null())
    except Exception as exc:  # noqa: BLE001 - a stale pointer raising is the evidence
        return {"returned": "raised", "error": str(exc), "selected": sc.selected_count(doc)}
    count = sc.selected_count(doc)
    call(doc, "ClearSelection2", True)
    return {"returned": returned, "selected": count}


def _same(a: Any, b: Any) -> Any:
    try:
        return bool(a == b)
    except Exception as exc:  # noqa: BLE001
        return f"raised {exc}"


@probe("curve_end_points", needs=("curve_relations", "curve_fixed_rebuild"), tier=1,
       members=("ISketch.GetSketchPoints2", "ISketchPoint.Select4", "IModelDoc2.SketchAddConstraints"))
def curve_end_points(px: Px) -> None:
    """What a point drawn exactly on another entity's end becomes.

    Recipe A draws each radial line starting exactly where its flank curve
    starts, then relates the two. In the first end-to-end build that relation
    could not select the curve's start, and the selection was empty afterwards.
    This records whether the second point is a point at all, or the same one —
    for a curve and a line, two lines, and an arc and a line — and whether
    fixing the curve changes anything about it.
    """
    start = (10.0, 0.0)
    with sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        sketch = call(manager, "ActiveSketch")
        curve = _curve(px, manager, "ends", "10*cos(t)", "10*sin(t)", "0", "pi/2")
        px.require(curve is not None, "the curve is made")
        captured = _near_points(sketch, start)
        px.fact("points_at_curve_start_with_curve_only", len(captured))
        px.require(len(captured) == 1, "the curve's start is one sketch point")
        captured = captured[0]

        line = call(manager, "CreateLine", 0.010, 0.0, 0.0, 0.005, -0.005, 0.0)
        line_start, line_end = call(line, "GetStartPoint2"), call(line, "GetEndPoint2")
        at_start = _near_points(sketch, start)
        px.fact("points_at_curve_start_after_line", len(at_start))
        px.fact("line_start_is_the_curve_start_point", _same(line_start, captured))
        px.fact("line_end_is_the_curve_start_point", _same(line_end, captured))
        px.fact("captured_start_selects_after_line", _selects_alone(doc, captured))
        call(doc, "ClearSelection2", True)
        call(line_start, "Select4", False, sc.null())
        call(captured, "Select4", True, sc.null())
        px.fact("selected_after_selecting_the_merged_point_twice", sc.selected_count(doc))
        call(doc, "ClearSelection2", True)

        got, _ = px.attempt("sgFIXED on the curve", lambda: sc.relate(doc, "sgFIXED", curve))
        px.fact("points_at_curve_start_after_fixed", len(_near_points(sketch, start)))
        px.fact("captured_start_selects_after_fixed", _selects_alone(doc, captured))
        px.fact("status_curve_fixed_line_from_its_start", int(call(sketch, "GetConstrainedStatus")))

        first = call(manager, "CreateLine", 0.0, 0.020, 0.0, 0.005, 0.020, 0.0)
        second = call(manager, "CreateLine", 0.005, 0.020, 0.0, 0.010, 0.025, 0.0)
        px.fact("points_at_a_shared_line_end", len(_near_points(sketch, (5.0, 20.0))))
        px.fact("line_start_is_the_previous_line_end", _same(call(second, "GetStartPoint2"),
                                                              call(first, "GetEndPoint2")))
        arc = call(manager, "CreateArc", 0.0, 0.040, 0.0, 0.005, 0.040, 0.0, 0.0, 0.045, 0.0, 1)
        after_arc = call(manager, "CreateLine", 0.005, 0.040, 0.0, 0.010, 0.035, 0.0)
        px.fact("points_at_a_shared_arc_end", len(_near_points(sketch, (5.0, 40.0))))
        px.fact("line_start_is_the_arc_start", _same(call(after_arc, "GetStartPoint2"), call(arc, "GetStartPoint2")))
        apart = call(manager, "CreateLine", 0.0051, 0.040, 0.0, 0.010, 0.045, 0.0)
        px.fact("a_line_0_1_mm_away_is_its_own_point", not _same(call(apart, "GetStartPoint2"),
                                                                 call(arc, "GetStartPoint2")))
        sc.close_sketch(px, doc, "Probe Curve Ends", before)
