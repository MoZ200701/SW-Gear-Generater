"""Tier 1 and 2 for helical and herringbone gears: twisted sweeps, offset planes, mirrored bodies.

A helical tooth space is the spur gear's transverse section swept along the
axis with a constant twist. Every question that build raises is settled here
on scratch parts, with the geometry itself as the oracle rather than a return
value:

* **volume** — a section swept straight or twisted along a line encloses the
  same volume, A·L, whatever the twist (Cavalieri), so a sweep that removed or
  added the wrong amount shows at once;
* **centre of mass** — a circle of radius r at distance r0 from the axis, turned
  uniformly through θ over the length, has its centroid at
  ``r0·(sin θ/θ, ±(1 − cos θ)/θ)``: the sign says which way the twist went and
  the size says the twist was uniform and in the units it was given in;
* **where a sketch is** — a sketch's own transform to model space, read as the
  columns SW-Macro-Database reading/05 says it is stored as, so a plane's
  position and a sketch's axes are measured, not assumed.

Every enum value used is from ``swconst.tlb`` and every arity from
``sldworks.tlb`` on SolidWorks 2026 (revision 34), read with pythoncom.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p1_equations import adder, delete_from
from .p2_solid import BLANK_R, BLANK_W, _blank, _volume

# swTwistControlType_e
TWIST_CONSTANT_ALONG_PATH = 8
# swRefPlaneReferenceConstraints_e
PLANE_DISTANCE = 8
PLANE_FLIP = 256
# swSweepDirection_e
SWEEP_DIRECTION_1 = 0
# swBodyType_e: swSolidBody
SOLID_BODY = 0
# swFeatureNameID_e
FM_SWEEP_CUT = 18

PROFILE_R = 3.0      # mm, the probe section: a circle this big ...
PROFILE_X = 12.0     # ... this far from the axis
SWEEP_L = 20.0       # mm, the length of a probe sweep
QUARTER = math.pi / 2.0

Vec = Tuple[float, float, float]


# -- measuring --------------------------------------------------------------


def transform_point(data: Sequence[float], point: Vec) -> Vec:
    """A point through an IMathTransform's ArrayData: rotation by columns (reading/05)."""
    r = [float(v) for v in data[:9]]
    tx, ty, tz = (float(v) for v in data[9:12])
    s = float(data[12]) if len(data) > 12 else 1.0
    x, y, z = point
    return (s * (r[0] * x + r[3] * y + r[6] * z) + tx,
            s * (r[1] * x + r[4] * y + r[7] * z) + ty,
            s * (r[2] * x + r[5] * y + r[8] * z) + tz)


def model_to_sketch(sketch: Any) -> List[float]:
    return [float(v) for v in call(call(sketch, "ModelToSketchTransform"), "ArrayData")]


def sketch_to_model(sketch: Any) -> List[float]:
    return [float(v) for v in call(call(call(sketch, "ModelToSketchTransform"), "Inverse"), "ArrayData")]


def mm(v: Vec) -> Vec:
    return (v[0] * sc.MM, v[1] * sc.MM, v[2] * sc.MM)


def centre_of_mass_mm(doc: Any) -> Vec:
    call(doc, "ForceRebuild3", False)
    props = call(sc.extension(doc), "CreateMassProperty")
    centre = call(props, "CenterOfMass")
    if centre is None or len(centre) < 3:
        raise Require(f"CenterOfMass returned {centre!r}.")
    return mm((float(centre[0]), float(centre[1]), float(centre[2])))


def solid_bodies(doc: Any) -> int:
    bodies = call(doc, "GetBodies2", SOLID_BODY, True)
    return len(bodies) if bodies else 0


def twisted_centroid(theta: float, r0: float = PROFILE_X) -> Tuple[float, float]:
    """``(x, |y|)`` of a circle's centroid turned uniformly through ``theta`` radians."""
    if abs(theta) < 1e-12:
        return r0, 0.0
    return r0 * math.sin(theta) / theta, r0 * (1.0 - math.cos(theta)) / abs(theta)


