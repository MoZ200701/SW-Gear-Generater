"""Planning a gearbox build and recording it (docs/PLAN-WORKBOOK.md §4.2–§4.5, phase W4)."""

import math
import os

import pytest

from gear_generator import findings, store, swbuild
from gear_generator.gears.base import (AddComponent, BuildPlan, GlobalVariable, NewAssembly, NewPart, SaveAs)
from gear_generator.spec import GearSpec
from gear_generator.workbook import assess, gearbox, layout
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
    equations, made = sw.saved[norm(g2.path)]
    sw.saved[norm(g2.path)] = (equations, [f for f in made if f != "Teeth"])           # deleted in SolidWorks
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
    """Review S1 and the Locate nit: the record's workbook is a path with no file now, so the workbook was moved or
    renamed — the record is adopted, the old path kept, and its parts' .gear.json, which name the old path, are
    still this workbook's."""
    disk = Disk()
    plan0, record = _built_on_disk(disk)                               # WORKBOOK is not on the disk: moved away
    for p in (plan0.layout_path, plan0.assembly_path):
        disk.remove(p)
    record.gearbox, record.assembly = None, ""
    a = assessed_at(MOVED)
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
    as_built = tuple(list(held) for held in sw.saved[norm(n68)])     # the fake changes its saved lists in place

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

    sw.saved[norm(n68)] = as_built          # closed without saving: the file still holds 68 teeth ...
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
    assert marked.record.digest == record.digest and marked.sidecars == []
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
