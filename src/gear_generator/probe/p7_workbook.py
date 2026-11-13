"""Tier 7: what a workbook's layout part and static assembly need (PLAN-WORKBOOK §4.2).

A workbook gearbox is built as a layout part — for each shaft a plane offset
from Right by its X and one offset from Top by its Y, driven by globals, and a
named axis through the two — and an assembly of five or more components, each
``Place``d at its face centre and ``Fix``ed. Update SolidWorks later opens a part
by path to change its globals, and re-``Place``s the components of an assembly
it reopened. Every one of those steps is close to something already probed and
none of them is the same thing, so each is settled here on scratch documents:

1. ``layout_planes`` — ``InsertRefPlane`` from the **Right** and **Top** planes:
   which side each flip value puts the plane on, measured twice (an empty
   sketch's transform, as ``ref_plane_offset`` measured the Front plane, and
   ``IRefPlane.Transform``); its offset driven by a global, and the global
   changed; a plane on the minus side linked to a negative global.
2. ``axis_through_named_planes`` — ``InsertAxis2`` through two planes made in
   the same part, each route of selecting them tried on its own shaft: the
   feature found by name and ``Select2``, ``SelectByID2`` by name, and
   ``Select2`` on the object ``InsertRefPlane`` returned. Where each axis lies
   is read back with ``GetRefAxisParams``, and again after the globals move.
3. ``axis_through_base_planes`` — a shaft at X = 0, at Y = 0 and at both: the
   base plane itself in place of an offset plane.
4. ``layout_assembly_five`` and ``layout_assembly_reopen`` — five components
   (one part twice) inserted, placed, fixed and saved; the assembly closed,
   opened again by path, each component found by name by every route there is,
   its frame read, re-placed while fixed, saved, and opened once more to see the
   new frames kept.
5. ``open_and_activate_part`` and ``open_part_from_assembly`` — a closed part
   opened by path while another document is active, made active, and changed by
   the tool's own ``swbuild.update_variables``; then the same for a part that is
   loaded only as a component of an open assembly.

``layout_plane_negative_global`` (extra, last) asks what a plane's offset does
when its global goes below zero, which the plan assumes it cannot follow.

Written on a machine without SolidWorks: it has never run. Every call in it not
already in an earlier probe is UNVERIFIED until it does, and where the API offers
more than one route each is tried and the one SolidWorks accepted is recorded.
Lengths cross COM in metres; everything recorded is in millimetres.
"""

from __future__ import annotations

import math
import os
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from ..gears import crossed
from ..gears.base import GlobalVariable
from ..store import same_path
from ..swcom import _out_bool, call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p1_equations import adder
from .p2_bevel import plane_frame
from .p2_helical import PLANE_DISTANCE, PLANE_FLIP, offset_plane
from .p4_assembly import _part_with_axis
from .p4_interference import member
from .p4_nonparallel import IDENTITY, Matrix, array_data, frame_error, make_transform, place

Vec = Tuple[float, float, float]

# swOpenDocOptions_e.swOpenDocOptions_Silent, as Airfoil-Converter's open_part
# passes it to OpenDoc6. Also read from swconst.tlb at run time and recorded.
OPEN_SILENT = 1
# swSaveAsVersion_e current, swSaveAsOptions_e silent (probe save_as).
SAVE_AS_CURRENT_VERSION = 0
SAVE_AS_SILENT = 1

TOLERANCE_MM = 1e-6
TOLERANCE_ROTATION = 1e-6

OFFSET = 7.0      # mm, the first offset of every layout plane
MOVED = 23.0      # mm, what its global is changed to
NEGATIVE = -9.0   # mm, a global below zero (extra probe)

# Item 2: one shaft per selection route, on every side of the origin.
NAMED_SHAFTS = (("S1", 20.0, 12.0), ("S2", -15.0, 30.0), ("S3", 35.0, -8.0))
NAMED_MOVE = (6.0, -3.0)   # mm, added to the size of the moved shaft's X and Y, each keeping its side
# Item 3: a shaft on each base plane, and one on both.
BASE_SHAFTS = (("B1", 0.0, 15.0), ("B2", 25.0, 0.0), ("B3", 0.0, 0.0))
BASE_MOVE = {"B1": (0.0, 18.0), "B2": (31.0, 0.0)}

# Item 4: the layout part and four gears, one part used twice (identical gears
# share a part file, PLAN-WORKBOOK §1). The last is on a -Z shaft.
LAYOUT_STEM = "Probe W7 Layout"
COMPONENTS = (
    (LAYOUT_STEM, IDENTITY, (0.0, 0.0, 0.0)),
    ("Probe W7 A", crossed.rot_z(0.0), (40.0, 0.0, 5.0)),
    ("Probe W7 B", crossed.rot_z(12.0), (0.0, 35.0, -3.0)),
    ("Probe W7 C", crossed.rot_z(-25.0), (-30.0, -20.0, 0.0)),
    ("Probe W7 C", crossed.multiply(crossed.rot_x(180.0), crossed.rot_z(40.0)), (-30.0, -20.0, 25.0)),
)
ASSEMBLY_STEM = "Probe W7 Gearbox"
REPLACE_SHIFT = (5.0, -4.0, 2.0)   # mm, how far Update SolidWorks moves each gear in the probe
REPLACE_TURN = 7.0                 # degrees about the gear's own axis

FIND_ROUTES = ("GetComponentByName", "GetComponents(True) by Name2", "root component GetChildren by Name2",
               "FeatureByName then GetSpecificFeature2")
PLANE_ROUTES = ("Select2 on the feature found by name", "SelectByID2 by name",
                "Select2 on what InsertRefPlane returned")


# -- pure: what a measurement says (tested on Linux) --------------------------


def plus_flip(sides: Mapping[str, float], distance: float = OFFSET, tol: float = TOLERANCE_MM) -> Optional[bool]:
    """The flip that put a plane on the plus side, from where each flip put it.

    ``sides`` maps ``"False"`` and ``"True"`` to the plane's signed position
    along the base plane's axis, in mm. ``None`` unless the two are ``distance``
    either side of zero: anything else is not a flip of one offset.
    """
    if set(sides) != {"False", "True"}:
        return None
    off, on = float(sides["False"]), float(sides["True"])
    if abs(abs(off) - distance) > tol or abs(off + on) > tol:
        return None
    return on > 0


def axis_crossing(params: Sequence[float]) -> Tuple[Tuple[float, float], Vec]:
    """``GetRefAxisParams`` — two points on the axis in metres — as where it crosses z = 0 in mm, and its direction.

    Raises ``ValueError`` for an axis that does not cross the Front plane: a
    layout axis is meant to lie along Z.
    """
    p = [float(v) for v in params[:3]]
    q = [float(v) for v in params[3:6]]
    d = [b - a for a, b in zip(p, q)]
    n = math.sqrt(sum(c * c for c in d))
    if n == 0.0:
        raise ValueError("The axis's two points are the same point.")
    u = (d[0] / n, d[1] / n, d[2] / n)
    if abs(u[2]) < 1e-9:
        raise ValueError(f"The axis lies in the Front plane, along {u}.")
    t = -p[2] / u[2]
    return ((p[0] + t * u[0]) * sc.MM, (p[1] + t * u[1]) * sc.MM), u