def near(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


# -- making -----------------------------------------------------------------


def open_on(px: Px, doc: Any, plane: Any) -> Any:
    """Open a sketch on a plane feature. Returns the sketch manager."""
    if not sc.select_feature(doc, plane):
        raise Require(f"The plane {call(plane, 'Name')} could not be selected.")
    manager = sc.sketch_manager(doc)
    manager.AddToDB = True
    manager.DisplayWhenAdded = False
    call(manager, "InsertSketch", True)
    if call(manager, "ActiveSketch") is None:
        raise Require("InsertSketch(True) did not open a sketch.")
    call(doc, "ClearSelection2", True)
    return manager


def plane_origin_z(px: Px, doc: Any, plane: Any) -> Tuple[float, Vec]:
    """Where a plane is, as its sketch origin's model z in mm, and its sketch normal in model space."""
    before = sc.feature_names(doc)
    manager = open_on(px, doc, plane)
    data = sketch_to_model(call(manager, "ActiveSketch"))
    sc.close_sketch(px, doc, "Probe Empty", before, allow_empty=True)
    origin = transform_point(data, (0.0, 0.0, 0.0))
    tip = transform_point(data, (0.0, 0.0, 1.0))
    return origin[2] * sc.MM, (tip[0] - origin[0], tip[1] - origin[1], tip[2] - origin[2])


def offset_plane(px: Px, doc: Any, distance_mm: float, flip: bool, base: int = 1) -> Any:
    """InsertRefPlane at a distance from the Nth plane; returns the new RefPlane feature."""
    if not sc.select_plane(doc, base):
        raise Require(f"Reference plane {base} could not be selected.")
    before = sc.feature_names(doc)
    constraint = PLANE_DISTANCE | (PLANE_FLIP if flip else 0)
    made = call(sc.feature_manager(doc), "InsertRefPlane", constraint, sc.m(distance_mm), 0, 0.0, 0, 0.0)
    call(doc, "ClearSelection2", True)
    new = [name for name, kind in sc.new_features(doc, before) if kind == "RefPlane"]
    if made is None or len(new) != 1:
        raise Require(f"InsertRefPlane({constraint}, {sc.m(distance_mm)}) made {new}.")
    return sc.feature_by_name(doc, new[0])


def circle_sketch(px: Px, doc: Any, plane: Any, name: str, at_model: Vec, radius_mm: float = PROFILE_R) -> str:
    """A circle whose centre is at a model point on the plane, placed through the sketch's own transform."""
    before = sc.feature_names(doc)
    manager = open_on(px, doc, plane)
    local = transform_point(model_to_sketch(call(manager, "ActiveSketch")),
                            (sc.m(at_model[0]), sc.m(at_model[1]), sc.m(at_model[2])))
    call(manager, "CreateCircleByRadius", local[0], local[1], 0.0, sc.m(radius_mm))
    return sc.close_sketch(px, doc, name, before)


def path_sketch(px: Px, doc: Any, name: str, z0_mm: float, z1_mm: float, plane_index: int = 2) -> str:
    """A line on the axis from model z0 to z1, drawn on the Nth plane (Top) through its transform."""
    before = sc.feature_names(doc)
    manager = open_on(px, doc, sc.planes(doc)[plane_index - 1])
    data = model_to_sketch(call(manager, "ActiveSketch"))
    a = transform_point(data, (0.0, 0.0, sc.m(z0_mm)))
    b = transform_point(data, (0.0, 0.0, sc.m(z1_mm)))
    call(manager, "CreateLine", a[0], a[1], 0.0, b[0], b[1], 0.0)
    return sc.close_sketch(px, doc, name, before)


def select_profile_and_path(doc: Any, profile: str, path: str) -> bool:
    return (sc.select_feature(doc, sc.feature_by_name(doc, profile), append=False, mark=1)
            and sc.select_feature(doc, sc.feature_by_name(doc, path), append=True, mark=4))


def boss_sweep_args(twist: float) -> Tuple[Any, ...]:
    """InsertProtrusionSwept4's 20 arguments: constant twist along path, merged, direction 1."""
    return (False, False, TWIST_CONSTANT_ALONG_PATH, False, False, 0, 0, False, 0.0, 0.0, 0, 0,
            True, True, True, twist, True, False, 0.0, SWEEP_DIRECTION_1)


def cut_sweep_args(twist: float) -> Tuple[Any, ...]:
    """InsertCutSwept5's 22 arguments: constant twist along path, direction 1."""
    return (False, False, TWIST_CONSTANT_ALONG_PATH, False, False, 0, 0, False, 0.0, 0.0, 0, 0,
            True, True, twist, True, False, False, False, False, 0.0, SWEEP_DIRECTION_1)


def cut_sweep4_args(twist: float) -> Tuple[Any, ...]:
    """InsertCutSwept4's 19 arguments, the same sweep without the circular-profile tail."""
    return (False, False, TWIST_CONSTANT_ALONG_PATH, False, False, 0, 0, False, 0.0, 0.0, 0, 0,
            True, True, twist, True, False, False, False)


def made_feature(doc: Any, before: Sequence[str], result: Any) -> Optional[Any]:
    new = sc.new_features(doc, before)
    solids = [name for name, kind in new if kind not in ("ProfileFeature",)]
    if result is None and not solids:
        return None
    return sc.feature_by_name(doc, solids[-1]) if solids else result


def extrude_direction(px: Px) -> float:
    """+1 when a blank from the Front plane goes toward +Z (probe center_of_mass)."""
    sign = px.shared.get("extrude_z_sign")
    if sign is None:
        raise Require("center_of_mass has not said which way the blank goes.")
    return float(sign)


def flip_for_side(px: Px, sign: float) -> bool:
    """The InsertRefPlane flip that puts a plane on the ``sign`` side of the Front plane."""
    plus = px.shared.get("ref_plane_plus_z_flip")
    if plus is None:
        raise Require("ref_plane_offset has not said which flip is +Z.")
    return bool(plus) if sign > 0 else not bool(plus)


# -- tier 1 -----------------------------------------------------------------


INVERSE_CASES = (
    ("atn", '"Probe Atn"= atn ( 1 )', 45.0, math.pi / 4.0),
    ("arctan", '"Probe Arctan"= arctan ( 1 )', 45.0, math.pi / 4.0),
    ("arcsin", '"Probe Arcsin"= arcsin ( 0.5 )', 30.0, math.pi / 6.0),
    ("arccos", '"Probe Arccos"= arccos ( 0.5 )', 60.0, math.pi / 3.0),
)


@probe("equation_inverse_trig", needs=("equation_syntax",), tier=1,
       members=("IEquationMgr.Add2", "IEquationMgr.Value", "IEquationMgr.AngularEquationUnits"))
def equation_inverse_trig(px: Px) -> None:
    """Which inverse trig functions the Equation Manager takes, and what unit they answer in."""
    with sc.scratch(px) as doc:
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        start = int(call(eqm, "GetCount"))
        try:
            accepted: Dict[str, str] = {}
            for label, text, degrees, radians in INVERSE_CASES:
                got, index = px.attempt(f"{label}: {text}", lambda: add(text))
                if not got or index < 0:
                    px.note(f"{label} is not accepted")
                    continue
                value = float(call(eqm, "Value", index))
                unit = "degrees" if near(value, degrees, 1e-9) else "radians" if near(value, radians, 1e-9) else "?"
                accepted[label] = unit
                px.fact(f"inverse_{label}", {"value": value, "unit": unit})
            px.fact("inverse_trig_accepted", accepted)
            px.require(bool(accepted), "some inverse trig function is accepted")

            spelling = next(name for name in ("atn", "arctan") if name in accepted) if \
                any(name in accepted for name in ("atn", "arctan")) else None
            px.fact("inverse_trig_tangent", spelling)
            if spelling is not None:
                beta, alpha = add('"Probe Beta"= 15'), add('"Probe Alpha"= 20')
                px.require(beta >= 0 and alpha >= 0, "helix and pressure angle globals are added")
                text = f'"Probe TPA"= {spelling} ( tan ( "Probe Alpha" ) / cos ( "Probe Beta" ) )'
                index = add(text)
                px.require(index >= 0, f"accepted: {text}")
                value = float(call(eqm, "Value", index))
                expected = math.degrees(math.atan(math.tan(math.radians(20.0)) / math.cos(math.radians(15.0))))
                px.fact("transverse_pressure_angle_value", value)
                px.check(near(value, expected, 1e-6), f"the transverse pressure angle reads {value!r} (maths {expected!r})")

            got, units = px.attempt("AngularEquationUnits", lambda: call(eqm, "AngularEquationUnits"))
            px.fact("angular_equation_units", units if got else None)
        finally:
            delete_from(eqm, start)


# -- tier 2 -----------------------------------------------------------------


@probe("center_of_mass", needs=("extrude",), tier=2,
       members=("IMassProperty.CenterOfMass", "ISketch.ModelToSketchTransform", "IMathTransform.Inverse"))
def center_of_mass(px: Px) -> None:
    """The mass centre's shape and units, and which way a blank from the Front plane goes."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        front = sc.planes(doc)[0]
        sketch = circle_sketch(px, doc, front, "Probe Boss Sketch", (PROFILE_X, 5.0, 0.0))
        px.require(sc.select_feature(doc, sc.feature_by_name(doc, sketch)), "the boss sketch selects")
        from .p2_solid import _extrude_args  # noqa: PLC0415
        boss = call(sc.feature_manager(doc), "FeatureExtrusion3", *_extrude_args(BLANK_W / sc.MM))
        call(doc, "ClearSelection2", True)
        px.require(boss is not None, "the boss is extruded")
        centre = centre_of_mass_mm(doc)
        px.fact("boss_centre_of_mass_mm", centre)
        px.check(near(centre[0], PROFILE_X, 1e-6) and near(centre[1], 5.0, 1e-6),
                 f"x and y of the centre are the sketch's, in metres: {centre}")
        px.require(near(abs(centre[2]), BLANK_W / 2.0, 1e-6), f"the centre is half the depth off the plane: {centre[2]}")
        sign = 1 if centre[2] > 0 else -1
        px.fact("extrude_z_sign", sign, f"a blank from the Front plane extrudes toward {'+' if sign > 0 else '-'}Z")
        px.shared["extrude_z_sign"] = sign

        top = sc.planes(doc)[1]
        before = sc.feature_names(doc)
        manager = open_on(px, doc, top)
        data = sketch_to_model(call(manager, "ActiveSketch"))
        sc.close_sketch(px, doc, "Probe Empty", before, allow_empty=True)
        origin = transform_point(data, (0.0, 0.0, 0.0))
        x_axis = [round(a - o, 9) for a, o in zip(transform_point(data, (1.0, 0.0, 0.0)), origin)]
        y_axis = [round(a - o, 9) for a, o in zip(transform_point(data, (0.0, 1.0, 0.0)), origin)]
        px.fact("top_sketch_axes_in_model", {"x": x_axis, "y": y_axis})
        px.check(abs(abs(x_axis[2]) + abs(y_axis[2]) - 1.0) < 1e-9, "one of the Top sketch's axes is the model's Z axis")
        px.shared["top_sketch_axes"] = {"x": x_axis, "y": y_axis}


@probe("ref_plane_offset", needs=("center_of_mass", "dimension_link"), tier=2,
       members=("IFeatureManager.InsertRefPlane", "IEquationMgr.Add2"))
def ref_plane_offset(px: Px) -> None:
    """A plane at a distance from the Front plane, each way, with its offset driven by a global."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        sides: Dict[str, float] = {}
        planes: Dict[bool, Any] = {}
        for flip in (False, True):
            got, plane = px.attempt(f"InsertRefPlane distance 5 mm, flip {flip}",
                                    lambda: offset_plane(px, doc, 5.0, flip))
            if not got:
                continue
            planes[flip] = plane
            z, normal = plane_origin_z(px, doc, plane)
            sides[str(flip)] = z
            px.fact(f"plane_flip_{flip}", {"origin_z_mm": round(z, 9), "normal": [round(v, 9) for v in normal]})
        px.require(len(sides) == 2, "both flips make a plane")
        px.require(near(abs(sides["False"]), 5.0, 1e-6) and near(sides["False"], -sides["True"], 1e-6),
                   f"the two flips are 5 mm either side: {sides}")
        plus = sides["True"] > 0
        px.fact("ref_plane_plus_z_flip", plus, f"flip {plus} puts the plane on the +Z side")
        px.shared["ref_plane_plus_z_flip"] = plus
        px.fact("ref_plane_on_extrude_side_flip",
                plus if extrude_direction(px) > 0 else not plus)

        plane = planes[False]
        px.fact("ref_plane_type_name", sc.type_name(plane))
        plane.Name = "Probe Plane"
        px.check(str(call(plane, "Name")) == "Probe Plane", "the plane renames and reads back")
        dims = sc.dimensions_of(plane)
        px.fact("ref_plane_dimensions", [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in dims])
        offset = [d for d in dims if near(float(call(d, "SystemValue")), 0.005, 1e-9)]
        px.require(len(offset) == 1, "the offset dimension is found by its value")
        px.fact("ref_plane_offset_dim_default_name", str(call(offset[0], "Name")))
        offset[0].Name = "Offset"
        px.check(str(call(offset[0], "Name")) == "Offset", "the offset dimension renames to Offset")
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add('"Probe Off"= 7') >= 0, "a global is added")
        px.require(add('"Offset@Probe Plane"= "Probe Off"') >= 0, 'the link "Offset@Probe Plane"= "Probe Off" is accepted')
        call(doc, "ForceRebuild3", False)
        z, _ = plane_origin_z(px, doc, plane)
        px.check(near(z, 7.0 if sides["False"] > 0 else -7.0, 1e-6), f"linked to 7 the plane moves to z {z}")


