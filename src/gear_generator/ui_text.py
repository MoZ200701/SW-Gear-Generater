"""The words the window puts on screen, worked out without a window.

Every panel header's readout, every derived row, candidate row and status line
is derived text: one short line standing for the state of something. Working
them out here keeps them testable on a machine with no display, and keeps
:mod:`gui` to laying out widgets and wiring handlers.

Nothing here touches tkinter, and nothing here holds state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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
    if len(text) > limit:
        # One component is longer than the room: keep the start and end of the last one, which is the name.
        name = parts[-1]
        room = max(8, limit - len(head) - 4)
        keep = (room - 1) // 2
        text = f"{head}{sep}…{sep}{name[:keep]}…{name[-(room - 1 - keep):]}"
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
# W4 (Agent C): a gear whose part is built and matches the record; built, and Update SolidWorks would change it;
# built, but its change needs a new part (a new revision). ``workbook_gear_rows`` gains keyword-only ``record=None,
# update=None`` (a store.LinkRecord and a workbook.update.UpdatePlan) to choose them; without them it is as today.
GEAR_STATE_BUILT, GEAR_STATE_CHANGES, GEAR_STATE_NEW_PART = "built", "changes", "new part"


def workbook_gear_rows(spec, parts, diagnostics: Sequence[Diagnostic], *, record=None,
                       update=None, plan=None) -> List[Tuple[str, ...]]:
    """One row per gear for the window's table: gear, shaft, kind, teeth, module, face, part, state, what.

    ``part`` is the part file's name without ``.SLDPRT`` (every part is one), so the column stays narrow.

    ``parts`` is a :class:`workbook.build.PartsPlan` (it may be empty when the
    workbook has errors); ``diagnostics`` are the per-gear ones, each naming its
    cell. ``state`` is one of the ``GEAR_STATE_*`` words, for the window's dot.

    With ``record`` (a ``store.LinkRecord``) a gear its current parts serve is
    *built*, its part the recorded file's; with ``update`` too (a
    ``workbook.update.UpdatePlan``) it is *built · changes on Update* when its
    part's values change, and *needs a new part* (red) when a reason Update
    cannot carry names it, or its part's file is missing. A gear still to
    build shows the part the build would make — ``plan.part_of`` (a
    ``workbook.gearbox.GearboxPlan``), which is ``<stem>_r2`` when its own
    file name is taken — rather than its own stem (second review N6). A built
    gear whose part the next build would make new rather than reuse
    (``plan.made_new``: its Update not saved, or found not as recorded) is
    *built · new part on Build*, as the footer says it (the W4 rerun on
    SolidWorks: the table said *built* beside a footer making G2's part new).
    """
    by_gear = {}
    for job in parts.jobs:
        for index, gear_id in enumerate(job.gear_ids):
            by_gear[gear_id] = (job, index)
    later = dict(parts.later)
    built = {g: p for p in (record.current_parts() if record is not None else []) for g in p.gears}
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
        elif gear.id in built:
            entry = built[gear.id]
            part = _stem(entry.path)
            state, what = _built_state(gear.id, entry, update, plan)
        elif gear.id in by_gear:
            job, index = by_gear[gear.id]
            planned = (getattr(plan, "part_of", None) or {}).get(gear.id, "") if plan is not None else ""
            part = _stem(planned) if planned else job.stem
            if index:
                state, what = GEAR_STATE_SHARES, f"the same part as {job.gear_ids[0]}"
            else:
                state, what = GEAR_STATE_BUILDS, "to build"
        else:
            state, what = GEAR_STATE_ERROR, "see Checks"
        rows.append((gear.id, gear.shaft, kind, gear.teeth, gear.module, gear.face_width, part, state, what))
    return rows


def _built_state(gear_id: str, entry, update, plan=None) -> Tuple[str, str]:
    """A gear already built: whether Update SolidWorks leaves it, changes it, or cannot carry its change — and
    whether the next build makes its part new rather than reuse it (``plan.made_new``)."""
    import re
    from .store import same_path
    if update is not None:
        named = re.compile(rf"(?<![\w]){re.escape(gear_id)}(?![\w])")
        if any(same_path(entry.path, m) for m in update.missing) or any(named.search(s) for s in update.structural):
            return GEAR_STATE_NEW_PART, "needs a new part"
    if update is not None and any(gear_id in p.gear_ids for p in update.changed_parts):
        return GEAR_STATE_CHANGES, "built · changes on Update"
    if any(gear_id in m.gear_ids and same_path(m.old, entry.path) for m in (getattr(plan, "made_new", ()) or ())):
        return GEAR_STATE_CHANGES, "built · new part on Build"
    return GEAR_STATE_BUILT, "built"


def _gears_row(where: str) -> int:
    """The row of a Gears-sheet cell a diagnostic names (``Gears!F3``, ``Gears row 3``), or 0."""
    import re
    match = re.match(r"^Gears(?:!\$?[A-Za-z]{1,3}\$?(\d+)| row (\d+))$", where or "")
    return int(match.group(1) or match.group(2)) if match else 0


def workbook_parts_readout(parts, *, record=None) -> str:
    """The Gears panel's readout: ``4 parts to build · 1 later``.

    With ``record`` (a ``store.LinkRecord``), the parts whose every gear its
    current parts serve are counted as built, as the table's rows say:
    ``4 parts built``, ``3 parts built · 1 to build``."""
    served = {g for p in (record.current_parts() if record is not None else []) for g in p.gears}
    built = [job for job in parts.jobs if job.gear_ids and all(g in served for g in job.gear_ids)]
    new = len(parts.jobs) - len(built)
    if built:
        pieces = [_plural(len(built), "part") + " built"] + ([f"{new} to build"] if new else [])
    else:
        pieces = [_plural(len(parts.jobs), "part") + " to build"] if parts.jobs else ["nothing to build yet"]
    if parts.later:
        pieces.append(f"{len(parts.later)} later")
    return " · ".join(pieces)


CHECKS_PROVISIONAL = ("Provisional: the workbook's formulas still hold Excel's old values, so these checks may "
                      "change once Excel recalculates and saves it, and no fixes are offered until then.")
EXPORT_WAITS = ("the workbook's formulas still hold Excel's old values; open and save it in Excel first, so what is "
                "exported is worked out from what they now give.")


def provisional_tag(provisional: bool) -> str:
    """`` · provisional`` after a readout worked out from a read whose formulas Excel has yet to recalculate."""
    return " · provisional" if provisional else ""


def workbook_checks_readout(diagnostics: Sequence[Diagnostic], provisional: bool = False) -> str:
    if provisional:
        rest = workbook_checks_readout(diagnostics)
        return "provisional" + ("" if rest == "no problems" else f" · {rest}")
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


CONSEQUENCE_CELLS = 3      # cells named in one piece of the line; more are counted, not named


def _cells(fields: Sequence[str]) -> str:
    cells = list(dict.fromkeys(f for f in fields if f))
    shown = ", ".join(cells[:CONSEQUENCE_CELLS]) + (", …" if len(cells) > CONSEQUENCE_CELLS else "")
    return f" ({shown})" if shown else ""


COVERED_BY_FIX = ", covered by the chosen fix"


def workbook_consequence(consequence, covered: Sequence[Tuple[str, str]] = ()) -> str:
    """What a save did to the checks, in one line: ``G1–G2 now 0.25 mm off · 1 new error (Gears!F3)``.

    ``consequence`` is a :class:`workbook.link.Consequence`. Empty when the
    checks say what they said before; the Checks panel has the sentences.
    ``covered``: meshes said to be off that a chosen, unexported fix puts back
    on centres (:func:`workbook.link.covered_by_fix`)."""
    if not consequence:
        return ""
    pieces = [f"{a}–{b} now on centres" if off is None
              else f"{a}–{b} now {_n(off)} mm off" + (COVERED_BY_FIX if (a, b) in covered else "")
              for a, b, off in consequence.meshes]
    if consequence.new_errors:
        pieces.append(_plural(len(consequence.new_errors), "new error") + _cells(consequence.new_errors))
    if consequence.new_warnings:
        pieces.append(_plural(len(consequence.new_warnings), "new warning") + _cells(consequence.new_warnings))
    if consequence.cleared:
        pieces.append(f"{len(consequence.cleared)} cleared" + _cells(consequence.cleared))
    return " · ".join(pieces)


def workbook_change_lines(changes: Sequence[str], consequence=None,
                          covered: Sequence[Tuple[str, str]] = ()) -> List[str]:
    """The Since the last read panel: one line per changed cell, and what they did.

    One cell changed: what it did follows it on its line, *Gears!F3 G2 Teeth
    68 → 70 · G1–G2 now 1.5 mm off*. Several: no one cell did it, so it is a
    line of its own after them."""
    did = workbook_consequence(consequence, covered) if consequence is not None else ""
    if not did:
        return list(changes)
    if len(changes) == 1:
        return [f"{changes[0]} · {did}"]
    return list(changes) + [did]


def _left_for_later(parts) -> str:
    """`` Left for a later phase: Gears!A6: G5 is a bevel gear: …`` — never a bare "Ready" or "Built" while rows
    wait for a later phase: they are not checked, and nothing places them."""
    refused = getattr(parts, "refused", [])
    if not refused:
        return ""
    more = f" ({len(refused) - 1} more under Checks)" if len(refused) > 1 else ""
    return f" Left for a later phase: {refused[0].message}{more}"


def _shared_steps(results) -> List[str]:
    """Manual steps across a batch, one line for a step every part shares: *Assign a material to each of the 4
    parts* rather than four sentences that differ only in the part's name."""
    import os
    import re
    counts: Dict[str, List[str]] = {}
    for result in results:
        stem = os.path.splitext(os.path.basename(result.saved.replace("\\", "/")))[0]
        for step in result.manual:
            # The part's name as a whole word, and the last one: a name like "a" also reads as a word earlier on.
            found = list(re.finditer(rf"(?<![\w.-]){re.escape(stem)}(?![\w.-])", step)) if stem else []
            key = step[:found[-1].start()] + "{part}" + step[found[-1].end():] if found else step
            counts.setdefault(key, []).append(step)
    out = []
    for key, steps in counts.items():
        if len(steps) > 1 and "{part}" in key:
            out.append(key.replace("{part}", f"each of the {len(steps)} parts"))
        else:
            out.extend(steps)
    return out


NOTE_JOB = "job"              # a finished job's own sentence: it marks a moment the workbook may have moved on from
NOTE_STANDING = "standing"    # what an Export, a Locate… or a save did: no job stood between it and the state
NOTE_ANSWER = "answer"        # how the Build again? question was answered: the state it answered still holds


@dataclass(frozen=True)
class Note:
    """The Workbook window's last sentence of its own, kept until the file next changes: ``text``, shown as good
    when ``ok``, and its ``kind``, which says how the footer joins it to the state (:func:`workbook_footer`):

    - :data:`NOTE_JOB` — a build's or an update's sentence. It takes the
      state's place while the state is fine; otherwise *… Since then: <state>*.
    - :data:`NOTE_STANDING` — what an Export, a Locate… or a save did. It
      takes the state's place while the state is fine; otherwise the state
      follows plainly, since it was already so.
    - :data:`NOTE_ANSWER` — No to *Build again?*, or the question left open
      while the workbook changed. The state follows plainly, always: the
      reason the question was asked still stands (W4 review nit).
    """

    text: str
    ok: bool
    kind: str = NOTE_JOB


def _as_note(note) -> Optional[Note]:
    """A :class:`Note`, or a plain ``(text, ok)`` pair from a caller that knows only a job's sentence (the
    demonstration script's desk), taken as a job's."""
    if note is None or isinstance(note, Note):
        return note
    text, ok = note
    return Note(text, ok)


def export_note(done, copy_name: str = "") -> Note:
    """What an Export did, for the footer: a :data:`NOTE_STANDING` :class:`Note`. ``done`` is a
    :class:`workbook.export.Exported`; ``copy_name`` the file Export as… wrote, or ``""``.

    A formula cell is never written over. When it is a fix's target the
    formula may well land on the fix's value once Excel recalculates — S3's X
    as ``=C3+68`` follows S2 — so the sentence says what to look for rather than
    asking for the formula to be typed over, and Results wait for that save.
    The fix's own value is given (no fix is offered from a provisional read,
    so it is worked from what Excel last calculated), but Checks are the test.
    When every cell the fix names is a formula nothing reaches the file, so
    nothing a formula reads has changed: that is said as a fault, and the
    formula, or a cell it reads, is what has to change."""
    formula_cells = {cell for cell, *_ in done.formulas}
    if not done.written and done.formulas and all(cell in formula_cells for cell, _ in done.refused):
        # Nothing reached the file, so nothing a formula reads changed: recalculating cannot move them.
        cells = "; ".join(f"{cell} ({item} {header}, the fix would make it {value})"
                          for cell, item, header, value in done.formulas)
        where = f"changed in the copy, {copy_name}" if copy_name else "written"
        return Note(f"Nothing was {where}: every cell the fix would change holds a formula — {cells} — and Excel "
                    "recalculating cannot move them, since nothing they read has changed. Change the formula, or a "
                    "cell it reads, in Excel; the fix stays chosen until then.", False, NOTE_STANDING)
    what = _plural(len(done.written), "cell") + (" and the Results sheet" if done.results else "")
    parts = [f"Exported {what}" + (f" to {copy_name}" if copy_name else "") + "."]
    if done.added_headers:
        parts.append("Added the column " + ", ".join(done.added_headers) + ".")
    for cell, item, header, value in done.formulas:
        parts.append(f"{cell} ({item} {header}) holds a formula, so it was not written (the fix would make it "
                     f"{value}): once Excel has recalculated, Checks will say whether {item} sits where its meshes "
                     "need it.")
    others = [(cell, why) for cell, why in done.refused if cell not in formula_cells]
    if others:
        parts.append("Not written: " + "; ".join(f"{cell} ({why})" for cell, why in others)
                     + ". Results were not written, since the fix is only partly in the workbook.")
    elif done.formulas:
        parts.append("The Results sheet was left out until then: Export again after Excel's save to write it."
                     if not copy_name else "The Results sheet was left out of the copy, since the fix is only "
                                           "partly in it.")
    if done.results_error:
        parts.append(f"The Results sheet could not be written: {done.results_error} Export again to write it.")
    return Note(" ".join(parts), not others and not done.results_error, NOTE_STANDING)


RECALC_WAIT = ("Export wrote cells that formulas in the workbook may depend on: open and save it in Excel so they "
               "recalculate; Build and Export wait for that save.")
RESULTS_DUE = " Export again to write the Results sheet: it waited for Excel to recalculate."


def workbook_speed_lines(spec, motion) -> Tuple[List[str], str]:
    """The Speeds panel: one line per shaft (speed, way round, torque), and its header readout. A gearbox a
    later phase drives gives the one sentence saying so, and no readout."""
    if motion.later:
        return [motion.later], ""
    lines = []
    for shaft in spec.shafts:
        speed = motion.speeds.get(shaft.id)
        if speed is None:
            lines.append(f"{shaft.id:<4}  not driven")
            continue
        torque = motion.torques.get(shaft.id)
        torque_text = f" · {torque:.2f} N·m" if torque is not None else ""
        lines.append(f"{shaft.id:<4}  {abs(float(speed)):.1f} rpm {motion.turns(shaft.id)}{torque_text}")
    return lines, ("seen from +Z" if motion.speeds else "no input")


def end_view_readout(view) -> str:
    """The end view's header: the face heights it colours apart, and whether the origin is in sight."""
    return " · ".join(f"z {_n(z, 1)}" for z in view.planes) + (" · origin" if view.origin else " · origin off view")


# -- W4: the footer as one decision, and the sentences of a gearbox build and update ----------------------------
#
# Interfaces pinned in the W4 interface commit (docs/PLAN-WORKBOOK.md §5, W4-PLAN §4.1–§4.2). ``workbook_footer``
# replaced W2–W3's ``workbook_state`` once the window was wired to it. Everything here reads the plans and the
# worker's results by their fields only (never ``GearboxResult.ok``), and the worker's own BuildError text is
# shown as it comes, never reworded.

BUILD = "build"              # make the parts, the layout part and the assembly (reusing what is built)
BUILD_PARTS = "parts"        # W2's batch, when only rows a later phase builds hold the layout back
BUILD_AGAIN = "again"        # an assembly is on record: ask, then make the next revision
BUILD_LABELS = {BUILD: "Build", BUILD_PARTS: "Build parts", BUILD_AGAIN: "Build again…"}

RECALC_WAIT_UPDATE = ("Export wrote cells that formulas in the workbook may depend on: open and save it in Excel so "
                      "they recalculate; Build, Update SolidWorks and Export wait for that save.")
ALREADY_MATCHES = "SolidWorks already matches the workbook: nothing was changed."


def save_to_keep(paths: Sequence[str]) -> str:
    """After an update, the save asked for, naming every document it changed (W4 review S4.8: a bare *Save in
    SolidWorks to keep it.* followed a list of several)."""
    return f"Save {_and(_stem(p) for p in paths)} in SolidWorks to keep {_them(len(paths))}."


@dataclass(frozen=True)
class Footer:
    """The Workbook window's footer, decided whole: the sentence and how it is shown, and both buttons.

    ``build_action`` is one of :data:`BUILD`, :data:`BUILD_PARTS`,
    :data:`BUILD_AGAIN` and ``build_label`` its :data:`BUILD_LABELS` word;
    ``build_primary`` is False for Build again… (Update is the primary then).
    ``update_shown`` once anything is on record; ``update_enabled`` under the
    same gate as Build plus the record's own checks; ``update_primary`` once
    an assembly is on record.
    """

    text: str
    ok: bool
    build_action: str = BUILD
    build_label: str = "Build"
    build_enabled: bool = False
    build_primary: bool = True
    update_shown: bool = False
    update_enabled: bool = False
    update_primary: bool = False


_EXTENSIONS = (".sldprt", ".sldasm", ".slddrw")


def _stem(path: str) -> str:
    """``C:\\P\\Gear_m1.5_N68.SLDPRT`` -> ``Gear_m1.5_N68``; a SolidWorks extension only, so ``Gear_m1.5`` keeps
    its ``.5``."""
    name = _file(path)
    return name[:-7] if name.lower().endswith(_EXTENSIONS) else name


def _folder_of(path: str) -> str:
    text = path.replace("\\", "/")
    return path[:len(text.rsplit("/", 1)[0])] if "/" in text else ""


def _and(items: Iterable[str]) -> str:
    """``A``, ``A and B``, ``A, B and C``."""
    items = [str(i) for i in items if str(i)]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if not text or text[-1] in ".?!…" else text + "."


def progress_text(step, updating: bool = False) -> str:
    """*Building in SolidWorks: part 2 of 4, Gear_m1.5_N68…*, *… the layout part…*, *… the assembly…*,
    *… checking interference…*; *Updating SolidWorks: Gear_m1.5_N68…* — from a ``swbuild.Step`` (None: the
    first words alone)."""
    from . import swbuild
    lead = "Updating SolidWorks" if updating else "Building in SolidWorks"
    if step is None:
        return f"{lead}…"
    name, of = step.name, (f"{step.index} of {step.count}" if step.count else "")
    stage = step.stage
    if stage == swbuild.STAGE_PART:
        what = ", ".join(p for p in (f"part {of}" if of else "a part", name) if p)
    elif stage == swbuild.STAGE_CHECK:
        counted = (f"{of} already built" if not updating else of) if of else ""
        what = f"checking {name or 'what is built'}" + (f" ({counted})" if counted else "")
    elif stage == swbuild.STAGE_LAYOUT:
        what = "the layout part" + (f", {name}" if name else "")
    elif stage == swbuild.STAGE_ASSEMBLY:
        what = "the assembly" + (f", {name}" if name else "")
    elif stage == swbuild.STAGE_INTERFERENCE:
        what = "checking interference"
    elif stage == swbuild.STAGE_VALUES:
        what = name or "the values"
    elif stage == swbuild.STAGE_PLACE:
        what = "placing the gears" + (f" in {name}" if name else "")
    else:
        what = name
    return f"{lead}: {what}…" if what else f"{lead}…"


def _clash_lines(clashes) -> List[str]:
    lines = []
    for clash in clashes:
        named = [g for g in (clash.gears or clash.components) if g]
        if len(named) >= 2:
            lines.append(f"{_and(named)} interfere, {_n(clash.volume)} mm³")
        elif named:
            lines.append(f"{named[0]} interferes with something, {_n(clash.volume)} mm³")
        else:
            lines.append(f"an interference of {_n(clash.volume)} mm³ that SolidWorks could not name")
    return lines


def _all_meshes(clashes, meshes) -> bool:
    """Whether every clash is between the two gears of a listed mesh. ``meshes`` None: not known (the wording from
    before W4's smoke test, which took every clash for a mesh)."""
    if meshes is None:
        return True
    listed = {frozenset(pair) for pair in meshes}
    return all(len(set(c.gears)) == 2 and frozenset(c.gears) in listed for c in clashes)


def _interference(clashes, error: str, assembly: str, meshes=None) -> Tuple[str, bool]:
    """``; no interference between the gears`` (to end a sentence), or a sentence of its own that stands out.

    A clash is said to be at *their mesh* only when its two gears are a listed mesh (``meshes``, pairs of gear
    ids): SolidWorks 2026 showed a widened gear clashing with one beside it on the same shaft that it does not
    mesh with (W4 smoke test), so any other clash, or one it could not name, is *where they meet*."""
    where = f" in {assembly}" if assembly else ""
    if error:
        return f". Interference could not be checked: {_sentence(error)} Look at each mesh{where} by eye.", False
    if clashes:
        lines = _clash_lines(clashes)
        if _all_meshes(clashes, meshes):
            look = "at their mesh" if len(lines) == 1 else "at those meshes"
        else:
            look = "where they meet"
        return f". Check: {'; '.join(lines)}; look {look}{where}.", False
    return "; no interference between the gears.", True


def _done_phrase(made: Sequence[str], reused: Sequence[str]) -> str:
    """``Built 1 part and R_r2_Layout, reusing the 3 parts already built``; ``Reused R_Layout and …``."""
    if made:
        return "Built " + _and(made) + (", reusing " + _and(reused) if reused else "")
    if reused:
        return "Reused " + _and(reused)
    return ""


def _already(count: int) -> str:
    return "" if not count else ("the part already built" if count == 1 else f"the {count} parts already built")


def _layout_reused(plan) -> bool:
    from .workbook.gearbox import LayoutReuse
    return isinstance(getattr(plan, "layout", None), LayoutReuse)


def _never_made(doc) -> bool:
    """A document SolidWorks never made (``swbuild._build_in_job``: no title, its first step the new document's):
    a template it could not use, nearly always, so pressing again fails the same way until that is changed."""
    return not doc.document and doc.stopped_at in ("new part", "new assembly")


def _went_wrong(doc, name: str, title: str = "") -> str:
    """What one document's failure left, as a sentence: *SolidWorks did not make the assembly. There is no
    assembly template at …* for one never made (no label left lower-case in the middle: W4 review S4.3), else
    *Part3 was left open, unsaved; cut 'Tooth Space': FeatureCut4 would not cut.* ``title``: how the document
    made is named (*the assembly Assem1*), its SolidWorks title by default."""
    title = title or doc.document
    if doc.failures:
        what, why = doc.failures[0]
        if _never_made(doc):
            return f"SolidWorks did not make {name}. {_sentence(why)}"
        if what.strip() == "save":
            return f"{title} was left open, unsaved, since it would not save: {_sentence(why)}"
        if what.strip() == "the build":
            return f"{title} was left open, unsaved: {_sentence(why)}"
        return f"{title} was left open, unsaved; {what.strip()}: {_sentence(why)}"
    return f"SolidWorks reported an error rebuilding {title}, so it was left open, unsaved."


def _template_first(doc, button: str, reused: str) -> str:
    """For a document never made: change the template before pressing again (the same press would fail the same
    way); else ``""``."""
    if not _never_made(doc):
        return ""
    noun = "assembly" if doc.stopped_at == "new assembly" else "part"
    tail = f": {reused}" if reused else ""
    return (f" Set {'an' if noun == 'assembly' else 'a'} {noun} template SolidWorks can use (the Box sheet's "
            f"{noun.capitalize()} template, else the strip's), then press {button}{tail}.")


def _gears_part(gear_ids: Sequence[str], count: int = 1) -> Tuple[str, str]:
    """(``G2's part`` / ``the part for G1 and G5`` / ``the parts for G1 and G2``, ``is``/``are``)."""
    ids = list(gear_ids)
    if count == 1:
        return (f"{ids[0]}'s part" if len(ids) == 1 else f"the part for {_and(ids)}"), "is"
    return f"the parts for {_and(ids)}", "are"


def _them(count: int) -> str:
    return "it" if count == 1 else "them"


def _mismatched_status(plan, result, button: str) -> str:
    """A build the live check stopped (``GearboxResult.mismatched``): what it found, and that the next press makes
    those parts new — the finish has recorded them (W4 review B2's last corner) — rather than fail again."""
    from . import store
    found = [p for p, _ in result.mismatched]
    reuse = list(getattr(plan, "reuse", ()) or ())
    parts = [r for r in reuse if any(store.same_path(r.path, p) for p in found)]
    layout = getattr(plan, "layout", None)
    layout_bad = _layout_reused(plan) and any(store.same_path(layout.path, p) for p in found)
    does = []
    if parts:
        who, _ = _gears_part([g for r in parts for g in r.gear_ids], len(parts))
        does.append(f"makes {who} new rather than reuse {_and(r.stem for r in parts)}")
    if layout_bad:
        does.append("builds the next revision, with a layout part of its own")
    whys = " ".join(_sentence(why) for _, why in result.mismatched)
    then = (f" The next press of {button} {_and(does)}; nothing is overwritten." if does else
            f" The next press of {button} does not reuse {_them(len(found))}.")
    return f"Nothing was built. {whys}{then}"


def gearbox_status(plan, result, again: bool = False) -> Tuple[str, bool]:
    """A finished build's sentence (``workbook.gearbox.GearboxPlan``, ``swbuild.GearboxResult``): *Built 4 parts,
    Reducer_12to1_Layout and Reducer_12to1.SLDASM; no interference between the gears.*, a clash's *Check: G1 and
    G2 interfere, 12.345 mm³; …*, or what went wrong and what the next press does.

    ``again``: the press was Build again… (an assembly was on record), so
    until this revision's layout part is saved the button still reads Build
    again… and the sentence names it. A document SolidWorks never made (its
    template) asks for the template first rather than another press that
    would fail the same way. A raise between documents
    (``GearboxResult.failures``) says where the job stopped and what was not
    attempted; a live check that found a document to reuse not holding what
    it should (``mismatched``) says what it found and that the next press
    makes it new."""
    parts_only = plan is None or (plan.layout is None and plan.assembly is None)
    layout = result.layout
    layout_on = bool(result.layout_reused) or (layout is not None and layout.ok and bool(layout.saved))
    button = "Build parts" if parts_only else ("Build again…" if again and not layout_on else "Build")
    if result.mismatched:
        return _mismatched_status(plan, result, button), False
    made = [r for r in result.parts.built if r.ok and r.saved]
    reused_parts = len(plan.reuse) if plan is not None else 0
    reused_layout = _stem(result.layout_reused) if result.layout_reused else ""
    made_names = [_plural(len(made), "part")] if made else []

    for part in result.parts.built:
        if not (part.ok and part.saved):
            text = _went_wrong(part, _stem(part.path) or "the part")
            before = f"{_plural(len(made), 'part')} built before it; " if made else ""
            skipped = len(result.parts.skipped)
            if parts_only:
                tail = f" {_plural(skipped, 'part')} not attempted." if skipped else ""
            elif skipped:
                tail = f" {_plural(skipped, 'part')} not attempted, nor the layout and assembly."
            else:
                tail = " The layout and assembly were not attempted."
            reused = "what was built is reused" if made or reused_parts else ""
            then = _template_first(part, button, reused) or (
                f" Press {button} to carry on" + (f": {reused}." if reused else "."))
            return f"{before}{text}{tail}{then}", False

    if layout is not None and not (layout.ok and layout.saved):
        text = _went_wrong(layout, "the layout part")
        done = _done_phrase(made_names, [_already(reused_parts)] if reused_parts else [])
        lead = f"{done}; " if done else ""
        reused = ("the parts are reused" if made or reused_parts else "")
        then = _template_first(layout, button, reused) or (
            f" Press {button} to carry on" + (f": {reused}." if reused else "."))
        return f"{lead}{text} The assembly was not attempted.{then}", False

    layout_name = _stem(layout.saved) if layout is not None and layout.saved else ""
    assembly = result.assembly
    if assembly is not None and not (assembly.ok and assembly.saved):
        made_now = made_names + ([layout_name] if layout_name else [])
        reused_now = ([reused_layout] if reused_layout else []) + ([_already(reused_parts)] if reused_parts else [])
        done = _done_phrase(made_now, reused_now)
        failed = _went_wrong(assembly, "the assembly", f"the assembly {assembly.document}")
        lead = f"{done}; " if done else ""
        failed = failed if lead else failed[:1].upper() + failed[1:]
        then = _template_first(assembly, button, "the parts and layout are reused") or (
            f" Press {button} to try the assembly again: the parts and layout are reused.")
        return f"{lead}{failed}{then}", False

    built_names = made_names + ([layout_name] if layout_name else [])
    asm_name = _file(assembly.saved) if assembly is not None and assembly.saved else ""
    if asm_name:
        built_names.append(asm_name)
    reused_names = ([reused_layout] if reused_layout else []) + ([_already(reused_parts)] if reused_parts else [])
    done = _done_phrase(built_names, reused_names)
    if result.failures:
        # A raise between documents (W4 review B1): the job returned what it had saved, and says where it stopped.
        what, why = result.failures[0]
        later = [] if plan is None else [
            name for name, planned, reached in (
                ("the layout part", plan.layout is not None and not _layout_reused(plan), layout is not None),
                ("the assembly", plan.assembly is not None, assembly is not None))
            if planned and not reached and name != what]
        missed = (f" {_and(later)[:1].upper()}{_and(later)[1:]} {'was' if len(later) == 1 else 'were'} not "
                  "attempted.") if later else ""
        stopped = f"The job stopped during {what}: {_sentence(why)}{missed}"
        if not done:
            return f"Nothing was saved. {stopped} Press {button} to try again.", False
        return f"{done}. {stopped} Press {button} to carry on: what was built is reused.", False
    if not done:
        return "Nothing was built.", False
    results = made + [r for r in (layout, assembly) if r is not None and r.saved]
    checks = [c for r in results for c in r.checks]
    ok = not checks
    if not parts_only and not asm_name:
        # Planned and never reached, with nothing failing: say what the worker said was left.
        skipped = f" {_sentence(result.skipped)}" if result.skipped else " The assembly was not made."
        text, ok = f"{done}.{skipped}", False
    elif asm_name:
        ending, clean = _interference(result.clashes, result.interference_error, asm_name,
                                      tuple(plan.meshes) if plan is not None and plan.meshes else None)
        text, ok = done + ending, ok and clean
    else:
        text = f"{done}."
    if checks:
        text += " Check: " + "; ".join(checks) + "."
    manual = manual_steps_line(_shared_steps(results))
    if manual:
        text += " " + manual
    return text, ok


def _missing_sentence(missing: Sequence[str]) -> str:
    files = [_file(p) for p in missing]
    if len(files) == 1:
        folder = _folder_of(missing[0])
        where = f"in {short_path(folder, 48)}" if folder else "where it was built"
        return (f"{files[0]} is no longer {where}: it was moved, renamed or deleted since it was built, so Update "
                "SolidWorks cannot change it.")
    return (f"{_and(files)} are no longer where they were built: they were moved, renamed or deleted since, so "
            "Update SolidWorks cannot change them.")


_STRIP_AGAIN = "; build it again as a new part."


def _reason(text: str) -> str:
    """A reason Update cannot carry, as the workbook says it. ``swbuild.structural_change`` ends its sentence for
    the strip's single part, *…; build it again as a new part.*; folded into the footer's offer that read "build
    again" twice (W4 review S4.2), so here the part *needs a new part* and the offer says how."""
    text = _sentence(text)
    return text[:-len(_STRIP_AGAIN)] + ", so it needs a new part." if text.endswith(_STRIP_AGAIN) else text


def _cannot_carry(update) -> str:
    """Why Update SolidWorks cannot carry the change, as one sentence (the first reason, and how many more)."""
    if update.missing:
        more = len(update.structural)
        also = f" (and {_plural(more, 'other change')} it cannot carry)" if more else ""
        return _missing_sentence(update.missing)[:-1] + also + "."
    more = len(update.structural) - 1
    also = f" (and {_plural(more, 'other change')} Update SolidWorks cannot carry)" if more else ""
    return _reason(update.structural[0])[:-1] + also + "."


def _again_sentence(update, name: str = "") -> str:
    """Why Update cannot carry it, and the offer: *Gear_m1.5_N17 (G1): The recipe changed from 'A' to 'B', so it
    needs a new part. Update SolidWorks offers to build again as Reducer_12to1_r2.* — "build again" once."""
    target = name or "a new revision"
    offer = f"Update SolidWorks offers to build again as {target}."
    if update.missing:
        more = len(update.structural)
        also = f" (and {_plural(more, 'other change')} Update SolidWorks cannot carry)" if more else ""
        files = [_file(p) for p in update.missing]
        if len(files) == 1:
            folder = _folder_of(update.missing[0])
            where = f"in {short_path(folder, 48)}" if folder else "where it was built"
            return (f"{files[0]} is no longer {where}: it was moved, renamed or deleted since it was built{also}, so "
                    f"{offer}")
        return (f"{_and(files)} are no longer where they were built: they were moved, renamed or deleted since{also}, "
                f"so {offer}")
    return f"{_cannot_carry(update)} {offer}"


def update_summary(update) -> str:
    """What Update SolidWorks will do, before the press (``workbook.update.UpdatePlan``): *Update SolidWorks will
    change G2's values (Gear_m1.5_N68), move S2 and S3 in Reducer_12to1_Layout, and re-place G2, G3 and G4.*; the
    structural sentence when it needs a new revision; *SolidWorks already matches the workbook on record* when
    nothing on record differs."""
    if update.refusal:
        return update.refusal
    if update.needs_new_revision:
        return _again_sentence(update)
    if update.record_matches:
        return ("SolidWorks already matches the workbook on record; Update SolidWorks checks it live and puts right "
                "anything changed there.")
    pieces = []
    changed = update.changed_parts
    if len(changed) == 1 and len(changed[0].gear_ids) == 1:
        pieces.append(f"change {changed[0].gear_ids[0]}'s values ({_stem(changed[0].path)})")
    elif changed:
        pieces.append("change the values in " + _and(f"{_stem(p.path)} ({', '.join(p.gear_ids)})" for p in changed))
    if update.moved_shafts:
        layout = f" in {_stem(update.layout.path)}" if update.layout is not None else ""
        pieces.append(f"move {_and(update.moved_shafts)}{layout}")
    if update.replaced:
        pieces.append(f"re-place {_and(update.replaced)}")
    if len(pieces) > 1:
        pieces[-1] = "and " + pieces[-1]
    return "Update SolidWorks will " + ", ".join(pieces) + "."


def _kept_name(path: str, spec) -> str:
    """`` (it now has 69 teeth; its file keeps its name)`` when a value update leaves a default-named part's file
    name saying what it no longer holds; ``""`` otherwise (a Part name of the user's own never goes stale)."""
    import re
    if spec is None or str(getattr(spec, "name", "")).strip():
        return ""
    try:
        wanted = spec.default_stem()
    except Exception:  # noqa: BLE001 - a spec that does not work out has no name to compare
        return ""
    held = re.sub(r"_r\d+$", "", _stem(path))
    if held == wanted:
        return ""
    for mark, word in (("N", "{} teeth"), ("m", "module {}")):
        old, new = (re.search(rf"_{mark}([^_]+)", s) for s in (held, wanted))
        if old and new and old.group(1) != new.group(1):
            now_ = "now has" if mark == "N" else "is now"
            return f" (it {now_} {word.format(new.group(1))}; its file keeps its name)"
    return " (its file keeps its name, which no longer says what it holds)"


def _layout_shafts(names: Sequence[str]) -> List[str]:
    """``["S2 X", "S3 X", "S3 Y"]`` -> ``["S2", "S3"]``: the shafts a layout's changed globals move."""
    shafts: List[str] = []
    for name in names:
        head, _, axis = name.rpartition(" ")
        if head and axis in ("X", "Y") and head not in shafts:
            shafts.append(head)
    return shafts


def gearbox_update_status(update, result, dragged: Sequence[str] = (), *, meshes=None) -> Tuple[str, bool]:
    """A finished update's sentence (``UpdatePlan``, ``swbuild.GearboxUpdate``, ``Finished.dragged``), ending
    with :func:`save_to_keep` naming the documents whenever ``result.changed`` is not empty; *SolidWorks already
    matches the workbook: nothing was changed.* when nothing was. ``meshes``: the record's listed meshes (pairs of
    gear ids), so a clash is called a mesh only when it is one (see :func:`_interference`)."""
    changed_docs = [_stem(p) for p in result.changed]
    if result.failures:
        what, why = result.failures[0]
        text = f"Update SolidWorks stopped. {what.strip()}: {_sentence(why)}"
        if changed_docs:
            one = len(changed_docs) == 1
            text += (f" It had already changed {_and(changed_docs)}, not saved: press Update SolidWorks again once "
                     f"that is put right, or save {'it' if one else 'them'} in SolidWorks to keep what it did.")
        else:
            text += " Nothing was changed."
        return text, False

    pieces: List[str] = []
    ok = True
    for index, part in enumerate(result.parts):
        if not part.changed:
            continue
        planned = update.parts[index] if index < len(update.parts) else None
        name = _stem(planned.path) if planned is not None else _stem(part.document)
        pieces.append(f"changed {_plural(len(part.changed), 'variable')} in {name}"
                      + _kept_name(planned.path if planned is not None else part.document,
                                   getattr(planned, "spec", None)))
        if not part.rebuilt:
            pieces[-1] += " (SolidWorks reported an error rebuilding it)"
            ok = False
    if result.layout is not None and result.layout.changed:
        name = _stem(update.layout.path) if update.layout is not None else _stem(result.layout.document)
        shafts = _layout_shafts(result.layout.changed)
        pieces.append(f"moved {_and(shafts)} in {name}" if shafts
                      else f"changed {_plural(len(result.layout.changed), 'variable')} in {name}")
        if not result.layout.rebuilt:
            pieces[-1] += " (SolidWorks reported an error rebuilding it)"
            ok = False
    dragged = list(dragged)
    placed = [g for g in result.placed if g not in dragged]
    if placed:
        pieces.append(f"re-placed {_and(placed)}")

    assembly = _file(update.assembly) if update.assembly else ""
    nothing = not pieces and not dragged and not result.changed
    if nothing:
        text = ALREADY_MATCHES
        if assembly and (result.clashes or result.interference_error):
            ending, ok = _interference(result.clashes, result.interference_error, assembly, meshes)
            text += ending[1:]
        return text, ok
    put_back = ""
    if dragged:
        one = len(dragged) == 1
        put_back = (f"{_and(dragged)} had been moved in SolidWorks; put back where the workbook has "
                    f"{'it' if one else 'them'}")
    text = "Updated SolidWorks: " + (", ".join(pieces) if pieces else put_back)
    if assembly:
        if not result.rebuilt:
            text += f". SolidWorks reported an error rebuilding {assembly}, so look at it before saving."
            ok = False
        else:
            ending, clean = _interference(result.clashes, result.interference_error, assembly, meshes)
            text, ok = text + ending, ok and clean
    else:
        text += "."
    if put_back and pieces:
        text += f" {put_back}."
    if result.changed:
        text += " " + save_to_keep(result.changed)
    return text, ok


def _made_new_by(plan, why: str) -> list:
    return [m for m in (getattr(plan, "made_new", ()) or ()) if m.why == why]


def _occupied(plan, overwritten: bool = True, superseded: Sequence[str] = ()) -> str:
    """Why a new part takes another file name than its own (``GearboxPlan.made_new``, review S5), one sentence per
    reason: *Gear_m1.5_N17.SLDPRT is already there, built from this workbook for values G1 no longer has, so G1's
    part is made as Gear_m1.5_N17_r2; nothing is overwritten.* For a copied workbook the files of the workbook it
    was copied from are said once, by :func:`_copy_sentence`, not part by part. *Nothing is overwritten* is said
    once, after the last (``overwritten``; the question says it in its own last sentence). A part of this
    workbook's own for other values that is one of the parts on record (``superseded``) is not said: it is the
    part a change Update cannot carry replaces, and that change's sentence says so already."""
    from . import store
    from .workbook.gearbox import NO_RECORD, OTHER_WORKBOOK, STALE
    folder = getattr(plan, "folder", "") or ""
    copied = getattr(plan, "foreign_record", "") or ""
    groups: Dict[Tuple[str, str], list] = {}
    for m in getattr(plan, "made_new", ()) or ():
        if m.why not in (STALE, OTHER_WORKBOOK, NO_RECORD):
            continue
        if m.why == OTHER_WORKBOOK and copied and store.same_path(m.workbook, copied):
            continue
        if m.why == STALE and any(store.same_path(m.old, p) for p in superseded):
            continue
        groups.setdefault((m.why, m.workbook.lower()), []).append(m)
    out = []
    for (why, _), items in groups.items():
        one = len(items) == 1
        files = _and(_file(m.old) for m in items)
        there = _folder_of(items[0].old)
        where = ("already there" if not there or store.same_path(there, folder)
                 else f"already in {short_path(there, 48)}")
        ids = [g for m in items for g in m.gear_ids]
        who, be = _gears_part(ids, len(items))
        lead = f"{files} {'is' if one else 'are'} {where}"
        if why == STALE:
            lead += f", built from this workbook for values {_and(ids)} no longer {'has' if len(ids) == 1 else 'have'}"
        elif why == OTHER_WORKBOOK:
            lead += f", built from {_file(items[0].workbook)}"
        else:
            lead += (f", with no record that this workbook built {_them(len(items))} (a build that was interrupted "
                     "can leave such a file)")
        out.append(f"{lead}, so {who} {be} made as {_and(_stem(m.new) for m in items)}")
    if not out:
        return ""
    return ". ".join(out) + ("; nothing is overwritten." if overwritten else ".")


def _held_back(plan, subject: str, after_unsaved_line: bool) -> str:
    """The parts made new although a built one matched (``GearboxPlan.made_new``, UNSAVED and MISMATCHED), as what
    ``subject`` (*Build*, *the new revision*) does: *While Gear_m1.5_N68's changes are not saved, the new revision
    makes G2's part new, as Gear_m1.5_N69, rather than reuse it.* — after the sentence asking for the save, which is
    not asked again (W4 review S3, S4.1); true too if SolidWorks closed it unsaved, which nothing here can know
    (second review N2) — else with its own reason. A part marked mismatched — a check found it not holding what
    the record says, or a job found it closed with Update's changes unsaved — *does not hold what the record
    says, as the last job in SolidWorks found*."""
    from .workbook.gearbox import MISMATCHED, UNSAVED
    out = []
    for why in (UNSAVED, MISMATCHED):
        items = _made_new_by(plan, why)
        if not items:
            continue
        one = len(items) == 1
        olds = _and(_stem(m.old) for m in items)
        who, _ = _gears_part([g for m in items for g in m.gear_ids], len(items))
        does = (f"{subject} makes {who} new, as {_and(_stem(m.new) for m in items)}, rather than reuse "
                f"{_them(len(items))}.")
        if why == UNSAVED and after_unsaved_line:
            whose = f"{olds}'s changes are" if one else f"the changes in {olds} are"
            out.append(f"While {whose} not saved, {does}")
        elif why == UNSAVED:
            out.append(f"{olds} {'has' if one else 'have'} changes from Update SolidWorks that are not saved, so "
                       f"{does}")
        else:
            out.append(f"{olds} {'does' if one else 'do'} not hold what the record says, as the last job in "
                       f"SolidWorks found, so {does}")
    return " ".join(out)


def _copy_sentence(plan) -> str:
    """A copied workbook (``GearboxPlan.foreign_record``, review S1): the record that came with it, and the files it
    lists, are the other workbook's; Build makes this one's own beside them. A record whose workbook is gone, and
    nobody has said whether this one was moved from it (``plan.foreign_gone``, second review N1c), is said as
    such: the window is asking. One whose workbook is gone and which the person said this one is a copy of
    (``plan.foreign_said``, third review) is said so — never "still there" — with the way to take the answer back:
    it holds for the session only, so until this workbook has built its own gearbox, a new session asks again."""
    other = plan.foreign_record
    if getattr(plan, "foreign_said", False):
        return (f"The record that came with this workbook was written for {short_path(other, 48)}, which you said "
                "this workbook is a copy of, so that record, and the SolidWorks files it lists, are that workbook's: "
                "Build makes this workbook's own gearbox beside them, sharing and overwriting nothing. If this "
                "workbook was in fact moved or renamed from it, quit Gear Generator and open this workbook again "
                "before you build, and you are asked again.")
    if getattr(plan, "foreign_gone", False):
        return (f"The record that came with this workbook was written for {short_path(other, 48)}, which is not there "
                "any more: until you say whether this workbook was moved or renamed from it, Build makes this "
                "workbook's own gearbox beside the files it lists, sharing and overwriting nothing.")
    return (f"This workbook is a copy of {short_path(other, 48)}, which is still there, so the record that came with "
            "it is that workbook's, and so are the SolidWorks files it lists: Build makes this workbook's own gearbox "
            "beside them, sharing and overwriting nothing.")


def build_again_question(update, again) -> str:
    """The *Build again?* question (``UpdatePlan``, and the ``GearboxPlan`` it would run): why Update cannot carry
    the change, what the new revision makes and reuses — and why a part is made new although one was built — and,
    decision 8, that the reused parts are shared, so a later Update changes the earlier revision's assembly too.
    Never promises the old assembly is untouched, and never names one when none was built (a record from Build
    parts)."""
    from .workbook.gearbox import MISMATCHED, UNSAVED
    reasons = []
    if update is not None and update.missing:
        reasons.append(_missing_sentence(update.missing))
    if update is not None:
        reasons.extend(_reason(s) for s in update.structural)
    if not reasons:
        reasons.append("Nothing on record needs a new revision.")
    text = " ".join(reasons) + f" Build again as {again.name}?"
    if again.refusal:
        return f"{text} It cannot go ahead: {again.refusal}"

    does = []
    if again.build:
        news = [f"{', '.join(job.gear_ids)} ({job.stem})" for job in again.build]
        does.append(f"makes {'a new part' if len(news) == 1 else 'new parts'} for {_and(news)}")
    kept = len(again.reuse)
    if kept:
        does.append(f"reuses {_plural(kept, 'part')} that {'has' if kept == 1 else 'have'} not changed")
    asm = _file(again.assembly_path) if again.assembly_path else ""
    if _layout_reused(again):
        does.append(f"reuses {_stem(again.layout.path)} and makes a new assembly, {asm}")
    elif again.layout is not None:
        does.append(f"makes a new layout part and assembly ({_stem(again.layout_path)} and {asm})")
    if does:
        text += " That " + _and(does) + "."
    for why, because, after in ((UNSAVED, "has changes from Update SolidWorks that are not saved", True),
                                (MISMATCHED, "does not hold what the record says, as the last job in SolidWorks "
                                             "found", False)):
        items = _made_new_by(again, why)
        if not items:
            continue
        one = len(items) == 1
        who, be = _gears_part([g for m in items for g in m.gear_ids], len(items))
        olds = _and(_stem(m.old) for m in items)
        said = because if one else because.replace("has", "have", 1).replace("does", "do", 1)
        text += f" {who[:1].upper()}{who[1:]} {be} new because {olds} {said}"
        # The save it asks for may no longer be possible (SolidWorks closed since): said so, true either way (N2).
        them = _them(len(items))
        text += (f"; to reuse {them} instead, answer No and save {them} in SolidWorks first (if SolidWorks has "
                 f"closed {them} since without saving, those changes are gone, and {them} cannot be reused)."
                 if after else ".")
    occupied = _occupied(again, overwritten=False,
                         superseded=[p.path for p in update.parts] if update is not None else ())
    if occupied:
        text += " " + occupied

    old = _file(update.assembly) if update is not None and update.assembly else ""
    if not old:
        text += " Nothing is overwritten, and what is already built is left as it is."
    elif kept:
        one = kept == 1
        text += (f" Nothing is overwritten, and {old} stays as it is on disk, but it shares the "
                 f"{'reused part' if one else f'{kept} reused parts'}: a later Update SolidWorks that changes "
                 f"{'it' if one else 'one of them'} changes {old} too.")
    else:
        text += f" Nothing is overwritten, and {old} and its files are left as they are."
    return text


def _without_folder(assessment):
    """The assessment as if an output folder were set: Update SolidWorks writes nothing there, so a folder unset
    or gone must not hold it back (review nit)."""
    if assessment.folder:
        return assessment
    import dataclasses
    return dataclasses.replace(assessment, folder="-")


def _ready_build(assessment, plan, folder: str, superseded: Sequence[str] = ()) -> Tuple[str, bool]:
    """*Ready: Build makes 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM in C:\\Parts\\Reducer_12to1.*,
    reusing what is built; why the revision is not 0; why a new part takes another name (:func:`_occupied`); and,
    for a copied workbook, whose the files beside it are (:func:`_copy_sentence`)."""
    where = short_path((plan.folder if plan is not None and plan.folder else folder), 48)
    if plan is None:
        return (f"Ready: Build makes {_plural(len(assessment.parts.jobs), 'part')}, the layout part and the "
                f"assembly in {where}."), True
    made = [_plural(len(plan.build), "part")] if plan.build else []
    reused = []
    if _layout_reused(plan):
        reused.append(_stem(plan.layout.path))
    elif plan.layout is not None:
        made.append(_stem(plan.layout_path))
    if plan.assembly is not None:
        made.append(_file(plan.assembly_path))
    if plan.reuse:
        reused.append(_already(len(plan.reuse)))
    text = f"Ready: Build makes {_and(made)} in {where}" + (", reusing " + _and(reused) if reused else "") + "."
    copied = bool(getattr(plan, "foreign_record", ""))
    if plan.revision_reason and not copied:
        text += " " + _sentence(plan.revision_reason)
    occupied = _occupied(plan, superseded=superseded)
    if occupied:
        text += " " + occupied
    if copied:
        text += " " + _copy_sentence(plan)
    return text, bool(made)


def _waiting_rows(parts) -> str:
    refused = parts.refused
    more = f" ({len(refused) - 1} more under Checks)" if len(refused) > 1 else ""
    return f"the layout and assembly wait for a later phase: {refused[0].message}{more}" if refused else ""


def _ready_parts(assessment, plan, folder: str, superseded: Sequence[str] = ()) -> Tuple[str, bool]:
    """*Ready: Build parts makes 2 parts in …; the layout and assembly wait for a later phase: Shafts!A4: …* (W2's
    batch, through the same reuse as Build, decision 9)."""
    where = short_path((plan.folder if plan is not None and plan.folder else folder), 48)
    new = len(plan.build) if plan is not None else len(assessment.parts.jobs)
    kept = len(plan.reuse) if plan is not None else 0
    waits = _waiting_rows(assessment.parts)
    if not new:
        return (f"The {_plural(kept, 'part')} {'is' if kept == 1 else 'are'} built already, so Build parts has "
                f"nothing to make; {waits}"), True
    text = f"Ready: Build parts makes {_plural(new, 'part')} in {where}"
    if kept:
        text += f", reusing {_already(kept)}"
    text += f"; {waits}" if waits else "."
    occupied = _occupied(plan, superseded=superseded) if plan is not None else ""
    if occupied:
        text += " " + occupied
    if plan is not None and getattr(plan, "foreign_record", ""):
        text += " " + _copy_sentence(plan)
    return text, True


def _unsaved_line(paths: Sequence[str], update_puts_back: bool = False) -> str:
    """The save asked for once, naming every document of the current revision Update changed and that is not
    saved: parts first, the assembly last, as Update changed them. Nothing here can know whether SolidWorks has
    them open still, so the sentence is true either way (second review N2): if SolidWorks closed them without
    saving, the changes are gone — and, where Update SolidWorks would carry the workbook again
    (``update_puts_back``), pressing it makes them again. A job that finds them closed takes the mark off."""
    paths = sorted(paths, key=lambda p: str(p).lower().endswith(".sldasm"))
    one = len(paths) == 1
    them = _them(len(paths))
    then = (" press Update SolidWorks to make them again." if update_puts_back else " those changes are gone.")
    return (f"{_and(_stem(p) for p in paths)} {'has' if one else 'have'} changes from Update SolidWorks that are not "
            f"saved: save {them} in SolidWorks to keep {them}. If SolidWorks closed {them} without saving,{then}")


def workbook_footer(assessment, *, record=None, record_problem: str = "", plan=None, update=None,
                    error: str = "", folder: str = "", folder_exists: bool = True, building: bool = False,
                    updating: bool = False, progress=None, note=None, results_due: bool = False,
                    digest: str = "") -> Footer:
    """The footer for every state of the window (design/UI-DESIGN.md §9's table): its sentence, colour, buttons.

    ``assessment`` is the last good read's ``workbook.assess.Assessment``
    (assessed with ``provisional=`` the window's recalc, and its chosen
    fixes), or None when there is none. ``record`` is the planning read of the
    link record (``store.read_link_record``) when it is this workbook's (None
    for a copy's: ``plan.foreign_record`` says so), ``record_problem`` the
    sentence if that read raised (a newer or broken record). ``plan`` is the
    ``workbook.gearbox.GearboxPlan`` the build button would run (None while
    the gate refuses) and ``update`` the ``workbook.update.UpdatePlan`` from
    ``classify`` (None with nothing on record). ``building``/``updating``: a
    worker job is running, and ``progress`` its last ``swbuild.Step``.
    ``note``: the window's last sentence of its own, a :class:`Note` (a plain
    ``(text, ok)`` is a job's). Order of the gate: the window's own state
    (error, a job running, the folder missing on disk, the record problem),
    then ``assessment.lay_out_refusal()`` — falling back to Build parts when
    only ``parts.refused`` holds the layout back and ``build_refusal()``
    passes — then ``plan.refusal``.

    The build button's action follows the record and the read, not the
    moment: Build again… once an assembly is on record, else Build parts
    while rows a later phase builds are there, else Build. A newer record
    (its sentence ends ``store.LINK_WAITS``) holds both buttons back; a
    broken one only Update. Update SolidWorks is gated as Build is, but never
    on the output folder, since it writes nothing there; it stays enabled
    when the record says nothing differs (the worker compares live), and
    when the change needs a new revision once an assembly is built (the press
    asks, then builds again) — but not when that build cannot go, nor before
    an assembly is built, when Build itself makes what is needed.

    Every sentence is decided from fields, never from another sentence's
    words: a greyed button always has its reason on screen, no sentence offers
    a greyed button, the save of what Update left unsaved is asked for once
    (:func:`_unsaved_line`), and the parts a build makes new rather than reuse
    are said from ``plan.made_new`` (:func:`_occupied`, :func:`_held_back`).
    The note joins as its kind says (:class:`Note`).

    W5 (Agent C; W5-INTERFACES.md): ``digest`` is the sha256 of the read the
    window shows (``Reading.digest``; the window passes it, Agent D). While
    the record's gearbox has no assembly and its ``mate_problems`` came from
    this same read (``mate_problems_digest == digest``), Build is not
    enabled and the sentence says SolidWorks refused a mate, naming it, and
    that Build waits for a change to the workbook (W5-DECISIONS, answer 1:
    the footer never invites a retry of an unchanged workbook). ``""``, as
    every W4 caller passes, never matches.
    """
    from .store import LINK_WAITS
    a = assessment
    note = _as_note(note)
    gearbox = getattr(record, "gearbox", None)
    has_assembly = bool(gearbox is not None and gearbox.assembly)
    on_record = record is not None and bool(record.parts or gearbox is not None)
    later = bool(a is not None and a.parts.refused)
    action = BUILD_AGAIN if has_assembly else (BUILD_PARTS if later else BUILD)
    newer = bool(record_problem) and record_problem.rstrip().endswith(LINK_WAITS)

    def footer(text: str, ok: bool, build: bool = False, update_on: bool = False) -> Footer:
        return Footer(text, ok, action, BUILD_LABELS[action], build, action != BUILD_AGAIN, on_record,
                      update_on and on_record, has_assembly)

    if building or updating:
        return footer(progress_text(progress, updating=updating), True)
    if error:
        return footer(error, False)
    if a is None:
        return footer(record_problem, not record_problem)
    if note is not None and not note.ok and a.chosen:
        return footer(note.text, False)          # a refused Export must show, even with a fix still chosen
    if a.chosen:
        n = len(a.chosen)
        waits = "Build and Update SolidWorks wait" if on_record else "Build waits"
        return footer(f"{_plural(n, 'fix', 'fixes')} chosen: Export writes {'it' if n == 1 else 'them'} into the "
                      f"workbook, and {waits} for that, so the workbook and SolidWorks agree.", True)
    if a.provisional:
        lead = f"{note.text} " if note is not None else ""
        return footer(lead + (RECALC_WAIT_UPDATE if on_record else RECALC_WAIT), True)

    due = RESULTS_DUE if results_due else ""
    if newer:
        text = _after_note(note, record_problem) if note is not None else record_problem
        return footer(text + due, False)

    where = folder or a.folder
    missing_folder = (f"The output folder {short_path(where, 48)} does not exist; make it, or change it on the Box "
                      "sheet.")
    gate = a.build_refusal() if action == BUILD_PARTS else a.lay_out_refusal()
    build_block = gate or ("" if folder_exists else missing_folder) or (plan.refusal if plan is not None else "")
    loose = _without_folder(a)
    update_gate = loose.lay_out_refusal() if gearbox is not None else loose.build_refusal()
    update_on = on_record and not update_gate and update is not None and not update.refusal
    if update is not None:
        unsaved = list(update.unsaved)
    elif record is not None:
        unsaved = list(record.current_marks(record.unsaved))
    else:
        unsaved = []
    superseded = [p.path for p in record.parts] if record is not None else []

    held = ""              # why Build again… or Update SolidWorks is greyed, when the sentence does not say it
    subject = ""           # who makes the plan's parts new, when this state offers the plan's build
    if action == BUILD_AGAIN:
        build_on = not build_block
        if update_gate:
            text, ok = update_gate, False
        elif update is None:
            text, ok, held = f"{_file(gearbox.assembly)} is built from this workbook.", True, build_block
        elif update.refusal:
            text, ok, held = update.refusal, False, build_block
        elif update.needs_new_revision and build_block:
            # Update would ask, then build again, and that build cannot go: say why, and offer neither.
            name = f", {plan.name}," if plan is not None and plan.name else ""
            text, ok, update_on = (f"{_cannot_carry(update)} The new revision it needs{name} cannot be built yet: "
                                   f"{build_block}"), False, False
        elif update.needs_new_revision:
            text, ok = _again_sentence(update, plan.name if plan is not None else ""), not update.missing
            occupied = _occupied(plan, superseded=superseded) if plan is not None else ""
            if occupied:
                text += " " + occupied
            subject = "the new revision"
        else:
            text, ok, held = update_summary(update), True, build_block
    else:
        if build_block:
            text, ok, build_on = build_block, False, False
        elif action == BUILD_PARTS:
            text, ok = _ready_parts(a, plan, where, superseded)
            build_on = plan is None or bool(plan.build)
            subject = "Build parts"
        else:
            text, ok = _ready_build(a, plan, where, superseded)
            build_on = ok
            subject = "Build"
        if on_record and update is not None and not update.refusal and update.needs_new_revision:
            # Nothing is assembled yet (a record from Build parts): Build makes what is needed, and Update would
            # otherwise offer a build-again of an assembly that was never built (W4 review S4.4).
            update_on = False
            held = f"{_cannot_carry(update)} Update SolidWorks waits until Build has made what that needs."
        elif on_record and update is not None and update.refusal:
            held = update.refusal              # Update shown but greyed: its reason, whatever shows (S4.5)

    if record_problem:                            # a broken record: Build goes ahead and sets it aside
        text, ok = f"{text} {record_problem}", False
    puts_back = bool(update_on and update is not None and not update.needs_new_revision)
    if note is None or note.kind == NOTE_ANSWER:
        # The state's own lines — the save asked for, the parts made new — follow an answer too (after "No" to
        # Build again? the reason it answered is kept, and these with it).
        if unsaved:
            text += " " + _unsaved_line(unsaved, puts_back)
        if subject and plan is not None and not plan.refusal:
            back = _held_back(plan, subject, after_unsaved_line=bool(unsaved))
            if back:
                text += " " + back
    if note is not None:
        if note.kind == NOTE_ANSWER:
            text, ok = f"{note.text} {text}", ok and note.ok
        elif ok:
            text, ok = note.text + _left_for_later(a.parts), note.ok
        else:
            text = _after_note(note, text)
    if held:
        text += " " + held
    return footer(text + due, ok, build_on, update_on)


# -- W4: what the Workbook window itself says around a job (the window wiring) ----------------------------------
#
# The footer's sentence is :func:`workbook_footer`'s and a finished job's is :func:`gearbox_status` or
# :func:`gearbox_update_status`; these are the few things only the window knows to say: a job that could not
# start, a record it could not write, the question's title and its "No", and the header's word on the record.

BUILD_AGAIN_TITLE = "Build again?"
NOTHING_CHANGED = "Nothing was changed in SolidWorks."
ASKED_TOO_LATE = ("The workbook changed while the question was open, so nothing was built; press Build again… once "
                  "more if it still applies.")


def _after_note(note: Note, text: str) -> str:
    """A note, then a state that is not fine: *Built 4 parts. Since then: Fix the workbook …* after a job, which
    marks a moment the workbook may have moved on from; plainly joined after anything else, which marks none —
    *Exported 1 cell and the Results sheet. Fix the workbook before building: …* — since what follows was already
    so."""
    if note.kind != NOTE_JOB:
        return f"{note.text} {text}"
    return f"{note.text} Since then: {text}"


def workbook_built_tag(record, digest: str) -> str:
    """The header's word on the record beside the workbook: `` · built from this version`` or `` · changed since
    it was built`` once a layout part or assembly is on record (``record.digest`` is the read SolidWorks was last
    built or updated from), `` · parts built from this version`` / `` · changed since its parts were built`` for
    W2's parts alone, and ``""`` with nothing on record. While documents of the current revision Update changed
    are not saved (``record.unsaved``) this version is in SolidWorks only: `` · updated from this version, not
    yet saved`` (W4 review S4.7); an earlier revision's are not counted (second review N2). While a document of
    the current revision is marked mismatched (a check found it not holding what the record says, or a job found
    Update's changes in it lost) it is `` · SolidWorks no longer holds all of this version``."""
    if record is None or not (record.parts or record.gearbox is not None):
        return ""
    same = bool(digest) and record.digest == digest
    unsaved = bool(record.current_marks(record.unsaved))
    if same and record.current_marks(record.mismatched):
        return " · SolidWorks no longer holds all of this version"
    if record.gearbox is None:
        if same:
            return (" · parts updated from this version, not yet saved" if unsaved
                    else " · parts built from this version")
        return " · changed since its parts were built"
    if same:
        return " · updated from this version, not yet saved" if unsaved else " · built from this version"
    return " · changed since it was built"


def job_unreachable(reason: str, updating: bool = False) -> str:
    """*SolidWorks cannot be reached from here, so nothing was built.* and why (``swcom.unavailable_reason``)."""
    done = "updated" if updating else "built"
    return f"SolidWorks cannot be reached from here, so nothing was {done}. {reason}".strip()


def unowned_job_busy(updating: bool = False) -> str:
    """A job whose window was closed anyway (``close_anyway_question``) is still running in SolidWorks: no window
    will collect it, and a new build or update must not overtake it (third W4 review)."""
    then = "press Update SolidWorks" if updating else "build"
    return (f"A job from a Workbook window that was closed while SolidWorks had not answered is still running in "
            f"SolidWorks; {then} when it has finished.")


def strip_busy(updating: bool = False) -> str:
    """The strip has a build of its own in SolidWorks (they share one worker)."""
    then = "press Update SolidWorks" if updating else "build the workbook"
    return f"The strip is building in SolidWorks; {then} when it has finished."


def job_failed(error: BaseException, updating: bool = False) -> str:
    """A job the worker answered with a raise.

    Since the W4 review that is a refusal before anything was made or
    changed: ``build_gearbox`` and ``update_gearbox`` turn whatever goes wrong
    after their own checks into failures on the result they return. So it is
    one of those checks — the paths, a document of the same name open from
    another folder, the plans, a document to reuse or update that cannot be
    opened or read, and Update's check phase (a global, feature or component
    gone; new values that do not evaluate) — or the connection to SolidWorks
    failing before the job began. One thing short of a change is done first:
    when an Update's new values evaluate in one trig unit only, that
    document's units are measured, which leaves it marked modified in
    SolidWorks although no value in it changed. A live check that finds a
    document to reuse not holding what it should is not a raise any more
    (``GearboxResult.mismatched``).

    A SolidWorks refusal is said as it came; anything else is named. A
    document Update found not as it was built (``swbuild.NotAsBuilt``: a
    component, feature or global renamed or deleted in SolidWorks) gets the
    way on, since Update cannot put it back (W4 review S4.6)."""
    from .swbuild import NotAsBuilt
    from .swcom import SolidWorksError
    if isinstance(error, SolidWorksError):
        text = str(error)
        if updating and isinstance(error, NotAsBuilt):
            text = (f"{_sentence(text)} Update SolidWorks cannot put that back; Build again… builds the next revision "
                    "beside it, with an assembly of its own, and leaves this one as it is.")
        return text
    what = "Update SolidWorks stopped before it changed anything" if updating else \
        "The build stopped before it made anything"
    return f"{what} — {type(error).__name__}: {error}"


def planning_failed(error: BaseException) -> str:
    """Planning a build or an update raised, which it should never do: say so rather than offer the button."""
    return (f"What to build could not be worked out — {type(error).__name__}: {error}. Nothing is built or updated "
            "until it can be.")


def sidecar_unwritten(path: str, error: BaseException) -> str:
    """A part saved, but its ``.gear.json`` could not be written beside it."""
    return f"The part's record {_file(path)} could not be written beside it: {error}."


def record_unwritten(path: str, error: BaseException) -> str:
    """The ``.workbook.json`` could not be written (the disk refused): the files SolidWorks saved stay."""
    return (f"The record of what was built, {_file(path)}, could not be written: {error}. What SolidWorks saved "
            "stays on disk, and the next Build goes beside it rather than over it.")


FIX_SET_ASIDE = ("The workbook changed, so the fix you chose no longer applies as it was and was set aside; choose "
                 "again from Checks.")


def record_not_carried(why: str) -> str:
    """Locate…: the record beside the workbook's old place could not be carried to its new one."""
    return f"The record of what was built stays beside the workbook's old place: {_sentence(why)}"


def export_busy(updating: bool = False) -> str:
    """Why Export waits while a job runs (follows *Nothing was exported:*)."""
    if updating:
        return "Update SolidWorks is running; export when it has finished."
    return "a build is running in SolidWorks; export when it has finished."


def closes_when_done(updating: bool = False) -> str:
    """The window was closed while a job runs: it stays until what the job saved is on record."""
    job = "the update" if updating else "the build"
    return (f"This window closes once {job} has finished and what it saved is on record; it stays open if "
            "something needs saying.")


def collect_failed(error: BaseException, updating: bool = False) -> str:
    """A finished job whose answer the window could not take in."""
    what = "update" if updating else "build"
    return f"The {what} could not be collected — {type(error).__name__}: {error}"


def finish_failed(error: BaseException, updating: bool = False, journaled: bool = False,
                  changed: bool = True) -> str:
    """Working out what a finished job leaves on record raised (W4 review B1, the window's half), so nothing of the
    record was written. A build whose journal was written before it began (``journaled``, second review N4) still
    has it on record: the next Build reuses what SolidWorks saved, once checked. Update saves nothing: what it
    changed is in SolidWorks only, and not marked unsaved — unless it changed nothing (``changed`` False, third
    review), when nothing is said to be in SolidWorks."""
    lead = f"What the {'update changed' if updating else 'build saved'} could not all be put on record — " \
           f"{type(error).__name__}: {error}."
    if updating and not changed:
        return (f"What the update found could not all be put on record — {type(error).__name__}: {error}. It "
                "changed nothing in SolidWorks.")
    if updating:
        return f"{lead} Its changes are in SolidWorks, not saved: save them there to keep them."
    if journaled:
        return (f"{lead} What SolidWorks saved stays on disk, and the next Build finds it from the journal written "
                "before the build, checks it in SolidWorks and reuses what it can.")
    return f"{lead} What SolidWorks saved stays on disk, and the next Build goes beside it rather than over it."


def app_closes_when_done(count: int = 1, strip: bool = False) -> str:
    """The strip's window was closed while Workbook windows (``count``) or the strip itself (``strip``) have jobs in
    SolidWorks: the app stays until they have finished and been collected (the worker thread would die with it,
    and nothing would reach the record). Closing it again offers to quit anyway (:func:`quit_anyway_question`).

    Only a Workbook window stays open to show what its job said (``CloseGuard.check``); the strip is not waited
    on for that — once its job is collected the app quits, whatever it said — and the strip's job may be a build
    or an update of a part's values, so it is called a job, collected, not a build whose saved files are on record
    (third W4 review)."""
    said = []
    if count:
        jobs = "a workbook's job" if count == 1 else f"{count} workbooks' jobs"
        said.append(f"{jobs} in SolidWorks {'has' if count == 1 else 'have'} finished and "
                    f"what {'it' if count == 1 else 'they'} did is on record")
    if strip:
        said.append("the strip's job in SolidWorks has finished and the strip has collected it")
    text = "Gear Generator closes once " + ", and once ".join(said)
    if count:
        text += "; it stays open if a Workbook window has something to say"
    return text + "."


APP_CLOSES_AFTER_QUESTION = "Gear Generator closes once the question open in a Workbook window is answered."

QUIT_ANYWAY_TITLE = "Quit anyway?"
CLOSE_ANYWAY_TITLE = "Close anyway?"


def quit_anyway_question(workbook_build: bool = False) -> str:
    """Asked (default No) when the strip's window is closed a second time while a job in SolidWorks has not
    answered — SolidWorks may be held by a dialog, and nothing can stop a call it does not answer (second W4
    review N4.3). What it says is what holds: nothing those jobs save or change is put on record by this session
    (not only what they do from now: their finishes never run), and no file is overwritten (a build never
    overwrites one). ``workbook_build``: a workbook's build is among the jobs; its journal covers the files a
    build saves — written before it began unless the record could not be written, which is said as such — and
    never an update's changes (third review)."""
    text = ("SolidWorks has not answered yet: a job is still running there, perhaps held up by a dialog open in "
            "SolidWorks. Quit anyway? Nothing that job saves or changes is put on record by this session, and nothing "
            "will be overwritten.")
    if workbook_build:
        text += (" A workbook's build lists what it is about to make in that workbook's record before it begins, "
                 "unless the record cannot be written, so the workbook's next Build finds the files it saved, checks "
                 "them in SolidWorks and reuses what it can.")
    return text


def close_anyway_question(updating: bool = False, journaled: bool = False) -> str:
    """The Workbook window's own close, a second time while its job has not answered (second W4 review N4.3).
    Nothing the job saves or changes is put on record by this window — not only what it does from now: its finish
    never runs. The build's journal (``journaled``: written before it began) lets the next Build find what it
    saved; without one, the next Build goes beside those files. An update has no journal: what it changes is in
    SolidWorks only (third review)."""
    if updating:
        return ("SolidWorks has not answered yet: Update SolidWorks is still running there, perhaps held up by a "
                "dialog open in SolidWorks. Close this window anyway? Nothing the update changes is put on record by "
                "this window, so it will not ask for those documents to be saved, and nothing will be overwritten.")
    then = ("the build listed what it is about to make in the record before it began, so the next Build finds those "
            "files, checks them in SolidWorks and reuses what it can." if journaled else
            "what the build was about to make could not be listed in the record before it began, so the next Build "
            "goes beside the files it saves rather than over them.")
    return ("SolidWorks has not answered yet: the build is still running there, perhaps held up by a dialog open in "
            "SolidWorks. Close this window anyway? Nothing the build saves is put on record by this window, and "
            f"nothing will be overwritten: {then}")


MOVED_TITLE = "Moved, or a copy?"


def moved_question(workbook: str, other: str) -> str:
    """Asked once (default No) when the record beside a workbook was written for another that is not there any more
    (``store.UNSURE``, second W4 review N1c): moved or renamed — the record is this workbook's — or a copy of an
    original since deleted, renamed or gone offline, whose files are not this workbook's. Yes is kept in the record;
    No holds for the session, and is asked again in a new one until this workbook has built its own gearbox (third
    review). A drive not connected now is named, and No is the safe answer then."""
    return (f"The record of what was built beside this workbook was written for {short_path(other, 60)}, which is not "
            "there any more. Was this workbook moved or renamed from it? Yes: the record is this workbook's, and "
            "Update SolidWorks and Build carry on from what it lists; the answer is kept in the record. No: this "
            "workbook is a copy, so Build makes its own gearbox beside those files, sharing and overwriting nothing; "
            "until it has, you are asked again the next time Gear Generator opens this workbook. If that workbook "
            "may be on a drive that is not connected now, answer No: nothing is shared or overwritten.")


def answer_not_kept(error: BaseException) -> str:
    """The move-or-copy answer could not be written into the record: this session keeps it."""
    return (f"Your answer holds until Gear Generator closes, but it could not be kept in the record of what was "
            f"built: {error}.")


APP_STAYED_OPEN = ("Gear Generator stayed open: a workbook's job has something to say in its window. Close this window "
                   "again to quit.")


# -- W5: the gearbox that turns (docs/notes-workbook/W5-PLAN.md §1.8, as W5-INTERFACES.md amends it) ---------------
#
# Interfaces pinned in the W5 interface commit; Agent C writes each, and calls them from the functions above that
# already exist (``_ready_build``, ``gearbox_status``, ``workbook_footer``, ``build_again_question``,
# ``update_summary``, ``gearbox_update_status``), whose signatures stay as they are (``workbook_footer`` gained
# ``digest``). Every sentence is decided from fields, never from another sentence's words, and is true in every
# state; a mate problem (``BuildResult.mate_problems``, ``GearboxRecord.mate_problems``) is a whole sentence of the
# worker's and is shown as one, never lower-cased or cut into another sentence. There is no static fallback, so no
# sentence about one (W5-DECISIONS, answer 1).


def drag_phrase(drag: Sequence[str]) -> str:
    """The gear(s) to drag, from ``MotionPlan.drag`` / ``GearboxRecord.drag`` (one per train): *drag G1 in
    SolidWorks and the rest of its train follow* for one train (review M11: "of its train", since a lone gear or a
    fixed one does not follow), *drag G1 to turn one train and G5 to turn the other* for two, *drag G1, G5 and G9,
    one for each train* for three or more; ``""`` for none."""
    raise NotImplementedError("W5: Agent C, ui_text.drag_phrase")


def motion_ready_line(plan) -> str:
    """Appended to the sentence before Build (``_ready_build``) from a ``workbook.gearbox.GearboxPlan``: with
    ``plan.motion``, *Its gears are mated to their shafts and to each other, so they turn together in
    SolidWorks.*; with ``plan.static_reason``, *Its gears are placed meshed and fixed, not mated to turn:
    {static_reason}*; ``""`` for a parts-only or refused plan."""
    raise NotImplementedError("W5: Agent C, ui_text.motion_ready_line")


def motion_done_line(plan, result) -> str:
    """After a build whose assembly saved (``swbuild.GearboxResult.kind``): for ``motion.MOTION``, that the gears
    are mated to turn and SolidWorks reports no mate in error, with :func:`drag_phrase` of ``plan.motion.drag``
    (no train: *Its gears are each mated to their shaft, free to turn, …*); for ``motion.STATIC`` with
    ``plan.static_reason``, that they are placed fixed and why; ``""`` otherwise (W4's static build says nothing
    new)."""
    raise NotImplementedError("W5: Agent C, ui_text.motion_done_line")


def mate_refused_status(plan, result, again: bool = False) -> Tuple[str, bool]:
    """A build whose assembly SolidWorks refused or flagged a mate of (``result.assembly.mate_problems``, the
    assembly not saved and nothing saved in its place): what was built and kept (the parts, the layout part),
    each mate problem as the worker's sentence, that the assembly is left open in SolidWorks as
    ``result.assembly.document``, not saved, its parts the saved ones, and that Build makes the assembly once the
    workbook has changed; never an invitation to press again unchanged. ``ok`` is False. ``again`` as
    :func:`gearbox_status`'s."""
    raise NotImplementedError("W5: Agent C, ui_text.mate_refused_status")


def motion_record_line(record, digest: str = "") -> str:
    """The footer's line on a gearbox on record (``store.LinkRecord``), appended in the Build again… states whose
    sentence is not an error, and in Build's state after a refusal: ``kind`` ``motion`` — *It was built with its
    gears mated to turn: drag G1 in SolidWorks to turn the gearbox.* (``drag``; two trains: *… drag G1 or G5 to
    turn its trains.*); ``static`` with no ``static_reason`` (W4's) — *It was built static, before gears could be
    mated to turn: Build again… makes a new revision whose gears turn.*; ``static`` with a ``static_reason`` —
    built static because that was not settled, and Build again… tries a turning revision; no assembly and
    ``mate_problems`` — the refusal, and, when ``mate_problems_digest == digest``, that Build waits for a change
    to the workbook. ``""`` with no gearbox."""
    raise NotImplementedError("W5: Agent C, ui_text.motion_record_line")


def motion_update_lines(update, result) -> List[str]:
    """The W5 pieces of a finished update's sentence (``UpdatePlan``, ``swbuild.GearboxUpdate`` of the motion
    path), in order, each a whole sentence: *Moved G4 along S3.* (``result.axial``, the shaft from the ALONG mate
    in ``update.motion.mates``), *Set the gear mate G1 meshes G2 to 17 : 69.* (``result.ratios``), *Turned the
    mate G1 meshes G2 back on (it was suppressed in SolidWorks).* (``result.unsuppressed``), *The gears had been
    turned in SolidWorks; they are back at the turn they were built at.* (``result.restored``), *G4 had been turned
    out of step with G3 in SolidWorks; it is back in mesh.* (``result.out_of_step``), *Reducer_12to1.SLDASM also
    has mates the app did not make (Angle1), suppressed; Update SolidWorks left them as they are.*
    (``result.extra_mates``); and, with nothing changed and ``result.turned``, *The gears stand where they were
    turned in SolidWorks.* after ``ALREADY_MATCHES``. ``[]`` for W4's static path."""
    raise NotImplementedError("W5: Agent C, ui_text.motion_update_lines")
