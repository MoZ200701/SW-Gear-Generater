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
        "1 part built before it; Part3 was left open, unsaved; cut 'Tooth Space': FeatureCut4 would not cut. 2 parts "
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
        "Built 4 parts; Part5 was left open, unsaved; insert plane 'S2 X Plane': SolidWorks returned None. The "
        "assembly was not attempted. Press Build to carry on: the parts are reused.", False)


def test_an_assembly_that_fails_leaves_the_parts_and_layout_for_the_next_press():
    plan = _gearbox(**FULL)
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved(s) for s in STEMS]),
                                   layout=_saved("Reducer_12to1_Layout"),
                                   assembly=_failed("Assem1", "place G2", "Transform2 was not taken."))
    assert ui_text.gearbox_status(plan, result) == (
        "Built 4 parts and Reducer_12to1_Layout; the assembly Assem1 was left open, unsaved; place G2: Transform2 was "
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
        "Reused Reducer_12to1_Layout and the 4 parts already built; the assembly Assem1 was left open, unsaved;")


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
        "G2's bore was added, which its built part cannot take. Update SolidWorks offers to build again as a new "
        "revision.")
    two = _update(structural=("G2's bore was added, which its built part cannot take.", "S4 was added."))
    assert ui_text.update_summary(two).startswith("G2's bore was added, which its built part cannot take (and 1 "
                                                  "other change Update SolidWorks cannot carry). Update ")
    # swbuild.structural_change's own "build it again" is not said twice (W4 review S4.2).
    recipe = _update(structural=("Gear_m1.5_N17 (G1): The recipe changed from 'A' to 'B'; build it again as a new "
                                 "part.",))
    assert ui_text.update_summary(recipe) == (
        "Gear_m1.5_N17 (G1): The recipe changed from 'A' to 'B', so it needs a new part. Update SolidWorks offers to "
        "build again as a new revision.")
    assert ui_text.update_summary(_update(missing=(_path("Gear_m1.5_N68"),))) == (
        f"Gear_m1.5_N68.SLDPRT is no longer in {P}: it was moved, renamed or deleted since it was built, so Update "
        "SolidWorks offers to build again as a new revision.")
    both = _update(missing=(_path("Gear_m1.5_N68"), _path("Reducer_12to1_Layout")), structural=("S4 was added.",))
    assert ui_text.update_summary(both) == (
        "Gear_m1.5_N68.SLDPRT and Reducer_12to1_Layout.SLDPRT are no longer where they were built: they were moved, "
        "renamed or deleted since (and 1 other change Update SolidWorks cannot carry), so Update SolidWorks offers to build "
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
        "Gear_m1.5_N68, Reducer_12to1_Layout and Reducer_12to1 in SolidWorks to keep them.", True)


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
                          "no interference between the gears. Save Reducer_12to1 in SolidWorks to keep it.", True)
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
                      "look at it before saving. Save Gear_m1.5_N68, Reducer_12to1_Layout and Reducer_12to1 in " \
                      "SolidWorks to keep them." in text


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
    assert missing.startswith(f"Gear_m1.5_N68.SLDPRT is no longer in {P}: it was moved, renamed or deleted since it "
                              "was built, "
                              "so Update SolidWorks cannot change it. Build again as Reducer_12to1_r2? ")
    fresh = _gearbox("Reducer_12to1_r2", **FULL)
    chosen = ui_text.build_again_question(_update(), fresh)
    assert chosen.startswith("Nothing on record needs a new revision. Build again as Reducer_12to1_r2? That makes new "
                             "parts for G1 (Gear_m1.5_N17), ")
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
        "G2's bore was added, which its built part cannot take. Update SolidWorks offers to build again as "
        "Reducer_12to1_r2.", True, True, True)
    # The build it offers cannot go: neither button offers it, and the sentence says why (W4 review S4.1).
    blocked = _footer(ready, record=_record(), plan=dataclasses.replace(
        _again(), refusal="Gears!R5: G4's part would be Reducer_12to1_Layout.SLDPRT, …: give it another Part name."),
        update=update)
    assert blocked.text == ("G2's bore was added, which its built part cannot take. The new revision it needs, "
                            "Reducer_12to1_r2, cannot be built yet: Gears!R5: G4's part would be "
                            "Reducer_12to1_Layout.SLDPRT, …: give it another Part name.")
    assert "offers" not in blocked.text
    assert (blocked.ok, blocked.update_enabled, blocked.build_enabled) == (False, False, False)


def test_a_missing_file_offers_to_build_again_and_stands_out(ready):
    f = _footer(ready, record=_record(), plan=_again(), update=_update(missing=(_path("Gear_m1.5_N68"),)))
    assert f.text.endswith("offers to build again as Reducer_12to1_r2.") and not f.ok and f.update_enabled


def test_an_answer_is_followed_plainly_by_what_was_already_so(ready, tmp_path):
    """No to Build again? for a missing file: nothing happened, so *Since then* would be wrong (it read
    "Nothing was changed in SolidWorks. Since then: Gear_m1.5_N68.SLDPRT is no longer in …")."""
    missing = _update(missing=(_path("Gear_m1.5_N68"),))
    f = _footer(ready, record=_record(), plan=_again(), update=missing,
                note=ui_text.Note(ui_text.NOTHING_CHANGED, True, ui_text.NOTE_ANSWER))
    assert f.text == (f"Nothing was changed in SolidWorks. Gear_m1.5_N68.SLDPRT is no longer in {P}: it was moved, "
                      "renamed or deleted since it was built, so Update SolidWorks offers to build again as "
                      "Reducer_12to1_r2.")
    assert not f.ok
    f = _footer(ready, record=_record(), plan=_again(), update=missing,
                note=ui_text.Note(ui_text.ASKED_TOO_LATE, False, ui_text.NOTE_ANSWER))
    assert f.text.startswith(ui_text.ASKED_TOO_LATE + " Gear_m1.5_N68.SLDPRT is no longer in")
    # An Export's sentence is an answer too: an error it did not mend was there before it.
    spec = model.replace(reducer(), gears=(reducer().gears[0], model.replace(reducer().gears[1], teeth="68.5"))
                         + reducer().gears[2:])
    read, diagnostics = model.from_book(xlsx.read(write(tmp_path, spec, "Bad.xlsx")))
    bad = assess.assess(read, diagnostics, P)
    from gear_generator.workbook.export import Exported
    exported = ui_text.export_note(Exported(written=["Shafts!C3"], results=True))
    assert exported == ui_text.Note("Exported 1 cell and the Results sheet.", True, ui_text.NOTE_STANDING)
    f = _footer(bad, note=exported)
    assert f.text.startswith("Exported 1 cell and the Results sheet. Fix the workbook before building:")
    # A job's sentence keeps *Since then*: the workbook may have moved on while it ran.
    assert _footer(bad, note=("Built 4 parts.", True)).text.startswith("Built 4 parts. Since then: Fix the workbook")


def test_an_update_left_unsaved_is_said_until_it_is_saved(ready):
    update = _update(unsaved=(_path("Gear_m1.5_N68"), _path("Reducer_12to1_Layout")))
    f = _footer(ready, record=_record(), update=update)
    assert f.text.endswith("re-place G2, G3 and G4. Gear_m1.5_N68 and Reducer_12to1_Layout have changes from Update "
                           "SolidWorks that are not saved: save them in SolidWorks to keep them. If SolidWorks "
                           "closed them without saving, press Update SolidWorks to make them again.")
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
    (tmp_path / "R.workbook.json").write_text('{"link_schema_version": %d}' % (store.LINK_SCHEMA_VERSION + 1))
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


def test_the_gear_table_shows_the_part_the_build_would_make(ready):
    """Second W4 review N6: a gear whose own file name is taken is built as <stem>_r2, but the Part column showed
    its own stem (visible on the WorkbookCopy board)."""
    plan = _gearbox(part_of={"G1": _path("Gear_m1.5_N17_r2"), "G2": _path("Gear_m1.5_N68"),
                             "G3": _path("Gear_m2_N17_r3"), "G4": _path("OutputGear")})
    rows = {r[0]: r for r in ui_text.workbook_gear_rows(ready.spec, ready.parts, ready.diagnostics, plan=plan)}
    assert [rows[g][6] for g in ("G1", "G2", "G3", "G4")] == ["Gear_m1.5_N17_r2", "Gear_m1.5_N68", "Gear_m2_N17_r3",
                                                              "OutputGear"]


# -- what the Workbook window itself says around a job (the W4 window wiring) ------------------------------------


def test_the_gears_readout_counts_what_is_on_record(ready):
    assert ui_text.workbook_parts_readout(ready.parts) == "4 parts to build"
    assert ui_text.workbook_parts_readout(ready.parts, record=_record()) == "4 parts built"
    two = store.LinkRecord(parts=_record().parts[:2])
    assert ui_text.workbook_parts_readout(ready.parts, record=two) == "2 parts built · 2 to build"
    assert ui_text.workbook_parts_readout(ready.parts, record=store.LinkRecord()) == "4 parts to build"


def test_the_header_says_whether_what_is_built_is_this_version():
    assert ui_text.workbook_built_tag(None, "abc") == ""
    assert ui_text.workbook_built_tag(store.LinkRecord(digest="abc"), "abc") == ""        # nothing on record
    built = dataclasses.replace(_record(), digest="abc")
    assert ui_text.workbook_built_tag(built, "abc") == " · built from this version"
    assert ui_text.workbook_built_tag(built, "def") == " · changed since it was built"
    parts = dataclasses.replace(_record(layout=False), digest="abc")
    assert ui_text.workbook_built_tag(parts, "abc") == " · parts built from this version"
    assert ui_text.workbook_built_tag(parts, "def") == " · changed since its parts were built"


def test_a_job_that_cannot_start_says_why():
    assert ui_text.job_unreachable("pywin32 is not installed.") == (
        "SolidWorks cannot be reached from here, so nothing was built. pywin32 is not installed.")
    assert ui_text.job_unreachable("", updating=True) == "SolidWorks cannot be reached from here, so nothing was " \
                                                          "updated."
    assert ui_text.strip_busy() == "The strip is building in SolidWorks; build the workbook when it has finished."
    assert ui_text.strip_busy(True) == ("The strip is building in SolidWorks; press Update SolidWorks when it has "
                                        "finished.")
    assert ui_text.export_busy() == "a build is running in SolidWorks; export when it has finished."
    assert ui_text.export_busy(True) == "Update SolidWorks is running; export when it has finished."


def test_a_job_that_raised_is_said_as_it_came_or_named():
    refusal = swbuild.BuildError("C:\\P\\R.SLDASM already exists, and a build never overwrites a file.")
    assert ui_text.job_failed(refusal) == str(refusal)
    assert ui_text.job_failed(KeyError("x")) == "The build stopped before it made anything — KeyError: 'x'"
    assert ui_text.job_failed(ValueError("v"), updating=True) == (
        "Update SolidWorks stopped before it changed anything — ValueError: v")
    # A component renamed or deleted in SolidWorks: Update cannot put it back, and says the way on (S4.6).
    gone = swbuild.NotAsBuilt("Gear_m1.5_N68-1 is not in Reducer_12to1.SLDASM any more: it was renamed or deleted in "
                              "SolidWorks.", _path("Reducer_12to1", ".SLDASM"))
    assert ui_text.job_failed(gone, updating=True) == (
        "Gear_m1.5_N68-1 is not in Reducer_12to1.SLDASM any more: it was renamed or deleted in SolidWorks. Update "
        "SolidWorks cannot put that back; Build again… builds the next revision beside it, with an assembly of its "
        "own, and leaves this one as it is.")
    assert ui_text.collect_failed(ValueError("v")) == "The build could not be collected — ValueError: v"
    assert ui_text.planning_failed(ValueError("v")) == (
        "What to build could not be worked out — ValueError: v. Nothing is built or updated until it can be.")


