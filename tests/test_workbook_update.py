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
from test_workbook_gearbox import static_w4, turning  # noqa: E402,F401  (W4's tests stay static: W5-INTERFACES §5)
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
     "Gear_m1.5_N68 (G2): Flank changed from involute to arcs, which its values cannot carry; build it again as a "
     "new part."),
    (lambda s: gears(s, G2=dict(side="internal")),
     "Gear_m1.5_N68 (G2): Side changed from external to internal, which its values cannot carry; build it again as "
     "a new part."),
    (lambda s: gears(s, G2=dict(kind="helical", helix_angle="15")),
     "Gear_m1.5_N68 (G2): Kind changed from spur to helical, which its values cannot carry; build it again as a new "
     "part."),
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
    store.adopt(record, str(path))                     # the record is this workbook's (built() names WORKBOOK)
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
    # The original gone: moved or renamed, or a copy of an original since deleted. Held until the person says
    # (second review N1c), then the record is this workbook's.
    disk.remove(WORKBOOK)
    unanswered = update.classify(record, a, exists=disk.exists)
    assert unanswered.foreign_record == WORKBOOK and unanswered.parts == ()
    assert unanswered.refusal == ("The record of what was built beside this workbook, Reducer_12to1.workbook.json, "
                                  "was written for C:\\Work\\Reducer_12to1.xlsx, which is not there any more, and "
                                  "whether this workbook was moved or renamed from it has not been answered: until it "
                                  "is, Update SolidWorks leaves the files that record lists alone.")
    store.settle_owner(record, copy, moved=True)
    assert update.classify(record, a, exists=disk.exists).refusal == ""


def test_an_update_finish_adopts_a_record_of_a_moved_workbook(built):
    disk, record = built
    plan = classify(built, gears(reducer(), G2=dict(teeth="69")))
    done = update.finish_update(plan, worker_answer(plan), record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0, workbook="C:\\Moved\\Reducer_12to1.xlsx")
    assert done.record.workbook == "C:\\Moved\\Reducer_12to1.xlsx" and done.record.moved_from == [WORKBOOK]


def test_every_field_a_structural_change_names_is_said_in_the_workbooks_words():
    """Second W4 review N6: the footer said "The recipe changed from 'A' to 'B'" for Flank = arcs, and "The
    teeth_side changed" for Side. Every field swbuild.structural_change names by its field name is said as its
    Gears column; bore, profile shift and groove were words already. The strip keeps its own sentence."""
    base = {"kind": "helical", "recipe": "A", "hand": "right", "teeth_side": "external"}
    said = {key: update._structural(base, dict(base, **{key: value}))
            for key, value in (("kind", "herringbone"), ("recipe", "B"), ("hand", "left"), ("teeth_side", "internal"))}
    assert said == {
        "kind": "Kind changed from helical to herringbone, which its values cannot carry; build it again as a new part.",
        "recipe": "Flank changed from involute to arcs, which its values cannot carry; build it again as a new part.",
        "hand": "Hand changed from right to left, which its values cannot carry; build it again as a new part.",
        "teeth_side": "Side changed from external to internal, which its values cannot carry; build it again as a "
                      "new part."}
    assert all(field not in text for text in said.values() for field in ("recipe", "teeth_side", "'"))
    assert update._structural({"bore": "12"}, {"bore": ""}).startswith("A bore cannot be added to or removed")
    assert update._structural({"profile_shift": "0.1"}, {}).startswith("Profile shift cannot be added")
    assert update._structural({"groove": "2"}, {}).startswith("A centre groove cannot be added")
    assert swbuild.structural_change(base, dict(base, recipe="B")) == (
        "The recipe changed from 'A' to 'B'; build it again as a new part.")         # the strip's, unchanged


# -- W5: classify and finish a gearbox built to turn (W5-PLAN §3.2 B, as W5-DECISIONS and W5-INTERFACES amend it) --

import copy  # noqa: E402
import dataclasses  # noqa: E402

from gear_generator.gears.base import GlobalVariable as Global  # noqa: E402
from gear_generator.workbook import motion  # noqa: E402

REBUILD = "so the gearbox needs building again."


def with_pair(spec, s5_role="", s4_role=""):
    """The reducer and a second pair on S4 and S5, apart from the first train: S5 fixed holds S4 still (M9)."""
    return replace(spec,
                   shafts=spec.shafts + (Shaft("S4", "frame", "0", "100", "0", "Z+", s4_role, "",
                                               "100" if s4_role == "input" else ""),
                                         Shaft("S5", "frame", "63.75", "100", "0", "Z+", s5_role)),
                   gears=spec.gears + (Gear("G5", "S4", "7.5", "spur", "external", "17", "1.5", "", "15", "8"),
                                       Gear("G6", "S5", "7.5", "spur", "external", "68", "1.5", "", "15", "12")),
                   meshes=spec.meshes + (Mesh("G5", "G6"),))


