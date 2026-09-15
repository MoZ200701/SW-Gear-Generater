"""Tier 4: components on axes that are not parallel — placing them, and mating them there.

A bevel pair's axes meet at the shaft angle, and a crossed helical pair's pass
each other at it. Each probe here sets a component's whole frame, or mates it
into one, and then reads its ``Transform2`` back as the oracle: the rotation to
1e-6 and the origin to 1e-6 mm, so a mate that was satisfied the other way round
shows at once.

What is settled:

* how a component's frame is set from code (a math transform, and which order
  ``ArrayData`` holds the rotation in);
* how a component's origin is selected for a mate;
* whether an angle mate between two axes, and a distance mate from a point to a
  plane, are made by ``AddMate5`` and hold the frame;
* for a bevel-style frame — origins together, gear 2's axis in gear 1's top plane
  at the shaft angle, spun by a top-plane angle — and for a crossed-style one.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..gears import crossed
from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p4_assembly import (
    ALIGN_CLOSEST,
    MATE_ANGLE,
    MATE_COINCIDENT,
    MATE_DISTANCE,
    _mate,
    _mate_features,
    _part_with_axis,
    _plane_names,
    _select_in_component,
)

Matrix = Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]

IDENTITY: Matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
TOLERANCE_ROTATION = 1e-6
TOLERANCE_MM = 1e-6

BEVEL_SHAFT = 70.0
BEVEL_SPIN = 12.0
CROSSED_SHAFT = 90.0
CROSSED_SPIN = 7.0
CROSSED_CENTRE = 60.0
CROSSED_ORIGIN = (60.0, -8.0, 12.0)


def array_data(matrix: Matrix, at_mm: Sequence[float], order: str) -> List[float]:
    """The 16 numbers of an IMathTransform: rotation, translation in metres, scale, and three unused."""
    if order == "columns":
        rotation = [matrix[i][j] for j in range(3) for i in range(3)]
    else:
        rotation = [matrix[i][j] for i in range(3) for j in range(3)]
    return rotation + [at_mm[0] / sc.MM, at_mm[1] / sc.MM, at_mm[2] / sc.MM, 1.0, 0.0, 0.0, 0.0]


def frame_of(component: Any) -> Tuple[Matrix, Tuple[float, float, float]]:
    """A component's rotation (rows) and origin in mm, reading ``ArrayData`` as columns (SW-Macro-Database reading/05)."""
    data = [float(v) for v in call(call(component, "Transform2"), "ArrayData")]
    matrix = tuple(tuple(data[j * 3 + i] for j in range(3)) for i in range(3))
    return matrix, (data[9] * sc.MM, data[10] * sc.MM, data[11] * sc.MM)  # type: ignore[return-value]


def frame_error(component: Any, matrix: Matrix, at_mm: Sequence[float]) -> Tuple[float, float]:
    got, origin = frame_of(component)
    rotation = max(abs(got[i][j] - matrix[i][j]) for i in range(3) for j in range(3))
    return rotation, math.dist(origin, at_mm)


def make_transform(px: Px, data: List[float]) -> Any:
    utility = call(sc.app(px), "GetMathUtility")
    try:
        from win32com.client import VARIANT  # noqa: PLC0415 - Windows only
        import pythoncom  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise Require(f"pywin32 is needed to make a transform: {exc}")
    import win32com.client.dynamic as dynamic  # noqa: PLC0415

    def invoked(argument: Any) -> Any:
        # Late binding reached CreateTransform as a property get with an
        # argument, which SolidWorks answered "member not found"; invoke it as
        # the method the type library says it is.
        oleobj = utility._oleobj_  # noqa: SLF001
        dispid = oleobj.GetIDsOfNames("CreateTransform")
        raw = oleobj.Invoke(dispid, 0, pythoncom.DISPATCH_METHOD, True, argument)
        return dynamic.Dispatch(raw) if raw is not None and not hasattr(raw, "ArrayData") else raw

    array = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, data)
    for label, thunk in (
        ("list", lambda: call(utility, "CreateTransform", data)),
        ("VT_ARRAY|VT_R8", lambda: call(utility, "CreateTransform", array)),
        ("Invoke DISPATCH_METHOD, VT_ARRAY|VT_R8", lambda: invoked(array)),
        ("Invoke DISPATCH_METHOD, list", lambda: invoked(data)),
    ):
        got, transform = px.attempt(f"IMathUtility.CreateTransform({label})", thunk)
        if got and transform is not None:
            px.shared["create_transform_argument"] = label
            return transform
    raise Require("CreateTransform made no transform from any argument form.")


