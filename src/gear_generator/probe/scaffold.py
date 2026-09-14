"""What every probe needs around the call it is actually probing.

A scratch part it made itself, closed afterwards; the reference planes in tree
order rather than by their English names; a feature-tree diff; a selection;
the part's volume as an oracle. These are raw COM on purpose, and small, so a
probe's report shows the calls that ran rather than a layer that hid them.

Everything here runs on the worker thread. Lengths cross in metres.
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from .. import swcom
from ..swcom import call
from .harness import Px, Require

MM = 1000.0

# swconst, read from swconst.tlb on SolidWorks 2026 (revision 34) with makepy.
SW_DOC_PART = 1
SW_DOC_ASSEMBLY = 2
SW_DEFAULT_TEMPLATE_PART = 8
SW_DEFAULT_TEMPLATE_ASSEMBLY = 9

# swUserPreferenceToggle_e and swUserPreferenceIntegerValue_e, same source.
SW_INPUT_DIM_VAL_ON_CREATE = 10     # the dimension-value dialog on AddDimension2: a modal hang if left on
SW_UNITS_LINEAR = 47
SW_UNIT_SYSTEM = 263
SW_DETAILING_NO_OPTION = 0
SW_MM = 0
SW_INCHES = 3
SW_UNIT_SYSTEM_MMGS = 5

# swSketchSegments_e and swConstrainedStatus_e, same source.
SW_SKETCH_LINE = 0
SW_SKETCH_ARC = 1
SW_SKETCH_SPLINE = 3
SW_UNDER_CONSTRAINED = 2
SW_FULLY_CONSTRAINED = 3
SW_OVER_CONSTRAINED = 4

# The Context's known-good template paths on this machine.
FALLBACK_TEMPLATES = {
    SW_DOC_PART: r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2026\templates\Part.PRTDOT",
    SW_DOC_ASSEMBLY: r"C:\ProgramData\SOLIDWORKS\SOLIDWORKS 2026\templates\Assembly.ASMDOT",
}


_LAST_APP: List[Any] = []


def app(px: Px) -> Any:
    application = px.session._app  # noqa: SLF001 - probes call raw members by design
    _LAST_APP[:] = [application]
    return application


def _active_title() -> str:
    if not _LAST_APP:
        return "unknown"
    active = call(_LAST_APP[0], "ActiveDoc")
    return "nothing" if active is None else str(call(active, "GetTitle"))


def null() -> Any:
    return swcom._null_dispatch()  # noqa: SLF001


def out_long() -> Any:
    return swcom._out_long()  # noqa: SLF001


def m(mm: float) -> float:
    return mm / MM


def type_name(obj: Any) -> str:
    """``GetTypeName2`` first, defaulting to ``?`` — never let naming a failure fail."""
    try:
        return str(call(obj, "GetTypeName2"))
    except Exception:  # noqa: BLE001
        return "?"


def open_titles(px: Px) -> List[str]:
    titles: List[str] = []
    doc = call(app(px), "GetFirstDocument")
    guard = 0
    while doc is not None and guard < 500:
        guard += 1
        titles.append(str(call(doc, "GetTitle")))
        doc = call(doc, "GetNext")
    return titles


def template(px: Px, doc_type: int = SW_DOC_PART) -> str:
    """The template a probe makes documents from: what tier 0 found, or the fallback."""
    key = "part_template" if doc_type == SW_DOC_PART else "assembly_template"
    return px.shared.get(key) or FALLBACK_TEMPLATES[doc_type]


def new_document(px: Px, doc_type: int = SW_DOC_PART, path: str = "") -> Any:
    path = path or template(px, doc_type)
    doc = call(app(px), "NewDocument", path, 0, 0.0, 0.0)
    if doc is None:
        raise Require(f"NewDocument returned nothing for {path}.")
    title = str(call(doc, "GetTitle"))
    px.shared.setdefault("created", []).append(title)
    return doc


def close(px: Px, doc: Any) -> None:
    """Close a document this probe made. Never one it did not."""
    title = str(call(doc, "GetTitle"))
    if title not in px.shared.get("created", []):
        raise Require(f"Refusing to close {title}: the probe did not create it.")
    if px.options.get("keep"):
        return
    call(app(px), "CloseDoc", title)


@contextlib.contextmanager
def scratch(px: Px, doc_type: int = SW_DOC_PART, path: str = "") -> Iterator[Any]:
    """A fresh document for the length of a probe, closed afterwards unless --keep."""
    doc = new_document(px, doc_type, path)
    try:
        yield doc
    finally:
        try:
            app(px).CommandInProgress = False
        except Exception:  # noqa: BLE001 - restoring the flag must not mask the probe's own error
            pass
        try:
            close(px, doc)
        except Exception as exc:  # noqa: BLE001
            px.note(f"CLEANUP could not close the scratch document: {exc}")


def top_features(doc: Any) -> List[Any]:
    out: List[Any] = []
    feature = call(doc, "FirstFeature")
    guard = 0
    while feature is not None and guard < 5000:
        guard += 1
        out.append(feature)
        feature = call(feature, "GetNextFeature")
    return out


def feature_names(doc: Any) -> List[str]:
    return [str(call(f, "Name")) for f in top_features(doc)]


def feature_by_name(doc: Any, name: str) -> Any:
    for feature in top_features(doc):
        if str(call(feature, "Name")) == name:
            return feature
    raise Require(f"No feature called {name!r}.")


def new_features(doc: Any, before: Sequence[str]) -> List[Tuple[str, str]]:
    """``(name, type)`` of every top-level feature not in ``before``."""
    seen = set(before)
    return [(str(call(f, "Name")), type_name(f)) for f in top_features(doc) if str(call(f, "Name")) not in seen]


def planes(doc: Any) -> List[Any]:
    """The reference planes in tree order: Front, Top, Right in an English template."""
    return [f for f in top_features(doc) if type_name(f) == "RefPlane"]


# Which route last selected a feature, so the report can say. On SolidWorks 2026
# IFeature::Select2 on a reference plane returned True in one session and False
# in a later one with identical code, while SelectByID2 with the plane's own
# name (read from the tree, so no English is assumed) selected it both times.
SELECT_ROUTES: Dict[str, int] = {}

SELECT_TYPES = {"RefPlane": "PLANE", "RefAxis": "AXIS", "ProfileFeature": "SKETCH"}


def selected_count(doc: Any) -> int:
    return int(call(call(doc, "SelectionManager"), "GetSelectedObjectCount2", -1) or 0)


RETRIES = 4
RETRY_PAUSE = 0.25   # seconds


def _count(route: str) -> None:
    SELECT_ROUTES[route] = SELECT_ROUTES.get(route, 0) + 1


def _retrying(doc: Any, attempt: Any, before: int, route: str) -> bool:
    """Try an object's own select a few times, judging by the selection count.

    On SolidWorks 2026 Select2 and Select4 each returned False with nothing
    selected in one run and True on the same kind of object in the next, which
    looks like timing just after the object was made rather than anything about
    the object. So a refusal is retried briefly before a fallback is used, and
    how often that was needed is kept as evidence.
    """
    for number in range(RETRIES):
        if attempt() and selected_count(doc) > before:
            _count(route if number == 0 else f"{route} after {number} retr{'y' if number == 1 else 'ies'}")
            return True
        time.sleep(RETRY_PAUSE)
    return False


def select_feature(doc: Any, feature: Any, append: bool = False, mark: int = 0) -> bool:
    """Select a feature: IFeature::Select2, then SelectByID2 by its read-back name.

    Success is judged by the selection count going up, not by the return value.
    """
    if not append:
        call(doc, "ClearSelection2", True)
    before = selected_count(doc)
    if _retrying(doc, lambda: call(feature, "Select2", append, mark), before, "Select2"):
        return True
    kind = SELECT_TYPES.get(type_name(feature), "BODYFEATURE")
    name = str(call(feature, "Name"))
    if call(extension(doc), "SelectByID2", name, kind, 0.0, 0.0, 0.0, append, mark, null(), 0) and \
            selected_count(doc) > before:
        _count(f"SelectByID2 {kind}")
        return True
    return False


def select_plane(doc: Any, index: int, append: bool = False, mark: int = 0) -> bool:
    """Select the Nth reference plane (1-based) by tree order."""
    return select_feature(doc, planes(doc)[index - 1], append, mark)


def sketch_manager(doc: Any) -> Any:
    return call(doc, "SketchManager")


def feature_manager(doc: Any) -> Any:
    return call(doc, "FeatureManager")


def extension(doc: Any) -> Any:
    return call(doc, "Extension")


def volume_mm3(doc: Any) -> Optional[float]:
    """The part's volume through its mass properties, in cubic millimetres."""
    try:
        props = call(extension(doc), "CreateMassProperty")
        return float(call(props, "Volume")) * 1e9
    except Exception:  # noqa: BLE001
        return None


