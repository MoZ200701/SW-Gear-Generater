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
# still returns True. Deleted (Select2, then EditDelete(), as compound_lock's
# over_defined.deleted_by records; W5-PROBE-REPORT's "DeleteSelection2(0)" was a
# misstatement, and DeleteSelection2 was never reached), its errors went and
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

# -- what W5 takes from tier 8, and tier 8 items 7-13 (W5-PLAN §0.3, package P0) --
#
# Six values read off tier 8's records as they stand (no new probe): motion_enums'
# motion_enum_values from swconst.tlb, the route motion_update suppressed and
# unsuppressed both its gear mate and its compound lock by (judged by IsSuppressed2),
# how compound_lock selected both components of every lock it made, and how it deleted
# the mate it over-defined the assembly with. Each matches W5-PLAN §0.3's text, in
# 2026's full runs and every 2024 file alike.
FEATURE_SUPPRESS = 0        # swFeatureSuppressionAction_e.swSuppressFeature
FEATURE_UNSUPPRESS = 1      # swFeatureSuppressionAction_e.swUnSuppressFeature
THIS_CONFIGURATION = 1      # swInConfigurationOpts_e.swThisConfiguration
SUPPRESSION_ROUTE = "SetSuppression2 this configuration, None"
LOCK_SELECT_ROUTE = "Select4 with a mark-1 select data"
MATE_DELETE_ROUTE = "Select2 then EditDelete()"

# Items 7-15, as probe round P0b left them (W5-DECISIONS, "Rulings on package P0's findings"), observed on
# SolidWorks 2026 (34.1.1: latest.json, a full run, probe-results-20261114-081921, 85 of 85) and 2024 (32.5.0,
# each in a SolidWorks started fresh for it: sw2024/probe-results-20261114-071324, items 7-14 and what they
# need, and sw2024/probe-results-20261114-073328, gear_mate_definition alone), every snapshot the app as of
# 64f4620 with the probes as of 4ced012, on 2026-11-14. Every decision is the same on both versions. Items
# 7, 8-11 each work on their own on-disk copy of the 12 : 1 train mated_train saved (all Z+, and with a Z-
# middle shaft); 7b and 13 build their own; each
# rebuilds with ForceRebuild3(True) as Update will, except where item 13 compares the routes. The earlier files
# (P0: latest.json's predecessors, sw2024/...-040636 and -051023) are kept: the 2024 ones ran beside an assembly
# the definition route had stranded.
#
# gear_mate_ratio (P1): the output's gear mate (17 : 51, made by AddMate5 with the first
# selection's count first) deleted (MATE_DELETE_ROUTE) and made again by AddMate5 between the
# two components found by GetComponentByName, at (17, 60), Flip False, given its old name: the
# output turned 17/60 of its partner (input 30°, output 2.125°, the other train still 2.5°),
# saved, closed, reopened, the same, closed; on both versions, the 2024 one in a clean
# session. The remade mate went to the end of the mate group (8th of 20 before, last after)
# and is found by its name all the same.
# gear_mate_update (P1b): an Update's whole tooth change, on W4's 12 : 1 reducer built by the
# app (assess, plan_gearbox, build_gearbox) and mated here as W5 will (anchors G1, G2, G4 on
# their axes and along their shafts, G4's distance on "G4 Face Z", G3 locked to G2, two gear
# mates, D12's names; the mate check clean, 1/12, no interference): G3 17 -> 18 and G4 51 -> 50
# (the same 68 mm centre distance) by swbuild.update_variables in each part's own document;
# every lock suppressed; "G3 meshes G4" deleted, made again at 18 : 50 and given its old name;
# every gear put to its new built frame (workbook.layout.frames); the locks back on; a top-only
# rebuild; the mate check clean, every gear at its frame to 1e-6, the train driven 30° (the
# demonstration's 90° drive) turning G4 2.7° (17/68 x 18/50) the same way and every gear back
# at its frame after, no interference at the built phase, and a full rebuild afterwards moving
# nothing. Closed without saving the assembly (the parts set back first, since the probe saves
# its parts on closing) and reopened: as it was saved, 17 : 51, the same frames and mates.
# Again, saved: reopened with 18 and 50 teeth, the frames, a clean check, 2.7° and no
# interference. The same on both versions. So D7 may be an Update, by the remake.
# The definition route (gear_mate_definition, last in the tier, recorded and never chosen):
# GetDefinition reads the counts the other way round from AddMate5 (GearRatioNumerator 51, the
# SECOND selection's), but the fields take them in AddMate5's order: 17 in GearRatioNumerator
# and 60 in GearRatioDenominator turned the train 17/60 and read back 60 : 17 (P0's 2026 full
# run also showed 60 in the field that read 51 inverting the ratio). On 2026 that copy closed;
# on 2024 it could not be closed: CloseDoc raised 0x80010105 ("the server threw an exception")
# and then, like QuitDoc, left it open without a word, holding the train's layout and part
# (sw2024/...-040636, -051023 and sw2024/probe-results-20261114-073328). AccessSelections does not exist on this
# definition (AttributeError).
GEAR_MATE_RATIO_ROUTE = "remake"
GEAR_MATE_RATIO_REMAKE_WORKS = True                 # on both versions, closing included
GEAR_MATE_UPDATE_HOLDS = True                       # P1b: the whole tooth change as an Update
REMADE_GEAR_MATE_GOES_LAST = True                   # in the mate group; found by name all the same
MODIFIED_GEAR_MATE_CLOSES_ON_2024 = False           # after ModifyDefinition on a gear mate
GEAR_MATE_RATIO_PUT_NUMERATOR_FIRST = True          # put: numerator = the first selection's teeth
GEAR_MATE_DEFINITION_READS_NUMERATOR_SECOND = True  # read: numerator = the second selection's teeth

