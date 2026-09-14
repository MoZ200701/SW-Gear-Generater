"""Spur gears: the involute maths, the checks, and the two ways to build one.

Millimetres and degrees at the boundary, radians inside. The tooth *space* is
the unit of construction: one space, centred on +X, is cut from a blank the size
of the outer diameter and patterned round the axis. So every routine here that
draws describes that one space, and the whole-gear outline is it rotated N times.

The two recipes differ only in the flank:

* **A, involute** — the true involute, as two Equation Driven Curves. The curve
  starts at ``Flank Start Diameter``, the larger of the base circle and three
  fillet radii above the root, and a radial line bridges down to the root
  fillet. One sketch topology then serves gears whose base circle is above the
  root and gears whose base circle is below it, which matters because a sketch
  cannot change topology when ``No. of Teeth`` changes on a rebuild.
* **B, arcs** — each flank is the involute's osculating circle at the pitch
  point: centred on the base circle, radius ``rp · sin α``. Circles, arcs, lines
  and relations only. It is an approximation, and :func:`flank_deviation` says
  by how much.

Both close the space with a chord beyond the outer diameter, so nothing has to
coincide with the edge of the blank. That closure is not possible for every
gear — a very small tooth count swings the flank round so far that the chord
cuts back inside the outer diameter — and :meth:`SpurGear.validate` refuses
those gears with a sentence rather than building a part with slivers in it.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .. import findings
from ..spec import RECIPE_ARCS, RECIPE_INVOLUTE, GearSpec, InputError
from . import equations
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
    OpenSketch,
    Op,
    Point2,
    Rebuild,
    Relation,
    SaveAs,
)

KIND = "spur"
RECIPES = {RECIPE_INVOLUTE: "Involute", RECIPE_ARCS: "Arcs"}

BACKLASH_FACTOR = 0.3      # the user's own "Backlash"= 0.3 * "Module"
FILLET_FACTOR = 0.38       # the user's own "Fillet Radius"= 0.38 * "Module"
MIN_TEETH = 6
PRESSURE_ANGLE_MIN = 10.0
PRESSURE_ANGLE_MAX = 35.0
TIP_THICKNESS_WARNING = 0.3   # × module
FLANK_START_FILLETS = 3.0     # the involute starts this many fillet radii above the root

# The global variables, by name. The first ten are the user's own, byte for byte.
TEETH = "No. of Teeth"
MODULE = "Module"
BORE = "Bore Diameter"
PRESSURE_ANGLE = "Pressure Angle"
OUTER = "Outer Diameter"
PITCH = "Pitch Diameter"
BACKLASH = "Backlash"
ARC_LENGTH = "Arc Length"
FILLET = "Fillet Radius"
DEPTH = "Tooth Depth"
FACE_WIDTH = "Face Width"
ROOT = "Root Diameter"
BASE = "Base Diameter"
BASE_RADIUS = "Base Radius"
THICKNESS = "Tooth Thickness"
HALF_SPACE = "Half Space Angle"
INVOLUTE_FN = "Involute Fn"
FLANK_OFFSET = "Flank Offset"
TIP_CAP = "Tip Cap Diameter"
FLANK_START = "Flank Start Diameter"
T1 = "Involute t1"
T2 = "Involute t2"
FLANK_ARC = "Flank Arc Radius"
FLANK_CENTRE = "Flank Centre Angle"

USER_VARIABLES = (TEETH, MODULE, BORE, PRESSURE_ANGLE, OUTER, PITCH, BACKLASH, ARC_LENGTH, FILLET, DEPTH)

# Feature and sketch names the build sets, and reads back.
AXIS_NAME = "Gear Axis"
BLANK_SKETCH = "Blank Sketch"
BLANK = "Blank"
SPACE_SKETCH = "Tooth Space Sketch"
SPACE = "Tooth Space"
TEETH_PATTERN = "Teeth"
BORE_SKETCH = "Bore Sketch"
BORE_CUT = "Bore"


def _q(name: str) -> str:
    return equations.quote(name)


def _deg_arg(name: str) -> Tuple[str, str]:
    """A trig argument that is a degree-valued global, in both document modes."""
    return f"{_q(name)}", f"{_q(name)} * pi / 180"


# -- the numbers ------------------------------------------------------------


@dataclass(frozen=True)
class SpurDerived:
    """Every derived size of one spur gear. mm, and radians unless named ``_deg``."""

    teeth: int
    module: float
    pressure_angle_deg: float
    face_width: float
    bore: float
    backlash: float
    fillet: float
    backlash_typed: bool
    fillet_typed: bool

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
    psi_t: float
    inv_alpha: float
    phi: float
    t_max: float
    n_min: float
    tip_cap_d: float
    flank_start_d: float
    t1: float
    t2: float
    form_d: float
    flank_arc_radius: float
    tip_thickness: float

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
    def base_above_root(self) -> bool:
        return self.db > self.df

    @property
    def undercut_limit(self) -> int:
        """The theoretical minimum tooth count, as the whole number it is quoted as.

        ``2 / sin² α`` is 17.10 at 20°, and 17 teeth is the figure every table
        gives, so a gear of exactly 17 is not warned about.
        """
        return int(math.floor(self.n_min + 0.5))

    @property
    def undercut(self) -> bool:
        return self.teeth < self.undercut_limit

    def values(self) -> Dict[str, float]:
        """The value of every global variable, by name."""
        return {
            TEETH: float(self.teeth),
            MODULE: self.module,
            BORE: self.bore,
            PRESSURE_ANGLE: self.pressure_angle_deg,
            OUTER: self.da,
            PITCH: self.d,
            BACKLASH: self.backlash,
            ARC_LENGTH: self.space,
            FILLET: self.fillet,
            DEPTH: self.h,
            FACE_WIDTH: self.face_width,
            ROOT: self.df,
            BASE: self.db,
            BASE_RADIUS: self.rb,
            THICKNESS: self.s,
            HALF_SPACE: math.degrees(self.psi_s),
            INVOLUTE_FN: self.inv_alpha,
            FLANK_OFFSET: self.phi,
            TIP_CAP: self.tip_cap_d,
            FLANK_START: self.flank_start_d,
            T1: self.t1,
            T2: self.t2,
            FLANK_ARC: self.flank_arc_radius,
            FLANK_CENTRE: math.degrees(self.psi_s) + self.pressure_angle_deg,
        }

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def tooth_depth(module: float) -> float:
    """The user's IIF: 2.4 m up to module 1.25, 2.25 m above it."""
    return module * 2.4 if module <= 1.25 else module * 2.25


