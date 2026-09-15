"""Straight bevel gears, Gleason proportions: the cone, the back-cone section, the checks and the globals.

A straight bevel gear's teeth run straight toward the pitch apex, where the
axes of the two gears meet. Its size is given at the **heel**, the outer end of
the face: ``module`` there, a pitch diameter ``d = m·N``, and a pitch cone of
half-angle ``δ`` set by the mate's tooth count and the shaft angle ``Σ``::

    δ = atan( sin Σ / (N_mate / N + cos Σ) )          R = d / (2 sin δ)

``R`` is the cone distance, apex to heel along the pitch cone.

The tooth proportions are the Gleason straight bevel system as KHK tabulates it:
a working depth of ``2m``, the bigger gear's addendum
``0.540m + 0.460m / ((N_big cos δ_small) / (N_small cos δ_big))`` and the
smaller gear's the rest of the working depth, a dedendum of ``2.188m − ha``,
and uniform clearance — a face cone parallel to the mate's root cone, so the
face angle is ``δ + θf,mate``. The tooth thickness is shifted to match the
addendum, ``s = πm/2 + 2(ha − m) tan α``; Gleason's chart factor K is taken as 0.

The tooth is cut from its **Tredgold section**: the tooth of a spur gear of
``Nv = N / cos δ`` teeth on the back cone, of radius ``rv = d / (2 cos δ)``,
drawn in the plane square to the pitch cone at the heel. Sections of the same
shape, scaled by distance from the apex, are the tooth anywhere along the face,
so the space is a loft between the heel's section and the toe's.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from .. import findings
from ..spec import KIND_BEVEL, GearSpec, InputError
from . import equations, spur
from .base import (
    ERROR,
    ORIGIN,
    WARNING,
    AddGlobal,
    Axis,
    BuildPlan,
    CircularPattern,
    CloseSketch,
    Diagnostic,
    Dimension,
    GeometryError,
    GlobalVariable,
    Line,
    LinkDimension,
    LoftCut,
    ManualStep,
    NewPart,
    Op,
    OpenSketch,
    Point2,
    Rebuild,
    RefPlaneNormal,
    Relation,
    Revolve,
    SaveAs,
)
from .spur import (
    ARC_LENGTH,
    BACKLASH,
    BLANK,
    BLANK_SKETCH,
    BACKLASH_FACTOR,
    BORE,
    DEPTH,
    FACE_WIDTH,
    FILLET,
    FILLET_FACTOR,
    MODULE,
    OUTER,
    PITCH,
    PRESSURE_ANGLE,
    TEETH,
    SpurDerived,
)

# Gleason straight bevel system (KHK, "Calculation of gear dimensions", bevel gears).
WORKING_DEPTH = 2.0         # × module
WHOLE_DEPTH = 2.188         # × module; the dedendum is this less the addendum
BIG_ADDENDUM = 0.540        # × module
RATIO_ADDENDUM = 0.460      # × module, over the equivalent ratio

SHAFT_MIN = 10.0
SHAFT_MAX = 170.0
CROWN_LIMIT = 89.0          # degrees of pitch cone at and above which a gear is a crown or internal bevel
OVERRUN_MODULES = 1.0       # the loft runs this far past the heel and the toe

# The globals a bevel gear adds, by name.
SHAFT = "Shaft Angle"
MATE_TEETH = "Mate Teeth"
PITCH_CONE = "Pitch Cone Angle"
MATE_CONE = "Mate Cone Angle"
CONE_DISTANCE = "Cone Distance"
ADDENDUM = "Addendum"
MATE_ADDENDUM = "Mate Addendum"
DEDENDUM = "Dedendum"
MATE_DEDENDUM = "Mate Dedendum"
DEDENDUM_ANGLE = "Dedendum Angle"
MATE_DEDENDUM_ANGLE = "Mate Dedendum Angle"
FACE_ANGLE = "Face Angle"
ROOT_ANGLE = "Root Angle"
OVERRUN = "Overrun"
BACK_PITCH = "Back Cone Pitch Diameter"
BACK_OUTER = "Back Cone Outer Diameter"
HEEL_DISTANCE = "Heel Distance"
TOE_DISTANCE = "Toe Distance"
HEEL_SCALE = "Heel Scale"
TOE_SCALE = "Toe Scale"
HEEL_RADIUS = "Heel Virtual Radius"
TOE_RADIUS = "Toe Virtual Radius"

# The user's names a bevel part keeps, in their order; "Tooth Depth" is Gleason's, not the IIF.
USER_VARIABLES = (TEETH, MODULE, BORE, PRESSURE_ANGLE, OUTER, PITCH, BACKLASH, ARC_LENGTH, FILLET, DEPTH)


def _q(name: str) -> str:
    return equations.quote(name)


def _num(value: float, places: int = 3) -> str:
    return equations.literal(round(value, places))


# -- the numbers ------------------------------------------------------------


def pitch_cone_angle(teeth: int, mate_teeth: int, shaft: float) -> float:
    """``δ``, degrees: ``atan2(sin Σ, N_mate / N + cos Σ)``, which is past 90° when the denominator is negative."""
    return math.degrees(math.atan2(math.sin(math.radians(shaft)), mate_teeth / teeth + math.cos(math.radians(shaft))))


def addenda(module: float, teeth: int, mate_teeth: int, delta: float, delta_mate: float) -> Tuple[float, float]:
    """``(this gear's addendum, the mate's)``, Gleason: the bigger gear gets ``0.54m + 0.46m / q``."""
    c, c_mate = math.cos(math.radians(delta)), math.cos(math.radians(delta_mate))
    if teeth >= mate_teeth:
        big = BIG_ADDENDUM * module + RATIO_ADDENDUM * module / ((teeth * c_mate) / (mate_teeth * c))
        return big, WORKING_DEPTH * module - big
    big = BIG_ADDENDUM * module + RATIO_ADDENDUM * module / ((mate_teeth * c) / (teeth * c_mate))
    return WORKING_DEPTH * module - big, big


def cone_distance(module: float, teeth_1: int, teeth_2: int, shaft: float) -> float:
    """``R = (m / 2) √(N1² + N2² + 2 N1 N2 cos Σ) / sin Σ`` — the same for both gears of a pair."""
    s = math.radians(shaft)
    return module / 2.0 * math.sqrt(teeth_1 ** 2 + teeth_2 ** 2 + 2.0 * teeth_1 * teeth_2 * math.cos(s)) / math.sin(s)


def undercut_limit(pressure_angle_deg: float, shift: float) -> float:
    """``2 (1 − x) / sin² α``: the fewest virtual teeth a gear of shift ``x`` has without undercut."""
    return 2.0 * (1.0 - shift) / math.sin(math.radians(pressure_angle_deg)) ** 2


@dataclass(frozen=True)
class BevelDerived:
    """A straight bevel gear: its cone and Gleason tooth, and its heel section as a spur gear's.

    Everything of the section — ``rb``, ``phi``, ``t1`` … — reads through, and
    ``d``, ``da`` and ``teeth`` are the bevel gear's own, so the readouts treat
    it as a gear. Lengths in mm at the heel, angles in degrees.
    """

    section: SpurDerived        # of the heel back cone: Nv teeth, pitch diameter dv
    teeth: int
    mate_teeth: int
    module: float
    pressure_angle_deg: float
    shaft_angle: float
    face_width: float
    bore: float
    d: float
    delta: float
    delta_mate: float
    cone_distance: float
    addendum: float
    mate_addendum: float
    dedendum: float
    mate_dedendum: float
    dedendum_angle: float
    mate_dedendum_angle: float
    face_angle: float
    root_angle: float
    da: float
    crown_to_apex: float
    shift: float
    virtual_teeth: float
    virtual_radius: float
    overrun: float

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") or name == "section":
            raise AttributeError(name)
        return getattr(self.section, name)

    @property
    def rp(self) -> float:
        return self.d / 2.0

    @property
    def ra(self) -> float:
        return self.da / 2.0

    @property
    def h(self) -> float:
        return self.addendum + self.dedendum

    @property
    def heel_distance(self) -> float:
        return self.cone_distance + self.overrun

    @property
    def toe_distance(self) -> float:
        return self.cone_distance - self.face_width - self.overrun

    @property
    def toe_scale(self) -> float:
        return (self.cone_distance - self.face_width) / self.cone_distance

    @property
    def undercut_limit(self) -> int:
        return int(math.floor(undercut_limit(self.pressure_angle_deg, self.shift) + 0.5))

    @property
    def undercut(self) -> bool:
        return self.virtual_teeth < undercut_limit(self.pressure_angle_deg, self.shift)

    def values(self) -> Dict[str, float]:
        """The value of every global variable, by name."""
        s = self.section
        out = dict(s.values())
        tan_delta = math.tan(math.radians(self.delta))
        out.update({
            TEETH: float(self.teeth),
            MODULE: self.module,
            BORE: self.bore,
            PRESSURE_ANGLE: self.pressure_angle_deg,
            SHAFT: self.shaft_angle,
            MATE_TEETH: float(self.mate_teeth),
            PITCH_CONE: self.delta,
            MATE_CONE: self.delta_mate,
            ADDENDUM: self.addendum,
            OUTER: self.da,
            PITCH: self.d,
            CONE_DISTANCE: self.cone_distance,
            MATE_ADDENDUM: self.mate_addendum,
            DEDENDUM: self.dedendum,
            MATE_DEDENDUM: self.mate_dedendum,
            DEPTH: self.h,
            DEDENDUM_ANGLE: self.dedendum_angle,
            MATE_DEDENDUM_ANGLE: self.mate_dedendum_angle,
            FACE_ANGLE: self.face_angle,
            ROOT_ANGLE: self.root_angle,
            OVERRUN: self.overrun,
            BACK_PITCH: s.d,
            BACK_OUTER: s.da,
            HEEL_DISTANCE: self.heel_distance,
            TOE_DISTANCE: self.toe_distance,
            HEEL_SCALE: self.heel_distance / self.cone_distance,
            TOE_SCALE: self.toe_distance / self.cone_distance,
            HEEL_RADIUS: self.heel_distance * tan_delta,
            TOE_RADIUS: self.toe_distance * tan_delta,
        })
        return out

    def to_dict(self) -> Dict[str, Any]:
        data = {key: value for key, value in asdict(self).items() if key != "section"}
        data["section"] = asdict(self.section)
        return data


def _field_errors(spec: GearSpec) -> List[Diagnostic]:
    out = spur.field_errors(spec, KIND_BEVEL)
    try:
        mate = spec.mate_teeth_count()
    except InputError as exc:
        out.append(Diagnostic(ERROR, str(exc), "mate_teeth"))
    else:
        if mate < spur.MIN_TEETH:
            out.append(Diagnostic(ERROR, f"Mate teeth must be at least {spur.MIN_TEETH} (got {mate}).", "mate_teeth"))
    try:
        shaft = spec.shaft_angle_deg()
    except InputError as exc:
        out.append(Diagnostic(ERROR, str(exc), "shaft_angle"))
    else:
        if not SHAFT_MIN <= shaft <= SHAFT_MAX:
            out.append(Diagnostic(ERROR, (
                f"Shaft angle must be between {_num(SHAFT_MIN)}° and {_num(SHAFT_MAX)}° (got {_num(shaft)}°)."),
                "shaft_angle"))
    return out


def derive(spec: GearSpec) -> BevelDerived:
    """Every size of a bevel gear. Raises :class:`GeometryError` on a form that makes none."""
    for problem in _field_errors(spec):
        raise GeometryError(problem.message)
    m = spec.module_mm()
    n = spec.teeth_count()
    mate = spec.mate_teeth_count()
    shaft = spec.shaft_angle_deg()
    alpha = spec.pressure_angle_deg()
    width = spec.face_width_mm()
    delta = pitch_cone_angle(n, mate, shaft)
    delta_mate = shaft - delta
    for name, angle in (("This gear", delta), ("Its mate", delta_mate)):
        if angle >= CROWN_LIMIT:
            raise GeometryError(
                f"{name} would have a pitch cone of {_num(angle, 2)}°: a crown or internal bevel gear, which is "
                "not built; change the teeth or the shaft angle.")
    d = m * n
    radius = d / (2.0 * math.sin(math.radians(delta)))
    ha, ha_mate = addenda(m, n, mate, delta, delta_mate)
    hf, hf_mate = WHOLE_DEPTH * m - ha, WHOLE_DEPTH * m - ha_mate
    theta_f = math.degrees(math.atan(hf / radius))
    theta_f_mate = math.degrees(math.atan(hf_mate / radius))
    shift = (ha - m) / m
    cos_delta = math.cos(math.radians(delta))
    virtual = n / cos_delta
    typed_backlash = spec.backlash_mm()
    typed_fillet = spec.fillet_mm()
    j = BACKLASH_FACTOR * m if typed_backlash is None else typed_backlash
    section = spur.profile(
        virtual, m, alpha, width, 0.0, j, FILLET_FACTOR * m if typed_fillet is None else typed_fillet,
        backlash_typed=typed_backlash is not None, fillet_typed=typed_fillet is not None,
        addendum=ha, whole_depth=ha + hf, space_change=-2.0 * (ha - m) * math.tan(math.radians(alpha)),
    )
    return BevelDerived(
        section=section, teeth=n, mate_teeth=mate, module=m, pressure_angle_deg=alpha, shaft_angle=shaft,
        face_width=width, bore=spec.bore_mm(), d=d, delta=delta, delta_mate=delta_mate, cone_distance=radius,
        addendum=ha, mate_addendum=ha_mate, dedendum=hf, mate_dedendum=hf_mate, dedendum_angle=theta_f,
        mate_dedendum_angle=theta_f_mate, face_angle=delta + theta_f_mate, root_angle=delta - theta_f,
        da=d + 2.0 * ha * cos_delta, crown_to_apex=radius * cos_delta - ha * math.sin(math.radians(delta)),
        shift=shift, virtual_teeth=virtual, virtual_radius=d / (2.0 * cos_delta), overrun=OVERRUN_MODULES * m,
    )


def contact_ratio(g: BevelDerived) -> float:
    """εα of the virtual spur pair on the back cones, with each gear's own Gleason addendum."""
    alpha = math.radians(g.pressure_angle_deg)
    rv, rv_mate = g.virtual_radius, g.mate_teeth * g.module / (2.0 * math.cos(math.radians(g.delta_mate)))
    total = math.sqrt((rv + g.addendum) ** 2 - (rv * math.cos(alpha)) ** 2)
    total += math.sqrt((rv_mate + g.mate_addendum) ** 2 - (rv_mate * math.cos(alpha)) ** 2)
    total -= (rv + rv_mate) * math.sin(alpha)
    return total / (math.pi * g.module * math.cos(alpha))


