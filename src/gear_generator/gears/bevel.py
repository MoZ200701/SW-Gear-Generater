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
from . import equations, internal, spur
from .properties import property_ops
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
CROWN_LIMIT = 89.0          # degrees of pitch cone from which a gear is too near a crown gear to build as a cone
CROWN_TOLERANCE = 0.01      # degrees either side of 90° within which a gear is built as a crown gear
INTERNAL_LIMIT = 91.0       # degrees of pitch cone at and above which a gear is an internal bevel
OVERRUN_MODULES = 1.0       # the loft runs this far past the heel and the toe
CROWN_BACK_MODULES = 3.0    # a crown gear's back face is this far behind its root at the heel
CROWN_FRONT_MODULES = 1.0   # and the face inside its toe this far behind the root there
RING_MODULES = 3.0          # an internal bevel's rim is this far behind its root cone, as a ring's is
RING_FILLET_FACTOR = 0.15   # × module, an internal bevel's default fillet, as a ring's

# What a bevel gear's pitch cone makes it.
FORM_CONE = "cone"          # δ < 90°: the usual bevel gear, its teeth outside a cone
FORM_CROWN = "crown"        # δ = 90°: the pitch cone is a plane, the teeth on the gear's face, the section a rack's
FORM_INTERNAL = "internal"  # δ > 90°: the teeth inside a cone, the section a ring's

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
BACK_INNER = "Back Cone Inner Diameter"     # an internal bevel's: its back cone's ring's tip circle

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


def is_crown(delta: float) -> bool:
    return abs(delta - 90.0) <= CROWN_TOLERANCE


def form_of(delta: float) -> str:
    """:data:`FORM_CONE`, :data:`FORM_CROWN` or :data:`FORM_INTERNAL`; ``""`` in the bands either side of a crown."""
    if is_crown(delta):
        return FORM_CROWN
    if delta >= INTERNAL_LIMIT:
        return FORM_INTERNAL
    if delta >= CROWN_LIMIT:
        return ""
    return FORM_CONE


def crown_shaft_angle(teeth: int, mate_teeth: int) -> Optional[float]:
    """The shaft angle, degrees, that makes a gear of ``teeth`` a crown gear with its mate: ``cos Σ = −N_mate / N``.

    None when there is none: only the bigger gear of a pair can be the crown.
    """
    if mate_teeth >= teeth:
        return None
    return math.degrees(math.acos(-mate_teeth / teeth))