def undercut_minimum(pressure_angle_deg: float) -> float:
    return 2.0 / math.sin(math.radians(pressure_angle_deg)) ** 2


def involute_point(rb: float, phi: float, t: float) -> Point2:
    u = t + phi
    return (rb * (math.cos(u) + t * math.sin(u)), rb * (math.sin(u) - t * math.cos(u)))


def involute_t(rb: float, r: float) -> float:
    ratio = r / rb
    return math.sqrt(ratio * ratio - 1.0) if ratio > 1.0 else 0.0


def involute_polar(g: SpurDerived, r: float) -> float:
    """The polar angle of the upper flank's involute at radius ``r``."""
    t = involute_t(g.rb, r)
    return g.phi + t - math.atan(t)


def contact_ratio(module: float, teeth_1: int, teeth_2: int, pressure_angle_deg: float,
                  centre_distance: Optional[float] = None) -> float:
    """``[√(ra1²−rb1²) + √(ra2²−rb2²) − C·sin α] / (π·m·cos α)``, standard teeth."""
    alpha = math.radians(pressure_angle_deg)
    if centre_distance is None:
        centre_distance = module * (teeth_1 + teeth_2) / 2.0
    total = 0.0
    for teeth in (teeth_1, teeth_2):
        ra = (teeth + 2) * module / 2.0
        rb = teeth * module * math.cos(alpha) / 2.0
        total += math.sqrt(max(0.0, ra * ra - rb * rb))
    total -= centre_distance * math.sin(alpha)
    return total / (math.pi * module * math.cos(alpha))


# -- point helpers ----------------------------------------------------------


def _polar(p: Point2) -> float:
    return math.atan2(p[1], p[0])


def _radius(p: Point2) -> float:
    return math.hypot(p[0], p[1])


def _at(r: float, angle: float) -> Point2:
    return (r * math.cos(angle), r * math.sin(angle))


def _add(a: Point2, b: Point2) -> Point2:
    return (a[0] + b[0], a[1] + b[1])


def _scale(p: Point2, k: float) -> Point2:
    return (p[0] * k, p[1] * k)


def _mirror(p: Point2) -> Point2:
    return (p[0], -p[1])


def _rotate(p: Point2, angle: float) -> Point2:
    c, s = math.cos(angle), math.sin(angle)
    return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def _same(a: Point2, b: Point2, tol: float = 1e-9) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def signed_area(points: Sequence[Point2]) -> float:
    """Positive when the closed loop runs counter-clockwise."""
    n = len(points)
    total = 0.0
    for i in range(n):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        total += x0 * y1 - x1 * y0
    return 0.5 * total


def clean_loop(points: Sequence[Point2]) -> List[Point2]:
    """Drop repeated points, including the one that closes the loop."""
    pts: List[Point2] = []
    for p in points:
        if not pts or not _same(pts[-1], p):
            pts.append(p)
    while len(pts) > 2 and _same(pts[0], pts[-1]):
        pts.pop()
    return pts


def auto_close(points: Sequence[Point2]) -> List[Point2]:
    """Make the last point exactly equal the first, appending it if there is a gap."""
    pts = list(points)
    if not pts:
        return pts
    if _same(pts[0], pts[-1]):
        pts[-1] = pts[0]
    else:
        pts.append(pts[0])
    return pts


def _arc(centre: Point2, radius: float, a0: float, a1: float, steps: int) -> List[Point2]:
    return [_add(centre, _at(radius, a0 + (a1 - a0) * i / steps)) for i in range(steps + 1)]


def _short(a0: float, a1: float) -> float:
    """``a1`` moved by whole turns to lie within half a turn of ``a0``."""
    while a1 - a0 > math.pi:
        a1 -= 2.0 * math.pi
    while a1 - a0 < -math.pi:
        a1 += 2.0 * math.pi
    return a1


