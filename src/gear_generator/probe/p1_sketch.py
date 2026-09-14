"""Tier 1, part two: units, sketches, entities, relations and dimensions.

Recipe B is built from nothing but these, and Recipe A's fillets and lines are
too. Every relation is checked by where the geometry ends up, not by whether
the call returned: a relation that silently did nothing looks exactly like one
that worked until the part is measured.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, Optional, Tuple

from ..swcom import call
from . import scaffold as sc
from .harness import Px, probe
from .p1_equations import adder, delete_from

Point = Tuple[float, float]


def _close(a: Optional[Point], b: Point, tol: float = 1e-6) -> bool:
    return a is not None and math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _point(px: Px, label: str, entity: Any, member: str) -> Optional[Point]:
    got, point = px.attempt(f"{label}.{member}", lambda: call(entity, member))
    return sc.point_mm(point) if got and point is not None else None


def _ends(entity: Any) -> Tuple[Point, Point]:
    return sc.point_mm(call(entity, "GetStartPoint2")), sc.point_mm(call(entity, "GetEndPoint2"))


@probe("document_units", needs=("new_document",), tier=1,
       members=("IModelDocExtension.GetUserPreferenceInteger", "IModelDocExtension.SetUserPreferenceInteger"))
def document_units(px: Px) -> None:
    """What length unit a new part is in, from each template, and whether it can be set.

    Equations are in document units, so a link from a global of 40.5 is 40.5 mm
    only in a millimetre document. Later probes use a millimetre template.
    """
    candidates = [("default", sc.template(px))]
    fallback = sc.FALLBACK_TEMPLATES[sc.SW_DOC_PART]
    if fallback.lower() != candidates[0][1].lower() and os.path.isfile(fallback):
        candidates.append(("2026 folder", fallback))
    units: Dict[str, Dict[str, Any]] = {}
    set_works = False
    for label, path in candidates:
        with sc.scratch(px, path=path) as doc:
            ext = sc.extension(doc)
            linear = int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, sc.SW_DETAILING_NO_OPTION))
            system = int(call(ext, "GetUserPreferenceInteger", sc.SW_UNIT_SYSTEM, sc.SW_DETAILING_NO_OPTION))
            units[label] = {"path": path, "linear": linear, "system": system}
            px.fact(f"units_{label.replace(' ', '_')}", units[label])
            if linear != sc.SW_MM:
                got, returned = px.attempt(
                    "SetUserPreferenceInteger(swUnitSystem, 0, swUnitSystem_MMGS)",
                    lambda: call(ext, "SetUserPreferenceInteger", sc.SW_UNIT_SYSTEM, sc.SW_DETAILING_NO_OPTION,
                                 sc.SW_UNIT_SYSTEM_MMGS),
                )
                after = int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, sc.SW_DETAILING_NO_OPTION))
                px.fact(f"set_mmgs_{label.replace(' ', '_')}", {"returned": returned if got else "raised",
                                                               "linear_after": after})
                set_works = set_works or after == sc.SW_MM
    mm_templates = [u["path"] for u in units.values() if u["linear"] == sc.SW_MM]
    px.fact("mm_templates", mm_templates)
    px.fact("default_template_is_mm", units["default"]["linear"] == sc.SW_MM)
    px.fact("set_mmgs_works", set_works)
    if mm_templates:
        px.shared["part_template"] = mm_templates[0]
    px.require(bool(mm_templates) or set_works, "a new part can be had in millimetres")


@probe("sketch_open_close", needs=("document_units",), tier=1,
       members=("IFeature.Select2", "ISketchManager.InsertSketch", "ISketchManager.ActiveSketch",
                "ISketchManager.AddToDB", "ISketchManager.CreateCircleByRadius", "IFeature.Name",
                "IModelDocExtension.SelectByID2"))
def sketch_open_close(px: Px) -> None:
    """A sketch opens on a plane chosen by tree order, closes, and takes its name."""
    with sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        first = sc.planes(doc)[0]
        call(doc, "ClearSelection2", True)
        got, returned = px.attempt("IFeature.Select2(False, 0) on the first RefPlane", lambda: call(first, "Select2", False, 0))
        px.fact("select2_plane", {"returned": returned if got else "raised", "selected": sc.selected_count(doc)})
        call(doc, "ClearSelection2", True)
        plane_name = str(call(first, "Name"))
        got, returned = px.attempt(f'SelectByID2("{plane_name}", "PLANE", ...) with the name read from the tree',
                                   lambda: call(sc.extension(doc), "SelectByID2", plane_name, "PLANE", 0.0, 0.0, 0.0,
                                                False, 0, sc.null(), 0))
        px.fact("select_by_id2_plane_tree_name", {"returned": returned if got else "raised",
                                                   "selected": sc.selected_count(doc)})
        px.check(sc.select_plane(doc, 1), "the first RefPlane in tree order can be selected by one of the two routes")
        manager = sc.sketch_manager(doc)
        manager.AddToDB = True
        px.fact("add_to_db_reads_back", bool(call(manager, "AddToDB")))
        call(manager, "InsertSketch", True)
        px.require(call(manager, "ActiveSketch") is not None, "InsertSketch(True) opens a sketch")
        px.check(call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, 0.01) is not None,
                 "CreateCircleByRadius returns the new segment")
        name = sc.close_sketch(px, doc, "Probe Sketch", before)
        px.check(call(manager, "ActiveSketch") is None, "a second InsertSketch(True) closes it")
        px.check(name == "Probe Sketch", f"the new sketch feature renames and reads back {name!r}")

        before = sc.feature_names(doc)
        sc.open_sketch(px, doc, 1)
        call(manager, "CreatePoint", 0.001, 0.001, 0.0)
        collided = sc.close_sketch(px, doc, "Probe Sketch", before)
        px.fact("rename_onto_taken_name_reads_back", collided)
        px.check(collided != "Probe Sketch", "renaming onto a taken name does not take it, and read-back shows so")

        call(doc, "ClearSelection2", True)
        px.fact("select_routes_used", dict(sc.SELECT_ROUTES))


@probe("sketch_entities", needs=("sketch_open_close",), tier=1,
       members=("ISketchManager.CreateCircle", "ISketchManager.CreateArc", "ISketchManager.Create3PointArc",
                "ISketchManager.CreateLine", "ISketchManager.CreateCenterLine", "ISketchManager.CreatePoint",
                "ISketchSegment.ConstructionGeometry", "ISketchSegment.GetType", "ISketchSegment.GetLength",
                "ISketchArc.GetCenterPoint2", "ISketchArc.GetRadius", "ISketchLine.GetStartPoint2",
                "ISketch.GetSketchSegments"))
def sketch_entities(px: Px) -> None:
    """Every entity the recipes draw, made where asked and read back in metres."""
    with sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)

        circle = call(manager, "CreateCircleByRadius", 0.010, 0.020, 0.0, 0.005)
        px.require(circle is not None, "CreateCircleByRadius makes a circle")
        px.fact("circle_segment_type", int(call(circle, "GetType")))
        centre = _point(px, "circle", circle, "GetCenterPoint2")
        px.check(_close(centre, (10.0, 20.0)), f"a circle's centre reads back from the segment itself: {centre}")
        got, radius = px.attempt("circle.GetRadius", lambda: call(circle, "GetRadius"))
        px.check(got and abs(float(radius) - 0.005) < 1e-12, "GetRadius reads the radius in metres")

        second = call(manager, "CreateCircle", 0.050, 0.0, 0.0, 0.056, 0.0, 0.0)
        got, radius = px.attempt("CreateCircle(centre, point).GetRadius", lambda: call(second, "GetRadius"))
        px.check(got and abs(float(radius) - 0.006) < 1e-12, "CreateCircle takes a centre and a point on it")

        for direction, sweep in ((1, math.pi / 2), (-1, 3 * math.pi / 2)):
            arc = call(manager, "CreateArc", 0.0, 0.0, 0.0, 0.030, 0.0, 0.0, 0.0, 0.030, 0.0, direction)
            got, length = px.attempt(f"CreateArc direction {direction:+d}.GetLength", lambda: call(arc, "GetLength"))
            start, end = _ends(arc)
            px.fact(f"arc_direction_{direction:+d}", {"length_mm": float(length) * 1000 if got else None,
                                                      "start": start, "end": end})
            px.check(got and abs(float(length) * 1000 - 30 * sweep) < 1e-6,
                     f"CreateArc with direction {direction:+d} runs {'counter-clockwise' if direction > 0 else 'clockwise'}"
                     " from its start")

        three = call(manager, "Create3PointArc", 0.080, 0.0, 0.0, 0.100, 0.0, 0.0, 0.090, 0.010, 0.0)
        centre = _point(px, "three-point arc", three, "GetCenterPoint2")
        px.check(_close(centre, (90.0, 0.0)), f"Create3PointArc passes through its three points: centre {centre}")

        line = call(manager, "CreateLine", 0.001, 0.002, 0.0, 0.031, 0.042, 0.0)
        start, end = _ends(line)
        px.check(_close(start, (1.0, 2.0)) and _close(end, (31.0, 42.0)), f"a line's ends read back: {start}, {end}")
        px.check(abs(float(call(line, "GetLength")) - 0.050) < 1e-12, "GetLength is in metres")
        px.fact("line_segment_type", int(call(line, "GetType")))

        centreline = call(manager, "CreateCenterLine", 0.0, -0.01, 0.0, 0.04, -0.01, 0.0)
        px.fact("centreline_is_construction", bool(call(centreline, "ConstructionGeometry")))
        line.ConstructionGeometry = True
        px.check(bool(call(line, "ConstructionGeometry")), "ConstructionGeometry sets and reads back on a line")

        point = call(manager, "CreatePoint", 0.070, 0.080, 0.0)
        px.check(_close(sc.point_mm(point), (70.0, 80.0)), "CreatePoint puts a point where asked")

        name = sc.close_sketch(px, doc, "Probe Entities", before)
        segments = call(sc.sketch_of(doc, name), "GetSketchSegments") or ()
        px.fact("segments_after_close", len(segments))
        px.check(len(segments) == 7, "all seven segments are still in the sketch once it is closed")


@probe("relations", needs=("sketch_entities",), tier=1,
       members=("IModelDoc2.SketchAddConstraints", "ISketchSegment.Select4", "ISketchPoint.Select4",
                "ISketch.GetSketchPoints2"))
def relations(px: Px) -> None:
    """Coincident, point-on-curve, line-through-origin, tangent, symmetric, equal, horizontal."""
    with sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        origin = sc.origin_point(doc)
        px.fact("origin_point_mm", sc.point_mm(origin))

        line = call(manager, "CreateLine", 0.004, 0.003, 0.0, 0.030, 0.010, 0.0)
        sc.relate(doc, "sgCOINCIDENT", call(line, "GetStartPoint2"), origin)
        start, end = _ends(line)
        px.check(_close(start, (0.0, 0.0)), f"sgCOINCIDENT pulls a line's start onto the origin: {start}")
        sc.relate(doc, "sgHORIZONTAL2D", line)
        start, end = _ends(line)
        px.check(abs(start[1] - end[1]) < 1e-6, f"sgHORIZONTAL2D levels the line: {start} {end}")

        radial = call(manager, "CreateLine", 0.020, 0.030, 0.0, 0.040, 0.050, 0.0)
        sc.relate(doc, "sgCOINCIDENT", origin, radial)
        start, end = _ends(radial)
        cross = start[0] * end[1] - start[1] * end[0]
        px.check(abs(cross) < 1e-6, f"the origin and a line made coincident put the origin on the line's extension: {start} {end}")

        circle = call(manager, "CreateCircleByRadius", 0.080, 0.0, 0.0, 0.010)
        free = call(manager, "CreatePoint", 0.095, 0.004, 0.0)
        sc.relate(doc, "sgCOINCIDENT", free, circle)
        where = sc.point_mm(free)
        centre = sc.point_mm(call(circle, "GetCenterPoint2"))
        px.check(abs(math.hypot(where[0] - centre[0], where[1] - centre[1]) - 10.0) < 1e-6,
                 f"sgCOINCIDENT puts a point on a circle: {where}")

        arc = call(manager, "CreateArc", 0.0, -0.050, 0.0, 0.010, -0.050, 0.0, -0.010, -0.050, 0.0, 1)
        tangent = call(manager, "CreateLine", -0.020, -0.037, 0.0, 0.020, -0.037, 0.0)
        sc.relate(doc, "sgTANGENT", tangent, arc)
        start, end = _ends(tangent)
        centre = sc.point_mm(call(arc, "GetCenterPoint2"))
        radius = float(call(arc, "GetRadius")) * sc.MM
        dx, dy = end[0] - start[0], end[1] - start[1]
        distance = abs(dx * (centre[1] - start[1]) - dy * (centre[0] - start[0])) / math.hypot(dx, dy)
        px.check(abs(distance - radius) < 1e-6, f"sgTANGENT makes the line touch the arc: {distance} vs {radius}")

        mirror = call(manager, "CreateCenterLine", 0.150, 0.0, 0.0, 0.150, 0.050, 0.0)
        left = call(manager, "CreatePoint", 0.140, 0.020, 0.0)
        right = call(manager, "CreatePoint", 0.163, 0.021, 0.0)
        sc.relate(doc, "sgSYMMETRIC", left, right, mirror)
        a, b = sc.point_mm(left), sc.point_mm(right)
        px.check(abs(a[0] + b[0] - 300.0) < 1e-6 and abs(a[1] - b[1]) < 1e-6,
                 f"sgSYMMETRIC mirrors two points about a centreline: {a} {b}")

        small = call(manager, "CreateCircleByRadius", 0.200, 0.0, 0.0, 0.004)
        large = call(manager, "CreateCircleByRadius", 0.230, 0.0, 0.0, 0.007)
        got, _ = px.attempt("sgEQUAL on two circles", lambda: sc.relate(doc, "sgEQUAL", small, large))
        radii = (float(call(small, "GetRadius")), float(call(large, "GetRadius")))
        px.fact("sgEQUAL_radii_after", radii, f"after sgEQUAL the radii are {radii}")
        equal_routes = ["sgEQUAL"] if abs(radii[0] - radii[1]) < 1e-9 else []
        if not equal_routes:
            sc.relate(doc, "sgSAMELENGTH", small, large)
            radii = (float(call(small, "GetRadius")), float(call(large, "GetRadius")))
            if abs(radii[0] - radii[1]) < 1e-9:
                equal_routes.append("sgSAMELENGTH")
        px.fact("equal_radius_constraint", equal_routes[0] if equal_routes else None)
        px.check(bool(equal_routes), f"some constant makes two radii equal: {equal_routes} {radii}")

        centred = call(manager, "CreateArc", 0.060, 0.060, 0.0, 0.070, 0.060, 0.0, 0.060, 0.070, 0.0, 1)
        sc.relate(doc, "sgCOINCIDENT", call(centred, "GetCenterPoint2"), circle)
        centre = sc.point_mm(call(centred, "GetCenterPoint2"))
        on = sc.point_mm(call(circle, "GetCenterPoint2"))
        px.check(abs(math.hypot(centre[0] - on[0], centre[1] - on[1]) - 10.0) < 1e-6,
                 f"an arc's centre point goes onto a circle: {centre}")

        sc.close_sketch(px, doc, "Probe Relations", before)
        px.fact("select_routes_so_far", dict(sc.SELECT_ROUTES))


@probe("dimensions", needs=("relations",), tier=1,
       members=("IModelDoc2.AddDimension2", "IDisplayDimension.GetDimension2", "IDimension.Name",
                "IDimension.FullName", "IDimension.SystemValue", "IFeature.GetFirstDisplayDimension",
                "IFeature.GetNextDisplayDimension", "ISldWorks.SetUserPreferenceToggle"))
def dimensions(px: Px) -> None:
    """Dimensions on a circle, an arc and an angle: what they measure, their names, their units."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)

        def dimension(entities, at, name):
            sc.select(doc, *entities)
            display = call(doc, "AddDimension2", at[0], at[1], 0.0)
            call(doc, "ClearSelection2", True)
            if not px.check(display is not None, f"AddDimension2 makes the {name} dimension"):
                return None
            made = call(display, "GetDimension2", 0)
            made.Name = name
            px.check(str(call(made, "Name")) == name, f"the {name} dimension renames and reads back")
            return made

        circle = call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, 0.010)
        od = dimension((circle,), (0.015, 0.015), "OD")
        if od is not None:
            value = float(call(od, "SystemValue"))
            kind = "diameter" if abs(value - 0.020) < 1e-9 else "radius" if abs(value - 0.010) < 1e-9 else "?"
            px.fact("circle_dimension_measures", kind, f"a circle's dimension reads {value!r} m: its {kind}")
            px.fact("full_name_while_open", str(call(od, "FullName")))
            od.SystemValue = 0.030
            px.check(abs(float(call(circle, "GetRadius")) - (0.015 if kind == "diameter" else 0.030)) < 1e-9,
                     "setting SystemValue in metres drives the circle")

        arc = call(manager, "CreateArc", 0.060, 0.0, 0.0, 0.070, 0.0, 0.0, 0.050, 0.0, 0.0, 1)
        radius = dimension((arc,), (0.060, 0.020), "R")
        if radius is not None:
            value = float(call(radius, "SystemValue"))
            kind = "radius" if abs(value - 0.010) < 1e-9 else "diameter" if abs(value - 0.020) < 1e-9 else "?"
            px.fact("arc_dimension_measures", kind, f"an arc's dimension reads {value!r} m: its {kind}")

        twenty = math.radians(20.0)
        base = call(manager, "CreateLine", 0.100, 0.0, 0.0, 0.130, 0.0, 0.0)
        leaning = call(manager, "CreateLine", 0.100, 0.0, 0.0, 0.100 + 0.030 * math.cos(twenty),
                       0.030 * math.sin(twenty), 0.0)
        mid = math.radians(10.0)
        angle = dimension((base, leaning), (0.100 + 0.020 * math.cos(mid), 0.020 * math.sin(mid)), "HalfSpace")
        if angle is not None:
            value = float(call(angle, "SystemValue"))
            px.fact("angle_dimension_system_value", value)
            px.check(abs(value - twenty) < 1e-9, f"an angle dimension's SystemValue is radians: {value!r}")

        name = sc.close_sketch(px, doc, "Probe Dims", before)
        feature = sc.feature_by_name(doc, name)
        names = [str(call(d, "Name")) for d in sc.dimensions_of(feature)]
        px.fact("dimension_names_after_close", names)
        px.check({"OD", "R", "HalfSpace"} <= set(names), "names set while the sketch was open survive closing it")
        if "OD" in names:
            px.fact("full_name_after_close", str(call(sc.dimension_named(feature, "OD"), "FullName")))