def test_records_that_could_not_be_written_or_carried():
    assert ui_text.sidecar_unwritten("C:\\P\\G.gear.json", OSError("denied")) == (
        "The part's record G.gear.json could not be written beside it: denied.")
    assert ui_text.record_unwritten("C:\\P\\R.workbook.json", OSError("denied")) == (
        "The record of what was built, R.workbook.json, could not be written: denied. What SolidWorks saved stays "
        "on disk, and the next Build goes beside it rather than over it.")
    assert ui_text.record_not_carried("it was written by a newer Gear Generator") == (
        "The record of what was built stays beside the workbook's old place: it was written by a newer Gear "
        "Generator.")


def test_the_question_its_answer_and_closing_while_a_job_runs():
    assert ui_text.BUILD_AGAIN_TITLE == "Build again?" and ui_text.NOTHING_CHANGED == "Nothing was changed in " \
                                                                                      "SolidWorks."
    assert ui_text.ASKED_TOO_LATE == ("The workbook changed while the question was open, so nothing was built; press "
                                      "Build again… once more if it still applies.")     # "build again" once
    assert ui_text.closes_when_done() == ("This window closes once the build has finished and what it saved is on "
                                          "record; it stays open if something needs saying.")
    assert ui_text.closes_when_done(True).startswith("This window closes once the update has finished")


def test_a_clash_is_called_a_mesh_only_when_it_is_one():
    """W4 smoke test on SolidWorks 2026: a widened G1 clashed with G4 beside it, which it does not mesh with."""
    asm = _saved("Reducer_12to1", ".SLDASM")
    built = dict(parts=swbuild.ManyResult(built=[_saved(s) for s in STEMS]), layout=_saved("Reducer_12to1_Layout"),
                 assembly=asm)
    plan = _gearbox(**FULL, meshes=(("G1", "G2"), ("G3", "G4")))
    mesh = swbuild.Clash(("Gear_m1.5_N17-1", "Gear_m1.5_N68-1"), ("G2", "G1"), 1.0)
    beside = swbuild.Clash(("Gear_m1.5_N17-1", "OutputGear-1"), ("G1", "G4"), 2.0)
    result = swbuild.GearboxResult(clashes=[mesh], **built)
    assert ui_text.gearbox_status(plan, result)[0].endswith(
        "Check: G2 and G1 interfere, 1 mm³; look at their mesh in Reducer_12to1.SLDASM.")
    result.clashes = [beside]
    assert ui_text.gearbox_status(plan, result)[0].endswith(
        "Check: G1 and G4 interfere, 2 mm³; look where they meet in Reducer_12to1.SLDASM.")
    result.clashes = [mesh, beside]
    assert ui_text.gearbox_status(plan, result)[0].endswith(
        "Check: G2 and G1 interfere, 1 mm³; G1 and G4 interfere, 2 mm³; look where they meet in "
        "Reducer_12to1.SLDASM.")
    result.clashes = [swbuild.Clash((), (), 0.5)]               # unnamed: not known to be a mesh
    assert ui_text.gearbox_status(plan, result)[0].endswith("look where they meet in Reducer_12to1.SLDASM.")
    nothing = _updated(parts=[], layout=None, placed=[], changed=[], clashes=[beside])
    assert ui_text.gearbox_update_status(_update(), nothing, meshes=[["G1", "G2"], ["G3", "G4"]])[0].endswith(
        "look where they meet in Reducer_12to1.SLDASM.")
    nothing.clashes = [mesh]
    assert ui_text.gearbox_update_status(_update(), nothing, meshes=[["G1", "G2"], ["G3", "G4"]])[0].endswith(
        "look at their mesh in Reducer_12to1.SLDASM.")


def test_an_update_left_unsaved_never_holds_build_again(ready):
    """W4 review B2: a part Update left unsaved is made new by the next build (GearboxPlan.unsaved_made_new), so
    Build again… is never greyed for a save; the footer still asks for the save, and reads no refusal's words."""
    unsaved = {_path("Gear_m1.5_N68"): 1.0, _path("Reducer_12to1", ".SLDASM"): 1.0}
    again = _gearbox(name="Reducer_12to1_r2", revision=2)
    matches = _update(parts=(), moved_shafts=(), replaced=(), unsaved=tuple(unsaved))
    f = _footer(ready, record=_record(unsaved=unsaved), plan=again, update=matches)
    assert f.build_enabled and f.update_enabled
    assert f.text.endswith("Gear_m1.5_N68 and Reducer_12to1 have changes from Update SolidWorks that are not saved: "
                           "save them in SolidWorks to keep them. If SolidWorks closed them without saving, press "
                           "Update SolidWorks to make them again.")
    assert "waits" not in f.text
    updated = ("Updated SolidWorks: changed 1 variable in Gear_m1.5_N68; no interference between the gears. Save in "
               "SolidWorks to keep it.", True)
    f = _footer(ready, record=_record(unsaved=unsaved), plan=again, update=matches, note=updated)
    assert f.text == updated[0] and f.build_enabled
    # A refusal that happens to name an unsaved file is said as the refusal it is, not as a wait for a save.
    taken = _gearbox(name="Reducer_12to1_r2", revision=2,
                     refusal=r"This build would use both C:\P\Gear_m1.5_N68.SLDPRT and C:\Q\Gear_m1.5_N68.SLDPRT.")
    f = _footer(ready, record=_record(unsaved=unsaved), plan=taken, update=matches)
    assert not f.build_enabled and f.text.endswith(taken.refusal)


def test_build_again_greyed_always_says_why(ready):
    # Held for anything else, the reason itself follows what Update would do.
    f = _footer(ready, record=_record(), plan=_gearbox(name="Reducer_12to1_r2", revision=2), update=_update(),
                folder_exists=False)
    assert not f.build_enabled and f.update_enabled and f.text.startswith("Update SolidWorks will change")
    assert f.text.endswith("does not exist; make it, or change it on the Box sheet.")


def test_a_job_that_stopped_between_documents_says_so_and_what_it_saved():
    """W4 review B1: build_gearbox no longer raises after its pre-flight; a raise between documents is a failure on
    the result (GearboxResult.failures): the sentence says what was saved, where it stopped, what was not
    attempted, and that Build carries on."""
    from gear_generator import swbuild
    result = swbuild.GearboxResult()
    result.parts.built = [swbuild.BuildResult(saved=r"C:\P\A.SLDPRT", rebuilt=True),
                          swbuild.BuildResult(saved=r"C:\P\B.SLDPRT", rebuilt=True)]
    result.failures = [("the layout part", "SolidWorks did not complete SaveAs3: The remote procedure call failed "
                                           "(RPC_S_CALL_FAILED).")]
    text, ok = ui_text.gearbox_status(_gearbox(), result)
    assert not ok and text == ("Built 2 parts. The job stopped during the layout part: SolidWorks did not complete "
                               "SaveAs3: The remote procedure call failed (RPC_S_CALL_FAILED). The assembly was not "
                               "attempted. Press Build to carry on: what was built is reused.")
    result.failures = [("the parts", "it stopped on an unexpected KeyError: 'x'.")]
    assert ui_text.gearbox_status(_gearbox(), result)[0] == (
        "Built 2 parts. The job stopped during the parts: it stopped on an unexpected KeyError: 'x'. The layout part "
        "and the assembly were not attempted. Press Build to carry on: what was built is reused.")
    result.parts.built = []
    assert ui_text.gearbox_status(_gearbox(), result) == (
        "Nothing was saved. The job stopped during the parts: it stopped on an unexpected KeyError: 'x'. The layout "
        "part and the assembly were not attempted. Press Build to try again.", False)


# -- W4 review, pass 2: every sentence true, the save asked once, a greyed button always with its reason -----------


def _made(gears, old, new, why, workbook=""):
    from gear_generator.workbook.gearbox import MadeNew
    return MadeNew(tuple(gears), _path(old), _path(new), why, workbook)


UNSAVED_DOCS = {_path("Gear_m1.5_N68"): 1.0, _path("Reducer_12to1_Layout"): 1.0, _path("Reducer_12to1", ".SLDASM"): 1.0}


def test_structural_and_unsaved_asks_for_the_save_once_and_says_which_part_is_made_new(ready):
    """W4 review S4.1 and the demonstration's log: the save was asked twice, Update offered while greyed, "build
    again" three times, and only one of three unsaved documents named."""
    from gear_generator.workbook.gearbox import UNSAVED
    again = dataclasses.replace(_again(), revision=2, made_new=(_made(["G2"], "Gear_m1.5_N68", "Gear_m1.5_N69",
                                                                       UNSAVED),))
    update = _update(structural=("Gear_m1.5_N17 (G1): A bore cannot be added to or removed from a built part through "
                                 "its values; build it again as a new part.",), unsaved=tuple(UNSAVED_DOCS))
    f = _footer(ready, record=_record(unsaved=UNSAVED_DOCS), plan=again, update=update)
    assert f.text == (
        "Gear_m1.5_N17 (G1): A bore cannot be added to or removed from a built part through its values, so it needs a "
        "new part. Update SolidWorks offers to build again as Reducer_12to1_r2. Gear_m1.5_N68, Reducer_12to1_Layout "
        "and Reducer_12to1 have changes from Update SolidWorks that are not saved: save them in SolidWorks to keep "
        "them. If SolidWorks closed them without saving, those changes are gone. While Gear_m1.5_N68's changes are "
        "not saved, the new revision makes G2's part new, as Gear_m1.5_N69, rather than reuse it.")
    assert (f.ok, f.build_enabled, f.update_enabled) == (True, True, True)
    assert f.text.count("save them") == 1 and all(s.lower().count("build again") <= 1 for s in f.text.split(". "))
    question = ui_text.build_again_question(update, again)
    assert ("G2's part is new because Gear_m1.5_N68 has changes from Update SolidWorks that are not saved; to reuse "
            "it instead, answer No and save it in SolidWorks first (if SolidWorks has closed it since without saving, "
            "those changes are gone, and it cannot be reused).") in question


def test_one_document_left_unsaved_is_it_throughout(ready):
    f = _footer(ready, record=_record(unsaved={_path("Gear_m1.5_N68"): 1.0}), update=None)
    assert f.text.endswith("Gear_m1.5_N68 has changes from Update SolidWorks that are not saved: save it in "
                           "SolidWorks to keep it. If SolidWorks closed it without saving, those changes are gone.")
    assert ui_text.save_to_keep([_path("Gear_m1.5_N68")]) == "Save Gear_m1.5_N68 in SolidWorks to keep it."