def toe_root_radius(g: BevelDerived) -> float:
    """How far the root cone is from the axis at the toe, mm."""
    along = g.cone_distance - g.face_width
    return along * math.sin(math.radians(g.delta)) - g.dedendum * (along / g.cone_distance) * math.cos(math.radians(g.delta))


def validate(spec: GearSpec, derived: Optional[BevelDerived] = None, recipe: str = "A") -> List[Diagnostic]:
    problems = _field_errors(spec)
    if problems:
        return problems
    try:
        g = derived if derived is not None else derive(spec)
    except GeometryError as exc:
        return [Diagnostic(ERROR, str(exc), "teeth")]
    out: List[Diagnostic] = []
    if g.face_width >= g.cone_distance / 2.0:
        out.append(Diagnostic(ERROR, (
            f"A face width of {_num(g.face_width)} mm is half the cone distance of {_num(g.cone_distance)} mm or more; "
            "the teeth would shrink to nothing toward the apex."), "face_width"))
        return out
    out.extend(d for d in spur.section_diagnostics(g.section, recipe, g.undercut_limit) if d.field != "bore")
    if g.bore > 0.0 and g.bore / 2.0 >= toe_root_radius(g) - g.module:
        out.append(Diagnostic(ERROR, (
            f"Bore of {_num(g.bore)} mm reaches within a module of the root at the toe, "
            f"{_num(2.0 * toe_root_radius(g))} mm across; it must be smaller."), "bore"))
    if g.face_width > g.cone_distance / 3.0 or g.face_width > 10.0 * g.module:
        out.append(Diagnostic(WARNING, (
            f"A face width of {_num(g.face_width)} mm is more than the Gleason limit of the smaller of a third of the "
            f"cone distance and ten modules ({_num(min(g.cone_distance / 3.0, 10.0 * g.module))} mm)."), "face_width"))
    return out


