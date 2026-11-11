"""Internal gears: rings whose teeth point inward, meshing with an external pinion inside them.

A ring's tooth space is an external gear's tooth turned inside out. The space
is still centred on +X and cut from a blank, then patterned, but everything
about it runs the other way round the rim:

* the **blank** is an annulus: a rim outside, and a hole the size of the teeth's
  tips inside, ``da = d − 2m``;
* the **root** is outside the pitch circle, ``df = da + 2h``, and the space is
  closed by a chord *inside* the hole, where there is no material to cut;
* the **flank narrows outward**. Its polar angle is ``ψs + inv α − inv αr``, the
  pinion's lower involute mirrored, so in the Equation Manager it is spur's
  lower curve expression with ``"Flank Offset"`` negated.

Recipe A keeps spur's topology turned inside out: the involute runs from the
flank start diameter (the base circle, or a module inside the tip circle,
whichever is further out) to three fillet radii inside the root, a radial line
carries on to fillets tangent to it and to the root arc, and another radial line
runs in from the start to the tip cap, where the chord closes the space. Recipe B
swaps the involute for its osculating arc, centred on the base circle at polar
angle ψs − α.

The default fillet is 0.15 × module rather than spur's 0.38: a standard pinion's
tip reaches a module outside the ring's pitch circle, and the straight root line
of a 0.38 m fillet starts inside that reach.

A pair is a pinion inside a ring, turning the same way, at ``C = m (N2 − N1) / 2``.
An internal helical pair has the same helix angle and the **same** hand.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from .. import findings
from ..spec import KIND_HELICAL, KIND_HERRINGBONE, KIND_SPUR, RECIPE_ARCS, RECIPE_INVOLUTE, GearSpec, InputError
from . import equations, helical, spur
from .properties import property_ops
from .base import (
    ERROR,
    ORIGIN,
    WARNING,
    AddGlobal,
    Arc,
    Axis,
    BuildPlan,
    Circle,
    CircularPattern,
    CloseSketch,
    Cut,
    Diagnostic,
    Dimension,
    EquationCurve,
    Extrude,
    GeometryError,
    GlobalVariable,
    Line,
    LinkDimension,
    ManualStep,
    NewPart,
    Op,
    OpenSketch,
    Point2,
    Rebuild,
    Relation,
    SaveAs,
)
from .spur import (
    ARC_LENGTH,
    AXIS_NAME,
    BACKLASH,
    BACKLASH_FACTOR,
    BASE,
    BASE_RADIUS,
    BLANK,
    BLANK_SKETCH,
    DEPTH,
    FACE_WIDTH,
    FILLET,
    FLANK_ARC,
    FLANK_CENTRE,
    FLANK_OFFSET,
    FLANK_START,
    HALF_SPACE,
    INVOLUTE_FN,
    MODULE,
    PITCH,
    PRESSURE_ANGLE,
    ROOT,
    SPACE,
    SPACE_SKETCH,
    T1,
    T2,
    TEETH,
    TEETH_PATTERN,
    THICKNESS,
    TIP_CAP,
    _add,
    _arc,
    _at,
    _ccw,
    _mirror,
    _polar,
    _radius,
    _rotate,
    _same,
    _scale,
    _short,
    auto_close,
    clean_loop,
    involute_point,
    involute_t,
    signed_area,
)

# The globals a ring has that an external gear does not, by name.
INNER = "Inner Diameter"
RIM = "Rim Diameter"
FLANK_END = "Flank End Diameter"

# Eight of the user's ten names: a ring has no outer tip diameter and no bore.
USER_VARIABLES = (TEETH, MODULE, PRESSURE_ANGLE, PITCH, BACKLASH, ARC_LENGTH, FILLET, DEPTH)

FILLET_FACTOR = 0.15          # × module; see the module docstring
RIM_MODULES = 6.0             # a blank rim is the root diameter plus this many modules: a 3 m rim
RIM_WARNING_MODULES = 2.0     # a rim thinner than this many modules is warned about
FLANK_END_FILLETS = 3.0       # the involute ends this many fillet radii inside the root
TIP_THICKNESS_WARNING = 0.3   # × module

# The pair's tip clash, worked out at module 1 with no backlash and scaled.
CLASH_STEPS = 60              # positions through one pitch
CLASH_SAMPLES = 24            # points up each pinion flank
CLASH_TOLERANCE = 1e-3        # mm; less than this is no clash
CLASH_CHECK_BELOW = 20        # tooth differences at or above this never clash with standard teeth


def _q(name: str) -> str:
    return equations.quote(name)


def _num(value: float, places: int = 3) -> str:
    return equations.literal(round(value, places))


def _inv(angle: float) -> float:
    return math.tan(angle) - angle


# -- the numbers ------------------------------------------------------------


@dataclass(frozen=True)
class InternalDerived:
    """Every derived size of one ring's tooth-space section. mm, radians unless named ``_deg``.

    ``da`` is the teeth's tip diameter, inside the pitch circle; ``df`` the root,
    outside it. ``module`` is the normal module and ``pressure_angle_deg`` the
    section's own (transverse) pressure angle, as for :class:`spur.SpurDerived`.
    """

    teeth: int
    module: float
    pressure_angle_deg: float
    face_width: float
    rim: float
    backlash: float
    fillet: float
    backlash_typed: bool
    fillet_typed: bool
    rim_typed: bool

    alpha: float
    d: float
    da: float
    h: float
    df: float
    db: float
    p: float
    space: float
    s: float
    psi_s: float
    inv_alpha: float
    phi: float
    tip_cap_d: float
    flank_start_d: float
    flank_end_d: float
    t1: float
    t2: float
    flank_arc_radius: float
    transverse_module: float
    tip_thickness: float = 0.0
    bore: float = 0.0          # a ring has none; read by what draws gears

    @property
    def rp(self) -> float:
        return self.d / 2.0

    @property
    def ra(self) -> float:
        return self.da / 2.0

    @property
    def rf(self) -> float:
        return self.df / 2.0

    @property
    def rb(self) -> float:
        return self.db / 2.0

    @property
    def rc(self) -> float:
        return self.tip_cap_d / 2.0

    @property
    def rim_radius(self) -> float:
        return self.rim / 2.0

    @property
    def tip_below_base(self) -> bool:
        return self.da < self.db

    # A ring is not generated by a rack, so it has no undercut limit of its own.
    undercut_limit = 0
    undercut = False

    def values(self) -> Dict[str, float]:
        """The value of every global variable, by name."""
        return {
            TEETH: float(self.teeth),
            MODULE: self.module,
            PRESSURE_ANGLE: self.pressure_angle_deg,
            INNER: self.da,
            PITCH: self.d,
            BACKLASH: self.backlash,
            ARC_LENGTH: self.space,
            FILLET: self.fillet,
            DEPTH: self.h,
            FACE_WIDTH: self.face_width,
            ROOT: self.df,
            RIM: self.rim,
            BASE: self.db,
            BASE_RADIUS: self.rb,
            THICKNESS: self.s,
            HALF_SPACE: math.degrees(self.psi_s),
            INVOLUTE_FN: self.inv_alpha,
            FLANK_OFFSET: self.phi,
            TIP_CAP: self.tip_cap_d,
            FLANK_START: self.flank_start_d,
            FLANK_END: self.flank_end_d,
            T1: self.t1,
            T2: self.t2,
            FLANK_ARC: self.flank_arc_radius,
            FLANK_CENTRE: math.degrees(self.psi_s) - self.pressure_angle_deg,
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def section(teeth: int, module: float, pressure_angle_deg: float, face_width: float, rim: Optional[float],
            backlash: float, fillet: float, backlash_typed: bool = False, fillet_typed: bool = False,
            transverse_module: Optional[float] = None, transverse_backlash: Optional[float] = None,
            whole_depth: Optional[float] = None) -> InternalDerived:
    """Every size of a ring's tooth-space section; ``rim`` None is the root plus six modules.

    As :func:`spur.profile`: a helical ring passes its transverse module,
    backlash and pressure angle, and ``module`` stays the normal one, which
    every size up the tooth is measured in. ``whole_depth`` None is the user's
    depth IIF; an internal bevel gear's back-cone ring passes Gleason's.
    """
    m = module
    mt = module if transverse_module is None else transverse_module
    j_t = backlash if transverse_backlash is None else transverse_backlash
    n = teeth
    alpha = math.radians(pressure_angle_deg)
    d = n * mt
    da = d - 2.0 * m
    h = spur.tooth_depth(m) if whole_depth is None else whole_depth
    df = da + 2.0 * h
    db = d * math.cos(alpha)
    p = math.pi * mt
    space = mt * math.pi / 2.0 + j_t
    psi_s = space / d
    inv_alpha = _inv(alpha)
    start = db if db >= da - m else da - m
    end = df - FLANK_END_FILLETS * fillet
    g = InternalDerived(
        teeth=n, module=m, pressure_angle_deg=pressure_angle_deg, face_width=face_width,
        rim=df + RIM_MODULES * m if rim is None else rim, backlash=backlash, fillet=fillet,
        backlash_typed=backlash_typed, fillet_typed=fillet_typed, rim_typed=rim is not None,
        alpha=alpha, d=d, da=da, h=h, df=df, db=db, p=p, space=space, s=p - space, psi_s=psi_s,
        inv_alpha=inv_alpha, phi=-(psi_s + inv_alpha), tip_cap_d=da - 2.0 * m, flank_start_d=start,
        flank_end_d=end, t1=math.sqrt(max(0.0, (start / db) ** 2 - 1.0)),
        t2=math.sqrt(max(0.0, (end / db) ** 2 - 1.0)), flank_arc_radius=d / 2.0 * math.sin(alpha),
        transverse_module=mt,
    )
    tip = max(g.ra, g.flank_start_d / 2.0)
    return replace(g, tip_thickness=g.ra * (2.0 * math.pi / n - 2.0 * half_space_angle(g, tip)))


def half_space_angle(g: InternalDerived, r: float) -> float:
    """The upper flank's polar angle at radius ``r``: half the space's angular width there.

    Inside the flank start the flank is the radial line, so the angle there is
    the start's.
    """
    t = involute_t(g.rb, max(r, g.flank_start_d / 2.0))
    return -g.phi - (t - math.atan(t))


def flank_point(g: InternalDerived, t: float) -> Point2:
    """The upper flank at involute parameter ``t``: spur's lower involute, whose offset is now negative."""
    return _mirror(involute_point(g.rb, g.phi, t))


