"""Tier 2: extrude, cut, axis and circular pattern, with the volume as the oracle.

A feature call returning an object says little; the part's volume says whether
material went where it should. Each feature is checked against the volume the
geometry must have, which is what catches a cut that went the wrong way and
removed nothing.
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple

from ..swcom import call
from . import scaffold as sc
from .harness import Px, Require, probe
from .p1_equations import adder

# swEndConditions_e, from swconst.tlb on SolidWorks 2026.
BLIND = 0
THROUGH_ALL = 1
THROUGH_ALL_BOTH = 9

BLANK_R = 20.0      # mm
BLANK_W = 10.0      # mm
HOLE_R = 3.0        # mm
HOLE_X = 12.0       # mm


def _extrude_args(depth_m: float) -> Tuple[Any, ...]:
    """FeatureExtrusion3's 23 arguments for a single-ended blind boss, in the help's order."""
    return (True, False, False, BLIND, BLIND, depth_m, 0.0, False, False, False, False, 0.0, 0.0,
            False, False, False, False, True, True, True, 0, 0.0, False)


def _cut_args(single: bool, flip_direction: bool, end: int) -> Tuple[Any, ...]:
    """FeatureCut4's 27 arguments for a through cut, in the help's order."""
    return (single, False, flip_direction, end, end, 0.01, 0.01, False, False, False, False, 0.0, 0.0,
            False, False, False, False, False, True, True, True, True, False, 0, 0.0, False, False)


def _blank(px: Px, doc: Any, name: str = "Blank") -> Any:
    """A cylinder r 20 x 10 mm on the first plane, named, with its sketch named."""
    with sc.quiet_dimensions(px):
        before = sc.feature_names(doc)
        manager = sc.open_sketch(px, doc, 1)
        circle = call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, BLANK_R / sc.MM)
        sc.relate(doc, "sgCOINCIDENT", call(circle, "GetCenterPoint2"), sc.origin_point(doc))
        sc.select(doc, circle)
        display = call(doc, "AddDimension2", 0.025, 0.025, 0.0)
        call(doc, "ClearSelection2", True)
        call(display, "GetDimension2", 0).Name = "OD"
        sketch = sc.close_sketch(px, doc, f"{name} Sketch", before)
    if not sc.select_feature(doc, sc.feature_by_name(doc, sketch)):
        raise Require(f"{sketch} could not be selected to extrude.")
    before = sc.feature_names(doc)
    feature = call(sc.feature_manager(doc), "FeatureExtrusion3", *_extrude_args(BLANK_W / sc.MM))
    call(doc, "ClearSelection2", True)
    if feature is None:
        raise Require("FeatureExtrusion3 returned nothing.")
    feature.Name = name
    return feature


def _hole_sketch(px: Px, doc: Any, name: str, x_mm: float = HOLE_X) -> str:
    before = sc.feature_names(doc)
    manager = sc.open_sketch(px, doc, 1)
    call(manager, "CreateCircleByRadius", x_mm / sc.MM, 0.0, 0.0, HOLE_R / sc.MM)
    return sc.close_sketch(px, doc, name, before)


def _volume(doc: Any) -> float:
    call(doc, "ForceRebuild3", False)
    value = sc.volume_mm3(doc)
    if value is None:
        raise Require("The part's volume could not be read.")
    return value


@probe("extrude", needs=("sketch_open_close", "dimensions"), tier=2,
       members=("IFeatureManager.FeatureExtrusion3", "IModelDocExtension.CreateMassProperty", "IMassProperty.Volume",
                "IFeature.GetFirstDisplayDimension"))
def extrude(px: Px) -> None:
    """A blind boss from a closed sketch, measured by volume, with its depth dimension found by value."""
    with sc.scratch(px) as doc:
        feature = _blank(px, doc)
        px.fact("extrude_type_name", sc.type_name(feature))
        px.check(str(call(feature, "Name")) == "Blank", "the extrusion renames and reads back")
        volume = _volume(doc)
        expected = math.pi * BLANK_R ** 2 * BLANK_W
        px.fact("blank_volume_mm3", volume)
        px.check(abs(volume - expected) < 1e-3 * expected, f"the blank's volume is {volume:.3f} mm³ (expected {expected:.3f})")

        dimensions = sc.dimensions_of(feature)
        found = [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in dimensions]
        px.fact("extrude_dimensions", found)
        depth = [d for d in dimensions if abs(float(call(d, "SystemValue")) - BLANK_W / sc.MM) < 1e-9]
        px.require(len(depth) >= 1, "the depth dimension is found by its value")
        px.fact("depth_dimension_default_name", str(call(depth[0], "Name")))
        depth[0].Name = "Width"
        px.check(str(call(depth[0], "Name")) == "Width", "the depth dimension renames to Width")
        px.fact("depth_full_name", str(call(depth[0], "FullName")))

        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add('"Probe W"= 12') >= 0, "a width global is added")
        px.require(add('"Width@Blank"= "Probe W"') >= 0, 'the link "Width@Blank"= "Probe W" is accepted')
        volume = _volume(doc)
        expected = math.pi * BLANK_R ** 2 * 12.0
        px.check(abs(volume - expected) < 1e-3 * expected, f"linked to 12 mm the blank is {volume:.3f} mm³")


@probe("cut", needs=("extrude",), tier=2, members=("IFeatureManager.FeatureCut4", "IFeatureManager.FeatureCut3"))
def cut(px: Px) -> None:
    """Which way a cut from the blank's own sketch plane goes, tried every plausible way."""
    hole = math.pi * HOLE_R ** 2 * BLANK_W
    working: List[str] = []
    for label, single, flip, end in (
        ("through all, default direction", True, False, THROUGH_ALL),
        ("through all, direction flipped", True, True, THROUGH_ALL),
        ("through all both", False, False, THROUGH_ALL_BOTH),
        ("through all, both ends", False, False, THROUGH_ALL),
    ):
        with sc.scratch(px) as doc:
            _blank(px, doc)
            before_volume = _volume(doc)
            sketch = _hole_sketch(px, doc, "Hole Sketch")
            px.require(sc.select_feature(doc, sc.feature_by_name(doc, sketch)), "the hole sketch selects")
            got, feature = px.attempt(f"FeatureCut4 {label}",
                                      lambda: call(sc.feature_manager(doc), "FeatureCut4", *_cut_args(single, flip, end)))
            call(doc, "ClearSelection2", True)
            removed = before_volume - _volume(doc) if got and feature is not None else 0.0
            px.fact(f"cut {label}", {"made": bool(got and feature is not None), "removed_mm3": round(removed, 3),
                                     "type": sc.type_name(feature) if got and feature is not None else None})
            if abs(removed - hole) < 1e-3 * hole:
                working.append(label)
    px.fact("cut_routes_that_remove_the_hole", working)
    px.require(bool(working), "some FeatureCut4 form removes exactly the hole")
    px.shared["cut_route"] = working[0]