def _ccw(a0: float, a1: float) -> float:
    """``a1`` moved by whole turns to lie within one turn counter-clockwise of ``a0``."""
    while a1 < a0:
        a1 += 2.0 * math.pi
    while a1 - a0 >= 2.0 * math.pi:
        a1 -= 2.0 * math.pi
    return a1


def _num(value: float, places: int = 3) -> str:
    return equations.literal(round(value, places))


# -- the flank of each recipe, upper side of the space ----------------------


@dataclass(frozen=True)
class InvoluteFlank:
    """Recipe A's upper flank: root fillet, radial line, involute."""

    start: Point2           # where the involute begins, at the flank start diameter
    end: Point2             # where it ends, on the tip cap
    line_inner: Point2      # the radial line's inner end, where the fillet meets it
    fillet_centre: Point2
    root_touch: Point2      # where the fillet meets the root circle


@dataclass(frozen=True)
class ArcFlank:
    """Recipe B's upper flank: root fillet, then the osculating arc."""

    centre: Point2          # on the base circle, at polar angle ψs + α
    radius: float
    pitch_point: Point2     # where the arc crosses the pitch circle, at polar angle ψs
    end: Point2             # where it reaches the tip cap
    flank_touch: Point2     # where the fillet meets the arc
    fillet_centre: Point2
    root_touch: Point2


def involute_flank(g: SpurDerived) -> InvoluteFlank:
    rs = g.flank_start_d / 2.0
    start = involute_point(g.rb, g.phi, g.t1)
    end = involute_point(g.rb, g.phi, g.t2)
    theta = _polar(start)
    rf, rho = g.rf, g.fillet
    along = math.sqrt(rf * rf + 2.0 * rf * rho)
    if along > rs:
        raise GeometryError(
            f"The root fillet reaches past the start of the involute ({_num(rs * 2)} mm); make Fillet smaller."
        )
    unit = (math.cos(theta), math.sin(theta))
    toward_space = (math.sin(theta), -math.cos(theta))
    centre = _add(_scale(unit, along), _scale(toward_space, rho))
    return InvoluteFlank(
        start=start,
        end=end,
        line_inner=_scale(unit, along),
        fillet_centre=centre,
        root_touch=_scale(centre, rf / (rf + rho)),
    )


def _arc_at_radius(centre: Point2, radius: float, r: float) -> Optional[Point2]:
    """Where a flank arc about ``centre`` crosses the circle of radius ``r``, space side."""
    d = _radius(centre)
    x = (r * r + d * d - radius * radius) / (2.0 * d)
    h2 = r * r - x * x
    if h2 < 0.0:
        return None
    h = math.sqrt(h2)
    beta = _polar(centre)
    return (x * math.cos(beta) + h * math.sin(beta), x * math.sin(beta) - h * math.cos(beta))


def arc_flank(g: SpurDerived) -> ArcFlank:
    beta = g.psi_s + g.alpha
    centre = _at(g.rb, beta)
    radius = g.flank_arc_radius
    pitch_point = _at(g.rp, g.psi_s)
    end = _arc_at_radius(centre, radius, g.rc)
    if end is None:
        raise GeometryError(
            f"Recipe B's flank arc (radius {_num(radius)} mm) never reaches the tip cap at "
            f"{g.teeth} teeth and {_num(g.pressure_angle_deg)}°, so it cannot close the tooth space; "
            "use the involute recipe."
        )
    rf, rho = g.rf, g.fillet
    r1, r2 = rf + rho, radius + rho
    x = (r1 * r1 + g.rb * g.rb - r2 * r2) / (2.0 * g.rb)
    h2 = r1 * r1 - x * x
    if h2 < 0.0:
        raise GeometryError(
            f"A {_num(rho)} mm root fillet cannot touch both the root and Recipe B's flank arc; "
            "make Fillet smaller."
        )
    h = math.sqrt(h2)
    fillet_centre = (x * math.cos(beta) + h * math.sin(beta), x * math.sin(beta) - h * math.cos(beta))
    toward_arc = (centre[0] - fillet_centre[0], centre[1] - fillet_centre[1])
    length = _radius(toward_arc)
    return ArcFlank(
        centre=centre,
        radius=radius,
        pitch_point=pitch_point,
        end=end,
        flank_touch=_add(fillet_centre, _scale(toward_arc, rho / length)),
        fillet_centre=fillet_centre,
        root_touch=_scale(fillet_centre, rf / r1),
    )


def flank_deviation(g: SpurDerived, steps: int = 200) -> float:
    """Recipe B's worst error against the true involute, in mm along the circle.

    Measured on the working flank, from the base circle (or the root, if that is
    higher) to the outer diameter.
    """
    beta = g.psi_s + g.alpha
    centre = _at(g.rb, beta)
    low = max(g.rb, g.rf)
    worst = 0.0
    for i in range(steps + 1):
        r = low + (g.ra - low) * i / steps
        on_arc = _arc_at_radius(centre, g.flank_arc_radius, r)
        if on_arc is None:
            continue
        worst = max(worst, r * abs(_short(involute_polar(g, r), _polar(on_arc)) - involute_polar(g, r)))
    return worst


# -- the gear kind ----------------------------------------------------------