def put_indexed(obj: Any, name: str, index: int, value: Any) -> None:
    """Set an indexed property, which late binding cannot spell as an assignment.

    ``eqm.Equation(i) = text`` in VBA is a property *put* with an argument;
    pywin32's dynamic dispatch only ever invokes that name as a get or a call,
    so the put has to be made through ``Invoke`` directly.
    """
    import pythoncom  # noqa: PLC0415 - Windows only, and only ever on the worker

    oleobj = obj._oleobj_  # noqa: SLF001
    dispid = oleobj.GetIDsOfNames(name)
    oleobj.Invoke(dispid, 0, pythoncom.DISPATCH_PROPERTYPUT, False, index, value)


def point_mm(point: Any) -> Tuple[float, float]:
    """A sketch point's X and Y, in millimetres."""
    return (float(call(point, "X")) * MM, float(call(point, "Y")) * MM)


def attempts(px: Px, label: str, variants: Sequence[Tuple[str, Any]]) -> Tuple[Optional[str], Any]:
    """Try each ``(name, thunk)`` in turn; the first that returns a usable value wins.

    Returns ``(winner, value)``, or ``(None, None)``. Each attempt is a line in
    the report, so a variant that raised is evidence too.
    """
    for name, thunk in variants:
        succeeded, value = px.attempt(f"{label} [{name}]", thunk)
        if succeeded and value is not None and value is not False:
            return name, value
    return None, None


