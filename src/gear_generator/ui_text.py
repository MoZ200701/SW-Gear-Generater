"""The words the window puts on screen, worked out without a window.

Every panel header's readout, every derived row, candidate row and status line
is derived text: one short line standing for the state of something. Working
them out here keeps them testable on a machine with no display, and keeps
:mod:`gui` to laying out widgets and wiring handlers.

Nothing here touches tkinter, and nothing here holds state.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .gears import pair as pairs, standards
from .gears.base import Diagnostic
from .gears.equations import literal
from .spec import MODE_PAIR, RECIPE_ARCS, RECIPE_INVOLUTE, GearSpec, InputError, PairSpec, pair_stems

RECIPE_WORDS = {RECIPE_INVOLUTE: "involute curve", RECIPE_ARCS: "arc flanks"}
RECIPE_LABELS = {RECIPE_INVOLUTE: "Involute", RECIPE_ARCS: "Arcs"}
KIND_LABELS = {"spur": "Spur", "helical": "Helical", "herringbone": "Herringbone", "bevel": "Bevel",
               "internal": "Internal"}
TEETH_SIDE_LABELS = {"external": "External", "internal": "Internal"}
MESH_LABELS = TEETH_SIDE_LABELS
SHAFTS_LABELS = {"parallel": "Parallel", "crossed": "Crossed"}
MOTION_LABELS = {"fixed": "Fixed", "gear mate": "Gear mate"}
HANDS_PAIRING_LABELS = {"same": "Same", "opposite": "Opposite"}
HAND_LABELS = {"right": "Right", "left": "Left"}
# Five kinds share one segmented row, and "Herringbone" does not fit its share;
# the Gear panel's readout still says the whole word.
KIND_BUTTON_LABELS = {**KIND_LABELS, "herringbone": "Double"}
SERIES_LABELS = {standards.SERIES_1: "Series 1", standards.SERIES_1_2: "1 + 2", standards.SERIES_ALL: "+ fine"}

# What a readout says when the gear it stands for does not work out yet.
CHECK_THE_FIELDS = "check the fields"


def _n(value: float, places: int = 3) -> str:
    return literal(round(float(value), places))


# ------------------------------------------------------------- the readouts


def kind_readout(kind: str, recipe: str) -> str:
    """``Spur · involute curve``."""
    return f"{KIND_LABELS.get(kind, kind.title())} · {RECIPE_WORDS.get(recipe, recipe)}"


def gear_readout(spec: GearSpec) -> str:
    """``m1.5 · z25 · 20° · PD 37.5 mm``, or what is stopping it.

    A helical gear adds its helix, ``β15° R``, and its pitch diameter is the
    transverse one, ``m z / cos β``. A shifted gear adds ``x+0.25``. A ring ends
    ``· ring``; a bevel gear names its mate and shaft angle, ``z20:40 · Σ90°``.
    """
    try:
        m = spec.module_mm()
        n = spec.teeth_count()
        alpha = spec.pressure_angle_deg()
        if spec.kind == "bevel":
            return (f"m{_n(m)} · z{n}:{spec.mate_teeth_count()} · {_n(alpha, 2)}° · "
                    f"Σ{_n(spec.shaft_angle_deg(), 2)}° · PD {_n(m * n)} mm")
        shift = spec.profile_shift_value()
        if spec.is_helical():
            beta = spec.helix_angle_deg()
            hand = spec.hand_value()
            if not 0.0 < beta < 90.0:
                return CHECK_THE_FIELDS
    except InputError:
        return CHECK_THE_FIELDS
    ring = " · ring" if spec.is_internal() else ""
    shifted = f"x{shift_text(shift)} · " if shift else ""
    if spec.is_helical():
        return (f"m{_n(m)} · z{n} · {_n(alpha, 2)}° · β{_n(beta, 2)}° {hand[0].upper()} · {shifted}"
                f"PD {_n(m * n / math.cos(math.radians(beta)))} mm{ring}")
    return f"m{_n(m)} · z{n} · {_n(alpha, 2)}° · {shifted}PD {_n(m * n)} mm{ring}"


def is_bevel(g) -> bool:
    """A :class:`bevel.BevelDerived` — which passes every other name through to its back-cone section."""
    return type(g).__name__ == "BevelDerived"


def is_ring(g) -> bool:
    return type(g).__name__ == "InternalDerived"


def derived_line(g) -> str:
    """``PD 37.5 · OD 40.5 · RD 33.75 · base 35.238 · p 4.712``.

    A bevel gear: ``δ 26.565° · R 67.082 · OD 67.218 · X 58.195``; a ring
    ``PD 120 · tip 116 · root 125 · rim 137``.
    """
    if is_bevel(g):
        form = " · crown" if g.crown else (" · internal" if g.ring else "")
        return (f"δ {_n(g.delta, 3)}° · R {_n(g.cone_distance)} · OD {_n(g.da)} · X {_n(g.crown_to_apex)}{form}")
    if is_ring(g):
        return f"PD {_n(g.d)} · tip {_n(g.da)} · root {_n(g.df)} · rim {_n(g.rim)}"
    return (
        f"PD {_n(g.d)} · OD {_n(g.da)} · RD {_n(g.df)} · base {_n(g.db)} · p {_n(g.p)}"
    )


def derived_rows(g) -> List[Tuple[str, str]]:
    """The Derived panel's label/value rows. Every value is in mm, said once above them.

    Short on purpose: in pair mode two columns of these share the width the
    preview leaves.
    """
    if is_bevel(g):
        return [
            ("Pitch cone δ", f"{_n(g.delta, 3)}°"),
            ("Cone distance", _n(g.cone_distance)),
            ("Pitch diameter", _n(g.d)),
            ("Tip diameter" if g.ring else "Outer diameter", _n(g.da)),
            ("Apex to crown", _n(g.crown_to_apex)),
            ("Addendum", _n(g.addendum)),
            ("Dedendum", _n(g.dedendum)),
            ("Face angle", f"{_n(g.face_angle, 3)}°"),
            ("Root angle", f"{_n(g.root_angle, 3)}°"),
            ("Virtual teeth", "∞ · a rack" if g.crown else _n(g.virtual_teeth, 2) + (" · a ring" if g.ring else "")),
            ("Toe scale", _n(g.toe_scale, 4)),
            ("Tooth at pitch", _n(g.section.s)),
            ("Backlash", _n(g.section.backlash) + ("" if g.section.backlash_typed else " · 0.3m")),
        ]
    ring = []
    if is_ring(g):
        ring = [
            ("Rim diameter", _n(g.rim) + ("" if g.rim_typed else " · root + 6m")),
        ]
    helix = []
    if hasattr(g, "helix_angle_deg"):
        helix = [
            ("Helix", f"{_n(g.helix_angle_deg, 4)}° · {HAND_LABELS.get(g.hand, g.hand).lower()}"),
            ("Transverse m", _n(g.transverse_module, 4)),
            ("Transverse α", f"{_n(g.pressure_angle_deg, 3)}°"),
            ("Lead", _n(g.lead, 2)),
            ("Twist on face", f"{_n(g.face_twist_deg, 2)}°"),
            ("Overlap εβ", _n(g.overlap, 3)),
        ]
        if getattr(g, "groove", 0.0):
            helix.append(("Centre groove", f"{_n(g.groove)} · floor {_n(g.groove_d)}"))
    if is_ring(g):
        fillet_note = " · 0.15m"
        tip_label = "Inner tip"
    else:
        fillet_note = " · 0.38m"
        tip_label = "Outer diameter"
    shift = getattr(g, "shift", 0.0)
    if shift:
        # The coefficient, and how far that moves the tip and the root, in mm.
        ring = ring + [("Profile shift", f"{shift_text(shift)} · {_n(shift * g.module)}")]
    return helix + ring + [
        ("Pitch diameter", _n(g.d)),
        (tip_label, _n(g.da)),
        ("Root diameter", _n(g.df)),
        ("Base diameter", _n(g.db)),
        ("Tooth depth", _n(g.h)),
        ("Circular pitch", _n(g.p)),
        ("Space at pitch", _n(g.space)),
        ("Tooth at pitch", _n(g.s)),
        ("Tip thickness", _n(g.tip_thickness)),
        ("Backlash", _n(g.backlash) + ("" if g.backlash_typed else " · 0.3m")),
        ("Fillet", _n(g.fillet) + ("" if g.fillet_typed else fillet_note)),
    ]


def warning_lines(diagnostics: Sequence[Diagnostic]) -> List[str]:
    """Errors first, then warnings, each once."""
    ordered = [d for d in diagnostics if d.is_error] + [d for d in diagnostics if not d.is_error]
    return list(dict.fromkeys(d.message for d in ordered))


def pair_readout(centre: str, ratio: str, chosen: Optional["pairs.Candidate"] = None, symbol: str = "C") -> str:
    """``C 60 mm · i 3`` and, once one is chosen, ``· m1.5 20:60``; a bevel pair's ``R 50 mm``."""
    parts = []
    if centre.strip():
        parts.append(f"{symbol} {centre.strip()} mm")
    if ratio.strip():
        parts.append(f"i {ratio.strip()}")
    if chosen is not None:
        parts.append(f"m{_n(chosen.module, 4)} {chosen.teeth_driver}:{chosen.teeth_driven}")
    return " · ".join(parts) or "centre distance and ratio"