def built_from(spec):
    disk = Disk()
    _, _, record = build(assessed(spec), None, disk)
    return disk, record


@pytest.fixture
def turned(turning):
    """The 12 : 1 reducer built to turn: (disk, record)."""
    disk, record = built_from(reducer())
    assert record.gearbox.kind == motion.MOTION
    return disk, record


def structural(plan, *starts):
    for start in starts:
        assert any(s.startswith(start) for s in plan.structural), (start, plan.structural)
    assert plan.needs_new_revision and all(s.endswith(".") and s[:1].isupper() for s in plan.structural)


def test_a_turning_gearbox_unchanged_gives_the_worker_its_mates_links_and_globals(turned):
    disk, record = turned
    plan = classify(turned, reducer())
    assert nothing(plan) and plan.axial == () and plan.ratios == ()
    m = plan.motion
    assert [r.name for r in m.mates] == [e.name for e in record.gearbox.mates]
    assert m.meshes == (swbuild.MeshLink("G1", "G2", -0.25, 360 / 68), swbuild.MeshLink("G3", "G4", -1 / 3, 360 / 51))
    assert m.recorded_meshes == m.meshes and m.locks == (swbuild.LockLink("G2", "G3", 360 / 17),)
    assert [(p.gear, p.component, p.pitch) for p in m.recorded] == [
        ("G1", "Gear_m1.5_N17-1", 360 / 17), ("G2", "Gear_m1.5_N68-1", 360 / 68), ("G3", "Gear_m2_N17-1", 360 / 17),
        ("G4", "OutputGear-1", 360 / 51)]
    assert [p.rotation for p in m.recorded] == [tuple(c.rotation) for c in record.gearbox.components]
    assert m.face_globals == (("G4", Global("G4 Face Z", "17")),) and (m.ratios, m.fixed) == ((), ())
    assert plan.update_kwargs()["motion"] is m


def test_a_static_gearbox_keeps_w4s_path_even_once_gears_can_turn(built, turning):
    assert built[1].gearbox.kind == motion.STATIC
    plan = classify(built, gears(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), G2=dict(teeth="69")))
    assert plan.motion is None and plan.structural == () and "motion" not in plan.update_kwargs()


def demonstration():
    return gears(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), G2=dict(teeth="69"))