# lock_retake_offset (P2): each compound lock suppressed (SUPPRESSION_ROUTE), its second
# gear put 3 mm along its own axis and 11° round, the lock unsuppressed and rebuilt: the
# second gear kept 11° and 3 mm against the first, on its axis, after the lock came back
# and after the anchor turned -7.5° under a drive, on the Z+ and the Z- compound shaft,
# no mate error. So a follower's At or face-width change is an Update (D8): the lock
# re-takes whatever relative frame it finds, along the shaft as well as round it.
LOCK_RETAKES_AN_OFFSET = True

# lock_mate_rename (M4a): a lock, a gear mate, an axis (coincident) mate, an axial
# distance mate, and the other train's lock suppressed first, renamed by an IFeature.Name
# put to "TG3 locked to TG2", "TG3 meshes TG4", "TG4 on T3 Axis", "TG4 along T3" and
# "UG3 locked to UG2": each read its new name back; nothing moved, and no mate's type,
# suppression or error code changed. Saved, closed, reopened: each was found by its new
# name through the MateGroup's sub-features and by IModelDoc2.FeatureByName, no old name
# was left, each was still its kind (IMate2.Type 16, 10, 0, 5, 16), the suppressed lock
# still suppressed and the others not; driven, the renamed lock held, the renamed gear
# mate turned the output 1/12, the renamed axis and axial mates held it; the suppressed
# lock, turned back on by its new name, held. So Update finds mates by W5's names.
MATE_RENAME_ROUTE = "IFeature.Name put"
MATE_FIND_ROUTE = "mate group"

# demonstration_drive (M4b): with tier 8's drives suppressed and each input put at its
# built phase (θ = 0), an angle mate from the input's Top plane to the layout's Right
# plane at 90°, its dimension linked to an assembly global, moved no gear and made every
# gear fully defined; the global 90 -> 120 turned each input +30° about +Z and each output
# +2.5°, on both trains; back to 90 every frame was where it was built (to 1e-13), and with
# the link equation and global deleted (IEquationMgr.Delete) and the angle mates deleted
# (MATE_DELETE_ROUTE) every frame still was, no mate error, every gear under-defined again.
# The 90° geometry behaves as tier 8's 10° -> 40° drive between Top planes did.
DEMONSTRATION_DRIVE_HOLDS = True
DEMONSTRATION_DRIVE_SENSE = 1    # the input (on Z+) turns +θ about +Z as the angle grows