@probe("path_sketch_relations", needs=("center_of_mass", "relations", "dimensions", "constrained_status"), tier=2,
       members=("ISketchManager.CreateLine", "IModelDoc2.SketchAddConstraints", "IModelDoc2.AddDimension2",
                "ISketch.GetConstrainedStatus"))
def path_sketch_relations(px: Px) -> None:
    """A lead-in and a path line on the axis in the Top plane, held there by relations and two length dimensions."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        before = sc.feature_names(doc)
        manager = open_on(px, doc, sc.planes(doc)[1])
        data = model_to_sketch(call(manager, "ActiveSketch"))
        e, far = -2.0, 12.0
        o = transform_point(data, (0.0, 0.0, 0.0))
        a = transform_point(data, (0.0, 0.0, sc.m(e)))
        b = transform_point(data, (0.0, 0.0, sc.m(far)))
        lead = call(manager, "CreateLine", o[0], o[1], 0.0, a[0], a[1], 0.0)
        lead.ConstructionGeometry = True
        path = call(manager, "CreateLine", a[0], a[1], 0.0, b[0], b[1], 0.0)
        px.require(lead is not None and path is not None, "the lead-in and the path are drawn")
        vertical = abs(a[1] - o[1]) > abs(a[0] - o[0])
        px.fact("axis_is_sketch_vertical", vertical)
        direction = "sgVERTICAL2D" if vertical else "sgHORIZONTAL2D"
        got, _ = px.attempt(f"{direction} on the lead-in", lambda: sc.relate(doc, direction, lead))
        got2, _ = px.attempt(f"{direction} on the path", lambda: sc.relate(doc, direction, path))
        start = call(lead, "GetStartPoint2")
        got3, _ = px.attempt("coincident lead-in start and origin",
                             lambda: sc.relate(doc, "sgCOINCIDENT", start, sc.origin_point(doc)))
        lengths = {}
        for label, line, value, at in (("Lead In", lead, abs(e), a), ("Length", path, far - e, b)):
            sc.select(doc, line)
            display = call(doc, "AddDimension2", at[0] + 0.01, at[1] + 0.01, 0.0)
            call(doc, "ClearSelection2", True)
            if not px.check(display is not None, f"AddDimension2 dimensions the {label} line"):
                continue
            dim = call(display, "GetDimension2", 0)
            dim.Name = label
            lengths[label] = float(call(dim, "SystemValue"))
            px.check(near(lengths[label], sc.m(value), 1e-9), f"a line's dimension is its length: {lengths[label]!r} m")
        status = int(call(call(manager, "ActiveSketch"), "GetConstrainedStatus"))
        px.fact("path_sketch_status", status)
        px.check(status == sc.SW_FULLY_CONSTRAINED, f"the path sketch is fully defined (status {status})")
        name = sc.close_sketch(px, doc, "Probe Path", before)
        feature = sc.feature_by_name(doc, name)
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add('"Probe Lead"= 3') >= 0 and add(f'"Lead In@{name}"= "Probe Lead"') >= 0,
                   "the lead-in length links to a global")
        call(doc, "ForceRebuild3", False)
        ends = [transform_point(sketch_to_model(call(feature, "GetSpecificFeature2")), (float(call(p, "X")),
                                float(call(p, "Y")), 0.0)) for p in (call(path, "GetStartPoint2"),)]
        px.fact("path_start_after_link_mm", mm(ends[0]))
        px.check(near(mm(ends[0])[2], -3.0, 1e-6) and near(mm(ends[0])[0], 0.0, 1e-9),
                 f"the path now starts at z -3 on the axis: {mm(ends[0])}")


def _sweep_boss(px: Px, doc: Any, label: str, z0: float, z1: float, twist: float) -> Tuple[Optional[Any], str, str]:
    """A circle at (12, 0) on a plane at z0, swept to z1 with a twist; returns the feature and the two sketches."""
    if abs(z0) < 1e-12:
        plane = sc.planes(doc)[0]
    else:
        plane = offset_plane(px, doc, abs(z0), flip_for_side(px, 1.0 if z0 > 0 else -1.0))
    profile = circle_sketch(px, doc, plane, f"{label} Profile", (PROFILE_X, 0.0, z0))
    path = path_sketch(px, doc, f"{label} Path", z0, z1)
    px.require(select_profile_and_path(doc, profile, path), "the profile selects at mark 1 and the path at mark 4")
    before = sc.feature_names(doc)
    got, result = px.attempt(f"{label}: InsertProtrusionSwept4(twist {twist:.6f})",
                             lambda: call(sc.feature_manager(doc), "InsertProtrusionSwept4", *boss_sweep_args(twist)))
    call(doc, "ClearSelection2", True)
    return (made_feature(doc, before, result) if got else None), profile, path


@probe("sweep_twist", needs=("center_of_mass", "ref_plane_offset"), tier=2,
       members=("IFeatureManager.InsertProtrusionSwept4", "IFeature.GetDefinition", "ISweepFeatureData.D1ReverseTwistDir",
                "IFeature.ModifyDefinition", "IMassProperty.CenterOfMass"))
def sweep_twist(px: Px) -> None:
    """A constant-twist sweep along the axis: its units, which way it turns, and how to turn it the other way."""
    area = math.pi * PROFILE_R ** 2
    signs: Dict[str, int] = {}
    for label, z0, z1, twist in (("plus z", 0.0, SWEEP_L, QUARTER), ("negative angle", 0.0, SWEEP_L, -QUARTER),
                                 ("minus z", SWEEP_L, 0.0, QUARTER)):
        with sc.quiet_dimensions(px), sc.scratch(px) as doc:
            feature, _, _ = _sweep_boss(px, doc, "Probe Sweep", z0, z1, twist)
            if feature is None:
                px.fail(f"{label}: no sweep was made")
                continue
            volume = _volume(doc)
            centre = centre_of_mass_mm(doc)
            x, y = twisted_centroid(QUARTER)
            px.fact(f"sweep_{label.replace(' ', '_')}", {"volume_mm3": round(volume, 4), "centre_mm": centre,
                                                         "type": sc.type_name(feature)})
            px.check(near(volume, area * SWEEP_L, 1e-3 * area * SWEEP_L), f"{label}: volume {volume:.4f} = A·L")
            quarter = near(centre[0], x, 1e-3) and near(abs(centre[1]), y, 1e-3)
            px.check(quarter, f"{label}: the centroid {centre} is a uniform quarter turn ({x:.4f}, ±{y:.4f})")
            if quarter:
                # Travelling toward larger z, is the section turning counter-clockwise about +Z?
                travel = 1 if z1 > z0 else -1
                about_plus_z = (1 if centre[1] > 0 else -1) * travel
                signs[label] = about_plus_z
            if label == "plus z":
                px.shared["sweep_ok"] = True
                dims = sc.dimensions_of(feature)
                values = [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in dims]
                px.fact("sweep_dimensions", values)
                twist_dims = [d for d in dims if near(abs(float(call(d, "SystemValue"))), QUARTER, 1e-9)]
                px.fact("twist_dimension_found", bool(twist_dims))
                if twist_dims:
                    px.fact("twist_dim_default_name", str(call(twist_dims[0], "Name")))
                    px.shared["twist_dim_by_value"] = True

                data = call(feature, "GetDefinition")
                px.fact("sweep_definition_type", type(data).__name__ if data is not None else None)
                if data is not None:
                    got, reverse = px.attempt("D1ReverseTwistDir", lambda: call(data, "D1ReverseTwistDir"))
                    px.fact("d1_reverse_twist_dir_default", reverse if got else None)
                    px.fact("twist_control_type_read", call(data, "TwistControlType"))
                    px.fact("twist_angle_read", call(data, "GetTwistAngle"))
                    ok = call(data, "AccessSelections", doc, sc.null())
                    data.D1ReverseTwistDir = True
                    got, modified = px.attempt("ModifyDefinition with D1ReverseTwistDir True",
                                               lambda: call(feature, "ModifyDefinition", data, doc, sc.null()))
                    px.fact("modify_definition_access", ok)
                    flipped = centre_of_mass_mm(doc)
                    px.fact("centre_after_reverse_mm", flipped)
                    px.check(got and near(flipped[1], -centre[1], 1e-3),
                             f"D1ReverseTwistDir turns the sweep the other way: {flipped}")
                    px.fact("reverse_flag_flips", bool(got and near(flipped[1], -centre[1], 1e-3)))
    px.fact("twist_about_plus_z", signs,
            "+1 is counter-clockwise about +Z, travelling toward +Z, i.e. a right-hand helix")
    px.require("plus z" in signs, "a positive twist along +Z has a measured sense")
    px.shared["twist_sign_plus_z"] = signs["plus z"]


@probe("sweep_twist_link", needs=("sweep_twist",), tier=2, members=("IEquationMgr.Add2", "IDimension.Name"))
def sweep_twist_link(px: Px) -> None:
    """The twist dimension is named, linked to a global in degrees, and the sweep follows it."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        feature, _, _ = _sweep_boss(px, doc, "Probe Sweep", 0.0, SWEEP_L, QUARTER)
        px.require(feature is not None, "the sweep is made")
        feature.Name = "Probe Sweep"
        px.check(str(call(feature, "Name")) == "Probe Sweep", "the sweep renames and reads back")
        twist = [d for d in sc.dimensions_of(feature) if near(abs(float(call(d, "SystemValue"))), QUARTER, 1e-9)]
        px.require(len(twist) == 1, "exactly one dimension of the sweep has the twist's value")
        twist[0].Name = "Twist"
        px.check(str(call(twist[0], "Name")) == "Twist", "the twist dimension renames to Twist")
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add('"Probe T"= 45') >= 0, "a twist global is added")
        link = add('"Twist@Probe Sweep"= "Probe T"')
        px.require(link >= 0, 'the link "Twist@Probe Sweep"= "Probe T" is accepted')
        centre = centre_of_mass_mm(doc)
        x, y = twisted_centroid(math.radians(45.0))
        px.fact("centre_at_45_mm", centre)
        value = float(call(twist[0], "SystemValue"))
        px.fact("twist_system_value_after_link", value)
        px.check(near(value, math.radians(45.0), 1e-9), f"a global of 45 is 45 degrees on the dimension: {value!r} rad")
        # A twisted sweep is a spline surface: its centroid lands within a few µm,
        # which a relative tolerance of 1e-3 allows and a wrong twist does not.
        px.check(near(centre[0], x, 1e-3 * x) and near(abs(centre[1]), y, 1e-3 * x),
                 f"the sweep follows the global to an eighth of a turn: {centre} vs ({x:.4f}, ±{y:.4f})")


