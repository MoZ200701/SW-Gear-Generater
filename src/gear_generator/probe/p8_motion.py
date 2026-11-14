"""Tier 8: what a workbook gearbox that turns needs (PLAN-WORKBOOK §4.4, phase W5).

W4 builds a static assembly: a body-less layout part holding a named axis per
shaft (``"<Shaft> Axis"``, through planes driven by globals, Top-parallel
plane selected first so it reads +Z), and each gear inserted, placed at its
face centre turned to its mesh phase, and fixed. W5 makes it turn: each gear
unfixed and mated to its shaft axis and its axial position, each listed mesh a
gear mate, and the gears on one shaft locked together. PLAN-WORKBOOK §4.4 says
this needs PLAN-GEARBOX's probe tier 6 items 3–5 — axis-to-axis mates, five or
more components mated and not fixed, a lock between free components — and
that if they fail the build STOPs and asks. Those are settled here, on scratch
documents, together with what the review of W4 found missing: the gear mate's
Flip had been measured only between parallel axes pointing the same way.

Why tier 8 and not 6: PLAN-GEARBOX's tier 6 is the planner's whole tier (a
sketch-point layout, an axis from a point and a plane, …), most of which the
workbook superseded; these probes stand on tier 7 instead — its plus-side flip,
its plane selection route and its body-less layout part — so they must come
after it in the registry and in ``--tier``.

1. ``motion_enums`` — every mate type, alignment and error code the tier
   uses, read from ``swconst.tlb`` after the reader gives back the four values
   already verified (coincident 0, distance 5, angle 6, gear 10).
2. ``shaft_axis_mates`` — W4's state: a layout part and eight cylinders
   placed and fixed, then unfixed and mated to their shaft's axis, each by
   one route — axis coincident with axis, axis concentric with axis, the
   cylinder's face concentric with the axis, and an explicit aligned or
   anti-aligned on a gear set the other way — on shafts along Z+ and Z−; held
   along the shaft by its origin's distance from the layout's Front plane, or
   by its Front plane's. Each gear's frame is read before and after (no jump,
   no flip), then pushed — turned about its axis, moved off it, along it, and
   tilted — to see that only the turn stays. Saved, closed, reopened: the mates
   found again, no errors, the frames kept.
3. ``gear_mate_sense`` — the Flip question. Twenty-two pairs on layout axes,
   five to an assembly, driven together by one global: parallel and anti-parallel axes, the drive
   on Z+ and on Z−, the ratio's bigger number first, the gears' faces selected
   in place of their axes, AddMate5's alignment given explicitly, and a ring
   (an annulus) round a pinion with its shaft on Z+ and Z−. Every turn read
   about the gear's own axis and about +Z, and the candidate rules tested
   against all of them; three placements no meshing pair has (apart along
   the axis, a pinion outside its ring) are recorded beside the rule. The
   layout's own axes are tried as the gear mate's entities last.
4. ``compound_lock`` — two gears on one shaft turning together at a placed
   relative angle that is not zero: a lock mate with the second gear also on
   the axis, a lock mate alone, an angle mate between their Top planes at the
   placed angle (under and over 90°), and a 1 : 1 gear mate; then a
   deliberately conflicting mate, to see how an over-defined assembly shows
   itself to the API.
5. ``mated_train`` — the 12 : 1 reducer twice, 17/68 + 17/51, once with every
   shaft on Z+ and once with the middle shaft on Z−: nine components, placed
   and fixed as W4 leaves them, then unfixed and mated by what 2–4 found, with
   the flips the rule gives. No gear may jump; driven, the output turns 1/12 of
   the input, the same way; every gear under-defined until the one drive mate
   makes them all fully defined (one degree of freedom); the input dragged
   with the drive suppressed (IDragOperator, SetTransformAndSolve2, a
   Transform2 put); saved, reopened, driven again.
6. ``motion_update`` — the saved train after a layout global moves a shaft,
   and the mesh phase put right afterwards: a gear turned while its gear mate
   is on, then between suppressing and unsuppressing the mate (and, only if
   neither keeps the new phase, the mate deleted and made again); the
   compound lock the same way; an axial distance linked to an assembly global
   and changed.

Lengths cross COM in metres; everything recorded is in millimetres and
degrees. Written without SolidWorks, then iterated on SolidWorks 2026 (34.0.0)
on 2026-11-13: the first runs found the probe's own faults (a plane-to-plane
axial distance and an axis-to-axis concentric judged together with the axial
mate; EditDelete and EditSuppress2 fetched rather than invoked; GetWhatsWrong
needing its three out-parameters; Transform2 puts used as a drag, which a gear
mate does not follow). What it found is in :mod:`findings` once a full run has
recorded it.
"""

from __future__ import annotations

import math
import os
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import findings
from ..gears import crossed
from ..swcom import _out_bool, call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p1_equations import adder
from .p2_solid import BLANK_R, BLANK_W, _extrude_args
from .p4_assembly import SAVE_AS_SILENT, _mate_features, _part_with_axis
from .p4_interference import member
from .p4_nonparallel import IDENTITY, Matrix, array_data, frame_of, make_transform, origin_name, place
from .p2_helical import PLANE_DISTANCE, PLANE_FLIP
from .p7_workbook import (_link, _millimetres, _name_offset, _rename, _save_in_place, _select_two,
                          _set_global, axis_crossing, close_paths, open_by_path, plain)

Vec = Tuple[float, float, float]

TOLERANCE_MM = 1e-6
TOLERANCE_ROTATION = 1e-6     # matrix entries
TOLERANCE_RATIO = 1e-6

RING_OUTER = 50.0   # mm, the annulus standing in for a ring gear
RING_INNER = 40.0

DRIVE = "Drive"
DRIVE_FROM, DRIVE_TO = 10.0, 40.0    # degrees: every driver is placed at DRIVE_FROM so the drive does not jump it

SELECT_FEATURE = "FeatureByName then Select2"
SELECT_ID = "SelectByID2 <feature>@<component>@<assembly>"
SELECT_CORRESPONDING = "GetCorresponding of the part's feature, Select4"
FACE_AT = "SelectByID2 FACE at a point on it"


# -- pure: frames, turns and rules (tested on Linux) ---------------------------


