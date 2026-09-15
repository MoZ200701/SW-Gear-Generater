"""The window's derived text, tested without a window."""

import pytest

from gear_generator import ui_text
from gear_generator.gears import KINDS, pair
from gear_generator.gears.base import Diagnostic
from gear_generator.spec import GearSpec, PairSpec, pair_stems

SPUR = KINDS["spur"]


def test_the_gear_panel_reads_out_kind_and_recipe():
    assert ui_text.kind_readout("spur", "A") == "Spur · involute curve"
    assert ui_text.kind_readout("spur", "B") == "Spur · arc flanks"


def test_a_gear_reads_out_in_one_breath():
    assert ui_text.gear_readout(GearSpec()) == "m1.5 · z25 · 20° · PD 37.5 mm"
    assert ui_text.gear_readout(GearSpec(module="1.25", teeth="72", pressure_angle="14.5")) == (
        "m1.25 · z72 · 14.5° · PD 90 mm"
    )


def test_a_half_typed_gear_says_so():
    assert ui_text.gear_readout(GearSpec(teeth="2x")) == "check the fields"


def test_the_derived_line():
    g = SPUR.derive(GearSpec())
    assert ui_text.derived_line(g) == "PD 37.5 · OD 40.5 · RD 33.75 · base 35.238 · p 4.712"


def test_the_derived_rows_say_where_a_value_came_from():
    rows = dict(ui_text.derived_rows(SPUR.derive(GearSpec())))
    assert rows["Pitch diameter"] == "37.5"
    assert rows["Backlash"] == "0.45 · 0.3m"
    typed = dict(ui_text.derived_rows(SPUR.derive(GearSpec(backlash="0.05"))))
    assert typed["Backlash"] == "0.05"


def test_errors_come_before_warnings_and_each_is_said_once():
    lines = ui_text.warning_lines([
        Diagnostic("warning", "Thin rim."),
        Diagnostic("error", "No tooth."),
        Diagnostic("warning", "Thin rim."),
    ])
    assert lines == ["No tooth.", "Thin rim."]


def test_the_pair_readout_grows_as_it_is_filled_in():
    assert ui_text.pair_readout("", "") == "centre distance and ratio"
    assert ui_text.pair_readout("60", "3") == "C 60 mm · i 3"
    chosen = pair.solve(60, 3)[0]
    assert ui_text.pair_readout("60", "3", chosen) == "C 60 mm · i 3 · m1.5 20:60"


def test_a_candidate_row_says_what_is_off_about_it():
    found = pair.solve(60, 3)
    assert ui_text.candidate_row(found[0]) == ("1.5", "20 : 60", "exact", "exact")
    near = next(c for c in found if c.ratio_error > 0 and not c.undercut)
    module, teeth, error, tag = ui_text.candidate_row(near)
    assert error.startswith("i ") and error.endswith(" %") and tag == "near"
    undercut = next(c for c in found if c.undercut and c.exact)
    assert ui_text.candidate_row(undercut)[2] == "undercut"


def test_a_non_standard_module_is_starred():
    odd = next(c for c in pair.solve(62, 3) if not c.standard)
    assert ui_text.candidate_row(odd)[0].endswith(" *")


def test_a_centre_distance_miss_is_signed():
    miss = next(c for c in pair.solve(61, 3) if abs(c.centre_error) > 1e-9)
    assert ui_text.candidate_row(miss)[2].startswith(("C +", "C −"))


def test_the_solve_summary_counts():
    found = pair.solve(60, 3)
    assert ui_text.solve_summary(found).endswith("· 3 exact")
    assert "No pair" in ui_text.solve_summary([])


def test_the_solve_summary_names_the_chosen_candidate():
    """With the flyout closed, the strip still says which pair was picked."""
    found = pair.solve(60, 3)
    assert ui_text.solve_summary(found, found[0]) == "64 candidates · 3 exact · m1.5 20 : 60 chosen"


# -- Derived, in pair mode -----------------------------------------------------


def test_the_derived_panel_reads_out_the_pair():
    centre, ratio, epsilon = pair.describe(1.5, 20, 60, 20.0)
    assert ui_text.pair_derived_readout(centre, ratio, epsilon) == "C 60 mm · i 3 · contact ratio 1.671"


def test_the_pair_rows_above_the_table():
    centre, ratio, epsilon = pair.describe(1.5, 20, 60, 20.0)
    assert ui_text.pair_derived_rows(centre, ratio, epsilon, 20, 60) == [
        ("Centre distance", "60 mm"),
        ("Ratio", "3 · 20 : 60"),
        ("Contact ratio", "1.671"),
    ]


# -- the explainer card --------------------------------------------------------
#
# The worked lines are design/UI-DESIGN.md §2's table: Gear A of the pair the
# docs use throughout — m 1.5, 20 teeth, 20°, bore 10, at C 60 and i 3.