def test_parts_from_build_parts_never_offer_a_build_again_of_an_assembly_never_built(ready):
    """W4 review S4.4 (w4r_partsonly): Update was enabled and asked "Build again as …?", claiming an earlier
    assembly, while the primary Build did the same without asking."""
    update = _update(structural=("G5 is new, and Update SolidWorks cannot add a part to what was built.",),
                     layout=None, assembly="")
    f = _footer(ready, record=_record(layout=False), plan=_gearbox(**FULL), update=update)
    assert (f.build_action, f.build_enabled, f.update_shown, f.update_enabled) == (ui_text.BUILD, True, True, False)
    assert f.text.endswith("G5 is new, and Update SolidWorks cannot add a part to what was built. Update SolidWorks "
                           "waits until Build has made what that needs.")
    question = ui_text.build_again_question(update, _gearbox(**FULL))
    assert "stays as it is on disk" not in question and question.endswith(
        "Nothing is overwritten, and what is already built is left as it is.")


def test_update_greyed_after_a_stopped_build_says_why_even_under_the_jobs_sentence(ready):
    """W4 review S4.5: after a build whose assembly failed, Update showed greyed with no reason."""
    waits = ("Reducer_12to1_Layout.SLDPRT was saved but its assembly was not made: Build carries on with it, and "
             "Update SolidWorks waits until it has.")
    plan = _gearbox(layout="reuse", reuse=[_reuse(s, [g]) for s, g in zip(STEMS, ("G1", "G2", "G3", "G4"))])
    f = _footer(ready, record=_record(assembly=False), plan=plan, update=UpdatePlan(refusal=waits))
    assert f.update_shown and not f.update_enabled and f.text.endswith(" " + waits)
    note = ui_text.Note("Built 4 parts and Reducer_12to1_Layout; the assembly Assem1 was left open, unsaved; place "
                        "G2: Transform2 was not taken. Press Build to try the assembly again: the parts and layout are "
                        "reused.", False)
    f = _footer(ready, record=_record(assembly=False), plan=plan, update=UpdatePlan(refusal=waits), note=note)
    assert f.text == f"{note.text} {waits}"


def test_a_file_in_the_way_of_a_part_says_whose_it_is_once_per_reason(ready):
    from gear_generator.workbook.gearbox import NO_RECORD, OTHER_WORKBOOK, STALE
    plan = dataclasses.replace(_gearbox(**FULL), made_new=(
        _made(["G1"], "Gear_m1.5_N17", "Gear_m1.5_N17_r2", NO_RECORD),
        _made(["G4"], "OutputGear", "OutputGear_r2", OTHER_WORKBOOK, "C:\\Other\\Box.xlsx"),
        _made(["G2", "G5"], "Gear_m1.5_N68", "Gear_m1.5_N68_r2", STALE)))
    assert _footer(ready, plan=plan).text == (
        f"Ready: Build makes 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM in {P}. Gear_m1.5_N17.SLDPRT is "
        "already there, with no record that this workbook built it (a build that was interrupted can leave such a "
        "file), so G1's part is made as Gear_m1.5_N17_r2. OutputGear.SLDPRT is already there, built from Box.xlsx, so "
        "G4's part is made as OutputGear_r2. Gear_m1.5_N68.SLDPRT is already there, built from this workbook for "
        "values G2 and G5 no longer have, so the part for G2 and G5 is made as Gear_m1.5_N68_r2; nothing is "
        "overwritten.")
    # The part a change Update cannot carry replaces is not said again: that change's sentence says it.
    again = dataclasses.replace(_again(), made_new=(_made(["G2"], "Gear_m1.5_N68", "Gear_m1.5_N68_r2", STALE),))
    update = _update(structural=("G2's bore was added, which its built part cannot take.",))
    assert _footer(ready, record=_record(), plan=again, update=update).text == (
        "G2's bore was added, which its built part cannot take. Update SolidWorks offers to build again as "
        "Reducer_12to1_r2.")


def test_a_copied_workbook_is_said_once_in_green_with_build_going_ahead(ready):
    from gear_generator.workbook.gearbox import OTHER_WORKBOOK
    original = "C:\\Work\\Reducer_12to1.xlsx"
    plan = dataclasses.replace(
        _gearbox("Reducer_12to1_r2", revision=2, revision_reason="Reducer_12to1_Layout.SLDPRT is already in C:\\P, and "
                 "a build never overwrites a file. So this build is Reducer_12to1_r2, beside it; nothing is "
                 "overwritten.", **FULL),
        foreign_record=original,
        made_new=(_made(["G1"], "Gear_m1.5_N17", "Gear_m1.5_N17_r2", OTHER_WORKBOOK, original),))
    f = _footer(ready, plan=plan)
    assert (f.ok, f.build_enabled, f.update_shown) == (True, True, False)
    assert f.text == (f"Ready: Build makes 4 parts, Reducer_12to1_r2_Layout and Reducer_12to1_r2.SLDASM in {P}. This "
                      f"workbook is a copy of {original}, which is still there, so the record that came with it is "
                      "that workbook's, and so are the SolidWorks files it lists: Build makes this workbook's own "
                      "gearbox beside them, sharing and overwriting nothing.")


def test_a_part_that_failed_the_live_check_is_said_and_the_next_press_makes_it_new(ready):
    """W4 review B2's last corner: the reuse check refused on every press ("68 there and 69 here")."""
    from gear_generator.workbook.gearbox import MISMATCHED
    why = ('Gear_m1.5_N68.SLDPRT does not hold what the workbook asks of it, so it cannot be reused: "No. of Teeth" '
           "is 68 there and 69 here.")
    plan = _gearbox("Reducer_12to1_r2", build=[_job("Gear_m1.5_N17_r2", ["G1"])],
                    reuse=[_reuse("Gear_m1.5_N68", ["G2"]), _reuse("Gear_m2_N17", ["G3"])])
    result = swbuild.GearboxResult(mismatched=[(_path("Gear_m1.5_N68"), why)])
    assert ui_text.gearbox_status(plan, result, again=True) == (
        f"Nothing was built. {why} The next press of Build again… makes G2's part new rather than reuse "
        "Gear_m1.5_N68; nothing is overwritten.", False)
    assert ui_text.gearbox_status(plan, result)[0].endswith("The next press of Build makes G2's part new rather "
                                                            "than reuse Gear_m1.5_N68; nothing is overwritten.")
    again = dataclasses.replace(_again(), made_new=(_made(["G2"], "Gear_m1.5_N68", "Gear_m1.5_N69", MISMATCHED),))
    f = _footer(ready, record=_record(), plan=again, update=_update(structural=("G1's bore was cleared.",)))
    assert f.text.endswith("Update SolidWorks offers to build again as Reducer_12to1_r2. Gear_m1.5_N68 does not hold "
                           "what the record says, as the last job in SolidWorks found, so the new revision makes G2's "
                           "part new, as Gear_m1.5_N69, rather than reuse it.")
    assert "G2's part is new because Gear_m1.5_N68 does not hold what the record says, as the last job in SolidWorks " \
           "found." \
        in ui_text.build_again_question(_update(structural=("G1's bore was cleared.",)), again)


def test_a_document_never_made_asks_for_the_template_first():
    """W4 review S4.3: "…the assembly was not made. new assembly: There is no assembly template at …", and "Press
    Build to try the assembly again" while the same press must fail the same way."""
    asm = swbuild.BuildResult(failures=[("new assembly", "There is no assembly template at C:\\T\\No.asmdot.")],
                              stopped_at="new assembly")
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved(s) for s in STEMS]),
                                   layout=_saved("Reducer_12to1_Layout"), assembly=asm)
    assert ui_text.gearbox_status(_gearbox(**FULL), result) == (
        "Built 4 parts and Reducer_12to1_Layout; SolidWorks did not make the assembly. There is no assembly template "
        "at C:\\T\\No.asmdot. Set an assembly template SolidWorks can use (the Box sheet's Assembly template, else "
        "the strip's), then press Build: the parts and layout are reused.", False)
    part = swbuild.BuildResult(path=_path(STEMS[0]), failures=[("new part", "There is no part template at "
                                                                             "C:\\T\\No.prtdot.")],
                               stopped_at="new part")
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[part], skipped=[_path(s) for s in STEMS[1:]]))
    assert ui_text.gearbox_status(_gearbox(**FULL), result) == (
        "SolidWorks did not make Gear_m1.5_N17. There is no part template at C:\\T\\No.prtdot. 3 parts not attempted, "
        "nor the layout and assembly. Set a part template SolidWorks can use (the Box sheet's Part template, else the "
        "strip's), then press Build.", False)


def test_a_build_again_that_stopped_before_its_layout_names_build_again():
    plan = _gearbox("Reducer_12to1_r2", build=[_job("Gear_m1.5_N68_r2", ["G2"])], reuse=[_reuse(STEMS[0], ["G1"])])
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_failed("Part3")]))
    assert ui_text.gearbox_status(plan, result, again=True)[0].endswith(
        "The layout and assembly were not attempted. Press Build again… to carry on: what was built is reused.")
    result = swbuild.GearboxResult(parts=swbuild.ManyResult(built=[_saved("Gear_m1.5_N68_r2")]),
                                   layout=_saved("Reducer_12to1_r2_Layout"), assembly=_failed("Assem1"))
    assert "Press Build to try the assembly again" in ui_text.gearbox_status(plan, result, again=True)[0]


def test_the_header_never_says_built_from_this_version_while_an_update_is_unsaved():
    """W4 review S4.7: " · built from this version" right after an Update whose changes were not saved."""
    built = dataclasses.replace(_record(unsaved={_path("Gear_m1.5_N68"): 1.0}), digest="abc")
    assert ui_text.workbook_built_tag(built, "abc") == " · updated from this version, not yet saved"
    assert ui_text.workbook_built_tag(built, "def") == " · changed since it was built"
    parts = dataclasses.replace(_record(layout=False, unsaved={_path("Gear_m1.5_N68"): 1.0}), digest="abc")
    assert ui_text.workbook_built_tag(parts, "abc") == " · parts updated from this version, not yet saved"


def test_an_answer_keeps_the_reason_it_answered(ready):
    """W4 review nit: after No the footer showed only "Nothing was changed in SolidWorks.", and the structural
    reason was gone until the next save."""
    update = _update(structural=("G2's bore was added, which its built part cannot take.",))
    no = ui_text.Note(ui_text.NOTHING_CHANGED, True, ui_text.NOTE_ANSWER)
    f = _footer(ready, record=_record(), plan=_again(), update=update, note=no)
    assert (f.text, f.ok, f.build_enabled, f.update_enabled) == (
        "Nothing was changed in SolidWorks. G2's bore was added, which its built part cannot take. Update SolidWorks "
        "offers to build again as Reducer_12to1_r2.", True, True, True)
    # A plain (text, ok) pair is a job's sentence, as the demonstration script's desk passes it.
    f = _footer(ready, record=_record(), plan=_again(), update=update, note=("Built 4 parts.", True))
    assert f.text == "Built 4 parts."


