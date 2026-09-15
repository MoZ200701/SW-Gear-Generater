"""Tier 2 for bevel gears: a revolved blank, a lofted cut, a body turned in place, an axis from a line.

A bevel gear is built with its pitch cone's generatrix along +Z, so the heel
and toe sections lie on planes square to it — the offset planes the helical
probes already settled — and the finished body is then turned about Y onto
its own axis. Every question that recipe raises is settled on scratch parts,
with geometry as the oracle:

* **revolve** — a square revolved about a sketch centreline encloses
  ``2π r A`` (Pappus) and its centre of mass is on that centreline, both about
  the model's Z and about a tilted one;
* **loft cut** — a cut lofted between two similar rectangles on parallel
  planes, scaled about a common apex, removes the frustum
  ``L A (1 + k + k²) / 3``; a twisted or mismatched loft removes something else;
* **move body** — a body turned about Y has its centre of mass turned with it,
  and the turn, if it is a dimension, follows a global;
* **axis from a line** — a reference axis made from a sketch line lies along
  the line, and follows the line when its angle does; and where an angle
  dimension's placement point has to be, on the Top plane, for it to read the
  angle meant rather than its supplement;
* **plane square to a line** — a plane perpendicular to a sketch line through
  its end: where its sketch's origin and axes are in model space, and that they
  follow the line when its angle and length change.

The arities are from ``sldworks.tlb`` on SolidWorks 2026 (revision 34):
FeatureRevolve2 20 arguments, InsertCutBlend 12, InsertMoveCopyBody2 12.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p1_equations import adder
from .p2_helical import (
    centre_of_mass_mm,
    model_to_sketch,
    offset_plane,
    open_on,
    solid_bodies,
    transform_point,
)
from .p2_solid import _extrude_args, _volume

Vec = Tuple[float, float, float]

TILT = 30.0          # degrees, the tilted centreline's angle from +Z toward -X
SQUARE = 4.0         # mm, the revolved square's side
SQUARE_S = 15.0      # mm from the axis
SQUARE_T = 20.0      # mm along the axis

LOFT_BLANK_R = 30.0
LOFT_BLANK_W = 40.0
HEEL_Z = 35.0
TOE_Z = 5.0
APEX_Z = -15.0
RECT_W = 6.0         # along x at the heel
RECT_H = 4.0         # along y at the heel
RECT_X = 12.0        # the heel rectangle's centre, x

BODY_R = 5.0
BODY_X = 20.0
BODY_W = 10.0
TURN = 30.0
TURN_LINKED = 45.0

FEATURE_REVOLVE2_ARGS = 20


def revolve_args(angle: float = 2.0 * math.pi) -> Tuple[Any, ...]:
    """FeatureRevolve2: one direction, solid, blind through ``angle``, merged."""
    return (True, True, False, False, False, False, 0, 0, angle, 0.0, False, False, 0.0, 0.0, 0, 0.0, 0.0,
            True, True, True)


def cut_blend_args() -> Tuple[Any, ...]:
    """InsertCutBlend: open, no tangency, rational, tolerance 1, no matching, not thin, feature scope auto."""
    return (False, False, False, 1.0, 0, 0, False, 0.0, 0.0, 0, True, True)


def rotate_y(degrees: float, v: Sequence[float]) -> Vec:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (c * v[0] + s * v[2], v[1], -s * v[0] + c * v[2])


def _sketch_point(data: Sequence[float], model_mm: Vec) -> Vec:
    return transform_point(data, (model_mm[0] / sc.MM, model_mm[1] / sc.MM, model_mm[2] / sc.MM))


def _polyline(manager: Any, data: Sequence[float], points: Sequence[Vec]) -> List[Any]:
    """Closed polygon through model points (mm), drawn on the open sketch through its own transform."""
    segments = []
    for a, b in zip(points, list(points[1:]) + [points[0]]):
        pa, pb = _sketch_point(data, a), _sketch_point(data, b)
        segments.append(call(manager, "CreateLine", pa[0], pa[1], 0.0, pb[0], pb[1], 0.0))
    return segments


def _segment_name(segment: Any) -> str:
    try:
        return str(call(segment, "GetName"))
    except Exception:  # noqa: BLE001
        return "?"


def _select_segment(doc: Any, sketch_name: str, segment_name: str, append: bool, mark: int) -> bool:
    before = sc.selected_count(doc) if append else 0
    if not append:
        call(doc, "ClearSelection2", True)
    return bool(call(sc.extension(doc), "SelectByID2", f"{segment_name}@{sketch_name}", "EXTSKETCHSEGMENT",
                     0.0, 0.0, 0.0, append, mark, sc.null(), 0)) and sc.selected_count(doc) > before


def _revolve_square(px: Px, doc: Any, label: str, axis_dir: Vec, normal: Vec,
                    decoy: bool = False) -> Tuple[Optional[Any], str]:
    """A square SQUARE_S from an axis through the origin along ``axis_dir``, revolved about a centreline on it.

    With ``decoy`` a second centreline, at 30° to the first, is drawn too.
    """
    before = sc.feature_names(doc)
    manager = open_on(px, doc, sc.planes(doc)[1])
    data = model_to_sketch(call(manager, "ActiveSketch"))
    tip = tuple(v * 40.0 for v in axis_dir)
    a, b = _sketch_point(data, (0.0, 0.0, 0.0)), _sketch_point(data, tip)
    centreline = call(manager, "CreateCenterLine", a[0], a[1], 0.0, b[0], b[1], 0.0)
    px.require(centreline is not None, f"{label}: the centreline is made")
    if decoy:
        other = _sketch_point(data, (30.0 * math.sin(math.radians(TILT)), 0.0, 30.0 * math.cos(math.radians(TILT))))
        px.require(call(manager, "CreateCenterLine", a[0], a[1], 0.0, other[0], other[1], 0.0) is not None,
                   f"{label}: the second centreline is made")
    centre = tuple(SQUARE_T * axis_dir[i] + SQUARE_S * normal[i] for i in range(3))
    half = SQUARE / 2.0
    corners = [tuple(centre[i] + su * half * axis_dir[i] + sv * half * normal[i] for i in range(3))
               for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    _polyline(manager, data, corners)
    name = sc.close_sketch(px, doc, f"{label} Sketch", before)
    return centreline, name


@probe("revolve", needs=("extrude", "center_of_mass", "path_sketch_relations"), tier=2,
       members=("ISketchManager.CreateCenterLine", "IFeatureManager.FeatureRevolve2"))
def revolve(px: Px) -> None:
    """A square revolved a full turn about a sketch centreline, along Z and tilted, weighed and centred.

    The third case has a second construction line in the sketch, as a bevel
    blank's does, so the axis cannot be found by SolidWorks alone and has to be
    selected.
    """
    routes: List[str] = []
    for label, tilt in (("Revolve Z", 0.0), ("Revolve Tilted", TILT), ("Revolve Selected", 0.0)):
        axis_dir = (-math.sin(math.radians(tilt)), 0.0, math.cos(math.radians(tilt)))
        normal = (math.cos(math.radians(tilt)), 0.0, math.sin(math.radians(tilt)))
        with sc.scratch(px) as doc:
            centreline, sketch = _revolve_square(px, doc, label, axis_dir, normal, decoy=label == "Revolve Selected")
            made = None
            order = ("sketch only", "sketch and its centreline at mark 16", "sketch and its centreline at mark 4")
            if label == "Revolve Selected":
                order = order[1:] + order[:1]
            for route in order:
                call(doc, "ClearSelection2", True)
                px.require(sc.select_feature(doc, sc.feature_by_name(doc, sketch)), f"{label}: the sketch selects")
                if route != "sketch only":
                    mark = 16 if "16" in route else 4
                    if not _select_segment(doc, sketch, _segment_name(centreline), True, mark):
                        px.note(f"{label}: the centreline did not select for {route}")
                        continue
                got, made = px.attempt(f"{label}: FeatureRevolve2 [{route}]",
                                       lambda: call(sc.feature_manager(doc), "FeatureRevolve2", *revolve_args()))
                call(doc, "ClearSelection2", True)
                if got and made is not None:
                    routes.append(route)
                    break
            px.require(made is not None, f"{label}: a revolve is made")
            px.fact(f"{label.lower().replace(' ', '_')}_type", sc.type_name(made))
            volume = _volume(doc)
            expected = 2.0 * math.pi * SQUARE_S * SQUARE * SQUARE
            px.check(abs(volume - expected) < 1e-4 * expected,
                     f"{label}: the ring weighs {volume:.4f} mm³ (Pappus {expected:.4f})")
            centre = centre_of_mass_mm(doc)
            on_axis = tuple(SQUARE_T * v for v in axis_dir)
            px.fact(f"{label.lower().replace(' ', '_')}_centre_mm", centre)
            px.check(math.dist(centre, on_axis) < 1e-3, f"{label}: its centre of mass is on the centreline: {centre}")
            dims = [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in sc.dimensions_of(made)]
            px.fact(f"{label.lower().replace(' ', '_')}_dimensions", dims)
    px.fact("revolve_routes", routes)


def _loft_blank(px: Px, doc: Any) -> None:
    with sc.quiet_dimensions(px):
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, LOFT_BLANK_R / sc.MM)
        sketch = sc.close_sketch(px, doc, "Loft Blank Sketch", before)
    px.require(sc.select_feature(doc, sc.feature_by_name(doc, sketch)), "the blank sketch selects")
    made = call(sc.feature_manager(doc), "FeatureExtrusion3", *_extrude_args(LOFT_BLANK_W / sc.MM))
    call(doc, "ClearSelection2", True)
    px.require(made is not None, "the loft blank is extruded")


def _rectangle_sketch(px: Px, doc: Any, plane: Any, name: str, z: float) -> str:
    k = (z - APEX_Z) / (HEEL_Z - APEX_Z)
    before = sc.feature_names(doc)
    manager = open_on(px, doc, plane)
    data = model_to_sketch(call(manager, "ActiveSketch"))
    cx, w, h = RECT_X * k, RECT_W * k, RECT_H * k
    corners = [(cx - w / 2, -h / 2, z), (cx + w / 2, -h / 2, z), (cx + w / 2, h / 2, z), (cx - w / 2, h / 2, z)]
    _polyline(manager, data, corners)
    return sc.close_sketch(px, doc, name, before)


@probe("loft_cut_sections", needs=("extrude", "ref_plane_offset", "cut"), tier=2,
       members=("IFeatureManager.InsertCutBlend",))
def loft_cut_sections(px: Px) -> None:
    """A cut lofted between two similar rectangles on parallel planes removes exactly their frustum."""
    with sc.scratch(px) as doc:
        _loft_blank(px, doc)
        blank = _volume(doc)
        heel_plane = offset_plane(px, doc, HEEL_Z, flip=False)
        toe_plane = offset_plane(px, doc, TOE_Z, flip=False)
        heel = _rectangle_sketch(px, doc, heel_plane, "Heel Sketch", HEEL_Z)
        toe = _rectangle_sketch(px, doc, toe_plane, "Toe Sketch", TOE_Z)
        made = None
        for label, order in (("heel then toe, mark 1", (heel, toe)), ("toe then heel, mark 1", (toe, heel))):
            call(doc, "ClearSelection2", True)
            px.require(sc.select_feature(doc, sc.feature_by_name(doc, order[0]), mark=1) and
                       sc.select_feature(doc, sc.feature_by_name(doc, order[1]), append=True, mark=1),
                       f"{label}: both sections select")
            got, made = px.attempt(f"InsertCutBlend [{label}]",
                                   lambda: call(sc.feature_manager(doc), "InsertCutBlend", *cut_blend_args()))
            call(doc, "ClearSelection2", True)
            if got and made is not None:
                px.fact("loft_cut_route", label)
                break
        px.require(made is not None, "a lofted cut is made")
        px.fact("loft_cut_type", sc.type_name(made))
        removed = blank - _volume(doc)
        k = (TOE_Z - APEX_Z) / (HEEL_Z - APEX_Z)
        expected = (HEEL_Z - TOE_Z) * RECT_W * RECT_H * (1.0 + k + k * k) / 3.0
        px.fact("loft_cut_removed_mm3", {"removed": removed, "frustum": expected})
        px.check(abs(removed - expected) < 1e-4 * expected,
                 f"the loft removes {removed:.4f} mm³, the frustum's {expected:.4f}")
        px.check(solid_bodies(doc) == 1, "one solid body")
        dims = [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in sc.dimensions_of(made)]
        px.fact("loft_cut_dimensions", dims)


def _body_blank(px: Px, doc: Any) -> None:
    before = sc.feature_names(doc)
    manager = sc.open_sketch(px, doc, 1)
    call(manager, "CreateCircleByRadius", BODY_X / sc.MM, 0.0, 0.0, BODY_R / sc.MM)
    sketch = sc.close_sketch(px, doc, "Body Sketch", before)
    px.require(sc.select_feature(doc, sc.feature_by_name(doc, sketch)), "the body sketch selects")
    made = call(sc.feature_manager(doc), "FeatureExtrusion3", *_extrude_args(BODY_W / sc.MM))
    call(doc, "ClearSelection2", True)
    px.require(made is not None, "the body is extruded")


def _select_body(px: Px, doc: Any, mark: int) -> bool:
    bodies = call(doc, "GetBodies2", 0, True)
    if not bodies:
        return False
    call(doc, "ClearSelection2", True)
    data = call(call(doc, "SelectionManager"), "CreateSelectData")
    data.Mark = mark
    return bool(call(bodies[0], "Select2", False, data)) and sc.selected_count(doc) > 0


@probe("move_body_rotate", needs=("extrude", "center_of_mass", "dimension_link"), tier=2,
       members=("IFeatureManager.InsertMoveCopyBody2", "IBody2.Select2"))
def move_body_rotate(px: Px) -> None:
    """A body turned about Y by InsertMoveCopyBody2: its centre of mass turns, and the turn follows a global."""
    start = (BODY_X, 0.0, BODY_W / 2.0)
    with sc.scratch(px) as doc:
        _body_blank(px, doc)
        made = None
        before = sc.feature_names(doc)
        for mark in (1, 0, 2):
            px.require(_select_body(px, doc, mark), f"the body selects at mark {mark}")
            got, made = px.attempt(
                f"InsertMoveCopyBody2 turn {TURN:g}° about Y, body at mark {mark}",
                lambda: call(sc.feature_manager(doc), "InsertMoveCopyBody2", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                             0.0, math.radians(TURN), 0.0, False, 1))
            call(doc, "ClearSelection2", True)
            if got and made is not None:
                px.fact("move_body_mark", mark)
                break
        px.require(made is not None, "a move body feature is made")
        new = sc.new_features(doc, before)
        px.fact("move_body_features", new)
        feature = sc.feature_by_name(doc, new[-1][0])
        px.fact("move_body_type", sc.type_name(feature))
        centre = centre_of_mass_mm(doc)
        want = rotate_y(TURN, start)
        px.fact("move_body_centre_mm", {"got": centre, "want": want})
        sign = 1 if math.dist(centre, want) < 1e-3 else (-1 if math.dist(centre, rotate_y(-TURN, start)) < 1e-3 else 0)
        px.fact("move_body_turn_sign", sign)
        px.require(sign != 0, f"the body's centre of mass turned about Y by {TURN:g}° one way or the other: {centre}")
        dims = sc.dimensions_of(feature)
        values = [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in dims]
        px.fact("move_body_dimensions", values)
        turn = [d for d in dims if abs(abs(float(call(d, "SystemValue"))) - math.radians(TURN)) < 1e-9]
        px.fact("move_body_turn_is_dimension", len(turn) == 1)
        if len(turn) != 1:
            # On SolidWorks 2026 the feature carried no dimension at all, so no
            # equation can drive the turn; the bevel recipe does not use it.
            px.note("the turn is not a dimension, so a global cannot drive it")
            return
        turn[0].Name = "Tilt"
        name = str(call(turn[0], "Name"))
        px.check(name == "Tilt", "the turn's dimension renames to Tilt")
        feature_name = str(call(feature, "Name"))
        add = adder(px, call(doc, "GetEquationMgr"))
        px.require(add(f'"Probe Tilt"= {TURN_LINKED:g}') >= 0, "a tilt global is added")
        px.require(add(f'"Tilt@{feature_name}"= "Probe Tilt"') >= 0, f'the link "Tilt@{feature_name}" is accepted')
        call(doc, "ForceRebuild3", False)
        centre = centre_of_mass_mm(doc)
        want = rotate_y(sign * TURN_LINKED, start)
        px.fact("move_body_centre_linked_mm", {"got": centre, "want": want})
        px.check(math.dist(centre, want) < 1e-3, f"linked to {TURN_LINKED:g}° the body turns with it: {centre}")


@probe("axis_from_sketch_line", needs=("axis", "path_sketch_relations", "dimensions", "dimension_link"), tier=2,
       members=("IModelDoc2.InsertAxis2", "IRefAxis.GetRefAxisParams", "IModelDocExtension.SelectByID2"))
def axis_from_sketch_line(px: Px) -> None:
    """A reference axis made from a sketch line lies along it, and follows the line's linked angle."""
    with sc.scratch(px) as doc:
        with sc.quiet_dimensions(px):
            before = sc.feature_names(doc)
            manager = open_on(px, doc, sc.planes(doc)[1])
            data = model_to_sketch(call(manager, "ActiveSketch"))
            o = _sketch_point(data, (0.0, 0.0, 0.0))
            up = _sketch_point(data, (0.0, 0.0, 30.0))
            tilted = _sketch_point(data, (-30.0 * math.sin(math.radians(TILT)), 0.0, 30.0 * math.cos(math.radians(TILT))))
            vertical = call(manager, "CreateCenterLine", o[0], o[1], 0.0, up[0], up[1], 0.0)
            line = call(manager, "CreateLine", o[0], o[1], 0.0, tilted[0], tilted[1], 0.0)
            px.require(vertical is not None and line is not None, "the two lines are made")
            origin = sc.origin_point(doc)
            sc.relate(doc, "sgCOINCIDENT", call(vertical, "GetStartPoint2"), origin)
            sc.relate(doc, "sgCOINCIDENT", call(line, "GetStartPoint2"), origin)
            sc.relate(doc, "sgVERTICAL2D", vertical)
            sc.select(doc, line, vertical)
            # Inside the 30° between the two lines, 15 mm out, given in model coordinates.
            inside = (-15.0 * math.sin(math.radians(TILT / 2.0)), 0.0, 15.0 * math.cos(math.radians(TILT / 2.0)))
            display = call(doc, "AddDimension2", inside[0] / sc.MM, inside[1] / sc.MM, inside[2] / sc.MM)
            call(doc, "ClearSelection2", True)
            px.require(display is not None, "an angle dimension between the lines is made")
            dimension = call(display, "GetDimension2", 0)
            dimension.Name = "Tilt"
            read = math.degrees(float(call(dimension, "SystemValue")))
            px.fact("line_angle_dimension_value_deg", read)
            px.fact("angle_dimension_placed_in_model_space_reads_the_angle", abs(read - TILT) < 1e-6)
            px.check(abs(read - TILT) < 1e-6, f"placed inside the angle in model space, it reads {read:.6f}°")
            line_name = _segment_name(line)
            sketch = sc.close_sketch(px, doc, "Axis Line Sketch", before)
        px.fact("line_segment_name", line_name)
        px.require(_select_segment(doc, sketch, line_name, False, 0), f"{line_name}@{sketch} selects")
        before = sc.feature_names(doc)
        made = call(doc, "InsertAxis2", True)
        call(doc, "ClearSelection2", True)
        new = [n for n, t in sc.new_features(doc, before) if t == "RefAxis"]
        px.require(bool(made) and len(new) == 1, "InsertAxis2 makes one axis from the line")
        axis = sc.feature_by_name(doc, new[0])

        def direction() -> Vec:
            params = [float(v) for v in call(call(axis, "GetSpecificFeature2"), "GetRefAxisParams")]
            d = (params[3] - params[0], params[4] - params[1], params[5] - params[2])
            n = math.sqrt(sum(v * v for v in d))
            return (d[0] / n, d[1] / n, d[2] / n)

        want = (-math.sin(math.radians(TILT)), 0.0, math.cos(math.radians(TILT)))
        got = direction()
        px.fact("axis_direction", got)
        px.check(abs(abs(sum(a * b for a, b in zip(got, want))) - 1.0) < 1e-9, f"the axis lies along the line: {got}")
        add = adder(px, call(doc, "GetEquationMgr"))
        px.require(add('"Probe Axis Tilt"= 50') >= 0, "a tilt global is added")
        px.require(add(f'"Tilt@{sketch}"= "Probe Axis Tilt"') >= 0, "the angle dimension links")
        call(doc, "ForceRebuild3", False)
        got = direction()
        want = (-math.sin(math.radians(50.0)), 0.0, math.cos(math.radians(50.0)))
        px.fact("axis_direction_linked", got)
        px.check(abs(abs(sum(a * b for a, b in zip(got, want))) - 1.0) < 1e-9, f"linked to 50° the axis follows: {got}")


