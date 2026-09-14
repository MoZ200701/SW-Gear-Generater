"""Tier 4: an assembly, two components, and the mates a gear pair needs.

Two small parts are made and saved first, because AddComponent5 takes a path
and the API help says the file must already be loaded. The mates are the ones
the pair assembly uses: faces coplanar, one axis on the other's plane, a
distance between an axis and a plane — linked to a global — and an angle.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Tuple

from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p1_equations import adder
from .p2_solid import _blank

# swMateType_e, swMateAlign_e, swAddMateError_e, from swconst.tlb on SolidWorks 2026.
MATE_COINCIDENT = 0
MATE_DISTANCE = 5
MATE_ANGLE = 6
ALIGN_CLOSEST = 2
ADD_MATE_NO_ERROR = 1
SAVE_AS_SILENT = 1

CENTRE = 60.0   # mm


def _part_with_axis(px: Px, folder: str, stem: str) -> Tuple[Any, str]:
    """A saved r 20 x 10 mm cylinder with a Gear Axis, left open."""
    path = os.path.join(folder, f"{stem}.SLDPRT")
    if os.path.exists(path):
        raise Require(f"{path} already exists.")
    doc = sc.new_document(px)
    _blank(px, doc)
    if not (sc.select_plane(doc, 2) and sc.select_plane(doc, 3, append=True)):
        raise Require("Planes 2 and 3 could not be selected for the axis.")
    before = sc.feature_names(doc)
    call(doc, "InsertAxis2", True)
    call(doc, "ClearSelection2", True)
    sc.feature_by_name(doc, sc.new_features(doc, before)[0][0]).Name = "Gear Axis"
    result = call(sc.extension(doc), "SaveAs3", path, 0, SAVE_AS_SILENT, sc.null(), sc.null(), sc.out_long(),
                  sc.out_long())
    px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
    if not os.path.isfile(path):
        raise Require(f"{stem} did not save: {result!r}")
    return doc, path


def _plane_names(doc: Any) -> List[str]:
    return [str(call(p, "Name")) for p in sc.planes(doc)]


def _select_in_component(px: Px, asm: Any, component: Any, feature_name: str, kind: str,
                         append: bool, mark: int = 1) -> bool:
    """A component's plane or axis: FeatureByName then Select2, else SelectByID2 by full name."""
    before = sc.selected_count(asm)
    if not append:
        call(asm, "ClearSelection2", True)
        before = 0
    feature = call(component, "FeatureByName", feature_name)
    if feature is not None and sc._retrying(asm, lambda: call(feature, "Select2", append, mark), before,
                                            "component FeatureByName.Select2"):
        return True
    asm_name = os.path.splitext(str(call(asm, "GetTitle")))[0]
    full = f"{feature_name}@{call(component, 'Name2')}@{asm_name}"
    if call(sc.extension(asm), "SelectByID2", full, kind, 0.0, 0.0, 0.0, append, mark, sc.null(), 0) and \
            sc.selected_count(asm) > before:
        sc._count(f"SelectByID2 {kind} in component")
        return True
    return False


def _mate_features(asm: Any) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for feature in sc.top_features(asm):
        if sc.type_name(feature) == "MateGroup":
            child = call(feature, "GetFirstSubFeature")
            while child is not None:
                out.append((str(call(child, "Name")), sc.type_name(child)))
                child = call(child, "GetNextSubFeature")
    return out


def _mate(px: Px, asm: Any, label: str, kind: int, distance: float = 0.0, angle: float = 0.0) -> Optional[str]:
    before = [n for n, _ in _mate_features(asm)]
    got, result = px.attempt(
        f"AddMate5 {label}",
        lambda: call(asm, "AddMate5", kind, ALIGN_CLOSEST, False, distance, distance, distance, 1, 1,
                     angle, angle, angle, False, False, 0, sc.out_long()),
    )
    call(asm, "ClearSelection2", True)
    mate, status = (result[0], result[1]) if got and isinstance(result, tuple) else (result, None)
    px.fact(f"mate {label}", {"returned": type(mate).__name__ if got else "raised", "status": status})
    made = [n for n, _ in _mate_features(asm) if n not in before]
    if not px.check(got and mate is not None and len(made) == 1, f"{label}: one mate appears under Mates"):
        return None
    return made[0]


