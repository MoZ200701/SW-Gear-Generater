"""Planning a gearbox build and recording it (docs/PLAN-WORKBOOK.md §4.2–§4.5, phase W4)."""

import math
import os

import pytest

from gear_generator import findings, store, swbuild
from gear_generator.gears.base import (AddComponent, BuildPlan, GlobalVariable, NewAssembly, NewPart, SaveAs)
from gear_generator.spec import GearSpec
from gear_generator.workbook import assess, gearbox, layout, motion
from gear_generator.workbook.build import PartJob
from gear_generator.workbook.gearbox import GearboxPlan, LayoutReuse, PartReuse
from gear_generator.workbook.model import Gear, replace
from test_workbook_model import reducer

FOLDER = "C:\\Parts\\Reducer_12to1"
WORKBOOK = "C:\\Work\\Reducer_12to1.xlsx"
TIER_7 = {"LAYOUT_PLUS_FLIP": {"right": False, "top": False}, "LAYOUT_NEGATED_LINK": "minus",
          "LAYOUT_AXIS_Z_SIGN": -1, "REPLACE_FIXED_ROUTE": "Transform2 put", "WORKBOOK_LAYOUT_ROUTE": "layout"}


@pytest.fixture(autouse=True)
def tier_7(monkeypatch):
    for name, value in TIER_7.items():
        monkeypatch.setattr(findings, name, value, raising=False)


# W4's tests pin the static assembly and run it end to end on the fake SolidWorks, whose turning half is package
# A's. They stay static by making motion.motion_reason give a sentence, as a missing W5 finding would
# (W5-INTERFACES §5); a test of the turning gearbox asks for ``turning``, which puts the real one back.
STATIC_FOR_W4 = "This test pins phase W4's static assembly, so its gears are placed fixed."
MOTION_REASON = motion.motion_reason


# The findings a probe round may still change, pinned to what these tests were written against, so none of them
# leans on the committed value; a test of another branch pins its own value over this.
SETTLED = {"GEAR_MATE_RATIO_ROUTE": None, "LOCK_RETAKES_AN_OFFSET": True,
           "MATED_ASSEMBLY_REBUILD_ROUTE": "ForceRebuild3(True)", "GEAR_MATE_RATIO_REMAKE_WORKS": True}


@pytest.fixture(autouse=True)
def settled_findings(monkeypatch):
    for name, value in SETTLED.items():
        monkeypatch.setattr(findings, name, value, raising=False)


@pytest.fixture(autouse=True)
def static_w4(monkeypatch):
    monkeypatch.setattr(motion, "motion_reason", lambda: STATIC_FOR_W4)


@pytest.fixture
def turning(monkeypatch, static_w4):
    monkeypatch.setattr(motion, "motion_reason", MOTION_REASON)


def _plan(**changes):
    new = PartJob("Gear_m1.5_N68_r2", r"C:\P\Gear_m1.5_N68_r2.SLDPRT", ("G2",), GearSpec(), None,
                  BuildPlan("spur", "A", (NewPart(""),)))
    kept = PartReuse(r"C:\P\Gear_m1.5_N17.SLDPRT", "Gear_m1.5_N17", ("G1", "G3"), GearSpec(), None,
                     (GlobalVariable("No. of Teeth", "17"),), 0)
    fields = dict(revision=2, name="R_r2", folder=r"C:\P", layout_path=r"C:\P\R_r2_Layout.SLDPRT",
                  assembly_path=r"C:\P\R_r2.SLDASM", build=(new,), reuse=(kept,), shafts=(), frames={},
                  layout=LayoutReuse(r"C:\P\R_r2_Layout.SLDPRT", (GlobalVariable("S2 X", "63.75"),),
                                     ("S2 X Plane", "S2 Axis")),
                  assembly=BuildPlan("assembly", "", (NewAssembly(""),)), handles={"gear1": "G1"},
                  part_of={"G1": kept.path, "G2": new.path, "G3": kept.path})
    fields.update(changes)
    return GearboxPlan(**fields)


def test_a_plan_hands_the_worker_plain_data_for_build_gearbox():
    plan = _plan()
    kwargs = plan.build_kwargs()
    assert kwargs["parts"] == [plan.build[0].plan]
    assert kwargs["reuse"] == [swbuild.DocumentValues(r"C:\P\Gear_m1.5_N17.SLDPRT",
                                                      (GlobalVariable("No. of Teeth", "17"),))]
    assert kwargs["layout"] == swbuild.DocumentValues(r"C:\P\R_r2_Layout.SLDPRT", (GlobalVariable("S2 X", "63.75"),),
                                                      ("S2 X Plane", "S2 Axis"))
    assert kwargs["assembly"] is plan.assembly and kwargs["gears"] == {"gear1": "G1"}
    assert set(kwargs) == set(swbuild.build_gearbox.__code__.co_varnames[1:6])


def test_a_parts_only_plan_has_no_layout_or_assembly():
    plan = _plan(layout=None, assembly=None, layout_path="", assembly_path="")
    assert plan.parts_only and plan.build_kwargs()["layout"] is None


def test_a_refused_plan_cannot_be_run():
    with pytest.raises(ValueError, match="already exists"):
        _plan(refusal=r"C:\P\R_r2.SLDASM already exists.").build_kwargs()


# -- a disk, and the worker's answer, faked --------------------------------------------------------


def norm(path):
    return path.replace("/", "\\").lower()


class Disk:
    """Files by path, as Windows compares them, and the .gear.json records beside some of them."""

    def __init__(self):
        self.files = set()
        self.sidecars = {}

    def add(self, *paths):
        for path in paths:
            self.files.add(norm(path))

    def remove(self, path):
        self.files.discard(norm(path))

    def exists(self, path):
        return norm(path) in self.files

    def read_sidecar(self, path):
        return self.sidecars.get(norm(path)) if self.exists(path) else None

    def write(self, finished):
        for path, sidecar in finished.sidecars:
            self.add(path)
            self.sidecars[norm(path)] = sidecar


def stem(path):
    return os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]


def built(path, kind="spur"):
    return swbuild.BuildResult(kind=kind, recipe="A", document=os.path.basename(path), path=path, trig="degrees",
                               features=["Gear"], rebuilt=True, saved=path)


def failed(path):
    return swbuild.BuildResult(document="Part3", path=path, failures=[("extrude", "it would not")])


def run(plan, disk, fail_part=None, fail_layout=False, fail_assembly=False):
    """What build_gearbox would answer, by its pinned fields, with the files it saved put on the disk."""
    assert plan.refusal == ""
    made = [j.path for j in plan.build] + [plan.assembly_path]
    if isinstance(plan.layout, BuildPlan):
        made.append(plan.layout_path)
    for path in made:
        assert not path or not disk.exists(path), f"the plan would overwrite {path}"
    for r in plan.reuse:
        assert disk.exists(r.path)
    result = swbuild.GearboxResult()
    for index, job in enumerate(plan.build):
        if index == fail_part:
            result.parts.built.append(failed(job.path))
            result.parts.skipped = [j.path for j in plan.build[index + 1:]]
            result.skipped = "the rest"
            return result
        result.parts.built.append(built(job.path, job.spec.kind))
        disk.add(job.path)
    result.checked = [r.path for r in plan.reuse]
    if plan.layout is None:
        return result
    if isinstance(plan.layout, LayoutReuse):
        result.checked.append(plan.layout.path)
        result.layout_reused = plan.layout.path
    elif fail_layout:
        result.layout = failed(plan.layout_path)
        return result
    else:
        result.layout = built(plan.layout_path, "layout")
        disk.add(plan.layout_path)
    if fail_assembly:
        result.assembly = failed(plan.assembly_path)
        return result
    result.assembly = built(plan.assembly_path, "assembly")
    disk.add(plan.assembly_path)
    counts = {}
    names = {layout.LAYOUT_HANDLE: stem(plan.layout_path) + "-1"}
    for handle, gear in plan.handles.items():
        part = stem(plan.part_of[gear])
        counts[part] = counts.get(part, 0) + 1
        names[handle] = f"{part}-{counts[part]}"
    result.components = names
    result.assembly.components = dict(names)
    return result


def assessed(spec=None):
    spec = spec or reducer()
    a = assess.assess(replace(spec, source_path=WORKBOOK), [], FOLDER)
    assert a.lay_out_refusal() == ""
    return a


def plan_for(a, record, disk, **kw):
    return gearbox.plan_gearbox(a, record, exists=disk.exists, read_sidecar=disk.read_sidecar, **kw)


def build(a, record, disk, **faults):
    """Plan, run and finish one press of Build; returns (plan, result, the record now on disk)."""
    plan = plan_for(a, record, disk)
    result = run(plan, disk, **faults)
    done = gearbox.finish_build(plan, result, record, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar, stamp="2026-11-13T00:00:00Z")
    disk.write(done)
    return plan, result, done.record or record


def path(name):
    return os.path.join(FOLDER, name)


# -- the first build -------------------------------------------------------------------------------


def test_the_first_build_makes_four_parts_the_layout_and_the_assembly():
    disk = Disk()
    plan = plan_for(assessed(), None, disk)
    assert (plan.refusal, plan.revision, plan.name, plan.revision_reason) == ("", 0, "Reducer_12to1", "")
    assert norm(plan.layout_path) == norm(path("Reducer_12to1_Layout.SLDPRT"))
    assert norm(plan.assembly_path) == norm(path("Reducer_12to1.SLDASM"))
    assert [j.stem for j in plan.build] == ["Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear"]
    assert plan.reuse == () and plan.handles == {"gear1": "G1", "gear2": "G2", "gear3": "G3", "gear4": "G4"}
    assert plan.part_of == {j.gear_ids[0]: j.path for j in plan.build}
    assert plan.meshes == (("G1", "G2"), ("G3", "G4"))
    assert [s.shaft for s in plan.shafts] == ["S1", "S2", "S3"] and set(plan.frames) == {"G1", "G2", "G3", "G4"}
    assert isinstance(plan.layout, BuildPlan) and plan.layout.check() == [] and plan.assembly.check() == []
    assert plan.layout.ops[-1] == SaveAs(plan.layout_path) and plan.assembly.ops[-1] == SaveAs(plan.assembly_path)
    inserted = [op.path for op in plan.assembly.ops if isinstance(op, AddComponent)]
    assert inserted == [plan.layout_path] + [j.path for j in plan.build]
    kwargs = plan.build_kwargs()
    assert kwargs["gears"] == plan.handles and kwargs["reuse"] == []


def test_the_plans_run_on_the_fake_solidworks():
    from test_swbuild import FakeSolidWorks, never_exists
    plan = plan_for(assessed(), None, Disk())
    for each in (plan.layout, plan.assembly):
        result = swbuild.build(FakeSolidWorks(), each, never_exists)
        assert result.ok and result.saved == each.ops[-1].path


