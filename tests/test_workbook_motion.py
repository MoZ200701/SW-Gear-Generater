"""The workbook gearbox that turns: its mates' names and shapes, and the plan that makes them (W5,
``workbook/motion.py``).

The interface commit wrote the names and the record's mirror; the planning tests below are W5-PLAN §3.2's B list
as the review (M2, M9, M13) and W5-DECISIONS amend it: the three Windows fixtures' anchors, locks, gear mates and
globals, the mesh signs against kinematics, loops, fixed and still shafts, trains, the op order, and the findings.
"""

import dataclasses

import pytest

from gear_generator import store, swbuild
from gear_generator.workbook import motion
from gear_generator.workbook.motion import ALONG, AXIS, LOCK, MESH, MatePlan


@pytest.mark.parametrize("kind,gears,shaft,name", [
    (AXIS, ("G1",), "S1", "G1 on S1 Axis"),
    (ALONG, ("G4",), "S3", "G4 along S3"),
    (LOCK, ("G2", "G3"), "", "G3 locked to G2"),
    (MESH, ("G1", "G2"), "", "G1 meshes G2"),
    (MESH, ("Ring_1", "P-2"), "", "Ring_1 meshes P-2"),
])
def test_each_mate_is_named_as_the_user_reads_it_in_the_tree(kind, gears, shaft, name):
    assert motion.mate_name(kind, gears, shaft) == name


@pytest.mark.parametrize("kind,gears,shaft", [("angle", ("G1", "G2"), ""), (AXIS, ("G1",), ""),
                                              (ALONG, ("G1", "G2"), "S1"), (LOCK, ("G2",), ""),
                                              (MESH, ("G1", "G2"), "S1"), (MESH, ("G1", ""), "")])
def test_a_mate_that_cannot_be_named_is_refused(kind, gears, shaft):
    with pytest.raises(ValueError):
        motion.mate_name(kind, gears, shaft)


def test_an_anchors_distance_is_a_global_named_for_the_gear():
    assert motion.face_global("G4") == "G4 Face Z"
    with pytest.raises(ValueError):
        motion.face_global("")


def test_the_record_mirrors_a_mate_field_for_field():
    plans = [MatePlan("G4 along S3", ALONG, ("G4",), "S3", face_global="G4 Face Z", z_front=17.0),
             MatePlan("G1 meshes G2", MESH, ("G1", "G2"), ratio=(17, 68)),
             MatePlan("G3 locked to G2", LOCK, ("G2", "G3"))]
    assert [f.name for f in dataclasses.fields(MatePlan)] == [f.name for f in dataclasses.fields(store.MateEntry)]
    for plan in plans:
        entry = motion.mate_entry(plan)
        assert isinstance(entry.gears, list) and isinstance(entry.ratio, list)
        assert {k: (tuple(v) if isinstance(v, list) else v) for k, v in dataclasses.asdict(entry).items()} == \
            dataclasses.asdict(plan)
        assert motion.mate_ref(entry) == swbuild.MateRef(plan.name, plan.kind, plan.gears, plan.shaft)
    assert store.link_record_from_json(store.link_record_to_json(store.LinkRecord(gearbox=store.GearboxRecord(
        kind=motion.MOTION, mates=[motion.mate_entry(p) for p in plans])))).gearbox.mates == [
        motion.mate_entry(p) for p in plans]


def test_the_kinds_of_gearbox_are_the_records_words():
    assert (motion.STATIC, motion.MOTION) == (store.GEARBOX_STATIC, store.GEARBOX_MOTION) == ("static", "motion")


# -- planning (W5-PLAN §3.2 B, with review M2, M9 and M13) -------------------------------------------------------

import os  # noqa: E402
from fractions import Fraction  # noqa: E402

from gear_generator import findings  # noqa: E402
from gear_generator.gears import kind_for, plan_for  # noqa: E402
from gear_generator.gears.base import (AddComponent, AddGlobal, Axis, Fix, LinkDimension, Mate,  # noqa: E402
                                       NewAssembly, Place, Rebuild, SaveAs, Unfix)