def contact_ratio(module: float, pinion_teeth: int, ring_teeth: int, pressure_angle_deg: float,
                  centre_distance: Optional[float] = None, transverse_module: Optional[float] = None) -> float:
    """``[√(ra1² − rb1²) − √(ra2² − rb2²) + C·sin α] / (π·mt·cos α)``, standard teeth.

    ``ra2`` is the ring's tip radius, inside its pitch circle. As
    :func:`spur.contact_ratio`, a helical pair passes the transverse module and
    pressure angle and gets εα.
    """
    alpha = math.radians(pressure_angle_deg)
    mt = module if transverse_module is None else transverse_module
    if centre_distance is None:
        centre_distance = mt * (ring_teeth - pinion_teeth) / 2.0
    ra1 = pinion_teeth * mt / 2.0 + module
    rb1 = pinion_teeth * mt * math.cos(alpha) / 2.0
    ra2 = ring_teeth * mt / 2.0 - module
    rb2 = ring_teeth * mt * math.cos(alpha) / 2.0
    total = math.sqrt(max(0.0, ra1 * ra1 - rb1 * rb1)) - math.sqrt(max(0.0, ra2 * ra2 - rb2 * rb2))
    total += centre_distance * math.sin(alpha)
    return total / (math.pi * mt * math.cos(alpha))


# -- tip clash --------------------------------------------------------------


