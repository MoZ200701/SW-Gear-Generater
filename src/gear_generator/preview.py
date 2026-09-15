"""Where the Derived panel's gears go on its canvas, worked out without a window.

The panel draws one picture: in pair mode both gears at one scale, meshed at the
centre distance their teeth make, with that distance dimensioned below them; in
single mode the one gear with its pitch diameter dimensioned. Everything about
*where* — the scale, the two centres, how far gear B is turned, where the
dimension line and its label sit — is decided here, in millimetres and canvas
pixels, so it can be tested on a machine with no display. :mod:`gui` only
strokes what comes back.

Nothing here touches tkinter, and nothing here holds state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .gears import pair as pairs
from .gears.equations import literal

# The panel body is the strip less the panel border and its own padding; the
# design's 436 is that width rounded up. 210 px is deep enough for a 60-tooth
# wheel beside its pinion and the dimension under them.
WIDTH = 434
HEIGHT = 210

PAD = 14          # left and right of the gears
TOP = 8           # above them
DIM_ZONE = 46     # kept clear under them for the dimension and its label
DIM_DROP = 24     # from the lowest point of the larger gear down to the line
DIM_OVERRUN = 4   # how far an extension line passes the dimension line
LABEL_LIFT = 5    # the label's baseline above the dimension line


@dataclass(frozen=True)
class Placed:
    """One gear on the canvas: where its centre is, and how far it is turned."""

    label: str
    x: float              # canvas px
    y: float              # canvas px
    rotation: float       # radians, anticlockwise, the way the outline is given
    tip_radius: float     # mm
    pitch_radius: float   # mm
    bore_radius: float    # mm, 0 when there is no bore


@dataclass(frozen=True)
class Dimension:
    """The dimension under the gears: a line with arrowheads, and what it says."""

    x0: float
    x1: float
    y: float
    extensions: Tuple[Tuple[float, float, float], ...]   # (x, from y, to y)
    text: str
    text_x: float
    text_y: float                                        # the text's bottom edge


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    scale: float                  # canvas px per mm
    gears: Tuple[Placed, ...]
    centre_distance: float        # mm; 0 for a single gear
    dimension: Dimension


def mesh_rotation(teeth: int) -> float:
    """How far the second gear is turned to face the first, in radians.

    Half a turn, so its far side is drawn towards the pinion, plus the mesh
    angle the assembly is actually mated at — half a tooth pitch for an even
    count, nothing for an odd one, which already has a tooth opposite a space
    (:func:`gears.pair.mesh_angle`). Turned any other way the two outlines
    would be drawn crossing, which is not what the pair does.
    """
    return math.pi + math.radians(pairs.mesh_angle(teeth))


def layout(gears: Sequence, width: int = WIDTH, height: int = HEIGHT,
           labels: Sequence[str] = ("A", "B")) -> Layout:
    """Place one or two gears — ``SpurDerived``s — on a canvas that size.

    Two gears are placed at ``m (N_A + N_B) / 2`` apart, the distance their
    teeth make and the one the assembly is mated at, and the scale is whatever
    lets both of them and the gap between them fit; one gear fills the height.
    """
    if not gears or len(gears) > 2:
        raise ValueError(f"The preview draws one gear or two, not {len(gears)}.")
    tips = [g.ra for g in gears]
    centre_distance = (gears[0].d + gears[1].d) / 2.0 if len(gears) == 2 else 0.0
    extent = tips[0] + centre_distance + tips[-1] if centre_distance else 2 * tips[0]
    gear_height = height - DIM_ZONE - TOP
    scale = min((width - 2 * PAD) / extent, gear_height / (2 * max(tips)))
    y = TOP + gear_height / 2.0
    left = (width - extent * scale) / 2.0

    placed: List[Placed] = []
    for index, g in enumerate(gears):
        x = left + tips[0] * scale + (centre_distance * scale if index else 0.0)
        placed.append(Placed(
            label=labels[index] if len(gears) > 1 else "",
            x=x, y=y,
            rotation=mesh_rotation(g.teeth) if index else 0.0,
            tip_radius=g.ra, pitch_radius=g.rp,
            bore_radius=g.bore / 2.0 if g.bore > 0 else 0.0,
        ))

    y_dim = y + max(tips) * scale + DIM_DROP
    if centre_distance:
        # Centre to centre: the extension lines start clear of the centre marks.
        x0, x1 = placed[0].x, placed[1].x
        top = y + 6
        text = f"C {_n(centre_distance)} mm"
    else:
        # The pitch diameter, which is what module × teeth comes to.
        x0 = placed[0].x - placed[0].pitch_radius * scale
        x1 = placed[0].x + placed[0].pitch_radius * scale
        top = y
        text = f"PD {_n(2 * placed[0].pitch_radius)} mm"
    dimension = Dimension(
        x0=x0, x1=x1, y=y_dim,
        extensions=((x0, top, y_dim + DIM_OVERRUN), (x1, top, y_dim + DIM_OVERRUN)),
        text=text, text_x=(x0 + x1) / 2.0, text_y=y_dim - LABEL_LIFT,
    )
    return Layout(width=width, height=height, scale=scale, gears=tuple(placed),
                  centre_distance=centre_distance, dimension=dimension)


def points_on(outline: Sequence[Tuple[float, float]], placed: Placed,
              scale: float) -> List[Tuple[float, float]]:
    """One gear's outline in canvas pixels: turned, scaled, and put at its centre.

    The canvas counts y downwards and the outline counts it upwards, so y is
    subtracted rather than added.
    """
    cos, sin = math.cos(placed.rotation), math.sin(placed.rotation)
    return [
        (placed.x + (x * cos - y * sin) * scale, placed.y - (x * sin + y * cos) * scale)
        for x, y in outline
    ]


def _n(value: float, places: int = 3) -> str:
    """The same number formatting the readouts use: 60.0 reads ``60``."""
    return literal(round(float(value), places))
