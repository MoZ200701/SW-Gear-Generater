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
    assert not parts.buildable                               # Build waits for the error...
    assert [j.gear_ids for j in parts.jobs] == [("G1",), ("G2",), ("G3",), ("G4",)]   # ...the good gears still plan
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
    for _ in range(12):                                             # said once — not every second, nor every 5 s
        clock.now += 1
        assert watch.poll() is None
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


# -- what a save did to the checks (PLAN-WORKBOOK §5: "Gears!F3 Teeth 68 → 70 · G1–G2 now 1.50 off") ----


def checked(reading):
    """Every diagnostic and the gearbox report for a read, as WorkbookWindow._checked makes them."""
    from gear_generator.workbook import checks
    skip_rows = build.rows_with_errors(reading.diagnostics)
    parts = build.plan_parts(reading.spec, FOLDER, skip_rows=skip_rows)
    bad_rows = skip_rows | build.rows_with_errors(parts.diagnostics)
    report = checks.check(reading.spec, {g.id for g in reading.spec.gears if g.row in bad_rows})
    return reading.diagnostics + parts.diagnostics + report.diagnostics, report


def saved(path, watch, cells):
    """``cells`` saved into the workbook: the change lines the window shows for that save."""
    before = checked(watch.read())
    xlsx.write_cells(str(path), cells)
    touch_later(path)
    reading = watch.poll()
    return reading.changes, link.consequence(before, checked(reading))


def test_one_cell_says_what_it_did_on_its_own_line(tmp_path):
    """The plan's own example: G2 at 70 teeth needs 65.25 between centres, and S2 is still 63.75 from S1."""
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), Clock())
    changes, did = saved(path, watch, {"Gears": {"F3": 70}})
    assert did.meshes == [("G1", "G2", pytest.approx(1.5))] and not did.new_errors and not did.cleared
    assert ui_text.workbook_change_lines(changes, did) == ["Gears!F3 G2 Teeth 68 → 70 · G1–G2 now 1.5 mm off"]


def test_several_cells_say_it_once_after_them_and_say_when_it_mends(tmp_path):
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), Clock())
    changes, did = saved(path, watch, {"Shafts": {"C3": 64, "C4": 132}})
    assert ui_text.workbook_change_lines(changes, did) == [
        "Shafts!C3 S2 X 63.75 → 64", "Shafts!C4 S3 X 131.75 → 132", "G1–G2 now 0.25 mm off"]
    # Further off: the same error with other numbers, said as the distance and not as a new error.
    changes, did = saved(path, watch, {"Shafts": {"C3": 64.5, "C4": 132.5}})
    assert ui_text.workbook_consequence(did) == "G1–G2 now 0.75 mm off"
    changes, did = saved(path, watch, {"Shafts": {"C3": 63.75, "C4": 131.75}})
    assert ui_text.workbook_change_lines(changes, did)[-1] == "G1–G2 now on centres"


def test_new_problems_are_counted_by_their_cells_and_cleared_ones_too(tmp_path):
    path = write(tmp_path, reducer())
    watch = link.Link(str(path), Clock())
    changes, did = saved(path, watch, {"Gears": {"F3": 68.5}})
    # G2 no longer reads, so nothing reaches S2 or S3, and its own warning goes with it.
    assert did.new_errors == ["Gears!F3", "Shafts!A3", "Shafts!A4"] and did.cleared == ["Gears!Q3"]
    assert ui_text.workbook_change_lines(changes, did) == [
        "Gears!F3 G2 Teeth 68 → 68.5 · 3 new errors (Gears!F3, Shafts!A3, Shafts!A4) · 1 cleared (Gears!Q3)"]
    # The same error with another number is not a new one.
    _, did = saved(path, watch, {"Gears": {"F3": 68.7}})
    assert not did and ui_text.workbook_consequence(did) == ""
    _, did = saved(path, watch, {"Gears": {"F3": 68}})
    assert did.cleared == ["Gears!F3", "Shafts!A3", "Shafts!A4"] and did.new_warnings == ["Gears!Q3"]