@lru_cache(maxsize=2048)
def _clash_at_module_one(pinion_teeth: int, ring_teeth: int, pressure_angle_deg: float, phase: float) -> float:
    n1, n2 = pinion_teeth, ring_teeth
    alpha = math.radians(pressure_angle_deg)
    inv_alpha = _inv(alpha)
    centre = (n2 - n1) / 2.0
    ra1, rf1, rb1 = n1 / 2.0 + 1.0, n1 / 2.0 - 1.25, n1 * math.cos(alpha) / 2.0
    ra2, rf2, rb2 = n2 / 2.0 - 1.0, n2 / 2.0 + 1.25, n2 * math.cos(alpha) / 2.0
    psi1, psi2 = math.pi / (2.0 * n1), math.pi / (2.0 * n2)
    low = max(rb1, rf1)
    points: List[Tuple[float, float]] = []
    for i in range(CLASH_SAMPLES + 1):
        r = low + (ra1 - low) * i / CLASH_SAMPLES
        half = psi1 + inv_alpha - _inv(math.acos(min(1.0, rb1 / r)))
        if half > 0.0:
            points.extend(((r, half), (r, -half)))
    pitch1, pitch2 = 2.0 * math.pi / n1, 2.0 * math.pi / n2
    worst = 0.0
    for k in range(CLASH_STEPS):
        turn = pitch1 * k / CLASH_STEPS
        ring_turn = turn * n1 / n2
        for tooth in range(n1):
            base = turn + tooth * pitch1 + phase
            for r, a in points:
                angle = a + base
                x = centre + r * math.cos(angle)
                y = r * math.sin(angle)
                radius = math.hypot(x, y)
                if radius <= ra2 or radius >= rf2:
                    continue
                polar = math.atan2(y, x) - ring_turn
                off = polar - round(polar / pitch2) * pitch2
                half = psi2 + inv_alpha - _inv(math.acos(min(1.0, rb2 / max(radius, rb2))))
                worst = max(worst, (abs(off) - half) * radius)
    return worst


def tip_clash(module: float, pinion_teeth: int, ring_teeth: int, pressure_angle_deg: float = 20.0,
              phase: float = 0.0) -> float:
    """How deep a pinion's teeth run into a ring's as they mesh, in mm; 0 when they clear.

    The pinion is turned through one pitch inside the ring, the ring turning
    with it, and every point up each pinion flank that lands inside a ring tooth
    counts by how far round the circle it is inside. Flanks only, standard
    teeth, no backlash: a warning, never a refusal. ``phase`` turns the pinion
    off its meshing position, which is how the check is shown to be able to fail.
    """
    if ring_teeth <= pinion_teeth:
        raise ValueError(f"A ring of {ring_teeth} teeth cannot hold a pinion of {pinion_teeth}.")
    return module * _clash_at_module_one(pinion_teeth, ring_teeth, round(pressure_angle_deg, 9), phase)


# -- the flank of each recipe, upper side of the space ----------------------


@dataclass(frozen=True)
class InvoluteFlank:
    """Recipe A's upper flank on a ring: tip-cap line, involute, root line, root fillet."""

    start: Point2           # where the involute begins, inside, at the flank start diameter
    end: Point2             # where it ends, outside, at the flank end diameter
    cap: Point2             # the inner radial line's end, on the tip cap
    line_outer: Point2      # the outer radial line's end, where the fillet meets it
    fillet_centre: Point2
    root_touch: Point2


@dataclass(frozen=True)
class ArcFlank:
    """Recipe B's upper flank on a ring: the osculating arc from the tip cap, then the root fillet."""

    centre: Point2          # on the base circle, at polar angle ψs − α
    radius: float
    pitch_point: Point2
    cap_point: Point2       # where the arc meets the tip cap
    flank_touch: Point2     # where the fillet meets the arc
    fillet_centre: Point2
    root_touch: Point2


def involute_flank(g: InternalDerived) -> InvoluteFlank:
    start = flank_point(g, g.t1)
    end = flank_point(g, g.t2)
    theta = _polar(end)
    if theta <= 0.0:
        raise GeometryError(
            f"The flanks of each tooth space meet before they reach {_num(g.flank_end_d)} mm, inside the root; "
            "reduce the backlash or the fillet, or add teeth."
        )
    rf, rho = g.rf, g.fillet
    along2 = (rf - rho) ** 2 - rho * rho
    if along2 <= 0.0 or math.sqrt(along2) <= g.flank_end_d / 2.0:
        raise GeometryError(
            f"A {_num(rho)} mm root fillet does not fit between the flank and the root; make Fillet smaller."
        )
    along = math.sqrt(along2)
    unit = (math.cos(theta), math.sin(theta))
    toward_space = (math.sin(theta), -math.cos(theta))
    centre = _add(_scale(unit, along), _scale(toward_space, rho))
    return InvoluteFlank(
        start=start,
        end=end,
        cap=_scale((math.cos(_polar(start)), math.sin(_polar(start))), g.rc),
        line_outer=_scale(unit, along),
        fillet_centre=centre,
        root_touch=_scale(centre, rf / (rf - rho)),
    )


def _arc_at_radius(centre: Point2, radius: float, r: float) -> Optional[Point2]:
    """Where an arc about ``centre`` crosses the circle of radius ``r``, counter-clockwise of the centre's own line."""
    d = _radius(centre)
    x = (r * r + d * d - radius * radius) / (2.0 * d)
    h2 = r * r - x * x
    if h2 < 0.0:
        return None
    h = math.sqrt(h2)
    beta = _polar(centre)
    return (x * math.cos(beta) - h * math.sin(beta), x * math.sin(beta) + h * math.cos(beta))


def arc_flank(g: InternalDerived) -> ArcFlank:
    beta = g.psi_s - g.alpha
    centre = _at(g.rb, beta)
    radius = g.flank_arc_radius
    cap_point = _arc_at_radius(centre, radius, g.rc)
    if cap_point is None:
        raise GeometryError(
            f"Recipe B's flank arc (radius {_num(radius)} mm) never reaches the tip cap of this ring, so it cannot "
            "close the tooth space; use the involute recipe."
        )
    rf, rho = g.rf, g.fillet
    r1, r2 = rf - rho, radius - rho
    x = (r1 * r1 + g.rb * g.rb - r2 * r2) / (2.0 * g.rb)
    h2 = r1 * r1 - x * x
    if r2 <= 0.0 or h2 < 0.0:
        raise GeometryError(
            f"A {_num(rho)} mm root fillet cannot touch both the root and Recipe B's flank arc; make Fillet smaller."
        )
    h = math.sqrt(h2)
    fillet_centre = (x * math.cos(beta) - h * math.sin(beta), x * math.sin(beta) + h * math.cos(beta))
    toward = (fillet_centre[0] - centre[0], fillet_centre[1] - centre[1])
    length = _radius(toward)
    return ArcFlank(
        centre=centre,
        radius=radius,
        pitch_point=_at(g.rp, g.psi_s),
        cap_point=cap_point,
        flank_touch=_add(centre, _scale(toward, radius / length)),
        fillet_centre=fillet_centre,
        root_touch=_scale(fillet_centre, rf / r1),
    )