def _cut_route(px: Px) -> Tuple[bool, bool, int]:
    return {
        "through all, default direction": (True, False, THROUGH_ALL),
        "through all, direction flipped": (True, True, THROUGH_ALL),
        "through all both": (False, False, THROUGH_ALL_BOTH),
        "through all, both ends": (False, False, THROUGH_ALL),
    }[px.shared.get("cut_route", "through all both")]


@probe("axis", needs=("new_document",), tier=2, members=("IModelDoc2.InsertAxis2",))
def axis(px: Px) -> None:
    """An axis from the second and third planes, which is the normal of the first."""
    with sc.scratch(px) as doc:
        px.require(sc.select_plane(doc, 2) and sc.select_plane(doc, 3, append=True), "planes 2 and 3 select together")
        before = sc.feature_names(doc)
        made = call(doc, "InsertAxis2", True)
        call(doc, "ClearSelection2", True)
        px.fact("insert_axis2_returns", made)
        new = sc.new_features(doc, before)
        px.fact("axis_new_features", new)
        px.require(len(new) == 1, "InsertAxis2 adds exactly one feature")
        feature = sc.feature_by_name(doc, new[0][0])
        feature.Name = "Gear Axis"
        px.check(str(call(feature, "Name")) == "Gear Axis", "the axis renames and reads back")
        px.fact("axis_type_name", sc.type_name(feature))
        px.check(sc.select_feature(doc, feature), "the axis can be selected again")
        call(doc, "ClearSelection2", True)


@probe("pattern", needs=("cut", "axis"), tier=2,
       members=("IFeatureManager.FeatureCircularPattern5", "IFeatureManager.FeatureCircularPattern4"))
def pattern(px: Px) -> None:
    """A circular pattern of the cut about the axis: the axis at mark 1, the feature at mark 4."""
    hole = math.pi * HOLE_R ** 2 * BLANK_W
    with sc.scratch(px) as doc:
        _blank(px, doc)
        px.require(sc.select_plane(doc, 2) and sc.select_plane(doc, 3, append=True), "planes 2 and 3 select")
        before = sc.feature_names(doc)
        call(doc, "InsertAxis2", True)
        call(doc, "ClearSelection2", True)
        axis_name = sc.new_features(doc, before)[0][0]
        sketch = _hole_sketch(px, doc, "Hole Sketch")
        single, flip, end = _cut_route(px)
        px.require(sc.select_feature(doc, sc.feature_by_name(doc, sketch)), "the hole sketch selects")
        cut_feature = call(sc.feature_manager(doc), "FeatureCut4", *_cut_args(single, flip, end))
        call(doc, "ClearSelection2", True)
        px.require(cut_feature is not None, "the seed cut is made")
        cut_feature.Name = "Tooth Space"
        blank_volume = math.pi * BLANK_R ** 2 * BLANK_W

        count = 6
        made = None
        for label, args in (
            ('FeatureCircularPattern5 DName "NULL"',
             (count, 2 * math.pi, False, "NULL", False, True, False, False, False, False, 1, 0.0, "NULL", False)),
            ('FeatureCircularPattern5 DName ""',
             (count, 2 * math.pi, False, "", False, True, False, False, False, False, 1, 0.0, "", False)),
        ):
            call(doc, "ClearSelection2", True)
            px.require(sc.select_feature(doc, sc.feature_by_name(doc, axis_name), append=False, mark=1),
                       "the axis selects at mark 1")
            px.require(sc.select_feature(doc, cut_feature, append=True, mark=4), "the cut selects at mark 4")
            before = sc.feature_names(doc)
            got, made = px.attempt(label, lambda: call(sc.feature_manager(doc), "FeatureCircularPattern5", *args))
            call(doc, "ClearSelection2", True)
            if got and made is not None:
                px.fact("pattern_call", label)
                break
        px.require(made is not None, "a circular pattern is made")
        px.fact("pattern_type_name", sc.type_name(made))
        made.Name = "Teeth"
        px.check(str(call(made, "Name")) == "Teeth", "the pattern renames and reads back")
        volume = _volume(doc)
        expected = blank_volume - count * hole
        px.check(abs(volume - expected) < 1e-3 * expected, f"six holes leave {volume:.3f} mm³ (expected {expected:.3f})")

        dims = sc.dimensions_of(made)
        values = [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in dims]
        px.fact("pattern_dimensions", values)
        counts = [(i, d) for i, d in enumerate(dims) if abs(float(call(d, "SystemValue")) - count) < 1e-9]
        px.require(len(counts) == 1, "exactly one pattern dimension has the count's value")
        px.fact("pattern_count_dim_index", counts[0][0])
        px.fact("pattern_count_dim_default_name", str(call(counts[0][1], "Name")))
        counts[0][1].Name = "Count"
        px.check(str(call(counts[0][1], "Name")) == "Count", "the count dimension renames to Count")
        px.shared["pattern_ok"] = True


