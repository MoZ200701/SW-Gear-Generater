"""Gear kinds: the maths of each, and the SolidWorks recipe that builds it."""

from .spur import SpurGear

KINDS = {"spur": SpurGear()}

# Shown greyed out in the window, so the seam for them is visible.
PLANNED_KINDS = ("bevel", "helical", "internal")
