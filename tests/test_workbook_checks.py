"""Gearbox-level checks, speeds and the fixes (docs/PLAN-WORKBOOK.md §3.4–§3.6).

The 12 : 1 example's numbers are an answer key checked by an independent
subagent from the problem statement alone (2026-11-13): centres 63.75 and 68,
S2 −375 rpm / 39.20 N·m, S3 125 rpm / 115.248 N·m; at 64.000 mm stage 1
needs x1 + x2 = 0.169100, 0.084550 each, working angle 20.61°, εα 1.62.
"""

import math
from fractions import Fraction

import pytest

from gear_generator.workbook import checks, fixes, kinematics, model, xlsx
from gear_generator.workbook.model import Box, Gear, GearboxSpec, Mesh, Shaft
from test_workbook_model import reducer, write


def read(tmp_path, spec, name="R.xlsx"):
    return model.from_book(xlsx.read(write(tmp_path, spec, name)))[0]


def check(tmp_path, spec, name="R.xlsx"):
    read_spec = read(tmp_path, spec, name)
    return read_spec, checks.check(read_spec)


def errors(report):
    return [d.message for d in report.diagnostics if d.is_error]


def moved(spec, **shaft_x):
    return model.replace(spec, shafts=tuple(model.replace(s, x=shaft_x.get(s.id, s.x)) for s in spec.shafts))


# -- the example, clean ------------------------------------------------------------------------


def test_the_example_checks_clean_with_its_answer_key(tmp_path):
    spec, report = check(tmp_path, reducer())
    assert errors(report) == []
    assert report.centres[("G1", "G2")] == (pytest.approx(63.75), pytest.approx(63.75))
    assert report.centres[("G3", "G4")] == (pytest.approx(68.0), pytest.approx(68.0))
    motion = report.motion
    assert motion.settled
    assert motion.speeds == {"S1": Fraction(1500), "S2": Fraction(-375), "S3": Fraction(125)}
    assert [motion.turns(s) for s in ("S1", "S2", "S3")] == ["anticlockwise", "clockwise", "anticlockwise"]
    assert motion.torques["S1"] == 10.0
    assert motion.torques["S2"] == pytest.approx(39.2)
    assert motion.torques["S3"] == pytest.approx(115.248)
    assert report.worked_out_as == "Parallel train · 2 meshes · 12.000 : 1 · output turns the same way"
    assert set(report.theta) == {"G1", "G2", "G3", "G4"}


# -- a centre distance that is off, and its two fixes -------------------------------------------


def test_s2_at_64_is_caught_with_both_fixes(tmp_path):
    spec, report = check(tmp_path, moved(reducer(), S2="64", S3="132"))
    (error,) = errors(report)
    assert error.startswith("Meshes!A2: G1 and G2 are 64 apart; their teeth make 63.75 (+0.25 mm).")
    move, shift = report.fixes["Meshes!A2"]
    assert move.title == "Move S2 and S3 beyond it by -0.25 mm"
    assert move.detail == "S2 X 64 → 63.75 · S3 X 132 → 131.75"
    assert [(e.sheet, e.item, e.key, e.value) for e in move.edits] == [
        ("Shafts", "S2", "x", "63.75"), ("Shafts", "S3", "x", "131.75")]
    assert shift.title == "Keep your positions: profile-shift G1 and G2"
    assert shift.detail == "x +0.084550 / +0.084550 → 64.000 exact · working angle 20.61° · ε 1.62"
    assert [(e.item, e.key, e.value) for e in shift.edits] == [("G1", "profile_shift", "0.08455"),
                                                              ("G2", "profile_shift", "0.08455")]
    # Either fix, applied, checks clean.
    for fix in (move, shift):
        assert errors(checks.check(fixes.apply(spec, fix))) == []


def test_a_typed_distance_within_half_the_last_digit_passes(tmp_path):
    spec, report = check(tmp_path, moved(reducer(), S2="63.754", S3="131.754"))
    assert errors(report) == []


