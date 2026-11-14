"""The workbook gearbox that turns: its mates' names and shapes (W5, ``workbook/motion.py``).

The interface commit wrote the names and the record's mirror; Agent B adds the planning tests (W5-PLAN §3.2 B).
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
