"""Batch parts from a workbook, the live link, and what is remembered (docs/PLAN-WORKBOOK.md W2)."""

import os

import pytest

from gear_generator import store, swbuild
from gear_generator.gears import kind_for
from gear_generator.spec import GearSpec
from gear_generator.workbook import build, link, model, xlsx
from gear_generator.workbook.model import Gear
from test_swbuild import FakeSolidWorks, never_exists
from test_workbook_model import reducer, transfer_case, write

FOLDER = "C:\\Parts\\Reducer_12to1"


def from_file(path):
    return model.from_book(xlsx.read(path))[0]


# -- every row builds the strip's part ---------------------------------------------


def strip_plan(spec: GearSpec, path: str):
    """What gui._plan_single makes for the same form: the strip's own call, written out."""
    kind = kind_for(spec)
    return kind.plan(spec, kind.derive(spec), kind.recipe_for(spec), "", path)


def test_each_row_builds_exactly_the_strips_part(tmp_path):
    spec = from_file(write(tmp_path, reducer()))
    parts = build.plan_parts(spec, FOLDER)
    assert parts.buildable and parts.errors == [] and parts.later == []
    # The strip's own warnings come through too, each pointing at its cell (here the fillet's, column Q).
    assert {d.field for d in parts.diagnostics} == {"Gears!Q3", "Gears!Q5"}
    assert [j.stem for j in parts.jobs] == ["Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear"]
    typed = {  # the strip's form for each gear, as a person would type it there
        "G1": GearSpec(module="1.5", teeth="17", face_width="15", bore="8", pressure_angle="20"),
        "G2": GearSpec(module="1.5", teeth="68", face_width="15", bore="12", pressure_angle="20"),
        "G3": GearSpec(module="2", teeth="17", face_width="20", bore="12", pressure_angle="20"),
        "G4": GearSpec(module="2", teeth="51", face_width="20", bore="16", pressure_angle="20", name="OutputGear"),
    }
    for job in parts.jobs:
        (gear_id,) = job.gear_ids
        assert job.path == os.path.join(FOLDER, job.stem + ".SLDPRT")
        assert job.plan == strip_plan(typed[gear_id], job.path)


def test_identical_gears_share_one_part(tmp_path):
    spec = reducer()
    twin = Gear("G5", "S3", "47", "spur", "external", "17", "1.5", "", "15", "8")
    spec = model.replace(spec, gears=spec.gears + (twin,))
    parts = build.plan_parts(from_file(write(tmp_path, spec)), FOLDER)
    assert [j.gear_ids for j in parts.jobs][0] == ("G1", "G5")
    assert len(parts.jobs) == 4


def test_two_gears_one_name_is_caught(tmp_path):
    spec = reducer()
    wider = Gear("G5", "S3", "47", "spur", "external", "17", "1.5", "", "25", "8")   # G1 but 25 wide
    spec = model.replace(spec, gears=spec.gears + (wider,))
    parts = build.plan_parts(from_file(write(tmp_path, spec)), FOLDER)
    assert not parts.buildable and parts.jobs == []
    (error,) = parts.errors
    assert error.field == "Gears!T6"
    assert "G5 and G1 would both be Gear_m1.5_N17.SLDPRT" in error.message and "Part name" in error.message


def test_kinds_a_later_phase_builds_are_set_aside(tmp_path):
    spec = from_file(write(tmp_path, transfer_case(), "tc.xlsx"))
    parts = build.plan_parts(spec, FOLDER)
    assert parts.jobs == [] and not parts.buildable
    assert [g for g, _ in parts.later] == ["InDog", "LoDog", "RangeSlv", "FrontDog", "ModeSlv"]
    assert "W8" in parts.later[0][1]


def test_the_strips_own_checks_name_the_cell(tmp_path):
    path = write(tmp_path, reducer())
    xlsx.write_cells(str(path), {"Gears": {"F2": 3}})          # three teeth: the strip refuses it
    spec = from_file(path)
    diagnostics = build.gear_diagnostics(spec)
    errors = [d for d in diagnostics if d.is_error]
    assert errors and all(d.message.startswith(d.field + ": G1: ") for d in errors)
    assert errors[0].field.startswith("Gears!")
    assert not build.plan_parts(spec, FOLDER).buildable


def test_the_boxs_part_template_wins(tmp_path):
    spec = model.replace(reducer(), box=model.replace(reducer().box, part_template="C:\\T\\gear.prtdot"))
    parts = build.plan_parts(from_file(write(tmp_path, spec)), FOLDER, part_template="C:\\T\\other.prtdot")
    assert parts.jobs[0].plan.ops[0].template == "C:\\T\\gear.prtdot"


# -- building a batch --------------------------------------------------------------


def plans(tmp_path):
    return [j.plan for j in build.plan_parts(from_file(write(tmp_path, reducer())), FOLDER).jobs]


def test_a_batch_builds_every_part_in_order(tmp_path):
    fake = FakeSolidWorks()
    many = swbuild.build_many(fake, plans(tmp_path), never_exists)
    assert many.ok and len(many.built) == 4 and many.skipped == []
    saved = [args[0] for name, args in fake.calls if name == "save_as"]
    assert [os.path.basename(p) for p in saved] == ["Gear_m1.5_N17.SLDPRT", "Gear_m1.5_N68.SLDPRT",
                                                    "Gear_m2_N17.SLDPRT", "OutputGear.SLDPRT"]


def test_the_first_failure_stops_the_batch(tmp_path):
    second = os.path.join(FOLDER, "Gear_m1.5_N68.SLDPRT")
    fake = FakeSolidWorks(fail_on={"save_as": (second, "The disk is full.")})
    many = swbuild.build_many(fake, plans(tmp_path), never_exists)
    assert not many.ok and len(many.built) == 2
    assert [os.path.basename(p) for p in many.skipped] == ["Gear_m2_N17.SLDPRT", "OutputGear.SLDPRT"]
    assert any("SKIPPED 2 part(s)" in line for line in many.log_lines())


