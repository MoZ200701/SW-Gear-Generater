"""A pair that turns: gear 1 free, a gear mate turning gear 2 — refused until the gear_mate probe has settled it.

Probe gear_mate has passed (SolidWorks 2026 and 2024) and its findings are set. The
plan is checked for its order and its references, the build against the fake,
and the decisions against canned probe records; whether SolidWorks does what the
findings say is the probe's to find.
"""

import math

import pytest

from gear_generator import findings, swbuild, ui_text
from gear_generator.gears import pair
from gear_generator.gears.base import AddGlobal, Mate, Place, Unfix
from gear_generator.probe import decide
from gear_generator.spec import GearSpec, InputError, PairSpec

from test_swbuild import FakeSolidWorks, never_exists

A = GearSpec(module="1.5", teeth="20")
B = GearSpec(module="1.5", teeth="60")
PATHS = (r"C:\Gears\Pinion.SLDPRT", r"C:\Gears\Gear.SLDPRT", "", r"C:\Gears\Pair.SLDASM")


@pytest.fixture
def settled(monkeypatch):
    """The findings a passing gear_mate probe would give: numerator with the first selection, no flip outside."""
    for name, value in (("GEAR_MATE_ROUTE", "mates"), ("MATE_GEAR", 10), ("GEAR_MATE_NUMERATOR_FIRST", True),
                        ("GEAR_MATE_EXTERNAL_FLIP", False)):
        monkeypatch.setattr(findings, name, value)


def test_while_the_probe_is_unsettled_a_gear_mate_is_refused_not_guessed(monkeypatch):
    monkeypatch.setattr(findings, "GEAR_MATE_ROUTE", None)
    with pytest.raises(InputError, match="gear_mate probe"):
        pair.assembly_plan(A, B, *PATHS, motion="gear mate")
    # A fixed pair is what it always was.
    fixed = pair.assembly_plan(A, B, *PATHS)
    assert any(isinstance(op, Mate) and op.kind == "angle" for op in fixed.ops)


def test_a_turning_pair_frees_gear_one_and_mates_the_axes_by_the_teeth(settled):
    plan = pair.assembly_plan(A, B, *PATHS, motion="gear mate")
    assert plan.check() == []
    ops = plan.ops
    assert Unfix("gear1") in ops
    mates = {op.id: op for op in ops if isinstance(op, Mate)}
    assert (mates["axis_top"].b, mates["axis_right"].b, mates["front"].b) == ("asm:plane2", "asm:plane3", "asm:plane1")
    assert (mates["axis"].b, mates["centre"].b) == ("asm:plane2", "asm:plane3")   # gear 1's own planes turn
    gear = mates["gear"]
    assert (gear.kind, gear.ratio, gear.flip, gear.name) == ("gear", (20.0, 60.0), False, "Gear Mate")
    assert not any(op.kind == "angle" for op in mates.values())                    # its spin is placed, not mated
    placed = next(op for op in ops if isinstance(op, Place) and op.component == "gear2")
    assert placed.at == (60.0, 0.0, 0.0)
    # Turned about its axis by the mesh angle, 3° for 60 teeth: rows of rot_z, so the second entry is −sin.
    assert placed.rotation[1] == pytest.approx(-math.sin(math.radians(pair.mate_angle(60))))
    assert "Mesh Angle" not in [op.name for op in ops if isinstance(op, AddGlobal)]


def test_round_a_ring_the_gear_mate_turns_the_same_way(settled):
    ring = GearSpec(module="2", teeth="60", teeth_side="internal")
    pinion = GearSpec(module="2", teeth="20")
    plan = pair.assembly_plan(pinion, ring, *PATHS, motion="gear mate")
    assert plan.check() == []
    gear = next(op for op in plan.ops if isinstance(op, Mate) and op.kind == "gear")
    assert gear.ratio == (60.0, 20.0) and gear.flip is True                      # the ring is gear 1


def test_a_herringbone_pair_turns_on_its_mid_planes(settled):
    a = GearSpec(kind="herringbone", module="2", teeth="20", helix_angle="30", face_width="20")
    b = GearSpec(kind="herringbone", module="2", teeth="40", helix_angle="30", hand="left", face_width="16")
    plan = pair.assembly_plan(a, b, *PATHS, motion="gear mate")
    assert plan.check() == []
    faces = next(op for op in plan.ops if isinstance(op, Mate) and op.id == "faces")
    assert faces.a == "gear2:Mid Plane"
    placed = next(op for op in plan.ops if isinstance(op, Place) and op.component == "gear2")
    assert placed.at[2] == pytest.approx(2.0)                                    # (20 − 16) / 2


def test_bevel_and_crossed_pairs_are_not_built_turning(settled):
    bevel_a = GearSpec(kind="bevel", module="3", teeth="20", mate_teeth="40")
    bevel_b = GearSpec(kind="bevel", module="3", teeth="40", mate_teeth="20")
    with pytest.raises(InputError, match="parallel shafts"):
        pair.assembly_plan(bevel_a, bevel_b, *PATHS, motion="gear mate")
    with pytest.raises(InputError, match="parallel shafts"):
        pair.assembly_plan(A, B, *PATHS, shafts="crossed", motion="gear mate")


def test_a_turning_pair_builds_against_the_fake_in_order(settled):
    fake = FakeSolidWorks()
    result = swbuild.build(fake, pair.assembly_plan(A, B, *PATHS, motion="gear mate"), never_exists)
    assert result.ok, result.log_lines()
    names = [name for name, _ in fake.calls]
    assert names.index("unfix_component") < names.index("add_mate")
    gear = [args for name, args in fake.calls if name == "add_mate" and args[0] == "gear"]
    assert gear == [("gear", "gear1:Gear Axis", "gear2:Gear Axis", (20.0, 60.0), False)]
    assert "ok      unfixed gear1" in result.log_lines()


def test_the_pair_spec_reads_its_motion():
    assert PairSpec().motion_value() == "fixed"
    assert PairSpec(motion="Gear mate").motion_value() == "gear mate"
    with pytest.raises(InputError, match="Assembly must be"):
        PairSpec(motion="spinning").motion_value()


def test_the_decisions_come_only_from_a_passing_probe():
    facts = {"mate_gear_type": 10, "gear_mate_numerator_first": True, "gear_mate_external_flip": False}
    passed = decide.decide({"gear_mate": {"status": "pass", "facts": facts}})
    assert (passed["gear_mate_route"], passed["mate_gear_type"], passed["gear_mate_numerator_first"],
            passed["gear_mate_external_flip"]) == ("mates", 10, True, False)
    failed = decide.decide({"gear_mate": {"status": "fail", "facts": facts}})
    assert (failed["gear_mate_route"], failed["mate_gear_type"]) == (None, None)


def test_the_explainer_says_which_way_the_gears_turn():
    turning = PairSpec(mode="pair", motion="gear mate", gear_a=A, gear_b=B)
    assert ui_text.explainer("motion", object(), "", turning)[3] == \
        "gear mate → a turn of gear 1 turns gear 2 0.3333 of a turn, the other way"
    ring = PairSpec(mode="pair", motion="gear mate", mesh="internal", gear_a=A, gear_b=B)
    assert ui_text.explainer("motion", object(), "", ring)[3].endswith("the same way")
