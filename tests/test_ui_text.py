"""The window's derived text, tested without a window."""

from gear_generator import ui_text
from gear_generator.gears import KINDS, pair
from gear_generator.gears.base import Diagnostic
from gear_generator.spec import GearSpec

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