def test_the_w4_demonstration_edit_on_a_turning_gearbox_waits_for_the_ratio_route(turned):
    plan = classify(turned, demonstration())
    assert plan.structural == (
        "G2's teeth (68 → 69) change the gear mate G1 meshes G2 from 17 : 68 to 17 : 69, and a gear mate's ratio "
        "cannot be changed in a built assembly until the probes settle how (findings.GEAR_MATE_RATIO_ROUTE), "
        f"{REBUILD}",)
    # The moves alone are an Update, with the mates following the layout.
    moved = classify(turned, shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")))
    assert moved.structural == () and moved.moved_shafts == ("S2", "S3") and moved.replaced == ("G2", "G3", "G4")
    assert [(v.name, v.expression) for v in moved.layout.variables] == [("S2 X", "64.5"), ("S3 X", "132.5")]
    assert moved.motion.face_globals == (("G4", Global("G4 Face Z", "17")),) and moved.axial == ()


def test_modify_definition_is_never_taken_and_says_what_2024_does(turned, monkeypatch):
    monkeypatch.setattr(findings, "GEAR_MATE_RATIO_ROUTE", "modify definition")
    plan = classify(turned, demonstration())
    structural(plan, "G2's teeth (68 → 69) change the gear mate G1 meshes G2")
    assert "leaves an assembly SolidWorks 2024 cannot close" in plan.structural[0]
    monkeypatch.setattr(findings, "GEAR_MATE_RATIO_ROUTE", "something else")
    assert "'something else', which this version does not know how to follow" in classify(
        turned, demonstration()).structural[0]


def test_a_tooth_change_by_remake_is_an_update_in_the_records_gear_order(turned, monkeypatch):
    """D7's Update branch, coded and tested behind the finding; M10: the Meshes row reversed changes nothing."""
    monkeypatch.setattr(findings, "GEAR_MATE_RATIO_ROUTE", "remake")
    spec = replace(demonstration(), meshes=(Mesh("G2", "G1"), Mesh("G3", "G4")))
    plan = classify(turned, spec)
    assert plan.structural == () and plan.ratios == ("G1 meshes G2",)
    assert plan.motion.ratios == (("G1 meshes G2", 17, 69),)
    assert plan.motion.meshes[0] == swbuild.MeshLink("G1", "G2", -17 / 69, 360 / 69)
    assert plan.motion.recorded_meshes[0] == swbuild.MeshLink("G1", "G2", -0.25, 360 / 68)
    assert plan.motion.recorded[1].pitch == pytest.approx(360 / 68)          # as built, not as now wanted
    assert next(p for p in plan.placements if p.gear == "G2").pitch == pytest.approx(360 / 69)


def test_a_meshes_row_rewritten_the_other_way_round_is_no_change(turned):
    plan = classify(turned, replace(reducer(), meshes=(Mesh("G2", "G1"), Mesh("G4", "G3"))))
    assert nothing(plan) and plan.ratios == () and plan.motion.meshes[0].a == "G1"


def test_a_flipped_mated_shaft_is_built_again(turned):
    spec = shafts(gears(reducer(), G4=dict(at="-27")), S3=dict(axis="Z-"))
    plan = classify(turned, spec)
    structural(plan, "S3's axis is now Z- where it was built Z+: the mate G4 on S3 Axis keeps the direction it was "
                     f"made with, {REBUILD}")
    assert len(plan.structural) == 1                       # its anchor's new front face is not said twice


def test_a_gear_moved_to_another_shaft_is_built_again(turned):
    plan = classify(turned, gears(reducer(), G3=dict(shaft="S3", at="50")))
    structural(plan, f"G3 is now on S3 where it was built on S2: the mate G3 locked to G2 holds it to S2, {REBUILD}")
    plan = classify(turned, gears(reducer(), G4=dict(shaft="S2", at="50")))
    structural(plan, "G4 is now on S2 where it was built on S3: the mates G4 on S3 Axis and G4 along S3 hold it to "
                     f"S3, {REBUILD}")


@pytest.mark.parametrize("edit_, sentence", [
    (lambda s: gears(s, G1=dict(face_width="20")),
     "G1's face width (15 → 20) moves its front face off the Front plane (z 0 → -2.5): the mate G1 along S1 holds "
     "it on that plane and cannot take a distance"),
    (lambda s: gears(s, G1=dict(at="10")),
     "G1's At (7.5 → 10) moves its front face off the Front plane (z 0 → 2.5): the mate G1 along S1 holds it on "
     "that plane and cannot take a distance"),
    (lambda s: gears(s, G2=dict(face_width="20", at="12")),
     "G2's face width (15 → 20) and At (7.5 → 12) move its front face off the Front plane (z 0 → 2)"),
    (lambda s: gears(s, G4=dict(at="10")),
     "G4's At (27 → 10) moves its front face onto the Front plane (z 17 → 0): the mate G4 along S3 holds it at a "
     "distance from that plane and cannot reach it"),
    (lambda s: shafts(s, S3=dict(z="-40")),
     "S3's Z (0 → -40) moves G4's front face across the Front plane (z 17 → -23): the mate G4 along S3 cannot "
     "carry its distance across that plane"),
])
def test_an_anchors_front_face_reaching_leaving_or_crossing_the_front_plane_names_the_edit(turned, edit_, sentence):
    """W5-DECISIONS answer 3: structural, and the sentence names the edit, never only the plane."""
    plan = classify(turned, edit_(reducer()))
    structural(plan, sentence)
    assert plan.structural[0].endswith(REBUILD)


def test_an_anchors_move_along_its_shaft_on_one_side_of_the_front_plane_is_an_update(turned):
    for spec in (gears(reducer(), G4=dict(at="30")), shafts(reducer(), S3=dict(z="3"))):
        plan = classify(turned, spec)
        assert plan.structural == () and plan.axial == ("G4",) and "G4" in plan.replaced
        assert plan.motion.face_globals == (("G4", Global("G4 Face Z", "20")),)
    keeps = classify(turned, gears(reducer(), G1=dict(face_width="20", at="10")))        # front face stays at 0
    assert keeps.structural == () and keeps.axial == ()


@pytest.mark.parametrize("value, why", [
    (True, None),
    (None, "whether its lock to G2 takes a new place along the shaft is not settled (findings.LOCK_RETAKES_AN_OFFSET)"),
    (False, "the probes found that its lock to G2 does not take a new place along the shaft "
            "(findings.LOCK_RETAKES_AN_OFFSET)"),
])
def test_a_followers_at_or_face_width_is_an_update_only_while_the_lock_retakes_an_offset(turned, monkeypatch, value,
                                                                                         why):
    monkeypatch.setattr(findings, "LOCK_RETAKES_AN_OFFSET", value)
    for spec, edit_ in ((gears(reducer(), G3=dict(at="30")), "G3's At (27 → 30) moves its front face along S2 "
                                                              "(z 17 → 20)"),
                        (gears(reducer(), G3=dict(face_width="14")), "G3's face width (20 → 14) moves its front "
                                                                     "face along S2 (z 17 → 20)")):
        plan = classify(turned, spec)
        if why is None:
            assert plan.structural == () and "G3" in plan.replaced and plan.axial == ()
        else:
            assert plan.structural == (f"{edit_}, and {why}, {REBUILD}",)


def test_a_reordered_gears_sheet_keeps_the_recorded_anchors(turned):
    spec = reducer()
    spec = replace(spec, gears=(spec.gears[0], spec.gears[2], spec.gears[1], spec.gears[3]))
    plan = classify(turned, spec)
    assert nothing(plan)
    assert [r.name for r in plan.motion.mates] == [e.name for e in turned[1].gearbox.mates]
    assert plan.motion.locks == (swbuild.LockLink("G2", "G3", 360 / 17),)
    # G3 now first on S2: its At change is still a follower's, never an anchor's front face.
    assert classify(turned, gears(spec, G3=dict(at="30"))).structural == ()


def test_a_shaft_whose_role_becomes_or_stops_being_fixed_is_built_again(turning):
    free = built_from(with_pair(reducer()))
    assert free[1].gearbox.fixed == [] and free[1].gearbox.drag == ["G1", "G5"]
    plan = classify(free, with_pair(reducer(), s5_role="fixed"))
    assert plan.structural == (                             # in Shafts-sheet order
        "S4 now stands still, held through the fixed shaft S5, but G5 was built mated to turn, so the gearbox needs "
        "building again to hold it fixed.",
        "S5's Role is now fixed, but G6 was built mated to turn, so the gearbox needs building again to hold it "
        "fixed.")
    held = built_from(with_pair(reducer(), s5_role="fixed"))
    assert held[1].gearbox.fixed == ["G5", "G6"] and held[1].gearbox.drag == ["G1"]
    plan = classify(held, with_pair(reducer()))
    assert plan.structural == (
        "G5 was built fixed, but S4 now turns (its Role is not fixed and no fixed shaft holds it still), so the "
        "gearbox needs building again to mate it to turn.",
        "G6 was built fixed, but S5 now turns (its Role is not fixed and no fixed shaft holds it still), so the "
        "gearbox needs building again to mate it to turn.")
    still = classify(held, with_pair(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), s5_role="fixed"))
    assert still.structural == () and still.motion.fixed == ("G5", "G6")