from gear_generator.gears.spur import AXIS_NAME  # noqa: E402
from gear_generator.workbook import assess, checks, kinematics, layout, link  # noqa: E402
from gear_generator.workbook.geometry import Layout, Placed  # noqa: E402
from gear_generator.workbook.model import Box, Gear, GearboxSpec, Mesh, Shaft  # noqa: E402
from test_workbook_geometry import FACINGS, outside_pair, ring_pair  # noqa: E402
from test_workbook_model import reducer  # noqa: E402

WINDOWS = os.path.join(os.path.dirname(__file__), "fixtures", "excel-windows")


@pytest.fixture(autouse=True)
def settled_findings(monkeypatch):
    """The findings a probe round may still change, pinned (none of these tests leans on the committed value)."""
    for name, value in {"GEAR_MATE_RATIO_ROUTE": None, "LOCK_RETAKES_AN_OFFSET": True,
                        "MATED_ASSEMBLY_REBUILD_ROUTE": "ForceRebuild3(True)",
                        "MATED_BUILD_REBUILD_ROUTE": "ForceRebuild3(True)",
                        "GEAR_MATE_RATIO_REMAKE_WORKS": True,
                        "GEAR_MATE_DEFINITION_READ_MARKS": "nothing", "MATES_UNDER_COMMAND_IN_PROGRESS": True,
                        "MATE_RENAME_AT_ONCE": True, "IDLER_UPDATE_HOLDS": True}.items():
        monkeypatch.setattr(findings, name, value, raising=False)


def windows(name):
    """One of the three workbooks of W4's Windows demonstration, read and assessed: (spec, report, frames)."""
    reading = link.Link(os.path.join(WINDOWS, name)).read()
    assert reading.ok, reading.error
    a = assess.assess(reading.spec, reading.diagnostics, reading.spec.box.output_folder,
                      reading.spec.box.part_template)
    assert a.lay_out_refusal() == ""
    return a.spec, a.report, layout.frames(a.report)


def planned(name):
    spec, report, frames = windows(name)
    return motion.motion_plan(spec, report, frames)


def kinds(plan, kind):
    return [m for m in plan.mates if m.kind == kind]


def test_the_12_to_1_reducer_is_mated_through_g1_g2_and_g4():
    plan = planned("Reducer_12to1.xlsx")
    assert dict(plan.anchors) == {"S1": "G1", "S2": "G2", "S3": "G4"}
    assert [m.name for m in plan.mates] == [
        "G1 on S1 Axis", "G1 along S1", "G2 on S2 Axis", "G2 along S2", "G3 locked to G2", "G4 on S3 Axis",
        "G4 along S3", "G1 meshes G2", "G3 meshes G4"]
    assert [(m.gears, m.ratio) for m in kinds(plan, MESH)] == [(("G1", "G2"), (17, 68)), (("G3", "G4"), (17, 51))]
    assert [m.gears for m in kinds(plan, LOCK)] == [("G2", "G3")]
    assert [(m.gears[0], m.face_global, m.z_front) for m in kinds(plan, ALONG)] == [
        ("G1", "", 0.0), ("G2", "", 0.0), ("G4", "G4 Face Z", 17.0)]
    assert (plan.fixed, plan.unmated, plan.trains, plan.drag) == ((), (), (("S1", "S2", "S3"),), ("G1",))


def test_risky_placements_holds_its_z_minus_anchors_and_its_ring_at_their_distances():
    plan = planned("Risky_Placements.xlsx")
    assert dict(plan.anchors) == {"S1": "G1", "S2": "G2", "S3": "G4", "S4": "G6"}
    assert [(m.gears[0], m.face_global, m.z_front) for m in kinds(plan, ALONG)] == [
        ("G1", "", 0.0), ("G2", "G2 Face Z", 10.0), ("G4", "G4 Face Z", 18.0), ("G6", "G6 Face Z", 50.0)]
    assert [m.gears for m in kinds(plan, LOCK)] == [("G2", "G3"), ("G4", "G5")]
    assert [m.gears for m in kinds(plan, MESH)] == [("G1", "G2"), ("G3", "G4"), ("G5", "G6")]
    assert (plan.trains, plan.drag, plan.fixed, plan.unmated) == ((("S1", "S2", "S3", "S4"),), ("G1",), (), ())


