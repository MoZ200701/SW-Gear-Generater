"""The gear record beside each part, and the app's own memory."""

import json
import os
import pathlib

import pytest

from gear_generator import store
from gear_generator.store import GearRecord, Recent, Sidecar, StoreError, UnknownSchema


def sidecar():
    return Sidecar(
        part_path=r"C:\Gears\Gear_m1.5_N25.SLDPRT",
        part_title="Gear_m1.5_N25.SLDPRT",
        written_by="gear-generator 0.1.0",
        record=GearRecord(
            record_id="gear-1234abcd", recipe="A",
            spec={"module": "1.5", "teeth": "25"},
            derived={"d": 37.5},
            variables=[["No. of Teeth", "25"], ["Module", "1.5"]],
            features=["Gear Axis", "Blank", "Tooth Space", "Teeth"],
            dimensions=["OD@Blank Sketch", "Count@Teeth"],
            manual_steps=["Assign a material."],
            created="2026-09-14T00:00:00Z",
        ),
    )


# -- where it lives ---------------------------------------------------------


def test_the_record_sits_beside_the_part():
    assert store.sidecar_path(r"C:\Gears\Gear_m1.5_N25.SLDPRT") == r"C:\Gears\Gear_m1.5_N25.gear.json"


def test_an_unsaved_part_says_why_it_has_no_record():
    with pytest.raises(StoreError, match="never been saved"):
        store.sidecar_path("")


def test_paths_compare_the_way_windows_does():
    assert store.same_path(r"C:\Gears\A.SLDPRT", "c:/gears/a.sldprt")
    assert not store.same_path(r"C:\Gears\A.SLDPRT", r"C:\Gears\B.SLDPRT")
    assert not store.same_path("", "")


# -- the file ---------------------------------------------------------------


def test_a_record_round_trips():
    original = sidecar()
    assert store.from_json(store.to_json(original)) == original


def test_writing_twice_gives_identical_bytes():
    assert store.to_json(sidecar()) == store.to_json(sidecar())


def test_saving_an_unchanged_record_leaves_the_file_alone(tmp_path, monkeypatch):
    path = str(tmp_path / "Gear.gear.json")
    assert store.save(path, sidecar()) is True

    def fail(*args):
        raise AssertionError("os.replace was called for an unchanged record")

    monkeypatch.setattr(store.os, "replace", fail)
    assert store.save(path, sidecar()) is False


def test_saving_leaves_no_temporary_behind(tmp_path):
    path = str(tmp_path / "Gear.gear.json")
    store.save(path, sidecar())
    assert [p.name for p in tmp_path.iterdir()] == ["Gear.gear.json"]


def test_loading_what_is_not_there_is_not_an_error(tmp_path):
    assert store.load(str(tmp_path / "nothing.gear.json")) is None


def test_a_record_from_a_newer_version_is_refused_not_overwritten(tmp_path):
    path = tmp_path / "Gear.gear.json"
    path.write_text(json.dumps({"schemaVersion": 99}), encoding="utf-8")
    with pytest.raises(UnknownSchema, match="newer version"):
        store.load(str(path))
    assert path.exists()


def test_an_unreadable_record_is_moved_aside_never_deleted(tmp_path):
    path = tmp_path / "Gear.gear.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StoreError, match="moved to"):
        store.load(str(path))
    assert not path.exists()
    assert any(p.name.startswith("Gear.gear.json.bad-") for p in tmp_path.iterdir())


def test_unknown_keys_from_a_later_version_are_ignored():
    raw = json.loads(store.to_json(sidecar()))
    raw["gear"]["crown_radius"] = 15
    raw["invented"] = True
    assert store.from_json(json.dumps(raw)) == sidecar()


def test_a_record_that_is_not_an_object_is_refused():
    with pytest.raises(StoreError, match="not an object"):
        store.from_json("[1, 2]")


# -- the app's memory -------------------------------------------------------


def test_recent_round_trips(tmp_path):
    path = str(tmp_path / "gg" / "recent.json")
    recent = Recent(folder=r"C:\Gears", part_template=r"C:\T\Part.PRTDOT", recipe="B", mode="pair")
    recent.remember(r"C:\Gears\A.gear.json")
    assert store.save_recent(recent, path) is True
    assert store.load_recent(path) == recent


def test_recent_keeps_the_last_ten_most_recent_first_and_once_each():
    recent = Recent()
    for i in range(12):
        recent.remember(f"C:\\Gears\\G{i}.gear.json")
    recent.remember("c:/gears/g5.gear.json")
    assert len(recent.sidecars) == 10
    assert recent.sidecars[0] == "c:/gears/g5.gear.json"
    assert sum(store.same_path(p, r"C:\Gears\G5.gear.json") for p in recent.sidecars) == 1


def test_a_broken_recent_file_is_a_fresh_start(tmp_path):
    path = tmp_path / "recent.json"
    path.write_text("garbage", encoding="utf-8")
    assert store.load_recent(str(path)) == Recent()
    assert store.load_recent(str(tmp_path / "missing.json")) == Recent()