def test_a_recorded_mate_update_cannot_read_is_refused_with_a_sentence(turned):
    disk, record = turned
    cases = [
        (dict(kind="angle"), "as an 'angle' mate, which is not a kind of mate the app makes"),
        (dict(gears=["G1"]), "with 1 gear where a mesh mate holds 2"),
        (dict(gears=[]), "with 0 gears where a mesh mate holds 2"),
        (dict(ratio=[17]), "with the ratio [17], where a gear mate holds two tooth counts"),
        (dict(ratio=[17, 0]), "with the ratio [17, 0], where a gear mate holds two tooth counts"),
        (dict(gears=["G1", "G9"]), "on G9, which is not in the assembly on record"),
        (dict(name=""), "The record of what was built lists a mate with no name, and Update SolidWorks finds each "
                        "mate by its name"),
    ]
    for change, said in cases:
        bad = copy.deepcopy(record)
        mesh = next(e for e in bad.gearbox.mates if e.kind == motion.MESH)
        for key, value in change.items():
            setattr(mesh, key, value)
        plan = update.classify(bad, assessed(reducer()), exists=disk.exists)
        assert said in plan.refusal and plan.refusal.endswith(
            "so Update SolidWorks cannot act on the gearbox the record describes: Build again… makes a new revision "
            "from the workbook instead."), plan.refusal
        assert plan.motion is None
    bad = copy.deepcopy(record)
    bad.gearbox.mates[1].shaft = ""
    assert "with no shaft" in update.classify(bad, assessed(reducer()), exists=disk.exists).refusal


def test_a_turning_gearbox_whose_update_findings_are_not_settled_is_refused(turned, monkeypatch):
    monkeypatch.setattr(findings, "MESH_PHASE_ROUTE", None)
    plan = classify(turned, reducer())
    assert plan.refusal == motion.update_reason() != "" and plan.motion is None


def turned_by(rotation, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    r = [rotation[i * 3:i * 3 + 3] for i in range(3)]
    z = [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]
    return tuple(sum(r[i][k] * z[k][j] for k in range(3)) for i in range(3) for j in range(3))


def test_finishing_a_turning_update_drags_only_gears_found_off_their_axis(turned):
    disk, record = turned
    plan = classify(turned, reducer())
    found = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in record.gearbox.components}
    found["G1"] = (turned_by(found["G1"][0], 30.0), found["G1"][1])           # turned by the user: not a drag
    found["G4"] = (found["G4"][0], (140.0, 3.0, 17.0))                         # pulled off its axis: a drag
    result = worker_answer(plan, found=found, placed=("G1", "G2", "G3", "G4"), changed_parts=())
    result.off_axis = ["G4"]
    done = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0)
    assert done.dragged == ["G4"]
    assert [c.rotation for c in done.record.gearbox.components] == [c.rotation for c in record.gearbox.components]


