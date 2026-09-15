"""The build's order, against a fake SolidWorks that records every call."""

import pytest

from gear_generator import swbuild
from gear_generator.gears import KINDS
from gear_generator.gears.base import BuildPlan, CloseSketch, Dimension, LinkDimension, SaveAs
from gear_generator.gears.equations import DEGREES, RADIANS, split_equation
from gear_generator.spec import GearSpec
from gear_generator.swcom import DocInfo, SolidWorksError

SPUR = KINDS["spur"]
PATH = r"C:\Gears\Gear_m1.5_N25.SLDPRT"


class FakeSolidWorks:
    def __init__(self, trig=DEGREES, fail_on=None, rename=None, rebuild_ok=True, statuses=None, values=None):
        self.revision = (34, 0, 0)
        self.calls = []
        self.trig = trig
        self.fail_on = fail_on or {}
        self.rename = rename or {}
        self.rebuild_ok = rebuild_ok
        self.statuses = statuses or {}
        self.values_override = values or {}
        self.suppressed = False
        self.equations_text = []
        self.active = None
        self.handles = set()

    def _log(self, name, *args):
        self.calls.append((name, args))
        reason = self.fail_on.get(name)
        if reason and (not isinstance(reason, tuple) or reason[0] in args):
            raise SolidWorksError(reason if isinstance(reason, str) else reason[1])

    def active_document(self):
        return self.active

    def begin_build(self):
        self._log("begin_build")

    def end_build(self):
        self._log("end_build")

    def new_part(self, template=""):
        self._log("new_part", template)
        self.equations_text = []
        return DocInfo(title="Part1", path="", doc_type=1)

    def new_assembly(self, template=""):
        self._log("new_assembly", template)
        self.equations_text = []
        return DocInfo(title="Assem1", path="", doc_type=2)

    def document_path(self):
        return ""

    def set_rebuild_suppressed(self, suppressed):
        self._log("suppress", suppressed)
        self.suppressed = suppressed

    def rebuild(self):
        self._log("rebuild", self.suppressed)
        return self.rebuild_ok

    def save_as(self, path):
        self._log("save_as", path)
        return path

    def detect_trig_units(self):
        self._log("detect_trig_units")
        return self.trig

    def add_global_variable(self, name, expression):
        self._log("add_global_variable", name, expression)
        self.equations_text.append(f'"{name}"= {expression}')
        return len(self.equations_text) - 1

    def set_global_variable(self, name, expression):
        self._log("set_global_variable", name, expression)
        for i, text in enumerate(self.equations_text):
            if split_equation(text)[0] == name:
                self.equations_text[i] = f'"{name}"= {expression}'

    def link_dimension(self, dimension, expression):
        self._log("link_dimension", dimension, expression)
        return 0

    def equations(self):
        return [(text, 0.0) for text in self.equations_text]

    def equation_values(self):
        from gear_generator.gears.equations import evaluate_all
        values = evaluate_all([split_equation(t) for t in self.equations_text], self.trig)
        values.update(self.values_override)
        return values

    def insert_axis(self, handle, name, planes):
        self._log("insert_axis", handle, name)
        return self.rename.get(name, name)

    def open_sketch(self, handle, plane):
        self._log("open_sketch", handle, plane)

    def close_sketch(self, handle, name):
        self._log("close_sketch", handle, name)
        return self.rename.get(name, name)

    def sketch_status(self, name):
        return self.statuses.get(name, 3)

    def sketch_circle(self, handle, centre, radius, construction=False):
        self._log("sketch_circle", handle)

    def sketch_arc(self, handle, centre, start, end, direction=1, construction=False):
        self._log("sketch_arc", handle)

    def sketch_line(self, handle, start, end, construction=False):
        self._log("sketch_line", handle)

    def sketch_point(self, handle, at):
        self._log("sketch_point", handle)

    def sketch_equation_curve(self, handle, x, y, t1, t2, start, end):
        self._log("sketch_equation_curve", handle)

    def add_relation(self, kind, refs):
        self._log("add_relation", kind, *refs)
        return "already one point" if refs == ("L+.start", "I+.start") else ""

    def dimension(self, name, refs, at):
        self._log("dimension", name)
        return self.rename.get(name, name)

    def extrude(self, handle, sketch, name, depth, depth_dim):
        self._log("extrude", name)
        return self.rename.get(name, name), depth_dim

    def cut_extrude(self, handle, sketch, name):
        self._log("cut_extrude", name)
        return self.rename.get(name, name)

    def circular_pattern(self, handle, name, axis, feature, count, count_dim):
        self._log("circular_pattern", name, count)
        return self.rename.get(name, name), count_dim

    def ref_plane(self, handle, name, plane, offset, flip, offset_dim):
        self._log("ref_plane", name, round(offset, 6), flip)
        return self.rename.get(name, name), offset_dim

    def sweep_cut(self, handle, profile, path, name, twist, reverse, twist_dim):
        self._log("sweep_cut", name, round(twist, 6), reverse)
        return self.rename.get(name, name), twist_dim

    def mirror_body(self, handle, name, plane):
        self._log("mirror_body", name, plane)
        return self.rename.get(name, name)

    def add_component(self, handle, path, at):
        self._log("add_component", handle, path)
        return f"{handle}-1"

    def fix_component(self, handle):
        self._log("fix_component", handle)

    def add_mate(self, handle, kind, a, b, value=0.0, name=""):
        self._log("add_mate", kind, a, b)
        return (name or f"Mate{len(self.calls)}"), ("D7" if kind in ("distance", "angle") else "")