def test_arc_move_holds_only_g4_at_a_distance():
    plan = planned("Arc_Move.xlsx")
    assert dict(plan.anchors) == {"S1": "G1", "S2": "G2", "S3": "G4"}
    assert [(m.gears[0], m.face_global, m.z_front) for m in kinds(plan, ALONG) if m.face_global] == [
        ("G4", "G4 Face Z", 15.0)]


def test_each_mesh_turns_its_second_gear_at_the_solved_speeds_ratio_about_its_own_axis():
    """Review M2: k == ω_b/ω_a with kinematics' speeds, each about its own shaft's axis; the Risky signs pinned."""
    expected = {"Reducer_12to1.xlsx": [-0.25, -0.333333], "Arc_Move.xlsx": [-0.818182, -0.73913],
                "Risky_Placements.xlsx": [0.7, 0.636364, -0.388889]}
    for name, ks in expected.items():
        spec, report, _ = windows(name)
        placed = report.layout.placed
        links = motion.mesh_links([(m.a, m.b) for m in spec.meshes], {g: p.teeth for g, p in placed.items()},
                                  {g: p.sigma for g, p in placed.items()}, {g: p.internal for g, p in placed.items()})
        assert [round(link_.k, 6) for link_ in links] == ks, name
        speeds = report.motion.speeds
        for link_ in links:
            assert link_.k == pytest.approx(float(speeds[placed[link_.b].shaft] / speeds[placed[link_.a].shaft]))
            assert link_.pitch == pytest.approx(360 / placed[link_.b].teeth)


@pytest.mark.parametrize("facing", FACINGS)
@pytest.mark.parametrize("make", [outside_pair, ring_pair])
def test_mesh_link_signs_agree_with_kinematics_outside_and_in_a_ring_on_every_facing(make, facing):
    """The built turn δ_i = 30°·ω_i/ω_in about each gear's own axis (M2), for both orders of each mesh."""
    spec = make("spur", facing)
    report = checks.check(spec)
    assert report.errors == []
    placed, speeds = report.layout.placed, report.motion.speeds
    teeth = {g: p.teeth for g, p in placed.items()}
    sigma = {g: p.sigma for g, p in placed.items()}
    internal = {g: p.internal for g, p in placed.items()}
    a, b = spec.meshes[0].a, spec.meshes[0].b
    for x, y in ((a, b), (b, a)):
        (link_,) = motion.mesh_links([(x, y)], teeth, sigma, internal)
        assert link_.k == pytest.approx(float(speeds[placed[y].shaft] / speeds[placed[x].shaft]))
        ring = internal[x] or internal[y]
        assert (link_.k > 0) == (ring == (sigma[x] == sigma[y]))
    assert motion.lock_links([("G2", "G3")], {"G2": 68, "G3": 17}) == (swbuild.LockLink("G2", "G3", 360 / 17),)


def made_up(shafts, gears, meshes, face=10.0):
    """A gearbox planned without laying it out: ``shafts`` (id, axis, role, speed), ``gears`` (id, shaft, teeth,
    side, z_front). Returns (spec, report, frames) with kinematics' own speeds, as motion_plan reads them."""
    spec = GearboxSpec(box=Box(name="T"),
                       shafts=tuple(Shaft(s, "frame", "0", "0", "0", axis, role, "", speed)
                                    for s, axis, role, speed in shafts),
                       gears=tuple(Gear(g, s, "0", "spur", side, str(z), "2", face_width=str(face))
                                   for g, s, z, side, _ in gears),
                       meshes=tuple(Mesh(x, y) for x, y in meshes))
    sigma = {s: (1 if axis == "Z+" else -1) for s, axis, _, _ in shafts}
    placed = {g: Placed(gear=g, shaft=s, x=0.0, y=0.0, z=zf + sigma[s] * face / 2, sigma=sigma[s], face=face,
                        teeth=z, module=2.0, internal=side == "internal", derived=None)
              for g, s, z, side, zf in gears}
    report = checks.Report(layout=Layout(placed=placed), theta={g: 0.0 for g in placed},
                           motion=kinematics.solve(spec))
    return spec, report, layout.frames(report)