def test_no_move_is_offered_inside_a_loop(tmp_path):
    spec = reducer()
    loop = model.replace(spec, meshes=spec.meshes + (Mesh("G1", "G4"),))   # S1 meshes S3 too: a loop
    read_spec = read(tmp_path, moved(loop, S2="64", S3="132"))
    report = checks.check(read_spec)
    assert any(e.startswith("Meshes!A2: G1 and G2 are 64 apart") for e in errors(report))
    # No move (it would break the loop's other mesh), and no shift (G1 is in G1–G4 too, so shifting it breaks that).
    assert report.fixes.get("Meshes!A2", []) == []


# -- meshes that cannot be ---------------------------------------------------------------------


@pytest.mark.parametrize("cells,expected", [
    ({"G2": {"module": "2"}}, "G1 has module 1.5 and G2 2; meshing gears share one module."),
    ({"G2": {"pressure_angle": "25"}}, "G1's pressure angle is 20° and G2's 25°; meshing gears share one."),
    ({"G2": {"at": "40"}}, "G1 and G2 do not meet along the axis: their faces are 17.5 mm apart. Check their At."),
])
def test_meshes_that_cannot_be(tmp_path, cells, expected):
    spec = reducer()
    gears = tuple(model.replace(g, **cells.get(g.id, {})) for g in spec.gears)
    _, report = check(tmp_path, model.replace(spec, gears=gears))
    assert any(e.endswith(expected) for e in errors(report)), errors(report)


def test_helical_hands_must_be_opposite_on_parallel_shafts(tmp_path):
    spec = reducer()
    gears = tuple(model.replace(g, kind="helical", helix_angle="15", hand="right") if g.id in ("G1", "G2") else g
                  for g in spec.gears)
    _, report = check(tmp_path, model.replace(spec, gears=gears))
    assert any("are both right-handed; gears on parallel shafts take opposite hands" in e for e in errors(report))


# -- gears that do not mesh but meet --------------------------------------------------------------


def test_an_unlisted_pair_at_mesh_distance_is_a_warning_not_a_clash(tmp_path):
    spec = reducer()
    extra = Gear("G5", "S2", "47", teeth="68", module="1.5", face_width="15")
    near = Gear("G6", "S1", "47", teeth="17", module="1.5", face_width="15")
    _, report = check(tmp_path, model.replace(spec, gears=spec.gears + (extra, near)))
    warnings = [d.message for d in report.diagnostics if not d.is_error]
    assert any("G5 and G6 sit where they would mesh" in w or "G6 and G5 sit where they would mesh" in w
               for w in warnings)


def test_a_clash_between_gears_that_do_not_mesh(tmp_path):
    spec = reducer()
    big = Gear("G5", "S3", "7.5", teeth="60", module="2", face_width="15")   # beside G2 at stage 1's height
    _, report = check(tmp_path, model.replace(spec, gears=spec.gears + (big,)))
    assert any("clash" in e for e in errors(report)), errors(report)


def test_a_shaft_without_gears_and_one_nothing_drives(tmp_path):
    spec = reducer()
    spec = model.replace(spec, shafts=spec.shafts + (Shaft("S9", x="300", y="0", role="output"),))
    _, report = check(tmp_path, spec)
    warnings = [d.message for d in report.diagnostics if not d.is_error]
    assert any("S9 carries no gear" in w for w in warnings)
    assert any("nothing drives S9" in w for w in warnings)


# -- speeds for other layouts ---------------------------------------------------------------------


