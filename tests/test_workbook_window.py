"""The Workbook window's W4 wiring, through the real window (docs/PLAN-WORKBOOK.md §4.2–§4.5, §5).

Build makes the parts, the layout part and the static assembly; Update SolidWorks carries a later edit of the
workbook into them; Build again… makes the next revision. Each press goes through a fake worker whose job runs
against the fake SolidWorks of ``test_swbuild`` — saving real (empty) files, so the window's own planning, which
looks at the disk, sees what a job left — and the finishes write real sidecars and a real record beside the
workbook. Needs Tk and a display (run on Windows: ``python.exe -m pytest tests/test_workbook_window.py``);
skipped where there is none.
"""

import hashlib
import json
import os
import pathlib

import pytest

from gear_generator import store, swbuild, ui_text
from gear_generator.swcom import DocInfo
from gear_generator.workbook import model, xlsx
from gear_generator.workbook.gearbox import LayoutReuse
from gear_generator.workbook.model import Gear
from test_swbuild import FakeSolidWorks
from test_workbook_model import reducer, write

tk = pytest.importorskip("tkinter")

NAME = "Reducer_12to1"
PARTS = ("Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear")


class DiskSolidWorks(FakeSolidWorks):
    """The fake SolidWorks, leaving a real file wherever it saves a document, and keeping each component's
    frame under the Name2 it was inserted as, so a reopened assembly reads back where the build put it."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.names = {}

    def save_as(self, path):
        kept = super().save_as(path)
        pathlib.Path(path).write_bytes(b"saved by the fake SolidWorks")
        return kept

    def add_component(self, handle, path, at):
        name = super().add_component(handle, path, at)
        self.names[handle] = name
        return name

    def place_component(self, handle, rotation, at):
        super().place_component(handle, rotation, at)
        if handle in self.names:
            self.frames[self.names[handle]] = (tuple(rotation), tuple(at))

    def saved_in(self, start):
        """The paths saved since call ``start``."""
        return [args[0] for name, args in self.calls[start:] if name == "save_as"]


class FakeCall:
    """A submitted job: answered only when the worker runs, so a test sees the window while it is in flight."""

    def __init__(self, work, sw):
        self.work, self.sw, self.answer = work, sw, None

    def run(self):
        try:
            self.answer = (self.work(self.sw), None)
        except BaseException as exc:  # noqa: BLE001 - the real worker hands every raise back the same way
            self.answer = (None, exc)

    def poll(self):
        return self.answer


class FakeWorker:
    def __init__(self, sw):
        self.sw = sw
        self.calls = []

    def submit(self, work):
        call = FakeCall(work, self.sw)
        self.calls.append(call)
        return call

    def run(self):
        for call in self.calls:
            if call.answer is None:
                call.run()


class Desk:
    """A Tk root, the strip's stand-in, a fake worker on the fake SolidWorks, and the windows opened."""

    def __init__(self, root, tmp_path):
        self.root, self.tmp = root, tmp_path
        self.folder = tmp_path / "parts"
        self.folder.mkdir()
        self.sw = DiskSolidWorks()
        self.worker = FakeWorker(self.sw)
        self.windows = []

        class App:
            out_folder = tk.StringVar(root, "")
            part_template = tk.StringVar(root, "")
            assembly_template = tk.StringVar(root, "")
            _worker = self.worker
            _pending_build = None
            recent = store.Recent()

        self.app = App()

    def spec(self, spec=None):
        spec = spec or reducer()
        return model.replace(spec, box=model.replace(spec.box, output_folder=str(self.folder)))

    def open(self, spec=None, name=f"{NAME}.xlsx", path=None):
        from gear_generator import workbook_gui
        path = path or write(self.tmp, self.spec(spec), name)
        window = workbook_gui.WorkbookWindow(self.root, self.app, str(path), poll_ms=10 ** 6)
        window.withdraw()
        self.windows.append(window)
        return window

    def finish(self, window):
        """The worker answers, and the window's poll collects it."""
        self.worker.run()
        window._tick()

    def part(self, stem, ext=".SLDPRT"):
        return str(self.folder / f"{stem}{ext}")