def test_finishing_a_turning_update_drags_a_fixed_gear_by_w4s_rule(turning):
    disk, record = built_from(with_pair(reducer(), s5_role="fixed"))
    plan = classify((disk, record), with_pair(reducer(), s5_role="fixed"))
    found = {c.gear: (tuple(c.rotation), tuple(c.at)) for c in record.gearbox.components}
    found["G6"] = (turned_by(found["G6"][0], 1.0), found["G6"][1])
    found["G1"] = (turned_by(found["G1"][0], 1.0), found["G1"][1])
    done = update.finish_update(plan, worker_answer(plan, found=found, placed=("G6",), changed_parts=()), record,
                                digest="d2", read_sidecar=disk.read_sidecar, mtime=lambda p: 1.0)
    assert done.dragged == ["G6"]


def test_finishing_a_turning_update_follows_the_ratios_and_face_globals_set(turned, monkeypatch):
    monkeypatch.setattr(findings, "GEAR_MATE_RATIO_ROUTE", "remake")
    disk, record = turned
    spec = gears(reducer(), G2=dict(teeth="69"), G4=dict(at="30"))
    plan = classify(turned, spec)
    assert plan.structural == () and plan.ratios == ("G1 meshes G2",) and plan.axial == ("G4",)
    result = worker_answer(plan, placed=("G1", "G2", "G3", "G4"))
    result.ratios, result.axial = ["G1 meshes G2"], ["G4"]
    done = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0)
    mates = {e.name: e for e in done.record.gearbox.mates}
    assert mates["G1 meshes G2"].ratio == [17, 69] and mates["G3 meshes G4"].ratio == [17, 51]
    assert mates["G4 along S3"].z_front == 20.0 and mates["G1 along S1"].z_front == 0.0
    assert {e.name: e for e in record.gearbox.mates}["G4 along S3"].z_front == 17.0      # the input is not changed
    after = update.classify(done.record, assessed(spec), exists=disk.exists)
    assert after.ratios == () and after.axial == () and after.structural == ()
    # Not set (the worker failed before them): the record keeps what the assembly holds.
    result.ratios, result.axial = [], []
    kept = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                mtime=lambda p: 1.0)
    assert {e.name: e.ratio for e in kept.record.gearbox.mates}["G1 meshes G2"] == [17, 68]


def test_a_renamed_shaft_is_said_once_not_again_as_its_gears_moving(turned):
    spec = reducer()
    spec = replace(spec, shafts=spec.shafts[:2] + (replace(spec.shafts[2], id="Out"),),
                   gears=spec.gears[:3] + (replace(spec.gears[3], shaft="Out"),))
    plan = classify(turned, spec)
    assert "Shaft S3 is no longer in the workbook, and its axis cannot be taken out of the layout part." in \
        plan.structural
    assert not any(s.startswith("G4 is now on") for s in plan.structural)


def test_moving_the_input_is_an_update_whose_drag_gear_follows(turned):
    disk, record = turned
    spec = shafts(reducer(), S1=dict(role="", speed="", torque=""), S3=dict(role="input", speed="125"))
    plan = classify(turned, spec)
    assert plan.structural == () and plan.drag == ("G4",)
    done = update.finish_update(plan, worker_answer(plan, placed=("G1", "G2", "G3", "G4"), changed_parts=()),
                                record, digest="d2", read_sidecar=disk.read_sidecar, mtime=lambda p: 1.0)
    assert done.record.gearbox.drag == ["G4"] and record.gearbox.drag == ["G1"]


def test_a_trains_frames_go_on_record_whole_or_not_at_all(turned):
    """Should-fix 3: a train put only in part by an update that failed keeps every frame it had on record."""
    disk, record = turned
    spec = shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5"))
    plan = classify(turned, spec)
    wanted = {p.gear: list(p.rotation) + list(p.at) for p in plan.placements}

    def kept(placed, failures):
        result = worker_answer(plan, placed=placed, changed_parts=(), failures=failures)
        done = update.finish_update(plan, result, record, digest="d2", read_sidecar=disk.read_sidecar,
                                    mtime=lambda p: 1.0)
        return {c.gear: (c.rotation + c.at) == wanted[c.gear] for c in done.record.gearbox.components}
    assert kept(("G1", "G2"), True) == {"G1": True, "G2": False, "G3": False, "G4": False}     # S1 did not move
    assert kept(("G1", "G2", "G3", "G4"), True) == {"G1": True, "G2": True, "G3": True, "G4": True}
    assert kept((), False) == {"G1": True, "G2": True, "G3": True, "G4": True}