def along_z(direction: Sequence[float], tol: float = 1e-9) -> bool:
    return abs(abs(float(direction[2])) - 1.0) <= tol


def turned(matrix: Matrix, degrees: float) -> Matrix:
    """A component's rotation turned about its own axis — its frame's Z — by ``degrees``."""
    return crossed.multiply(matrix, crossed.rot_z(degrees))


def shifted(at: Sequence[float], by: Sequence[float]) -> Vec:
    return (float(at[0]) + by[0], float(at[1]) + by[1], float(at[2]) + by[2])


def moved_away(x: float, y: float, by: Sequence[float] = NAMED_MOVE) -> Tuple[float, float]:
    """A shaft moved by changing the size of each coordinate, on the side it is: (-15, 30) by (6, -3) is (-21, 27)."""
    return (math.copysign(abs(x) + by[0], x), math.copysign(abs(y) + by[1], y))


def plain(value: Any) -> Any:
    """A value fit for the JSON report: COM objects and the like become their repr."""
    if isinstance(value, (bool, int, float, str, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    return repr(value)


def instance_stems(names: Sequence[str]) -> Dict[str, List[str]]:
    """Component names grouped by the part they are instances of: ``Probe W7 C-2`` → ``Probe W7 C``."""
    out: Dict[str, List[str]] = {}
    for name in names:
        stem, _, number = name.rpartition("-")
        out.setdefault(stem if number.isdigit() else name, []).append(name)
    return out


# -- helpers that touch SolidWorks -------------------------------------------


def _millimetres(px: Px, doc: Any) -> None:
    ext = sc.extension(doc)
    if int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, 0)) != sc.SW_MM:
        call(ext, "SetUserPreferenceInteger", sc.SW_UNIT_SYSTEM, 0, sc.SW_UNIT_SYSTEM_MMGS)
    px.require(int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, 0)) == sc.SW_MM,
               f"{call(doc, 'GetTitle')} is in millimetres")


def _rounded(v: Sequence[float], places: int = 9) -> List[float]:
    return [round(float(c), places) for c in v]


def _measure(px: Px, doc: Any, plane: Any) -> Dict[str, Any]:
    """Where a plane is: its sketch origin and normal in model space, and IRefPlane.Transform's, in mm."""
    origin, _x, _y, normal = plane_frame(px, doc, plane)
    out: Dict[str, Any] = {"origin_mm": _rounded(origin), "normal": _rounded(normal)}
    name = str(call(plane, "Name"))
    got, data = px.attempt(f"IRefPlane.Transform of {name}",
                           lambda: [float(v) for v in call(call(call(plane, "GetSpecificFeature2"), "Transform"),
                                                           "ArrayData")])
    if got:
        # Rotation by columns (SW-Macro-Database reading/05): the third column is the plane's Z.
        out["transform_origin_mm"] = _rounded([data[9] * sc.MM, data[10] * sc.MM, data[11] * sc.MM])
        out["transform_normal"] = _rounded(data[6:9])
    return out


def _set_global(eqm: Any, name: str, value: float) -> str:
    """Change a global in place by an indexed put of ``Equation(i)`` (probe equation_set); returns what reads back."""
    for index in range(int(call(eqm, "GetCount"))):
        if str(call(eqm, "Equation", index)).replace(" ", "").startswith(f'"{name}"='):
            sc.put_indexed(eqm, "Equation", index, f'"{name}"= {value:g}')
            return str(call(eqm, "Equation", index))
    raise Require(f'There is no global "{name}" to change.')


def _global_value(eqm: Any, name: str) -> Optional[float]:
    for index in range(int(call(eqm, "GetCount"))):
        if str(call(eqm, "Equation", index)).replace(" ", "").startswith(f'"{name}"='):
            return float(call(eqm, "Value", index))
    return None


def _name_offset(px: Px, plane: Any, distance: float) -> str:
    """Find a plane's offset dimension by its value and name it Offset; returns its default name."""
    dims = sc.dimensions_of(plane)
    match = [d for d in dims if abs(float(call(d, "SystemValue")) - sc.m(distance)) < 1e-9]
    px.require(len(match) == 1, f"{call(plane, 'Name')}'s offset dimension is found by its value",
               [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in dims])
    default = str(call(match[0], "Name"))
    match[0].Name = "Offset"
    px.check(str(call(match[0], "Name")) == "Offset", f"{call(plane, 'Name')}'s offset dimension renames to Offset")
    return default


def _rename(px: Px, feature: Any, name: str) -> str:
    feature.Name = name
    kept = str(call(feature, "Name"))
    px.check(kept == name, f"renamed {name!r}, it reads back {kept!r}")
    return kept


def _flip_for(px: Px, base: str, sign: float) -> bool:
    plus = (px.shared.get("layout_plus_flip") or {}).get(base)
    if plus is None:
        raise Require("layout_planes has not said which flip puts a plane on the plus side.")
    return bool(plus) if sign > 0 else not bool(plus)


def _layout_plane(px: Px, doc: Any, base: str, coordinate: float, name: str) -> Tuple[Any, Any]:
    """A plane ``|coordinate|`` from Right (base ``x``) or Top (``y``) on the coordinate's side, named.

    Returns ``(feature, what InsertRefPlane returned)``: the second is kept so
    selecting by that handle can be tried as a route of its own.
    """
    index = 3 if base == "x" else 2
    flip = _flip_for(px, "right" if base == "x" else "top", coordinate)
    if not sc.select_plane(doc, index):
        raise Require(f"Reference plane {index} could not be selected.")
    before = sc.feature_names(doc)
    constraint = PLANE_DISTANCE | (PLANE_FLIP if flip else 0)
    made = call(sc.feature_manager(doc), "InsertRefPlane", constraint, sc.m(abs(coordinate)), 0, 0.0, 0, 0.0)
    call(doc, "ClearSelection2", True)
    new = [n for n, kind in sc.new_features(doc, before) if kind == "RefPlane"]
    if made is None or len(new) != 1:
        raise Require(f"InsertRefPlane({constraint}, {sc.m(abs(coordinate))}) from plane {index} made {new}.")
    feature = sc.feature_by_name(doc, new[0])
    _rename(px, feature, name)
    return feature, made


