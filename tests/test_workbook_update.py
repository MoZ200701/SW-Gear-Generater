"""What Update SolidWorks changes, and recording it (docs/PLAN-WORKBOOK.md §4.5, phase W4)."""

import pytest

from gear_generator import swbuild
from gear_generator.gears.base import GlobalVariable
from gear_generator.spec import GearSpec
from gear_generator.workbook.update import PartUpdate, UpdatePlan


def _update(**changes):
    part = PartUpdate(r"C:\P\Gear_m1.5_N68.SLDPRT", ("G2",), GearSpec(), None,
                      (GlobalVariable("No. of Teeth", "69"),), changed=True)
    fields = dict(parts=(part,), layout=swbuild.DocumentValues(r"C:\P\R_Layout.SLDPRT"),
                  assembly=r"C:\P\R.SLDASM",
                  placements=(swbuild.Placement("G2", "Gear_m1.5_N68-1", (1, 0, 0, 0, 1, 0, 0, 0, 1),
                                                (64.5, 0, 0), 360 / 69),))
    fields.update(changes)
    return UpdatePlan(**fields)


def test_an_update_plan_hands_the_worker_plain_data_for_update_gearbox():
    plan = _update()
    kwargs = plan.update_kwargs()
    assert kwargs["parts"] == [swbuild.DocumentValues(r"C:\P\Gear_m1.5_N68.SLDPRT",
                                                      (GlobalVariable("No. of Teeth", "69"),))]
    assert kwargs["layout"] is plan.layout and kwargs["assembly"] == r"C:\P\R.SLDASM"
    assert kwargs["placements"] == list(plan.placements)
    assert set(kwargs) == set(swbuild.update_gearbox.__code__.co_varnames[1:5])
    assert not plan.record_matches and plan.changed_parts == plan.parts


@pytest.mark.parametrize("changes", [{"structural": ("G2's bore was added.",)},
                                     {"missing": (r"C:\P\Gear_m1.5_N68.SLDPRT",)}])
def test_a_change_update_cannot_carry_is_never_run(changes):
    plan = _update(**changes)
    assert plan.needs_new_revision
    with pytest.raises(ValueError):
        plan.update_kwargs()


# -- classify: the table, and edits that try to break it ---------------------------------------------

import math  # noqa: E402

from gear_generator import findings, store  # noqa: E402
from gear_generator.workbook import assess, layout, update  # noqa: E402
from gear_generator.workbook.model import Gear, Mesh, Shaft, replace  # noqa: E402
from test_workbook_gearbox import FOLDER, WORKBOOK, Disk, build, norm, stem  # noqa: E402
from test_workbook_model import edit, read, reducer, write  # noqa: E402


def assessed(spec):
    return assess.assess(replace(spec, source_path=WORKBOOK), [], FOLDER)


@pytest.fixture
def built():
    """The 12 : 1 reducer built once: (disk, record)."""
    disk = Disk()
    _, _, record = build(assessed(reducer()), None, disk)
    return disk, record


def classify(built, spec):
    disk, record = built
    return update.classify(record, assessed(spec), exists=disk.exists)


def gears(spec, **changes):
    """The reducer with gear rows changed: gears(spec, G2=dict(teeth="69"))."""
    return replace(spec, gears=tuple(replace(g, **changes.get(g.id, {})) for g in spec.gears))


def shafts(spec, **changes):
    return replace(spec, shafts=tuple(replace(s, **changes.get(s.id, {})) for s in spec.shafts))


def nothing(plan):
    return (plan.refusal, plan.structural, plan.missing, plan.replaced, plan.moved_shafts,
            [p.changed for p in plan.parts]) == ("", (), (), (), (), [False] * len(plan.parts))