# put_on_twice_meshed_gear (M4c): tier 8's records covered a put on the driven output
# (motion_update put_with_gear_mate_on), on the undriven input (mated_train dragged
# "Transform2 put") and on a follower under a suppressed lock in a driven train
# (lock_moved), not this. In the undriven train, every lock suppressed, rebuilt, the put,
# every lock unsuppressed and rebuilt (W5-PLAN §1.6 step 6): the compound anchor TG2
# (meshing TG1, locked to TG3 which meshes TG4) put 7° round held to 1e-6, nothing else
# turned and its lock took the new angle; every gear put back to where it started was
# there after the locks came back; TG4 joined to the other train's input by one more gear
# mate, so it carries two, put 9° round held and nothing else turned; no mate error, every
# gear under-defined, and one drive then made all eight fully defined and turned them as
# one train. Recorded beside it (lock_on_put_turns): a put on TG2 with its lock ON held too,
# TG3 did not follow and no mate reported an error. Then driven (lock_on_put_after_drive, P0b):
# TG2 and TG3 both turned -2.5° and their relative angle stayed where the put left it, no
# error: the lock takes the relative frame it finds, so a put with a lock on silently changes
# the pair's relation, which is why W5 puts only with every lock suppressed (M1, M8).
# The remake on a gear carrying two gear mates (P0b): TG3-TG4 deleted and made again at 17 : 60
# under suppressed locks and given its old name, while TG4 also carried the gear mate to the
# other train: found by its name and the other mate by its own, the joined train turning at the
# new ratio through both (UG1 -2.125° for TG1's 10°); the remade mate went to the end of the
# mate group (8th of 21 before, last after). The same on both versions.
PUT_ON_TWICE_MESHED_GEAR_HOLDS = True
LOCK_RETAKES_AFTER_A_PUT = True                     # with the lock on: the pair's new relation is kept
REMAKE_ON_TWICE_MESHED_GEAR_HOLDS = True

# axial_datum_plane (M5): a plane in the layout part offset 1000 mm from Front with the
# flip bit (REF_PLANE_UNFLIPPED_IS_PLUS_Z: it landed at z = -1000, facing +Z), and an
# anchor on Z+ and one on Z-, each held by AXIS_MATE_ROUTE and by a distance from its
# origin (Point1@Origin) to that plane, Flip False (no anchor moved when mated), the
# distance linked to an assembly global. The global at 1000, 995 and back to 1017 put both
# origins at z = 0, -5 and 17 (through where the Front plane is, with no flip change),
# on their axes; both read under-defined, no mate error, and their 20 : 40 gear mate drove
# GB -15° for GA's 30°. Saved, reopened: where they were, moved to z = 8 by the global,
# and turning. So a datum plane far behind Front would remove D8's Front-plane cases (an
# anchor's front face reaching, leaving or crossing Front would be a global's new value).
# The user declined that route on 2026-11-14: W5 keeps the Front plane as the axial
# reference (W5-PLAN D8), and nothing is built on these two values; they stay as a record.
AXIAL_DATUM_ROUTE = "origin distance from a datum plane"
AXIAL_DATUM_FLIP = False

# mated_rebuild_scope (as probe round P0b rebuilt it): each route built its own train from its
# own layout part and gear part, with that route as its only assembly rebuild (Transform2 puts,
# then the route; mates; the output's axial distance on "TG4 Face Z"; the drive), and every
# build passed W5-PLAN §1.4's mate check (18 AddMate5 statuses 1, no mate error, every gear
# under-defined), one drive made every gear fully defined, both trains turned 1/12 the same
# way, and its frames were the full rebuild's build's to 1e-13. The full rebuild's build left
# its layout and part modified; the top-only and EditRebuild3 builds left them unmodified.
# Saved, closed, reopened (every document read GetSaveFlag False), each train took six changes
# under its route, each read once between the change and the route and once after it:
# - shown only by the route: the axial global +4 mm (0 before, 4 after) and the drive +30°
#   (nothing turned before, 1/12 after); and the compound anchor put 7° under its suppressed
#   lock held after the lock came back and the route (judged then: a reading straight after a
#   Transform2 put is the put's own value);
# - shown before any route (recorded, not counted): the output shaft moved in the layout's own
#   document (it had moved once ActivateDoc3 brought the assembly back), the gears' part's OD
#   (the volume read new before the route, though a mass property may itself update what it
#   measures), and the conflicting angle mate's errors (AddMate5 solves: status 5, errors 47 /
#   46 on 2026, 51 on 2024, before and after the route; deleted, cleared before the route).
#   No route returned False with the mate error;
# - driven 30° after the put, after the layout move and after the part change, under the route:
#   both trains 1/12, the put's lock angle kept, the output on its moved axis; every frame
#   the full rebuild's train's to 1e-13.
# ForceRebuild3(True) and EditRebuild3 marked exactly the documents changed on purpose at every
# step; ForceRebuild3(False) marked the layout and the part at the first step. NeedsRebuild and
# NeedsRebuild2 read True / 1 after an assembly global changed and False / 0 after every route;
# after a change in the layout's or the part's own document they read False / 0 before the
# route, on both versions. The P0 file's two 2024 differences (the layout move not shown before
# the route; NeedsRebuild True / 1 there) did not recur in a clean 2024 session: they were the
# stranded assembly's. So a train is built and changed with the top-only rebuild.
# What it was measured on, and so what it covers: the workbook TRAIN as W5 builds it, every
# gear's Gear Axis coincident with its layout "<Shaft> Axis", each anchor's origin a distance
# from the layout's Front plane (the output's linked to an assembly global), compound gears held
# by a lock mate alone, external gear mates (Flip False), and an angle mate between Top planes
# driven by an assembly global. It does NOT cover a gear-PAIR assembly (swbuild.build_pair, the
# p5 half-pitch controls): their centre-distance equation, mesh or shaft-angle mates and point
# mates were not measured here, and pairs keep the full rebuild.
MATED_ASSEMBLY_REBUILD_ROUTE = "ForceRebuild3(True)"
MATED_REBUILD_KEEPS_COMPONENTS_UNMODIFIED = True
MATED_BUILD_REBUILD_ROUTE = "ForceRebuild3(True)"      # building the train, with nothing else
MATED_BUILD_KEEPS_COMPONENTS_UNMODIFIED = True