def test_templates_are_the_box_sheets_or_else_the_strips():
    spec = reducer()
    plan = plan_for(assessed(spec), None, Disk(), part_template=r"C:\T\p.PRTDOT", assembly_template=r"C:\T\a.ASMDOT")
    assert plan.layout.ops[0] == NewPart(r"C:\T\p.PRTDOT") and plan.assembly.ops[0] == NewAssembly(r"C:\T\a.ASMDOT")
    spec = replace(spec, box=replace(spec.box, part_template=r"C:\B\p.PRTDOT", assembly_template=r"C:\B\a.ASMDOT"))
    plan = plan_for(assessed(spec), None, Disk(), part_template=r"C:\T\p.PRTDOT", assembly_template=r"C:\T\a.ASMDOT")
    assert plan.layout.ops[0] == NewPart(r"C:\B\p.PRTDOT") and plan.assembly.ops[0] == NewAssembly(r"C:\B\a.ASMDOT")
    assert (plan.part_template, plan.assembly_template) == (r"C:\B\p.PRTDOT", r"C:\B\a.ASMDOT")


def test_identical_gears_share_one_part_inserted_twice():
    """A second pinion, G5, the same as G1, on its own shaft above G2: one file, inserted twice."""
    spec = reducer()
    g1 = spec.gears[0]
    spec = replace(spec, shafts=spec.shafts + (replace(spec.shafts[1], id="S4", y="63.75", notes=""),),
                   gears=spec.gears + (replace(g1, id="G5", shaft="S4", notes=""),),
                   meshes=spec.meshes + (replace(spec.meshes[0], a="G5", b="G2", notes=""),))
    plan = plan_for(assessed(spec), None, Disk())
    assert plan.refusal == "" and plan.part_of["G1"] == plan.part_of["G5"]
    assert [j.gear_ids for j in plan.build][0] == ("G1", "G5") and len(plan.build) == 4
    inserted = [op.path for op in plan.assembly.ops if isinstance(op, AddComponent)]
    assert inserted.count(plan.part_of["G1"]) == 2 and plan.handles["gear5"] == "G5"
    disk = Disk()
    plan, result, record = build(assessed(spec), None, disk)
    assert [(c.gear, c.name) for c in record.gearbox.components if c.gear in ("G1", "G5")] == [
        ("G1", "Gear_m1.5_N17-1"), ("G5", "Gear_m1.5_N17-2")]
    assert record.parts[0].gears == ["G1", "G5"]


def test_a_layout_or_assembly_already_there_moves_the_build_to_r2():
    for there in ("Reducer_12to1_Layout.SLDPRT", "Reducer_12to1.SLDASM"):
        disk = Disk()
        disk.add(path(there))
        plan = plan_for(assessed(), None, disk)
        assert (plan.refusal, plan.revision, plan.name) == ("", 2, "Reducer_12to1_r2")
        assert plan.revision_reason == (f"{there} is already in {FOLDER}, and a build never overwrites a file. So "
                                        "this build is Reducer_12to1_r2, beside it; nothing is overwritten.")
        assert stem(plan.assembly_path) == "Reducer_12to1_r2" and stem(plan.layout_path) == "Reducer_12to1_r2_Layout"
        assert [j.stem for j in plan.build] == ["Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear"]


def test_the_revision_after_0_is_2_or_3_when_the_r2_files_are_there():
    disk = Disk()
    disk.add(path("Reducer_12to1.SLDASM"), path("Reducer_12to1_r2_Layout.SLDPRT"))
    plan = plan_for(assessed(), None, disk)
    assert (plan.revision, plan.name) == (3, "Reducer_12to1_r3")
    assert plan.revision_reason.startswith("Reducer_12to1.SLDASM is already in")


def test_a_part_file_not_built_from_this_workbook_is_never_reused_or_overwritten():
    """Review S5 and B1: a file at one part's path gives that part its own suffix, and the first build stays
    revision 0; the sentence does not claim the file was not built from this workbook, which nothing can know."""
    disk = Disk()
    disk.add(path("Gear_m1.5_N68.SLDPRT"))                       # someone else's, or ours with its record lost
    plan = plan_for(assessed(), None, disk)
    assert (plan.refusal, plan.revision, plan.name, plan.revision_reason) == ("", 0, "Reducer_12to1", "")
    assert [j.stem for j in plan.build] == ["Gear_m1.5_N17", "Gear_m1.5_N68_r2", "Gear_m2_N17", "OutputGear"]
    g2 = plan.build[1]
    assert g2.plan.ops[-1] == SaveAs(g2.path) and norm(g2.path) == norm(path("Gear_m1.5_N68_r2.SLDPRT"))
    assert plan.part_of["G2"] == g2.path
    assert plan.made_new == (gearbox.MadeNew(("G2",), path("Gear_m1.5_N68.SLDPRT"), g2.path, gearbox.NO_RECORD),)
    assert plan.made_new[0].sentence == (
        f"Gear_m1.5_N68.SLDPRT is already in {FOLDER}, and there is no record that this workbook built it (a build "
        "that was interrupted can leave such a file), so G2's part is made as Gear_m1.5_N68_r2; nothing is "
        "overwritten.")
    assert "not built from this workbook" not in plan.made_new[0].sentence
    assert plan.unsaved_made_new == ()


def test_a_part_whose_own_name_and_r2_are_taken_takes_the_smallest_free_suffix_at_revision_0():
    disk = Disk()
    disk.add(path("Gear_m1.5_N68.SLDPRT"), path("Gear_m1.5_N68_r2.SLDPRT"), path("Gear_m1.5_N17_r2.SLDPRT"))
    plan = plan_for(assessed(), None, disk)
    assert (plan.refusal, plan.revision) == ("", 0)
    assert [j.stem for j in plan.build] == ["Gear_m1.5_N17", "Gear_m1.5_N68_r3", "Gear_m2_N17", "OutputGear"]


@pytest.mark.parametrize("typed", ["Gear_m1.5_N17_r2", "gear_m1.5_n17_R2"])
@pytest.mark.parametrize("reverse", [False, True])
def test_a_suffix_never_takes_another_rows_typed_part_name_whatever_the_row_order(typed, reverse):
    """W4 review N3: G1's own name is taken by a file with no record, and G4's Part name is what G1's first suffix
    would be. G4 keeps the name typed, G1 takes the next suffix, the result does not depend on the order of the
    rows, and no sentence says a file is on disk when it is not."""
    disk = Disk()
    disk.add(path("Gear_m1.5_N17.SLDPRT"))
    spec = reducer()
    gears = tuple(replace(g, part_name=typed) if g.id == "G4" else g for g in spec.gears)
    spec = replace(spec, gears=tuple(reversed(gears)) if reverse else gears)
    plan = plan_for(assessed(spec), None, disk)
    assert plan.refusal == ""
    assert {g: stem(p) for g, p in plan.part_of.items() if g in ("G1", "G4")} == {"G1": "Gear_m1.5_N17_r3",
                                                                                   "G4": typed}
    assert plan.made_new == (gearbox.MadeNew(("G1",), path("Gear_m1.5_N17.SLDPRT"), plan.part_of["G1"],
                                             gearbox.NO_RECORD),)
    from gear_generator import ui_text
    said = ui_text.workbook_footer(assessed(spec), plan=plan, folder=FOLDER).text
    assert "Gear_m1.5_N17.SLDPRT is already there" in said and f"{typed}.SLDPRT" not in said


# -- reuse ----------------------------------------------------------------------------------------


def test_parts_built_by_build_parts_are_reused_by_the_record():
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk)
    # W2's Build parts record: parts only, no gearbox.
    record.gearbox, record.assembly = None, ""
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    again = plan_for(a, record, disk)
    assert (again.refusal, again.revision, again.build) == ("", 0, ())
    assert [r.stem for r in again.reuse] == ["Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear"]
    assert [r.revision for r in again.reuse] == [0, 0, 0, 0]
    assert again.reuse[1].variables == tuple(again.reuse[1].variables) and again.reuse[1].gear_ids == ("G2",)
    assert again.build_kwargs()["reuse"][0].variables[0].name


def test_parts_are_reused_by_their_sidecars_when_there_is_no_record():
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk)
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    again = plan_for(a, None, disk)                              # the record was lost
    assert (again.refusal, again.revision, again.build) == ("", 0, ())
    assert len(again.reuse) == 4


def test_a_part_recorded_for_another_workbook_is_not_reused():
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk)
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    other = assess.assess(replace(reducer(), source_path=r"C:\Work\Other.xlsx"), [], FOLDER)
    again = plan_for(other, None, disk)
    assert (again.revision, again.reuse) == (0, ())
    assert [j.stem for j in again.build] == ["Gear_m1.5_N17_r2", "Gear_m1.5_N68_r2", "Gear_m2_N17_r2", "OutputGear_r2"]
    assert {m.why for m in again.made_new} == {gearbox.OTHER_WORKBOOK}
    assert again.made_new[0].sentence == (f"Gear_m1.5_N17.SLDPRT in {FOLDER} was built from Reducer_12to1.xlsx, so "
                                          "G1's part is made as Gear_m1.5_N17_r2; nothing is overwritten.")


def test_our_own_stale_part_says_so_and_gets_its_r_n():
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk)
    record.gearbox, record.assembly = None, ""
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    spec = reducer()
    spec = replace(spec, gears=(spec.gears[0], replace(spec.gears[1], bore="14")) + spec.gears[2:])
    again = plan_for(assessed(spec), record, disk)
    assert (again.refusal, again.revision, again.revision_reason) == ("", 0, "")
    assert [m.sentence for m in again.made_new] == [
        f"Gear_m1.5_N68.SLDPRT in {FOLDER} was built from this workbook for values G2 no longer has, so G2's part is "
        "made as Gear_m1.5_N68_r2; nothing is overwritten."]
    assert [j.stem for j in again.build] == ["Gear_m1.5_N68_r2"]
    assert [r.stem for r in again.reuse] == ["Gear_m1.5_N17", "Gear_m2_N17", "OutputGear"]


def test_a_part_update_changed_without_saving_is_made_new_and_never_holds_the_build():
    """Review B2 (overruling interface agreement 7): a part Update left unsaved is simply not reusable."""
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk)
    record.gearbox, record.assembly = None, ""
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    record.unsaved = {plan.part_of["G2"]: 1.0}
    again = plan_for(a, record, disk)
    assert again.refusal == "" and again.revision == 0
    assert [j.stem for j in again.build] == ["Gear_m1.5_N68_r2"] and len(again.reuse) == 3
    assert again.unsaved_made_new == (gearbox.MadeNew(("G2",), plan.part_of["G2"], again.build[0].path,
                                                      gearbox.UNSAVED),)
    assert again.made_new[0].sentence == ("Gear_m1.5_N68 has changes from Update SolidWorks that are not saved, so "
                                          "its file is not yet the part G2 needs: this build makes G2's part new, as "
                                          "Gear_m1.5_N68_r2.")
    assert again.build_kwargs()["parts"][0].path == again.build[0].path