def place(px: Px, asm: Any, component: Any, matrix: Matrix, at_mm: Sequence[float]) -> Tuple[str, str]:
    """Set a component's frame, trying each route and array order until it reads back. Returns ``(route, order)``."""
    for order in ("columns", "rows"):
        transform = make_transform(px, array_data(matrix, at_mm, order))
        for route, thunk in (
            ("Transform2 put", lambda t=transform: setattr(component, "Transform2", t)),
            ("SetTransformAndSolve2", lambda t=transform: call(component, "SetTransformAndSolve2", t)),
        ):
            got, _ = px.attempt(f"{route} ({order})", thunk)
            call(asm, "ForceRebuild3", False)
            if not got:
                continue
            rotation, origin = frame_error(component, matrix, at_mm)
            px.note(f"{route} ({order}): rotation off by {rotation:.2e}, origin by {origin:.2e} mm")
            if rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM:
                return route, order
    raise Require("No route set the component's frame so that it read back.")


def _flipped_mate(px: Px, asm: Any, label: str, distance: float, flip: bool) -> Optional[str]:
    """A distance mate with AddMate5's Flip argument given; otherwise :func:`p4_assembly._mate`."""
    before = [n for n, _ in _mate_features(asm)]
    got, result = px.attempt(
        f"AddMate5 {label} (flip {flip})",
        lambda: call(asm, "AddMate5", MATE_DISTANCE, ALIGN_CLOSEST, flip, distance, distance, distance, 1, 1,
                     0.0, 0.0, 0.0, False, False, 0, sc.out_long()),
    )
    call(asm, "ClearSelection2", True)
    mate = result[0] if got and isinstance(result, tuple) else result
    made = [n for n, _ in _mate_features(asm) if n not in before]
    if not px.check(got and mate is not None and len(made) == 1, f"{label}: one mate appears under Mates"):
        return None
    return made[0]


def origin_name(part: Any) -> str:
    for feature in sc.top_features(part):
        if sc.type_name(feature) == "OriginProfileFeature":
            return str(call(feature, "Name"))
    raise Require("The part has no origin feature.")


def select_origin(px: Px, asm: Any, component: Any, part: Any, append: bool, mark: int = 1) -> str:
    """A component's origin, selected for a mate. Returns the route that selected it."""
    name = origin_name(part)
    asm_name = os.path.splitext(str(call(asm, "GetTitle")))[0]
    component_name = str(call(component, "Name2"))

    def by_id(kind: str, full: str):
        return lambda: call(sc.extension(asm), "SelectByID2", full, kind, 0.0, 0.0, 0.0, append, mark, sc.null(), 0)

    def corresponding():
        feature = call(component, "FeatureByName", name)
        point = call(call(feature, "GetSpecificFeature2"), "GetSketchPoints2")[0]
        entity = call(component, "GetCorresponding", point)
        data = call(call(asm, "SelectionManager"), "CreateSelectData")
        data.Mark = mark
        return call(entity, "Select4", append, data)

    routes = (
        ("SelectByID2 EXTSKETCHPOINT Point1@Origin", by_id("EXTSKETCHPOINT", f"Point1@{name}@{component_name}@{asm_name}")),
        ("GetCorresponding origin point, Select4", corresponding),
        ("SelectByID2 ORIGINFOLDER", by_id("ORIGINFOLDER", f"{name}@{component_name}@{asm_name}")),
    )
    for label, thunk in routes:
        if not append:
            call(asm, "ClearSelection2", True)
        before = sc.selected_count(asm)
        got, _ = px.attempt(f"select origin of {component_name}: {label}", thunk)
        if got and sc.selected_count(asm) > before:
            return label
    raise Require(f"The origin of {component_name} could not be selected by any route.")