def addenda(module: float, teeth: int, mate_teeth: int, delta: float, delta_mate: float) -> Tuple[float, float]:
    """``(this gear's addendum, the mate's)``, Gleason: the bigger gear gets ``0.54m + 0.46m / q``.

    A crown gear's ``q`` is infinite, so it gets ``0.54m`` and its pinion the
    rest. Gleason tabulates nothing for an internal bevel pair, so both gears
    of one get the module, as an internal spur pair's do.
    """
    if max(delta, delta_mate) >= INTERNAL_LIMIT:
        return module, module
    if is_crown(delta):
        return BIG_ADDENDUM * module, WORKING_DEPTH * module - BIG_ADDENDUM * module
    if is_crown(delta_mate):
        return WORKING_DEPTH * module - BIG_ADDENDUM * module, BIG_ADDENDUM * module
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
class RackSection:
    """A crown gear's section. Its back cone is a cylinder, so its virtual gear is a rack.

    The space is a trapezoid, its flanks straight at the pressure angle, ``space``
    wide on the pitch line and a fillet into each corner at the root. ``teeth``
    is infinite, which is how the readouts know a rack when they see one.
    """

    module: float
    pressure_angle_deg: float
    face_width: float
    bore: float
    backlash: float
    fillet: float
    backlash_typed: bool
    fillet_typed: bool
    alpha: float
    addendum: float
    dedendum: float
    space: float
    s: float
    p: float
    teeth: float = math.inf

    @property
    def h(self) -> float:
        return self.addendum + self.dedendum

    def half_width(self, u: float) -> float:
        """Half the space's width ``u`` mm out from the pitch line, toward the tips."""
        return self.space / 2.0 + u * math.tan(self.alpha)

    @property
    def fillet_centre(self) -> Point2:
        """The upper root fillet's centre, ``(u, v)``: a fillet above the root line, tangent to the upper flank."""
        u = -self.dedendum + self.fillet
        return u, self.half_width(u) - self.fillet / math.cos(self.alpha)

    @property
    def cap(self) -> float:
        """How far out the space is closed: a module past the tips, as a spur gear's tip cap."""
        return self.addendum + self.module

    @property
    def tip_thickness(self) -> float:
        return self.p - 2.0 * self.half_width(self.addendum)

    def values(self) -> Dict[str, float]:
        return {BACKLASH: self.backlash, ARC_LENGTH: self.space, FILLET: self.fillet, DEPTH: self.h,
                FACE_WIDTH: self.face_width}


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
    form: str = FORM_CONE

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
        """Only a cone's teeth undercut: a crown gear's are a rack's, and an internal bevel's a ring's."""
        return self.form == FORM_CONE and self.virtual_teeth < undercut_limit(self.pressure_angle_deg, self.shift)

    @property
    def crown(self) -> bool:
        return self.form == FORM_CROWN

    @property
    def ring(self) -> bool:
        return self.form == FORM_INTERNAL

    def values(self) -> Dict[str, float]:
        """The value of every global variable, by name."""
        s = self.section
        out = dict(s.values())
        if self.ring:
            for name in (internal.INNER, internal.RIM, TEETH):
                out.pop(name, None)
        tan_delta = abs(math.tan(math.radians(self.delta))) if not self.crown else 0.0
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
            HEEL_DISTANCE: self.heel_distance,
            TOE_DISTANCE: self.toe_distance,
            HEEL_SCALE: self.heel_distance / self.cone_distance,
            TOE_SCALE: self.toe_distance / self.cone_distance,
        })
        if not self.crown:
            out.update({
                BACK_PITCH: s.d,
                HEEL_RADIUS: self.heel_distance * tan_delta,
                TOE_RADIUS: self.toe_distance * tan_delta,
            })
            out[BACK_INNER if self.ring else BACK_OUTER] = s.da
        return out

    def to_dict(self) -> Dict[str, Any]:
        """As :func:`dataclasses.asdict`, with a crown gear's infinite virtual teeth written as None, JSON having no infinity."""
        def finite(data: Dict[str, Any]) -> Dict[str, Any]:
            return {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in data.items()}

        data = finite({key: value for key, value in asdict(self).items() if key != "section"})
        data["section"] = finite(asdict(self.section))
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
    for name, angle, teeth, other in (("This gear", delta, n, mate), ("Its mate", delta_mate, mate, n)):
        if not form_of(angle):
            crown = crown_shaft_angle(teeth, other)
            raise GeometryError(
                f"{name} would have a pitch cone of {_num(angle, 2)}°, too near a crown gear's 90° to build either "
                f"as a cone or as a crown gear; a shaft angle of {_num(crown, 3)}° makes it a crown gear, or change "
                "the teeth or the shaft angle.")
    form = form_of(delta)
    if form == FORM_CROWN:
        # Built as exactly a crown: the mate takes up what the typed shaft angle leaves.
        delta, delta_mate = 90.0, shaft - 90.0
    d = m * n
    radius = d / (2.0 * math.sin(math.radians(delta)))
    ha, ha_mate = addenda(m, n, mate, delta, delta_mate)
    hf, hf_mate = WHOLE_DEPTH * m - ha, WHOLE_DEPTH * m - ha_mate
    theta_f = math.degrees(math.atan(hf / radius))
    theta_f_mate = math.degrees(math.atan(hf_mate / radius))
    shift = (ha - m) / m
    cos_delta = 0.0 if form == FORM_CROWN else math.cos(math.radians(delta))
    typed_backlash = spec.backlash_mm()
    typed_fillet = spec.fillet_mm()
    j = BACKLASH_FACTOR * m if typed_backlash is None else typed_backlash
    space_change = -2.0 * (ha - m) * math.tan(math.radians(alpha))
    section: Any
    if form == FORM_CROWN:
        virtual = virtual_radius = math.inf
        space = m * math.pi / 2.0 + j + space_change
        section = RackSection(
            module=m, pressure_angle_deg=alpha, face_width=width, bore=spec.bore_mm(), backlash=j,
            fillet=FILLET_FACTOR * m if typed_fillet is None else typed_fillet,
            backlash_typed=typed_backlash is not None, fillet_typed=typed_fillet is not None,
            alpha=math.radians(alpha), addendum=ha, dedendum=hf, space=space, s=m * math.pi - space, p=m * math.pi,
        )
    elif form == FORM_INTERNAL:
        # The back cone's ring: Nv = N / |cos δ| teeth, its centre on the tips' side of the pitch cone.
        virtual = n / abs(cos_delta)
        virtual_radius = d / (2.0 * abs(cos_delta))
        section = internal.section(
            virtual, m, alpha, width, None, j, RING_FILLET_FACTOR * m if typed_fillet is None else typed_fillet,
            backlash_typed=typed_backlash is not None, fillet_typed=typed_fillet is not None, whole_depth=ha + hf,
        )
    else:
        virtual = n / cos_delta
        virtual_radius = d / (2.0 * cos_delta)
        section = spur.profile(
            virtual, m, alpha, width, 0.0, j, FILLET_FACTOR * m if typed_fillet is None else typed_fillet,
            backlash_typed=typed_backlash is not None, fillet_typed=typed_fillet is not None,
            addendum=ha, whole_depth=ha + hf, space_change=space_change,
        )
    sin_delta = math.sin(math.radians(delta))
    return BevelDerived(
        section=section, teeth=n, mate_teeth=mate, module=m, pressure_angle_deg=alpha, shaft_angle=shaft,
        face_width=width, bore=spec.bore_mm(), d=d, delta=delta, delta_mate=delta_mate, cone_distance=radius,
        addendum=ha, mate_addendum=ha_mate, dedendum=hf, mate_dedendum=hf_mate, dedendum_angle=theta_f,
        mate_dedendum_angle=theta_f_mate, face_angle=delta + theta_f_mate, root_angle=delta - theta_f,
        da=d + 2.0 * ha * cos_delta, crown_to_apex=radius * cos_delta - ha * sin_delta,
        shift=shift, virtual_teeth=virtual, virtual_radius=virtual_radius, overrun=OVERRUN_MODULES * m, form=form,
    )