def test_no_change_is_an_empty_plan_that_still_lists_everything_for_the_live_compare(built):
    plan = classify(built, reducer())
    assert nothing(plan) and plan.record_matches and not plan.needs_new_revision
    assert [stem(p.path) for p in plan.parts] == ["Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear"]
    assert [(p.gear, p.component) for p in plan.placements] == [
        ("G1", "Gear_m1.5_N17-1"), ("G2", "Gear_m1.5_N68-1"), ("G3", "Gear_m2_N17-1"), ("G4", "OutputGear-1")]
    assert plan.placements[1].pitch == pytest.approx(360 / 68)
    assert norm(plan.layout.path) == norm(built[1].gearbox.layout) and norm(plan.assembly) == norm(
        built[1].gearbox.assembly)
    assert plan.layout.features == ("S1 Axis", "S2 X Plane", "S2 Axis", "S3 X Plane", "S3 Axis")
    kwargs = plan.update_kwargs()
    assert len(kwargs["parts"]) == 4 and kwargs["layout"] is plan.layout


def test_the_demonstration_edit_is_values_and_moves_only(built):
    """S2 X 63.75 -> 64.5 and G2 68 -> 69 teeth (S3 X follows by its formula to 132.5)."""
    spec = gears(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), G2=dict(teeth="69"))
    plan = classify(built, spec)
    assert (plan.structural, plan.missing, plan.refusal) == ((), (), "")
    assert [stem(p.path) for p in plan.changed_parts] == ["Gear_m1.5_N68"]        # keeps its file name
    assert ("No. of Teeth", "69") in [(v.name, v.expression) for v in plan.changed_parts[0].variables]
    assert [(v.name, v.expression) for v in plan.layout.variables] == [("S2 X", "64.5"), ("S3 X", "132.5")]
    assert plan.moved_shafts == ("S2", "S3") and plan.replaced == ("G2", "G3", "G4")
    g2 = next(p for p in plan.placements if p.gear == "G2")
    assert math.degrees(math.atan2(g2.rotation[3], g2.rotation[0])) == pytest.approx(0.0, abs=1e-9)  # 69 is odd
    assert g2.at == (64.5, 0.0, 0.0) and g2.pitch == pytest.approx(360 / 69)
    assert not plan.needs_new_revision and plan.update_kwargs()["placements"] == list(plan.placements)


def test_a_teeth_change_alone_re_places_the_gear_by_its_new_parity(built):
    plan = classify(built, gears(reducer(), G4=dict(teeth="52")))
    # 52 teeth at 2 mm need S3 one millimetre further out; classify still says what Update would do
    assert plan.structural == () and [stem(p.path) for p in plan.changed_parts] == ["OutputGear"]
    assert "G4" in plan.replaced and plan.moved_shafts == ()


@pytest.mark.parametrize("edit_, why", [
    (lambda s: shafts(s, S2=dict(y="5")),
     "S2's Y moves off 0 (0 → 5): the layout part has no plane for S2 Y, so it needs a new layout part."),
    (lambda s: shafts(s, S2=dict(x="-63.75"), S3=dict(x="-131.75")),
     "S2's X crosses 0 (63.75 → -63.75): a layout plane cannot follow a global across its base plane, so it needs "
     "a new layout part."),
    (lambda s: shafts(s, S2=dict(x="0", y="63.75")),
     "S2's X moves to 0 (63.75 → 0): its layout plane cannot reach the base plane, so it needs a new layout part."),
    (lambda s: gears(s, G1=dict(bore="")),
     "Gear_m1.5_N17 (G1): A bore cannot be added to or removed from a built part through its values; build it "
     "again as a new part."),
    (lambda s: gears(s, G4=dict(part_name="Output")),
     "OutputGear (G4): its Part name now makes Output.SLDPRT, and a built part's file is never renamed, so it "
     "needs a new part."),
    (lambda s: gears(s, G4=dict(part_name="")),
     "OutputGear (G4): its Part name now makes Gear_m2_N51.SLDPRT, and a built part's file is never renamed, so it "
     "needs a new part."),
    (lambda s: gears(s, G2=dict(flank="arcs")),
     "Gear_m1.5_N68 (G2): The recipe changed from 'A' to 'B'; build it again as a new part."),
    (lambda s: replace(s, gears=s.gears[:3]),
     "G4 is no longer in the workbook, and Update SolidWorks cannot take a part out of what was built."),
    (lambda s: replace(s, meshes=s.meshes[:1]),
     "The mesh G3–G4 is no longer listed, and Update SolidWorks cannot take one out."),
])
def test_what_needs_a_new_revision_says_why(built, edit_, why):
    plan = classify(built, edit_(reducer()))
    assert why in plan.structural, plan.structural
    assert plan.needs_new_revision and not plan.record_matches
    with pytest.raises(ValueError, match="Update SolidWorks cannot carry this change"):
        plan.update_kwargs()