def test_what_the_window_says_when_the_app_closes_mid_job_or_a_finish_raises():
    assert ui_text.app_closes_when_done(1) == (
        "Gear Generator closes once a workbook's job in SolidWorks has finished and what it did is on record; it "
        "stays open if a Workbook window has something to say.")
    assert ui_text.app_closes_when_done(2).startswith("Gear Generator closes once 2 workbooks' jobs in SolidWorks have "
                                                      "finished and what they did")
    assert ui_text.APP_STAYED_OPEN == ("Gear Generator stayed open: a workbook's job has something to say in its "
                                       "window. Close this window again to quit.")
    assert ui_text.finish_failed(RuntimeError("boom")) == (
        "What the build saved could not all be put on record — RuntimeError: boom. What SolidWorks saved stays on "
        "disk, and the next Build goes beside it rather than over it.")
    assert ui_text.finish_failed(RuntimeError("boom"), journaled=True) == (
        "What the build saved could not all be put on record — RuntimeError: boom. What SolidWorks saved stays on "
        "disk, and the next Build finds it from the journal written before the build, checks it in SolidWorks and "
        "reuses what it can.")
    assert ui_text.finish_failed(RuntimeError("boom"), updating=True) == (
        "What the update changed could not all be put on record — RuntimeError: boom. Its changes are in SolidWorks, "
        "not saved: save them there to keep them.")


# -- the second W4 review: the save asked only where it can happen (N2), the answer keeps the state's lines (N6) ----


def test_an_earlier_revisions_unsaved_documents_are_never_nagged_about(ready):
    """Second review N2 (w4v_after_build_again_unsaved): after Build again… made the next revision, the header for
    _r2 read "updated from this version, not yet saved" because revision 0's documents were still marked, for ever
    if they were abandoned. Only the current revision's documents count, in the header and the footer."""
    record = _record(unsaved=UNSAVED_DOCS)
    record.digest = "d"
    assert ui_text.workbook_built_tag(record, "d") == " · updated from this version, not yet saved"
    record.earlier = [store.EarlierRevision(revision=0, name="Reducer_12to1", layout=_path("Reducer_12to1_Layout"),
                                            assembly=_path("Reducer_12to1", ".SLDASM"),
                                            parts=[_path("Gear_m1.5_N68")])]
    r2 = [_path(s) for s in ("Gear_m1.5_N17", "Gear_m1.5_N69", "Gear_m2_N17", "OutputGear")]
    record.parts = [store.PartEntry(path=p, gears=[g]) for p, g in zip(r2, ("G1", "G2", "G3", "G4"))]
    record.gearbox = store.GearboxRecord(
        revision=2, name="Reducer_12to1_r2", layout=_path("Reducer_12to1_r2_Layout"),
        assembly=_path("Reducer_12to1_r2", ".SLDASM"),
        components=[store.ComponentEntry(gear=g, part=p, name="x-1") for p, g in zip(r2, ("G1", "G2", "G3", "G4"))])
    assert record.current_marks(record.unsaved) == []
    assert ui_text.workbook_built_tag(record, "d") == " · built from this version"
    f = _footer(ready, record=record, update=None)
    assert "not saved" not in f.text and "save" not in f.text


def test_a_document_found_not_holding_what_the_record_says_is_not_called_built_from_this_version():
    record = _record()
    record.digest = "d"
    record.mismatched = {_path("Gear_m1.5_N68"): 1.0}
    assert ui_text.workbook_built_tag(record, "d") == " · SolidWorks no longer holds all of this version"
    assert ui_text.workbook_built_tag(record, "e") == " · changed since it was built"
    record.mismatched = {_path("Gear_m1.5_N68_old"): 1.0}               # an earlier revision's: not counted
    assert ui_text.workbook_built_tag(record, "d") == " · built from this version"


def test_after_no_to_build_again_the_unsaved_and_made_new_lines_stay_with_the_reason(ready):
    """The leftover nit: after "No" the reason was kept, but the save asked for and the part made new were dropped."""
    from gear_generator.workbook.gearbox import UNSAVED
    again = dataclasses.replace(_again(), revision=2, made_new=(_made(["G2"], "Gear_m1.5_N68", "Gear_m1.5_N69",
                                                                       UNSAVED),))
    update = _update(structural=("G1's bore was cleared.",), unsaved=tuple(UNSAVED_DOCS))
    plain = _footer(ready, record=_record(unsaved=UNSAVED_DOCS), plan=again, update=update).text
    answered = _footer(ready, record=_record(unsaved=UNSAVED_DOCS), plan=again, update=update,
                       note=ui_text.Note(ui_text.NOTHING_CHANGED, True, ui_text.NOTE_ANSWER)).text
    assert answered == f"{ui_text.NOTHING_CHANGED} {plain}"
    assert "have changes from Update SolidWorks that are not saved" in answered
    assert "the new revision makes G2's part new, as Gear_m1.5_N69" in answered


def test_the_save_is_never_asked_as_if_it_were_certain_to_be_possible(ready):
    """Second review N2: the footer asked for a save of documents SolidWorks had closed. Nothing on the Tk thread can
    know whether they are open, so the sentence is true either way and says what to press."""
    f = _footer(ready, record=_record(unsaved=UNSAVED_DOCS), plan=_again(), update=_update(unsaved=tuple(UNSAVED_DOCS)))
    assert f.update_enabled and f.text.endswith(
        "save them in SolidWorks to keep them. If SolidWorks closed them without saving, press Update SolidWorks to "
        "make them again.")


# -- the third W4 review: sentences true in every state they appear in ------------------------------------------


def test_the_strips_close_sentence_says_only_what_is_true_for_the_strip():
    """The strip does not stay open to show what its job said (CloseGuard.check quits once it is collected), and its
    job may be an update of a part's values, not a build with saved files."""
    alone = ui_text.app_closes_when_done(0, strip=True)
    assert alone == ("Gear Generator closes once the strip's job in SolidWorks has finished and the strip has "
                     "collected it.")
    both = ui_text.app_closes_when_done(1, strip=True)
    assert both == ("Gear Generator closes once a workbook's job in SolidWorks has finished and what it did is on "
                    "record, and once the strip's job in SolidWorks has finished and the strip has collected it; it "
                    "stays open if a Workbook window has something to say.")
    assert "build" not in alone and "saved" not in alone


def test_the_escape_questions_say_nothing_the_job_does_reaches_the_record_and_promise_only_a_written_journal():
    for question in (ui_text.quit_anyway_question(), ui_text.quit_anyway_question(True),
                     ui_text.close_anyway_question(), ui_text.close_anyway_question(journaled=True),
                     ui_text.close_anyway_question(updating=True)):
        assert "from now" not in question and "nothing will be overwritten" in question
    assert "Nothing that job saves or changes is put on record by this session" in ui_text.quit_anyway_question()
    built = ui_text.close_anyway_question(journaled=True)
    assert "Nothing the build saves is put on record by this window" in built
    assert built.endswith("the build listed what it is about to make in the record before it began, so the next "
                          "Build finds those files, checks them in SolidWorks and reuses what it can.")
    unjournaled = ui_text.close_anyway_question(journaled=False)
    assert "finds" not in unjournaled and unjournaled.endswith(
        "what the build was about to make could not be listed in the record before it began, so the next Build goes "
        "beside the files it saves rather than over them.")
    update = ui_text.close_anyway_question(updating=True)
    assert "Nothing the update changes is put on record by this window" in update and "journal" not in update
    assert "Build finds" not in update
    # The quit question's promise is worded to hold even when a workbook's journal could not be written.
    assert "unless the record cannot be written" in ui_text.quit_anyway_question(True)


def test_a_finish_that_raises_after_an_update_that_changed_nothing_never_says_its_changes_are_in_solidworks():
    nothing = ui_text.finish_failed(RuntimeError("boom"), updating=True, changed=False)
    assert nothing == ("What the update found could not all be put on record — RuntimeError: boom. It changed "
                       "nothing in SolidWorks.")
    assert "Its changes are in SolidWorks" in ui_text.finish_failed(RuntimeError("boom"), updating=True)


def test_the_moved_question_names_a_drive_not_connected_and_says_no_holds_only_until_the_copy_builds():
    q = ui_text.moved_question("C:\\Copy\\R.xlsx", "Z:\\Work\\R.xlsx")
    assert "a drive that is not connected now, answer No: nothing is shared or overwritten." in q
    assert "the answer is kept in the record. No:" in q
    assert "until it has, you are asked again the next time Gear Generator opens this workbook" in q


def test_a_copy_by_answer_whose_original_is_gone_is_never_said_to_be_still_there(ready):
    """Third review item 4 (w4x_copy_of_gone_sentence): after No, with the original gone, the footer and Update's
    refusal both said the original "is still there"."""
    plan = dataclasses.replace(_again(), revision=0, foreign_record="C:\\Work\\Reducer_12to1.xlsx",
                               foreign_said=True)
    sentence = ui_text._copy_sentence(plan)
    assert "still there" not in sentence
    assert sentence.startswith("The record that came with this workbook was written for C:\\Work\\Reducer_12to1.xlsx, "
                               "which you said this workbook is a copy of,")
    assert sentence.endswith("If this workbook was in fact moved or renamed from it, quit Gear Generator and open "
                             "this workbook again before you build, and you are asked again.")
    refusal = store.foreign_record_sentence("C:\\Copy\\Reducer_12to1.xlsx", "C:\\Work\\Reducer_12to1.xlsx",
                                            said=True)
    assert "still there" not in refusal and "which you said this workbook is a copy of" in refusal


def test_a_job_a_closed_window_left_running_holds_build_and_update_with_a_sentence():
    assert ui_text.unowned_job_busy() == (
        "A job from a Workbook window that was closed while SolidWorks had not answered is still running in "
        "SolidWorks; build when it has finished.")
    assert ui_text.unowned_job_busy(True).endswith("press Update SolidWorks when it has finished.")


def test_a_built_gear_the_next_build_makes_new_is_never_shown_as_simply_built(ready):
    """The W4 rerun on SolidWorks 2026, window state 06: the Gears table said G2 was "built" while the footer said
    the new revision makes G2's part new (its Update not saved)."""
    from gear_generator.workbook.gearbox import MISMATCHED, UNSAVED
    record = _record()
    for why in (UNSAVED, MISMATCHED):
        plan = dataclasses.replace(_again(), made_new=(_made(["G2"], "Gear_m1.5_N68", "Gear_m1.5_N69", why),))
        rows = {r[0]: (r[7], r[8]) for r in ui_text.workbook_gear_rows(ready.spec, ready.parts, [], record=record,
                                                                       plan=plan)}
        assert rows["G2"] == (ui_text.GEAR_STATE_CHANGES, "built · new part on Build")
        assert rows["G1"] == (ui_text.GEAR_STATE_BUILT, "built")


# -- W5: the gearbox that turns (W5-PLAN §1.8 as W5-DECISIONS and W5-INTERFACES amend it) ---------------------------
#
# Plans and results are built by hand from the pinned dataclasses, as W4's were: nothing here runs package A's or
# B's bodies. Every sentence is checked whole, and for what must never be in one.

import re  # noqa: E402

from gear_generator.workbook.motion import MatePlan, MotionPlan  # noqa: E402

REFUSED_LAYOUT = ("Reducer_12to1_Layout.SLDPRT was saved but its assembly was not made: Build carries on with it, "
                  "and Update SolidWorks waits until it has.")