def _translation_mm(component: Any) -> Tuple[float, float, float]:
    data = call(call(component, "Transform2"), "ArrayData")
    return (float(data[9]) * sc.MM, float(data[10]) * sc.MM, float(data[11]) * sc.MM)


def _assembly(px: Px, with_link: bool) -> None:
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder), "there is a scratch folder to save parts in")
    tag = "Link" if with_link else "Add"
    part_a, path_a = _part_with_axis(px, folder, f"Probe {tag} A")
    part_b, path_b = _part_with_axis(px, folder, f"Probe {tag} B")
    planes = _plane_names(part_a)
    asm = sc.new_document(px, sc.SW_DOC_ASSEMBLY)
    try:
        ext = sc.extension(asm)
        linear = int(call(ext, "GetUserPreferenceInteger", sc.SW_UNITS_LINEAR, 0))
        if linear != sc.SW_MM:
            call(ext, "SetUserPreferenceInteger", sc.SW_UNIT_SYSTEM, 0, sc.SW_UNIT_SYSTEM_MMGS)
        px.fact("assembly_units_before_setting", linear)
        px.check(int(call(asm, "GetType")) == sc.SW_DOC_ASSEMBLY, "NewDocument from the assembly template is an assembly")

        got, first = px.attempt("AddComponent5(part A at the origin)",
                                lambda: call(asm, "AddComponent5", path_a, 0, "", False, "", 0.0, 0.0, 0.0))
        got2, second = px.attempt("AddComponent5(part B at 60 mm)",
                                  lambda: call(asm, "AddComponent5", path_b, 0, "", False, "", CENTRE / sc.MM, 0.0, 0.0))
        px.require(got and got2 and first is not None and second is not None, "both components are inserted")
        names = (str(call(first, "Name2")), str(call(second, "Name2")))
        px.fact("component_names", names)
        px.fact("component_b_translation_mm_as_inserted", _translation_mm(second))

        got, fixed = px.attempt("IsFixed of the first component", lambda: call(first, "IsFixed"))
        px.fact("first_component_fixed_on_insert", fixed if got else "raised")
        call(asm, "ClearSelection2", True)
        px.require(bool(call(first, "Select4", False, sc.null(), False)), "the first component selects")
        # FixComponent takes no arguments, so call() would only fetch it: an earlier
        # version of this probe got back a bound method and never ran it.
        got, _ = px.attempt("FixComponent() on the already fixed first component", lambda: asm.FixComponent())
        call(asm, "ClearSelection2", True)
        px.check(bool(call(first, "IsFixed")), "the first component is fixed")

        front, top, right = planes[0], planes[1], planes[2]
        px.require(_select_in_component(px, asm, second, front, "PLANE", False) and
                   _select_in_component(px, asm, first, front, "PLANE", True), "the two front planes select")
        _mate(px, asm, "coincident fronts", MATE_COINCIDENT)
        px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                   _select_in_component(px, asm, first, top, "PLANE", True), "B's axis and A's top plane select")
        _mate(px, asm, "axis on top plane", MATE_COINCIDENT)
        px.require(_select_in_component(px, asm, second, "Gear Axis", "AXIS", False) and
                   _select_in_component(px, asm, first, right, "PLANE", True), "B's axis and A's right plane select")
        distance = _mate(px, asm, "distance axis to right plane", MATE_DISTANCE, distance=CENTRE / sc.MM)
        px.require(_select_in_component(px, asm, second, top, "PLANE", False) and
                   _select_in_component(px, asm, first, top, "PLANE", True), "the two top planes select")
        angle = _mate(px, asm, "angle between top planes", MATE_ANGLE, angle=math.radians(3.0))

        call(asm, "ForceRebuild3", False)
        where = _translation_mm(second)
        px.fact("component_b_translation_mm_mated", where)
        px.check(abs(math.hypot(where[0], where[1]) - CENTRE) < 1e-6, f"B sits {CENTRE} mm from A's axis: {where}")

        if distance is not None:
            feature = None
            for mate in sc.top_features(asm):
                if sc.type_name(mate) == "MateGroup":
                    child = call(mate, "GetFirstSubFeature")
                    while child is not None:
                        if str(call(child, "Name")) == distance:
                            feature = child
                        child = call(child, "GetNextSubFeature")
            px.require(feature is not None, "the distance mate is found in the tree")
            feature.Name = "Centre Distance"
            px.check(str(call(feature, "Name")) == "Centre Distance", "the distance mate renames and reads back")
            dims = sc.dimensions_of(feature)
            values = [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in dims]
            px.fact("distance_mate_dimensions", values)
            if with_link:
                match = [d for d in dims if abs(float(call(d, "SystemValue")) - CENTRE / sc.MM) < 1e-9]
                px.require(len(match) == 1, "the distance mate's dimension is found by value")
                dim_name = str(call(match[0], "Name"))
                eqm = call(asm, "GetEquationMgr")
                add = adder(px, eqm)
                index = add('"Centre Distance"= 60')
                px.require(index >= 0, "an assembly global is added")
                link = add(f'"{dim_name}@Centre Distance"= "Centre Distance"')
                px.require(link >= 0, f'the link "{dim_name}@Centre Distance"= "Centre Distance" is accepted')
                sc.put_indexed(eqm, "Equation", index, '"Centre Distance"= 70')
                call(asm, "ForceRebuild3", False)
                where = _translation_mm(second)
                px.fact("component_b_translation_mm_after_global_70", where)
                px.check(abs(math.hypot(where[0], where[1]) - 70.0) < 1e-6,
                         f"changing the global moves B to 70 mm: {where}")
        px.fact("mates", _mate_features(asm))
        if not with_link:
            # Last, because a fixed second component would fight its mates.
            px.fact("second_component_fixed_before_fix_component", bool(call(second, "IsFixed")))
            call(asm, "ClearSelection2", True)
            px.require(bool(call(second, "Select4", False, sc.null(), False)), "the second component selects")
            got, _ = px.attempt("FixComponent() on the free second component", lambda: asm.FixComponent())
            call(asm, "ClearSelection2", True)
            fixed = bool(call(second, "IsFixed"))
            px.fact("second_component_fixed_after_fix_component", fixed)
            px.check(got and fixed, "FixComponent() fixes the selected component")
    finally:
        for doc in (asm, part_b, part_a):
            try:
                sc.close(px, doc)
            except Exception as exc:  # noqa: BLE001
                px.note(f"CLEANUP {exc}")


@probe("assembly_components_and_mates", needs=("save_as", "axis", "extrude"), tier=4,
       members=("IAssemblyDoc.AddComponent5", "IComponent2.Name2", "IComponent2.Transform2", "IComponent2.IsFixed",
                "IAssemblyDoc.FixComponent", "IComponent2.FeatureByName", "IAssemblyDoc.AddMate5"))
def assembly_components_and_mates(px: Px) -> None:
    """Two components inserted, one fixed, and coincident, distance and angle mates between them."""
    _assembly(px, with_link=False)


@probe("assembly_distance_link", needs=("assembly_components_and_mates", "equation_set"), tier=4,
       members=("IEquationMgr.Add2", "IFeature.GetFirstDisplayDimension"))
def assembly_distance_link(px: Px) -> None:
    """The distance mate's dimension, linked to an assembly global, moves the component."""
    _assembly(px, with_link=True)