def test_a_gear_and_a_mesh_added(built):
    spec = reducer()
    spec = replace(spec, shafts=spec.shafts + (Shaft("S4", x="63.75", y="63.75"),),
                   gears=spec.gears + (replace(spec.gears[0], id="G5", shaft="S4", notes=""),),
                   meshes=spec.meshes + (Mesh("G5", "G2"),))
    plan = classify(built, spec)
    assert plan.structural == ("G5 is new, and Update SolidWorks cannot add a part to what was built.",
                               "Shaft S4 is new, and the layout part has no axis for it.",
                               "The mesh G2–G5 is new, and Update SolidWorks cannot add one.")


def test_a_renamed_shaft_and_a_renamed_gear_are_each_a_removal_and_an_addition(built):
    spec = reducer()
    spec = replace(spec, shafts=(spec.shafts[0], replace(spec.shafts[1], id="Mid"), spec.shafts[2]),
                   gears=(spec.gears[0], replace(spec.gears[1], id="Big", shaft="Mid"),
                          replace(spec.gears[2], shaft="Mid"), spec.gears[3]),
                   meshes=(Mesh("G1", "Big"), spec.meshes[1]))
    plan = classify(built, spec)
    assert plan.structural == (
        "G2 is no longer in the workbook, and Update SolidWorks cannot take a part out of what was built.",
        "Big is new, and Update SolidWorks cannot add a part to what was built.",
        "Shaft S2 is no longer in the workbook, and its axis cannot be taken out of the layout part.",
        "Shaft Mid is new, and the layout part has no axis for it.",
        "The mesh Big–G1 is new, and Update SolidWorks cannot add one.",
        "The mesh G1–G2 is no longer listed, and Update SolidWorks cannot take one out.")


def test_a_shared_part_whose_rows_diverge_is_split():
    spec = reducer()
    spec = replace(spec, shafts=spec.shafts + (Shaft("S4", x="63.75", y="63.75"),),
                   gears=spec.gears + (replace(spec.gears[0], id="G5", shaft="S4", notes=""),),
                   meshes=spec.meshes + (Mesh("G5", "G2"),))
    disk = Disk()
    _, _, record = build(assessed(spec), None, disk)
    assert record.parts[0].gears == ["G1", "G5"]
    edited = assessed(gears(spec, G5=dict(bore="10", part_name="Idler_pinion")))
    assert edited.lay_out_refusal() == ""
    plan = update.classify(record, edited, exists=disk.exists)
    assert plan.structural == ("G1 and G5 share Gear_m1.5_N17.SLDPRT, but G5 now differs from G1, so they need "
                               "parts of their own.",)