def plane_frame(px: Px, doc: Any, plane: Any) -> Tuple[Vec, Vec, Vec, Vec]:
    """Where a plane's sketch is in model space: its origin in mm, and its x, y and normal as unit vectors."""
    from .p2_helical import sketch_to_model  # noqa: PLC0415

    before = sc.feature_names(doc)
    manager = open_on(px, doc, plane)
    data = sketch_to_model(call(manager, "ActiveSketch"))
    sc.close_sketch(px, doc, "Probe Frame", before, allow_empty=True)
    origin = transform_point(data, (0.0, 0.0, 0.0))

    def axis(v: Vec) -> Vec:
        tip = transform_point(data, v)
        d = (tip[0] - origin[0], tip[1] - origin[1], tip[2] - origin[2])
        n = math.sqrt(sum(c * c for c in d))
        return (d[0] / n, d[1] / n, d[2] / n)

    return (origin[0] * sc.MM, origin[1] * sc.MM, origin[2] * sc.MM), axis((1.0, 0.0, 0.0)), axis((0.0, 1.0, 0.0)), \
        axis((0.0, 0.0, 1.0))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@probe("ref_plane_normal", needs=("path_sketch_relations", "dimensions", "dimension_link", "ref_plane_offset"), tier=2,
       members=("IFeatureManager.InsertRefPlane", "ISketch.ModelToSketchTransform", "IModelDocExtension.SelectByID2"))