LOCK_PROBLEM = "The mate G3 locked to G2 over-defines the assembly."
FLAG_PROBLEM = "SolidWorks answered 3 when making the mate G1 meshes G2."
TURN_PROBLEM = "G2 cannot turn: SolidWorks reads it fully defined."
STATIC_REASON = "how gears are mated to turn is not settled for this version (findings.MOTION_ROUTE)."


def _clean(text):
    """No sentence says "None", leaves an empty pair of quotes, a doubled space or a dangling comma."""
    assert "None" not in text and "''" not in text and '""' not in text and "  " not in text, text
    assert not re.search(r",\s*[.;:)]|,\s*$|\s[.,;]|\(\s*\)|\.\.(?!\.)", text), text
    return text


def _axis(gear, shaft, z=0.0):
    along = MatePlan(f"{gear} along {shaft}", "along", (gear,), shaft, face_global=f"{gear} Face Z" if z else "",
                     z_front=z)
    return (MatePlan(f"{gear} on {shaft} Axis", "axis", (gear,), shaft), along)


def _motion(trains=(("S1", "S2", "S3"),), drag=("G1",), fixed=(), extra_shafts=None, locks=(("G2", "G3"),),
            meshes=(("G1", "G2", 17, 68), ("G3", "G4", 17, 51))):
    """The 12 : 1's turning plan (anchors G1, G2, G4; G3 locked to G2), or a variant."""
    anchors = {"S1": "G1", "S2": "G2", "S3": "G4"}
    anchors.update(extra_shafts or {})
    mates = []
    for shaft, gear in anchors.items():
        mates.extend(_axis(gear, shaft, 17.0 if gear == "G4" else 0.0))
    mates.extend(MatePlan(f"{f} locked to {a}", "lock", (a, f)) for a, f in locks)
    mates.extend(MatePlan(f"{a} meshes {b}", "mesh", (a, b), ratio=(za, zb)) for a, b, za, zb in meshes)
    return MotionPlan(anchors=anchors, mates=tuple(mates), fixed=tuple(fixed), trains=tuple(trains), drag=tuple(drag))


def _turning(**kw):
    return _gearbox(motion=_motion(**kw), **FULL)


def _built(kind="motion", **values):
    fields = dict(parts=swbuild.ManyResult(built=[_saved(s) for s in STEMS]), layout=_saved("Reducer_12to1_Layout"),
                  assembly=_saved("Reducer_12to1", ".SLDASM"), kind=kind)
    fields.update(values)
    return swbuild.GearboxResult(**fields)


def _refused(*problems, document="Assem1", **values):
    assembly = swbuild.BuildResult(document=document, failures=[("the mate check", p) for p in problems],
                                   mate_problems=list(problems))
    return _built(kind="", assembly=assembly, **values)


# before Build


def test_drag_phrase_for_one_two_and_three_trains():
    assert ui_text.drag_phrase(()) == ""
    assert ui_text.drag_phrase(("G1",)) == "drag G1 in SolidWorks and the rest of its train follow"
    assert ui_text.drag_phrase(("G1", "G5")) == "drag G1 in SolidWorks to turn one train and G5 to turn the other"
    assert ui_text.drag_phrase(("G1", "G5", "G9")) == "drag G1, G5 and G9 in SolidWorks, one for each train"
    assert ui_text.drag_phrase(("G1", "", "G5")) == ui_text.drag_phrase(("G1", "G5"))


def test_before_build_a_turning_gearbox_says_its_gears_turn_together():
    plan = _turning()
    assert _clean(ui_text.motion_ready_line(plan)) == (
        "Its gears are mated to their shafts and to each other, so they turn together in SolidWorks.")


def test_the_ready_line_says_it_right_after_naming_the_assembly(ready):
    f = _footer(ready, plan=_turning())
    assert (_clean(f.text), f.ok, f.build_enabled) == (
        f"Ready: Build makes 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM in {P}. Its gears are mated to "
        "their shafts and to each other, so they turn together in SolidWorks.", True, True)
    later = dataclasses.replace(_turning(), name="Reducer_12to1_r2", revision=2,
                                assembly_path=_path("Reducer_12to1_r2", ".SLDASM"),
                                revision_reason="Reducer_12to1.SLDASM is already there, with no record of it")
    assert _footer(ready, plan=later).text.endswith(
        "Reducer_12to1_r2.SLDASM in C:\\Parts\\Reducer_12to1. Its gears are mated to their shafts and to each other, "
        "so they turn together in SolidWorks. Reducer_12to1.SLDASM is already there, with no record of it.")


def test_before_build_gears_that_turn_alone_or_stay_fixed_are_said():
    """Review M11: the sentence is true in every state, so a lone shaft's gears and fixed ones are named."""
    lone = _turning(extra_shafts={"S4": "G7"}, locks=(("G2", "G3"), ("G7", "G8")))
    assert _clean(ui_text.motion_ready_line(lone)) == (
        "Its gears are mated to their shafts and, where they mesh, to each other, so those that mesh turn together "
        "in SolidWorks. G7 and G8 turn apart from the train: they mesh no other gear.")
    one = _turning(extra_shafts={"S4": "G7"})
    assert ui_text.motion_ready_line(one).endswith(" G7 turns apart from the train: it meshes no other gear.")
    assert _clean(ui_text.motion_ready_line(_turning(fixed=("G9",)))) == (
        "Its turning gears are mated to their shafts and to each other, so they turn together in SolidWorks. G9 "
        "stays fixed where it is placed: its shaft does not turn.")
    assert ui_text.motion_ready_line(_turning(fixed=("G9", "G10", "G11"))).endswith(
        " G9, G10 and G11 stay fixed where they are placed: their shafts do not turn.")


def test_before_build_two_trains_each_turn_together():
    two = _turning(trains=(("S1", "S2"), ("S3",)), drag=("G1", "G4"))
    assert _clean(ui_text.motion_ready_line(two)) == (
        "Its gears are mated to their shafts and to each other, so each train turns together in SolidWorks.")
    lone = _turning(trains=(("S1", "S2"), ("S3",)), drag=("G1", "G4"), extra_shafts={"S4": "G7"}, fixed=("G9",))
    assert _clean(ui_text.motion_ready_line(lone)) == (
        "Its turning gears are mated to their shafts and, where they mesh, to each other, so each train turns "
        "together in SolidWorks. G7 turns apart from the trains: it meshes no other gear. G9 stays fixed where it is "
        "placed: its shaft does not turn.")


def test_before_build_with_no_mesh_each_gear_is_mated_to_its_shaft():
    plan = _turning(trains=(), drag=(), meshes=())
    assert _clean(ui_text.motion_ready_line(plan)) == (
        "Its gears are each mated to their shaft, free to turn in SolidWorks.")
    fixed = _turning(trains=(), drag=(), meshes=(), fixed=("G9",))
    assert _clean(ui_text.motion_ready_line(fixed)) == (
        "Its turning gears are each mated to their shaft, free to turn in SolidWorks. G9 stays fixed where it is "
        "placed: its shaft does not turn.")


def test_before_build_a_missing_finding_says_the_assembly_will_be_static_and_why(ready):
    """Ruling (a) on 2f82a0e: the static build stays when a W5 finding is missing, and is said before Build."""
    plan = _gearbox(static_reason=STATIC_REASON, **FULL)
    assert _clean(ui_text.motion_ready_line(plan)) == (
        "Its gears are placed meshed and fixed, not mated to turn: how gears are mated to turn is not settled for "
        "this version (findings.MOTION_ROUTE).")
    assert _footer(ready, plan=plan).text == (
        f"Ready: Build makes 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM in {P}. Its gears are placed "
        "meshed and fixed, not mated to turn: how gears are mated to turn is not settled for this version "
        "(findings.MOTION_ROUTE).")


def test_nothing_new_is_said_for_parts_only_refused_or_w4_static_plans():
    assert ui_text.motion_ready_line(None) == ""
    assert ui_text.motion_ready_line(_gearbox(layout=None, assembly=False, motion=_motion(), **FULL)) == ""
    assert ui_text.motion_ready_line(_gearbox(refusal="No.", motion=_motion(), **FULL)) == ""
    assert ui_text.motion_ready_line(_gearbox(**FULL)) == ""


# after Build


def test_after_build_one_train_says_drag_and_the_rest_of_its_train_follow():
    assert ui_text.gearbox_status(_turning(), _built()) == (
        "Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM; no interference between the gears where they "
        "stand. Its gears are mated to turn together, and SolidWorks reports no mate in error: drag G1 in SolidWorks "
        "and the rest of its train follow.", True)


def test_after_build_two_and_three_trains_name_a_gear_for_each():
    two = _turning(trains=(("S1", "S2"), ("S3", "S4")), drag=("G1", "G5"))
    assert _clean(ui_text.motion_done_line(two, _built())) == (
        "Its gears are mated to turn in 2 trains, and SolidWorks reports no mate in error: drag G1 in SolidWorks to "
        "turn one train and G5 to turn the other.")
    three = _turning(trains=(("S1",), ("S2",), ("S3",)), drag=("G1", "G5", "G9"))
    assert _clean(ui_text.motion_done_line(three, _built())) == (
        "Its gears are mated to turn in 3 trains, and SolidWorks reports no mate in error: drag G1, G5 and G9 in "
        "SolidWorks, one for each train.")


def test_after_build_with_no_train_each_gear_turns_on_its_shaft_and_fixed_or_lone_gears_are_said():
    assert ui_text.motion_done_line(_turning(trains=(), drag=(), meshes=()), _built()) == (
        "Its gears are each mated to their shaft, free to turn, and SolidWorks reports no mate in error.")
    both = _turning(extra_shafts={"S4": "G7"}, fixed=("G9", "G10"))
    assert _clean(ui_text.motion_done_line(both, _built())) == (
        "Its turning gears are mated to their shafts and, where they mesh, to each other; SolidWorks reports no mate "
        "in error: drag G1 in SolidWorks and the rest of its train follow. G7 turns apart from the train: it meshes "
        "no other gear. G9 and G10 stay fixed where they are placed: their shafts do not turn.")
    assert ui_text.motion_done_line(_turning(fixed=("G9",)), _built()).startswith(
        "Its turning gears are mated to turn together, and SolidWorks reports no mate in error: drag G1")


def test_a_train_with_no_drag_gear_is_never_said_to_be_gears_each_on_their_shaft():
    assert ui_text.motion_done_line(_turning(drag=()), _built()) == (
        "Its gears are mated to turn together, and SolidWorks reports no mate in error.")
    assert ui_text.motion_done_line(_turning(drag=(), trains=(("S1", "S2"), ("S3",))), _built()) == (
        "Its gears are mated to turn in 2 trains, and SolidWorks reports no mate in error.")


def test_after_build_a_clash_still_stands_out_and_the_mates_are_said_after_it():
    result = _built(clashes=[swbuild.Clash(("Gear_m1.5_N17-1", "Gear_m1.5_N68-1"), ("G1", "G2"), 12.3454)])
    plan = dataclasses.replace(_turning(), meshes=(("G1", "G2"),))
    assert ui_text.gearbox_status(plan, result) == (
        "Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM. Check: G1 and G2 interfere, 12.345 mm³; look "
        "at their mesh in Reducer_12to1.SLDASM. Its gears are mated to turn together, and SolidWorks reports no mate "
        "in error: drag G1 in SolidWorks and the rest of its train follow.", False)