class SpurGear:
    kind = KIND
    recipes = RECIPES

    @property
    def default_recipe(self) -> str:
        return findings.DEFAULT_RECIPE

    def recipe_for(self, spec: GearSpec) -> str:
        return spec.recipe_or(self.default_recipe)

    # -- deriving --------------------------------------------------------

    def derive(self, spec: GearSpec) -> SpurDerived:
        """Every size of the gear. Raises :class:`GeometryError` on a field that makes none."""
        for problem in _field_errors(spec):
            raise GeometryError(problem.message)

        m = spec.module_mm()
        n = spec.teeth_count()
        alpha_deg = spec.pressure_angle_deg()
        alpha = math.radians(alpha_deg)
        typed_backlash = spec.backlash_mm()
        typed_fillet = spec.fillet_mm()
        j = BACKLASH_FACTOR * m if typed_backlash is None else typed_backlash
        rho = FILLET_FACTOR * m if typed_fillet is None else typed_fillet

        d = n * m
        da = (n + 2) * m
        h = tooth_depth(m)
        df = da - 2.0 * h
        db = d * math.cos(alpha)
        p = math.pi * m
        space = m * math.pi / 2.0 + j
        s = m * math.pi - space
        psi_s = space / d
        inv_alpha = math.tan(alpha) - alpha
        phi = psi_s - inv_alpha
        tip_cap_d = da + 2.0 * m
        floor = df + FLANK_START_FILLETS * rho
        flank_start_d = db if db >= floor else floor
        rp = d / 2.0
        reach = rp * math.sin(alpha) - m / math.sin(alpha)
        rb = db / 2.0
        form_d = 2.0 * math.sqrt(rb * rb + max(0.0, reach) ** 2)

        t_tip = math.sqrt((da / db) ** 2 - 1.0)
        tip_angle = phi + t_tip - math.atan(t_tip)
        return SpurDerived(
            teeth=n, module=m, pressure_angle_deg=alpha_deg, face_width=spec.face_width_mm(),
            bore=spec.bore_mm(), backlash=j, fillet=rho,
            backlash_typed=typed_backlash is not None, fillet_typed=typed_fillet is not None,
            alpha=alpha, d=d, da=da, h=h, df=df, db=db, p=p, space=space, s=s,
            psi_s=psi_s, psi_t=s / d, inv_alpha=inv_alpha, phi=phi, t_max=t_tip,
            n_min=undercut_minimum(alpha_deg), tip_cap_d=tip_cap_d, flank_start_d=flank_start_d,
            t1=math.sqrt((flank_start_d / db) ** 2 - 1.0),
            t2=math.sqrt((tip_cap_d / db) ** 2 - 1.0),
            form_d=form_d, flank_arc_radius=rp * math.sin(alpha),
            tip_thickness=2.0 * (da / 2.0) * (math.pi / n - tip_angle),
        )

    # -- checking --------------------------------------------------------

    def validate(self, spec: GearSpec, derived: Optional[SpurDerived] = None) -> List[Diagnostic]:
        """Everything wrong with the gear, and everything worth knowing, as sentences."""
        problems = _field_errors(spec)
        if problems:
            return problems
        try:
            recipe = self.recipe_for(spec)
        except InputError as exc:
            return [Diagnostic(ERROR, str(exc), "recipe")]
        g = derived if derived is not None else self.derive(spec)
        out: List[Diagnostic] = []

        if g.backlash >= g.p / 2.0:
            out.append(Diagnostic(ERROR, (
                f"Backlash of {_num(g.backlash)} mm leaves no tooth: it must be less than half "
                f"the circular pitch, {_num(g.p / 2.0)} mm."), "backlash"))
            return out
        if g.bore >= g.df:
            out.append(Diagnostic(ERROR, (
                f"Bore of {_num(g.bore)} mm reaches the root diameter of {_num(g.df)} mm; "
                "it must be smaller."), "bore"))
        if g.tip_thickness <= 0.0:
            out.append(Diagnostic(ERROR, (
                f"At {g.teeth} teeth and {_num(g.pressure_angle_deg)}° the teeth come to a point "
                "below the outer diameter; reduce the backlash or add teeth."), "teeth"))
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
        end = flank.end
        if end[0] <= g.ra:
            out.append(Diagnostic(ERROR, (
                f"Recipe {recipe} cannot close the tooth space beyond the outer diameter at {g.teeth} "
                f"teeth and {_num(g.pressure_angle_deg)}°: the flanks swing round too far"
                + ("; use the involute recipe." if recipe == RECIPE_ARCS else "; add teeth.")),
                "teeth"))

        if g.undercut:
            out.append(Diagnostic(WARNING, (
                f"{g.teeth} teeth at {_num(g.pressure_angle_deg)}° is below the undercut limit of "
                f"{g.undercut_limit}: a generated gear would lose the bottom of its flanks, which "
                "this profile does not show."), "teeth"))
        if g.bore > 0.0 and (g.df - g.bore) / 2.0 < g.module and g.bore < g.df:
            out.append(Diagnostic(WARNING, (
                f"The bore leaves {_num((g.df - g.bore) / 2.0)} mm of rim under the teeth, thinner "
                f"than one module ({_num(g.module)} mm)."), "bore"))
        if g.tip_thickness < TIP_THICKNESS_WARNING * g.module:
            out.append(Diagnostic(WARNING, (
                f"The tooth tip is {_num(g.tip_thickness)} mm thick, under 0.3 × module "
                f"({_num(TIP_THICKNESS_WARNING * g.module)} mm)."), "teeth"))
        if recipe == RECIPE_INVOLUTE and g.flank_start_d > g.form_d + 1e-9:
            out.append(Diagnostic(WARNING, (
                f"The involute starts at {_num(g.flank_start_d)} mm, above the form diameter of "
                f"{_num(g.form_d)} mm, so the bottom of the working flank is a straight line."),
                "fillet"))
        if recipe == RECIPE_ARCS:
            out.append(Diagnostic(WARNING, (
                f"Arcs stand in for the involute on this gear to within "
                f"{_num(flank_deviation(g) * 1000.0, 1)} µm."), "recipe"))
        return out

    # -- the equations ---------------------------------------------------

    def variables(self, spec: GearSpec, derived: SpurDerived) -> List[GlobalVariable]:
        """The global variables, in the order they must be added.

        Each is written for a degree document, with a radian form beside it
        wherever trig makes the two differ.
        """
        g = derived
        deg_pa, rad_pa = _deg_arg(PRESSURE_ANGLE)
        backlash = equations.literal(g.backlash) if g.backlash_typed else f"{BACKLASH_FACTOR} * {_q(MODULE)}"
        fillet = equations.literal(g.fillet) if g.fillet_typed else f"{FILLET_FACTOR} * {_q(MODULE)}"
        return [
            GlobalVariable(TEETH, equations.literal(g.teeth)),
            GlobalVariable(MODULE, equations.literal(g.module)),
            GlobalVariable(BORE, equations.literal(g.bore)),
            GlobalVariable(PRESSURE_ANGLE, equations.literal(g.pressure_angle_deg)),
            GlobalVariable(OUTER, f"( {_q(TEETH)} + 2 ) * {_q(MODULE)}"),
            GlobalVariable(PITCH, f"{_q(TEETH)} * {_q(MODULE)}"),
            GlobalVariable(BACKLASH, backlash),
            GlobalVariable(ARC_LENGTH, f"( ( {_q(MODULE)} * pi ) / 2 + {_q(BACKLASH)} )"),
            GlobalVariable(FILLET, fillet),
            GlobalVariable(DEPTH, f"IIF ( {_q(MODULE)} <= 1.25 , {_q(MODULE)} * 2.4 , {_q(MODULE)} * 2.25 )"),
            GlobalVariable(FACE_WIDTH, equations.literal(g.face_width)),
            GlobalVariable(ROOT, f"{_q(OUTER)} - 2 * {_q(DEPTH)}"),
            GlobalVariable(BASE, f"{_q(PITCH)} * cos ( {deg_pa} )", f"{_q(PITCH)} * cos ( {rad_pa} )"),
            GlobalVariable(BASE_RADIUS, f"{_q(BASE)} / 2"),
            GlobalVariable(THICKNESS, f"{_q(MODULE)} * pi - {_q(ARC_LENGTH)}"),
            GlobalVariable(HALF_SPACE, f"( {_q(ARC_LENGTH)} / {_q(PITCH)} ) * 180 / pi"),
            GlobalVariable(INVOLUTE_FN, f"tan ( {deg_pa} ) - {_q(PRESSURE_ANGLE)} * pi / 180",
                           f"tan ( {rad_pa} ) - {_q(PRESSURE_ANGLE)} * pi / 180"),
            GlobalVariable(FLANK_OFFSET, f"{_q(ARC_LENGTH)} / {_q(PITCH)} - {_q(INVOLUTE_FN)}"),
            GlobalVariable(TIP_CAP, f"{_q(OUTER)} + 2 * {_q(MODULE)}"),
            GlobalVariable(FLANK_START, (
                f"IIF ( {_q(BASE)} >= {_q(ROOT)} + 3 * {_q(FILLET)} , {_q(BASE)} , "
                f"{_q(ROOT)} + 3 * {_q(FILLET)} )")),
            GlobalVariable(T1, f"sqr ( ( {_q(FLANK_START)} / {_q(BASE)} ) ^ 2 - 1 )"),
            GlobalVariable(T2, f"sqr ( ( {_q(TIP_CAP)} / {_q(BASE)} ) ^ 2 - 1 )"),
            GlobalVariable(FLANK_ARC, f"( {_q(PITCH)} / 2 ) * sin ( {deg_pa} )",
                           f"( {_q(PITCH)} / 2 ) * sin ( {rad_pa} )"),
            GlobalVariable(FLANK_CENTRE, f"{_q(HALF_SPACE)} + {_q(PRESSURE_ANGLE)}"),
        ]

    def equation_lines(self, spec: GearSpec, derived: SpurDerived, trig: str) -> List[str]:
        return [v.text(trig) for v in self.variables(spec, derived)]

    # -- drawing ---------------------------------------------------------

    def outline(self, spec: GearSpec, derived: SpurDerived, recipe: str = "") -> List[Point2]:
        """The whole gear's outline, closed and counter-clockwise, in mm."""
        g = derived
        recipe = recipe or self.recipe_for(spec)
        upper = _upper_half(g, recipe)
        period = [_mirror(p) for p in reversed(upper[1:])] + upper
        loop: List[Point2] = []
        for k in range(g.teeth):
            turn = 2.0 * math.pi * k / g.teeth
            loop.extend(_rotate(p, turn) for p in period[:-1])
        loop = auto_close(clean_loop(loop))
        if signed_area(loop[:-1]) <= 0.0:
            raise GeometryError("The gear outline does not enclose any area; check the fields.")
        return loop

    # -- building --------------------------------------------------------

    def plan(self, spec: GearSpec, derived: SpurDerived, recipe: str, template: str, path: str) -> BuildPlan:
        g = derived
        recipe = recipe or self.recipe_for(spec)
        ops: List[Op] = [NewPart(template)]
        ops.extend(AddGlobal(v.name, v.expression, v.radian_expression) for v in self.variables(spec, g))

        ops.append(Axis("axis", AXIS_NAME, (2, 3)))
        ops.extend(_blank_ops(g))
        ops.extend(_space_ops_involute(g) if recipe == RECIPE_INVOLUTE else _space_ops_arcs(g))
        ops.append(Cut("space_cut", "space", SPACE))
        ops.append(CircularPattern("teeth", TEETH_PATTERN, "axis", "space_cut", g.teeth, "Count"))
        ops.append(LinkDimension(f"Count@{TEETH_PATTERN}", _q(TEETH)))
        if spec.has_bore():
            ops.extend(_bore_ops(g))
        ops.append(ManualStep("material", f"Assign a material to {spec.stem()}; the build leaves it unset."))
        ops.append(Rebuild())
        ops.append(SaveAs(path))
        return BuildPlan(kind=KIND, recipe=recipe, ops=tuple(ops), path=path)