def flank_deviation(g: InternalDerived, steps: int = 200) -> float:
    """Recipe B's worst error against the true involute on a ring, in mm along the circle.

    Measured on the working flank: from the tip circle (or the base circle, if
    that is further out) to a module outside the pitch circle, where a standard
    pinion's tip reaches.
    """
    centre = _at(g.rb, g.psi_s - g.alpha)
    low = max(g.ra, g.rb)
    high = min(g.rp + g.module, g.rf)
    worst = 0.0
    for i in range(steps + 1):
        r = low + (high - low) * i / steps
        on_arc = _arc_at_radius(centre, g.flank_arc_radius, r)
        if on_arc is None:
            continue
        want = half_space_angle(g, r)
        worst = max(worst, r * abs(_short(want, _polar(on_arc)) - want))
    return worst


# -- checking ---------------------------------------------------------------


def section_diagnostics(g: InternalDerived, recipe: str, _undercut_limit: int = 0) -> List[Diagnostic]:
    """What is wrong with a ring's tooth-space section, and what is worth knowing, as sentences."""
    out: List[Diagnostic] = []
    if g.backlash >= g.p / 2.0:
        out.append(Diagnostic(ERROR, (
            f"Backlash of {_num(g.backlash)} mm leaves no tooth: it must be less than half "
            f"the circular pitch, {_num(g.p / 2.0)} mm."), "backlash"))
        return out
    if g.rim <= g.df:
        out.append(Diagnostic(ERROR, (
            f"A rim of {_num(g.rim)} mm does not reach past the root diameter of {_num(g.df)} mm; "
            "it must be bigger."), "rim"))
    if g.tip_thickness <= 0.0:
        out.append(Diagnostic(ERROR, (
            f"At {_num(g.teeth, 2)} teeth and {_num(g.pressure_angle_deg)}° the ring's teeth come to a point before "
            "their tips; reduce the backlash or add teeth."), "teeth"))
        return out
    try:
        flank = involute_flank(g) if recipe == RECIPE_INVOLUTE else arc_flank(g)
    except GeometryError as exc:
        out.append(Diagnostic(ERROR, str(exc), "fillet" if "Fillet" in str(exc) else "recipe"))
        return out
    if _polar(flank.fillet_centre) <= 0.0:
        out.append(Diagnostic(ERROR, (
            f"The two {_num(g.fillet)} mm root fillets do not fit in the root of the tooth space; "
            "make Fillet smaller."), "fillet"))
    if recipe == RECIPE_ARCS and _polar(flank.cap_point) >= math.pi / g.teeth:
        out.append(Diagnostic(ERROR, (
            f"Recipe B's flank arcs swing past the middle of the ring's teeth at {_num(g.teeth, 2)} teeth; "
            "use the involute recipe."), "recipe"))

    if g.tip_below_base:
        out.append(Diagnostic(WARNING, (
            f"The teeth's tips, at {_num(g.da)} mm, are inside the base circle of {_num(g.db)} mm, so the "
            "last of each tooth is a straight radial line, not an involute; above "
            f"{int(math.ceil(2.0 / (1.0 - math.cos(g.alpha))))} teeth it would not be."), "teeth"))
    if g.rim > g.df and (g.rim - g.df) / 2.0 < RIM_WARNING_MODULES * g.module:
        out.append(Diagnostic(WARNING, (
            f"The rim is {_num((g.rim - g.df) / 2.0)} mm outside the root, thinner than two modules "
            f"({_num(RIM_WARNING_MODULES * g.module)} mm)."), "rim"))
    if g.tip_thickness < TIP_THICKNESS_WARNING * g.module:
        out.append(Diagnostic(WARNING, (
            f"The ring's tooth tips are {_num(g.tip_thickness)} mm thick, under 0.3 × module "
            f"({_num(TIP_THICKNESS_WARNING * g.module)} mm)."), "teeth"))
    if recipe == RECIPE_INVOLUTE and g.flank_end_d / 2.0 < g.rp + g.module - 1e-9:
        out.append(Diagnostic(WARNING, (
            f"The involute ends at {_num(g.flank_end_d)} mm, inside the {_num(g.d + 2 * g.module)} mm a standard "
            "pinion's tips reach, so the outer end of the working flank is a straight line; make Fillet smaller."),
            "fillet"))
    if recipe == RECIPE_ARCS:
        out.append(Diagnostic(WARNING, (
            f"Arcs stand in for the involute on this ring to within "
            f"{_num(flank_deviation(g) * 1000.0, 1)} µm."), "recipe"))
    return out


def _field_errors(spec: GearSpec, kind: str) -> List[Diagnostic]:
    out = spur.field_errors(spec, kind, internal=True)
    try:
        rim = spec.rim_mm()
    except InputError as exc:
        out.append(Diagnostic(ERROR, str(exc), "rim"))
    else:
        if rim is not None and rim <= 0:
            out.append(Diagnostic(ERROR, f"Rim must be more than zero (got {spec.rim.strip()!r}).", "rim"))
    return out


# -- the equations ----------------------------------------------------------