def test_after_build_a_static_build_by_necessity_says_why_and_w4s_says_nothing_new():
    plan = _gearbox(static_reason=STATIC_REASON, **FULL)
    assert ui_text.gearbox_status(plan, _built(kind="static")) == (
        "Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM; no interference between the gears. Its gears "
        "are placed meshed and fixed, not mated to turn: how gears are mated to turn is not settled for this version "
        "(findings.MOTION_ROUTE).", True)
    w4 = "Built 4 parts, Reducer_12to1_Layout and Reducer_12to1.SLDASM; no interference between the gears."
    assert ui_text.gearbox_status(_gearbox(**FULL), _built(kind="static")) == (w4, True)
    assert ui_text.gearbox_status(_gearbox(**FULL), _built(kind="")) == (w4, True)
    assert ui_text.motion_done_line(None, _built()) == (
        "Its gears are mated to turn, and SolidWorks reports no mate in error.")


# a refused or flagged mate stops the build (W5-DECISIONS, answer 1): no fallback text anywhere


def test_a_refused_mate_names_it_keeps_the_parts_and_says_build_waits_for_a_changed_workbook():
    text, ok = ui_text.gearbox_status(_turning(), _refused(LOCK_PROBLEM))
    assert (_clean(text), ok) == (
        "Built 4 parts and Reducer_12to1_Layout; no assembly was saved, because SolidWorks found a problem with its "
        "mates. The mate G3 locked to G2 over-defines the assembly. The parts and the layout part are kept. The "
        "assembly is left open in SolidWorks as Assem1, not saved; its parts are the saved ones. Build is available "
        "again once the workbook changes: the same workbook would make the same mates.", False)
    assert "static" not in text and "fixed" not in text and "Press" not in text and "try" not in text


def test_blank_mate_problems_are_no_refusal_and_never_counted_as_none():
    """A failed assembly whose problems are all blank is W4's failed assembly, never "found 0 problems"."""
    result = _refused("", " ")
    text, _ = ui_text.gearbox_status(_turning(), result)
    assert "0 problems" not in text and "no assembly was saved" not in text
    assert text.startswith("Built 4 parts and Reducer_12to1_Layout; the assembly Assem1 was left open, unsaved;")
    text, _ = ui_text.gearbox_status(_turning(), _refused("", LOCK_PROBLEM))
    assert "found a problem with its mates. The mate G3 locked to G2 over-defines the assembly. The parts" in text


def test_every_problem_is_its_own_whole_sentence_and_they_are_counted():
    text, _ = ui_text.mate_refused_status(_turning(), _refused(FLAG_PROBLEM, TURN_PROBLEM))
    assert _clean(text).startswith(
        "Built 4 parts and Reducer_12to1_Layout; no assembly was saved, because SolidWorks found 2 problems with its "
        "mates. SolidWorks answered 3 when making the mate G1 meshes G2. G2 cannot turn: SolidWorks reads it fully "
        "defined. The parts and the layout part are kept.")
    three, _ = ui_text.mate_refused_status(_turning(), _refused(LOCK_PROBLEM, FLAG_PROBLEM, "G4 is over-defined in "
                                                                                           "SolidWorks"))
    assert "found 3 problems with its mates. The mate G3 locked to G2 over-defines the assembly. SolidWorks answered " \
           "3 when making the mate G1 meshes G2. G4 is over-defined in SolidWorks. The parts" in _clean(three)


def test_a_refusal_after_reusing_the_parts_and_layout_and_with_no_document_left_open():
    plan = _gearbox(layout="reuse", motion=_motion(), reuse=[_reuse(s, [g]) for s, g in zip(STEMS, ("G1", "G2", "G3",
                                                                                                   "G4"))])
    result = _refused(TURN_PROBLEM, document="", parts=swbuild.ManyResult(), layout=None,
                      layout_reused=_path("Reducer_12to1_Layout"))
    text, ok = ui_text.gearbox_status(plan, result, again=True)
    assert (_clean(text), ok) == (
        "Reused Reducer_12to1_Layout and the 4 parts already built; no assembly was saved, because SolidWorks found a "
        "problem with its mates. G2 cannot turn: SolidWorks reads it fully defined. The parts and the layout part are "
        "kept. Build is available again once the workbook changes: the same workbook would make the same mates.",
        False)


def test_an_assembly_that_failed_for_any_other_reason_is_w4s_sentence_and_build_carries_on():
    """Only a real refusal is a mate problem; a COM failure during a mate is W4's failed assembly (W5-INTERFACES)."""
    result = _built(kind="", assembly=_failed("Assem1", "mate G1 meshes G2", "The RPC server is unavailable."))
    assert ui_text.gearbox_status(_turning(), result) == (
        "Built 4 parts and Reducer_12to1_Layout; the assembly Assem1 was left open, unsaved; mate G1 meshes G2: The "
        "RPC server is unavailable. Press Build to try the assembly again: the parts and layout are reused.", False)


def _refused_record(digest="d1", problems=(LOCK_PROBLEM,)):
    record = _record(assembly=False)
    record.gearbox.mate_problems, record.gearbox.mate_problems_digest = list(problems), digest
    record.digest = digest
    return record


def _carry_on_plan():
    return _gearbox(layout="reuse", motion=_motion(), reuse=[_reuse(s, [g]) for s, g in zip(STEMS, ("G1", "G2", "G3",
                                                                                                   "G4"))])


def test_the_footer_after_a_refusal_keeps_build_greyed_for_the_same_read_and_says_why(ready):
    """Ruling (b): Build stays greyed for the read the refusal came from; the sentence names the mate and says that
    changing the workbook makes Build available again; Update's own reason is not the record's "Build carries on"."""
    f = _footer(ready, record=_refused_record(), plan=_carry_on_plan(), update=UpdatePlan(refusal=REFUSED_LAYOUT),
                digest="d1")
    assert _clean(f.text) == (
        "Reducer_12to1.SLDASM was not saved, because SolidWorks found a problem with its mates. The mate G3 locked "
        "to G2 over-defines the assembly. Build is available again once the workbook changes: the same workbook "
        "would make the same mates. Update SolidWorks waits until Build has made the assembly.")
    assert (f.ok, f.build_action, f.build_enabled, f.update_shown, f.update_enabled) == (
        False, ui_text.BUILD, False, True, False)
    assert "carries on" not in f.text


def test_under_the_refusing_builds_own_sentence_the_footer_does_not_say_it_twice(ready):
    said = ui_text.gearbox_status(_carry_on_plan(), _refused(LOCK_PROBLEM, parts=swbuild.ManyResult(), layout=None,
                                                             layout_reused=_path("Reducer_12to1_Layout")))
    f = _footer(ready, record=_refused_record(), plan=_carry_on_plan(), update=UpdatePlan(refusal=REFUSED_LAYOUT),
                digest="d1", note=said)
    assert f.text == (
        "Reused Reducer_12to1_Layout and the 4 parts already built; no assembly was saved, because SolidWorks found a "
        "problem with its mates. The mate G3 locked to G2 over-defines the assembly. The parts and the layout part "
        "are kept. The assembly is left open in SolidWorks as Assem1, not saved; its parts are the saved ones. Build "
        "is available again once the workbook changes: the same workbook would make the same mates. Update "
        "SolidWorks waits until Build has made the assembly.")
    assert (f.ok, f.build_enabled, f.update_enabled) == (False, False, False)
    assert f.text.count(LOCK_PROBLEM) == 1


READY_CARRY_ON = (f"Ready: Build makes Reducer_12to1.SLDASM in {P}, reusing Reducer_12to1_Layout and the 4 parts "
                  "already built. Its gears are mated to their shafts and to each other, so they turn together in "
                  "SolidWorks.")
REFUSAL_ON_RECORD = ("Reducer_12to1.SLDASM was not saved, because SolidWorks found a problem with its mates. The mate "
                     "G3 locked to G2 over-defines the assembly.")


def test_once_the_workbook_changes_build_is_offered_and_the_refusal_still_said(ready):
    f = _footer(ready, record=_refused_record(), plan=_carry_on_plan(), update=UpdatePlan(refusal=REFUSED_LAYOUT),
                digest="d2")
    assert _clean(f.text) == (
        f"{READY_CARRY_ON} {REFUSAL_ON_RECORD} The workbook has changed since, so Build tries the assembly again. "
        f"{REFUSED_LAYOUT}")
    assert (f.ok, f.build_enabled, f.update_enabled) == (True, True, False)


def test_a_change_is_never_claimed_when_either_read_is_not_known(ready):
    """With no digest from the window ("", as today's caller passes) or none on record, the footer cannot tell the
    workbook changed: it offers Build and says only that it tries the assembly again."""
    for record_digest, digest in (("d1", ""), ("", "d2"), ("", "")):
        f = _footer(ready, record=_refused_record(digest=record_digest), plan=_carry_on_plan(),
                    update=UpdatePlan(refusal=REFUSED_LAYOUT), digest=digest)
        assert _clean(f.text) == (
            f"{READY_CARRY_ON} {REFUSAL_ON_RECORD} Build tries the assembly again. {REFUSED_LAYOUT}")
        assert "changed since" not in f.text and f.build_enabled
    assert ui_text.motion_record_line(_refused_record(), "", offer=False) == REFUSAL_ON_RECORD
    unnamed = _refused_record()
    unnamed.gearbox.name = ""
    assert ui_text.motion_record_line(unnamed, "d1").startswith("The assembly was not saved, because SolidWorks found")


def test_a_record_with_no_problems_or_no_digest_never_holds_build(ready):
    record = _refused_record(digest="")
    f = _footer(ready, record=record, plan=_carry_on_plan(), digest="")
    assert f.build_enabled and f.text == f"{READY_CARRY_ON} {REFUSAL_ON_RECORD} Build tries the assembly again."
    record = _refused_record(problems=(" ", ""))
    f = _footer(ready, record=record, plan=_carry_on_plan(), digest="d1")
    assert f.build_enabled and f.text == READY_CARRY_ON
    record = _refused_record(problems=())
    f = _footer(ready, record=record, plan=_carry_on_plan(), digest="d1")
    assert f.build_enabled and f.text == (
        f"Ready: Build makes Reducer_12to1.SLDASM in {P}, reusing Reducer_12to1_Layout and the 4 parts already built. "
        "Its gears are mated to their shafts and to each other, so they turn together in SolidWorks.")


def test_a_gate_that_refuses_comes_before_the_refusal(ready, tmp_path):
    f = _footer(ready, record=_refused_record(), plan=_carry_on_plan(), digest="d1", folder_exists=False)
    assert f.text.startswith("The output folder") and not f.build_enabled


# the footer on a gearbox on record


def _turning_record(drag=("G1",)):
    record = _record()
    record.gearbox.kind, record.gearbox.drag = store.GEARBOX_MOTION, list(drag)
    return record


