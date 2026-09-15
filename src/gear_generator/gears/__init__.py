"""Gear kinds: the maths of each, and the SolidWorks recipe that builds it."""

from .helical import HelicalGear, HerringboneGear
from .spur import SpurGear

KINDS = {"spur": SpurGear(), "helical": HelicalGear(), "herringbone": HerringboneGear()}

# Kinds the form shows, greyed, as coming in a later version.
PLANNED_KINDS = ("bevel", "internal")