def profile_variables(g: InternalDerived, pressure_angle: str = PRESSURE_ANGLE,
                      circular_module: str = MODULE, pitch: str = PITCH, inner: str = INNER,
                      rim: bool = True) -> List[GlobalVariable]:
    """The globals a ring's tooth-space sketch reads, from ``"Root Diameter"`` on, in order.

    As :func:`spur.profile_variables`: ``pressure_angle`` and
    ``circular_module`` name the section's own globals, the transverse ones for
    a helical ring. ``pitch`` and ``inner`` name the section's pitch and tip
    diameters, and ``rim`` False leaves out the blank's rim: an internal bevel
    gear's section is its back cone's ring, which has globals of its own and no rim.
    """
    deg_pa, rad_pa = _q(pressure_angle), f"{_q(pressure_angle)} * pi / 180"
    rim_value = (equations.literal(g.rim) if g.rim_typed
                 else f"{_q(ROOT)} + {equations.literal(RIM_MODULES)} * {_q(MODULE)}")
    return [
        GlobalVariable(ROOT, f"{_q(inner)} + 2 * {_q(DEPTH)}"),
        *((GlobalVariable(RIM, rim_value),) if rim else ()),
        GlobalVariable(BASE, f"{_q(pitch)} * cos ( {deg_pa} )", f"{_q(pitch)} * cos ( {rad_pa} )"),
        GlobalVariable(BASE_RADIUS, f"{_q(BASE)} / 2"),
        GlobalVariable(THICKNESS, f"{_q(circular_module)} * pi - {_q(ARC_LENGTH)}"),
        GlobalVariable(HALF_SPACE, f"( {_q(ARC_LENGTH)} / {_q(pitch)} ) * 180 / pi"),
        GlobalVariable(INVOLUTE_FN, f"tan ( {deg_pa} ) - {_q(pressure_angle)} * pi / 180",
                       f"tan ( {rad_pa} ) - {_q(pressure_angle)} * pi / 180"),
        # Negative: the flank narrows outward, the other way from a pinion's.
        GlobalVariable(FLANK_OFFSET, f"0 - {_q(ARC_LENGTH)} / {_q(pitch)} - {_q(INVOLUTE_FN)}"),
        GlobalVariable(TIP_CAP, f"{_q(inner)} - 2 * {_q(MODULE)}"),
        # Bracketed both sides, as spur's: SolidWorks 2026 read "a >= b - c" as "( a >= b ) - c".
        GlobalVariable(FLANK_START, (
            f"IIF ( {_q(BASE)} >= ( {_q(inner)} - {_q(MODULE)} ) , {_q(BASE)} , {_q(inner)} - {_q(MODULE)} )")),
        GlobalVariable(FLANK_END, f"{_q(ROOT)} - {equations.literal(FLANK_END_FILLETS)} * {_q(FILLET)}"),
        GlobalVariable(T1, f"( abs ( ( {_q(FLANK_START)} / {_q(BASE)} ) ^ 2 - 1 ) ) ^ 0.5"),
        GlobalVariable(T2, f"( abs ( ( {_q(FLANK_END)} / {_q(BASE)} ) ^ 2 - 1 ) ) ^ 0.5"),
        GlobalVariable(FLANK_ARC, f"( {_q(pitch)} / 2 ) * sin ( {deg_pa} )",
                       f"( {_q(pitch)} / 2 ) * sin ( {rad_pa} )"),
        GlobalVariable(FLANK_CENTRE, f"{_q(HALF_SPACE)} - {_q(pressure_angle)}"),
    ]


# -- drawing ----------------------------------------------------------------


def _upper_half(g: InternalDerived, recipe: str) -> List[Point2]:
    """From the middle of the space's root, in round the flank to the middle of the next tooth's tip."""
    pts: List[Point2] = []
    if recipe == RECIPE_INVOLUTE:
        flank = involute_flank(g)
        pts.extend(_arc((0.0, 0.0), g.rf, 0.0, _polar(flank.root_touch), 4))
        c = flank.fillet_centre
        a0 = _polar((flank.root_touch[0] - c[0], flank.root_touch[1] - c[1]))
        a1 = _short(a0, _polar((flank.line_outer[0] - c[0], flank.line_outer[1] - c[1])))
        pts.extend(_arc(c, g.fillet, a0, a1, 6)[1:])
        stop = max(g.ra, g.flank_start_d / 2.0)
        t_stop = involute_t(g.rb, stop)
        pts.extend(flank_point(g, g.t2 + (t_stop - g.t2) * i / 12) for i in range(13))
        if stop > g.ra:
            pts.append(_scale((math.cos(_polar(pts[-1])), math.sin(_polar(pts[-1]))), g.ra))
        tip_angle = _polar(pts[-1])
    elif recipe == RECIPE_ARCS:
        flank = arc_flank(g)
        pts.extend(_arc((0.0, 0.0), g.rf, 0.0, _polar(flank.root_touch), 4))
        f = flank.fillet_centre
        a0 = _polar((flank.root_touch[0] - f[0], flank.root_touch[1] - f[1]))
        a1 = _short(a0, _polar((flank.flank_touch[0] - f[0], flank.flank_touch[1] - f[1])))
        pts.extend(_arc(f, g.fillet, a0, a1, 6)[1:])
        b = flank.centre
        tip_point = _arc_at_radius(b, flank.radius, g.ra)
        if tip_point is None:
            raise GeometryError("Recipe B's flank arc never reaches the ring's tip circle.")
        e0 = _polar((flank.flank_touch[0] - b[0], flank.flank_touch[1] - b[1]))
        e1 = _short(e0, _polar((tip_point[0] - b[0], tip_point[1] - b[1])))
        pts.extend(_add(b, _at(flank.radius, e0 + (e1 - e0) * i / 12)) for i in range(1, 13))
        tip_angle = _polar(tip_point)
    else:
        raise GeometryError(f"Unknown recipe {recipe!r}.")
    pts.extend(_arc((0.0, 0.0), g.ra, tip_angle, math.pi / g.teeth, 3)[1:])
    return pts


def outline(g: InternalDerived, recipe: str) -> List[Point2]:
    """The ring's toothed inner edge, closed and counter-clockwise, in mm. The rim is a circle of ``g.rim``."""
    upper = _upper_half(g, recipe)
    period = [_mirror(p) for p in reversed(upper[1:])] + upper
    loop: List[Point2] = []
    for k in range(g.teeth):
        turn = 2.0 * math.pi * k / g.teeth
        loop.extend(_rotate(p, turn) for p in period[:-1])
    loop = auto_close(clean_loop(loop))
    if signed_area(loop[:-1]) <= 0.0:
        raise GeometryError("The ring's outline does not enclose any area; check the fields.")
    return loop


# -- the operations ---------------------------------------------------------


def _ccw_arc(identifier: str, centre: Point2, p: Point2, q: Point2) -> Tuple[Arc, str, str]:
    """An arc from ``p`` to ``q`` the short way round, drawn counter-clockwise as SolidWorks draws arcs.

    Returns the arc and the refs of the ends ``p`` and ``q`` became.
    """
    a = _polar((p[0] - centre[0], p[1] - centre[1]))
    b = _polar((q[0] - centre[0], q[1] - centre[1]))
    if (b - a) % (2.0 * math.pi) <= math.pi:
        return Arc(identifier, centre, p, q, 1), f"{identifier}.start", f"{identifier}.end"
    return Arc(identifier, centre, q, p, 1), f"{identifier}.end", f"{identifier}.start"