def pair_derived_readout(centre: float, ratio: float, epsilon: float, symbol: str = "C") -> str:
    """``C 60 mm · i 3 · contact ratio 1.671`` — the Derived panel's readout in pair mode.

    The three numbers are the pair's own, from :func:`pairs.describe`: the
    centre distance the teeth make, the ratio they turn at, and how many teeth
    are in contact on average. The per-gear sizes are in the table below it.
    """
    return f"{symbol} {_n(centre)} mm · i {_n(ratio)} · contact ratio {contact_ratio_text(epsilon)}"


def pair_derived_rows(centre: float, ratio: float, epsilon: float,
                      teeth_driver: int, teeth_driven: int, label: str = "Centre distance",
                      working_angle: Optional[float] = None) -> List[Tuple[str, str]]:
    """The three rows above the per-gear columns in Derived; a bevel pair's first is its cone distance.

    A shifted pair adds a fourth, the pressure angle it actually meshes at.
    """
    rows = [
        (label, f"{_n(centre)} mm"),
        ("Ratio", f"{_n(ratio)} · {teeth_driver} : {teeth_driven}"),
        ("Contact ratio", contact_ratio_text(epsilon)),
    ]
    if working_angle is not None:
        rows.append(("Working α", f"{_n(working_angle, 3)}°"))
    return rows


