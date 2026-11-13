"""The layout part and the static assembly, as plans (docs/PLAN-WORKBOOK.md §4.2–§4.3, phase W4).

Pure: no COM, no Tk, no file system; Linux-tested. Interfaces pinned in the W4
interface commit; every body that raises NotImplementedError is Agent B's.

**The layout part** ``<Name>_Layout.SLDPRT`` (``<Name>_r<n>_Layout`` for a
revision) holds, for each shaft held by the frame with its axis along Z±, the
plane offset from Right by X and the one offset from Top by Y — or the base
plane itself where the coordinate is 0 — and an axis through them named
``"<Shaft> Axis"``. A global ``"<Shaft> X"`` / ``"<Shaft> Y"`` drives each
offset; a coordinate at 0 has no plane and so no global (a global that drove
nothing would be edited in SolidWorks and silently move nothing), and a
coordinate that changes side or reaches or leaves 0 is a structural change,
since a global cannot carry a plane across its base plane
(``findings.OFFSET_GLOBAL_CROSSES_ZERO``).

**The frame of each gear** (``Place``): every kind's part is drawn with its
origin at the front-face centre, a tooth space centred on local +X, extruded
along local +Z (``findings.EXTRUDE_Z_SIGN`` = 1). A gear on shaft σ (+1 Z+,
−1 Z−) turned θ about its own axis is placed by

    F₊ = I,  F₋ = rot_x(180°) = diag(1, −1, −1)
    R  = F_σ · rot_z(degrees(θ))
    at = (x, y, z_front),   z_front = Placed.z_front = z − σ·face/2

so its mid-face lands on ``(x, y, z)``, and the tooth space the part's
section centres on local +X lands on the global angle σ·θ *at the height
where that section is drawn*: the Profile Plane, one overrun behind the front
face, for a plain helical gear or ring; the apex (mid-face) for a herringbone;
any height for a spur. Elsewhere along the face the helix turns it by
``HelicalDerived.turn_at(z)`` (``section_z`` is where it is 0), which
:meth:`geometry.Placed.twist` uses — the single source for the twist; this
module never works it out again. Rotations are 9 numbers by rows,
``v_global = R · v_local + at``. This module reads only ``Placed``'s public
fields (x, y, z, sigma, face, teeth, z_front) and ``Report.theta``; how θ is
worked out (the helical phase across Z+/Z−, decision 1, commit 119da25) is
:mod:`.geometry`'s. Tests of :func:`frame` model each part from its build
plan (``built_turn`` in ``tests/test_workbook_geometry.py``), never from
``space_angle``, which shares any error the geometry has.

Findings this module reads are probe tier 7's and are not committed yet; read
them with ``getattr(findings, NAME, None)`` and refuse (``ValueError`` with a
sentence) where one is None, never default it: ``LAYOUT_PLUS_FLIP``,
``LAYOUT_NEGATED_LINK``, ``LAYOUT_AXIS_Z_SIGN``, ``REPLACE_FIXED_ROUTE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

from ..gears.base import BuildPlan, GlobalVariable
from .checks import Report
from .geometry import Placed
from .model import GearboxSpec

LAYOUT_SUFFIX = "_Layout"
REVISION_SUFFIX = "_r"          # <Name>_r2, <Name>_r2_Layout, <part stem>_r2
ASSEMBLY_EXTENSION = ".SLDASM"
PART_EXTENSION = ".SLDPRT"

# A coordinate's side of its base plane.
PLUS = "plus"
MINUS = "minus"
BASE = "base"                   # |value| < BASE_TOLERANCE: the base plane itself, no offset plane, no global
BASE_TOLERANCE = 1e-9

# Base planes in tree order, as RefPlane/Axis take them.
FRONT, TOP, RIGHT = 1, 2, 3

# Handles in the assembly plan: the layout is "layout", the gears "gear1", "gear2", … in Gears-sheet order.
LAYOUT_HANDLE = "layout"
GEAR_HANDLE = "gear"

IDENTITY: Tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True)
class ShaftLayout:
    """One frame shaft as the layout part draws it (and as ``store.ShaftEntry`` records it, field for field).

    ``x``, ``y``, ``z`` in mm from the origin; ``sigma`` +1 for Z+, −1 for
    Z−. ``x_side``/``y_side`` are :data:`PLUS`, :data:`MINUS` or
    :data:`BASE`. ``x_global`` is the global's unquoted name (``S2 X``) and
    ``x_plane`` the plane's feature name (``S2 X Plane``), both ``""`` on a
    base coordinate; ``axis_name`` is ``"S2 Axis"``. ``z`` and ``sigma`` are
    not in the layout part (an axis has no end): they are kept for the frames
    and for saying a shaft moved.
    """

    shaft: str
    x: float
    y: float
    z: float
    sigma: int
    x_side: str
    y_side: str
    x_global: str
    y_global: str
    x_plane: str
    y_plane: str
    axis_name: str


@dataclass(frozen=True)
class Frame:
    """Where a gear's part goes in the assembly: ``rotation`` 9 numbers by rows, ``at`` its origin in mm."""

    rotation: Tuple[float, ...]
    at: Tuple[float, float, float]