def ref_plane_normal(px: Px) -> None:
    """A plane square to a sketch line through its end: its sketch frame in model space, before and after the line moves."""
    with sc.scratch(px) as doc:
        cone, length = 30.0, 40.0
        with sc.quiet_dimensions(px):
            before = sc.feature_names(doc)
            manager = open_on(px, doc, sc.planes(doc)[1])
            data = model_to_sketch(call(manager, "ActiveSketch"))
            o = _sketch_point(data, (0.0, 0.0, 0.0))
            up = _sketch_point(data, (0.0, 0.0, 50.0))
            end_model = (length * math.sin(math.radians(cone)), 0.0, length * math.cos(math.radians(cone)))
            end = _sketch_point(data, end_model)
            vertical = call(manager, "CreateCenterLine", o[0], o[1], 0.0, up[0], up[1], 0.0)
            line = call(manager, "CreateLine", o[0], o[1], 0.0, end[0], end[1], 0.0)
            px.require(vertical is not None and line is not None, "the axis and the generatrix are drawn")
            origin = sc.origin_point(doc)
            sc.relate(doc, "sgCOINCIDENT", call(vertical, "GetStartPoint2"), origin)
            sc.relate(doc, "sgCOINCIDENT", call(line, "GetStartPoint2"), origin)
            sc.relate(doc, "sgVERTICAL2D", vertical)
            sc.select(doc, line, vertical)
            inside = (15.0 * math.sin(math.radians(cone / 2.0)), 0.0, 15.0 * math.cos(math.radians(cone / 2.0)))
            angle = call(call(doc, "AddDimension2", inside[0] / sc.MM, inside[1] / sc.MM, inside[2] / sc.MM),
                         "GetDimension2", 0)
            call(doc, "ClearSelection2", True)
            angle.Name = "Cone"
            sc.select(doc, line)
            size = call(call(doc, "AddDimension2", (end_model[0] + 5) / sc.MM, 0.0, end_model[2] / sc.MM),
                        "GetDimension2", 0)
            call(doc, "ClearSelection2", True)
            size.Name = "Heel"
            px.fact("cone_dimensions_deg_mm", (math.degrees(float(call(angle, "SystemValue"))),
                                               float(call(size, "SystemValue")) * sc.MM))
            line_name = _segment_name(line)
            sketch = sc.close_sketch(px, doc, "Cone Sketch", before)
        px.require(_select_segment(doc, sketch, line_name, False, 0), f"{line_name}@{sketch} selects at mark 0")
        count = sc.selected_count(doc)
        picked = call(sc.extension(doc), "SelectByID2", "", "EXTSKETCHPOINT", end_model[0] / sc.MM, 0.0,
                      end_model[2] / sc.MM, True, 1, sc.null(), 0)
        px.require(bool(picked) and sc.selected_count(doc) > count, "the line's end selects at mark 1 by its location")
        before = sc.feature_names(doc)
        made = call(sc.feature_manager(doc), "InsertRefPlane", 2, 0.0, 4, 0.0, 0, 0.0)
        call(doc, "ClearSelection2", True)
        new = [n for n, t in sc.new_features(doc, before) if t == "RefPlane"]
        px.require(made is not None and len(new) == 1, "InsertRefPlane(perpendicular 2, coincident 4) makes one plane")
        plane = sc.feature_by_name(doc, new[0])
        px.fact("ref_plane_normal_dimensions", [(str(call(d, "Name")), float(call(d, "SystemValue")))
                                                for d in sc.dimensions_of(plane)])

        def measure(label: str, cone_deg: float, length_mm: float) -> Dict[str, float]:
            origin_mm, ex, ey, ez = plane_frame(px, doc, plane)
            g = (math.sin(math.radians(cone_deg)), 0.0, math.cos(math.radians(cone_deg)))
            outward = (math.cos(math.radians(cone_deg)), 0.0, -math.sin(math.radians(cone_deg)))
            signs = {"x_along_outward": _dot(ex, outward), "y_along_plus_y": _dot(ey, (0.0, 1.0, 0.0)),
                     "normal_along_line": _dot(ez, g)}
            px.fact(f"ref_plane_normal_frame_{label}", {"origin_mm": origin_mm, "x": ex, "y": ey, "normal": ez, **signs})
            want_origin = tuple(length_mm * c for c in g)
            px.check(math.dist(origin_mm, want_origin) < 1e-6,
                     f"{label}: the sketch origin is the line's end {want_origin}: {origin_mm}")
            px.check(all(abs(abs(v) - 1.0) < 1e-9 for v in signs.values()),
                     f"{label}: the sketch's x, y and normal are the outward radial, Y and the line, each one way or the other",
                     signs)
            return signs

        first = measure("30", cone, length)
        add = adder(px, call(doc, "GetEquationMgr"))
        px.require(add('"Probe Cone"= 50') >= 0 and add('"Probe Heel"= 45') >= 0, "the cone globals are added")
        px.require(add(f'"Cone@{sketch}"= "Probe Cone"') >= 0 and add(f'"Heel@{sketch}"= "Probe Heel"') >= 0,
                   "the angle and the length link")
        call(doc, "ForceRebuild3", False)
        second = measure("50", 50.0, 45.0)
        px.fact("ref_plane_normal_signs", {k: round(v) for k, v in first.items()})
        px.check({k: round(v) for k, v in first.items()} == {k: round(v) for k, v in second.items()},
                 "the plane's sketch keeps the same frame when the line moves", (first, second))
