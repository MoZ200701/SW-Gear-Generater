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
    # Two of the exact rows are undercut ones cleared by equal and opposite shifts.
    assert ui_text.solve_summary(found).endswith("· 3 exact · 2 with shift")
    assert "No pair" in ui_text.solve_summary([])


def test_the_solve_summary_names_the_chosen_candidate():
    """With the flyout closed, the strip still says which pair was picked."""
    found = pair.solve(60, 3)
    assert ui_text.solve_summary(found, found[0]) == "69 candidates · 3 exact · 2 with shift · m1.5 20 : 60 chosen"


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
    "groove": "only a herringbone gear has a centre groove",
    "helix_angle": "only a helical gear has a helix angle",
    "hand": "only a helical gear has a hand",
    "hands": "same → β₁ + β₂ = 90°, gear B the same hand as gear A",
    "profile_shift": "0 → a standard tooth · OD 33 mm · root 26.25 · tooth at pitch 1.906 · undercut below 17 teeth",
    "name": r"Pinion_m1.5_N20.SLDPRT in D:\Gears",
    "centre_distance": "60 mm → z₁ + z₂ = 80 at m 1.5 · 96 at m 1.25 · 120 at m 1",
    "ratio": "3 → 20 : 60",
    "pair_module": "blank → 1 · 1.25 · 1.5 · 2 · 2.5 · 3 · 4 … from Series 1",
    "series": "Series 1 → 18 modules from 1 to 50 (ISO 54)",
    "teeth_range": "17 to 200 → 69 candidates at C 60, i 3 · 3 exact · 2 with shift",
    "assembly_name": r"Pair_m1.5_20T_60T.SLDASM in D:\Gears",
    "teeth_side": "external → teeth point outward, tips at 33 mm",
    "rim": "only a ring has a rim",
    "shaft_angle": "only a bevel gear has a shaft angle",
    "mate_teeth": "only a bevel gear has a mate count",
    "cone_distance": "check the fields",
    "mesh": "external → the gears sit side by side, C = m (z₁ + z₂) / 2",
    "shafts": "parallel → both gears the same helix angle, opposite hands",
    "pair_shaft_angle": "Σ 90°",
    "motion": "fixed → gear 1 fixed, gear 2 mated at the mesh angle; nothing turns",
}


@pytest.mark.parametrize("field", ui_text.EXPLAINER_FIELDS)
def test_every_field_works_its_own_value_out(field):
    name, symbol, what, worked = ui_text.explainer(field, DERIVED_A, pair_stems(PAIR)[0], PAIR, FOLDER)
    assert name and what.endswith(".")
    assert worked == WORKED[field]
    assert (symbol == "") == (field in ("bore", "name", "series", "assembly_name", "teeth_side", "rim", "mesh",
                                        "shafts", "motion", "hand", "hands"))


def test_every_field_on_the_form_has_a_card():
    assert set(ui_text.EXPLAINER_FIELDS) == set(WORKED)
    assert len(ui_text.GEAR_EXPLAINERS) == 16 and len(ui_text.PAIR_EXPLAINERS) == 12


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


# -- W4: the footer as one decision, and the sentences of a gearbox build and update -----------------------------
#
# Plans, results and records are built from their dataclasses, never by plan_gearbox, classify, build_gearbox or
# update_gearbox; the gate is a real assessment of the 12 : 1 fixture.

import dataclasses  # noqa: E402

from gear_generator import store, swbuild  # noqa: E402
from gear_generator.gears.base import BuildPlan, GlobalVariable, NewAssembly, NewPart  # noqa: E402
from gear_generator.workbook import assess, model, xlsx  # noqa: E402
from gear_generator.workbook.build import PartJob  # noqa: E402
from gear_generator.workbook.gearbox import GearboxPlan, LayoutReuse, PartReuse  # noqa: E402
from gear_generator.workbook.model import Gear  # noqa: E402
from gear_generator.workbook.update import PartUpdate, UpdatePlan  # noqa: E402
from test_workbook_model import reducer, write  # noqa: E402

P = "C:\\Parts\\Reducer_12to1"
STEMS = ("Gear_m1.5_N17", "Gear_m1.5_N68", "Gear_m2_N17", "OutputGear")


def _path(stem, ext=".SLDPRT"):
    return f"{P}\\{stem}{ext}"


@pytest.fixture
def ready(tmp_path):
    """The 12 : 1 workbook, read and assessed: every gate open."""
    spec, diagnostics = model.from_book(xlsx.read(write(tmp_path, reducer())))
    a = assess.assess(spec, diagnostics, P)
    assert a.lay_out_refusal() == ""
    return a