def test_the_consequence_names_at_most_three_cells():
    did = link.Consequence(new_errors=["Gears!F3", "Gears!F3", "Gears!F4", "Gears!F5", "Gears!F6"],
                           new_warnings=["Shafts"])
    assert ui_text.workbook_consequence(did) == ("5 new errors (Gears!F3, Gears!F4, Gears!F5, …) · "
                                                 "1 new warning (Shafts)")
    assert ui_text.workbook_change_lines(["a", "b"], link.Consequence()) == ["a", "b"]
    assert ui_text.workbook_change_lines(["a"], None) == ["a"]


def test_the_window_shows_what_a_save_did(tmp_path):
    """Needs Tk and a display (run on Windows); skipped where there is none."""
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display for Tk")
    root.withdraw()
    from gear_generator import theme, workbook_gui
    theme.setup(root)

    class App:
        out_folder = tk.StringVar(root, "")
        part_template = tk.StringVar(root, "")

    path = write(tmp_path, reducer())
    window = workbook_gui.WorkbookWindow(root, App(), str(path), poll_ms=10 ** 6)
    try:
        window.withdraw()
        xlsx.write_cells(str(path), {"Gears": {"F3": 70}})
        window.reread()
        shown = [w.cget("text") for w in window.changes_body.winfo_children()]
        assert shown == ["Gears!F3 G2 Teeth 68 → 70 · G1–G2 now 1.5 mm off"]
        # A fix chosen does not change what the save did: that is read against the file, as the cells are.
        window.choose(window.report.fixes["Meshes!A2"][0])
        shown = [w.cget("text") for w in window.changes_body.winfo_children()]
        assert shown == ["Gears!F3 G2 Teeth 68 → 70 · G1–G2 now 1.5 mm off"]
        window.reread()                                       # nothing new: the list and what it did stay
        assert [w.cget("text") for w in window.changes_body.winfo_children()] == shown
    finally:
        window.close()
        root.destroy()


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


# -- the window's words (ui_text) ---------------------------------------------------------

from gear_generator import ui_text  # noqa: E402


def test_the_windows_readouts(tmp_path):
    spec = from_file(write(tmp_path, reducer()))
    parts = build.plan_parts(spec, FOLDER)
    assert ui_text.workbook_counts(spec) == "3 shafts · 4 gears · 2 meshes · no modes"
    assert ui_text.workbook_read_line("14:02:31", True) == "read 14:02:31 · open in Excel"
    assert ui_text.workbook_parts_readout(parts) == "4 parts to build"
    assert ui_text.workbook_checks_readout(parts.diagnostics) == "2 warnings"
    assert ui_text.workbook_changes_readout([], "14:02") == "nothing changed · 14:02"
    assert ui_text.workbook_status(parts, parts.diagnostics, folder=FOLDER) == (
        f"Ready: Build makes 4 parts in {FOLDER}.", True)
    assert ui_text.workbook_status(parts, parts.diagnostics, folder="")[1] is False


def test_the_gear_tables_states(tmp_path):
    spec = reducer()
    spec = model.replace(spec, gears=(
        spec.gears[0], model.replace(spec.gears[1], teeth="68.5"), spec.gears[2], spec.gears[3],
        Gear("G5", "S3", "47", "spur", "external", "17", "1.5", "", "15", "8"),
        Gear("G6", "S2", "60", "bevel", "external", "20", "3", "", "14", "10")))
    read_spec, diagnostics = model.from_book(xlsx.read(write(tmp_path, spec)))
    parts = build.plan_parts(read_spec, FOLDER, skip_rows=build.rows_with_errors(diagnostics))
    rows = {r[0]: r for r in ui_text.workbook_gear_rows(read_spec, parts, diagnostics + parts.diagnostics)}
    assert rows["G1"][6:] == ("Gear_m1.5_N17", ui_text.GEAR_STATE_BUILDS, "to build")
    assert rows["G2"][3] == "68.5" and rows["G2"][7:] == (ui_text.GEAR_STATE_ERROR, "see Checks")
    assert rows["G5"][6:] == ("Gear_m1.5_N17", ui_text.GEAR_STATE_SHARES, "the same part as G1")
    assert rows["G6"][7:] == (ui_text.GEAR_STATE_LATER, "later · phase W6")
    text, ok = ui_text.workbook_status(parts, diagnostics + parts.diagnostics, folder=FOLDER)
    assert not ok and text.startswith("Fix the workbook before building: Gears!F3: Teeth must be a whole number")


