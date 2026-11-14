"""What the probe settled about the SolidWorks API, as constants the tool reads.

Every value here is a finding, not a preference: each names the probe it came
from, and every one of them was observed on SolidWorks 2026 (revision 34.0.0,
and again in a full run on 34.1.1, which latest.json now is).
SolidWorks 2024 (revision 32.5.0) reached the same decisions; its runs are in
``probe/results/sw2024/``, where the README says what each one showed.
``tests/test_findings.py`` checks them against ``probe/results/latest.json``
through :mod:`probe.decide`, so they cannot drift from the evidence. They are
constants rather than runtime JSON because the exe must behave the same for
someone who never ran the probe.
"""

from __future__ import annotations

VERIFIED_ON = "SolidWorks 2026 (revision 34.1.1)"

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

# -- which rebuild Update SolidWorks gives an assembly (tier 7, item 6) ------
#
# assembly_rebuild_scope, after the W4 rerun on 2026 found ForceRebuild3(False) on an
# assembly marking every component modified (docs/notes-workbook/W4-RERUN-2026.md).
# Observed on SolidWorks 2026 (34.1.1, a full run, latest.json) and 2024 (32.5.0, this
# item and what it needs, sw2024/probe-results-20261114-014813) on 2026-11-14, with every
# decision the same. Each route ran on a two-gear gearbox of its own (17 and 68 teeth,
# module 1.5) built by assess, plan_gearbox and build_gearbox, saved, closed and opened
# again (every document then read GetSaveFlag False, as W4's a3 expects of a document
# just opened). Then: a raw Transform2 put turning G2 half a pitch and back; S2 X moved
# 63.75 -> 68.75 in the layout part's own document (opened by path, rebuilt there); G2
# given 69 teeth by update_variables in its own document; and G2's Bore Diameter set
# to 500, which failed its Bore cut (error code 1). After each, the route ran on the
# assembly, and the frame, the interferences, CreateMeasure from the layout's S2 Axis
# in the assembly to the assembly's Right plane, and every document's GetSaveFlag were
# read.
#
# What shows does not depend on the route: with every route, and with no rebuild at
# all, the put's frame read back, G2 half a pitch round clashed with G1 and was clean
# put back, the layout axis measured 68.75 mm from Right in the assembly, and the
# 69-tooth G2 at its old frame clashed with G1. What differs is what is marked and
# what is reported:
# - ForceRebuild3(False) marked G1, which nothing changed, and every other document
#   modified at the first step; the fault the rerun found.
# - ForceRebuild3(True) and EditRebuild3 marked exactly the documents changed on
#   purpose at every step (the assembly; then the layout; then G2), G1 never, both
#   before and after the interference check; and both returned False while G2 was in
#   error and True once it was put right. ForceRebuild3(True) is the app's existing
#   call with its one argument turned over, so it is taken.
# - With no rebuild the put did not mark the assembly modified at all (only the
#   interference check afterwards did), and nothing reports G2's failure; so a put is
#   always followed by the rebuild, though it shows without one.
# A Face Width of 0 failed nothing: G2's rebuild returned True with no feature error
# and the global was taken (as a negative layout global is, OFFSET_GLOBAL_CROSSES_ZERO).
ASSEMBLY_REBUILD_ROUTE = "ForceRebuild3(True)"
ASSEMBLY_REBUILD_TOP_ONLY = True          # the argument ForceRebuild3 takes for that route
ASSEMBLY_REBUILD_KEEPS_COMPONENTS_UNMODIFIED = True
FULL_ASSEMBLY_REBUILD_MARKS_COMPONENTS_MODIFIED = True   # ForceRebuild3(False): every component
PUT_NEEDS_REBUILD = False                 # to show; the rebuild still follows, for the mark and the report
PUT_MARKS_ASSEMBLY_MODIFIED = False       # a Transform2 put on its own
OPENED_READS_UNMODIFIED = True            # every document of an assembly just opened

# -- the workbook gearbox that turns (tier 8) --------------------------------
#
# Probe tier 8 (p8_motion), PLAN-WORKBOOK §4.4 / phase W5, which needs PLAN-GEARBOX's
# tier 6 items 3-5. Observed on SolidWorks 2026 (34.0.0, a full run, latest.json) and
# 2024 (32.5.0, tier 8 in a freshly restarted session, sw2024/probe-results-20261113-223412)
# on 2026-11-13, with every decision the same; the one difference (the mate error codes
# GetErrorCode2 gives) is noted where it bites. tests/test_findings.py pins each finding
# against both files.

