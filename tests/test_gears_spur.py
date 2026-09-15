"""Spur gear maths, outlines, checks and plans."""

import math

import pytest

from gear_generator.gears import KINDS, PLANNED_KINDS
from gear_generator.gears.base import (
    AddGlobal,
    BuildPlan,
    Dimension,
    GeometryError,
    LinkDimension,
    ManualStep,
    NewPart,
    OpenSketch,
    Rebuild,
    SaveAs,
)
from gear_generator.gears.spur import contact_ratio, flank_deviation, signed_area
from gear_generator.spec import GearSpec

SPUR = KINDS["spur"]
PINNED = GearSpec(module="1.5", teeth="25", pressure_angle="20", backlash="", fillet="")


def messages(spec, level=None):
    return [d.message for d in SPUR.validate(spec) if level is None or d.level == level]


# -- §2.1 pinned values -----------------------------------------------------


def test_the_pinned_gear():
    g = SPUR.derive(PINNED)
    assert g.backlash == pytest.approx(0.45)
    assert g.fillet == pytest.approx(0.57)
    expected = {
        "d": 37.5, "da": 40.5, "h": 3.375, "df": 33.75, "db": 35.238473, "p": 4.712389,
        "space": 2.806194, "s": 1.906194, "psi_s": 0.074832, "inv_alpha": 0.014904,
        "phi": 0.059927, "t_max": 0.566496,
    }
    for name, value in expected.items():
        assert getattr(g, name) == pytest.approx(value, abs=1e-6), name
    assert g.n_min == pytest.approx(17.097, abs=1e-3)


def test_the_pinned_contact_ratio_meshing_with_itself():
    assert contact_ratio(1.5, 25, 25, 20.0, 37.5) == pytest.approx(1.6117, abs=1e-4)


def test_tooth_depth_follows_the_users_iif():
    assert SPUR.derive(GearSpec(module="1.25")).h == pytest.approx(3.0)
    assert SPUR.derive(GearSpec(module="1.26")).h == pytest.approx(2.835)


def test_a_typed_backlash_and_fillet_are_used_as_given():
    g = SPUR.derive(GearSpec(backlash="0.05", fillet="0.3"))
    assert (g.backlash, g.fillet, g.backlash_typed, g.fillet_typed) == (0.05, 0.3, True, True)


# -- undercut and the base circle -------------------------------------------


def test_exactly_seventeen_teeth_is_not_warned_about():
    assert not any("undercut" in m for m in messages(GearSpec(module="1", teeth="17", bore="")))


def test_sixteen_teeth_is_warned_about():
    assert any("undercut" in m for m in messages(GearSpec(module="1", teeth="16", bore="")))


def test_twelve_teeth_warns_and_still_closes():
    spec = GearSpec(module="2", teeth="12", bore="", recipe="A")
    warnings = messages(spec, "warning")
    assert any("undercut limit of 17" in m for m in warnings)
    assert not messages(spec, "error")
    outline = SPUR.outline(spec, SPUR.derive(spec))
    assert outline[0] == outline[-1]


@pytest.mark.parametrize("module,teeth,above", [
    (1.5, 25, True), (1.5, 41, True), (1.5, 42, False), (1, 46, True), (1, 47, False), (1, 50, False),
])
def test_where_the_base_circle_drops_below_the_root(module, teeth, above):
    """N·(1 − cos α) < 2h/m − 2: N ≤ 41 at h = 2.25 m, N ≤ 46 at h = 2.4 m."""
    g = SPUR.derive(GearSpec(module=str(module), teeth=str(teeth), bore=""))
    assert g.base_above_root is above


def test_the_involute_starts_at_the_larger_of_base_and_three_fillets_above_root():
    small = SPUR.derive(GearSpec(module="1.5", teeth="18"))
    assert small.flank_start_d == pytest.approx(max(small.db, small.df + 3 * small.fillet))
    large = SPUR.derive(GearSpec(module="1", teeth="50", bore=""))
    assert large.flank_start_d == pytest.approx(large.df + 3 * large.fillet)
    assert large.t1 > 0


# -- outlines ---------------------------------------------------------------


def _pitch_vertices(outline, rp):
    return [p for p in outline[:-1] if abs(math.hypot(*p) - rp) <= 1e-9]


def _sign_changes(outline, rp):
    signs = [math.hypot(*p) - rp for p in outline[:-1] if abs(math.hypot(*p) - rp) > 1e-9]
    return sum(1 for a, b in zip(signs, signs[1:] + signs[:1]) if (a > 0) != (b > 0))