def plan(spec=None, recipe="A", path=PATH):
    spec = spec or GearSpec()
    return SPUR.plan(spec, SPUR.derive(spec), recipe, "", path)


def names(fake):
    return [name for name, _ in fake.calls]


def never_exists(_path):
    return False


# -- order ------------------------------------------------------------------


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_a_clean_build_suppresses_first_rebuilds_once_then_saves(recipe):
    fake = FakeSolidWorks()
    result = swbuild.build(fake, plan(recipe=recipe), never_exists)
    called = names(fake)
    assert result.ok, result.failures
    assert called[:3] == ["begin_build", "new_part", "detect_trig_units"]
    first_geometry = next(i for i, n in enumerate(called) if n in ("insert_axis", "open_sketch"))
    assert called.index("suppress") < first_geometry
    assert called.count("rebuild") == 1
    assert fake.calls[called.index("rebuild")] == ("rebuild", (False,))
    assert called[-1] == "save_as" and called.index("rebuild") < called.index("save_as")
    assert result.saved == PATH
    assert "ok      rebuilt once" in result.log_lines()


def test_every_global_is_added_before_any_link():
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(), never_exists)
    called = names(fake)
    last_global = max(i for i, n in enumerate(called) if n == "add_global_variable")
    first_link = called.index("link_dimension")
    assert last_global < first_link
    assert called.count("add_global_variable") == 24


def test_the_measured_trig_units_choose_the_expressions():
    fake = FakeSolidWorks(trig=RADIANS)
    result = swbuild.build(fake, plan(), never_exists)
    base = next(args for name, args in fake.calls if name == "add_global_variable" and args[0] == "Base Diameter")
    assert "180" in base[1] and result.ok and result.trig == RADIANS


def test_manual_steps_are_counted_in_the_log():
    result = swbuild.build(FakeSolidWorks(), plan(), never_exists)
    lines = result.log_lines()
    assert "MANUAL  1 step(s) to do by hand" in lines
    assert any(line.startswith("MANUAL  Assign a material") for line in lines)


# -- failures ----------------------------------------------------------------