# -- the equations ----------------------------------------------------------


def variables(spec: GearSpec, g: BevelDerived) -> List[GlobalVariable]:
    """The global variables in order: the user's names where a bevel gear has them, every global before its use."""
    s = g.section
    atn = "atn"

    def deg(name: str) -> Tuple[str, str]:
        return _q(name), f"{_q(name)} * pi / 180"

    shaft, shaft_r = deg(SHAFT)
    cone, cone_r = deg(PITCH_CONE)
    mate_cone, mate_cone_r = deg(MATE_CONE)
    alpha, alpha_r = deg(PRESSURE_ANGLE)
    m, n, nm = _q(MODULE), _q(TEETH), _q(MATE_TEETH)
    denominator = f"( {nm} / {n} + cos ( {shaft} ) )"
    denominator_r = f"( {nm} / {n} + cos ( {shaft_r} ) )"
    base_angle = f"{atn} ( sin ( {shaft} ) / {denominator} )"
    base_angle_r = f"{atn} ( sin ( {shaft_r} ) / {denominator_r} ) * 180 / pi"

    def big(n_big: str, cos_small: str, n_small: str, cos_big: str) -> str:
        return (f"{equations.literal(BIG_ADDENDUM)} * {m} + {equations.literal(RATIO_ADDENDUM)} * {m} / "
                f"( ( {n_big} * cos ( {cos_small} ) ) / ( {n_small} * cos ( {cos_big} ) ) )")

    addendum = (f"IIF ( {n} >= {nm} , {big(n, mate_cone, nm, cone)} , "
                f"2 * {m} - ( {big(nm, cone, n, mate_cone)} ) )")
    addendum_r = (f"IIF ( {n} >= {nm} , {big(n, mate_cone_r, nm, cone_r)} , "
                  f"2 * {m} - ( {big(nm, cone_r, n, mate_cone_r)} ) )")
    backlash = equations.literal(s.backlash) if s.backlash_typed else f"{BACKLASH_FACTOR} * {m}"
    fillet = equations.literal(s.fillet) if s.fillet_typed else f"{FILLET_FACTOR} * {m}"
    return [
        GlobalVariable(TEETH, equations.literal(g.teeth)),
        GlobalVariable(MODULE, equations.literal(g.module)),
        GlobalVariable(BORE, equations.literal(g.bore)),
        GlobalVariable(PRESSURE_ANGLE, equations.literal(g.pressure_angle_deg)),
        GlobalVariable(SHAFT, equations.literal(g.shaft_angle)),
        GlobalVariable(MATE_TEETH, equations.literal(g.mate_teeth)),
        # Past 90° when the denominator is negative; both branches are evaluated, so a zero one is refused by validate.
        GlobalVariable(PITCH_CONE, f"IIF ( {denominator} > 0 , {base_angle} , 180 + {base_angle} )",
                       f"IIF ( {denominator_r} > 0 , {base_angle_r} , 180 + {base_angle_r} )"),
        GlobalVariable(MATE_CONE, f"{shaft} - {cone}"),
        GlobalVariable(ADDENDUM, addendum, addendum_r),
        GlobalVariable(OUTER, f"{n} * {m} + 2 * {_q(ADDENDUM)} * cos ( {cone} )",
                       f"{n} * {m} + 2 * {_q(ADDENDUM)} * cos ( {cone_r} )"),
        GlobalVariable(PITCH, f"{n} * {m}"),
        GlobalVariable(BACKLASH, backlash),
        GlobalVariable(ARC_LENGTH, f"( ( {m} * pi ) / 2 + {_q(BACKLASH)} - 2 * ( {_q(ADDENDUM)} - {m} ) * tan ( {alpha} ) )",
                       f"( ( {m} * pi ) / 2 + {_q(BACKLASH)} - 2 * ( {_q(ADDENDUM)} - {m} ) * tan ( {alpha_r} ) )"),
        GlobalVariable(FILLET, fillet),
        GlobalVariable(MATE_ADDENDUM, f"2 * {m} - {_q(ADDENDUM)}"),
        GlobalVariable(DEDENDUM, f"{equations.literal(WHOLE_DEPTH)} * {m} - {_q(ADDENDUM)}"),
        GlobalVariable(DEPTH, f"{_q(ADDENDUM)} + {_q(DEDENDUM)}"),
        GlobalVariable(MATE_DEDENDUM, f"{equations.literal(WHOLE_DEPTH)} * {m} - {_q(MATE_ADDENDUM)}"),
        GlobalVariable(FACE_WIDTH, equations.literal(g.face_width)),
        GlobalVariable(CONE_DISTANCE, f"{_q(PITCH)} / ( 2 * sin ( {cone} ) )",
                       f"{_q(PITCH)} / ( 2 * sin ( {cone_r} ) )"),
        GlobalVariable(DEDENDUM_ANGLE, f"{atn} ( {_q(DEDENDUM)} / {_q(CONE_DISTANCE)} )",
                       f"{atn} ( {_q(DEDENDUM)} / {_q(CONE_DISTANCE)} ) * 180 / pi"),
        GlobalVariable(MATE_DEDENDUM_ANGLE, f"{atn} ( {_q(MATE_DEDENDUM)} / {_q(CONE_DISTANCE)} )",
                       f"{atn} ( {_q(MATE_DEDENDUM)} / {_q(CONE_DISTANCE)} ) * 180 / pi"),
        GlobalVariable(FACE_ANGLE, f"{cone} + {_q(MATE_DEDENDUM_ANGLE)}"),
        GlobalVariable(ROOT_ANGLE, f"{cone} - {_q(DEDENDUM_ANGLE)}"),
        GlobalVariable(OVERRUN, m),
        GlobalVariable(BACK_PITCH, f"{_q(PITCH)} / cos ( {cone} )", f"{_q(PITCH)} / cos ( {cone_r} )"),
        GlobalVariable(BACK_OUTER, f"{_q(BACK_PITCH)} + 2 * {_q(ADDENDUM)}"),
        *spur.profile_variables(PRESSURE_ANGLE, MODULE, pitch=BACK_PITCH, outer=BACK_OUTER),
        GlobalVariable(HEEL_DISTANCE, f"{_q(CONE_DISTANCE)} + {_q(OVERRUN)}"),
        GlobalVariable(TOE_DISTANCE, f"{_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)} - {_q(OVERRUN)}"),
        GlobalVariable(HEEL_SCALE, f"{_q(HEEL_DISTANCE)} / {_q(CONE_DISTANCE)}"),
        GlobalVariable(TOE_SCALE, f"{_q(TOE_DISTANCE)} / {_q(CONE_DISTANCE)}"),
        GlobalVariable(HEEL_RADIUS, f"{_q(HEEL_DISTANCE)} * tan ( {cone} )", f"{_q(HEEL_DISTANCE)} * tan ( {cone_r} )"),
        GlobalVariable(TOE_RADIUS, f"{_q(TOE_DISTANCE)} * tan ( {cone} )", f"{_q(TOE_DISTANCE)} * tan ( {cone_r} )"),
    ]