@pytest.fixture
def desk(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display for Tk")
    root.withdraw()
    from gear_generator import theme
    theme.setup(root)
    monkeypatch.setattr(store, "save_recent", lambda recent, path=None: True)    # never the user's own list
    d = Desk(root, tmp_path)
    try:
        yield d
    finally:
        for window in d.windows:
            if not window._closed():
                window._pending = window._job = None
                window.close()
        root.destroy()


def touch_later(path, seconds=2):
    info = os.stat(path)
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + seconds * 1_000_000_000))


def save_in_excel(window, cells, seconds=2):
    """Cells changed and saved as Excel would, then the window's poll."""
    xlsx.write_cells(window.link.path, cells)
    touch_later(window.link.path, seconds)
    window._tick()


def record_of(window):
    return store.read_link_record(window.link.path)


def record_bytes(window):
    return pathlib.Path(store.link_record_path(window.link.path)).read_bytes()


def gear_states(window):
    """The Gears table's last column, by gear: what the dot says."""
    out = {}
    for cell in window.table.grid_slaves(column=7):
        if not isinstance(cell, tk.Frame):
            continue
        row = int(cell.grid_info()["row"])
        gear = window.table.grid_slaves(row=row, column=0)[0].cget("text")
        out[gear] = [w.cget("text") for w in cell.winfo_children() if isinstance(w, tk.Label)][0]
    return out


def built(desk, spec=None):
    """A window whose workbook is built once: the four parts, the layout part and the assembly."""
    window = desk.open(spec)
    window.press_build()
    desk.finish(window)
    assert record_of(window).gearbox.assembly
    return window


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


# -- Build ----------------------------------------------------------------------------------------------------------


def test_build_makes_the_parts_the_layout_and_the_assembly_and_records_them(desk):
    window = desk.open()
    footer = window.footer()
    assert (footer.build_action, footer.build_label, footer.build_enabled, footer.update_shown) == (
        ui_text.BUILD, "Build", True, False)
    assert window.status.get() == (f"Ready: Build makes 4 parts, {NAME}_Layout and {NAME}.SLDASM in "
                                   f"{ui_text.short_path(str(desk.folder), 48)}.")
    assert window.build_button._primary and not window.update_button.winfo_manager()
    assert gear_states(window) == {"G1": "to build", "G2": "to build", "G3": "to build", "G4": "to build"}

    window.press_build()
    # In flight: the worker's last step in the footer, every button held, the window still answering.
    assert window._pending is not None and window.status.get() == "Building in SolidWorks…"
    window._job.progress.say(swbuild.Step(swbuild.STAGE_PART, "Gear_m1.5_N68", 2, 4))
    window._tick()
    assert window.status.get() == "Building in SolidWorks: part 2 of 4, Gear_m1.5_N68…"
    assert not window.build_button._enabled and not window.export_button._enabled
    window.press_build()                                       # a second press while it runs does nothing
    assert len(desk.worker.calls) == 1

    desk.finish(window)
    assert window._pending is None
    assert window.status.get().startswith(f"Built 4 parts, {NAME}_Layout and {NAME}.SLDASM; no interference "
                                          "between the gears.")
    assert [os.path.basename(p) for p in desk.sw.saved_in(0)] == [
        "Gear_m1.5_N17.SLDPRT", "Gear_m1.5_N68.SLDPRT", "Gear_m2_N17.SLDPRT", "OutputGear.SLDPRT",
        f"{NAME}_Layout.SLDPRT", f"{NAME}.SLDASM"]
    for stem in PARTS:                                         # each part's .gear.json names the workbook
        sidecar = store.read_sidecar(desk.part(stem))
        assert sidecar is not None and store.same_path(sidecar.record.workbook, window.link.path)
    raw = json.loads(record_bytes(window))
    assert raw["link_schema_version"] == 2
    record = record_of(window)
    assert record.gearbox.revision == 0 and store.same_path(record.gearbox.assembly, desk.part(NAME, ".SLDASM"))
    assert store.same_path(record.assembly, record.gearbox.assembly)
    assert [c.gear for c in record.gearbox.components] == ["G1", "G2", "G3", "G4"]
    assert all(c.name for c in record.gearbox.components) and record.gearbox.layout_component
    assert record.digest == window.reading.digest and len(record.parts) == 4

    footer = window.footer()
    assert (footer.build_action, footer.build_label, footer.build_enabled) == (
        ui_text.BUILD_AGAIN, "Build again…", True)
    assert (footer.update_shown, footer.update_enabled, footer.update_primary) == (True, True, True)
    assert not window.build_button._primary and window.update_button._primary
    assert window.update_button.winfo_manager() and window.build_button.label.cget("text") == "Build again…"
    assert window.read_line.get().endswith(" · built from this version")
    assert set(gear_states(window).values()) == {"built"} and window.parts_readout.get() == "4 parts built"