def test_an_idler_reverses_and_keeps_the_ratio(tmp_path):
    spec = reducer()
    idler = Shaft("Si", x="97.75", y="0")
    shafts = (spec.shafts[0], spec.shafts[1], idler, model.replace(spec.shafts[2], x="165.75"))
    gears = spec.gears + (Gear("Id", "Si", "27", teeth="17", module="2", face_width="20"),)
    meshes = (spec.meshes[0], Mesh("G3", "Id"), Mesh("Id", "G4"))
    _, report = check(tmp_path, model.replace(spec, shafts=shafts, gears=gears, meshes=meshes))
    assert errors(report) == []
    assert report.motion.speeds["S3"] == Fraction(-125)
    assert report.worked_out_as.endswith("12.000 : 1 · output turns the other way")
    # The idler's shaft carries no torque; the output takes one more mesh's loss: 10 · 12 · 0.98³.
    assert report.motion.torques["Si"] == 0.0
    assert report.motion.torques["S3"] == pytest.approx(10 * 12 * 0.98 ** 3)


def test_a_z_minus_output_turns_the_same_way_when_seen_from_plus_z(tmp_path):
    spec = reducer()
    shafts = spec.shafts[:2] + (model.replace(spec.shafts[2], axis="Z-"),)
    gears = spec.gears[:3] + (model.replace(spec.gears[3], at="-27"),)
    _, report = check(tmp_path, model.replace(spec, shafts=shafts, gears=gears))
    assert errors(report) == []
    assert report.motion.speeds["S3"] == Fraction(-125)          # about its own axis, which points the other way
    assert report.motion.turns("S3") == "anticlockwise"           # but seen from +Z, as S1 does
    assert report.worked_out_as.endswith("output turns the same way")


def test_jammed_and_underdriven_boxes():
    def box(shafts, gears, meshes):
        return GearboxSpec(box=Box(name="T"), shafts=tuple(shafts), gears=tuple(gears), meshes=tuple(meshes))
    gears = (Gear("A", "S1", teeth="20", module="2", face_width="10"),
             Gear("B", "S2", teeth="40", module="2", face_width="10"))
    jammed = box([Shaft("S1", x="0", y="0", role="input", speed="100"), Shaft("S2", x="60", y="0", role="fixed")],
                 gears, [Mesh("A", "B")])
    assert "jammed" in kinematics.solve(jammed).jammed
    free = box([Shaft("S1", x="0", y="0", role="input", speed="100"), Shaft("S2", x="60", y="0"),
                Shaft("S3", x="200", y="0")], gears, [Mesh("A", "B")])
    motion = kinematics.solve(free)
    assert motion.free == ["S3"] and motion.speeds["S2"] == Fraction(-50)


def test_torque_stops_where_power_splits():
    box = GearboxSpec(box=Box(name="T", efficiency="100"),
                      shafts=(Shaft("S1", x="0", y="0", role="input", speed="100", torque="10"),
                              Shaft("S2", x="60", y="0"), Shaft("S3", x="-60", y="0")),
                      gears=(Gear("A", "S1", teeth="20", module="2", face_width="10"),
                             Gear("B", "S2", teeth="40", module="2", face_width="10"),
                             Gear("C", "S3", teeth="40", module="2", face_width="10")),
                      meshes=(Mesh("A", "B"), Mesh("A", "C")))
    motion = kinematics.solve(box)
    assert motion.speeds["S2"] == motion.speeds["S3"] == Fraction(-50)
    assert set(motion.torques) == {"S1"}              # each branch's share depends on its load



# -- found in the W3 review ------------------------------------------------------------------


def test_two_gear_pairs_between_the_same_shafts_get_no_move(tmp_path):
    spec = reducer()
    second = (Gear("G5", "S1", "47", teeth="20", module="1.5", face_width="15"),
              Gear("G6", "S2", "47", teeth="65", module="1.5", face_width="15"))
    loop = model.replace(spec, gears=spec.gears + second, meshes=spec.meshes + (Mesh("G5", "G6"),))
    report = checks.check(read(tmp_path, moved(loop, S2="64", S3="132")))
    assert not any(f.title.startswith("Move") for fs in report.fixes.values() for f in fs)