# -- building ---------------------------------------------------------------

# Feature and sketch names the build sets, and reads back.
CONE_SKETCH = "Cone Sketch"
HEEL_PLANE = "Heel Plane"
TOE_PLANE = "Toe Plane"
HEEL_SKETCH = "Heel Section Sketch"
TOE_SKETCH = "Toe Section Sketch"


def _top(x: float, z: float) -> Point2:
    """A model point in the Top plane (x, z) as its sketch has it."""
    return (x, -z) if findings.TOP_SKETCH_Y_IS_MINUS_Z else (x, z)


def _deg(name: str) -> Tuple[str, str]:
    return _q(name), f"{_q(name)} * pi / 180"


@dataclass(frozen=True)
class BlankPoints:
    """The corners of the half-section the blank is revolved from, in model (x, z) mm."""

    pitch: Point2        # heel pitch point, the generatrix's end
    toe_pitch: Point2
    heel_tip: Point2
    heel_rim: Point2     # a module below the root at the heel
    toe_tip: Point2
    toe_rim: Point2
    back_bore: Point2    # where the heel rim's square line meets the bore
    front_bore: Point2

    def loop(self) -> List[Point2]:
        """Counter-clockwise in (x, z): toe rim, toe tip, heel tip, heel rim, back bore, front bore."""
        return [self.toe_rim, self.toe_tip, self.heel_tip, self.heel_rim, self.back_bore, self.front_bore]