def test_fields_a_kind_ignores_do_not_stop_a_part_being_reused():
    """Decision 5: a spur gear's Hand, a Part name typed as the default stem, a recipe typed as the default."""
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk)
    record.gearbox, record.assembly = None, ""
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    spec = reducer()
    g1, g2 = spec.gears[0], spec.gears[1]
    spec = replace(spec, gears=(replace(g1, hand="left"), replace(g2, part_name="Gear_m1.5_N68"))
                   + spec.gears[2:])
    again = plan_for(assessed(spec), record, disk)
    assert (again.revision, again.build, len(again.reuse)) == (0, (), 4)


def test_same_part_and_name_changed():
    a = GearSpec(module="1.5", teeth="68", face_width="15", bore="12")
    assert gearbox.same_part(a, a.with_values(hand="left"))
    assert gearbox.same_part(a, a.with_values(name="Gear_m1.5_N68"))
    assert gearbox.same_part(a, a.with_values(teeth="68.0"))
    assert not gearbox.same_part(a, a.with_values(name="Idler"))
    assert not gearbox.same_part(a, a.with_values(bore="14"))
    # a default stem drifting with the values is not a new name; a typed one that holds the old name is not either
    assert not gearbox.name_changed(a, a.with_values(teeth="69"))
    assert not gearbox.name_changed(a, a.with_values(teeth="69", name="Gear_m1.5_N68"))
    assert gearbox.name_changed(a.with_values(name="OutputGear"), a.with_values(name="Output"))
    assert gearbox.name_changed(a.with_values(name="OutputGear"), a)
    assert not gearbox.name_changed(a.with_values(name="OutputGear"), a.with_values(name="outputgear"))
    helical = GearSpec(kind="helical", module="2", teeth="20", face_width="20", helix_angle="15", bore="")
    assert not gearbox.same_part(helical, helical.with_values(hand="left"))


def test_replan_moves_the_save_and_the_stem():
    job = plan_for(assessed(), None, Disk()).build[1]
    moved = gearbox.replan(job, r"C:\P\Gear_m1.5_N68_r4.SLDPRT", "")
    assert (moved.stem, moved.path, moved.gear_ids) == ("Gear_m1.5_N68_r4", r"C:\P\Gear_m1.5_N68_r4.SLDPRT", ("G2",))
    assert moved.plan.ops[-1] == SaveAs(r"C:\P\Gear_m1.5_N68_r4.SLDPRT")
    # the same part: every op but the save and the steps that name the file
    same = lambda ops: [op for op in ops[1:-1] if type(op).__name__ != "ManualStep"]
    assert same(moved.plan.ops) == same(job.plan.ops)
    assert any("Gear_m1.5_N68_r4" in getattr(op, "text", "") for op in moved.plan.ops)


# -- what a build leaves ---------------------------------------------------------------------------


def test_a_build_records_every_part_the_layout_and_the_assembly():
    disk = Disk()
    plan, result, record = build(assessed(), None, disk)
    assert (record.workbook, record.digest, record.last_built, record.written_by) == (
        WORKBOOK, "d1", "2026-11-13T00:00:00Z", "test")
    assert [(stem(p.path), p.gears, p.revision, p.trig) for p in record.parts] == [
        ("Gear_m1.5_N17", ["G1"], 0, "degrees"), ("Gear_m1.5_N68", ["G2"], 0, "degrees"),
        ("Gear_m2_N17", ["G3"], 0, "degrees"), ("OutputGear", ["G4"], 0, "degrees")]
    assert record.parts[1].spec == plan.build[1].spec.to_dict()
    assert ["No. of Teeth", "68"] in record.parts[1].variables
    box = record.gearbox
    assert (box.revision, box.name, box.layout, box.assembly) == (0, "Reducer_12to1", plan.layout_path,
                                                                   plan.assembly_path)
    assert record.assembly == plan.assembly_path and box.layout_component == "Reducer_12to1_Layout-1"
    assert [(c.gear, stem(c.part), c.name) for c in box.components] == [
        ("G1", "Gear_m1.5_N17", "Gear_m1.5_N17-1"), ("G2", "Gear_m1.5_N68", "Gear_m1.5_N68-1"),
        ("G3", "Gear_m2_N17", "Gear_m2_N17-1"), ("G4", "OutputGear", "OutputGear-1")]
    assert box.components[1].rotation == list(plan.frames["G2"].rotation)
    assert box.components[3].at == [131.75, 0.0, 17.0]
    assert [s.shaft for s in box.shafts] == ["S1", "S2", "S3"] and box.shafts[1].x_global == "S2 X"
    assert box.meshes == [["G1", "G2"], ["G3", "G4"]] and record.current_parts() == record.parts
    # one .gear.json per new part, each saying which workbook and which rows
    assert [stem(p) for p, _ in disk.sidecars.items()] == [
        "gear_m1.5_n17.gear", "gear_m1.5_n68.gear", "gear_m2_n17.gear", "outputgear.gear"]
    sidecar = disk.read_sidecar(store.sidecar_path(plan.part_of["G2"]))
    assert (sidecar.record.workbook, sidecar.record.workbook_gears) == (WORKBOOK, ["G2"])
    # the record round-trips through its own JSON
    assert store.link_record_from_json(store.link_record_to_json(record)) == record


def test_a_failed_part_keeps_what_saved_and_the_retry_carries_on():
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk, fail_part=2)
    assert [stem(p.path) for p in record.parts] == ["Gear_m1.5_N17", "Gear_m1.5_N68"]
    assert record.gearbox is None and record.assembly == ""
    again = plan_for(a, record, disk)
    assert (again.revision, [r.stem for r in again.reuse], [j.stem for j in again.build]) == (
        0, ["Gear_m1.5_N17", "Gear_m1.5_N68"], ["Gear_m2_N17", "OutputGear"])
    plan, result, record = build(a, record, disk)
    assert record.gearbox.assembly and len(record.parts) == 4 and record.earlier == []


def test_a_build_that_stopped_part_way_does_not_claim_the_read():
    """The digest says SolidWorks wholly matches a read: a build with no assembly, or missing a part, does not."""
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk, fail_assembly=True)
    assert not result.ok and record.gearbox.layout and record.last_built and record.digest == ""
    plan, result, record = build(a, record, disk)            # carried on: the layout and parts reused
    assert result.ok and record.digest == "d1"
    disk = Disk()
    plan, result, record = build(a, None, disk, fail_part=2)
    assert not result.ok and len(record.parts) == 2 and record.digest == ""


def test_nothing_saved_leaves_the_record_alone():
    disk = Disk()
    a = assessed()
    plan = plan_for(a, None, disk)
    result = run(plan, disk, fail_part=0)
    done = gearbox.finish_build(plan, result, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar)
    assert done.record is None and done.sidecars == []


def test_an_assembly_that_failed_is_continued_with_its_layout_reused():
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk, fail_assembly=True)
    box = record.gearbox
    assert (box.revision, box.layout, box.assembly, box.components) == (0, plan.layout_path, "", [])
    assert [s.shaft for s in box.shafts] == ["S1", "S2", "S3"]               # decision 4: as soon as it saved
    again = plan_for(a, record, disk)
    assert (again.refusal, again.revision, again.revision_reason, again.build) == ("", 0, "", ())
    assert again.layout == LayoutReuse(plan.layout_path, layout.layout_globals(again.shafts),
                                       layout.layout_features(again.shafts))
    assert len(again.reuse) == 4 and again.build_kwargs()["layout"].features == layout.layout_features(again.shafts)
    plan2, result2, record = build(a, record, disk)
    assert record.gearbox.assembly == plan.assembly_path and record.gearbox.layout == plan.layout_path
    assert len(record.gearbox.components) == 4 and record.earlier == []


def test_a_saved_layout_whose_shafts_moved_since_is_left_and_the_next_revision_built():
    disk = Disk()
    plan, result, record = build(assessed(), None, disk, fail_assembly=True)
    spec = reducer()
    s2, s3 = spec.shafts[1], spec.shafts[2]
    spec = replace(spec, shafts=(spec.shafts[0], replace(s2, x="64.5"), replace(s3, x="132.5")),
                   gears=(spec.gears[0], replace(spec.gears[1], teeth="69")) + spec.gears[2:])
    again = plan_for(assessed(spec), record, disk)
    assert (again.refusal, again.revision) == ("", 2)
    assert again.revision_reason == ("Reducer_12to1_Layout.SLDPRT was saved by a build whose assembly was not made, "
                                     "but the shafts have moved since, so it is not the layout part this workbook "
                                     "needs. So this build is Reducer_12to1_r2, beside it; nothing is overwritten.")
    assert isinstance(again.layout, BuildPlan)


def test_build_again_makes_r2_beside_the_first_and_moves_it_to_earlier():
    disk = Disk()
    plan0, _, record = build(assessed(), None, disk)
    spec = reducer()
    spec = replace(spec, gears=(replace(spec.gears[0], bore="10"),) + spec.gears[1:])     # 8 -> 10: a value
    spec = replace(spec, gears=(replace(spec.gears[0], bore=""),) + spec.gears[1:])       # no bore: structural
    plan2, result, record = build(assessed(spec), record, disk)
    assert (plan2.revision, plan2.name, plan2.revision_reason) == (
        2, "Reducer_12to1_r2", "Reducer_12to1.SLDASM was built from this workbook already. So this build is "
                               "Reducer_12to1_r2, beside it; nothing is overwritten.")
    assert [j.stem for j in plan2.build] == ["Gear_m1.5_N17_r2"]
    assert [r.stem for r in plan2.reuse] == ["Gear_m1.5_N68", "Gear_m2_N17", "OutputGear"]
    box = record.gearbox
    assert (box.revision, stem(box.assembly), stem(box.layout)) == (2, "Reducer_12to1_r2", "Reducer_12to1_r2_Layout")
    assert [(e.revision, e.name, stem(e.assembly), [stem(p) for p in e.parts]) for e in record.earlier] == [
        (0, "Reducer_12to1", "Reducer_12to1", ["Gear_m1.5_N17"])]
    assert sorted(stem(p.path) for p in record.parts) == ["Gear_m1.5_N17_r2", "Gear_m1.5_N68", "Gear_m2_N17",
                                                         "OutputGear"]
    assert [p.revision for p in record.parts if stem(p.path) == "Gear_m1.5_N17_r2"] == [2]
    assert [p.revision for p in record.parts if stem(p.path) == "Gear_m1.5_N68"] == [0]
    assert record.current_parts() == record.parts
    # and the next one is r3, never back on r0's files
    plan3 = plan_for(assessed(spec), record, disk)
    assert plan3.revision == 3 and plan3.build == ()