@pytest.mark.parametrize("edit_", [
    lambda s: gears(s, G1=dict(hand="left")),                         # a spur gear's Hand: the part has none
    lambda s: gears(s, G2=dict(part_name="Gear_m1.5_N68")),           # a Part name equal to the default stem
    lambda s: gears(s, G4=dict(part_name="outputgear")),              # one file to Windows
    lambda s: gears(s, G1=dict(teeth="17.0")),                        # the same number
    lambda s: gears(s, G1=dict(flank="involute")),                    # the default, typed
    lambda s: gears(s, G1=dict(pressure_angle="20")),                 # the Box's, typed
    lambda s: gears(s, G1=dict(notes="the motor's")),
    lambda s: shafts(s, S1=dict(speed="3000", torque="5")),           # speeds and torques: nothing in SolidWorks
    lambda s: replace(s, meshes=(replace(s.meshes[0], efficiency="97"), s.meshes[1])),
    lambda s: replace(s, meshes=(Mesh("G2", "G1"), s.meshes[1])),     # a mesh listed the other way round
    lambda s: replace(s, box=replace(s.box, name="Renamed", efficiency="95")),
])
def test_edits_the_part_cannot_see_change_nothing(built, edit_):
    assert nothing(classify(built, edit_(reducer())))


def test_an_edit_the_reader_normalises_away_changes_nothing(tmp_path):
    """Hand typed R, teeth typed as 17.0 text, Kind ext: the reader's own forms, read back from a workbook."""
    path = write(tmp_path, reducer())
    spec, _ = read(path)
    disk = Disk()
    _, _, record = build(assess.assess(spec, [], FOLDER), None, disk)
    edit(path, "Gears", {"M2": "R", "F2": "17.0", "E3": "ext"})
    spec2, diagnostics = read(path)
    assert [d.message for d in diagnostics if d.is_error] == []
    plan = update.classify(record, assess.assess(spec2, diagnostics, FOLDER), exists=disk.exists)
    assert nothing(plan), (plan.structural, [p.changed for p in plan.parts])


def test_moves_alone_re_place_without_touching_a_part(built):
    plan = classify(built, gears(reducer(), G3=dict(at="30"), G4=dict(at="30")))
    assert (plan.structural, plan.moved_shafts, plan.replaced) == ((), (), ("G3", "G4"))
    assert [p.changed for p in plan.parts] == [False] * 4
    plan = classify(built, gears(shafts(reducer(), S3=dict(axis="Z-")), G4=dict(at="-27")))
    assert (plan.structural, plan.moved_shafts, plan.replaced) == ((), ("S3",), ("G4",))
    g4 = next(p for p in plan.placements if p.gear == "G4")
    assert g4.rotation[8] == -1.0 and g4.at == (131.75, 0.0, 37.0)


def test_changing_the_input_shaft_changes_phases_but_no_part(built):
    """phases() starts at the input, so another input turns other gears: re-placed, never a new revision. With
    S2 the input, G2 starts at 0 (not 180/68°) and G1 follows it half its pitch round; S3 as input changes no frame
    here, since each gear on a shaft is placed by its own mesh."""
    spec = shafts(reducer(), S1=dict(role="", speed="", torque=""), S2=dict(role="input", speed="-375"))
    plan = classify(built, spec)
    assert (plan.structural, plan.moved_shafts, plan.replaced) == ((), (), ("G1", "G2"))
    assert [p.changed for p in plan.parts] == [False] * 4
    g2 = next(p for p in plan.placements if p.gear == "G2")
    assert g2.rotation == layout.IDENTITY
    spec = shafts(reducer(), S1=dict(role="", speed="", torque=""), S3=dict(role="input", speed="125"))
    assert nothing(classify(built, spec))


def test_a_frame_one_pitch_round_is_not_a_change(built):
    disk, record = built
    g2 = next(c for c in record.gearbox.components if c.gear == "G2")
    turned = [*g2.rotation]
    angle = math.atan2(turned[3], turned[0]) + 2 * math.pi / 68 * 5
    g2.rotation = [math.cos(angle), -math.sin(angle), 0.0, math.sin(angle), math.cos(angle), 0.0, 0.0, 0.0, 1.0]
    assert nothing(update.classify(record, assessed(reducer()), exists=disk.exists))