@pytest.mark.parametrize("recipe", ["A", "B"])
@pytest.mark.parametrize("module,teeth", [(1.5, 25), (1, 17), (1, 50), (3, 40)])
def test_the_outline_is_closed_counter_clockwise_and_crosses_the_pitch_circle_2n_times(recipe, module, teeth):
    spec = GearSpec(module=str(module), teeth=str(teeth), bore="", recipe=recipe)
    g = SPUR.derive(spec)
    outline = SPUR.outline(spec, g)
    assert outline[0] == outline[-1]
    assert signed_area(outline[:-1]) > 0
    assert _sign_changes(outline, g.rp) == 2 * teeth
    assert len(_pitch_vertices(outline, g.rp)) == 2 * teeth


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_each_space_is_exactly_the_arc_length_wide_at_the_pitch_circle(recipe):
    spec = PINNED.with_values(recipe=recipe)
    g = SPUR.derive(spec)
    angles = [math.atan2(p[1], p[0]) for p in _pitch_vertices(SPUR.outline(spec, g), g.rp)]
    # Every space is the one on +X turned by a whole number of tooth pitches.
    pitch = 2 * math.pi / g.teeth
    for k in range(g.teeth):
        centre = k * pitch
        near = sorted(angles, key=lambda a: abs(math.remainder(a - centre, 2 * math.pi)))[:2]
        lower, upper = sorted(math.remainder(a - centre, 2 * math.pi) for a in near)
        assert (upper - lower) == pytest.approx(g.space / g.rp, abs=1e-9)
        assert (upper + lower) == pytest.approx(0.0, abs=1e-9)


def test_recipe_b_is_close_to_the_involute_at_this_size():
    """Tens of microns at module 1.5."""
    deviation = flank_deviation(SPUR.derive(PINNED))
    assert 0.01 < deviation < 0.1


# -- validation -------------------------------------------------------------


@pytest.mark.parametrize(
    "changes,field,words",
    [
        ({"module": "0"}, "module", "Module must be more than zero"),
        ({"teeth": "5"}, "teeth", "at least 6"),
        ({"teeth": "25.5"}, "teeth", "whole number"),
        ({"pressure_angle": "40"}, "pressure_angle", "between 10° and 35°"),
        ({"pressure_angle": "9"}, "pressure_angle", "between 10° and 35°"),
        ({"face_width": "0"}, "face_width", "Face width must be more than zero"),
        ({"backlash": "2.4"}, "backlash", "leaves no tooth"),
        ({"bore": "34"}, "bore", "reaches the root diameter"),
        ({"fillet": "3"}, "fillet", "Fillet smaller"),
        ({"profile_shift": "0.2"}, "profile_shift", "reserved"),
        ({"kind": "bevel"}, "kind", "form says"),
        ({"backlash": "-0.1"}, "backlash", "must not be negative"),
    ],
)
def test_every_refusal_is_a_sentence_naming_its_field(changes, field, words):
    errors = [d for d in SPUR.validate(PINNED.with_values(**changes)) if d.is_error]
    assert errors, changes
    assert any(d.field == field and words in d.message for d in errors), [d.message for d in errors]
    assert all(d.message.endswith(".") for d in errors)


def test_the_pinned_gear_has_nothing_to_say_on_the_involute_recipe():
    assert SPUR.validate(PINNED.with_values(recipe="A")) == []


def test_the_arc_recipe_says_how_close_it_is():
    notes = messages(PINNED.with_values(recipe="B"), "warning")
    assert len(notes) == 1 and "µm" in notes[0]


def test_a_thin_rim_under_the_teeth_is_warned_about():
    assert any("rim" in m for m in messages(PINNED.with_values(bore="32")))


def test_a_thin_tip_is_warned_about():
    assert any("tip is" in m for m in messages(GearSpec(module="2", teeth="12", bore="")))


def test_a_flank_start_above_the_form_diameter_is_warned_about():
    assert any("form diameter" in m for m in messages(GearSpec(module="1", teeth="50", bore="", recipe="A")))


def test_seven_teeth_cannot_be_closed_by_the_involute_recipe():
    errors = messages(GearSpec(module="2", teeth="7", bore="", recipe="A"), "error")
    assert any("cannot close the tooth space" in m for m in errors)


def test_twelve_teeth_cannot_be_built_with_arcs_and_says_to_use_the_involute():
    errors = messages(GearSpec(module="2", teeth="12", bore="", recipe="B"), "error")
    assert errors and "involute recipe" in errors[0]


def test_pointed_teeth_are_refused():
    errors = messages(GearSpec(module="1", teeth="6", pressure_angle="35", bore=""), "error")
    assert any("come to a point" in m for m in errors)


def test_derive_refuses_a_field_that_makes_no_gear():
    with pytest.raises(GeometryError, match="Module must be more than zero"):
        SPUR.derive(PINNED.with_values(module="-1"))


# -- plans ------------------------------------------------------------------