GEAR_A = GearSpec(teeth="20")
GEAR_B = GearSpec(teeth="60")
PAIR = PairSpec(mode="pair", centre_distance="60", ratio="3", gear_a=GEAR_A, gear_b=GEAR_B)
DERIVED_A = SPUR.derive(GEAR_A)
FOLDER = r"D:\Gears"

WORKED = {
    "module": "m 1.5 × z 20 = PD 30 mm · tooth depth 3.375 · circular pitch 4.712",
    "teeth": "z 20 → PD 30 mm · OD 33 mm · no undercut (17 or more)",
    "pressure_angle": "20° → base diameter 28.191 mm · undercut below 17 teeth",
    "face_width": "10 mm = 6.7 × module",
    "bore": "10 mm → rim 8.125 mm to the root circle",
    "backlash": "blank → 0.45 mm (0.3 m) · tooth 1.906 · space 2.806 · play in the mesh 0.9",
    "fillet": "blank → 0.57 mm (0.38 m)",
    "name": r"Pinion_m1.5_N20.SLDPRT in D:\Gears",
    "centre_distance": "60 mm → z₁ + z₂ = 80 at m 1.5 · 96 at m 1.25 · 120 at m 1",
    "ratio": "3 → 20 : 60",
    "pair_module": "blank → 1 · 1.25 · 1.5 · 2 · 2.5 · 3 · 4 … from Series 1",
    "series": "Series 1 → 18 modules from 1 to 50 (ISO 54)",
    "teeth_range": "17 to 200 → 64 candidates at C 60, i 3 · 3 exact",
    "assembly_name": r"Pair_m1.5_20T_60T.SLDASM in D:\Gears",
    "teeth_side": "external → teeth point outward, tips at 33 mm",
    "rim": "only a ring has a rim",
    "shaft_angle": "only a bevel gear has a shaft angle",
    "mate_teeth": "only a bevel gear has a mate count",
    "cone_distance": "check the fields",
    "mesh": "external → the gears sit side by side, C = m (z₁ + z₂) / 2",
    "shafts": "parallel → both gears the same helix angle, opposite hands",
    "pair_shaft_angle": "Σ 90°",
}


@pytest.mark.parametrize("field", ui_text.EXPLAINER_FIELDS)
def test_every_field_works_its_own_value_out(field):
    name, symbol, what, worked = ui_text.explainer(field, DERIVED_A, pair_stems(PAIR)[0], PAIR, FOLDER)
    assert name and what.endswith(".")
    assert worked == WORKED[field]
    assert (symbol == "") == (field in ("bore", "name", "series", "assembly_name", "teeth_side", "rim", "mesh",
                                        "shafts"))


def test_every_field_on_the_form_has_a_card():
    assert set(ui_text.EXPLAINER_FIELDS) == set(WORKED)
    assert len(ui_text.GEAR_EXPLAINERS) == 12 and len(ui_text.PAIR_EXPLAINERS) == 10


def test_a_typed_backlash_and_fillet_drop_the_word_blank():
    typed = SPUR.derive(GearSpec(teeth="20", backlash="0.05", fillet="0.4"))
    assert ui_text.explainer("backlash", typed, "", PAIR)[3].startswith("0.05 mm · tooth")
    assert ui_text.explainer("fillet", typed, "", PAIR)[3] == "0.4 mm"


def test_a_blank_bore_says_what_blank_means():
    solid = SPUR.derive(GearSpec(teeth="20", bore=""))
    assert ui_text.explainer("bore", solid, "")[3] == "blank → a solid disc, no bore feature"


def test_a_gear_that_does_not_work_out_says_check_the_fields():
    for field in ui_text.EXPLAINER_FIELDS:
        assert ui_text.explainer(field, None, "", PAIR, FOLDER)[3] == "check the fields"
    # …and so does a solver field with nothing to solve.
    empty = PairSpec(mode="pair", gear_a=GEAR_A, gear_b=GEAR_B)
    assert ui_text.explainer("centre_distance", DERIVED_A, "", empty)[3] == "check the fields"
    assert ui_text.explainer("ratio", DERIVED_A, "", None)[3] == "check the fields"


def test_the_name_line_drops_the_folder_until_one_is_chosen():
    assert ui_text.explainer("name", DERIVED_A, "Gear_m1.5_N20")[3] == "Gear_m1.5_N20.SLDPRT"


def test_an_unknown_field_is_refused_in_a_sentence():
    with pytest.raises(ValueError, match="no explainer for a field called 'kind'"):
        ui_text.explainer("kind", DERIVED_A, "")


