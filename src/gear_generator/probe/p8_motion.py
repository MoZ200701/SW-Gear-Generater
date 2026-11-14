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

Items 7-15 are what W5's plan (docs/notes-workbook/W5-PLAN.md §0.3) and its
review (W5-PLAN-REVIEW.md M4, M5) asked before any code, what the review of
tier 7's assembly_rebuild_scope found missing for a mated assembly, and probe
round P0b (docs/notes-workbook/W5-DECISIONS.md, "Rulings on package P0's
findings"). Items 7, 8-11 each work on their own copy of the train mated_train
saved; 7b and 13 build their own; each rebuild is the one Update gives an
assembly (ForceRebuild3(True)), except where item 13 compares the routes.

7. ``gear_mate_ratio`` (P1) — a saved gear mate's ratio changed in the
   reopened train by deleting it and making it again (the remake); driven,
   saved, closed (whether it could be), reopened, driven again.
7b. ``gear_mate_update`` (P1b) — the shape an Update needs for a tooth
   change, on real gears the app builds: the parts' teeth by their globals,
   every lock suppressed, the gear mate remade and given its old name, every
   gear put to its built frame, the locks back on, a top-only rebuild, the
   mate check, the drive at the new ratio, interference; closed unsaved and
   reopened as it was saved; and again, saved, reopened, driven.
8. ``lock_retake_offset`` (P2) — each compound lock suppressed, its second
   gear put 3 mm along its axis and 11° round, the lock back on: is the axial
   offset kept as well as the angle, through a drive?
9. ``lock_mate_rename`` (M4a) — a lock, a gear mate, an axis mate, an axial
   mate and a suppressed lock renamed as W5 names them, saved, reopened: found
   by the new names, old names gone, the same kinds, suppression kept, holding.
10. ``demonstration_drive`` (M4b) — the drive W5's demonstration plans: the
    input at its built phase, an angle mate from its Top plane to the layout's
    Right at 90°, 90 -> 120 -> 90, then deleted; every frame back as built.
11. ``put_on_twice_meshed_gear`` (M4c) — in the undriven train, locks
    suppressed around the puts: the compound anchor put round, every gear put
    back, and a gear carrying two gear mates put round; a put with the lock on,
    then driven; and the remake on the gear carrying two gear mates.
12. ``axial_datum_plane`` (M5) — anchors on Z+ and Z- held along their shafts
    from a layout plane 1000 mm behind Front, the distance on an assembly
    global, moved through where the Front plane is, driven, saved, reopened.
13. ``mated_rebuild_scope`` — per assembly rebuild route, a train of its own,
    built with that route as its only rebuild and its own layout and part:
    the build's mate check and drive, then an axial global, a drive, a put
    under a suppressed lock, a layout move, a part change and an
    over-defining mate, each read before and after the route, the train
    driven after the put, the move and the change, every frame compared with
    the full rebuild's train; what shows and what is marked.
15. ``gear_mate_definition`` (last) — a gear mate's ratio changed through its
    definition, each recipe on its own copy, and whether the copy can be
    closed afterwards: recorded, never chosen. Last, because on 2024 what it
    changes cannot be closed and holds the train's layout and part open.

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
import shutil
import time
from dataclasses import dataclass
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


def rebuild(px: Px, asm: Any, label: str, top_only: bool = False) -> Dict[str, Any]:
    """``ForceRebuild3``: of everything (False, items 1-6 as they ran), or of the top level only (True, the route
    Update gives an assembly, findings.ASSEMBLY_REBUILD_ROUTE, which items 7-12 use)."""
    started = time.monotonic()
    got, result = px.attempt(f"ForceRebuild3{'(True)' if top_only else ''} ({label})",
                             lambda: call(asm, "ForceRebuild3", top_only))
    out = {"returned": plain(result) if got else "raised", "seconds": round(time.monotonic() - started, 3)}
    if top_only:
        out["top_only"] = True
    return out


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


def put(px: Px, asm: Any, component: Any, matrix: Matrix, at: Sequence[float], route: str = "Transform2 put",
        top_only: bool = False) -> bool:
    """Set a frame by ``Transform2`` (then a rebuild) or ``SetTransformAndSolve2``, without checking where it ended."""
    transform = make_transform(px, array_data(matrix, at, findings.TRANSFORM_ARRAY_ORDER or "columns"))
    if route == "Transform2 put":
        got, _ = px.attempt(f"Transform2 put on {call(component, 'Name2')}",
                            lambda: setattr(component, "Transform2", transform))
        call(asm, "ForceRebuild3", top_only)
        return got
    got, value = px.attempt(f"SetTransformAndSolve2 on {call(component, 'Name2')}",
                            lambda: call(component, "SetTransformAndSolve2", transform))
    return bool(got and value)


def frame_mm(component: Any) -> Tuple[Matrix, Vec]:
    return frame_of(component)


def frame_report(component: Any, matrix: Matrix, at: Sequence[float]) -> Dict[str, float]:
    got, origin = frame_of(component)
    return {"rotation": rotation_error(got, matrix), "origin_mm": math.dist(origin, at)}


def is_suppressed(px: Px, feature: Any) -> Optional[bool]:
    """``IsSuppressed2`` in this configuration, else ``IsSuppressed``; None when neither answers."""
    try:
        value = call(feature, "IsSuppressed2", _enums(px)["this_configuration"], sc.null())
        value = value[0] if isinstance(value, tuple) else value
        return bool(value[0] if isinstance(value, (list, tuple)) else value)
    except Exception:  # noqa: BLE001
        try:
            return bool(call(feature, "IsSuppressed"))
        except Exception:  # noqa: BLE001
            return None


def suppress(px: Px, asm: Any, name: str, on: bool) -> Optional[str]:
    """Suppress or unsuppress one mate; the route that did it, judged by ``IsSuppressed2``, or None."""
    enums = _enums(px)
    action = enums["suppress"] if on else enums["unsuppress"]
    feature = mate_feature(asm, name)

    def state() -> Optional[bool]:
        return is_suppressed(px, feature)

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
               add: Callable[[str], int], align: int, angle: float = DRIVE_FROM,
               global_name: str = DRIVE) -> Optional[str]:
    """An angle mate between a gear's plane ``gear_top`` and the layout's ``layout_top`` (their Top planes, unless
    told otherwise), named ``<global> <label>``, its dimension linked to the global ``global_name`` ("Drive" by
    default; it must exist). Returns the mate's name, or None."""
    if not (select_in(px, asm, gear, gear_top, "PLANE", False) and select_in(px, asm, layout, layout_top, "PLANE", True)):
        px.fail(f"{label}: the gear's Top plane and the layout's could not both be selected")
        return None
    made = add_mate(px, asm, f"{label}: drive angle", _enums(px)["angle"], align, angle=angle)
    if made["name"] is None:
        px.fail(not_made(f"{label}: the drive angle mate", made))
        return None
    feature = mate_feature(asm, made["name"])
    name = _rename(px, feature, f"{global_name} {label}")
    match = [d for d in sc.dimensions_of(feature) if abs(float(call(d, "SystemValue")) - math.radians(angle)) < 1e-9]
    if len(match) != 1 or add(f'"{call(match[0], "Name")}@{name}"= "{global_name}"') < 0:
        px.fail(f"{label}: the drive's dimension could not be linked to the global")
        return None
    return name


# -- the layout part and the parts --------------------------------------------

DATUM_PLANE = "Datum Plane"   # a layout plane far behind Front (W5-PLAN-REVIEW M5), when one is asked for


def layout_part(px: Px, folder: str, stem: str, shafts: Sequence[Tuple[str, float, float]],
                link: bool = False, datum: Optional[float] = None) -> str:
    """A body-less part of planes offset from Right and Top and an axis ``"<shaft> Axis"`` through each pair, the
    Top-parallel plane selected first so it reads +Z as W4 makes it; saved and closed. With ``link``, each offset
    driven by a global ``"<shaft> X"`` / ``"<shaft> Y"``. Every coordinate must be positive. With ``datum``, also
    a plane ``DATUM_PLANE`` offset from Front to z = ``datum`` mm, on the side ref_plane_offset's flip rule gives
    (findings.REF_PLANE_UNFLIPPED_IS_PLUS_Z), measured where it landed."""
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
        if datum is not None:
            unflipped_plus = findings.REF_PLANE_UNFLIPPED_IS_PLUS_Z
            if unflipped_plus is None:
                raise Require("ref_plane_offset has not said which flip puts a plane from Front on +Z.")
            flip = bool(unflipped_plus) == (datum < 0)
            plane = _plane_from(px, doc, sc.planes(doc)[0], abs(datum), flip, DATUM_PLANE, routes)
            call(doc, "ForceRebuild3", False)
            from .p7_workbook import _measure  # noqa: PLC0415
            where = _measure(px, doc, plane)
            directions[DATUM_PLANE] = {"flip": flip, **where}
            if abs(where["origin_mm"][2] - datum) > TOLERANCE_MM:
                raise Require(f"{DATUM_PLANE} landed at {where}, not at z = {datum:g} mm.")
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


def rename_at_once(px: Px, doc: Any, made: Dict[str, Any], new: str) -> Dict[str, Any]:
    """Give a mate its name straight after its AddMate5 (an ``IFeature.Name`` put), as W5's build does: what reads
    back at once and whether the mate-group walk finds it by the new name at once. ``made`` takes the new name."""
    out: Dict[str, Any] = {"made_as": made.get("name"), "to": new}
    if not made.get("name"):
        return out
    feature = mate_feature(doc, made["name"])
    out["put"] = px.attempt(f"IFeature.Name = {new!r} on {made['name']} straight after AddMate5",
                            lambda: setattr(feature, "Name", new))[0]
    out["reads"] = str(call(feature, "Name"))
    out["walk_finds"] = new in mate_names(doc)
    if out["reads"] == new:
        made["name"] = new
    return out