@probe("sweep_cut_ends", needs=("sweep_twist", "cut"), tier=2,
       members=("IFeatureManager.InsertCutSwept5", "IFeatureManager.InsertCutSwept4", "IPartDoc.GetBodies2"))
def sweep_cut_ends(px: Px) -> None:
    """A twisted cut through a blank, starting on its face and starting ahead of it: one body, A·w removed."""
    removed_expected = math.pi * PROFILE_R ** 2 * BLANK_W
    working: List[str] = []
    ez = extrude_direction(px)
    for label, start, end in (("flush", 0.0, BLANK_W * ez), ("overrun", -2.0 * ez, (BLANK_W + 2.0) * ez)):
        for call_name, args in (("InsertCutSwept5", cut_sweep_args), ("InsertCutSwept4", cut_sweep4_args)):
            with sc.quiet_dimensions(px), sc.scratch(px) as doc:
                _blank(px, doc)
                blank_volume = _volume(doc)
                plane = sc.planes(doc)[0] if abs(start) < 1e-12 else offset_plane(px, doc, abs(start),
                                                                                  flip_for_side(px, math.copysign(1, start)))
                profile = circle_sketch(px, doc, plane, "Probe Profile", (PROFILE_X, 0.0, start))
                path = path_sketch(px, doc, "Probe Path", start, end)
                px.require(select_profile_and_path(doc, profile, path), "profile and path select")
                before = sc.feature_names(doc)
                twist = math.radians(30.0) * abs(end - start) / BLANK_W
                got, result = px.attempt(f"{label}: {call_name}",
                                         lambda: call(sc.feature_manager(doc), call_name, *args(twist)))
                call(doc, "ClearSelection2", True)
                feature = made_feature(doc, before, result) if got else None
                if feature is None:
                    px.note(f"{label}: {call_name} made nothing")
                    continue
                removed = blank_volume - _volume(doc)
                bodies = solid_bodies(doc)
                px.fact(f"cut_{label}_{call_name}", {"removed_mm3": round(removed, 4), "bodies": bodies,
                                                     "type": sc.type_name(feature)})
                if near(removed, removed_expected, 1e-3 * removed_expected) and bodies == 1:
                    working.append(f"{label} {call_name}")
                    break
    px.fact("sweep_cut_routes", working)
    px.require(any(route.startswith("overrun") for route in working), "an overrun twisted cut removes exactly A·w")
    px.shared["sweep_cut_call"] = next(r for r in working if r.startswith("overrun")).split(" ", 1)[1]