def test_a_build_the_worker_refuses_says_so_and_records_nothing(desk):
    window = desk.open()
    elsewhere = str(desk.tmp / "elsewhere" / "Gear_m1.5_N17.SLDPRT")
    desk.sw.open_docs = [DocInfo(title="Gear_m1.5_N17.SLDPRT", path=elsewhere, doc_type=1)]
    window.press_build()
    desk.finish(window)
    assert window.status.get().startswith(f"{elsewhere} is open in SolidWorks, and it has the same file name as ")
    assert window.status_label.cget("fg") == __import__("gear_generator.theme", fromlist=["x"]).ERROR
    assert desk.sw.saved_in(0) == [] and not os.path.exists(store.link_record_path(window.link.path))
    assert window.footer().build_enabled                      # close the other document and press again


def test_without_solidworks_nothing_is_submitted(desk):
    window = desk.open()
    desk.app._worker = None
    window.press_build()
    assert window.status.get().startswith("SolidWorks cannot be reached from here, so nothing was built.")
    desk.app._worker = desk.worker
    desk.app._pending_build = object()                        # the strip is building
    window.press_build()
    assert window.status.get() == ui_text.strip_busy()
    assert desk.worker.calls == []


# -- what a failure leaves, and what the next press does ---------------------------------------------------------


def test_a_part_that_fails_mid_batch_is_recorded_and_the_next_build_carries_on(desk):
    window = desk.open()
    desk.sw.fail_on = {"save_as": (desk.part("Gear_m2_N17"), "The disk is full.")}
    window.press_build()
    desk.finish(window)
    text = window.status.get()
    assert text.startswith("2 parts built before it; ") and "Press Build to carry on: what was built is reused." in text
    record = record_of(window)
    assert [os.path.basename(p.path) for p in record.parts] == ["Gear_m1.5_N17.SLDPRT", "Gear_m1.5_N68.SLDPRT"]
    assert record.gearbox is None
    assert window.footer().build_label == "Build" and [r.stem for r in window.plan.reuse] == list(PARTS[:2])

    desk.sw.fail_on = {}
    start = len(desk.sw.calls)
    window.press_build()
    desk.finish(window)
    assert [os.path.basename(p) for p in desk.sw.saved_in(start)] == [
        "Gear_m2_N17.SLDPRT", "OutputGear.SLDPRT", f"{NAME}_Layout.SLDPRT", f"{NAME}.SLDASM"]
    assert len(record_of(window).parts) == 4                  # merged, never replaced by the second batch
    assert window.status.get().startswith(f"Built 2 parts, {NAME}_Layout and {NAME}.SLDASM, reusing the 2 parts "
                                          "already built")


