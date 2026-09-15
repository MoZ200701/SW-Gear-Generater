"""The pair solver: from a centre distance and a ratio to module and teeth."""

import pytest

from gear_generator.gears import pair
from gear_generator.spec import GearSpec, PairSpec, parse_ratio


def rows(candidates):
    return [(c.module, c.teeth_driver, c.teeth_driven) for c in candidates]


# -- the pinned cases -------------------------------------------------------


def test_sixty_millimetres_at_three_to_one():
    found = pair.solve(60, 3)
    assert rows(found[:3]) == [(1.5, 20, 60), (1.25, 24, 72), (1.0, 30, 90)]
    assert all(c.exact and c.standard and not c.undercut for c in found[:3])


def test_the_undercut_exact_rows_come_after_every_clean_row():
    found = pair.solve(60, 3)
    listed = rows(found)
    assert (2.0, 15, 45) in listed and (2.5, 12, 36) in listed
    first_undercut = min(listed.index((2.0, 15, 45)), listed.index((2.5, 12, 36)))
    clean = [c for c in found if not c.undercut and c.standard and abs(c.centre_error) < 1e-9]
    assert all(found.index(c) < first_undercut for c in clean)
    assert all(found[i].undercut for i in (listed.index((2.0, 15, 45)), listed.index((2.5, 12, 36))))


def test_rows_that_miss_the_centre_distance_come_last():
    found = pair.solve(61, 3, series="1+2", limit=1000)
    misses = [i for i, c in enumerate(found) if abs(c.centre_error) > 1e-9]
    hits = [i for i, c in enumerate(found) if abs(c.centre_error) <= 1e-9]
    assert misses and hits
    assert max(hits) < min(misses)


def test_forty_five_millimetres_at_two_to_one():
    assert rows(pair.solve(45, 2)[:3]) == [(1.5, 20, 40), (1.25, 24, 48), (1.0, 30, 60)]


def test_tooth_counts_far_below_min_teeth_are_not_offered():
    listed = rows(pair.solve(60, 3))
    assert (3.0, 10, 30) not in listed
    assert (5.0, 6, 18) not in listed
    assert pair.floor_teeth(17) == 12


def test_one_to_three_makes_the_driver_the_bigger_gear():
    best = pair.solve(60, parse_ratio("1:3"))[0]
    assert best.teeth_driver > best.teeth_driven
    assert (best.teeth_driver, best.teeth_driven) == (60, 20)


def test_the_ranking_is_the_documented_key():
    found = pair.solve(60, 3, series="1+2")
    assert found == sorted(found, key=pair.Candidate.rank)


def test_non_standard_rows_hit_exactly_and_are_flagged():
    found = pair.solve(62, 3)
    odd = [c for c in found if not c.standard]
    assert odd
    assert all(c.exact for c in odd)
    assert all(abs(c.module - 124.0 / (c.teeth_driver + c.teeth_driven)) < 1e-9 for c in odd)
    standard_hits = [found.index(c) for c in found if c.standard and abs(c.centre_error) < 1e-9]
    if standard_hits:
        assert max(standard_hits) < min(found.index(c) for c in odd)


def test_a_typed_module_is_the_only_module_tried():
    found = pair.solve(60, 3, module=1.5)
    assert {c.module for c in found} == {1.5}
    assert rows(found)[0] == (1.5, 20, 60)


def test_the_series_widens_what_is_tried():
    narrow = {c.module for c in pair.solve(60, 3) if c.standard}
    wide = {c.module for c in pair.solve(60, 3, series="1+2") if c.standard}
    assert narrow < wide


def test_solving_from_the_form():
    spec = PairSpec(mode="pair", centre_distance="60", ratio="3", gear_a=GearSpec(pressure_angle="20"))
    assert rows(pair.solve_spec(spec)[:1]) == [(1.5, 20, 60)]


# -- the other direction ----------------------------------------------------