def _select_two(px: Px, doc: Any, route: str, pair: Sequence[Tuple[Any, Any]]) -> bool:
    """Select two planes by one route only, judged by the selection count; ``pair`` is ``(feature, returned)``."""
    call(doc, "ClearSelection2", True)
    for position, (feature, returned) in enumerate(pair):
        append = position > 0
        before = sc.selected_count(doc)
        name = str(call(feature, "Name"))
        if route == PLANE_ROUTES[0]:
            target = sc.feature_by_name(doc, name)
            thunk: Callable[[], Any] = lambda t=target: call(t, "Select2", append, 0)
        elif route == PLANE_ROUTES[1]:
            thunk = lambda n=name: call(sc.extension(doc), "SelectByID2", n, "PLANE", 0.0, 0.0, 0.0, append, 0,
                                        sc.null(), 0)
        else:
            if returned is None:
                return False
            thunk = lambda r=returned: call(r, "Select2", append, 0)
        selected = False
        for number in range(sc.RETRIES):
            got, value = px.attempt(f"{route}: {name}" + (f" (retry {number})" if number else ""), thunk)
            if got and value and sc.selected_count(doc) > before:
                selected = True
                break
            time.sleep(sc.RETRY_PAUSE)
        if not selected:
            call(doc, "ClearSelection2", True)
            return False
    return sc.selected_count(doc) == 2


def _insert_axis(px: Px, doc: Any, name: str) -> Optional[Any]:
    """``InsertAxis2(True)`` on what is selected; the one new RefAxis, renamed, or None."""
    before = sc.feature_names(doc)
    got, made = px.attempt(f"InsertAxis2(True) for {name}", lambda: call(doc, "InsertAxis2", True))
    call(doc, "ClearSelection2", True)
    new = [n for n, kind in sc.new_features(doc, before) if kind == "RefAxis"]
    if not px.check(got and bool(made) and len(new) == 1, f"InsertAxis2 makes one axis for {name}", new):
        return None
    axis = sc.feature_by_name(doc, new[0])
    _rename(px, axis, name)
    return axis


def _axis_at(axis: Any) -> Tuple[Tuple[float, float], Vec]:
    return axis_crossing(call(call(axis, "GetSpecificFeature2"), "GetRefAxisParams"))


def _check_axis(px: Px, axis: Any, x: float, y: float, label: str) -> Dict[str, Any]:
    (ax, ay), direction = _axis_at(axis)
    px.check(abs(ax - x) < TOLERANCE_MM and abs(ay - y) < TOLERANCE_MM and along_z(direction),
             f"{label} lies along Z through ({x:g}, {y:g}): it crosses at ({ax:.9f}, {ay:.9f}) along {direction}")
    return {"at_mm": [round(ax, 9), round(ay, 9)], "direction": _rounded(direction)}


def _link(px: Px, add: Callable[[str], int], plane_name: str, global_name: str, value: float) -> None:
    px.require(add(f'"{global_name}"= {value:g}') >= 0, f'the global "{global_name}" is added')
    px.require(add(f'"Offset@{plane_name}"= "{global_name}"') >= 0,
               f'the link "Offset@{plane_name}"= "{global_name}" is accepted')


def _enum(px: Px, enum: str) -> Optional[Dict[str, int]]:
    """An swconst enum read for the record; never fatal, the probe's constants do not come from it."""
    try:
        return sc.swconst(px, enum)
    except Exception as exc:  # noqa: BLE001 - Require included: this is evidence, not a step
        px.note(f"{enum} could not be read from swconst.tlb: {exc}")
        return None


def _doc_of(result: Any) -> Any:
    """A document from a call that may hand back ``(doc, out, out)`` or the document alone."""
    return result[0] if isinstance(result, tuple) and result else result


def _shape(result: Any) -> str:
    return f"tuple of {len(result)}" if isinstance(result, tuple) else type(result).__name__


def open_by_path(px: Px, path: str, doc_type: int = sc.SW_DOC_PART, prefer: str = "") -> Tuple[Any, str]:
    """Open a saved document by its path. Each route is tried in turn; returns ``(doc, route)``.

    ``OpenDoc6`` is what Airfoil-Converter's ``open_part`` uses from Python with
    two by-reference longs; ``OpenDoc7`` takes a document specification from
    ``GetOpenDocSpec``; ``OpenDoc`` is the old two-argument form.
    """
    application = sc.app(px)
    label = os.path.basename(path)
    seen: Dict[str, Any] = {}

    def doc6() -> Any:
        errors, warnings = sc.out_long(), sc.out_long()
        result = call(application, "OpenDoc6", path, doc_type, OPEN_SILENT, "", errors, warnings)
        seen["OpenDoc6"] = {"shape": _shape(result), "errors": plain(getattr(errors, "value", None)),
                            "warnings": plain(getattr(warnings, "value", None))}
        return _doc_of(result)

    def doc7() -> Any:
        spec = call(application, "GetOpenDocSpec", path)
        spec.Silent = True
        result = call(application, "OpenDoc7", spec)
        seen["OpenDoc7"] = {"shape": _shape(result), "error": plain(getattr(spec, "Error", None)),
                            "warning": plain(getattr(spec, "Warning", None))}
        return _doc_of(result)

    def doc0() -> Any:
        result = call(application, "OpenDoc", path, doc_type)
        seen["OpenDoc"] = {"shape": _shape(result)}
        return _doc_of(result)

    routes = [("OpenDoc6", doc6), ("OpenDoc7", doc7), ("OpenDoc", doc0)]
    routes.sort(key=lambda r: r[0] != prefer)
    for name, thunk in routes:
        got, doc = px.attempt(f"{name}({label})", thunk)
        if got and doc is not None and same_path(str(call(doc, "GetPathName") or ""), path):
            px.fact(f"open {label}", {"route": name, **seen.get(name, {})})
            title = str(call(doc, "GetTitle"))
            if title not in px.shared.setdefault("created", []):
                px.shared["created"].append(title)
            return doc, name
    px.fact(f"open {label}", {"route": None, **seen})
    raise Require(f"{path} could not be opened by any route.")


def activate(px: Px, title: str) -> bool:
    """``ActivateDoc3`` (probe activate_document), then whether the active document is that title."""
    px.attempt(f"ActivateDoc3({title})", lambda: call(sc.app(px), "ActivateDoc3", title, False, 0, sc.out_long()))
    return _active_title(px) == title


def _active_title(px: Px) -> str:
    active = call(sc.app(px), "ActiveDoc")
    return "" if active is None else str(call(active, "GetTitle"))


def _active_path(px: Px) -> str:
    active = call(sc.app(px), "ActiveDoc")
    return "" if active is None else str(call(active, "GetPathName") or "")


def _open_paths(px: Px) -> Dict[str, Tuple[str, int]]:
    """Every open document with a path: normalised path → (title, type)."""
    out: Dict[str, Tuple[str, int]] = {}
    doc = call(sc.app(px), "GetFirstDocument")
    guard = 0
    while doc is not None and guard < 500:
        guard += 1
        path = str(call(doc, "GetPathName") or "")
        if path:
            out[os.path.normcase(path)] = (str(call(doc, "GetTitle")), int(call(doc, "GetType")))
        doc = call(doc, "GetNext")
    return out


