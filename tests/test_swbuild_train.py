"""Whether a mated train stands as built, up to a turn (W5): ``swbuild.turn_between`` and ``swbuild.train_check``.

Pure, written in the W5 interface commit because both the worker (Agent A) and planning (Agent B) rest on them. The
frames are ``layout.frame``'s form, ``F_σ · rot_z(θ)`` by rows (F₋ = diag(1, −1, −1)), so a gear on a Z− shaft is
turned about its own +Z, which points along −Z.
"""

import math

import pytest

from gear_generator import swbuild
from gear_generator.swbuild import LockLink, MeshLink, TrainCheck, train_check, turn_between


def rot(sigma, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    if sigma > 0:
        return (c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0)
    return (c, -s, 0.0, -s, -c, 0.0, 0.0, 0.0, -1.0)


def tilted(degrees):
    """rot_x(degrees): the gear's axis tipped off Z."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c)


# -- turn_between ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("sigma", [1, -1])
@pytest.mark.parametrize("start,turn", [(0, 30), (12.5, -7.5), (100, 179), (-40, -179), (0, 0)])
def test_the_turn_between_two_frames_is_about_the_gears_own_axis(sigma, start, turn):
    assert turn_between(rot(sigma, start), rot(sigma, start + turn)) == pytest.approx(math.radians(turn), abs=1e-12)


def test_the_turn_comes_back_in_the_half_open_turn():
    assert turn_between(rot(1, 0), rot(1, 190)) == pytest.approx(math.radians(-170))
    assert turn_between(rot(1, 0), rot(1, 180)) == pytest.approx(math.pi)


def test_a_tilted_or_turned_over_gear_has_no_turn_between():
    assert turn_between(rot(1, 0), tilted(10)) is None
    assert turn_between(rot(1, 20), rot(-1, 20)) is None          # turned over: its axis the other way
    assert turn_between(rot(1, 0), tilted(3e-5)) is not None      # 5e-7 rad: within the pose tolerance
    assert turn_between(rot(1, 0), tilted(1e-3)) is None


def test_same_frame_still_reads_whole_pitches_as_the_same_placement():
    """Refactored onto turn_between, unchanged: a whole tooth off is the same; half a tooth, a tilt or a move not."""
    at = (64.5, 0.0, 17.0)
    assert swbuild.same_frame(rot(1, 3), at, rot(1, 3 + 360 / 17), at, 360 / 17)
    assert not swbuild.same_frame(rot(1, 3), at, rot(1, 3 + 180 / 17), at, 360 / 17)
    assert not swbuild.same_frame(rot(1, 3), at, rot(1, 3 + 360 / 17), at)
    assert not swbuild.same_frame(rot(1, 0), at, tilted(5), at, 360 / 17)
    assert not swbuild.same_frame(rot(1, 0), at, rot(1, 0), (64.5, 0.0, 17.01), 360 / 17)


# -- train_check: the 12 : 1 reducer (G1 17 on S1, G2 68 and G3 17 locked on S2, G4 51 on S3, all Z+) ------------

TEETH = {"G1": 17, "G2": 68, "G3": 17, "G4": 51}
PITCH = {g: 360 / z for g, z in TEETH.items()}
AT = {"G1": (0.0, 0.0, 0.0), "G2": (63.75, 0.0, 0.0), "G3": (63.75, 0.0, 17.0), "G4": (132.5, 0.0, 17.0)}
BUILT = {"G1": 4.0, "G2": -1.25, "G3": 11.0, "G4": 2.0}            # each gear's built phase, degrees
MESHES = (MeshLink("G1", "G2", -17 / 68, PITCH["G2"]), MeshLink("G3", "G4", -17 / 51, PITCH["G4"]))
LOCKS = (LockLink("G2", "G3", PITCH["G3"]),)


def frames(turns=None, sigma=None, at=None):
    turns, sigma, at = turns or {}, sigma or {}, dict(AT, **(at or {}))
    return {g: (rot(sigma.get(g, 1), BUILT[g] + turns.get(g, 0.0)), at[g]) for g in BUILT}


def check(found, wanted=None, meshes=MESHES, locks=LOCKS):
    return train_check(found, wanted or frames(), meshes, locks, PITCH)


def driven(input_degrees):
    """Every gear turned as the train turns it when G1 turns ``input_degrees`` (k about each gear's own axis)."""
    g2 = -17 / 68 * input_degrees
    return {"G1": input_degrees, "G2": g2, "G3": g2, "G4": -17 / 51 * g2}


def test_a_train_as_built_is_in_step_and_not_turned():
    found = check(frames())
    assert found == TrainCheck(residuals=found.residuals) and found.in_step and not found.turned
    assert [(a, b) for a, b, _ in found.residuals] == [("G1", "G2"), ("G3", "G4"), ("G2", "G3")]
    assert max(r for _, _, r in found.residuals) < 1e-12


def test_a_train_turned_as_one_is_in_step_and_turned():
    """The user dragged G1 30°: G4 turns 2.5° the same way, 1/12 (the drag a person makes, M2's signs)."""
    turns = driven(30.0)
    assert turns["G4"] == pytest.approx(2.5)
    found = check(frames(turns))
    assert found.in_step and found.turned and found.out_of_step == () and found.off_axis == ()


def test_one_gear_turned_alone_is_out_of_step():
    found = check(frames(dict(driven(30.0), G4=driven(30.0)["G4"] + 3.0)))
    assert found.out_of_step == (("G3", "G4"),) and not found.in_step and not found.turned


def test_whole_teeth_turns_are_not_turned():
    """G4 one tooth alone, or G1 one tooth alone: every mesh still meshes and every gear is on a whole pitch."""
    for turns in ({"G4": PITCH["G4"]}, {"G1": PITCH["G1"]}, {"G1": -2 * PITCH["G1"], "G4": 3 * PITCH["G4"]}):
        found = check(frames(turns))
        assert found.in_step and not found.turned, turns


def test_the_input_turned_one_tooth_turns_the_compound_gear_off_its_pitch():
    """Review M1's scenario: G1 one tooth turns G2 one of its teeth, and G3 with it, which is not a G3 tooth."""
    turns = driven(PITCH["G1"])
    assert turns["G2"] == pytest.approx(-PITCH["G2"])
    found = check(frames(turns))
    assert found.in_step and found.turned


def test_a_lock_is_tested_exactly_never_modulo_a_pitch():
    """Review M1: an anchor a whole tooth off its follower, or a follower a whole tooth of its own off, is out of
    step, though each gear alone is on a whole pitch (what the plan's modulo-pitch rule would have let through)."""
    assert check(frames({"G2": PITCH["G2"]})).out_of_step == (("G2", "G3"),)
    assert check(frames({"G3": PITCH["G3"], "G4": -17 / 51 * PITCH["G3"]})).out_of_step == (("G2", "G3"),)


def test_a_lock_turned_half_a_turn_is_judged_across_the_wrap():
    """G2 and G3 turned 180° less and more a hair: their turns come back as +π and −π, the same turn."""
    turns = {"G2": 180.0 - 1e-7, "G3": 180.0 + 1e-7}
    assert turn_between(rot(1, BUILT["G2"]), rot(1, BUILT["G2"] + turns["G2"])) > 3.14
    assert turn_between(rot(1, BUILT["G3"]), rot(1, BUILT["G3"] + turns["G3"])) < -3.14
    found = train_check(frames(turns), frames(), (), LOCKS, PITCH)
    assert found.in_step and found.residuals[0][2] < 1e-8


def test_a_moved_tilted_or_missing_gear_is_off_its_axis_and_its_relations_are_not_judged():
    found = check(frames(at={"G4": (132.5, 0.0, 17.01)}))
    assert found.off_axis == ("G4",) and found.out_of_step == () and not found.in_step and not found.turned
    assert [(a, b) for a, b, _ in found.residuals] == [("G1", "G2"), ("G2", "G3")]
    tipped = dict(frames(), G2=(tilted(10), AT["G2"]))
    assert check(tipped).off_axis == ("G2",)
    gone = {g: f for g, f in frames().items() if g != "G1"}
    assert check(gone).off_axis == ("G1",)


def test_a_gear_found_but_not_wanted_is_ignored():
    found = dict(frames(), G9=(tilted(30), (1.0, 2.0, 3.0)))
    assert check(found).in_step


def test_the_tolerance_is_on_each_relation():
    assert check(frames({"G4": math.degrees(5e-6)})).in_step
    assert not check(frames({"G4": math.degrees(5e-5)})).in_step
    assert swbuild.TRAIN_TOLERANCE == 1e-5


# -- train_check: Z− shafts and a ring (k's sign, review M2) ---------------------------------------------------


@pytest.mark.parametrize("sa,sb,internal", [(1, 1, False), (1, -1, False), (-1, 1, False), (-1, -1, False),
                                            (1, 1, True), (-1, -1, True), (1, -1, True), (-1, 1, True)])
def test_a_mesh_on_either_shaft_sense_and_a_ring_is_judged_about_each_gears_own_axis(sa, sb, internal):
    """k = −σa·σb·za/zb outside, +σa·σb·za/zb with a ring: what workbook.motion.mesh_links makes. A train turned
    by that k is in step; turned by the opposite sign it is not."""
    za, zb = 20, 28
    k = (1 if internal else -1) * sa * sb * za / zb
    sigma = {"A": sa, "B": sb}
    built = {"A": 7.0, "B": -3.0}
    at = {"A": (0.0, 0.0, 0.0), "B": (4.0, 0.0, 0.0)}

    def placed(turn_a, turn_b):
        return {g: (rot(sigma[g], built[g] + t), at[g]) for g, t in (("A", turn_a), ("B", turn_b))}

    mesh = (MeshLink("A", "B", k, 360 / zb),)
    pitch = {"A": 360 / za, "B": 360 / zb}
    right = train_check(placed(30.0, k * 30.0), placed(0.0, 0.0), mesh, (), pitch)
    wrong = train_check(placed(30.0, -k * 30.0), placed(0.0, 0.0), mesh, (), pitch)
    assert right.in_step and right.turned
    assert wrong.out_of_step == (("A", "B"),)


def test_the_risky_placements_signs_pin_k_against_own_axis_speeds():
    """Review M2's values for Risky_Placements (G1–G2, G3–G4, G5–G6 as k = ω_b/ω_a): +0.7, +0.636364, −0.388889.
    A train driven by those k's, each gear on its own axis, is in step."""
    ks = {("G1", "G2"): 0.7, ("G3", "G4"): 0.636364, ("G5", "G6"): -0.388889}
    meshes = tuple(MeshLink(a, b, k, 9.0) for (a, b), k in ks.items())
    locks = (LockLink("G2", "G3", 9.0), LockLink("G4", "G5", 9.0))
    turns = {"G1": 30.0}
    turns["G2"] = turns["G3"] = 0.7 * 30.0
    turns["G4"] = turns["G5"] = 0.636364 * turns["G3"]
    turns["G6"] = -0.388889 * turns["G5"]
    sigma = {"G1": 1, "G2": -1, "G3": -1, "G4": 1, "G5": 1, "G6": -1}
    wanted = {g: (rot(sigma[g], 0.0), (float(i), 0.0, 0.0)) for i, g in enumerate(turns)}
    found = {g: (rot(sigma[g], turns[g]), (float(i), 0.0, 0.0)) for i, g in enumerate(turns)}
    result = train_check(found, wanted, meshes, locks, {g: 9.0 for g in turns})
    assert result.in_step and result.turned