def test_a_failed_assembly_leaves_a_record_the_next_build_continues_from(desk):
    window = desk.open()
    desk.sw.fail_on = {"save_as": (desk.part(NAME, ".SLDASM"), "The disk is full.")}
    window.press_build()
    desk.finish(window)
    assert window.status.get().endswith("Press Build to try the assembly again: the parts and layout are reused.")
    record = record_of(window)
    assert record.gearbox.layout and not record.gearbox.assembly and len(record.parts) == 4
    footer = window.footer()
    assert (footer.build_label, footer.build_enabled) == ("Build", True)
    assert isinstance(window.plan.layout, LayoutReuse) and len(window.plan.reuse) == 4 and not window.plan.build

    desk.sw.fail_on = {}
    start = len(desk.sw.calls)
    window.press_build()
    desk.finish(window)
    assert [os.path.basename(p) for p in desk.sw.saved_in(start)] == [f"{NAME}.SLDASM"]
    assert window.status.get().startswith(f"Built {NAME}.SLDASM, reusing {NAME}_Layout and the 4 parts already "
                                          "built; no interference between the gears.")
    assert record_of(window).gearbox.assembly and window.footer().build_label == "Build again…"


# -- Update SolidWorks -------------------------------------------------------------------------------------------


DEMONSTRATION = {"Shafts": {"C3": 64.5, "C4": 132.5}, "Gears": {"F3": 69}}    # S3 X follows S2 by its formula


def test_the_demonstration_edit_is_summed_up_and_update_carries_it_unsaved(desk):
    window = built(desk)
    before = record_of(window)
    save_in_excel(window, DEMONSTRATION)
    assert window.status.get() == ("Update SolidWorks will change G2's values (Gear_m1.5_N68), move S2 and S3 in "
                                   f"{NAME}_Layout, and re-place G2, G3 and G4.")
    assert window.read_line.get().endswith(" · changed since it was built")
    assert gear_states(window)["G2"] == "built · changes on Update" and gear_states(window)["G1"] == "built"
    assert window.update_button._enabled and window.update_button._primary

    window.press_update()
    assert window.status.get() == "Updating SolidWorks…" and not window.update_button._enabled
    start = len(desk.sw.calls)
    desk.finish(window)
    text = window.status.get()
    assert text.startswith("Updated SolidWorks: changed ") and f"; no interference between the gears. " \
        f"{ui_text.SAVE_TO_KEEP} " in text
    # Build again… is greyed until those are saved, and says so (a part Update changed is not reused unsaved).
    assert not window.build_button._enabled and text.endswith(
        f"Build again… waits until Gear_m1.5_N68, {NAME} and {NAME}_Layout are saved in SolidWorks.")
    assert "Gear_m1.5_N68 (it now has 69 teeth; its file keeps its name)" in text
    assert f"moved S2 and S3 in {NAME}_Layout" in text and "re-placed G2, G3 and G4" in text
    sets = [args for name, args in desk.sw.calls[start:] if name == "set_global_variable"]
    assert ("S2 X", "64.5") in sets and ("S3 X", "132.5") in sets and ("No. of Teeth", "69") in sets
    assert desk.sw.saved_in(start) == []                       # Update SolidWorks saves nothing

    record = record_of(window)
    assert {os.path.basename(p) for p in record.unsaved} == {"Gear_m1.5_N68.SLDPRT", f"{NAME}_Layout.SLDPRT",
                                                             f"{NAME}.SLDASM"}
    assert record.digest == window.reading.digest and record.digest != before.digest
    assert [s.x for s in record.gearbox.shafts if s.shaft == "S2"] == [64.5]
    assert store.read_sidecar(desk.part("Gear_m1.5_N68")).record.spec["teeth"] == "69"
    assert window.read_line.get().endswith(" · built from this version")

    # Until those documents are saved in SolidWorks the footer asks for it, and Build again… waits for it.
    window.note = None
    window._refresh_state()
    assert window.status.get().endswith("have changes from Update SolidWorks that are not saved: save them in "
                                        "SolidWorks to keep them. Build again… waits for that save.")
    assert not window.footer().build_enabled and "has not been saved since" in window.plan.refusal
    for path in record.unsaved:
        touch_later(path)                                      # saved in SolidWorks
    window._tick()
    assert "not saved" not in window.status.get() and "waits" not in window.status.get()
    assert window.footer().build_enabled


