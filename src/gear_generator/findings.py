"""What the probe settled about the SolidWorks API, as constants the tool reads.

Every value here is a finding, not a preference: each names the probe it came
from, and every one of them was observed on SolidWorks 2026 (revision 34.0.0).
SolidWorks 2024 (revision 32.5.0) reached the same decisions; its runs are in
``probe/results/sw2024/``, where the README says what each one showed.
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

# document_units: this reads the session's default part template, so it says
# what that template is rather than anything about the API. In the 2026-09-15
# run the default was an inch document (swUnitsLinear 3), and
# SetUserPreferenceInteger(swUnitSystem, 0, MMGS) made a new part millimetres,
# after which a global of 30 drove a dimension to 0.030 m (that run's results
# are kept beside latest.json). By 2026-11-13 the default was a millimetre
# template ("MMGS 8 Decimals"), so there was nothing to set, as on 2024. The
# build measures every new part and sets MMGS only when it is not millimetres.
SET_UNITS_MMGS_AFTER_NEW = False
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
    # path_sketch_relations: vertical on both path lines left the sketch fully defined.
    "vertical": "sgVERTICAL2D",
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

# assembly_components_and_mates: AddMate5 returned the mate itself; a distance
# mate's dimension is D1. Whether the first component inserted comes in fixed
# follows the session's default assembly template: it did with the stock
# template (2026-09-15, and 2024), and did not with "MMGS 8 Decimals.asmdot"
# (2026-11-13). The build fixes gear 1 itself (Fix), so it does not rely on it.
MATE_CALL = "IAssemblyDoc.AddMate5"
MATE_COINCIDENT = 0          # swMateType_e
MATE_DISTANCE = 5
MATE_ANGLE = 6
MATE_ALIGN_CLOSEST = 2       # swMateAlign_e
FIRST_COMPONENT_FIXED = False
MATE_DISTANCE_DIM_NAME = "D1"

# -- helical and herringbone ------------------------------------------------

# equation_inverse_trig: atn ( 1 ) read 45 in a degree document, arcsin and
# arccos answered in degrees too, arctan was refused; atn of the transverse
# pressure angle read back equal to the maths.
INVERSE_TANGENT = "atn"
INVERSE_TRIG_UNITS = "degrees"

# center_of_mass: a boss extruded from the Front plane has its centre of mass
# at z = +w/2, so a blank goes toward +Z. The Top plane's sketch x is model +X
# and its sketch y is model -Z, so a line along the axis is sketch-vertical.
EXTRUDE_Z_SIGN = 1
TOP_SKETCH_Y_IS_MINUS_Z = True

# ref_plane_offset: InsertRefPlane(8, d, 0, 0, 0, 0) on the Front plane put the
# plane at z = +d, and with the flip bit 256 at z = -d; both planes' sketches
# face +Z like the Front plane's. The offset is the plane's only dimension, D1.
REF_PLANE_CALL = "IFeatureManager.InsertRefPlane"
REF_PLANE_DISTANCE = 8       # swRefPlaneReferenceConstraints_e.swRefPlaneReferenceConstraint_Distance
REF_PLANE_FLIP = 256         # swRefPlaneReferenceConstraint_OptionFlip
REF_PLANE_UNFLIPPED_IS_PLUS_Z = True

# mirror_body_merge: with the body selected at mark 256 and the plane at mark 2,
# InsertMirrorFeature2(True, False, True, False, 0) made one body of twice the
# volume centred on the plane; marks 1/2 and 1/1 mirrored nothing.
MIRROR_CALL = "IFeatureManager.InsertMirrorFeature2"
MIRROR_BODY_MARK = 256
MIRROR_PLANE_MARK = 2

# sweep_twist: selected as profile at mark 1 and path at mark 4, a sweep with
# swTwistControlConstantTwistAlongPath (8) and a twist of pi/2 turned a circle
# at r 12 a uniform quarter turn (centroid within 3e-4 mm of r0 sin θ/θ), its
# volume A·L to 3e-4. The twist argument is radians; a negative one turned the
# same way as a positive one. Unreversed, the section turned counter-clockwise
# about +Z as z increased for a path toward +Z and for one toward -Z alike — a
# right-hand helix both ways. D1ReverseTwistDir, set through GetDefinition,
# AccessSelections(doc, null) and ModifyDefinition(data, doc, null), turned it
# the other way. Its one dimension is the twist, in radians, D4 by default.
TWIST_CONSTANT_ALONG_PATH = 8   # swTwistControlType_e.swTwistControlConstantTwistAlongPath
SWEEP_DIRECTION = 0            # swSweepDirection_e.swSweepDirection1
SWEEP_PROFILE_MARK = 1
SWEEP_PATH_MARK = 4
TWIST_TURN = {"plus z": 1, "minus z": 1}
TWIST_REVERSE_ROUTE = "ISweepFeatureData.D1ReverseTwistDir through ModifyDefinition"

# sweep_twist_link: renamed Twist and linked to a global of 45, the dimension
# read pi/4: a linked twist is in degrees, and the sweep followed it.
# sweep_cut_ends: InsertCutSwept5 (22 arguments) removed A·w from a blank to
# 1e-7 with the section 2 mm ahead of the face and the path 2 mm past the far
# one, and to 1.5e-4 with the section on the face itself; one body either way.
SWEEP_CUT_CALL = "IFeatureManager.InsertCutSwept5"
SWEEP_ENDS = "overrun"

# pattern_sweep: FeatureCircularPattern5 of a twisted cut left N·A·w removed and
# one body; 24 of them rebuilt in 0.37 s, 0.20 s as a geometry pattern.
PATTERN_OF_SWEEPS_SECONDS_24 = 0.373

# -- internal gears ---------------------------------------------------------

# annulus_extrude: a sketch of two concentric circles, D 40 and d 24, extruded
# by FeatureExtrusion3 to one body of pi/4 (D^2 - d^2) w to 1e-6; the inner
# circle's diameter linked to a global of 20 opened the hole to match.
ANNULUS_EXTRUDES = True

# -- interference -----------------------------------------------------------

# interference: IAssemblyDoc.InterferenceDetectionManager on two r 20 mm,
# 10 mm cylinders 30 mm apart counted one interference of 1813.247 mm^3, the
# lens exactly, and none 50 mm apart. GetInterferenceCount, GetInterferences
# and IInterference.Volume (m^3) read as properties; Done is a method. The
# options below were set before counting.
INTERFERENCE_CALL = "IAssemblyDoc.InterferenceDetectionManager"
INTERFERENCE_OPTIONS = (
    ("TreatCoincidenceAsInterference", False),
    ("TreatSubAssembliesAsComponents", True),
    ("IncludeMultibodyPartInterferences", True),
    ("MakeInterferingPartsTransparent", False),
    ("CreateFastenersFolder", False),
    ("IgnoreHiddenBodies", True),
    ("ShowIgnoredInterferences", False),
    ("UseTransform", False),
)
# So a pair's assembly is checked for interference by the build, and a person
# no longer has to look along the axis for clashing teeth.
INTERFERENCE_CHECKED = True

# -- bevel gears ------------------------------------------------------------

# revolve: a square revolved by FeatureRevolve2 (20 arguments, a full turn in
# radians) about a sketch centreline weighed 2 pi r A to 1e-4 with its centre of
# mass on the centreline, along Z and tilted. With one centreline the sketch
# alone was enough; with a second one in the sketch, the axis line had to be
# selected too, at mark 16, by SelectByID2 "LineN@Sketch" EXTSKETCHSEGMENT.
REVOLVE_CALL = "IFeatureManager.FeatureRevolve2"
REVOLVE_AXIS_MARK = 16
REVOLVE_TYPE = "Revolution"

# ref_plane_normal: InsertRefPlane(2 perpendicular, 0, 4 coincident, 0, 0, 0)
# with a sketch line at mark 0 and its end, selected by its model location
# (EXTSKETCHPOINT), at mark 1 made a plane square to the line through its end.
# Its sketch's origin was the line's end, its x the outward radial of a cone
# whose axis is Z, its y +Y and its normal along the line; the plane kept that
# frame when the line's linked angle and length changed.
REF_PLANE_PERPENDICULAR = 2   # swRefPlaneReferenceConstraint_Perpendicular
REF_PLANE_COINCIDENT = 4      # swRefPlaneReferenceConstraint_Coincident
BEVEL_SECTION_X_SIGN = 1      # the section's outward radial is the plane's sketch +x

# bevel_planes_beyond_90: the same plane made fresh on a pitch cone of 90° (a
# crown gear's, square to X) and of 120° (an internal bevel's, leaning past it).
# On both, the angle placed on the bisector read the angle meant (90°, 120°, not
# a supplement), the plane's origin was the line's end, and its sketch +x was
# (cos δ, 0, −sin δ), the way the teeth's tips point, as it is below 90°; its y
# was +Y and its normal along the line.
BEVEL_CROWN_SECTION_X_SIGN = 1
BEVEL_INTERNAL_SECTION_X_SIGN = 1

# loft_cut_sections: InsertCutBlend (12 arguments) through two similar
# rectangles on parallel planes, both at mark 1 in order, removed their frustum
# L A (1 + k + k^2) / 3 to 1e-4 and left one body.
LOFT_CUT_CALL = "IFeatureManager.InsertCutBlend"
LOFT_PROFILE_MARK = 1
LOFT_CUT_TYPE = "BlendCut"

# axis_from_sketch_line: an angle dimension between two lines on the Top plane,
# placed inside the angle at a point given in model coordinates, read the angle
# (30°); placed at the same point's sketch coordinates it had read 150°.
DIMENSION_PLACED_IN_MODEL_SPACE = True

# move_body_rotate: InsertMoveCopyBody2 turned a body about Y as expected, but the
# feature carried no dimension, so no equation can drive its turn. The bevel
# recipe builds in its final frame instead.
MOVE_BODY_TURN_IS_DIMENSION = False

# -- non-parallel assemblies ------------------------------------------------

# nonparallel_mates: IMathUtility.CreateTransform answered "member not found"
# to late binding and made a transform when invoked as a method with a double
# array; put on IComponent2.Transform2 with the rotation in columns it set the
# frame to 1e-16. AddComponent5 put a part's middle, not its origin, at the
# point given, so the first gear is set on the assembly frame too.
PLACE_ROUTE = "Transform2 put"
TRANSFORM_ARRAY_ORDER = "columns"
# A component's origin selected by SelectByID2 "Point1@Origin@<component>@<assembly>"
# as EXTSKETCHPOINT; two origins made a coincident mate.
ORIGIN_POINT = "Point1"
# Placed first and then mated — origins coincident, gear 2's axis in gear 1's
# top plane, an angle mate between the axes and one between the top planes — a
# bevel-style frame held to 1e-16 and 0 mm.
BEVEL_MATE_ROUTE = "mates"

# -- custom properties ------------------------------------------------------

# custom_properties: IModelDocExtension.CustomPropertyManager("") gave the
# part's manager; Add3(name, swCustomInfoText, value, swCustomPropertyReplaceValue)
# returned 0 and Get6 with by-reference outs read the value back; a second Add3
# of the same name replaced it. Both enum values were read from swconst.tlb.
# A property whose value was a global's quoted name, '"No. of Teeth"', resolved
# to that text itself, before and after the global changed from 25 to 40, so
# the sizes are not stamped: as plain text they would go stale.
CUSTOM_PROPERTY_ROUTE = "Add3"
CUSTOM_INFO_TEXT = 30            # swCustomInfoType_e.swCustomInfoText
CUSTOM_PROPERTY_REPLACE = 2      # swCustomPropertyAddOption_e.swCustomPropertyReplaceValue
PROPERTY_READ_ROUTE = "Get6 with by-reference outs"
PROPERTY_LINKS_GLOBALS = False

# -- gear mate --------------------------------------------------------------

# gear_mate: two cylinders, the first unfixed by IAssemblyDoc.UnfixComponent and
# held on the assembly's own planes with an angle mate to drive it, the second's
# axis held 60 mm away, and AddMate5(swMateGEAR, closest, flip, 0, 0, 0, 20, 40,
# ...) between the two axes made one MateGearDim. Driving the angle mate through
# a global turned the first 30° and the second 15°: the ratio's numerator goes
# with the first selection. With Flip off the two turned opposite ways, as an
# external pair does; with Flip on, the same way. swMateGEAR was read from
# swconst.tlb, after the reader gave back the three mate types above.
GEAR_MATE_ROUTE = "mates"
MATE_GEAR = 10                   # swMateType_e.swMateGEAR
GEAR_MATE_NUMERATOR_FIRST = True
GEAR_MATE_EXTERNAL_FLIP = False
# The same Flip serves a ring. probe/gear_pairs_check.py built pairs through
# pair.assembly_plan and drove gear 1 30°: an external 20 / 40 spur pair turned
# opposite ways at 1 : 2 with Flip False, and a 20-tooth pinion in a 60-tooth ring
# turned the SAME way as the ring at 3 : 1, with no interference, also with Flip
# False; with Flip True it turned against the ring and the teeth clashed (4
# interferences). So SolidWorks takes the sense from where the gears sit, and
# Flip only reverses it; pair.py no longer inverts it for a ring.
# The crossed frame's mates held its rotation; a point's distance from a plane is
# measured along the plane's normal, so a negative offset is mated flipped.
CROSSED_ROUTE = "mates"

# -- the workbook's layout part and static assembly (tier 7) -----------------
#
# Probe tier 7 (p7_workbook), PLAN-WORKBOOK §4.2, on SolidWorks 2026 (34.0.0)
# and 2024 (32.5.0) with the same answers; tests/test_findings.py pins each one
# against both versions' latest.json.

# layout_planes: InsertRefPlane(8 | flip 256, 7 mm) from the Right plane put the
# unflipped plane at x = +7 and the flipped one at -7, both facing +X; from the
# Top plane, y = +7 and -7, both facing +Y. The sketch transform and
# IRefPlane.Transform agreed. The offset was the plane's only dimension, D1, and
# linked to a global it followed 7 -> 23. So, as from Front, unflipped is the plus side.
LAYOUT_PLUS_FLIP = {"right": False, "top": False}
LAYOUT_OFFSET_DIM = "D1"
# A plane on the minus side keeps a positive offset; linked as
# "Offset@<plane>"= - "<global>" it followed a negative global (-7 -> -11), so a
# shaft's X and Y globals can keep their sign. The first form tried was taken.
LAYOUT_NEGATED_LINK = "minus"

# layout_plane_negative_global: a plus-side plane's offset linked to a global set
# to -9 did NOT cross zero. The Equation Manager took the value (it read -9),
# ForceRebuild3 returned True and the plane's error code was 0, yet the offset
# stayed 7 mm and the plane at x = +7: the change was dropped without a word.
# So a shaft whose X or Y changes sign is a structural change, and the layout
# must never rely on a global to carry a plane across its base plane.
OFFSET_GLOBAL_CROSSES_ZERO = False

# axis_through_named_planes: InsertAxis2(True) through two planes made in the
# same part, selected by IFeature.Select2 on the feature found by name (the
# route the app's _select_feature takes first), by SelectByID2 "<name>", "PLANE",
# and by Select2 on the RefPlane InsertRefPlane returned: all three made the axis
# where the planes cross, and it followed both planes' globals on a rebuild.
AXIS_PLANE_SELECT_ROUTE = "Select2 on the feature found by name"
# Every axis made this way, from a Right-parallel and a Top-parallel plane in
# that order, read along -Z from GetRefAxisParams (its second point below the first).
# The order of selection sets it: each gear part's "Gear Axis", made from Top then
# Right (swcom.insert_axis, planes 2 and 3), read +Z in the parts built by
# probe/gear_pairs_check.py on 2026. A layout axis that a gear's axis is to be
# mated to (W5) can be made Top-parallel first so the two agree.
LAYOUT_AXIS_Z_SIGN = -1
# axis_through_base_planes: with the Right or Top plane itself in place of an
# offset plane (a shaft at X = 0, Y = 0, or both), the axis lay on it and the
# other coordinate still followed its global.
AXIS_THROUGH_BASE_PLANE = True

# layout_assembly_five / layout_assembly_reopen: five components (one part twice,
# named "<part>-1" and "<part>-2"), each set by a Transform2 put, then fixed by
# Select4 + FixComponent(), saved, closed and opened again by OpenDoc6: each was
# where it was left and still fixed, found by IAssemblyDoc.GetComponentByName
# (GetComponents(True), the root component's GetChildren and FeatureByName ->
# GetSpecificFeature2 found all five too). A Transform2 put moved a FIXED
# component without unfixing it, and the new frames survived a save and reopen.
COMPONENT_FIND_ROUTE = "GetComponentByName"
REPLACE_FIXED_ROUTE = "Transform2 put"
OPEN_ASSEMBLY_ROUTE = "OpenDoc6"

# open_and_activate_part: OpenDoc6(path, 1, swOpenDocOptions_Silent 1, "", out,
# out) returned the document itself, not a tuple, with errors 0, and made a
# closed part active over another document. On a part already open it returned
# the same document with warning 128 (swFileLoadWarning_AlreadyOpen) and did NOT
# bring it forward, so ActivateDoc3 always follows; swbuild.update_variables
# then accepted it. open_part_from_assembly: the same for a part loaded only as
# a component of an open assembly (listed among the open documents, opened with
# warning 128, activated, and changed by update_variables).
UPDATE_OPEN_ROUTE = "open and activate"
OPEN_DOC_ROUTE = "OpenDoc6"
OPEN_DOC_SILENT = 1              # swOpenDocOptions_e.swOpenDocOptions_Silent, read from swconst.tlb
OPEN_DOC_ALREADY_OPEN_WARNING = 128
OPEN_PART_BESIDE_ASSEMBLY = True

# layout_part_without_body: the layout part as W4 makes it, planes and named axes
# and no solid body, inserted by AddComponent5 at (12, -7, 3) mm landed with its
# ORIGIN there (a solid part lands with the middle of its box there, see
# PLACE_ROUTE), was placed at identity, fixed, and saved with no error or warning;
# interference detection ran with it in the assembly and found nothing. Reopened,
# it was found by GetComponentByName at identity, fixed and fully resolved, and
# each named axis selected in the assembly both by FeatureByName + Select2 and by
# SelectByID2 "<axis>@<component>@<assembly>", "AXIS".
LAYOUT_PART_WITHOUT_BODY = True
BODILESS_LANDS_ORIGIN_AT_POINT = True

# add_component_opened_part: AddComponent5 of a part saved and CLOSED returned
# None, though the API help's "the file must be loaded" is about exactly this;
# the same part opened by OpenDoc6 first (and left the active document) went in.
# So a part reused from an earlier build is opened before it is inserted. The
# same file inserted twice is "<stem>-1" and "<stem>-2".
REUSE_ADD_ROUTE = "opened"
# add_component_same_name_elsewhere (extra): with "<stem>.SLDPRT" in the assembly,
# OpenDoc6 of another folder's "<stem>.SLDPRT" returned nothing with error 65536
# (swFileWithSameTitleAlreadyOpen) and AddComponent5 of it returned None. No
# dialog. Two parts of one file name cannot be in one session, so the build must
# refuse a reused part whose name clashes with one it makes.
SAME_NAME_ELSEWHERE_INSERTED = False
SAME_NAME_OPEN_ERROR = 65536

# interference_components (extra): IInterference.Components, read as a property
# through late binding, gave a tuple of the two components; their Name2s named the
# two overlapping cylinders and not the third, with the lens's volume. So a CHECK
# can say which gears interfere.
INTERFERENCE_NAMES_ROUTE = "Components (property)"

# layout_assembly_reopen: every component of a reopened assembly came back fully
# resolved (GetSuppression2 2, swComponentFullyResolved), on 2026 and in the
# user's own 2024 session, so finding and re-placing them need no resolve step.
COMPONENTS_RESOLVED_AFTER_REOPEN = True

# Items 1-4 of PLAN-WORKBOOK §4.2 and the body-less layout part all passed, so the
# layout part and the static assembly are built.
WORKBOOK_LAYOUT_ROUTE = "layout"
