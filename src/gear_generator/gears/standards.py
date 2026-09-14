"""The standard numbers a gear is chosen from.

Metric module only. ISO 54 gives two preference series — series 1 first, series
2 where series 1 has nothing close enough — and DIN 780 adds a fine series below
one millimetre, which is off by default because most people cutting spur gears
for a mechanism never want it.
"""

from __future__ import annotations

from typing import Sequence, Tuple

ISO_MODULES_1 = (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32, 40, 50)
ISO_MODULES_2 = (1.125, 1.375, 1.75, 2.25, 2.75, 3.5, 4.5, 5.5, 7, 9, 11, 14, 18, 22, 28, 36, 45)
FINE = (0.5, 0.6, 0.7, 0.8, 0.9)

PRESSURE_ANGLES = ("14.5", "20", "25")

SERIES_1 = "1"
SERIES_1_2 = "1+2"
SERIES_ALL = "1+2+fine"
SERIES = (SERIES_1, SERIES_1_2, SERIES_ALL)


def modules(series: str = SERIES_1) -> Tuple[float, ...]:
    """Every module a series allows, smallest first."""
    if series == SERIES_1:
        chosen: Sequence[float] = ISO_MODULES_1
    elif series == SERIES_1_2:
        chosen = ISO_MODULES_1 + ISO_MODULES_2
    elif series == SERIES_ALL:
        chosen = ISO_MODULES_1 + ISO_MODULES_2 + FINE
    else:
        raise ValueError(f"Module series must be one of {', '.join(SERIES)} (got {series!r}).")
    return tuple(sorted(float(m) for m in chosen))


def is_standard(module: float, series: str = SERIES_ALL) -> bool:
    return any(abs(module - m) < 1e-9 for m in modules(series))


def nearest_module(module: float, series: str = SERIES_1) -> float:
    """The standard module closest to this one; the smaller on a tie."""
    return min(modules(series), key=lambda m: (abs(m - module), m))