def side(value: float) -> str:
    """:data:`PLUS`, :data:`MINUS`, or :data:`BASE` within :data:`BASE_TOLERANCE` of 0."""
    raise NotImplementedError("W4: Agent B, workbook.layout.side")


def shaft_layouts(spec: GearboxSpec) -> Tuple[ShaftLayout, ...]:
    """Every shaft, in Shafts-sheet order. Called only on a spec that passed ``Assessment.lay_out_refusal()``,
    so every shaft is on the frame with axis Z+ or Z−; anything else raises ValueError with a sentence."""
    raise NotImplementedError("W4: Agent B, workbook.layout.shaft_layouts")


def layout_globals(shafts: Sequence[ShaftLayout]) -> Tuple[GlobalVariable, ...]:
    """One ``GlobalVariable`` per non-base coordinate, in shaft order, X before Y: ``"S2 X" = 63.75``. The value
    is signed or |v| as ``findings.LAYOUT_NEGATED_LINK`` makes :func:`link_expression` need it (None: |v|)."""
    raise NotImplementedError("W4: Agent B, workbook.layout.layout_globals")


def link_expression(global_name: str, plus: bool) -> str:
    """The offset dimension's equation text for a coordinate on the plus or minus side, by
    ``findings.LAYOUT_NEGATED_LINK``: plus is always ``"S2 X"``; minus is ``- "S2 X"`` for "minus",
    ``-1 * "S2 X"`` for "times minus one", ``abs ( "S2 X" )`` for "abs", and ``"S2 X"`` (holding |x|) for None."""
    raise NotImplementedError("W4: Agent B, workbook.layout.link_expression")


def flip_for(base: str, value: float) -> bool:
    """The ``RefPlane.flip`` that puts a plane offset from ``base`` (``"right"`` or ``"top"``) on ``value``'s side,
    from ``findings.LAYOUT_PLUS_FLIP``."""
    raise NotImplementedError("W4: Agent B, workbook.layout.flip_for")


def layout_features(shafts: Sequence[ShaftLayout]) -> Tuple[str, ...]:
    """Every plane and axis name the layout part holds, in plan order: what a reused layout is checked for live
    (``swbuild.DocumentValues.features``) beside its globals."""
    raise NotImplementedError("W4: Agent B, workbook.layout.layout_features")


def layout_plan(shafts: Sequence[ShaftLayout], template: str, path: str) -> BuildPlan:
    """The layout part's plan: ``NewPart``; every global; per shaft ``i``, the X plane ``RefPlane("x<i>", …,
    RIGHT, |x|, flip_for("right", x))`` and its ``LinkDimension``, the same for Y on TOP, then ``Axis("axis<i>",
    "<Shaft> Axis", (y_ref, x_ref))`` with a str id for a made plane or the int base plane, in the order
    ``findings.LAYOUT_AXIS_Z_SIGN`` asks; ``Rebuild``; ``SaveAs(path)``. Ids are by index so no shaft name can
    collide. ``check()`` is empty. No ``.gear.json``: the link record holds it."""
    raise NotImplementedError("W4: Agent B, workbook.layout.layout_plan")


def frame(placed: Placed, theta: float) -> Frame:
    """A gear's frame, by the formula in the module docstring; ``theta`` in radians (``Report.theta``)."""
    raise NotImplementedError("W4: Agent B, workbook.layout.frame")


def frames(report: Report) -> Dict[str, Frame]:
    """Every placed gear's frame, from ``report.layout.placed`` and ``report.theta``, keyed by gear id."""
    raise NotImplementedError("W4: Agent B, workbook.layout.frames")


def pitch(placed: Placed) -> float:
    """The gear's angular pitch in degrees, 360 / teeth: frames are compared modulo it (``swbuild.same_frame``)."""
    raise NotImplementedError("W4: Agent B, workbook.layout.pitch")


def assembly_plan(layout_path: str, components: Sequence[Tuple[str, str, Frame]], template: str,
                  path: str) -> BuildPlan:
    """The static assembly's plan: ``NewAssembly``; the layout inserted as :data:`LAYOUT_HANDLE`, ``Place``d at
    :data:`IDENTITY` and the origin (AddComponent5 puts a part's middle at the point), and ``Fix``ed; then each
    ``(handle, part path, frame)`` in order — ``AddComponent`` at the frame's origin, ``Place`` (wrapped in
    ``Unfix``/``Fix`` if ``findings.REPLACE_FIXED_ROUTE`` asks), ``Fix``; ``Rebuild``; ``SaveAs(path)``. A part
    path given twice is inserted twice (identical gears share one file). No ``ManualStep``: interference is
    checked by the build (``findings.INTERFERENCE_CHECKED``)."""
    raise NotImplementedError("W4: Agent B, workbook.layout.assembly_plan")


def stems(box_name: str, revision: int) -> Tuple[str, str]:
    """``(assembly stem, layout stem)`` from the Box sheet's Name through ``spec.sanitize_stem``: revision 0 gives
    ``("Reducer_12to1", "Reducer_12to1_Layout")``, revision n ≥ 2 ``("Reducer_12to1_r2",
    "Reducer_12to1_r2_Layout")``. Revision 1 does not exist (the first build is 0); asking for it is a ValueError."""
    raise NotImplementedError("W4: Agent B, workbook.layout.stems")