@pytest.fixture
def with_bevel(tmp_path):
    """The 12 : 1 workbook with a bevel gear: its parts build, its layout waits for W6."""
    spec = reducer()
    spec = model.replace(spec, gears=spec.gears + (Gear("G6", "S2", "60", "bevel", "external", "20", "3", "", "14",
                                                        "10"),))
    read, diagnostics = model.from_book(xlsx.read(write(tmp_path, spec)))
    a = assess.assess(read, diagnostics, P)
    assert a.build_refusal() == "" and a.parts.refused
    return a


def _job(stem, gears, path=None):
    return PartJob(stem, path or _path(stem), tuple(gears), GearSpec(), None, BuildPlan("spur", "A", (NewPart(""),)))


def _reuse(stem, gears, revision=0):
    return PartReuse(_path(stem), stem, tuple(gears), GearSpec(), None, (GlobalVariable("No. of Teeth", "17"),),
                     revision)


def _gearbox(name="Reducer_12to1", build=(), reuse=(), layout="build", assembly=True, **changes):
    layout_path = _path(f"{name}_Layout")
    plans = {"build": BuildPlan("layout", "", (NewPart(""),)),
             "reuse": LayoutReuse(layout_path, (GlobalVariable("S2 X", "63.75"),), ("S2 Axis",)), None: None}
    fields = dict(revision=0, name=name, folder=P, layout_path=layout_path if layout else "",
                  assembly_path=_path(name, ".SLDASM") if assembly else "", build=tuple(build), reuse=tuple(reuse),
                  shafts=(), frames={}, layout=plans[layout],
                  assembly=BuildPlan("assembly", "", (NewAssembly(""),)) if assembly else None, handles={},
                  part_of={})
    fields.update(changes)
    return GearboxPlan(**fields)


FULL = dict(build=[_job(s, [g]) for s, g in zip(STEMS, ("G1", "G2", "G3", "G4"))])


def _record(assembly=True, layout=True, unsaved=None):
    parts = [store.PartEntry(path=_path(s), gears=[g], revision=0) for s, g in zip(STEMS, ("G1", "G2", "G3", "G4"))]
    gearbox = store.GearboxRecord(
        revision=0, name="Reducer_12to1", layout=_path("Reducer_12to1_Layout") if layout else "",
        assembly=_path("Reducer_12to1", ".SLDASM") if assembly else "",
        components=[store.ComponentEntry(gear=g, part=_path(s), name=f"{s}-1") for s, g in
                    zip(STEMS, ("G1", "G2", "G3", "G4"))] if assembly else [])
    return store.LinkRecord(workbook=f"{P}\\Reducer_12to1.xlsx", parts=parts, gearbox=gearbox if layout else None,
                            unsaved=unsaved or {})


def _update(**changes):
    part = PartUpdate(_path("Gear_m1.5_N68"), ("G2",), GearSpec(module="1.5", teeth="69"), None,
                      (GlobalVariable("No. of Teeth", "69"),), changed=True)
    fields = dict(parts=(part,), layout=swbuild.DocumentValues(_path("Reducer_12to1_Layout")),
                  assembly=_path("Reducer_12to1", ".SLDASM"), moved_shafts=("S2", "S3"),
                  replaced=("G2", "G3", "G4"))
    fields.update(changes)
    return UpdatePlan(**fields)


def _saved(stem, ext=".SLDPRT", **values):
    return swbuild.BuildResult(document=stem, saved=_path(stem, ext), **values)


def _failed(document, what="cut 'Tooth Space'", why="FeatureCut4 would not cut."):
    return swbuild.BuildResult(document=document, failures=[(what, why)])


# progress


@pytest.mark.parametrize("step,updating,text", [
    (None, False, "Building in SolidWorks…"),
    (None, True, "Updating SolidWorks…"),
    (swbuild.Step("part", "Gear_m1.5_N68", 2, 4), False, "Building in SolidWorks: part 2 of 4, Gear_m1.5_N68…"),
    (swbuild.Step("check", "Gear_m1.5_N17", 1, 3), False,
     "Building in SolidWorks: checking Gear_m1.5_N17 (1 of 3 already built)…"),
    (swbuild.Step("layout", "Reducer_12to1_Layout"), False,
     "Building in SolidWorks: the layout part, Reducer_12to1_Layout…"),
    (swbuild.Step("assembly", "Reducer_12to1"), False, "Building in SolidWorks: the assembly, Reducer_12to1…"),
    (swbuild.Step("interference"), False, "Building in SolidWorks: checking interference…"),
    (swbuild.Step("check", "Gear_m1.5_N68", 1, 6), True, "Updating SolidWorks: checking Gear_m1.5_N68 (1 of 6)…"),
    (swbuild.Step("values", "Gear_m1.5_N68"), True, "Updating SolidWorks: Gear_m1.5_N68…"),
    (swbuild.Step("place", "Reducer_12to1"), True, "Updating SolidWorks: placing the gears in Reducer_12to1…"),
    (swbuild.Step("interference"), True, "Updating SolidWorks: checking interference…"),
])
def test_progress_says_what_the_worker_is_doing(step, updating, text):
    assert ui_text.progress_text(step, updating) == text


