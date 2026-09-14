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