def test_a_batchs_sentence(tmp_path):
    batch = plans(tmp_path)
    assert ui_text.many_status(swbuild.build_many(FakeSolidWorks(), batch, never_exists))[0] == (
        "Built 4 parts. 1 thing to do by hand: Assign a material to each of the 4 parts; the build leaves it unset.")
    second = os.path.join(FOLDER, "Gear_m1.5_N68.SLDPRT")
    failed = swbuild.build_many(FakeSolidWorks(fail_on={"save_as": (second, "The disk is full.")}), batch,
                                never_exists)
    text, ok = ui_text.many_status(failed)
    assert not ok and text.startswith("1 part built before it; ") and text.endswith("2 parts not attempted.")



def test_twins_are_compared_by_the_part_they_build(tmp_path):
    """A Part name typed as the default, or a Hand on a spur, changes the form but not the part."""
    spec = reducer()
    named = Gear("G5", "S3", "47", "spur", "external", "17", "1.5", "", "15", "8", part_name="Gear_m1.5_N17")
    handed = Gear("G6", "S3", "67", "spur", "external", "17", "1.5", "", "15", "8", hand="left")
    spec = model.replace(spec, gears=spec.gears + (named, handed))
    parts = build.plan_parts(from_file(write(tmp_path, spec)), FOLDER)
    assert parts.errors == []
    assert parts.jobs[0].gear_ids == ("G1", "G5", "G6")


def test_names_differing_only_in_case_are_one_file(tmp_path):
    spec = reducer()
    other = Gear("G5", "S3", "47", "spur", "external", "30", "2", "", "20", "16", part_name="outputgear")
    parts = build.plan_parts(from_file(write(tmp_path, model.replace(spec, gears=spec.gears + (other,)))), FOLDER)
    (error,) = parts.errors
    assert "would both be OutputGear.SLDPRT (OutputGear and outputgear are one name to Windows)" in error.message


def test_one_gears_error_leaves_the_others_planned(tmp_path):
    spec = reducer()
    bad = Gear("G5", "S3", "47", "spur", "external", "3", "1.5", "", "15", "8")     # three teeth: the strip refuses
    read_spec = from_file(write(tmp_path, model.replace(spec, gears=spec.gears + (bad,))))
    parts = build.plan_parts(read_spec, FOLDER)
    assert parts.errors and not parts.buildable and len(parts.jobs) == 4
    rows = {r[0]: r for r in ui_text.workbook_gear_rows(read_spec, parts, parts.diagnostics)}
    assert rows["G1"][7] == ui_text.GEAR_STATE_BUILDS and rows["G5"][7] == ui_text.GEAR_STATE_ERROR



def test_a_damaged_link_record_is_no_record(tmp_path):
    workbook = str(tmp_path / "R.xlsx")
    (tmp_path / "R.workbook.json").write_text('{"workbook": "R.xlsx", "parts": "notalist"}')
    assert store.load_link_record(workbook) is None


# -- the window's one decision: what the footer says and whether Build may run ---------------


def ready(tmp_path, spec=None):
    read_spec, diagnostics = model.from_book(xlsx.read(write(tmp_path, spec or reducer())))
    parts = build.plan_parts(read_spec, FOLDER, skip_rows=build.rows_with_errors(diagnostics))
    return parts, diagnostics + parts.diagnostics


def test_build_is_enabled_only_for_a_good_current_read(tmp_path):
    parts, diagnostics = ready(tmp_path)
    assert ui_text.workbook_state(parts, diagnostics, folder=FOLDER)[2] is True
    # A read that failed (mid-save, gone, unreadable): the last good plan is not built from.
    text, ok, enabled = ui_text.workbook_state(parts, diagnostics, error="The workbook is no longer at X.",
                                               folder=FOLDER)
    assert (text, ok, enabled) == ("The workbook is no longer at X.", False, False)
    # A build in flight.
    assert ui_text.workbook_state(parts, diagnostics, folder=FOLDER, building=True) == (
        "Building 4 parts in SolidWorks…", True, False)
    # The output folder is missing.
    text, ok, enabled = ui_text.workbook_state(parts, diagnostics, folder=FOLDER, folder_exists=False)
    assert not enabled and "does not exist" in text


