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

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from .. import findings
from ..gears import equations
from ..gears.base import (AddComponent, AddGlobal, Axis, BuildPlan, Fix, GlobalVariable, LinkDimension, NewAssembly,
                          NewPart, Place, Rebuild, RefPlane, SaveAs, Unfix)
from ..spec import sanitize_stem
from .checks import Report
from .geometry import AXES, Placed
from .model import GearboxSpec
from .schema import FRAME

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


#: The findings this module reads, all from probe tier 7 (``p7_workbook``), and what each decides here.
REPLACE_STRAIGHT = "Transform2 put"                                  # a fixed component moves as it is
REPLACE_UNFIXED = "UnfixComponent, Transform2 put, FixComponent"     # unfixed, put, fixed again
NEGATED_LINKS = {"minus": "- {}", "times minus one": "-1 * {}", "abs": "abs ( {} )"}

_MISSING = object()


def _finding(name: str) -> Any:
    """A tier-7 finding, or :data:`_MISSING` while it is not committed (``None`` is a value some findings take)."""
    return getattr(findings, name, _MISSING)


def _not_settled(name: str, what: str) -> ValueError:
    return ValueError(f"The layout part and assembly wait for probe tier 7: findings.{name}, which says {what}, "
                      "is not settled yet.")


def side(value: float) -> str:
    """:data:`PLUS`, :data:`MINUS`, or :data:`BASE` within :data:`BASE_TOLERANCE` of 0."""
    if abs(value) < BASE_TOLERANCE:
        return BASE
    return PLUS if value > 0 else MINUS


def _number(text: str, what: str) -> float:
    try:
        value = float(str(text).strip() or "0")
    except ValueError:
        raise ValueError(f"{what} is {text!r}, which is not a number.") from None
    if not math.isfinite(value):
        raise ValueError(f"{what} is {text!r}, which is not a finite number.")
    return value


def shaft_layouts(spec: GearboxSpec) -> Tuple[ShaftLayout, ...]:
    """Every shaft, in Shafts-sheet order. Called only on a spec that passed ``Assessment.lay_out_refusal()``,
    so every shaft is on the frame with axis Z+ or Z−; anything else raises ValueError with a sentence."""
    out: List[ShaftLayout] = []
    for shaft in spec.shafts:
        if shaft.mount() != FRAME:
            raise ValueError(f"{shaft.id} is mounted on {shaft.mount()}: the layout part holds only shafts held by "
                             "the frame until phase W7.")
        axis = shaft.axis or "Z+"
        if axis not in AXES:
            raise ValueError(f"{shaft.id}'s axis is {axis}: the layout part holds only axes along Z+ or Z- until "
                             "phase W6.")
        x = _number(shaft.x, f"{shaft.id}'s X")
        y = _number(shaft.y, f"{shaft.id}'s Y")
        z = _number(shaft.z, f"{shaft.id}'s Z")
        x_side, y_side = side(x), side(y)
        out.append(ShaftLayout(
            shaft=shaft.id, x=x, y=y, z=z, sigma=AXES[axis], x_side=x_side, y_side=y_side,
            x_global="" if x_side == BASE else f"{shaft.id} X", y_global="" if y_side == BASE else f"{shaft.id} Y",
            x_plane="" if x_side == BASE else f"{shaft.id} X Plane",
            y_plane="" if y_side == BASE else f"{shaft.id} Y Plane",
            axis_name=f"{shaft.id} Axis"))
    return tuple(out)


def _negated_link() -> Any:
    form = _finding("LAYOUT_NEGATED_LINK")
    if form is _MISSING:
        raise _not_settled("LAYOUT_NEGATED_LINK", "how a plane on the minus side follows its global")
    if form is not None and form not in NEGATED_LINKS:
        raise ValueError(f"findings.LAYOUT_NEGATED_LINK is {form!r}, which this version does not know how to "
                         "write; the layout part is not planned.")
    return form


def layout_globals(shafts: Sequence[ShaftLayout]) -> Tuple[GlobalVariable, ...]:
    """One ``GlobalVariable`` per non-base coordinate, in shaft order, X before Y: ``"S2 X" = 63.75``. The value
    is signed or |v| as ``findings.LAYOUT_NEGATED_LINK`` makes :func:`link_expression` need it (None: |v|)."""
    signed = _negated_link() is not None
    out: List[GlobalVariable] = []
    for s in shafts:
        for name, value in ((s.x_global, s.x), (s.y_global, s.y)):
            if name:
                out.append(GlobalVariable(name, equations.literal(value if signed else abs(value))))
    return tuple(out)