def candidate_row(candidate: "pairs.Candidate") -> Tuple[str, str, str, str]:
    """``(MODULE, TEETH, ERROR, tag)`` for one row of the candidate list.

    The tag is ``exact`` or ``near``, which is what the row is coloured by.
    """
    module = _n(candidate.module, 4) + ("" if candidate.standard else " *")
    teeth = f"{candidate.teeth_driver} : {candidate.teeth_driven}"
    errors = []
    symbol = "R" if candidate.cone else "C"
    if abs(candidate.centre_error) > pairs.TOLERANCE:
        errors.append(f"{symbol} {'+' if candidate.centre_error > 0 else '−'}{_n(abs(candidate.centre_error))} mm")
    if candidate.ratio_error > pairs.TOLERANCE:
        errors.append(f"i {_n(candidate.ratio_error * 100, 2)} %")
    if candidate.undercut:
        errors.append("undercut")
    if candidate.clashes:
        errors.append(f"clash {_n(candidate.clash, 2)} mm")
    text = " · ".join(errors) if errors else "exact"
    if candidate.shifted:
        text = f"x {shift_text(candidate.shift_1)}/{shift_text(candidate.shift_2)} · {text}"
    if candidate.cone:
        forms = pairs.bevel_forms(candidate.teeth_driver, candidate.teeth_driven, candidate.shaft_angle)
        named = [f"{side} {form}" for side, form in zip("AB", forms) if form != pairs.bevel.FORM_CONE]
        if named:
            text = f"{', '.join(named)} · {text}"
    if candidate.crossed:
        text = f"β{_n(candidate.helix_angle, 2)}°/{_n(candidate.helix_angle_b, 2)}° · {text}"
    elif candidate.helix_angle:
        text = f"β{_n(candidate.helix_angle, 2)}° · {text}"
    return module, teeth, text, "exact" if candidate.exact else "near"


def _exact_counts(candidates: Sequence["pairs.Candidate"]) -> Tuple[int, int]:
    """Clean rows — exact, standard, not undercut — without profile shift, and with it."""
    clean = [c for c in candidates if c.exact and c.standard and not c.undercut]
    shifted = sum(1 for c in clean if c.shifted)
    return len(clean) - shifted, shifted


def shift_text(shift: float) -> str:
    """``+0.25``, ``−0.1``, ``0``: a profile shift coefficient with its sign, always."""
    if not shift:
        return "0"
    return ("+" if shift > 0 else "−") + _n(abs(shift), 4)


def solve_summary(candidates: Sequence["pairs.Candidate"],
                  chosen: Optional["pairs.Candidate"] = None) -> str:
    """``64 candidates · 3 exact``, and the chosen row once there is one.

    ``64 candidates · 3 exact · m1.5 20 : 60 chosen``. The Pair panel and the
    flyout show the same line, so the strip still says what was picked with the
    candidates hidden.
    """
    if not candidates:
        return "No pair of whole tooth counts fits; widen the series or Min teeth."
    exact, shifted = _exact_counts(candidates)
    noun = "candidate" if len(candidates) == 1 else "candidates"
    text = f"{len(candidates)} {noun} · {exact} exact"
    if shifted:
        text += f" · {shifted} with shift"
    if chosen is not None:
        text += f" · m{_n(chosen.module, 4)} {chosen.teeth_driver} : {chosen.teeth_driven} chosen"
    return text


def output_readout(folder: str, limit: int = 38) -> str:
    """The folder, shortened from the left so its last parts stay readable."""
    text = folder.strip()
    if not text:
        return "choose a folder"
    if len(text) <= limit:
        return text
    return "…" + text[-(limit - 1):]


def link_headline(available: bool, snapshot: Optional[dict]) -> Tuple[str, str]:
    """The SolidWorks bar's readout, and which colour its dot takes.

    Unlike Airfoil Converter this app makes its own documents, so no document
    open is a perfectly good state to build from: it is ``ok``.
    """
    if not available:
        return "pywin32 not installed", "off"
    if snapshot is None:
        return "not reachable", "bad"
    label = snapshot.get("version") or "SolidWorks"
    if snapshot.get("newer_than_tested"):
        label += " (newer than tested)"
    title = snapshot.get("title")
    if not title:
        return f"{label} — no document open", "ok"
    return f"{label} — {title}", "ok"


def mode_note(mode: str, stems: Sequence[str], update_count: int = 0, document: str = "") -> str:
    """What the primary button is about to do, in a sentence."""
    if update_count and document:
        noun = "variable" if update_count == 1 else "variables"
        return f"Update values will change {update_count} {noun} in {document}."
    if mode == MODE_PAIR and len(stems) >= 3:
        return f"Build will make {stems[0]}.SLDPRT, {stems[1]}.SLDPRT and {stems[2]}.SLDASM."
    if stems:
        return f"Build will make {stems[0]}.SLDPRT."
    return "Build will make a new part."


def manual_steps_line(steps: Iterable[str]) -> str:
    """``1 thing to do by hand: …`` — counted, so it is not a surprise."""
    listed = list(dict.fromkeys(steps))
    if not listed:
        return ""
    noun = "thing" if len(listed) == 1 else "things"
    return f"{len(listed)} {noun} to do by hand: " + "; ".join(s.rstrip(".") for s in listed) + "."


# ------------------------------------------- what the number being typed means
#
# One card at the foot of the panel holding the caret. The name, the symbol and
# the sentences are fixed copy; the worked line is derived text like every
# readout, so it changes as the form does.

# The fields with a card, in the order they are on the form.
GEAR_EXPLAINERS = ("module", "teeth", "pressure_angle", "face_width", "bore", "backlash", "fillet", "profile_shift",
                   "helix_angle", "hand", "groove", "teeth_side", "rim", "shaft_angle", "mate_teeth", "name")
PAIR_EXPLAINERS = ("centre_distance", "cone_distance", "ratio", "pair_module", "series", "teeth_range", "mesh",
                   "shafts", "pair_shaft_angle", "hands", "motion", "assembly_name")
EXPLAINER_FIELDS = GEAR_EXPLAINERS + PAIR_EXPLAINERS