def test_parts_only_plans_reuse_and_resume_too():
    """Decision 9: Build parts goes through the same reuse, so it can carry on after a part that failed."""
    disk = Disk()
    a = assessed()
    plan = plan_for(a, None, disk, parts_only=True)
    assert plan.parts_only and (plan.layout_path, plan.assembly_path, plan.handles, plan.shafts) == ("", "", {}, ())
    result = run(plan, disk, fail_part=1)
    done = gearbox.finish_build(plan, result, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar)
    disk.write(done)
    assert done.record.gearbox is None and [stem(p.path) for p in done.record.parts] == ["Gear_m1.5_N17"]
    again = plan_for(a, done.record, disk, parts_only=True)
    assert [r.stem for r in again.reuse] == ["Gear_m1.5_N17"] and len(again.build) == 3


def test_parts_only_does_not_wait_for_tier_7(monkeypatch):
    monkeypatch.delattr(findings, "LAYOUT_PLUS_FLIP", raising=False)
    assert plan_for(assessed(), None, Disk(), parts_only=True).refusal == ""


@pytest.mark.parametrize("name", ["LAYOUT_PLUS_FLIP", "LAYOUT_NEGATED_LINK", "LAYOUT_AXIS_Z_SIGN",
                                  "REPLACE_FIXED_ROUTE", "WORKBOOK_LAYOUT_ROUTE"])
def test_a_finding_tier_7_has_not_committed_refuses_the_layout_with_a_sentence(monkeypatch, name):
    monkeypatch.delattr(findings, name, raising=False)
    plan = plan_for(assessed(), None, Disk())
    assert "probe tier 7" in plan.refusal and plan.refusal.endswith(".")
    with pytest.raises(ValueError):
        plan.build_kwargs()


def test_a_layout_route_other_than_layout_is_refused(monkeypatch):
    monkeypatch.setattr(findings, "WORKBOOK_LAYOUT_ROUTE", "parts only", raising=False)
    assert plan_for(assessed(), None, Disk()).refusal == (
        "The layout part and assembly are not built by this version, since probe tier 7 found 'parts only' "
        "(findings.WORKBOOK_LAYOUT_ROUTE), so only the parts can be built.")


@pytest.mark.parametrize("name,whose", [("Reducer_12to1_Layout", "the layout part's"),
                                        ("reducer_12to1_r3_layout", "the layout part's"),
                                        ("Reducer_12to1", "the assembly's"), ("Reducer_12to1_r2", "the assembly's")])
def test_a_part_named_like_the_gearboxs_own_files_is_refused_naming_its_cell(name, whose):
    """Review S5 / S4.9: it was built anyway, as a gear part literally named Reducer_12to1_Layout.SLDPRT."""
    spec = reducer()
    spec = replace(spec, gears=spec.gears[:3] + (replace(spec.gears[3], part_name=name, row=5),),
                   columns={"Gears": {"id": 1, "part_name": 18}})
    plan = plan_for(assessed(spec), None, Disk())
    assert plan.refusal == (f"Gears!R5: G4's part would be {name}.SLDPRT, which is a name of the gearbox's own "
                            "files (Reducer_12to1.SLDASM, Reducer_12to1_Layout.SLDPRT and their revisions; here "
                            f"{whose}), so nothing is built: give it another Part name.")
    assert plan.build == () and plan.revision == 0
    with pytest.raises(ValueError):
        plan.build_kwargs()


def test_the_frames_in_the_plan_are_the_reports():
    a = assessed()
    plan = plan_for(a, None, Disk())
    assert plan.frames == layout.frames(a.report)
    r = plan.frames["G2"].rotation
    assert math.degrees(math.atan2(r[3], r[0])) == pytest.approx(180 / 68)


def test_two_files_of_one_name_from_two_folders_are_refused():
    """SolidWorks keeps one document per file name (findings.SAME_NAME_OPEN_ERROR): a reused part from an earlier
    folder and a part to be made here under the same name cannot both go in."""
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk)
    record.gearbox, record.assembly = None, ""
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    old = "C:\\Old\\Gear_m1.5_N68_r2.SLDPRT"
    record.parts[1].path = old
    disk.add(old)
    spec = reducer()
    spec = replace(spec, gears=spec.gears[:3] + (replace(spec.gears[3], part_name="Gear_m1.5_N68_r2"),))
    again = plan_for(assessed(spec), record, disk)
    made = [j.path for j in plan_for(assessed(spec), None, Disk()).build if j.gear_ids == ("G4",)][0]
    assert again.refusal == (f"This build would use both {made} and {old}, and SolidWorks cannot have two documents "
                             "of one file name open at once: give the gear a Part name, or change the output "
                             "folder.")
    assert findings.SAME_NAME_OPEN_ERROR == 65536


def test_a_plan_builds_through_the_worker_and_its_finish_records_the_names_solidworks_kept():
    """plan_gearbox -> swbuild.build_gearbox on the fake -> finish_build, as the window will run them."""
    from test_swbuild import FakeSolidWorks, never_exists
    plan = plan_for(assessed(), None, Disk())
    result = swbuild.build_gearbox(FakeSolidWorks(), **plan.build_kwargs(), exists=never_exists)
    assert result.ok and result.clashes == []
    done = gearbox.finish_build(plan, result, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=lambda p: None)
    box = done.record.gearbox
    assert box.layout_component == result.components["layout"]
    assert [c.name for c in box.components] == [result.components[h] for h in plan.handles]
    assert len(done.sidecars) == 4 and box.assembly == plan.assembly_path


# -- the W4 review's findings, as regression tests ------------------------------------------------------------


COPY = "C:\\Copy\\Reducer_12to1.xlsx"
MOVED = "C:\\Moved\\Reducer_12to1.xlsx"


def assessed_at(source, spec=None):
    a = assess.assess(replace(spec or reducer(), source_path=source), [], FOLDER)
    assert a.lay_out_refusal() == ""
    return a


def _built_on_disk(disk, record=None):
    plan, result, record = build(assessed(), record, disk)
    return plan, record


def test_a_com_error_part_way_keeps_the_saved_parts_on_record_and_the_retry_reuses_them():
    """Review B1 (w4r_crash): the third save raised a non-SolidWorksError; the two parts SolidWorks had saved were
    on no record, and the next plan called them not built from this workbook and went to _r2."""
    from test_swbuild import FakeSolidWorks
    disk = Disk()
    a = assessed()
    plan = plan_for(a, None, disk)

    class ComErrorLookAlike(Exception):
        pass
    sw = FakeSolidWorks(raises={"save_as": (3, ComErrorLookAlike(-2147023170, "The remote procedure call failed.",
                                                                 None, None))})
    result = swbuild.build_gearbox(sw, **plan.build_kwargs(), exists=sw.exists)       # returns: nothing escapes
    assert not result.ok and [stem(r.saved) for r in result.parts.built if r.saved] == ["Gear_m1.5_N17",
                                                                                         "Gear_m1.5_N68"]
    disk.add(*sw.saved)
    done = gearbox.finish_build(plan, result, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar)
    disk.write(done)
    assert [stem(p.path) for p in done.record.parts] == ["Gear_m1.5_N17", "Gear_m1.5_N68"]
    again = plan_for(a, done.record, disk)
    assert (again.refusal, again.revision, again.name, again.made_new) == ("", 0, "Reducer_12to1", ())
    assert [r.stem for r in again.reuse] == ["Gear_m1.5_N17", "Gear_m1.5_N68"]
    assert [j.stem for j in again.build] == ["Gear_m2_N17", "OutputGear"]


def test_a_reused_part_is_checked_for_its_features_too():
    """Review S6: build_kwargs passed a reused part's globals only, so a part whose features were deleted or
    renamed by hand still passed the live check."""
    from test_swbuild import FakeSolidWorks

    def stopped_at_the_assembly():
        """The parts and the layout built and saved on a fake SolidWorks, the assembly not made; on record."""
        disk = Disk()
        plan = plan_for(assessed(), None, disk)
        sw = FakeSolidWorks(fail_on={"new_assembly": "There is no assembly template at 'C:\\T\\No.asmdot'."})
        result = swbuild.build_gearbox(sw, **plan.build_kwargs(), exists=sw.exists)
        disk.add(*sw.saved)
        done = gearbox.finish_build(plan, result, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                    read_sidecar=disk.read_sidecar)
        disk.write(done)
        sw.fail_on = {}
        return sw, plan_for(assessed(), done.record, disk), disk

    sw, again, disk = stopped_at_the_assembly()
    g2 = next(r for r in again.reuse if r.gear_ids == ("G2",))
    sidecar = disk.read_sidecar(store.sidecar_path(g2.path))
    assert g2.features == tuple(sidecar.record.features) and "Teeth" in g2.features
    assert again.build_kwargs()["reuse"][1].features == g2.features
    assert swbuild.build_gearbox(sw, **again.build_kwargs(), exists=sw.exists).ok      # all there: it goes ahead

    sw, again, disk = stopped_at_the_assembly()
    equations, made = sw.memory[norm(g2.path)]
    sw.memory[norm(g2.path)] = (equations, [f for f in made if f != "Teeth"])          # deleted in SolidWorks
    tried = sw.counts.get("new_assembly", 0)
    result = swbuild.build_gearbox(sw, **again.build_kwargs(), exists=sw.exists)
    assert result.mismatched == [(g2.path, 'Gear_m1.5_N68.SLDPRT cannot be reused: "Teeth" is no longer in it; it '
                                           "was renamed or deleted in SolidWorks.")]
    assert sw.counts.get("new_assembly", 0) == tried                                   # nothing was made


def test_a_sidecar_update_marked_unsaved_is_not_reused_until_the_file_is_newer():
    """Review B2: the .gear.json beside a part Update changed must not claim values the file may not hold. With the
    record lost, reuse by .gear.json skips a marked one until the file on disk is newer than the mark."""
    disk = Disk()
    plan, record = _built_on_disk(disk)
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    n68 = plan.part_of["G2"]
    key = norm(store.sidecar_path(n68))
    disk.sidecars[key] = store.updated_sidecar(disk.sidecars[key], disk.sidecars[key].record.spec,
                                               disk.sidecars[key].record.derived,
                                               disk.sidecars[key].record.variables, unsaved_since=5.0)
    times = {norm(n68): 5.0}
    again = plan_for(assessed(), None, disk, mtime=lambda p: times[norm(p)])
    assert again.refusal == "" and [m.why for m in again.made_new] == [gearbox.UNSAVED]
    assert [j.stem for j in again.build] == ["Gear_m1.5_N68_r2"] and len(again.reuse) == 3
    times[norm(n68)] = 6.0                                             # saved in SolidWorks since
    again = plan_for(assessed(), None, disk, mtime=lambda p: times[norm(p)])
    assert again.build == () and len(again.reuse) == 4 and again.made_new == ()