def test_describe_gives_centre_ratio_and_contact_ratio():
    centre, ratio, epsilon = pair.describe(1.5, 20, 60)
    assert centre == 60.0 and ratio == 3.0
    assert 1.4 < epsilon < 2.0


def test_every_candidate_reports_its_errors():
    found = pair.solve(60, 3)
    near = next(c for c in found if c.ratio_error > 0)
    assert near.ratio == pytest.approx(near.teeth_driven / near.teeth_driver)
    assert near.ratio_error == pytest.approx(abs(near.ratio - 3) / 3)


# -- applying a choice ------------------------------------------------------


def test_applying_a_candidate_touches_only_module_and_teeth():
    a = GearSpec(module="9", teeth="99", bore="6", backlash="0.1", name="Motor", recipe="B")
    b = GearSpec(module="9", teeth="99", bore="", face_width="12", fillet="0.4")
    new_a, new_b = pair.apply(pair.solve(60, 3)[0], a, b)
    assert (new_a.module, new_a.teeth, new_b.module, new_b.teeth) == ("1.5", "20", "1.5", "60")
    assert new_a.with_values(module="9", teeth="99") == a
    assert new_b.with_values(module="9", teeth="99") == b


def test_the_mesh_angle_turns_an_even_gear_half_a_tooth():
    assert pair.mesh_angle(61) == 0.0
    assert pair.mesh_angle(60) == pytest.approx(3.0)


@pytest.mark.parametrize("centre,ratio", [(0, 3), (60, 0)])
def test_nonsense_is_refused(centre, ratio):
    with pytest.raises(Exception, match="more than zero"):
        pair.solve(centre, ratio)


# -- the assembly -------------------------------------------------------------


def _assembly(teeth_a="20", teeth_b="60", module="1.5"):
    return pair.assembly_plan(GearSpec(module=module, teeth=teeth_a), GearSpec(module=module, teeth=teeth_b),
                              r"C:\g\Pinion.SLDPRT", r"C:\g\Gear.SLDPRT", "", r"C:\g\Pair.SLDASM")


def test_the_assembly_plan_is_sound_and_mates_at_the_centre_the_teeth_make():
    from gear_generator.gears.base import AddGlobal, Mate
    plan = _assembly()
    assert plan.check() == []
    globals_ = {op.name: op.expression for op in plan.ops if isinstance(op, AddGlobal)}
    assert globals_ == {"Centre Distance": "60", "Ratio": "3", "Mesh Angle": "3"}
    distance = next(op for op in plan.ops if isinstance(op, Mate) and op.kind == "distance")
    assert (distance.value, distance.name, distance.a, distance.b) == (60.0, "Centre Distance", "gear2:Gear Axis",
                                                                       "gear1:plane3")
    # The build checks the teeth for interference, so nobody has to look along the axis.
    assert plan.manual_steps() == []


def test_the_mate_angle_is_never_zero_and_an_odd_count_turns_a_whole_pitch():
    assert pair.mate_angle(60) == pair.mesh_angle(60) == 3.0
    assert pair.mesh_angle(45) == 0.0 and pair.mate_angle(45) == 8.0


def test_gears_of_different_modules_do_not_make_an_assembly():
    from gear_generator.spec import InputError
    with pytest.raises(InputError, match="same module"):
        pair.assembly_plan(GearSpec(module="1.5"), GearSpec(module="2"), "a", "b", "", "c")


# -- helical pairs ----------------------------------------------------------


def _rows(candidates, n):
    return [(c.module, c.teeth_driver, c.teeth_driven, round(c.helix_angle, 4)) for c in candidates[:n]]


def test_a_blank_helix_angle_is_solved_so_every_exact_ratio_row_meets_the_centre_distance():
    from gear_generator.gears.pair import solve

    rows = solve(60.0, 2.0, kind="helical", helix_range=(8.0, 25.0))
    assert _rows(rows, 9) == [
        (2.5, 15, 30, 20.3641), (2.0, 19, 38, 18.1949), (1.5, 26, 52, 12.8386), (1.5, 25, 50, 20.3641),
        (1.25, 31, 62, 14.3615), (1.25, 30, 60, 20.3641), (1.0, 39, 78, 12.8386), (1.0, 38, 76, 18.1949),
        (1.0, 37, 74, 22.3316),
    ]
    assert all(abs(c.centre_error) < 1e-9 for c in rows)
    undercut = next(c for c in rows if (c.module, c.teeth_driver) == (3.0, 13))
    assert undercut.undercut and rows.index(undercut) > 8


