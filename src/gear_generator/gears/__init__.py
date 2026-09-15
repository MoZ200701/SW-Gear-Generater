"""Gear kinds: the maths of each, and the SolidWorks recipe that builds it."""

from .helical import HelicalGear, HerringboneGear
from .internal import InternalHelicalGear, InternalHerringboneGear, InternalSpurGear
from .spur import SpurGear

KINDS = {"spur": SpurGear(), "helical": HelicalGear(), "herringbone": HerringboneGear()}

# A ring of each kind that can have one. Internal is not a kind of its own: it
# is which side of the rim a spur, helical or herringbone gear's teeth are on.
INTERNAL_KINDS = {"spur": InternalSpurGear(), "helical": InternalHelicalGear(),
                  "herringbone": InternalHerringboneGear()}

# Kinds the form shows, greyed, as coming in a later version.
PLANNED_KINDS = ("bevel",)


def kind_for(spec):
    """The calculation for a form: its kind, and a ring's when its teeth are internal. None when there is none."""
    if str(getattr(spec, "teeth_side", "")).strip().lower() == "internal":
        return INTERNAL_KINDS.get(spec.kind)
    return KINDS.get(spec.kind)