def test_a_copied_workbook_does_not_use_the_originals_record_or_files():
    """Review S1: a project folder copied whole brings the original's record, whose output folder is absolute; the
    copy's Update would have rewritten the original's parts. While the original is still there, the copy plans a
    gearbox of its own beside those files, sharing nothing, and its first build starts a record of its own."""
    disk = Disk()
    plan0, record = _built_on_disk(disk)
    disk.add(WORKBOOK)                                                 # the original is still there
    copied = store.link_record_from_json(store.link_record_to_json(record))
    a = assessed_at(COPY)
    plan = plan_for(a, copied, disk)
    assert plan.foreign_record == WORKBOOK and plan.refusal == ""
    assert plan.reuse == () and plan.revision == 2                     # its own revision, beside the original's
    assert [j.stem for j in plan.build] == ["Gear_m1.5_N17_r2", "Gear_m1.5_N68_r2", "Gear_m2_N17_r2", "OutputGear_r2"]
    assert {m.why for m in plan.made_new} == {gearbox.OTHER_WORKBOOK}
    result = run(plan, disk)
    done = gearbox.finish_build(plan, result, copied, workbook=COPY, digest="dc", written_by="test",
                                read_sidecar=disk.read_sidecar)
    rec = done.record
    assert rec.workbook == COPY and rec.earlier == [] and rec.moved_from == []
    assert sorted(stem(p.path) for p in rec.parts) == ["Gear_m1.5_N17_r2", "Gear_m1.5_N68_r2", "Gear_m2_N17_r2",
                                                       "OutputGear_r2"]
    assert rec.gearbox.revision == 2 and stem(rec.gearbox.assembly) == "Reducer_12to1_r2"
    assert all(s.record.workbook == COPY for _, s in done.sidecars)


def test_a_moved_workbook_adopts_its_record_and_still_knows_its_parts():
    """Review S1 and the Locate nit: the record's workbook is a path with no file now. Second review N1c: that is
    never adopted silently — it may be one of two copies of an original since deleted — so until the person says
    it was moved it is planned as a copy (``foreign_gone``). Once they say so, the record is adopted, the old path
    kept, and its parts' .gear.json, which name the old path, are still this workbook's."""
    disk = Disk()
    plan0, record = _built_on_disk(disk)                               # WORKBOOK is not on the disk: moved away
    for p in (plan0.layout_path, plan0.assembly_path):
        disk.remove(p)
    record.gearbox, record.assembly = None, ""
    a = assessed_at(MOVED)
    unanswered = plan_for(a, record, disk)
    assert unanswered.foreign_record == WORKBOOK and unanswered.foreign_gone and unanswered.reuse == ()
    store.settle_owner(record, MOVED, moved=True)                      # "Yes: it was moved or renamed"
    plan = plan_for(a, record, disk)
    assert plan.foreign_record == "" and plan.build == () and len(plan.reuse) == 4
    done = gearbox.finish_build(plan, run(plan, disk), record, workbook=MOVED, digest="dm", written_by="test",
                                read_sidecar=disk.read_sidecar)
    assert done.record.workbook == MOVED and done.record.moved_from == [WORKBOOK]
    # With the record's parts gone too, the .gear.json beside each part (naming WORKBOOK) still says it is ours.
    lost = store.LinkRecord(workbook=MOVED, moved_from=[WORKBOOK])
    for p in (plan.layout_path, plan.assembly_path):
        disk.remove(p)
    plan = plan_for(a, lost, disk)
    assert plan.build == () and len(plan.reuse) == 4
    # ... but not once a workbook stands at the old path again: that one is another workbook.
    disk.add(WORKBOOK)
    plan = plan_for(a, lost, disk)
    assert plan.reuse == () and {m.why for m in plan.made_new} == {gearbox.OTHER_WORKBOOK}


def test_every_pair_of_one_file_name_is_named():
    sentence = gearbox._same_file_name([r"C:\A\G1.SLDPRT", r"C:\B\G1.SLDPRT", r"C:\A\G2.SLDPRT", r"C:\C\g2.sldprt"])
    assert sentence == (r"This build would use both C:\A\G1.SLDPRT and C:\B\G1.SLDPRT; both C:\A\G2.SLDPRT and "
                        r"C:\C\g2.sldprt, and SolidWorks cannot have two documents of one file name open at once: "
                        "give the gear a Part name, or change the output folder.")


def test_a_part_that_fails_the_live_check_is_recorded_and_made_new_by_the_next_press():
    """Review B2's last corner (the orchestrator's ruling): Update set N68 to 69 teeth and was never saved;
    SolidWorks was closed without saving and the unchanged 68-tooth file saved later, so its time moved past the
    unsaved mark while the record still expects 69. The reuse check then refused on every press ("68 there and 69
    here"). Now the build answers with the part it found, its finish records it, and the next plan makes that
    part new."""
    from test_swbuild import FakeSolidWorks
    from gear_generator.workbook import update
    disk = Disk()
    sw = FakeSolidWorks()
    a = assessed()
    plan = plan_for(a, None, disk)
    first = swbuild.build_gearbox(sw, **plan.build_kwargs(), exists=sw.exists)
    disk.add(*sw.saved)
    done = gearbox.finish_build(plan, first, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar)
    disk.write(done)
    n68 = plan.part_of["G2"]
    as_built = tuple(list(held) for held in sw.saved[norm(n68)])     # the file, as the build saved it

    demo = replace(reducer(), shafts=(reducer().shafts[0], replace(reducer().shafts[1], x="64.5"),
                                      replace(reducer().shafts[2], x="132.5")),
                   gears=(reducer().gears[0], replace(reducer().gears[1], teeth="69")) + reducer().gears[2:])
    up = update.classify(done.record, assessed(demo), exists=disk.exists)
    changed = swbuild.update_gearbox(sw, **up.update_kwargs(), exists=sw.exists, mtime=lambda p: 100.0)
    fin = update.finish_update(up, changed, done.record, digest="d2", read_sidecar=disk.read_sidecar,
                               mtime=lambda p: 100.0)
    disk.write(fin)
    record = fin.record
    assert norm(n68) in {norm(p) for p in record.unsaved}

    sw.close_all()                          # closed without saving: the file still holds 68 teeth ...
    assert sw.saved[norm(n68)] == as_built
    store.clear_saved(record, mtime=lambda p: 200.0)                   # ... and was saved later, unchanged
    assert record.unsaved == {}
    structural = replace(demo, gears=(replace(demo.gears[0], bore=""),) + demo.gears[1:])
    again = plan_for(assessed(structural), record, disk, mtime=lambda p: 200.0)
    assert n68 in [r.path for r in again.reuse]                       # the record says it holds 69: reused

    stopped = swbuild.build_gearbox(sw, **again.build_kwargs(), exists=sw.exists, mtime=lambda p: 200.0)
    ((path, why),) = stopped.mismatched
    assert path == n68 and '"No. of Teeth" is 68 there and 69 here' in why and not stopped.ok
    assert stopped.parts.built == [] and stopped.assembly is None     # nothing made
    marked = gearbox.finish_build(again, stopped, record, workbook=WORKBOOK, digest="d3", written_by="test",
                                  read_sidecar=disk.read_sidecar)
    assert marked.record is not None and marked.record.mismatched == {n68: 200.0}
    assert marked.record.digest == record.digest
    # N68 was loaded from its file by the check (SolidWorks had been closed): Update's changes are gone from it, so
    # its .gear.json is no longer marked unsaved (second review N2); the mismatched mark is what holds it back now.
    assert [(norm(path), s.record.unsaved_since) for path, s in marked.sidecars] == [
        (norm(store.sidecar_path(n68)), 0.0)]
    round_trip = store.link_record_from_json(store.link_record_to_json(marked.record))
    assert round_trip.mismatched == {n68: 200.0}

    after = plan_for(assessed(structural), round_trip, disk, mtime=lambda p: 200.0)
    assert after.refusal == "" and n68 not in [r.path for r in after.reuse]
    (made,) = [m for m in after.made_new if m.why == gearbox.MISMATCHED]
    assert made.gear_ids == ("G2",) and made.old == n68 and stem(made.new) == "Gear_m1.5_N69"
    built = swbuild.build_gearbox(sw, **after.build_kwargs(), exists=sw.exists)
    assert built.ok and built.mismatched == []
    final = gearbox.finish_build(after, built, round_trip, workbook=WORKBOOK, digest="d3", written_by="test",
                                 read_sidecar=disk.read_sidecar)
    assert final.record.digest == "d3"
    # A file saved since the check is tried again (checked live, as ever), and a check that passes clears the mark.
    later = plan_for(assessed(structural), round_trip, disk, mtime=lambda p: 300.0)
    assert n68 in [r.path for r in later.reuse]
    cleared = gearbox.finish_build(later, swbuild.GearboxResult(checked=[n68]), round_trip, workbook=WORKBOOK,
                                   digest="d4", written_by="test", read_sidecar=disk.read_sidecar)
    assert cleared.record.mismatched == {}


def test_a_continued_layout_that_failed_the_live_check_is_left_and_the_next_revision_built():
    disk = Disk()
    a = assessed()
    plan, result, record = build(a, None, disk, fail_assembly=True)
    record.mismatched = {plan.layout_path: 5.0}
    again = plan_for(a, record, disk, mtime=lambda p: 5.0)
    assert again.revision == 2 and not isinstance(again.layout, LayoutReuse)
    assert again.revision_reason.startswith("Reducer_12to1_Layout.SLDPRT was saved by a build whose assembly was not "
                                            "made, but the last build found it no longer holds what was recorded")
    saved_since = plan_for(a, record, disk, mtime=lambda p: 6.0)
    assert saved_since.revision == 0 and isinstance(saved_since.layout, LayoutReuse)


# -- the second W4 review: marks that clear (N2), the journal (N4) -------------------------------------------------


DEMO = replace(reducer(), shafts=(reducer().shafts[0], replace(reducer().shafts[1], x="64.5"),
                                  replace(reducer().shafts[2], x="132.5")),
               gears=(reducer().gears[0], replace(reducer().gears[1], teeth="69")) + reducer().gears[2:])