# (name, symbol, what it is). The symbol is what the diagram beside it marks.
_EXPLAINER_COPY: Dict[str, Tuple[str, str, str]] = {
    "module": ("Module", "m",
               "Tooth size, in mm: the pitch diameter divided by the number of teeth. A bigger module means "
               "bigger, stronger teeth and fewer of them for the same diameter. Two gears mesh only if their "
               "modules match."),
    "teeth": ("Teeth", "z",
              "How many teeth go round the gear. With the module it sets the size, PD = m × z, and the ratio "
              "between two gears is the ratio of their tooth counts. Fewer than 17 undercuts the root at 20°."),
    "pressure_angle": ("Pressure angle", "α",
                       "The slant of the flank: the angle between the line along which the teeth push on each "
                       "other and the tangent to the pitch circle. 20° is the standard; 14.5° runs quieter but "
                       "undercuts sooner, 25° is stronger but loads the bearings more. Meshing gears must "
                       "share it."),
    "face_width": ("Face width", "b",
                   "How thick the gear is along its axis: the depth it is extruded. Wider carries more load; "
                   "6 to 12 × module is usual for a spur gear."),
    "bore": ("Bore", "",
             "The hole through the centre for the shaft. Blank makes a solid disc. Leave a rim between the "
             "bore and the root circle: the form warns under one module, and two to three is usual."),
    "backlash": ("Backlash", "j",
                 "How much each tooth is thinned at the pitch circle so the pair does not bind: the space "
                 "grows by this and the tooth shrinks by it, on both gears, so the play in the mesh is twice "
                 "the number. Blank uses 0.3 × module, the default the equations carry; ISO asks 0.02–0.05 × m "
                 "for a precise pair."),
    "fillet": ("Fillet", "ρ",
               "The radius where each flank meets the root circle. It rounds off the sharp inside corner where "
               "a tooth would otherwise crack. Blank uses 0.38 × module."),
    "profile_shift": ("Profile shift", "x",
                      "How far the cutting rack is moved out from the gear, in modules. A positive shift makes the "
                      "tip and root circles bigger and the tooth thicker, which cures undercut on a small pinion; "
                      "the shifts of a pair together move its centre distance, which is how a standard module is "
                      "made to fit one. 0 is the standard tooth."),
    "helix_angle": ("Helix angle", "β",
                    "How far the teeth lean from the axis, measured on the pitch cylinder. Module and pressure "
                    "angle are then the normal ones, square to the teeth; round the gear the pitch is longer, "
                    "mt = m / cos β. Steeper runs smoother but pushes the gear harder along its shaft: 8–25° is "
                    "usual for a helical gear, 20–40° for a herringbone."),
    "hand": ("Hand", "",
             "Which way the teeth wind: a right-hand gear's lean like a right-hand screw thread. Helical gears on "
             "parallel shafts mesh only with opposite hands, and a pinion inside a ring with the same hand; in a "
             "pair gear B's hand follows gear A's. A herringbone's names its half nearest the Front plane."),
    "groove": ("Groove", "g",
               "A plain channel round the middle of a herringbone gear, between its two sets of teeth, where a "
               "hob or a grinding wheel runs out. Its floor is two modules inside the root circle. Blank leaves "
               "the two halves meeting at a point, as they do on a gear cut in one piece."),
    "teeth_side": ("Teeth", "",
                   "Which side of the rim the teeth are cut on. External teeth point outward, as on any gear; "
                   "internal teeth point inward from a ring, and a pinion runs inside it turning the same way. "
                   "A bevel gear's side is set by its cone, not here: outside a pitch cone under 90°, inside one "
                   "past it."),
    "rim": ("Rim", "",
            "A ring's outside diameter: the solid rim round the roots of its teeth. Blank leaves three modules "
            "of rim outside the root circle; under two modules the ring is thin."),
    "shaft_angle": ("Shaft angle", "Σ",
                    "The angle between the two shafts a bevel gear works across, 90° for a right-angle drive. "
                    "Each gear's pitch cone is its share of it, set by the two tooth counts; both gears of a pair "
                    "must be cut for the same angle. Past 90° the bigger gear's cone opens out: where it reaches "
                    "90° exactly it is a crown gear, its teeth on its face, and beyond that an internal bevel "
                    "gear, its teeth inside a cone."),
    "mate_teeth": ("Mate teeth", "z₂",
                   "How many teeth the gear this bevel gear meshes with has. A bevel gear's cone, and the Gleason "
                   "split of its tooth depth, depend on its mate; in a pair it is the other gear's teeth."),
    "name": ("Name", "",
             "The file the part is saved as, without .SLDPRT. Blank uses the name shown, built from module and "
             "teeth; in a pair the smaller gear is the pinion."),
    "centre_distance": ("Centre distance", "C",
                        "Shaft to shaft, centre to centre. Standard gears sit at C = m (z₁ + z₂) / 2, their "
                        "pitch circles touching, so C fixes how many teeth the pair has between them once a "
                        "module is chosen."),
    "cone_distance": ("Cone distance", "R",
                      "From the pitch apex, where the two bevel gears' axes meet, out along the pitch cone to "
                      "the back of the teeth. It is a bevel pair's size, as the centre distance is a spur "
                      "pair's: R = m √(z₁² + z₂² + 2 z₁ z₂ cos Σ) / (2 sin Σ)."),
    "mesh": ("Mesh", "",
             "External puts the two gears side by side, turning opposite ways. Internal makes gear B a ring "
             "with gear A inside it, turning the same way, at C = m (z₂ − z₁) / 2."),
    "shafts": ("Shafts", "",
               "Parallel shafts mesh helical gears of equal helix and opposite hand. Crossed shafts mesh them "
               "at an angle: of the same hand their two helix angles add up to the shaft angle, of opposite "
               "hands they differ by it."),
    "hands": ("Hands", "",
              "Whether the two gears of a crossed pair are the same hand or opposite hands. The same hand splits "
              "the shaft angle between the two helices, β₁ + β₂ = Σ, and suits a large angle such as 90°; "
              "opposite hands make it the difference, β₁ − β₂ = Σ, which reaches a small angle with two steep "
              "helices."),
    "pair_shaft_angle": ("Shaft angle", "Σ",
                         "The angle between the two shafts. A crossed helical pair splits it between its helix "
                         "angles; a bevel pair between its pitch cones."),
    "motion": ("Assembly", "",
               "Fixed holds both gears still, meshed: gear 1 fixed and gear 2 mated where its teeth meet gear 1's. "
               "Gear mate lets gear 1 turn on its axis and adds a SolidWorks gear mate, so dragging gear 1 turns "
               "gear 2 at the tooth ratio, the other way round, or the same way round a ring."),
    "ratio": ("Ratio", "i",
              "Turns of the driver for one turn of the driven gear, z₂ / z₁. 3 or 3:1 makes the second gear "
              "three times the first; 1:3 makes it a third."),
    "pair_module": ("Module", "m",
                    "Pin the module the solver may use, or leave it blank to try every standard one in the "
                    "chosen series."),
    "series": ("Series", "",
               "Which standard modules the solver tries. Series 1 is the preferred set (1, 1.25, 1.5, 2, "
               "2.5 …); 1 + 2 adds the in-between sizes (1.125, 1.375 …); + fine adds 0.5, 0.6, 0.7, 0.8 and "
               "0.9 for small gears."),
    "teeth_range": ("Teeth", "min to max",
                    "The tooth counts the solver may give either gear. Below 17 a 20° pinion undercuts; the "
                    "maximum keeps the list short."),
    "assembly_name": ("Assembly name", "",
                      "The file the assembly is saved as, without .SLDASM. Blank uses the name shown, built "
                      "from the module and both tooth counts."),
}


