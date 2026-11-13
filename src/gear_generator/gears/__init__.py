"""Gear kinds: the maths of each, and the SolidWorks recipe that builds it."""

from .bevel import BevelGear
from .helical import HelicalGear, HerringboneGear
from .internal import InternalHelicalGear, InternalHerringboneGear, InternalSpurGear
from .spur import SpurGear

KINDS = {"spur": SpurGear(), "helical": HelicalGear(), "herringbone": HerringboneGear(), "bevel": BevelGear()}

# A ring of each kind that can have one. Internal is not a kind of its own: it
# is which side of the rim a spur, helical or herringbone gear's teeth are on.
INTERNAL_KINDS = {"spur": InternalSpurGear(), "helical": InternalHelicalGear(),
                  "herringbone": InternalHerringboneGear()}

# Kinds the form shows, greyed, as coming in a later version.
PLANNED_KINDS: tuple = ()


def kind_for(spec):
    """The calculation for a form: its kind, and a ring's when its teeth are internal. None when there is none."""
    if str(getattr(spec, "teeth_side", "")).strip().lower() == "internal":
        return INTERNAL_KINDS.get(spec.kind)
    return KINDS.get(spec.kind)


def plan_for(spec, derived, template: str, path: str):
    """The build plan for one gear, exactly as the strip makes it: its kind, its recipe, the template, the path.

    The strip (``gui._plan_single``) and a workbook (``workbook.build``) both
    call this, so a workbook row and the strip build the same part from the
    same values by construction, not by two calls kept in step.
    """
    kind = kind_for(spec)
    return kind.plan(spec, derived, kind.recipe_for(spec), template, path)