def _live(times=None):
    """A first build on the fake SolidWorks, its finish written: (sw, disk, record, plan, mtime)."""
    from test_swbuild import FakeSolidWorks
    times = times if times is not None else {}
    mtime = lambda p: times.get(norm(p), 100.0)                         # noqa: E731
    disk, sw = Disk(), FakeSolidWorks()
    plan = plan_for(assessed(), None, disk)
    first = swbuild.build_gearbox(sw, **plan.build_kwargs(), exists=sw.exists, mtime=mtime)
    for handle, gear in plan.handles.items():          # each component where the build put it, by its Name2
        sw.frames[first.components[handle]] = (tuple(plan.frames[gear].rotation), tuple(plan.frames[gear].at))
    sw.saved_frames = dict(sw.frames)
    disk.add(*sw.saved)
    done = gearbox.finish_build(plan, first, None, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar, mtime=mtime)
    disk.write(done)
    return sw, disk, done.record, plan, mtime


def _update_live(sw, disk, record, spec, mtime, digest="d2"):
    from gear_generator.workbook import update
    up = update.classify(record, assessed(spec), exists=disk.exists)
    result = swbuild.update_gearbox(sw, **up.update_kwargs(), exists=sw.exists, mtime=mtime)
    fin = update.finish_update(up, result, record, digest=digest, read_sidecar=disk.read_sidecar, mtime=mtime)
    disk.write(fin)
    return result, fin.record


def test_an_update_lost_when_solidworks_closed_is_cleared_by_the_next_update_that_reads_the_files():
    """Second W4 review N2 (w4v_unsaved_never_clears): Update set N68 to 69 teeth and was never saved; SolidWorks
    was closed without saving; the person typed 68 back, which is what the file holds. Update read N68 holding 68
    and left it alone — and the unsaved marks stayed for ever, so every Build again… made G2's part new. The job now
    says which documents it loaded from their files: those hold in memory what their files hold, so marks go."""
    sw, disk, record, plan, mtime = _live()
    n68 = plan.part_of["G2"]
    result, record = _update_live(sw, disk, record, DEMO, mtime)
    assert {norm(p) for p in record.unsaved} == {norm(n68), norm(plan.layout_path), norm(plan.assembly_path)}
    assert result.opened == []                                         # all open since the build: nothing from disk
    assert disk.read_sidecar(store.sidecar_path(n68)).record.unsaved_since == 100.0
    sw.close_all()                                                     # SolidWorks closed without saving
    store.clear_saved(record, mtime=mtime)                             # no file is newer: still marked
    assert len(record.unsaved) == 3
    result, record = _update_live(sw, disk, record, reducer(), mtime, digest="d3")
    assert result.changed == [] and {norm(p) for p in result.opened} == {
        norm(p) for p in list(plan.part_of.values()) + [plan.layout_path, plan.assembly_path]}
    assert record.unsaved == {} and record.mismatched == {}
    sidecar = disk.read_sidecar(store.sidecar_path(n68)).record
    assert sidecar.unsaved_since == 0.0 and sidecar.spec["teeth"] == "68"
    from gear_generator import ui_text
    assert ui_text.workbook_built_tag(record, "d3") == " · built from this version"
    again = plan_for(assessed(replace(reducer(), gears=(replace(reducer().gears[0], bore=""),)
                                      + reducer().gears[1:])), record, disk, mtime=mtime)
    assert n68 in [r.path for r in again.reuse] and not [m for m in again.made_new if m.old == n68]


def test_an_update_put_back_after_solidworks_closed_marks_it_unsaved_again_and_clears_mismatched():
    sw, disk, record, plan, mtime = _live()
    n68 = plan.part_of["G2"]
    _, record = _update_live(sw, disk, record, DEMO, mtime)
    sw.close_all()
    record.mismatched = {n68: 100.0}                                   # whatever a check found before
    result, record = _update_live(sw, disk, record, DEMO, mtime, digest="d3")
    assert {norm(p) for p in result.changed} == {norm(n68), norm(plan.layout_path), norm(plan.assembly_path)}
    assert {norm(p) for p in record.unsaved} == {norm(n68), norm(plan.layout_path), norm(plan.assembly_path)}
    assert record.mismatched == {}                                     # in memory now; the save clears the rest


def test_a_part_proved_to_match_by_a_later_update_loses_its_mismatched_mark():
    sw, disk, record, plan, mtime = _live()
    n68 = plan.part_of["G2"]
    record.mismatched = {n68: 100.0}
    sw.close_all()
    _, record = _update_live(sw, disk, record, reducer(), mtime)
    assert record.mismatched == {}


def test_a_build_that_finds_an_unsaved_document_closed_marks_it_mismatched_not_unsaved():
    """A document marked unsaved that is not open when a job begins lost Update's changes when it was closed:
    the footer must never ask for a save that can no longer happen. Its file does not hold what the record says,
    which is what mismatched means, and planning makes the part new for that reason."""
    sw, disk, record, plan, mtime = _live()
    n68 = plan.part_of["G2"]
    _, record = _update_live(sw, disk, record, DEMO, mtime)
    sw.close_all()
    structural = replace(DEMO, gears=(replace(DEMO.gears[0], bore=""),) + DEMO.gears[1:])
    again = plan_for(assessed(structural), record, disk, mtime=mtime)
    assert [m.why for m in again.made_new if m.old == n68] == [gearbox.UNSAVED]
    result = swbuild.build_gearbox(sw, **again.build_kwargs(), exists=sw.exists, mtime=mtime)
    assert result.ok and result.open_before == []
    done = gearbox.finish_build(again, result, record, workbook=WORKBOOK, digest="d3", written_by="test",
                                read_sidecar=disk.read_sidecar, mtime=mtime)
    assert done.record.unsaved == {}
    assert norm(n68) in {norm(p) for p in done.record.mismatched}
    assert disk.read_sidecar(store.sidecar_path(n68)).record.unsaved_since == 100.0
    disk.write(done)
    assert disk.read_sidecar(store.sidecar_path(n68)).record.unsaved_since == 0.0


def test_the_journal_makes_an_interrupted_builds_parts_reusable_once_checked_live():
    """Second W4 review N4.3: a build interrupted after SolidWorks saved some parts and before the finish (a crash,
    a kill, a power cut, quitting while SolidWorks did not answer) left files with no .gear.json and no record:
    the next build called them files with no record and went beside them. The journal written before the worker
    starts says they are this workbook's, so they are planned for reuse and checked live like any reused part."""
    from test_swbuild import FakeSolidWorks
    disk, sw = Disk(), FakeSolidWorks()
    a = assessed()
    plan = plan_for(a, None, disk)
    record = store.LinkRecord(workbook=WORKBOOK, pending=gearbox.journal(plan), pending_for=WORKBOOK)
    assert [e.kind for e in record.pending] == ["spur"] * 4 + ["layout", "assembly"]
    # The job saved two parts, then the app was gone: nothing collected, nothing written but the journal.
    swbuild.build_many(sw, [j.plan for j in plan.build[:2]], sw.exists)
    disk.add(*sw.saved)
    assert disk.read_sidecar(store.sidecar_path(plan.build[0].path)) is None
    again = plan_for(a, store.link_record_from_json(store.link_record_to_json(record)), disk)
    assert again.revision == 0 and again.made_new == ()
    assert [r.stem for r in again.reuse] == ["Gear_m1.5_N17", "Gear_m1.5_N68"] and all(r.journaled
                                                                                       for r in again.reuse)
    assert [j.stem for j in again.build] == ["Gear_m2_N17", "OutputGear"]
    # The new journal keeps the two (they still have no .gear.json) beside what this build makes.
    assert [stem(e.path) for e in gearbox.journal(again)][:4] == ["Gear_m2_N17", "OutputGear", "Gear_m1.5_N17",
                                                                   "Gear_m1.5_N68"]
    result = swbuild.build_gearbox(sw, **again.build_kwargs(), exists=sw.exists)
    assert result.ok and result.checked[:2] == [r.path for r in again.reuse]
    assert set(result.held.values()) == {"degrees"}
    record.pending = gearbox.journal(again)
    done = gearbox.finish_build(again, result, record, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar)
    assert done.record.pending == [] and done.record.pending_for == ""
    written = {stem(p)[:-len(".gear")]: s for p, s in done.sidecars}
    assert set(written) == {"Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear"}
    assert written["Gear_m1.5_N17"].record.workbook == WORKBOOK and written["Gear_m1.5_N17"].record.trig == "degrees"
    assert written["Gear_m1.5_N17"].record.variables
    assert {stem(p.path) for p in done.record.parts} == set(written)


def test_a_journaled_part_for_other_values_is_ours_and_stale_and_one_not_on_disk_is_dropped():
    from test_swbuild import FakeSolidWorks
    disk, sw = Disk(), FakeSolidWorks()
    plan = plan_for(assessed(), None, disk)
    record = store.LinkRecord(workbook=WORKBOOK, pending=gearbox.journal(plan), pending_for=WORKBOOK)
    swbuild.build_many(sw, [plan.build[1].plan], sw.exists)            # only N68 saved
    disk.add(*sw.saved)
    changed = replace(reducer(), gears=(reducer().gears[0], replace(reducer().gears[1], part_name="Big",
                                                                    teeth="68", face_width="16"))
                      + reducer().gears[2:])
    again = plan_for(assessed(changed), record, disk)
    assert again.reuse == () and again.made_new == ()                  # "Big" is free; N68 is not in its way
    record.pending[1] = replace(record.pending[1], path=path("Big.SLDPRT"))   # as if Big had been planned then
    disk.add(path("Big.SLDPRT"))
    again = plan_for(assessed(changed), record, disk)
    assert [(m.why, stem(m.new)) for m in again.made_new] == [(gearbox.STALE, "Big_r2")]
    # Another workbook's journal (a copy's, say) is not this one's.
    record.pending_for = r"C:\Elsewhere\Other.xlsx"
    again = plan_for(assessed(changed), record, disk)
    assert [m.why for m in again.made_new] == [gearbox.NO_RECORD]


def test_a_journaled_layout_is_reused_once_checked_and_a_journaled_assembly_is_gone_beside():
    from test_swbuild import FakeSolidWorks
    disk, sw = Disk(), FakeSolidWorks()
    a = assessed()
    plan = plan_for(a, None, disk)
    record = store.LinkRecord(workbook=WORKBOOK, pending=gearbox.journal(plan), pending_for=WORKBOOK)
    swbuild.build_many(sw, [j.plan for j in plan.build] + [plan.layout], sw.exists)
    disk.add(*sw.saved)
    again = plan_for(a, record, disk)
    assert again.revision == 0 and isinstance(again.layout, LayoutReuse) and again.layout.journaled
    assert len(again.reuse) == 4 and again.build == ()
    result = swbuild.build_gearbox(sw, **again.build_kwargs(), exists=sw.exists)
    assert result.ok and result.layout_reused == plan.layout_path
    # Had the assembly been saved too, the build goes beside it, saying why.
    disk.add(plan.assembly_path)
    beside = plan_for(a, record, disk)
    assert beside.revision == 2 and beside.revision_reason == (
        "Reducer_12to1.SLDASM was saved by a build that was interrupted before it was put on record, and a build "
        "never overwrites a file. So this build is Reducer_12to1_r2, beside it; nothing is overwritten.")