def test_a_file_moved_away_is_missing_and_needs_a_new_revision(built):
    disk, record = built
    disk.remove(record.parts[1].path)
    disk.remove(record.gearbox.layout)
    plan = update.classify(record, assessed(reducer()), exists=disk.exists)
    assert [stem(p) for p in plan.missing] == ["Reducer_12to1_Layout", "Gear_m1.5_N68"]
    assert plan.needs_new_revision and plan.structural == ()


def test_only_the_current_revisions_parts_are_classified():
    """Decision 2: after a build-again, the superseded part is in earlier, and Update never reads it."""
    disk = Disk()
    _, _, record = build(assessed(reducer()), None, disk)
    spec = gears(reducer(), G1=dict(bore=""))
    _, _, record = build(assessed(spec), record, disk)
    plan = update.classify(record, assessed(spec), exists=disk.exists)
    assert nothing(plan)
    assert sorted(stem(p.path) for p in plan.parts) == ["Gear_m1.5_N17_r2", "Gear_m1.5_N68", "Gear_m2_N17",
                                                        "OutputGear"]
    assert [stem(p) for p in record.earlier[0].parts] == ["Gear_m1.5_N17"]


def test_unsaved_documents_are_listed_and_do_not_stop_an_update(built):
    disk, record = built
    record.unsaved = {record.parts[1].path: 12.0}
    plan = update.classify(record, assessed(reducer()), exists=disk.exists)
    assert plan.unsaved == (record.parts[1].path,) and plan.update_kwargs()


def test_a_record_from_build_parts_updates_parts_only():
    disk = Disk()
    _, _, record = build(assessed(reducer()), None, disk)
    record.gearbox, record.assembly = None, ""
    plan = update.classify(record, assessed(gears(reducer(), G2=dict(teeth="69"))), exists=disk.exists)
    assert (plan.layout, plan.assembly, plan.placements, plan.structural) == (None, "", (), ())
    assert [stem(p.path) for p in plan.changed_parts] == ["Gear_m1.5_N68"]
    kwargs = plan.update_kwargs()
    assert kwargs["layout"] is None and kwargs["assembly"] == ""


def test_a_v1_part_with_no_spec_is_left_to_the_live_compare():
    disk = Disk()
    _, _, record = build(assessed(reducer()), None, disk)
    record.gearbox, record.assembly = None, ""
    record.parts[0].spec, record.parts[0].variables = {}, []
    plan = update.classify(record, assessed(reducer()), exists=disk.exists)
    assert plan.structural == () and [p.changed for p in plan.parts] == [True, False, False, False]


def test_nothing_to_update_is_refused_with_a_sentence(built):
    assert update.classify(None, assessed(reducer())).refusal == (
        "Nothing has been built from this workbook yet, so Update SolidWorks has nothing to change.")
    disk, record = built
    record.gearbox.assembly = ""
    assert update.classify(record, assessed(reducer()), exists=disk.exists).refusal == (
        "Reducer_12to1_Layout.SLDPRT was saved but its assembly was not made: Build carries on with it, and Update "
        "SolidWorks waits until it has.")


def test_a_layout_finding_not_committed_refuses(built, monkeypatch):
    monkeypatch.delattr(findings, "LAYOUT_NEGATED_LINK", raising=False)
    plan = classify(built, reducer())
    assert "probe tier 7" in plan.refusal


# -- finishing an update ---------------------------------------------------------------------------


def worker_answer(plan, found=None, placed=(), changed_parts=("Gear_m1.5_N68",), failures=False):
    """What update_gearbox would answer, by its pinned fields."""
    result = swbuild.GearboxUpdate()
    for p in plan.parts:
        names = [v.name for v in p.variables if v.name == "No. of Teeth"] if stem(p.path) in changed_parts else []
        result.parts.append(swbuild.UpdateResult(document=os.path.basename(p.path), changed=names, trig="degrees"))
        if names:
            result.changed.append(p.path)
    result.layout = swbuild.UpdateResult(document="layout", changed=["S2 X"], trig="degrees")
    result.changed.append(plan.layout.path)
    result.found = dict(found or {})
    result.placed = list(placed)
    if placed:
        result.changed.append(plan.assembly)
    result.rebuilt = True
    if failures:
        result.failures.append(("x", "y"))
    return result