def _approach(form: str, rv: float, ha: float, alpha: float) -> float:
    """One gear's share of the path of contact, from its tip circle to the pitch point, on its back cone.

    A cone's virtual gear is external, ``√((rv + ha)² − rb²) − rv sin α``; a
    crown gear's is a rack, ``ha / sin α``; an internal bevel's is a ring, whose
    tip circle is inside its pitch circle, ``rv sin α − √((rv − ha)² − rb²)``.
    """
    if form == FORM_CROWN:
        return ha / math.sin(alpha)
    rb = rv * math.cos(alpha)
    if form == FORM_INTERNAL:
        return rv * math.sin(alpha) - math.sqrt(max(0.0, (rv - ha) ** 2 - rb * rb))
    return math.sqrt((rv + ha) ** 2 - rb * rb) - rv * math.sin(alpha)


def virtual_radius(module: float, teeth: int, delta: float) -> float:
    """``rv = m N / (2 |cos δ|)``, infinite for a crown gear."""
    if is_crown(delta):
        return math.inf
    return module * teeth / (2.0 * abs(math.cos(math.radians(delta))))


def pair_contact_ratio(module: float, pressure_angle_deg: float, teeth: int, mate_teeth: int, delta: float,
                       delta_mate: float, addendum: float, mate_addendum: float) -> float:
    """εα of the virtual pair on the two back cones: each gear's share of the path of contact, over the base pitch."""
    alpha = math.radians(pressure_angle_deg)
    total = sum(_approach(form_of(d), virtual_radius(module, n, d), ha, alpha)
                for n, d, ha in ((teeth, delta, addendum), (mate_teeth, delta_mate, mate_addendum)))
    return total / (math.pi * module * math.cos(alpha))


def contact_ratio(g: BevelDerived) -> float:
    """εα of the virtual spur pair on the back cones, with each gear's own Gleason addendum."""
    return pair_contact_ratio(g.module, g.pressure_angle_deg, g.teeth, g.mate_teeth, g.delta, g.delta_mate,
                              g.addendum, g.mate_addendum)


def rack_diagnostics(r: RackSection) -> List[Diagnostic]:
    """A crown gear's rack section: the teeth must not come to a point, and the root fillets must fit."""
    out: List[Diagnostic] = []
    if r.backlash >= r.p / 2.0:
        out.append(Diagnostic(ERROR, (
            f"Backlash of {_num(r.backlash)} mm leaves no tooth: it must be less than half "
            f"the circular pitch, {_num(r.p / 2.0)} mm."), "backlash"))
        return out
    if r.tip_thickness <= 0.0:
        out.append(Diagnostic(ERROR, (
            f"The crown gear's teeth come to a point before their tips at {_num(r.pressure_angle_deg)}°; "
            "reduce the backlash or the pressure angle."), "teeth"))
    if r.fillet <= 0.0:
        out.append(Diagnostic(ERROR, "Fillet must be more than zero.", "fillet"))
    elif r.fillet_centre[1] <= 0.0:
        out.append(Diagnostic(ERROR, (
            f"The two {_num(r.fillet)} mm root fillets do not fit in the root of the crown gear's tooth space, "
            f"{_num(2.0 * r.half_width(-r.dedendum))} mm wide; make Fillet smaller."), "fillet"))
    return out