def blank_ops(g: InternalDerived) -> List[Op]:
    """An annulus: the rim outside, the teeth's tip circle inside, extruded the face width."""
    lean = math.radians(45.0)
    return [
        OpenSketch("blank", 1),
        Circle("rim", (0.0, 0.0), g.rim_radius),
        Circle("tip", (0.0, 0.0), g.ra),
        Relation("coincident", ("rim.centre", ORIGIN)),
        Relation("coincident", ("tip.centre", ORIGIN)),
        Dimension("Rim", ("rim",), _at(g.rim_radius * 1.15, lean), g.rim),
        Dimension("Tip", ("tip",), _at(g.ra * 0.6, -lean), g.da),
        CloseSketch("blank", BLANK_SKETCH),
        Extrude("blank_extrude", "blank", BLANK, g.face_width, "Width"),
        LinkDimension(f"Rim@{BLANK_SKETCH}", _q(RIM)),
        LinkDimension(f"Tip@{BLANK_SKETCH}", _q(INNER)),
        LinkDimension(f"Width@{BLANK}", _q(FACE_WIDTH)),
    ]


def space_ops(g: InternalDerived, recipe: str, plane: Any = 1, pitch: str = PITCH) -> List[Op]:
    """A ring's tooth-space sketch of either recipe, opened on ``plane``, closed and linked.

    ``pitch`` names the global recipe B's pitch circle is linked to, as :func:`spur.space_ops`.
    """
    return _space_ops_involute(g, plane) if recipe == RECIPE_INVOLUTE else _space_ops_arcs(g, plane, pitch)


def _space_ops_involute(g: InternalDerived, plane: Any) -> List[Op]:
    f = involute_flank(g)
    # The ring's upper flank is the pinion's lower involute with its offset negated, and the other way round.
    x_up, y_up = spur._curve_expressions(lower=True)  # noqa: SLF001
    x_lo, y_lo = spur._curve_expressions(lower=False)  # noqa: SLF001
    t1, t2 = _q(T1), _q(T2)
    fc = f.fillet_centre
    upper_fillet, up_line, up_root = _ccw_arc("F+", fc, f.line_outer, f.root_touch)
    lower_fillet, lo_line, lo_root = _ccw_arc("F-", _mirror(fc), _mirror(f.line_outer), _mirror(f.root_touch))
    rf, rc = g.rf, g.rc
    return [
        OpenSketch("space", plane),
        EquationCurve("I+", x_up, y_up, t1, t2, f.start, f.end),
        EquationCurve("I-", x_lo, y_lo, t1, t2, _mirror(f.start), _mirror(f.end)),
        Circle("cap", (0.0, 0.0), rc, construction=True),
        Line("Li+", f.start, f.cap),
        Line("Li-", _mirror(f.start), _mirror(f.cap)),
        Line("T", f.cap, _mirror(f.cap)),
        Line("Lo+", f.end, f.line_outer),
        Line("Lo-", _mirror(f.end), _mirror(f.line_outer)),
        upper_fillet,
        lower_fillet,
        Arc("R", (0.0, 0.0), _mirror(f.root_touch), f.root_touch, 1),
        Relation("fixed", ("I+",)),
        Relation("fixed", ("I-",)),
        Relation("coincident", ("R.centre", ORIGIN)),
        Relation("coincident", ("cap.centre", ORIGIN)),
        Relation("coincident", ("Li+.start", "I+.start")),
        Relation("coincident", ("Li-.start", "I-.start")),
        Relation("coincident", (ORIGIN, "Li+")),
        Relation("coincident", (ORIGIN, "Li-")),
        Relation("coincident", ("Li+.end", "cap")),
        Relation("coincident", ("Li-.end", "cap")),
        Relation("coincident", ("T.start", "Li+.end")),
        Relation("coincident", ("T.end", "Li-.end")),
        Relation("coincident", ("Lo+.start", "I+.end")),
        Relation("coincident", ("Lo-.start", "I-.end")),
        Relation("coincident", (ORIGIN, "Lo+")),
        Relation("coincident", (ORIGIN, "Lo-")),
        Relation("coincident", (up_line, "Lo+.end")),
        Relation("coincident", (lo_line, "Lo-.end")),
        Relation("coincident", (up_root, "R.end")),
        Relation("coincident", (lo_root, "R.start")),
        Relation("tangent", ("F+", "Lo+")),
        Relation("tangent", ("F-", "Lo-")),
        Relation("tangent", ("F+", "R")),
        Relation("tangent", ("F-", "R")),
        Relation("equal", ("F+", "F-")),
        Dimension("Root", ("R",), (rf * 1.08, rf * 0.05), rf),
        Dimension("Fillet", ("F+",), _add(fc, (g.fillet * 2.0, g.fillet)), g.fillet),
        Dimension("Cap", ("cap",), _at(rc * 0.6, math.radians(-30.0)), g.tip_cap_d),
        CloseSketch("space", SPACE_SKETCH),
        LinkDimension(f"Root@{SPACE_SKETCH}", f"{_q(ROOT)} / 2"),
        LinkDimension(f"Fillet@{SPACE_SKETCH}", _q(FILLET)),
        LinkDimension(f"Cap@{SPACE_SKETCH}", _q(TIP_CAP)),
    ]