def test_a_loop_closed_by_one_internal_mesh_leaves_that_mesh_unmated():
    """M13: S1-S2 outside, S2-S3 inside a ring, S3-S1 outside again, at ratios that agree (not jammed)."""
    spec, report, frames = made_up(
        [("S1", "Z+", "input", "100"), ("S2", "Z+", "", ""), ("S3", "Z+", "", "")],
        [("G1", "S1", 20, "", 0), ("G2", "S2", 10, "", 0), ("G3", "S3", 40, "internal", 0),
         ("G4", "S3", 20, "", 20), ("G5", "S1", 10, "", 20)],
        [("G1", "G2"), ("G2", "G3"), ("G4", "G5")])
    assert not report.motion.jammed and report.motion.speeds["S3"] == Fraction(-50)
    plan = motion.motion_plan(spec, report, frames)
    assert [m.gears for m in kinds(plan, MESH)] == [("G1", "G2"), ("G2", "G3")]
    assert plan.unmated == (("G4", "G5"),)
    assert [m.gears for m in kinds(plan, LOCK)] == [("G1", "G5"), ("G3", "G4")]
    assert plan.trains == (("S1", "S2", "S3"),) and plan.drag == ("G1",)


def test_two_meshes_between_the_same_two_shafts_mate_the_first_only():
    spec, report, frames = made_up(
        [("S1", "Z+", "input", "100"), ("S2", "Z-", "", "")],
        [("G1", "S1", 17, "", 0), ("G2", "S2", 68, "", 0), ("G3", "S1", 17, "", 20), ("G4", "S2", 68, "", -20)],
        [("G1", "G2"), ("G3", "G4")])
    plan = motion.motion_plan(spec, report, frames)
    assert [m.name for m in kinds(plan, MESH)] == ["G1 meshes G2"] and plan.unmated == (("G3", "G4"),)
    assert [m.name for m in kinds(plan, LOCK)] == ["G3 locked to G1", "G4 locked to G2"]


def test_a_fixed_shaft_and_a_shaft_held_still_by_it_stay_fixed_and_unmated():
    """D9 and review M9: S4 meshes only the fixed S3, so kinematics settles it to 0 and its gear stays fixed."""
    spec, report, frames = made_up(
        [("S1", "Z+", "input", "100"), ("S2", "Z+", "", ""), ("S3", "Z+", "fixed", ""), ("S4", "Z+", "", "")],
        [("G1", "S1", 17, "", 0), ("G2", "S2", 68, "", 0), ("G3", "S3", 20, "", 0), ("G4", "S4", 30, "", 0)],
        [("G1", "G2"), ("G3", "G4")])
    assert report.motion.speeds["S4"] == 0
    assert motion.still_shafts(spec, report) == {"S3": "", "S4": "S3"}
    plan = motion.motion_plan(spec, report, frames)
    assert plan.fixed == ("G3", "G4") and set(plan.anchors) == {"S1", "S2"}
    assert [m.name for m in kinds(plan, MESH)] == ["G1 meshes G2"] and plan.unmated == ()
    assert not any(g in m.gears for m in plan.mates for g in ("G3", "G4"))


def test_an_input_turning_at_0_is_not_held_still_unless_a_fixed_shaft_holds_it():
    spec, report, frames = made_up([("S1", "Z+", "input", "0"), ("S2", "Z+", "", "")],
                                   [("G1", "S1", 17, "", 0), ("G2", "S2", 68, "", 0)], [("G1", "G2")])
    assert motion.still_shafts(spec, report) == {} and motion.motion_plan(spec, report, frames).fixed == ()