def _field_errors(spec: GearSpec) -> List[Diagnostic]:
    """The fields that stop a gear being worked out at all."""
    out: List[Diagnostic] = []

    def read(field: str, reader):
        try:
            return reader()
        except InputError as exc:
            out.append(Diagnostic(ERROR, str(exc), field))
            return None

    if spec.kind != KIND:
        out.append(Diagnostic(ERROR, f"Only spur gears can be built so far (got {spec.kind!r}).", "kind"))
    m = read("module", spec.module_mm)
    if m is not None and m <= 0:
        out.append(Diagnostic(ERROR, f"Module must be more than zero (got {spec.module.strip()!r}).", "module"))
    n = read("teeth", spec.teeth_count)
    if n is not None and n < MIN_TEETH:
        out.append(Diagnostic(ERROR, f"No. of teeth must be at least {MIN_TEETH} (got {n}).", "teeth"))
    alpha = read("pressure_angle", spec.pressure_angle_deg)
    if alpha is not None and not PRESSURE_ANGLE_MIN <= alpha <= PRESSURE_ANGLE_MAX:
        out.append(Diagnostic(ERROR, (
            f"Pressure angle must be between {_num(PRESSURE_ANGLE_MIN)}° and "
            f"{_num(PRESSURE_ANGLE_MAX)}° (got {_num(alpha)}°)."), "pressure_angle"))
    width = read("face_width", spec.face_width_mm)
    if width is not None and width <= 0:
        out.append(Diagnostic(ERROR, f"Face width must be more than zero (got {spec.face_width.strip()!r}).", "face_width"))
    bore = read("bore", spec.bore_mm)
    if bore is not None and bore < 0:
        out.append(Diagnostic(ERROR, f"Bore must not be negative (got {spec.bore.strip()!r}).", "bore"))
    backlash = read("backlash", spec.backlash_mm)
    if backlash is not None and backlash < 0:
        out.append(Diagnostic(ERROR, f"Backlash must not be negative (got {spec.backlash.strip()!r}).", "backlash"))
    fillet = read("fillet", spec.fillet_mm)
    if fillet is not None and fillet <= 0:
        out.append(Diagnostic(ERROR, f"Fillet must be more than zero (got {spec.fillet.strip()!r}).", "fillet"))
    shift = read("profile_shift", spec.profile_shift_value)
    if shift is not None and shift != 0:
        out.append(Diagnostic(ERROR, (
            f"Profile shift is reserved for a later version and must be 0 (got {spec.profile_shift.strip()!r})."),
            "profile_shift"))
    return out