def explainer(field: str, derived, stem: str = "", pair: Optional[PairSpec] = None,
              folder: str = "") -> Tuple[str, str, str, str]:
    """``(name, symbol, what it is, the worked line)`` for one field of the form.

    ``derived`` is the :class:`spur.SpurDerived` of the gear the caret is in and
    ``pair`` the :class:`PairSpec` the solver's own fields are worked out from;
    ``stem`` is the name the part would be saved as and ``folder`` the output
    folder, both of which the Name lines quote. A gear that does not work out —
    ``derived`` ``None``, or a solver field the form cannot yet be read for —
    says ``check the fields``, exactly as the gear readout does, rather than
    showing a number that is about to change.

    The sentences are fixed copy; the worked line is derived text, so the card
    is filled in again on every re-derive and not only when the caret moves.
    """
    try:
        name, symbol, what = _EXPLAINER_COPY[field]
    except KeyError:
        raise ValueError(
            f"There is no explainer for a field called {field!r}; the fields with one are "
            f"{', '.join(EXPLAINER_FIELDS)}."
        ) from None
    return name, symbol, what, _worked_line(field, derived, stem, pair, folder)


def _in(folder: str) -> str:
    """`` in D:\\Gears`` — nothing at all until a folder is chosen."""
    return f" in {folder.strip()}" if folder.strip() else ""


def _worked_line(field: str, derived, stem: str, pair: Optional[PairSpec], folder: str) -> str:
    if derived is None:
        return CHECK_THE_FIELDS
    try:
        if field in PAIR_EXPLAINERS:
            if pair is None:
                return CHECK_THE_FIELDS
            return _pair_worked(field, derived, pair, folder)
        return _gear_worked(field, derived, stem, folder)
    except (InputError, ValueError, ZeroDivisionError):
        return CHECK_THE_FIELDS