def test_the_footer_on_a_turning_gearbox_says_which_gear_to_drag(ready):
    f = _footer(ready, record=_turning_record(), plan=_turning(), update=_update())
    assert _clean(f.text) == (
        "Update SolidWorks will change G2's values (Gear_m1.5_N68), move S2 and S3 in Reducer_12to1_Layout, and "
        "re-place G2, G3 and G4. It was built with its gears mated to turn: drag G1 in SolidWorks and the rest of "
        "its train follow.")
    assert ui_text.motion_record_line(_turning_record(("G1", "G5"))) == (
        "It was built with its gears mated to turn: drag G1 in SolidWorks to turn one train and G5 to turn the other.")
    assert ui_text.motion_record_line(_turning_record(("G1", "G5", "G9"))) == (
        "It was built with its gears mated to turn: drag G1, G5 and G9 in SolidWorks, one for each train.")
    assert ui_text.motion_record_line(_turning_record(())) == (
        "It was built with its gears each mated to their shaft, free to turn.")
    nothing = _footer(ready, record=_turning_record(), plan=_turning())
    assert nothing.text == (
        "Reducer_12to1.SLDASM is built from this workbook. It was built with its gears mated to turn: drag G1 in "
        "SolidWorks and the rest of its train follow.")


def test_a_w4_static_gearbox_is_offered_a_turning_revision_never_forced(ready):
    """D5: the footer says it was built before gears could turn and that Build again… makes a turning revision;
    Update stays the primary, and every W4 sentence before it is as it was."""
    f = _footer(ready, record=_record(), plan=dataclasses.replace(_again(), motion=_motion()), update=_update())
    assert _clean(f.text) == (
        "Update SolidWorks will change G2's values (Gear_m1.5_N68), move S2 and S3 in Reducer_12to1_Layout, and "
        "re-place G2, G3 and G4. It was built static, before gears could be mated to turn: Build again… makes a new "
        "revision whose gears turn.")
    assert (f.build_action, f.build_enabled, f.build_primary, f.update_enabled, f.update_primary) == (
        ui_text.BUILD_AGAIN, True, False, True, True)
    structural = _footer(ready, record=_record(), plan=dataclasses.replace(_again(), motion=_motion()),
                         update=_update(structural=("G2's bore was added, which its built part cannot take.",)))
    assert structural.text == (
        "G2's bore was added, which its built part cannot take. Update SolidWorks offers to build again as "
        "Reducer_12to1_r2. It was built static, before gears could be mated to turn: Build again… makes a new "
        "revision whose gears turn.")


def test_a_w4_static_gearbox_whose_next_revision_would_not_turn_or_cannot_go_is_told_nothing_new(ready):
    w4 = ("Update SolidWorks will change G2's values (Gear_m1.5_N68), move S2 and S3 in Reducer_12to1_Layout, and "
          "re-place G2, G3 and G4.")
    assert _footer(ready, record=_record(), plan=_again(), update=_update()).text == w4
    static_next = dataclasses.replace(_again(), static_reason=STATIC_REASON)
    assert _footer(ready, record=_record(), plan=static_next, update=_update()).text == w4
    greyed = _footer(ready, record=_record(), plan=dataclasses.replace(_again(), motion=_motion()), update=_update(),
                     folder_exists=False)
    assert "Build again… makes" not in greyed.text and not greyed.build_enabled


def test_a_gearbox_built_static_for_a_missing_finding_says_why_and_offers_once_it_is_settled(ready):
    record = _record()
    record.gearbox.static_reason = STATIC_REASON
    assert _clean(ui_text.motion_record_line(record, offer=False)) == (
        "It was built static: how gears are mated to turn is not settled for this version (findings.MOTION_ROUTE).")
    f = _footer(ready, record=record, plan=dataclasses.replace(_again(), motion=_motion()), update=_update())
    assert f.text.endswith(
        "re-place G2, G3 and G4. It was built static: how gears are mated to turn is not settled for this version "
        "(findings.MOTION_ROUTE). That is settled now, so Build again… makes a new revision whose gears turn.")


def test_the_record_line_is_empty_with_no_gearbox_and_never_follows_an_error(ready):
    assert ui_text.motion_record_line(None) == "" and ui_text.motion_record_line(_record(layout=False)) == ""
    f = _footer(ready, record=_turning_record(), plan=_turning(), update=_update(missing=(_path("Gear_m1.5_N68"),)))
    assert not f.ok and "drag" not in f.text


def test_the_build_again_question_on_a_static_record_says_the_new_revision_turns():
    fresh = _gearbox("Reducer_12to1_r2", motion=_motion(), **FULL)
    question = ui_text.build_again_question(_update(), fresh, record=_record())
    assert _clean(question).startswith(
        "Reducer_12to1.SLDASM was built static; the new revision's gears are mated to turn. Build again as "
        "Reducer_12to1_r2? That makes new parts for G1 (Gear_m1.5_N17), ")
    update = _update(structural=("G2's bore was added, which its built part cannot take.",))
    assert ui_text.build_again_question(update, fresh, record=_record()).startswith(
        "G2's bore was added, which its built part cannot take. Reducer_12to1.SLDASM was built static; the new "
        "revision's gears are mated to turn. Build again as Reducer_12to1_r2? ")
    # A turning record, a static next revision, or no record given: W4's words.
    for record, plan in ((_turning_record(), fresh), (_record(), _gearbox("Reducer_12to1_r2", **FULL)), (None, fresh)):
        assert ui_text.build_again_question(_update(), plan, record=record).startswith(
            "Nothing on record needs a new revision. Build again as Reducer_12to1_r2? ")


def test_a_structural_edit_on_a_turning_gearbox_is_shown_as_classify_wrote_it(ready):
    """D8, answer 3 and D7 are classify's sentences (package B); the footer and the question show them whole."""
    face = ("G1's face width moves its front face off the Front plane (0 → 2 mm), and its mate along S1 has no "
            "distance to set, so it needs a new revision.")
    teeth = ("G2's teeth changed from 68 to 69, and the gear mate G1 meshes G2 still turns at 17 : 68: Update "
             "SolidWorks cannot change a gear mate's ratio, so it needs a new revision.")
    update = _update(structural=(face, teeth))
    f = _footer(ready, record=_turning_record(), plan=dataclasses.replace(_again(), motion=_motion()), update=update)
    assert _clean(f.text) == (
        "G1's face width moves its front face off the Front plane (0 → 2 mm), and its mate along S1 has no distance "
        "to set, so it needs a new revision (and 1 other change Update SolidWorks cannot carry). Update SolidWorks "
        "offers to build again as Reducer_12to1_r2. It was built with its gears mated to turn: drag G1 in "
        "SolidWorks and the rest of its train follow.")
    question = ui_text.build_again_question(update, _again(), record=_turning_record())
    assert question.startswith(f"{face} {teeth} Build again as Reducer_12to1_r2? ")


# before Update SolidWorks, and after, on a turning gearbox


def _motion_update(plan=None, **changes):
    refs = tuple(swbuild.MateRef(m.name, m.kind, m.gears, m.shaft) for m in (plan or _motion()).mates)
    motion = swbuild.MotionUpdate(mates=refs, locks=(swbuild.LockLink("G2", "G3", 0.0),),
                                  meshes=(swbuild.MeshLink("G1", "G2", -0.25, 5.294),
                                          swbuild.MeshLink("G3", "G4", -1 / 3, 7.059)),
                                  ratios=(("G1 meshes G2", 17, 69), ("G3 meshes G4", 17, 52)))
    fields = dict(motion=motion, parts=(), layout=None, moved_shafts=(), replaced=())
    fields.update(changes)
    return _update(**fields)


ASM = _path("Reducer_12to1", ".SLDASM")


def _moved(**values):
    fields = dict(parts=[], layout=None, placed=[], rebuilt=True, changed=[])
    fields.update(values)
    return swbuild.GearboxUpdate(**fields)


def test_the_update_summary_names_a_move_along_a_shaft_and_a_new_ratio():
    assert ui_text.update_summary(_motion_update(axial=("G4",), replaced=("G4",))) == (
        "Update SolidWorks will move G4 along S3, and re-place G4.")
    assert ui_text.update_summary(_motion_update(axial=("G4",))) == "Update SolidWorks will move G4 along S3."
    both = _motion_update(axial=("G2", "G4"), ratios=("G1 meshes G2",), replaced=("G2", "G3", "G4"),
                          moved_shafts=("S2",), layout=swbuild.DocumentValues(_path("Reducer_12to1_Layout")))
    assert _clean(ui_text.update_summary(both)) == (
        "Update SolidWorks will move S2 in Reducer_12to1_Layout, move G2 along S2 and G4 along S3, set the gear mate "
        "G1 meshes G2 to 17 : 69, and re-place G2, G3 and G4.")
    two = _motion_update(ratios=("G1 meshes G2", "G3 meshes G4"))
    assert ui_text.update_summary(two) == (
        "Update SolidWorks will set the gear mates G1 meshes G2 to 17 : 69 and G3 meshes G4 to 17 : 52.")


def test_after_update_a_train_that_had_to_move_is_said_to_be_back_at_its_built_turn():
    """Answer 2 and D4: when Update had to put a train, it put every mated gear of it back to the built turn."""
    result = _moved(placed=["G1", "G2", "G3", "G4"], changed=[ASM], restored=[("G1", "G2", "G3", "G4")],
                    layout=swbuild.UpdateResult(document="Reducer_12to1_Layout.SLDPRT", changed=["S2 X"], rebuilt=True))
    update = _motion_update(moved_shafts=("S2",), layout=swbuild.DocumentValues(_path("Reducer_12to1_Layout")))
    assert _clean(ui_text.gearbox_update_status(update, result)[0]) == (
        "Updated SolidWorks: moved S2 in Reducer_12to1_Layout, re-placed G1, G2, G3 and G4; no interference between "
        "the gears where they stand. G1, G2, G3 and G4 had been turned in SolidWorks; their train is back at the turn "
        "it was built at. Save Reducer_12to1 in SolidWorks to keep it.")
    one = _moved(placed=["G1", "G2"], changed=[ASM], restored=[("G2",)])
    assert "G2 had been turned in SolidWorks; its train is back at the turn it was built at." in \
        ui_text.gearbox_update_status(_motion_update(), one)[0]


TWO_TRAINS = _motion(trains=(("S1", "S2", "S3"), ("S4", "S5")), drag=("G1", "G5"),
                     extra_shafts={"S4": "G5", "S5": "G6"},
                     meshes=(("G1", "G2", 17, 68), ("G3", "G4", 17, 51), ("G5", "G6", 20, 40)))