@probe("pattern_count_link", needs=("pattern",), tier=2, members=("IEquationMgr.Add2",))
def pattern_count_link(px: Px) -> None:
    """The pattern's count follows a global: "Count@Teeth"= "Probe N"."""
    hole = math.pi * HOLE_R ** 2 * BLANK_W
    with sc.scratch(px) as doc:
        _blank(px, doc)
        sc.select_plane(doc, 2)
        sc.select_plane(doc, 3, append=True)
        before = sc.feature_names(doc)
        call(doc, "InsertAxis2", True)
        call(doc, "ClearSelection2", True)
        axis_name = sc.new_features(doc, before)[0][0]
        sketch = _hole_sketch(px, doc, "Hole Sketch")
        single, flip, end = _cut_route(px)
        sc.select_feature(doc, sc.feature_by_name(doc, sketch))
        cut_feature = call(sc.feature_manager(doc), "FeatureCut4", *_cut_args(single, flip, end))
        call(doc, "ClearSelection2", True)
        sc.select_feature(doc, sc.feature_by_name(doc, axis_name), mark=1)
        sc.select_feature(doc, cut_feature, append=True, mark=4)
        made = call(sc.feature_manager(doc), "FeatureCircularPattern5",
                    6, 2 * math.pi, False, "NULL", False, True, False, False, False, False, 1, 0.0, "NULL", False)
        call(doc, "ClearSelection2", True)
        px.require(made is not None, "the pattern is made")
        made.Name = "Teeth"
        count_dim = [d for d in sc.dimensions_of(made) if abs(float(call(d, "SystemValue")) - 6) < 1e-9]
        px.require(len(count_dim) == 1, "the count dimension is found by value")
        count_dim[0].Name = "Count"

        eqm = call(doc, "GetEquationMgr")
        add = adder(px, eqm)
        px.require(add('"Probe N"= 8') >= 0, "the count global is added")
        link = add('"Count@Teeth"= "Probe N"')
        px.fact("count_link_index", link)
        px.require(link >= 0, 'the link "Count@Teeth"= "Probe N" is accepted')
        volume = _volume(doc)
        expected = math.pi * BLANK_R ** 2 * BLANK_W - 8 * hole
        px.check(abs(volume - expected) < 1e-3 * expected, f"linked to 8 the pattern leaves {volume:.3f} mm³")


@probe("batched_under_command_in_progress", needs=("pattern",), tier=2, members=("ISldWorks.CommandInProgress",))
def batched(px: Px) -> None:
    """The same features made with rebuilds held off come out the same once the flag is restored."""
    app = sc.app(px)
    with sc.scratch(px) as doc:
        app.CommandInProgress = True
        try:
            _blank(px, doc)
            sketch = _hole_sketch(px, doc, "Hole Sketch")
            single, flip, end = _cut_route(px)
            sc.select_feature(doc, sc.feature_by_name(doc, sketch))
            made = call(sc.feature_manager(doc), "FeatureCut4", *_cut_args(single, flip, end))
            call(doc, "ClearSelection2", True)
        finally:
            app.CommandInProgress = False
        px.check(made is not None, "a cut is made while CommandInProgress is True")
        px.check(not bool(app.CommandInProgress), "the flag reads back False after restoring")
        volume = _volume(doc)
        expected = math.pi * BLANK_R ** 2 * BLANK_W - math.pi * HOLE_R ** 2 * BLANK_W
        px.check(abs(volume - expected) < 1e-3 * expected, f"after one rebuild the part is {volume:.3f} mm³")