def test_an_update_that_stops_part_way_records_what_it_changed_and_the_next_press_finishes(desk):
    window = built(desk)
    save_in_excel(window, DEMONSTRATION)
    desk.sw.fail_on = {"set_global_variable": ("S2 X", "The equation would not take.")}
    window.press_update()
    desk.finish(window)
    text = window.status.get()
    assert text.startswith("Update SolidWorks stopped. ") and "It had already changed Gear_m1.5_N68" in text
    record = record_of(window)
    unsaved = {os.path.basename(p) for p in record.unsaved}
    assert "Gear_m1.5_N68.SLDPRT" in unsaved and f"{NAME}.SLDASM" not in unsaved     # the gears were not moved
    # What is left is still offered: the part's values are on record now, the moves are not.
    window.note = None
    window._refresh_state()
    assert window.status.get().startswith(f"Update SolidWorks will move S2 and S3 in {NAME}_Layout, and re-place "
                                          "G2, G3 and G4.")

    desk.sw.fail_on = {}
    start = len(desk.sw.calls)
    window.press_update()
    desk.finish(window)
    sets = [args[0] for name, args in desk.sw.calls[start:] if name == "set_global_variable"]
    assert "No. of Teeth" not in sets and "S2 X" in sets       # compared live: the part already holds 69
    assert record_of(window).digest == window.reading.digest


def test_a_structural_edit_asks_and_no_changes_nothing(desk, monkeypatch):
    from gear_generator import workbook_gui
    window = built(desk)
    save_in_excel(window, {"Gears": {"K2": "arcs"}})           # G1's flank: a new recipe, a new part
    assert window.status.get().endswith(f"Update SolidWorks offers to build again as {NAME}_r2.")
    assert gear_states(window)["G1"] == "needs a new part" and gear_states(window)["G2"] == "built"
    asked = []
    monkeypatch.setattr(workbook_gui, "ask_yes_no", lambda parent, title, text: asked.append((title, text)) or False)
    on_record, calls = record_bytes(window), len(desk.worker.calls)
    window.press_update()
    (title, question), = asked
    assert title == "Build again?" and f"Build again as {NAME}_r2?" in question
    assert "reuses 3 parts that have not changed" in question and f"{NAME}.SLDASM stays as it is on disk" in question
    assert window.status.get() == ui_text.NOTHING_CHANGED
    assert len(desk.worker.calls) == calls and record_bytes(window) == on_record
    window.press_build()                                       # Build again… asks the same question
    assert len(asked) == 2 and asked[1] == asked[0] and len(desk.worker.calls) == calls


def test_a_structural_edit_answered_yes_builds_the_next_revision_beside_the_first(desk, monkeypatch):
    from gear_generator import workbook_gui
    window = built(desk)
    first = {p: sha(p) for p in desk.sw.saved_in(0)}
    times = {p: os.stat(p).st_mtime_ns for p in first}
    save_in_excel(window, {"Gears": {"K2": "arcs"}})
    monkeypatch.setattr(workbook_gui, "ask_yes_no", lambda parent, title, text: True)
    start = len(desk.sw.calls)
    window.press_update()
    desk.finish(window)
    made = [os.path.basename(p) for p in desk.sw.saved_in(start)]
    assert made[1:] == [f"{NAME}_r2_Layout.SLDPRT", f"{NAME}_r2.SLDASM"] and made[0].endswith("_r2.SLDPRT")
    assert window.status.get().startswith(f"Built 1 part, {NAME}_r2_Layout and {NAME}_r2.SLDASM, reusing the 3 "
                                          "parts already built")
    record = record_of(window)
    assert (record.gearbox.revision, record.gearbox.name) == (2, f"{NAME}_r2")
    (earlier,) = record.earlier
    assert earlier.revision == 0 and store.same_path(earlier.assembly, desk.part(NAME, ".SLDASM"))
    assert [os.path.basename(p) for p in earlier.parts] == ["Gear_m1.5_N17.SLDPRT"]
    assert {os.path.basename(c.part) for c in record.gearbox.components} == {
        made[0], "Gear_m1.5_N68.SLDPRT", "Gear_m2_N17.SLDPRT", "OutputGear.SLDPRT"}
    assert {p: sha(p) for p in first} == first and {p: os.stat(p).st_mtime_ns for p in first} == times
    assert window.footer().build_label == "Build again…" and window.update.record_matches