def test_a_finish_that_made_nothing_still_takes_the_journal_out():
    disk = Disk()
    plan = plan_for(assessed(), None, disk)
    record = store.LinkRecord(workbook=WORKBOOK, pending=gearbox.journal(plan), pending_for=WORKBOOK)
    done = gearbox.finish_build(plan, swbuild.GearboxResult(), record, workbook=WORKBOOK, digest="d",
                                written_by="t", read_sidecar=disk.read_sidecar)
    assert done.record is not None and done.record.pending == [] and done.record.parts == []
    # A copy's journal sits in the record that came with it: taken out of that record, which stays the other's.
    disk.add(WORKBOOK)
    other = store.LinkRecord(workbook=WORKBOOK, digest="theirs", parts=[store.PartEntry(path=path("X.SLDPRT"))])
    copy_plan = plan_for(assessed_at(COPY), other, disk)
    other.pending, other.pending_for = gearbox.journal(copy_plan), COPY
    done = gearbox.finish_build(copy_plan, swbuild.GearboxResult(), other, workbook=COPY, digest="d",
                                written_by="t", read_sidecar=disk.read_sidecar)
    assert done.record.workbook == WORKBOOK and done.record.digest == "theirs" and done.record.pending == []


def test_one_workbook_reached_by_another_path_keeps_its_record_through_a_build(tmp_path):
    """Second W4 review N1a (w4v_same_file_two_paths): the record named the workbook by one path (a mapped drive,
    say) and the window opened it by another (its UNC path): compared as text it was a copy of itself, and the next
    build's finish wrote a fresh record over its own — the same file — losing the gearbox and ``earlier``."""
    real = tmp_path / "share"
    real.mkdir()
    (tmp_path / "Z").symlink_to(real, target_is_directory=True)
    workbook, alias = real / "Reducer_12to1.xlsx", tmp_path / "Z" / "Reducer_12to1.xlsx"
    workbook.write_bytes(b"x")
    disk = Disk()
    a = assessed_at(str(workbook))
    plan, result, record = build(a, None, disk)
    record.workbook = str(workbook)
    record.earlier = [store.EarlierRevision(revision=0, name="Old")]
    through = assessed_at(str(alias), replace(reducer(), gears=(replace(reducer().gears[0], bore=""),)
                                               + reducer().gears[1:]))
    again = plan_for(through, record, disk)
    assert again.foreign_record == "" and again.revision == 2 and len(again.reuse) == 3
    done = gearbox.finish_build(again, run(again, disk), record, workbook=str(alias), digest="d2",
                                written_by="test", read_sidecar=disk.read_sidecar)
    assert done.record.workbook == str(workbook) and done.record.moved_from == []
    assert [e.name for e in done.record.earlier] == ["Old", "Reducer_12to1"]      # kept, and the first build added
    assert done.record.gearbox.revision == 2


# -- the third W4 review ---------------------------------------------------------------------------------------


def test_a_document_holding_unsaved_changes_is_never_counted_loaded_from_its_file_whatever_the_list_says():
    """Third W4 review item 1 (w4x_documents_cap): Update left N68 changed and open; more than 200 documents were
    loaded, so documents() (which stopped at 200) did not list it; the next Update counted it loaded from its file
    and its finish took the unsaved marks off while the changes were still unsaved in SolidWorks. The walk now goes
    to the end of the list, and as the belt a document opened is counted from disk only if GetSaveFlag reads it
    holding nothing unsaved — this test cuts the list short, as the old walk did, and the belt alone holds."""
    sw, disk, record, plan, mtime = _live()
    n68 = plan.part_of["G2"]
    _, record = _update_live(sw, disk, record, DEMO, mtime)
    marked = {norm(p) for p in record.unsaved}
    assert norm(n68) in marked
    listed = list(sw.open_docs)
    sw.documents = lambda: [d for d in listed if "N68" not in d.path]       # the 200-document cut stood in for
    result, record = _update_live(sw, disk, record, DEMO, mtime, digest="d3")
    assert norm(n68) not in {norm(p) for p in result.opened}
    assert norm(n68) in {norm(p) for p in record.unsaved}
    assert disk.read_sidecar(store.sidecar_path(n68)).record.unsaved_since == 100.0


def test_when_the_documents_open_are_not_known_no_document_counts_as_loaded_from_its_file():
    """open_before None means not known: _from_disk is then never True, so nothing is listed in ``opened`` and the
    finishes clear no mark on its account (they skip the open_before rule when it is None)."""
    from test_swbuild import FakeSolidWorks
    assert not swbuild._from_disk("C:\\P\\A.SLDPRT", None)
    unknown = swbuild.GearboxUpdate()
    swbuild._note_opened(FakeSolidWorks(), "C:\\P\\A.SLDPRT", unknown)
    assert unknown.opened == [] and unknown.open_before is None
    sw, disk, record, plan, mtime = _live()
    _, record = _update_live(sw, disk, record, DEMO, mtime)
    sw.close_all()
    from gear_generator.workbook import update
    up = update.classify(record, assessed(reducer()), exists=disk.exists)
    result = swbuild.update_gearbox(sw, **up.update_kwargs(), exists=sw.exists, mtime=mtime)
    result.open_before, result.opened = None, []
    fin = update.finish_update(up, result, record, digest="d3", read_sidecar=disk.read_sidecar, mtime=mtime)
    assert {norm(p) for p in fin.record.unsaved} == {norm(p) for p in record.unsaved}


def test_a_list_of_open_documents_that_never_ends_refuses_the_job_before_anything_is_made():
    """Decision 7's same-name check cannot pass silently on a list it could not read to the end."""
    from test_swbuild import FakeSolidWorks
    from gear_generator import swcom
    disk = Disk()
    plan = plan_for(assessed(), None, disk)
    sw = FakeSolidWorks()

    def runaway():
        raise swcom.DocumentsUnknown("SolidWorks listed 100000 open documents without coming to the end of its list, "
                                     "so which documents it holds open cannot be known here, and nothing that "
                                     "depends on it is started; restart SolidWorks and try again.")
    sw.documents = runaway
    with pytest.raises(swcom.DocumentsUnknown, match="nothing that depends on it is started"):
        swbuild.build_gearbox(sw, **plan.build_kwargs(), exists=sw.exists)
    assert sw.saved == {} and "new_part" not in [c[0] for c in sw.calls]


def _interrupted(disk, sw):
    """An interrupted first build: the journal written, N17 and N68 saved by SolidWorks, nothing collected."""
    a = assessed()
    plan = plan_for(a, None, disk)
    record = store.LinkRecord(workbook=WORKBOOK, pending=gearbox.journal(plan), pending_for=WORKBOOK)
    swbuild.build_many(sw, [j.plan for j in plan.build[:2]], sw.exists)
    disk.add(*sw.saved)
    return a, plan, record


def test_a_refused_job_never_orphans_what_an_interrupted_build_saved():
    """Third W4 review item 3 (w4x_clear_journal_orphans): the next Build's job was refused at its pre-flight (here a
    same-named document open elsewhere; SolidWorks not running does the same) and the window cleared the whole
    journal, so the two files the interrupted build saved became files with no record and the plan after went
    beside them as _r2. Now only what is not on disk, or is on record, leaves the journal."""
    from test_swbuild import FakeSolidWorks
    from gear_generator.swcom import DocInfo
    disk, sw = Disk(), FakeSolidWorks()
    a, plan, record = _interrupted(disk, sw)
    again = plan_for(a, record, disk)
    assert [(r.stem, r.journaled) for r in again.reuse] == [("Gear_m1.5_N17", True), ("Gear_m1.5_N68", True)]
    record.pending = gearbox.merged_journal(record, gearbox.journal(again), WORKBOOK, exists=disk.exists,
                                            read_sidecar=disk.read_sidecar)
    sw2 = FakeSolidWorks(open_docs=[DocInfo(title="Gear_m2_N17.SLDPRT", path="D:\\Other\\Gear_m2_N17.SLDPRT",
                                            doc_type=1)])
    sw2.saved = dict(sw.saved)
    with pytest.raises(swbuild.BuildError):
        swbuild.build_gearbox(sw2, **again.build_kwargs(), exists=sw2.exists)
    # What the window does with a build answered with a raise (WorkbookWindow._settle_journal):
    record.pending = gearbox.settled_journal(record.pending, record, exists=disk.exists, read_sidecar=disk.read_sidecar)
    assert sorted(stem(e.path) for e in record.pending) == ["Gear_m1.5_N17", "Gear_m1.5_N68"]
    third = plan_for(a, record, disk)
    assert [r.stem for r in third.reuse] == ["Gear_m1.5_N17", "Gear_m1.5_N68"] and third.made_new == ()
    assert [j.stem for j in third.build] == ["Gear_m2_N17", "OutputGear"]


def test_a_new_journal_is_merged_by_path_into_the_old_never_replacing_it():
    """Close anyway, then a new Build: its journal replaced the old one, so files the abandoned job saved afterwards
    were in no journal. Merged by path, what the old journal names and the new plan does not stays."""
    from test_swbuild import FakeSolidWorks
    disk, sw = Disk(), FakeSolidWorks()
    a, plan, record = _interrupted(disk, sw)
    disk.add(plan.build[2].path)                                    # a third saved after the new journal was planned
    narrow = gearbox.journal(plan_for(a, record, disk))
    narrow = [e for e in narrow if stem(e.path) == "OutputGear"]
    merged = gearbox.merged_journal(record, narrow, WORKBOOK, exists=disk.exists, read_sidecar=disk.read_sidecar)
    assert stem(merged[0].path) == "OutputGear"
    assert sorted(stem(e.path) for e in merged[1:]) == ["Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17"]
    # Another workbook's journal (a copy's original's, carried in the folder) is never merged into this one's.
    record.pending_for = r"C:\Elsewhere\Other.xlsx"
    assert gearbox.merged_journal(record, narrow, WORKBOOK, exists=disk.exists,
                                  read_sidecar=disk.read_sidecar) == narrow