USERS_TEN = [
    '"No. of Teeth"= 25',
    '"Module"= 1.5',
    '"Bore Diameter"= 10',
    '"Pressure Angle"= 20',
    '"Outer Diameter"= ( "No. of Teeth" + 2 ) * "Module"',
    '"Pitch Diameter"= "No. of Teeth" * "Module"',
    '"Backlash"= 0.3 * "Module"',
    '"Arc Length"= ( ( "Module" * pi ) / 2 + "Backlash" )',
    '"Fillet Radius"= 0.38 * "Module"',
    '"Tooth Depth"= IIF ( "Module" <= 1.25 , "Module" * 2.4 , "Module" * 2.25 )',
]


def _plan(recipe, spec=PINNED):
    return SPUR.plan(spec, SPUR.derive(spec), recipe, r"C:\Templates\Part.PRTDOT", r"C:\Gears\Gear_m1.5_N25.SLDPRT")


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_both_recipes_make_a_sound_plan(recipe):
    assert _plan(recipe).check() == []


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_the_users_ten_variables_come_first_verbatim_and_in_order(recipe):
    plan = _plan(recipe)
    texts = [f'"{op.name}"= {op.expression}' for op in plan.ops if isinstance(op, AddGlobal)]
    assert texts[:10] == USERS_TEN
    assert len(texts) == 24
    first_global = next(i for i, op in enumerate(plan.ops) if isinstance(op, AddGlobal))
    first_sketch = next(i for i, op in enumerate(plan.ops) if isinstance(op, OpenSketch))
    assert first_global == 1 and all(isinstance(op, AddGlobal) for op in plan.ops[1:25]) and first_sketch > 24


@pytest.mark.parametrize("recipe,manual", [("A", 1), ("B", 1)])
def test_the_manual_steps_are_counted_per_recipe(recipe, manual):
    steps = _plan(recipe).manual_steps()
    assert len(steps) == manual
    assert steps[0].cause == "material"


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_every_dimension_the_plan_makes_is_linked(recipe):
    plan = _plan(recipe)
    made = {op.name for op in plan.ops if isinstance(op, Dimension)} | {"Width", "Count"}
    linked = {op.dimension.split("@")[0] for op in plan.ops if isinstance(op, LinkDimension)}
    assert made == linked


def test_the_plan_starts_new_ends_saved_and_rebuilds_once():
    plan = _plan("A")
    assert isinstance(plan.ops[0], NewPart)
    assert isinstance(plan.ops[-1], SaveAs)
    assert isinstance(plan.ops[-2], Rebuild)
    assert sum(isinstance(op, Rebuild) for op in plan.ops) == 1


def test_no_bore_means_no_bore_feature_but_the_global_stays():
    plan = _plan("A", PINNED.with_values(bore=""))
    assert not any(isinstance(op, LinkDimension) and op.dimension.startswith("Bore@") for op in plan.ops)
    assert any(isinstance(op, AddGlobal) and op.name == "Bore Diameter" and op.expression == "0" for op in plan.ops)
    assert plan.check() == []


def test_a_plan_with_things_out_of_order_is_caught():
    good = _plan("A")
    ops = list(good.ops)
    link = next(i for i, op in enumerate(ops) if isinstance(op, LinkDimension))
    ops.insert(1, ops.pop(link))                       # a link before its dimension exists
    ops.insert(-1, ManualStep("x", "y"))               # something after the rebuild
    ops.append(Rebuild())                              # and a second rebuild, after the save
    problems = BuildPlan("spur", "A", tuple(ops)).check()
    assert any("before anything is named" in p for p in problems)
    assert any("SaveAs must be the last step" in p for p in problems)
    assert any("rebuilds exactly once" in p for p in problems)


def test_a_global_referring_forward_is_caught():
    ops = list(_plan("A").ops)
    ops[1], ops[5] = ops[5], ops[1]
    problems = BuildPlan("spur", "A", tuple(ops)).check()
    assert any("before it is defined" in p for p in problems)


def test_the_dry_run_log_counts_manual_steps_and_lists_globals_first():
    lines = _plan("A").log_lines()
    assert lines[1] == "globals 24"
    assert lines[2].startswith("MANUAL  1 step")
    assert lines[4] == 'global  "No. of Teeth"= 25'


def test_later_kinds_are_named_so_the_window_can_grey_them():
    assert PLANNED_KINDS == ()
    assert set(KINDS) == {"spur", "helical", "herringbone", "bevel"}


def test_the_material_step_names_the_file_the_plan_saves():
    spec = GearSpec()
    plan = SPUR.plan(spec, SPUR.derive(spec), "A", "", r"C:\Gears\Pinion_m1.5_N20.SLDPRT")
    assert plan.manual_steps()[0].text == "Assign a material to Pinion_m1.5_N20; the build leaves it unset."
    unsaved = SPUR.plan(spec, SPUR.derive(spec), "A", "", "")
    assert "Gear_m1.5_N25" in unsaved.manual_steps()[0].text