def test_the_flag_is_restored_and_the_build_stops_at_the_failing_op():
    fake = FakeSolidWorks(fail_on={"cut_extrude": "FeatureCut4 would not cut the tooth space."})
    result = swbuild.build(fake, plan(), never_exists)
    called = names(fake)
    assert not result.ok
    assert result.stopped_at.startswith("cut ")
    assert result.failures[0][1] == "FeatureCut4 would not cut the tooth space."
    assert "circular_pattern" not in called
    assert fake.suppressed is False
    assert called.count("rebuild") == 1
    assert "save_as" not in called
    assert called[-1] == "end_build"
    assert any(line.startswith("FAIL    cut") for line in result.log_lines())


def test_a_raise_that_is_not_a_solidworks_error_still_restores_the_flag():
    fake = FakeSolidWorks()

    def boom(*_args):
        raise RuntimeError("the COM server went away")

    fake.sketch_circle = boom
    with pytest.raises(RuntimeError):
        swbuild.build(fake, plan(), never_exists)
    assert fake.suppressed is False
    assert names(fake)[-1] == "end_build"


def test_a_name_solidworks_did_not_keep_stops_before_the_link_that_uses_it():
    fake = FakeSolidWorks(rename={"Blank Sketch": "Sketch1"})
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.ok
    assert "'Sketch1' instead of 'Blank Sketch'" in result.failures[0][1]
    assert "link_dimension" not in names(fake)
    assert "save_as" not in names(fake)


def test_a_global_that_disagrees_with_the_maths_fails_and_is_not_saved():
    fake = FakeSolidWorks(values={"Base Diameter": 12.0})
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.ok and "Base Diameter" in result.failures[0][0]
    assert "save_as" not in names(fake)


def test_a_failed_rebuild_is_not_saved():
    fake = FakeSolidWorks(rebuild_ok=False)
    result = swbuild.build(fake, plan(), never_exists)
    assert "save_as" not in names(fake)
    assert "FAIL    the rebuild reported an error" in result.log_lines()


def test_an_under_defined_sketch_is_a_check_not_a_failure():
    fake = FakeSolidWorks(statuses={"Tooth Space Sketch": 2})
    result = swbuild.build(fake, plan(), never_exists)
    assert result.ok and result.saved
    assert "CHECK   Tooth Space Sketch is under-defined, not fully defined" in result.log_lines()


def test_an_existing_file_is_refused_before_anything_is_made():
    fake = FakeSolidWorks()
    with pytest.raises(swbuild.BuildError, match="already exists"):
        swbuild.build(fake, plan(), lambda path: True)
    assert fake.calls == []


def test_an_old_solidworks_is_refused():
    fake = FakeSolidWorks()
    fake.revision = (33, 5, 0)
    with pytest.raises(swbuild.BuildError, match="2026"):
        swbuild.build(fake, plan(), never_exists)


def test_an_unsound_plan_is_refused():
    good = plan()
    broken = BuildPlan(good.kind, good.recipe, good.ops[:-2] + (SaveAs(PATH),), good.path)
    with pytest.raises(swbuild.BuildError, match="not sound"):
        swbuild.build(FakeSolidWorks(), broken, never_exists)


# -- kept names ---------------------------------------------------------------


def test_the_reported_features_and_dimensions_are_the_kept_ones():
    result = swbuild.build(FakeSolidWorks(), plan(), never_exists)
    assert result.features[:3] == ["Gear Axis", "Blank Sketch", "Blank"]
    assert result.dimensions["OD@Blank Sketch"] == "OD@Blank Sketch"
    assert result.dimensions["Width@Blank"] == "Width@Blank"
    assert result.dimensions["Count@Teeth"] == "Count@Teeth"


# -- pairs ---------------------------------------------------------------------


def _assembly_plan():
    from gear_generator.gears import base
    return BuildPlan("pair", "", (
        base.NewAssembly(""),
        base.AddGlobal("Centre Distance", "60"),
        base.AddComponent("gear1", r"C:\g\a.SLDPRT"),
        base.AddComponent("gear2", r"C:\g\b.SLDPRT", (60.0, 0.0, 0.0)),
        base.Fix("gear1"),
        base.Mate("dist", "distance", "gear2:Gear Axis", "gear1:plane3", 60.0, "Centre Distance"),
        base.LinkDimension("D1@Centre Distance", '"Centre Distance"'),
        base.Rebuild(),
        base.SaveAs(r"C:\g\Pair.SLDASM"),
    ), r"C:\g\Pair.SLDASM")