def _gear_worked(field: str, g, stem: str, folder: str) -> str:
    if field == "module":
        return (f"m {_n(g.module)} × z {g.teeth} = PD {_n(g.d)} mm · tooth depth {_n(g.h)} · "
                f"circular pitch {_n(g.p)}")
    if field == "teeth":
        undercut = "undercut" if g.undercut else f"no undercut ({_n(g.undercut_limit, 2)} or more)"
        return f"z {g.teeth} → PD {_n(g.d)} mm · OD {_n(g.da)} mm · {undercut}"
    if field == "pressure_angle":
        return (f"{_n(g.pressure_angle_deg, 2)}° → base diameter {_n(g.db)} mm · "
                f"undercut below {_n(g.undercut_limit, 2)} teeth")
    if field == "face_width":
        return f"{_n(g.face_width)} mm = {_n(g.face_width / g.module, 1)} × module"
    if field == "bore":
        if g.bore <= 0:
            return "blank → a solid disc, no bore feature"
        return f"{_n(g.bore)} mm → rim {_n((g.df - g.bore) / 2)} mm to the root circle"
    if field == "backlash":
        # The equations thin the tooth by j and widen the space by j on both
        # gears, so what a mesh actually has to play with is 2 j.
        blank = "" if g.backlash_typed else "blank → "
        default = "" if g.backlash_typed else " (0.3 m)"
        return (f"{blank}{_n(g.backlash)} mm{default} · tooth {_n(g.s)} · space {_n(g.space)} · "
                f"play in the mesh {_n(2 * g.backlash)}")
    if field == "fillet":
        blank = "" if g.fillet_typed else "blank → "
        default = "" if g.fillet_typed else (" (0.15 m)" if is_ring(g) else " (0.38 m)")
        return f"{blank}{_n(g.fillet)} mm{default}"
    if field == "profile_shift":
        if is_bevel(g):
            return "a bevel gear's Gleason addendum is its shift; this stays 0"
        if is_ring(g):
            return "a ring is cut unshifted; this stays 0"
        shift = getattr(g, "shift", 0.0)
        lead = f"x {shift_text(shift)} →" if shift else "0 → a standard tooth ·"
        return (f"{lead} OD {_n(g.da)} mm · root {_n(g.df)} · tooth at pitch {_n(g.s)} · "
                f"undercut below {_n(g.undercut_limit, 2)} teeth")
    if field == "helix_angle":
        if not hasattr(g, "helix_angle_deg"):
            return "only a helical gear has a helix angle"
        return (f"β {_n(g.helix_angle_deg, 4)}° → mt {_n(g.transverse_module, 4)} · PD {_n(g.d)} mm · "
                f"lead {_n(g.lead, 2)} · overlap εβ {_n(g.overlap, 3)}")
    if field == "hand":
        if not hasattr(g, "helix_angle_deg"):
            return "only a helical gear has a hand"
        return (f"{HAND_LABELS.get(g.hand, g.hand).lower()} → wound like a {g.hand}-hand thread, "
                f"{_n(g.face_twist_deg, 2)}° round across the face")
    if field == "groove":
        if getattr(g, "kind", "") != "herringbone":
            return "only a herringbone gear has a centre groove"
        if not g.groove:
            return f"blank → the halves meet at the apex, {_n(g.face_width / 2)} mm of teeth each side"
        return (f"{_n(g.groove)} mm → {_n(g.toothed_width)} mm of teeth each side · floor ⌀ {_n(g.groove_d)} mm")
    if field == "teeth_side":
        if is_bevel(g):
            if g.ring:
                return f"internal → its pitch cone is {_n(g.delta, 2)}°, past 90°, so its teeth are inside the cone"
            if g.crown:
                return "external → a crown gear's teeth stand on its face"
            return "external → a bevel gear's teeth are outside its cone below 90°"
        if is_ring(g):
            return f"internal → teeth point inward from a {_n(g.rim)} mm rim, tips at {_n(g.da)} mm"
        return f"external → teeth point outward, tips at {_n(g.da)} mm"
    if field == "rim":
        if not is_ring(g):
            return "only a ring has a rim"
        blank = "" if g.rim_typed else "blank → "
        return f"{blank}{_n(g.rim)} mm → {_n((g.rim - g.df) / 2)} mm of rim outside the root circle"
    if field == "shaft_angle":
        if not is_bevel(g):
            return "only a bevel gear has a shaft angle"
        form = " · a crown gear" if g.crown else (" · an internal bevel" if g.ring else "")
        return (f"Σ {_n(g.shaft_angle, 2)}° → this gear's cone {_n(g.delta, 3)}°, its mate's "
                f"{_n(g.delta_mate, 3)}°{form}")
    if field == "mate_teeth":
        if not is_bevel(g):
            return "only a bevel gear has a mate count"
        return (f"z₂ {g.mate_teeth} → cone distance {_n(g.cone_distance)} mm · addendum {_n(g.addendum)} · "
                f"dedendum {_n(g.dedendum)}")
    if field == "name":
        return f"{stem}.SLDPRT{_in(folder)}"
    raise ValueError(f"There is no worked line for a gear field called {field!r}.")


def _pair_worked(field: str, g, pair: PairSpec, folder: str) -> str:
    if field == "centre_distance":
        centre = pair.centre_distance_mm()
        # The gear's own module first, then the two standard ones below it: the
        # same centre distance buys more teeth as the module comes down.
        smaller = [m for m in standards.modules(pair.series or standards.SERIES_1) if m < g.module - 1e-9]
        tried = [g.module] + sorted(smaller, reverse=True)[:2]
        sums = " · ".join(f"{int(round(2 * centre / m))} at m {_n(m)}" for m in tried)
        return f"{_n(centre)} mm → z₁ + z₂ = {sums}"
    if field == "cone_distance":
        radius = pair.cone_distance_mm()
        shaft = pair.shaft_angle_deg()
        return (f"{_n(radius)} mm at Σ {_n(shaft, 2)}° → m {_n(g.module)} × z {g.teeth} gives R "
                f"{_n(pairs.bevel.cone_distance(g.module, g.teeth, pair.gear_b.teeth_count(), shaft))}")
    if field == "mesh":
        if pair.mesh_value() == "internal":
            return f"internal → gear B is a ring round gear A, C = m (z₂ − z₁) / 2"
        return "external → the gears sit side by side, C = m (z₁ + z₂) / 2"
    if field == "shafts":
        if pair.shafts_value() == "crossed":
            if pair.hands_value() == "opposite":
                return f"crossed → |β₁ − β₂| = {_n(pair.shaft_angle_deg(), 2)}°, opposite hands"
            return f"crossed → β₁ + β₂ = {_n(pair.shaft_angle_deg(), 2)}°, both gears the same hand"
        return "parallel → both gears the same helix angle, opposite hands"
    if field == "hands":
        shaft = _n(pair.shaft_angle_deg(), 2)
        if pair.hands_value() == "opposite":
            return f"opposite → β₁ − β₂ = ±{shaft}°, gear B the other hand from gear A"
        return f"same → β₁ + β₂ = {shaft}°, gear B the same hand as gear A"
    if field == "pair_shaft_angle":
        return f"Σ {_n(pair.shaft_angle_deg(), 2)}°"
    if field == "motion":
        n1, n2 = pair.gear_a.teeth_count(), pair.gear_b.teeth_count()
        if pair.motion_value() == "fixed":
            return "fixed → gear 1 fixed, gear 2 mated at the mesh angle; nothing turns"
        way = "the same way" if pair.mesh_value() == "internal" else "the other way"
        return f"gear mate → a turn of gear 1 turns gear 2 {_n(n1 / n2, 4)} of a turn, {way}"
    if field == "ratio":
        wanted = pair.ratio.strip() or _n(pair.ratio_value())
        return f"{wanted} → {pair.gear_a.teeth_count()} : {pair.gear_b.teeth_count()}"
    if field == "pair_module":
        pinned = pair.module_mm()
        if pinned is not None:
            return f"m {_n(pinned)} → the solver tries only this module"
        allowed = standards.modules(pair.series or standards.SERIES_1)
        listed = " · ".join(_n(m) for m in allowed[:7])
        return f"blank → {listed} … from {SERIES_LABELS.get(pair.series, pair.series)}"
    if field == "series":
        allowed = standards.modules(pair.series or standards.SERIES_1)
        label = SERIES_LABELS.get(pair.series, pair.series)
        return f"{label} → {len(allowed)} modules from {_n(allowed[0])} to {_n(allowed[-1])} (ISO 54)"
    if field == "teeth_range":
        candidates = pairs.solve_spec(pair)
        exact, shifted = _exact_counts(candidates)
        noun = "candidate" if len(candidates) == 1 else "candidates"
        return (f"{pair.min_teeth_count()} to {pair.max_teeth_count()} → {len(candidates)} {noun} at "
                f"C {_n(pair.centre_distance_mm())}, i {pair.ratio.strip()} · {exact} exact"
                + (f" · {shifted} with shift" if shifted else ""))
    if field == "assembly_name":
        return f"{pair_stems(pair)[2]}.SLDASM{_in(folder)}"
    raise ValueError(f"There is no worked line for a solver field called {field!r}.")


