"""The workbook's format as data (docs/PLAN-WORKBOOK.md §1, §3.1).

Every sheet's columns are written down here once: the header, its unit, whether
a row needs it, what a blank means, the words it accepts and their short forms,
and which model field it fills. The reader, the template writer, the drop-down
lists and the window's column help are all generated from these tables, so the
format cannot say one thing in one place and another elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Sequence, Tuple

FORMAT = "1"


@dataclass(frozen=True)
class Column:
    key: str                         # the model field it fills
    header: str                      # without the unit
    unit: str = ""                   # shown in brackets after the header
    required: bool = False
    blank: str = ""                  # what a blank means, for the help text
    words: Tuple[str, ...] = ()      # the accepted values, canonical form first in the drop-down
    aliases: Mapping[str, str] = field(default_factory=dict)   # lower-case alias -> canonical word
    numeric: bool = False
    whole: bool = False
    width: float = 12.0
    help: str = ""

    @property
    def title(self) -> str:
        return f"{self.header} ({self.unit})" if self.unit else self.header

    def canonical(self, text: str) -> Optional[str]:
        """The canonical word for ``text``, or None when it is not one of this column's words."""
        lowered = text.strip().lower()
        for word in self.words:
            if word.lower() == lowered:
                return word
        return self.aliases.get(lowered)


@dataclass(frozen=True)
class SheetDef:
    name: str
    columns: Tuple[Column, ...]

    def column(self, key: str) -> Column:
        for column in self.columns:
            if column.key == key:
                return column
        raise KeyError(key)


def header_key(text: str) -> str:
    """A header as matched: lower case, spaces collapsed, a trailing ``(unit)`` dropped."""
    text = re.sub(r"\s*\([^)]*\)\s*$", "", str(text)).strip().lower()
    return re.sub(r"\s+", " ", text)


NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
FRAME = "frame"

AXES = ("Z+", "Z-", "X+", "X-", "Y+", "Y-")
_AXIS_ALIASES = {}
for _axis in AXES:
    _letter, _sign = _axis[0].lower(), _axis[1]
    _AXIS_ALIASES[_sign + _letter] = _axis              # +z, -z
    _AXIS_ALIASES[("−" if _sign == "-" else _sign) + _letter] = _axis   # −z (U+2212)
    _AXIS_ALIASES[_letter + ("−" if _sign == "-" else _sign)] = _axis   # z− (U+2212)
for _letter in "xyz":
    _AXIS_ALIASES[_letter] = _letter.upper() + "+"

ROLES = ("input", "output", "fixed")
KINDS = ("spur", "helical", "herringbone", "bevel", "sleeve", "dog")
SIDES = ("external", "internal")
HANDS = ("right", "left")
FLANKS = ("involute", "arcs")
FLANK_RECIPE = {"involute": "A", "arcs": "B"}

# -- Box: two columns, a setting per row --------------------------------------


