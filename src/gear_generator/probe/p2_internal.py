"""Tier 2 for internal gears: a ring's blank is an annulus.

A ring is cut from a sketch of two concentric circles extruded together: the
rim outside and the teeth's tip circle inside. Whether FeatureExtrusion3 makes
that one ring-shaped body, rather than a disc or two, is settled by the volume,
and whether the inner circle's dimension still drives it from a global by the
volume after a change.
"""

from __future__ import annotations

import math
from typing import Any

from ..swcom import call
from . import scaffold as sc
from .harness import Px, probe
from .p1_equations import adder
from .p2_solid import BLANK_W, _extrude_args, _volume

RIM_D = 40.0      # mm
TIP_D = 24.0      # mm
TIP_LINKED_D = 20.0


def _annulus_mm3(outer: float, inner: float, width: float) -> float:
    return math.pi / 4.0 * (outer ** 2 - inner ** 2) * width


def _dimension(doc: Any, entity: Any, at_mm: float, name: str) -> str:
    sc.select(doc, entity)
    display = call(doc, "AddDimension2", at_mm / sc.MM, at_mm / sc.MM, 0.0)
    call(doc, "ClearSelection2", True)
    dimension = call(display, "GetDimension2", 0)
    dimension.Name = name
    return str(call(dimension, "Name"))


@probe("annulus_extrude", needs=("extrude", "dimension_link"), tier=2,
       members=("ISketchManager.CreateCircleByRadius", "IFeatureManager.FeatureExtrusion3", "IBody2.GetType"))
def annulus_extrude(px: Px) -> None:
    """Two concentric circles extruded as one annulus, the inner diameter linked to a global."""
    with sc.scratch(px) as doc:
        with sc.quiet_dimensions(px):
            before = sc.feature_names(doc)
            manager = sc.open_sketch(px, doc, 1)
            rim = call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, RIM_D / 2.0 / sc.MM)
            tip = call(manager, "CreateCircleByRadius", 0.0, 0.0, 0.0, TIP_D / 2.0 / sc.MM)
            px.require(rim is not None and tip is not None, "both circles are made")
            origin = sc.origin_point(doc)
            sc.relate(doc, "sgCOINCIDENT", call(rim, "GetCenterPoint2"), origin)
            sc.relate(doc, "sgCOINCIDENT", call(tip, "GetCenterPoint2"), origin)
            px.check(_dimension(doc, rim, 28.0, "Rim") == "Rim", "the rim's dimension renames to Rim")
            px.check(_dimension(doc, tip, 5.0, "Tip") == "Tip", "the tip circle's dimension renames to Tip")
            sketch = sc.close_sketch(px, doc, "Ring Sketch", before)
        px.require(sc.select_feature(doc, sc.feature_by_name(doc, sketch)), "the ring sketch selects")
        feature = call(sc.feature_manager(doc), "FeatureExtrusion3", *_extrude_args(BLANK_W / sc.MM))
        call(doc, "ClearSelection2", True)
        px.require(feature is not None, "FeatureExtrusion3 extrudes the two circles")
        feature.Name = "Blank"

        volume = _volume(doc)
        expected = _annulus_mm3(RIM_D, TIP_D, BLANK_W)
        px.fact("annulus_volume_mm3", {"volume": volume, "expected": expected})
        px.check(abs(volume - expected) < 1e-6 * expected,
                 f"the blank is a ring of {volume:.4f} mm³ (expected {expected:.4f}), not a disc")
        bodies = call(doc, "GetBodies2", 0, True)
        px.fact("annulus_solid_bodies", len(bodies) if bodies else 0)
        px.check(bodies is not None and len(bodies) == 1, "one solid body")

        add = adder(px, call(doc, "GetEquationMgr"))
        px.require(add(f'"Probe Tip"= {TIP_LINKED_D:g}') >= 0, "a tip diameter global is added")
        px.require(add('"Tip@Ring Sketch"= "Probe Tip"') >= 0, 'the link "Tip@Ring Sketch"= "Probe Tip" is accepted')
        volume = _volume(doc)
        expected = _annulus_mm3(RIM_D, TIP_LINKED_D, BLANK_W)
        px.fact("annulus_volume_linked_mm3", {"volume": volume, "expected": expected})
        px.check(abs(volume - expected) < 1e-6 * expected,
                 f"linked to {TIP_LINKED_D:g} mm the hole follows: {volume:.4f} mm³ (expected {expected:.4f})")