# -- the outline of one space's upper half ----------------------------------


def _upper_half(g: SpurDerived, recipe: str) -> List[Point2]:
    """From the middle of the space's root, round to the middle of the next tooth's tip."""
    pts: List[Point2] = []
    half_period = math.pi / g.teeth

    if recipe == RECIPE_INVOLUTE:
        flank = involute_flank(g)
        pts.extend(_arc((0.0, 0.0), g.rf, 0.0, _polar(flank.root_touch), 4))
        c = flank.fillet_centre
        a0 = _polar((flank.root_touch[0] - c[0], flank.root_touch[1] - c[1]))
        a1 = _short(a0, _polar((flank.line_inner[0] - c[0], flank.line_inner[1] - c[1])))
        pts.extend(_arc(c, g.fillet, a0, a1, 6)[1:])
        t_tip = g.t_max
        ts = [g.t1 + (t_tip - g.t1) * i / 12 for i in range(13)]
        pitch_t = math.tan(g.alpha)
        if g.t1 < pitch_t < t_tip:
            ts = sorted(set(ts + [pitch_t]))
        pts.extend(involute_point(g.rb, g.phi, t) for t in ts)
        tip_angle = involute_polar(g, g.ra)
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
            raise GeometryError("Recipe B's flank arc never reaches the outer diameter on this gear.")
        e0 = _polar((flank.flank_touch[0] - b[0], flank.flank_touch[1] - b[1]))
        e1 = _ccw(e0, _polar((tip_point[0] - b[0], tip_point[1] - b[1])))
        angles = [e0 + (e1 - e0) * i / 12 for i in range(13)]
        ep = _ccw(e0, _polar((flank.pitch_point[0] - b[0], flank.pitch_point[1] - b[1])))
        if e0 < ep < e1:
            angles = sorted(set(angles + [ep]))
        pts.extend(_add(b, _at(flank.radius, a)) for a in angles[1:])
        tip_angle = _polar(tip_point)
    else:
        raise GeometryError(f"Unknown recipe {recipe!r}.")

    pts.extend(_arc((0.0, 0.0), g.ra, tip_angle, half_period, 3)[1:])
    return pts