@dataclass(frozen=True)
class Setting:
    key: str
    name: str
    unit: str = ""
    required: bool = False
    default: str = ""
    numeric: bool = False
    note: str = ""

    @property
    def title(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name


BOX_SETTINGS: Tuple[Setting, ...] = (
    Setting("format", "Format", default=FORMAT, note="written by the app; lets later versions read this file"),
    Setting("name", "Name", required=True, note="names the assembly and the layout part"),
    Setting("output_folder", "Output folder", note="blank: the strip's Output folder"),
    Setting("part_template", "Part template", note="blank: SolidWorks' default part template"),
    Setting("assembly_template", "Assembly template", note="blank: SolidWorks' default assembly template"),
    Setting("pressure_angle", "Pressure angle", unit="°", default="20", numeric=True,
            note="used where a gear's own cell is blank"),
    Setting("efficiency", "Efficiency per mesh", unit="%", default="98", numeric=True,
            note="used where a mesh's own cell is blank"),
    Setting("units", "Units", default="mm · degrees · rpm · N·m", note="fixed; shown so the file explains itself"),
)
BOX = SheetDef("Box", (
    Column("setting", "Setting", width=26),
    Column("value", "Value", width=34),
    Column("notes", "Notes", width=48),
))

SHAFTS = SheetDef("Shafts", (
    Column("id", "Shaft", required=True, width=10, help="A unique name. Its axis in SolidWorks is \"<name> Axis\"."),
    Column("mounted_on", "Mounted on", blank=FRAME, width=12,
           help="frame, or another shaft it rides round with (a planet on its carrier)."),
    Column("x", "X", "mm", required=True, numeric=True, width=10, help="A point on the axis, from the origin."),
    Column("y", "Y", "mm", required=True, numeric=True, width=10),
    Column("z", "Z", "mm", blank="0", numeric=True, width=10),
    Column("axis", "Axis", blank="Z+", words=AXES, aliases=_AXIS_ALIASES, width=8,
           help="Z+ Z- X+ X- Y+ Y-, or three numbers dx, dy, dz."),
    Column("role", "Role", blank="turns as the gears make it", words=ROLES, width=9),
    Column("copies", "Copies", blank="1", numeric=True, whole=True, width=8,
           help="Only on a shaft mounted on another shaft: that many, evenly round it."),
    Column("speed", "Speed", "rpm", numeric=True, width=11,
           help="Input rows only. Positive turns anticlockwise seen from the tip of Axis."),
    Column("torque", "Torque", "N·m", numeric=True, width=12, help="Input rows only."),
    Column("notes", "Notes", width=30),
))

GEARS = SheetDef("Gears", (
    Column("id", "Gear", required=True, width=8, help="A unique name; Meshes and Modes refer to it."),
    Column("shaft", "Shaft", required=True, width=8, help="A name from Shafts. The gear turns with it."),
    Column("at", "At", "mm", blank="0", numeric=True, width=9,
           help="Along the shaft's Axis from its X Y Z point to the middle of the face (a bevel gear: its cone tip)."),
    Column("kind", "Kind", blank="spur", words=KINDS, aliases={"double": "herringbone"}, width=12),
    Column("side", "Side", blank="external", words=SIDES, aliases={"ext": "external", "int": "internal"}, width=10),
    Column("teeth", "Teeth", required=True, numeric=True, whole=True, width=8),
    Column("module", "Module", "mm", required=True, numeric=True, width=12),
    Column("pressure_angle", "Pressure angle", "°", blank="the Box's", numeric=True, width=17),
    Column("face_width", "Face width", "mm", required=True, numeric=True, width=16),
    Column("bore", "Bore", "mm", blank="no bore", numeric=True, width=11),
    Column("flank", "Flank", blank="involute", words=FLANKS, width=10),
    Column("helix_angle", "Helix angle", "°", numeric=True, width=15, help="Helical kinds: needed."),
    Column("hand", "Hand", blank="right", words=HANDS, aliases={"r": "right", "l": "left"}, width=8),
    Column("groove", "Groove", "mm", blank="none", numeric=True, width=13),
    Column("profile_shift", "Profile shift", "× m", blank="0", numeric=True, width=18),
    Column("backlash", "Backlash", "mm", blank="0.3 × module", numeric=True, width=15),
    Column("fillet", "Fillet", "mm", blank="0.38 × module", numeric=True, width=12),
    Column("rim", "Rim", "mm", blank="root + 6 × module", numeric=True, width=10),
    Column("slides", "Slides", blank="doesn't slide", width=20, help="Named positions from At: H=-10, N=0, L=+10."),
    Column("part_name", "Part name", blank="as the strip names it", width=20),
    Column("notes", "Notes", width=30),
))

MESHES = SheetDef("Meshes", (
    Column("a", "Gear A", required=True, width=10),
    Column("b", "Gear B", required=True, width=10),
    Column("efficiency", "Efficiency", "%", blank="the Box's", numeric=True, width=14),
    Column("notes", "Notes", width=30),
))

# Modes' middle columns are named after the sliding gears, so only its ends are fixed.
MODE_NAME = Column("name", "Mode", required=True, width=10)
MODE_NOTES = Column("notes", "Notes", width=30)

RESULTS = "Results"
SHEET_ORDER = ("Box", "Shafts", "Gears", "Meshes", "Modes", RESULTS)
SHEETS: Dict[str, SheetDef] = {s.name: s for s in (BOX, SHAFTS, GEARS, MESHES)}

RESULTS_NOTE = ("Written by Gear Generator, {when}, from this workbook. "
                "Edits here are ignored and replaced on the next Export.")


def match_headers(sheet_def: SheetDef, headers: Mapping[int, str]) -> Tuple[Dict[str, int], Dict[int, str]]:
    """Which column of the sheet holds each known key, and the columns it does not know.

    ``headers`` is column number -> header text. Returns (key -> column, column -> unknown header).
    """
    wanted = {header_key(c.header): c.key for c in sheet_def.columns}
    found: Dict[str, int] = {}
    unknown: Dict[int, str] = {}
    for col, text in sorted(headers.items()):
        key = wanted.get(header_key(text))
        if key is not None and key not in found:
            found[key] = col
        elif text.strip():
            unknown[col] = text
    return found, unknown