def _space_ops_arcs(g: InternalDerived, plane: Any, pitch: str = PITCH) -> List[Op]:
    f = arc_flank(g)
    rp, rb, rc, rf = g.rp, g.rb, g.rc, g.rf
    b = f.centre
    fc = f.fillet_centre
    upper_flank, up_cap, up_touch = _ccw_arc("E+", b, f.cap_point, f.flank_touch)
    lower_flank, lo_cap, lo_touch = _ccw_arc("E-", _mirror(b), _mirror(f.cap_point), _mirror(f.flank_touch))
    upper_fillet, fu_touch, fu_root = _ccw_arc("F+", fc, f.flank_touch, f.root_touch)
    lower_fillet, fl_touch, fl_root = _ccw_arc("F-", _mirror(fc), _mirror(f.flank_touch), _mirror(f.root_touch))
    half = g.psi_s
    return [
        OpenSketch("space", plane),
        Circle("pitch", (0.0, 0.0), rp, construction=True),
        Circle("base", (0.0, 0.0), rb, construction=True),
        Circle("cap", (0.0, 0.0), rc, construction=True),
        Line("CL", (0.0, 0.0), (rc, 0.0), construction=True),
        Line("A", (0.0, 0.0), f.pitch_point, construction=True),
        upper_flank,
        lower_flank,
        upper_fillet,
        lower_fillet,
        Arc("R", (0.0, 0.0), _mirror(f.root_touch), f.root_touch, 1),
        Line("T", f.cap_point, _mirror(f.cap_point)),
        Relation("coincident", ("pitch.centre", ORIGIN)),
        Relation("coincident", ("base.centre", ORIGIN)),
        Relation("coincident", ("cap.centre", ORIGIN)),
        Relation("coincident", ("R.centre", ORIGIN)),
        Relation("coincident", ("CL.start", ORIGIN)),
        Relation("horizontal", ("CL",)),
        Relation("coincident", ("CL.end", "cap")),
        Relation("coincident", ("A.start", ORIGIN)),
        Relation("coincident", ("A.end", "pitch")),
        Relation("coincident", ("E+.centre", "base")),
        Relation("coincident", ("A.end", "E+")),
        Relation("coincident", (up_cap, "cap")),
        Relation("symmetric", ("E+.centre", "E-.centre", "CL")),
        Relation("equal", ("E+", "E-")),
        Relation("coincident", (lo_cap, "cap")),
        Relation("coincident", (fu_touch, up_touch)),
        Relation("coincident", (fu_root, "R.end")),
        Relation("tangent", ("F+", "E+")),
        Relation("tangent", ("F+", "R")),
        Relation("coincident", (fl_touch, lo_touch)),
        Relation("coincident", (fl_root, "R.start")),
        Relation("tangent", ("F-", "E-")),
        Relation("tangent", ("F-", "R")),
        Relation("equal", ("F+", "F-")),
        Relation("coincident", ("T.start", up_cap)),
        Relation("coincident", ("T.end", lo_cap)),
        Dimension("Pitch", ("pitch",), _at(rp * 1.15, math.radians(100.0)), g.d),
        Dimension("Base", ("base",), _at(rb * 1.15, math.radians(125.0)), g.db),
        Dimension("Cap", ("cap",), _at(rc * 0.6, math.radians(-30.0)), g.tip_cap_d),
        Dimension("HalfSpace", ("A", "CL"), _at(rp * 0.5, half / 2.0), math.degrees(half), "deg"),
        Dimension("Flank", ("E+",), _add(b, _scale(_add(f.pitch_point, _scale(b, -1.0)), 0.5)), f.radius),
        Dimension("Fillet", ("F+",), _add(fc, (g.fillet * 2.0, -g.fillet)), g.fillet),
        Dimension("Root", ("R",), (rf * 1.08, rf * 0.05), rf),
        CloseSketch("space", SPACE_SKETCH),
        LinkDimension(f"Pitch@{SPACE_SKETCH}", _q(pitch)),
        LinkDimension(f"Base@{SPACE_SKETCH}", _q(BASE)),
        LinkDimension(f"Cap@{SPACE_SKETCH}", _q(TIP_CAP)),
        LinkDimension(f"HalfSpace@{SPACE_SKETCH}", _q(HALF_SPACE)),
        LinkDimension(f"Flank@{SPACE_SKETCH}", _q(FLANK_ARC)),
        LinkDimension(f"Fillet@{SPACE_SKETCH}", _q(FILLET)),
        LinkDimension(f"Root@{SPACE_SKETCH}", f"{_q(ROOT)} / 2"),
    ]


# -- the gear kinds ---------------------------------------------------------