def test_a_typed_helix_angle_is_held():
    from gear_generator.gears.pair import solve

    from gear_generator.gears.pair import describe

    centre = describe(2.0, 20, 40, 20.0, 15.0)[0]      # 62.116571…, exactly what m2 20:40 at 15° makes
    rows = solve(centre, 2.0, kind="helical", helix_angle=15.0)
    assert _rows(rows, 2) == [(2.5, 16, 32, 15.0), (2.0, 20, 40, 15.0)]
    assert all(abs(c.centre_error) < 1e-9 for c in rows[:2])


def test_describe_a_helical_pair_gives_the_transverse_contact_ratio():
    from gear_generator.gears.pair import describe

    centre, ratio, epsilon = describe(2.0, 20, 40, 20.0, 15.0)
    assert (round(centre, 6), ratio, round(epsilon, 4)) == (62.116571, 2.0, 1.5609)


def test_apply_writes_the_helix_and_gives_gear_b_the_other_hand():
    from gear_generator.gears.pair import apply, solve

    a = GearSpec(kind="helical", hand="right", face_width="20")
    b = GearSpec(kind="helical", hand="right", face_width="20", bore="12")
    chosen = solve(60.0, 2.0, kind="helical", helix_range=(8.0, 25.0))[1]
    new_a, new_b = apply(chosen, a, b)
    assert (new_a.module, new_a.teeth, new_a.helix_angle, new_a.hand) == ("2", "19", "18.194872", "right")
    assert (new_b.teeth, new_b.helix_angle, new_b.hand, new_b.bore) == ("38", "18.194872", "left", "12")


def test_a_helical_assembly_is_mated_at_the_transverse_centre_distance():
    from gear_generator.gears.base import Mate
    from gear_generator.gears.pair import assembly_plan

    a = GearSpec(kind="helical", module="2", teeth="20", helix_angle="15", hand="right")
    b = a.with_values(teeth="40", hand="left")
    plan = assembly_plan(a, b, r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "", r"C:\G\p.SLDASM")
    assert plan.check() == []
    centre = next(op for op in plan.ops if isinstance(op, Mate) and op.kind == "distance")
    assert centre.value == pytest.approx(62.116571, abs=1e-6)
    faces = next(op for op in plan.ops if isinstance(op, Mate) and op.id == "faces")
    assert (faces.a, faces.b) == ("gear2:plane1", "gear1:plane1")

    h = a.with_values(kind="herringbone", helix_angle="30")
    plan = assembly_plan(h, h.with_values(teeth="40", hand="left"), r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "",
                         r"C:\G\p.SLDASM")
    faces = next(op for op in plan.ops if isinstance(op, Mate) and op.id == "faces")
    assert (faces.a, faces.b) == ("gear2:Mid Plane", "gear1:Mid Plane")


@pytest.mark.parametrize("change, words", [
    ({"hand": "right"}, "opposite hands"),
    ({"helix_angle": "20"}, "same helix angle"),
    ({"kind": "spur"}, "same kind"),
])
def test_a_helical_assembly_refuses_gears_that_would_not_mesh(change, words):
    from gear_generator.gears.pair import assembly_plan
    from gear_generator.spec import InputError

    a = GearSpec(kind="helical", module="2", teeth="20", helix_angle="15", hand="right")
    b = a.with_values(**{"teeth": "40", "hand": "left", **change})
    with pytest.raises(InputError, match=words):
        assembly_plan(a, b, r"C:\G\a.SLDPRT", r"C:\G\b.SLDPRT", "", r"C:\G\p.SLDASM")
