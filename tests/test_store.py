"""The gear record beside each part, and the app's own memory."""

import json

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
    raw["gear"]["helix_angle"] = 15
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