def test_an_idler_gets_no_shift_fix(tmp_path):
    spec = reducer()
    shafts = (spec.shafts[0], spec.shafts[1], Shaft("Si", x="98", y="0"), model.replace(spec.shafts[2], x="166"))
    gears = spec.gears + (Gear("Id", "Si", "27", teeth="17", module="2", face_width="20"),)
    spec = model.replace(spec, shafts=shafts, gears=gears, meshes=(spec.meshes[0], Mesh("G3", "Id"), Mesh("Id", "G4")))
    report = checks.check(read(tmp_path, spec))
    offered = [f.title for fs in report.fixes.values() for f in fs]
    assert offered and not any("profile-shift" in t and "Id" in t for t in offered)


def test_a_box_whose_gears_mesh_needs_an_input(tmp_path):
    spec = model.replace(reducer(), shafts=tuple(model.replace(s, role="", speed="", torque="") for s in reducer().shafts))
    _, report = check(tmp_path, spec)
    assert any("no shaft is an input with a speed" in e for e in errors(report))


def test_a_gear_just_outside_a_ring_is_a_clash(tmp_path):
    ring = Gear("R", "S1", "0", teeth="60", module="2", face_width="10", side="internal", rim="140")
    near = Gear("P", "S2", "0", teeth="20", module="2", face_width="10")
    spec = GearboxSpec(box=Box(name="T"), shafts=(Shaft("S1", x="0", y="0", role="input", speed="10"),
                                                 Shaft("S2", x=str(70 + 22 + 0.2), y="0")), gears=(ring, near))
    _, report = check(tmp_path, spec)
    assert any("from R's rim" in e for e in errors(report)), errors(report)


def test_a_loop_that_does_not_close_is_reported():
    """Three outside gears in a triangle, each at its own mesh distance: their teeth cannot all sit in each
    other's spaces (and the box is jammed besides)."""
    from gear_generator.gears import pair as pairs
    from gear_generator.workbook import geometry
    za, zb, zc = 20, 22, 24
    cab, cbc, cca = (pairs.describe(2.0, *z)[0] for z in ((za, zb), (zb, zc), (zc, za)))
    x = (cab ** 2 + cca ** 2 - cbc ** 2) / (2 * cab)
    y = math.sqrt(cca ** 2 - x ** 2)
    shafts = (Shaft("A", x="0", y="0", role="input", speed="10"), Shaft("B", x=repr(cab), y="0"),
              Shaft("C", x=repr(x), y=repr(y)))
    gears = (Gear("GA", "A", "5", teeth=str(za), module="2", face_width="10"),
             Gear("GB", "B", "5", teeth=str(zb), module="2", face_width="10"),
             Gear("GC", "C", "5", teeth=str(zc), module="2", face_width="10"))
    spec = GearboxSpec(box=Box(name="T"), shafts=shafts, gears=gears,
                       meshes=(Mesh("GA", "GB"), Mesh("GB", "GC"), Mesh("GC", "GA")))
    _, conflicts = geometry.phases(spec, geometry.layout(spec).placed, with_conflicts=True)
    assert conflicts
    report = checks.check(spec)
    assert any("a loop of meshes that does not close" in d.message for d in report.diagnostics)
    assert any("jammed" in e for e in errors(report))


def test_shift_for_centre_directly():
    from gear_generator.gears import pair as pairs
    x1, x2 = pairs.shift_for_centre(1.5, 17, 68, 64.0)
    assert x1 == pytest.approx(0.0845501, abs=1e-6) and x2 == pytest.approx(x1)
    assert pairs.describe(1.5, 17, 68, shift_1=x1, shift_2=x2)[0] == pytest.approx(64.0, abs=1e-6)
    with pytest.raises(ValueError, match="past the"):
        pairs.shift_for_centre(1.5, 17, 68, 70.0)
    with pytest.raises(ValueError, match="No profile shift brings"):
        pairs.shift_for_centre(1.5, 17, 68, 50.0)
