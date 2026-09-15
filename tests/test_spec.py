"""The form as data: kept as typed, read with sentences that name the field."""

import pytest

from gear_generator.spec import (
    GearSpec,
    InputError,
    PairSpec,
    default_stem,
    pair_stems,
    parse_ratio,
    sanitize_stem,
)


# -- round trips ------------------------------------------------------------


def test_a_gear_round_trips_through_a_dict():
    spec = GearSpec(module="1.25", teeth="40", bore="", backlash="0.05", name="Idler")
    assert GearSpec.from_dict(spec.to_dict()) == spec


def test_a_pair_round_trips_with_both_gears():
    pair = PairSpec(mode="pair", centre_distance="60", ratio="1:3",
                    gear_a=GearSpec(teeth="60"), gear_b=GearSpec(teeth="20"), assembly_name="Drive")
    back = PairSpec.from_dict(pair.to_dict())
    assert back == pair
    assert isinstance(back.gear_a, GearSpec)


def test_unknown_keys_from_a_later_version_are_ignored():
    raw = GearSpec().to_dict()
    raw["crown_radius"] = "15"
    assert GearSpec.from_dict(raw) == GearSpec()
    pair = PairSpec().to_dict()
    pair["invented_later"] = 1
    assert PairSpec.from_dict(pair) == PairSpec()


def test_a_typed_number_stays_text():
    spec = GearSpec(module="1.5", teeth="25")
    assert spec.to_dict()["module"] == "1.5"
    assert GearSpec.from_dict({"teeth": 25}).teeth == "25"


# -- blank is not zero ------------------------------------------------------


def test_a_blank_backlash_is_the_equation_and_a_zero_is_none_at_all():
    assert GearSpec(backlash="").backlash_mm() is None
    assert GearSpec(backlash="0").backlash_mm() == 0.0


def test_a_blank_fillet_is_the_equation():
    assert GearSpec(fillet="").fillet_mm() is None
    assert GearSpec(fillet="0.5").fillet_mm() == 0.5


def test_a_blank_bore_and_a_zero_bore_both_mean_no_bore_feature():
    assert not GearSpec(bore="").has_bore()
    assert not GearSpec(bore="0").has_bore()
    assert GearSpec(bore="8").has_bore()
    assert GearSpec(bore="").bore_mm() == 0.0


# -- refusals name their field ----------------------------------------------


@pytest.mark.parametrize(
    "field,value,reader,name",
    [
        ("module", "abc", "module_mm", "Module"),
        ("module", "", "module_mm", "Module"),
        ("teeth", "25.5", "teeth_count", "No. of teeth"),
        ("teeth", "x", "teeth_count", "No. of teeth"),
        ("pressure_angle", "twenty", "pressure_angle_deg", "Pressure angle"),
        ("face_width", "wide", "face_width_mm", "Face width"),
        ("bore", "?", "bore_mm", "Bore"),
        ("backlash", "some", "backlash_mm", "Backlash"),
        ("fillet", "r1", "fillet_mm", "Fillet"),
        ("profile_shift", "a", "profile_shift_value", "Profile shift"),
        ("module", "inf", "module_mm", "Module"),
    ],
)
def test_every_parse_refusal_names_the_field(field, value, reader, name):
    spec = GearSpec(**{field: value})
    with pytest.raises(InputError, match=name):
        getattr(spec, reader)()


def test_a_whole_number_typed_with_a_decimal_point_is_still_whole():
    assert GearSpec(teeth="25.0").teeth_count() == 25


def test_the_recipe_defaults_and_refuses_what_it_does_not_know():
    assert GearSpec(recipe="").recipe_or("A") == "A"
    assert GearSpec(recipe="B").recipe_or("A") == "B"
    with pytest.raises(InputError, match="Recipe"):
        GearSpec(recipe="C").recipe_or("A")


def test_pair_fields_are_read_with_their_names():
    with pytest.raises(InputError, match="Centre distance"):
        PairSpec(centre_distance="").centre_distance_mm()
    with pytest.raises(InputError, match="Centre distance"):
        PairSpec(centre_distance="-4").centre_distance_mm()
    with pytest.raises(InputError, match="Min teeth"):
        PairSpec(min_teeth="many").min_teeth_count()
    assert PairSpec(module="").module_mm() is None
    assert PairSpec(module="2").module_mm() == 2.0


# -- ratios -----------------------------------------------------------------


@pytest.mark.parametrize("text,value", [("3", 3.0), ("3:1", 3.0), ("1:3", 1 / 3), ("0.333", 0.333), (" 2 : 1 ", 2.0)])
def test_a_ratio_reads_as_driven_over_driver(text, value):
    assert parse_ratio(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["", "0", "-2", "1:0", "a:b", "3:"])
def test_a_ratio_that_is_not_one_is_refused(text):
    with pytest.raises(InputError, match="atio"):
        parse_ratio(text)


# -- names ------------------------------------------------------------------


def test_the_default_stem_says_module_and_teeth():
    assert default_stem(GearSpec(module="1.5", teeth="25")) == "Gear_m1.5_N25"
    assert GearSpec(module="1.50", teeth="25").stem() == "Gear_m1.5_N25"
    assert GearSpec(module="2", teeth="12").stem() == "Gear_m2_N12"


def test_a_typed_name_wins_and_is_made_legal():
    assert GearSpec(name="Drive: left").stem() == "Drive_ left"
    assert sanitize_stem("  ...  ") == "Gear"
    assert sanitize_stem("a@b") == "a_b"


def test_a_pair_calls_the_smaller_gear_the_pinion():
    pair = PairSpec(gear_a=GearSpec(module="1.5", teeth="20"), gear_b=GearSpec(module="1.5", teeth="60"))
    assert pair_stems(pair) == ("Pinion_m1.5_N20", "Gear_m1.5_N60", "Pair_m1.5_20T_60T")


def test_a_reduction_the_other_way_names_the_second_gear_the_pinion():
    pair = PairSpec(gear_a=GearSpec(teeth="60"), gear_b=GearSpec(teeth="20"))
    stem_a, stem_b, _ = pair_stems(pair)
    assert stem_a.startswith("Gear_") and stem_b.startswith("Pinion_")


def test_equal_gears_never_share_a_file_name():
    pair = PairSpec(gear_a=GearSpec(teeth="30"), gear_b=GearSpec(teeth="30"))
    stem_a, stem_b, _ = pair_stems(pair)
    assert stem_a != stem_b


def test_typed_pair_names_win():
    pair = PairSpec(gear_a=GearSpec(name="Motor"), gear_b=GearSpec(name="Wheel"), assembly_name="Drive")
    assert pair_stems(pair) == ("Motor", "Wheel", "Drive")
