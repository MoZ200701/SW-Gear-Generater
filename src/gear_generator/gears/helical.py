"""Helical and herringbone gears: a spur gear's transverse section, swept along the axis with a twist.

Module and pressure angle are the **normal** ones, as a hob is sold by, and the
tooth's height — addendum, depth, tip cap, fillet — is measured in the normal
module. Everything round the circle is transverse: ``mt = mn / cos β``, the
pitch diameter ``d = mt·N``, and the transverse pressure angle
``αt = atan(tan αn / cos β)`` that the involute is drawn with. So the tooth
space is :func:`spur.profile` with transverse values, and the sketch is spur's
sketch, unchanged.

A **helical** gear sweeps that section from a plane one module ahead of the
Front plane to one module past the far face, turning uniformly — an exact
helicoid, with no sweep end lying on a face of the blank. A **herringbone**
gear builds half: a blank half the width, the section on the plane at its far
face, swept back past the Front plane, patterned, then the body mirrored about
that plane. The mirror reverses the hand by geometry, and the apex is the
section itself.

Sign convention: +Z is the way the blank extrudes from the Front plane
(``findings.EXTRUDE_Z_SIGN``). A **right-hand** gear's section turns
counter-clockwise about +Z as z increases, by ``360·z / L`` degrees for a lead
``L = π·d / tan β``. A herringbone's hand names its half nearest the Front
plane. SolidWorks' Front view looks from +Z, so the face it shows is the far one.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from .. import findings
from ..spec import HAND_RIGHT, HANDS, KIND_HELICAL, KIND_HERRINGBONE, GearSpec, InputError
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
    Extrude,
    GeometryError,
    GlobalVariable,
    Line,
    LinkDimension,
    ManualStep,
    MirrorBody,
    NewPart,
    Op,
    OpenSketch,
    Point2,
    Rebuild,
    RefPlane,
    Relation,
    SaveAs,
    SweepCut,
)
from .spur import (
    ARC_LENGTH,
    AXIS_NAME,
    BACKLASH,
    BACKLASH_FACTOR,
    BLANK,
    BORE,
    DEPTH,
    FACE_WIDTH,
    FILLET,
    FILLET_FACTOR,
    MODULE,
    OUTER,
    PITCH,
    PRESSURE_ANGLE,
    SPACE,
    TEETH,
    TEETH_PATTERN,
    SpurDerived,
)

# The globals a helical gear adds to spur's, by name.
HELIX_ANGLE = "Helix Angle"
TRANSVERSE_MODULE = "Transverse Module"
TRANSVERSE_PRESSURE_ANGLE = "Transverse Pressure Angle"
LEAD = "Lead"
OVERRUN = "Overrun"
MID_WIDTH = "Mid Width"
PATH_LENGTH = "Path Length"
TWIST_ANGLE = "Twist Angle"

# Feature and sketch names the build sets, and reads back.
PROFILE_PLANE = "Profile Plane"
MID_PLANE = "Mid Plane"
PATH_SKETCH = "Path Sketch"
MIRROR = "Mirror"

HELIX_MAX = 45.0
# What the pair solver searches when the helix angle is left blank, and what
# the form does not warn about.
DEFAULT_RANGE = {KIND_HELICAL: (8.0, 25.0), KIND_HERRINGBONE: (20.0, 40.0)}
USUAL_RANGE = {KIND_HELICAL: (8.0, 30.0), KIND_HERRINGBONE: (20.0, 45.0)}

RIGHT_HAND_TURN = 1   # counter-clockwise about +Z as z increases


def _q(name: str) -> str:
    return equations.quote(name)


def _num(value: float, places: int = 3) -> str:
    return equations.literal(round(value, places))


# -- the numbers ------------------------------------------------------------


@dataclass(frozen=True)
class HelicalDerived:
    """A helical or herringbone gear: its transverse section, and what the helix adds.

    Everything the section has — ``d``, ``ra``, ``teeth``, ``bore`` … — reads
    through, so the preview and the readouts treat it like a spur gear's. The
    section's ``pressure_angle_deg`` and ``alpha`` are the transverse ones.
    """

    section: SpurDerived
    kind: str
    helix_angle_deg: float
    hand: str
    normal_pressure_angle_deg: float
    transverse_module: float
    lead: float
    overrun: float
    path_length: float
    twist_deg: float       # over the swept path, which runs past the faces
    overlap: float         # εβ over the whole face width
    n_min: float

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__") or name == "section":
            raise AttributeError(name)
        return getattr(self.section, name)

    @property
    def hand_sign(self) -> int:
        return RIGHT_HAND_TURN if self.hand == HAND_RIGHT else -RIGHT_HAND_TURN

    @property
    def face_twist_deg(self) -> float:
        """How far the section turns from one face to the other (a helical gear), or face to apex (herringbone)."""
        width = self.section.face_width / (2.0 if self.kind == KIND_HERRINGBONE else 1.0)
        return width * 360.0 / self.lead

    @property
    def undercut_limit(self) -> int:
        return int(math.floor(self.n_min + 0.5))

    @property
    def undercut(self) -> bool:
        return self.section.teeth < self.undercut_limit

    def face_rotations(self) -> Tuple[float, float]:
        """How far the Front-plane face and the far face are turned from the section drawn, in degrees.

        For a helical gear the section drawn is the Front-plane face; for a
        herringbone it is the apex, and both faces are turned the same way.
        """
        per_mm = 360.0 / self.lead * self.hand_sign
        width = self.section.face_width
        if self.kind == KIND_HERRINGBONE:
            return (-per_mm * width / 2.0, -per_mm * width / 2.0)
        return (0.0, per_mm * width)

    def values(self) -> Dict[str, float]:
        """The value of every global variable, by name."""
        out = dict(self.section.values())
        out[PRESSURE_ANGLE] = self.normal_pressure_angle_deg
        out.update({
            HELIX_ANGLE: self.helix_angle_deg,
            TRANSVERSE_MODULE: self.transverse_module,
            TRANSVERSE_PRESSURE_ANGLE: self.section.pressure_angle_deg,
            LEAD: self.lead,
            OVERRUN: self.overrun,
            PATH_LENGTH: self.path_length,
            TWIST_ANGLE: self.twist_deg,
        })
        if self.kind == KIND_HERRINGBONE:
            out[MID_WIDTH] = self.section.face_width / 2.0
        return out

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self.section)
        data.update({key: value for key, value in asdict(self).items() if key != "section"})
        return data


def transverse_pressure_angle(normal_deg: float, helix_deg: float) -> float:
    return math.degrees(math.atan(math.tan(math.radians(normal_deg)) / math.cos(math.radians(helix_deg))))


def undercut_minimum(normal_deg: float, helix_deg: float) -> float:
    """``2·cos β / sin² αt``: the fewest teeth a generated helical pinion has without undercut."""
    alpha_t = math.radians(transverse_pressure_angle(normal_deg, helix_deg))
    return 2.0 * math.cos(math.radians(helix_deg)) / math.sin(alpha_t) ** 2


def overlap_ratio(module: float, helix_deg: float, face_width: float) -> float:
    return face_width * math.sin(math.radians(helix_deg)) / (math.pi * module)


# -- the gear kinds ---------------------------------------------------------


class HelicalGear:
    kind = KIND_HELICAL
    recipes = spur.RECIPES
    # What an internal gear of the same kind changes, in :mod:`gears.internal`.
    internal = False
    fillet_factor = FILLET_FACTOR
    has_bore_global = True

    @property
    def default_recipe(self) -> str:
        return findings.DEFAULT_RECIPE

    def recipe_for(self, spec: GearSpec) -> str:
        return spec.recipe_or(self.default_recipe)

    def _errors(self, spec: GearSpec) -> List[Diagnostic]:
        out = spur.field_errors(spec, self.kind, internal=self.internal)
        try:
            beta = spec.helix_angle_deg()
        except InputError as exc:
            out.append(Diagnostic(ERROR, str(exc), "helix_angle"))
        else:
            if not 0.0 < beta <= HELIX_MAX:
                out.append(Diagnostic(ERROR, (
                    f"Helix angle must be more than 0° and at most {_num(HELIX_MAX)}° (got {_num(beta)}°); "
                    "a gear with no helix is a spur gear."), "helix_angle"))
        try:
            spec.hand_value()
        except InputError as exc:
            out.append(Diagnostic(ERROR, str(exc), "hand"))
        return out

    # -- deriving --------------------------------------------------------

    def derive(self, spec: GearSpec) -> HelicalDerived:
        """Every size of the gear. Raises :class:`GeometryError` on a field that makes none."""
        for problem in self._errors(spec):
            raise GeometryError(problem.message)
        mn = spec.module_mm()
        beta = spec.helix_angle_deg()
        normal = spec.pressure_angle_deg()
        cos_beta = math.cos(math.radians(beta))
        mt = mn / cos_beta
        typed_backlash = spec.backlash_mm()
        typed_fillet = spec.fillet_mm()
        j = BACKLASH_FACTOR * mn if typed_backlash is None else typed_backlash
        width = spec.face_width_mm()
        section = self._section(
            spec, spec.teeth_count(), mn, transverse_pressure_angle(normal, beta), width, j,
            self.fillet_factor * mn if typed_fillet is None else typed_fillet,
            backlash_typed=typed_backlash is not None, fillet_typed=typed_fillet is not None,
            transverse_module=mt, transverse_backlash=j / cos_beta,
        )
        lead = math.pi * section.d / math.tan(math.radians(beta))
        path = width / 2.0 + mn if self.kind == KIND_HERRINGBONE else width + 2.0 * mn
        return HelicalDerived(
            section=section, kind=self.kind, helix_angle_deg=beta, hand=spec.hand_value(),
            normal_pressure_angle_deg=normal, transverse_module=mt, lead=lead, overrun=mn,
            path_length=path, twist_deg=path * 360.0 / lead,
            overlap=overlap_ratio(mn, beta, width), n_min=self._n_min(normal, beta),
        )

    # -- what an internal gear overrides ----------------------------------

    def _section(self, spec: GearSpec, teeth: int, module: float, pressure_angle: float, width: float,
                 backlash: float, fillet: float, **extra: Any) -> SpurDerived:
        return spur.profile(teeth, module, pressure_angle, width, spec.bore_mm(), backlash, fillet, **extra)

    def _n_min(self, normal: float, beta: float) -> float:
        return undercut_minimum(normal, beta)

    def _section_diagnostics(self, section: Any, recipe: str, undercut_limit: int) -> List[Diagnostic]:
        return spur.section_diagnostics(section, recipe, undercut_limit)

    def _section_variables(self, spec: GearSpec, g: "HelicalDerived", beta_rad: str) -> List[GlobalVariable]:
        """From ``"Outer Diameter"`` to the end of the section's globals."""
        s = g.section
        beta = _q(HELIX_ANGLE)
        backlash = equations.literal(s.backlash) if s.backlash_typed else f"{BACKLASH_FACTOR} * {_q(MODULE)}"
        fillet = equations.literal(s.fillet) if s.fillet_typed else f"{FILLET_FACTOR} * {_q(MODULE)}"
        tm = _q(TRANSVERSE_MODULE)
        return [
            GlobalVariable(OUTER, f"{_q(TEETH)} * {tm} + 2 * {_q(MODULE)}"),
            GlobalVariable(PITCH, f"{_q(TEETH)} * {tm}"),
            GlobalVariable(BACKLASH, backlash),
            GlobalVariable(ARC_LENGTH, f"( ( {tm} * pi ) / 2 + {_q(BACKLASH)} / cos ( {beta} ) )",
                           f"( ( {tm} * pi ) / 2 + {_q(BACKLASH)} / cos ( {beta_rad} ) )"),
            GlobalVariable(FILLET, fillet),
            GlobalVariable(DEPTH, f"IIF ( {_q(MODULE)} <= 1.25 , {_q(MODULE)} * 2.4 , {_q(MODULE)} * 2.25 )"),
            GlobalVariable(FACE_WIDTH, equations.literal(s.face_width)),
            *spur.profile_variables(TRANSVERSE_PRESSURE_ANGLE, TRANSVERSE_MODULE),
        ]

    def _section_outline(self, spec: GearSpec, section: Any, recipe: str) -> List[Point2]:
        return spur.SpurGear().outline(spec, section, recipe)

    def _blank_ops(self, section: Any) -> List[Op]:
        return spur._blank_ops(section)  # noqa: SLF001

    def _space_ops(self, section: Any, recipe: str, plane: str) -> List[Op]:
        return spur.space_ops(section, recipe, plane=plane)

    def _bore_ops(self, spec: GearSpec, section: Any) -> List[Op]:
        return spur._bore_ops(section) if spec.has_bore() else []  # noqa: SLF001

    @property
    def plan_kind(self) -> str:
        return self.kind

    # -- checking --------------------------------------------------------

    def validate(self, spec: GearSpec, derived: Optional[HelicalDerived] = None) -> List[Diagnostic]:
        problems = self._errors(spec)
        if problems:
            return problems
        try:
            recipe = self.recipe_for(spec)
        except InputError as exc:
            return [Diagnostic(ERROR, str(exc), "recipe")]
        g = derived if derived is not None else self.derive(spec)
        out = self._section_diagnostics(g.section, recipe, g.undercut_limit)
        if any(d.is_error for d in out):
            return out
        low, high = USUAL_RANGE[self.kind]
        if not low <= g.helix_angle_deg <= high:
            out.append(Diagnostic(WARNING, (
                f"A helix angle of {_num(g.helix_angle_deg)}° is outside the usual {_num(low)}–{_num(high)}° "
                f"for a {self.kind} gear."), "helix_angle"))
        if self.kind == KIND_HELICAL and g.overlap < 1.0:
            out.append(Diagnostic(WARNING, (
                f"The teeth overlap {_num(g.overlap, 2)} of a pitch along the face, under one, which loses most "
                "of the smoothness helical teeth are for; widen the face or raise the helix angle."), "face_width"))
        if g.face_twist_deg > 360.0:
            out.append(Diagnostic(WARNING, (
                f"Each tooth turns {_num(g.face_twist_deg, 1)}° along the face, more than a whole turn."),
                "helix_angle"))
        return out

    # -- the equations ---------------------------------------------------

    def variables(self, spec: GearSpec, derived: HelicalDerived) -> List[GlobalVariable]:
        """The global variables, in the order they must be added.

        All ten of the user's spur names are here, in their spur order, with
        the helix globals they now refer to ahead of them.
        """
        g = derived
        s = g.section
        beta, beta_rad = f"{_q(HELIX_ANGLE)}", f"{_q(HELIX_ANGLE)} * pi / 180"
        alpha, alpha_rad = f"{_q(PRESSURE_ANGLE)}", f"{_q(PRESSURE_ANGLE)} * pi / 180"
        atn = findings.INVERSE_TANGENT
        out = [
            GlobalVariable(TEETH, equations.literal(s.teeth)),
            GlobalVariable(MODULE, equations.literal(s.module)),
            *([GlobalVariable(BORE, equations.literal(s.bore))] if self.has_bore_global else []),
            GlobalVariable(PRESSURE_ANGLE, equations.literal(g.normal_pressure_angle_deg)),
            GlobalVariable(HELIX_ANGLE, equations.literal(g.helix_angle_deg)),
            GlobalVariable(TRANSVERSE_MODULE, f"{_q(MODULE)} / cos ( {beta} )", f"{_q(MODULE)} / cos ( {beta_rad} )"),
            # atn answers in the document's angle unit; the radian form turns it back into degrees.
            GlobalVariable(TRANSVERSE_PRESSURE_ANGLE, f"{atn} ( tan ( {alpha} ) / cos ( {beta} ) )",
                           f"{atn} ( tan ( {alpha_rad} ) / cos ( {beta_rad} ) ) * 180 / pi"),
            *self._section_variables(spec, g, beta_rad),
            GlobalVariable(LEAD, f"pi * {_q(PITCH)} / tan ( {beta} )", f"pi * {_q(PITCH)} / tan ( {beta_rad} )"),
            GlobalVariable(OVERRUN, _q(MODULE)),
        ]
        if self.kind == KIND_HERRINGBONE:
            out.append(GlobalVariable(MID_WIDTH, f"{_q(FACE_WIDTH)} / 2"))
            out.append(GlobalVariable(PATH_LENGTH, f"{_q(MID_WIDTH)} + {_q(OVERRUN)}"))
        else:
            out.append(GlobalVariable(PATH_LENGTH, f"{_q(FACE_WIDTH)} + 2 * {_q(OVERRUN)}"))
        out.append(GlobalVariable(TWIST_ANGLE, f"{_q(PATH_LENGTH)} * 360 / {_q(LEAD)}"))
        return out

    def equation_lines(self, spec: GearSpec, derived: HelicalDerived, trig: str) -> List[str]:
        return [v.text(trig) for v in self.variables(spec, derived)]

    # -- drawing ---------------------------------------------------------

    def outline(self, spec: GearSpec, derived: HelicalDerived, recipe: str = "") -> List[Point2]:
        """The transverse section's outline, closed and counter-clockwise, in mm."""
        return self._section_outline(spec, derived.section, recipe or self.recipe_for(spec))

    # -- building --------------------------------------------------------

    def plan(self, spec: GearSpec, derived: HelicalDerived, recipe: str, template: str, path: str) -> BuildPlan:
        g = derived
        s = g.section
        recipe = recipe or self.recipe_for(spec)
        herringbone = self.kind == KIND_HERRINGBONE
        ez = findings.EXTRUDE_Z_SIGN
        width = s.face_width

        ops: List[Op] = [NewPart(template)]
        ops.extend(AddGlobal(v.name, v.expression, v.radian_expression) for v in self.variables(spec, g))
        ops.append(Axis("axis", AXIS_NAME, (2, 3)))

        blank = self._blank_ops(s)  # the same blank, half as deep for a herringbone
        if herringbone:
            blank = [
                replace(op, depth=width / 2.0) if isinstance(op, Extrude)
                else LinkDimension(f"Width@{BLANK}", _q(MID_WIDTH))
                if isinstance(op, LinkDimension) and op.dimension == f"Width@{BLANK}" else op
                for op in blank
            ]
        ops.extend(blank)

        if herringbone:
            z_section, z_end = ez * width / 2.0, -ez * g.overrun
            ops.append(RefPlane("plane", MID_PLANE, 1, width / 2.0, _flip_for(z_section)))
            ops.append(LinkDimension(f"Offset@{MID_PLANE}", _q(MID_WIDTH)))
            lead_in, lead_global = "Mid", MID_WIDTH
        else:
            z_section, z_end = -ez * g.overrun, ez * (width + g.overrun)
            ops.append(RefPlane("plane", PROFILE_PLANE, 1, g.overrun, _flip_for(z_section)))
            ops.append(LinkDimension(f"Offset@{PROFILE_PLANE}", _q(OVERRUN)))
            lead_in, lead_global = "Lead In", OVERRUN

        ops.extend(self._space_ops(s, recipe, "plane"))
        ops.extend(_path_ops(z_section, z_end, lead_in, lead_global))
        ops.append(SweepCut("space_cut", "space", "path", SPACE, g.twist_deg,
                            reverse=_reverse_for(g.hand_sign, z_end > z_section)))
        ops.append(LinkDimension(f"Twist@{SPACE}", _q(TWIST_ANGLE)))
        ops.append(CircularPattern("teeth", TEETH_PATTERN, "axis", "space_cut", s.teeth, "Count"))
        ops.append(LinkDimension(f"Count@{TEETH_PATTERN}", _q(TEETH)))
        if herringbone:
            ops.append(MirrorBody("mirror", MIRROR, "plane"))
        ops.extend(self._bore_ops(spec, s))
        part = re.split(r"[\\/]", path)[-1].rsplit(".", 1)[0] if path else spec.stem()
        ops.append(ManualStep("material", f"Assign a material to {part}; the build leaves it unset."))
        ops.append(Rebuild())
        ops.append(SaveAs(path))
        return BuildPlan(kind=self.plan_kind, recipe=recipe, ops=tuple(ops), path=path)