def test_two_trains_get_a_drag_gear_each_input_first_and_a_lone_gear_turns_alone():
    spec, report, frames = made_up(
        [("S1", "Z+", "input", "100"), ("S2", "Z+", "", ""), ("S4", "Z+", "", ""), ("S3", "Z+", "input", "50"),
         ("S5", "Z+", "", "")],
        [("G1", "S1", 17, "", 0), ("G2", "S2", 68, "", 0), ("G4", "S4", 40, "", 0), ("G3", "S3", 20, "", 0),
         ("G5", "S5", 30, "", 5)],
        [("G1", "G2"), ("G3", "G4")])
    plan = motion.motion_plan(spec, report, frames)
    assert plan.trains == (("S1", "S2"), ("S3", "S4")) and plan.drag == ("G1", "G3")
    assert plan.anchors["S5"] == "G5" and plan.fixed == ()
    assert [m.name for m in plan.mates if "G5" in m.gears] == ["G5 on S5 Axis", "G5 along S5"]


def test_a_front_face_behind_the_front_plane_is_held_at_a_flipped_distance():
    """No fixture puts a front face below z = 0, so a made-up one pins it; tier 8 held z = -12 on SolidWorks."""
    spec, report, frames = made_up([("S1", "Z+", "", ""), ("S2", "Z-", "", "")],
                                   [("G1", "S1", 17, "", -12.0), ("G2", "S2", 20, "", -3.5)], [])
    plan = motion.motion_plan(spec, report, frames)
    assert [(m.face_global, m.z_front) for m in kinds(plan, ALONG)] == [("G1 Face Z", -12.0), ("G2 Face Z", -3.5)]
    ops = motion.motion_assembly_plan("C:\\B\\T_Layout.SLDPRT", [("gear1", "C:\\B\\A.SLDPRT", frames["G1"]),
                                                                  ("gear2", "C:\\B\\B.SLDPRT", frames["G2"])],
                                      {"G1": "gear1", "G2": "gear2"}, plan, "", "C:\\B\\T.SLDASM").ops
    assert [op for op in ops if isinstance(op, AddGlobal)] == [AddGlobal("G1 Face Z", "12"), AddGlobal("G2 Face Z", "3.5")]
    assert [(op.kind, op.value) for op in ops if isinstance(op, Mate) and op.name.endswith(("along S1", "along S2"))] \
        == [("point distance", -12.0), ("point distance", -3.5)]


def reducer_assembly():
    """The 12 : 1 reducer's turning plan, as plan_gearbox makes it, from the motion plan up."""
    a = assess.assess(reducer(), [], "C:\\Parts\\Reducer_12to1\\")
    frames = layout.frames(a.report)
    plan = motion.motion_plan(a.spec, a.report, frames)
    components = [(f"gear{i}", f"C:\\P\\{g.id}.SLDPRT", frames[g.id]) for i, g in enumerate(a.spec.gears, 1)]
    handle_of = {g.id: f"gear{i}" for i, g in enumerate(a.spec.gears, 1)}
    built = motion.motion_assembly_plan("C:\\P\\R_Layout.SLDPRT", components, handle_of, plan, "C:\\T\\A.asmdot",
                                        "C:\\P\\R.SLDASM")
    static = layout.assembly_plan("C:\\P\\R_Layout.SLDPRT", components, "C:\\T\\A.asmdot", "C:\\P\\R.SLDASM")
    return built, static, plan