# a finished build


def test_a_built_gearbox_names_its_files_and_says_there_is_no_interference():
    plan = _gearbox(**FULL)
    result = swbuild.GearboxResult(
        parts=swbuild.ManyResult(built=[_saved(s, manual=[f"Assign a material to {s}; the build leaves it unset."])
                                        for s in STEMS]),
        layout=_saved("Reducer_12to1_Layout"), assembly=_saved("Reducer_12to1", ".SLDASM"))
    assert ui_text.gearbox_status(plan, result) == (
        "Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM; no interference between the gears. 1 thing "
        "to do by hand: Assign a material to each of the 4 parts; the build leaves it unset.", True)


def test_a_build_again_says_what_it_reused():
    plan = _gearbox("Reducer_12to1_r2", build=[_job("Gear_m1.5_N68_r2", ["G2"])],
                    reuse=[_reuse("Gear_m1.5_N17", ["G1"]), _reuse("Gear_m2_N17", ["G3"]),
                           _reuse("OutputGear", ["G4"])])
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved("Gear_m1.5_N68_r2")]),
                                   layout=_saved("Reducer_12to1_r2_Layout"),
                                   assembly=_saved("Reducer_12to1_r2", ".SLDASM"))
    assert ui_text.gearbox_status(plan, result) == (
        "Built 1 part, Reducer_12to1_r2_Layout and Reducer_12to1_r2.SLDASM, reusing the 3 parts already built; no "
        "interference between the gears.", True)


def test_a_clash_is_a_check_that_stands_out():
    plan = _gearbox(**FULL)
    result = swbuild.GearboxResult(
        parts=swbuild.ManyResult(built=[_saved(s) for s in STEMS]), layout=_saved("Reducer_12to1_Layout"),
        assembly=_saved("Reducer_12to1", ".SLDASM"),
        clashes=[swbuild.Clash(("Gear_m1.5_N17-1", "Gear_m1.5_N68-1"), ("G1", "G2"), 12.3454)])
    assert ui_text.gearbox_status(plan, result) == (
        "Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM. Check: G1 and G2 interfere, 12.345 mm³; look "
        "at their mesh in Reducer_12to1.SLDASM.", False)
    result.clashes.append(swbuild.Clash((), (), 0.5))
    assert ui_text.gearbox_status(plan, result)[0].endswith(
        "Check: G1 and G2 interfere, 12.345 mm³; an interference of 0.5 mm³ that SolidWorks could not name; look at "
        "those meshes in Reducer_12to1.SLDASM.")
    result.clashes, result.interference_error = [], "SolidWorks did not answer."
    assert ui_text.gearbox_status(plan, result) == (
        "Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM. Interference could not be checked: "
        "SolidWorks did not answer. Look at each mesh in Reducer_12to1.SLDASM by eye.", False)


def test_a_part_that_fails_stops_the_rest_and_build_carries_on():
    plan = _gearbox(**FULL)
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved(STEMS[0]), _failed("Part3")],
                                                            skipped=[_path(STEMS[2]), _path(STEMS[3])]))
    assert ui_text.gearbox_status(plan, result) == (
        "1 part built before it; Part3 was left open, unsaved. cut 'Tooth Space': FeatureCut4 would not cut. 2 parts "
        "not attempted, nor the layout and assembly. Press Build to carry on: what was built is reused.", False)
    result.parts.skipped = []
    assert ui_text.gearbox_status(plan, result)[0].endswith(
        "would not cut. The layout and assembly were not attempted. Press Build to carry on: what was built is "
        "reused.")
    parts_only = _gearbox(layout=None, assembly=False, **FULL)
    result.parts.skipped = [_path(STEMS[2])]
    assert ui_text.gearbox_status(parts_only, result)[0].endswith(
        "would not cut. 1 part not attempted. Press Build parts to carry on: what was built is reused.")


def test_a_layout_that_fails_leaves_the_parts_for_the_next_press():
    plan = _gearbox(**FULL)
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved(s) for s in STEMS]),
                                   layout=_failed("Part5", "insert plane 'S2 X Plane'", "SolidWorks returned None."))
    assert ui_text.gearbox_status(plan, result) == (
        "Built 4 parts; Part5 was left open, unsaved. insert plane 'S2 X Plane': SolidWorks returned None. The "
        "assembly was not attempted. Press Build to carry on: the parts are reused.", False)


def test_an_assembly_that_fails_leaves_the_parts_and_layout_for_the_next_press():
    plan = _gearbox(**FULL)
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved(s) for s in STEMS]),
                                   layout=_saved("Reducer_12to1_Layout"),
                                   assembly=_failed("Assem1", "place G2", "Transform2 was not taken."))
    assert ui_text.gearbox_status(plan, result) == (
        "Built 4 parts and Reducer_12to1_Layout; the assembly Assem1 was left open, unsaved. place G2: Transform2 was "
        "not taken. Press Build to try the assembly again: the parts and layout are reused.", False)