def angle_text(degrees: float) -> str:
    return f"{_n(degrees, 4)}°"


def contact_ratio_text(epsilon: float) -> str:
    return "—" if not math.isfinite(epsilon) else _n(epsilon, 3)


# -- after SolidWorks has done something -------------------------------------


def _file(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1] if path else ""


def build_status(result) -> Tuple[str, bool]:
    """One sentence for a finished build, and whether it went well.

    ``result`` is a :class:`swbuild.BuildResult`, read by its fields only.
    """
    if result.failures:
        what, why = result.failures[0]
        where = f"{result.document} was left open, unsaved" if result.document else "Nothing was built"
        return f"{where}. {what.strip()}: {why}", False
    if not result.saved:
        return f"SolidWorks reported an error rebuilding {result.document}, so it was left open, unsaved.", False
    text = f"Built {_file(result.saved)}."
    if result.checks:
        text += " Check: " + "; ".join(result.checks) + "."
    manual = manual_steps_line(result.manual)
    if manual:
        text += " " + manual
    return text, not result.checks


def pair_status(result) -> Tuple[str, bool]:
    """One sentence for a pair: the first thing that went wrong, or all three files."""
    for part in (result.gear_a, result.gear_b, result.assembly):
        if part is None:
            continue
        text, ok = build_status(part)
        if not ok or not part.saved:
            return text + (f" Skipped {result.skipped}." if result.skipped else ""), False
    files = [_file(part.saved) for part in (result.gear_a, result.gear_b, result.assembly) if part is not None]
    manual = [step for part in (result.gear_a, result.gear_b, result.assembly) if part is not None
              for step in part.manual]
    checks = [check for part in (result.gear_a, result.gear_b, result.assembly) if part is not None
              for check in part.checks]
    text = f"Built {', '.join(files[:-1])} and {files[-1]}."
    if checks:
        text += " Check: " + "; ".join(checks) + "."
    line = manual_steps_line(manual)
    return (text + (" " + line if line else "")), not checks


def update_status(result) -> Tuple[str, bool]:
    """One sentence for Update values."""
    if result.failures:
        what, why = result.failures[0]
        return f"{what} could not be set in {result.document}: {why}", False
    if not result.changed:
        return f"Nothing to update: every value in {result.document} already matches the form.", True
    noun = "variable" if len(result.changed) == 1 else "variables"
    if not result.rebuilt:
        return (f"Changed {len(result.changed)} {noun} in {result.document}, but SolidWorks reported an error "
                "on the rebuild."), False
    return f"Changed {len(result.changed)} {noun} in {result.document} and rebuilt it.", True


# -- the Workbook window (docs/PLAN-WORKBOOK.md §5) --------------------------------------


def _plural(count: int, one: str, many: str = "") -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def short_path(path: str, limit: int = 64) -> str:
    """A path that fits a line: the start and as much of the end as room allows, ``…`` between.

    The end — the folder a file is in, and its name — is what tells files apart,
    so it is kept whole whenever it fits.
    """
    if len(path) <= limit:
        return path
    sep = "\\" if "\\" in path and "/" not in path else "/"
    parts = path.split(sep)
    head = sep.join(parts[:2]) if path.startswith(sep) else parts[0]
    tail: List[str] = []
    for piece in reversed(parts[1:]):
        candidate = sep.join([piece] + tail)
        if len(head) + len(candidate) + 3 > limit and tail:
            break
        tail.insert(0, piece)
    text = f"{head}{sep}…{sep}{sep.join(tail)}"
    return text if len(text) < len(path) else path


def workbook_counts(spec) -> str:
    """``3 shafts · 4 gears · 2 meshes · no modes`` — the header's readout of what the file holds."""
    modes = _plural(len(spec.modes), "mode") if spec.modes else "no modes"
    return " · ".join([_plural(len(spec.shafts), "shaft"), _plural(len(spec.gears), "gear"),
                       _plural(len(spec.meshes), "mesh", "meshes"), modes])


def workbook_read_line(clock_text: str, open_in_excel: bool) -> str:
    """``read 14:02:31 · open in Excel`` — when the file was last read, and whether Excel holds it."""
    return f"read {clock_text}" + (" · open in Excel" if open_in_excel else "")


GEAR_STATE_BUILDS, GEAR_STATE_SHARES, GEAR_STATE_LATER, GEAR_STATE_ERROR = "builds", "shares", "later", "error"


