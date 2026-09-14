"""The form as data.

Every field of the form is kept as the text the user typed, because ``""``
means something different from ``"0"`` — a blank backlash is the
``0.3 × Module`` equation, while ``"0"`` is no backlash at all — and because a
number that round-trips through ``float`` comes back as ``25.0`` when the user
typed ``25``. Parsing happens in the methods below, each of which names its
field in the sentence it raises.

Output folder and templates are not here: like the output folder in Airfoil
Converter they are app state, remembered across runs, not a property of a gear.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Optional, Tuple


KIND_SPUR = "spur"
RECIPE_INVOLUTE = "A"
RECIPE_ARCS = "B"
RECIPES = (RECIPE_INVOLUTE, RECIPE_ARCS)

MODE_SINGLE = "single"
MODE_PAIR = "pair"
MODES = (MODE_SINGLE, MODE_PAIR)


class InputError(Exception):
    """A field on the form could not be read."""


def parse_float(text: str, name: str) -> float:
    stripped = str(text).strip()
    if not stripped:
        raise InputError(f"{name} is empty; it needs a number.")
    try:
        value = float(stripped)
    except ValueError:
        raise InputError(f"{name} must be a number (got {stripped!r}).") from None
    if not math.isfinite(value):
        raise InputError(f"{name} must be a finite number (got {stripped!r}).")
    return value


def parse_whole(text: str, name: str) -> int:
    value = parse_float(text, name)
    if abs(value - round(value)) > 1e-9:
        raise InputError(f"{name} must be a whole number (got {str(text).strip()!r}).")
    return int(round(value))


def parse_ratio(text: str) -> float:
    """``"3"``, ``"3:1"``, ``"1:3"``, ``"0.333"`` -> N driven / N driver.

    ``a:b`` reads as a over b, so ``3:1`` is 3 and ``1:3`` is a third — the
    driven gear the smaller one.
    """
    stripped = str(text).strip()
    if not stripped:
        raise InputError("Ratio is empty; type it as 3, or as 1:3.")
    if ":" in stripped:
        left, _, right = stripped.partition(":")
        a = parse_float(left, "Ratio")
        b = parse_float(right, "Ratio")
        if a <= 0 or b <= 0:
            raise InputError(f"Both sides of the ratio must be more than zero (got {stripped!r}).")
        return a / b
    value = parse_float(stripped, "Ratio")
    if value <= 0:
        raise InputError(f"Ratio must be more than zero (got {stripped!r}).")
    return value


def sanitize_stem(stem: str, fallback: str = "Gear") -> str:
    """A name reduced to something legal as a file name and a feature name."""
    cleaned = re.sub(r'[<>:"/\\|?*@]', "_", str(stem)).strip().strip(".")
    return cleaned or fallback


def _number_text(text: str) -> str:
    """A typed number as it goes into a file name: ``1.50`` -> ``1.5``.

    Kept free of :mod:`gears` so the gear kinds can import this module.
    """
    try:
        value = float(str(text).strip())
    except ValueError:
        return str(text).strip()
    if not math.isfinite(value):
        return str(text).strip()
    text = f"{value:.9f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


@dataclass(frozen=True)
class GearSpec:
    """Every setting of one gear, as typed."""

    kind: str = KIND_SPUR
    recipe: str = ""              # "" = findings.DEFAULT_RECIPE
    module: str = "1.5"
    teeth: str = "25"
    pressure_angle: str = "20"
    face_width: str = "10"
    bore: str = "10"              # "" = no bore feature
    backlash: str = ""            # "" = the 0.3 × Module equation; typed = a literal
    fillet: str = ""              # "" = the 0.38 × Module equation; typed = a literal
    profile_shift: str = "0"      # reserved; must be 0 in v1
    name: str = ""                # "" = default_stem()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "GearSpec":
        known = {f.name for f in fields(cls)}
        return cls(**{k: str(v) for k, v in (raw or {}).items() if k in known})

    # -- reading the fields ------------------------------------------------

    def module_mm(self) -> float:
        return parse_float(self.module, "Module")

    def teeth_count(self) -> int:
        return parse_whole(self.teeth, "No. of teeth")

    def pressure_angle_deg(self) -> float:
        return parse_float(self.pressure_angle, "Pressure angle")

    def face_width_mm(self) -> float:
        return parse_float(self.face_width, "Face width")

    def has_bore(self) -> bool:
        text = self.bore.strip()
        return bool(text) and parse_float(text, "Bore") != 0.0

    def bore_mm(self) -> float:
        """Zero when blank: no bore feature is made, and the global reads 0."""
        text = self.bore.strip()
        return parse_float(text, "Bore") if text else 0.0

    def backlash_mm(self) -> Optional[float]:
        """None when blank, which means the ``0.3 × Module`` equation."""
        text = self.backlash.strip()
        return parse_float(text, "Backlash") if text else None

    def fillet_mm(self) -> Optional[float]:
        """None when blank, which means the ``0.38 × Module`` equation."""
        text = self.fillet.strip()
        return parse_float(text, "Fillet") if text else None

    def profile_shift_value(self) -> float:
        text = self.profile_shift.strip()
        return parse_float(text, "Profile shift") if text else 0.0

    def recipe_or(self, default: str) -> str:
        recipe = self.recipe.strip() or default
        if recipe not in RECIPES:
            raise InputError(f"Recipe must be {' or '.join(RECIPES)} (got {recipe!r}).")
        return recipe

    def default_stem(self) -> str:
        return default_stem(self)

    def stem(self) -> str:
        return sanitize_stem(self.name) if self.name.strip() else self.default_stem()

    def with_values(self, **changes: str) -> "GearSpec":
        values = self.to_dict()
        values.update(changes)
        return GearSpec(**values)


def default_stem(spec: GearSpec, prefix: str = "Gear") -> str:
    """``Gear_m1.5_N25``."""
    return sanitize_stem(f"{prefix}_m{_number_text(spec.module)}_N{_number_text(spec.teeth)}")


@dataclass(frozen=True)
class PairSpec:
    """A gear pair: the solver's inputs and the two gears it fills in."""

    mode: str = MODE_SINGLE
    centre_distance: str = ""
    ratio: str = ""
    module: str = ""              # "" = any module the series allows
    series: str = "1"
    min_teeth: str = "17"
    max_teeth: str = "200"
    gear_a: GearSpec = field(default_factory=GearSpec)
    gear_b: GearSpec = field(default_factory=GearSpec)
    assembly_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["gear_a"] = self.gear_a.to_dict()
        data["gear_b"] = self.gear_b.to_dict()
        return data

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "PairSpec":
        known = {f.name for f in fields(cls)}
        values: Dict[str, Any] = {}
        for key, value in (raw or {}).items():
            if key not in known:
                continue
            if key in ("gear_a", "gear_b"):
                values[key] = GearSpec.from_dict(value if isinstance(value, dict) else {})
            else:
                values[key] = str(value)
        return cls(**values)

    def centre_distance_mm(self) -> float:
        value = parse_float(self.centre_distance, "Centre distance")
        if value <= 0:
            raise InputError(f"Centre distance must be more than zero (got {self.centre_distance.strip()!r}).")
        return value

    def ratio_value(self) -> float:
        return parse_ratio(self.ratio)

    def module_mm(self) -> Optional[float]:
        text = self.module.strip()
        if not text:
            return None
        value = parse_float(text, "Module")
        if value <= 0:
            raise InputError(f"Module must be more than zero (got {text!r}).")
        return value

    def min_teeth_count(self) -> int:
        return parse_whole(self.min_teeth, "Min teeth")

    def max_teeth_count(self) -> int:
        return parse_whole(self.max_teeth, "Max teeth")


def pair_stems(pair: PairSpec) -> Tuple[str, str, str]:
    """``(Pinion_m1.5_N20, Gear_m1.5_N60, Pair_m1.5_20T_60T)``, typed names first.

    The smaller gear is the pinion. On a tie the first is called the pinion,
    so the two files never share a name.
    """
    a, b = pair.gear_a, pair.gear_b
    try:
        a_smaller = a.teeth_count() <= b.teeth_count()
    except InputError:
        a_smaller = True
    stem_a = sanitize_stem(a.name) if a.name.strip() else default_stem(a, "Pinion" if a_smaller else "Gear")
    stem_b = sanitize_stem(b.name) if b.name.strip() else default_stem(b, "Gear" if a_smaller else "Pinion")
    if pair.assembly_name.strip():
        stem_pair = sanitize_stem(pair.assembly_name)
    else:
        stem_pair = sanitize_stem(
            f"Pair_m{_number_text(a.module)}_{_number_text(a.teeth)}T_{_number_text(b.teeth)}T"
        )
    return stem_a, stem_b, stem_pair
