"""What the probe settled about the SolidWorks API, as constants the tool reads.

Every value here is a finding, not a preference: each names the probe it came
from, and every one of them was observed on SolidWorks 2026 (revision 34.0.0).
``tests/test_findings.py`` checks them against ``probe/results/latest.json``
through :mod:`probe.decide`, so they cannot drift from the evidence. They are
constants rather than runtime JSON because the exe must behave the same for
someone who never ran the probe.
"""

from __future__ import annotations

VERIFIED_ON = "SolidWorks 2026 (revision 34.0.0)"

# -- decisions -------------------------------------------------------------

# decide.flank_recipe: curve_literal, curve_globals and curve_rebuild all pass.
DEFAULT_RECIPE = "A"

# equation_syntax: sin ( 90 ) = 1 in a new part from the default template.
# The build measures every document anyway; this is what the dry run prints.
TRIG_DEFAULT = "degrees"

# -- equations --------------------------------------------------------------

# equation_add: Add3 returned -1 on a one-configuration part, as its help says
# it will; Add2 added, read back, and deleted.
EQUATION_ADD_CALL = "Add2"

# equation_set: an indexed property put of Equation(i) propagated to a
# dependent global on rebuild; SetEquationAndConfigurationOption returned -1.
EQUATION_SET_ROUTE = "indexed put Equation(i)"

# -- documents --------------------------------------------------------------

# document_units: the default templates here are inch documents
# (swUnitsLinear 3); SetUserPreferenceInteger(swUnitSystem, 0, MMGS) made a
# new part millimetres, and a global of 30 then drove a dimension to 0.030 m.
SET_UNITS_MMGS_AFTER_NEW = True
UNIT_SYSTEM = 263            # swUserPreferenceIntegerValue_e.swUnitSystem
UNIT_SYSTEM_MMGS = 5         # swUnitSystem_e.swUnitSystem_MMGS
UNITS_LINEAR = 47            # swUserPreferenceIntegerValue_e.swUnitsLinear
LENGTH_MM = 0                # swLengthUnit_e.swMM

# save_as: IModelDocExtension.SaveAs3 with typed nulls and two by-reference
# longs returned a plain True, not a tuple, and silently overwrote a file that
# was already there — so the tool refuses an existing path itself.
SAVE_AS_CALL = "IModelDocExtension.SaveAs3"
SAVE_AS_OVERWRITES = True
SAVE_AS_SILENT = 1           # swSaveAsOptions_e.swSaveAsOptions_Silent

# -- selecting --------------------------------------------------------------

# sketch_open_close, close_document: IFeature.Select2 on a plane returned False
# with nothing selected in some runs and True in others; SelectByID2 with the
# plane's name read from the tree selected it every time.
PLANE_SELECT_ROUTE = "Select2 checked by count, then SelectByID2 by tree name"

# The dialog AddDimension2 opens for a value; turned off for the build.
INPUT_DIM_VAL_ON_CREATE = 10  # swUserPreferenceToggle_e.swInputDimValOnCreate

# -- sketches ---------------------------------------------------------------

# relations: every constant below was checked by where the geometry went.
# sgEQUAL left two radii at 4 and 7 mm; sgSAMELENGTH made them equal.
RELATIONS = {
    "coincident": "sgCOINCIDENT",
    "tangent": "sgTANGENT",
    "symmetric": "sgSYMMETRIC",
    "horizontal": "sgHORIZONTAL2D",
    "fixed": "sgFIXED",
    "equal": "sgSAMELENGTH",
}

# dimensions: a circle's AddDimension2 measures its diameter, an arc's its
# radius; an angle's SystemValue is radians.
CIRCLE_DIMENSION = "diameter"
ARC_DIMENSION = "radius"

# constrained_status: a free line read 2, the same line defined read 3.
UNDER_CONSTRAINED = 2
FULLY_CONSTRAINED = 3

# curve_end_points: an entity drawn starting exactly on another's end shares
# that point — a line on a curve's end, a line's, or an arc's — so a coincident
# relation between them already holds and is skipped.
SHARED_ENDS_ARE_ONE_POINT = True

# curve_literal: expressions are in document units and their trig in radians,
# and a degree conversion inside one was refused. curve_fixed_rebuild: sgFIXED
# makes the curve fully defined and it still follows its globals.
CURVE_TRIG = "radians"
CURVE_UNITS = "document"
CURVES_ARE_FIXED = True

# -- features ---------------------------------------------------------------

# extrude: the blank's volume was pi r^2 w to 1e-3, and its depth was D1.
EXTRUDE_CALL = "IFeatureManager.FeatureExtrusion3"

# cut: from the blank's own plane the default direction removed nothing;
# swEndCondThroughAllBoth removed exactly the hole.
CUT_CALL = "IFeatureManager.FeatureCut4"
CUT_END_CONDITION = 9        # swEndConditions_e.swEndCondThroughAllBoth

# pattern: FeatureCircularPattern5 with DName "NULL", axis at mark 1 and the
# cut at mark 4; its dimensions came back as [D3 = 2 pi, D1 = count].
PATTERN_CALL = "IFeatureManager.FeatureCircularPattern5"
PATTERN_COUNT_DIM_INDEX = 1
PATTERN_COUNT_DIM_NAME = "D1"

# -- assemblies -------------------------------------------------------------

# assembly_components_and_mates: AddMate5 returned the mate itself; the first
# component inserted was already fixed; a distance mate's dimension is D1.
MATE_CALL = "IAssemblyDoc.AddMate5"
MATE_COINCIDENT = 0          # swMateType_e
MATE_DISTANCE = 5
MATE_ANGLE = 6
MATE_ALIGN_CLOSEST = 2       # swMateAlign_e
FIRST_COMPONENT_FIXED = True
MATE_DISTANCE_DIM_NAME = "D1"