# -- probe round P0c: what W5's build and Update code do that no probe had done -------------
# Evidence: probe/results/probe-results-20261114-095421.json (2026) and
# probe/results/sw2024/probe-results-20261114-102300.json (2024), each in a SolidWorks started
# fresh for it. The same on both versions except where a line says otherwise.

# gear_mate_update and idler_update (P1b, the review's additions). On W4's 12 : 1, every pass
# also read interference at the old frames before the put (4 clashes) and with G4 put half a
# pitch off its new phase (4), then 0 after the put: the interference reading tells. A train
# with an idler (17/30/40 -> 15/32/38, module 2, no shaft moved), built by the app and mated as
# W5 does, carried the change as an Update. Both of the idler's gear mates were deleted, made
# again at the new ratio and given their old names (found by name; they were last in the mate
# group already and stayed there). Every gear stood at its new built frame to 8e-15. The check
# was clean and a full rebuild moved nothing. Driven 30°, G2 turned -14.0625° and G3 +11.842°.
# Interference was 0 after the put. At the old frames it was 0 too (a changed phase can happen
# to clear), and with G2 half a pitch off it was 6, so the half-pitch reading is the control.
# Closed unsaved and reopened, the train was as saved (17/30/40, the old definitions); saved and
# reopened, it had 15/32/38, ratios 32 : 15 and 38 : 32, the same turns and no interference.
IDLER_UPDATE_HOLDS = True
UPDATE_INTERFERENCE_CONTROL_HOLDS = True        # a gear half a pitch off clashes; at its built phase none

# unsaved_update_close: after an unsaved Update (G3 and G4 changed in their own documents, the
# assembly updated, nothing saved: the assembly and both parts GetSaveFlag True), CloseDoc on
# the assembly returned at once (0.34 s) with no window opened. The two parts stayed open,
# still modified, and CloseDoc on each closed it silently. On disk afterwards nothing had been
# written and the parts still had their saved teeth. QuitDoc did exactly the same. On 2024 too:
# no "Save Modified Documents" here. That dialog (scaffold.save_created_parts, 2026-11-02) came
# from parts modified while loaded only as components, not from parts open in their own
# windows, as Update opens them.
UNSAVED_UPDATE_CLOSE_ASKS = False
UNSAVED_UPDATE_CLOSE_DISCARDS = True            # CloseDoc and QuitDoc alike, assembly first then each part

# gear_mate_definition_read: the saved 12 : 1 reopened, every document GetSaveFlag False. Each of
# its two gear mates read as the app's Update check reads it (IFeature.GetDefinition, then
# GearRatioNumerator and GearRatioDenominator, the object released; no ModifyDefinition, no
# AccessSelections), both in one session. The reads gave 68 : 17 and 50 : 18 (numerator the
# second gear's). Every flag stayed False after the get, after the reads and after the release,
# and the train then closed with nothing left. So an Update with nothing to do may read the
# ratios and still change nothing.
GEAR_MATE_DEFINITION_READ_MARKS = "nothing"

# origin_noise: each gear's origin read at full precision before and after ForceRebuild3(True)
# moved 0.0 mm after nothing, after a part's teeth changed by its globals, and after another
# shaft moved 1 mm by its layout global. That shaft's own gear had moved its full 1 mm by the
# first read, once the assembly was active again. After the temporary drive was added, driven,
# set back and taken away it also moved 0.0 mm; from before the drive to after it, the largest
# move was 2.8e-14 mm. So the app's 1e-6 mm "moved" tolerance sits eight orders above the noise.
ORIGIN_NOISE_MM = 0.0                           # around a top-only rebuild, every case
ORIGIN_NOISE_AFTER_A_DRIVE_MM = 2.8474599777423056e-14   # from before the drive to after its removal