def test_the_12_to_1_turning_assembly_is_planned_op_for_op():
    built, static, _ = reducer_assembly()
    assert built.check() == [] and built.kind == layout.ASSEMBLY_KIND and built.path == "C:\\P\\R.SLDASM"
    ax = AXIS_NAME
    assert list(built.ops) == [NewAssembly("C:\\T\\A.asmdot"), AddGlobal("G4 Face Z", "17")] + list(static.ops[1:-2]) + [
        Unfix("gear1"),
        Mate("axis1", "coincident", f"gear1:{ax}", "layout:S1 Axis", name="G1 on S1 Axis"),
        Mate("along1", "point", "gear1:origin", "layout:plane1", name="G1 along S1"),
        Unfix("gear2"),
        Mate("axis2", "coincident", f"gear2:{ax}", "layout:S2 Axis", name="G2 on S2 Axis"),
        Mate("along2", "point", "gear2:origin", "layout:plane1", name="G2 along S2"),
        Unfix("gear3"),
        Mate("lock1", "lock", "gear2", "gear3", name="G3 locked to G2"),
        Unfix("gear4"),
        Mate("axis3", "coincident", f"gear4:{ax}", "layout:S3 Axis", name="G4 on S3 Axis"),
        Mate("along3", "point distance", "gear4:origin", "layout:plane1", 17.0, name="G4 along S3"),
        LinkDimension("D1@G4 along S3", '"G4 Face Z"'),
        Mate("mesh1", "gear", f"gear1:{ax}", f"gear2:{ax}", ratio=(17.0, 68.0), flip=findings.GEAR_MATE_FLIP,
             name="G1 meshes G2"),
        Mate("mesh2", "gear", f"gear3:{ax}", f"gear4:{ax}", ratio=(17.0, 51.0), flip=findings.GEAR_MATE_FLIP,
             name="G3 meshes G4"),
        Rebuild(), SaveAs("C:\\P\\R.SLDASM")]
    assert static.ops[1:-2] == tuple(op for op in built.ops if isinstance(op, (AddComponent, Place, Fix)))


def test_every_gear_is_unfixed_after_its_fix_and_before_its_first_mate_and_followers_only_locked():
    built, _, plan = reducer_assembly()
    ops = list(built.ops)
    followers = {f"gear{int(m.gears[1][1:])}" for m in kinds(plan, LOCK)}
    for handle in ("gear1", "gear2", "gear3", "gear4"):
        fix = next(i for i, op in enumerate(ops) if isinstance(op, Fix) and op.component == handle)
        unfix = next(i for i, op in enumerate(ops) if isinstance(op, Unfix) and op.component == handle)
        mate = next(i for i, op in enumerate(ops) if isinstance(op, Mate) and handle in (op.a.split(":")[0],
                                                                                        op.b.split(":")[0]))
        assert fix < unfix < mate, handle
    for op in ops:
        if isinstance(op, Mate) and op.kind in ("coincident", "point", "point distance"):
            assert op.a.split(":")[0] not in followers
    for i, op in enumerate(ops):
        if isinstance(op, LinkDimension):
            owner = op.dimension.split("@", 1)[1]
            assert any(isinstance(o, Mate) and o.name == owner for o in ops[:i])
    last_global = max(i for i, op in enumerate(ops) if isinstance(op, AddGlobal))
    assert all(i > last_global for i, op in enumerate(ops) if isinstance(op, LinkDimension))


def test_a_mate_on_a_fixed_gear_or_a_gear_not_inserted_is_refused_with_a_sentence():
    _, _, plan = reducer_assembly()
    with pytest.raises(ValueError, match="G4 is not in the assembly"):
        motion.motion_assembly_plan("L", [], {"G1": "gear1", "G2": "gear2", "G3": "gear3"}, plan, "", "A")
    stuck = dataclasses.replace(plan, fixed=("G3",))
    with pytest.raises(ValueError, match="G3 is to stay fixed"):
        motion.motion_assembly_plan("L", [], {f"G{i}": f"gear{i}" for i in range(1, 5)}, stuck, "", "A")