import os  # noqa: E402


def test_finishing_the_demonstration_update(built):
    disk, record = built
    spec = gears(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), G2=dict(teeth="69"))
    plan = classify(built, spec)
    found = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in record.gearbox.components}
    result = worker_answer(plan, found=found, placed=("G2", "G3", "G4"))
    times = {norm(p): 100.0 + i for i, p in enumerate(result.changed)}
    done = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: times[norm(p)], stamp="2026-11-14T00:00:00Z")
    rec = done.record
    assert rec is not record and record.digest == "d1"                      # the input is left alone
    assert (rec.digest, rec.last_updated, rec.gearbox.updated) == ("d2",) + ("2026-11-14T00:00:00Z",) * 2
    g2 = next(p for p in rec.parts if stem(p.path) == "Gear_m1.5_N68")
    assert g2.spec["teeth"] == "69" and ["No. of Teeth", "69"] in g2.variables and g2.path.endswith("N68.SLDPRT")
    assert [stem(p) for p, _ in done.sidecars] == ["Gear_m1.5_N68.gear"]
    sidecar = done.sidecars[0][1]
    assert sidecar.record.spec["teeth"] == "69" and sidecar.record.last_updated == "2026-11-14T00:00:00Z"
    assert sidecar.record.workbook == WORKBOOK                              # everything else kept
    assert [s.x for s in rec.gearbox.shafts] == [0.0, 64.5, 132.5]
    wanted = {p.gear: p for p in plan.placements}
    for c in rec.gearbox.components:
        assert (c.rotation, c.at) == (list(wanted[c.gear].rotation), list(wanted[c.gear].at))
    assert {stem(p): t for p, t in rec.unsaved.items()} == {"Gear_m1.5_N68": 100.0, "Reducer_12to1_Layout": 101.0,
                                                             "Reducer_12to1": 102.0}
    assert done.dragged == []
    # and the next classify sees nothing left to do
    assert nothing(update.classify(rec, assessed(spec), exists=disk.exists))


def test_a_component_dragged_in_solidworks_is_said_to_have_been_put_back(built):
    disk, record = built
    plan = classify(built, reducer())
    found = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in record.gearbox.components}
    found["G4"] = (found["G4"][0], (140.0, 3.0, 17.0))
    result = worker_answer(plan, found=found, placed=("G4",), changed_parts=())
    done = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0)
    assert done.dragged == ["G4"] and done.sidecars == []


def test_a_failed_update_records_only_what_it_did(built):
    disk, record = built
    spec = gears(reducer(), G2=dict(teeth="69"))
    plan = classify(built, spec)
    result = worker_answer(plan, failures=True)
    result.parts[1].failures.append(("\"No. of Teeth\"", "SolidWorks said no"))
    done = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0)
    g2 = next(p for p in done.record.parts if stem(p.path) == "Gear_m1.5_N68")
    assert g2.spec["teeth"] == "68" and done.sidecars == []
    # Something changed in SolidWorks (the layout), but not all of it: SolidWorks does not match this read, so
    # the record keeps the digest it was built from and the header says the workbook changed since.
    assert done.record.digest == record.digest != "d2"
    assert done.record.last_updated and done.record.unsaved


def test_an_update_that_skipped_the_rest_keeps_the_digest_and_a_clean_retry_takes_it(built):
    disk, record = built
    spec = gears(reducer(), G2=dict(teeth="69"))
    plan = classify(built, spec)
    stopped = worker_answer(plan)
    stopped.skipped = "the assembly, because Reducer_12to1_Layout.SLDPRT failed"
    done = update.finish_update(plan, stopped, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0)
    assert done.record.digest == record.digest
    again = update.finish_update(plan, worker_answer(plan), done.record, digest="d2", read_sidecar=disk.read_sidecar,
                                 mtime=lambda p: 1.0)
    assert again.record.digest == "d2"