@probe("dimension_link", needs=("dimensions", "equation_set"), tier=1,
       members=("IEquationMgr.Add2", "IEquationMgr.Equation", "IDimension.SystemValue", "IModelDoc2.ForceRebuild3"))
def dimension_link(px: Px) -> None:
    """A dimension linked to a global follows it, in millimetres, after a rebuild."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        got, early = px.attempt('link before the dimension exists: "OD@Probe Link"= 30',
                                lambda: add('"OD@Probe Link"= 30'))
        px.fact("link_before_dimension_returns", early if got else "raised")
        if got and early >= 0:
            delete_from(eqm, early)

        global_index = add('"Probe D"= 30')
        px.require(global_index >= 0, "the global is added")

        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        circle = call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, 0.010)
        sc.select(doc, circle)
        display = call(doc, "AddDimension2", 0.015, 0.015, 0.0)
        call(doc, "ClearSelection2", True)
        made = call(display, "GetDimension2", 0)
        made.Name = "OD"
        sketch = sc.close_sketch(px, doc, "Probe Link", before)

        link = add(f'"OD@{sketch}"= "Probe D"')
        px.require(link >= 0, f'the link "OD@{sketch}"= "Probe D" is accepted once the dimension exists')
        px.fact("link_text_reads_back", str(call(eqm, "Equation", link)))
        call(doc, "ForceRebuild3", False)
        dim = sc.dimension_named(sc.feature_by_name(doc, sketch), "OD")
        value = float(call(dim, "SystemValue"))
        units = "mm" if abs(value - 0.030) < 1e-9 else "inch" if abs(value - 0.762) < 1e-9 else "?"
        px.fact("equation_length_units", units, f"a global of 30 drives the dimension to {value!r} m")
        px.check(units == "mm", "equations are in millimetres in this document")

        sc.put_indexed(eqm, "Equation", global_index, '"Probe D"= 40')
        call(doc, "ForceRebuild3", False)
        value = float(call(sc.dimension_named(sc.feature_by_name(doc, sketch), "OD"), "SystemValue"))
        px.check(abs(value - 0.040) < 1e-9, f"changing the global and rebuilding moves the dimension to {value!r} m")


@probe("constrained_status", needs=("dimensions",), tier=1, members=("ISketch.GetConstrainedStatus",))
def constrained_status(px: Px) -> None:
    """GetConstrainedStatus, calibrated on a sketch known to be under- then fully defined."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        sketch = call(manager, "ActiveSketch")
        line = call(manager, "CreateLine", 0.004, 0.003, 0.0, 0.030, 0.010, 0.0)
        under = int(call(sketch, "GetConstrainedStatus"))
        px.fact("status_free_line", under)
        sc.relate(doc, "sgCOINCIDENT", call(line, "GetStartPoint2"), sc.origin_point(doc))
        sc.relate(doc, "sgHORIZONTAL2D", line)
        sc.select(doc, line)
        call(doc, "AddDimension2", 0.015, 0.010, 0.0)
        call(doc, "ClearSelection2", True)
        full = int(call(sketch, "GetConstrainedStatus"))
        px.fact("status_defined_line", full)
        px.check(under == sc.SW_UNDER_CONSTRAINED, f"a free line reads {under} (swUnderConstrained is 2)")
        px.check(full == sc.SW_FULLY_CONSTRAINED, f"a line fixed at one end, level and dimensioned reads {full} "
                                                  "(swFullyConstrained is 3)")
        name = sc.close_sketch(px, doc, "Probe Status", before)
        after = int(call(sc.sketch_of(doc, name), "GetConstrainedStatus"))
        px.fact("status_after_close", after)
        px.check(after == full, "the closed sketch reports the same status through its feature")