def close_paths(px: Px, paths: Sequence[str]) -> List[str]:
    """Close the probe's own documents at these paths, assemblies first. Returns any still open.

    Only titles the probe created are closed, and the probe's modified parts
    are saved before an assembly closes (``scaffold.save_created_parts``: on
    SolidWorks 2024 closing an assembly whose parts changed asked about them in
    a modal dialog).
    """
    wanted = {os.path.normcase(p) for p in paths}
    created = px.shared.get("created", [])
    if px.options.get("keep"):
        return []
    # A modified part is saved before anything closes, as probe end_to_end does
    # before closing what it built: CloseDoc discarding silently is verified on 2026 only.
    sc.save_created_parts(px)
    for kind in (sc.SW_DOC_ASSEMBLY, sc.SW_DOC_PART):
        for path, (title, doc_type) in _open_paths(px).items():
            if path not in wanted or doc_type != kind:
                continue
            if title not in created:
                px.note(f"CLEANUP refusing to close {title}: the probe did not create it")
                continue
            call(sc.app(px), "CloseDoc", title)
    return [title for path, (title, _) in _open_paths(px).items() if path in wanted]


def _save_in_place(px: Px, doc: Any, path: str, label: str) -> bool:
    """``SaveAs3`` to ``path``, silently: a first save, or onto the document's own path (probe save_as: it overwrites)."""
    got, result = px.attempt(f"SaveAs3 {label} to {os.path.basename(path)}",
                             lambda: call(sc.extension(doc), "SaveAs3", path, SAVE_AS_CURRENT_VERSION,
                                          SAVE_AS_SILENT, sc.null(), sc.null(), sc.out_long(), sc.out_long()))
    flag = result[0] if got and isinstance(result, tuple) and result else result
    return bool(got and flag)


# -- 1: planes from Right and Top --------------------------------------------


@probe("layout_planes", needs=("ref_plane_offset",), tier=7,
       members=("IFeatureManager.InsertRefPlane", "IRefPlane.Transform", "IEquationMgr.Add2", "IEquationMgr.Equation"))