def test_a_question_left_open_while_the_workbook_changes_builds_nothing(desk, monkeypatch):
    from gear_generator import workbook_gui
    window = built(desk)
    save_in_excel(window, {"Gears": {"K2": "arcs"}})

    def saved_meanwhile(parent, title, text):
        save_in_excel(window, {"Gears": {"K3": "arcs"}}, seconds=4)
        return True

    monkeypatch.setattr(workbook_gui, "ask_yes_no", saved_meanwhile)
    calls = len(desk.worker.calls)
    window.press_update()
    assert window.status.get() == ui_text.ASKED_TOO_LATE and len(desk.worker.calls) == calls


# -- the record --------------------------------------------------------------------------------------------------


def test_a_newer_record_holds_build_and_update_and_is_left_byte_identical(desk):
    path = write(desk.tmp, desk.spec())
    target = pathlib.Path(store.link_record_path(str(path)))
    target.write_bytes(json.dumps({"link_schema_version": 3, "schema_version": 1, "workbook": str(path)}).encode())
    before = target.read_bytes()
    window = desk.open(path=path)
    footer = window.footer()
    assert window.status.get().endswith(store.LINK_WAITS) and not footer.ok
    assert not footer.build_enabled and not footer.update_shown
    window.press_build()
    window.press_update()
    assert desk.worker.calls == [] and target.read_bytes() == before


def test_a_record_that_turns_newer_during_a_build_is_left_alone_and_said(desk):
    window = desk.open()
    window.press_build()
    target = pathlib.Path(store.link_record_path(window.link.path))
    target.write_bytes(json.dumps({"link_schema_version": 3, "workbook": window.link.path}).encode())
    before = target.read_bytes()
    desk.finish(window)
    assert target.read_bytes() == before and window.status.get().endswith(store.LINK_WAITS)
    assert store.read_sidecar(desk.part("Gear_m1.5_N17")) is not None     # the parts' own records are written


def test_a_broken_record_is_set_aside_on_the_next_write(desk):
    path = write(desk.tmp, desk.spec())
    target = pathlib.Path(store.link_record_path(str(path)))
    target.write_text("not json")
    window = desk.open(path=path)
    assert "The next Build sets it aside and starts a new one." in window.status.get()
    assert window.footer().build_enabled and target.read_text() == "not json"     # planning never moves it
    window.press_build()
    desk.finish(window)
    aside = [p for p in desk.tmp.iterdir() if p.name.startswith(target.name + ".bad-")]
    assert len(aside) == 1 and aside[0].read_text() == "not json"
    assert record_of(window).gearbox.assembly
    assert f"so it was moved to {aside[0].name} and a new one is started." in window.status.get()


def test_locate_carries_the_record_to_the_workbooks_new_place(desk, monkeypatch):
    from gear_generator import workbook_gui
    window = built(desk)
    old_record = record_bytes(window)
    moved = desk.tmp / "Moved.xlsx"
    os.replace(window.link.path, moved)
    monkeypatch.setattr(workbook_gui.filedialog, "askopenfilename", lambda **kwargs: str(moved))
    window.locate()
    carried = store.read_link_record(str(moved))
    assert carried is not None and store.same_path(carried.workbook, str(moved))
    assert carried.gearbox.assembly and pathlib.Path(store.link_record_path(str(desk.tmp / f"{NAME}.xlsx"))
                                                     ).read_bytes() == old_record
    assert window.footer().build_label == "Build again…" and window.read_line.get().endswith(
        " · built from this version")


# -- Build parts, and the states that hold everything -------------------------------------------------------------


def with_bevel():
    spec = reducer()
    return model.replace(spec, gears=spec.gears + (Gear("G6", "S2", "60", "bevel", "external", "20", "3", "", "14",
                                                        "10"),))