def env_scratch_folder(px: Px) -> str:
    folder = px.options.get("scratch") or ""
    if folder:
        os.makedirs(folder, exist_ok=True)
    return folder


@contextlib.contextmanager
def quiet_dimensions(px: Px) -> Iterator[None]:
    """Turn off the dialog AddDimension2 would open for a value, and put it back.

    The API help for ``IModelDoc2::AddDimension2`` says to use
    ``swInputDimValOnCreate`` for this. Left on, the dialog is modal, and a
    modal dialog blocks every COM call until someone closes it.
    """
    application = app(px)
    previous = bool(call(application, "GetUserPreferenceToggle", SW_INPUT_DIM_VAL_ON_CREATE))
    call(application, "SetUserPreferenceToggle", SW_INPUT_DIM_VAL_ON_CREATE, False)
    try:
        yield
    finally:
        call(application, "SetUserPreferenceToggle", SW_INPUT_DIM_VAL_ON_CREATE, previous)


def open_sketch(px: Px, doc: Any, plane: int = 1) -> Any:
    """Select the Nth plane by tree order and open a sketch on it. Returns the manager."""
    if not select_plane(doc, plane):
        raise Require(f"Reference plane {plane} could not be selected.")
    manager = sketch_manager(doc)
    manager.AddToDB = True
    manager.DisplayWhenAdded = False
    call(manager, "InsertSketch", True)
    if call(manager, "ActiveSketch") is None:
        raise Require("InsertSketch(True) did not open a sketch.")
    call(doc, "ClearSelection2", True)
    return manager


def close_sketch(px: Px, doc: Any, name: str, before: Sequence[str], allow_empty: bool = False) -> str:
    """Close the open sketch, find the feature it made by diffing the tree, name it.

    An empty sketch makes no feature when it closes; with ``allow_empty`` that
    returns an empty name instead of ending the probe.
    """
    manager = sketch_manager(doc)
    call(manager, "InsertSketch", True)
    manager.AddToDB = False
    manager.DisplayWhenAdded = True
    made = [n for n, t in new_features(doc, before) if t == "ProfileFeature"]
    if not made and allow_empty:
        return ""
    if len(made) != 1:
        raise Require(f"Closing the sketch added {len(made)} sketch features, so which one it is cannot be told.")
    feature = feature_by_name(doc, made[0])
    feature.Name = name
    return str(call(feature, "Name"))