def blank_points(g: BevelDerived) -> BlankPoints:
    d = math.radians(g.delta)
    gv = (math.sin(d), math.cos(d))
    nv = (math.cos(d), -math.sin(d))
    radius, width, m = g.cone_distance, g.face_width, g.module
    tan_f, tan_fm = math.tan(math.radians(g.dedendum_angle)), math.tan(math.radians(g.mate_dedendum_angle))

    def along(t: float, s: float) -> Point2:
        return (t * gv[0] + s * nv[0], t * gv[1] + s * nv[1])

    heel_rim = along(radius, -(g.dedendum + m / math.cos(d)))
    toe_rim = along(radius - width, -(g.dedendum - width * tan_f + m / math.cos(d)))
    bore = g.bore / 2.0
    return BlankPoints(
        pitch=along(radius, 0.0), toe_pitch=along(radius - width, 0.0),
        heel_tip=along(radius, g.addendum), heel_rim=heel_rim,
        toe_tip=along(radius - width, g.addendum - width * tan_fm), toe_rim=toe_rim,
        back_bore=(bore, heel_rim[1]), front_bore=(bore, toe_rim[1]),
    )


def outline(g: BevelDerived) -> List[Point2]:
    """The blank's half-section, closed, in (radial, axial) mm."""
    loop = blank_points(g).loop()
    return loop + [loop[0]]