def test_a_batch_never_overwrites_and_never_starts_half_blocked(tmp_path):
    fake = FakeSolidWorks()
    batch = plans(tmp_path)
    last = os.path.join(FOLDER, "OutputGear.SLDPRT")
    with pytest.raises(swbuild.BuildError, match="already exists"):
        swbuild.build_many(fake, batch, lambda p: p == last)
    assert fake.calls == []                      # nothing was made, not even the first part
    twice = batch[:1] * 2
    with pytest.raises(swbuild.BuildError, match="both be saved as"):
        swbuild.build_many(fake, twice, never_exists)


# -- the live link -------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def touch_later(path, seconds=2):
    """A save a moment later: some file systems keep coarse times, and the link watches size and time."""
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + seconds * 1_000_000_000))


def test_a_save_is_read_and_its_changes_listed(tmp_path):
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), Clock())
    first = watch.read()
    assert first.ok and first.changes == [] and first.diagnostics == []
    assert watch.poll() is None                                    # nothing changed
    xlsx.write_cells(str(path), {"Gears": {"F3": 70}, "Shafts": {"C3": 64}})
    touch_later(path)
    reading = watch.poll()
    assert reading.ok
    assert reading.changes == ["Shafts!C3 S2 X 63.75 → 64", "Gears!F3 G2 Teeth 68 → 70"]
    assert watch.poll() is None


def test_rows_added_and_removed_are_named(tmp_path):
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), Clock())
    watch.read()
    xlsx.write_cells(str(path), {"Gears": {"A5": "G9"}, "Meshes": {"A4": "G1", "B4": "G9"}})
    touch_later(path)
    changes = watch.poll().changes
    assert "gear G9 added (Gears row 5)" in changes and "gear G4 removed" in changes
    assert "mesh G1–G9 added (Meshes row 4)" in changes


def test_a_file_caught_mid_save_waits_then_says_so(tmp_path):
    clock = Clock()
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), clock)
    watch.read()
    good = path.read_bytes()
    path.write_bytes(good[: len(good) // 3])                        # Excel half-way through writing it
    touch_later(path)
    assert watch.poll() is None                                     # quietly waits
    clock.now += 4
    assert watch.poll() is None
    path.write_bytes(good)                                          # the save finishes
    touch_later(path, 4)
    reading = watch.poll()
    assert reading.ok and reading.changes == []
    path.write_bytes(b"PK\x03\x04 not really")                      # and this time it never settles
    touch_later(path, 6)
    assert watch.poll() is None
    clock.now += link.RETRY_SECONDS + 0.1
    reading = watch.poll()
    assert not reading.ok and "has not settled" in reading.error


def test_a_workbook_that_goes_away_and_comes_back(tmp_path):
    clock = Clock()
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), clock)
    watch.read()
    moved = tmp_path / "elsewhere.xlsx"
    os.replace(path, moved)
    assert watch.poll() is None
    clock.now += link.RETRY_SECONDS + 0.1
    reading = watch.poll()
    assert reading.error == f"The workbook is no longer at {path}."
    assert watch.poll() is None                                     # said once, not every second
    os.replace(moved, path)
    touch_later(path)
    assert watch.poll().ok


def test_an_unreadable_workbook_is_a_reading_with_an_error(tmp_path):
    path = tmp_path / "w.xlsx"
    path.write_bytes(xlsx.OLE_MAGIC + b"\0" * 64)
    reading = link.Link(str(path), Clock()).read()
    assert not reading.ok and "encrypted" in reading.error


def test_the_apps_own_write_is_recognised(tmp_path):
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), Clock())
    watch.read()
    xlsx.write_cells(str(path), {"Gears": {"F3": 70}})
    watch.own_digest = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    touch_later(path)
    assert watch.poll().own


# -- what is remembered ----------------------------------------------------------------


def test_recent_workbooks(tmp_path):
    recent = store.Recent()
    for name in ("a.xlsx", "b.xlsx", "A.XLSX"):
        recent.remember_workbook(str(tmp_path / name))
    assert [os.path.basename(p) for p in recent.workbooks] == ["A.XLSX", "b.xlsx"]
    target = tmp_path / "recent.json"
    assert store.save_recent(recent, str(target))
    assert store.load_recent(str(target)).workbooks == recent.workbooks


def test_a_link_record_sits_beside_its_workbook(tmp_path):
    workbook = str(tmp_path / "Reducer_12to1.xlsx")
    record = store.LinkRecord(workbook=workbook, digest="abc",
                              parts=[{"path": "C:\\P\\Gear_m1.5_N17.SLDPRT", "gears": ["G1", "G5"]}])
    where = store.save_link_record(record)
    assert where == str(tmp_path / "Reducer_12to1.workbook.json")
    assert store.load_link_record(workbook) == record
    assert store.load_link_record(str(tmp_path / "other.xlsx")) is None


def test_a_parts_record_says_which_workbook_it_came_from():
    sidecar = store.built_sidecar("C:\\P\\G.SLDPRT", "G.SLDPRT", kind="spur", recipe="A", spec={}, derived={},
                                  variables=[], features=[], dimensions=[], manual_steps=[], template="",
                                  trig="degrees", written_by="t", workbook="C:\\P\\R.xlsx",
                                  workbook_gears=["G1", "G5"])
    again = store.from_json(store.to_json(sidecar))
    assert again.record.workbook == "C:\\P\\R.xlsx" and again.record.workbook_gears == ["G1", "G5"]