# -- the operations for each part of the build ------------------------------


def _blank_ops(g: SpurDerived) -> List[Op]:
    lean = math.radians(45.0)
    return [
        OpenSketch("blank", 1),
        Circle("od", (0.0, 0.0), g.ra),
        Relation("coincident", ("od.centre", ORIGIN)),
        Dimension("OD", ("od",), _at(g.ra * 1.2, lean), g.da),
        CloseSketch("blank", BLANK_SKETCH),
        Extrude("blank_extrude", "blank", BLANK, g.face_width, "Width"),
        LinkDimension(f"OD@{BLANK_SKETCH}", _q(OUTER)),
        LinkDimension(f"Width@{BLANK}", _q(FACE_WIDTH)),
    ]


def _curve_expressions(lower: bool) -> Tuple[str, str, str, str]:
    """x and y of the upper (or lower) involute, degree-document then radian-document."""
    br, off = _q(BASE_RADIUS), _q(FLANK_OFFSET)
    forms = []
    for arg in (f"( t + {off} ) * 180 / pi", f"( t + {off} )"):
        x = f"{br} * ( cos ( {arg} ) + t * sin ( {arg} ) )"
        if lower:
            y = f"{br} * ( t * cos ( {arg} ) - sin ( {arg} ) )"
        else:
            y = f"{br} * ( sin ( {arg} ) - t * cos ( {arg} ) )"
        forms.append((x, y))
    return forms[0][0], forms[0][1], forms[1][0], forms[1][1]


def _space_ops_involute(g: SpurDerived) -> List[Op]:
    f = involute_flank(g)
    x_up, y_up, x_up_rad, y_up_rad = _curve_expressions(lower=False)
    x_lo, y_lo, x_lo_rad, y_lo_rad = _curve_expressions(lower=True)
    t1, t2 = _q(T1), _q(T2)
    rf = g.rf
    return [
        OpenSketch("space", 1),
        EquationCurve("I+", x_up, y_up, t1, t2, f.start, f.end, x_up_rad, y_up_rad),
        EquationCurve("I-", x_lo, y_lo, t1, t2, _mirror(f.start), _mirror(f.end), x_lo_rad, y_lo_rad),
        Line("L+", f.start, f.line_inner),
        Line("L-", _mirror(f.start), _mirror(f.line_inner)),
        Arc("F+", f.fillet_centre, f.line_inner, f.root_touch, 1),
        Arc("F-", _mirror(f.fillet_centre), _mirror(f.root_touch), _mirror(f.line_inner), 1),
        Arc("R", (0.0, 0.0), _mirror(f.root_touch), f.root_touch, 1),
        Line("T", f.end, _mirror(f.end)),
        Relation("coincident", ("R.centre", ORIGIN)),
        Relation("coincident", ("L+.start", "I+.start")),
        Relation("coincident", ("L-.start", "I-.start")),
        Relation("coincident", (ORIGIN, "L+")),
        Relation("coincident", (ORIGIN, "L-")),
        Relation("coincident", ("F+.start", "L+.end")),
        Relation("coincident", ("F-.end", "L-.end")),
        Relation("coincident", ("F+.end", "R.end")),
        Relation("coincident", ("F-.start", "R.start")),
        Relation("tangent", ("F+", "L+")),
        Relation("tangent", ("F-", "L-")),
        Relation("tangent", ("F+", "R")),
        Relation("tangent", ("F-", "R")),
        Relation("equal", ("F+", "F-")),
        Relation("coincident", ("T.start", "I+.end")),
        Relation("coincident", ("T.end", "I-.end")),
        Dimension("Root", ("R",), (rf * 0.5, rf * 0.05), rf),
        Dimension("Fillet", ("F+",), _add(f.fillet_centre, (g.fillet * 2.0, g.fillet)), g.fillet),
        CloseSketch("space", SPACE_SKETCH),
        LinkDimension(f"Root@{SPACE_SKETCH}", f"{_q(ROOT)} / 2"),
        LinkDimension(f"Fillet@{SPACE_SKETCH}", _q(FILLET)),
    ]