def test_a_retry_after_the_assembly_failed_reuses_the_layout():
    plan = _gearbox(layout="reuse", reuse=[_reuse(s, [g]) for s, g in zip(STEMS, ("G1", "G2", "G3", "G4"))])
    result = swbuild.GearboxResult(layout_reused=_path("Reducer_12to1_Layout"),
                                   assembly=_saved("Reducer_12to1", ".SLDASM"))
    assert ui_text.gearbox_status(plan, result) == (
        "Built Reducer_12to1.SLDASM, reusing Reducer_12to1_Layout and the 4 parts already built; no interference "
        "between the gears.", True)
    result.assembly = _failed("Assem1", "place G2", "Transform2 was not taken.")
    assert ui_text.gearbox_status(plan, result)[0].startswith(
        "Reused Reducer_12to1_Layout and the 4 parts already built; the assembly Assem1 was left open, unsaved.")


def test_build_parts_counts_what_it_made():
    plan = _gearbox(layout=None, assembly=False, build=[_job(STEMS[1], ["G2"])], reuse=[_reuse(STEMS[0], ["G1"])])
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved(STEMS[1])]))
    assert ui_text.gearbox_status(plan, result) == ("Built 1 part, reusing the part already built.", True)


# before Update SolidWorks, and after


def test_the_update_summary_says_what_will_change():
    assert ui_text.update_summary(_update()) == (
        "Update SolidWorks will change G2's values (Gear_m1.5_N68), move S2 and S3 in Reducer_12to1_Layout, and "
        "re-place G2, G3 and G4.")
    shared = PartUpdate(_path("Gear_m1.5_N17"), ("G1", "G5"), GearSpec(), None, (), changed=True)
    assert ui_text.update_summary(_update(parts=(_update().parts[0], shared), moved_shafts=(), replaced=())) == (
        "Update SolidWorks will change the values in Gear_m1.5_N68 (G2) and Gear_m1.5_N17 (G1, G5).")
    assert ui_text.update_summary(_update(parts=(), moved_shafts=(), replaced=("G4",))) == (
        "Update SolidWorks will re-place G4.")
    assert ui_text.update_summary(_update(parts=(), moved_shafts=(), replaced=())) == (
        "SolidWorks already matches the workbook on record; Update SolidWorks checks it live and puts right anything "
        "changed there.")


def test_a_change_update_cannot_carry_offers_to_build_again():
    assert ui_text.update_summary(_update(structural=("G2's bore was added, which its built part cannot take.",))) == (
        "G2's bore was added, which its built part cannot take: Update SolidWorks offers to build again as a new "
        "revision.")
    two = _update(structural=("G2's bore was added, which its built part cannot take.", "S4 was added."))
    assert ui_text.update_summary(two).startswith("G2's bore was added, which its built part cannot take (and 1 "
                                                  "other change Update SolidWorks cannot carry): ")
    assert ui_text.update_summary(_update(missing=(_path("Gear_m1.5_N68"),))) == (
        f"Gear_m1.5_N68.SLDPRT is no longer in {P}: it was moved or renamed since it was built, so Update SolidWorks "
        "offers to build again as a new revision.")
    both = _update(missing=(_path("Gear_m1.5_N68"), _path("Reducer_12to1_Layout")), structural=("S4 was added.",))
    assert ui_text.update_summary(both) == (
        "Gear_m1.5_N68.SLDPRT and Reducer_12to1_Layout.SLDPRT are no longer where they were built: they were moved "
        "or renamed since (and 1 other change Update SolidWorks cannot carry), so Update SolidWorks offers to build "
        "again as a new revision.")


def _updated(**values):
    fields = dict(parts=[swbuild.UpdateResult(document="Gear_m1.5_N68.SLDPRT", changed=["No. of Teeth"],
                                              rebuilt=True)],
                  layout=swbuild.UpdateResult(document="Reducer_12to1_Layout.SLDPRT", changed=["S2 X", "S3 X"],
                                              rebuilt=True),
                  placed=["G2", "G3", "G4"], rebuilt=True,
                  changed=[_path("Gear_m1.5_N68"), _path("Reducer_12to1_Layout"), _path("Reducer_12to1", ".SLDASM")])
    fields.update(values)
    return swbuild.GearboxUpdate(**fields)


def test_an_update_says_what_it_changed_that_a_file_keeps_its_name_and_to_save():
    assert ui_text.gearbox_update_status(_update(), _updated()) == (
        "Updated SolidWorks: changed 1 variable in Gear_m1.5_N68 (it now has 69 teeth; its file keeps its name), "
        "moved S2 and S3 in Reducer_12to1_Layout, re-placed G2, G3 and G4; no interference between the gears. Save "
        "in SolidWorks to keep it.", True)