def _assembly(px: Px, path_a: str, path_b: str) -> Tuple[Any, Any, Any]:
    asm = sc.new_document(px, sc.SW_DOC_ASSEMBLY)
    ext = sc.extension(asm)
    if int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, 0)) != sc.SW_MM:
        call(ext, "SetUserPreferenceInteger", sc.SW_UNIT_SYSTEM, 0, sc.SW_UNIT_SYSTEM_MMGS)
    first = call(asm, "AddComponent5", path_a, 0, "", False, "", 0.0, 0.0, 0.0)
    second = call(asm, "AddComponent5", path_b, 0, "", False, "", 0.0, 0.0, 0.0)
    if first is None or second is None:
        raise Require("AddComponent5 did not insert both parts.")
    return asm, first, second


def _dimension_names(asm: Any, mate_name: Optional[str]) -> List[Tuple[str, float]]:
    if mate_name is None:
        return []
    for feature in sc.top_features(asm):
        if sc.type_name(feature) == "MateGroup":
            child = call(feature, "GetFirstSubFeature")
            while child is not None:
                if str(call(child, "Name")) == mate_name:
                    return [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in sc.dimensions_of(child)]
                child = call(child, "GetNextSubFeature")
    return []


@probe("nonparallel_mates", needs=("assembly_components_and_mates",), tier=4,
       members=("IMathUtility.CreateTransform", "IComponent2.Transform2", "IComponent2.GetCorresponding",
                "IModelDocExtension.SelectByID2", "IAssemblyDoc.AddMate5"))