# motion_enums, read from swconst.tlb after the reader gave back coincident 0,
# distance 5, angle 6 and gear 10.
MATE_CONCENTRIC = 1              # swMateType_e.swMateCONCENTRIC
MATE_LOCK = 16                   # swMateType_e.swMateLOCK
MATE_ALIGN_ALIGNED = 0           # swMateAlign_e
MATE_ALIGN_ANTI_ALIGNED = 1
ADD_MATE_NO_ERROR = 1            # swAddMateError_e.swAddMateError_NoError

# shaft_axis_mates: eight cylinders placed turned and fixed as W4 leaves them, on
# shafts along Z+ and Z-, then unfixed (UnfixComponent) and mated to their shaft's
# "<Shaft> Axis" in the body-less layout part. AddMate5(swMateCOINCIDENT, closest)
# between the gear's "Gear Axis" and the layout axis held it: no gear moved or turned
# over (closest kept a Z- gear anti-aligned: IMate2.Alignment read 0 on Z+, 1 on Z-),
# a Transform2 put turning it 25° about its axis stayed, and one moving it 5 mm off
# the axis, 5 mm along it, or tilting it 10° came back on the rebuild; the mates and
# frames came back unchanged after a save and reopen, with no mate error. The axes
# selected by FeatureByName + Select2, by SelectByID2 "<axis>@<component>@<assembly>"
# and by GetCorresponding of the part's feature + Select4 alike. A CONCENTRIC mate
# between the two axes was refused: AddMate5 returned nothing with status 0
# (swAddMateError_ErrorUknown), on Z+ and Z-. The cylinder's outside face concentric
# with the layout axis held too. Given explicitly, swMateAlignANTI_ALIGNED turned a Z+
# gear over and swMateAlignALIGNED a Z- one, so closest is what keeps W4's placing.
AXIS_MATE_ROUTE = "axis coincident"
AXIS_CONCENTRIC_REFUSED = True
# Along the shaft: a distance from the gear's origin (Point1@Origin, its front-face
# centre) to the layout's Front plane, |z| with Flip set when z < 0 (a point's distance
# is along the plane's normal, as nonparallel_mates found), held a gear at z = 5, -12
# and 8 on Z+ and Z-, and a coincident one at z = 0. The gear's Front plane at a distance
# from the layout's Front, Flip off, put it on the wrong side (12 and 14 mm off).
AXIAL_MATE_ROUTE = "origin distance"

# gear_mate_sense: nineteen pairs of cylinders and annuli on layout axes, mated as
# above, each joined by AddMate5(swMateGEAR) and its first gear driven 30° by an angle
# mate on one global. With Flip False every external pair turned opposite ways about
# +Z, at the ratio, whichever way the two shafts pointed (Z+ Z+, Z+ Z-, Z- Z+, Z- Z-),
# whichever number of the ratio was the bigger, and whether the gears' axes, their
# outside faces or one of each were selected; with Flip True, the same way. An annulus
# round a cylinder (a ring round its pinion) turned the SAME way as it with Flip False,
# ring selected first or second, on Z+ or Z-, axes or faces. AddMate5's alignment
# (aligned, anti-aligned or closest) changed nothing, and IMate2.Alignment read 2
# (closest) whatever was passed. So Flip False is the mesh's own sense, read from where
# the gears sit, and every mesh a workbook lists - outside or inside a ring, on any
# shafts - takes Flip False. What the mate keeps as IGearMateFeatureData.Reverse is
# about the selected axes' own senses instead: Flip, reversed once for opposed axes
# and once for a ring (with a face, its own sense). Two of the layout's own axes
# were refused as a gear mate's entities (AddMate5 returned nothing, status 0).
# What would break this: a pair SolidWorks cannot tell is inside a ring, which a
# meshing pair is not (the pinion's axis is inside the ring's bore, an external
# partner's outside the other gear); geometry not loaded (lightweight components) is
# untried.
GEAR_MATE_FLIP_RULE = "mesh"
GEAR_MATE_FLIP = False