def test_a_sidecar_that_cannot_be_read_is_said(built):
    disk, record = built
    spec = gears(reducer(), G2=dict(teeth="69"))
    plan = classify(built, spec)
    done = update.finish_update(plan, worker_answer(plan), record, digest="d2", read_sidecar=lambda p: None,
                                mtime=lambda p: 1.0)
    assert done.notes == ["Gear_m1.5_N68.gear.json could not be read, so it was left as it is; the workbook's "
                          "record says what the part now holds."]


def test_an_unsaved_mark_on_a_file_that_has_gone_is_said(built):
    disk, record = built
    plan = classify(built, gears(reducer(), G2=dict(teeth="69")))

    def gone(path):
        raise FileNotFoundError(path)
    done = update.finish_update(plan, worker_answer(plan), record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=gone)
    assert done.record.unsaved == {} and len(done.notes) == 2


def test_build_then_update_through_the_worker_and_nothing_is_left():
    """plan -> build_gearbox -> finish_build -> classify -> update_gearbox -> finish_update -> classify, on one
    fake SolidWorks that keeps what each document holds."""
    from gear_generator.workbook import gearbox
    from test_swbuild import FakeSolidWorks, never_exists
    sw = FakeSolidWorks()
    plan = gearbox.plan_gearbox(assessed(reducer()), None, exists=lambda p: False, read_sidecar=lambda p: None)
    result = swbuild.build_gearbox(sw, **plan.build_kwargs(), exists=never_exists)
    record = gearbox.finish_build(plan, result, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                  read_sidecar=lambda p: None).record
    spec = gears(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), G2=dict(teeth="69"))
    wanted = update.classify(record, assessed(spec), exists=lambda p: True)
    done = swbuild.update_gearbox(sw, **wanted.update_kwargs(), exists=lambda p: True)
    assert done.ok and done.placed == ["G2", "G3", "G4"] and done.layout.changed == ["S2 X", "S3 X"]
    assert [r.changed for r in done.parts] == [[], ["No. of Teeth"], [], []]
    finished = update.finish_update(wanted, done, record, digest="d2", read_sidecar=lambda p: None,
                                    mtime=lambda p: 5.0)
    assert len(finished.record.unsaved) == 3 and finished.dragged == []
    assert nothing(update.classify(finished.record, assessed(spec), exists=lambda p: True))


# -- the W4 review's findings, as regression tests ------------------------------------------------------------


def _demonstration_update(disk, record, times):
    """The demonstration edit carried by Update and finished, the worker having read each file's time before."""
    spec = gears(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), G2=dict(teeth="69"))
    plan = update.classify(record, assessed(spec), exists=disk.exists)
    found = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in record.gearbox.components}
    result = worker_answer(plan, found=found, placed=("G2", "G3", "G4"))
    result.mtimes = {p: times[norm(p)] for p in result.changed}
    done = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 999.0)
    disk.write(done)
    return spec, done.record


def test_the_unsaved_mark_is_the_files_time_before_the_job_so_a_quick_save_is_not_missed(built):
    """Review nit: finish_update read the time at the finish, up to a second after the change; a save in that
    second was taken as the time of the change, and the document stayed unsaved for ever."""
    disk, record = built
    times = {norm(p.path): 100.0 for p in record.parts}
    times.update({norm(record.gearbox.layout): 101.0, norm(record.gearbox.assembly): 102.0})
    _, rec = _demonstration_update(disk, record, times)
    assert {stem(p): t for p, t in rec.unsaved.items()} == {"Gear_m1.5_N68": 100.0, "Reducer_12to1_Layout": 101.0,
                                                             "Reducer_12to1": 102.0}
    # the .gear.json of the part it changed says so, at the same time
    sidecar = disk.read_sidecar(store.sidecar_path(next(p for p in rec.unsaved if stem(p) == "Gear_m1.5_N68")))
    assert sidecar.record.unsaved_since == 100.0 and sidecar.record.spec["teeth"] == "69"
    # the save landed while the finish was being written: newer than the mark, so it clears
    assert store.clear_saved(rec, mtime=lambda p: 102.5) and rec.unsaved == {}