def _blank_ops(g: BevelDerived) -> List[Op]:
    """The half-section on the Top plane, every length and angle linked, revolved about the axis line ``A``.

    The generatrix ``G`` runs from the apex at the origin at the pitch cone
    angle from the axis, to the heel's pitch point; ``G2`` to the toe's. Short
    construction lines square to them carry the addendum and the rims, the face
    line is at the mate's dedendum angle to ``G`` (uniform clearance), and the
    two rim lines run square to the axis in to the bore. Eighteen unknowns,
    eighteen constraints.
    """
    p = blank_points(g)
    d = g.delta
    radius, width = g.cone_distance, g.face_width
    cone, cone_r = _deg(PITCH_CONE)
    m = _q(MODULE)

    def half_angle_point(length: float, first: float, second: float) -> Point2:
        middle = math.radians((first + second) / 2.0)
        return _top(length * math.sin(middle), length * math.cos(middle))

    def offset(point: Point2, dx: float, dz: float) -> Point2:
        return _top(point[0] + dx, point[1] + dz)

    nx, nz = math.cos(math.radians(d)), -math.sin(math.radians(d))
    heel_rim_len = f"{_q(DEDENDUM)} + {m} / cos ( {cone} )"
    heel_rim_len_r = f"{_q(DEDENDUM)} + {m} / cos ( {cone_r} )"
    toe_rim_len = f"{_q(DEDENDUM)} - {_q(FACE_WIDTH)} * tan ( {_q(DEDENDUM_ANGLE)} ) + {m} / cos ( {cone} )"
    toe_rim_len_r = (f"{_q(DEDENDUM)} - {_q(FACE_WIDTH)} * tan ( {_q(DEDENDUM_ANGLE)} * pi / 180 ) + "
                     f"{m} / cos ( {cone_r} )")
    back = f"{_q(CONE_DISTANCE)} * sin ( {cone} ) - {_q(DEDENDUM)} * cos ( {cone} ) - {m} - {_q(BORE)} / 2"
    back_r = f"{_q(CONE_DISTANCE)} * sin ( {cone_r} ) - {_q(DEDENDUM)} * cos ( {cone_r} ) - {m} - {_q(BORE)} / 2"
    front = (f"( {_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)} ) * sin ( {cone} ) - ( {toe_rim_len} ) * cos ( {cone} ) - "
             f"{_q(BORE)} / 2")
    front_r = (f"( {_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)} ) * sin ( {cone_r} ) - ( {toe_rim_len_r} ) * "
               f"cos ( {cone_r} ) - {_q(BORE)} / 2")
    s_heel = p.heel_rim[0] - g.bore / 2.0
    s_toe = p.toe_rim[0] - g.bore / 2.0
    return [
        OpenSketch("blank", 2),
        Line("A", (0.0, 0.0), _top(0.0, radius), construction=True),
        Line("G", (0.0, 0.0), _top(*p.pitch), construction=True),
        Line("G2", (0.0, 0.0), _top(*p.toe_pitch), construction=True),
        Line("L1", _top(*p.toe_rim), _top(*p.toe_tip)),
        Line("L2", _top(*p.toe_tip), _top(*p.heel_tip)),
        Line("L3", _top(*p.heel_tip), _top(*p.heel_rim)),
        Line("L4", _top(*p.heel_rim), _top(*p.back_bore)),
        Line("L5", _top(*p.back_bore), _top(*p.front_bore)),
        Line("L6", _top(*p.front_bore), _top(*p.toe_rim)),
        Line("Ha", _top(*p.pitch), _top(*p.heel_tip), construction=True),
        Line("Hc", _top(*p.pitch), _top(*p.heel_rim), construction=True),
        Line("Hf", _top(*p.toe_pitch), _top(*p.toe_rim), construction=True),
        Relation("coincident", ("A.start", ORIGIN)),
        Relation("vertical", ("A",)),
        Relation("coincident", ("G.start", "A.start")),
        Relation("coincident", ("G2.start", "A.start")),
        Relation("coincident", ("L1.end", "L2.start")),
        Relation("coincident", ("L2.end", "L3.start")),
        Relation("coincident", ("L3.end", "L4.start")),
        Relation("coincident", ("L4.end", "L5.start")),
        Relation("coincident", ("L5.end", "L6.start")),
        Relation("coincident", ("L6.end", "L1.start")),
        Relation("coincident", ("Ha.start", "G.end")),
        Relation("coincident", ("Hc.start", "G.end")),
        Relation("coincident", ("Hf.start", "G2.end")),
        Relation("coincident", ("Ha.end", "L2.end")),
        Relation("coincident", ("Hc.end", "L3.end")),
        Relation("coincident", ("Hf.end", "L1.start")),
        Relation("horizontal", ("L4",)),
        Relation("horizontal", ("L6",)),
        Dimension("Axis", ("A",), _top(-radius * 0.1, radius * 0.5), radius),
        Dimension("Cone", ("G", "A"), half_angle_point(radius * 0.4, 0.0, d), d, "deg"),
        Dimension("Heel", ("G",), offset(p.pitch, -nx * 3.0, -nz * 3.0), radius),
        Dimension("Toe Cone", ("G2", "A"), half_angle_point((radius - width) * 0.3, 0.0, d), d, "deg"),
        Dimension("Toe", ("G2",), offset(p.toe_pitch, -nx * 6.0, -nz * 6.0), radius - width),
        Dimension("Heel Square", ("Ha", "G"), offset(p.pitch, nx * 0.5 - math.sin(math.radians(d)) * 0.5,
                                                    nz * 0.5 - math.cos(math.radians(d)) * 0.5), 90.0, "deg"),
        Dimension("Addendum", ("Ha",), offset(p.heel_tip, 1.0, 2.0), g.addendum),
        Dimension("Root Square", ("Hc", "G"), offset(p.pitch, -nx * 0.5 - math.sin(math.radians(d)) * 0.5,
                                                    -nz * 0.5 - math.cos(math.radians(d)) * 0.5), 90.0, "deg"),
        Dimension("Heel Rim", ("Hc",), offset(p.heel_rim, 1.0, 2.0), g.dedendum + g.module / math.cos(math.radians(d))),
        Dimension("Toe Square", ("Hf", "G2"), offset(p.toe_pitch, -nx * 0.5 - math.sin(math.radians(d)) * 0.5,
                                                    -nz * 0.5 - math.cos(math.radians(d)) * 0.5), 90.0, "deg"),
        Dimension("Toe Rim", ("Hf",), offset(p.toe_rim, 1.0, -2.0),
                  math.hypot(p.toe_pitch[0] - p.toe_rim[0], p.toe_pitch[1] - p.toe_rim[1])),
        Dimension("Front Square", ("L1", "G2"), offset(p.toe_pitch, nx * 0.5 - math.sin(math.radians(d)) * 0.5,
                                                      nz * 0.5 - math.cos(math.radians(d)) * 0.5), 90.0, "deg"),
        Dimension("Face", ("L2", "G"), offset(p.pitch, nx * g.addendum / 2.0, nz * g.addendum / 2.0),
                  g.mate_dedendum_angle, "deg"),
        Dimension("Back", ("L4",), offset(p.back_bore, s_heel / 2.0, 3.0), s_heel),
        Dimension("Front", ("L6",), offset(p.front_bore, s_toe / 2.0, -3.0), s_toe),
        CloseSketch("blank", BLANK_SKETCH),
        LinkDimension(f"Axis@{BLANK_SKETCH}", _q(CONE_DISTANCE)),
        LinkDimension(f"Cone@{BLANK_SKETCH}", _q(PITCH_CONE)),
        LinkDimension(f"Heel@{BLANK_SKETCH}", _q(CONE_DISTANCE)),
        LinkDimension(f"Toe Cone@{BLANK_SKETCH}", _q(PITCH_CONE)),
        LinkDimension(f"Toe@{BLANK_SKETCH}", f"{_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)}"),
        LinkDimension(f"Addendum@{BLANK_SKETCH}", _q(ADDENDUM)),
        LinkDimension(f"Heel Rim@{BLANK_SKETCH}", heel_rim_len, heel_rim_len_r),
        LinkDimension(f"Toe Rim@{BLANK_SKETCH}", toe_rim_len, toe_rim_len_r),
        LinkDimension(f"Face@{BLANK_SKETCH}", _q(MATE_DEDENDUM_ANGLE)),
        LinkDimension(f"Back@{BLANK_SKETCH}", back, back_r),
        LinkDimension(f"Front@{BLANK_SKETCH}", front, front_r),
        Revolve("blank_revolve", "blank", BLANK, "A"),
    ]