class HerringboneGear(HelicalGear):
    kind = KIND_HERRINGBONE


def _flip_for(z: float) -> bool:
    """The InsertRefPlane flip that puts a plane at ``z`` rather than ``-z``."""
    plus = findings.REF_PLANE_UNFLIPPED_IS_PLUS_Z
    return (z < 0) if plus else (z > 0)


def _reverse_for(hand_sign: int, toward_plus_z: bool) -> bool:
    """Whether the sweep's reverse-twist flag is needed for this hand on a path running this way.

    ``findings.TWIST_TURN`` says, for a path toward +Z and toward -Z, which way
    an unreversed sweep turned about +Z as z increases (+1 counter-clockwise).
    """
    turn = findings.TWIST_TURN["plus z" if toward_plus_z else "minus z"]
    return turn != hand_sign


def _sketch_point(z: float) -> Point2:
    """Where a point on the axis at model ``z`` is in the Top plane's sketch."""
    return (0.0, -z) if findings.TOP_SKETCH_Y_IS_MINUS_Z else (0.0, z)


def _path_ops(z_section: float, z_end: float, lead_in: str, lead_global: str) -> List[Op]:
    """The path sketch on the Top plane: a construction line from the origin to the section, then the path.

    Both lines are held vertical — the axis is the Top sketch's y direction —
    the lead-in starts on the origin and the path starts where it ends, and two
    lengths are linked, so the path stays on the axis whatever the globals do.
    """
    a = _sketch_point(z_section)
    b = _sketch_point(z_end)
    return [
        OpenSketch("path", 2),
        Line("lead", (0.0, 0.0), a, construction=True),
        Line("P", a, b),
        Relation("coincident", ("lead.start", ORIGIN)),
        Relation("vertical", ("lead",)),
        Relation("vertical", ("P",)),
        Relation("coincident", ("P.start", "lead.end")),
        Dimension(lead_in, ("lead",), (a[0] + 3.0, a[1] / 2.0), abs(z_section)),
        Dimension("Length", ("P",), (b[0] + 6.0, (a[1] + b[1]) / 2.0), abs(z_end - z_section)),
        CloseSketch("path", PATH_SKETCH),
        LinkDimension(f"{lead_in}@{PATH_SKETCH}", _q(lead_global)),
        LinkDimension(f"Length@{PATH_SKETCH}", _q(PATH_LENGTH)),
    ]


__all__ = [
    "DEFAULT_RANGE", "HelicalDerived", "HelicalGear", "HerringboneGear", "overlap_ratio", "transverse_pressure_angle",
    "undercut_minimum",
]