# -- the turning round trip (plan -> fake build -> finish -> classify -> update -> finish -> classify) --------------
#
# On package A's fake SolidWorks (tests/test_swbuild.py), written against what the contract pins
# (W5-INTERFACES §3), never against A's incidental call order: what the record, the classify after, and the fake's
# own state (frames, mates, locked_puts, touched) say.


def fake_build(spec, sw=None, record=None, digest="d1"):
    """plan_gearbox -> build_gearbox on the fake -> finish_build: (sw, plan, result, record)."""
    from gear_generator.workbook import gearbox
    from test_swbuild import FakeSolidWorks
    sw = sw or FakeSolidWorks()
    plan = gearbox.plan_gearbox(assessed(spec), record, exists=sw.exists, read_sidecar=lambda p: None)
    assert plan.refusal == "", plan.refusal
    result = swbuild.build_gearbox(sw, **plan.build_kwargs(), exists=sw.exists)
    done = gearbox.finish_build(plan, result, record, workbook=WORKBOOK, digest=digest, written_by="test",
                                read_sidecar=lambda p: None, exists=sw.exists)
    return sw, plan, result, done.record or record


def press(sw, record, spec, digest="d2"):
    """classify -> update_gearbox on the fake -> finish_update: (plan, result, finished)."""
    plan = update.classify(record, assessed(spec), exists=lambda p: True)
    assert plan.refusal == "" and not plan.needs_new_revision, (plan.refusal, plan.structural)
    result = swbuild.update_gearbox(sw, **plan.update_kwargs(), exists=lambda p: True, mtime=lambda p: 5.0)
    finished = update.finish_update(plan, result, record, digest=digest, read_sidecar=lambda p: None,
                                    mtime=lambda p: 5.0)
    return plan, result, finished


def name2(record, gear):
    return next(c.name for c in record.gearbox.components if c.gear == gear)


def frames_of(sw, record):
    return {c.gear: tuple(map(tuple, sw.frames[c.name])) for c in record.gearbox.components}


def in_step_on_record(sw, record, spec):
    """The fake's gears against the record, as the next Update's check phase reads them."""
    plan = update.classify(record, assessed(spec), exists=lambda p: True)
    fixed = set(plan.motion.fixed)
    recorded = {p.gear: (p.rotation, p.at) for p in plan.motion.recorded if p.gear not in fixed}
    found = {g: f for g, f in frames_of(sw, record).items() if g in recorded}
    return swbuild.train_check(found, recorded, plan.motion.recorded_meshes, plan.motion.locks,
                               {p.gear: p.pitch for p in plan.motion.recorded})


def no_lock_left_off(sw, record):
    asm = record.gearbox.assembly
    locks = [e.name for e in record.gearbox.mates if e.kind == motion.LOCK]
    return sw.locked_puts == [] and all(not sw.mate(name, asm).suppressed for name in locks)


def wanted_frames(record, spec):
    plan = update.classify(record, assessed(spec), exists=lambda p: True)
    return {p.gear: (p.rotation, p.at) for p in plan.placements}


def at_wanted(sw, record, spec, gears_=None):
    live, wanted = frames_of(sw, record), wanted_frames(record, spec)
    return all(swbuild.same_frame(live[g][0], live[g][1], wanted[g][0], wanted[g][1]) for g in (gears_ or wanted))


def turn_train(sw, record, degrees, links=None):
    """The user drags the 12 : 1's input: each gear turns δ_i = θ·ω_i/ω_in about its own axis (review M2)."""
    for gear, k in (links or {"G1": 1.0, "G2": -0.25, "G3": -0.25, "G4": 1 / 12}).items():
        sw.turn(name2(record, gear), degrees * k)


@pytest.fixture
def on_fake(turning):
    sw, plan, result, record = fake_build(reducer())
    return sw, record


def test_round_trip_a_clean_build_records_a_turning_gearbox(on_fake):
    sw, record = on_fake
    box = record.gearbox
    assert box.kind == motion.MOTION and box.assembly and box.mate_problems == [] and box.drag == ["G1"]
    assert [e.name for e in box.mates] == [m.name for m in sw.mates]
    assert all(sw.mate(e.name, box.assembly).status == findings.ADD_MATE_NO_ERROR for e in box.mates)
    assert nothing(update.classify(record, assessed(reducer()), exists=lambda p: True))
    _, result, _ = press(sw, record, reducer())
    assert result.ok and result.placed == [] and not result.turned