# mates_under_command_in_progress: with ISldWorks.CommandInProgress True, the whole W5 mate set
# (18 AddMate5 calls) answered status 1, every mate code 0, every gear under-defined, none moved,
# one drive defined it and it turned 1/12. A conflicting angle mate under it answered status 5
# with the codes P0b saw (47 / 46 on 2026, 51 on 2024). Each mate renamed straight after its
# AddMate5, in a new unsaved assembly, read its new name back at once and was found by it; saved
# and reopened, every mate was found by its new name and no first name was left.
# SetSuppression2(unsuppress) on a lock already on returned True, left it on, raised no error,
# and marked the assembly modified. Suppressed, a sound lock and a conflicting angle mate both
# read GetErrorCode2 0 with the warning flag False.
MATES_UNDER_COMMAND_IN_PROGRESS = True
MATE_RENAME_AT_ONCE = True
UNSUPPRESS_ON_LOCK_ALREADY_ON_MARKS_MODIFIED = True
SUPPRESSED_MATE_ERROR_CODE = 0                  # warning flag False, whatever the mate would report on

# mate_folders: IFeatureManager.InsertFeatureTreeFolder2(swFeatureTreeFolder_Containing = 2) with
# two mates selected made a folder in the mate group. The MateGroup walk then lists the folder
# (GetTypeName2 "FtrFolder"), the mates inside it as ordinary following siblings, and an end
# marker "Folder1___EndTag___" (also "FtrFolder"). FeatureByName finds a mate inside it. Every
# type met: FtrFolder, MateCoincident, MateDistanceDim, MateGearDim, MateLock,
# MatePlanarAngleDim. A walk that keeps only types starting with "Mate" skips both folder
# entries and still sees every mate.
MATE_FOLDER_ROUTE = "IFeatureManager.InsertFeatureTreeFolder2(swFeatureTreeFolder_Containing)"
MATE_FOLDER_TYPE_NAME = "FtrFolder"
MATE_GROUP_WALK_SEES_MATES_IN_A_FOLDER = True

# lightweight_remake: OpenDoc6 with swOpenDocOptions_LoadLightweight (128) alone left every
# component swComponentFullyResolved. Adding swOpenDocOptions_OverrideDefaultLoadLightweight
# (64) made all eight swComponentLightweight. On both versions the SOLIDWORKS CAM add-in then put
# up a modal "SOLIDWORKS CAM Error" box ("...loading of lightweight parts has been detected"),
# which blocks OpenDoc6 until it is closed: the probe's watch closed it with WM_CLOSE. Lightweight,
# a component's "Gear Axis" was found, the remake made the gear mate (status 1, no error), and
# the train turned at the new ratio (TG4 2.125° for 30°). Every component was fully resolved
# afterwards. W5 does not open lightweight; if it ever does, the add-in's box must be expected.
LIGHTWEIGHT_FORCED_BY = "swOpenDocOptions_LoadLightweight | swOpenDocOptions_OverrideDefaultLoadLightweight"
LIGHTWEIGHT_REMAKE_HOLDS = True
LIGHTWEIGHT_OPEN_RAISES_AN_ADDIN_DIALOG = True  # SOLIDWORKS CAM, modal, on this machine's install

# second_assembly_beside_unsaved: a new assembly left open and unsaved ("Assem20"), holding a
# component of a saved part with its mate. A second new assembly ("Assem21") from the same part
# took the same component name, its mate, and saved to its path under the file's name. There
# was no dialog, no refusal and no name clash, and both closed afterwards.
SECOND_ASSEMBLY_BESIDE_UNSAVED_HOLDS = True

# drag_operator_turns_train (optional): the saved 12 : 1 train, its drives suppressed, dragged by
# SW-Macro-Database entries/assemblies/05's recipe: AddComponent(gear, False), TransformType 0,
# UseAbsoluteTransform False, DragMode left at 3, BeginDrag, Drag with a relative turn per step
# about the gear's own axis, EndDrag. It was dragged 10°, since 30° on the output would turn the
# input 360°. Every Drag returned True. The output (10 steps, the entry's success; then 1 and 30
# steps), the input and the compound follower each turned exactly 10° and every other gear 0°.
# No mate reported an error, nothing was left selected and CommandInProgress read False. Not
# varied: the mate holding a gear to its axis (W5's axis coincident; the entry's held case was
# concentric to sketch points). So the demonstration keeps its temporary driving mate.
DRAG_OPERATOR_TURNS_TRAIN = False