def test_a_journaled_part_that_fails_its_live_check_stays_this_workbooks_with_its_mismatched_mark():
    """Third W4 review (ride-along): the finish took the whole journal out, so a journaled part found not holding
    what it should got its mismatched mark and then read as "no record that this workbook built it"."""
    from test_swbuild import FakeSolidWorks
    disk, sw = Disk(), FakeSolidWorks()
    a, plan, record = _interrupted(disk, sw)
    n68 = plan.build[1].path
    again = plan_for(a, record, disk)
    sw.close_all()
    sw.saved[n68.lower().replace("/", "\\")] = ([], [])             # its globals gone by hand
    result = swbuild.build_gearbox(sw, **again.build_kwargs(), exists=sw.exists, mtime=lambda p: 50.0)
    assert [stem(p) for p, _ in result.mismatched] == ["Gear_m1.5_N68"]
    record.pending = gearbox.journal(again)
    done = gearbox.finish_build(again, result, record, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar, mtime=lambda p: 50.0, exists=disk.exists)
    assert norm(n68) in {norm(e.path) for e in done.record.pending}
    assert norm(n68) in {norm(p) for p in done.record.mismatched}
    after = plan_for(a, done.record, disk, mtime=lambda p: 50.0)
    reasons = {stem(m.old): m.why for m in after.made_new}
    assert reasons["Gear_m1.5_N68"] == gearbox.MISMATCHED
    assert gearbox.NO_RECORD not in reasons.values()


def test_a_finish_takes_out_only_what_is_on_record_or_gone():
    """The finish of a build that saved its parts but not its assembly: the parts are on record and leave the
    journal; the assembly it never saved is not on disk and leaves too; nothing on disk and off record is lost."""
    disk = Disk()
    a = assessed()
    plan = plan_for(a, None, disk)
    record = store.LinkRecord(workbook=WORKBOOK, pending=gearbox.journal(plan), pending_for=WORKBOOK)
    stray = path("Stray.SLDPRT")
    disk.add(stray)
    record.pending.append(store.PartEntry(path=stray, kind="spur"))  # an earlier interrupted build's, still off record
    result = run(plan, disk, fail_assembly=True)
    done = gearbox.finish_build(plan, result, record, workbook=WORKBOOK, digest="d1", written_by="test",
                                read_sidecar=disk.read_sidecar, exists=disk.exists)
    assert [stem(e.path) for e in done.record.pending] == ["Stray"] and done.record.pending_for == WORKBOOK


def test_after_no_with_the_original_gone_nothing_says_it_is_still_there():
    """Third W4 review item 4 (w4x_copy_of_gone_sentence)."""
    from gear_generator import ui_text
    from gear_generator.workbook import update
    disk = Disk()
    _, record = _built_on_disk(disk)                                  # WORKBOOK not on disk: gone
    store.settle_owner(record, MOVED, moved=False)                    # answered No, this session
    a = assessed_at(MOVED)
    p = plan_for(a, record, disk)
    assert (p.foreign_record, p.foreign_gone, p.foreign_said) == (WORKBOOK, False, True)
    footer = ui_text.workbook_footer(a, record=None, plan=p, update=None, folder=FOLDER).text
    assert "still there" not in footer and "which you said this workbook is a copy of" in footer
    refusal = update.classify(record, a, exists=disk.exists).refusal
    assert "still there" not in refusal and "which you said this workbook is a copy of" in refusal
    # The original back on disk: a copy because it is there, and said so.
    disk.add(WORKBOOK)
    p = plan_for(a, record, disk)
    assert p.foreign_said is False and "which is still there" in ui_text.workbook_footer(
        a, record=None, plan=p, update=None, folder=FOLDER).text


# -- W5: the gearbox that turns (W5-PLAN §3.2 B, as W5-INTERFACES and W5-DECISIONS amend it) ----------------------

from gear_generator.gears.base import Mate  # noqa: E402

REFUSED = "SolidWorks would not make the mate G3 locked to G2."


def components_of(plan):
    return [(h, plan.part_of[g], plan.frames[g]) for h, g in plan.handles.items()]


def test_a_turning_plan_carries_its_motion_plan_and_the_mated_assembly(turning):
    plan = plan_for(assessed(), None, Disk())
    assert plan.refusal == "" and plan.static_reason == "" and plan.motion is not None
    assert dict(plan.motion.anchors) == {"S1": "G1", "S2": "G2", "S3": "G4"} and plan.motion.drag == ("G1",)
    a = assessed()
    assert plan.motion == motion.motion_plan(a.spec, a.report, plan.frames)
    assert plan.assembly == motion.motion_assembly_plan(plan.layout_path, components_of(plan),
                                                        {g: h for h, g in plan.handles.items()}, plan.motion,
                                                        plan.assembly_template, plan.assembly_path)
    assert plan.assembly.check() == [] and swbuild.is_mated(plan.assembly)
    kwargs = plan.build_kwargs()
    assert set(kwargs) == {"parts", "reuse", "layout", "assembly", "gears"} and kwargs["assembly"] is plan.assembly
    assert gearbox.journal(plan)[-1].path == plan.assembly_path


def test_a_w5_finding_missing_plans_w4s_static_assembly_and_says_why(turning, monkeypatch):
    monkeypatch.delattr(findings, "COMPOUND_LOCK_ROUTE")
    plan = plan_for(assessed(), None, Disk())
    assert plan.refusal == "" and plan.motion is None
    assert plan.static_reason == motion.motion_reason() and "findings.COMPOUND_LOCK_ROUTE" in plan.static_reason
    assert plan.assembly == layout.assembly_plan(plan.layout_path, components_of(plan), plan.assembly_template,
                                                 plan.assembly_path)
    assert not any(isinstance(op, Mate) for op in plan.assembly.ops)


def test_a_parts_only_or_refused_plan_has_neither_motion_nor_a_static_reason(turning):
    plan = plan_for(assessed(), None, Disk(), parts_only=True)
    assert (plan.motion, plan.static_reason, plan.assembly) == (None, "", None)


def test_a_continued_revision_is_planned_turning_too(turning):
    disk, a = Disk(), assessed()
    _, _, record = build(a, None, disk, fail_assembly=True)
    again = plan_for(a, record, disk)
    assert isinstance(again.layout, LayoutReuse) and again.motion is not None and swbuild.is_mated(again.assembly)


def test_finishing_a_turning_build_records_its_mates_unmated_fixed_and_drag(turning):
    disk = Disk()
    plan, result, record = build(assessed(), None, disk)
    box = record.gearbox
    assert box.kind == motion.MOTION and box.static_reason == ""
    assert box.mates == [motion.mate_entry(m) for m in plan.motion.mates]
    assert [motion.mate_ref(e) for e in box.mates][4] == swbuild.MateRef("G3 locked to G2", "lock", ("G2", "G3"))
    assert (box.unmated, box.fixed, box.drag) == ([], [], ["G1"])
    assert (box.mate_problems, box.mate_problems_digest) == ([], "")
    again = store.link_record_from_json(store.link_record_to_json(record))
    assert again.gearbox.mates == box.mates and again.gearbox.kind == motion.MOTION


def test_finishing_a_static_build_records_why_it_is_static(turning, monkeypatch):
    monkeypatch.setattr(findings, "MOTION_ROUTE", None)
    plan, _, record = build(assessed(), None, Disk())
    box = record.gearbox
    assert box.kind == motion.STATIC and box.static_reason == plan.static_reason != ""
    assert (box.mates, box.unmated, box.fixed, box.drag) == ([], [], [], [])


def test_w4s_tests_build_static_for_the_reason_their_fixture_gives():
    plan, _, record = build(assessed(), None, Disk())
    assert plan.motion is None and not swbuild.is_mated(plan.assembly)
    assert record.gearbox.kind == motion.STATIC and record.gearbox.static_reason == STATIC_FOR_W4


def finish(plan, result, record=None, digest="d1", disk=None):
    return gearbox.finish_build(plan, result, record, workbook=WORKBOOK, digest=digest, written_by="test",
                                read_sidecar=(disk or Disk()).read_sidecar, stamp="2026-11-14T00:00:00Z")


@pytest.mark.parametrize("reported,note", [("", False), (motion.MOTION, False), (motion.STATIC, True),
                                           ("odd", True)])
def test_the_plan_alone_decides_the_kind_and_a_worker_that_disagrees_is_noted(turning, reported, note):
    disk = Disk()
    plan = plan_for(assessed(), None, disk)
    result = run(plan, disk)
    result.kind = reported
    done = finish(plan, result, disk=disk)
    assert done.record.gearbox.kind == motion.MOTION
    said = [n for n in done.notes if "planned to turn" in n]
    assert bool(said) == note
    if note:
        assert said[0].startswith("The job reported the assembly as built ") and said[0].endswith(".")


def refused(plan, disk, problems=(REFUSED,)):
    result = run(plan, disk, fail_assembly=True)
    result.assembly.mate_problems = list(problems)
    result.assembly.failures = [("mate", p) for p in problems] or result.assembly.failures
    return result


def test_a_refused_mate_keeps_the_parts_and_layout_and_records_what_was_refused_and_for_which_read(turning):
    disk = Disk()
    plan = plan_for(assessed(), None, disk)
    done = finish(plan, refused(plan, disk), disk=disk)
    disk.write(done)
    box = done.record.gearbox
    assert (box.layout, box.assembly, box.components) == (plan.layout_path, "", [])
    assert (box.mate_problems, box.mate_problems_digest) == ([REFUSED], "d1")
    assert box.kind == motion.STATIC and box.mates == [] and done.record.digest == ""
    assert len(done.record.parts) == 4
    record = done.record

    # The same read refused again on a continued revision (nothing made): nothing new to record.
    again = plan_for(assessed(), record, disk)
    assert again.motion is not None and isinstance(again.layout, LayoutReuse)
    assert finish(again, refused(again, disk), record, disk=disk).record is None

    # A changed workbook refused again: only the problems and their read change on record.
    other = finish(again, refused(again, disk, ("The mate G1 meshes G2 is in error in SolidWorks.",)), record,
                   digest="d2", disk=disk)
    assert other.record.gearbox.mate_problems == ["The mate G1 meshes G2 is in error in SolidWorks."]
    assert other.record.gearbox.mate_problems_digest == "d2"
    assert other.record.gearbox.built == record.gearbox.built and other.record.digest == ""
    record = other.record

    # Built at last: the problems go, the kind and mates come.
    last = finish(again, run(again, disk), record, digest="d3", disk=disk)
    box = last.record.gearbox
    assert (box.mate_problems, box.mate_problems_digest, box.kind) == ([], "", motion.MOTION)
    assert box.assembly == plan.assembly_path and last.record.digest == "d3"


def test_an_assembly_failure_that_is_no_refusal_leaves_no_mate_problem(turning):
    disk = Disk()
    plan = plan_for(assessed(), None, disk)
    done = finish(plan, run(plan, disk, fail_assembly=True), disk=disk)
    assert (done.record.gearbox.mate_problems, done.record.gearbox.mate_problems_digest) == ([], "")
