"""The standard module series, and picking from them."""

import pytest

from gear_generator.gears import standards


@pytest.mark.parametrize("series", standards.SERIES)
def test_every_series_is_sorted_and_has_no_repeats(series):
    modules = standards.modules(series)
    assert list(modules) == sorted(modules)
    assert len(set(modules)) == len(modules)


def test_the_raw_series_are_each_sorted():
    for raw in (standards.ISO_MODULES_1, standards.ISO_MODULES_2, standards.FINE):
        assert list(raw) == sorted(raw)


def test_series_one_is_the_default_and_the_others_add_to_it():
    one = set(standards.modules())
    both = set(standards.modules(standards.SERIES_1_2))
    everything = set(standards.modules(standards.SERIES_ALL))
    assert one < both < everything
    assert 1.75 in both and 1.75 not in one
    assert 0.5 in everything and 0.5 not in both


def test_an_unknown_series_is_refused_by_name():
    with pytest.raises(ValueError, match="Module series"):
        standards.modules("7")


@pytest.mark.parametrize("wanted,nearest", [(1.5, 1.5), (1.4, 1.5), (1.1, 1.0), (2.2, 2.0), (70, 50)])
def test_the_nearest_series_one_module(wanted, nearest):
    assert standards.nearest_module(wanted) == nearest


def test_a_tie_goes_to_the_smaller_module():
    assert standards.nearest_module(1.125) == 1.0


def test_a_standard_module_is_recognised_in_any_series():
    assert standards.is_standard(1.375)
    assert not standards.is_standard(1.4)


def test_the_pressure_angles_are_offered_as_text():
    assert standards.PRESSURE_ANGLES == ("14.5", "20", "25")