def test_build_parts_falls_back_while_a_bevel_row_holds_the_layout_back(desk):
    window = desk.open(with_bevel())
    footer = window.footer()
    assert (footer.build_action, footer.build_label, footer.build_primary) == (ui_text.BUILD_PARTS, "Build parts",
                                                                               True)
    assert window.status.get().startswith("Ready: Build parts makes 4 parts in ") and \
        "the layout and assembly wait for a later phase: Gears!A6: G6 is a bevel gear" in window.status.get()
    desk.sw.fail_on = {"save_as": (desk.part("OutputGear"), "The disk is full.")}
    window.press_build()
    desk.finish(window)
    assert len(record_of(window).parts) == 3 and record_of(window).gearbox is None
    desk.sw.fail_on = {}
    start = len(desk.sw.calls)
    window.press_build()
    desk.finish(window)
    assert [os.path.basename(p) for p in desk.sw.saved_in(start)] == ["OutputGear.SLDPRT"]   # the rest reused
    record = record_of(window)
    assert len(record.parts) == 4 and record.gearbox is None                 # merged; no layout, no assembly
    assert window.read_line.get().endswith(" · parts built from this version")
    footer = window.footer()
    assert footer.build_label == "Build parts" and not footer.build_enabled and footer.update_shown
    assert not footer.update_primary


def test_a_chosen_fix_and_a_provisional_read_hold_both_buttons(desk):
    window = built(desk)
    save_in_excel(window, {"Shafts": {"C3": 64, "C4": 132}})              # G1–G2 0.25 mm off its centres
    assert not window.footer().build_enabled and not window.footer().update_enabled
    window.choose(window.report.fixes["Meshes!A2"][0])
    footer = window.footer()
    assert footer.text.startswith("1 fix chosen: Export writes it into the workbook, and Build and Update "
                                  "SolidWorks wait for that")
    assert not footer.build_enabled and not footer.update_enabled and footer.update_shown
    window.press_build()
    window.press_update()
    window.unchoose(window.chosen[0])
    save_in_excel(window, {"Shafts": {"C3": 63.75, "C4": 131.75}}, seconds=4)
    assert window.footer().update_enabled
    window.recalc = True                                                      # an Export Excel has yet to save
    window._plan()
    window._paint()
    footer = window.footer()
    assert footer.text == ui_text.RECALC_WAIT_UPDATE and not footer.build_enabled and not footer.update_enabled
    window.press_build()
    window.press_update()
    assert len(desk.worker.calls) == 1                                        # only the first build


# -- closing while a job runs -------------------------------------------------------------------------------------


def test_closing_mid_build_records_what_it_saved_then_closes(desk):
    window = desk.open()
    window.press_build()
    window.close()
    assert not window._closed() and window.status.get().endswith(ui_text.closes_when_done())
    desk.worker.run()
    window._tick()
    assert window._closed()
    assert store.read_link_record(str(desk.tmp / f"{NAME}.xlsx")).gearbox.assembly


def test_closing_mid_build_that_fails_stays_open_to_say_why(desk):
    window = desk.open()
    desk.sw.fail_on = {"save_as": (desk.part(NAME, ".SLDASM"), "The disk is full.")}
    window.press_build()
    window.close()
    desk.finish(window)
    assert not window._closed() and "The disk is full." in window.status.get()
    assert record_of(window).gearbox.layout


def test_a_clash_beside_a_mesh_is_said_where_they_meet_and_stands_out(desk):
    window = desk.open()
    desk.sw.clashes = [(("gear1-1", "gear4-1"), 2.0)]           # G1 and G4: on different shafts, not a mesh
    window.press_build()
    desk.finish(window)
    assert f"Check: G1 and G4 interfere, 2 mm³; look where they meet in {NAME}.SLDASM." in window.status.get()
    assert window.status_label.cget("fg") == __import__("gear_generator.theme", fromlist=["x"]).ERROR


# -- the window keeps its width whatever the footer holds ------------------------------------------------------