# compound_lock: two cylinders on one layout axis, the second placed turned 37° (or
# 137°) from the first, the first driven 30° then 90° more. A LOCK mate
# (AddMate5(swMateLOCK) on the two components, each selected by IComponent2.Select4
# with a mark-1 select data) between the second and the first, the second not mated to
# the axis itself, held 37° through both drives on Z+ and on Z-, the second on the axis
# and with no mate error. With the second ALSO on the axis and along it, the lock held
# too, but its axial mates (and on Z- its axis mate) were flagged (GetErrorCode2 46,
# swFeatureErrorMateOverdefined, as a warning; on Z- both components read
# GetConstrainedStatus 4), so a locked gear is not mated to its shaft as well. An
# angle mate between the two Top planes at the placed angle held 37° and 137° without
# error; a 1 : 1 gear mate between the two axes held with Flip off and slipped with it
# on (a coaxial pair is read as one gear inside the other).
COMPOUND_LOCK_ROUTE = "lock alone"
# How an over-defined assembly shows (the same pair given a second angle mate 10°
# off the first): AddMate5's status out-parameter is 5
# (swAddMateError_OverDefinedAssembly) but the mate IS made; that mate's
# GetErrorCode2 is 47 (swFeatureErrorMateIlldefined, not a warning) and the mates it
# fights read 46 (overdefined, warning); the over-defined component's
# GetConstrainedStatus is 4; IModelDocExtension.GetWhatsWrongCount rose (6 to 8, and
# GetWhatsWrong, given three by-reference variants, named them); and ForceRebuild3
# still returns True. Deleted (Select2, then DeleteSelection2(0)), its errors went and
# the status was 3 again. SolidWorks 2024 flagged exactly the same mates, the same
# warnings and the same status, but GetErrorCode2 gave 51 for every one of them (the
# number swconst calls swSketchErrorExtRefFail) where 2026 gave 46, 47 and 1. So a
# build checks AddMate5's status, treats any non-zero GetErrorCode2 as a mate problem
# and IsWarning False as the mate at fault, and never reads meaning into the number;
# the rebuild's result says nothing.
ADD_MATE_OVER_DEFINED = 5        # swAddMateError_e.swAddMateError_OverDefinedAssembly
MATE_ERROR_OVER_DEFINED = 46     # swFeatureError_e.swFeatureErrorMateOverdefined (a warning); 2026 only
MATE_ERROR_ILL_DEFINED = 47      # swFeatureError_e.swFeatureErrorMateIlldefined; 2026 only
MATE_ERROR_2024 = 51             # what 2024 gave for each of the same mates
COMPONENT_OVER_DEFINED = 4       # IComponent2.GetConstrainedStatus, swConstrainedStatus_e
COMPONENT_FULLY_DEFINED = 3
COMPONENT_UNDER_DEFINED = 2

# mated_train: the 12 : 1 reducer (17/68 + 17/51) twice, all shafts Z+ and the middle
# shaft Z-, nine components: placed turned and fixed as W4 leaves them, then each gear
# unfixed and mated by the routes above (the second gear of each compound shaft locked
# to the first and not mated to its axis), the two gear mates with Flip False, and no
# gear moved (0 mm, 0 rotation). Every gear read GetConstrainedStatus 2 (under-defined)
# until one angle mate drove the input, which made all of them 3 (fully defined): the
# train has one degree of freedom. Driven 30°, each output turned 2.5° the same way as
# its input, 1/12, on both trains; saved, reopened (the same mates, no errors, every
# gear where it was) and driven again, the same. A gear mate follows the SOLVER, not a
# transform: turning the input by a Transform2 put, SetTransformAndSolve2 or
# IDragOperator (Drag or DragAsUI, every call answering True) turned the input alone,
# and a Transform2 put on the output turned it alone while the input stayed driven;
# IDragOperator's TransformType 1 and 2 and DragMode 0, 1 and 2 did no better. So no
# API drag reproduces a mouse drag, and W5's demonstrable (drag the input in
# SolidWorks) is seen by a person; the one degree of freedom and the 1/12 are
# measured here through the solver. The same on 2024.
MOTION_ROUTE = "mates"

# motion_update: the saved train, its output shaft swung 20° round the compound shaft
# by the layout part's two globals (the layout opened by path, activated, rebuilt; then
# the assembly rebuilt): the output gear went with its axis, nothing else moved, no
# mate error, and the train still turned 1/12. SolidWorks turned the output about +Z
# by -(1 + 17/51)·20° as its shaft swung, the opposite of the +(1 + 17/51)·20° staying
# in mesh needs, so after any move the app puts each gear back to the frame
# workbook.layout.frames gives. A Transform2 put turning the output with its gear mate
# on was kept (the rest of the train did not move) and the train then turned 1/12 from
# there: the gear mate takes the new phase. Suppressing the gear mate around the put,
# then unsuppressing it, kept the new phase too. A compound lock suppressed
# (SetSuppression2, this configuration), its second gear turned 11° by a put, and
# unsuppressed, held the new 11° through a drive. The output's axial distance mate
# (D1) linked to an assembly global and the global changed moved the gear along its
# shaft alone.
LAYOUT_MOVE_CARRIES_MATES = True
MESH_PHASE_ROUTE = "Transform2 put with the gear mate on"
LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE = True
AXIAL_GLOBAL_MOVES_GEAR = True