def test_a_part_with_a_name_of_its_own_never_goes_stale():
    named = PartUpdate(_path("Pinion"), ("G2",), GearSpec(teeth="69", name="Pinion"), None, (), changed=True)
    text, _ = ui_text.gearbox_update_status(_update(parts=(named,)), _updated(placed=[]))
    assert text.startswith("Updated SolidWorks: changed 1 variable in Pinion, moved")
    module = PartUpdate(_path("Gear_m1.5_N68"), ("G2",), GearSpec(module="2", teeth="68"), None, (), changed=True)
    text, _ = ui_text.gearbox_update_status(_update(parts=(module,)), _updated(placed=[]))
    assert "Gear_m1.5_N68 (it is now module 2; its file keeps its name)" in text


def test_a_component_dragged_in_solidworks_is_put_back_and_said():
    text, ok = ui_text.gearbox_update_status(_update(parts=(), layout=None), _updated(
        parts=[], layout=None, placed=["G4"], changed=[_path("Reducer_12to1", ".SLDASM")]), dragged=["G4"])
    assert (text, ok) == ("Updated SolidWorks: G4 had been moved in SolidWorks; put back where the workbook has it; "
                          "no interference between the gears. Save in SolidWorks to keep it.", True)
    text, _ = ui_text.gearbox_update_status(_update(), _updated(), dragged=["G3", "G4"])
    assert "re-placed G2; no interference" in text and "G3 and G4 had been moved in SolidWorks; put back where the " \
                                                       "workbook has them." in text


def test_an_update_that_changed_nothing_says_so():
    nothing = _updated(parts=[swbuild.UpdateResult(document="Gear_m1.5_N68.SLDPRT", unchanged=["No. of Teeth"],
                                                   rebuilt=True)], layout=None, placed=[], changed=[])
    assert ui_text.gearbox_update_status(_update(), nothing) == (ui_text.ALREADY_MATCHES, True)
    nothing.clashes = [swbuild.Clash(("a-1", "b-1"), ("G1", "G2"), 1.0)]
    assert ui_text.gearbox_update_status(_update(), nothing) == (
        "SolidWorks already matches the workbook: nothing was changed. Check: G1 and G2 interfere, 1 mm³; look at "
        "their mesh in Reducer_12to1.SLDASM.", False)


def test_an_update_that_stops_says_what_it_had_changed_unsaved():
    stopped = _updated(failures=[("Reducer_12to1_Layout", "S2 X could not be set: the value was refused")],
                       changed=[_path("Gear_m1.5_N68")])
    assert ui_text.gearbox_update_status(_update(), stopped) == (
        "Update SolidWorks stopped. Reducer_12to1_Layout: S2 X could not be set: the value was refused. It had already "
        "changed Gear_m1.5_N68, not saved: press Update SolidWorks again once that is put right, or save it in "
        "SolidWorks to keep what it did.", False)
    stopped.changed = []
    assert ui_text.gearbox_update_status(_update(), stopped)[0].endswith("the value was refused. Nothing was changed.")


def test_an_assembly_that_will_not_rebuild_after_an_update_stands_out():
    text, ok = ui_text.gearbox_update_status(_update(), _updated(rebuilt=False))
    assert not ok and "re-placed G2, G3 and G4. SolidWorks reported an error rebuilding Reducer_12to1.SLDASM, so " \
                      "look at it before saving. Save in SolidWorks to keep it." in text


# the build-again question (decision 8)


def _again():
    return _gearbox("Reducer_12to1_r2", build=[_job("Gear_m1.5_N68_r2", ["G2"])],
                    reuse=[_reuse("Gear_m1.5_N17", ["G1"]), _reuse("Gear_m2_N17", ["G3"]),
                           _reuse("OutputGear", ["G4"])])


def test_the_build_again_question_never_promises_the_old_assembly_is_untouched():
    update = _update(structural=("G2's bore was added, which its built part cannot take through its values.",))
    assert ui_text.build_again_question(update, _again()) == (
        "G2's bore was added, which its built part cannot take through its values. Build again as Reducer_12to1_r2? "
        "That makes a new part for G2 (Gear_m1.5_N68_r2), reuses 3 parts that have not changed and makes a new "
        "layout part and assembly (Reducer_12to1_r2_Layout and Reducer_12to1_r2.SLDASM). Nothing is overwritten, and "
        "Reducer_12to1.SLDASM stays as it is on disk, but it shares the 3 reused parts: a later Update SolidWorks "
        "that changes one of them changes Reducer_12to1.SLDASM too.")