@probe("pattern_sweep", needs=("sweep_cut_ends", "pattern"), tier=2,
       members=("IFeatureManager.FeatureCircularPattern5",))
def pattern_sweep(px: Px) -> None:
    """A circular pattern of a twisted cut: the volume, and the rebuild time with and without geometry pattern."""
    ez = extrude_direction(px)
    call_name = px.shared.get("sweep_cut_call", "InsertCutSwept5")
    args = cut_sweep_args if call_name == "InsertCutSwept5" else cut_sweep4_args
    timings: Dict[str, float] = {}
    for count, radius, geometry in ((6, PROFILE_R, False), (24, 1.0, False), (24, 1.0, True)):
        with sc.quiet_dimensions(px), sc.scratch(px) as doc:
            _blank(px, doc)
            blank_volume = _volume(doc)
            px.require(sc.select_plane(doc, 2) and sc.select_plane(doc, 3, append=True), "planes 2 and 3 select")
            before = sc.feature_names(doc)
            call(doc, "InsertAxis2", True)
            call(doc, "ClearSelection2", True)
            axis_name = sc.new_features(doc, before)[0][0]
            plane = offset_plane(px, doc, 2.0, flip_for_side(px, -ez))
            profile = circle_sketch(px, doc, plane, "Probe Profile", (PROFILE_X + 3.0, 0.0, -2.0 * ez), radius)
            path = path_sketch(px, doc, "Probe Path", -2.0 * ez, (BLANK_W + 2.0) * ez)
            select_profile_and_path(doc, profile, path)
            before = sc.feature_names(doc)
            result = call(sc.feature_manager(doc), call_name, *args(math.radians(30.0) * 14.0 / BLANK_W))
            call(doc, "ClearSelection2", True)
            seed = made_feature(doc, before, result)
            px.require(seed is not None, f"the seed cut is made ({count} × r {radius})")
            sc.select_feature(doc, sc.feature_by_name(doc, axis_name), mark=1)
            sc.select_feature(doc, seed, append=True, mark=4)
            made = call(sc.feature_manager(doc), "FeatureCircularPattern5", count, 2 * math.pi, False, "NULL",
                        geometry, True, False, False, False, False, 1, 0.0, "NULL", False)
            call(doc, "ClearSelection2", True)
            px.require(made is not None, f"the pattern of {count} is made (geometry pattern {geometry})")
            started = time.monotonic()
            call(doc, "ForceRebuild3", False)
            seconds = time.monotonic() - started
            volume = _volume(doc)
            expected = blank_volume - count * math.pi * radius ** 2 * BLANK_W
            key = f"{count} r{radius:g} geometry {geometry}"
            timings[key] = round(seconds, 3)
            px.check(near(volume, expected, 1e-4 * blank_volume), f"{key}: {volume:.3f} mm³ (expected {expected:.3f})")
            px.check(solid_bodies(doc) == 1, f"{key}: one body")
    px.fact("pattern_sweep_rebuild_seconds", timings)