def column(matrix: Matrix, j: int) -> Vec:
    return (float(matrix[0][j]), float(matrix[1][j]), float(matrix[2][j]))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _cross(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def unwrap(delta: float) -> float:
    return (delta + 180.0) % 360.0 - 180.0


def own_turn(before: Matrix, after: Matrix) -> float:
    """How far a component turned about its own axis (``before``'s third column), in degrees, right-handed.

    Read off its X axis: the angle from the old X to the new one, signed about
    the axis. A component that also tilted is not turning about its axis, and
    the caller checks the axis separately.
    """
    x0, x1, axis = column(before, 0), column(after, 0), column(before, 2)
    return math.degrees(math.atan2(_dot(_cross(x0, x1), axis), _dot(x0, x1)))


def axis_z(matrix: Matrix) -> float:
    """The Z component of a component's own axis in the assembly: +1 on a Z+ shaft, −1 on Z−."""
    return column(matrix, 2)[2]


def world_turn(before: Matrix, after: Matrix) -> float:
    """The turn about the assembly's +Z: the own turn, negated for a component whose axis points along −Z."""
    return own_turn(before, after) * (1.0 if axis_z(before) > 0 else -1.0)


def w4_rotation(sigma: int, theta: float) -> Matrix:
    """W4's frame for a gear turned ``theta`` degrees on a shaft along Z+ (σ = 1) or Z− (σ = −1), by rows
    (``workbook.layout.frame``: F₊ = I, F₋ = rot_x(180°), R = F_σ · rot_z(θ))."""
    if sigma > 0:
        return crossed.rot_z(theta)
    return crossed.multiply(crossed.rot_x(180.0), crossed.rot_z(theta))


def rotation_error(a: Matrix, b: Matrix) -> float:
    return max(abs(float(a[i][j]) - float(b[i][j])) for i in range(3) for j in range(3))


#: What ``Flip`` = False does, by each hypothesis; ``needed_flip`` turns one into the flip a mesh needs.
RULES = ("own axes", "plus z", "mesh", "own axes, bigger first", "plus z, bigger first", "mesh, own axes")


def predicted_world_same(rule: str, flip: bool, sigma_a: int, sigma_b: int, internal: bool, bigger_first: bool) -> bool:
    """Whether a rule says the two gears turn the same way about +Z, for a gear mate made with ``flip``.

    * ``own axes`` — Flip False turns them opposite ways about their OWN axes,
      whatever those are; about +Z that is the same way when the axes oppose.
    * ``plus z`` — Flip False turns them opposite ways about +Z.
    * ``mesh`` — Flip False turns them the way their mesh would: opposite
      outside a ring, the same way inside one (the gear mate reads the geometry).
    * the same two first rules with the sense reversed when the ratio's
      bigger number goes first (the first selection has more teeth);
    * ``mesh, own axes`` — the mesh's way about their own axes.
    """
    same_axes = sigma_a == sigma_b
    if rule == "own axes":
        return flip == same_axes
    if rule == "plus z":
        return flip
    if rule == "mesh":
        return internal != flip
    if rule == "own axes, bigger first":
        return (flip != bigger_first) == same_axes
    if rule == "plus z, bigger first":
        return flip != bigger_first
    if rule == "mesh, own axes":
        return (internal != flip) == same_axes
    raise ValueError(f"There is no rule called {rule!r}.")


def consistent_rules(cases: Sequence[Mapping[str, Any]]) -> List[str]:
    """The rules every measured case agrees with. A case is a dict with ``flip``, ``sigma_a``, ``sigma_b``,
    ``internal``, ``bigger_first`` and the measured ``world_same``; one without ``world_same`` (refused, or
    not turned) is left out."""
    measured = [c for c in cases if c.get("world_same") is not None]
    if not measured:
        return []
    return [rule for rule in RULES
            if all(predicted_world_same(rule, bool(c["flip"]), int(c["sigma_a"]), int(c["sigma_b"]),
                                        bool(c["internal"]), bool(c["bigger_first"])) == bool(c["world_same"])
                   for c in measured)]


def needed_flip(rule: str, sigma_a: int, sigma_b: int, internal: bool, bigger_first: bool = False) -> bool:
    """The Flip a gear mate needs for its gears to turn as they mesh: opposite ways about +Z outside a ring,
    the same way inside one. ``sigma_a`` is the first selection's shaft (+1 Z+, −1 Z−)."""
    for flip in (False, True):
        if predicted_world_same(rule, flip, sigma_a, sigma_b, internal, bigger_first) == internal:
            return flip
    raise ValueError(f"Rule {rule!r} gives no flip for this mesh.")  # pragma: no cover - every rule has one


def decide_rule(cases: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """The one rule every case agrees with, or None when none does or the cases cannot tell two apart."""
    rules = consistent_rules(cases)
    return rules[0] if len(rules) == 1 else None


def stored_reverse(flip: bool, sigma_a: int, sigma_b: int, internal: bool) -> bool:
    """What a gear mate between two axes keeps as its Reverse (``IGearMateFeatureData.Reverse``), by the reading
    tier 8 made: AddMate5's Flip, reversed once when the axes point opposite ways and once for a ring. The
    stored flag is about the axes' own senses; the Flip passed is about the mesh."""
    return bool(flip) ^ (sigma_a != sigma_b) ^ bool(internal)


def train_turns(teeth: Sequence[int], sigmas: Sequence[int]) -> List[float]:
    """Each gear's turn about +Z per degree of the first, for a compound train ``z1/z2 + z3/z4 + …`` of external
    meshes, gears 2k and 2k+1 on one shaft: ``[1, -z1/z2, -z1/z2, z1 z3/(z2 z4), …]``. ``sigmas`` is unused for
    the turns about +Z (an external mesh reverses the sense about +Z whatever way the shafts point) and is
    taken so the caller states them."""
    if len(teeth) % 2 or len(teeth) != len(sigmas):
        raise ValueError("A compound train has gears in pairs, one shaft-sense each.")
    out = [1.0]
    for k in range(0, len(teeth), 2):
        turned = -out[-1] * teeth[k] / teeth[k + 1]
        out.append(turned)
        if k + 2 < len(teeth):
            out.append(turned)
    return out


# -- helpers that touch SolidWorks -------------------------------------------


def _enum(px: Px, name: str) -> Dict[str, int]:
    found = sc.swconst(px, name)
    px.fact(f"enum {name}", found)
    return found


def _enums(px: Px) -> Dict[str, Any]:
    enums = px.shared.get("motion_enums")
    if not enums:
        raise Require("motion_enums has not read the enum values this probe uses.")
    return enums


def _mm(v: Sequence[float]) -> List[float]:
    return [round(float(c), 9) for c in v]


def _selected_components(asm: Any) -> List[str]:
    manager = call(asm, "SelectionManager")
    out = []
    for index in range(1, sc.selected_count(asm) + 1):
        try:
            component = call(manager, "GetSelectedObjectsComponent4", index, -1)
            out.append(str(call(component, "Name2")) if component is not None else "")
        except Exception:  # noqa: BLE001 - the name is evidence, not a step
            out.append("?")
    return out


def select_in(px: Px, asm: Any, component: Any, name: str, kind: str, append: bool,
              routes: Sequence[str] = (SELECT_FEATURE, SELECT_ID), mark: int = 1) -> Optional[str]:
    """A plane or axis of a component, by the first of ``routes`` that raises the selection count; the route, or None."""
    if not append:
        call(asm, "ClearSelection2", True)
    asm_name = os.path.splitext(str(call(asm, "GetTitle")))[0]
    for route in routes:
        before = sc.selected_count(asm)
        if route == SELECT_FEATURE:
            feature = call(component, "FeatureByName", name)
            thunk: Callable[[], Any] = (lambda f=feature: call(f, "Select2", append, mark)) if feature is not None \
                else (lambda: False)
        elif route == SELECT_ID:
            full = f"{name}@{call(component, 'Name2')}@{asm_name}"
            thunk = lambda full=full: call(sc.extension(asm), "SelectByID2", full, kind, 0.0, 0.0, 0.0, append, mark,
                                           sc.null(), 0)
        elif route == SELECT_CORRESPONDING:
            def thunk() -> Any:
                part = call(component, "GetModelDoc2")
                entity = call(component, "GetCorresponding", sc.feature_by_name(part, name))
                data = call(call(asm, "SelectionManager"), "CreateSelectData")
                data.Mark = mark
                return call(entity, "Select4", append, data)
        else:
            raise ValueError(f"No selection route {route!r}.")
        if sc._retrying(asm, thunk, before, f"tier 8 {route}"):   # noqa: SLF001 - the scaffold's retry, by count
            return route
    return None


def select_face_at(px: Px, asm: Any, point: Sequence[float], append: bool, want: str, mark: int = 1) -> bool:
    """The face at a point, in assembly millimetres, by ``SelectByID2("", "FACE", …)``; True only if what was
    selected belongs to the component ``want``."""
    if not append:
        call(asm, "ClearSelection2", True)
    before = sc.selected_count(asm)
    got, value = px.attempt(f"{FACE_AT} ({want}, {_mm(point)})",
                            lambda: call(sc.extension(asm), "SelectByID2", "", "FACE", sc.m(point[0]), sc.m(point[1]),
                                         sc.m(point[2]), append, mark, sc.null(), 0))
    if not (got and value and sc.selected_count(asm) > before):
        return False
    owners = _selected_components(asm)
    if not owners or owners[-1] != want:
        px.note(f"the face at {_mm(point)} belongs to {owners[-1:] or 'nothing'}, not {want}")
        return False
    return True


def add_mate(px: Px, asm: Any, label: str, kind: int, align: int, flip: bool = False, distance: float = 0.0,
             angle: float = 0.0, ratio: Tuple[float, float] = (1.0, 1.0), lock_rotation: bool = False) -> Dict[str, Any]:
    """``AddMate5`` on what is selected; what it returned, its error status, and the one new mate's name (or None).

    Distance in mm and angle in degrees; the argument order is the API help's:
    type, align, flip, distance and its two limits, the gear ratio's numerator
    and denominator, angle and its two limits, for-positioning-only, lock
    rotation, width option, error status.
    """
    before = [n for n, _ in _mate_features(asm)]
    d, a = sc.m(distance), math.radians(angle)
    status = sc.out_long()
    got, result = px.attempt(
        f"AddMate5 {label}",
        lambda: call(asm, "AddMate5", kind, align, flip, d, d, d, float(ratio[0]), float(ratio[1]), a, a, a, False,
                     lock_rotation, 0, status))
    call(asm, "ClearSelection2", True)
    mate = result[0] if got and isinstance(result, tuple) and result else result
    code = result[1] if got and isinstance(result, tuple) and len(result) > 1 else getattr(status, "value", None)
    made = [n for n, _ in _mate_features(asm) if n not in before]
    names = px.shared.get("mate_errors") or {}
    out = {"returned": (type(mate).__name__ if mate is not None else None) if got else "raised",
           "status": plain(code), "status_name": names.get(code) if isinstance(code, int) else None, "made": made,
           "name": made[0] if got and mate is not None and len(made) == 1 else None}
    if not got:
        out["error"] = plain(result)
    return out


def mate_feature(asm: Any, name: str) -> Any:
    for feature in sc.top_features(asm):
        if sc.type_name(feature) == "MateGroup":
            child = call(feature, "GetFirstSubFeature")
            while child is not None:
                if str(call(child, "Name")) == name:
                    return child
                child = call(child, "GetNextSubFeature")
    raise Require(f"No mate called {name!r}.")


def error_code(px: Px, feature: Any) -> Dict[str, Any]:
    """``IFeature.GetErrorCode2``: the code and whether it is only a warning."""
    out = _out_bool()
    try:
        result = call(feature, "GetErrorCode2", out)
    except Exception as exc:  # noqa: BLE001 - evidence
        return {"error": str(exc)}
    if isinstance(result, tuple):
        return {"code": plain(result[0]), "warning": plain(result[1]) if len(result) > 1 else None}
    return {"code": plain(result), "warning": plain(getattr(out, "value", None))}


def mate_errors(px: Px, asm: Any) -> Dict[str, Dict[str, Any]]:
    """Every mate's error code, by name."""
    out = {}
    for feature in sc.top_features(asm):
        if sc.type_name(feature) == "MateGroup":
            child = call(feature, "GetFirstSubFeature")
            while child is not None:
                out[str(call(child, "Name"))] = error_code(px, child)
                child = call(child, "GetNextSubFeature")
    return out


def errors_only(errors: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """The mates whose error code is not 0."""
    return {name: e for name, e in errors.items() if e.get("code") not in (0, None) or "error" in e}


def whats_wrong(px: Px, asm: Any) -> Dict[str, Any]:
    """``IModelDocExtension.GetWhatsWrongCount`` and ``GetWhatsWrong``, as far as each answers."""
    ext = sc.extension(asm)
    out: Dict[str, Any] = {}
    got, count = px.attempt("GetWhatsWrongCount", lambda: call(ext, "GetWhatsWrongCount"))
    out["count"] = plain(count) if got else "raised"
    def by_reference() -> Any:
        from win32com.client import VARIANT  # noqa: PLC0415 - Windows only
        import pythoncom  # noqa: PLC0415
        outs = [VARIANT(pythoncom.VT_BYREF | pythoncom.VT_VARIANT, None) for _ in range(3)]
        returned = call(ext, "GetWhatsWrong", *outs)
        if isinstance(returned, tuple):
            return returned
        return (returned,) + tuple(o.value for o in outs)

    # Its three arrays are out parameters: with none passed it raised "Parameter not optional".
    got, listed = px.attempt("GetWhatsWrong with three by-reference variants", by_reference)
    if got and isinstance(listed, tuple):
        names = []
        for item in listed[1] or () if len(listed) > 1 else ():
            try:
                names.append(str(call(item, "Name")))
            except Exception:  # noqa: BLE001
                names.append(repr(item))
        out["list"] = {"returned": plain(listed[0]), "features": names,
                       "codes": plain(listed[2]) if len(listed) > 2 else None,
                       "warnings": plain(listed[3]) if len(listed) > 3 else None}
    else:
        out["list"] = plain(listed) if got else "raised"
    return out


def rebuild(px: Px, asm: Any, label: str) -> Dict[str, Any]:
    started = time.monotonic()
    got, result = px.attempt(f"ForceRebuild3 ({label})", lambda: call(asm, "ForceRebuild3", False))
    return {"returned": plain(result) if got else "raised", "seconds": round(time.monotonic() - started, 3)}


def constrained(px: Px, component: Any) -> Any:
    """``IComponent2.GetConstrainedStatus``, as far as it answers (evidence only)."""
    got, value = px.attempt(f"GetConstrainedStatus of {call(component, 'Name2')}",
                            lambda: member(component, "GetConstrainedStatus")[0])
    return plain(value) if got else "raised"


def mate_entities(px: Px, asm: Any, name: str) -> Dict[str, Any]:
    """What a mate holds after a rebuild: its type, alignment and flip, and each entity's reference type and component."""
    feature = mate_feature(asm, name)
    out: Dict[str, Any] = {"feature_type": sc.type_name(feature)}
    got, mate = px.attempt(f"GetSpecificFeature2 of {name}", lambda: call(feature, "GetSpecificFeature2"))
    if not got or mate is None:
        return out
    for key in ("Type", "Alignment", "Flipped"):
        ok, value = px.attempt(f"IMate2.{key} of {name}", lambda k=key: member(mate, k)[0])
        out[key.lower()] = plain(value) if ok else "raised"
    ok, count = px.attempt(f"IMate2.GetMateEntityCount of {name}", lambda: member(mate, "GetMateEntityCount")[0])
    entities = []
    for index in range(int(count) if ok and isinstance(count, int) else 0):
        entity: Dict[str, Any] = {}
        ok, item = px.attempt(f"IMate2.MateEntity({index}) of {name}", lambda i=index: call(mate, "MateEntity", i))
        if ok and item is not None:
            for key in ("ReferenceType2", "ReferenceType"):
                ok2, value = px.attempt(f"IMateEntity2.{key}", lambda k=key, it=item: member(it, k)[0])
                entity[key] = plain(value) if ok2 else "raised"
            ok2, owner = px.attempt("IMateEntity2.ReferenceComponent", lambda it=item: call(it, "ReferenceComponent"))
            entity["component"] = str(call(owner, "Name2")) if ok2 and owner is not None else None
        entities.append(entity)
    out["entities"] = entities
    return out


def gear_mate_definition(px: Px, asm: Any, name: str) -> Dict[str, Any]:
    """``GetDefinition`` of a gear mate: what SolidWorks keeps as its ratio and its Reverse."""
    feature = mate_feature(asm, name)
    got, data = px.attempt(f"GetDefinition of {name}", lambda: call(feature, "GetDefinition"))
    out: Dict[str, Any] = {}
    if not got or data is None:
        return out
    for key in ("Reverse", "GearRatioNumerator", "GearRatioDenominator"):
        ok, value = px.attempt(f"IGearMateFeatureData.{key} of {name}", lambda k=key: member(data, k)[0])
        out[key] = plain(value) if ok else "raised"
    return out


def unfix(px: Px, asm: Any, component: Any) -> bool:
    if not bool(call(component, "IsFixed")):
        return True
    call(asm, "ClearSelection2", True)
    if not call(component, "Select4", False, sc.null(), False):
        return False
    px.attempt(f"UnfixComponent() on {call(component, 'Name2')}", lambda: asm.UnfixComponent())
    call(asm, "ClearSelection2", True)
    return not bool(call(component, "IsFixed"))


def fix(px: Px, asm: Any, component: Any) -> bool:
    if bool(call(component, "IsFixed")):
        return True
    call(asm, "ClearSelection2", True)
    if not call(component, "Select4", False, sc.null(), False):
        return False
    px.attempt(f"FixComponent() on {call(component, 'Name2')}", lambda: asm.FixComponent())
    call(asm, "ClearSelection2", True)
    return bool(call(component, "IsFixed"))


def put(px: Px, asm: Any, component: Any, matrix: Matrix, at: Sequence[float], route: str = "Transform2 put") -> bool:
    """Set a frame by ``Transform2`` (then a rebuild) or ``SetTransformAndSolve2``, without checking where it ended."""
    transform = make_transform(px, array_data(matrix, at, findings.TRANSFORM_ARRAY_ORDER or "columns"))
    if route == "Transform2 put":
        got, _ = px.attempt(f"Transform2 put on {call(component, 'Name2')}",
                            lambda: setattr(component, "Transform2", transform))
        call(asm, "ForceRebuild3", False)
        return got
    got, value = px.attempt(f"SetTransformAndSolve2 on {call(component, 'Name2')}",
                            lambda: call(component, "SetTransformAndSolve2", transform))
    return bool(got and value)


def frame_mm(component: Any) -> Tuple[Matrix, Vec]:
    return frame_of(component)


def frame_report(component: Any, matrix: Matrix, at: Sequence[float]) -> Dict[str, float]:
    got, origin = frame_of(component)
    return {"rotation": rotation_error(got, matrix), "origin_mm": math.dist(origin, at)}


def suppress(px: Px, asm: Any, name: str, on: bool) -> Optional[str]:
    """Suppress or unsuppress one mate; the route that did it, judged by ``IsSuppressed2``, or None."""
    enums = _enums(px)
    action = enums["suppress"] if on else enums["unsuppress"]
    feature = mate_feature(asm, name)

    def state() -> Optional[bool]:
        try:
            value = call(feature, "IsSuppressed2", enums["this_configuration"], sc.null())
            value = value[0] if isinstance(value, tuple) else value
            return bool(value[0] if isinstance(value, (list, tuple)) else value)
        except Exception:  # noqa: BLE001
            try:
                return bool(call(feature, "IsSuppressed"))
            except Exception:  # noqa: BLE001
                return None

    routes: List[Tuple[str, Callable[[], Any]]] = [
        ("SetSuppression2 this configuration, None",
         lambda: call(feature, "SetSuppression2", action, enums["this_configuration"], None)),
        ("SetSuppression2 this configuration, null dispatch",
         lambda: call(feature, "SetSuppression2", action, enums["this_configuration"], sc.null())),
        ("Select2 then EditSuppress2()" if on else "Select2 then EditUnsuppress2()",
         lambda: (call(feature, "Select2", False, 0), getattr(asm, "EditSuppress2" if on else "EditUnsuppress2")())[1]),
    ]
    for label, thunk in routes:
        px.attempt(f"{label} on {name}", thunk)
        call(asm, "ClearSelection2", True)
        if state() is on:
            return label
    return None


def drive_mate(px: Px, asm: Any, gear: Any, gear_top: str, layout: Any, layout_top: str, label: str,
               add: Callable[[str], int], align: int, angle: float = DRIVE_FROM) -> Optional[str]:
    """An angle mate between a gear's Top plane and the layout's, named ``Drive <label>``, its dimension linked to
    the global ``"Drive"`` (which must exist). Returns the mate's name, or None."""
    if not (select_in(px, asm, gear, gear_top, "PLANE", False) and select_in(px, asm, layout, layout_top, "PLANE", True)):
        px.fail(f"{label}: the gear's Top plane and the layout's could not both be selected")
        return None
    made = add_mate(px, asm, f"{label}: drive angle", _enums(px)["angle"], align, angle=angle)
    if made["name"] is None:
        px.fail(f"{label}: the drive angle mate was not made: {made}")
        return None
    feature = mate_feature(asm, made["name"])
    name = _rename(px, feature, f"{DRIVE} {label}")
    match = [d for d in sc.dimensions_of(feature) if abs(float(call(d, "SystemValue")) - math.radians(angle)) < 1e-9]
    if len(match) != 1 or add(f'"{call(match[0], "Name")}@{name}"= "{DRIVE}"') < 0:
        px.fail(f"{label}: the drive's dimension could not be linked to the global")
        return None
    return name


# -- the layout part and the parts --------------------------------------------


def layout_part(px: Px, folder: str, stem: str, shafts: Sequence[Tuple[str, float, float]],
                link: bool = False) -> str:
    """A body-less part of planes offset from Right and Top and an axis ``"<shaft> Axis"`` through each pair, the
    Top-parallel plane selected first so it reads +Z as W4 makes it; saved and closed. With ``link``, each offset
    driven by a global ``"<shaft> X"`` / ``"<shaft> Y"``. Every coordinate must be positive."""
    path = os.path.join(folder, f"{stem}.SLDPRT")
    if os.path.exists(path):
        raise Require(f"{path} already exists.")
    route = px.shared.get("axis_plane_select_route")
    if not route:
        raise Require("axis_through_named_planes has not decided how planes are selected.")
    doc = sc.new_document(px)
    _millimetres(px, doc)
    directions = {}
    flips = px.shared.get("layout_plus_flip") or {}
    if set(flips) != {"right", "top"}:
        raise Require("layout_planes has not said which flip puts a plane on the plus side.")
    top, right = sc.planes(doc)[1], sc.planes(doc)[2]
    routes = {"plane": {}, "axis": {}}
    with sc.quiet_dimensions(px):
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        for shaft, x, y in shafts:
            if x <= 0 or y <= 0:
                raise Require(f"{shaft} must be off both base planes on their plus sides here.")
            xp = _plane_from(px, doc, right, x, bool(flips["right"]), f"{shaft} X Plane", routes)
            yp = _plane_from(px, doc, top, y, bool(flips["top"]), f"{shaft} Y Plane", routes)
            call(doc, "ClearSelection2", True)
            # Top-parallel first, so the axis reads +Z (findings.LAYOUT_AXIS_Z_SIGN); Select2 on what
            # InsertRefPlane returned is one of the three routes tier 7 found all work.
            if not (sc._retrying(doc, lambda: call(yp, "Select2", False, 0), 0, "tier 8 layout plane")   # noqa: SLF001
                    and sc._retrying(doc, lambda: call(xp, "Select2", True, 0), 1, "tier 8 layout plane")):  # noqa: SLF001
                if not _select_two(px, doc, route, ((yp, yp), (xp, xp))):
                    raise Require(f"{shaft}'s planes did not select.")
            axis = _last_feature(px, doc, "RefAxis", lambda: call(doc, "InsertAxis2", True), routes["axis"])
            call(doc, "ClearSelection2", True)
            _rename(px, axis, f"{shaft} Axis")
            (ax, ay), direction = axis_crossing(call(call(axis, "GetSpecificFeature2"), "GetRefAxisParams"))
            directions[shaft] = {"at_mm": [round(ax, 9), round(ay, 9)], "direction": _mm(direction)}
            if abs(ax - x) > TOLERANCE_MM or abs(ay - y) > TOLERANCE_MM or abs(direction[2] - 1.0) > 1e-9:
                raise Require(f"{shaft} Axis is at ({ax}, {ay}) along {direction}, not ({x}, {y}) along +Z.")
            if link:
                for plane, letter, value in ((xp, "X", x), (yp, "Y", y)):
                    _name_offset(px, plane, value)
                    _link(px, add, str(call(plane, "Name")), f"{shaft} {letter}", value)
    px.fact(f"layout {stem} routes", routes)
    call(doc, "ForceRebuild3", False)
    px.fact(f"layout {stem}", directions)
    px.require(_save_in_place(px, doc, path, stem) and os.path.isfile(path), f"{stem} saves")
    px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
    return path


def _last_feature(px: Px, doc: Any, kind: str, make: Callable[[], Any], seen: Dict[str, int]) -> Any:
    """Make a feature and return it: ``FeatureByPositionReverse(0)`` if that is a new feature of ``kind``,
    else by diffing the tree (slow on a long tree, which is why the first is tried). The route is counted."""
    last = call(doc, "FeatureByPositionReverse", 0)
    before_name = str(call(last, "Name")) if last is not None else ""
    result = make()
    feature = call(doc, "FeatureByPositionReverse", 0)
    if feature is not None and sc.type_name(feature) == kind and str(call(feature, "Name")) != before_name:
        seen["FeatureByPositionReverse(0)"] = seen.get("FeatureByPositionReverse(0)", 0) + 1
        return feature
    raise Require(f"Making a {kind} left {sc.type_name(feature) if feature is not None else 'nothing'} last "
                  f"in the tree (it returned {result!r}).")


def _plane_from(px: Px, doc: Any, base: Any, distance: float, flip: bool, name: str, routes: Dict[str, Any]) -> Any:
    """``InsertRefPlane`` offset ``distance`` mm from ``base`` (a feature), named; the plane feature it returned."""
    if not sc.select_feature(doc, base):
        raise Require(f"{call(base, 'Name')} could not be selected.")
    constraint = PLANE_DISTANCE | (PLANE_FLIP if flip else 0)
    made = call(sc.feature_manager(doc), "InsertRefPlane", constraint, sc.m(distance), 0, 0.0, 0, 0.0)
    call(doc, "ClearSelection2", True)
    if made is None or sc.type_name(made) != "RefPlane":
        raise Require(f"InsertRefPlane({constraint}, {distance} mm) returned {made!r}.")
    key = "the feature InsertRefPlane returned"
    routes["plane"][key] = routes["plane"].get(key, 0) + 1
    _rename(px, made, name)
    return made


def ring_part(px: Px, folder: str, stem: str) -> Tuple[Any, str]:
    """An annulus RING_OUTER / RING_INNER × BLANK_W mm with a Gear Axis (planes 2 then 3, +Z), saved, left open:
    a ring gear's shape without its teeth."""
    path = os.path.join(folder, f"{stem}.SLDPRT")
    if os.path.exists(path):
        raise Require(f"{path} already exists.")
    doc = sc.new_document(px)
    _millimetres(px, doc)
    with sc.quiet_dimensions(px):
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, sc.m(RING_OUTER))
        call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, sc.m(RING_INNER))
        sketch = sc.close_sketch(px, doc, "Ring Sketch", before)
    if not sc.select_feature(doc, sc.feature_by_name(doc, sketch)):
        raise Require("The ring's sketch could not be selected.")
    feature = call(sc.feature_manager(doc), "FeatureExtrusion3", *_extrude_args(sc.m(BLANK_W)))
    call(doc, "ClearSelection2", True)
    if feature is None:
        raise Require("The ring's extrusion returned nothing.")
    volume = sc.volume_mm3(doc)
    expected = math.pi * (RING_OUTER ** 2 - RING_INNER ** 2) * BLANK_W
    if volume is None or abs(volume - expected) > 1e-3 * expected:
        raise Require(f"The ring's volume is {volume} mm³, not the annulus's {expected:.1f}.")
    if not (sc.select_plane(doc, 2) and sc.select_plane(doc, 3, append=True)):
        raise Require("Planes 2 and 3 could not be selected for the ring's axis.")
    before = sc.feature_names(doc)
    call(doc, "InsertAxis2", True)
    call(doc, "ClearSelection2", True)
    sc.feature_by_name(doc, sc.new_features(doc, before)[0][0]).Name = "Gear Axis"
    call(sc.extension(doc), "SaveAs3", path, 0, SAVE_AS_SILENT, sc.null(), sc.null(), sc.out_long(), sc.out_long())
    px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
    if not os.path.isfile(path):
        raise Require(f"{stem} did not save.")
    return doc, path


def _plane_names(component: Any) -> List[str]:
    return [str(call(p, "Name")) for p in sc.planes(call(component, "GetModelDoc2"))]


def _fresh(px: Px, path: str) -> None:
    if os.path.exists(path):
        raise Require(f"{path} already exists.")


def _folder(px: Px) -> str:
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    return folder


class Assembly:
    """A scratch assembly with the layout fixed at identity and gears placed and fixed as W4 leaves them."""

    def __init__(self, px: Px, layout_path: str, parts: Mapping[str, str]) -> None:
        self.px = px
        self.layout_path = layout_path
        self.parts = dict(parts)
        self.doc = None
        self.layout = None
        self.gears: Dict[str, Any] = {}
        self.placed: Dict[str, Tuple[Matrix, Vec]] = {}

    def open(self) -> "Assembly":
        px = self.px
        open_by_path(px, self.layout_path)
        self.doc = sc.new_document(px, sc.SW_DOC_ASSEMBLY)
        _millimetres(px, self.doc)
        self.layout = call(self.doc, "AddComponent5", self.layout_path, 0, "", False, "", 0.0, 0.0, 0.0)
        px.require(self.layout is not None, "the layout part is inserted")
        place(px, self.doc, self.layout, IDENTITY, (0.0, 0.0, 0.0))
        px.require(fix(px, self.doc, self.layout), "the layout component is fixed")
        return self

    def add(self, key: str, part: str, sigma: int, theta: float, at: Vec) -> Any:
        px = self.px
        matrix = w4_rotation(sigma, theta)
        component = call(self.doc, "AddComponent5", self.parts[part], 0, "", False, "", sc.m(at[0]), sc.m(at[1]),
                         sc.m(at[2]))
        px.require(component is not None, f"{key} ({part}) is inserted")
        place(px, self.doc, component, matrix, at)
        px.require(fix(px, self.doc, component), f"{key} is fixed, as W4 leaves it")
        self.gears[key] = component
        self.placed[key] = (matrix, at)
        return component

    def names(self) -> Dict[str, str]:
        return {key: str(call(c, "Name2")) for key, c in self.gears.items()}


# -- 1: the enums ----------------------------------------------------------------


@probe("motion_enums", needs=("gear_mate",), tier=8,
       members=("swconst.swMateType_e", "swconst.swMateAlign_e", "swconst.swAddMateError_e",
                "swconst.swFeatureError_e", "swconst.swFeatureSuppressionAction_e", "swconst.swInConfigurationOpts_e"))
def motion_enums(px: Px) -> None:
    """Every mate type, alignment, mate error, feature error and suppression value tier 8 uses, read from swconst.tlb."""
    types = _enum(px, "swMateType_e")
    known = {"swMateCOINCIDENT": findings.MATE_COINCIDENT, "swMateDISTANCE": findings.MATE_DISTANCE,
             "swMateANGLE": findings.MATE_ANGLE, "swMateGEAR": findings.MATE_GEAR}
    read = {name: types.get(name) for name in known}
    px.require(read == known, f"the reader gives back the four mate types already verified: {read}")
    align = _enum(px, "swMateAlign_e")
    errors = _enum(px, "swAddMateError_e")
    feature_errors = _enum(px, "swFeatureError_e")
    suppression = _enum(px, "swFeatureSuppressionAction_e")
    configurations = _enum(px, "swInConfigurationOpts_e")
    try:
        _enum(px, "swMateEntity2ReferenceType_e")   # for reading what a mate holds; evidence only
    except Require as exc:
        px.note(str(exc))
    px.require(align.get("swMateAlignCLOSEST") == findings.MATE_ALIGN_CLOSEST,
               f"swMateAlignCLOSEST is {align.get('swMateAlignCLOSEST')}, as the mates use")
    wanted = {
        "concentric": types.get("swMateCONCENTRIC"), "lock": types.get("swMateLOCK"),
        "parallel": types.get("swMatePARALLEL"), "coincident": types["swMateCOINCIDENT"],
        "distance": types["swMateDISTANCE"], "angle": types["swMateANGLE"], "gear": types["swMateGEAR"],
        "aligned": align.get("swMateAlignALIGNED"), "anti_aligned": align.get("swMateAlignANTI_ALIGNED"),
        "closest": align.get("swMateAlignCLOSEST"), "no_error": errors.get("swAddMateError_NoError"),
        "suppress": suppression.get("swSuppressFeature"), "unsuppress": suppression.get("swUnSuppressFeature"),
        "this_configuration": configurations.get("swThisConfiguration"),
    }
    missing = [k for k, v in wanted.items() if v is None]
    px.require(not missing, f"every value tier 8 uses is in swconst.tlb: missing {missing}")
    px.fact("motion_enum_values", wanted)
    px.shared["motion_enums"] = wanted
    px.shared["feature_errors"] = {v: k for k, v in feature_errors.items()}
    px.shared["mate_errors"] = {v: k for k, v in errors.items()}


# -- 2: a gear on its shaft's axis, from W4's state ------------------------------

AXIS_LAYOUT = "Probe W8 Axes Layout"
AXIS_PART = "Probe W8 Axes Gear"
AXIS_ASSEMBLY = "Probe W8 Axes"
AXIS_TYPES = ("axis coincident", "axis concentric", "face concentric")
AXIAL_ROUTES = ("origin distance", "front plane distance")
#: key, shaft, x, y, sigma, theta, z_front, axis mate, alignment, how the axes are selected, axial mate
AXIS_CASES = (
    ("g1", "S1", 40.0, 30.0, 1, 20.0, 5.0, "axis coincident", "closest", SELECT_FEATURE, "origin distance"),
    ("g2", "S2", 100.0, 30.0, -1, 35.0, -12.0, "axis coincident", "closest", SELECT_ID, "origin distance"),
    ("g3", "S3", 160.0, 30.0, 1, -15.0, 0.0, "axis concentric", "closest", SELECT_CORRESPONDING, "origin coincident"),
    ("g4", "S4", 220.0, 30.0, -1, 50.0, 8.0, "axis concentric", "closest", SELECT_FEATURE, "origin distance"),
    ("g5", "S5", 40.0, 90.0, 1, 10.0, 6.0, "face concentric", "closest", SELECT_FEATURE, "front plane distance"),
    ("g6", "S6", 100.0, 90.0, -1, 25.0, -7.0, "face concentric", "closest", SELECT_FEATURE, "front plane distance"),
    ("g7", "S7", 160.0, 90.0, 1, 30.0, 4.0, "axis either", "anti_aligned", SELECT_FEATURE, ""),
    ("g8", "S8", 220.0, 90.0, -1, 30.0, 4.0, "axis either", "aligned", SELECT_FEATURE, ""),
)
PUSH_TURN = 25.0     # degrees about the gear's own axis: must stay
PUSH_SHIFT = 5.0     # mm off the axis and along it: must come back
PUSH_TILT = 10.0     # degrees about the gear's X: must come back


def face_point(at: Sequence[float], sigma: int, radius: float = BLANK_R, azimuth: float = 45.0) -> Vec:
    """A point on a cylinder's outside face, half way along it: the part runs from its origin along its own +Z."""
    a = math.radians(azimuth)
    return (at[0] + radius * math.cos(a), at[1] + radius * math.sin(a), at[2] + sigma * BLANK_W / 2.0)


def _axis_mate(px: Px, asm: Assembly, key: str, kind: str, align: str, route: str) -> Dict[str, Any]:
    """Gear ``key`` mated to its shaft's layout axis by ``kind``; what happened."""
    enums = _enums(px)
    (_k, shaft, x, y, sigma, theta, z, *_rest) = next(c for c in AXIS_CASES if c[0] == key)
    gear, layout, doc = asm.gears[key], asm.layout, asm.doc
    out: Dict[str, Any] = {"kind": kind, "align": align}
    kinds = ("axis coincident", "axis concentric") if kind == "axis either" else (kind,)
    for each in kinds:
        if each == "face concentric":
            picked = select_face_at(px, doc, face_point((x, y, z), sigma), False, str(call(gear, "Name2")))
            out["gear_select"] = FACE_AT if picked else None
        else:
            out["gear_select"] = select_in(px, doc, gear, "Gear Axis", "AXIS", False, routes=(route,))
        out["layout_select"] = select_in(px, doc, layout, f"{shaft} Axis", "AXIS", True, routes=(route,)) \
            if out["gear_select"] else None
        if not (out["gear_select"] and out["layout_select"]):
            # The route under test did not select; say so, then let the next route do it so the mate is still tried.
            px.note(f"{key}: {route} did not select both ({out})")
            out["gear_select"] = out["gear_select"] or select_in(px, doc, gear, "Gear Axis", "AXIS", False)
            out["layout_select"] = select_in(px, doc, layout, f"{shaft} Axis", "AXIS", True)
        mate_type = enums["coincident"] if each == "axis coincident" else enums["concentric"]
        made = add_mate(px, doc, f"{key}: {each} with {shaft} Axis, {align}", mate_type, enums[align])
        out["mate"] = made
        out["kind_made"] = each
        if made["name"] is not None:
            break
    return out


def _axial_mate(px: Px, asm: Assembly, key: str, route: str) -> Dict[str, Any]:
    enums = _enums(px)
    (_k, shaft, x, y, sigma, theta, z, *_rest) = next(c for c in AXIS_CASES if c[0] == key)
    gear, layout, doc = asm.gears[key], asm.layout, asm.doc
    layout_front = _plane_names(layout)[0]
    out: Dict[str, Any] = {"route": route}
    if route.startswith("origin"):
        out["origin_select"] = _select_origin(px, doc, gear, append=False)
    else:
        out["origin_select"] = select_in(px, doc, gear, _plane_names(gear)[0], "PLANE", False)
    out["layout_select"] = select_in(px, doc, layout, layout_front, "PLANE", True)
    if route == "origin coincident":
        out["mate"] = add_mate(px, doc, f"{key}: origin on the layout's Front", enums["coincident"], enums["closest"])
    elif route == "origin distance":
        # A point's distance from a plane is along the plane's normal; a negative one is flipped (nonparallel_mates).
        out["mate"] = add_mate(px, doc, f"{key}: origin {z:g} mm from the layout's Front", enums["distance"],
                               enums["closest"], flip=z < 0, distance=abs(z))
    else:
        out["mate"] = add_mate(px, doc, f"{key}: Front plane {abs(z):g} mm from the layout's Front", enums["distance"],
                               enums["closest"], distance=abs(z))
    return out


def _select_origin(px: Px, asm: Any, component: Any, append: bool) -> Optional[str]:
    from .p4_nonparallel import select_origin  # noqa: PLC0415
    try:
        return select_origin(px, asm, component, call(component, "GetModelDoc2"), append)
    except Require as exc:
        px.note(str(exc))
        return None


def _pushes(px: Px, asm: Assembly, key: str) -> Dict[str, Any]:
    """Turn, shift, lift and tilt a mated gear by a Transform2 put and a rebuild; what stayed."""
    gear, doc = asm.gears[key], asm.doc
    out: Dict[str, Any] = {}
    matrix, origin = frame_of(gear)
    put(px, doc, gear, crossed.multiply(matrix, crossed.rot_z(PUSH_TURN)), origin)
    after, at = frame_of(gear)
    out["turn"] = {"turned": round(own_turn(matrix, after), 9), "origin_moved_mm": math.dist(at, origin),
                   "axis_moved": rotation_error(((0, 0, column(matrix, 2)[0]), (0, 0, column(matrix, 2)[1]),
                                                 (0, 0, column(matrix, 2)[2])),
                                                ((0, 0, column(after, 2)[0]), (0, 0, column(after, 2)[1]),
                                                 (0, 0, column(after, 2)[2])))}
    if abs(out["turn"]["turned"] - PUSH_TURN) > 1e-6:
        put(px, doc, gear, crossed.multiply(matrix, crossed.rot_z(PUSH_TURN)), origin, route="SetTransformAndSolve2")
        again, _ = frame_of(gear)
        out["turn_by_set_transform_and_solve"] = round(own_turn(matrix, again), 9)
    matrix, origin = frame_of(gear)
    for label, moved_matrix, moved_at in (
            ("off the axis", matrix, (origin[0] + PUSH_SHIFT, origin[1], origin[2])),
            ("along the axis", matrix, (origin[0], origin[1], origin[2] + PUSH_SHIFT)),
            ("tilted", crossed.multiply(matrix, crossed.rot_x(PUSH_TILT)), origin)):
        put(px, doc, gear, moved_matrix, moved_at)
        after, at = frame_of(gear)
        axis_off = max(abs(a - b) for a, b in zip(column(after, 2), column(matrix, 2)))
        out[label] = {"origin_off_mm": math.dist(at, origin), "axis_off": axis_off,
                      "turned": round(own_turn(matrix, after), 9)}
    return out


@probe("shaft_axis_mates", needs=("motion_enums", "layout_part_without_body", "nonparallel_mates"), tier=8,
       members=("IAssemblyDoc.UnfixComponent", "IAssemblyDoc.AddMate5 concentric", "IAssemblyDoc.AddMate5 coincident axes",
                "IComponent2.GetCorresponding", "IModelDocExtension.SelectByID2 FACE", "IFeature.GetErrorCode2",
                "IMate2.MateEntity", "IComponent2.Transform2", "IComponent2.SetTransformAndSolve2",
                "IModelDoc2.FeatureByPositionReverse"))
def shaft_axis_mates(px: Px) -> None:
    """Gears placed and fixed as W4 leaves them, unfixed and mated to their layout axis and axial place, by each route."""
    folder = _folder(px)
    asm_path = os.path.join(folder, f"{AXIS_ASSEMBLY}.SLDASM")
    _fresh(px, asm_path)
    layout_path = layout_part(px, folder, AXIS_LAYOUT, [(c[1], c[2], c[3]) for c in AXIS_CASES])
    _part, part_path = _part_with_axis(px, folder, AXIS_PART)
    paths = [asm_path, layout_path, part_path]
    asm = Assembly(px, layout_path, {"cyl": part_path})
    results: Dict[str, Any] = {}
    try:
        asm.open()
        for key, shaft, x, y, sigma, theta, z, *_ in AXIS_CASES:
            asm.add(key, "cyl", sigma, theta, (x, y, z))
        names = asm.names()
        px.fact("axis_component_names", names)
        rebuild(px, asm.doc, "placed and fixed")
        for key, *_ in AXIS_CASES:
            px.require(unfix(px, asm.doc, asm.gears[key]), f"{key} floats after UnfixComponent")
        px.fact("unfixed_frames", {k: frame_report(asm.gears[k], *asm.placed[k]) for k in asm.gears})

        for key, shaft, x, y, sigma, theta, z, kind, align, route, axial in AXIS_CASES:
            result: Dict[str, Any] = {"sigma": sigma, "z_front": z}
            result["axis"] = _axis_mate(px, asm, key, kind, align, route)
            matrix, at = asm.placed[key]
            got, origin = frame_of(asm.gears[key])
            result["after_axis_mate"] = {"rotation": rotation_error(got, matrix), "origin_mm": math.dist(origin, at),
                                         "axis_z": round(axis_z(got), 9)}
            if axial:
                result["axial"] = _axial_mate(px, asm, key, axial)
            results[key] = result
        result_rebuild = rebuild(px, asm.doc, "every mate made")
        px.fact("axis_rebuild", result_rebuild)
        for key, *_ in AXIS_CASES:
            results[key]["frame_after_mates"] = frame_report(asm.gears[key], *asm.placed[key])
            results[key]["axis_z_after_mates"] = round(axis_z(frame_of(asm.gears[key])[0]), 9)
        errors = mate_errors(px, asm.doc)
        px.fact("axis_mate_errors", errors)
        px.fact("axis_whats_wrong", whats_wrong(px, asm.doc))
        px.fact("axis_constrained_status", {k: constrained(px, c) for k, c in asm.gears.items()})
        kept = {}
        for key in results:
            for part in ("axis", "axial"):
                name = (results[key].get(part) or {}).get("mate", {}).get("name")
                if name:
                    kept[f"{key} {part}"] = mate_entities(px, asm.doc, name)
        px.fact("axis_mate_entities", kept)

        # Only the gears mated on their axis and along it are pushed.
        for key, *_rest, axial in AXIS_CASES:
            r = results[key]
            if axial and r["axis"]["mate"]["name"] and r["axial"]["mate"]["name"]:
                r["pushes"] = _pushes(px, asm, key)
        px.fact("axis_results", results)
        before_close = {k: [list(map(list, frame_of(c)[0])), list(frame_of(c)[1])] for k, c in asm.gears.items()}
        mates_before = sorted(n for n, _ in _mate_features(asm.doc))
        errors = errors_only(mate_errors(px, asm.doc))
        px.fact("axis_errors_before_save", errors)
        px.require(_save_in_place(px, asm.doc, asm_path, "the mated assembly") and os.path.isfile(asm_path),
                   "the mated assembly saves")
        px.shared.setdefault("created", []).append(str(call(asm.doc, "GetTitle")))
    finally:
        if asm.doc is not None and not str(call(asm.doc, "GetPathName") or ""):
            sc.close(px, asm.doc)
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")

    # Reopened: the mates found again, with no errors, the frames where they were.
    reopened: Dict[str, Any] = {}
    try:
        doc, _route = open_by_path(px, asm_path, sc.SW_DOC_ASSEMBLY, prefer="OpenDoc6")
        reopened["mates"] = sorted(n for n, _ in _mate_features(doc))
        reopened["errors_on_open"] = errors_only(mate_errors(px, doc))
        frames = {}
        for key, name in names.items():
            component = call(doc, "GetComponentByName", name)
            if component is None:
                frames[key] = None
                continue
            m, o = frame_of(component)
            frames[key] = {"rotation": rotation_error(m, before_close[key][0]),
                           "origin_mm": math.dist(o, before_close[key][1]), "fixed": bool(call(component, "IsFixed"))}
        reopened["frames"] = frames
        reopened["rebuild"] = rebuild(px, doc, "reopened")
        reopened["errors_after_rebuild"] = errors_only(mate_errors(px, doc))
        frames_after = {}
        for key, name in names.items():
            component = call(doc, "GetComponentByName", name)
            if component is not None:
                m, o = frame_of(component)
                frames_after[key] = {"rotation": rotation_error(m, before_close[key][0]),
                                     "origin_mm": math.dist(o, before_close[key][1])}
        reopened["frames_after_rebuild"] = frames_after
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.fact("axis_reopened", reopened)

    # -- what it says
    px.check(reopened["mates"] == mates_before, f"the same mates after a reopen: {reopened['mates']}")
    px.check(not reopened["errors_on_open"] and not reopened["errors_after_rebuild"],
             f"no mate has an error after the reopen: {reopened['errors_on_open']} {reopened['errors_after_rebuild']}")
    px.check(not errors, f"no mate has an error before the save: {errors}")

    def axis_held(key: str) -> bool:
        """On its axis, not jumped or turned over, free to turn and nothing else, and so after a reopen."""
        r = results[key]
        a = r["after_axis_mate"]
        p = r.get("pushes") or {}
        moved = reopened["frames_after_rebuild"].get(key) or {}
        return bool(r["axis"]["mate"]["name"] and a["rotation"] < TOLERANCE_ROTATION and a["origin_mm"] < TOLERANCE_MM
                    and abs(p.get("turn", {}).get("turned", 0.0) - PUSH_TURN) < 1e-6
                    and all(p.get(k, {}).get("origin_off_mm", 1.0) < TOLERANCE_MM and
                            p.get(k, {}).get("axis_off", 1.0) < TOLERANCE_ROTATION for k in ("off the axis", "tilted"))
                    and moved.get("rotation", 1.0) < TOLERANCE_ROTATION)

    def axial_held(key: str) -> bool:
        """At its place along the shaft after every mate, back there when pushed along it, and so after a reopen."""
        r = results[key]
        f = r["frame_after_mates"]
        p = r.get("pushes")
        moved = reopened["frames_after_rebuild"].get(key) or {}
        pushed = p is None or p.get("along the axis", {}).get("origin_off_mm", 1.0) < TOLERANCE_MM
        return bool((r.get("axial") or {}).get("mate", {}).get("name") and f["origin_mm"] < TOLERANCE_MM and pushed
                    and moved.get("origin_mm", 1.0) < TOLERANCE_MM)

    on_axis = {key: axis_held(key) for key, *_rest, axial in AXIS_CASES if axial}
    along = {key: axial_held(key) for key, *_rest, axial in AXIS_CASES if axial}
    px.fact("axis_cases_holding", on_axis)
    px.fact("axial_cases_holding", along)
    for key in on_axis:
        r = results[key]
        held = "held on its axis, free to turn" if on_axis[key] else "NOT held on its axis"
        px.check(True, f"{key} ({r['axis']['kind_made']}, σ {r['sigma']:+d}): {held}; "
                       f"{r['axial']['route']} at {r['z_front']:g}: {'held' if along[key] else 'NOT held'}"
                       f" (after every mate {r['frame_after_mates']['origin_mm']:.6g} mm off)")
    by_type: Dict[str, bool] = {}
    for kind in AXIS_TYPES:
        keys = [c[0] for c in AXIS_CASES if c[7] == kind and c[10]]
        by_type[kind] = bool(keys) and all(on_axis.get(k) for k in keys) and \
            {results[k]["sigma"] for k in keys} == {1, -1}
    px.fact("axis_mate_types_holding", by_type)
    refused = {c[0]: results[c[0]]["axis"]["mate"] for c in AXIS_CASES if results[c[0]]["axis"]["mate"]["name"] is None}
    px.fact("axis_mates_refused", refused)
    winner = next((k for k in AXIS_TYPES if by_type[k]), None)
    px.require(winner is not None, f"some mate holds a gear on its layout axis on Z+ and Z-: {by_type}")
    px.fact("axis_mate_route", winner)
    px.shared["axis_mate_route"] = winner
    axial_ok: Dict[str, bool] = {}
    for route in AXIAL_ROUTES + ("origin coincident",):
        keys = [c[0] for c in AXIS_CASES if c[10] == route]
        axial_ok[route] = bool(keys) and all(along.get(k) for k in keys)
    px.fact("axial_routes_holding", axial_ok)
    axial = next((r for r in AXIAL_ROUTES if axial_ok[r]), None)
    px.require(axial is not None, f"some mate holds a gear along its shaft: {axial_ok}")
    px.fact("axial_mate_route", axial)
    px.shared["axial_mate_route"] = axial
    px.fact("axial_zero_route_holds", axial_ok["origin coincident"])
    selects = {route: all(results[c[0]]["axis"]["gear_select"] == route and results[c[0]]["axis"]["layout_select"] == route
                          for c in AXIS_CASES if c[9] == route and c[7] != "face concentric") for route in
               (SELECT_FEATURE, SELECT_ID, SELECT_CORRESPONDING)}
    px.fact("axis_select_routes", selects)
    explicit = {}
    for key, *_rest in AXIS_CASES:
        r = results[key]
        if r["axis"]["align"] != "closest":
            explicit[key] = {"sigma": r["sigma"], "align": r["axis"]["align"], "kind": r["axis"].get("kind_made"),
                             "made": r["axis"]["mate"]["name"] is not None,
                             "axis_z_before": r["sigma"], "axis_z_after": r["axis_z_after_mates"],
                             "turned_over": r["axis_z_after_mates"] * r["sigma"] < 0}
    px.fact("explicit_alignment", explicit)
    closest = {key: results[key]["axis_z_after_mates"] * results[key]["sigma"] > 0
               for key, *_rest in AXIS_CASES if results[key]["axis"]["align"] == "closest"}
    px.fact("closest_keeps_the_side", closest)
    px.check(all(closest.values()), f"closest alignment never turns a gear over: {closest}")


# -- mounting a gear on its shaft by what shaft_axis_mates decided ---------------


def mount(px: Px, asm: Assembly, key: str, shaft: str, sigma: int, z_front: float, at: Sequence[float]) -> List[str]:
    """Unfix gear ``key`` and mate it to ``"<shaft> Axis"`` and along it, the way shaft_axis_mates decided.

    Returns the mates' names; a mate that was not made ends the probe.
    """
    enums = _enums(px)
    kind, axial = px.shared.get("axis_mate_route"), px.shared.get("axial_mate_route")
    if not kind or not axial:
        raise Require("shaft_axis_mates has not decided how a gear is held on its shaft.")
    gear, layout, doc = asm.gears[key], asm.layout, asm.doc
    if not unfix(px, doc, gear):
        raise Require(f"{key} would not unfix.")
    if kind == "face concentric":
        picked = select_face_at(px, doc, face_point(at, sigma), False, str(call(gear, "Name2")))
    else:
        picked = bool(select_in(px, doc, gear, "Gear Axis", "AXIS", False))
    if not (picked and select_in(px, doc, layout, f"{shaft} Axis", "AXIS", True)):
        raise Require(f"{key}'s axis and {shaft} Axis could not be selected.")
    mate_type = enums["coincident"] if kind == "axis coincident" else enums["concentric"]
    made = [add_mate(px, doc, f"{key} on {shaft} Axis", mate_type, enums["closest"])]
    if axial.startswith("origin"):
        picked = bool(_select_origin(px, doc, gear, append=False))
    else:
        picked = bool(select_in(px, doc, gear, _plane_names(gear)[0], "PLANE", False))
    if not (picked and select_in(px, doc, layout, _plane_names(layout)[0], "PLANE", True)):
        raise Require(f"{key}'s axial reference and the layout's Front could not be selected.")
    if abs(z_front) < 1e-9:
        made.append(add_mate(px, doc, f"{key} at 0 along {shaft}", enums["coincident"], enums["closest"]))
    else:
        made.append(add_mate(px, doc, f"{key} at {z_front:g} along {shaft}", enums["distance"], enums["closest"],
                             flip=axial.startswith("origin") and z_front < 0, distance=abs(z_front)))
    names = [m["name"] for m in made]
    if None in names:
        raise Require(f"{key} was not mounted: {made}")
    return names


# -- 3: which way a gear mate turns -----------------------------------------------

SENSE_LAYOUT = "Probe W8 Sense Layout"
SENSE_ASSEMBLY = "Probe W8 Sense"
SENSE_CYLINDER = "Probe W8 Sense Cylinder"
SENSE_RING = "Probe W8 Sense Ring"
SENSE_ROW = 120.0          # mm between pairs, more than a ring across
EXTERNAL_CENTRE = 60.0     # mm, two r 20 cylinders clear of each other
RING_CENTRE = 15.0         # mm, an r 20 cylinder inside an r 40 bore
#: name, (A part, σ), (B part, σ), entities, (A teeth, B teeth), flip, alignment. A is selected first and driven.
SENSE_CASES = (
    ("ext ++ F", ("cyl", 1), ("cyl", 1), "axis", (20, 40), False, "closest"),
    ("ext ++ T", ("cyl", 1), ("cyl", 1), "axis", (20, 40), True, "closest"),
    ("ext ++ F bigger first", ("cyl", 1), ("cyl", 1), "axis", (40, 20), False, "closest"),
    ("ext +- F", ("cyl", 1), ("cyl", -1), "axis", (20, 40), False, "closest"),
    ("ext +- T", ("cyl", 1), ("cyl", -1), "axis", (20, 40), True, "closest"),
    ("ext -+ F", ("cyl", -1), ("cyl", 1), "axis", (20, 40), False, "closest"),
    ("ext -- F", ("cyl", -1), ("cyl", -1), "axis", (20, 40), False, "closest"),
    ("ext ++ F faces", ("cyl", 1), ("cyl", 1), "face", (20, 40), False, "closest"),
    ("ext +- F faces", ("cyl", 1), ("cyl", -1), "face", (20, 40), False, "closest"),
    ("ext +- F axis and face", ("cyl", 1), ("cyl", -1), "mixed", (20, 40), False, "closest"),
    ("ext ++ F aligned", ("cyl", 1), ("cyl", 1), "axis", (20, 40), False, "aligned"),
    ("ext ++ F anti-aligned", ("cyl", 1), ("cyl", 1), "axis", (20, 40), False, "anti_aligned"),
    ("ext +- F aligned", ("cyl", 1), ("cyl", -1), "axis", (20, 40), False, "aligned"),
    ("ext +- F anti-aligned", ("cyl", 1), ("cyl", -1), "axis", (20, 40), False, "anti_aligned"),
    ("ring ++ F ring first", ("ring", 1), ("cyl", 1), "axis", (60, 20), False, "closest"),
    ("ring ++ F pinion first", ("cyl", 1), ("ring", 1), "axis", (20, 60), False, "closest"),
    ("ring -+ F ring first", ("ring", -1), ("cyl", 1), "axis", (60, 20), False, "closest"),
    ("ring -- F ring first", ("ring", -1), ("cyl", -1), "axis", (60, 20), False, "closest"),
    ("ring ++ F faces", ("ring", 1), ("cyl", 1), "face", (60, 20), False, "closest"),
    # Where the rule might stop: no meshing pair sits like these, so they are recorded, not fitted.
    ("ext ++ F apart", ("cyl", 1), ("cyl", 1), "axis", (20, 40), False, "closest", "apart"),
    ("ring ++ F apart", ("ring", 1), ("cyl", 1), "axis", (60, 20), False, "closest", "apart"),
    ("ring ++ F pinion outside", ("ring", 1), ("cyl", 1), "axis", (60, 20), False, "closest", "outside"),
)
SENSE_APART = 30.0         # mm the second gear is moved along its shaft, clear of the first's face
SENSE_OUTSIDE = RING_OUTER + BLANK_R + 5.0   # mm, a cylinder's axis outside an annulus, clear of it


def placement(case: Sequence[Any]) -> str:
    """A sense case's placement: "" as a meshing pair sits, or "apart" / "outside" (boundary cases)."""
    return str(case[7]) if len(case) > 7 else ""


def sense_layout(index: int, case: Sequence[Any]) -> Dict[str, Any]:
    """Where a case's two shafts and gears go: row ``index``; a ring's pinion sits inside its bore. A gear on Z−
    has its origin one face width up, so the two faces span the same 0..W whichever way they point."""
    _name, (part_a, sigma_a), (part_b, sigma_b), *_ = case
    y = 60.0 + SENSE_ROW * index
    ring = "ring" in (part_a, part_b)
    centre = (SENSE_OUTSIDE if placement(case) == "outside" else RING_CENTRE) if ring else EXTERNAL_CENTRE
    ring_x, other_x = 70.0, 70.0 + centre
    xa, xb = (ring_x, other_x) if part_a == "ring" or not ring else (other_x, ring_x)
    if not ring:
        xa, xb = 40.0, 40.0 + centre
    za = 0.0 if sigma_a > 0 else BLANK_W
    zb = (0.0 if sigma_b > 0 else BLANK_W) + (SENSE_APART if placement(case) == "apart" else 0.0)
    return {"a": (xa, y, za), "b": (xb, y, zb), "shaft_a": f"P{index + 1}A", "shaft_b": f"P{index + 1}B",
            "internal": ring, "placement": placement(case)}


def _face_of(part: str, at: Sequence[float], sigma: int, towards: float) -> Vec:
    """A point on the face a gear mate between faces takes: a cylinder's outside, a ring's bore; ``towards`` is
    the x of the other gear, and the point is on the side away from it (outside) or towards it (bore)."""
    if part == "ring":
        azimuth = 0.0 if towards > at[0] else 180.0
        return face_point(at, sigma, RING_INNER, azimuth + 180.0)
    azimuth = 135.0 if towards > at[0] else 45.0
    return face_point(at, sigma, BLANK_R, azimuth)


SENSE_BATCH = 5   # pairs to an assembly


def _sense_pair(px: Px, asm: Assembly, i: int, case: Sequence[Any], p: Mapping[str, Any],
                add: Callable[[str], int]) -> Dict[str, Any]:
    """Mount one case's two gears, join them by its gear mate, and drive the first; what was made."""
    enums = _enums(px)
    name, (part_a, sigma_a), (part_b, sigma_b), entities, ratio, flip, align = case[:7]
    record: Dict[str, Any] = {"name": name, "sigma_a": sigma_a, "sigma_b": sigma_b, "entities": entities,
                              "ratio": list(ratio), "flip": flip, "align": align, "internal": p["internal"],
                              "bigger_first": ratio[0] > ratio[1], "placement": p["placement"]}
    mount(px, asm, f"{i}a", p["shaft_a"], sigma_a, p["a"][2], p["a"])
    mount(px, asm, f"{i}b", p["shaft_b"], sigma_b, p["b"][2], p["b"])
    a, b, doc = asm.gears[f"{i}a"], asm.gears[f"{i}b"], asm.doc
    if entities == "face":
        picked = select_face_at(px, doc, _face_of(part_a, p["a"], sigma_a, p["b"][0]), False, str(call(a, "Name2"))) \
            and select_face_at(px, doc, _face_of(part_b, p["b"], sigma_b, p["a"][0]), True, str(call(b, "Name2")))
    elif entities == "mixed":
        picked = bool(select_in(px, doc, a, "Gear Axis", "AXIS", False)) and \
            select_face_at(px, doc, _face_of(part_b, p["b"], sigma_b, p["a"][0]), True, str(call(b, "Name2")))
    else:
        picked = bool(select_in(px, doc, a, "Gear Axis", "AXIS", False)) and \
            bool(select_in(px, doc, b, "Gear Axis", "AXIS", True))
    record["selected"] = picked
    made = add_mate(px, doc, f"{name}: gear {ratio[0]}:{ratio[1]}", enums["gear"], enums[align], flip=flip,
                    ratio=(float(ratio[0]), float(ratio[1])))
    record["mate"] = made
    if made["name"] is not None:
        record["definition"] = gear_mate_definition(px, doc, made["name"])
        record["held"] = mate_entities(px, doc, made["name"])
    record["drive"] = drive_mate(px, doc, a, _plane_names(a)[1], asm.layout, _plane_names(asm.layout)[1],
                                 f"P{i + 1}", add, enums["closest"])
    return record


def _sense_measure(px: Px, record: Dict[str, Any], a0: Matrix, b0: Matrix, a1: Matrix, b1: Matrix) -> None:
    turns = {"own_a": own_turn(a0, a1), "own_b": own_turn(b0, b1), "world_a": world_turn(a0, a1),
             "world_b": world_turn(b0, b1)}
    record["turns"] = {k: round(v, 9) for k, v in turns.items()}
    ratio = record["ratio"][0] / record["ratio"][1]
    driven = abs(abs(turns["world_a"]) - (DRIVE_TO - DRIVE_FROM)) < 1e-6
    turned = driven and abs(abs(turns["world_b"] / turns["world_a"]) - ratio) < TOLERANCE_RATIO
    record["turned_by_ratio"] = turned
    record["world_same"] = (turns["world_b"] / turns["world_a"] > 0) if turned else None
    record["own_same"] = (turns["own_b"] / turns["own_a"] > 0) if turned else None
    px.check(turned, f"{record['name']}: A turned {turns['world_a']:.6f}° about +Z, B {turns['world_b']:.6f}°"
                     f" ({'same' if record['world_same'] else 'opposite'} way about +Z, "
                     f"{'same' if record['own_same'] else 'opposite'} about their own axes)")


@probe("gear_mate_sense", needs=("shaft_axis_mates",), tier=8,
       members=("IAssemblyDoc.AddMate5 gear", "IFeature.GetDefinition", "IGearMateFeatureData.Reverse",
                "IMate2.Alignment", "IMate2.Flipped", "IEquationMgr.Add2"))
def gear_mate_sense(px: Px) -> None:
    """Which way a gear mate turns its second gear: axes' senses, the ratio's order, entities, alignment, a ring."""
    enums = _enums(px)
    folder = _folder(px)
    asm_path = os.path.join(folder, f"{SENSE_ASSEMBLY}.SLDASM")
    _fresh(px, asm_path)
    places = [sense_layout(i, c) for i, c in enumerate(SENSE_CASES)]
    shafts = []
    for p in places:
        shafts += [(p["shaft_a"], p["a"][0], p["a"][1]), (p["shaft_b"], p["b"][0], p["b"][1])]
    layout_path = layout_part(px, folder, SENSE_LAYOUT, shafts)
    _c, cyl_path = _part_with_axis(px, folder, SENSE_CYLINDER)
    _r, ring_path = ring_part(px, folder, SENSE_RING)
    paths = [asm_path, layout_path, cyl_path, ring_path]
    cases: List[Dict[str, Any]] = []
    rebuilds: List[Dict[str, Any]] = []
    errors_seen: Dict[str, Any] = {}
    layout_try: Dict[str, Any] = {}
    indexed = list(enumerate(zip(SENSE_CASES, places)))
    try:
        # A few pairs to an assembly: every AddMate5 solves the whole assembly, so one of 39
        # components took minutes; the layout and the parts are shared and stay open.
        for first in range(0, len(indexed), SENSE_BATCH):
            batch = indexed[first:first + SENSE_BATCH]
            asm = Assembly(px, layout_path, {"cyl": cyl_path, "ring": ring_path})
            try:
                asm.open()
                eqm = call(asm.doc, "GetEquationMgr")
                add = adder(px, eqm)
                px.require(add(f'"{DRIVE}"= {DRIVE_FROM:g}') >= 0, "the drive global is added")
                for i, (case, p) in batch:
                    name, (part_a, sigma_a), (part_b, sigma_b), *_ = case
                    asm.add(f"{i}a", part_a, sigma_a, DRIVE_FROM, p["a"])
                    asm.add(f"{i}b", part_b, sigma_b, 0.0, p["b"])
                made_here: List[Dict[str, Any]] = []
                for i, (case, p) in batch:
                    made_here.append(_sense_pair(px, asm, i, case, p, add))
                rebuilds.append({"batch": first // SENSE_BATCH, "before": rebuild(px, asm.doc, "every pair mated")})
                errors_seen[f"batch {first // SENSE_BATCH} mated"] = errors_only(mate_errors(px, asm.doc))
                before = {k: frame_of(c)[0] for k, c in asm.gears.items()}
                _set_global(eqm, DRIVE, DRIVE_TO)
                rebuilds[-1]["after"] = rebuild(px, asm.doc, "driven")
                errors_seen[f"batch {first // SENSE_BATCH} driven"] = errors_only(mate_errors(px, asm.doc))
                for (i, _cp), record in zip(batch, made_here):
                    _sense_measure(px, record, before[f"{i}a"], before[f"{i}b"], frame_of(asm.gears[f"{i}a"])[0],
                                   frame_of(asm.gears[f"{i}b"])[0])
                    cases.append(record)
                if first == 0:
                    # Last in its assembly, which is not saved: the layout's own two axes as a gear mate's entities.
                    p = places[0]
                    if select_in(px, asm.doc, asm.layout, f"{p['shaft_a']} Axis", "AXIS", False) and \
                            select_in(px, asm.doc, asm.layout, f"{p['shaft_b']} Axis", "AXIS", True):
                        layout_try["mate"] = add_mate(px, asm.doc, "gear mate between two of the layout's axes",
                                                      enums["gear"], enums["closest"], ratio=(20.0, 40.0))
                        layout_try["rebuild"] = rebuild(px, asm.doc, "after the layout-axes gear mate")
                        layout_try["errors"] = errors_only(mate_errors(px, asm.doc))
                    else:
                        layout_try["selected"] = False
            finally:
                try:
                    sc.close(px, asm.doc) if asm.doc is not None else None
                except Exception as exc:  # noqa: BLE001
                    px.note(f"CLEANUP {exc}")
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.fact("sense_rebuilds", rebuilds)
    px.fact("sense_errors", errors_seen)
    px.fact("gear_mate_on_layout_axes", layout_try)
    px.fact("sense_cases", cases)
    boundary = {c["name"]: {"world_same": c["world_same"], "own_same": c["own_same"],
                            "mesh_says_same": c["internal"] and c["placement"] != "outside"}
                for c in cases if c["placement"]}
    px.fact("sense_boundary_cases", boundary)
    cases_fitted = [c for c in cases if not c["placement"]]
    closest = [c for c in cases_fitted if c["align"] == "closest"]
    # The rule is the one the build can use: gear mates between the gears' own axes (Gear Axis), closest
    # alignment. Whether faces agree is recorded beside it.
    on_axes = [c for c in closest if c["entities"] == "axis"]
    rules = consistent_rules(on_axes)
    px.fact("sense_rules_consistent", rules)
    px.fact("sense_rules_consistent_with_faces_too", consistent_rules(closest))
    rule = decide_rule(on_axes)
    px.check(all(c["turned_by_ratio"] for c in cases), "every pair turned at its ratio")
    aligned = {c["name"]: {"world_same": c["world_same"], "own_same": c["own_same"]} for c in cases
               if c["align"] != "closest"}
    px.fact("sense_by_alignment", aligned)
    by_entities = {}
    for c in cases_fitted:
        if c["align"] == "closest":
            key = f"σ {c['sigma_a']:+d}{c['sigma_b']:+d} internal {c['internal']} flip {c['flip']} " \
                  f"bigger first {c['bigger_first']}"
            by_entities.setdefault(key, {})[c["entities"]] = c["world_same"]
    px.fact("sense_by_entities", by_entities)
    px.fact("sense_depends_on_entities", any(len(set(v.values())) > 1 for v in by_entities.values()))
    stored = {c["name"]: {"passed_flip": c["flip"], "kept_reverse": (c.get("definition") or {}).get("Reverse"),
                          "reading": stored_reverse(c["flip"], c["sigma_a"], c["sigma_b"], c["internal"])}
              for c in cases_fitted if c["entities"] == "axis"}
    px.fact("gear_mate_kept_reverse", stored)
    px.fact("kept_reverse_follows_the_axes", all(v["kept_reverse"] == v["reading"] for v in stored.values()))
    px.fact("alignment_changes_sense", any(len({(c["world_same"]) for c in cases_fitted
                                                if c["sigma_a"] == sa and c["sigma_b"] == sb and not c["internal"]
                                                and c["flip"] is False and c["entities"] == "axis"
                                                and not c["bigger_first"]}) > 1 for sa, sb in ((1, 1), (1, -1))))
    px.require(rule is not None, f"one rule explains every pair: {rules}")
    px.fact("gear_mate_flip_rule", rule)
    px.shared["gear_mate_flip_rule"] = rule


# -- 4: two gears on one shaft, locked at their placed angle ----------------------

LOCK_LAYOUT = "Probe W8 Lock Layout"
LOCK_ASSEMBLY = "Probe W8 Lock"
LOCK_PART = "Probe W8 Lock Gear"
LOCK_GAP_Z = 15.0            # mm: the second gear's front face, clear of the first's 10 mm face
LOCK_STEPS = (40.0, 130.0)   # degrees the drive is set to in turn, from DRIVE_FROM
#: name, how Q is held, Q's angle from P in degrees, shaft sense
LOCK_CASES = (
    ("lock, both on the shaft", "lock both", 37.0, 1),
    ("lock alone", "lock alone", 37.0, 1),
    ("angle 37", "angle", 37.0, 1),
    ("angle 137", "angle", 137.0, 1),
    ("gear 1:1 flip off", "gear False", 37.0, 1),
    ("gear 1:1 flip on", "gear True", 37.0, 1),
    ("lock, both on the shaft, Z-", "lock both", 37.0, -1),
    ("lock alone, Z-", "lock alone", 37.0, -1),
)
CONFLICT = 10.0   # degrees added to an angle lock's value by the deliberately conflicting mate


def select_components(px: Px, asm: Any, components: Sequence[Any]) -> Optional[str]:
    """Select whole components for a mate that takes them (a lock): with a mark-1 select data, else none."""
    for label in ("Select4 with a mark-1 select data", "Select4 with no select data"):
        call(asm, "ClearSelection2", True)
        ok = True
        for position, component in enumerate(components):
            before = sc.selected_count(asm)
            if label.startswith("Select4 with a mark"):
                data = call(call(asm, "SelectionManager"), "CreateSelectData")
                data.Mark = 1
            else:
                data = sc.null()
            got, value = px.attempt(f"{label}: {call(component, 'Name2')}",
                                    lambda c=component, d=data, a=position > 0: call(c, "Select4", a, d, False))
            if not (got and value and sc.selected_count(asm) > before):
                ok = False
                break
        if ok:
            return label
    call(asm, "ClearSelection2", True)
    return None


def delete_mate(px: Px, asm: Any, name: str) -> Optional[str]:
    """Delete one mate: selected, then ``EditDelete``, else ``DeleteSelection2``; the route, judged by the tree."""
    # EditDelete takes no arguments, so it is invoked: call() would only fetch it (as with FixComponent).
    for label, thunk in (("Select2 then EditDelete()", lambda: asm.EditDelete()),
                         ("Select2 then DeleteSelection2(0)", lambda: call(sc.extension(asm), "DeleteSelection2", 0))):
        try:
            feature = mate_feature(asm, name)
        except Require:
            return None
        call(asm, "ClearSelection2", True)
        call(feature, "Select2", False, 0)
        px.attempt(f"{label} on {name}", thunk)
        call(asm, "ClearSelection2", True)
        if name not in [n for n, _ in _mate_features(asm)]:
            return label
    return None


def relative_angle(p: Any, q: Any) -> float:
    """Q's turn from P about P's axis, in degrees: the angle a compound lock must hold."""
    return own_turn(frame_of(p)[0], frame_of(q)[0])


@probe("compound_lock", needs=("shaft_axis_mates",), tier=8,
       members=("IAssemblyDoc.AddMate5 lock", "IAssemblyDoc.AddMate5 angle", "IComponent2.Select4",
                "IModelDoc2.EditDelete", "IModelDocExtension.GetWhatsWrong", "IComponent2.GetConstrainedStatus"))
def compound_lock(px: Px) -> None:
    """Two gears on one shaft held at a placed angle that is not 0 through a drive, by each lock; then an over-definition."""
    enums = _enums(px)
    folder = _folder(px)
    asm_path = os.path.join(folder, f"{LOCK_ASSEMBLY}.SLDASM")
    _fresh(px, asm_path)
    shafts = [(f"L{i + 1}", 40.0 + 70.0 * (i % 4), 40.0 + 70.0 * (i // 4)) for i in range(len(LOCK_CASES))]
    layout_path = layout_part(px, folder, LOCK_LAYOUT, shafts)
    _part, part_path = _part_with_axis(px, folder, LOCK_PART)
    paths = [asm_path, layout_path, part_path]
    asm = Assembly(px, layout_path, {"cyl": part_path})
    results: Dict[str, Any] = {}
    overdefined: Dict[str, Any] = {}
    try:
        asm.open()
        doc = asm.doc
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add(f'"{DRIVE}"= {DRIVE_FROM:g}') >= 0, "the drive global is added")
        for i, (name, how, delta, sigma) in enumerate(LOCK_CASES):
            shaft, x, y = shafts[i]
            zp = 0.0 if sigma > 0 else BLANK_W
            zq = zp + sigma * LOCK_GAP_Z
            asm.add(f"{i}p", "cyl", sigma, DRIVE_FROM, (x, y, zp))
            asm.add(f"{i}q", "cyl", sigma, DRIVE_FROM + delta, (x, y, zq))
        for i, (name, how, delta, sigma) in enumerate(LOCK_CASES):
            shaft, x, y = shafts[i]
            p_key, q_key = f"{i}p", f"{i}q"
            p, q = asm.gears[p_key], asm.gears[q_key]
            zp = asm.placed[p_key][1][2]
            zq = asm.placed[q_key][1][2]
            result: Dict[str, Any] = {"how": how, "delta": delta, "sigma": sigma}
            result["mounts"] = mount(px, asm, p_key, shaft, sigma, zp, (x, y, zp))
            if how != "lock alone":
                result["mounts"] += mount(px, asm, q_key, shaft, sigma, zq, (x, y, zq))
            else:
                px.require(unfix(px, doc, q), f"{name}: Q floats")
            if how.startswith("lock"):
                result["select"] = select_components(px, doc, (p, q))
                result["mate"] = add_mate(px, doc, f"{name}: lock", enums["lock"], enums["closest"])
            elif how == "angle":
                picked = select_in(px, doc, q, _plane_names(q)[1], "PLANE", False) and \
                    select_in(px, doc, p, _plane_names(p)[1], "PLANE", True)
                result["select"] = bool(picked)
                result["mate"] = add_mate(px, doc, f"{name}: angle {delta:g}", enums["angle"], enums["closest"],
                                          angle=delta)
            else:
                flip = how.endswith("True")
                picked = select_in(px, doc, p, "Gear Axis", "AXIS", False) and \
                    select_in(px, doc, q, "Gear Axis", "AXIS", True)
                result["select"] = bool(picked)
                result["mate"] = add_mate(px, doc, f"{name}: gear 1:1 flip {flip}", enums["gear"], enums["closest"],
                                          flip=flip)
            result["relative_after_lock"] = round(relative_angle(p, q), 9)
            result["drive"] = drive_mate(px, doc, p, _plane_names(p)[1], asm.layout, _plane_names(asm.layout)[1],
                                         f"L{i + 1}", add, enums["closest"])
            results[name] = result
        px.fact("lock_rebuild", rebuild(px, doc, "every lock made"))
        px.fact("lock_errors", errors_only(mate_errors(px, doc)))
        px.fact("lock_constrained_status", {k: constrained(px, c) for k, c in asm.gears.items()})
        for step in LOCK_STEPS:
            frames = {k: frame_of(c)[0] for k, c in asm.gears.items()}
            _set_global(eqm, DRIVE, step)
            rebuild(px, doc, f"drive {step:g}")
            for i, (name, how, delta, sigma) in enumerate(LOCK_CASES):
                p, q = asm.gears[f"{i}p"], asm.gears[f"{i}q"]
                shaft, x, y = shafts[i]
                q_matrix, q_at = frame_of(q)
                results[name].setdefault("steps", []).append({
                    "drive": step, "p_turned": round(own_turn(frames[f"{i}p"], frame_of(p)[0]), 9),
                    "relative": round(relative_angle(p, q), 9),
                    "q_axis_off": max(abs(a - b) for a, b in zip(column(q_matrix, 2), (0.0, 0.0, float(sigma)))),
                    "q_off_axis_mm": math.hypot(q_at[0] - x, q_at[1] - y)})
        px.fact("lock_errors_after_drive", errors_only(mate_errors(px, doc)))
        px.fact("lock_constrained_status_driven", {k: constrained(px, c) for k, c in asm.gears.items()})
        px.fact("lock_whats_wrong", whats_wrong(px, doc))

        # Over-defined on purpose: a second angle between the "angle 37" pair's Top planes, 10° more.
        i = [c[0] for c in LOCK_CASES].index("angle 37")
        p, q = asm.gears[f"{i}p"], asm.gears[f"{i}q"]
        picked = select_in(px, doc, q, _plane_names(q)[1], "PLANE", False) and \
            select_in(px, doc, p, _plane_names(p)[1], "PLANE", True)
        overdefined["selected"] = bool(picked)
        overdefined["mate"] = add_mate(px, doc, "a conflicting angle", enums["angle"], enums["closest"],
                                       angle=37.0 + CONFLICT)
        overdefined["relative_after"] = round(relative_angle(p, q), 9)
        overdefined["rebuild"] = rebuild(px, doc, "over-defined")
        errors = errors_only(mate_errors(px, doc))
        names = px.shared.get("feature_errors") or {}
        overdefined["errors"] = {n: {**e, "name": names.get(e.get("code"))} for n, e in errors.items()}
        overdefined["whats_wrong"] = whats_wrong(px, doc)
        overdefined["constrained"] = {"p": constrained(px, p), "q": constrained(px, q)}
        made = overdefined["mate"]["name"] or (overdefined["mate"]["made"] or [None])[0]
        if made:
            overdefined["deleted_by"] = delete_mate(px, doc, made)
            overdefined["rebuild_after_delete"] = rebuild(px, doc, "conflict deleted")
            overdefined["errors_after_delete"] = errors_only(mate_errors(px, doc))
            overdefined["constrained_after_delete"] = {"p": constrained(px, p), "q": constrained(px, q)}
    finally:
        try:
            sc.close(px, asm.doc) if asm.doc is not None else None
        except Exception as exc:  # noqa: BLE001
            px.note(f"CLEANUP {exc}")
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.fact("lock_results", results)
    px.fact("over_defined", overdefined)

    errors = px.record.facts.get("lock_errors_after_drive") or {}

    def mate_names(r: Mapping[str, Any]) -> List[str]:
        return [n for n in [r["mate"]["name"], r.get("drive")] + list(r.get("mounts") or []) if n]

    holding = {}
    for name, how, delta, sigma in LOCK_CASES:
        r = results[name]
        steps = r.get("steps") or []
        previous = (DRIVE_FROM,) + LOCK_STEPS[:-1]
        held = bool(r["mate"]["name"]) and len(steps) == len(LOCK_STEPS) and all(
            abs(unwrap(s["relative"] - delta)) < 1e-6 and s["q_off_axis_mm"] < TOLERANCE_MM and s["q_axis_off"] < 1e-9
            and abs(abs(s["p_turned"]) - abs(s["drive"] - before)) < 1e-6
            for s, before in zip(steps, previous)) and abs(unwrap(r["relative_after_lock"] - delta)) < 1e-6
        clean = not any(n in errors for n in mate_names(r))
        holding[name] = {"held": held, "no_errors": clean,
                         "errors": {n: errors[n] for n in mate_names(r) if n in errors},
                         "constrained": {k: (px.record.facts.get("lock_constrained_status_driven") or {}).get(k)
                                         for k in (f"{[c[0] for c in LOCK_CASES].index(name)}p",
                                                   f"{[c[0] for c in LOCK_CASES].index(name)}q")}}
        px.check(True, f"{name}: {'held its ' + format(delta, 'g') + '°' if held else 'did NOT hold'}"
                       f"{'' if clean else ', with mate errors'}: {[s['relative'] for s in steps]}")
    px.fact("lock_holding", holding)
    routes = {"lock alone": ("lock alone", "lock alone, Z-"), "lock both": ("lock, both on the shaft",
                                                                           "lock, both on the shaft, Z-"),
              "angle": ("angle 37", "angle 137")}
    working = {route: all(holding[n]["held"] and holding[n]["no_errors"] for n in names) for route, names in routes.items()}
    px.fact("lock_routes_holding", working)
    px.check(bool(overdefined.get("errors")) or overdefined.get("mate", {}).get("name") is None,
             f"a conflicting mate shows itself: {overdefined}")
    winner = next((r for r in ("lock alone", "lock both", "angle") if working[r]), None)
    px.require(winner is not None, f"some lock holds two free gears on one shaft at their placed angle: {working}")
    px.fact("compound_lock_route", winner)
    px.shared["compound_lock_route"] = winner


# -- 5: the 12 : 1 reducer, mated from W4's state, twice ---------------------------

TRAIN_LAYOUT = "Probe W8 Train Layout"
TRAIN_ASSEMBLY = "Probe W8 Train"
TRAIN_PART = "Probe W8 Train Gear"
TRAIN_TEETH = (17, 68, 17, 51)                 # PLAN-WORKBOOK's 12 : 1 reducer
TRAIN_PHASES = (DRIVE_FROM, 23.0, -41.0, 7.0)  # degrees each gear is placed turned, as W4 would
TRAIN_C12, TRAIN_C34 = 42.5, 34.0              # mm, module 1
#: name, the shafts' prefix, each shaft's sense (input, compound, output), and where the input shaft is
TRAINS = (("all Z+", "T", (1, 1, 1), (40.0, 40.0)), ("middle Z-", "U", (1, -1, 1), (40.0, 240.0)))
TRAIN_DRIVE_AGAIN = 70.0   # degrees, the drive after the reopen
DRAG = 20.0                # degrees the input is turned with the drive suppressed
# The first run tried DragAsUI and Drag as IDragOperator came (TransformType 0, DragMode 3): every call returned
# True and the input turned, but the train did not follow; the other settings are tried in turn after them.
DRAG_ROUTES = ("IDragOperator.DragAsUI", "IDragOperator.Drag", "IDragOperator.DragAsUI TransformType=1",
               "IDragOperator.DragAsUI TransformType=2", "IDragOperator.DragAsUI DragMode=0",
               "IDragOperator.DragAsUI DragMode=1", "IDragOperator.DragAsUI DragMode=2", "SetTransformAndSolve2",
               "Transform2 put")


def rotation_about(axis: Sequence[float], degrees: float) -> Matrix:
    """The rotation ``degrees`` about a unit ``axis``, by rows (Rodrigues)."""
    x, y, z = (float(a) for a in axis)
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    k = 1.0 - c
    return ((c + x * x * k, x * y * k - z * s, x * z * k + y * s),
            (y * x * k + z * s, c + y * y * k, y * z * k - x * s),
            (z * x * k - y * s, z * y * k + x * s, c + z * z * k))


def turn_about_point(axis: Sequence[float], degrees: float, point: Sequence[float]) -> Tuple[Matrix, Vec]:
    """A relative move turning ``degrees`` about an axis through ``point`` (mm): ``x' = R x + (p - R p)``."""
    r = rotation_about(axis, degrees)
    rp = crossed.apply(r, point)
    return r, (point[0] - rp[0], point[1] - rp[1], point[2] - rp[2])


def drag(px: Px, asm: Any, component: Any, degrees: float, route: str) -> Dict[str, Any]:
    """Drag a component ``degrees`` about its own axis through ``IDragOperator`` — what a mouse drag does, mates
    solving as it goes — by ``DragAsUI`` or ``Drag`` with a relative transform. What each step answered."""
    out: Dict[str, Any] = {}
    got, op = px.attempt("IAssemblyDoc.GetDragOperator", lambda: member(asm, "GetDragOperator")[0])
    if not got or op is None:
        out["operator"] = None
        return out
    for key in ("TransformType", "DragMode", "UseAbsoluteTransform", "IsDragSpecific"):
        ok, value = px.attempt(f"IDragOperator.{key}", lambda k=key: member(op, k)[0])
        out[key] = plain(value) if ok else "raised"
    px.attempt("IDragOperator.UseAbsoluteTransform = False", lambda: setattr(op, "UseAbsoluteTransform", False))
    call_part, _, setting = route.partition(" ")
    if setting:
        key, _, value = setting.partition("=")
        px.attempt(f"IDragOperator.{key} = {value}", lambda: setattr(op, key, int(value)))
        ok, read = px.attempt(f"IDragOperator.{key} read back", lambda: member(op, key)[0])
        out[f"{key} set"] = plain(read) if ok else "raised"
    m, o = frame_of(component)
    r, t = turn_about_point(column(m, 2), degrees, o)
    xform = make_transform(px, array_data(r, t, findings.TRANSFORM_ARRAY_ORDER or "columns"))
    method = call_part.rsplit(".", 1)[-1]
    for step, thunk in (("AddComponent", lambda: call(op, "AddComponent", component, False)),
                        ("BeginDrag", lambda: member(op, "BeginDrag")[0]),
                        (method, lambda: call(op, method, xform)),
                        ("EndDrag", lambda: member(op, "EndDrag")[0])):
        ok, value = px.attempt(f"IDragOperator.{step}", thunk)
        out[step] = plain(value) if ok else "raised"
    return out


def train_geometry(prefix: str, sigmas: Sequence[int], origin: Sequence[float]) -> Dict[str, Any]:
    """Shafts and gears of one train: S1 at ``origin``, S2 C12 along +X, S3 C34 along +Y from S2. The two meshes
    sit at z = 5 and z = 20 (mid-face); a gear on Z− has its origin a face width above its mid-face's other side."""
    x1, y1 = origin
    shafts = [(f"{prefix}1", x1, y1), (f"{prefix}2", x1 + TRAIN_C12, y1), (f"{prefix}3", x1 + TRAIN_C12, y1 + TRAIN_C34)]
    mids = (5.0, 5.0, 20.0, 20.0)
    on = (0, 1, 1, 2)
    gears = []
    for k in range(4):
        sigma = sigmas[on[k]]
        z_front = mids[k] - sigma * BLANK_W / 2.0
        shaft, x, y = shafts[on[k]]
        gears.append({"key": f"{prefix}G{k + 1}", "shaft": shaft, "sigma": sigma, "at": (x, y, z_front),
                      "theta": TRAIN_PHASES[k], "teeth": TRAIN_TEETH[k]})
    return {"shafts": shafts, "gears": gears}


def _turns(asm: Assembly, keys: Sequence[str], before: Mapping[str, Matrix]) -> Dict[str, float]:
    return {k: round(world_turn(before[k], frame_of(asm.gears[k])[0]), 9) for k in keys}


def _ratio_ok(turns: Sequence[float], expected: Sequence[float]) -> bool:
    if not turns or abs(turns[0]) < 1e-9:
        return False
    return all(abs(t / turns[0] - e) < TOLERANCE_RATIO for t, e in zip(turns, expected))


@probe("mated_train", needs=("gear_mate_sense", "compound_lock"), tier=8,
       members=("IAssemblyDoc.AddMate5", "IAssemblyDoc.UnfixComponent", "IFeature.SetSuppression2",
                "IComponent2.SetTransformAndSolve2", "IComponent2.GetConstrainedStatus", "ISldWorks.OpenDoc6",
                "IAssemblyDoc.GetDragOperator", "IDragOperator.DragAsUI", "IDragOperator.Drag"))
def mated_train(px: Px) -> None:
    """The 12 : 1 reducer twice (all Z+, middle shaft Z-), placed and fixed as W4 leaves it, mated to turn; driven,
    dragged, saved, reopened, driven again."""
    enums = _enums(px)
    rule, lock = px.shared.get("gear_mate_flip_rule"), px.shared.get("compound_lock_route")
    px.require(bool(rule) and bool(lock), f"the flip rule ({rule}) and the lock route ({lock}) are decided")
    folder = _folder(px)
    asm_path = os.path.join(folder, f"{TRAIN_ASSEMBLY}.SLDASM")
    _fresh(px, asm_path)
    trains = {name: train_geometry(prefix, sigmas, origin) for name, prefix, sigmas, origin in TRAINS}
    shafts = [s for t in trains.values() for s in t["shafts"]]
    layout_path = layout_part(px, folder, TRAIN_LAYOUT, shafts, link=True)
    _part, part_path = _part_with_axis(px, folder, TRAIN_PART)
    paths = [asm_path, layout_path, part_path]
    asm = Assembly(px, layout_path, {"cyl": part_path})
    facts: Dict[str, Any] = {"rule": rule, "lock": lock}
    mates: Dict[str, Any] = {}
    try:
        asm.open()
        doc = asm.doc
        for name, t in trains.items():
            for g in t["gears"]:
                asm.add(g["key"], "cyl", g["sigma"], g["theta"], g["at"])
        facts["components"] = 1 + len(asm.gears)
        facts["rebuild_fixed"] = rebuild(px, doc, "placed and fixed")
        placed = {k: frame_of(c) for k, c in asm.gears.items()}

        started = time.monotonic()
        for name, t in trains.items():
            g1, g2, g3, g4 = t["gears"]
            for g in t["gears"]:
                if g is g3 and lock == "lock alone":
                    px.require(unfix(px, doc, asm.gears[g["key"]]), f"{g['key']} floats")
                    continue
                mates[g["key"]] = mount(px, asm, g["key"], g["shaft"], g["sigma"], g["at"][2], g["at"])
            for a, b in ((g1, g2), (g3, g4)):
                flip = needed_flip(rule, a["sigma"], b["sigma"], False, a["teeth"] > b["teeth"])
                picked = select_in(px, doc, asm.gears[a["key"]], "Gear Axis", "AXIS", False) and \
                    select_in(px, doc, asm.gears[b["key"]], "Gear Axis", "AXIS", True)
                px.require(bool(picked), f"{a['key']} and {b['key']}'s axes select")
                made = add_mate(px, doc, f"{a['key']}-{b['key']} gear {a['teeth']}:{b['teeth']} flip {flip}",
                                enums["gear"], enums["closest"], flip=flip, ratio=(float(a["teeth"]), float(b["teeth"])))
                px.require(made["name"] is not None, f"the {a['key']}-{b['key']} gear mate is made: {made}")
                mates[f"{a['key']}-{b['key']}"] = {"name": made["name"], "flip": flip}
            p, q = asm.gears[g2["key"]], asm.gears[g3["key"]]
            if lock.startswith("lock"):
                px.require(bool(select_components(px, doc, (p, q))), f"{name}: G2 and G3 select")
                made = add_mate(px, doc, f"{name}: G2-G3 lock", enums["lock"], enums["closest"])
            else:
                delta = relative_angle(p, q)
                picked = select_in(px, doc, q, _plane_names(q)[1], "PLANE", False) and \
                    select_in(px, doc, p, _plane_names(p)[1], "PLANE", True)
                px.require(bool(picked), f"{name}: G3's and G2's Top planes select")
                made = add_mate(px, doc, f"{name}: G2-G3 angle {abs(delta):g}", enums["angle"], enums["closest"],
                                angle=abs(delta))
            px.require(made["name"] is not None, f"{name}: the compound lock is made: {made}")
            mates[f"{name} lock"] = made["name"]
        facts["seconds_to_mate"] = round(time.monotonic() - started, 3)
        facts["rebuild_mated"] = rebuild(px, doc, "mated")
        jumps = {k: {"rotation": rotation_error(frame_of(c)[0], placed[k][0]),
                     "origin_mm": math.dist(frame_of(c)[1], placed[k][1])} for k, c in asm.gears.items()}
        facts["jumps_after_mating"] = jumps
        facts["errors_mated"] = errors_only(mate_errors(px, doc))
        facts["whats_wrong_mated"] = whats_wrong(px, doc)
        facts["constrained_mated"] = {k: constrained(px, c) for k, c in asm.gears.items()}

        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add(f'"{DRIVE}"= {DRIVE_FROM:g}') >= 0, "the drive global is added")
        drives = {}
        for name, t in trains.items():
            g1 = t["gears"][0]
            drives[name] = drive_mate(px, doc, asm.gears[g1["key"]], _plane_names(asm.gears[g1["key"]])[1],
                                      asm.layout, _plane_names(asm.layout)[1], name, add, enums["closest"])
            px.require(drives[name] is not None, f"{name}: the input is driven")
        facts["rebuild_driven"] = rebuild(px, doc, "drive added")
        facts["jumps_after_drive"] = {k: {"rotation": rotation_error(frame_of(c)[0], placed[k][0]),
                                          "origin_mm": math.dist(frame_of(c)[1], placed[k][1])}
                                      for k, c in asm.gears.items()}
        facts["constrained_driven"] = {k: constrained(px, c) for k, c in asm.gears.items()}
        facts["errors_driven"] = errors_only(mate_errors(px, doc))

        before = {k: frame_of(c)[0] for k, c in asm.gears.items()}
        _set_global(eqm, DRIVE, DRIVE_TO)
        facts["rebuild_turned"] = rebuild(px, doc, "driven 30°")
        turned = {}
        for name, t in trains.items():
            keys = [g["key"] for g in t["gears"]]
            turned[name] = _turns(asm, keys, before)
        facts["turns"] = turned
        facts["errors_turned"] = errors_only(mate_errors(px, doc))

        # Driven, the output turned by a Transform2 put: does the gear mate bring it back, turn the train, or keep it?
        pushed = {}
        for name, t in trains.items():
            keys = [g["key"] for g in t["gears"]]
            g4 = asm.gears[keys[3]]
            start = {k: frame_of(asm.gears[k])[0] for k in keys}
            m, o = frame_of(g4)
            put(px, doc, g4, crossed.multiply(m, crossed.rot_z(DRAG)), o)
            pushed[name] = _turns(asm, keys, start)
            put(px, doc, g4, m, o)          # and back where it was
            pushed[name]["back"] = round(own_turn(m, frame_of(g4)[0]), 9)
        facts["output_put_while_driven"] = pushed

        # The drive suppressed: the input dragged, and the train follows as one.
        dragged = {}
        suppressed = {name: suppress(px, doc, drive, True) for name, drive in drives.items()}
        facts["drive_suppressed_by"] = suppressed
        facts["rebuild_undriven"] = rebuild(px, doc, "drive suppressed")
        facts["constrained_undriven"] = {k: constrained(px, c) for k, c in asm.gears.items()}
        for route in DRAG_ROUTES:
            before = {k: frame_of(c)[0] for k, c in asm.gears.items()}
            for name, t in trains.items():
                g1 = asm.gears[t["gears"][0]["key"]]
                if route.startswith("IDragOperator"):
                    facts.setdefault("drag_operator", {})[f"{route} {name}"] = drag(px, doc, g1, DRAG, route)
                else:
                    m, o = frame_of(g1)
                    put(px, doc, g1, crossed.multiply(m, crossed.rot_z(DRAG)), o, route=route)
            call(doc, "ForceRebuild3", False)
            dragged[route] = {name: _turns(asm, [g["key"] for g in t["gears"]], before) for name, t in trains.items()}
        facts["dragged"] = dragged
        unsuppressed = {name: suppress(px, doc, drive, False) for name, drive in drives.items()}
        facts["drive_unsuppressed_by"] = unsuppressed
        facts["rebuild_redriven"] = rebuild(px, doc, "drive back on")
        facts["errors_before_save"] = errors_only(mate_errors(px, doc))
        names = asm.names()
        mate_list = sorted(n for n, _ in _mate_features(doc))
        frames_saved = {k: frame_of(c) for k, c in asm.gears.items()}
        px.require(_save_in_place(px, doc, asm_path, "the train") and os.path.isfile(asm_path), "the train saves")
        px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
    finally:
        if asm.doc is not None and not str(call(asm.doc, "GetPathName") or ""):
            sc.close(px, asm.doc)
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")

    reopened: Dict[str, Any] = {}
    try:
        started = time.monotonic()
        doc, _route = open_by_path(px, asm_path, sc.SW_DOC_ASSEMBLY, prefer="OpenDoc6")
        reopened["seconds_to_open"] = round(time.monotonic() - started, 3)
        reopened["mates_same"] = sorted(n for n, _ in _mate_features(doc)) == mate_list
        reopened["errors"] = errors_only(mate_errors(px, doc))
        components = {k: call(doc, "GetComponentByName", n) for k, n in names.items()}
        reopened["frames"] = {k: {"rotation": rotation_error(frame_of(c)[0], frames_saved[k][0]),
                                  "origin_mm": math.dist(frame_of(c)[1], frames_saved[k][1])}
                              for k, c in components.items() if c is not None}
        before = {k: frame_of(c)[0] for k, c in components.items()}
        eqm = call(doc, "GetEquationMgr")
        _set_global(eqm, DRIVE, TRAIN_DRIVE_AGAIN)
        reopened["rebuild"] = rebuild(px, doc, "driven after the reopen")
        reopened["turns"] = {name: {g["key"]: round(world_turn(before[g["key"]], frame_of(components[g["key"]])[0]), 9)
                                    for g in t["gears"]} for name, t in trains.items()}
        reopened["errors_after"] = errors_only(mate_errors(px, doc))
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    facts["reopened"] = reopened
    px.fact("train", facts)
    px.fact("train_mates", mates)

    # -- what it says
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    px.fact("train_expected_turns_per_degree", expected)
    jump = max(max(v["rotation"], v["origin_mm"]) for v in facts["jumps_after_mating"].values())
    jump_drive = max(max(v["rotation"], v["origin_mm"]) for v in facts["jumps_after_drive"].values())
    px.check(jump < TOLERANCE_MM, f"no gear moved when mated from where W4 placed it (largest {jump:.1e})")
    px.check(jump_drive < TOLERANCE_MM, f"no gear moved when the drive was added (largest {jump_drive:.1e})")
    px.check(not facts["errors_mated"] and not facts["errors_driven"] and not facts["errors_turned"]
             and not reopened["errors"] and not reopened["errors_after"], "no mate has an error, before or after the reopen")
    right_way = {}
    drag_follow: Dict[str, List[bool]] = {}
    for name, t in trains.items():
        keys = [g["key"] for g in t["gears"]]
        turns = [facts["turns"][name][k] for k in keys]
        right_way[name] = _ratio_ok(turns, expected) and abs(abs(turns[0]) - (DRIVE_TO - DRIVE_FROM)) < 1e-6
        px.check(right_way[name], f"{name}: the input turned {turns[0]:.6f}°, the output {turns[3]:.6f}° "
                                  f"({turns[3] / turns[0] if turns[0] else math.nan:.9f} of it; 1/12 the same way wanted)")
        again = [reopened["turns"][name][k] for k in keys]
        px.check(_ratio_ok(again, expected), f"{name}, reopened and driven again: {again}")
        for route, by in facts["dragged"].items():
            dragged_turns = [by[name][k] for k in keys]
            follows = _ratio_ok(dragged_turns, expected) and abs(abs(dragged_turns[0]) - DRAG) < 1e-6
            drag_follow.setdefault(route, []).append(follows)
            px.note(f"{name}: the drive suppressed, the input turned by {route}: {dragged_turns} — "
                    f"{'the train followed' if follows else 'the train did NOT follow'}")
        put_on = facts["output_put_while_driven"][name]
        px.note(f"{name}: driven, the output turned {DRAG:g}° by a Transform2 put: {put_on}")
    px.fact("train_right_way", right_way)
    routes_followed = [r for r in DRAG_ROUTES if drag_follow.get(r) and all(drag_follow[r])]
    px.fact("drag_routes_the_train_follows", routes_followed)
    one = all(v == 2 for v in facts["constrained_mated"].values()) and \
        all(v == 3 for v in facts["constrained_driven"].values()) and \
        all(v == 2 for v in facts["constrained_undriven"].values())
    px.fact("one_drive_fully_defines_the_train", one)
    px.check(one, "every gear is under-defined until the input's one drive mate, which makes every gear fully defined: "
                  "the train has one degree of freedom")
    kept = all(abs(v[t["gears"][3]["key"]] - DRAG) < 1e-6 and
               all(abs(v[g["key"]]) < 1e-6 for g in t["gears"][:3])
               for (n, v), t in zip(facts["output_put_while_driven"].items(), trains.values()))
    px.fact("put_turns_a_gear_mated_gear_alone", kept)
    px.check(all(reopened["frames"].get(k, {"origin_mm": 1.0})["origin_mm"] < TOLERANCE_MM for k in names),
             "reopened, every gear is where it was saved")
    px.check(reopened["mates_same"], "reopened, the same mates")
    px.shared["w8_train"] = {"path": asm_path, "layout": layout_path, "part": part_path, "names": names,
                             "mates": mates, "trains": trains}


# -- 6: after the train turns: a shaft moved by its globals, and the mesh phase -----

MOVE_ANGLE = 20.0    # degrees the output shaft is swung round the compound shaft, keeping its centre distance
AT_MOVED = 22.0      # mm, the output gear's front face moved along its shaft through an assembly global
LOCK_TURN = 11.0     # degrees the compound's second gear is turned while its lock is suppressed


def swung(centre: Sequence[float], radius: float, degrees: float) -> Tuple[float, float]:
    """A shaft ``radius`` from ``centre`` at ``degrees`` from +Y towards +X: where S3 goes when swung round S2."""
    a = math.radians(degrees)
    return (centre[0] + radius * math.sin(a), centre[1] + radius * math.cos(a))


def _set_exact(eqm: Any, name: str, value: float) -> str:
    """Change a global in place to ``value`` written to nine decimals; returns what reads back."""
    from .p7_workbook import _names_global  # noqa: PLC0415
    for index in range(int(call(eqm, "GetCount"))):
        if _names_global(str(call(eqm, "Equation", index)), name):
            sc.put_indexed(eqm, "Equation", index, f'"{name}"= {value:.9f}')
            return str(call(eqm, "Equation", index))
    raise Require(f'There is no global "{name}" to change.')


def phase_change(swing: float, teeth_driver: int, teeth_driven: int) -> float:
    """How far the driven gear must turn, about +Z, when the direction to it from its driver turns ``swing`` degrees
    and the driver stays put: θq = φ + π − π/zq − (θp − φ)·zp/zq (PLAN-WORKBOOK §3.3), so dθq/dφ = 1 + zp/zq."""
    return swing * (1.0 + teeth_driver / teeth_driven)


@probe("motion_update", needs=("mated_train",), tier=8,
       members=("ISldWorks.OpenDoc6", "ISldWorks.ActivateDoc3", "IEquationMgr.Equation", "IFeature.SetSuppression2",
                "IComponent2.Transform2", "IModelDoc2.EditDelete"))
def motion_update(px: Px) -> None:
    """The saved train: a shaft moved by the layout's globals, the mates following; the mesh phase put right; At moved."""
    enums = _enums(px)
    info = px.shared.get("w8_train")
    px.require(bool(info), "mated_train left a train to update")
    rule = px.shared["gear_mate_flip_rule"]
    trains, names, mates = info["trains"], info["names"], info["mates"]
    t = trains["all Z+"]
    g1, g2, g3, g4 = t["gears"]
    (s1, x1, y1), (s2, x2, y2), (s3, x3, y3) = t["shafts"]
    paths = [info["path"], info["layout"], info["part"]]
    facts: Dict[str, Any] = {}
    try:
        doc, _ = open_by_path(px, info["path"], sc.SW_DOC_ASSEMBLY, prefer="OpenDoc6")
        asm_title = str(call(doc, "GetTitle"))
        components = {k: call(doc, "GetComponentByName", n) for k, n in names.items()}
        px.require(all(c is not None for c in components.values()), "every gear is found by name")
        others = [g["key"] for g in trains["middle Z-"]["gears"]]
        before = {k: frame_of(c) for k, c in components.items()}

        # A: the layout's globals move S3 round S2, as Update SolidWorks would.
        x_new, y_new = swung((x2, y2), TRAIN_C34, MOVE_ANGLE)
        layout, route = open_by_path(px, info["layout"], prefer="OpenDoc6")
        from .p7_workbook import activate  # noqa: PLC0415
        px.require(activate(px, str(call(layout, "GetTitle"))), "the layout part is made active")
        leqm = call(layout, "GetEquationMgr")
        # Written to 9 decimals: _set_global's :g kept six figures, and the first run put S3 5e-5 mm off.
        facts["layout_set"] = [_set_exact(leqm, f"{s3} X", x_new), _set_exact(leqm, f"{s3} Y", y_new)]
        facts["layout_rebuild"] = plain(call(layout, "ForceRebuild3", False))
        px.require(activate(px, asm_title), "the assembly is made active again")
        facts["assembly_rebuild_after_move"] = rebuild(px, doc, "after the layout moved S3")
        m4, o4 = frame_of(components[g4["key"]])
        facts["output_after_move"] = {"at_mm": _mm(o4), "axis": _mm(column(m4, 2)),
                                      "wanted_mm": [round(x_new, 9), round(y_new, 9), g4["at"][2]],
                                      "turned": round(world_turn(before[g4["key"]][0], m4), 9)}
        facts["moved_others"] = {k: math.dist(frame_of(components[k])[1], before[k][1]) for k in names if k != g4["key"]}
        facts["errors_after_move"] = errors_only(mate_errors(px, doc))

        eqm = call(doc, "GetEquationMgr")
        keys = [g["key"] for g in t["gears"]]
        start = {k: frame_of(c)[0] for k, c in components.items()}
        _set_global(eqm, DRIVE, DRIVE_TO + 15.0)
        rebuild(px, doc, "driven after the move")
        facts["turns_after_move"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}

        # B: the mesh phase. The output must turn this much more than its gear mate holds it.
        delta = phase_change(MOVE_ANGLE, g3["teeth"], g4["teeth"])
        facts["phase_change_wanted"] = delta
        gear_mate = mates[f"{g3['key']}-{g4['key']}"]["name"]
        out4 = components[g4["key"]]

        # (a) turned while its gear mate is on
        start = {k: frame_of(c)[0] for k, c in components.items()}
        m, o = frame_of(out4)
        put(px, doc, out4, crossed.multiply(m, crossed.rot_z(delta)), o)
        facts["put_with_gear_mate_on"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}
        facts["errors_after_put"] = errors_only(mate_errors(px, doc))
        start = {k: frame_of(c)[0] for k, c in components.items()}
        _set_global(eqm, DRIVE, DRIVE_TO + 22.0)
        rebuild(px, doc, "driven after the put")
        facts["turns_after_put"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}

        # (b) turned between suppressing and unsuppressing its gear mate
        start = {k: frame_of(c)[0] for k, c in components.items()}
        facts["suppressed_by"] = suppress(px, doc, gear_mate, True)
        rebuild(px, doc, "gear mate suppressed")
        m, o = frame_of(out4)
        put(px, doc, out4, crossed.multiply(m, crossed.rot_z(delta)), o)
        facts["put_while_suppressed"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}
        facts["unsuppressed_by"] = suppress(px, doc, gear_mate, False)
        facts["rebuild_unsuppressed"] = rebuild(px, doc, "gear mate back on")
        facts["after_unsuppress"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}
        facts["errors_after_unsuppress"] = errors_only(mate_errors(px, doc))
        start = {k: frame_of(c)[0] for k, c in components.items()}
        _set_global(eqm, DRIVE, DRIVE_TO + 30.0)
        rebuild(px, doc, "driven after the phase")
        facts["turns_after_phase"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}

        # (c) only if (b) did not keep the new phase: the gear mate deleted, the gear turned, the mate made again.
        kept = abs(facts["after_unsuppress"][g4["key"]] - delta) < 1e-6
        facts["unsuppress_keeps_the_phase"] = kept
        if not kept:
            start = {k: frame_of(c)[0] for k, c in components.items()}
            facts["deleted_by"] = delete_mate(px, doc, gear_mate)
            m, o = frame_of(out4)
            put(px, doc, out4, crossed.multiply(m, crossed.rot_z(delta)), o)
            flip = needed_flip(rule, g3["sigma"], g4["sigma"], False, g3["teeth"] > g4["teeth"])
            picked = select_in(px, doc, components[g3["key"]], "Gear Axis", "AXIS", False) and \
                select_in(px, doc, out4, "Gear Axis", "AXIS", True)
            made = add_mate(px, doc, "the output's gear mate made again", enums["gear"], enums["closest"], flip=flip,
                            ratio=(float(g3["teeth"]), float(g4["teeth"]))) if picked else {"name": None}
            facts["remade"] = made
            rebuild(px, doc, "gear mate made again")
            facts["after_remake"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}
            start = {k: frame_of(c)[0] for k, c in components.items()}
            _set_global(eqm, DRIVE, DRIVE_TO + 45.0)
            rebuild(px, doc, "driven after the remake")
            facts["turns_after_remake"] = {k: round(world_turn(start[k], frame_of(components[k])[0]), 9) for k in keys}

        # (d) the compound lock the same way: suppressed, the second gear turned, unsuppressed.
        lock = mates.get("all Z+ lock")
        if lock:
            p2, p3 = components[g2["key"]], components[g3["key"]]
            relative = relative_angle(p2, p3)
            lock_result: Dict[str, Any] = {"mate": lock, "suppressed_by": suppress(px, doc, lock, True)}
            rebuild(px, doc, "lock suppressed")
            m, o = frame_of(p3)
            put(px, doc, p3, crossed.multiply(m, crossed.rot_z(LOCK_TURN)), o)
            lock_result["relative_while_suppressed"] = round(unwrap(relative_angle(p2, p3) - relative), 9)
            lock_result["unsuppressed_by"] = suppress(px, doc, lock, False)
            lock_result["rebuild"] = rebuild(px, doc, "lock back on")
            lock_result["relative_after_unsuppress"] = round(unwrap(relative_angle(p2, p3) - relative), 9)
            lock_result["errors"] = errors_only(mate_errors(px, doc))
            start = {k: frame_of(c)[0] for k, c in components.items()}
            _set_global(eqm, DRIVE, DRIVE_TO + 60.0)
            rebuild(px, doc, "driven after the lock moved")
            lock_result["relative_after_drive"] = round(unwrap(relative_angle(p2, p3) - relative), 9)
            facts["lock_moved"] = lock_result

        # C: At through an assembly global on the output's axial distance mate.
        axial = (mates.get(g4["key"]) or [None, None])[1]
        at_result: Dict[str, Any] = {"mate": axial}
        if axial:
            feature = mate_feature(doc, axial)
            wanted = sc.m(abs(g4["at"][2]))
            match = [d for d in sc.dimensions_of(feature) if abs(float(call(d, "SystemValue")) - wanted) < 1e-9]
            at_result["dimensions"] = [(str(call(d, "Name")), float(call(d, "SystemValue")) * sc.MM)
                                       for d in sc.dimensions_of(feature)]
            add = adder(px, eqm)
            if len(match) == 1 and add(f'"{g4["key"]} At"= {abs(g4["at"][2]):g}') >= 0 and \
                    add(f'"{call(match[0], "Name")}@{axial}"= "{g4["key"]} At"') >= 0:
                start = {k: frame_of(c) for k, c in components.items()}
                _set_global(eqm, f"{g4['key']} At", AT_MOVED)
                at_result["rebuild"] = rebuild(px, doc, "At moved")
                m4, o4 = frame_of(out4)
                at_result["output_at_mm"] = _mm(o4)
                at_result["others_moved_mm"] = {k: math.dist(frame_of(components[k])[1], start[k][1])
                                                for k in names if k != g4["key"]}
                at_result["errors"] = errors_only(mate_errors(px, doc))
        facts["at_by_global"] = at_result
        facts["other_train_moved_mm"] = {k: math.dist(frame_of(components[k])[1], before[k][1]) for k in others}
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.fact("motion_update", facts)

    # -- what it says
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    out = facts["output_after_move"]
    followed = math.dist(out["at_mm"], out["wanted_mm"]) < TOLERANCE_MM and abs(out["axis"][2] - 1.0) < 1e-9
    px.check(followed, f"the layout's globals moved S3 and the output gear went with its axis: {out}")
    px.check(not facts["errors_after_move"], f"no mate error after the move: {facts['errors_after_move']}")
    px.check(all(v < TOLERANCE_MM for k, v in facts["moved_others"].items() if k not in (g4["key"],)),
             f"nothing else moved: {facts['moved_others']}")
    turns = [facts["turns_after_move"][k] for k in [g["key"] for g in t["gears"]]]
    px.check(_ratio_ok(turns, expected), f"after the move the train still turns 1/12 the same way: {turns}")
    px.fact("layout_move_carries_mates", bool(followed and not facts["errors_after_move"] and _ratio_ok(turns, expected)))
    # What SolidWorks did to the gear's turn as its shaft swung, against what keeping it meshed needs.
    turned = out["turned"]
    px.fact("turn_on_a_shaft_move", {"turned": turned, "mesh_needs": delta,
                                      "as_a_multiple_of_the_need": round(turned / delta, 6) if delta else None})
    px.note(f"swinging S3 {MOVE_ANGLE:g}° round S2 turned the output {turned:.6f}°; staying in mesh needs "
            f"{delta:+.6f}°, so the app puts the phase back after any move")
    phase_route = None
    after = facts["after_unsuppress"]
    put_on = facts["put_with_gear_mate_on"]
    if abs(put_on[g4["key"]] - delta) < 1e-6 and all(abs(put_on[k]) < 1e-6 for k in keys if k != g4["key"]) and \
            not facts["errors_after_put"] and _ratio_ok([facts["turns_after_put"][g["key"]] for g in t["gears"]], expected):
        phase_route = "Transform2 put with the gear mate on"
    elif facts["unsuppress_keeps_the_phase"] and abs(after[g3["key"]]) < 1e-6 and \
            _ratio_ok([facts["turns_after_phase"][g["key"]] for g in t["gears"]], expected):
        phase_route = "suppress the gear mate, Transform2 put, unsuppress"
    elif facts.get("after_remake") and abs(facts["after_remake"][g4["key"]] - delta) < 1e-6 and \
            _ratio_ok([facts["turns_after_remake"][g["key"]] for g in t["gears"]], expected):
        phase_route = "delete the gear mate, Transform2 put, add it again"
    px.fact("mesh_phase_route", phase_route)
    moved = facts.get("lock_moved") or {}
    lock_kept = bool(moved) and abs(moved.get("relative_after_unsuppress", 0.0) - LOCK_TURN) < 1e-6 and \
        abs(moved.get("relative_after_drive", 0.0) - LOCK_TURN) < 1e-6 and not moved.get("errors")
    px.fact("lock_unsuppress_keeps_the_new_angle", lock_kept if moved else None)
    px.check(phase_route is not None, f"the output's mesh phase can be put right with the train mated: {phase_route}")
    px.fact("put_with_gear_mate_on_moves", {"output": put_on[g4["key"]], "input": put_on[g1["key"]]})
    at = facts["at_by_global"]
    moved_at = bool(at.get("output_at_mm")) and abs(at["output_at_mm"][2] - AT_MOVED) < TOLERANCE_MM and \
        all(v < TOLERANCE_MM for v in at.get("others_moved_mm", {"x": 1.0}).values()) and not at.get("errors")
    px.check(moved_at, f"an assembly global on the axial mate moves the gear along its shaft: {at}")
    px.fact("axial_global_moves_gear", moved_at)