def nonparallel_mates(px: Px) -> None:
    """Set a component's frame, select its origin, and mate it onto non-parallel axes two ways, read back each time."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder), "there is a scratch folder to save parts in")
    part_a, path_a = _part_with_axis(px, folder, "Probe Skew A")
    part_b, path_b = _part_with_axis(px, folder, "Probe Skew B")
    planes = _plane_names(part_a)
    front, top, right = planes[0], planes[1], planes[2]
    try:
        # -- a bevel-style frame: origins together, axes at the shaft angle in the top plane
        bevel = crossed.multiply(crossed.rot_y(BEVEL_SHAFT), crossed.rot_z(BEVEL_SPIN))
        asm, first, second = _assembly(px, path_a, path_b)
        try:
            # AddComponent5 puts a component's middle, not its origin, at the point:
            # A is set to the assembly's own frame so B's frame reads back directly.
            place(px, asm, first, IDENTITY, (0.0, 0.0, 0.0))
            route, order = place(px, asm, second, bevel, (0.0, 0.0, 0.0))
            px.fact("place_route", route)
            px.fact("transform_array_order", order)
            px.fact("create_transform_argument", px.shared.get("create_transform_argument"))
            px.ok(f"a component's frame is set by {route} with ArrayData in {order}")

            selected = select_origin(px, asm, second, part_b, append=False)
            px.require(select_origin(px, asm, first, part_a, append=True) == selected,
                       "both origins select by the same route")
            px.fact("origin_select_route", selected)
            px.fact("origin_select_types", [int(call(call(asm, "SelectionManager"), "GetSelectedObjectType3", i, -1))
                                            for i in (1, 2)])
            point = _mate(px, asm, "bevel: origins coincident", MATE_COINCIDENT)
            px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                       _select_in_component(px, asm, first, top, "PLANE", True), "B's axis and A's top plane select")
            _mate(px, asm, "bevel: axis in top plane", MATE_COINCIDENT)
            px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                       _select_in_component(px, asm, first, "Gear Axis", "AXIS", True), "the two axes select")
            shaft = _mate(px, asm, "bevel: angle between axes", MATE_ANGLE, angle=math.radians(BEVEL_SHAFT))
            px.fact("axis_angle_mate_dimensions", _dimension_names(asm, shaft))
            px.require(_select_in_component(px, asm, second, top, "PLANE", False) and
                       _select_in_component(px, asm, first, top, "PLANE", True), "the two top planes select")
            _mate(px, asm, "bevel: spin by the top planes", MATE_ANGLE, angle=math.radians(BEVEL_SPIN))
            call(asm, "ForceRebuild3", False)
            rotation, origin = frame_error(second, bevel, (0.0, 0.0, 0.0))
            px.fact("bevel_frame_error", {"rotation": rotation, "origin_mm": origin,
                                          "mates": _mate_features(asm)})
            px.check(point is not None and shaft is not None, "the point and axis-angle mates are made")
            px.check(rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM,
                     f"mated, B holds the bevel frame (rotation off {rotation:.2e}, origin {origin:.2e} mm)")
        finally:
            sc.close(px, asm)

        # -- a crossed-style frame: axis at C from A's right plane, square to X, placed by two point distances
        tilt = crossed.rot_x(-CROSSED_SHAFT)
        skew = crossed.multiply(tilt, crossed.rot_z(CROSSED_SPIN))
        asm, first, second = _assembly(px, path_a, path_b)
        try:
            place(px, asm, first, IDENTITY, (0.0, 0.0, 0.0))
            place(px, asm, second, skew, CROSSED_ORIGIN)
            px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                       _select_in_component(px, asm, first, right, "PLANE", True), "B's axis and A's right plane select")
            centre = _mate(px, asm, "crossed: axis to right plane", MATE_DISTANCE, distance=CROSSED_CENTRE / sc.MM)
            px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                       _select_in_component(px, asm, first, "Gear Axis", "AXIS", True), "the two axes select")
            _mate(px, asm, "crossed: angle between axes", MATE_ANGLE, angle=math.radians(CROSSED_SHAFT))
            distances = {}
            # On the first run, without flipping, the origin 8 mm below Top went to 8 mm
            # above it: the distance was taken along the plane's normal. So a point on
            # a plane's negative side is mated with AddMate5's Flip set.
            for plane, value in ((top, CROSSED_ORIGIN[1]), (front, CROSSED_ORIGIN[2])):
                select_origin(px, asm, second, part_b, append=False)
                px.require(_select_in_component(px, asm, first, plane, "PLANE", True), f"A's {plane} selects")
                distances[plane] = _flipped_mate(px, asm, f"crossed: origin to {plane}", abs(value) / sc.MM,
                                                 flip=value < 0)
            px.fact("point_distance_mate_dimensions", {k: _dimension_names(asm, v) for k, v in distances.items()})
            spin_angle = crossed.angle_between(crossed.apply(skew, (0.0, 1.0, 0.0)), (1.0, 0.0, 0.0))
            px.fact("crossed_spin_mate_angle", spin_angle)
            px.require(_select_in_component(px, asm, second, top, "PLANE", False) and
                       _select_in_component(px, asm, first, right, "PLANE", True), "B's top and A's right planes select")
            _mate(px, asm, "crossed: spin by B's top to A's right", MATE_ANGLE, angle=math.radians(spin_angle))
            call(asm, "ForceRebuild3", False)
            rotation, origin = frame_error(second, skew, CROSSED_ORIGIN)
            px.fact("crossed_first_frame_error", frame_error(first, IDENTITY, (0.0, 0.0, 0.0)))
            px.fact("crossed_second_origin_mm", frame_of(second)[1])
            px.fact("point_distance_flip_below_plane", True)
            px.fact("crossed_frame_error", {"rotation": rotation, "origin_mm": origin, "mates": _mate_features(asm)})
            px.check(centre is not None and all(distances.values()), "the distance mates are made")
            px.check(rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM,
                     f"mated, B holds the crossed frame (rotation off {rotation:.2e}, origin {origin:.2e} mm)")
        finally:
            sc.close(px, asm)
    finally:
        for doc in (part_b, part_a):
            try:
                sc.close(px, doc)
            except Exception as exc:  # noqa: BLE001
                px.note(f"CLEANUP {exc}")