LONG = ("Updated SolidWorks: changed 1 variable in Gear_m1.5_N68 (it now has 69 teeth; its file keeps its name), "
        "moved S2 and S3 in Reducer_12to1_Layout, re-placed G2, G3 and G4. Check: G1 and G4 interfere, 2 mm³; "
        "G2 and G3 interfere, 0.5 mm³; look where they meet in Reducer_12to1.SLDASM. Save in SolidWorks to keep it.")


def width_and_height(window):
    """The size :meth:`WorkbookWindow._fit` gives the window (a withdrawn window does not report one back)."""
    asked = []
    real = window.geometry
    window.geometry = lambda spec=None: asked.append(spec) if spec else real()
    try:
        window._fit()
    finally:
        del window.geometry
    w, h = (int(v) for v in asked[-1].split("+")[0].split("x"))
    return w, h


def test_the_window_keeps_its_width_with_update_shown_and_a_long_sentence(desk):
    from gear_generator import workbook_gui
    from gear_generator.theme import px
    fresh = desk.open(name="Fresh.xlsx")
    fresh.note = (LONG, False)
    fresh._refresh_state()
    assert not fresh.update_button.winfo_manager()
    fresh_size = width_and_height(fresh)

    window = built(desk)                                       # Export, Export as…, Build again…, Update SolidWorks
    short_height = width_and_height(window)[1]
    window.note = (LONG, False)
    window._refresh_state()
    assert window.update_button.winfo_manager() and window.build_button.label.cget("text") == "Build again…"
    size = width_and_height(window)

    assert fresh_size[0] == size[0] == px(workbook_gui.WINDOW_WIDTH)
    assert window.winfo_reqwidth() <= px(workbook_gui.WINDOW_WIDTH)
    # With less room beside the buttons the sentence wraps sooner, and the window grows taller to hold it all.
    assert int(str(window.status_label.cget("wraplength"))) < int(str(fresh.status_label.cget("wraplength")))
    lines = window.status_label.winfo_reqheight() // window.fonts.label.metrics("linespace")
    assert lines >= 3                                          # the long update-and-clash sentence, wrapped
    assert size[1] == window.winfo_reqheight() > short_height


# -- notes that answer rather than report a job join the state plainly ---------------------------------------------


def test_a_fix_set_aside_by_a_save_is_joined_plainly_to_what_the_save_left(desk):
    window = desk.open()
    save_in_excel(window, {"Shafts": {"C3": 64, "C4": 132}})
    window.choose(window.report.fixes["Meshes!A2"][0])
    save_in_excel(window, {"Shafts": {"C3": 64.5, "C4": 132.5}}, seconds=4)   # the move chosen no longer fits
    assert window.chosen == [] and isinstance(window.note, ui_text.Standing)
    text = window.status.get()
    assert text.startswith(ui_text.FIX_SET_ASIDE + " Fix the workbook before building: Meshes!A2:")
    assert "Since then" not in text


def test_a_record_locate_could_not_carry_is_joined_plainly_to_the_state(desk, monkeypatch):
    from gear_generator import workbook_gui
    window = desk.open()
    old_record = pathlib.Path(store.link_record_path(window.link.path))
    old_record.write_text(json.dumps({"link_schema_version": 3, "workbook": window.link.path}))
    moved = desk.tmp / "Moved.xlsx"
    os.replace(window.link.path, moved)
    desk.folder.rmdir()                                        # and the output folder is gone too
    monkeypatch.setattr(workbook_gui.filedialog, "askopenfilename", lambda **kwargs: str(moved))
    window.locate()
    text = window.status.get()
    assert isinstance(window.note, ui_text.Standing) and "Since then" not in text
    assert text.startswith("The record of what was built stays beside the workbook's old place: The record of what "
                           "was built, Reducer_12to1.workbook.json, cannot be read: it was written by a newer Gear "
                           "Generator")
    assert text.endswith("does not exist; make it, or change it on the Box sheet.")
    assert not os.path.exists(store.link_record_path(str(moved)))