def test_after_a_build_the_note_shows_and_build_follows_the_file(tmp_path):
    parts, diagnostics = ready(tmp_path)
    note = ("Built 4 parts.", True)
    assert ui_text.workbook_state(parts, diagnostics, folder=FOLDER, note=note) == ("Built 4 parts.", True, True)
    spec = reducer()
    broken = model.replace(spec, gears=(model.replace(spec.gears[0], teeth="68.5"),) + spec.gears[1:])
    bad_parts, bad_diagnostics = ready(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path, broken)
    text, ok, enabled = ui_text.workbook_state(bad_parts, bad_diagnostics, folder=FOLDER, note=note)
    assert not enabled and not ok
    assert text.startswith("Built 4 parts. Since then: Fix the workbook before building: Gears!F2")


def test_a_chosen_fix_holds_build_until_export_and_a_refused_export_shows(tmp_path):
    parts, diagnostics = ready(tmp_path)
    text, ok, enabled = ui_text.workbook_state(parts, diagnostics, folder=FOLDER, chosen=2)
    assert ok and not enabled and text.startswith("2 fixes chosen: Export writes them")
    # The last Export was refused with the fix still chosen: that sentence wins, shown as a fault.
    refused = ("Nothing was written: the workbook changed since it was last read.", False)
    assert ui_text.workbook_state(parts, diagnostics, folder=FOLDER, chosen=1, note=refused) == (
        refused[0], False, False)
    # A good note does not hide the fix still waiting.
    text, _, enabled = ui_text.workbook_state(parts, diagnostics, folder=FOLDER, chosen=1,
                                              note=("Built 4 parts.", True))
    assert text.startswith("1 fix chosen: Export writes it") and not enabled
    # Building and a failed read still come first.
    assert ui_text.workbook_state(parts, diagnostics, folder=FOLDER, chosen=1, building=True)[0].startswith(
        "Building")
    assert ui_text.workbook_state(parts, diagnostics, error="Gone.", chosen=1, note=refused)[0] == "Gone."


def test_an_export_into_formulas_waits_for_excel_to_recalculate(tmp_path):
    parts, diagnostics = ready(tmp_path)
    text, ok, enabled = ui_text.workbook_state(parts, diagnostics, folder=FOLDER, recalc=True,
                                               note=("Wrote 1 cell.", True))
    assert ok and not enabled
    assert text == ("Wrote 1 cell. Open and save the workbook in Excel so its formulas recalculate; Build waits "
                    "for that save.")
    assert ui_text.workbook_state(parts, diagnostics, folder=FOLDER, recalc=True)[0].startswith("Open and save")


def test_short_path_fits_even_one_long_name():
    path = "C:\\Parts\\" + "X" * 80 + ".xlsx"
    short = ui_text.short_path(path, 62)
    assert len(short) <= 62 and short.endswith("X.xlsx") and "…" in short


def test_shared_steps_merge_only_on_the_whole_name():
    class R:
        def __init__(self, stem):
            self.saved = f"C:\\P\\{stem}.SLDPRT"
            self.manual = [f"Assign a material to {stem}; the build leaves it unset."]
    steps = ui_text._shared_steps([R("a"), R("b")])
    assert steps == ["Assign a material to each of the 2 parts; the build leaves it unset."]



def test_the_strip_and_a_workbook_plan_through_one_call():
    """Identical parts by construction: the strip's single-gear build goes through gears.plan_for, as rows do."""
    import inspect
    pytest.importorskip("tkinter")
    from gear_generator import gui
    assert "plan_for(" in inspect.getsource(gui.GearApp._plan_single)
    assert "plan_for(" in inspect.getsource(build.plan_parts)