def test_saving_recent_somewhere_impossible_says_so_rather_than_raising(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert store.save_recent(Recent(), str(blocker / "under" / "recent.json")) is False


def test_recent_lives_in_appdata_on_windows_and_config_elsewhere():
    assert store.recent_path({"APPDATA": r"C:\Users\u\AppData\Roaming"}, "win32").endswith(
        "recent.json"
    )
    assert "Gear Generator" in store.recent_path({"APPDATA": r"C:\Users\u\AppData\Roaming"}, "win32")
    assert store.recent_path({"HOME": "/home/u"}, "linux") == "/home/u/.config/gear-generator/recent.json"


# -- records from a build ---------------------------------------------------


def _built(previous=None, path=r"C:\Gears\Gear_m1.5_N25.SLDPRT", stamp="2026-09-15T00:00:00Z"):
    return store.built_sidecar(
        path, "Gear_m1.5_N25.SLDPRT", kind="spur", recipe="A", spec={"module": "1.5"}, derived={"d": 37.5},
        variables=[["Module", "1.5"]], features=["Blank"], dimensions=["OD@Blank Sketch"],
        manual_steps=["Assign a material."], template="", trig="degrees", written_by="gear-generator 0.1.0",
        previous=previous, stamp=stamp,
    )


def test_a_first_build_gets_a_new_id_and_is_created_now():
    built = _built()
    assert built.record.record_id.startswith("gear-")
    assert built.record.created == built.record.last_built == "2026-09-15T00:00:00Z"
    assert built.record.last_updated == ""


def test_a_rebuild_to_the_same_path_keeps_its_id_and_creation():
    first = sidecar()
    again = _built(previous=first, path=first.part_path.lower())
    assert again.record.record_id == "gear-1234abcd"
    assert again.record.created == "2026-09-14T00:00:00Z"
    assert again.record.last_built == "2026-09-15T00:00:00Z"


def test_a_record_for_another_path_is_not_inherited():
    assert _built(previous=sidecar(), path=r"C:\Gears\Other.SLDPRT").record.record_id != "gear-1234abcd"


def test_update_values_changes_the_form_and_values_only():
    before = sidecar()
    after = store.updated_sidecar(before, {"module": "2"}, {"d": 50.0}, [["Module", "2"]], "2026-09-16T00:00:00Z")
    assert after.record.spec == {"module": "2"} and after.record.variables == [["Module", "2"]]
    assert after.record.features == before.record.features
    assert after.record.record_id == before.record.record_id
    assert after.record.last_updated == "2026-09-16T00:00:00Z"
    assert before.record.spec == {"module": "1.5", "teeth": "25"}


# -- the link record, schema 2 (W4 interfaces) ------------------------------


def link_record(workbook):
    return store.LinkRecord(
        workbook=workbook, digest="abc", last_built="2026-11-13T00:00:00Z",
        parts=[store.PartEntry(path=r"C:\P\Gear_m1.5_N17.SLDPRT", gears=["G1"], revision=0, kind="spur",
                               spec={"teeth": "17"}, variables=[["No. of Teeth", "17"]], trig="degrees"),
               store.PartEntry(path=r"C:\P\Gear_m1.5_N17_r2.SLDPRT", gears=["G5"], revision=2)],
        gearbox=store.GearboxRecord(
            revision=2, name="R_r2", layout=r"C:\P\R_r2_Layout.SLDPRT", assembly=r"C:\P\R_r2.SLDASM",
            shafts=[store.ShaftEntry(shaft="S2", x=63.75, sigma=1, x_side="plus", y_side="base", x_global="S2 X",
                                     x_plane="S2 X Plane", axis_name="S2 Axis")],
            meshes=[["G1", "G2"]], layout_component="R_r2_Layout-1",
            components=[store.ComponentEntry(gear="G5", part=r"c:\p\gear_m1.5_n17_r2.SLDPRT",
                                             name="Gear_m1.5_N17_r2-1", rotation=[1, 0, 0, 0, 1, 0, 0, 0, 1],
                                             at=[0, 0, 0])]),
        earlier=[store.EarlierRevision(revision=0, name="R", layout=r"C:\P\R_Layout.SLDPRT",
                                       assembly=r"C:\P\R.SLDASM", parts=[r"C:\P\Gear_m1.5_N17.SLDPRT"])],
        unsaved={r"C:\P\Gear_m1.5_N68.SLDPRT": 1763000000.5},
    )


def test_a_link_record_round_trips(tmp_path):
    workbook = str(tmp_path / "R.xlsx")
    record = link_record(workbook)
    store.save_link_record(record)
    assert store.read_link_record(workbook) == record
    assert store.open_link_record(workbook) == record
    raw = json.loads((tmp_path / "R.workbook.json").read_text())
    assert raw["link_schema_version"] == store.LINK_SCHEMA_VERSION == 3
    assert raw["schema_version"] == 1          # what a build from before schema 2 checks: see the next test
    assert raw["parts"][0]["revision"] == 0 and raw["gearbox"]["components"][0]["name"] == "Gear_m1.5_N17_r2-1"


# The link record's reader and writer as they were before schema 2 (W2, commit a93d6d9^), for the old-reader test.
_OLD_FIELDS = ("workbook", "digest", "parts", "assembly", "last_built", "schema_version", "written_by", "own_digest",
               "recalc")


def _old_build_exports(path):
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or int(raw.get("schema_version", 0)) > 1:
        raw = {}                              # "no record": the old window then writes a fresh one
    kept = {k: v for k, v in raw.items() if k in _OLD_FIELDS}
    kept.setdefault("parts", [])
    kept["own_digest"], kept["recalc"] = "exported", False
    path.write_text(json.dumps(kept, indent=2, sort_keys=True) + "\n")


def test_an_old_build_rewriting_a_v2_record_keeps_its_parts(tmp_path):
    """An older build of the app (the Mac copy) reads schema_version 1 as its own. Its Export then keeps every part,
    revision and spec included, and drops only the blocks it does not know; read here, that is a v1 record."""
    workbook = str(tmp_path / "R.xlsx")
    record = link_record(workbook)
    store.save_link_record(record)
    _old_build_exports(tmp_path / "R.workbook.json")
    again = store.read_link_record(workbook)
    assert again.parts == record.parts and again.digest == "abc" and again.own_digest == "exported"
    assert again.gearbox is None and again.earlier == [] and again.unsaved == {}
    assert again.current_parts() == record.parts


def test_a_record_written_with_schema_version_2_alone_still_reads(tmp_path):
    """The interface commit wrote ``schema_version: 2`` and no ``link_schema_version``."""
    raw = json.loads(store.link_record_to_json(link_record("R.xlsx")))
    raw["schema_version"] = 2
    del raw["link_schema_version"]
    assert store.link_record_from_json(json.dumps(raw)) == link_record("R.xlsx")


def test_a_v1_link_record_reads_as_v3_with_no_gearbox(tmp_path):
    (tmp_path / "R.workbook.json").write_text(json.dumps({
        "schema_version": 1, "workbook": "R.xlsx", "digest": "abc", "assembly": "", "last_built": "t",
        "parts": [{"path": r"C:\P\Gear_m1.5_N17.SLDPRT", "gears": ["G1", "G5"]}]}))
    record = store.read_link_record(str(tmp_path / "R.xlsx"))
    assert record.schema_version == 3 and record.gearbox is None and record.earlier == []
    assert record.parts == [store.PartEntry(path=r"C:\P\Gear_m1.5_N17.SLDPRT", gears=["G1", "G5"])]
    assert record.current_parts() == record.parts


def test_the_current_parts_are_those_the_current_revisions_components_name(tmp_path):
    record = link_record(str(tmp_path / "R.xlsx"))
    assert [p.gears for p in record.current_parts()] == [["G5"]]


def test_a_revision_whose_assembly_is_not_made_yet_acts_on_every_part():
    """The layout saved and the assembly failed (decision 4): no components to filter by."""
    record = link_record("R.xlsx")
    record.gearbox.assembly, record.gearbox.components = "", []
    assert record.current_parts() == record.parts


NEWER = [{"link_schema_version": 4, "schema_version": 1, "workbook": "R.xlsx"},
         {"schema_version": 4, "workbook": "R.xlsx"}]


@pytest.mark.parametrize("text,error", [
    (json.dumps(NEWER[0]), UnknownSchema),
    (json.dumps(NEWER[1]), UnknownSchema),
    ('{"workbook": "R.xlsx", "parts": "notalist"}', StoreError),
    ("not json", StoreError),
])
def test_a_planning_read_never_moves_or_changes_the_file(tmp_path, text, error):
    target = tmp_path / "R.workbook.json"
    target.write_text(text)
    with pytest.raises(error, match="R.workbook.json"):
        store.read_link_record(str(tmp_path / "R.xlsx"))
    assert target.read_text() == text and sorted(p.name for p in tmp_path.iterdir()) == ["R.workbook.json"]
    assert not hasattr(store, "load_link_record")     # the legacy read that hid both as "no record" is gone


@pytest.mark.parametrize("raw", NEWER)
def test_a_newer_record_is_refused_and_left_byte_identical(tmp_path, raw):
    target = tmp_path / "R.workbook.json"
    target.write_bytes(json.dumps(raw).encode() + b"\r\n")
    before = target.read_bytes()
    with pytest.raises(UnknownSchema, match=r"R\.workbook\.json, cannot be read: it was written by a newer Gear "
                                            r"Generator \(schema 4, this one reads 3\)\. It is left alone, so Build "
                                            r"and Update SolidWorks wait\."):
        store.open_link_record(str(tmp_path / "R.xlsx"))
    with pytest.raises(UnknownSchema, match=store.LINK_WAITS):
        store.save_link_record(link_record(str(tmp_path / "R.xlsx")))
    assert target.read_bytes() == before and sorted(p.name for p in tmp_path.iterdir()) == ["R.workbook.json"]


@pytest.mark.parametrize("text", ["not json", '{"parts": [{"path": "C:\\\\P\\\\A.SLDPRT", "gears": "G1"}]}',
                                  '{"gearbox": {"revision": "two"}}'])
def test_the_read_before_a_write_moves_a_broken_record_aside(tmp_path, text):
    target = tmp_path / "R.workbook.json"
    target.write_text(text)
    with pytest.raises(StoreError, match=r"R\.workbook\.json, could not be read \(.*\), so it was moved to "
                                         r"R\.workbook\.json\.bad-\d{8}-\d{6} and a new one is started\."):
        store.open_link_record(str(tmp_path / "R.xlsx"))
    (aside,) = [p for p in tmp_path.iterdir()]
    assert aside.name.startswith("R.workbook.json.bad-") and aside.read_text() == text
    assert store.open_link_record(str(tmp_path / "R.xlsx")) is None


def test_a_record_is_read_again_just_before_it_is_written(tmp_path):
    """Something broke the file between the read and the write: it is set aside, never written over."""
    workbook = str(tmp_path / "R.xlsx")
    (tmp_path / "R.workbook.json").write_text("{half a record")
    assert store.save_link_record(link_record(workbook)) == str(tmp_path / "R.workbook.json")
    assert store.read_link_record(workbook) == link_record(workbook)
    assert [p.read_text() for p in tmp_path.iterdir() if ".bad-" in p.name] == ["{half a record"]


def test_a_link_record_is_written_atomically_and_only_when_it_changed(tmp_path, monkeypatch):
    workbook = str(tmp_path / "R.xlsx")
    store.save_link_record(link_record(workbook))
    assert [p.name for p in tmp_path.iterdir()] == ["R.workbook.json"]

    def fail(*args):
        raise AssertionError("os.replace was called for an unchanged record")

    monkeypatch.setattr(store.os, "replace", fail)
    store.save_link_record(link_record(workbook))


def test_fields_are_checked_and_whole_numbers_read_as_numbers():
    raw = json.loads(store.link_record_to_json(link_record("R.xlsx")))
    raw["gearbox"]["shafts"][0]["sigma"] = 1.0
    raw["gearbox"]["shafts"][0]["x"] = 64
    record = store.link_record_from_json(json.dumps(raw))
    assert record.gearbox.shafts[0].sigma == 1 and isinstance(record.gearbox.shafts[0].sigma, int)
    assert isinstance(record.gearbox.shafts[0].x, float)
    for where, value in (("revision", "0"), ("variables", [["No. of Teeth", 17]]), ("gears", "G1")):
        bad = json.loads(store.link_record_to_json(link_record("R.xlsx")))
        bad["parts"][0][where] = value
        with pytest.raises(StoreError, match=f"PartEntry.{where} is not"):
            store.link_record_from_json(json.dumps(bad))
    bad = json.loads(store.link_record_to_json(link_record("R.xlsx")))
    bad["unsaved"] = {"C:\\P\\A.SLDPRT": "yesterday"}
    with pytest.raises(StoreError, match="time is not a number"):
        store.link_record_from_json(json.dumps(bad))


def test_parts_are_merged_never_replaced_by_one_batch():
    old = link_record("R.xlsx").parts
    again = store.PartEntry(path=r"c:\p\GEAR_M1.5_N17.sldprt", gears=["G1", "G3"], revision=0, spec={"teeth": "17"})
    new = store.PartEntry(path=r"C:\P\Gear_m1.5_N69.SLDPRT", gears=["G2"], revision=2)
    merged = store.merge_parts(old, [again, new])
    assert merged == [again, old[1], new]
    assert old == link_record("R.xlsx").parts                    # neither argument is changed


def test_an_update_left_unsaved_clears_once_the_file_is_saved_or_gone():
    record = store.LinkRecord(unsaved={"saved": 100.0, "same": 100.0, "older": 100.0, "gone": 100.0})
    times = {"saved": 100.5, "same": 100.0, "older": 50.0}

    def mtime(path):
        if path not in times:
            raise FileNotFoundError(path)
        return times[path]

    assert store.clear_saved(record, mtime) is True
    assert record.unsaved == {"same": 100.0, "older": 100.0}
    assert store.clear_saved(record, mtime) is False


def test_a_sidecar_read_for_planning_never_moves_anything(tmp_path):
    part = str(tmp_path / "Gear_m1.5_N25.SLDPRT")
    assert store.read_sidecar(part) is None and store.read_sidecar("") is None
    store.save(store.sidecar_path(part), sidecar())
    assert store.read_sidecar(part) == sidecar() == store.read_sidecar(store.sidecar_path(part))
    for text in ("{broken", json.dumps({"schemaVersion": 99})):
        (tmp_path / "Gear_m1.5_N25.gear.json").write_text(text)
        assert store.read_sidecar(part) is None
        assert sorted(p.name for p in tmp_path.iterdir()) == ["Gear_m1.5_N25.gear.json"]


def test_locate_carries_the_record_beside_the_workbook_and_leaves_the_old_alone(tmp_path):
    (tmp_path / "old").mkdir(), (tmp_path / "new").mkdir()
    old, new = str(tmp_path / "old" / "R.xlsx"), str(tmp_path / "new" / "Renamed.xlsx")
    store.save_link_record(link_record(old))
    before = (tmp_path / "old" / "R.workbook.json").read_bytes()
    assert store.carry_link_record(old, new) == str(tmp_path / "new" / "Renamed.workbook.json")
    carried = store.read_link_record(new)
    assert carried.workbook == new and carried.parts == link_record(old).parts
    assert carried.gearbox == link_record(old).gearbox
    assert (tmp_path / "old" / "R.workbook.json").read_bytes() == before
    # Once one is there, it is the new workbook's own: never carried over.
    store.save_link_record(store.LinkRecord(workbook=new, digest="mine"))
    assert store.carry_link_record(old, new) is None and store.read_link_record(new).digest == "mine"


def test_locate_with_nothing_to_carry(tmp_path):
    old, new = str(tmp_path / "R.xlsx"), str(tmp_path / "S.xlsx")
    assert store.carry_link_record(old, new) is None
    assert store.carry_link_record(old, old.upper()) is None
    (tmp_path / "R.workbook.json").write_text(json.dumps(NEWER[0]))
    with pytest.raises(UnknownSchema, match="R.workbook.json"):
        store.carry_link_record(old, new)
    assert not (tmp_path / "S.workbook.json").exists()


# -- the W4 review: copies, moves and unsaved marks ------------------------------------------------------------


def test_a_record_written_for_another_workbook_still_there_is_that_workbooks():
    """Review S1: a copy's record names the original; while the original exists the copy is not to use it."""
    record = store.LinkRecord(workbook=r"C:\Work\R.xlsx")
    there = {r"C:\Work\R.xlsx"}
    exists = lambda p: p in there                                     # noqa: E731
    assert store.foreign_workbook(record, r"C:\Copy\R.xlsx", exists) == r"C:\Work\R.xlsx"
    assert store.foreign_workbook(record, r"c:\work\r.XLSX", exists) == ""          # the same file to Windows
    assert store.foreign_workbook(store.LinkRecord(), r"C:\Copy\R.xlsx", exists) == ""
    assert store.foreign_workbook(None, r"C:\Copy\R.xlsx", exists) == ""
    # Gone: moved or renamed, or a copy of an original since deleted. Not adopted until the person says (N1c).
    there.clear()
    assert store.record_owner(record, r"C:\Copy\R.xlsx", exists) == (store.UNSURE, r"C:\Work\R.xlsx")
    assert store.foreign_workbook(record, r"C:\Copy\R.xlsx", exists) == r"C:\Work\R.xlsx"
    said_no = store.LinkRecord(workbook=r"C:\Work\R.xlsx")
    store.settle_owner(said_no, r"C:\Copy\R.xlsx", moved=False)       # "No: a copy", for this session
    assert said_no.workbook == r"C:\Work\R.xlsx" and said_no.copy_of == r"C:\Work\R.xlsx"
    assert store.record_owner(said_no, r"C:\Copy\R.xlsx", exists) == (store.COPY, r"C:\Work\R.xlsx")
    assert store.copy_by_answer(said_no, r"C:\Copy\R.xlsx", exists)      # a copy only by the answer: said so
    said_yes = store.LinkRecord(workbook=r"C:\Work\R.xlsx")
    store.settle_owner(said_yes, r"C:\Copy\R.xlsx", moved=True)       # "Yes: moved", the record adopted
    assert said_yes.workbook == r"C:\Copy\R.xlsx" and said_yes.moved_from == [r"C:\Work\R.xlsx"]
    assert store.record_owner(said_yes, r"C:\Copy\R.xlsx", exists) == (store.OURS, "")
    # The original come back: a copy whatever was said, and no longer only by the answer.
    there.add(r"C:\Work\R.xlsx")
    assert store.record_owner(said_no, r"C:\Copy\R.xlsx", exists)[0] == store.COPY
    assert not store.copy_by_answer(said_no, r"C:\Copy\R.xlsx", exists)


def test_a_no_is_never_written_so_a_new_session_asks_again_until_the_copy_builds():
    """Third W4 review (the way back from a mistaken No): No, the default, was kept in the record for ever, and
    neither Locate… nor reopening could take it back. It now holds for the session only: written, the record reads
    as it came — unanswered — so a new session asks again, until the copy's own first build replaces the record."""
    exists = lambda p: False                                          # noqa: E731 - the original is gone
    said_no = store.LinkRecord(workbook=r"C:\Work\R.xlsx")
    store.settle_owner(said_no, r"C:\Copy\R.xlsx", moved=False)
    text = store.link_record_to_json(said_no)
    assert "copy_of" not in text
    round_trip = store.link_record_from_json(text)
    assert round_trip.copy_of == "" and store.record_owner(round_trip, r"C:\Copy\R.xlsx", exists)[0] == store.UNSURE
    # A record an earlier build of this branch wrote with the answer in it is read as unanswered too.
    old = text[:-2] + ',\n  "copy_of": "C:\\\\Work\\\\R.xlsx"\n}\n'
    assert store.link_record_from_json(old).copy_of == ""


def test_one_workbook_reached_by_two_paths_is_its_own_record_not_a_copy(tmp_path):
    """W4 review N1a: a mapped drive and its UNC path, a subst drive, a junction, a symlink, an 8.3 name — one
    file. Compared as text they looked like a copy of itself, and the next build's finish wrote a fresh record
    over the workbook's own (the same file), losing its gearbox."""
    real = tmp_path / "share"
    real.mkdir()
    alias = tmp_path / "Z_drive"
    alias.symlink_to(real, target_is_directory=True)
    workbook, through = real / "Reducer.xlsx", alias / "Reducer.xlsx"
    workbook.write_bytes(b"x")
    record = store.LinkRecord(workbook=str(workbook), parts=[store.PartEntry(path="C:\\P\\Gear.SLDPRT")])
    store.save_link_record(record)
    read = store.read_link_record(str(through))
    assert store.same_file(str(workbook), str(through)) and not store.same_path(str(workbook), str(through))
    assert store.record_owner(read, str(through)) == (store.OURS, "")
    assert store.foreign_workbook(read, str(through)) == ""
    store.adopt(read, str(through))                                   # not a move: the record keeps its path
    assert read.workbook == str(workbook) and read.moved_from == []
    # One of them gone, they are compared as text: another path to a file that is not there is not the same file.
    assert not store.same_file(str(workbook), str(tmp_path / "gone" / "Reducer.xlsx"))


def test_adopting_a_record_keeps_the_paths_it_had():
    record = store.LinkRecord(workbook=r"C:\A\R.xlsx")
    store.adopt(record, r"C:\B\R.xlsx")
    store.adopt(record, r"C:\C\R.xlsx")
    store.adopt(record, r"C:\C\R.xlsx")
    assert record.workbook == r"C:\C\R.xlsx" and record.moved_from == [r"C:\A\R.xlsx", r"C:\B\R.xlsx"]
    store.adopt(record, r"C:\A\R.xlsx")                               # back where it was: not its own former path
    assert record.moved_from == [r"C:\B\R.xlsx", r"C:\C\R.xlsx"]
    assert store.link_record_from_json(store.link_record_to_json(record)) == record


def test_locate_never_carries_a_copys_record_into_its_own(tmp_path):
    """W4 review N1b: a copy (its record still the original's) renamed while open, then Locate…: the record was
    adopted without a look, and the copy's Update then drove the original's files."""
    orig, copy = tmp_path / "orig" / "Reducer.xlsx", tmp_path / "copy" / "Reducer.xlsx"
    for path in (orig, copy):
        path.parent.mkdir()
        path.write_bytes(b"x")
    record = store.LinkRecord(workbook=str(orig), parts=[store.PartEntry(path="C:\\Parts\\Gear_m1.5_N68.SLDPRT")])
    store.save_link_record(record, store.link_record_path(str(orig)))
    store.save_link_record(record, store.link_record_path(str(copy)))           # the folder copied whole
    renamed = tmp_path / "copy" / "Reducer v2.xlsx"
    copy.rename(renamed)
    with pytest.raises(store.NotCarried) as raised:
        store.carry_link_record(str(copy), str(renamed))
    assert str(raised.value) == (f"it was written for {orig}, so it is that workbook's record and lists that "
                                 "workbook's files, not this one's.")
    assert not pathlib.Path(store.link_record_path(str(renamed))).exists()
    # A copy the person said was a copy, once the original has gone too: the answer was this session's only and is
    # not in the file, so the record is carried unanswered and the question is asked at the new place (third
    # review: never adopted, never laundered).
    said = store.LinkRecord(workbook=str(tmp_path / "gone.xlsx"), copy_of=str(tmp_path / "gone.xlsx"))
    store.save_link_record(said, store.link_record_path(str(renamed)))
    renamed.rename(tmp_path / "copy" / "Reducer v3.xlsx")
    v3 = str(tmp_path / "copy" / "Reducer v3.xlsx")
    store.carry_link_record(str(renamed), v3)
    assert store.record_owner(store.read_link_record(v3), v3) == (store.UNSURE, str(tmp_path / "gone.xlsx"))


def test_locate_carries_an_unanswered_record_as_it_is_so_the_question_is_asked_again(tmp_path):
    old, new = tmp_path / "a" / "R.xlsx", tmp_path / "b" / "R.xlsx"
    old.parent.mkdir()
    new.parent.mkdir()
    gone = str(tmp_path / "gone" / "R.xlsx")
    store.save_link_record(store.LinkRecord(workbook=gone), store.link_record_path(str(old)))
    assert store.carry_link_record(str(old), str(new)) == store.link_record_path(str(new))
    carried = store.read_link_record(str(new))
    assert carried.workbook == gone and carried.moved_from == []
    assert store.record_owner(carried, str(new)) == (store.UNSURE, gone)


def test_the_journal_round_trips_and_an_old_build_ignores_it():
    """W4 review N4: ``pending`` (and ``copy_of``) are new keys. A build from before schema 2 reads the record with
    LinkRecord(**_known(...)), dropping what it does not know, and shown schema 1 it keeps the parts."""
    record = store.LinkRecord(workbook=r"C:\W\R.xlsx", parts=[store.PartEntry(path=r"C:\P\G.SLDPRT", gears=["G1"])],
                              pending=[store.PartEntry(path=r"C:\P\H.SLDPRT", gears=["G2"], revision=2, kind="spur",
                                                       spec={"teeth": "68"}),
                                       store.PartEntry(path=r"C:\P\R_r2.SLDASM", revision=2, kind="assembly")],
                              pending_for=r"C:\W\R.xlsx", copy_of="")
    text = store.link_record_to_json(record)
    assert store.link_record_from_json(text) == record
    raw = json.loads(text)
    assert raw["schema_version"] == 1 and "pending" in raw
    # what the pre-schema-2 reader did (store.load_link_record before a93d6d9): keep only the fields it knows
    old_fields = {"workbook", "digest", "parts", "assembly", "last_built", "schema_version", "written_by",
                  "own_digest", "recalc"}
    kept = {k: v for k, v in raw.items() if k in old_fields}
    assert int(kept["schema_version"]) <= 1 and isinstance(kept["parts"], list)
    assert all(isinstance(p, dict) for p in kept["parts"])
    with pytest.raises(StoreError, match="not a link record"):
        store.link_record_from_json(json.dumps(dict(raw, pending=[1])))


def test_locate_carries_the_record_and_remembers_the_old_path(tmp_path):
    """The Locate nit: the parts' .gear.json name the old path, so the carried record keeps it in moved_from."""
    old, new = tmp_path / "old" / "R.xlsx", tmp_path / "new" / "R2.xlsx"
    old.parent.mkdir()
    new.parent.mkdir()
    store.save_link_record(store.LinkRecord(workbook=str(old)))
    carried = store.carry_link_record(str(old), str(new))
    record = store.read_link_record(str(new))
    assert carried == store.link_record_path(str(new))
    assert record.workbook == str(new) and record.moved_from == [str(old)]


def test_an_update_marks_a_sidecar_unsaved_and_keeps_the_mark_until_told():
    sidecar = Sidecar(part_path=r"C:\P\G.SLDPRT", record=GearRecord(spec={"teeth": "68"}, features=["Teeth"]))
    marked = store.updated_sidecar(sidecar, {"teeth": "69"}, {}, [["No. of Teeth", "69"]], "t1", unsaved_since=7.5)
    assert marked.record.unsaved_since == 7.5 and marked.record.features == ["Teeth"]
    kept = store.updated_sidecar(marked, {"teeth": "70"}, {}, [["No. of Teeth", "70"]], "t2")
    assert kept.record.unsaved_since == 7.5
    assert store.from_json(store.to_json(kept)).record.unsaved_since == 7.5
    # a sidecar written before the mark existed reads as saved
    assert store.from_json(store.to_json(sidecar)).record.unsaved_since == 0.0


def test_saved_since_compares_the_files_time():
    assert store.saved_since("x", 1.0, lambda p: 2.0) and not store.saved_since("x", 2.0, lambda p: 2.0)

    def gone(_path):
        raise FileNotFoundError("x")
    assert not store.saved_since("x", 1.0, gone)


# -- the third W4 review: same_file ------------------------------------------------------------------------------


def _ino_zero(real_stat):
    def stat(path, *args, **kwargs):
        s = real_stat(path, *args, **kwargs)
        return os.stat_result((s.st_mode, 0, 7, s.st_nlink, s.st_uid, s.st_gid, s.st_size, int(s.st_atime),
                               int(s.st_mtime), int(s.st_ctime)))
    return stat


def test_a_file_id_of_zero_never_makes_two_workbooks_one(tmp_path, monkeypatch):
    """Third W4 review item 2 (w4x_samefile_ino0): some redirectors and virtual drives report a file id (st_ino)
    of 0 for every file; os.path.samefile then called two different workbooks one file, so a copy's record was
    OURS and the copy drove the original's files."""
    orig, copy = tmp_path / "Reducer.xlsx", tmp_path / "Copy of Reducer.xlsx"
    for p in (orig, copy):
        p.write_bytes(b"x")
    record = store.LinkRecord(workbook=str(orig))
    assert store.record_owner(record, str(copy))[0] == store.COPY
    monkeypatch.setattr(os, "stat", _ino_zero(os.stat))
    assert not store.same_file(str(orig), str(copy))
    assert store.record_owner(record, str(copy))[0] == store.COPY
    assert store.same_file(str(orig), str(orig).upper() if os.name == "nt" else str(orig))   # the text still counts


def test_a_path_that_cannot_be_statted_is_not_known_to_be_the_same_file(tmp_path, monkeypatch):
    here = tmp_path / "R.xlsx"
    here.write_bytes(b"x")
    real = os.stat

    def offline(path, *args, **kwargs):
        if "Offline" in str(path):
            raise OSError("The network path was not found")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(os, "stat", offline)
    assert not store.same_file(str(here), r"\\Offline\Share\R.xlsx")
    assert not store.same_file(r"\\Offline\Share\R.xlsx", str(here))


def test_within_one_pass_each_path_is_statted_once_and_text_is_compared_first(tmp_path, monkeypatch):
    """same_file must not turn a planning pass on the Tk thread into repeated stats of an offline network path."""
    here = tmp_path / "R.xlsx"
    here.write_bytes(b"x")
    real, seen = os.stat, []

    def counting(path, *args, **kwargs):
        seen.append(str(path))
        if "Offline" in str(path):
            raise OSError("The network path was not found")
        return real(path, *args, **kwargs)
    monkeypatch.setattr(os, "stat", counting)
    assert store.same_file(str(here), str(here)) and seen == []        # the same text: nothing statted
    with store.one_pass():
        for _ in range(5):
            assert not store.same_file(r"\\Offline\Share\R.xlsx", str(here))
            assert not store.same_file(str(here), r"\\Offline\Share\R.xlsx")
    assert sorted(seen) == sorted([r"\\Offline\Share\R.xlsx", str(here)])
    seen.clear()
    store.same_file(r"\\Offline\Share\R.xlsx", str(here))             # a new pass (none): statted again
    assert seen == [r"\\Offline\Share\R.xlsx"]


def test_planning_is_one_pass():
    """plan_gearbox and classify each run as one pass (store.in_one_pass), and the window's planning wraps both."""
    from gear_generator.workbook import gearbox, update
    assert gearbox.plan_gearbox.__wrapped__ and update.classify.__wrapped__


# -- schema 3 (W5): the gearbox's kind and a turning assembly's mates -------------------------------------------


def turning_record(workbook):
    record = link_record(workbook)
    box = record.gearbox
    box.kind = store.GEARBOX_MOTION
    box.mates = [store.MateEntry(name="G5 on S2 Axis", kind="axis", gears=["G5"], shaft="S2"),
                 store.MateEntry(name="G5 along S2", kind="along", gears=["G5"], shaft="S2", face_global="G5 Face Z",
                                 z_front=-12.5),
                 store.MateEntry(name="G6 locked to G5", kind="lock", gears=["G5", "G6"]),
                 store.MateEntry(name="G1 meshes G5", kind="mesh", gears=["G1", "G5"], ratio=[17, 68])]
    box.unmated, box.fixed, box.drag = [["G7", "G8"]], ["G9"], ["G1"]
    return record


def _gearbox_raw(record, **changes):
    raw = json.loads(store.link_record_to_json(record))
    raw["gearbox"].update(changes)
    return raw


def test_a_v2_record_reads_as_v3_with_a_static_gearbox_and_no_mates():
    raw = json.loads(store.link_record_to_json(link_record("R.xlsx")))
    raw["link_schema_version"] = 2
    for key in ("kind", "mates", "unmated", "fixed", "drag", "static_reason", "mate_problems",
                "mate_problems_digest"):
        del raw["gearbox"][key]
    record = store.link_record_from_json(json.dumps(raw))
    assert record == link_record("R.xlsx") and record.schema_version == 3
    assert record.gearbox.kind == store.GEARBOX_STATIC == "static"
    assert (record.gearbox.mates, record.gearbox.unmated, record.gearbox.fixed, record.gearbox.drag) == ([], [], [], [])
    assert (record.gearbox.static_reason, record.gearbox.mate_problems, record.gearbox.mate_problems_digest) == (
        "", [], "")


def test_a_turning_gearbox_round_trips_byte_for_byte(tmp_path):
    workbook = str(tmp_path / "R.xlsx")
    record = turning_record(workbook)
    store.save_link_record(record)
    again = store.read_link_record(workbook)
    text = store.link_record_to_json(again)            # numbers as read: the fixture's frames are whole ints
    assert again == record and store.link_record_to_json(store.link_record_from_json(text)) == text
    assert again.gearbox.mates[3].ratio == [17, 68] and again.gearbox.mates[1].z_front == -12.5
    written = json.loads((tmp_path / "R.workbook.json").read_text())["gearbox"]["mates"][2]
    assert written == {"name": "G6 locked to G5", "kind": "lock", "gears": ["G5", "G6"], "shaft": "", "ratio": [],
                       "face_global": "", "z_front": 0.0}


def test_a_refused_build_is_kept_with_the_read_it_came_from():
    record = link_record("R.xlsx")
    record.gearbox.assembly, record.gearbox.components = "", []
    record.gearbox.mate_problems = ["The lock G3 locked to G2 over-defines the assembly."]
    record.gearbox.mate_problems_digest = "abc"
    assert store.link_record_from_json(store.link_record_to_json(record)) == record


def test_whole_numbers_written_as_floats_read_back_as_a_ratio_of_whole_numbers():
    raw = _gearbox_raw(turning_record("R.xlsx"))
    raw["gearbox"]["mates"][3]["ratio"] = [17.0, 68.0]
    assert store.link_record_from_json(json.dumps(raw)).gearbox.mates[3].ratio == [17, 68]


@pytest.mark.parametrize("field,value", [("gears", "G1"), ("ratio", ["17", 68]), ("ratio", [17.5, 68]),
                                         ("ratio", [True, 68]), ("z_front", "far"), ("name", 3)])
def test_a_mate_entry_of_the_wrong_type_is_refused(field, value):
    raw = _gearbox_raw(turning_record("R.xlsx"))
    raw["gearbox"]["mates"][3][field] = value
    with pytest.raises(StoreError, match=f"MateEntry.{field} is not"):
        store.link_record_from_json(json.dumps(raw))


@pytest.mark.parametrize("changes,match", [({"kind": "turning"}, "gearbox.kind is 'turning'"),
                                           ({"mates": "G1 meshes G2"}, "MateEntry entries are not a list"),
                                           ({"unmated": [["G1", 2]]}, r"GearboxRecord.unmated is not"),
                                           ({"mate_problems": "one"}, r"GearboxRecord.mate_problems is not")])
def test_a_gearbox_with_a_bad_schema_3_field_is_refused(changes, match):
    with pytest.raises(StoreError, match=match):
        store.link_record_from_json(json.dumps(_gearbox_raw(turning_record("R.xlsx"), **changes)))