def mount(px: Px, asm: Assembly, key: str, shaft: str, sigma: int, z_front: float, at: Sequence[float],
          record: Optional[List[Dict[str, Any]]] = None, rename: Optional[Sequence[str]] = None,
          renamed: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """Unfix gear ``key`` and mate it to ``"<shaft> Axis"`` and along it, the way shaft_axis_mates decided.

    Returns the mates' names (and adds what each AddMate5 answered to ``record``); a mate that was not made ends
    the probe. With ``rename`` (the axis mate's name, the axial one's), each is renamed straight after its own
    AddMate5 and what that read back is added to ``renamed``.
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
    if rename:
        (renamed if renamed is not None else []).append(rename_at_once(px, doc, made[0], rename[0]))
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
    if rename:
        (renamed if renamed is not None else []).append(rename_at_once(px, doc, made[1], rename[1]))
    if record is not None:
        record.extend(made)
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
        layout_name = str(call(asm.layout, "Name2"))
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
                             "mates": mates, "trains": trains, "layout_name": layout_name}


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


# -- 7-12: what W5's plan and its review ask before any code (W5-PLAN §0.3, package P0) --------
#
# Items 7-11 work on copies of the train mated_train saved (copied on disk while it is closed, so each starts from
# the same file and none sees another's changes); item 12 builds its own. Each rebuilds as Update will
# (ForceRebuild3(True), findings.ASSEMBLY_REBUILD_ROUTE). Note that motion_update saved the layout part with the
# output shaft swung 20°, so a copy's output gear goes there on its first rebuild; every measurement starts after it.

TOP_ONLY = bool(findings.ASSEMBLY_REBUILD_TOP_ONLY)


def relative_pose(anchor: Tuple[Matrix, Sequence[float]], follower: Tuple[Matrix, Sequence[float]]) -> Dict[str, float]:
    """Where a follower sits against its anchor on one shaft: its turn about the anchor's axis (degrees), its
    origin's distance along that axis from the anchor's (mm), how far its origin is off that axis (mm), and how far
    its own axis is from the anchor's (matrix entries)."""
    (ma, oa), (mf, of) = anchor, follower
    axis = column(ma, 2)
    d = tuple(float(of[i]) - float(oa[i]) for i in range(3))
    along = _dot(d, axis)
    return {"angle": own_turn(ma, mf), "along": along,
            "off_axis": math.sqrt(max(0.0, _dot(d, d) - along * along)),
            "axis_off": max(abs(a - b) for a, b in zip(column(mf, 2), axis))}


def pose_change(before: Mapping[str, float], after: Mapping[str, float]) -> Dict[str, float]:
    """How a relative pose changed: the turn (unwrapped) and the move along the axis; off-axis as it is after."""
    return {"angle": round(unwrap(after["angle"] - before["angle"]), 9), "along": round(after["along"] - before["along"], 9),
            "off_axis": round(after["off_axis"], 9), "axis_off": round(after["axis_off"], 12)}


def joined_turns(teeth: Sequence[int] = TRAIN_TEETH, bridge: Tuple[int, int] = (51, 17),
                 second: Optional[Sequence[int]] = None) -> List[float]:
    """Each gear's turn about +Z per degree of the first, for two compound trains (``teeth``, then ``second``, the
    same unless given) joined by one more external gear mate from the first train's output (``bridge[0]`` teeth in
    that mate's ratio) to the second's input (``bridge[1]``): the first train's turns then the second's."""
    first = train_turns(teeth, (1,) * len(teeth))
    other = list(second if second is not None else teeth)
    start = -first[-1] * bridge[0] / bridge[1]
    return first + [start * v for v in train_turns(other, (1,) * len(other))]


def _frames(components: Mapping[str, Any]) -> Dict[str, Tuple[Matrix, Vec]]:
    return {k: frame_of(c) for k, c in components.items()}


def _world_turns(components: Mapping[str, Any], before: Mapping[str, Tuple[Matrix, Vec]]) -> Dict[str, float]:
    return {k: round(world_turn(before[k][0], frame_of(components[k])[0]), 9) for k in before}


def _off(components: Mapping[str, Any], wanted: Mapping[str, Tuple[Matrix, Sequence[float]]]) -> Dict[str, Dict[str, float]]:
    """Each component's frame against a wanted one: the largest matrix entry off, and the origin's distance in mm."""
    out = {}
    for key, (matrix, at) in wanted.items():
        got, origin = frame_of(components[key])
        out[key] = {"rotation": rotation_error(got, matrix), "origin_mm": math.dist(origin, at)}
    return out


def worst(off: Mapping[str, Mapping[str, float]]) -> float:
    """The largest rotation or origin error in a table from ``_off`` (0 for an empty one)."""
    return max((max(v["rotation"], v["origin_mm"]) for v in off.values()), default=0.0)


def _train_ok(turns: Mapping[str, float], keys: Sequence[str], expected: Sequence[float], step: float) -> bool:
    """The first key turned ``step`` degrees (either way) and every other its share of it, signs included."""
    values = [turns[k] for k in keys]
    return _ratio_ok(values, expected) and abs(abs(values[0]) - abs(step)) < 1e-6


def _train_copy(px: Px, stem: str) -> Tuple[Dict[str, Any], str]:
    """A copy, on disk and under its own name, of the train mated_train saved; mated_train's record of it."""
    info = px.shared.get("w8_train")
    px.require(bool(info), "mated_train left a train")
    path = os.path.join(os.path.dirname(info["path"]), f"{stem}.SLDASM")
    _fresh(px, path)
    got, _ = px.attempt(f"copy {os.path.basename(info['path'])} to {os.path.basename(path)} on disk (no SolidWorks call)",
                        lambda: shutil.copyfile(info["path"], path))
    px.require(got and os.path.isfile(path), f"the saved train is copied to {os.path.basename(path)}")
    return info, path


def _open_train(px: Px, path: str, names: Mapping[str, str]) -> Tuple[Any, Dict[str, Any]]:
    """Open a train by its path (OpenDoc6) and find every gear by name; the document and the components by key."""
    doc, _route = open_by_path(px, path, sc.SW_DOC_ASSEMBLY, prefer="OpenDoc6")
    px.require(doc is not None, f"{os.path.basename(path)} opens")
    title = str(call(doc, "GetTitle"))
    if title not in px.shared.setdefault("created", []):
        px.shared["created"].append(title)
    components = {k: call(doc, "GetComponentByName", n) for k, n in names.items()}
    px.require(all(c is not None for c in components.values()), "every gear is found by name")
    return doc, components


def _drive_by(px: Px, doc: Any, components: Mapping[str, Any], step: float, label: str,
              global_name: str = DRIVE) -> Dict[str, float]:
    """Change a drive global by ``step`` degrees and rebuild; every gear's turn about +Z."""
    from .p7_workbook import _global_value  # noqa: PLC0415
    eqm = call(doc, "GetEquationMgr")
    now = _global_value(eqm, global_name)
    if now is None:
        raise Require(f'There is no global "{global_name}" to drive by.')
    before = _frames(components)
    _set_global(eqm, global_name, now + step)
    rebuild(px, doc, label, top_only=TOP_ONLY)
    return _world_turns(components, before)


def mate_names(asm: Any) -> List[str]:
    return [n for n, _ in _mate_features(asm)]


def mate_states(px: Px, asm: Any) -> Dict[str, Dict[str, Any]]:
    """Every mate by name: its feature type, whether it is suppressed, and its error code."""
    out: Dict[str, Dict[str, Any]] = {}
    for feature in sc.top_features(asm):
        if sc.type_name(feature) == "MateGroup":
            child = call(feature, "GetFirstSubFeature")
            while child is not None:
                out[str(call(child, "Name"))] = {"type": sc.type_name(child), "suppressed": is_suppressed(px, child),
                                                 **error_code(px, child)}
                child = call(child, "GetNextSubFeature")
    return out


def _turned_put(px: Px, doc: Any, component: Any, degrees: float, along: float = 0.0) -> Tuple[Matrix, Vec]:
    """Put a component turned ``degrees`` about its own axis and moved ``along`` mm along it (Transform2, then a
    top-level rebuild); the frame it was put to."""
    m, o = frame_of(component)
    axis = column(m, 2)
    target = (crossed.multiply(m, crossed.rot_z(degrees)), tuple(o[i] + along * axis[i] for i in range(3)))
    put(px, doc, component, target[0], target[1], top_only=TOP_ONLY)
    return target  # type: ignore[return-value]


# -- 7: a saved gear mate's ratio changed ------------------------------------------

RATIO_ASSEMBLY = "Probe W8 Ratio"
RATIO_NEW = 60          # the output gear's teeth after the change (made 51): a ratio no other state gives
RATIO_STEP = 30.0       # degrees each drive turns the input
RATIO_FIELDS = ("GearRatioNumerator", "GearRatioDenominator")
RATIO_ALONE = "the field holding the old count"
RATIO_AS_READ = "both fields, as GetDefinition read them"
RATIO_CROSSED = "both fields, the other way round"
# What gear_mate_definition (item 15, last in the tier) puts in the definition, each on a fresh copy of the train.
# The first run (2026, 34.1.1) tried RATIO_ALONE first: ModifyDefinition answered True, and the mate then read the two
# counts the other way round and turned the output 60/17 of its partner, not 17/60; RATIO_AS_READ did the same, and
# RATIO_CROSSED (the counts in AddMate5's order, though GetDefinition reads them reversed) gave 17/60. On 2024
# (32.5.0) an assembly whose gear mate ModifyDefinition had changed could not be closed: CloseDoc raised 0x80010105
# ("the server threw an exception") and from then on left it open without a word, holding the layout and the part
# with it (sw2024/probe-results-20261114-040636 and -051023). So the definition route is never chosen, and it runs
# last, where nothing else shares a session with what it strands.
RATIO_RECIPES = (RATIO_CROSSED, RATIO_ALONE, RATIO_AS_READ)


def ratio_fields(recipe: str, before: Mapping[str, Any], old: float, new: float) -> Dict[str, float]:
    """The fields a recipe puts, from the definition as read (``before``): the one holding ``old`` given ``new``
    alone; both, the other keeping its count; or both with the two counts the other way round. Empty when ``old``
    is not in exactly one field."""
    holding = [k for k in RATIO_FIELDS if isinstance(before.get(k), (int, float)) and abs(float(before[k]) - old) < 1e-9]
    if len(holding) != 1:
        return {}
    other = next(k for k in RATIO_FIELDS if k != holding[0])
    if recipe == RATIO_ALONE:
        return {holding[0]: float(new)}
    if recipe == RATIO_AS_READ:
        return {holding[0]: float(new), other: float(before[other])}
    if recipe == RATIO_CROSSED:
        return {holding[0]: float(before[other]), other: float(new)}
    raise ValueError(f"{recipe!r} is not one of the ways this probe knows to put a gear mate's ratio "
                     f"({', '.join(RATIO_RECIPES)}).")


def set_gear_ratio_by_definition(px: Px, doc: Any, name: str, recipe: str, old: float, new: float,
                                 access: bool = True) -> Dict[str, Any]:
    """``GetDefinition`` of a gear mate, the fields ``recipe`` names put, ``ModifyDefinition(data, doc, None)`` (the
    pattern of TWIST_REVERSE_ROUTE, ``AccessSelections`` first when ``access``); what each step answered."""
    feature = mate_feature(doc, name)
    out: Dict[str, Any] = {"recipe": recipe, "before": gear_mate_definition(px, doc, name), "access_selections": access}
    got, data = px.attempt(f"GetDefinition of {name} to change it", lambda: call(feature, "GetDefinition"))
    if not got or data is None:
        out["definition"] = None
        return out
    if access:
        got, value = px.attempt(f"AccessSelections(doc, None) on {name}'s definition",
                                lambda: call(data, "AccessSelections", doc, sc.null()))
        out["accessed"] = plain(value) if got else "raised"
    fields = ratio_fields(recipe, out["before"], old, new)
    out["fields"] = fields
    if not fields:
        return out
    out["put"] = all(px.attempt(f"IGearMateFeatureData.{k} = {v:g}", lambda k=k, v=v: setattr(data, k, v))[0]
                     for k, v in fields.items())
    got, modified = px.attempt(f"ModifyDefinition(data, doc, None) of {name}",
                               lambda: call(feature, "ModifyDefinition", data, doc, sc.null()))
    out["modified"] = plain(modified) if got else "raised"
    if access and out.get("accessed") is True and not (got and modified):
        ok, value = px.attempt(f"ReleaseSelectionAccess on {name}'s definition",
                               lambda: member(data, "ReleaseSelectionAccess")[0])
        out["released"] = plain(value) if ok else "raised"
    out["after"] = gear_mate_definition(px, doc, name)
    return out


def remake_gear_mate(px: Px, doc: Any, names: Mapping[str, str], name: str, first: str, second: str,
                     ratio: Tuple[float, float], new_name: str) -> Dict[str, Any]:
    """Delete a gear mate (MATE_DELETE_ROUTE) and make it again between the two components found by
    ``GetComponentByName``, at ``ratio`` with GEAR_MATE_FLIP, named ``new_name``; what happened."""
    enums = _enums(px)
    out: Dict[str, Any] = {"deleted_by": delete_mate(px, doc, name)}
    if not out["deleted_by"]:
        return out
    a, b = call(doc, "GetComponentByName", names[first]), call(doc, "GetComponentByName", names[second])
    picked = a is not None and b is not None and bool(select_in(px, doc, a, "Gear Axis", "AXIS", False)) and \
        bool(select_in(px, doc, b, "Gear Axis", "AXIS", True))
    out["selected"] = picked
    if not picked:
        return out
    out["made"] = add_mate(px, doc, f"{first}-{second} gear {ratio[0]:g}:{ratio[1]:g} made again", enums["gear"],
                           enums["closest"], flip=bool(findings.GEAR_MATE_FLIP), ratio=ratio)
    if out["made"]["name"]:
        out["name"] = _rename(px, mate_feature(doc, out["made"]["name"]), new_name)
        out["definition"] = gear_mate_definition(px, doc, out["name"])
    return out


def _close_quietly(px: Px, paths: Sequence[str]) -> List[str]:
    """``close_paths`` in a finally: a close that raises is noted, not raised, so it never hides the error that
    brought the probe there. Returns the titles still open (or every probe document, when the close raised)."""
    try:
        left = close_paths(px, paths)
    except Exception as exc:  # noqa: BLE001 - noted; the probe's own error, if any, is the one that matters
        from .comerr import one_line  # noqa: PLC0415
        px.note(f"CLEANUP closing raised {one_line(exc)}")
        return [os.path.basename(p) for p in paths]
    if left:
        px.note(f"CLEANUP still open after closing: {left}")
    return left


def _close_checked(px: Px, path: str, paths: Sequence[str]) -> Dict[str, Any]:
    """Close a copy and what it opened (``close_paths``), recording whether the copy itself closed: on SolidWorks 2024
    an assembly whose gear mate ModifyDefinition had changed could not be closed (CloseDoc raised 0x80010105, then
    left it open without a word), and the layout and part it uses then stay open with it."""
    try:
        left = close_paths(px, paths)
    except Exception as exc:  # noqa: BLE001 - the failure to close is the evidence
        from .comerr import one_line  # noqa: PLC0415
        px.note(f"CLEANUP closing {os.path.basename(path)} raised {one_line(exc)}")
        left = [t for t in sc.open_titles(px) if t == os.path.basename(path)]
        return {"closed": False, "raised": one_line(exc), "left": left}
    return {"closed": os.path.basename(path) not in left, "left": left}


def _ratio_turns_right(turns: Mapping[str, float], keys: Sequence[str], others: Sequence[str],
                       expected: Sequence[float], step: float = RATIO_STEP) -> bool:
    """The changed train turns at ``expected`` and the other train still 1/12."""
    return _train_ok(turns, keys, expected, step) and \
        _train_ok(turns, others, train_turns(TRAIN_TEETH, (1, 1, 1, 1)), step)


@probe("gear_mate_ratio", needs=("motion_update",), tier=8,
       members=("IAssemblyDoc.AddMate5 gear in a reopened assembly", "IModelDoc2.EditDelete", "IFeature.Name",
                "ISldWorks.CloseDoc"))
def gear_mate_ratio(px: Px) -> None:
    """A saved gear mate's ratio changed in the reopened train by deleting it and making it again (the remake), on a
    copy of its own: driven, saved, closed (whether it could be), reopened, driven again. The definition route runs
    in its own item, last in the tier (gear_mate_definition), since on 2024 it strands the assembly it changes."""
    info = px.shared.get("w8_train")
    px.require(bool(info), "mated_train left a train")
    t = info["trains"]["all Z+"]
    g1, g2, g3, g4 = t["gears"]
    keys = [g["key"] for g in t["gears"]]
    others = [g["key"] for g in info["trains"]["middle Z-"]["gears"]]
    name = info["mates"][f"{g3['key']}-{g4['key']}"]["name"]
    old_expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    new_expected = train_turns((g1["teeth"], g2["teeth"], g3["teeth"], RATIO_NEW), (1, 1, 1, 1))
    facts: Dict[str, Any] = {"mate": name, "teeth_before": list(TRAIN_TEETH), "expected_after": new_expected}
    _info, path = _train_copy(px, f"{RATIO_ASSEMBLY} Remake")
    paths = [path, info["layout"], info["part"]]
    current = name
    try:
        doc, components = _open_train(px, path, info["names"])
        facts["rebuild_on_open"] = rebuild(px, doc, "opened", top_only=TOP_ONLY)
        facts["turns_before"] = _drive_by(px, doc, components, RATIO_STEP, "driven before the change")
        facts["mates_before"] = mate_names(doc)
        facts["remake"] = remake_gear_mate(px, doc, info["names"], name, g3["key"], g4["key"],
                                           (float(g3["teeth"]), float(RATIO_NEW)), name)
        current = facts["remake"].get("name") or name
        facts["mates_after"] = mate_names(doc)
        facts["rebuild"] = rebuild(px, doc, "gear mate made again", top_only=TOP_ONLY)
        facts["errors"] = errors_only(mate_errors(px, doc))
        facts["turns"] = _drive_by(px, doc, components, RATIO_STEP, "driven after the remake")
        facts["right"] = bool(facts["remake"].get("name")) and not facts["errors"] and \
            _ratio_turns_right(facts["turns"], keys, others, new_expected) and \
            not _ratio_turns_right(facts["turns_before"], keys, others, new_expected)
        if facts["right"]:
            facts["saved"] = _save_in_place(px, doc, path, "the train with its remade gear mate")
    finally:
        facts["close"] = _close_checked(px, path, paths)
    reopened: Dict[str, Any] = {}
    if facts.get("saved") and facts["close"]["closed"]:
        try:
            doc, components = _open_train(px, path, info["names"])
            reopened["rebuild"] = rebuild(px, doc, "reopened", top_only=TOP_ONLY)
            reopened["definition"] = gear_mate_definition(px, doc, current)
            reopened["errors"] = errors_only(mate_errors(px, doc))
            reopened["turns"] = _drive_by(px, doc, components, RATIO_STEP, "driven after the reopen")
        finally:
            reopened["close"] = _close_checked(px, path, paths)
    facts["reopened"] = reopened
    px.fact("gear_mate_ratio", facts)

    # -- what it says
    before = facts.get("turns_before") or {}
    px.check(_train_ok(before, keys, old_expected, RATIO_STEP), f"before the change the train turns 1/12: {before}")
    px.check(bool(facts.get("right")), f"remade at {g3['teeth']} : {RATIO_NEW}, the output turned "
                                       f"{(facts.get('turns') or {}).get(keys[3])} for the input's 30 "
                                       f"({RATIO_STEP * new_expected[3]:.6f} wanted)")
    position = {"before": facts["mates_before"].index(name) if name in facts.get("mates_before", []) else None,
                "after": facts["mates_after"].index(current) if current in facts.get("mates_after", []) else None,
                "count": len(facts.get("mates_after", []))}
    px.fact("remade_mate_position", position, "where the remade gear mate sits in the mate group, before and after")
    kept = bool(reopened) and _ratio_turns_right(reopened["turns"], keys, others, new_expected) and \
        not reopened["errors"] and reopened["close"]["closed"]
    px.check(kept, f"saved, closed, reopened, closed: the new ratio holds: {reopened}")
    px.fact("gear_mate_ratio_route", "remake" if facts.get("right") and facts["close"]["closed"] and kept else None)


# -- 7b: the shape an Update needs for a tooth change (P1b, W5-DECISIONS "Rulings on package P0's findings") ----
#
# On real gears, built by the app's own assess, plan_gearbox and build_gearbox as assembly_rebuild_scope builds its
# gearbox, then mated here as W5-PLAN §1.2 makes a turning assembly (that code does not exist yet). The change is
# W4's 12 : 1 reducer's second stage taken from 17/51 to 18/50 teeth: the same centre distance (module 2, 68 mm), so
# no shaft moves and only the parts, the gear mate and the phases change.

UPDATE_TAG = "Probe W8 Update"
UPDATE_TEETH = {"G3": "18", "G4": "50"}
UPDATE_STEP = 30.0
UPDATE_DRIVE = "Update Drive"


def mesh_turns(gears: Sequence[str], locks: Sequence[Tuple[str, str]], meshes: Sequence[Tuple[str, str]],
               teeth: Mapping[str, int]) -> List[float]:
    """Each gear's turn about +Z per degree of the first, every shaft Z+: a lock turns its pair together and an
    external mesh turns its second gear ``-z_a / z_b`` of its first."""
    out: Dict[str, float] = {gears[0]: 1.0}
    for _ in range(len(gears)):
        for a, f in locks:
            for x, y in ((a, f), (f, a)):
                if x in out and y not in out:
                    out[y] = out[x]
        for a, b in meshes:
            if a in out and b not in out:
                out[b] = -out[a] * teeth[a] / teeth[b]
            elif b in out and a not in out:
                out[a] = -out[b] * teeth[b] / teeth[a]
    if set(out) != set(gears):
        raise ValueError(f"The meshes and locks do not reach every gear: {sorted(set(gears) - set(out))}")
    return [out[g] for g in gears]


@dataclass(frozen=True)
class UpdateFixture:
    """A gearbox P1b builds by the app, mates as W5 will and changes by an Update: its shafts (id, x, role), its
    gears (id, shaft, at, module, face width, bore), the teeth it is built with, the tooth change, and its W5 mates
    (anchors on their shafts, locks, gear mates). No shaft moves in the change: every centre distance holds."""
    tag: str
    folder: str
    shafts: Tuple[Tuple[str, str, str], ...]
    rows: Tuple[Tuple[str, str, str, str, str, str], ...]
    teeth: Tuple[Tuple[str, int], ...]
    change: Tuple[Tuple[str, str], ...]
    anchors: Tuple[Tuple[str, str], ...]
    locks: Tuple[Tuple[str, str], ...]
    meshes: Tuple[Tuple[str, str], ...]
    control: str = ""        # the gear the half-pitch control turns: one whose teeth change

    @property
    def gears(self) -> List[str]:
        return [r[0] for r in self.rows]

    def old_teeth(self) -> Dict[str, int]:
        return dict(self.teeth)

    def new_teeth(self, change: Optional[Mapping[str, str]] = None) -> Dict[str, int]:
        return {**dict(self.teeth), **{g: int(v) for g, v in dict(change or dict(self.change)).items()}}

    def remade(self, change: Optional[Mapping[str, str]] = None) -> List[Tuple[str, str]]:
        """The gear mates a tooth change remakes: every one with a changed gear in it."""
        changed = set(dict(change or dict(self.change)))
        return [(a, b) for a, b in self.meshes if a in changed or b in changed]

    def turns(self, teeth: Mapping[str, int]) -> List[float]:
        return mesh_turns(self.gears, self.locks, self.meshes, teeth)

    def spec(self, folder: str, teeth: Optional[Mapping[str, str]] = None) -> Any:
        from ..workbook.model import Box, Gear, GearboxSpec, Mesh, Shaft  # noqa: PLC0415

        t = {**{g: str(v) for g, v in self.teeth}, **dict(teeth or {})}
        return GearboxSpec(
            box=Box(name=self.tag, output_folder=folder.rstrip("\\/") + "\\"),
            shafts=tuple(Shaft(s, "frame", x, "0", "0", "Z+", role,
                               **({"speed": "1500", "torque": "10"} if role == "input" else {}))
                         for s, x, role in self.shafts),
            gears=tuple(Gear(g, s, at, "spur", "external", t[g], m, face_width=w, bore=b,
                             part_name=f"{self.tag} {g}") for g, s, at, m, w, b in self.rows),
            meshes=tuple(Mesh(a, b) for a, b in self.meshes))


#: W4's 12 : 1 reducer (tests/fixtures/excel-windows/Reducer_12to1.xlsx) with the probe's own part names: its second
#: stage 17/51 -> 18/50, the same centre distance (module 2, 68 mm), so only the parts, one gear mate and the phases
#: change. The W5 mates: anchors G1, G2, G4; G3 locked to G2; two gear mates (W5-PLAN §1.2, D12).
REDUCER = UpdateFixture(
    tag=UPDATE_TAG, folder="update",
    shafts=(("S1", "0", "input"), ("S2", "63.75", ""), ("S3", "131.75", "output")),
    rows=(("G1", "S1", "7.5", "1.5", "15", "8"), ("G2", "S2", "7.5", "1.5", "15", "12"),
          ("G3", "S2", "27", "2", "20", "12"), ("G4", "S3", "27", "2", "20", "16")),
    teeth=(("G1", 17), ("G2", 68), ("G3", 17), ("G4", 51)), change=tuple(UPDATE_TEETH.items()),
    anchors=(("G1", "S1"), ("G2", "S2"), ("G4", "S3")), locks=(("G2", "G3"),), meshes=(("G1", "G2"), ("G3", "G4")),
    control="G4")

#: A simple train with an idler: G2 sits in two gear mates and its teeth change, so both are remade. Module 2,
#: 17/30/40 -> 15/32/38: both centre distances (47 mm, 70 mm) hold, so no shaft moves; every gear takes new teeth
#: and a new phase. Each gear an anchor on its own shaft; no lock.
IDLER = UpdateFixture(
    tag="Probe W8 Idler", folder="idler",
    shafts=(("S1", "0", "input"), ("S2", "47", ""), ("S3", "117", "output")),
    rows=(("G1", "S1", "7.5", "2", "15", "8"), ("G2", "S2", "7.5", "2", "15", "10"),
          ("G3", "S3", "7.5", "2", "15", "12")),
    teeth=(("G1", 17), ("G2", 30), ("G3", 40)), change=(("G1", "15"), ("G2", "32"), ("G3", "38")),
    anchors=(("G1", "S1"), ("G2", "S2"), ("G3", "S3")), locks=(), meshes=(("G1", "G2"), ("G2", "G3")), control="G2")


def update_spec(folder: str, teeth: Optional[Mapping[str, str]] = None, fx: UpdateFixture = REDUCER) -> Any:
    """The fixture's gearbox spec (W4's 12 : 1 reducer unless told otherwise), with any gear's teeth given instead."""
    return fx.spec(folder, teeth)


def update_frames(folder: str, teeth: Optional[Mapping[str, str]] = None,
                  fx: UpdateFixture = REDUCER) -> Dict[str, Tuple[Matrix, Vec]]:
    """Each gear's built frame (``workbook.layout.frames``), as the probe's matrix and origin."""
    from ..workbook import assess as wb_assess, layout as wb_layout  # noqa: PLC0415
    from .p7_workbook import rows_matrix  # noqa: PLC0415

    spec = update_spec(folder, teeth, fx)
    assessed = wb_assess.assess(spec, [], spec.box.output_folder, "")
    if assessed.lay_out_refusal():
        raise Require(f"The update fixture does not lay out: {assessed.lay_out_refusal()}")
    return {g: (rows_matrix(f.rotation), tuple(f.at)) for g, f in wb_layout.frames(assessed.report).items()}


def frames_identity(matrix: Matrix) -> bool:
    """Whether a rotation is the identity: a Z+ gear at its built phase θ = 0, which the 90° drive starts from."""
    return rotation_error(matrix, crossed.rot_z(0.0)) < 1e-12


#: The W5 mates of the 12 : 1 reducer (W5-PLAN §1.2, D12): anchors G1, G2, G4; G3 locked to G2; two gear mates.
UPDATE_ANCHORS = REDUCER.anchors
UPDATE_LOCKS = REDUCER.locks
UPDATE_MESHES = REDUCER.meshes


def not_made(name: str, result: Mapping[str, Any]) -> str:
    """The sentence for a mate AddMate5 did not make."""
    return (f"{name} was not made: AddMate5 returned {result.get('returned')} with status {result.get('status')} "
            f"({result.get('status_name') or 'unnamed'}), and {len(result.get('made') or [])} new mates appeared.")


def mate_w5_train(px: Px, doc: Any, comps: Mapping[str, Any], layout: Any, frames: Mapping[str, Tuple[Matrix, Vec]],
                  teeth: Mapping[str, int], add: Callable[[str], int], fx: UpdateFixture = REDUCER) -> Dict[str, Any]:
    """Unfix and mate a static assembly (the 12 : 1 unless told otherwise) as W5 will: each anchor on its shaft's axis (AXIS_MATE_ROUTE) and
    along it (AXIAL_MATE_ROUTE, the distance on "<Gear> Face Z"), G3 locked to G2, each mesh a gear mate with
    GEAR_MATE_FLIP; every mate named as D12 says. What each AddMate5 answered, by name."""
    enums = _enums(px)
    made: Dict[str, Dict[str, Any]] = {}
    front = _plane_names(layout)[0]

    def named(result: Dict[str, Any], name: str) -> None:
        if result.get("name") is None:
            raise Require(not_made(name, result))
        _rename(px, mate_feature(doc, result["name"]), name)
        made[name] = result

    for gear, shaft in fx.anchors:
        px.require(unfix(px, doc, comps[gear]), f"{gear} floats")
        picked = select_in(px, doc, comps[gear], "Gear Axis", "AXIS", False) and \
            select_in(px, doc, layout, f"{shaft} Axis", "AXIS", True)
        px.require(bool(picked), f"{gear}'s axis and {shaft} Axis select")
        named(add_mate(px, doc, f"{gear} on {shaft} Axis", enums["coincident"], enums["closest"]),
              f"{gear} on {shaft} Axis")
        z = frames[gear][1][2]
        picked = bool(_select_origin(px, doc, comps[gear], append=False)) and \
            bool(select_in(px, doc, layout, front, "PLANE", True))
        px.require(picked, f"{gear}'s origin and the layout's Front select")
        if abs(z) < 1e-9:
            named(add_mate(px, doc, f"{gear} along {shaft}", enums["coincident"], enums["closest"]), f"{gear} along {shaft}")
        else:
            named(add_mate(px, doc, f"{gear} along {shaft}", enums["distance"], enums["closest"], flip=z < 0,
                           distance=abs(z)), f"{gear} along {shaft}")
            feature = mate_feature(doc, f"{gear} along {shaft}")
            match = [d for d in sc.dimensions_of(feature) if abs(float(call(d, "SystemValue")) - sc.m(abs(z))) < 1e-9]
            px.require(len(match) == 1 and add(f'"{gear} Face Z"= {abs(z):g}') >= 0 and
                       add(f'"{call(match[0], "Name")}@{gear} along {shaft}"= "{gear} Face Z"') >= 0,
                       f'{gear}\'s axial distance is linked to "{gear} Face Z"')
    for anchor, follower in fx.locks:
        px.require(unfix(px, doc, comps[follower]), f"{follower} floats")
        px.require(bool(select_components(px, doc, (comps[anchor], comps[follower]))), f"{anchor} and {follower} select")
        named(add_mate(px, doc, f"{follower} locked to {anchor}", enums["lock"], enums["closest"]),
              f"{follower} locked to {anchor}")
    for a, b in fx.meshes:
        picked = select_in(px, doc, comps[a], "Gear Axis", "AXIS", False) and \
            select_in(px, doc, comps[b], "Gear Axis", "AXIS", True)
        px.require(bool(picked), f"{a}'s and {b}'s axes select")
        named(add_mate(px, doc, f"{a} meshes {b}", enums["gear"], enums["closest"], flip=bool(findings.GEAR_MATE_FLIP),
                       ratio=(float(teeth[a]), float(teeth[b]))), f"{a} meshes {b}")
    return made


def mate_check(px: Px, doc: Any, comps: Mapping[str, Any], statuses: Mapping[str, Any] = ()) -> Dict[str, Any]:
    """W5-PLAN §1.4's mate check: every AddMate5 status, every mate's error code, every gear's constrained status."""
    return {"statuses": {n: r.get("status") for n, r in dict(statuses).items()},
            "errors": errors_only(mate_errors(px, doc)),
            "constrained": {k: constrained(px, c) for k, c in comps.items()}}


def mate_check_clean(check: Mapping[str, Any]) -> bool:
    return all(v == findings.ADD_MATE_NO_ERROR for v in check["statuses"].values()) and not check["errors"] and \
        all(v == findings.COMPONENT_UNDER_DEFINED for v in check["constrained"].values())


def _temporary_drive(px: Px, doc: Any, comps: Mapping[str, Any], layout: Any) -> Optional[str]:
    """The demonstration's drive (DEMONSTRATION_DRIVE_HOLDS): G1's Top plane to the layout's Right at 90°, its angle
    on the global UPDATE_DRIVE."""
    add = adder(px, call(doc, "GetEquationMgr"))
    if add(f'"{UPDATE_DRIVE}"= {DEMO_FROM:g}') < 0:
        return None
    return drive_mate(px, doc, comps["G1"], _plane_names(comps["G1"])[1], layout, _plane_names(layout)[2], "G1", add,
                      _enums(px)["closest"], angle=DEMO_FROM, global_name=UPDATE_DRIVE)


def _drop_drive(px: Px, doc: Any, drive: Optional[str]) -> Dict[str, Any]:
    """The temporary drive taken away: its global and link (IEquationMgr.Delete), then its mate (MATE_DELETE_ROUTE)."""
    eqm = call(doc, "GetEquationMgr")
    deleted = []
    for index in range(int(call(eqm, "GetCount")) - 1, -1, -1):
        if UPDATE_DRIVE in str(call(eqm, "Equation", index)):
            deleted.append(px.attempt(f"IEquationMgr.Delete({index})", lambda i=index: call(eqm, "Delete", i))[0])
    return {"equations_deleted": deleted, "mate_deleted_by": delete_mate(px, doc, drive) if drive else None}


def _drive_measure(px: Px, doc: Any, comps: Mapping[str, Any], layout: Any, built: Mapping[str, Tuple[Matrix, Vec]],
                   label: str) -> Dict[str, Any]:
    """Drive the train 30° by the temporary drive, read every turn, set it back, take it away; every frame then
    against ``built``."""
    out: Dict[str, Any] = {"drive": _temporary_drive(px, doc, comps, layout)}
    if not out["drive"]:
        return out
    rebuild(px, doc, f"{label}: drive added", top_only=TOP_ONLY)
    out["constrained_driven"] = {k: constrained(px, c) for k, c in comps.items()}
    out["turns"] = _drive_by(px, doc, comps, UPDATE_STEP, f"{label}: driven", global_name=UPDATE_DRIVE)
    _set_global(call(doc, "GetEquationMgr"), UPDATE_DRIVE, DEMO_FROM)
    rebuild(px, doc, f"{label}: drive set back", top_only=TOP_ONLY)
    out["dropped"] = _drop_drive(px, doc, out["drive"])
    rebuild(px, doc, f"{label}: drive taken away", top_only=TOP_ONLY)
    out["back_at_built"] = worst(_off(comps, built))
    return out


def _set_teeth(px: Px, swbuild: Any, jobs: Mapping[str, Any], gear: str, teeth: str) -> Dict[str, Any]:
    """A gear's tooth count changed through its part's globals by the app's swbuild.update_variables, in the part's
    own document (opened by path, activated), as Update SolidWorks changes a part."""
    from ..gears import KINDS  # noqa: PLC0415
    from .p7_workbook import _update_with, activate  # noqa: PLC0415

    job = jobs[gear]
    part, _ = open_by_path(px, job.path, prefer="OpenDoc6")
    px.require(activate(px, str(call(part, "GetTitle"))), f"{gear}'s part is active")
    kind = KINDS[job.spec.kind]
    wanted = job.spec.with_values(teeth=teeth)
    return _update_with(px, swbuild, job.path, kind.variables(wanted, kind.derive(wanted)))


def _teeth_global(px: Px, path: str) -> Optional[float]:
    from .p7_workbook import _doc_at, _global_value  # noqa: PLC0415
    doc = _doc_at(px, path)
    return None if doc is None else _global_value(call(doc, "GetEquationMgr"), "No. of Teeth")


def _unsuppress_all(px: Px, doc: Any, locks: Sequence[str]) -> Dict[str, Any]:
    """Every lock unsuppressed, each on its own, so one that cannot be found does not leave the others off."""
    out: Dict[str, Any] = {}
    for lock in locks:
        try:
            out[lock] = suppress(px, doc, lock, False)
        except Require as exc:
            out[lock] = f"not unsuppressed: {exc}"
    return out


def _update_pass(px: Px, swbuild: Any, doc: Any, asm_title: str, comps: Mapping[str, Any], layout: Any,
                 jobs: Mapping[str, Any], wanted: Mapping[str, Tuple[Matrix, Vec]],
                 compare_full: bool = False, fx: UpdateFixture = REDUCER,
                 change: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """One Update of the tooth change (the fixture's own, or ``change``), in the order W5-PLAN §1.6 and the rulings
    give: the parts' teeth through their globals; every lock suppressed; every gear mate with a changed gear deleted,
    made again at the new ratio and given its old name; an interference reading at the old frames (the control: a
    changed gear stands off its new phase there); every gear put to its new built frame; every lock unsuppressed (in
    a finally); a top-only rebuild; the mate check; the drive and interference at the built phase; and, with
    ``compare_full``, the frames after a full rebuild beside it (last, so nothing above is measured on what the full
    rebuild made)."""
    from .p4_interference import interferences  # noqa: PLC0415
    from .p7_workbook import activate  # noqa: PLC0415

    change = dict(change or dict(fx.change))
    new = fx.new_teeth(change)
    out: Dict[str, Any] = {"teeth": {g: _set_teeth(px, swbuild, jobs, g, t) for g, t in change.items()}}
    px.require(activate(px, asm_title), "the assembly is active again")
    locks = [f"{f} locked to {a}" for a, f in fx.locks]
    out["mates_before"] = mate_names(doc)
    try:
        out["suppressed_by"] = {lock: suppress(px, doc, lock, True) for lock in locks}
        out["rebuild_suppressed"] = rebuild(px, doc, "locks suppressed", top_only=TOP_ONLY)
        names = {k: str(call(c, "Name2")) for k, c in comps.items()}
        out["remakes"] = {}
        for a, b in fx.remade(change):
            name = f"{a} meshes {b}"
            out["remakes"][name] = remake_gear_mate(px, doc, names, name, a, b, (float(new[a]), float(new[b])), name)
        out["mates_after_remake"] = mate_names(doc)
        out["interference_before_put"] = interferences(px, doc, "at the old frames, before the put")
        if fx.control:
            # The second control: the control gear put half a pitch off its new built phase, which must clash
            # (the old frames need not: a phase that changed can still happen to clear). The puts below set it right.
            matrix, at = wanted[fx.control]
            half = 180.0 / float(new[fx.control])
            put(px, doc, comps[fx.control], crossed.multiply(matrix, crossed.rot_z(half)), at, top_only=TOP_ONLY)
            out["interference_half_pitch"] = interferences(px, doc, f"{fx.control} half a pitch off its built phase")
        for gear, (matrix, at) in wanted.items():
            put(px, doc, comps[gear], matrix, at, top_only=TOP_ONLY)
    finally:
        out["unsuppressed_by"] = _unsuppress_all(px, doc, locks)
    out["rebuild"] = rebuild(px, doc, "after the Update", top_only=TOP_ONLY)
    out["off_built"] = _off(comps, wanted)
    out["check"] = mate_check(px, doc, comps, {n: (r or {}).get("made") or {} for n, r in out["remakes"].items()})
    out["drive"] = _drive_measure(px, doc, comps, layout, wanted, "after the Update")
    out["interference"] = interferences(px, doc, "at the built phase after the Update")
    if compare_full:
        frames = _frames(comps)
        out["full_rebuild"] = rebuild(px, doc, "a full rebuild beside it", top_only=False)
        out["moved_by_the_full_rebuild"] = worst(_off(comps, frames))
    return out


STATIC_FOR_THE_PROBE = ("the probe gear_mate_update builds W4's static assembly and mates it itself, so this plan "
                       "is made static on purpose.")


def static_plan(px: Px, assessed: Any) -> Any:
    """``plan_gearbox`` of W4's static gearbox, whatever W5's planning would choose: once ``plan_gearbox`` plans a
    turning assembly when ``workbook.motion.motion_reason()`` is ``""`` (W5-INTERFACES, "workbook/motion.py"), the
    probe makes that reason a sentence while it plans, so the plan carries W4's static assembly (W5-PLAN D1's
    static-by-necessity case); without that module the plan is W4's anyway. A plan still carrying motion is refused
    with a sentence."""
    from ..workbook import gearbox as wb_gearbox  # noqa: PLC0415
    try:
        from ..workbook import motion as wb_motion  # noqa: PLC0415
    except ImportError:
        wb_motion = None
    original = getattr(wb_motion, "motion_reason", None) if wb_motion is not None else None
    if original is not None:
        wb_motion.motion_reason = lambda: STATIC_FOR_THE_PROBE
    try:
        plan = wb_gearbox.plan_gearbox(assessed, None)
    finally:
        if original is not None:
            wb_motion.motion_reason = original
    px.require(not plan.refusal, f"plan_gearbox plans it: {plan.refusal!r}")
    px.require(getattr(plan, "motion", None) is None,
               "the plan is W4's static assembly, which this probe mates itself (a plan with a turning assembly, "
               "though motion_reason said static, would need the probe taught the turning one)")
    px.fact("update_plan_static_reason", getattr(plan, "static_reason", ""))
    return plan


def update_turns(teeth: Mapping[str, int]) -> List[float]:
    """G1..G4's turns about +Z per degree of G1, every shaft Z+ and both meshes external."""
    return train_turns((teeth["G1"], teeth["G2"], teeth["G3"], teeth["G4"]), (1, 1, 1, 1))


def remakes_of(p: Mapping[str, Any]) -> Dict[str, Any]:
    """An Update pass's remade gear mates by name (P0b's files kept the one remake as ``remake``)."""
    if "remakes" in p:
        return dict(p["remakes"] or {})
    return {"G3 meshes G4": p["remake"]} if "remake" in p else {}


def update_pass_holds(p: Mapping[str, Any], teeth: Mapping[str, int], fx: UpdateFixture = REDUCER) -> bool:
    """An Update pass did what it must: the parts took their teeth, every remade gear mate kept its name, every gear
    stands at its new built frame after the rebuild, the mate check is clean, a full rebuild moves nothing, the
    drive turns the train at the new ratio in the right sense and returns every gear, and no gear interferes."""
    drive = p.get("drive") or {}
    turns = drive.get("turns") or {}
    remakes = remakes_of(p)
    wanted = [f"{a} meshes {b}" for a, b in fx.remade({g: str(v) for g, v in teeth.items()
                                                      if fx.old_teeth().get(g) != v} or None)]
    return bool(p["teeth"] and all(r.get("ok") and "No. of Teeth" in r.get("changed", []) for r in p["teeth"].values())
                and set(remakes) == set(wanted) and all((remakes[n] or {}).get("name") == n for n in wanted)
                and worst(p["off_built"]) < TOLERANCE_MM and mate_check_clean(p["check"])
                and p.get("moved_by_the_full_rebuild", 0.0) < TOLERANCE_MM and turns
                and _train_ok(turns, fx.gears, fx.turns(teeth), UPDATE_STEP)
                and drive.get("back_at_built", 1.0) < TOLERANCE_MM
                and (p.get("interference") or {}).get("count") == 0)


def remade_positions(p: Mapping[str, Any]) -> Dict[str, Any]:
    """Where each remade gear mate stood in the mate group before the Update and stands after it."""
    before, after = list(p.get("mates_before") or []), list(p.get("mates_after_remake") or [])
    return {n: [before.index(n) if n in before else None, after.index(n) if n in after else None, len(after)]
            for n in remakes_of(p)}


def interference_control(p: Mapping[str, Any]) -> Dict[str, Any]:
    """The interference reading at the old frames (before the put) beside the one at the new built phase."""
    return {"before_put": (p.get("interference_before_put") or {}).get("count"),
            "half_pitch": (p.get("interference_half_pitch") or {}).get("count"),
            "after": (p.get("interference") or {}).get("count")}


def run_update(px: Px, fx: UpdateFixture) -> Tuple[Dict[str, Any], Dict[str, bool]]:
    """P1b on a fixture: built by the app, mated as W5 will, saved; then the tooth change by the parts' globals,
    every gear mate with a changed gear remade under suppressed locks, every gear put to its built frame; checked,
    driven, interference; closed unsaved and reopened as it was saved; and again, saved, reopened, driven. Returns
    the facts and what held, step by step. Leaves the saved, updated train on disk (``px.shared["w8_" + folder]``)."""
    from .. import swbuild  # noqa: PLC0415
    from ..workbook import assess as wb_assess  # noqa: PLC0415
    from .p4_interference import interferences  # noqa: PLC0415
    from .p7_workbook import activate  # noqa: PLC0415

    folder = os.path.join(_folder(px), fx.folder)
    px.require(not os.path.exists(folder), f"{folder} does not exist yet")
    os.makedirs(folder)
    spec = update_spec(folder, fx=fx)
    assessed = wb_assess.assess(spec, [], spec.box.output_folder, "")
    px.require(assessed.lay_out_refusal() == "", f"{fx.tag} lays out: {assessed.lay_out_refusal()!r}")
    plan = static_plan(px, assessed)
    jobs = {job.gear_ids[0]: job for job in plan.build}
    px.require(sorted(jobs) == sorted(fx.gears), f"every gear of {fx.tag} is a part of its own: {sorted(jobs)}")
    paths = [plan.assembly_path, plan.layout_path] + [j.path for j in jobs.values()]
    change = dict(fx.change)
    built = update_frames(folder, fx=fx)
    wanted = update_frames(folder, change, fx=fx)
    px.require(frames_identity(built[fx.gears[0]][0]) and frames_identity(wanted[fx.gears[0]][0]),
               "the input stands at its built phase θ = 0, where the demonstration's 90° drive starts")
    old_teeth, new_teeth = fx.old_teeth(), fx.new_teeth()
    gears = fx.gears
    facts: Dict[str, Any] = {"teeth_before": old_teeth, "teeth_after": new_teeth,
                             "remade": [f"{a} meshes {b}" for a, b in fx.remade()]}
    before = sc.open_titles(px)
    try:
        try:
            result = swbuild.build_gearbox(px.session, **plan.build_kwargs())
        finally:
            made = [t for t in sc.open_titles(px) if t not in before]
            px.shared.setdefault("created", []).extend(t for t in made if t not in px.shared["created"])
        px.require(result.ok and not result.clashes, "build_gearbox built the parts, the layout and the static "
                   "assembly", {"failures": plain(result.failures), "clashes": plain(result.clashes)})
        names = {gear: result.components.get(handle, "") for handle, gear in plan.handles.items()}
        layout_name = result.components.get("layout", "")
        px.require(all(names.values()) and bool(layout_name), f"every component is named: {names} {layout_name}")
    finally:
        _close_quietly(px, paths)

    def open_train() -> Tuple[Any, Dict[str, Any], Any, str]:
        doc, _ = open_by_path(px, plan.assembly_path, sc.SW_DOC_ASSEMBLY, prefer="OpenDoc6")
        title = str(call(doc, "GetTitle"))
        if title not in px.shared["created"]:
            px.shared["created"].append(title)
        comps = {g: call(doc, "GetComponentByName", n) for g, n in names.items()}
        layout = call(doc, "GetComponentByName", layout_name)
        px.require(all(c is not None for c in comps.values()) and layout is not None, "every component is found")
        return doc, comps, layout, title

    px.shared[f"w8_{fx.folder}"] = {"fx": fx, "plan": plan, "jobs": jobs, "paths": paths, "names": names,
                                    "layout_name": layout_name, "built": built, "wanted": wanted,
                                    "open_train": open_train}
    first_remade = facts["remade"][0]
    try:
        # The static assembly mated as W5 will, checked, and saved: the turning train an Update finds.
        doc, comps, layout, title = open_train()
        px.require(not mate_names(doc), "build_gearbox made a static assembly, with no mates for the probe to "
                                        "double (a turning one would need the probe taught to mate nothing itself)")
        made = mate_w5_train(px, doc, comps, layout, built, old_teeth, adder(px, call(doc, "GetEquationMgr")), fx)
        facts["rebuild_mated"] = rebuild(px, doc, "mated", top_only=TOP_ONLY)
        facts["mated_off_built"] = worst(_off(comps, built))
        facts["mated_check"] = mate_check(px, doc, comps, made)
        facts["mated_drive"] = _drive_measure(px, doc, comps, layout, built, "as built")
        facts["mated_interference"] = interferences(px, doc, "at the built phase, mated")
        facts["mates_saved"] = mate_names(doc)
        facts["definitions_saved"] = {n: gear_mate_definition(px, doc, n) for n in facts["remade"]}
        facts["definition_saved"] = facts["definitions_saved"][first_remade]
        px.require(_save_in_place(px, doc, plan.assembly_path, "the mated train"), "the mated train saves")
    finally:
        _close_quietly(px, paths)

    # A: the Update, then closed WITHOUT saving the assembly. The parts are set back to their teeth first, since
    # closing saves the probe's modified parts (scaffold.save_created_parts, which keeps 2024 from asking).
    try:
        doc, comps, layout, title = open_train()
        saved_frames = _frames(comps)
        facts["unsaved"] = _update_pass(px, swbuild, doc, title, comps, layout, jobs, wanted, compare_full=True, fx=fx)
        facts["unsaved"]["teeth_back"] = {g: _set_teeth(px, swbuild, jobs, g, str(old_teeth[g])) for g in change}
        px.require(activate(px, title), "the assembly is active again")
    finally:
        facts.setdefault("unsaved", {})["left_open"] = _close_quietly(px, paths)
    try:
        doc, comps, layout, title = open_train()
        definitions = {n: gear_mate_definition(px, doc, n) for n in facts["remade"]}
        facts["unsaved"]["reopened"] = {
            "mates": mate_names(doc), "definitions": definitions, "definition": definitions[first_remade],
            "frames_off_saved": worst(_off(comps, saved_frames)),
            "teeth": {g: _teeth_global(px, jobs[g].path) for g in change},
            "errors": errors_only(mate_errors(px, doc))}
    finally:
        _close_quietly(px, paths)

    # B: the Update again, saved this time, reopened and driven.
    try:
        doc, comps, layout, title = open_train()
        facts["saved"] = _update_pass(px, swbuild, doc, title, comps, layout, jobs, wanted, fx=fx)
        px.require(activate(px, title), "the assembly is active again")
        facts["saved"]["saved"] = _save_in_place(px, doc, plan.assembly_path, "the updated train")
    finally:
        facts.setdefault("saved", {})["left_open"] = _close_quietly(px, paths)
    try:
        doc, comps, layout, title = open_train()
        definitions = {n: gear_mate_definition(px, doc, n) for n in facts["remade"]}
        r: Dict[str, Any] = {"mates": mate_names(doc), "definitions": definitions,
                             "definition": definitions[first_remade],
                             "teeth": {g: _teeth_global(px, jobs[g].path) for g in change}}
        r["rebuild"] = rebuild(px, doc, "reopened", top_only=TOP_ONLY)
        r["off_built"] = _off(comps, wanted)
        r["check"] = mate_check(px, doc, comps)
        r["drive"] = _drive_measure(px, doc, comps, layout, wanted, "reopened")
        r["interference"] = interferences(px, doc, "at the built phase, reopened")
        facts["saved"]["reopened"] = r
    finally:
        _close_quietly(px, paths)

    # -- what it says
    mated_ok = facts["mated_off_built"] < TOLERANCE_MM and mate_check_clean(facts["mated_check"]) and \
        _train_ok((facts["mated_drive"].get("turns") or {}), gears, fx.turns(old_teeth), UPDATE_STEP) and \
        facts["mated_interference"].get("count") == 0
    px.check(mated_ok, f"mated as W5 will, nothing moved ({facts['mated_off_built']:.1e}), the mate check is clean "
                       f"({facts['mated_check']}), it turns at its ratio ({facts['mated_drive'].get('turns')}) and "
                       f"nothing interferes ({facts['mated_interference'].get('count')})")
    a, b = facts["unsaved"], facts["saved"]
    for label, p in (("unsaved", a), ("saved", b)):
        px.check(update_pass_holds(p, new_teeth, fx),
                 f"{label}: the Update carried the tooth change: frames {worst(p['off_built']):.1e} off, check "
                 f"{p['check']}, full rebuild moved {p.get('moved_by_the_full_rebuild')}, turns "
                 f"{(p.get('drive') or {}).get('turns')}, interference {interference_control(p)}, remade mates "
                 f"(before, after, of) {remade_positions(p)}")
    ra = a.get("reopened") or {}
    as_saved = ra.get("mates") == facts["mates_saved"] and ra.get("definitions") == facts["definitions_saved"] and \
        ra.get("frames_off_saved", 1.0) < TOLERANCE_MM and not ra.get("errors") and \
        ra.get("teeth") == {g: float(old_teeth[g]) for g in change}
    px.check(as_saved and not a.get("left_open"), f"closed without saving and reopened, the train is as it was saved: {ra}")
    rb = b.get("reopened") or {}
    rdrive = rb.get("drive") or {}
    reopened_ok = bool(b.get("saved")) and not b.get("left_open") and \
        rb.get("teeth") == {g: float(v) for g, v in change.items()} and worst(rb.get("off_built") or {"x": {
            "rotation": 1.0, "origin_mm": 1.0}}) < TOLERANCE_MM and not rb["check"]["errors"] and \
        all(v == findings.COMPONENT_UNDER_DEFINED for v in rb["check"]["constrained"].values()) and \
        _train_ok(rdrive.get("turns") or {}, gears, fx.turns(new_teeth), UPDATE_STEP) and \
        (rb.get("interference") or {}).get("count") == 0
    px.check(reopened_ok, f"saved, reopened: the new teeth, the frames, a clean check, the new ratio and no "
                          f"interference: {rb}")
    control = {k: interference_control(p) for k, p in (("unsaved", a), ("saved", b))}
    px.check(True, f"the interference control: at the old frames, then at the new built phase: {control}")
    held = {"mated": bool(mated_ok), "unsaved": update_pass_holds(a, new_teeth, fx), "as_saved": bool(as_saved),
            "saved": update_pass_holds(b, new_teeth, fx), "reopened": bool(reopened_ok),
            "interference_control": all((c["half_pitch"] or 0) > 0 and c["after"] == 0 for c in control.values())}
    facts["interference_control"] = control
    return facts, held


@probe("gear_mate_update", needs=("motion_update", "end_to_end", "layout_assembly_reopen"), tier=8,
       members=("swbuild.build_gearbox", "swbuild.update_variables", "IAssemblyDoc.AddMate5", "IModelDoc2.EditDelete",
                "IFeature.SetSuppression2", "IComponent2.Transform2", "IAssemblyDoc.InterferenceDetectionManager"))
def gear_mate_update(px: Px) -> None:
    """A tooth change carried as an Update must carry it: the 12 : 1 reducer built by the app, mated as W5 will,
    saved; then G3 17 -> 18 and G4 51 -> 50 by the parts' globals, the gear mate remade under suppressed locks, every
    gear put to its built frame; checked, driven, interference (and a reading at the old frames before the put, the
    control); closed unsaved and reopened as it was saved; and again, saved, reopened, driven."""
    facts, held = run_update(px, REDUCER)
    px.fact("gear_mate_update", facts)
    b = facts["saved"]
    px.fact("remade_mate_moves_to_the_end", bool(b["mates_after_remake"]) and
            b["mates_after_remake"][-1] == "G3 meshes G4" and b["mates_before"][-1] != "G3 meshes G4")
    px.fact("update_interference_control", facts["interference_control"],
            "interference counts at the old frames before the put, and at the new built phase")
    px.fact("update_interference_control_discriminates", held["interference_control"])
    px.fact("gear_mate_update_holds", all(v for k, v in held.items() if k != "interference_control"))


@probe("idler_update", needs=("motion_update", "end_to_end", "layout_assembly_reopen"), tier=8,
       members=("swbuild.build_gearbox", "swbuild.update_variables", "IAssemblyDoc.AddMate5", "IModelDoc2.EditDelete",
                "IComponent2.Transform2", "IAssemblyDoc.InterferenceDetectionManager"))
def idler_update(px: Px) -> None:
    """P1b on a gear that carries two gear mates, in the whole Update shape: a train with an idler (17/30/40 -> 15/32/38,
    module 2, no shaft moves) built by the app and mated as W5 will; the idler's teeth change, so BOTH of its gear
    mates are remade; every gear put to its built frame; checked, driven, interference before and after the put;
    closed unsaved and reopened as saved; and again, saved, reopened, driven."""
    facts, held = run_update(px, IDLER)
    px.fact("idler_update", facts)
    px.fact("idler_update_steps", held)
    px.fact("idler_interference_control_discriminates", held["interference_control"])
    px.fact("idler_update_holds", all(v for k, v in held.items() if k != "interference_control"))


# -- 8: a lock re-taken after its gear moves along the shaft as well as round it ---

OFFSET_ASSEMBLY = "Probe W8 Offset"
OFFSET_ALONG = 3.0      # mm along its own axis the locked gear is put while its lock is suppressed
OFFSET_STEP = 30.0


@probe("lock_retake_offset", needs=("motion_update",), tier=8,
       members=("IFeature.SetSuppression2", "IComponent2.Transform2", "IAssemblyDoc.AddMate5 lock"))
def lock_retake_offset(px: Px) -> None:
    """Each compound lock suppressed, its second gear put 3 mm along its axis and 11° round, unsuppressed: kept through a drive?"""
    info, path = _train_copy(px, OFFSET_ASSEMBLY)
    paths = [path, info["layout"], info["part"]]
    facts: Dict[str, Any] = {"along_mm": OFFSET_ALONG, "turn": LOCK_TURN}
    cases: Dict[str, Dict[str, Any]] = {}
    try:
        doc, components = _open_train(px, path, info["names"])
        facts["rebuild_on_open"] = rebuild(px, doc, "opened", top_only=TOP_ONLY)
        pairs = {}
        for name, t in info["trains"].items():
            g2, g3 = t["gears"][1]["key"], t["gears"][2]["key"]
            pairs[name] = (g2, g3, info["mates"][f"{name} lock"])
            cases[name] = {"anchor": g2, "follower": g3, "lock": pairs[name][2], "sigma": t["gears"][1]["sigma"],
                           "before": relative_pose(frame_of(components[g2]), frame_of(components[g3]))}
        for name, (g2, g3, lock) in pairs.items():
            cases[name]["suppressed_by"] = suppress(px, doc, lock, True)
        facts["rebuild_suppressed"] = rebuild(px, doc, "locks suppressed", top_only=TOP_ONLY)
        for name, (g2, g3, lock) in pairs.items():
            target = _turned_put(px, doc, components[g3], LOCK_TURN, OFFSET_ALONG)
            cases[name]["put_read_back"] = worst(_off(components, {g3: target}))
            cases[name]["while_suppressed"] = pose_change(cases[name]["before"], relative_pose(
                frame_of(components[g2]), frame_of(components[g3])))
        for name, (g2, g3, lock) in pairs.items():
            cases[name]["unsuppressed_by"] = suppress(px, doc, lock, False)
        facts["rebuild_unsuppressed"] = rebuild(px, doc, "locks back on", top_only=TOP_ONLY)
        for name, (g2, g3, lock) in pairs.items():
            cases[name]["after_unsuppress"] = pose_change(cases[name]["before"], relative_pose(
                frame_of(components[g2]), frame_of(components[g3])))
        facts["errors_after_unsuppress"] = errors_only(mate_errors(px, doc))
        facts["turns"] = _drive_by(px, doc, components, OFFSET_STEP, "driven with the locks re-taken")
        for name, (g2, g3, lock) in pairs.items():
            cases[name]["after_drive"] = pose_change(cases[name]["before"], relative_pose(
                frame_of(components[g2]), frame_of(components[g3])))
            cases[name]["anchor_turned"] = facts["turns"][g2]
        facts["errors_after_drive"] = errors_only(mate_errors(px, doc))
        facts["constrained"] = {k: constrained(px, c) for k, c in components.items()}
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    facts["cases"] = cases
    px.fact("lock_retake_offset", facts)

    # -- what it says
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    held = {}
    for name, c in cases.items():
        put_held = c["put_read_back"] < TOLERANCE_MM and abs(c["while_suppressed"]["angle"] - LOCK_TURN) < 1e-6 and \
            abs(c["while_suppressed"]["along"] - OFFSET_ALONG) < TOLERANCE_MM
        px.check(put_held, f"{name}: the put moved {c['follower']} {OFFSET_ALONG:g} mm along and {LOCK_TURN:g}° round "
                           f"under the suppressed lock: {c['while_suppressed']}")
        moved = abs(c["anchor_turned"]) > 1.0     # the anchor turned, so the lock was tested under motion
        held[name] = bool(put_held and moved) and all(
            abs(c[k]["angle"] - LOCK_TURN) < 1e-6 and abs(c[k]["along"] - OFFSET_ALONG) < TOLERANCE_MM
            and c[k]["off_axis"] < TOLERANCE_MM and c[k]["axis_off"] < 1e-9 for k in ("after_unsuppress", "after_drive"))
        px.check(True, f"{name}: {c['follower']} against {c['anchor']} after the lock came back {c['after_unsuppress']}, "
                       f"after the anchor turned {c['anchor_turned']:g}°: {c['after_drive']}")
    px.fact("lock_offset_kept", held)
    turned = all(_train_ok(facts["turns"], [g["key"] for g in t["gears"]], expected, OFFSET_STEP)
                 for t in info["trains"].values())
    clean = not facts["errors_after_unsuppress"] and not facts["errors_after_drive"]
    px.check(turned, f"both trains still turn 1/12: {facts['turns']}")
    px.check(clean, f"no mate error: {facts['errors_after_unsuppress']} {facts['errors_after_drive']}")
    px.fact("lock_retakes_an_offset", all(held.values()) if turned and clean else None)


# -- 9: mates renamed by the names W5 gives them, found again after a reopen -------

RENAME_ASSEMBLY = "Probe W8 Rename"
RENAME_STEP = 20.0


def rename_plan(info: Mapping[str, Any]) -> List[Tuple[str, str, str]]:
    """``(kind, old name, new name)`` for the four kinds of mate Update finds by name (W5-PLAN D12) in the all-Z+
    train, then the other train's lock, which is suppressed before it is renamed."""
    t, u = info["trains"]["all Z+"], info["trains"]["middle Z-"]
    g2, g3, g4 = (g["key"] for g in t["gears"][1:])
    g4_shaft = t["gears"][3]["shaft"]
    axis, along = info["mates"][g4][:2]
    return [("lock", info["mates"]["all Z+ lock"], f"{g3} locked to {g2}"),
            ("gear", info["mates"][f"{g3}-{g4}"]["name"], f"{g3} meshes {g4}"),
            ("axis", axis, f"{g4} on {g4_shaft} Axis"),
            ("along", along, f"{g4} along {g4_shaft}"),
            ("suppressed lock", info["mates"]["middle Z- lock"],
             f"{u['gears'][2]['key']} locked to {u['gears'][1]['key']}")]


def rename_mate(px: Px, doc: Any, old: str, new: str) -> Dict[str, Any]:
    """``IFeature.Name`` put on a mate found by its old name; what reads back."""
    feature = mate_feature(doc, old)
    got, _ = px.attempt(f"IFeature.Name = {new!r} on {old}", lambda: setattr(feature, "Name", new))
    return {"put": got, "reads": str(call(feature, "Name"))}


def find_mate_by(px: Px, doc: Any, name: str) -> Dict[str, Any]:
    """A mate looked for by name: through the MateGroup's sub-features, and by ``IModelDoc2.FeatureByName``."""
    out: Dict[str, Any] = {}
    try:
        out["mate group"] = str(call(mate_feature(doc, name), "Name")) == name
    except Require:
        out["mate group"] = False
    got, feature = px.attempt(f"FeatureByName({name!r})", lambda: call(doc, "FeatureByName", name))
    out["FeatureByName"] = bool(got and feature is not None and str(call(feature, "Name")) == name)
    return out


@probe("lock_mate_rename", needs=("motion_update",), tier=8,
       members=("IFeature.Name", "IModelDoc2.FeatureByName", "IFeature.IsSuppressed2", "IMate2.Type"))
def lock_mate_rename(px: Px) -> None:
    """A lock, a gear mate, an axis mate and an axial mate renamed as W5 names them, saved, reopened, found by name."""
    info, path = _train_copy(px, RENAME_ASSEMBLY)
    paths = [path, info["layout"], info["part"]]
    plan = rename_plan(info)
    t, u = info["trains"]["all Z+"], info["trains"]["middle Z-"]
    keys = [g["key"] for g in t["gears"]]
    facts: Dict[str, Any] = {"plan": [list(p) for p in plan]}
    try:
        doc, components = _open_train(px, path, info["names"])
        facts["rebuild_on_open"] = rebuild(px, doc, "opened", top_only=TOP_ONLY)
        suppressed_old = plan[-1][1]
        facts["suppressed_by"] = suppress(px, doc, suppressed_old, True)
        facts["rebuild_suppressed"] = rebuild(px, doc, "the other lock suppressed", top_only=TOP_ONLY)
        frames = _frames(components)
        states = mate_states(px, doc)
        facts["states_before"] = states
        facts["renamed"] = {old: rename_mate(px, doc, old, new) for _kind, old, new in plan}
        renamed_states = mate_states(px, doc)
        facts["states_after_rename"] = renamed_states
        facts["moved_by_the_rename"] = worst(_off(components, frames))
        facts["rebuild_after_rename"] = rebuild(px, doc, "renamed", top_only=TOP_ONLY)
        facts["moved_by_the_rebuild"] = worst(_off(components, frames))
        old_to_new = {old: new for _kind, old, new in plan}
        facts["states_kept"] = all(
            renamed_states.get(old_to_new.get(n, n), {}).get(k) == s.get(k) for n, s in states.items()
            for k in ("type", "suppressed", "code"))
        px.require(_save_in_place(px, doc, path, "the renamed train") and os.path.isfile(path), "the renamed train saves")
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")

    reopened: Dict[str, Any] = {}
    try:
        doc, components = _open_train(px, path, info["names"])
        reopened["rebuild"] = rebuild(px, doc, "reopened", top_only=TOP_ONLY)
        names_now = mate_names(doc)
        reopened["mates"] = names_now
        reopened["found"] = {new: find_mate_by(px, doc, new) for _kind, _old, new in plan}
        reopened["old_gone"] = {old: old not in names_now for _kind, old, _new in plan}
        reopened["kinds"] = {new: mate_entities(px, doc, new) for _kind, _old, new in plan}
        reopened["states"] = {new: mate_states(px, doc).get(new) for _kind, _old, new in plan}
        reopened["errors"] = errors_only(mate_errors(px, doc))
        frames = _frames(components)
        g2, g3, g4 = keys[1], keys[2], keys[3]
        pose = relative_pose(frames[g2], frames[g3])
        reopened["turns"] = _drive_by(px, doc, components, RENAME_STEP, "driven after the reopen")
        reopened["lock_change"] = pose_change(pose, relative_pose(frame_of(components[g2]), frame_of(components[g3])))
        m4, o4 = frame_of(components[g4])
        reopened["output_moved_along_mm"] = round(o4[2] - frames[g4][1][2], 9)
        reopened["output_off_axis_mm"] = round(math.hypot(o4[0] - frames[g4][1][0], o4[1] - frames[g4][1][1]), 9)
        reopened["errors_after_drive"] = errors_only(mate_errors(px, doc))
        # The renamed suppressed lock turned back on by its new name, and it holds.
        new_lock = plan[-1][2]
        reopened["unsuppressed_by"] = suppress(px, doc, new_lock, False)
        rebuild(px, doc, "the other lock back on", top_only=TOP_ONLY)
        u2, u3 = u["gears"][1]["key"], u["gears"][2]["key"]
        pose = relative_pose(frame_of(components[u2]), frame_of(components[u3]))
        reopened["turns_again"] = _drive_by(px, doc, components, RENAME_STEP, "driven with the other lock on")
        reopened["other_lock_change"] = pose_change(pose, relative_pose(frame_of(components[u2]),
                                                                        frame_of(components[u3])))
        reopened["errors_at_end"] = errors_only(mate_errors(px, doc))
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    facts["reopened"] = reopened
    px.fact("lock_mate_rename", facts)

    # -- what it says
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    named = all(r["put"] and r["reads"] == new for (_k, old, new), r in zip(plan, facts["renamed"].values()))
    px.check(named, f"every mate takes its new name: {facts['renamed']}")
    quiet = facts["states_kept"] and facts["moved_by_the_rename"] < 1e-9 and facts["moved_by_the_rebuild"] < TOLERANCE_MM
    px.check(quiet, f"renaming moved nothing ({facts['moved_by_the_rename']:.1e}, after a rebuild "
                    f"{facts['moved_by_the_rebuild']:.1e}) and suppressed or unsuppressed nothing: {facts['states_kept']}")
    found = {route: all(f[route] for f in reopened["found"].values()) for route in ("mate group", "FeatureByName")}
    px.fact("mate_find_routes", found)
    gone = all(reopened["old_gone"].values())
    px.check(any(found.values()) and gone, f"reopened, every mate is found by its new name ({found}) and no old "
                                           f"name is left: {reopened['old_gone']}")
    types = {new: (reopened["kinds"][new] or {}).get("type") for _k, _o, new in plan}
    wanted_types = {"lock": findings.MATE_LOCK, "gear": findings.MATE_GEAR, "axis": findings.MATE_COINCIDENT,
                    "along": findings.MATE_DISTANCE, "suppressed lock": findings.MATE_LOCK}
    kinds_kept = all(types[new] == wanted_types[kind] for kind, _o, new in plan)
    px.check(kinds_kept, f"each is still the kind of mate it was: {types}")
    still_suppressed = (reopened["states"].get(plan[-1][2]) or {}).get("suppressed") is True and \
        all((reopened["states"].get(new) or {}).get("suppressed") is False for _k, _o, new in plan[:-1])
    px.check(still_suppressed, f"the renamed suppressed lock is still suppressed, the others are not: {reopened['states']}")
    turns = reopened["turns"]
    lock = reopened["lock_change"]
    holds = _train_ok(turns, keys, expected, RENAME_STEP) and abs(lock["angle"]) < 1e-6 and \
        abs(lock["along"]) < TOLERANCE_MM and abs(turns[keys[1]]) > 1.0 and \
        abs(reopened["output_moved_along_mm"]) < TOLERANCE_MM and reopened["output_off_axis_mm"] < TOLERANCE_MM
    px.check(holds, f"driven, the renamed lock holds {keys[2]} to {keys[1]} ({lock}), the renamed gear mate turns "
                    f"the output 1/12 ({[turns[k] for k in keys]}), and the renamed axis and axial mates hold it")
    other = reopened["other_lock_change"]
    other_holds = abs(other["angle"]) < 1e-6 and abs(other["along"]) < TOLERANCE_MM and \
        abs(reopened["turns_again"][u["gears"][1]["key"]]) > 1.0
    px.check(other_holds, f"the other lock, turned back on by its new name, holds: {other}")
    clean = not reopened["errors"] and not reopened["errors_after_drive"] and not reopened["errors_at_end"]
    px.check(clean, f"no mate error after the reopen: {reopened['errors']} {reopened['errors_after_drive']} "
                    f"{reopened['errors_at_end']}")
    works = named and quiet and any(found.values()) and gone and kinds_kept and still_suppressed and holds and \
        other_holds and clean
    px.fact("mate_rename_route", "IFeature.Name put" if works else None)


# -- 10: the drive W5's demonstration plans: Top plane to the layout's Right, 90° -> 120° --

DEMO_ASSEMBLY = "Probe W8 Demo"
DEMO_GLOBAL = "Demo Drive"
DEMO_FROM, DEMO_TO = 90.0, 120.0


@probe("demonstration_drive", needs=("motion_update",), tier=8,
       members=("IAssemblyDoc.AddMate5 angle", "IEquationMgr.Add2", "IEquationMgr.Delete", "IModelDoc2.EditDelete",
                "IComponent2.Transform2"))
def demonstration_drive(px: Px) -> None:
    """Each input put at its built phase (θ = 0), driven by an angle mate from its Top plane to the layout's Right at
    90°, 90 -> 120 -> 90; the drive deleted; every frame back where it was built."""
    enums = _enums(px)
    info, path = _train_copy(px, DEMO_ASSEMBLY)
    paths = [path, info["layout"], info["part"]]
    facts: Dict[str, Any] = {"from": DEMO_FROM, "to": DEMO_TO}
    drives: Dict[str, Optional[str]] = {}
    try:
        doc, components = _open_train(px, path, info["names"])
        facts["rebuild_on_open"] = rebuild(px, doc, "opened", top_only=TOP_ONLY)
        facts["old_drives_suppressed_by"] = {name: suppress(px, doc, f"{DRIVE} {name}", True) for name in info["trains"]}
        facts["rebuild_undriven"] = rebuild(px, doc, "tier 8's drives suppressed", top_only=TOP_ONLY)
        built: Dict[str, Tuple[Matrix, Vec]] = {}
        for name, t in info["trains"].items():
            g1 = t["gears"][0]
            _m, o = frame_of(components[g1["key"]])
            put(px, doc, components[g1["key"]], w4_rotation(g1["sigma"], 0.0), o, top_only=TOP_ONLY)
            built[g1["key"]] = (w4_rotation(g1["sigma"], 0.0), o)
        facts["input_at_phase_zero"] = worst(_off(components, built))
        built = _frames(components)
        facts["constrained_undriven"] = {k: constrained(px, c) for k, c in components.items()}
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add(f'"{DEMO_GLOBAL}"= {DEMO_FROM:g}') >= 0, f'the global "{DEMO_GLOBAL}" is added')
        layout = call(doc, "GetComponentByName", info["layout_name"])
        px.require(layout is not None, "the layout component is found by name")
        layout_right = _plane_names(layout)[2]
        for name, t in info["trains"].items():
            g1 = components[t["gears"][0]["key"]]
            drives[name] = drive_mate(px, doc, g1, _plane_names(g1)[1], layout, layout_right, name, add,
                                      enums["closest"], angle=DEMO_FROM, global_name=DEMO_GLOBAL)
        facts["drives"] = drives
        px.require(all(drives.values()), f"each input's Top plane is held at {DEMO_FROM:g}° to the layout's Right")
        facts["rebuild_driven"] = rebuild(px, doc, "demonstration drive added", top_only=TOP_ONLY)
        facts["moved_by_the_drive"] = _off(components, built)
        facts["errors_driven"] = errors_only(mate_errors(px, doc))
        facts["constrained_driven"] = {k: constrained(px, c) for k, c in components.items()}
        facts["entities"] = {name: mate_entities(px, doc, d) for name, d in drives.items() if d}
        facts["turns"] = _drive_by(px, doc, components, DEMO_TO - DEMO_FROM, f"demonstration drive {DEMO_TO:g}",
                                   global_name=DEMO_GLOBAL)
        facts["errors_turned"] = errors_only(mate_errors(px, doc))
        _set_global(eqm, DEMO_GLOBAL, DEMO_FROM)
        facts["rebuild_back"] = rebuild(px, doc, f"demonstration drive back to {DEMO_FROM:g}", top_only=TOP_ONLY)
        facts["back_at_start"] = _off(components, built)
        # Taken away as the demonstration will: the link and the global (IEquationMgr.Delete), then the angle mates.
        deleted = []
        for index in range(int(call(eqm, "GetCount")) - 1, -1, -1):
            text = str(call(eqm, "Equation", index))
            if DEMO_GLOBAL in text:
                got, _ = px.attempt(f"IEquationMgr.Delete({index}) of {text}", lambda i=index: call(eqm, "Delete", i))
                deleted.append({"equation": text, "deleted": got})
        facts["equations_deleted"] = deleted
        facts["equations_left"] = [str(call(eqm, "Equation", i)) for i in range(int(call(eqm, "GetCount")))]
        facts["drive_deleted_by"] = {name: delete_mate(px, doc, d) for name, d in drives.items() if d}
        facts["rebuild_deleted"] = rebuild(px, doc, "demonstration drive deleted", top_only=TOP_ONLY)
        facts["after_delete"] = _off(components, built)
        facts["mates_left"] = mate_names(doc)
        facts["errors_after_delete"] = errors_only(mate_errors(px, doc))
        facts["constrained_after_delete"] = {k: constrained(px, c) for k, c in components.items()}
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.fact("demonstration_drive", facts)

    # -- what it says
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    step = DEMO_TO - DEMO_FROM
    px.check(facts["input_at_phase_zero"] < TOLERANCE_ROTATION, f"each input put at θ = 0: {facts['input_at_phase_zero']}")
    jump = worst(facts["moved_by_the_drive"])
    px.check(jump < TOLERANCE_MM, f"no gear moved when the 90° drive was added (largest {jump:.1e})")
    full = all(v == findings.COMPONENT_FULLY_DEFINED for v in facts["constrained_driven"].values())
    px.check(full, f"the drive makes every gear fully defined: {facts['constrained_driven']}")
    right = {}
    for name, t in info["trains"].items():
        keys = [g["key"] for g in t["gears"]]
        right[name] = _train_ok(facts["turns"], keys, expected, step)
        px.check(right[name], f"{name}: {DEMO_FROM:g} -> {DEMO_TO:g} turned the input {facts['turns'][keys[0]]:.6f}° "
                              f"and the output {facts['turns'][keys[3]]:.6f}° (1/12 the same way wanted)")
    sense = {name: (1 if facts["turns"][t["gears"][0]["key"]] > 0 else -1) for name, t in info["trains"].items()}
    px.fact("demonstration_drive_sense", sense, "the input's turn about +Z when the drive's angle grows")
    back = worst(facts["back_at_start"])
    after = worst(facts["after_delete"])
    px.check(back < TOLERANCE_MM, f"set back to {DEMO_FROM:g}, every gear is where it was built (largest {back:.1e})")
    px.check(after < TOLERANCE_MM, f"the drive deleted, every gear is still there (largest {after:.1e})")
    gone = not any(DEMO_GLOBAL in e for e in facts["equations_left"]) and \
        not any(d and d in facts["mates_left"] for d in drives.values())
    px.check(gone, f"no demonstration equation or mate is left: {facts['equations_left']}")
    clean = not facts["errors_driven"] and not facts["errors_turned"] and not facts["errors_after_delete"]
    px.check(clean, f"no mate error: {facts['errors_driven']} {facts['errors_turned']} {facts['errors_after_delete']}")
    free = all(v == findings.COMPONENT_UNDER_DEFINED for v in facts["constrained_after_delete"].values())
    px.check(free, f"the drive deleted, every gear is under-defined again: {facts['constrained_after_delete']}")
    px.fact("demonstration_drive_holds", bool(jump < TOLERANCE_MM and full and all(right.values()) and back < TOLERANCE_MM
                                              and after < TOLERANCE_MM and gone and clean and free))



# -- 11: a put, in an undriven train, on a gear in two gear mates' paths ------------

TWICE_ASSEMBLY = "Probe W8 Twice"
TWICE_TURN = 7.0         # degrees the compound shaft's anchor is put round
TWICE_BRIDGE_TURN = 9.0  # degrees the gear carrying two gear mates is put round
TWICE_STEP = 10.0


def _locks(info: Mapping[str, Any]) -> List[str]:
    return [info["mates"][f"{name} lock"] for name in info["trains"]]


def _put_under_suppressed_locks(px: Px, doc: Any, components: Mapping[str, Any], locks: Sequence[str],
                                puts: Mapping[str, Tuple[Matrix, Sequence[float]]]) -> Dict[str, Any]:
    """W5-PLAN §1.6 step 6: every lock suppressed, a rebuild, each put, every lock unsuppressed, a rebuild. What
    each frame read straight after the puts (not a verdict: the put's own call) and after the last rebuild."""
    out: Dict[str, Any] = {"suppressed_by": {lock: suppress(px, doc, lock, True) for lock in locks}}
    out["rebuild_suppressed"] = rebuild(px, doc, "locks suppressed", top_only=TOP_ONLY)
    for key, (matrix, at) in puts.items():
        put(px, doc, components[key], matrix, at, top_only=TOP_ONLY)
    out["read_after_the_puts"] = worst(_off(components, puts))
    out["unsuppressed_by"] = {lock: suppress(px, doc, lock, False) for lock in locks}
    out["rebuild_unsuppressed"] = rebuild(px, doc, "locks back on", top_only=TOP_ONLY)
    out["off_after_the_locks"] = _off(components, puts)
    out["errors"] = errors_only(mate_errors(px, doc))
    out["constrained"] = {k: constrained(px, c) for k, c in components.items()}
    return out


@probe("put_on_twice_meshed_gear", needs=("motion_update",), tier=8,
       members=("IComponent2.Transform2", "IFeature.SetSuppression2", "IAssemblyDoc.AddMate5 gear",
                "IComponent2.GetConstrainedStatus"))
def put_on_twice_meshed_gear(px: Px) -> None:
    """In the undriven train, locks suppressed around each put: the compound anchor put round, every gear put back,
    and a gear that carries two gear mates put round; does each put hold, and what do its neighbours do?"""
    enums = _enums(px)
    info, path = _train_copy(px, TWICE_ASSEMBLY)
    paths = [path, info["layout"], info["part"]]
    t, u = info["trains"]["all Z+"], info["trains"]["middle Z-"]
    tk, uk = [g["key"] for g in t["gears"]], [g["key"] for g in u["gears"]]
    locks = _locks(info)
    facts: Dict[str, Any] = {}
    try:
        doc, components = _open_train(px, path, info["names"])
        facts["rebuild_on_open"] = rebuild(px, doc, "opened", top_only=TOP_ONLY)
        facts["drives_suppressed_by"] = {name: suppress(px, doc, f"{DRIVE} {name}", True) for name in info["trains"]}
        facts["rebuild_undriven"] = rebuild(px, doc, "undriven", top_only=TOP_ONLY)
        facts["constrained_undriven"] = {k: constrained(px, c) for k, c in components.items()}
        start = _frames(components)

        # (a) the compound shaft's anchor, in a gear mate itself and locked to a gear in another: put round.
        anchor = tk[1]
        m, o = start[anchor]
        target = (crossed.multiply(m, crossed.rot_z(TWICE_TURN)), o)
        a = _put_under_suppressed_locks(px, doc, components, locks, {anchor: target})
        a["turns"] = _world_turns(components, start)
        a["lock_change"] = pose_change(relative_pose(start[anchor], start[tk[2]]),
                                       relative_pose(frame_of(components[anchor]), frame_of(components[tk[2]])))
        facts["anchor_put"] = a

        # (b) every gear put back where it started (the restore Update makes), the locks suppressed around it.
        facts["restore"] = _put_under_suppressed_locks(px, doc, components, locks, start)

        # (c) the anchor put round again with its lock ON, recorded beside (a): what a lock does to a put.
        put(px, doc, components[anchor], target[0], target[1], top_only=TOP_ONLY)
        rebuild(px, doc, "put with the lock on", top_only=TOP_ONLY)
        facts["lock_on_put"] = {"turns": _world_turns(components, start),
                                "anchor_off": _off(components, {anchor: target})[anchor],
                                "errors": errors_only(mate_errors(px, doc))}
        # Then driven (the train's own drive turned back on): what the lock does on its next solve after the put.
        pose = relative_pose(frame_of(components[anchor]), frame_of(components[tk[2]]))
        from .p7_workbook import _global_value  # noqa: PLC0415
        drive_value = _global_value(call(doc, "GetEquationMgr"), DRIVE)
        facts["lock_on_put"]["drive_unsuppressed_by"] = suppress(px, doc, f"{DRIVE} all Z+", False)
        rebuild(px, doc, "driven again after the put with the lock on", top_only=TOP_ONLY)
        facts["lock_on_put"]["after_drive_on"] = pose_change(pose, relative_pose(frame_of(components[anchor]),
                                                                                 frame_of(components[tk[2]])))
        facts["lock_on_put"]["drive_turns"] = _drive_by(px, doc, components, TWICE_STEP, "driven after the put")
        facts["lock_on_put"]["after_drive"] = pose_change(pose, relative_pose(frame_of(components[anchor]),
                                                                              frame_of(components[tk[2]])))
        facts["lock_on_put"]["errors_after_drive"] = errors_only(mate_errors(px, doc))
        # The drive set back where it was before it is suppressed, so turning it on again in (d) moves nothing.
        _set_global(call(doc, "GetEquationMgr"), DRIVE, drive_value)
        rebuild(px, doc, "drive set back", top_only=TOP_ONLY)
        facts["lock_on_put"]["drive_suppressed_by"] = suppress(px, doc, f"{DRIVE} all Z+", True)
        rebuild(px, doc, "undriven again", top_only=TOP_ONLY)
        facts["restore_again"] = _put_under_suppressed_locks(px, doc, components, locks, start)

        # (d) a gear carrying two gear mates: the first train's output joined to the second's input by one more.
        picked = select_in(px, doc, components[tk[3]], "Gear Axis", "AXIS", False) and \
            select_in(px, doc, components[uk[0]], "Gear Axis", "AXIS", True)
        px.require(bool(picked), f"{tk[3]} and {uk[0]}'s axes select")
        bridge = add_mate(px, doc, f"{tk[3]}-{uk[0]} gear {t['gears'][3]['teeth']}:{u['gears'][0]['teeth']}",
                          enums["gear"], enums["closest"], flip=bool(findings.GEAR_MATE_FLIP),
                          ratio=(float(t["gears"][3]["teeth"]), float(u["gears"][0]["teeth"])))
        px.require(bridge["name"] is not None, f"the joining gear mate is made: {bridge}")
        facts["bridge"] = bridge
        facts["rebuild_joined"] = rebuild(px, doc, "joined", top_only=TOP_ONLY)
        facts["moved_by_joining"] = worst(_off(components, start))
        facts["errors_joined"] = errors_only(mate_errors(px, doc))
        facts["constrained_joined"] = {k: constrained(px, c) for k, c in components.items()}
        twice = tk[3]
        m, o = start[twice]
        target = (crossed.multiply(m, crossed.rot_z(TWICE_BRIDGE_TURN)), o)
        d = _put_under_suppressed_locks(px, doc, components, locks, {twice: target})
        d["turns"] = _world_turns(components, start)
        facts["two_gear_mates_put"] = d
        # Driven through the one input left: the joined train turns as one, from the new phase.
        before_drive = _frames(components)
        facts["drive_unsuppressed_by"] = suppress(px, doc, f"{DRIVE} all Z+", False)
        facts["rebuild_driven"] = rebuild(px, doc, "driven", top_only=TOP_ONLY)
        facts["moved_by_the_drive_coming_back"] = worst(_off(components, before_drive))
        facts["constrained_driven"] = {k: constrained(px, c) for k, c in components.items()}
        facts["joined_turns"] = _drive_by(px, doc, components, TWICE_STEP, "the joined train driven")
        facts["errors_driven"] = errors_only(mate_errors(px, doc))

        # (e) the remake on the gear carrying two gear mates: TG3-TG4 deleted and made again at 17 : 60 under
        # suppressed locks, given its old name; where it lands in the mate group; the joined train driven again.
        old = info["mates"][f"{tk[2]}-{tk[3]}"]["name"]
        e: Dict[str, Any] = {"mates_before": mate_names(doc)}
        try:
            e["suppressed_by"] = {lock: suppress(px, doc, lock, True) for lock in locks}
            e["remake"] = remake_gear_mate(px, doc, info["names"], old, tk[2], tk[3],
                                           (float(t["gears"][2]["teeth"]), float(RATIO_NEW)), old)
        finally:
            e["unsuppressed_by"] = {lock: suppress(px, doc, lock, False) for lock in locks}
        e["mates_after"] = mate_names(doc)
        e["rebuild"] = rebuild(px, doc, "remade on the twice-meshed gear", top_only=TOP_ONLY)
        e["errors"] = errors_only(mate_errors(px, doc))
        e["found_by_name"] = {n: find_mate_by(px, doc, n) for n in (old, bridge["name"])}
        e["turns"] = _drive_by(px, doc, components, TWICE_STEP, "the joined train driven after the remake")
        facts["remake_on_twice_meshed"] = e
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    px.fact("put_on_twice_meshed_gear", facts)

    # -- what it says
    def held(case: Mapping[str, Any], key: str, others: Sequence[str]) -> bool:
        """Its put held after the locks came back and the rebuild, its neighbours did not turn, no mate error, and
        every gear is still under-defined."""
        off = case["off_after_the_locks"][key]
        still = all(abs(case["turns"][k]) < 1e-6 for k in others)
        free = all(v == findings.COMPONENT_UNDER_DEFINED for v in case["constrained"].values())
        return off["rotation"] < TOLERANCE_ROTATION and off["origin_mm"] < TOLERANCE_MM and still and \
            not case["errors"] and free

    a = facts["anchor_put"]
    a_held = held(a, anchor, [k for k in tk + uk if k not in (anchor, tk[2])]) and \
        abs(a["turns"][anchor] - TWICE_TURN) < 1e-6 and abs(a["turns"][tk[2]]) < 1e-6 and \
        abs(a["lock_change"]["angle"] + TWICE_TURN) < 1e-6
    px.check(a_held, f"{anchor} put {TWICE_TURN:g}° round held, nothing else turned, its lock took the new angle "
                     f"({a['lock_change']}): {a['turns']}")
    restored = {k: worst(c["off_after_the_locks"]) for k, c in (("restore", facts["restore"]),
                                                                 ("restore_again", facts["restore_again"]))}
    clean = not facts["restore"]["errors"] and not facts["restore_again"]["errors"]
    px.check(all(v < TOLERANCE_MM for v in restored.values()) and clean,
             f"every gear put back where it started, and there after the locks came back (largest {restored})")
    px.fact("lock_on_put_turns", facts["lock_on_put"]["turns"], "a put on the anchor with its lock on")
    d = facts["two_gear_mates_put"]
    joined_ok = facts["moved_by_joining"] < TOLERANCE_MM and not facts["errors_joined"] and \
        all(v == findings.COMPONENT_UNDER_DEFINED for v in facts["constrained_joined"].values())
    px.check(joined_ok, f"the joining gear mate moved nothing ({facts['moved_by_joining']:.1e}) and left every gear "
                        f"under-defined: {facts['constrained_joined']}")
    d_held = held(d, twice, [k for k in tk + uk if k != twice]) and abs(d["turns"][twice] - TWICE_BRIDGE_TURN) < 1e-6
    px.check(d_held, f"{twice}, in two gear mates, put {TWICE_BRIDGE_TURN:g}° round held and nothing else turned: "
                     f"{d['turns']}")
    full = all(v == findings.COMPONENT_FULLY_DEFINED for v in facts["constrained_driven"].values()) and \
        facts["moved_by_the_drive_coming_back"] < TOLERANCE_MM
    joined = _train_ok(facts["joined_turns"], tk + uk, joined_turns(), TWICE_STEP) and not facts["errors_driven"]
    px.check(full and joined, f"one drive fully defines the joined train ({full}) and it turns as one: "
                              f"{facts['joined_turns']}")
    px.fact("put_on_twice_meshed_gear_holds", bool(a_held and all(v < TOLERANCE_MM for v in restored.values()) and clean
                                                   and joined_ok and d_held and full and joined))
    lock_on = facts["lock_on_put"]
    px.fact("lock_on_put_after_drive", {"relative_angle_change": lock_on["after_drive"]["angle"],
                                        "follower_turned": lock_on["drive_turns"][tk[2]],
                                        "anchor_turned": lock_on["drive_turns"][anchor],
                                        "errors": lock_on["errors_after_drive"]},
            "after a put on the anchor with its lock on, the train driven: the lock's angle and both gears' turns")
    e = facts["remake_on_twice_meshed"]
    wanted = joined_turns((17, 68, 17, RATIO_NEW), (51, 17), second=TRAIN_TEETH)
    remade = bool((e.get("remake") or {}).get("name")) and not e["errors"] and \
        all(all(v.values()) for v in e["found_by_name"].values()) and \
        _train_ok(e["turns"], tk + uk, wanted, TWICE_STEP)
    px.check(remade, f"the gear mate of the gear in two gear mates remade at 17 : {RATIO_NEW}: found by name "
                     f"({e['found_by_name']}), position {e['mates_before'].index(old)} -> "
                     f"{e['mates_after'].index(old) if old in e['mates_after'] else None} of {len(e['mates_after'])}, "
                     f"turns {e['turns']}")
    px.fact("remake_on_twice_meshed_gear_holds", remade)


# -- 12: an anchor held along its shaft from a datum plane far behind Front (W5-PLAN-REVIEW M5) --

DATUM_LAYOUT = "Probe W8 Datum Layout"
DATUM_ASSEMBLY = "Probe W8 Datum"
DATUM_PART = "Probe W8 Datum Gear"
DATUM_Z = -1000.0                      # mm: the datum plane, on the -Z side of Front
DATUM_START = 17.0                     # mm: each anchor's origin (its front face) as placed
DATUM_STEPS = (0.0, -5.0, DATUM_START)  # through where the Front plane is, and back
DATUM_AGAIN = 8.0                      # mm, after the reopen
DATUM_RATIO = (20, 40)
#: key, shaft, x, y, sigma, theta as placed
DATUM_GEARS = (("GA", "D1", 40.0, 40.0, 1, DRIVE_FROM), ("GB", "D2", 40.0 + EXTERNAL_CENTRE, 40.0, -1, 0.0))


def datum_distance(z: float, datum: float = DATUM_Z) -> float:
    """The distance from the datum plane to a gear origin at z: never 0 and never changing sign while z > datum."""
    return z - datum


def _mount_on_datum(px: Px, asm: Assembly, key: str, shaft: str, z: float) -> Dict[str, Any]:
    """Unfix a gear, hold it on its shaft's axis (AXIS_MATE_ROUTE) and its origin a distance from the layout's datum
    plane, Flip False first, then True if the gear did not stay at z; each try recorded."""
    enums = _enums(px)
    gear, layout, doc = asm.gears[key], asm.layout, asm.doc
    out: Dict[str, Any] = {"unfixed": unfix(px, doc, gear)}
    picked = select_in(px, doc, gear, "Gear Axis", "AXIS", False) and select_in(px, doc, layout, f"{shaft} Axis", "AXIS", True)
    out["axis"] = add_mate(px, doc, f"{key} on {shaft} Axis", enums["coincident"], enums["closest"]) if picked else None
    tries = []
    for flip in (False, True):
        picked = bool(_select_origin(px, doc, gear, append=False)) and \
            bool(select_in(px, doc, layout, DATUM_PLANE, "PLANE", True))
        if not picked:
            tries.append({"flip": flip, "selected": False})
            break
        made = add_mate(px, doc, f"{key} origin {datum_distance(z):g} mm from the datum, flip {flip}", enums["distance"],
                        enums["closest"], flip=flip, distance=datum_distance(z))
        attempt = {"flip": flip, "mate": made}
        if made["name"]:
            rebuild(px, doc, f"{key} on the datum, flip {flip}", top_only=TOP_ONLY)
            _m, origin = frame_of(gear)
            attempt["z"] = round(origin[2], 9)
            attempt["held"] = abs(origin[2] - z) < TOLERANCE_MM
        tries.append(attempt)
        if attempt.get("held"):
            out["along"] = made["name"]
            out["flip"] = flip
            break
        if made["name"]:
            attempt["deleted_by"] = delete_mate(px, doc, made["name"])
            place(px, doc, gear, asm.placed[key][0], asm.placed[key][1])
    out["tries"] = tries
    return out


def _datum_positions(components: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for key, shaft, x, y, sigma, _theta in DATUM_GEARS:
        m, o = frame_of(components[key])
        out[key] = {"z": round(o[2], 9), "off_axis_mm": round(math.hypot(o[0] - x, o[1] - y), 9),
                    "axis_z": round(axis_z(m), 12)}
    return out


@probe("axial_datum_plane", needs=("shaft_axis_mates",), tier=8,
       members=("IFeatureManager.InsertRefPlane", "IAssemblyDoc.AddMate5 distance", "IEquationMgr.Add2",
                "IEquationMgr.Equation"))
def axial_datum_plane(px: Px) -> None:
    """Two anchors, on Z+ and Z-, held along their shafts from a layout plane 1000 mm behind Front, the distance on
    an assembly global: moved to z = 0 and -5 and back, driven through their gear mate, saved, reopened, moved again."""
    enums = _enums(px)
    folder = _folder(px)
    asm_path = os.path.join(folder, f"{DATUM_ASSEMBLY}.SLDASM")
    _fresh(px, asm_path)
    layout_path = layout_part(px, folder, DATUM_LAYOUT, [(g[1], g[2], g[3]) for g in DATUM_GEARS], datum=DATUM_Z)
    _part, part_path = _part_with_axis(px, folder, DATUM_PART)
    paths = [asm_path, layout_path, part_path]
    asm = Assembly(px, layout_path, {"cyl": part_path})
    facts: Dict[str, Any] = {"datum_z": DATUM_Z}
    globals_ = {key: f"{key} Datum Z" for key, *_ in DATUM_GEARS}
    try:
        asm.open()
        doc = asm.doc
        for key, shaft, x, y, sigma, theta in DATUM_GEARS:
            asm.add(key, "cyl", sigma, theta, (x, y, DATUM_START))
        placed = {k: frame_of(c) for k, c in asm.gears.items()}
        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        mounts = {}
        for key, shaft, x, y, sigma, theta in DATUM_GEARS:
            mounts[key] = _mount_on_datum(px, asm, key, shaft, DATUM_START)
            along = mounts[key].get("along")
            px.require(bool(along), f"{key} is held from the datum plane: {mounts[key]['tries']}")
            axis_name = (mounts[key]["axis"] or {}).get("name")
            px.require(bool(axis_name), f"{key} is on its axis: {mounts[key]['axis']}")
            mounts[key]["axis"] = _rename(px, mate_feature(doc, axis_name), f"{key} on {shaft} Axis")
            mounts[key]["along"] = along = _rename(px, mate_feature(doc, along), f"{key} along {shaft}")
            feature = mate_feature(doc, along)
            match = [d for d in sc.dimensions_of(feature)
                     if abs(float(call(d, "SystemValue")) - sc.m(datum_distance(DATUM_START))) < 1e-9]
            px.require(len(match) == 1 and add(f'"{globals_[key]}"= {datum_distance(DATUM_START):g}') >= 0 and
                       add(f'"{call(match[0], "Name")}@{along}"= "{globals_[key]}"') >= 0,
                       f"{key}'s datum distance is linked to the global \"{globals_[key]}\"")
        facts["mounts"] = mounts
        picked = select_in(px, doc, asm.gears["GA"], "Gear Axis", "AXIS", False) and \
            select_in(px, doc, asm.gears["GB"], "Gear Axis", "AXIS", True)
        px.require(bool(picked), "GA's and GB's axes select")
        gear = add_mate(px, doc, f"GA-GB gear {DATUM_RATIO[0]}:{DATUM_RATIO[1]}", enums["gear"], enums["closest"],
                        flip=bool(findings.GEAR_MATE_FLIP), ratio=(float(DATUM_RATIO[0]), float(DATUM_RATIO[1])))
        px.require(gear["name"] is not None, f"the gear mate is made: {gear}")
        facts["gear_mate"] = _rename(px, mate_feature(doc, gear["name"]), "GA meshes GB")
        facts["rebuild_mated"] = rebuild(px, doc, "mated", top_only=TOP_ONLY)
        facts["moved_by_mating"] = worst(_off(asm.gears, placed))
        facts["errors_mated"] = errors_only(mate_errors(px, doc))
        facts["constrained_mated"] = {k: constrained(px, c) for k, c in asm.gears.items()}
        steps = [{"z": DATUM_START, "global": datum_distance(DATUM_START), "read": _datum_positions(asm.gears)}]
        for z in DATUM_STEPS:
            for key in globals_.values():
                _set_exact(eqm, key, datum_distance(z))
            step = {"z": z, "global": datum_distance(z), "read_before_the_rebuild": _datum_positions(asm.gears)}
            step["rebuild"] = rebuild(px, doc, f"the datum distance {datum_distance(z):g}", top_only=TOP_ONLY)
            step["read"] = _datum_positions(asm.gears)
            step["errors"] = errors_only(mate_errors(px, doc))
            steps.append(step)
        facts["steps"] = steps
        px.require(add(f'"{DRIVE}"= {DRIVE_FROM:g}') >= 0, "the drive global is added")
        facts["drive"] = drive_mate(px, doc, asm.gears["GA"], _plane_names(asm.gears["GA"])[1], asm.layout,
                                    _plane_names(asm.layout)[1], "GA", add, enums["closest"])
        px.require(facts["drive"] is not None, "GA is driven")
        rebuild(px, doc, "drive added", top_only=TOP_ONLY)
        facts["constrained_driven"] = {k: constrained(px, c) for k, c in asm.gears.items()}
        facts["turns"] = _drive_by(px, doc, asm.gears, DRIVE_TO - DRIVE_FROM, "driven")
        facts["errors_driven"] = errors_only(mate_errors(px, doc))
        names = asm.names()
        px.require(_save_in_place(px, doc, asm_path, "the datum assembly") and os.path.isfile(asm_path),
                   "the datum assembly saves")
        px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
    finally:
        if asm.doc is not None and not str(call(asm.doc, "GetPathName") or ""):
            sc.close(px, asm.doc)
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")

    reopened: Dict[str, Any] = {}
    try:
        doc, _route = open_by_path(px, asm_path, sc.SW_DOC_ASSEMBLY, prefer="OpenDoc6")
        components = {k: call(doc, "GetComponentByName", n) for k, n in names.items()}
        px.require(all(c is not None for c in components.values()), "reopened, both gears are found by name")
        reopened["errors"] = errors_only(mate_errors(px, doc))
        reopened["read_on_open"] = _datum_positions(components)
        eqm = call(doc, "GetEquationMgr")
        for key in globals_.values():
            _set_exact(eqm, key, datum_distance(DATUM_AGAIN))
        reopened["rebuild"] = rebuild(px, doc, f"reopened, the datum distance {datum_distance(DATUM_AGAIN):g}",
                                      top_only=TOP_ONLY)
        reopened["read"] = _datum_positions(components)
        reopened["turns"] = _drive_by(px, doc, components, DRIVE_TO - DRIVE_FROM, "reopened and driven")
        reopened["errors_after"] = errors_only(mate_errors(px, doc))
    finally:
        left = close_paths(px, paths)
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    facts["reopened"] = reopened
    px.fact("axial_datum_plane", facts)

    # -- what it says
    def at(read: Mapping[str, Mapping[str, Any]], z: float) -> bool:
        return all(abs(r["z"] - z) < TOLERANCE_MM and r["off_axis_mm"] < TOLERANCE_MM and
                   abs(r["axis_z"] - sigma) < 1e-9 for (key, _s, _x, _y, sigma, _t), r in
                   zip(DATUM_GEARS, (read[g[0]] for g in DATUM_GEARS)))

    px.check(facts["moved_by_mating"] < TOLERANCE_MM, f"no gear moved when mated ({facts['moved_by_mating']:.1e})")
    moved = []
    previous = DATUM_START
    for step in facts["steps"][1:]:
        ok = at(step["read"], step["z"]) and abs(step["z"] - previous) > 1.0 and not step["errors"]
        moved.append(ok)
        px.check(ok, f"the global at {step['global']:g}: both anchors at z = {step['z']:g} "
                     f"({step['read']}; before the rebuild {step['read_before_the_rebuild']})")
        previous = step["z"]
    free = all(v == findings.COMPONENT_UNDER_DEFINED for v in facts["constrained_mated"].values())
    px.check(free and not facts["errors_mated"], f"both anchors under-defined, no mate error: "
                                                 f"{facts['constrained_mated']} {facts['errors_mated']}")
    expected = [1.0, -DATUM_RATIO[0] / DATUM_RATIO[1]]
    step = DRIVE_TO - DRIVE_FROM
    turned = _train_ok(facts["turns"], ["GA", "GB"], expected, step) and not facts["errors_driven"]
    px.check(turned, f"driven, GB turned at the ratio, the way they mesh: {facts['turns']}")
    again = at(reopened["read_on_open"], DATUM_START) and at(reopened["read"], DATUM_AGAIN) and \
        _train_ok(reopened["turns"], ["GA", "GB"], expected, step) and not reopened["errors"] and \
        not reopened["errors_after"]
    px.check(again, f"reopened: where it was saved, moved to z = {DATUM_AGAIN:g} by the global, and turning: "
                    f"{reopened}")
    flips = {key: m.get("flip") for key, m in facts["mounts"].items()}
    px.fact("axial_datum_flips", flips)
    works = all(moved) and free and turned and again and not facts["errors_mated"] and \
        facts["moved_by_mating"] < TOLERANCE_MM and len(set(flips.values())) == 1
    px.fact("axial_datum_route", "origin distance from a datum plane" if works else None)
    px.fact("axial_datum_flip", flips["GA"] if works else None)


# -- 13: which rebuild a MATED train needs, built and changed, each route on a train of its own ----------------
#
# assembly_rebuild_scope (tier 7) settled ForceRebuild3(True) on a static assembly: fixed components, no mates, no
# assembly equations. Here each route builds its own 12 : 1 train twice over (all Z+, and with a Z- middle shaft)
# from its own layout part and gear part, with that route as its only assembly rebuild — placed, mated by what
# tiers 8's items 2-4 found, its output's axial distance on a global, the train driven 30° — and the mate check
# W5-PLAN §1.4 makes; then saves it, closes it, opens it again and takes it through six changes, the route after
# each: the axial global, the drive, the compound anchor put under its suppressed lock, the output shaft moved in
# the layout part's own document, the gears' part's OD changed in its own document, and an angle mate fighting the
# lock. Every change is read once between the change and the route and once after it: a change SolidWorks shows
# before any route is recorded as shown before the route and is not evidence for it. After the put, the layout
# move and the part change the train is driven 30° under the same route, and every frame is compared, gear by
# gear, with the full rebuild's train (ForceRebuild3(False), the route every mated result before P0b was made by).
# Every document's GetSaveFlag is read after the reopen and after every step. The review of P0 found the first
# version of this item ran all three routes on copies of one assembly that shared one layout and one part; here
# nothing is shared.

MATED_ROUTES = ("ForceRebuild3(True)", "EditRebuild3", "ForceRebuild3(False)")   # in order of preference
MATED_REFERENCE = "ForceRebuild3(False)"
MATED_STEMS = {"ForceRebuild3(True)": "Probe W8 Scope Top", "EditRebuild3": "Probe W8 Scope Edit",
               "ForceRebuild3(False)": "Probe W8 Scope Full"}
MATED_DOCS = ("assembly", "layout", "part")
MATED_AXIAL_MOVE = 4.0      # mm the output gear's axial global moves it
MATED_DRIVE_STEP = 30.0
MATED_PUT_TURN = 7.0        # degrees the compound anchor is put round under its suppressed lock
MATED_LAYOUT_MOVE = 5.0     # mm added to the output shaft's X in the layout part's own document
MATED_OD_STEP = 4.0         # mm added to the gears' part's OD in its own document
MATED_CONFLICT = 10.0       # degrees: an angle mate fighting the compound lock
#: the documents each step should leave modified: what it changed on purpose, and what earlier steps did
MATED_WANTED = {"axial": ("assembly",), "drive": ("assembly",), "put": ("assembly",), "layout": ("assembly", "layout"),
                "part": ("assembly", "layout", "part"), "failure": ("assembly", "layout", "part")}
BEFORE = "shown before the route"
#: criteria that must be True: what only the route can show
MATED_EVIDENCE = ("axial_shown", "drive_shown", "put_drive", "layout_drive", "part_drive", "matches_reference",
                  "only_changed_marked")
#: criteria that must be True or BEFORE: a change SolidWorks showed before any route says nothing about the route.
#: put_held is only ever True or False: the reading straight after a Transform2 put is the put's own value.
MATED_RECORDED = ("put_held", "layout_shown", "part_shown", "failure_shown", "failure_cleared")
MATED_CRITERIA = MATED_EVIDENCE + MATED_RECORDED
BUILD_CRITERIA = ("placed", "mate_check", "no_jump", "one_freedom", "turns_right", "matches_reference")
REBUILD_STATUS_WORDS = ("NeedsRebuild", "RebuildStatus")   # type-library members read (never ones that rebuild)


def typelib_members(px: Px, interface: str, library: str = "sldworks.tlb") -> Dict[str, List[Dict[str, int]]]:
    """Every member of one interface in the type library SolidWorks installs: its kinds and parameter counts."""
    import pythoncom  # noqa: PLC0415 - Windows only, and only ever on the worker

    where = str(call(sc.app(px), "GetExecutablePath") or "")
    folder = os.path.dirname(where) if where.lower().endswith(".exe") else where
    path = os.path.join(folder, library)
    if not os.path.isfile(path):
        raise Require(f"There is no {library} at {path}.")
    lib = pythoncom.LoadTypeLib(path)
    for index in range(lib.GetTypeInfoCount()):
        if lib.GetDocumentation(index)[0] != interface:
            continue
        info = lib.GetTypeInfo(index)
        out: Dict[str, List[Dict[str, int]]] = {}
        for i in range(info.GetTypeAttr().cFuncs):
            desc = info.GetFuncDesc(i)
            out.setdefault(str(info.GetNames(desc.memid)[0]), []).append(
                {"invkind": int(desc.invkind), "params": len(desc.args or ())})
        return out
    raise Require(f"{library} has no {interface}.")


def rebuild_status_members(px: Px) -> Dict[str, List[str]]:
    """The members of IModelDoc2 and IModelDocExtension the type library lists whose names say they report whether
    a rebuild is needed, and take no argument; every member with Rebuild in its name, as evidence."""
    out: Dict[str, List[str]] = {}
    for interface in ("IModelDoc2", "IModelDocExtension"):
        try:
            members = typelib_members(px, interface)
        except Exception as exc:  # noqa: BLE001 - evidence only
            px.note(f"{interface} could not be read from sldworks.tlb: {exc}")
            continue
        px.fact(f"rebuild members of {interface}", sorted(n for n in members if "Rebuild" in n))
        out[interface] = sorted(n for n, forms in members.items()
                                if any(w in n for w in REBUILD_STATUS_WORDS) and any(f["params"] == 0 for f in forms))
    return out


def _rebuild_status(px: Px, doc: Any, members: Mapping[str, Sequence[str]], label: str) -> Dict[str, Any]:
    """One read of each listed rebuild-status member; what each answered."""
    out: Dict[str, Any] = {}
    for interface, names in members.items():
        owner = doc if interface == "IModelDoc2" else sc.extension(doc)
        for name in names:
            got, value = px.attempt(f"{interface}.{name} ({label})", lambda n=name, o=owner: member(o, n)[0])
            out[f"{interface}.{name}"] = plain(value) if got else "raised"
    return out


def mated_marked(flags: Optional[Mapping[str, Any]], wanted: Sequence[str]) -> Optional[bool]:
    """Whether exactly the ``wanted`` documents read GetSaveFlag True; None when a flag could not be read."""
    if not flags or any(flags.get(name) is None for name in MATED_DOCS):
        return None
    return all(bool(flags[name]) is (name in wanted) for name in MATED_DOCS)




def shown(before: bool, after: bool) -> Any:
    """A step's verdict from the reading between its change and the route (``before``: the change already shows)
    and the reading after the route (``after``: it shows, right): BEFORE when SolidWorks showed it before any route,
    else whether the route did."""
    if before:
        return BEFORE if after else False
    return bool(after)


def frame_table(components: Mapping[str, Any]) -> Dict[str, List[Any]]:
    """Every frame as plain lists, rotation by rows then origin in mm: what two trains are compared by."""
    out = {}
    for key, component in components.items():
        m, o = frame_of(component)
        out[key] = [[list(map(float, row)) for row in m], [float(v) for v in o]]
    return out


def frame_table_diff(a: Mapping[str, Sequence[Any]], b: Mapping[str, Sequence[Any]]) -> float:
    """The largest difference between two frame tables over the gears both hold (matrix entries and mm alike);
    infinity when they hold different gears."""
    if set(a) != set(b) or not a:
        return math.inf
    return max(max(rotation_error(a[k][0], b[k][0]), math.dist(a[k][1], b[k][1])) for k in a)


def mated_verdict(case: Mapping[str, Any]) -> Dict[str, Any]:
    """What one route did, criterion by criterion (``MATED_CRITERIA``): True, False, BEFORE, or None where the step
    was not reached. ``matches_reference`` is filled in by the probe, against the full rebuild's train."""
    steps = {step: case.get(step) or {} for step in MATED_WANTED}
    marks = [mated_marked(steps[step].get(key), MATED_WANTED[step]) for step in MATED_WANTED
             for key in ("flags", "flags_after_reads")]
    return {
        "axial_shown": steps["axial"].get("shown"), "drive_shown": steps["drive"].get("shown"),
        "put_held": steps["put"].get("shown"), "put_drive": steps["put"].get("drive_right"),
        "layout_shown": steps["layout"].get("shown"), "layout_drive": steps["layout"].get("drive_right"),
        "part_shown": steps["part"].get("shown"), "part_drive": steps["part"].get("drive_right"),
        "failure_shown": steps["failure"].get("shown"), "failure_cleared": steps["failure"].get("cleared"),
        "only_changed_marked": None if any(m is None for m in marks) else all(marks),
        "matches_reference": case.get("matches_reference"),
    }


def first_mated_route(verdicts: Mapping[str, Mapping[str, Any]]) -> Optional[str]:
    """The first route of ``MATED_ROUTES`` whose every evidence criterion is True and every recorded one True or
    BEFORE; None when none is."""
    for route in MATED_ROUTES:
        v = verdicts.get(route)
        if v and all(v.get(c) is True for c in MATED_EVIDENCE) and all(v.get(c) in (True, BEFORE) for c in MATED_RECORDED):
            return route
    return None


def build_verdict(build: Mapping[str, Any]) -> Dict[str, Any]:
    """What one route's build did (``BUILD_CRITERIA``): every gear placed where it was put, the mate check clean
    (AddMate5 statuses, error codes, every gear under-defined), no gear moved by its mates, one drive making every
    gear fully defined, the trains turning 1/12 the same way, and the built frames the full rebuild's."""
    check = build.get("check") or {}
    return {
        "placed": build.get("placed_off", 1.0) < TOLERANCE_MM,
        "mate_check": bool(check) and all(v == findings.ADD_MATE_NO_ERROR for v in check.get("statuses", [None]))
        and not check.get("errors") and all(v == findings.COMPONENT_UNDER_DEFINED
                                            for v in (check.get("constrained") or {"x": None}).values()),
        "no_jump": build.get("moved_by_mating", 1.0) < TOLERANCE_MM,
        "one_freedom": bool(build.get("constrained_driven")) and all(
            v == findings.COMPONENT_FULLY_DEFINED for v in build["constrained_driven"].values()),
        "turns_right": build.get("turns_right"),
        "matches_reference": build.get("matches_reference"),
    }


def first_build_route(verdicts: Mapping[str, Mapping[str, Any]]) -> Optional[str]:
    """The first route of ``MATED_ROUTES`` whose build met every criterion; None when none did."""
    for route in MATED_ROUTES:
        v = verdicts.get(route)
        if v and all(v.get(c) is True for c in BUILD_CRITERIA):
            return route
    return None


def _put_by_route(px: Px, doc: Any, route: str, component: Any, matrix: Matrix, at: Sequence[float],
                  label: str) -> Dict[str, Any]:
    """A Transform2 put and then the route: the only rebuild a route's build makes."""
    from .p7_workbook import _apply_route  # noqa: PLC0415
    transform = make_transform(px, array_data(matrix, at, findings.TRANSFORM_ARRAY_ORDER or "columns"))
    px.attempt(f"Transform2 put ({label})", lambda: setattr(component, "Transform2", transform))
    return _apply_route(px, doc, route, label)


def _drive_route(px: Px, doc: Any, components: Mapping[str, Any], step: float, route: str, label: str) -> Dict[str, Any]:
    """The drive global moved by ``step`` and the route applied; every turn about +Z and every frame after."""
    from .p7_workbook import _apply_route, _global_value  # noqa: PLC0415
    eqm = call(doc, "GetEquationMgr")
    now = _global_value(eqm, DRIVE)
    if now is None:
        raise Require(f'There is no global "{DRIVE}" to drive by.')
    before = _frames(components)
    _set_global(eqm, DRIVE, now + step)
    rebuilt = _apply_route(px, doc, route, label)
    return {"rebuild": rebuilt, "turns": _world_turns(components, before), "frames": frame_table(components)}


def _scope_build(px: Px, route: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """One route's own train, built with the route as its only assembly rebuild, checked, driven, saved and closed.
    What the build showed, and the record of the train (as mated_train's)."""
    from .p7_workbook import _apply_route, _save_flags  # noqa: PLC0415

    enums = _enums(px)
    rule, lock = px.shared.get("gear_mate_flip_rule"), px.shared.get("compound_lock_route")
    px.require(bool(rule) and lock == "lock alone", f"the flip rule ({rule}) and the lock route ({lock}) are decided")
    stem = MATED_STEMS[route]
    folder = _folder(px)
    asm_path = os.path.join(folder, f"{stem} Train.SLDASM")
    _fresh(px, asm_path)
    trains = {name: train_geometry(prefix, sigmas, origin) for name, prefix, sigmas, origin in TRAINS}
    layout_path = layout_part(px, folder, f"{stem} Layout", [s for t in trains.values() for s in t["shafts"]], link=True)
    _part, part_path = _part_with_axis(px, folder, f"{stem} Gear")
    paths = {"assembly": asm_path, "layout": layout_path, "part": part_path}
    asm = Assembly(px, layout_path, {"cyl": part_path})
    out: Dict[str, Any] = {"route": route}
    mates: Dict[str, Any] = {}
    made: List[Dict[str, Any]] = []
    names: Dict[str, str] = {}
    layout_name = ""
    try:
        open_by_path(px, layout_path)
        asm.doc = doc = sc.new_document(px, sc.SW_DOC_ASSEMBLY)
        _millimetres(px, doc)
        asm.layout = call(doc, "AddComponent5", layout_path, 0, "", False, "", 0.0, 0.0, 0.0)
        px.require(asm.layout is not None, "the layout part is inserted")
        _put_by_route(px, doc, route, asm.layout, IDENTITY, (0.0, 0.0, 0.0), "the layout placed")
        px.require(fix(px, doc, asm.layout), "the layout component is fixed")
        for t in trains.values():
            for g in t["gears"]:
                component = call(doc, "AddComponent5", part_path, 0, "", False, "", sc.m(g["at"][0]), sc.m(g["at"][1]),
                                 sc.m(g["at"][2]))
                px.require(component is not None, f"{g['key']} is inserted")
                matrix = w4_rotation(g["sigma"], g["theta"])
                _put_by_route(px, doc, route, component, matrix, g["at"], f"{g['key']} placed")
                px.require(fix(px, doc, component), f"{g['key']} is fixed, as W4 leaves it")
                asm.gears[g["key"]] = component
                asm.placed[g["key"]] = (matrix, g["at"])
        out["placed_off"] = worst(_off(asm.gears, asm.placed))
        for name, t in trains.items():
            g1, g2, g3, g4 = t["gears"]
            for g in t["gears"]:
                if g is g3:
                    px.require(unfix(px, doc, asm.gears[g["key"]]), f"{g['key']} floats")
                    continue
                mates[g["key"]] = mount(px, asm, g["key"], g["shaft"], g["sigma"], g["at"][2], g["at"], record=made)
            for a, b in ((g1, g2), (g3, g4)):
                flip = needed_flip(rule, a["sigma"], b["sigma"], False, a["teeth"] > b["teeth"])
                picked = select_in(px, doc, asm.gears[a["key"]], "Gear Axis", "AXIS", False) and \
                    select_in(px, doc, asm.gears[b["key"]], "Gear Axis", "AXIS", True)
                px.require(bool(picked), f"{a['key']} and {b['key']}'s axes select")
                result = add_mate(px, doc, f"{a['key']}-{b['key']} gear", enums["gear"], enums["closest"], flip=flip,
                                  ratio=(float(a["teeth"]), float(b["teeth"])))
                made.append(result)
                px.require(result["name"] is not None, f"the {a['key']}-{b['key']} gear mate is made: {result}")
                mates[f"{a['key']}-{b['key']}"] = {"name": result["name"], "flip": flip}
            px.require(bool(select_components(px, doc, (asm.gears[g2["key"]], asm.gears[g3["key"]]))),
                       f"{name}: G2 and G3 select")
            result = add_mate(px, doc, f"{name}: G2-G3 lock", enums["lock"], enums["closest"])
            made.append(result)
            px.require(result["name"] is not None, f"{name}: the compound lock is made: {result}")
            mates[f"{name} lock"] = result["name"]
        out["rebuild_mated"] = _apply_route(px, doc, route, "mated")
        out["check"] = {"statuses": [m.get("status") for m in made], "errors": errors_only(mate_errors(px, doc)),
                        "constrained": {k: constrained(px, c) for k, c in asm.gears.items()}}
        out["moved_by_mating"] = worst(_off(asm.gears, asm.placed))
        # The output's axial distance on an assembly global, as W5 builds it ("<Gear> Face Z").
        t = trains["all Z+"]
        g4 = t["gears"][3]
        axial = mates[g4["key"]][1]
        face = f"{g4['key']} Face Z"
        add = adder(px, call(doc, "GetEquationMgr"))
        match = [d for d in sc.dimensions_of(mate_feature(doc, axial))
                 if abs(float(call(d, "SystemValue")) - sc.m(abs(g4["at"][2]))) < 1e-9]
        px.require(len(match) == 1 and add(f'"{face}"= {abs(g4["at"][2]):g}') >= 0 and
                   add(f'"{call(match[0], "Name")}@{axial}"= "{face}"') >= 0,
                   f'the output\'s axial distance is linked to "{face}"')
        px.require(add(f'"{DRIVE}"= {DRIVE_FROM:g}') >= 0, "the drive global is added")
        for name, tr in trains.items():
            g1 = asm.gears[tr["gears"][0]["key"]]
            px.require(drive_mate(px, doc, g1, _plane_names(g1)[1], asm.layout, _plane_names(asm.layout)[1], name,
                                  add, enums["closest"]) is not None, f"{name}: the input is driven")
        out["rebuild_driven"] = _apply_route(px, doc, route, "drive added")
        out["constrained_driven"] = {k: constrained(px, c) for k, c in asm.gears.items()}
        driven = _drive_route(px, doc, asm.gears, DRIVE_TO - DRIVE_FROM, route, "driven 30°")
        out["turns"] = driven["turns"]
        expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
        out["turns_right"] = all(_train_ok(driven["turns"], [g["key"] for g in tr["gears"]], expected,
                                           DRIVE_TO - DRIVE_FROM) for tr in trains.values())
        out["errors_driven"] = errors_only(mate_errors(px, doc))
        out["frames"] = driven["frames"]
        out["flags_before_save"] = _save_flags(px, paths)
        px.require(_save_in_place(px, doc, asm_path, f"{route}'s train") and os.path.isfile(asm_path),
                   f"{route}: the train saves")
        px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
        out["flags_after_save"] = _save_flags(px, paths)
        names = asm.names()
        layout_name = str(call(asm.layout, "Name2"))
    finally:
        if asm.doc is not None and not str(call(asm.doc, "GetPathName") or ""):
            sc.close(px, asm.doc)
        left = close_paths(px, list(paths.values()))
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    info = {"path": asm_path, "layout": layout_path, "part": part_path, "names": names, "mates": mates,
            "trains": trains, "layout_name": layout_name}
    return out, info


def _mated_case(px: Px, info: Mapping[str, Any], route: str, status_members: Mapping[str, Sequence[str]]) -> Dict[str, Any]:
    """One route through steps a-f on its own train, every change read before and after the route."""
    from .p7_workbook import _apply_route, _global_value, _save_flags, activate  # noqa: PLC0415

    enums = _enums(px)
    started = time.monotonic()
    path = info["path"]
    paths = {"assembly": path, "layout": info["layout"], "part": info["part"]}
    t = info["trains"]["all Z+"]
    tk = [g["key"] for g in t["gears"]]
    keys = [g["key"] for tr in info["trains"].values() for g in tr["gears"]]
    g4 = t["gears"][3]
    s3 = g4["shaft"]
    face = f"{g4['key']} Face Z"
    lock = info["mates"]["all Z+ lock"]
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    case: Dict[str, Any] = {"assembly": os.path.basename(path)}

    def flags() -> Dict[str, Optional[bool]]:
        return _save_flags(px, paths)

    def both_right(turns: Mapping[str, float]) -> bool:
        return all(_train_ok(turns, [g["key"] for g in tr["gears"]], expected, MATED_DRIVE_STEP)
                   for tr in info["trains"].values())

    try:
        doc, components = _open_train(px, path, info["names"])
        asm_title = str(call(doc, "GetTitle"))
        case["flags_on_open"] = flags()
        case["status_on_open"] = _rebuild_status(px, doc, status_members, "on open")
        eqm = call(doc, "GetEquationMgr")

        # (a) the output's axial global moved.
        e: Dict[str, Any] = {}
        start = _frames(components)
        _set_global(eqm, face, _global_value(eqm, face) + MATED_AXIAL_MOVE)
        e["before_route_mm"] = round(frame_of(components[g4["key"]])[1][2] - start[g4["key"]][1][2], 9)
        e["flags_before_route"] = flags()
        e["status_before_route"] = _rebuild_status(px, doc, status_members, "the axial global changed, before the route")
        e["rebuild"] = _apply_route(px, doc, route, "axial global")
        e["flags"] = flags()
        e["status"] = _rebuild_status(px, doc, status_members, "after the axial global")
        e["moved_mm"] = round(frame_of(components[g4["key"]])[1][2] - start[g4["key"]][1][2], 9)
        e["others_moved"] = worst(_off(components, {k: v for k, v in start.items() if k != g4["key"]}))
        e["errors"] = errors_only(mate_errors(px, doc))
        e["shown"] = shown(abs(e["before_route_mm"]) > TOLERANCE_MM,
                           abs(e["moved_mm"] - MATED_AXIAL_MOVE) < TOLERANCE_MM and e["others_moved"] < TOLERANCE_MM
                           and not e["errors"])
        e["flags_after_reads"] = flags()
        case["axial"] = e

        # (b) the drive's global turned.
        e = {}
        start = _frames(components)
        _set_global(eqm, DRIVE, _global_value(eqm, DRIVE) + MATED_DRIVE_STEP)
        e["before_route"] = _world_turns(components, start)
        e["flags_before_route"] = flags()
        e["status_before_route"] = _rebuild_status(px, doc, status_members, "the drive changed, before the route")
        e["rebuild"] = _apply_route(px, doc, route, "drive")
        e["flags"] = flags()
        e["status"] = _rebuild_status(px, doc, status_members, "after the drive")
        e["turns"] = _world_turns(components, start)
        e["errors"] = errors_only(mate_errors(px, doc))
        e["shown"] = shown(any(abs(v) > 1e-6 for v in e["before_route"].values()),
                           both_right(e["turns"]) and not e["errors"])
        e["flags_after_reads"] = flags()
        case["drive"] = e

        # (c) the compound lock suppressed, the route; its anchor put round (raw Transform2), the route; the lock back
        # on, the route; then driven under the route.
        e = {}
        anchor, follower = tk[1], tk[2]
        start = _frames(components)
        pose = relative_pose(start[anchor], start[follower])
        e["suppressed_by"] = suppress(px, doc, lock, True)
        e["rebuild_suppressed"] = _apply_route(px, doc, route, "lock suppressed")
        m, o = start[anchor]
        target = (crossed.multiply(m, crossed.rot_z(MATED_PUT_TURN)), o)
        transform = make_transform(px, array_data(target[0], o, findings.TRANSFORM_ARRAY_ORDER or "columns"))
        px.attempt(f"{route}: Transform2 put on {anchor}", lambda: setattr(components[anchor], "Transform2", transform))
        e["before_route_turn"] = round(own_turn(m, frame_of(components[anchor])[0]), 9)
        e["rebuild_put"] = _apply_route(px, doc, route, "put")
        e["unsuppressed_by"] = suppress(px, doc, lock, False)
        e["flags_before_route"] = flags()
        e["rebuild"] = _apply_route(px, doc, route, "lock back on")
        e["flags"] = flags()
        e["anchor_off"] = _off(components, {anchor: target})[anchor]
        e["turns"] = _world_turns(components, start)
        e["lock_change"] = pose_change(pose, relative_pose(frame_of(components[anchor]), frame_of(components[follower])))
        e["errors"] = errors_only(mate_errors(px, doc))
        held = e["anchor_off"]["rotation"] < TOLERANCE_ROTATION and e["anchor_off"]["origin_mm"] < TOLERANCE_MM \
            and abs(e["turns"][follower]) < 1e-6 and abs(e["lock_change"]["angle"] + MATED_PUT_TURN) < 1e-6 and \
            not e["errors"] and all(abs(e["turns"][k]) < 1e-6 for k in keys if k not in (anchor, follower))
        # Judged after the last route only: the reading straight after the put is the put's own value (recorded).
        e["shown"] = held
        e["flags_after_reads"] = flags()
        e["drive"] = _drive_route(px, doc, components, MATED_DRIVE_STEP, route, "driven after the put")
        after = pose_change(pose, relative_pose(frame_of(components[anchor]), frame_of(components[follower])))
        e["lock_change_after_drive"] = after
        e["drive_right"] = both_right(e["drive"]["turns"]) and abs(after["angle"] + MATED_PUT_TURN) < 1e-6 and \
            not errors_only(mate_errors(px, doc))
        case["put"] = e

        # (d) the output shaft moved in the layout part's own document (opened by path, activated, rebuilt there).
        e = {}
        start = _frames(components)
        layout_doc, _ = open_by_path(px, info["layout"], prefer="OpenDoc6")
        px.require(activate(px, str(call(layout_doc, "GetTitle"))), f"{route}: the layout part is active")
        leqm = call(layout_doc, "GetEquationMgr")
        x_old, y_old = _global_value(leqm, f"{s3} X"), _global_value(leqm, f"{s3} Y")
        x_new = x_old + MATED_LAYOUT_MOVE
        e["set"] = _set_exact(leqm, f"{s3} X", x_new)
        e["layout_rebuild"] = plain(call(layout_doc, "ForceRebuild3", False))
        e["before_activate_mm"] = round(frame_of(components[g4["key"]])[1][0] - start[g4["key"]][1][0], 9)
        px.require(activate(px, asm_title), f"{route}: the assembly is active again")
        # ActivateDoc3 sits between the change and the route: read after it, before the route.
        e["before_route_mm"] = round(frame_of(components[g4["key"]])[1][0] - start[g4["key"]][1][0], 9)
        e["flags_before_route"] = flags()
        e["status_before_route"] = _rebuild_status(px, doc, status_members, "the layout moved, before the route")
        e["rebuild"] = _apply_route(px, doc, route, "layout move")
        e["flags"] = flags()
        e["status"] = _rebuild_status(px, doc, status_members, "after the layout move")
        m4, o4 = frame_of(components[g4["key"]])
        e["output_at_mm"] = _mm(o4)
        e["wanted_mm"] = [round(x_new, 9), round(y_old, 9)]
        e["others_moved"] = worst(_off(components, {k: v for k, v in start.items() if k != g4["key"]}))
        e["errors"] = errors_only(mate_errors(px, doc))
        on_axis = math.hypot(o4[0] - x_new, o4[1] - y_old) < TOLERANCE_MM and abs(axis_z(m4) - 1.0) < 1e-9
        e["shown"] = shown(abs(e["before_route_mm"]) > TOLERANCE_MM or abs(e["before_activate_mm"]) > TOLERANCE_MM,
                           on_axis and e["others_moved"] < TOLERANCE_MM and not e["errors"])
        e["flags_after_reads"] = flags()
        e["drive"] = _drive_route(px, doc, components, MATED_DRIVE_STEP, route, "driven after the layout move")
        m4, o4 = frame_of(components[g4["key"]])
        e["drive_right"] = both_right(e["drive"]["turns"]) and \
            math.hypot(o4[0] - x_new, o4[1] - y_old) < TOLERANCE_MM and not errors_only(mate_errors(px, doc))
        case["layout"] = e

        # (e) the gears' part changed in its own document: its OD through a global there.
        e = {}
        e["volume_before_mm3"] = sc.volume_mm3(doc)
        e["flags_after_volume_before"] = flags()
        part_doc, _ = open_by_path(px, info["part"], prefer="OpenDoc6")
        px.require(activate(px, str(call(part_doc, "GetTitle"))), f"{route}: the gears' part is active")
        peqm = call(part_doc, "GetEquationMgr")
        od_now = float(call(sc.dimension_named(sc.feature_by_name(part_doc, "Blank Sketch"), "OD"), "SystemValue")) * sc.MM
        od_new = od_now + MATED_OD_STEP
        padd = adder(px, peqm)
        px.require(padd(f'"Probe OD"= {od_new:g}') >= 0 and padd('"OD@Blank Sketch"= "Probe OD"') >= 0,
                   f"{route}: the part's OD is put on a global")
        e["od_mm"] = [od_now, od_new]
        e["part_rebuild"] = plain(call(part_doc, "ForceRebuild3", False))
        px.require(activate(px, asm_title), f"{route}: the assembly is active again")
        start = _frames(components)
        e["flags_before_route"] = flags()
        e["status_before_route"] = _rebuild_status(px, doc, status_members, "the part changed, before the route")
        # Read before the route too, though a mass property might itself rebuild what it measures.
        e["volume_before_route_mm3"] = sc.volume_mm3(doc)
        e["flags_after_volume_before_route"] = flags()
        e["rebuild"] = _apply_route(px, doc, route, "part change")
        e["flags"] = flags()
        e["status"] = _rebuild_status(px, doc, status_members, "after the part change")
        e["moved"] = worst(_off(components, start))
        e["errors"] = errors_only(mate_errors(px, doc))
        e["flags_after_reads"] = flags()
        e["volume_after_mm3"] = sc.volume_mm3(doc)
        e["volume_wanted_mm3"] = round(len(keys) * math.pi * (od_new / 2.0) ** 2 * BLANK_W, 3)
        e["flags_after_volume"] = flags()

        def is_new(volume: Optional[float]) -> bool:
            return volume is not None and abs(volume - e["volume_wanted_mm3"]) < 1e-3 * e["volume_wanted_mm3"]

        e["shown"] = shown(is_new(e["volume_before_route_mm3"]),
                           is_new(e["volume_after_mm3"]) and e["moved"] < TOLERANCE_MM and not e["errors"])
        e["drive"] = _drive_route(px, doc, components, MATED_DRIVE_STEP, route, "driven after the part change")
        e["drive_right"] = both_right(e["drive"]["turns"]) and not errors_only(mate_errors(px, doc))
        case["part"] = e

        # (f) a failure that starts in the assembly: an angle mate fighting the compound lock; then deleted.
        e = {}
        p2, p3 = components[tk[1]], components[tk[2]]
        rel = abs(unwrap(relative_angle(p2, p3)))
        picked = select_in(px, doc, p3, _plane_names(p3)[1], "PLANE", False) and \
            select_in(px, doc, p2, _plane_names(p2)[1], "PLANE", True)
        e["selected"] = bool(picked)
        conflict = min(rel + MATED_CONFLICT, 179.0) if rel < 170.0 else rel - MATED_CONFLICT
        e["mate"] = add_mate(px, doc, f"{route}: an angle {conflict:g}° fighting the lock", enums["angle"],
                             enums["closest"], angle=conflict)
        made = e["mate"]["name"] or (e["mate"]["made"] or [None])[0]
        e["errors_before_route"] = errors_only(mate_errors(px, doc))
        e["flags_before_route"] = flags()
        e["rebuild"] = _apply_route(px, doc, route, "over-defined")
        e["flags"] = flags()
        e["status"] = _rebuild_status(px, doc, status_members, "over-defined")
        e["errors"] = errors_only(mate_errors(px, doc))
        e["whats_wrong"] = whats_wrong(px, doc)
        e["constrained"] = {k: constrained(px, components[k]) for k in tk}
        e["shown"] = shown(bool(made) and made in e["errors_before_route"], bool(made) and made in e["errors"])
        e["flags_after_reads"] = flags()
        if made:
            e["deleted_by"] = delete_mate(px, doc, made)
            e["errors_after_delete_before_route"] = errors_only(mate_errors(px, doc))
            e["rebuild_after_delete"] = _apply_route(px, doc, route, "conflict deleted")
            e["errors_after_delete"] = errors_only(mate_errors(px, doc))
            e["constrained_after_delete"] = {k: constrained(px, components[k]) for k in tk}
            e["cleared"] = shown(bool(e["deleted_by"]) and not e["errors_after_delete_before_route"],
                                 bool(e["deleted_by"]) and not e["errors_after_delete"])
        case["failure"] = e
    finally:
        left = close_paths(px, list(paths.values()))
        if left:
            px.note(f"CLEANUP still open after closing: {left}")
    case["seconds"] = round(time.monotonic() - started, 1)
    return case


@probe("mated_rebuild_scope", needs=("mated_train",), tier=8,
       members=("IModelDoc2.ForceRebuild3", "IModelDoc2.EditRebuild3", "IModelDoc2.GetSaveFlag", "IEquationMgr.Equation",
                "IComponent2.Transform2", "IFeature.SetSuppression2", "IModelDocExtension.CreateMassProperty",
                "IModelDocExtension.NeedsRebuild2"))
def mated_rebuild_scope(px: Px) -> None:
    """Which assembly rebuild a mated train needs, to be built and to be changed: each route builds its own train
    with itself as the only rebuild, then takes it through an axial global, a drive, a put under a suppressed lock,
    a layout move, a part change and an over-defining mate, each read before and after the route; frames compared
    with the full rebuild's train, and which documents each marks modified."""
    status_members = rebuild_status_members(px)
    px.fact("rebuild_status_members", status_members)
    builds: Dict[str, Dict[str, Any]] = {}
    cases: Dict[str, Dict[str, Any]] = {}
    for route in MATED_ROUTES:
        try:
            builds[route], info = _scope_build(px, route)
        except Require as exc:
            builds[route] = {"route": route, "failed": str(exc)}
            cases[route] = {"failed": "its build failed"}
            px.note(f"{route}: its build failed: {exc}")
            continue
        try:
            cases[route] = _mated_case(px, info, route, status_members)
        except Require as exc:
            cases[route] = {"failed": str(exc)}
            px.note(f"{route}: its changes failed: {exc}")
    reference_build, reference = builds[MATED_REFERENCE], cases[MATED_REFERENCE]
    against: Dict[str, Dict[str, float]] = {}
    for route in MATED_ROUTES:
        diffs = {"build": frame_table_diff(builds[route].get("frames") or {}, reference_build.get("frames") or {})}
        for step in ("put", "layout", "part"):
            diffs[step] = frame_table_diff(((cases[route].get(step) or {}).get("drive") or {}).get("frames") or {},
                                           ((reference.get(step) or {}).get("drive") or {}).get("frames") or {})
        against[route] = diffs
        builds[route]["matches_reference"] = diffs["build"] < TOLERANCE_MM
        cases[route]["matches_reference"] = all(diffs[s] < TOLERANCE_MM for s in ("put", "layout", "part"))
    px.fact("mated_frames_against_reference", against, "each route's frames against the full rebuild's, gear by gear "
                                                       "(largest matrix entry or mm off)")
    px.fact("mated_builds", builds)
    px.fact("mated_rebuild_cases", cases)
    build_verdicts = {route: build_verdict(b) for route, b in builds.items()}
    verdicts = {route: mated_verdict(c) for route, c in cases.items()}
    px.fact("mated_build_verdicts", build_verdicts)
    px.fact("mated_rebuild_verdicts", verdicts)
    px.fact("mated_build_marked", {route: {"before_save": [d for d in MATED_DOCS if (b.get("flags_before_save") or {}).get(d)],
                                           "after_save": [d for d in MATED_DOCS if (b.get("flags_after_save") or {}).get(d)]}
                                   for route, b in builds.items()})
    marked = {route: {step: [d for d in MATED_DOCS if ((case.get(step) or {}).get("flags") or {}).get(d)]
                      for step in MATED_WANTED} for route, case in cases.items()}
    px.fact("mated_rebuild_marked", marked)
    px.fact("mated_rebuild_returned", {route: {step: ((case.get(step) or {}).get("rebuild") or {}).get("returned")
                                               for step in MATED_WANTED} for route, case in cases.items()})
    px.fact("mated_flags_on_open", {route: case.get("flags_on_open") for route, case in cases.items()})
    shown_before = {route: [c for c in MATED_RECORDED if v.get(c) == BEFORE] for route, v in verdicts.items()}
    px.fact("mated_shown_before_the_route", shown_before, "changes SolidWorks showed before any route: not evidence")
    for route in MATED_ROUTES:
        px.check(True, f"{route}: build {build_verdicts[route]}; changes {verdicts[route]}; marked {marked[route]}")
    px.check(all(build_verdicts[MATED_REFERENCE].values()), f"the full rebuild's own build is right, so it can be the "
                                                           f"reference: {build_verdicts[MATED_REFERENCE]}")
    build = first_build_route(build_verdicts)
    px.fact("mated_build_rebuild_route", build)
    px.fact("mated_build_keeps_components_unmodified",
            None if build is None else not any((builds[build].get("flags_before_save") or {}).get(d)
                                               for d in ("layout", "part")))
    route = first_mated_route(verdicts)
    px.fact("mated_assembly_rebuild_route", route)
    px.fact("mated_rebuild_keeps_components_unmodified", None if route is None else verdicts[route]["only_changed_marked"])


# -- 14: what W5's build code does that no probe had done (probe round P0c) ------------------------------------
#
# From the review of the W5 SolidWorks code: its build makes every Unfix and AddMate5 with
# ISldWorks.CommandInProgress on, renames each mate straight after its AddMate5, then makes one top-only rebuild and
# turns it off; it reads every mate's error code, its warning flag and whether it is suppressed, and treats a
# sub-feature of the MateGroup as a mate when its type name starts with "Mate"; it turns recorded mates back on with
# SetSuppression2 whether or not they are off; it may remake a gear mate on lightweight components; and after a
# refused build it leaves the new assembly open, unsaved, while the next build makes another from the same parts.

CIP_STEM = "Probe W8 CIP"
CIP_CONFLICT = 10.0      # degrees: an angle mate fighting the compound lock


def cip_names(trains: Mapping[str, Any]) -> Dict[str, Any]:
    """W5's names (D12) for the probe trains' mates: per anchor its axis and axial mates, per mesh, per lock."""
    out: Dict[str, Any] = {}
    for name, t in trains.items():
        g1, g2, g3, g4 = t["gears"]
        for g in (g1, g2, g4):
            out[g["key"]] = (f"{g['key']} on {g['shaft']} Axis", f"{g['key']} along {g['shaft']}")
        out[f"{g1['key']}-{g2['key']}"] = f"{g1['key']} meshes {g2['key']}"
        out[f"{g3['key']}-{g4['key']}"] = f"{g3['key']} meshes {g4['key']}"
        out[f"{name} lock"] = f"{g3['key']} locked to {g2['key']}"
    return out


def _command_in_progress(px: Px, on: bool) -> Dict[str, Any]:
    """ISldWorks.CommandInProgress put (the property scaffold.scratch already sets back), and what reads back."""
    application = sc.app(px)
    got, _ = px.attempt(f"CommandInProgress = {on}", lambda: setattr(application, "CommandInProgress", on))
    ok, value = px.attempt("CommandInProgress read back", lambda: call(application, "CommandInProgress"))
    return {"put": got, "reads": plain(value) if ok else "raised"}


def suppression_of(px: Px, doc: Any) -> Dict[str, Optional[bool]]:
    return {n: is_suppressed(px, mate_feature(doc, n)) for n in mate_names(doc)}


@probe("mates_under_command_in_progress", needs=("mated_train",), tier=8,
       members=("ISldWorks.CommandInProgress", "IAssemblyDoc.AddMate5", "IFeature.Name", "IFeature.GetErrorCode2",
                "IFeature.IsSuppressed2", "IFeature.SetSuppression2", "IModelDoc2.GetSaveFlag"))
def mates_under_command_in_progress(px: Px) -> None:
    """The train built as W5's build makes it: every Unfix and AddMate5 with CommandInProgress on, each mate renamed
    straight after its AddMate5 in the new, unsaved assembly, one top-only rebuild, CommandInProgress off; checked
    and driven; a conflicting mate under CommandInProgress; error codes of suppressed mates; saved, reopened, found by
    name; and SetSuppression2(unsuppress) on a lock already on."""
    from .p7_workbook import _save_flags  # noqa: PLC0415

    enums = _enums(px)
    rule, lock_route = px.shared.get("gear_mate_flip_rule"), px.shared.get("compound_lock_route")
    px.require(bool(rule) and lock_route == "lock alone", f"the flip rule ({rule}) and the lock route ({lock_route}) "
                                                         "are decided")
    folder = _folder(px)
    asm_path = os.path.join(folder, f"{CIP_STEM} Train.SLDASM")
    _fresh(px, asm_path)
    trains = {name: train_geometry(prefix, sigmas, origin) for name, prefix, sigmas, origin in TRAINS}
    wanted = cip_names(trains)
    layout_path = layout_part(px, folder, f"{CIP_STEM} Layout", [s for t in trains.values() for s in t["shafts"]],
                              link=True)
    _part, part_path = _part_with_axis(px, folder, f"{CIP_STEM} Gear")
    paths = {"assembly": asm_path, "layout": layout_path, "part": part_path}
    asm = Assembly(px, layout_path, {"cyl": part_path})
    facts: Dict[str, Any] = {}
    made: List[Dict[str, Any]] = []
    renamed: List[Dict[str, Any]] = []
    names: Dict[str, str] = {}
    try:
        asm.open()
        doc = asm.doc
        for t in trains.values():
            for g in t["gears"]:
                asm.add(g["key"], "cyl", g["sigma"], g["theta"], g["at"])
        call(doc, "ForceRebuild3", True)
        placed = _frames(asm.gears)
        facts["cip_on"] = _command_in_progress(px, True)
        try:
            for name, t in trains.items():
                g1, g2, g3, g4 = t["gears"]
                for g in t["gears"]:
                    if g is g3:
                        px.require(unfix(px, doc, asm.gears[g["key"]]), f"{g['key']} floats")
                        continue
                    mount(px, asm, g["key"], g["shaft"], g["sigma"], g["at"][2], g["at"], record=made,
                          rename=wanted[g["key"]], renamed=renamed)
                for a, b in ((g1, g2), (g3, g4)):
                    picked = select_in(px, doc, asm.gears[a["key"]], "Gear Axis", "AXIS", False) and \
                        select_in(px, doc, asm.gears[b["key"]], "Gear Axis", "AXIS", True)
                    px.require(bool(picked), f"{a['key']} and {b['key']}'s axes select")
                    result = add_mate(px, doc, f"{a['key']}-{b['key']} gear", enums["gear"], enums["closest"],
                                      flip=needed_flip(rule, a["sigma"], b["sigma"], False, a["teeth"] > b["teeth"]),
                                      ratio=(float(a["teeth"]), float(b["teeth"])))
                    made.append(result)
                    renamed.append(rename_at_once(px, doc, result, wanted[f"{a['key']}-{b['key']}"]))
                px.require(bool(select_components(px, doc, (asm.gears[g2["key"]], asm.gears[g3["key"]]))),
                           f"{name}: G2 and G3 select")
                result = add_mate(px, doc, f"{name}: lock", enums["lock"], enums["closest"])
                made.append(result)
                renamed.append(rename_at_once(px, doc, result, wanted[f"{name} lock"]))
            facts["rebuild"] = rebuild(px, doc, "the one top-only rebuild, CommandInProgress on", top_only=True)
        finally:
            facts["cip_off"] = _command_in_progress(px, False)
        facts["renamed_at_once"] = renamed
        facts["statuses"] = {m.get("name"): m.get("status") for m in made}
        facts["mate_states"] = mate_states(px, doc)
        facts["constrained"] = {k: constrained(px, c) for k, c in asm.gears.items()}
        facts["off_placed"] = worst(_off(asm.gears, placed))
        # Driven, as the probes drive (the angle mate on the global "Drive"), CommandInProgress off.
        add = adder(px, call(doc, "GetEquationMgr"))
        px.require(add(f'"{DRIVE}"= {DRIVE_FROM:g}') >= 0, "the drive global is added")
        for name, t in trains.items():
            g1 = asm.gears[t["gears"][0]["key"]]
            px.require(drive_mate(px, doc, g1, _plane_names(g1)[1], asm.layout, _plane_names(asm.layout)[1], name,
                                  add, enums["closest"]) is not None, f"{name}: the input is driven")
        rebuild(px, doc, "drive added", top_only=True)
        facts["constrained_driven"] = {k: constrained(px, c) for k, c in asm.gears.items()}
        facts["turns"] = _drive_by(px, doc, asm.gears, DRIVE_TO - DRIVE_FROM, "driven 30°")

        # A conflicting mate under CommandInProgress: an angle between TG3's and TG2's Top planes fighting the lock.
        t = trains["all Z+"]
        p2, p3 = asm.gears[t["gears"][1]["key"]], asm.gears[t["gears"][2]["key"]]
        rel = abs(unwrap(relative_angle(p2, p3)))
        conflict_angle = min(rel + CIP_CONFLICT, 179.0) if rel < 170.0 else rel - CIP_CONFLICT
        c: Dict[str, Any] = {"cip_on": _command_in_progress(px, True)}
        try:
            picked = select_in(px, doc, p3, _plane_names(p3)[1], "PLANE", False) and \
                select_in(px, doc, p2, _plane_names(p2)[1], "PLANE", True)
            c["selected"] = bool(picked)
            c["mate"] = add_mate(px, doc, f"an angle {conflict_angle:g}° fighting the lock, CommandInProgress on",
                                 enums["angle"], enums["closest"], angle=conflict_angle)
            c["rebuild"] = rebuild(px, doc, "over-defined, CommandInProgress on", top_only=True)
        finally:
            c["cip_off"] = _command_in_progress(px, False)
        conflict = c["mate"]["name"] or (c["mate"]["made"] or [None])[0]
        c["states"] = mate_states(px, doc)
        # A suppressed mate's error code and warning flag: the conflicting one, then a sound one (the lock).
        lock = wanted["all Z+ lock"]
        if conflict:
            c["conflict_suppressed_by"] = suppress(px, doc, conflict, True)
            rebuild(px, doc, "the conflicting mate suppressed", top_only=True)
            c["conflict_suppressed"] = mate_states(px, doc).get(conflict)
        c["lock_suppressed_by"] = suppress(px, doc, lock, True)
        rebuild(px, doc, "the lock suppressed", top_only=True)
        c["lock_suppressed"] = mate_states(px, doc).get(lock)
        c["lock_unsuppressed_by"] = suppress(px, doc, lock, False)
        if conflict:
            c["deleted_by"] = delete_mate(px, doc, conflict)
        rebuild(px, doc, "the conflict deleted, the lock back on", top_only=True)
        c["states_after"] = errors_only(mate_errors(px, doc))
        facts["conflict"] = c
        facts["mates_before_save"] = mate_names(doc)
        px.require(_save_in_place(px, doc, asm_path, "the CommandInProgress train") and os.path.isfile(asm_path),
                   "the train saves")
        px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
        names = asm.names()
    finally:
        if asm.doc is not None and not str(call(asm.doc, "GetPathName") or ""):
            sc.close(px, asm.doc)
        _close_quietly(px, list(paths.values()))

    reopened: Dict[str, Any] = {}
    try:
        doc, components = _open_train(px, asm_path, names)
        reopened["flags_on_open"] = _save_flags(px, paths)
        reopened["mates"] = mate_names(doc)
        reopened["found"] = {r["to"]: find_mate_by(px, doc, r["to"]) for r in renamed}
        reopened["errors"] = errors_only(mate_errors(px, doc))
        # SetSuppression2(unsuppress) on a lock that is already on: what it answers, and what it marks.
        lock = wanted["all Z+ lock"]
        feature = mate_feature(doc, lock)
        u: Dict[str, Any] = {"suppressed_before": is_suppressed(px, feature)}
        got, value = px.attempt(f"SetSuppression2(unsuppress) on {lock}, already on",
                                lambda: call(feature, "SetSuppression2", enums["unsuppress"],
                                             enums["this_configuration"], None))
        u["returned"] = plain(value) if got else "raised"
        u["suppressed_after"] = is_suppressed(px, feature)
        u["errors_after"] = errors_only(mate_errors(px, doc))
        u["flags_after"] = _save_flags(px, paths)
        rebuild(px, doc, "after unsuppressing a lock already on", top_only=True)
        u["errors_after_rebuild"] = errors_only(mate_errors(px, doc))
        u["flags_after_rebuild"] = _save_flags(px, paths)
        reopened["unsuppress_on"] = u
    finally:
        _close_quietly(px, list(paths.values()))
    facts["reopened"] = reopened
    px.fact("mates_under_command_in_progress", facts)
    px.shared["w8_cip_train"] = {"path": asm_path, "layout": layout_path, "part": part_path, "names": names,
                                 "trains": trains, "mates": wanted}

    # -- what it says
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    states = facts["mate_states"]
    clean = all(v == findings.ADD_MATE_NO_ERROR for v in facts["statuses"].values()) and \
        all(st.get("code") == 0 and st.get("suppressed") is False for st in states.values()) and \
        all(v == findings.COMPONENT_UNDER_DEFINED for v in facts["constrained"].values()) and \
        facts["off_placed"] < TOLERANCE_MM
    px.check(clean, f"under CommandInProgress every AddMate5 answered {set(facts['statuses'].values())}, every mate "
                    f"code 0 and on, every gear under-defined, none moved ({facts['off_placed']:.1e})")
    turned = all(v == findings.COMPONENT_FULLY_DEFINED for v in facts["constrained_driven"].values()) and all(
        _train_ok(facts["turns"], [g["key"] for g in t["gears"]], expected, DRIVE_TO - DRIVE_FROM)
        for t in trains.values())
    px.check(turned, f"one drive fully defines it and it turns 1/12 the same way: {facts['turns']}")
    c = facts["conflict"]
    shows = c["mate"].get("status") == findings.ADD_MATE_OVER_DEFINED and bool(errors_only(c["states"]))
    px.check(shows, f"a conflicting mate under CommandInProgress: AddMate5 {c['mate'].get('status')}, errors "
                    f"{errors_only(c['states'])}")
    px.fact("suppressed_mate_error_codes", {"conflicting": c.get("conflict_suppressed"), "sound": c["lock_suppressed"]},
            "GetErrorCode2, its warning flag and IsSuppressed2 on a suppressed mate")
    at_once = all(r.get("reads") == r["to"] and r.get("walk_finds") for r in renamed) and len(renamed) == len(made)
    after = all(all(v.values()) for v in reopened["found"].values()) and \
        not any(r["made_as"] in reopened["mates"] for r in renamed if r["made_as"] != r["to"])
    px.check(at_once, f"each mate renamed straight after its AddMate5 read its new name back at once and the walk "
                      f"found it: {[(r['made_as'], r.get('reads')) for r in renamed]}")
    px.check(after, f"saved and reopened, each is found by its new name and no first name is left: {reopened['found']}")
    px.fact("mate_rename_at_once_holds", bool(at_once and after))
    u = reopened["unsuppress_on"]
    px.fact("unsuppress_on_a_lock_already_on", {"returned": u["returned"], "suppressed_after": u["suppressed_after"],
                                                "errors": u["errors_after"], "marks_assembly": u["flags_after"]["assembly"]})
    px.fact("mates_under_command_in_progress_hold", bool(clean and turned and shows and not c["states_after"]))


MATE_FOLDER = "Probe W8 Mate Folder"


@probe("mate_folders", needs=("mates_under_command_in_progress",), tier=8,
       members=("IFeatureManager.InsertFeatureTreeFolder2", "IFeature.GetFirstSubFeature", "IModelDoc2.FeatureByName",
                "IFeature.GetTypeName2"))
def mate_folders(px: Px) -> None:
    """One of the train's own mates and an extra, sound angle mate put in a folder of the MateGroup, if the type
    library lists a call that makes one: what the mate-group walk, FeatureByName and GetTypeName2 then see."""
    enums = _enums(px)
    info = px.shared.get("w8_cip_train")
    px.require(bool(info), "mates_under_command_in_progress left a train")
    members = typelib_members(px, "IFeatureManager")
    listed = sorted(n for n in members if "Folder" in n)
    px.fact("feature_manager_folder_members", listed)
    paths = [info["path"], info["layout"], info["part"]]
    facts: Dict[str, Any] = {"listed": listed}
    try:
        doc, components = _open_train(px, info["path"], info["names"])
        facts["types_before"] = sorted({t for _n, t in _mate_features(doc)})
        t = info["trains"]["all Z+"]
        g1, g2 = components[t["gears"][0]["key"]], components[t["gears"][1]["key"]]
        # The drive suppressed, so an angle mate between G1's and G2's Top planes at their angle now is sound.
        facts["drive_suppressed_by"] = suppress(px, doc, f"{DRIVE} all Z+", True)
        angle = abs(unwrap(relative_angle(g1, g2))) % 180.0
        px.require(1.0 < angle < 179.0, f"G1's and G2's Top planes are {angle:g}° apart, an angle a mate can hold")
        picked = select_in(px, doc, g2, _plane_names(g2)[1], "PLANE", False) and \
            select_in(px, doc, g1, _plane_names(g1)[1], "PLANE", True)
        extra = add_mate(px, doc, f"an extra angle {angle:g}° between G1 and G2", enums["angle"], enums["closest"],
                         angle=angle) if picked else {"name": None}
        facts["extra"] = extra
        rebuild(px, doc, "the extra angle mate", top_only=True)
        facts["extra_errors"] = errors_only(mate_errors(px, doc))
        own = info["mates"]["all Z+ lock"]
        if "InsertFeatureTreeFolder2" not in members or not extra.get("name"):
            facts["folder"] = "not tried: " + ("no InsertFeatureTreeFolder2 in sldworks.tlb" if
                                              "InsertFeatureTreeFolder2" not in members else "the extra mate failed")
        elif "swFeatureTreeFolder_Containing" not in (types := sc.swconst(px, "swFeatureTreeFolderType_e")):
            facts["folder_types"] = types
            facts["folder"] = "not tried: swconst.tlb's swFeatureTreeFolderType_e has no swFeatureTreeFolder_Containing"
        else:
            facts["folder_types"] = types
            call(doc, "ClearSelection2", True)
            selected = [bool(call(mate_feature(doc, n), "Select2", i > 0, 0)) for i, n in enumerate((own, extra["name"]))]
            facts["selected"] = selected
            before = mate_names(doc)
            got, folder = px.attempt("IFeatureManager.InsertFeatureTreeFolder2(swFeatureTreeFolder_Containing)",
                                     lambda: call(sc.feature_manager(doc), "InsertFeatureTreeFolder2",
                                                  types["swFeatureTreeFolder_Containing"]))
            call(doc, "ClearSelection2", True)
            facts["folder_made"] = got and folder is not None
            if facts["folder_made"]:
                facts["folder_type"] = sc.type_name(folder)
                facts["folder_name"] = px.attempt("rename the folder", lambda: setattr(folder, "Name", MATE_FOLDER))[0] \
                    and str(call(folder, "Name"))
            rebuild(px, doc, "the folder made", top_only=True)
            walk = []
            for feature in sc.top_features(doc):
                if sc.type_name(feature) == "MateGroup":
                    child = call(feature, "GetFirstSubFeature")
                    while child is not None:
                        entry = {"name": str(call(child, "Name")), "type": sc.type_name(child)}
                        inner = call(child, "GetFirstSubFeature")
                        kids = []
                        while inner is not None:
                            kids.append({"name": str(call(inner, "Name")), "type": sc.type_name(inner)})
                            inner = call(inner, "GetNextSubFeature")
                        if kids:
                            entry["sub_features"] = kids
                        walk.append(entry)
                        child = call(child, "GetNextSubFeature")
            facts["walk"] = walk
            facts["walk_before"] = before
            for n in (own, extra["name"]):
                got, found = px.attempt(f"FeatureByName({n!r}) inside the folder", lambda n=n: call(doc, "FeatureByName", n))
                facts.setdefault("feature_by_name", {})[n] = {"found": bool(got and found is not None),
                                                              "type": sc.type_name(found) if got and found else None}
            facts["mate_group_walk_finds"] = {n: n in [w["name"] for w in walk] for n in (own, extra["name"])}
            facts["errors_after"] = errors_only(mate_errors(px, doc))
    finally:
        _close_quietly(px, paths)
    px.fact("mate_folders", facts)
    seen = sorted({w["type"] for w in facts.get("walk", [])} | {k["type"] for w in facts.get("walk", [])
                                                                 for k in w.get("sub_features", [])}
                  | set(facts.get("types_before", [])))
    px.fact("mate_group_sub_feature_types", seen, "every GetTypeName2 met walking the MateGroup")
    if facts.get("folder_made"):
        px.fact("mate_group_walk_sees_mates_in_a_folder", all(facts["mate_group_walk_finds"].values()))
        px.fact("feature_by_name_finds_mates_in_a_folder", all(v["found"] for v in facts["feature_by_name"].values()))
    else:
        px.fact("mate_group_walk_sees_mates_in_a_folder", None, f"not probed: {facts.get('folder')}")


@probe("lightweight_remake", needs=("motion_update",), tier=8,
       members=("ISldWorks.OpenDoc6 lightweight", "IComponent2.GetSuppression2", "IComponent2.FeatureByName",
                "IAssemblyDoc.AddMate5 gear"))
def lightweight_remake(px: Px) -> None:
    """The saved train opened with its components lightweight, if OpenDoc6 can make them so: does a component's
    "Gear Axis" select, and does the remake (delete the gear mate, AddMate5 again) make the mate and turn right?"""
    info = px.shared.get("w8_train")
    px.require(bool(info), "mated_train left a train")
    options = sc.swconst(px, "swOpenDocOptions_e")
    states = sc.swconst(px, "swComponentSuppressionState_e")
    px.fact("lightweight_enums", {"open": options.get("swOpenDocOptions_LoadLightweight"),
                                  "states": {k: v for k, v in states.items() if "ight" in k or "esolved" in k}})
    _i, path = _train_copy(px, f"{RATIO_ASSEMBLY} Lightweight")
    paths = [path, info["layout"], info["part"]]
    t = info["trains"]["all Z+"]
    g1, g2, g3, g4 = t["gears"]
    keys = [g["key"] for g in t["gears"]]
    others = [g["key"] for g in info["trains"]["middle Z-"]["gears"]]
    name = info["mates"][f"{g3['key']}-{g4['key']}"]["name"]
    facts: Dict[str, Any] = {"attempts": []}
    names_of = {v: k for k, v in states.items()}
    silent = int(findings.OPEN_DOC_SILENT or 1)
    light = int(options.get("swOpenDocOptions_LoadLightweight") or 0)
    override = int(options.get("swOpenDocOptions_OverrideDefaultLoadLightweight") or 0)
    tries = [("silent and lightweight", silent | light)]
    if override:
        tries.append(("silent, lightweight, overriding the default", silent | light | override))
    got, pid = px.attempt("ISldWorks.GetProcessID", lambda: call(sc.app(px), "GetProcessID"))
    px.require(got and isinstance(pid, int) and pid > 0, f"GetProcessID answered the session's process ({pid!r})")
    try:
        for label, flags in tries:
            errors, warnings = sc.out_long(), sc.out_long()
            # Watched: on 2026 the open with the override made the components lightweight, and an add-in
            # (SOLIDWORKS CAM) answered with a modal error box that blocked OpenDoc6 until it was closed.
            with DialogWatch(pid) as watch:
                got, result = px.attempt(f"OpenDoc6({os.path.basename(path)}, options {flags}: {label})",
                                         lambda flags=flags: call(sc.app(px), "OpenDoc6", path, sc.SW_DOC_ASSEMBLY,
                                                                  flags, "", errors, warnings))
            facts.setdefault("dialogs", {})[label] = watch.report()
            doc = result[0] if got and isinstance(result, tuple) else result
            px.require(got and doc is not None, "the train opens")
            title = str(call(doc, "GetTitle"))
            if title not in px.shared.setdefault("created", []):
                px.shared["created"].append(title)
            components = {k: call(doc, "GetComponentByName", n) for k, n in info["names"].items()}
            facts["suppression"] = {k: names_of.get(int(call(c, "GetSuppression2")), int(call(c, "GetSuppression2")))
                                    for k, c in components.items()}
            lightweight = {k: "ightweight" in str(v) for k, v in facts["suppression"].items()}
            facts["lightweight"] = lightweight
            facts["attempts"].append({"how": label, "options": flags, "suppression": facts["suppression"]})
            if any(lightweight.values()):
                break
            _close_quietly(px, paths)
        if any(facts["lightweight"].values()):
            for k in (g3["key"], g4["key"]):
                got, feature = px.attempt(f"FeatureByName('Gear Axis') on {k}, lightweight",
                                          lambda k=k: call(components[k], "FeatureByName", "Gear Axis"))
                facts.setdefault("gear_axis", {})[k] = {"found": bool(got and feature is not None)}
            facts["turns_before"] = _drive_by(px, doc, components, RATIO_STEP, "driven, lightweight")
            facts["remake"] = remake_gear_mate(px, doc, info["names"], name, g3["key"], g4["key"],
                                               (float(g3["teeth"]), float(RATIO_NEW)), name)
            rebuild(px, doc, "remade, lightweight", top_only=TOP_ONLY)
            facts["errors"] = errors_only(mate_errors(px, doc))
            facts["turns"] = _drive_by(px, doc, components, RATIO_STEP, "driven after the remake, lightweight")
            facts["suppression_after"] = {k: names_of.get(int(call(c, "GetSuppression2")), int(call(c, "GetSuppression2")))
                                          for k, c in components.items()}
    finally:
        _close_quietly(px, paths)
    px.fact("lightweight_remake", facts)
    px.fact("lightweight_open_dialogs", {label: [[w["title"], w["children"]] for w in r["windows"]]
                                         for label, r in facts.get("dialogs", {}).items()},
            "the windows SolidWorks opened while each OpenDoc6 was blocked (each closed by WM_CLOSE)")
    if not any(facts.get("lightweight", {}).values()):
        px.fact("lightweight_remake_holds", None, f"not probed: OpenDoc6 left every component "
                                                 f"{set(facts.get('suppression', {}).values())}, by "
                                                 f"{[a['how'] for a in facts['attempts']]}")
        return
    new_expected = train_turns((g1["teeth"], g2["teeth"], g3["teeth"], RATIO_NEW), (1, 1, 1, 1))
    holds = bool((facts.get("remake") or {}).get("name")) and not facts.get("errors") and \
        _ratio_turns_right(facts.get("turns") or {}, keys, others, new_expected)
    px.check(True, f"lightweight: Gear Axis {facts.get('gear_axis')}, remade by "
                   f"{(facts.get('remake') or {}).get('selected')}, turns {facts.get('turns')}")
    px.fact("lightweight_remake_holds", holds)


SECOND_ASSEMBLY = "Probe W8 Second"


@probe("second_assembly_beside_unsaved", needs=("motion_update",), tier=8,
       members=("IModelDoc2.NewDocument assembly", "IAssemblyDoc.AddComponent5", "IModelDocExtension.SaveAs3",
                "ISldWorks.CloseDoc"))
def second_assembly_beside_unsaved(px: Px) -> None:
    """A refused build's assembly left open and unsaved, holding components from saved parts; then a second new
    assembly from the same parts, mated and saved to a path: any refusal or name clash, and whether both close."""
    enums = _enums(px)
    info = px.shared.get("w8_train")
    px.require(bool(info), "mated_train left a train")
    folder = os.path.dirname(info["path"])
    path = os.path.join(folder, f"{SECOND_ASSEMBLY}.SLDASM")
    _fresh(px, path)
    t = info["trains"]["all Z+"]
    g1 = t["gears"][0]
    facts: Dict[str, Any] = {"open_before": sc.open_titles(px)}
    docs: Dict[str, Any] = {}
    try:
        open_by_path(px, info["part"])           # a closed part does not go in (REUSE_ADD_ROUTE "opened")
        for label in ("unsaved", "second"):
            asm = Assembly(px, info["layout"], {"cyl": info["part"]})
            asm.open()
            docs[label] = asm
            asm.add(g1["key"], "cyl", g1["sigma"], g1["theta"], g1["at"])
            px.require(unfix(px, asm.doc, asm.gears[g1["key"]]), f"{label}: {g1['key']} floats")
            picked = select_in(px, asm.doc, asm.gears[g1["key"]], "Gear Axis", "AXIS", False) and \
                select_in(px, asm.doc, asm.layout, f"{g1['shaft']} Axis", "AXIS", True)
            made = add_mate(px, asm.doc, f"{label}: {g1['key']} on its axis", enums["coincident"], enums["closest"]) \
                if picked else {"name": None}
            px.shared.setdefault("created", []).append(str(call(asm.doc, "GetTitle")))
            facts[label] = {"title": str(call(asm.doc, "GetTitle")), "mate": made,
                            "components": [str(call(c, "Name2")) for c in asm.gears.values()]}
        facts["second"]["saved"] = _save_in_place(px, docs["second"].doc, path, "the second assembly")
        facts["second"]["path"] = str(call(docs["second"].doc, "GetPathName") or "")
        facts["second"]["title_after_save"] = str(call(docs["second"].doc, "GetTitle"))
        if facts["second"]["title_after_save"] not in px.shared["created"]:
            px.shared["created"].append(facts["second"]["title_after_save"])   # SaveAs3 gave it the file's name
        facts["open_with_both"] = sc.open_titles(px)
    finally:
        facts["close_second"] = _close_quietly(px, [path])
        unsaved = docs.get("unsaved")
        if unsaved is not None and unsaved.doc is not None:
            try:
                sc.close(px, unsaved.doc)
                facts["close_unsaved"] = "closed"
            except Exception as exc:  # noqa: BLE001 - the evidence
                facts["close_unsaved"] = f"raised {exc}"
        facts["close_parts"] = _close_quietly(px, [info["layout"], info["part"]])
        facts["open_after"] = sc.open_titles(px)
    px.fact("second_assembly_beside_unsaved", facts)
    saved = bool(facts["second"].get("saved")) and os.path.isfile(path) and \
        os.path.normcase(facts["second"].get("path", "")) == os.path.normcase(path)
    both_mated = all((facts[k]["mate"] or {}).get("name") for k in ("unsaved", "second"))
    closed = not [x for x in facts["open_after"] if x not in facts["open_before"]]
    px.check(saved and both_mated, f"beside the unsaved {facts['unsaved']['title']}, a second new assembly took the same "
                                   f"parts, its mate, and saved to its path: {facts['second']}")
    px.check(closed, f"both closed afterwards: left {facts['open_after']}")
    px.fact("second_assembly_beside_unsaved_holds", bool(saved and both_mated and closed))


# -- 14c: an unsaved Update closed with its parts left modified (round P0c, review addition 2) ------------------
#
# On SolidWorks 2024 CloseDoc on an assembly whose saved parts had changed opened a modal "Save Modified Documents"
# dialog (scaffold.save_created_parts), and a modal dialog blocks every COM call. So every close here is watched
# from a thread of its own, which uses no COM: it records any window SolidWorks opens while the call is blocked,
# and after a few seconds closes it (WM_CLOSE, then Escape, then a "Cancel" button), the least destructive answer.

WM_CLOSE, WM_KEYDOWN, WM_KEYUP, VK_ESCAPE, BM_CLICK = 0x0010, 0x0100, 0x0101, 0x1B, 0x00F5


class DialogWatch:
    """Windows of one process that appear while a blocking call runs: their title, class and child texts, how long
    they stood, and how they were answered. Uses user32 only (no COM), from its own thread."""

    def __init__(self, pid: int, dismiss_after: float = 5.0) -> None:
        import threading  # noqa: PLC0415
        self.pid, self.dismiss_after = int(pid), dismiss_after
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._seen: Dict[int, Dict[str, Any]] = {}
        self._before: set = set()
        self.error: Optional[str] = None

    @staticmethod
    def _user32() -> Any:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415
        u = ctypes.windll.user32
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u.IsWindow.argtypes = [wintypes.HWND]
        return u

    def _windows(self) -> List[int]:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415
        u = self._user32()
        found: List[int] = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def each(hwnd: Any, _l: Any) -> bool:
            pid = wintypes.DWORD()
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == self.pid and u.IsWindowVisible(hwnd):
                found.append(int(hwnd))
            return True

        u.EnumWindows(proc(each), 0)
        return found

    def _text(self, hwnd: int) -> Tuple[str, str]:
        import ctypes  # noqa: PLC0415
        u = self._user32()
        title, cls = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, title, 512)
        u.GetClassNameW(hwnd, cls, 256)
        return title.value, cls.value

    def _children(self, hwnd: int) -> List[Tuple[int, str, str]]:
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415
        u = self._user32()
        out: List[Tuple[int, str, str]] = []
        proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def each(child: Any, _l: Any) -> bool:
            if len(out) < 60:
                out.append((int(child), *self._text(int(child))))
            return True

        u.EnumChildWindows(hwnd, proc(each), 0)
        return out

    def _run(self) -> None:
        try:
            u = self._user32()
            while not self._stop.wait(0.25):
                now = time.monotonic()
                for hwnd in self._windows():
                    if hwnd in self._before:
                        continue
                    seen = self._seen.setdefault(hwnd, {"first": now, "answered": []})
                    title, cls = self._text(hwnd)
                    seen.update(title=title, cls=cls, last=now,
                                children=[[c, t] for _h, t, c in self._children(hwnd) if t][:30])
                    age = now - seen["first"]
                    if age >= self.dismiss_after and not seen["answered"]:
                        u.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                        seen["answered"].append(f"WM_CLOSE at {age:.1f} s")
                    elif age >= 2 * self.dismiss_after and len(seen["answered"]) == 1:
                        u.PostMessageW(hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
                        u.PostMessageW(hwnd, WM_KEYUP, VK_ESCAPE, 0)
                        seen["answered"].append(f"Escape at {age:.1f} s")
                    elif age >= 3 * self.dismiss_after and len(seen["answered"]) == 2:
                        cancel = [h for h, t, _c in self._children(hwnd) if t.replace("&", "").strip() == "Cancel"]
                        for h in cancel[:1]:
                            u.PostMessageW(h, BM_CLICK, 0, 0)
                        seen["answered"].append(f"Cancel clicked at {age:.1f} s" if cancel else
                                                f"no Cancel button at {age:.1f} s")
        except Exception as exc:  # noqa: BLE001 - the watch failing is evidence, never a crash of the probe
            self.error = repr(exc)

    def __enter__(self) -> "DialogWatch":
        try:
            self._before = set(self._windows())
        except Exception as exc:  # noqa: BLE001
            self.error = repr(exc)
        self._started = time.monotonic()
        self._thread.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        self._stop.set()
        self._thread.join(5.0)

    def report(self) -> Dict[str, Any]:
        windows = [{"title": s.get("title"), "class": s.get("cls"), "children": s.get("children"),
                    "stood_s": round(s.get("last", s["first"]) - s["first"], 2), "answered": s["answered"]}
                   for s in self._seen.values()]
        return {"windows": windows, "watch_error": self.error}


def watched_close(px: Px, how: str, title: str, pid: int) -> Dict[str, Any]:
    """``ISldWorks.CloseDoc`` or ``ISldWorks.QuitDoc`` on one of the probe's own documents, watched for a dialog:
    what it returned or raised, how long it took, and what windows stood meanwhile."""
    if title not in px.shared.get("created", []):
        raise Require(f"Refusing to close {title}: the probe did not create it.")
    started = time.monotonic()
    with DialogWatch(pid) as watch:
        got, result = px.attempt(f"{how}({title}) with its parts modified", lambda: call(sc.app(px), how, title))
    out = {"how": how, "title": title, "returned": plain(result) if got else None,
           "raised": None if got else plain(result), "seconds": round(time.monotonic() - started, 2),
           **watch.report()}
    out["dialog"] = bool(out["windows"])
    return out


def _disk(paths: Sequence[str]) -> Dict[str, Optional[float]]:
    return {os.path.basename(p): (os.path.getmtime(p) if os.path.isfile(p) else None) for p in paths}


def _open_probe_docs(px: Px, paths: Sequence[str]) -> Dict[str, Any]:
    """The probe's documents at these paths still open, with their save flags."""
    from .p7_workbook import _doc_at  # noqa: PLC0415
    out: Dict[str, Any] = {}
    for p in paths:
        doc = _doc_at(px, p)
        if doc is not None:
            out[os.path.basename(p)] = {"modified": bool(call(doc, "GetSaveFlag")), "visible": bool(call(doc, "Visible"))}
    return out


CLOSE_ROUTES = ("CloseDoc", "QuitDoc")


@probe("unsaved_update_close", needs=("gear_mate_update",), tier=8,
       members=("ISldWorks.CloseDoc", "ISldWorks.QuitDoc", "ISldWorks.GetProcessID", "IModelDoc2.GetSaveFlag"))
def unsaved_update_close(px: Px) -> None:
    """The app's own state after an unsaved Update, closed: the 12 : 1 train gear_mate_update left saved, given a tooth
    change by the Update's whole sequence and NOT saved, its parts left modified; then the assembly closed by
    CloseDoc (and, on a second Update, by QuitDoc), and every part still open closed the same way. For each: what
    the call answered, any dialog, what stayed open, and what is on disk afterwards (file times and the teeth)."""
    from .. import swbuild  # noqa: PLC0415
    from .p7_workbook import _update_with, activate  # noqa: PLC0415

    info = px.shared.get("w8_update")
    px.require(bool(info), "gear_mate_update left its train")
    fx: UpdateFixture = info["fx"]
    jobs, paths, plan = info["jobs"], info["paths"], info["plan"]
    got, pid = px.attempt("ISldWorks.GetProcessID", lambda: call(sc.app(px), "GetProcessID"))
    px.require(got and isinstance(pid, int) and pid > 0, f"GetProcessID answered the session's process ({pid!r})")
    gears = [g for g, _ in fx.change]
    facts: Dict[str, Any] = {}
    for how in CLOSE_ROUTES:
        r: Dict[str, Any] = {}
        facts[how] = r
        try:
            doc, comps, layout, title = info["open_train"]()
            r["teeth_on_disk"] = {g: _teeth_global(px, jobs[g].path) for g in gears}
            back = r["teeth_on_disk"] == {g: float(fx.new_teeth()[g]) for g in gears}
            change = {g: str(fx.old_teeth()[g] if back else fx.new_teeth()[g]) for g in gears}
            r["change"] = change
            wanted = info["built"] if back else info["wanted"]
            r["update"] = _update_pass(px, swbuild, doc, title, comps, layout, jobs, wanted, fx=fx, change=change)
            px.require(activate(px, title), "the assembly is active again")
            r["teeth_in_memory"] = {g: _teeth_global(px, jobs[g].path) for g in gears}
            r["open_before"] = _open_probe_docs(px, paths)
            r["disk_before"] = _disk(paths)
            r["assembly"] = watched_close(px, how, title, pid)
            r["open_after_assembly"] = _open_probe_docs(px, paths)
            r["parts"] = []
            from .p7_workbook import _doc_at  # noqa: PLC0415
            for p in paths[1:]:
                part = _doc_at(px, p)
                if part is not None:
                    r["parts"].append(watched_close(px, how, str(call(part, "GetTitle")), pid))
            r["open_after"] = _open_probe_docs(px, paths)
            r["disk_after"] = _disk(paths)
            r["written"] = sorted(k for k in r["disk_after"] if r["disk_after"][k] != r["disk_before"][k])
        finally:
            # Anything still open is set back to what is on disk before the cleanup saves it, so the next route
            # starts from the saved train.
            left = _open_probe_docs(px, paths)
            r["cleanup_left"] = left
            if left and r.get("teeth_on_disk"):
                from ..gears import KINDS  # noqa: PLC0415
                for g in gears:
                    if os.path.basename(jobs[g].path) in left:
                        kind = KINDS[jobs[g].spec.kind]
                        want = jobs[g].spec.with_values(teeth=str(int(r["teeth_on_disk"][g])))
                        try:
                            _update_with(px, swbuild, jobs[g].path, kind.variables(want, kind.derive(want)))
                        except Exception as exc:  # noqa: BLE001 - noted; the close evidence is what matters
                            px.note(f"CLEANUP could not set {g} back: {exc}")
            _close_quietly(px, paths)
        # On disk afterwards: the parts' teeth, each part opened on its own and closed.
        r["teeth_on_disk_after"] = {}
        for g in gears:
            try:
                part, _ = open_by_path(px, jobs[g].path, prefer="OpenDoc6")
                t = str(call(part, "GetTitle"))
                if t not in px.shared["created"]:
                    px.shared["created"].append(t)
                r["teeth_on_disk_after"][g] = _teeth_global(px, jobs[g].path)
            finally:
                _close_quietly(px, [jobs[g].path])
        r["discarded"] = r["teeth_on_disk_after"] == r["teeth_on_disk"]
        r["all_closed"] = not r.get("open_after")
        r["dialog"] = bool(r.get("assembly", {}).get("dialog")) or any(c.get("dialog") for c in r.get("parts", []))
    px.fact("unsaved_update_close", facts)
    summary = {how: {"dialog": r.get("dialog"), "assembly_closed": os.path.basename(plan.assembly_path) not in
                     (r.get("open_after_assembly") or {}), "all_closed": r.get("all_closed"),
                     "discarded": r.get("discarded"), "written": r.get("written")} for how, r in facts.items()}
    px.check(True, f"an unsaved Update closed with its parts modified: {summary}")
    px.fact("unsaved_update_close_summary", summary)
    px.fact("unsaved_update_close_asks", {how: s["dialog"] for how, s in summary.items()})
    px.fact("unsaved_update_close_discards", {how: bool(s["discarded"] and s["all_closed"] and not s["written"])
                                              for how, s in summary.items()})


# -- 14d: the drag operator by the SW-Macro-Database recipe (round P0c, optional) --------------------------------
#
# SW-Macro-Database entries/assemblies/05 (verified on 2024 SP5): IDragOperator with AddComponent(component, False),
# TransformType = 0, UseAbsoluteTransform = False, DragMode left as it came, BeginDrag, then Drag given each of
# ``steps`` steps as a RELATIVE transform turning deg / steps about a fixed line, EndDrag; a Transform2 put of every
# snapshot and EditRebuild3 to restore. Its one success dragged the DRIVEN gear 30 degrees in 10 steps; tier 8 had
# dragged only the driving gear, in one call. Here the recipe exactly, then one thing varied at a time.

DRAG_ASSEMBLY = "Probe W8 Drag"
#: The entry turned its output 30 degrees; on the 12 : 1 that turns the input 360 degrees, which reads as no turn at
#: all, so every drag here is 10 degrees (the entry's second assembly used 5 x 2 = 10): the input then turns 120.
DRAG_DEGREES = 10.0
#: (label, which gear of the "all Z+" train by index, steps): the entry's recipe first, then one change each
DRAG_CASES = (("the output, 10 steps (the entry's success, 10 degrees)", 3, 10), ("the input, 10 steps", 0, 10),
              ("the compound follower, 10 steps", 2, 10), ("the output, 1 step", 3, 1),
              ("the output, 30 steps", 3, 30))
DRAG_TOLERANCE_DEG = 0.05


def drag_by_recipe(px: Px, doc: Any, component: Any, degrees: float, steps: int) -> Dict[str, Any]:
    """The entry's drag: every call and argument as it gives them, the line being the gear's own axis through its
    origin as it stood when the drag began. What each call answered."""
    out: Dict[str, Any] = {}
    got, op = px.attempt("IAssemblyDoc.GetDragOperator", lambda: member(doc, "GetDragOperator")[0])
    if not got or op is None:
        return {"operator": None}
    for key in ("TransformType", "DragMode", "UseAbsoluteTransform"):
        ok, value = px.attempt(f"IDragOperator.{key} as it came", lambda k=key: member(op, k)[0])
        out[f"{key} as it came"] = plain(value) if ok else "raised"
    out["AddComponent"] = plain(px.attempt("IDragOperator.AddComponent(component, False)",
                                           lambda: call(op, "AddComponent", component, False))[1])
    out["TransformType = 0"] = px.attempt("IDragOperator.TransformType = 0", lambda: setattr(op, "TransformType", 0))[0]
    out["UseAbsoluteTransform = False"] = px.attempt("IDragOperator.UseAbsoluteTransform = False",
                                                     lambda: setattr(op, "UseAbsoluteTransform", False))[0]
    out["BeginDrag"] = plain(px.attempt("IDragOperator.BeginDrag", lambda: member(op, "BeginDrag")[0])[1])
    m, o = frame_of(component)
    r, t = turn_about_point(column(m, 2), degrees / steps, o)
    oks = []
    try:
        for _ in range(steps):
            xform = make_transform(px, array_data(r, t, findings.TRANSFORM_ARRAY_ORDER or "columns"))
            ok, value = px.attempt("IDragOperator.Drag(relative step)", lambda x=xform: call(op, "Drag", x))
            oks.append(plain(value) if ok else "raised")
    finally:
        out["EndDrag"] = plain(px.attempt("IDragOperator.EndDrag", lambda: member(op, "EndDrag")[0])[1])
    out["Drag"] = oks
    return out


def drag_residuals(before: Mapping[str, Tuple[Matrix, Vec]], after: Mapping[str, Tuple[Matrix, Vec]],
                   keys: Sequence[str], expected: Sequence[float], dragged: str) -> Dict[str, Any]:
    """Each gear's turn about +Z, origin move (mm) and axis tilt (degrees), against the kinematics: every gear turns
    its share (``expected``, per degree of the first) of what the dragged gear turned."""
    turns = {k: world_turn(before[k][0], after[k][0]) for k in keys}
    share = dict(zip(keys, expected))
    out: Dict[str, Any] = {"turns": {k: round(v, 6) for k, v in turns.items()}, "residual_deg": {}, "origin_mm": {},
                           "axis_tilt_deg": {}}
    for k in keys:
        want = turns[dragged] * share[k] / share[dragged]
        out["residual_deg"][k] = round(abs(turns[k] - want), 6)
        out["origin_mm"][k] = round(math.dist(before[k][1], after[k][1]), 6)
        a, b = column(before[k][0], 2), column(after[k][0], 2)
        out["axis_tilt_deg"][k] = round(math.degrees(math.acos(max(-1.0, min(1.0, _dot(a, b))))), 6)
    return out


def drag_follows(res: Mapping[str, Any], dragged: str, asked: float) -> bool:
    """The dragged gear turned what was asked and the whole train followed at its ratio, on its axes, in place."""
    return bool(res["turns"] and abs(abs(res["turns"][dragged]) - abs(asked)) < DRAG_TOLERANCE_DEG
                and max(res["residual_deg"].values()) < DRAG_TOLERANCE_DEG
                and max(res["origin_mm"].values()) < TOLERANCE_MM and max(res["axis_tilt_deg"].values()) < 1e-3)


@probe("drag_operator_turns_train", needs=("motion_update",), tier=8,
       members=("IAssemblyDoc.GetDragOperator", "IDragOperator.AddComponent", "IDragOperator.TransformType",
                "IDragOperator.UseAbsoluteTransform", "IDragOperator.BeginDrag", "IDragOperator.Drag",
                "IDragOperator.EndDrag", "IComponent2.Transform2", "IModelDoc2.EditRebuild3"))
def drag_operator_turns_train(px: Px) -> None:
    """The saved 12 : 1 train, its drives suppressed so it can turn, dragged by the SW-Macro-Database recipe: the
    output 10 degrees in 10 relative steps (the entry's success, scaled to the 12 : 1), then the input, the compound follower, 1 step and
    30 steps. For each: every gear's frame against the kinematics, the mates' errors, the save flag, the selection
    and CommandInProgress afterwards; every gear put back by its snapshot and EditRebuild3 between cases."""
    info, path = _train_copy(px, DRAG_ASSEMBLY)
    paths = [path, info["layout"], info["part"]]
    t = info["trains"]["all Z+"]
    keys = [g["key"] for g in t["gears"]]
    others = [g["key"] for g in info["trains"]["middle Z-"]["gears"]]
    expected = train_turns(TRAIN_TEETH, (1, 1, 1, 1))
    drives = [f"{DRIVE} {name}" for name in info["trains"]]
    facts: Dict[str, Any] = {"recipe": "SW-Macro-Database entries/assemblies/05: AddComponent(c, False), "
                                       "TransformType 0, UseAbsoluteTransform False, DragMode as it came, relative "
                                       "Drag steps about the gear's axis, EndDrag; restore by Transform2 and "
                                       "EditRebuild3", "mate_kind": "axis coincident (AXIS_MATE_ROUTE), not varied",
                             "cases": {}}
    try:
        doc, comps = _open_train(px, path, info["names"])
        facts["drives_suppressed_by"] = {d: suppress(px, doc, d, True) for d in drives}
        facts["rebuild_undriven"] = rebuild(px, doc, "drives suppressed")
        facts["errors_undriven"] = errors_only(mate_errors(px, doc))
        snapshot = _frames(comps)

        def restore() -> float:
            for k, c in comps.items():
                matrix, at = snapshot[k]
                transform = make_transform(px, array_data(matrix, at, findings.TRANSFORM_ARRAY_ORDER or "columns"))
                px.attempt(f"Transform2 put on {k} (restore)", lambda c=c, x=transform: setattr(c, "Transform2", x))
            px.attempt("EditRebuild3 (restore)", lambda: call(doc, "EditRebuild3"))
            return worst(_off(comps, snapshot))

        for label, index, steps in DRAG_CASES:
            case: Dict[str, Any] = {"dragged": keys[index], "steps": steps, "asked_deg": DRAG_DEGREES}
            facts["cases"][label] = case
            case["restored_before_mm"] = restore()
            call(doc, "ClearSelection2", True)
            case["save_flag_before"] = bool(call(doc, "GetSaveFlag"))
            before = _frames(comps)
            case["calls"] = drag_by_recipe(px, doc, comps[keys[index]], DRAG_DEGREES, steps)
            after = _frames(comps)
            case["train"] = drag_residuals(before, after, keys, expected, keys[index])
            case["other_train_moved_deg"] = max(abs(world_turn(before[k][0], after[k][0])) for k in others)
            case["errors"] = errors_only(mate_errors(px, doc))
            case["save_flag_after"] = bool(call(doc, "GetSaveFlag"))
            ok, count = px.attempt("selections after the drag",
                                   lambda: call(call(doc, "SelectionManager"), "GetSelectedObjectCount2", -1))
            case["selected_after"] = plain(count) if ok else "raised"
            ok, cip = px.attempt("CommandInProgress after the drag", lambda: call(sc.app(px), "CommandInProgress"))
            case["command_in_progress_after"] = plain(cip) if ok else "raised"
            case["follows"] = drag_follows(case["train"], keys[index], DRAG_DEGREES) and not case["errors"] and \
                case["other_train_moved_deg"] < DRAG_TOLERANCE_DEG
        facts["restored_after_mm"] = restore()
    finally:
        _close_quietly(px, paths)
    px.fact("drag_operator", facts)
    held = [label for label, case in facts["cases"].items() if case["follows"]]
    px.check(True, "the drag operator by the entry's recipe: " + "; ".join(
        f"{label}: turns {c['train']['turns']}, residual {max(c['train']['residual_deg'].values()):.3g} deg, "
        f"Drag {c['calls'].get('Drag')}" for label, c in facts["cases"].items()))
    px.fact("drag_operator_turns_train", {"holds": bool(held), "recipes_that_held": held})


# -- 15 (last): a gear mate's ratio changed through its definition, recorded and never chosen ------------------
#
# Last in the tier on purpose: on SolidWorks 2024 the copy it changes cannot be closed, and it holds the train's
# layout part and gear part open with it, so nothing may run after it in the same session.

@probe("gear_mate_definition", needs=("motion_update",), tier=8,
       members=("IFeature.GetDefinition", "IGearMateFeatureData.GearRatioNumerator",
                "IGearMateFeatureData.GearRatioDenominator", "IMateFeatureData.AccessSelections",
                "IFeature.ModifyDefinition", "ISldWorks.CloseDoc"))
def gear_mate_definition_route(px: Px) -> None:
    """A saved gear mate's ratio changed through its definition, each recipe on its own copy: what it turns, what it
    reads back, and whether the copy can be closed afterwards. Recorded only: W5 never takes this route."""
    info = px.shared.get("w8_train")
    px.require(bool(info), "mated_train left a train")
    t = info["trains"]["all Z+"]
    g1, g2, g3, g4 = t["gears"]
    keys = [g["key"] for g in t["gears"]]
    others = [g["key"] for g in info["trains"]["middle Z-"]["gears"]]
    name = info["mates"][f"{g3['key']}-{g4['key']}"]["name"]
    new_expected = train_turns((g1["teeth"], g2["teeth"], g3["teeth"], RATIO_NEW), (1, 1, 1, 1))
    tries: List[Dict[str, Any]] = []
    for index, how in enumerate(RATIO_RECIPES):
        _info, path = _train_copy(px, f"{RATIO_ASSEMBLY} Definition {index + 1}")
        paths = [path, info["layout"], info["part"]]
        attempt: Dict[str, Any] = {"how": how, "copy": os.path.basename(path)}
        try:
            doc, components = _open_train(px, path, info["names"])
            attempt["rebuild_on_open"] = rebuild(px, doc, "opened", top_only=TOP_ONLY)
            attempt["turns_before"] = _drive_by(px, doc, components, RATIO_STEP, "driven before the change")
            attempt["definition"] = set_gear_ratio_by_definition(px, doc, name, how, g4["teeth"], RATIO_NEW,
                                                                 access=index == 0)
            attempt["rebuild"] = rebuild(px, doc, f"ratio changed: {how}", top_only=TOP_ONLY)
            attempt["errors"] = errors_only(mate_errors(px, doc))
            attempt["turns"] = _drive_by(px, doc, components, RATIO_STEP, f"driven after: {how}")
            attempt["right"] = attempt["definition"].get("modified") is True and not attempt["errors"] and \
                _ratio_turns_right(attempt["turns"], keys, others, new_expected)
        finally:
            attempt["close"] = _close_checked(px, path, paths)
            tries.append(attempt)
            px.fact(f"gear_mate_definition {index + 1}", attempt, f"{how}: recorded as soon as it finished")
        if attempt.get("right") or not attempt["close"]["closed"]:
            break                     # the first right recipe is enough; a copy that would not close ends the item
    px.fact("gear_mate_definition", {"mate": name, "tries": tries})
    for attempt in tries:
        px.check(True, f"{attempt['how']}: the output turned {(attempt.get('turns') or {}).get(keys[3])} "
                       f"({RATIO_STEP * new_expected[3]:.6f} wanted), definition after "
                       f"{(attempt.get('definition') or {}).get('after')}, closed afterwards {attempt['close']}")
    definition = (tries[0].get("definition") or {}).get("before") or {}
    px.fact("definition_numerator_is_second_teeth",
            definition.get("GearRatioNumerator") == g4["teeth"] and definition.get("GearRatioDenominator") == g3["teeth"]
            if definition else None)
    px.fact("definition_recipe", next((a["how"] for a in tries if a.get("right")), None),
            "the recipe that turned the train at the new ratio")
    px.fact("definition_closes", {a["how"]: a["close"]["closed"] for a in tries})
    px.check(True, f"recipes tried {len(tries)} of {len(RATIO_RECIPES)}: after the first right one, or the first copy "
                   f"that would not close, none is tried")