def ring_outer_radius(g: BevelDerived) -> float:
    """How far an internal bevel's back reaches from its axis, mm: at the heel's rim."""
    return blank_points(g).heel_rim[0]


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
    if g.crown:
        out.extend(rack_diagnostics(g.section))
    elif g.ring:
        out.extend(d for d in internal.section_diagnostics(g.section, recipe) if d.field not in ("rim", "bore"))
    else:
        out.extend(d for d in spur.section_diagnostics(g.section, recipe, g.undercut_limit, suggest_shift=False)
                   if d.field != "bore")
    if g.ring:
        if g.bore > 0.0:
            out.append(Diagnostic(WARNING, (
                f"An internal bevel gear is a ring, {_num(2.0 * ring_outer_radius(g))} mm across its back, and has "
                "no bore; the Bore is not cut."), "bore"))
    elif g.bore > 0.0 and g.bore / 2.0 >= toe_root_radius(g) - g.module:
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
    pitch_cone = GlobalVariable(PITCH_CONE, f"IIF ( {denominator} > 0 , {base_angle} , 180 + {base_angle} )",
                                f"IIF ( {denominator_r} > 0 , {base_angle_r} , 180 + {base_angle_r} )")
    # Gleason's q is infinite beside a crown gear, and cos δ in it zero: those pairs, and the internal ones,
    # have addenda of their own (see addenda), written without it.
    mate_form = form_of(g.delta_mate)
    if FORM_INTERNAL in (g.form, mate_form):
        addendum = addendum_r = m
    elif g.crown:
        addendum = addendum_r = f"{equations.literal(BIG_ADDENDUM)} * {m}"
    elif mate_form == FORM_CROWN:
        addendum = addendum_r = f"{equations.literal(WORKING_DEPTH)} * {m} - {equations.literal(BIG_ADDENDUM)} * {m}"
    if g.crown:
        # The formula's denominator is zero at a crown gear; it is built as exactly 90°.
        pitch_cone = GlobalVariable(PITCH_CONE, "90")
    backlash = equations.literal(s.backlash) if s.backlash_typed else f"{BACKLASH_FACTOR} * {m}"
    factor = RING_FILLET_FACTOR if g.ring else FILLET_FACTOR
    fillet = equations.literal(s.fillet) if s.fillet_typed else f"{factor} * {m}"
    # A ring's back cone is on the far side of its axis: its pitch cone's supplement is what it is square to.
    back = f"180 - {cone}" if g.ring else cone
    back_r = f"pi - {cone_r}" if g.ring else cone_r
    if g.crown:
        section: List[GlobalVariable] = []
        radii: List[GlobalVariable] = []
    else:
        section = [GlobalVariable(BACK_PITCH, f"{_q(PITCH)} / cos ( {back} )", f"{_q(PITCH)} / cos ( {back_r} )")]
        if g.ring:
            section += [
                GlobalVariable(BACK_INNER, f"{_q(BACK_PITCH)} - 2 * {_q(ADDENDUM)}"),
                *internal.profile_variables(g.section, PRESSURE_ANGLE, MODULE, pitch=BACK_PITCH, inner=BACK_INNER,
                                            rim=False),
            ]
        else:
            section += [
                GlobalVariable(BACK_OUTER, f"{_q(BACK_PITCH)} + 2 * {_q(ADDENDUM)}"),
                *spur.profile_variables(PRESSURE_ANGLE, MODULE, pitch=BACK_PITCH, outer=BACK_OUTER),
            ]
        radii = [
            GlobalVariable(HEEL_RADIUS, f"{_q(HEEL_DISTANCE)} * tan ( {back} )", f"{_q(HEEL_DISTANCE)} * tan ( {back_r} )"),
            GlobalVariable(TOE_RADIUS, f"{_q(TOE_DISTANCE)} * tan ( {back} )", f"{_q(TOE_DISTANCE)} * tan ( {back_r} )"),
        ]
    return [
        GlobalVariable(TEETH, equations.literal(g.teeth)),
        GlobalVariable(MODULE, equations.literal(g.module)),
        GlobalVariable(BORE, equations.literal(g.bore)),
        GlobalVariable(PRESSURE_ANGLE, equations.literal(g.pressure_angle_deg)),
        GlobalVariable(SHAFT, equations.literal(g.shaft_angle)),
        GlobalVariable(MATE_TEETH, equations.literal(g.mate_teeth)),
        # Past 90° when the denominator is negative; both branches are evaluated, so a zero one is refused by validate.
        pitch_cone,
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
        *section,
        GlobalVariable(HEEL_DISTANCE, f"{_q(CONE_DISTANCE)} + {_q(OVERRUN)}"),
        GlobalVariable(TOE_DISTANCE, f"{_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)} - {_q(OVERRUN)}"),
        GlobalVariable(HEEL_SCALE, f"{_q(HEEL_DISTANCE)} / {_q(CONE_DISTANCE)}"),
        GlobalVariable(TOE_SCALE, f"{_q(TOE_DISTANCE)} / {_q(CONE_DISTANCE)}"),
        *radii,
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


def rim_lengths(g: BevelDerived) -> Tuple[float, float]:
    """How far behind the pitch cone, square to it, the blank's rim is at the heel and at the toe, mm.

    A cone's rims are a module inside its root, radially, so the rim lines run
    square to the axis in to the bore. A crown gear's back is a plane: it is
    three modules behind the root at the heel and one at the toe, so the web
    inside the toe is at least two modules thick. An internal bevel is a ring,
    its back parallel to its root cone three modules behind it.
    """
    m = g.module
    toe_root = g.dedendum - g.face_width * math.tan(math.radians(g.dedendum_angle))
    if g.crown:
        return g.dedendum + CROWN_BACK_MODULES * m, toe_root + CROWN_FRONT_MODULES * m
    if g.ring:
        return g.dedendum + RING_MODULES * m, toe_root + RING_MODULES * m
    c = math.cos(math.radians(g.delta))
    return g.dedendum + m / c, toe_root + m / c


def blank_points(g: BevelDerived) -> BlankPoints:
    d = math.radians(g.delta)
    gv = (math.sin(d), math.cos(d))
    nv = (math.cos(d), -math.sin(d))
    if g.crown:
        gv, nv = (1.0, 0.0), (0.0, -1.0)
    radius, width = g.cone_distance, g.face_width
    tan_fm = math.tan(math.radians(g.mate_dedendum_angle))

    def along(t: float, s: float) -> Point2:
        return (t * gv[0] + s * nv[0], t * gv[1] + s * nv[1])

    heel_rim_length, toe_rim_length = rim_lengths(g)
    heel_rim = along(radius, -heel_rim_length)
    toe_rim = along(radius - width, -toe_rim_length)
    bore = g.bore / 2.0
    return BlankPoints(
        pitch=along(radius, 0.0), toe_pitch=along(radius - width, 0.0),
        heel_tip=along(radius, g.addendum), heel_rim=heel_rim,
        toe_tip=along(radius - width, g.addendum - width * tan_fm), toe_rim=toe_rim,
        back_bore=(bore, heel_rim[1]), front_bore=(bore, toe_rim[1]),
    )


def outline(g: BevelDerived) -> List[Point2]:
    """The blank's half-section, closed, in (radial, axial) mm. An internal bevel's is a ring's, clear of the axis."""
    loop = blank_points(g).loop()
    if g.ring:
        loop = loop[:4]
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
    if g.crown:
        nx, nz = 0.0, -1.0
    toe_root = f"{_q(DEDENDUM)} - {_q(FACE_WIDTH)} * tan ( {_q(DEDENDUM_ANGLE)} )"
    toe_root_r = f"{_q(DEDENDUM)} - {_q(FACE_WIDTH)} * tan ( {_q(DEDENDUM_ANGLE)} * pi / 180 )"
    if g.ring:
        # A ring's back is parallel to its root cone, the same distance behind it at the heel and the toe.
        heel_rim_len = heel_rim_len_r = f"{_q(DEDENDUM)} + {equations.literal(RING_MODULES)} * {m}"
        toe_rim_len = f"{toe_root} + {equations.literal(RING_MODULES)} * {m}"
        toe_rim_len_r = f"{toe_root_r} + {equations.literal(RING_MODULES)} * {m}"
        back = back_r = front = front_r = ""
    elif g.crown:
        # The rims are measured along the axis; the rim lines run square to it from the heel's and the toe's radii.
        heel_rim_len = heel_rim_len_r = f"{_q(DEDENDUM)} + {equations.literal(CROWN_BACK_MODULES)} * {m}"
        toe_rim_len = f"{toe_root} + {equations.literal(CROWN_FRONT_MODULES)} * {m}"
        toe_rim_len_r = f"{toe_root_r} + {equations.literal(CROWN_FRONT_MODULES)} * {m}"
        back = back_r = f"{_q(CONE_DISTANCE)} - {_q(BORE)} / 2"
        front = front_r = f"{_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)} - {_q(BORE)} / 2"
    else:
        heel_rim_len = f"{_q(DEDENDUM)} + {m} / cos ( {cone} )"
        heel_rim_len_r = f"{_q(DEDENDUM)} + {m} / cos ( {cone_r} )"
        toe_rim_len = f"{toe_root} + {m} / cos ( {cone} )"
        toe_rim_len_r = f"{toe_root_r} + {m} / cos ( {cone_r} )"
        back = f"{_q(CONE_DISTANCE)} * sin ( {cone} ) - {_q(DEDENDUM)} * cos ( {cone} ) - {m} - {_q(BORE)} / 2"
        back_r = f"{_q(CONE_DISTANCE)} * sin ( {cone_r} ) - {_q(DEDENDUM)} * cos ( {cone_r} ) - {m} - {_q(BORE)} / 2"
        front = (f"( {_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)} ) * sin ( {cone} ) - ( {toe_rim_len} ) * cos ( {cone} ) - "
                 f"{_q(BORE)} / 2")
        front_r = (f"( {_q(CONE_DISTANCE)} - {_q(FACE_WIDTH)} ) * sin ( {cone_r} ) - ( {toe_rim_len_r} ) * "
                   f"cos ( {cone_r} ) - {_q(BORE)} / 2")
    heel_rim_value, _ = rim_lengths(g)
    s_heel = p.heel_rim[0] - g.bore / 2.0
    s_toe = p.toe_rim[0] - g.bore / 2.0
    ring = g.ring
    # A ring's back runs straight from the heel's rim to the toe's; everything else's runs in to the bore.
    back_lines: List[Op] = [Line("L4", _top(*p.heel_rim), _top(*p.toe_rim))] if ring else [
        Line("L4", _top(*p.heel_rim), _top(*p.back_bore)),
        Line("L5", _top(*p.back_bore), _top(*p.front_bore)),
        Line("L6", _top(*p.front_bore), _top(*p.toe_rim)),
    ]
    back_joints: List[Op] = [Relation("coincident", ("L4.end", "L1.start"))] if ring else [
        Relation("coincident", ("L4.end", "L5.start")),
        Relation("coincident", ("L5.end", "L6.start")),
        Relation("coincident", ("L6.end", "L1.start")),
    ]
    back_squares: List[Op] = [] if ring else [Relation("horizontal", ("L4",)), Relation("horizontal", ("L6",))]
    back_dimensions: List[Op] = [] if ring else [
        Dimension("Back", ("L4",), offset(p.back_bore, s_heel / 2.0, 3.0), s_heel),
        Dimension("Front", ("L6",), offset(p.front_bore, s_toe / 2.0, -3.0), s_toe),
    ]
    back_links: List[Op] = [] if ring else [
        LinkDimension(f"Back@{BLANK_SKETCH}", back, back_r),
        LinkDimension(f"Front@{BLANK_SKETCH}", front, front_r),
    ]
    return [
        OpenSketch("blank", 2),
        Line("A", (0.0, 0.0), _top(0.0, radius), construction=True),
        Line("G", (0.0, 0.0), _top(*p.pitch), construction=True),
        Line("G2", (0.0, 0.0), _top(*p.toe_pitch), construction=True),
        Line("L1", _top(*p.toe_rim), _top(*p.toe_tip)),
        Line("L2", _top(*p.toe_tip), _top(*p.heel_tip)),
        Line("L3", _top(*p.heel_tip), _top(*p.heel_rim)),
        *back_lines,
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
        *back_joints,
        Relation("coincident", ("Ha.start", "G.end")),
        Relation("coincident", ("Hc.start", "G.end")),
        Relation("coincident", ("Hf.start", "G2.end")),
        Relation("coincident", ("Ha.end", "L2.end")),
        Relation("coincident", ("Hc.end", "L3.end")),
        Relation("coincident", ("Hf.end", "L1.start")),
        *back_squares,
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
        Dimension("Heel Rim", ("Hc",), offset(p.heel_rim, 1.0, 2.0), heel_rim_value),
        Dimension("Toe Square", ("Hf", "G2"), offset(p.toe_pitch, -nx * 0.5 - math.sin(math.radians(d)) * 0.5,
                                                    -nz * 0.5 - math.cos(math.radians(d)) * 0.5), 90.0, "deg"),
        Dimension("Toe Rim", ("Hf",), offset(p.toe_rim, 1.0, -2.0),
                  math.hypot(p.toe_pitch[0] - p.toe_rim[0], p.toe_pitch[1] - p.toe_rim[1])),
        Dimension("Front Square", ("L1", "G2"), offset(p.toe_pitch, nx * 0.5 - math.sin(math.radians(d)) * 0.5,
                                                      nz * 0.5 - math.cos(math.radians(d)) * 0.5), 90.0, "deg"),
        Dimension("Face", ("L2", "G"), offset(p.pitch, nx * g.addendum / 2.0, nz * g.addendum / 2.0),
                  g.mate_dedendum_angle, "deg"),
        *back_dimensions,
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
        *back_links,
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


def section_sign(form: str) -> Optional[int]:
    """+1 when a heel plane's sketch +x is the way the teeth's tips point, ``(cos δ, 0, −sin δ)``; None if unprobed.

    Probe ref_plane_normal measured it on cones of 30° and 50°. A crown gear's
    plane is square to the X axis and an internal bevel's leans past it; probe
    bevel_planes_beyond_90 measured those at 90° and 120°, with the same sign.
    """
    return {FORM_CONE: findings.BEVEL_SECTION_X_SIGN, FORM_CROWN: findings.BEVEL_CROWN_SECTION_X_SIGN,
            FORM_INTERNAL: findings.BEVEL_INTERNAL_SECTION_X_SIGN}[form]


def _rack_ops(g: BevelDerived, plane: str, distance: float, scale_global: str, sketch_id: str, sketch_name: str,
              prefix: str, sign: int) -> List[Op]:
    """A crown gear's tooth space: a rack's, on a plane square to the pitch plane, scaled toward the apex.

    The sketch's origin is the pitch point. ``Du`` runs from it in to the root
    line ``R`` and ``Cu`` out to the cap line ``T``, both along the tooth; ``W``
    crosses the space on the pitch line, ``"Arc Length"`` long and halved by
    ``Cu``. The flank ``E+`` is at the pressure angle to ``Cu``, and ``T``, also
    halved by ``Cu``, carries ``E−`` round as its mirror. The fillets are
    tangent to the root and to their flanks.
    """
    r = g.section
    k = distance / g.cone_distance
    scale = _q(scale_global)
    a, rho, hf, cap = r.alpha, r.fillet, r.dedendum, r.cap
    uc, vc = r.fillet_centre
    touch = (uc - rho * math.sin(a), vc + rho * math.cos(a))
    w_cap, w_pitch = r.half_width(cap), r.space / 2.0
    p = prefix

    def at(u: float, v: float) -> Point2:
        return sign * k * u, k * v

    upper, upper_root, upper_flank = internal._ccw_arc(p + "F+", at(uc, vc), at(-hf, vc), at(*touch))  # noqa: SLF001
    lower, lower_flank, lower_root = internal._ccw_arc(  # noqa: SLF001
        p + "F-", at(uc, -vc), at(touch[0], -touch[1]), at(-hf, -vc))
    middle = (cap / 2.0, r.half_width(cap / 2.0) / 2.0)
    return [
        OpenSketch(sketch_id, plane),
        Line(p + "Du", (0.0, 0.0), at(-hf, 0.0), construction=True),
        Line(p + "Cu", (0.0, 0.0), at(cap, 0.0), construction=True),
        Line(p + "W", at(0.0, -w_pitch), at(0.0, w_pitch), construction=True),
        Line(p + "R", at(-hf, -vc), at(-hf, vc)),
        upper,
        Line(p + "E+", at(*touch), at(cap, w_cap)),
        Line(p + "T", at(cap, w_cap), at(cap, -w_cap)),
        Line(p + "E-", at(cap, -w_cap), at(touch[0], -touch[1])),
        lower,
        Relation("coincident", (p + "R.end", upper_root)),
        Relation("coincident", (upper_flank, p + "E+.start")),
        Relation("coincident", (p + "E+.end", p + "T.start")),
        Relation("coincident", (p + "T.end", p + "E-.start")),
        Relation("coincident", (p + "E-.end", lower_flank)),
        Relation("coincident", (lower_root, p + "R.start")),
        Relation("coincident", (p + "Du.start", ORIGIN)),
        Relation("horizontal", (p + "Du",)),
        Relation("coincident", (p + "Du.end", p + "R")),
        Relation("coincident", (p + "Cu.start", ORIGIN)),
        Relation("horizontal", (p + "Cu",)),
        Relation("coincident", (p + "Cu.end", p + "T")),
        Relation("vertical", (p + "R",)),
        Relation("symmetric", (p + "T.start", p + "T.end", p + "Cu")),
        Relation("coincident", (p + "W.start", p + "E-")),
        Relation("coincident", (p + "W.end", p + "E+")),
        Relation("symmetric", (p + "W.start", p + "W.end", p + "Cu")),
        Relation("coincident", (ORIGIN, p + "W")),
        Relation("tangent", (p + "F+", p + "R")),
        Relation("tangent", (p + "F+", p + "E+")),
        Relation("tangent", (p + "F-", p + "R")),
        Relation("tangent", (p + "F-", p + "E-")),
        Relation("equal", (p + "F+", p + "F-")),
        Dimension("Dedendum", (p + "Du",), at(-hf / 2.0, -w_pitch / 2.0), k * hf),
        Dimension("Cap", (p + "Cu",), at(cap / 2.0, -w_cap - k * r.module), k * cap),
        Dimension("Space", (p + "W",), at(-hf / 4.0, w_pitch * 1.2), k * r.space),
        Dimension("Flank", (p + "E+", p + "Cu"), at(*middle), r.pressure_angle_deg, "deg"),
        Dimension("Fillet", (p + "F+",), at(uc + 2.0 * rho, vc + rho), k * rho),
        CloseSketch(sketch_id, sketch_name),
        LinkDimension(f"Dedendum@{sketch_name}", f"( {_q(DEDENDUM)} ) * {scale}"),
        LinkDimension(f"Cap@{sketch_name}", f"( {_q(ADDENDUM)} + {_q(MODULE)} ) * {scale}"),
        LinkDimension(f"Space@{sketch_name}", f"( {_q(ARC_LENGTH)} ) * {scale}"),
        LinkDimension(f"Flank@{sketch_name}", _q(PRESSURE_ANGLE)),
        LinkDimension(f"Fillet@{sketch_name}", f"( {_q(FILLET)} ) * {scale}"),
    ]


def _section_ops(g: BevelDerived, recipe: str) -> List[Op]:
    """The heel's and the toe's sections: a cone's back-cone gear, a crown gear's rack, or an internal bevel's ring.

    A ring's centre is on its tips' side, so its section's own outward radial
    runs the other way along the sketch's x from a cone's.
    """
    tan_delta = math.tan(math.radians(g.delta)) if not g.crown else 0.0
    sign = section_sign(g.form)
    if sign is None:
        raise InputError(section_refusal(g))
    ops: List[Op] = []
    for plane, distance, radius_global, scale_global, sketch_id, sketch_name, prefix in (
        ("heel", g.heel_distance, HEEL_RADIUS, HEEL_SCALE, "heel_space", HEEL_SKETCH, "h_"),
        ("toe", g.toe_distance, TOE_RADIUS, TOE_SCALE, "toe_space", TOE_SKETCH, "t_"),
    ):
        if g.crown:
            ops.extend(_rack_ops(g, plane, distance, scale_global, sketch_id, sketch_name, prefix, sign))
            continue
        frame = spur.SectionFrame(
            centre_x=-sign * distance * tan_delta, centre_global=radius_global,
            scale=distance / g.cone_distance, scale_global=scale_global,
            sketch_id=sketch_id, sketch_name=sketch_name, prefix=prefix, x_sign=-sign if g.ring else sign,
        )
        if g.ring:
            ops.extend(spur._framed(internal.space_ops(g.section, recipe, plane, pitch=BACK_PITCH),  # noqa: SLF001
                                    frame, plane))
        else:
            ops.extend(spur.space_ops(g.section, recipe, plane=plane, frame=frame, pitch=BACK_PITCH))
    return ops


def section_refusal(g: BevelDerived) -> str:
    """Why a crown or internal bevel gear is not built yet."""
    what = "a crown gear" if g.crown else "an internal bevel gear"
    return (f"The heel and toe planes of {what} have not been settled on SolidWorks yet, so which way its tooth "
            "sections face is not known: run probe bevel_planes_beyond_90 on the host (probe.sh --only "
            "bevel_planes_beyond_90) and record its findings first.")


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
        ops.extend(property_ops(KIND_BEVEL, recipe, g.ring, [TEETH, MATE_TEETH, MODULE, PRESSURE_ANGLE, SHAFT,
                                                            FACE_WIDTH, PITCH, OUTER, *([BORE] if spec.has_bore()
                                                                                          else [])]))
        part = re.split(r"[\\/]", path)[-1].rsplit(".", 1)[0] if path else spec.stem()
        ops.append(ManualStep("material", f"Assign a material to {part}; the build leaves it unset."))
        ops.append(Rebuild())
        ops.append(SaveAs(path))
        return BuildPlan(kind=KIND_BEVEL, recipe=recipe, ops=tuple(ops), path=path)