def sketch_of(doc: Any, name: str) -> Any:
    """The ISketch behind a sketch feature."""
    return call(feature_by_name(doc, name), "GetSpecificFeature2")


def origin_point(doc: Any) -> Any:
    """The part origin as a selectable sketch point, found by type rather than by name."""
    for feature in top_features(doc):
        if type_name(feature) == "OriginProfileFeature":
            sketch = call(feature, "GetSpecificFeature2")
            points = call(sketch, "GetSketchPoints2")
            if points:
                return points[0]
    raise Require("The part origin has no sketch point to select.")


def select(doc: Any, *entities: Any) -> None:
    """Clear the selection, then select each sketch entity in order.

    ``Select4`` on the entity first, retried; then, for a sketch point,
    ``SelectByID2`` at its location, which is in model coordinates and so only
    right on the first plane, where the sketch and the model share them.
    """
    call(doc, "ClearSelection2", True)
    for position, entity in enumerate(entities):
        before = selected_count(doc)
        append = position > 0
        if _retrying(doc, lambda: call(entity, "Select4", append, null()), before, "Select4"):
            continue
        try:
            x, y = float(call(entity, "X")), float(call(entity, "Y"))
        except Exception:  # noqa: BLE001 - a segment has no X, and no location route
            x = y = None
        if x is not None and call(extension(doc), "SelectByID2", "", "SKETCHPOINT", x, y, 0.0, append, 0,
                                  null(), 0) and selected_count(doc) > before:
            _count("SelectByID2 SKETCHPOINT at location")
            continue
        raise Require(
            f"Entity {position + 1} of {len(entities)} could not be selected by any route "
            f"(in {call(doc, 'GetTitle')}, with {_active_title()} active and {selected_count(doc)} selected)."
        )


def relate(doc: Any, constraint: str, *entities: Any) -> None:
    select(doc, *entities)
    call(doc, "SketchAddConstraints", constraint)
    call(doc, "ClearSelection2", True)


def dimensions_of(feature: Any) -> List[Any]:
    """Every IDimension on a feature, through its display dimensions."""
    out: List[Any] = []
    display = call(feature, "GetFirstDisplayDimension")
    guard = 0
    while display is not None and guard < 500:
        guard += 1
        out.append(call(display, "GetDimension2", 0))
        display = call(feature, "GetNextDisplayDimension", display)
    return out


def dimension_named(feature: Any, name: str) -> Any:
    for dimension in dimensions_of(feature):
        if str(call(dimension, "Name")) == name:
            return dimension
    raise Require(f"No dimension called {name!r} on {call(feature, 'Name')}.")


def points_mm(sketch: Any) -> List[Tuple[Any, Tuple[float, float]]]:
    """Every sketch point in a sketch, with where it is in millimetres."""
    return [(point, point_mm(point)) for point in (call(sketch, "GetSketchPoints2") or ())]


def point_at(sketch: Any, where: Tuple[float, float], tol: float = 1e-4) -> Any:
    """The sketch point at a place, in mm — how an end of a curve without its own
    point accessors is selected."""
    near = [(abs(xy[0] - where[0]) + abs(xy[1] - where[1]), point) for point, xy in points_mm(sketch)]
    near = [pair for pair in near if pair[0] <= tol]
    if not near:
        raise Require(f"No sketch point at {where} mm.")
    return min(near, key=lambda pair: pair[0])[1]


def spline_ends_mm(spline: Any) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """A spline's first and last points, in millimetres.

    ``ISketchSpline::GetPoints2`` hands back sketch point objects, not a flat
    array of doubles: on SolidWorks 2026 ``float()`` of an element raised
    because each one is a ``CDispatch``.
    """
    points = list(call(spline, "GetPoints2") or ())
    if not points:
        raise Require("GetPoints2 returned no points.")
    return point_mm(points[0]), point_mm(points[-1])