class InternalSpurGear:
    """A spur ring. Its ``kind`` is the form's kind; ``internal`` is what sets it apart."""

    kind = KIND_SPUR
    internal = True
    recipes = spur.RECIPES
    plan_kind = "internal spur"

    @property
    def default_recipe(self) -> str:
        return findings.DEFAULT_RECIPE

    def recipe_for(self, spec: GearSpec) -> str:
        return spec.recipe_or(self.default_recipe)

    def derive(self, spec: GearSpec) -> InternalDerived:
        for problem in _field_errors(spec, self.kind):
            raise GeometryError(problem.message)
        m = spec.module_mm()
        typed_backlash = spec.backlash_mm()
        typed_fillet = spec.fillet_mm()
        return section(
            spec.teeth_count(), m, spec.pressure_angle_deg(), spec.face_width_mm(), spec.rim_mm(),
            BACKLASH_FACTOR * m if typed_backlash is None else typed_backlash,
            FILLET_FACTOR * m if typed_fillet is None else typed_fillet,
            backlash_typed=typed_backlash is not None, fillet_typed=typed_fillet is not None,
        )

    def validate(self, spec: GearSpec, derived: Optional[InternalDerived] = None) -> List[Diagnostic]:
        problems = _field_errors(spec, self.kind)
        if problems:
            return problems
        try:
            recipe = self.recipe_for(spec)
        except InputError as exc:
            return [Diagnostic(ERROR, str(exc), "recipe")]
        return section_diagnostics(derived if derived is not None else self.derive(spec), recipe)

    def variables(self, spec: GearSpec, derived: InternalDerived) -> List[GlobalVariable]:
        g = derived
        backlash = equations.literal(g.backlash) if g.backlash_typed else f"{BACKLASH_FACTOR} * {_q(MODULE)}"
        fillet = equations.literal(g.fillet) if g.fillet_typed else f"{FILLET_FACTOR} * {_q(MODULE)}"
        return [
            GlobalVariable(TEETH, equations.literal(g.teeth)),
            GlobalVariable(MODULE, equations.literal(g.module)),
            GlobalVariable(PRESSURE_ANGLE, equations.literal(g.pressure_angle_deg)),
            GlobalVariable(INNER, f"( {_q(TEETH)} - 2 ) * {_q(MODULE)}"),
            GlobalVariable(PITCH, f"{_q(TEETH)} * {_q(MODULE)}"),
            GlobalVariable(BACKLASH, backlash),
            GlobalVariable(ARC_LENGTH, f"( ( {_q(MODULE)} * pi ) / 2 + {_q(BACKLASH)} )"),
            GlobalVariable(FILLET, fillet),
            GlobalVariable(DEPTH, f"IIF ( {_q(MODULE)} <= 1.25 , {_q(MODULE)} * 2.4 , {_q(MODULE)} * 2.25 )"),
            GlobalVariable(FACE_WIDTH, equations.literal(g.face_width)),
            *profile_variables(g),
        ]

    def equation_lines(self, spec: GearSpec, derived: InternalDerived, trig: str) -> List[str]:
        return [v.text(trig) for v in self.variables(spec, derived)]

    def outline(self, spec: GearSpec, derived: InternalDerived, recipe: str = "") -> List[Point2]:
        return outline(derived, recipe or self.recipe_for(spec))

    def plan(self, spec: GearSpec, derived: InternalDerived, recipe: str, template: str, path: str) -> BuildPlan:
        g = derived
        recipe = recipe or self.recipe_for(spec)
        ops: List[Op] = [NewPart(template)]
        ops.extend(AddGlobal(v.name, v.expression, v.radian_expression) for v in self.variables(spec, g))
        ops.append(Axis("axis", AXIS_NAME, (2, 3)))
        ops.extend(blank_ops(g))
        ops.extend(space_ops(g, recipe))
        ops.append(Cut("space_cut", "space", SPACE))
        ops.append(CircularPattern("teeth", TEETH_PATTERN, "axis", "space_cut", g.teeth, "Count"))
        ops.append(LinkDimension(f"Count@{TEETH_PATTERN}", _q(TEETH)))
        ops.extend(property_ops(self.kind, recipe, True, [TEETH, MODULE, PRESSURE_ANGLE, FACE_WIDTH, PITCH, INNER,
                                                           RIM]))
        part = re.split(r"[\\/]", path)[-1].rsplit(".", 1)[0] if path else spec.stem()
        ops.append(ManualStep("material", f"Assign a material to {part}; the build leaves it unset."))
        ops.append(Rebuild())
        ops.append(SaveAs(path))
        return BuildPlan(kind=self.plan_kind, recipe=recipe, ops=tuple(ops), path=path)


class InternalHelicalGear(helical.HelicalGear):
    """A helical ring: the helical gear's sweep, of a ring's section, with no bore and the ring's globals."""

    kind = KIND_HELICAL
    internal = True
    fillet_factor = FILLET_FACTOR
    has_bore_global = False

    @property
    def plan_kind(self) -> str:
        return f"internal {self.kind}"

    def _section(self, spec: GearSpec, teeth: int, module: float, pressure_angle: float, width: float,
                 backlash: float, fillet: float, **extra: Any) -> InternalDerived:
        return section(teeth, module, pressure_angle, width, spec.rim_mm(), backlash, fillet, **extra)

    def _errors(self, spec: GearSpec) -> List[Diagnostic]:
        out = super()._errors(spec)
        try:
            rim = spec.rim_mm()
        except InputError as exc:
            out.append(Diagnostic(ERROR, str(exc), "rim"))
        else:
            if rim is not None and rim <= 0:
                out.append(Diagnostic(ERROR, f"Rim must be more than zero (got {spec.rim.strip()!r}).", "rim"))
        return out

    def _n_min(self, normal: float, beta: float) -> float:
        return 0.0

    def _section_diagnostics(self, g: Any, recipe: str, undercut_limit: float) -> List[Diagnostic]:
        return section_diagnostics(g, recipe)

    def _section_variables(self, spec: GearSpec, g: Any, beta_rad: str) -> List[GlobalVariable]:
        s = g.section
        beta = _q(helical.HELIX_ANGLE)
        backlash = equations.literal(s.backlash) if s.backlash_typed else f"{BACKLASH_FACTOR} * {_q(MODULE)}"
        fillet = equations.literal(s.fillet) if s.fillet_typed else f"{FILLET_FACTOR} * {_q(MODULE)}"
        tm = _q(helical.TRANSVERSE_MODULE)
        return [
            GlobalVariable(INNER, f"{_q(TEETH)} * {tm} - 2 * {_q(MODULE)}"),
            GlobalVariable(PITCH, f"{_q(TEETH)} * {tm}"),
            GlobalVariable(BACKLASH, backlash),
            GlobalVariable(ARC_LENGTH, f"( ( {tm} * pi ) / 2 + {_q(BACKLASH)} / cos ( {beta} ) )",
                           f"( ( {tm} * pi ) / 2 + {_q(BACKLASH)} / cos ( {beta_rad} ) )"),
            GlobalVariable(FILLET, fillet),
            GlobalVariable(DEPTH, f"IIF ( {_q(MODULE)} <= 1.25 , {_q(MODULE)} * 2.4 , {_q(MODULE)} * 2.25 )"),
            GlobalVariable(FACE_WIDTH, equations.literal(s.face_width)),
            *profile_variables(s, helical.TRANSVERSE_PRESSURE_ANGLE, helical.TRANSVERSE_MODULE),
        ]

    def _section_outline(self, spec: GearSpec, g: Any, recipe: str) -> List[Point2]:
        return outline(g, recipe)

    def _blank_ops(self, g: Any) -> List[Op]:
        return blank_ops(g)

    def _space_ops(self, g: Any, recipe: str, plane: str) -> List[Op]:
        return space_ops(g, recipe, plane)

    def _bore_ops(self, spec: GearSpec, g: Any) -> List[Op]:
        return []

    def _property_sizes(self, spec: GearSpec, g: Any) -> List[str]:
        return [TEETH, MODULE, PRESSURE_ANGLE, helical.HELIX_ANGLE, FACE_WIDTH, PITCH, INNER, RIM]


class InternalHerringboneGear(InternalHelicalGear):
    kind = KIND_HERRINGBONE


__all__ = [
    "INNER", "RIM", "InternalDerived", "InternalHelicalGear", "InternalHerringboneGear", "InternalSpurGear",
    "arc_flank", "contact_ratio", "flank_point", "half_space_angle", "involute_flank", "outline", "section",
    "tip_clash",
]