def _space_ops_arcs(g: SpurDerived) -> List[Op]:
    f = arc_flank(g)
    rp, rb, rc, rf = g.rp, g.rb, g.rc, g.rf
    fillet_up_start, fillet_up_end = f.flank_touch, f.root_touch
    fc = f.fillet_centre
    sweep = _ccw(_polar((fillet_up_start[0] - fc[0], fillet_up_start[1] - fc[1])),
                 _polar((fillet_up_end[0] - fc[0], fillet_up_end[1] - fc[1])))
    sweep -= _polar((fillet_up_start[0] - fc[0], fillet_up_start[1] - fc[1]))
    if sweep > math.pi:  # the short way round is clockwise, so run it the other way
        fillet_up_start, fillet_up_end = fillet_up_end, fillet_up_start
    upper_fillet = Arc("F+", fc, fillet_up_start, fillet_up_end, 1)
    lower_fillet = Arc("F-", _mirror(fc), _mirror(fillet_up_end), _mirror(fillet_up_start), 1)
    touches_start = _same(fillet_up_start, f.flank_touch)
    half = g.psi_s
    return [
        OpenSketch("space", 1),
        Circle("pitch", (0.0, 0.0), rp, construction=True),
        Circle("base", (0.0, 0.0), rb, construction=True),
        Circle("cap", (0.0, 0.0), rc, construction=True),
        Line("CL", (0.0, 0.0), (rc, 0.0), construction=True),
        Line("A", (0.0, 0.0), f.pitch_point, construction=True),
        Arc("E+", f.centre, f.flank_touch, f.end, 1),
        Arc("E-", _mirror(f.centre), _mirror(f.end), _mirror(f.flank_touch), 1),
        upper_fillet,
        lower_fillet,
        Arc("R", (0.0, 0.0), _mirror(f.root_touch), f.root_touch, 1),
        Line("T", f.end, _mirror(f.end)),
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
        Relation("coincident", ("E+.end", "cap")),
        Relation("symmetric", ("E+.centre", "E-.centre", "CL")),
        Relation("equal", ("E+", "E-")),
        Relation("coincident", ("E-.start", "cap")),
        Relation("coincident", ("F+.start" if touches_start else "F+.end", "E+.start")),
        Relation("coincident", ("F+.end" if touches_start else "F+.start", "R.end")),
        Relation("tangent", ("F+", "E+")),
        Relation("tangent", ("F+", "R")),
        Relation("coincident", ("F-.end" if touches_start else "F-.start", "E-.end")),
        Relation("coincident", ("F-.start" if touches_start else "F-.end", "R.start")),
        Relation("tangent", ("F-", "E-")),
        Relation("tangent", ("F-", "R")),
        Relation("equal", ("F+", "F-")),
        Relation("coincident", ("T.start", "E+.end")),
        Relation("coincident", ("T.end", "E-.start")),
        Dimension("Pitch", ("pitch",), _at(rp * 1.15, math.radians(100.0)), g.d),
        Dimension("Base", ("base",), _at(rb * 1.15, math.radians(125.0)), g.db),
        Dimension("Cap", ("cap",), _at(rc * 1.15, math.radians(75.0)), g.tip_cap_d),
        Dimension("HalfSpace", ("A", "CL"), _at(rp * 0.5, half / 2.0), math.degrees(half), "deg"),
        Dimension("Flank", ("E+",), _add(f.centre, _scale(_add(f.pitch_point, _scale(f.centre, -1.0)), 0.5)),
                  f.radius),
        Dimension("Fillet", ("F+",), _add(fc, (g.fillet * 2.0, -g.fillet)), g.fillet),
        Dimension("Root", ("R",), (rf * 0.5, rf * 0.05), rf),
        CloseSketch("space", SPACE_SKETCH),
        LinkDimension(f"Pitch@{SPACE_SKETCH}", _q(PITCH)),
        LinkDimension(f"Base@{SPACE_SKETCH}", _q(BASE)),
        LinkDimension(f"Cap@{SPACE_SKETCH}", _q(TIP_CAP)),
        LinkDimension(f"HalfSpace@{SPACE_SKETCH}", _q(HALF_SPACE)),
        LinkDimension(f"Flank@{SPACE_SKETCH}", _q(FLANK_ARC)),
        LinkDimension(f"Fillet@{SPACE_SKETCH}", _q(FILLET)),
        LinkDimension(f"Root@{SPACE_SKETCH}", f"{_q(ROOT)} / 2"),
    ]


def _bore_ops(g: SpurDerived) -> List[Op]:
    r = g.bore / 2.0
    return [
        OpenSketch("bore", 1),
        Circle("bore_circle", (0.0, 0.0), r),
        Relation("coincident", ("bore_circle.centre", ORIGIN)),
        Dimension("Bore", ("bore_circle",), _at(r * 1.3, math.radians(-45.0)), g.bore),
        CloseSketch("bore", BORE_SKETCH),
        Cut("bore_cut", "bore", BORE_CUT),
        LinkDimension(f"Bore@{BORE_SKETCH}", _q(BORE)),
    ]