@probe("mirror_body_merge", needs=("ref_plane_offset", "extrude"), tier=2,
       members=("IFeatureManager.InsertMirrorFeature2", "ISelectionMgr.CreateSelectData", "IBody2.Select2"))
def mirror_body_merge(px: Px) -> None:
    """Half a blank mirrored about a plane at its end face into one body twice the size."""
    ez = extrude_direction(px)
    half = BLANK_W / 2.0
    working: List[str] = []
    for label, body_mark, plane_mark, mirror_body in (
        ("body mark 1, plane mark 2", 1, 2, True),
        ("body mark 256, plane mark 2", 256, 2, True),
        ("body mark 1, plane mark 1", 1, 1, True),
    ):
        with sc.quiet_dimensions(px), sc.scratch(px) as doc:
            from .p2_solid import _extrude_args  # noqa: PLC0415
            front = sc.planes(doc)[0]
            sketch = circle_sketch(px, doc, front, "Blank Sketch", (0.0, 0.0, 0.0), BLANK_R)
            sc.select_feature(doc, sc.feature_by_name(doc, sketch))
            call(sc.feature_manager(doc), "FeatureExtrusion3", *_extrude_args(half / sc.MM))
            call(doc, "ClearSelection2", True)
            half_volume = _volume(doc)
            plane = offset_plane(px, doc, half, flip_for_side(px, ez))
            bodies = call(doc, "GetBodies2", SOLID_BODY, True)
            px.require(bool(bodies), "the half blank has a body")
            call(doc, "ClearSelection2", True)
            sc.select_feature(doc, plane, append=False, mark=plane_mark)
            data = call(call(doc, "SelectionManager"), "CreateSelectData")
            data.Mark = body_mark
            call(bodies[0], "Select2", True, data)
            before = sc.feature_names(doc)
            got, result = px.attempt(f"{label}: InsertMirrorFeature2(True, False, True, False, 0)",
                                     lambda: call(sc.feature_manager(doc), "InsertMirrorFeature2",
                                                  mirror_body, False, True, False, 0))
            call(doc, "ClearSelection2", True)
            feature = made_feature(doc, before, result) if got else None
            if feature is None:
                px.note(f"{label}: nothing was mirrored")
                continue
            volume = _volume(doc)
            centre = centre_of_mass_mm(doc)
            count = solid_bodies(doc)
            px.fact(f"mirror {label}", {"volume_mm3": round(volume, 4), "bodies": count, "centre_mm": centre,
                                        "type": sc.type_name(feature)})
            if near(volume, 2 * half_volume, 1e-6 * half_volume) and count == 1 and near(centre[2], half * ez, 1e-6):
                working.append(label)
    px.fact("mirror_body_routes", working)
    px.require(bool(working), "some selection mirrors the half blank into one body of twice the volume")