def test_round_trip_a_train_turned_only_is_left_where_it_was_turned(on_fake):
    sw, record = on_fake
    turn_train(sw, record, 30.0)
    before = frames_of(sw, record)
    sw.touched.clear()
    plan, result, finished = press(sw, record, reducer())
    assert result.ok and result.turned and result.placed == [] and result.restored == []
    assert result.out_of_step == [] and result.off_axis == []
    assert frames_of(sw, record) == before and record.gearbox.assembly not in result.changed
    assert not any(k.endswith(".sldasm") for k in sw.touched)
    assert finished.dragged == [] and finished.record.unsaved == {}
    assert [c.rotation for c in finished.record.gearbox.components] == [c.rotation for c in record.gearbox.components]
    check = in_step_on_record(sw, finished.record, reducer())
    assert check.in_step and check.turned


def test_round_trip_a_layout_move_puts_the_whole_train_back_with_its_locks_off_around_the_puts(on_fake):
    sw, record = on_fake
    turn_train(sw, record, 30.0)                              # turned first: the put returns it (D4)
    spec = shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5"))
    plan, result, finished = press(sw, record, spec)
    assert result.ok, result.failures
    assert sorted(result.placed) == ["G1", "G2", "G3", "G4"] and result.restored == [("G1", "G2", "G3", "G4")]
    assert no_lock_left_off(sw, record) and at_wanted(sw, record, spec)
    assert finished.dragged == [] and nothing(update.classify(finished.record, assessed(spec),
                                                              exists=lambda p: True))
    assert in_step_on_record(sw, finished.record, spec).in_step


def test_round_trip_an_anchors_face_z_moves_it_and_the_record_follows(on_fake):
    sw, record = on_fake
    spec = gears(reducer(), G4=dict(at="30"))
    plan, result, finished = press(sw, record, spec)
    assert plan.axial == ("G4",) and result.ok and result.axial == ["G4"]
    assert sw.frames[name2(record, "G4")][1][2] == pytest.approx(20.0) and at_wanted(sw, record, spec)
    assert {e.name: e for e in finished.record.gearbox.mates}["G4 along S3"].z_front == 20.0
    assert nothing(update.classify(finished.record, assessed(spec), exists=lambda p: True))


def test_round_trip_a_followers_at_is_carried_by_a_put_under_its_suppressed_lock(on_fake):
    sw, record = on_fake
    spec = gears(reducer(), G3=dict(at="30"))
    plan, result, finished = press(sw, record, spec)
    assert result.ok, result.failures
    assert "G3" in result.placed and no_lock_left_off(sw, record) and at_wanted(sw, record, spec)
    assert nothing(update.classify(finished.record, assessed(spec), exists=lambda p: True))
    assert in_step_on_record(sw, finished.record, spec).in_step


def test_round_trip_a_refused_mate_keeps_parts_and_layout_and_the_next_build_carries_on(turning):
    from test_swbuild import FakeSolidWorks
    sw = FakeSolidWorks(mate_codes={"G3 locked to G2": (46, False)})
    sw, plan, result, record = fake_build(reducer(), sw)
    assert result.assembly.mate_problems and not result.assembly.saved and result.kind == ""
    box = record.gearbox
    assert (box.layout, box.assembly, box.components) == (plan.layout_path, "", [])
    assert box.mate_problems == result.assembly.mate_problems and box.mate_problems_digest == "d1"
    assert len(record.parts) == 4 and record.digest == ""
    assert update.classify(record, assessed(reducer()), exists=lambda p: True).refusal
    sw.mate_codes = {}                                        # the workbook changed; SolidWorks takes it now
    sw, again, result, record = fake_build(reducer(), sw, record, digest="d2")
    assert isinstance(again.layout, gearbox_module().LayoutReuse) and len(again.reuse) == 4 and result.ok
    box = record.gearbox
    assert box.kind == motion.MOTION and box.assembly and (box.mate_problems, box.mate_problems_digest) == ([], "")
    assert nothing(update.classify(record, assessed(reducer()), exists=lambda p: True))


def gearbox_module():
    from gear_generator.workbook import gearbox
    return gearbox


def test_round_trip_a_tooth_change_by_remake(on_fake, monkeypatch):
    monkeypatch.setattr(findings, "GEAR_MATE_RATIO_ROUTE", "remake")
    sw, record = on_fake
    spec = gears(shafts(reducer(), S2=dict(x="64.5"), S3=dict(x="132.5")), G2=dict(teeth="69"))
    plan, result, finished = press(sw, record, spec)
    assert result.ok, result.failures
    assert result.ratios == ["G1 meshes G2"] and sw.mate("G1 meshes G2", record.gearbox.assembly).ratio == (17, 69)
    assert {e.name: e.ratio for e in finished.record.gearbox.mates}["G1 meshes G2"] == [17, 69]
    assert no_lock_left_off(sw, record) and at_wanted(sw, record, spec)
    assert nothing(update.classify(finished.record, assessed(spec), exists=lambda p: True))