def test_the_build_again_question_for_a_missing_file_or_by_choice():
    missing = ui_text.build_again_question(_update(missing=(_path("Gear_m1.5_N68"),)), _again())
    assert missing.startswith(f"Gear_m1.5_N68.SLDPRT is no longer in {P}: it was moved or renamed since it was built, "
                              "so Update SolidWorks cannot change it. Build again as Reducer_12to1_r2? ")
    fresh = _gearbox("Reducer_12to1_r2", **FULL)
    chosen = ui_text.build_again_question(_update(), fresh)
    assert chosen.startswith("Update SolidWorks can bring SolidWorks up to date as it is, so a new revision is not "
                             "needed. Build again as Reducer_12to1_r2? That makes new parts for G1 (Gear_m1.5_N17), ")
    assert chosen.endswith("Nothing is overwritten, and Reducer_12to1.SLDASM and its files are left as they are.")
    refused = ui_text.build_again_question(_update(), _gearbox("Reducer_12to1_r2", refusal="Save Gear_m1.5_N68 first."))
    assert refused.endswith("Build again as Reducer_12to1_r2? It cannot go ahead: Save Gear_m1.5_N68 first.")


# the footer: every state


def _footer(a, **kw):
    return ui_text.workbook_footer(a, folder=P, **kw)


def test_ready_to_build_the_whole_gearbox(ready):
    f = _footer(ready, plan=_gearbox(**FULL))
    assert f == ui_text.Footer(f"Ready: Build makes 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM in {P}.",
                               True, ui_text.BUILD, "Build", True, True, False, False, False)


def test_ready_with_the_parts_already_built(ready):
    record = _record(layout=False)
    plan = _gearbox(reuse=[_reuse(s, [g]) for s, g in zip(STEMS, ("G1", "G2", "G3", "G4"))])
    f = _footer(ready, record=record, plan=plan, update=_update(parts=(), moved_shafts=(), replaced=(), layout=None,
                                                                assembly=""))
    assert f.text == (f"Ready: Build makes Reducer_12to1_Layout and Reducer_12to1.SLDASM in {P}, reusing the 4 parts "
                      "already built.")
    assert (f.build_action, f.build_enabled, f.build_primary) == (ui_text.BUILD, True, True)
    assert (f.update_shown, f.update_enabled, f.update_primary) == (True, True, False)


def test_ready_to_carry_on_after_the_assembly_failed(ready):
    plan = _gearbox(layout="reuse", reuse=[_reuse(s, [g]) for s, g in zip(STEMS, ("G1", "G2", "G3", "G4"))])
    f = _footer(ready, record=_record(assembly=False), plan=plan)
    assert f.text == (f"Ready: Build makes Reducer_12to1.SLDASM in {P}, reusing Reducer_12to1_Layout and the 4 parts "
                      "already built.")
    assert f.build_action == ui_text.BUILD and f.build_enabled and not f.update_primary


def test_ready_at_a_later_revision_says_why(ready):
    plan = _gearbox("Reducer_12to1_r2", revision=2, revision_reason="Reducer_12to1.SLDASM is already there, with no "
                                                                    "record of it", **FULL)
    assert _footer(ready, plan=plan).text.endswith(
        f"Reducer_12to1_r2.SLDASM in {P}. Reducer_12to1.SLDASM is already there, with no record of it.")


def test_a_refused_plan_holds_build_back(ready):
    f = _footer(ready, plan=_gearbox(refusal=f"{P}\\Reducer_12to1.SLDASM already exists.", **FULL))
    assert (f.text, f.ok, f.build_enabled) == (f"{P}\\Reducer_12to1.SLDASM already exists.", False, False)


def test_build_parts_while_a_later_phase_holds_the_layout_back(with_bevel):
    f = _footer(with_bevel, plan=_gearbox(layout=None, assembly=False, **FULL))
    assert f.text == (f"Ready: Build parts makes 4 parts in {P}; the layout and assembly wait for a later "
                             "phase: Gears!A6: G6 is a bevel gear: right-angle stages are built in phase W6.")
    assert (f.ok, f.build_action, f.build_label, f.build_enabled, f.build_primary) == (
        True, ui_text.BUILD_PARTS, "Build parts", True, True)
    plan = _gearbox(layout=None, assembly=False, build=[_job(STEMS[3], ["G4"])],
                    reuse=[_reuse(s, [g]) for s, g in zip(STEMS[:3], ("G1", "G2", "G3"))])
    f = _footer(with_bevel, plan=plan, record=_record(layout=False))
    assert f.text.startswith(f"Ready: Build parts makes 1 part in {P}, reusing the 3 parts already built; the layout")
    assert f.update_shown and not f.update_primary
    nothing = _gearbox(layout=None, assembly=False, reuse=plan.reuse + (_reuse(STEMS[3], ["G4"]),))
    f = _footer(with_bevel, plan=nothing, record=_record(layout=False))
    assert f.text.startswith("The 4 parts are built already, so Build parts has nothing to make; the layout and ")
    assert f.ok and not f.build_enabled


