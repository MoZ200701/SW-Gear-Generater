"""Decisions from canned probe results: the plan's rules, pinned."""

from gear_generator.probe import decide


def records(passing=(), failing=(), facts=None):
    out = {name: {"status": "pass", "facts": {}} for name in passing}
    out.update({name: {"status": "fail", "facts": {}} for name in failing})
    for name, values in (facts or {}).items():
        out.setdefault(name, {"status": "pass", "facts": {}})["facts"].update(values)
    return out


EQUATIONS = ("equation_add", "equation_syntax", "equation_set")
CURVES = ("curve_literal", "curve_globals", "curve_rebuild")
SKETCHES = ("sketch_entities", "relations", "dimension_link")


def test_everything_passing_decides_the_involute():
    assert decide.flank_recipe(records(EQUATIONS + CURVES + SKETCHES)) == "A"


def test_curves_that_cannot_follow_a_rebuild_fall_back_to_arcs():
    assert decide.flank_recipe(records(EQUATIONS + SKETCHES + ("curve_literal", "curve_globals"),
                                       failing=("curve_rebuild",))) == "B"


def test_no_equations_means_stop_whatever_else_works():
    assert decide.flank_recipe(records(CURVES + SKETCHES + ("equation_add",), failing=("equation_syntax",))) == "STOP"


def test_neither_recipe_possible_means_stop_not_a_guess():
    assert decide.flank_recipe(records(EQUATIONS + ("curve_literal", "sketch_entities"),
                                       failing=("curve_globals", "relations"))) == "STOP"


def test_a_decision_is_never_read_off_a_failed_probe():
    canned = records(failing=("relations",), facts={})
    canned["relations"]["facts"]["equal_radius_constraint"] = "sgEQUAL"
    assert decide.decide(canned)["equal_constraint"] is None


def test_the_cut_prefers_the_route_that_does_not_depend_on_direction():
    canned = records(facts={"cut": {"cut_routes_that_remove_the_hole": ["through all, direction flipped",
                                                                         "through all both"]}})
    assert decide.decide(canned)["cut_end_condition"] == 9


def test_units_are_set_only_when_the_template_is_not_millimetres_and_setting_works():
    inch = records(facts={"document_units": {"default_template_is_mm": False, "set_mmgs_works": True}})
    mm = records(facts={"document_units": {"default_template_is_mm": True, "set_mmgs_works": False}})
    assert decide.decide(inch)["set_units_mmgs_after_new"] is True
    assert decide.decide(mm)["set_units_mmgs_after_new"] is False
    assert decide.decide(records())["set_units_mmgs_after_new"] is None


def test_manual_steps_grow_with_what_did_not_work():
    assert decide.manual_steps(records(), "A") == ["material", "fully define the flank curves"]
    full = records(("curve_fixed_rebuild", "pattern", "pattern_count_link", "assembly_components_and_mates",
                    "assembly_distance_link"))
    assert decide.manual_steps(full, "A") == ["material"]
    unlinked = records(("curve_fixed_rebuild", "pattern", "assembly_components_and_mates"))
    assert decide.manual_steps(unlinked, "A") == [
        "material", "link Count@Teeth in Equations", "link the centre distance mate in Equations",
    ]


def test_every_decision_key_is_present_even_with_nothing_run():
    decided = decide.decide({})
    assert decided["flank_recipe"] == "STOP"
    for key in ("trig_default", "equation_add_call", "equation_set_route", "plane_select_route", "equal_constraint",
                "circle_dimension", "arc_dimension", "curve_trig", "curves_are_fixed", "shared_ends_are_one_point",
                "cut_end_condition",
                "pattern_count_dim_index", "save_as_overwrites", "first_component_fixed", "inverse_tangent",
                "extrude_z_sign", "top_sketch_y_is_minus_z", "ref_plane_unflipped_is_plus_z", "twist_turn",
                "twist_reverse_flips", "mirror_body_route"):
        assert key in decided and decided[key] is None, key


HELIX = ("equation_inverse_trig", "sweep_twist", "sweep_twist_link", "sweep_cut_ends")


def test_the_helix_is_a_twisted_sweep_when_the_twist_links_and_cuts_exactly():
    assert decide.helix_route(records(HELIX)) == "twist"
    assert decide.herringbone_route(records(HELIX + ("mirror_body_merge",))) == "mirror"


def test_an_unlinkable_twist_falls_back_to_a_helix_guide_and_nothing_else():
    unlinked = HELIX[:2] + HELIX[3:]
    assert decide.helix_route(records(unlinked + ("helix_guide",), failing=("sweep_twist_link",))) == "guide"
    assert decide.helix_route(records(unlinked, failing=("sweep_twist_link",))) == "STOP"


def test_no_atn_or_no_mirror_stops_rather_than_guessing():
    assert decide.helix_route(records(HELIX[1:], failing=("equation_inverse_trig",))) == "STOP"
    assert decide.herringbone_route(records(HELIX, failing=("mirror_body_merge",))) == "STOP"