def test_a_pair_builds_both_parts_then_the_assembly_linking_the_kept_dimension():
    fake = FakeSolidWorks()
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok, result.log_lines()
    assert names(fake).count("new_part") == 2 and names(fake).count("new_assembly") == 1
    link = [args for name, args in fake.calls if name == "link_dimension"][-1]
    assert link == ("D7@Centre Distance", '"Centre Distance"')


def test_a_pair_skips_the_assembly_when_a_part_fails():
    fake = FakeSolidWorks(fail_on={"circular_pattern": "no pattern"})
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert not result.ok
    assert result.gear_b is None and result.assembly is None
    assert "new_assembly" not in names(fake)
    assert "SKIPPED" in result.log_lines()[-1]


# -- update values ---------------------------------------------------------------


def _built_fake(spec):
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(spec), never_exists)
    fake.calls.clear()
    fake.active = DocInfo(title="Gear_m1.5_N25.SLDPRT", path=PATH, doc_type=1)
    return fake


def test_update_values_changes_only_what_differs_in_one_rebuild():
    spec = GearSpec()
    fake = _built_fake(spec)
    wanted = spec.with_values(teeth="40")
    variables = SPUR.variables(wanted, SPUR.derive(wanted))
    result = swbuild.update_variables(fake, variables, PATH.lower())
    assert result.ok and result.changed == ["No. of Teeth"]
    assert names(fake).count("rebuild") == 1
    assert names(fake).index("suppress") < names(fake).index("set_global_variable")
    assert fake.suppressed is False


def test_update_values_refuses_the_wrong_document():
    fake = _built_fake(GearSpec())
    fake.active = DocInfo(title="Other.SLDPRT", path=r"C:\Other.SLDPRT", doc_type=1)
    with pytest.raises(swbuild.BuildError, match="Other.SLDPRT"):
        swbuild.update_variables(fake, SPUR.variables(GearSpec(), SPUR.derive(GearSpec())), PATH)
    assert "set_global_variable" not in names(fake)


def test_update_values_refuses_a_part_without_the_globals():
    fake = FakeSolidWorks()
    fake.active = DocInfo(title="Gear.SLDPRT", path=PATH, doc_type=1)
    with pytest.raises(swbuild.BuildError, match="not in this part"):
        swbuild.update_variables(fake, SPUR.variables(GearSpec(), SPUR.derive(GearSpec())), PATH)


def test_nothing_to_change_means_no_rebuild():
    spec = GearSpec()
    fake = _built_fake(spec)
    result = swbuild.update_variables(fake, SPUR.variables(spec, SPUR.derive(spec)), PATH)
    assert result.changed == [] and "rebuild" not in names(fake)


@pytest.mark.parametrize("built,wanted,word", [
    ({"kind": "spur", "recipe": "A", "bore": "10"}, {"kind": "spur", "recipe": "B", "bore": "10"}, "recipe"),
    ({"kind": "spur", "recipe": "A", "bore": "10"}, {"kind": "spur", "recipe": "A", "bore": ""}, "bore"),
    ({"kind": "spur", "recipe": "A", "bore": ""}, {"kind": "spur", "recipe": "A", "bore": "0"}, ""),
    ({"kind": "spur", "recipe": "A", "bore": "8"}, {"kind": "spur", "recipe": "A", "bore": "12"}, ""),
])
def test_structural_changes_are_named(built, wanted, word):
    text = swbuild.structural_change(built, wanted)
    assert (word in text.lower()) if word else text == ""


def test_a_relation_that_already_holds_is_logged_as_such():
    result = swbuild.build(FakeSolidWorks(), plan(recipe="A"), never_exists)
    assert "ok      coincident L+.start I+.start (already one point)" in result.log_lines()