def test_an_update_left_unsaved_and_never_saved_holds_neither_button(built):
    """Review B2 (w4r_unsaved): Update changed N68 to 69 teeth; SolidWorks was closed without saving, so the file's
    time never moved; then a structural edit. Build again… was refused for ever ("save it in SolidWorks"), with
    nothing open to save, and Update was held too. Now the unsaved part is made new, and both buttons go."""
    from gear_generator import ui_text
    from test_workbook_gearbox import plan_for
    disk, record = built
    times = {norm(p.path): 100.0 for p in record.parts}
    times.update({norm(record.gearbox.layout): 100.0, norm(record.gearbox.assembly): 100.0})
    spec, rec = _demonstration_update(disk, record, times)
    store.clear_saved(rec, mtime=lambda p: 100.0)                    # closed without saving: no time moved
    assert len(rec.unsaved) == 3
    a = assessed(gears(spec, G1=dict(bore="")))
    up = update.classify(rec, a, exists=disk.exists)
    assert up.needs_new_revision
    again = plan_for(a, rec, disk, mtime=lambda p: 100.0)
    assert again.refusal == "" and again.revision == 2
    assert [m.gear_ids for m in again.unsaved_made_new] == [("G2",)]
    assert sorted(j.stem for j in again.build) == ["Gear_m1.5_N17_r2", "Gear_m1.5_N69"]     # its own name, free
    assert sorted(r.stem for r in again.reuse) == ["Gear_m2_N17", "OutputGear"]
    footer = ui_text.workbook_footer(a, record=rec, plan=again, update=up, folder=FOLDER)
    assert footer.build_enabled and footer.update_enabled, footer.text


def test_a_copied_workbooks_record_holds_update_and_says_whose_files_those_are(built):
    """Review S1: the record beside a copy names the original, which is still there."""
    disk, record = built
    disk.add(WORKBOOK)
    copy = "C:\\Copy\\Reducer_12to1.xlsx"
    a = assess.assess(replace(reducer(), source_path=copy), [], FOLDER)
    plan = update.classify(record, a, exists=disk.exists)
    assert plan.foreign_record == WORKBOOK and plan.parts == () and plan.placements == ()
    assert plan.refusal == ("The record of what was built beside this workbook, Reducer_12to1.workbook.json, was "
                            "written for C:\\Work\\Reducer_12to1.xlsx, which is still there: this workbook is a copy "
                            "of it, and the SolidWorks files that record lists are Reducer_12to1.xlsx's. Update "
                            "SolidWorks leaves them alone, and Build makes this workbook's own gearbox beside them, "
                            "sharing and overwriting nothing.")
    with pytest.raises(ValueError):
        plan.update_kwargs()
    # moved, not copied: the original is gone, and the record is this workbook's
    disk.remove(WORKBOOK)
    assert update.classify(record, a, exists=disk.exists).refusal == ""


def test_an_update_finish_adopts_a_record_of_a_moved_workbook(built):
    disk, record = built
    plan = classify(built, gears(reducer(), G2=dict(teeth="69")))
    done = update.finish_update(plan, worker_answer(plan), record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0, workbook="C:\\Moved\\Reducer_12to1.xlsx")
    assert done.record.workbook == "C:\\Moved\\Reducer_12to1.xlsx" and done.record.moved_from == [WORKBOOK]