def test_round_trip_teeth_doubled_at_half_the_module_keep_the_ratio_and_need_no_remake(on_fake):
    """Should-fix 1: 17 : 68 -> 34 : 136 is the same 1 : 4, an Update as in W4, and the record's ratio follows."""
    sw, record = on_fake
    spec = gears(reducer(), G1=dict(teeth="34", module="0.75"), G2=dict(teeth="136", module="0.75"))
    plan, result, finished = press(sw, record, spec)
    assert plan.ratios == () and plan.motion.ratios == () and result.ok and result.ratios == []
    assert sw.mate("G1 meshes G2", record.gearbox.assembly).ratio == (17.0, 68.0)
    assert {e.name: e.ratio for e in finished.record.gearbox.mates}["G1 meshes G2"] == [34, 136]
    after = update.classify(finished.record, assessed(spec), exists=lambda p: True)
    assert nothing(after) and after.motion.recorded_meshes[0] == swbuild.MeshLink("G1", "G2", -0.25, 360 / 136)
    assert in_step_on_record(sw, finished.record, spec).in_step


def test_round_trip_a_gear_dragged_off_its_axis_is_put_back_and_said(on_fake):
    sw, record = on_fake
    rotation, at = sw.frames[name2(record, "G4")]
    sw.frames[name2(record, "G4")] = (rotation, (at[0] + 3.0, at[1] - 2.0, at[2]))
    plan, result, finished = press(sw, record, reducer())
    assert result.ok and result.off_axis == ["G4"] and "G4" in result.placed
    assert finished.dragged == ["G4"] and at_wanted(sw, record, reducer()) and no_lock_left_off(sw, record)


def test_round_trip_a_gear_held_still_by_a_fixed_shaft_is_re_placed_as_w4_does(turning):
    spec = with_pair(reducer(), s5_role="fixed")
    sw, _, result, record = fake_build(spec)
    assert result.ok and record.gearbox.fixed == ["G5", "G6"]
    sw.turn(name2(record, "G5"), 4.0)                         # S4 is held still (M9): a turn there is a drag
    turn_train(sw, record, 30.0)
    plan, result, finished = press(sw, record, spec)
    assert result.ok and result.placed == ["G5"] and result.turned
    assert finished.dragged == ["G5"] and at_wanted(sw, record, spec, ["G5", "G6"])


def test_round_trip_two_trains_and_only_the_one_that_moved_is_put(turning):
    spec = with_pair(reducer(), s4_role="input")
    sw, _, result, record = fake_build(spec)
    assert result.ok and record.gearbox.drag == ["G1", "G5"]
    turn_train(sw, record, 20.0, {"G5": 1.0, "G6": -0.25})    # the second train turned by hand
    moved = shafts(spec, S2=dict(x="64.5"), S3=dict(x="132.5"))
    second = frames_of(sw, record)
    plan, result, finished = press(sw, record, moved)
    assert result.ok and sorted(result.placed) == ["G1", "G2", "G3", "G4"] and no_lock_left_off(sw, record)
    assert {g: f for g, f in frames_of(sw, record).items() if g in ("G5", "G6")} == {
        g: second[g] for g in ("G5", "G6")}
    assert nothing(update.classify(finished.record, assessed(moved), exists=lambda p: True))
    check = in_step_on_record(sw, finished.record, moved)
    assert check.in_step and check.turned                    # the second train still stands where it was turned


def test_round_trip_moving_the_input_refreshes_the_drag_gear_and_records_the_train_whole(on_fake):
    """Should-fixes 2 and 3: Role input from S1 to S3 is an Update; G3's built turn moves a whole pitch, so the
    lock is out of step against the new frames and the whole train is put; the record takes every frame of it and
    the next check finds the train in step; the drag gear is now S3's anchor."""
    sw, record = on_fake
    turn_train(sw, record, 360 / 17)                          # one tooth of G1: G1 and G2 whole teeth, G3 and G4 not
    spec = shafts(reducer(), S1=dict(role="", speed="", torque=""), S3=dict(role="input", speed="125"))
    plan, result, finished = press(sw, record, spec)
    assert plan.structural == () and plan.drag == ("G4",)
    assert result.ok and sorted(result.placed) == ["G1", "G2", "G3", "G4"] and no_lock_left_off(sw, record)
    assert finished.record.gearbox.drag == ["G4"]
    check = in_step_on_record(sw, finished.record, spec)
    assert check.in_step and not check.turned