def test_two_trains_where_only_one_was_put_name_only_that_train():
    """The first train had to move (G4 along S3) and is said to be back; the second, which the user also turned,
    was not put: which one stayed turned cannot be told from the result, so the sentence says it of any gear not
    put back, and never names "the gears" as if all were back."""
    result = _moved(placed=["G1", "G2", "G3", "G4"], changed=[ASM], turned=True, restored=[("G1", "G2", "G3", "G4")],
                    axial=["G4"])
    text, ok = ui_text.gearbox_update_status(_motion_update(TWO_TRAINS), result)
    assert (_clean(text), ok) == (
        "Updated SolidWorks: moved G4 along S3, re-placed G1, G2, G3 and G4; no interference between the gears where "
        "they stand. G1, G2, G3 and G4 had been turned in SolidWorks; their train is back at the turn it was built "
        "at. Any gear it did not put back stands where it was turned in SolidWorks. Save Reducer_12to1 in SolidWorks "
        "to keep it.", True)
    assert "G5" not in text and "G6" not in text
    # Both trains put: nothing stands turned, so nothing more is said.
    every = _moved(placed=["G1", "G2", "G3", "G4", "G5", "G6"], changed=[ASM], turned=True,
                   restored=[("G1", "G2", "G3", "G4"), ("G5", "G6")])
    assert ui_text.gearbox_update_status(_motion_update(TWO_TRAINS), every)[0] == (
        "Updated SolidWorks: re-placed G1, G2, G3, G4, G5 and G6; no interference between the gears where they stand. "
        "G1, G2, G3 and G4 had been turned in SolidWorks; their train is back at the turn it was built at. G5 and G6 "
        "had been turned in SolidWorks; their train is back at the turn it was built at. Save Reducer_12to1 in "
        "SolidWorks to keep it.")


def test_a_train_put_with_no_gear_turned_back_gets_no_sentence():
    put = _moved(placed=["G1", "G2", "G3", "G4"], changed=[ASM], restored=[])
    assert ui_text.gearbox_update_status(_motion_update(), put)[0] == (
        "Updated SolidWorks: re-placed G1, G2, G3 and G4; no interference between the gears where they stand. Save "
        "Reducer_12to1 in SolidWorks to keep it.")


def test_with_nothing_to_put_a_turned_train_stays_and_the_sentence_says_so():
    """W5-DECISIONS answer 2: with nothing to put, the train stays where the user turned it, said plainly."""
    turned = _moved(turned=True)
    assert ui_text.gearbox_update_status(_motion_update(), turned) == (
        "SolidWorks already matches the workbook: nothing was changed. The gears stand where they were turned in "
        "SolidWorks.", True)
    values = _moved(turned=True, parts=[swbuild.UpdateResult(document="Gear_m1.5_N68.SLDPRT", changed=["No. of Teeth"],
                                                             rebuilt=True)], changed=[_path("Gear_m1.5_N68")])
    text, _ = ui_text.gearbox_update_status(_motion_update(parts=_update().parts), values)
    assert _clean(text) == (
        "Updated SolidWorks: changed 1 variable in Gear_m1.5_N68 (it now has 69 teeth; its file keeps its name); no "
        "interference between the gears where they stand. The gears stand where they were turned in SolidWorks. Save "
        "Gear_m1.5_N68 in SolidWorks to keep it.")
    # A fixed gear re-placed (W4's rule) is no mated gear put: the train still stands as it was turned.
    fixed = _moved(turned=True, placed=["G9"], changed=[ASM])
    assert ui_text.gearbox_update_status(_motion_update(), fixed)[0] == (
        "Updated SolidWorks: re-placed G9; no interference between the gears where they stand. The gears stand where "
        "they were turned in SolidWorks. Save Reducer_12to1 in SolidWorks to keep it.")
    # Not turned: nothing about it.
    assert ui_text.gearbox_update_status(_motion_update(), _moved()) == (ui_text.ALREADY_MATCHES, True)


def test_the_summary_before_update_on_a_turning_gearbox_never_promises_to_put_a_turn_back():
    assert ui_text.update_summary(_motion_update()) == (
        "SolidWorks already matches the workbook on record; Update SolidWorks checks it live and puts right anything "
        "changed there; gears turned in SolidWorks stay where they are unless something must move.")
    assert ui_text.update_summary(_update(parts=(), moved_shafts=(), replaced=())) == (
        "SolidWorks already matches the workbook on record; Update SolidWorks checks it live and puts right anything "
        "changed there.")


def test_a_relation_out_of_step_is_said_without_guessing_which_gear_was_turned():
    result = _moved(placed=["G1", "G2", "G3", "G4"], changed=[ASM], out_of_step=[("G1", "G2"), ("G2", "G3")],
                    restored=[("G2", "G3", "G4")])
    text = _clean(ui_text.gearbox_update_status(_motion_update(), result)[0])
    assert text == (
        "Updated SolidWorks: re-placed G1, G2, G3 and G4; no interference between the gears where they stand. G1 and "
        "G2 had been turned out of step with each other in SolidWorks; they are back in mesh. G2 and G3 had been "
        "turned out of step with each other in SolidWorks; they are back in step. G2, G3 and G4 had been turned in "
        "SolidWorks; their train is back at the turn it was built at. Save Reducer_12to1 in SolidWorks to keep it.")


def test_a_gear_moved_off_its_axis_is_w4s_put_back():
    result = _moved(placed=["G1", "G2", "G3", "G4"], changed=[ASM], off_axis=["G4"])
    text, _ = ui_text.gearbox_update_status(_motion_update(), result, dragged=["G4"])
    assert text == ("Updated SolidWorks: re-placed G1, G2 and G3; no interference between the gears where they stand. "
                    "G4 had been moved in SolidWorks; put back where the workbook has it. Save Reducer_12to1 in "
                    "SolidWorks to keep it.")


def test_a_recorded_mate_found_suppressed_was_turned_back_on_and_said():
    """D10."""
    result = _moved(changed=[ASM], unsuppressed=["G1 meshes G2"])
    assert ui_text.gearbox_update_status(_motion_update(), result)[0] == (
        "Updated SolidWorks: turned the mate G1 meshes G2 back on (it was suppressed in SolidWorks); no interference "
        "between the gears where they stand. Save Reducer_12to1 in SolidWorks to keep it.")
    two = _moved(changed=[ASM], unsuppressed=["G1 meshes G2", "G3 locked to G2"], axial=["G4"],
                 ratios=["G3 meshes G4"])
    assert _clean(ui_text.gearbox_update_status(_motion_update(), two)[0]).startswith(
        "Updated SolidWorks: turned the mates G1 meshes G2 and G3 locked to G2 back on (they were suppressed in "
        "SolidWorks), moved G4 along S3, set the gear mate G3 meshes G4 to 17 : 52; no interference")


def test_mates_the_app_did_not_make_and_left_alone_are_said_even_when_nothing_changed():
    one = _moved(extra_mates=["Angle1"])
    assert ui_text.gearbox_update_status(_motion_update(), one) == (
        "SolidWorks already matches the workbook: nothing was changed. Reducer_12to1.SLDASM also has a suppressed "
        "mate the app did not make, Angle1; Update SolidWorks left it as it is.", True)
    three = _moved(changed=[ASM], placed=["G4"], extra_mates=["Angle1", "Angle2", "Distance3"])
    assert ("Reducer_12to1.SLDASM also has suppressed mates the app did not make, Angle1, Angle2 and Distance3; "
            "Update SolidWorks left them as they are. Save Reducer_12to1") in \
        _clean(ui_text.gearbox_update_status(_motion_update(), three)[0])


def test_an_unknown_mate_not_suppressed_refuses_the_update_in_the_workers_own_words():
    """M7: the worker's check phase raises a BuildError naming the mate; the window shows it as it came."""
    said = ("Reducer_12to1.SLDASM has a mate the app did not make, Angle1, and it is not suppressed: suppress Angle1 "
            "in SolidWorks and press Update SolidWorks again.")
    assert ui_text.job_failed(swbuild.BuildError(said), updating=True) == said


def test_locks_that_could_not_be_turned_back_on_are_never_hidden_behind_the_failure_before_them():
    """M8: the put fails, then the locks' unsuppress in the finally fails too; both are said, in order."""
    result = _moved(changed=[ASM], failures=[
        ("Reducer_12to1.SLDASM", "G2 would not move: Transform2 was not taken."),
        ("Reducer_12to1.SLDASM", "The compound gears G2 and G3 are not locked: press Update SolidWorks again.")])
    assert ui_text.gearbox_update_status(_motion_update(), result) == (
        "Update SolidWorks stopped. Reducer_12to1.SLDASM: G2 would not move: Transform2 was not taken. The compound "
        "gears G2 and G3 are not locked: press Update SolidWorks again. It had already changed Reducer_12to1, not "
        "saved: press Update SolidWorks again once that is put right, or save it in SolidWorks to keep what it did.",
        False)
    post = _moved(failures=[("Gear_m1.5_N68.SLDPRT", "SolidWorks reported an error rebuilding Gear_m1.5_N68."),
                            ("Reducer_12to1.SLDASM", "G4 is not where Update SolidWorks put it once the assembly "
                                                     "rebuilt: a mate holds it elsewhere.")])
    assert ui_text.gearbox_update_status(_motion_update(), post)[0] == (
        "Update SolidWorks stopped. Gear_m1.5_N68.SLDPRT: SolidWorks reported an error rebuilding Gear_m1.5_N68. "
        "Reducer_12to1.SLDASM: G4 is not where Update SolidWorks put it once the assembly rebuilt: a mate holds it "
        "elsewhere. Nothing was changed.")
    # W4's static path keeps saying the first failure only, word for word.
    assert ui_text.gearbox_update_status(_update(), post)[0] == (
        "Update SolidWorks stopped. Gear_m1.5_N68.SLDPRT: SolidWorks reported an error rebuilding Gear_m1.5_N68. "
        "Nothing was changed.")


def test_motion_update_lines_are_whole_sentences_and_empty_on_the_static_path():
    result = _moved(changed=[ASM], placed=["G1", "G2", "G3", "G4"], unsuppressed=["G1 meshes G2"], axial=["G4"],
                    ratios=["G1 meshes G2"], out_of_step=[("G1", "G2")], restored=[("G1", "G2")],
                    extra_mates=["Angle1"])
    lines = ui_text.motion_update_lines(_motion_update(), result)
    assert lines == [
        "Turned the mate G1 meshes G2 back on (it was suppressed in SolidWorks).",
        "Moved G4 along S3.",
        "Set the gear mate G1 meshes G2 to 17 : 69.",
        "G1 and G2 had been turned out of step with each other in SolidWorks; they are back in mesh.",
        "G1 and G2 had been turned in SolidWorks; their train is back at the turn it was built at.",
        "Reducer_12to1.SLDASM also has a suppressed mate the app did not make, Angle1; Update SolidWorks left it as "
        "it is."]
    for line in lines:
        assert _clean(line)[0].isupper() and line.endswith(".")
    assert ui_text.motion_update_lines(_update(), result) == []


def test_a_static_gearboxs_update_reads_exactly_as_in_w4_whatever_the_result_carries():
    result = _updated(restored=[("G2",)], unsuppressed=["X"], extra_mates=["Angle1"], turned=True)
    assert ui_text.gearbox_update_status(_update(), result) == (
        "Updated SolidWorks: changed 1 variable in Gear_m1.5_N68 (it now has 69 teeth; its file keeps its name), "
        "moved S2 and S3 in Reducer_12to1_Layout, re-placed G2, G3 and G4; no interference between the gears. Save "
        "Gear_m1.5_N68, Reducer_12to1_Layout and Reducer_12to1 in SolidWorks to keep them.", True)


def test_no_w5_sentence_says_fallback_or_static_instead():
    """W5-DECISIONS answer 1: there is no static fallback, so nothing anywhere speaks of one."""
    import inspect
    source = inspect.getsource(ui_text)
    for phrase in ("static instead", "fallback record", "tries again as a new revision", "would not mate them",
                   "close it without saving"):
        assert phrase not in source