def test_built_and_changed_since_offers_update(ready):
    f = _footer(ready, record=_record(), plan=_again(), update=_update())
    assert f == ui_text.Footer(
        "Update SolidWorks will change G2's values (Gear_m1.5_N68), move S2 and S3 in Reducer_12to1_Layout, and "
        "re-place G2, G3 and G4.", True, ui_text.BUILD_AGAIN, "Build again…", True, False, True, True, True)


def test_built_and_matching_keeps_update_enabled(ready):
    f = _footer(ready, record=_record(), update=_update(parts=(), moved_shafts=(), replaced=()))
    assert f.text.startswith("SolidWorks already matches the workbook on record") and f.update_enabled


def test_a_structural_change_offers_to_build_again(ready):
    update = _update(structural=("G2's bore was added, which its built part cannot take.",))
    f = _footer(ready, record=_record(), plan=_again(), update=update)
    assert (f.text, f.ok, f.update_enabled, f.build_enabled) == (
        "G2's bore was added, which its built part cannot take: Update SolidWorks offers to build again as "
        "Reducer_12to1_r2.", True, True, True)
    blocked = _footer(ready, record=_record(), plan=dataclasses.replace(
        _again(), refusal="Gear_m1.5_N17 has changes from Update SolidWorks that are not saved: save it first."),
        update=update)
    assert blocked.text.endswith("Reducer_12to1_r2. Gear_m1.5_N17 has changes from Update SolidWorks that are not "
                                 "saved: save it first.")
    assert (blocked.ok, blocked.update_enabled, blocked.build_enabled) == (False, False, False)


def test_a_missing_file_offers_to_build_again_and_stands_out(ready):
    f = _footer(ready, record=_record(), plan=_again(), update=_update(missing=(_path("Gear_m1.5_N68"),)))
    assert f.text.endswith("offers to build again as Reducer_12to1_r2.") and not f.ok and f.update_enabled


def test_an_update_left_unsaved_is_said_until_it_is_saved(ready):
    update = _update(unsaved=(_path("Gear_m1.5_N68"), _path("Reducer_12to1_Layout")))
    f = _footer(ready, record=_record(), update=update)
    assert f.text.endswith("re-place G2, G3 and G4. Gear_m1.5_N68 and Reducer_12to1_Layout have changes from Update "
                           "SolidWorks that are not saved: save them in SolidWorks to keep them.")
    f = _footer(ready, record=_record(unsaved={_path("Gear_m1.5_N68"): 1.0}), update=None)
    assert "Gear_m1.5_N68 has changes from Update SolidWorks that are not saved: save it" in f.text


def test_a_job_running_holds_both_buttons(ready):
    step = swbuild.Step("part", "Gear_m1.5_N68", 2, 4)
    f = _footer(ready, record=_record(), update=_update(), building=True, progress=step)
    assert (f.text, f.ok, f.build_enabled, f.update_enabled, f.update_shown) == (
        "Building in SolidWorks: part 2 of 4, Gear_m1.5_N68…", True, False, False, True)
    f = _footer(ready, record=_record(), update=_update(), updating=True)
    assert f.text == "Updating SolidWorks…" and not f.update_enabled


def test_the_window_own_troubles_come_first(ready):
    gone = f"The workbook is no longer at {P}\\Reducer_12to1.xlsx."
    f = _footer(ready, record=_record(), update=_update(), error=gone)
    assert (f.text, f.ok, f.build_enabled, f.update_enabled) == (gone, False, False, False)
    f = _footer(dataclasses.replace(ready, chosen=("a fix",)), record=_record(), update=_update())
    assert f.text == ("1 fix chosen: Export writes it into the workbook, and Build and Update SolidWorks wait for "
                      "that, so the workbook and SolidWorks agree.") and not f.update_enabled
    f = _footer(dataclasses.replace(ready, provisional=True), record=_record(), update=_update())
    assert f.text == ui_text.RECALC_WAIT_UPDATE and f.ok and not (f.build_enabled or f.update_enabled)
    f = _footer(dataclasses.replace(ready, provisional=True), plan=_gearbox(**FULL))
    assert f.text == ui_text.RECALC_WAIT


def test_a_workbook_error_holds_build_and_update(ready, tmp_path):
    spec = model.replace(reducer(), gears=(reducer().gears[0], model.replace(reducer().gears[1], teeth="68.5"))
                         + reducer().gears[2:])
    read, diagnostics = model.from_book(xlsx.read(write(tmp_path, spec, "Bad.xlsx")))
    bad = assess.assess(read, diagnostics, P)
    f = _footer(bad, record=_record(), update=_update())
    assert f.text.startswith("Fix the workbook before building: Gears!F3") and not f.ok
    assert (f.build_action, f.build_enabled, f.update_shown, f.update_enabled) == (ui_text.BUILD_AGAIN, False, True,
                                                                                   False)