def _cone_ops(g: BevelDerived) -> List[Op]:
    """The heel's and the toe's generatrix lines, the planes square to them, and nothing else."""
    d = math.radians(g.delta)
    heel, toe = g.heel_distance, g.toe_distance
    gv = (math.sin(d), math.cos(d))

    def bisector(length: float) -> Point2:
        return _top(length * math.sin(d / 2.0), length * math.cos(d / 2.0))

    return [
        OpenSketch("cone", 2),
        Line("c_V", (0.0, 0.0), _top(0.0, g.cone_distance), construction=True),
        Line("c_Gh", (0.0, 0.0), _top(heel * gv[0], heel * gv[1])),
        Line("c_Gt", (0.0, 0.0), _top(toe * gv[0], toe * gv[1])),
        Relation("coincident", ("c_V.start", ORIGIN)),
        Relation("vertical", ("c_V",)),
        Relation("coincident", ("c_Gh.start", "c_V.start")),
        Relation("coincident", ("c_Gt.start", "c_V.start")),
        Dimension("Axis", ("c_V",), _top(-g.cone_distance * 0.1, g.cone_distance * 0.5), g.cone_distance),
        Dimension("Heel Cone", ("c_Gh", "c_V"), bisector(heel * 0.5), g.delta, "deg"),
        Dimension("Heel", ("c_Gh",), _top(heel * gv[0] + 4.0, heel * gv[1]), heel),
        Dimension("Toe Cone", ("c_Gt", "c_V"), bisector(toe * 0.3), g.delta, "deg"),
        Dimension("Toe", ("c_Gt",), _top(toe * gv[0] + 4.0, toe * gv[1] - 4.0), toe),
        CloseSketch("cone", CONE_SKETCH),
        LinkDimension(f"Axis@{CONE_SKETCH}", _q(CONE_DISTANCE)),
        LinkDimension(f"Heel Cone@{CONE_SKETCH}", _q(PITCH_CONE)),
        LinkDimension(f"Heel@{CONE_SKETCH}", _q(HEEL_DISTANCE)),
        LinkDimension(f"Toe Cone@{CONE_SKETCH}", _q(PITCH_CONE)),
        LinkDimension(f"Toe@{CONE_SKETCH}", _q(TOE_DISTANCE)),
        RefPlaneNormal("heel", HEEL_PLANE, "c_Gh", "c_Gh.end"),
        RefPlaneNormal("toe", TOE_PLANE, "c_Gt", "c_Gt.end"),
    ]