def workbook_gear_rows(spec, parts, diagnostics: Sequence[Diagnostic]) -> List[Tuple[str, ...]]:
    """One row per gear for the window's table: gear, shaft, kind, teeth, module, face, part, state, what.

    ``part`` is the part file's name without ``.SLDPRT`` (every part is one), so the column stays narrow.

    ``parts`` is a :class:`workbook.build.PartsPlan` (it may be empty when the
    workbook has errors); ``diagnostics`` are the per-gear ones, each naming its
    cell. ``state`` is one of the ``GEAR_STATE_*`` words, for the window's dot.
    """
    by_gear = {}
    for job in parts.jobs:
        for index, gear_id in enumerate(job.gear_ids):
            by_gear[gear_id] = (job, index)
    later = dict(parts.later)
    erred_rows = {_gears_row(d.field) for d in diagnostics if d.is_error}
    erred = {gear.id for gear in spec.gears if gear.row in erred_rows}
    rows = []
    for gear in spec.gears:
        kind = KIND_LABELS.get(gear.kind_word(), gear.kind_word().title())
        if gear.side == "internal":
            kind = "Ring"
        part = ""
        if gear.id in later:
            import re
            phase = re.search(r"phase (W\d+)", later[gear.id])
            state, what = GEAR_STATE_LATER, f"later · phase {phase.group(1)}" if phase else "later"
        elif gear.id in erred:
            state, what = GEAR_STATE_ERROR, "see Checks"
        elif gear.id in by_gear:
            job, index = by_gear[gear.id]
            part = job.stem
            if index:
                state, what = GEAR_STATE_SHARES, f"the same part as {job.gear_ids[0]}"
            else:
                state, what = GEAR_STATE_BUILDS, "to build"
        else:
            state, what = GEAR_STATE_ERROR, "see Checks"
        rows.append((gear.id, gear.shaft, kind, gear.teeth, gear.module, gear.face_width, part, state, what))
    return rows


def _gears_row(where: str) -> int:
    """The row of a Gears-sheet cell a diagnostic names (``Gears!F3``, ``Gears row 3``), or 0."""
    import re
    match = re.match(r"^Gears(?:!\$?[A-Za-z]{1,3}\$?(\d+)| row (\d+))$", where or "")
    return int(match.group(1) or match.group(2)) if match else 0


def workbook_parts_readout(parts) -> str:
    """The Gears panel's readout: ``4 parts to build · 1 later``."""
    pieces = [_plural(len(parts.jobs), "part") + " to build"] if parts.jobs else ["nothing to build yet"]
    if parts.later:
        pieces.append(f"{len(parts.later)} later")
    return " · ".join(pieces)


def workbook_checks_readout(diagnostics: Sequence[Diagnostic]) -> str:
    errors = sum(1 for d in diagnostics if d.is_error)
    warnings = len(diagnostics) - errors
    if not diagnostics:
        return "no problems"
    pieces = []
    if errors:
        pieces.append(_plural(errors, "error"))
    if warnings:
        pieces.append(_plural(warnings, "warning"))
    return " · ".join(pieces)


def workbook_changes_readout(changes: Sequence[str], clock_text: str) -> str:
    if not changes:
        return f"nothing changed · {clock_text}"
    return f"{_plural(len(changes), 'change')} · {clock_text}"


def workbook_status(parts, diagnostics: Sequence[Diagnostic], error: str = "", folder: str = "") -> Tuple[str, bool]:
    """The footer's one sentence, and whether Build can go ahead."""
    if error:
        return error, False
    errors = [d for d in diagnostics if d.is_error]
    if errors:
        first = errors[0].message
        more = f" ({len(errors) - 1} more under Checks)" if len(errors) > 1 else ""
        return f"Fix the workbook before building: {first}{more}", False
    if not parts.jobs:
        return "Nothing in this workbook can be built yet: " + (parts.later[0][1] + "." if parts.later
                                                                 else "it has no gears."), False
    if not folder:
        return "Choose an output folder (the Box sheet's, or the strip's Output) before building.", False
    files = _plural(len(parts.jobs), "part")
    return f"Ready: Build makes {files} in {short_path(folder, 48)}.", True


def _shared_steps(results) -> List[str]:
    """Manual steps across a batch, one line for a step every part shares: *Assign a material to each of the 4
    parts* rather than four sentences that differ only in the part's name."""
    import os
    counts: Dict[str, List[str]] = {}
    for result in results:
        stem = os.path.splitext(os.path.basename(result.saved.replace("\\", "/")))[0]
        for step in result.manual:
            key = step.replace(stem, "{part}") if stem else step
            counts.setdefault(key, []).append(step)
    out = []
    for key, steps in counts.items():
        if len(steps) > 1 and "{part}" in key:
            out.append(key.replace("{part}", f"each of the {len(steps)} parts"))
        else:
            out.extend(steps)
    return out


def many_status(result) -> Tuple[str, bool]:
    """One sentence for a batch of parts: how many were built, or the first thing that went wrong."""
    built = [r for r in result.built if r.ok and r.saved]
    for part in result.built:
        if not (part.ok and part.saved):
            text, _ = build_status(part)
            done = f"{_plural(len(built), 'part')} built before it; " if built else ""
            skipped = f" {_plural(len(result.skipped), 'part')} not attempted." if result.skipped else ""
            return f"{done}{text}{skipped}", False
    text = f"Built {_plural(len(built), 'part')}."
    manual = manual_steps_line(_shared_steps(built))
    checks = [c for r in built for c in r.checks]
    if checks:
        text += " Check: " + "; ".join(checks) + "."
    if manual:
        text += " " + manual
    return text, not checks