def layout_planes(px: Px) -> None:
    """Planes offset from Right and from Top: which side each flip puts them, measured; and their offsets driven by globals."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        _millimetres(px, doc)
        names = [str(call(p, "Name")) for p in sc.planes(doc)]
        px.fact("plane_names_in_tree_order", names)
        normals = {}
        for key, index in (("front", 1), ("top", 2), ("right", 3)):
            _origin, _x, _y, normal = plane_frame(px, doc, sc.planes(doc)[index - 1])
            normals[key] = _rounded(normal)
        px.fact("base_plane_normals", normals)
        px.require(abs(abs(normals["right"][0]) - 1.0) < 1e-9, f"plane 3 is square to X: {normals['right']}")
        px.require(abs(abs(normals["top"][1]) - 1.0) < 1e-9, f"plane 2 is square to Y: {normals['top']}")

        positions: Dict[str, Dict[str, Any]] = {}
        made: Dict[Tuple[str, bool], Any] = {}
        plus: Dict[str, Optional[bool]] = {}
        agree: Dict[str, Optional[bool]] = {}
        for key, index, axis in (("right", 3, 0), ("top", 2, 1)):
            sides: Dict[str, float] = {}
            for flip in (False, True):
                plane = offset_plane(px, doc, OFFSET, flip, base=index)
                made[(key, flip)] = plane
                where = _measure(px, doc, plane)
                positions.setdefault(key, {})[str(flip)] = where
                sides[str(flip)] = where["origin_mm"][axis]
                # A second reading, kept as evidence: the sketch's is the one ref_plane_offset was settled by.
                second = where.get("transform_origin_mm")
                agree[f"{key} {flip}"] = None if second is None else abs(second[axis] - sides[str(flip)]) < TOLERANCE_MM
                if agree[f"{key} {flip}"] is False:
                    px.note(f"{key}, flip {flip}: IRefPlane.Transform puts the plane at {second[axis]}, "
                            f"the sketch at {sides[str(flip)]}")
            plus[key] = plus_flip(sides)
            px.check(plus[key] is not None, f"from {key} the two flips put the plane {OFFSET:g} mm either side: {sides}")
        px.fact("layout_plane_positions", positions)
        px.fact("ref_plane_transform_agrees_with_sketch", agree)
        px.require(all(v is not None for v in plus.values()), "both base planes have a plus-side flip")
        px.fact("layout_plus_flip", plus, f"flip {plus['right']} is +X from Right; flip {plus['top']} is +Y from Top")
        px.shared["layout_plus_flip"] = plus

        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        defaults: Dict[str, str] = {}
        follows: Dict[str, Any] = {}
        for key, axis, letter in (("right", 0, "X"), ("top", 1, "Y")):
            plane = made[(key, bool(plus[key]))]
            name = _rename(px, plane, f"Probe S1 {letter} Plane")
            defaults[key] = _name_offset(px, plane, OFFSET)
            _link(px, add, name, f"Probe S1 {letter}", OFFSET)
            read = _set_global(eqm, f"Probe S1 {letter}", MOVED)
            call(doc, "ForceRebuild3", False)
            where = _measure(px, doc, plane)["origin_mm"][axis]
            follows[key] = {"set": read, "plane_at_mm": where}
            px.check(abs(where - MOVED) < TOLERANCE_MM, f"its global set to {MOVED:g}, the {letter} plane moves to {where}")
        px.fact("layout_offset_dim_default_names", defaults)
        px.fact("layout_offset_follows_global", follows)

        # A plane on the minus side keeps a positive offset; can it follow a signed global?
        plane = made[("right", not bool(plus["right"]))]
        name = _rename(px, plane, "Probe S2 X Plane")
        _name_offset(px, plane, OFFSET)
        px.require(add(f'"Probe S2 X"= {-OFFSET:g}') >= 0, f'the global "Probe S2 X" is added at {-OFFSET:g}')
        tried: Dict[str, Any] = {}
        form = None
        target = -OFFSET
        for label, text in (("minus", f'"Offset@{name}"= - "Probe S2 X"'),
                            ("times minus one", f'"Offset@{name}"= -1 * "Probe S2 X"'),
                            ("abs", f'"Offset@{name}"= abs ( "Probe S2 X" )')):
            got, index = px.attempt(f"negated link, {label}: {text}", lambda t=text: add(t))
            if not got or index is None or int(index) < 0:
                tried[label] = {"accepted": False}
                continue
            target -= 4.0   # a new value each time, so a form that does nothing cannot look as if it worked
            _set_global(eqm, "Probe S2 X", target)
            call(doc, "ForceRebuild3", False)
            at = _measure(px, doc, plane)["origin_mm"][0]
            tried[label] = {"accepted": True, "global": target, "plane_at_mm": at}
            if abs(at - target) < TOLERANCE_MM:
                form = label
                break
            call(eqm, "Delete", int(index))
        px.fact("negated_global_link", tried)
        px.fact("negated_global_link_form", form)
        if form is None:
            px.note("a minus-side plane did not follow a negative global by any form; "
                    "the layout would keep each offset's size in a global of its own")


# -- 2: an axis through two planes made in the same part ----------------------


@probe("axis_through_named_planes", needs=("layout_planes", "axis"), tier=7,
       members=("IModelDoc2.InsertAxis2", "IFeature.Select2", "IModelDocExtension.SelectByID2",
                "IRefAxis.GetRefAxisParams"))
def axis_through_named_planes(px: Px) -> None:
    """InsertAxis2 through two planes made in this part, each selection route on its own shaft, and the axis following their globals."""
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        _millimetres(px, doc)
        planes: Dict[str, Tuple[Tuple[Any, Any], Tuple[Any, Any]]] = {}
        for shaft, x, y in NAMED_SHAFTS:
            planes[shaft] = (_layout_plane(px, doc, "x", x, f"Probe {shaft} X Plane"),
                             _layout_plane(px, doc, "y", y, f"Probe {shaft} Y Plane"))
        px.fact("returned_by_insert_ref_plane", sc.type_name(planes[NAMED_SHAFTS[0][0]][0][1]))

        routes: Dict[str, Any] = {}
        axes: Dict[str, Any] = {}
        where: Dict[str, Any] = {}
        for (shaft, x, y), route in zip(NAMED_SHAFTS, PLANE_ROUTES):
            selected = _select_two(px, doc, route, planes[shaft])
            routes[route] = selected
            if not selected:
                px.note(f"{route} did not select {shaft}'s two planes")
                continue
            axis = _insert_axis(px, doc, f"Probe {shaft} Axis")
            routes[route] = axis is not None
            if axis is not None:
                axes[shaft] = axis
                where[shaft] = _check_axis(px, axis, x, y, f"{shaft}'s axis, by {route}")
        px.fact("axis_plane_select_routes", routes)
        px.fact("named_axes", where)
        working = [r for r in PLANE_ROUTES[:2] if routes.get(r)]
        px.require(bool(working), "the planes select by name or by the feature found by name, and an axis is made")
        px.fact("axis_plane_select_route", working[0])
        px.shared["axis_plane_select_route"] = working[0]

        # Each plane's offset driven by a global, as the layout part's are; then one shaft moved.
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        for shaft, x, y in NAMED_SHAFTS:
            (xp, _), (yp, _) = planes[shaft]
            for plane, letter, value in ((xp, "X", x), (yp, "Y", y)):
                _name_offset(px, plane, abs(value))
                _link(px, add, str(call(plane, "Name")), f"Probe {shaft} {letter}", abs(value))
        shaft, x0, y0 = NAMED_SHAFTS[PLANE_ROUTES.index(working[0])]
        x, y = moved_away(x0, y0)
        _set_global(eqm, f"Probe {shaft} X", abs(x))
        _set_global(eqm, f"Probe {shaft} Y", abs(y))
        call(doc, "ForceRebuild3", False)
        after: Dict[str, Any] = {}
        for name, xn, yn in NAMED_SHAFTS:
            if name not in axes:
                continue
            want = (x, y) if name == shaft else (xn, yn)
            after[name] = _check_axis(px, axes[name], want[0], want[1],
                                      f"after {shaft} moved, {name}'s axis" if name != shaft else f"{shaft}'s axis, moved")
        px.fact("named_axes_after_globals", after)


# -- 3: a shaft on a base plane ---------------------------------------------


@probe("axis_through_base_planes", needs=("axis_through_named_planes",), tier=7,
       members=("IModelDoc2.InsertAxis2", "IModelDocExtension.SelectByID2", "IRefAxis.GetRefAxisParams"))
def axis_through_base_planes(px: Px) -> None:
    """A shaft at X = 0, at Y = 0 and at both: the base plane itself in place of an offset plane, by the decided route."""
    route = px.shared.get("axis_plane_select_route")
    px.require(bool(route), "axis_through_named_planes decided how planes are selected")
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        _millimetres(px, doc)
        top, right = sc.planes(doc)[1], sc.planes(doc)[2]
        made: Dict[str, Dict[str, Any]] = {}
        axes: Dict[str, Any] = {}
        where: Dict[str, Any] = {}
        for shaft, x, y in BASE_SHAFTS:
            xp = (right, None) if x == 0.0 else _layout_plane(px, doc, "x", x, f"Probe {shaft} X Plane")
            yp = (top, None) if y == 0.0 else _layout_plane(px, doc, "y", y, f"Probe {shaft} Y Plane")
            made[shaft] = {"x": xp[0] if x != 0.0 else None, "y": yp[0] if y != 0.0 else None}
            selected = _select_two(px, doc, route, (xp, yp))
            if not px.check(selected, f"{shaft}: the two planes select by {route}"):
                continue
            axis = _insert_axis(px, doc, f"Probe {shaft} Axis")
            if axis is not None:
                axes[shaft] = axis
                where[shaft] = _check_axis(px, axis, x, y, f"{shaft}'s axis")
        px.fact("base_plane_axes", where)
        px.require(len(axes) == len(BASE_SHAFTS), "every base-plane shaft has its axis")

        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        for shaft, x, y in BASE_SHAFTS:
            for letter, value in (("X", x), ("Y", y)):
                plane = made[shaft][letter.lower()]
                if plane is not None:
                    _name_offset(px, plane, abs(value))
                    _link(px, add, str(call(plane, "Name")), f"Probe {shaft} {letter}", abs(value))
        for shaft, (x, y) in BASE_MOVE.items():
            for letter, value in (("X", x), ("Y", y)):
                if made[shaft][letter.lower()] is not None:
                    _set_global(eqm, f"Probe {shaft} {letter}", abs(value))
        call(doc, "ForceRebuild3", False)
        after = {}
        for shaft, x, y in BASE_SHAFTS:
            want = BASE_MOVE.get(shaft, (x, y))
            after[shaft] = _check_axis(px, axes[shaft], want[0], want[1], f"after the globals moved, {shaft}'s axis")
        px.fact("base_plane_axes_after_globals", after)


# -- 4: five components, saved, reopened, found and re-placed -----------------


@probe("layout_assembly_five", needs=("nonparallel_mates", "save_as"), tier=7,
       members=("IAssemblyDoc.AddComponent5", "IComponent2.Transform2", "IAssemblyDoc.FixComponent",
                "IComponent2.IsFixed", "IModelDocExtension.SaveAs3", "ISldWorks.CloseDoc"))
def layout_assembly_five(px: Px) -> None:
    """Five components, one part twice, inserted, placed and fixed; the assembly saved and closed with its parts."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    asm_path = os.path.join(folder, f"{ASSEMBLY_STEM}.SLDASM")
    px.require(not os.path.exists(asm_path), f"{asm_path} does not exist yet")
    parts: Dict[str, str] = {}
    asm = None
    try:
        for stem, _matrix, _at in COMPONENTS:
            if stem not in parts:
                _doc, parts[stem] = _part_with_axis(px, folder, stem)
        asm = sc.new_document(px, sc.SW_DOC_ASSEMBLY)
        _millimetres(px, asm)
        components = []
        for stem, _matrix, at in COMPONENTS:
            got, component = px.attempt(f"AddComponent5({stem})",
                                        lambda s=stem, a=at: call(asm, "AddComponent5", parts[s], 0, "", False, "",
                                                                  sc.m(a[0]), sc.m(a[1]), sc.m(a[2])))
            px.require(got and component is not None, f"{stem} is inserted")
            components.append(component)
        names = [str(call(c, "Name2")) for c in components]
        px.fact("component_names", names)
        px.fact("component_instances", instance_stems(names))
        px.require(len(set(names)) == len(names), f"every component has a name of its own: {names}")

        routes = []
        for component, (_stem, matrix, at) in zip(components, COMPONENTS):
            routes.append(place(px, asm, component, matrix, at))
        px.fact("place_routes", sorted(set(f"{r} ({o})" for r, o in routes)))
        order = routes[0][1]

        px.fact("fixed_on_insert", {n: bool(call(c, "IsFixed")) for n, c in zip(names, components)})
        for name, component in zip(names, components):
            if bool(call(component, "IsFixed")):
                continue
            call(asm, "ClearSelection2", True)
            px.require(bool(call(component, "Select4", False, sc.null(), False)), f"{name} selects")
            px.attempt(f"FixComponent() on {name}", lambda: asm.FixComponent())
            call(asm, "ClearSelection2", True)
        fixed = {n: bool(call(c, "IsFixed")) for n, c in zip(names, components)}
        px.fact("fixed_after_fix_component", fixed)
        px.check(all(fixed.values()), f"every component is fixed: {fixed}")
        call(asm, "ForceRebuild3", False)
        errors = {}
        for name, component, (_stem, matrix, at) in zip(names, components, COMPONENTS):
            rotation, origin = frame_error(component, matrix, at)
            errors[name] = {"rotation": rotation, "origin_mm": origin}
            px.check(rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM,
                     f"{name} keeps its frame once fixed (rotation off {rotation:.1e}, origin {origin:.1e} mm)")
        px.fact("frames_after_fix", errors)

        got, result = px.attempt("SaveAs3(the assembly, current version, silent)",
                                 lambda: call(sc.extension(asm), "SaveAs3", asm_path, SAVE_AS_CURRENT_VERSION,
                                              SAVE_AS_SILENT, sc.null(), sc.null(), sc.out_long(), sc.out_long()))
        px.shared.setdefault("created", []).append(str(call(asm, "GetTitle")))
        px.require(os.path.isfile(asm_path), f"the assembly is saved at {asm_path}: {result!r}")
        px.fact("assembly_title_after_save", str(call(asm, "GetTitle")))
        px.shared["w7_assembly"] = {
            "path": asm_path,
            "parts": parts,
            "order": order,
            "frames": {n: (matrix, at) for n, (_s, matrix, at) in zip(names, COMPONENTS)},
        }
    finally:
        if asm is not None and not str(call(asm, "GetPathName") or ""):
            sc.close(px, asm)   # never saved, so it has no path to close it by
        left = close_paths(px, [asm_path] + list(parts.values()))
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.check(not left, "the assembly and its parts are all closed")