def link_expression(global_name: str, plus: bool) -> str:
    """The offset dimension's equation text for a coordinate on the plus or minus side, by
    ``findings.LAYOUT_NEGATED_LINK``: plus is always ``"S2 X"``; minus is ``- "S2 X"`` for "minus",
    ``-1 * "S2 X"`` for "times minus one", ``abs ( "S2 X" )`` for "abs", and ``"S2 X"`` (holding |x|) for None."""
    quoted = equations.quote(global_name)
    form = _negated_link()
    if plus or form is None:
        return quoted
    return NEGATED_LINKS[form].format(quoted)


def flip_for(base: str, value: float) -> bool:
    """The ``RefPlane.flip`` that puts a plane offset from ``base`` (``"right"`` or ``"top"``) on ``value``'s side,
    from ``findings.LAYOUT_PLUS_FLIP``."""
    flips = _finding("LAYOUT_PLUS_FLIP")
    if flips is _MISSING or flips is None:
        raise _not_settled("LAYOUT_PLUS_FLIP", "which flip puts a plane on the plus side")
    if base not in flips:
        raise ValueError(f"findings.LAYOUT_PLUS_FLIP does not say which flip puts a plane offset from the {base} "
                         "plane on the plus side, so the layout part is not planned.")
    plus = bool(flips[base])
    return plus if value > 0 else not plus


def _top_first() -> bool:
    """Whether a layout axis selects its Top-parallel plane first, so it reads +Z like each part's Gear Axis."""
    sign = _finding("LAYOUT_AXIS_Z_SIGN")
    if sign is _MISSING or sign is None:
        raise _not_settled("LAYOUT_AXIS_Z_SIGN", "which way an axis through two planes points")
    if sign not in (1, -1):
        raise ValueError(f"findings.LAYOUT_AXIS_Z_SIGN is {sign!r}, not 1 or -1, so the layout part is not "
                         "planned.")
    # The finding is the sign read with the Right-parallel plane selected first.
    return sign == -1


def layout_features(shafts: Sequence[ShaftLayout]) -> Tuple[str, ...]:
    """Every plane and axis name the layout part holds, in plan order: what a reused layout is checked for live
    (``swbuild.DocumentValues.features``) beside its globals."""
    out: List[str] = []
    for s in shafts:
        out.extend(name for name in (s.x_plane, s.y_plane) if name)
        out.append(s.axis_name)
    return tuple(out)


def layout_plan(shafts: Sequence[ShaftLayout], template: str, path: str) -> BuildPlan:
    """The layout part's plan: ``NewPart``; every global; per shaft ``i``, the X plane ``RefPlane("x<i>", …,
    RIGHT, |x|, flip_for("right", x))`` and its ``LinkDimension``, the same for Y on TOP, then ``Axis("axis<i>",
    "<Shaft> Axis", (y_ref, x_ref))`` with a str id for a made plane or the int base plane, in the order
    ``findings.LAYOUT_AXIS_Z_SIGN`` asks; ``Rebuild``; ``SaveAs(path)``. Ids are by index so no shaft name can
    collide. ``check()`` is empty. No ``.gear.json``: the link record holds it."""
    top_first = _top_first()
    ops: List[Any] = [NewPart(template)]
    ops.extend(AddGlobal(g.name, g.expression) for g in layout_globals(shafts))
    for i, s in enumerate(shafts, 1):
        refs = {}
        for axis, base, base_plane, value, name, plane in (("x", "right", RIGHT, s.x, s.x_global, s.x_plane),
                                                           ("y", "top", TOP, s.y, s.y_global, s.y_plane)):
            if not plane:
                refs[axis] = base_plane                 # the base plane itself (AXIS_THROUGH_BASE_PLANE)
                continue
            ident = f"{axis}{i}"
            ops.append(RefPlane(ident, plane, base_plane, abs(value), flip_for(base, value)))
            ops.append(LinkDimension(f"Offset@{plane}", link_expression(name, value > 0)))
            refs[axis] = ident
        planes = (refs["y"], refs["x"]) if top_first else (refs["x"], refs["y"])
        ops.append(Axis(f"axis{i}", s.axis_name, planes))
    ops.append(Rebuild())
    ops.append(SaveAs(path))
    return BuildPlan("layout", "", tuple(ops), path=path)


def _rotation(sigma: int, theta: float) -> Tuple[float, ...]:
    """``F_σ · rot_z(θ)`` by rows, with F₋ = rot_x(180°) = diag(1, −1, −1) written exactly."""
    c, s = math.cos(theta), math.sin(theta)
    rows = (c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0) if sigma > 0 else (c, -s, 0.0, -s, -c, 0.0, 0.0, 0.0, -1.0)
    return tuple(v + 0.0 for v in rows)          # no -0.0 in a log or a record