def test_a_missing_output_folder_holds_build_but_not_update(ready):
    f = _footer(ready, plan=_gearbox(**FULL), folder_exists=False)
    assert (f.text, f.ok, f.build_enabled) == (
        f"The output folder {P} does not exist; make it, or change it on the Box sheet.", False, False)
    f = _footer(ready, record=_record(), plan=_again(), update=_update(), folder_exists=False)
    assert f.text.startswith("Update SolidWorks will change") and f.update_enabled and not f.build_enabled
    unset = dataclasses.replace(ready, folder="")
    f = ui_text.workbook_footer(unset, record=_record(), plan=_again(), update=_update())
    assert f.update_enabled and not f.build_enabled


def test_a_newer_record_holds_build_and_update(ready, tmp_path):
    (tmp_path / "R.workbook.json").write_text('{"link_schema_version": 3}')
    with pytest.raises(store.UnknownSchema) as caught:
        store.read_link_record(str(tmp_path / "R.xlsx"))
    f = _footer(ready, record_problem=str(caught.value), plan=_gearbox(**FULL))
    assert (f.text, f.ok, f.build_enabled, f.update_shown) == (str(caught.value), False, False, False)


def test_a_broken_record_lets_build_go_ahead_and_says_so(ready, tmp_path):
    (tmp_path / "R.workbook.json").write_text("{half")
    with pytest.raises(store.StoreError) as caught:
        store.read_link_record(str(tmp_path / "R.xlsx"))
    f = _footer(ready, record_problem=str(caught.value), plan=_gearbox(**FULL))
    assert f.text.startswith("Ready: Build makes 4 parts") and f.text.endswith(
        "R.workbook.json, cannot be read: it is not JSON (Expecting property name enclosed in double quotes: line 1 "
        "column 2 (char 1)). The next Build sets it aside and starts a new one.")
    assert (f.ok, f.build_enabled) == (False, True)


def test_a_finished_jobs_sentence_stays_until_something_goes_wrong(ready, tmp_path):
    built = ("Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM. Check: G1 and G2 interfere, 1 mm³; look "
             "at their mesh in Reducer_12to1.SLDASM.", False)
    f = _footer(ready, record=_record(), plan=_again(), update=_update(parts=(), moved_shafts=(), replaced=()),
                note=built)
    assert (f.text, f.ok, f.build_enabled, f.update_enabled) == (built[0], False, True, True)
    f = _footer(ready, record=_record(), update=_update(), note=("Updated SolidWorks: … Save in SolidWorks to keep "
                                                                 "it.", True), results_due=True)
    assert f.text == "Updated SolidWorks: … Save in SolidWorks to keep it." + ui_text.RESULTS_DUE and f.ok
    f = _footer(ready, record=_record(), plan=_again(), update=_update(), note=built, folder_exists=False,
                error="")
    assert f.text.startswith(built[0])
    spec = model.replace(reducer(), gears=(reducer().gears[0], model.replace(reducer().gears[1], teeth="68.5"))
                         + reducer().gears[2:])
    read, diagnostics = model.from_book(xlsx.read(write(tmp_path, spec, "Bad.xlsx")))
    f = _footer(assess.assess(read, diagnostics, P), record=_record(), update=_update(), note=built)
    assert f.text.startswith(built[0] + " Since then: Fix the workbook before building:") and not f.update_enabled


def test_the_gear_table_says_what_is_built_and_what_update_changes(ready):
    rows = {r[0]: r for r in ui_text.workbook_gear_rows(ready.spec, ready.parts, ready.diagnostics,
                                                         record=_record(), update=_update())}
    assert rows["G1"][6:] == ("Gear_m1.5_N17", ui_text.GEAR_STATE_BUILT, "built")
    assert rows["G2"][6:] == ("Gear_m1.5_N68", ui_text.GEAR_STATE_CHANGES, "built · changes on Update")
    structural = _update(structural=("G4's bore was added, which its built part cannot take.",),
                         missing=(_path("Gear_m2_N17"),))
    rows = {r[0]: r for r in ui_text.workbook_gear_rows(ready.spec, ready.parts, ready.diagnostics,
                                                         record=_record(), update=structural)}
    assert rows["G4"][7:] == (ui_text.GEAR_STATE_NEW_PART, "needs a new part")
    assert rows["G3"][7:] == (ui_text.GEAR_STATE_NEW_PART, "needs a new part")
    assert rows["G1"][7] == ui_text.GEAR_STATE_BUILT
    plain = {r[0]: r for r in ui_text.workbook_gear_rows(ready.spec, ready.parts, ready.diagnostics)}
    assert plain["G1"][7:] == (ui_text.GEAR_STATE_BUILDS, "to build")