def _section_ops(g: BevelDerived, recipe: str) -> List[Op]:
    tan_delta = math.tan(math.radians(g.delta))
    sign = findings.BEVEL_SECTION_X_SIGN
    ops: List[Op] = []
    for plane, distance, radius_global, scale_global, sketch_id, sketch_name, prefix in (
        ("heel", g.heel_distance, HEEL_RADIUS, HEEL_SCALE, "heel_space", HEEL_SKETCH, "h_"),
        ("toe", g.toe_distance, TOE_RADIUS, TOE_SCALE, "toe_space", TOE_SKETCH, "t_"),
    ):
        frame = spur.SectionFrame(
            centre_x=-sign * distance * tan_delta, centre_global=radius_global,
            scale=distance / g.cone_distance, scale_global=scale_global,
            sketch_id=sketch_id, sketch_name=sketch_name, prefix=prefix, x_sign=sign,
        )
        ops.extend(spur.space_ops(g.section, recipe, plane=plane, frame=frame))
    return ops


class BevelGear:
    """A straight bevel gear. See the module docstring."""

    kind = KIND_BEVEL
    recipes = spur.RECIPES
    internal = False

    @property
    def default_recipe(self) -> str:
        return findings.DEFAULT_RECIPE

    def recipe_for(self, spec: GearSpec) -> str:
        return spec.recipe_or(self.default_recipe)

    def derive(self, spec: GearSpec) -> BevelDerived:
        return derive(spec)

    def validate(self, spec: GearSpec, derived: Optional[BevelDerived] = None) -> List[Diagnostic]:
        try:
            recipe = self.recipe_for(spec)
        except InputError as exc:
            return [Diagnostic(ERROR, str(exc), "recipe")]
        return validate(spec, derived, recipe)

    def variables(self, spec: GearSpec, derived: BevelDerived) -> List[GlobalVariable]:
        return variables(spec, derived)

    def equation_lines(self, spec: GearSpec, derived: BevelDerived, trig: str) -> List[str]:
        return [v.text(trig) for v in variables(spec, derived)]

    def outline(self, spec: GearSpec, derived: BevelDerived, recipe: str = "") -> List[Point2]:
        """The blank's half-section in (radial, axial) mm — what the preview draws for a bevel gear."""
        return outline(derived)

    def plan(self, spec: GearSpec, derived: BevelDerived, recipe: str, template: str, path: str) -> BuildPlan:
        g = derived
        recipe = recipe or self.recipe_for(spec)
        ops: List[Op] = [NewPart(template)]
        ops.extend(AddGlobal(v.name, v.expression, v.radian_expression) for v in variables(spec, g))
        ops.append(Axis("axis", spur.AXIS_NAME, (2, 3)))
        ops.extend(_blank_ops(g))
        ops.extend(_cone_ops(g))
        ops.extend(_section_ops(g, recipe))
        ops.append(LoftCut("space_cut", spur.SPACE, ("heel_space", "toe_space")))
        ops.append(CircularPattern("teeth", spur.TEETH_PATTERN, "axis", "space_cut", g.teeth, "Count"))
        ops.append(LinkDimension(f"Count@{spur.TEETH_PATTERN}", _q(TEETH)))
        part = re.split(r"[\\/]", path)[-1].rsplit(".", 1)[0] if path else spec.stem()
        ops.append(ManualStep("material", f"Assign a material to {part}; the build leaves it unset."))
        ops.append(Rebuild())
        ops.append(SaveAs(path))
        return BuildPlan(kind=KIND_BEVEL, recipe=recipe, ops=tuple(ops), path=path)