def frame(placed: Placed, theta: float) -> Frame:
    """A gear's frame, by the formula in the module docstring; ``theta`` in radians (``Report.theta``)."""
    if findings.EXTRUDE_Z_SIGN != 1:
        raise ValueError("findings.EXTRUDE_Z_SIGN is not 1, so a part's blank does not run along its own +Z and "
                         "the frames here would put every gear's face on the wrong side.")
    return Frame(_rotation(placed.sigma, theta), (placed.x, placed.y, placed.z_front))


def frames(report: Report) -> Dict[str, Frame]:
    """Every placed gear's frame, from ``report.layout.placed`` and ``report.theta``, keyed by gear id."""
    out: Dict[str, Frame] = {}
    for gear, placed in report.layout.placed.items():
        if gear not in report.theta:
            raise ValueError(f"{gear} is placed but has no turn worked out, so it cannot be put in the assembly.")
        out[gear] = frame(placed, report.theta[gear])
    return out


def pitch(placed: Placed) -> float:
    """The gear's angular pitch in degrees, 360 / teeth: frames are compared modulo it (``swbuild.same_frame``)."""
    return 360.0 / placed.teeth


def _unfix_first() -> bool:
    route = _finding("REPLACE_FIXED_ROUTE")
    if route is _MISSING or route is None:
        raise _not_settled("REPLACE_FIXED_ROUTE", "whether a fixed component can be placed as it is")
    if route == REPLACE_STRAIGHT:
        return False
    if route == REPLACE_UNFIXED:
        return True
    raise ValueError(f"findings.REPLACE_FIXED_ROUTE is {route!r}, which this version does not know how to "
                     "follow; the assembly is not planned.")


def assembly_plan(layout_path: str, components: Sequence[Tuple[str, str, Frame]], template: str,
                  path: str) -> BuildPlan:
    """The static assembly's plan: ``NewAssembly``; the layout inserted as :data:`LAYOUT_HANDLE`, ``Place``d at
    :data:`IDENTITY` and the origin (AddComponent5 puts a part's middle at the point), and ``Fix``ed; then each
    ``(handle, part path, frame)`` in order — ``AddComponent`` at the frame's origin, ``Place`` (wrapped in
    ``Unfix``/``Fix`` if ``findings.REPLACE_FIXED_ROUTE`` asks), ``Fix``; ``Rebuild``; ``SaveAs(path)``. A part
    path given twice is inserted twice (identical gears share one file). No ``ManualStep``: interference is
    checked by the build (``findings.INTERFERENCE_CHECKED``)."""
    unfix = _unfix_first()
    origin = (0.0, 0.0, 0.0)
    ops: List[Any] = [NewAssembly(template)]

    def put(handle: str, part: str, rotation: Tuple[float, ...], at: Tuple[float, float, float]) -> None:
        ops.append(AddComponent(handle, part, tuple(at)))
        if unfix:
            ops.append(Unfix(handle))          # the first component inserted may come in fixed (2024)
        ops.append(Place(handle, tuple(rotation), tuple(at)))
        ops.append(Fix(handle))

    put(LAYOUT_HANDLE, layout_path, IDENTITY, origin)
    for handle, part, where in components:
        if handle == LAYOUT_HANDLE:
            raise ValueError(f"A gear's component cannot be called {LAYOUT_HANDLE!r}: that is the layout part's.")
        put(handle, part, where.rotation, where.at)
    ops.append(Rebuild())
    ops.append(SaveAs(path))
    return BuildPlan("assembly", "", tuple(ops), path=path)


def stems(box_name: str, revision: int) -> Tuple[str, str]:
    """``(assembly stem, layout stem)`` from the Box sheet's Name through ``spec.sanitize_stem``: revision 0 gives
    ``("Reducer_12to1", "Reducer_12to1_Layout")``, revision n ≥ 2 ``("Reducer_12to1_r2",
    "Reducer_12to1_r2_Layout")``. Revision 1 does not exist (the first build is 0); asking for it is a ValueError."""
    if revision == 1 or revision < 0:
        raise ValueError(f"There is no revision {revision}: the first build is revision 0 and a build-again is 2, "
                         "3 and so on.")
    name = sanitize_stem(box_name, fallback="Gearbox")
    if revision:
        name = f"{name}{REVISION_SUFFIX}{revision}"
    return name, name + LAYOUT_SUFFIX