def find_components(px: Px, asm: Any, names: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Each component, found by name, by every route there is: route → name → component (or missing)."""
    found: Dict[str, Dict[str, Any]] = {route: {} for route in FIND_ROUTES}

    def by_name2(listed: Any) -> Dict[str, Any]:
        out = {}
        for component in list(listed or ()):
            out[str(call(component, "Name2"))] = component
        return out

    for name in names:
        got, component = px.attempt(f"GetComponentByName({name})", lambda n=name: call(asm, "GetComponentByName", n))
        if got and component is not None:
            found[FIND_ROUTES[0]][name] = component
    got, listed = px.attempt("GetComponents(True)", lambda: by_name2(call(asm, "GetComponents", True)))
    if got:
        found[FIND_ROUTES[1]] = {n: c for n, c in listed.items() if n in names}

    def children() -> Dict[str, Any]:
        configuration, _form = member(asm, "GetActiveConfiguration")
        root = call(configuration, "GetRootComponent3", True)
        listed_children, _ = member(root, "GetChildren")
        return by_name2(listed_children)

    got, listed = px.attempt("GetActiveConfiguration, GetRootComponent3(True), GetChildren", children)
    if got:
        found[FIND_ROUTES[2]] = {n: c for n, c in listed.items() if n in names}
    for name in names:
        got, component = px.attempt(f"FeatureByName({name}).GetSpecificFeature2",
                                    lambda n=name: call(call(asm, "FeatureByName", n), "GetSpecificFeature2"))
        if got and component is not None:
            found[FIND_ROUTES[3]][name] = component
    for route, hits in found.items():
        for name, component in list(hits.items()):
            try:
                kept = str(call(component, "Name2"))
            except Exception as exc:  # noqa: BLE001 - what came back is not a component
                px.note(f"{route} gave {name} as something with no Name2: {exc}")
                del hits[name]
                continue
            if kept != name:
                px.note(f"{route} asked for {name} gave {kept}")
                del hits[name]
    return found


def _put_frame(px: Px, asm: Any, component: Any, matrix: Matrix, at: Sequence[float], order: str,
               label: str) -> Tuple[float, float]:
    transform = make_transform(px, array_data(matrix, at, order))
    px.attempt(f"Transform2 put on {label}", lambda: setattr(component, "Transform2", transform))
    call(asm, "ForceRebuild3", False)
    return frame_error(component, matrix, at)


def _replace(px: Px, asm: Any, name: str, component: Any, matrix: Matrix, at: Sequence[float],
             order: str) -> Optional[str]:
    """Move a fixed component to a new frame: put straight on, or else unfixed, put and fixed again."""
    rotation, origin = _put_frame(px, asm, component, matrix, at, order, f"{name} (fixed)")
    if rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM:
        return "Transform2 put"
    px.note(f"{name} did not move while fixed (rotation off {rotation:.1e}, origin {origin:.1e} mm)")
    call(asm, "ClearSelection2", True)
    if not call(component, "Select4", False, sc.null(), False):
        return None
    px.attempt(f"UnfixComponent() on {name}", lambda: asm.UnfixComponent())
    call(asm, "ClearSelection2", True)
    px.fact(f"{name} fixed after UnfixComponent", bool(call(component, "IsFixed")))
    rotation, origin = _put_frame(px, asm, component, matrix, at, order, f"{name} (unfixed)")
    call(asm, "ClearSelection2", True)
    if call(component, "Select4", False, sc.null(), False):
        px.attempt(f"FixComponent() on {name}", lambda: asm.FixComponent())
    call(asm, "ClearSelection2", True)
    if rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM and bool(call(component, "IsFixed")):
        return "UnfixComponent, Transform2 put, FixComponent"
    return None


@probe("layout_assembly_reopen", needs=("layout_assembly_five",), tier=7,
       members=("ISldWorks.OpenDoc6", "ISldWorks.OpenDoc7", "IAssemblyDoc.GetComponentByName",
                "IAssemblyDoc.GetComponents", "IComponent2.GetChildren", "IComponent2.Transform2",
                "IAssemblyDoc.UnfixComponent", "IComponent2.GetSuppression2"))
def layout_assembly_reopen(px: Px) -> None:
    """The saved assembly opened by path: each component found by name, where it was left, re-placed while fixed, and kept."""
    info = px.shared.get("w7_assembly")
    px.require(bool(info), "layout_assembly_five left an assembly to reopen")
    asm_path, frames, order = info["path"], info["frames"], info["order"]
    names = list(frames)
    paths = [asm_path] + list(info["parts"].values())
    px.require(not any(os.path.normcase(p) in _open_paths(px) for p in paths), "none of its files is open")
    px.fact("open_doc_options", _enum(px, "swOpenDocOptions_e"))
    moved = {n: (turned(m, REPLACE_TURN), shifted(at, REPLACE_SHIFT)) for n, (m, at) in frames.items()
             if not n.startswith(LAYOUT_STEM)}
    try:
        asm, route = open_by_path(px, asm_path, sc.SW_DOC_ASSEMBLY)
        px.fact("open_assembly_route", route)
        px.shared["w7_open_route"] = route
        px.fact("opened_assembly_is_active", _active_title(px) == str(call(asm, "GetTitle")))
        got, count = px.attempt("GetComponentCount(True)", lambda: call(asm, "GetComponentCount", True))
        px.fact("component_count_after_reopen", plain(count) if got else None)

        found = find_components(px, asm, names)
        counts = {r: sorted(hits) for r, hits in found.items()}
        px.fact("component_find_routes", counts)
        winners = [r for r in FIND_ROUTES if len(found[r]) == len(names)]
        px.require(bool(winners), f"some route finds all {len(names)} components by name: {counts}")
        px.fact("component_find_route", winners[0])
        components = found[winners[0]]

        states = {}
        for name, component in components.items():
            got, state = px.attempt(f"GetSuppression2 of {name}", lambda c=component: member(c, "GetSuppression2"))
            states[name] = plain(state[0]) if got else None
        px.fact("suppression_after_reopen", states)
        px.fact("suppression_states", _enum(px, "swComponentSuppressionState_e"))

        kept = {}
        for name, (matrix, at) in frames.items():
            rotation, origin = frame_error(components[name], matrix, at)
            kept[name] = {"rotation": rotation, "origin_mm": origin, "fixed": bool(call(components[name], "IsFixed"))}
            px.check(rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM and kept[name]["fixed"],
                     f"{name} is where it was left, and fixed (rotation off {rotation:.1e}, origin {origin:.1e} mm)")
        px.fact("frames_after_reopen", kept)

        replaced = {}
        for name, (matrix, at) in moved.items():
            replaced[name] = _replace(px, asm, name, components[name], matrix, at, order)
            px.check(replaced[name] is not None, f"{name} is re-placed: {replaced[name]}")
        px.fact("replace_routes", replaced)
        routes = sorted(set(r for r in replaced.values() if r))
        px.require(len(routes) == 1 and None not in replaced.values(), f"every gear re-places by one route: {replaced}")
        px.fact("replace_fixed_route", routes[0])
        others = {}
        for name, (matrix, at) in frames.items():
            if name in moved:
                continue
            rotation, origin = frame_error(components[name], matrix, at)
            others[name] = {"rotation": rotation, "origin_mm": origin}
            px.check(rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM, f"{name}, not re-placed, did not move")
        px.fact("frames_not_replaced", others)
        px.check(_save_in_place(px, asm, asm_path, "the re-placed assembly"), "the re-placed assembly saves")
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")

    # And once more, to see the new frames were saved.
    try:
        asm, _route = open_by_path(px, asm_path, sc.SW_DOC_ASSEMBLY, prefer=px.shared.get("w7_open_route", ""))
        found = find_components(px, asm, list(moved))
        components = found.get(px.record.facts.get("component_find_route", ""), {})
        persisted = {}
        for name, (matrix, at) in moved.items():
            if not px.check(name in components, f"opened again, {name} is found by the same route"):
                continue
            rotation, origin = frame_error(components[name], matrix, at)
            persisted[name] = {"rotation": rotation, "origin_mm": origin}
            px.check(rotation < TOLERANCE_ROTATION and origin < TOLERANCE_MM,
                     f"opened again, {name} is where it was re-placed (rotation off {rotation:.1e}, origin {origin:.1e} mm)")
        px.fact("replaced_frames_after_second_open", persisted)
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.check(not left, "the assembly and its parts are all closed")


# -- 5: a part opened by path and made active, for Update SolidWorks ---------


def _update(px: Px, path: str, name: str, value: str) -> Dict[str, Any]:
    """The tool's own ``swbuild.update_variables`` on the active document, expecting ``path``."""
    from .. import swbuild  # noqa: PLC0415 - as p5_end_to_end does

    got, result = px.attempt(f"swbuild.update_variables({name} = {value})",
                             lambda: swbuild.update_variables(px.session, [GlobalVariable(name, value)], path))
    if not got:
        return {"ok": False, "error": result}
    return {"ok": bool(result.ok), "changed": list(result.changed), "failures": [list(f) for f in result.failures],
            "rebuilt": bool(result.rebuilt), "document": result.document}


@probe("open_and_activate_part", needs=("save_as", "activate_document", "equation_set"), tier=7,
       members=("ISldWorks.OpenDoc6", "ISldWorks.OpenDoc7", "ISldWorks.GetOpenDocSpec", "ISldWorks.ActivateDoc3",
                "swbuild.update_variables"))
def open_and_activate_part(px: Px) -> None:
    """A closed part opened by path while another is active, made active, and changed by update_variables; then again while open."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    path = os.path.join(folder, "Probe W7 Open.SLDPRT")
    px.require(not os.path.exists(path), f"{path} does not exist yet")
    try:
        doc = sc.new_document(px)
        _millimetres(px, doc)
        eqm = call(doc, "GetEquationMgr")
        px.require(adder(px, eqm)('"Probe Teeth"= 12') >= 0, 'the global "Probe Teeth" is added')
        px.require(_save_in_place(px, doc, path, "the part") or os.path.isfile(path), "the part is saved")
        px.require(os.path.isfile(path), f"the part is on disk at {path}")
        title = str(call(doc, "GetTitle"))
        px.shared.setdefault("created", []).append(title)
        close_paths(px, [path])
        px.require(os.path.normcase(path) not in _open_paths(px), "the part is closed")

        with sc.scratch(px) as other:
            other_title = str(call(other, "GetTitle"))
            px.require(_active_title(px) == other_title, "another document is active, as the user's would be")

            opened, route = open_by_path(px, path)
            opened_title = str(call(opened, "GetTitle"))
            px.fact("open_doc_route", route)
            px.fact("opened_part_title", opened_title)
            px.fact("open_doc_makes_active", _active_title(px) == opened_title)
            px.require(activate(px, opened_title), "ActivateDoc3 makes the opened part active")
            px.check(same_path(_active_path(px), path), "the active document's path is the part's")
            update = _update(px, path, "Probe Teeth", "13")
            px.fact("update_after_open", update)
            px.check(update.get("ok") and update.get("changed") == ["Probe Teeth"],
                     f"update_variables accepts the opened part and changes the global: {update}")
            value = _global_value(call(opened, "GetEquationMgr"), "Probe Teeth")
            px.check(value == 13.0, f'"Probe Teeth" reads {value}')

            # Already open, but behind another document: does opening it again bring it forward, or open a second copy?
            px.require(activate(px, other_title), "the other document is active again")
            again, route_again = open_by_path(px, path, prefer=route)
            again_title = str(call(again, "GetTitle"))
            px.fact("open_doc_on_open_part", {"route": route_again, "title": again_title,
                                              "same_title": again_title == opened_title,
                                              "made_active": _active_title(px) == again_title})
            px.check(again_title == opened_title, "opening an open part gives back the same document")
            px.require(activate(px, again_title), "ActivateDoc3 brings the open part forward")
            update = _update(px, path, "Probe Teeth", "14")
            px.fact("update_after_reactivate", update)
            px.check(update.get("ok") and update.get("changed") == ["Probe Teeth"],
                     f"update_variables accepts it again: {update}")
    finally:
        left = close_paths(px, [path])
        if left:
            px.note(f"CLEANUP still open after closing: {left}")


@probe("open_part_from_assembly", needs=("open_and_activate_part", "layout_assembly_reopen"), tier=7,
       members=("ISldWorks.OpenDoc6", "ISldWorks.ActivateDoc3", "swbuild.update_variables"))
def open_part_from_assembly(px: Px) -> None:
    """A part loaded only as a component of an open assembly, opened by path, made active and changed by update_variables."""
    info = px.shared.get("w7_assembly")
    px.require(bool(info), "layout_assembly_five left an assembly")
    asm_path = info["path"]
    part_path = info["parts"]["Probe W7 A"]
    paths = [asm_path] + list(info["parts"].values())
    route = px.shared.get("w7_open_route", "")
    try:
        asm, _ = open_by_path(px, asm_path, sc.SW_DOC_ASSEMBLY, prefer=route)
        asm_title = str(call(asm, "GetTitle"))
        px.fact("component_part_listed_open_with_assembly", os.path.normcase(part_path) in _open_paths(px))
        part, part_route = open_by_path(px, part_path, prefer=route)
        title = str(call(part, "GetTitle"))
        px.fact("open_component_part", {"route": part_route, "title": title,
                                        "made_active": _active_title(px) == title, "assembly": asm_title})
        px.require(activate(px, title), "ActivateDoc3 makes the component's part active")
        px.check(same_path(_active_path(px), part_path), "the active document's path is the part's")
        px.require(adder(px, call(part, "GetEquationMgr"))('"Probe Teeth"= 20') >= 0, "a global is added to the part")
        update = _update(px, part_path, "Probe Teeth", "21")
        px.fact("update_component_part", update)
        px.check(update.get("ok") and update.get("changed") == ["Probe Teeth"],
                 f"update_variables accepts a part the assembly has open: {update}")
        px.check(_global_value(call(part, "GetEquationMgr"), "Probe Teeth") == 21.0, '"Probe Teeth" reads 21')
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.check(not left, "the assembly and its parts are all closed")


# -- extra: an offset's global below zero ------------------------------------


@probe("layout_plane_negative_global", needs=("layout_planes",), tier=7, extra=True,
       members=("IFeatureManager.InsertRefPlane", "IEquationMgr.Equation", "IFeature.GetErrorCode2"))
def layout_plane_negative_global(px: Px) -> None:
    """A plane's offset linked to a global, and the global set below zero: does the plane cross, refuse, or error?

    Extra and last, because a rebuild error might open a dialog in some
    sessions, and a dialog hangs the run.
    """
    plus = (px.shared.get("layout_plus_flip") or {}).get("right")
    px.require(plus is not None, "layout_planes said which flip is +X")
    with sc.quiet_dimensions(px), sc.scratch(px) as doc:
        _millimetres(px, doc)
        plane = offset_plane(px, doc, OFFSET, bool(plus), base=3)
        name = _rename(px, plane, "Probe N X Plane")
        _name_offset(px, plane, OFFSET)
        eqm = call(doc, "GetEquationMgr")
        _link(px, adder(px, eqm), name, "Probe N X", OFFSET)
        read = _set_global(eqm, "Probe N X", NEGATIVE)
        got, rebuilt = px.attempt("ForceRebuild3 with the global below zero", lambda: call(doc, "ForceRebuild3", False))
        got_error, error = px.attempt("GetErrorCode2 of the plane", lambda: call(plane, "GetErrorCode2", _out_bool()))
        offset = None
        for dimension in sc.dimensions_of(plane):
            if str(call(dimension, "Name")) == "Offset":
                offset = float(call(dimension, "SystemValue")) * sc.MM
        def measured() -> float:
            try:
                return _measure(px, doc, plane)["origin_mm"][0]
            except Require as exc:   # a plane in error may not select; that is an answer, not the end
                raise RuntimeError(str(exc)) from None

        got_where, where = px.attempt("measure the plane", measured)
        x = where if got_where else None
        crosses = None if x is None else abs(x - NEGATIVE) < TOLERANCE_MM
        px.fact("negative_global", {"equation": read, "global_value": _global_value(eqm, "Probe N X"),
                                    "rebuild": plain(rebuilt) if got else "raised",
                                    "error_code": plain(error) if got_error else "raised",
                                    "offset_mm": offset, "plane_x_mm": x})
        px.fact("crosses_zero", crosses)
        px.check(crosses is not None, f"where the plane went could be read: {x}")