def test_the_output_readout_keeps_the_end_of_a_long_path():
    assert ui_text.output_readout("") == "choose a folder"
    assert ui_text.output_readout(r"C:\Gears") == r"C:\Gears"
    long = "C:\\" + "very\\" * 20 + "Gears"
    shortened = ui_text.output_readout(long)
    assert shortened.startswith("…") and shortened.endswith("Gears") and len(shortened) == 38


def test_the_link_headline_is_happy_with_no_document_open():
    assert ui_text.link_headline(False, None) == ("pywin32 not installed", "off")
    assert ui_text.link_headline(True, None) == ("not reachable", "bad")
    assert ui_text.link_headline(True, {"version": "SolidWorks 2026", "title": ""}) == (
        "SolidWorks 2026 — no document open", "ok"
    )
    assert ui_text.link_headline(True, {"version": "SolidWorks 2026", "title": "Gear.SLDPRT"})[1] == "ok"


def test_the_mode_note_says_what_the_button_will_do():
    assert ui_text.mode_note("single", ["Gear_m1.5_N25"]) == "Build will make Gear_m1.5_N25.SLDPRT."
    assert ui_text.mode_note("pair", ["Pinion_m1.5_N20", "Gear_m1.5_N60", "Pair_m1.5_20T_60T"]) == (
        "Build will make Pinion_m1.5_N20.SLDPRT, Gear_m1.5_N60.SLDPRT and Pair_m1.5_20T_60T.SLDASM."
    )
    assert ui_text.mode_note("single", ["X"], update_count=3, document="Gear_m1.5_N25.SLDPRT") == (
        "Update values will change 3 variables in Gear_m1.5_N25.SLDPRT."
    )


def test_manual_steps_are_counted():
    assert ui_text.manual_steps_line([]) == ""
    assert ui_text.manual_steps_line(["Assign a material."]) == "1 thing to do by hand: Assign a material."
    assert ui_text.manual_steps_line(["A.", "B", "A."]) == "2 things to do by hand: A; B."


# -- after a build -------------------------------------------------------------


def _result(**values):
    from gear_generator.swbuild import BuildResult
    base = dict(document="Part1", saved=r"C:\Gears\Gear_m1.5_N25.SLDPRT", rebuilt=True,
                manual=["Assign a material to Gear_m1.5_N25; the build leaves it unset."])
    base.update(values)
    return BuildResult(**base)


def test_a_clean_build_names_the_file_and_the_manual_step():
    text, ok = ui_text.build_status(_result())
    assert ok
    assert text == ("Built Gear_m1.5_N25.SLDPRT. 1 thing to do by hand: Assign a material to Gear_m1.5_N25; "
                    "the build leaves it unset.")


def test_a_failed_build_says_where_it_stopped_and_what_solidworks_said():
    text, ok = ui_text.build_status(_result(saved="", failures=[("cut     'Tooth Space' from space, through all",
                                                                   "FeatureCut4 would not cut.")]))
    assert not ok
    assert text == "Part1 was left open, unsaved. cut     'Tooth Space' from space, through all: FeatureCut4 would not cut."


def test_a_build_with_something_to_check_is_not_all_clear():
    text, ok = ui_text.build_status(_result(checks=["Tooth Space Sketch is under-defined, not fully defined"]))
    assert not ok and "Check: Tooth Space Sketch is under-defined" in text


def test_a_pair_lists_all_three_files_or_the_first_failure():
    from gear_generator.swbuild import PairResult
    asm = _result(saved=r"C:\Gears\Pair_m1.5_20T_60T.SLDASM", manual=["Look along the gear axis."])
    text, ok = ui_text.pair_status(PairResult(_result(saved=r"C:\G\Pinion.SLDPRT"), _result(saved=r"C:\G\Gear.SLDPRT"), asm))
    assert ok and text.startswith("Built Pinion.SLDPRT, Gear.SLDPRT and Pair_m1.5_20T_60T.SLDASM.")
    assert "2 things to do by hand" in text
    broken = PairResult(_result(saved="", failures=[("pattern", "no")]), skipped="the second gear and the assembly")
    text, ok = ui_text.pair_status(broken)
    assert not ok and text.endswith("Skipped the second gear and the assembly.")


def test_update_values_says_how_many_changed():
    from gear_generator.swbuild import UpdateResult
    assert ui_text.update_status(UpdateResult(document="G.SLDPRT", changed=["Module"], rebuilt=True)) == (
        "Changed 1 variable in G.SLDPRT and rebuilt it.", True)
    assert ui_text.update_status(UpdateResult(document="G.SLDPRT"))[0].startswith("Nothing to update")
    text, ok = ui_text.update_status(UpdateResult(document="G.SLDPRT", failures=[('"Module"', "refused")]))
    assert not ok and text == '"Module" could not be set in G.SLDPRT: refused'