@pytest.mark.parametrize("kind", ["spur", "helical", "herringbone"])
def test_every_kind_w5_mates_plans_the_axis_its_mates_select(kind):
    beta = "" if kind == "spur" else "20"
    hands = ("", "") if kind == "spur" else ("right", "left")
    for spec in (outside_pair(kind, ("Z+", "Z+"), hands, beta=beta),
                 ring_pair(kind, ("Z+", "Z+"), ("right", "right") if beta else ("", ""), beta=beta)):
        for gear in spec.gears:
            gear_spec = gear.gear_spec(spec.box)
            built = plan_for(gear_spec, kind_for(gear_spec).derive(gear_spec), "", "C:\\P\\X.SLDPRT")
            assert any(isinstance(op, Axis) and op.name == AXIS_NAME for op in built.ops), (kind, gear.id)


# -- the findings a turning build and its update need -----------------------------------------------------------


BUILD_FINDINGS = ["MOTION_ROUTE", "GEAR_MATE_ROUTE", "MATED_ASSEMBLY_REBUILD_ROUTE", "MATE_COINCIDENT",
                  "MATE_DISTANCE", "AXIS_MATE_ROUTE", "AXIAL_MATE_ROUTE", "GEAR_MATE_FLIP_RULE", "GEAR_MATE_FLIP",
                  "GEAR_MATE_NUMERATOR_FIRST", "COMPOUND_LOCK_ROUTE", "MATE_RENAME_ROUTE", "MATE_FIND_ROUTE",
                  "MATE_LOCK", "MATE_GEAR", "ADD_MATE_NO_ERROR", "LOCK_SELECT_ROUTE", "COMPONENT_UNDER_DEFINED"]
UPDATE_FINDINGS = ["MESH_PHASE_ROUTE", "LOCK_UNSUPPRESS_KEEPS_THE_NEW_ANGLE", "LAYOUT_MOVE_CARRIES_MATES",
                   "AXIAL_GLOBAL_MOVES_GEAR", "SUPPRESSION_ROUTE", "FEATURE_SUPPRESS", "FEATURE_UNSUPPRESS",
                   "THIS_CONFIGURATION", "MATE_FIND_ROUTE"]


def sentence(text):
    return text[:1].isupper() and text.endswith(".")


def test_with_every_finding_committed_build_turns_and_update_acts():
    assert motion.motion_reason() == "" and motion.update_reason() == ""


@pytest.mark.parametrize("name", BUILD_FINDINGS)
def test_a_build_finding_missing_builds_static_and_says_which(monkeypatch, name):
    monkeypatch.delattr(findings, name)
    why = motion.motion_reason()
    assert f"(findings.{name})" in why and "not settled" in why and sentence(why)


@pytest.mark.parametrize("name,value", [("MOTION_ROUTE", "drag"), ("AXIS_MATE_ROUTE", "concentric"),
                                        ("GEAR_MATE_FLIP_RULE", "always"), ("GEAR_MATE_NUMERATOR_FIRST", False),
                                        ("COMPOUND_LOCK_ROUTE", "angle")])
def test_a_build_finding_this_version_does_not_build_is_said_with_its_value(monkeypatch, name, value):
    monkeypatch.setattr(findings, name, value)
    why = motion.motion_reason()
    assert repr(value) in why and f"(findings.{name})" in why and sentence(why)


@pytest.mark.parametrize("name", UPDATE_FINDINGS)
def test_an_update_finding_missing_refuses_update_and_says_which(monkeypatch, name):
    monkeypatch.setattr(findings, name, None)
    why = motion.update_reason()
    assert f"(findings.{name})" in why and why.startswith("Update SolidWorks cannot change") and sentence(why)


def test_update_reason_never_reads_the_ratio_route(monkeypatch):
    """Ruling c: the ratio route decides only whether a tooth change is structural, in classify."""
    for value in (None, "modify definition", "remake", "anything"):
        monkeypatch.setattr(findings, "GEAR_MATE_RATIO_ROUTE", value)
        assert motion.update_reason() == ""
    monkeypatch.setattr(findings, "LAYOUT_MOVE_CARRIES_MATES", False)
    assert "False" in motion.update_reason()
