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


def _key(path):
    return path.replace("/", "\\").lower()


class FakeSolidWorks:
    """Records every call. ``fail_on`` maps a call's name to a sentence it raises (or ``(arg, sentence)`` to
    raise only when that argument is passed).

    W4's members are configurable from the start: ``open_docs`` are the
    documents open before the job (``documents()``); a saved document keeps
    its globals and the planes and axes it made, and ``open_document`` brings
    them back, so ``planned_changes`` and ``feature_names`` see what a build
    left; ``missing_components`` are Name2s ``find_component`` will not find;
    ``frames`` maps a handle to the (rotation, at) ``component_frame`` reads,
    and ``place_component`` writes it; ``clashes`` is what ``interferences()``
    returns.
    """

    def __init__(self, trig=DEGREES, fail_on=None, rename=None, rebuild_ok=True, statuses=None, values=None,
                 interference=(0, 0.0), open_docs=(), missing_components=(), frames=None, clashes=()):
        self.interference = interference
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
        self.open_docs = list(open_docs)
        self.missing_components = set(missing_components)
        self.frames = dict(frames or {})
        self.clashes = list(clashes)
        self.made = []                 # planes and axes made in the current document, by kept name
        self.saved = {}                # lower-cased path -> (equations_text, made) as saved

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
        self.equations_text, self.made = [], []
        return DocInfo(title="Part1", path="", doc_type=1)

    def new_assembly(self, template=""):
        self._log("new_assembly", template)
        self.equations_text, self.made = [], []
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
        self.saved[_key(path)] = (self.equations_text, self.made)
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
        self._log("insert_axis", handle, name, tuple(planes))
        kept = self.rename.get(name, name)
        self.made.append(kept)
        return kept

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
        kept = self.rename.get(name, name)
        self.made.append(kept)
        return kept, offset_dim

    def sweep_cut(self, handle, profile, path, name, twist, reverse, twist_dim):
        self._log("sweep_cut", name, round(twist, 6), reverse)
        return self.rename.get(name, name), twist_dim

    def mirror_body(self, handle, name, plane):
        self._log("mirror_body", name, plane)
        return self.rename.get(name, name)

    def ref_plane_normal(self, handle, name, line, point):
        self._log("ref_plane_normal", name, line, point)
        return self.rename.get(name, name)

    def revolve(self, handle, sketch, name, axis):
        self._log("revolve", name, axis)
        return self.rename.get(name, name)

    def loft_cut(self, handle, name, profiles):
        self._log("loft_cut", name, *profiles)
        return self.rename.get(name, name)

    def add_component(self, handle, path, at):
        self._log("add_component", handle, path)
        return f"{handle}-1"

    def fix_component(self, handle):
        self._log("fix_component", handle)

    def unfix_component(self, handle):
        self._log("unfix_component", handle)

    def add_mate(self, handle, kind, a, b, value=0.0, name="", ratio=(1.0, 1.0), flip=False):
        self._log("add_mate", kind, a, b, *((ratio, flip) if kind == "gear" else ()))
        return (name or f"Mate{len(self.calls)}"), ("D7" if kind in ("distance", "angle", "axis angle",
                                                                    "point distance") else "")

    def place_component(self, handle, rotation, at):
        self._log("place_component", handle)
        self.frames[handle] = (tuple(rotation), tuple(at))

    def interference_count(self):
        self._log("interference_count")
        return self.interference

    def set_custom_property(self, name, value):
        self._log("set_custom_property", name, value)

    # -- W4

    def documents(self):
        return list(self.open_docs)

    def feature_names(self):
        return list(self.made)

    def open_document(self, path):
        self._log("open_document", path)
        doc_type = 2 if path.lower().endswith(".sldasm") else 1
        info = DocInfo(title=path.replace("/", "\\").rsplit("\\", 1)[-1], path=path, doc_type=doc_type)
        self.equations_text, self.made = self.saved.get(_key(path), ([], []))
        if not any(_key(d.path) == _key(path) for d in self.open_docs):
            self.open_docs.append(info)
        self.active = info
        return info

    def find_component(self, handle, name):
        self._log("find_component", handle, name)
        if name in self.missing_components:
            title = self.active.title if self.active else "the assembly"
            raise SolidWorksError(f"{name} is not in {title} any more: it was renamed or deleted in SolidWorks.")
        return name

    def component_frame(self, handle):
        self._log("component_frame", handle)
        return self.frames.get(handle, ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0)))

    def interferences(self):
        self._log("interferences")
        return list(self.clashes)


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
    fake.revision = (31, 5, 0)
    with pytest.raises(swbuild.BuildError, match="2024"):
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


def test_a_clean_pair_is_checked_for_interference_after_the_assembly():
    fake = FakeSolidWorks()
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok and names(fake)[-1] == "interference_count"
    assert "no interference between the gears" in result.assembly.done
    assert not result.assembly.checks


def test_interfering_teeth_are_a_check_not_a_failure():
    fake = FakeSolidWorks(interference=(3, 12.5))
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok
    assert result.assembly.checks == ["the gears interfere in 3 places, 12.500 mm³; look along the gear axis at the mesh"]
    assert "CHECK   the gears interfere in 3 places, 12.500 mm³; look along the gear axis at the mesh" \
        in result.log_lines()


def test_an_interference_check_that_raises_is_reported_and_the_pair_still_stands():
    fake = FakeSolidWorks(fail_on={"interference_count": "no manager"})
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok and result.assembly.checks == ["interference could not be checked: no manager"]


def test_a_pair_skips_the_assembly_when_a_part_fails():
    fake = FakeSolidWorks(fail_on={"circular_pattern": "no pattern"})
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert not result.ok
    assert result.gear_b is None and result.assembly is None
    assert "new_assembly" not in names(fake) and "interference_count" not in names(fake)
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


# -- W4 interfaces: an axis through planes made in the plan ---------------------------------


def _layout_like(axis_planes):
    from gear_generator.gears import base
    return BuildPlan("layout", "", (
        base.NewPart(""),
        base.RefPlane("x1", "S2 X Plane", 3, 63.75),
        base.Axis("axis1", "S2 Axis", axis_planes),
        base.Rebuild(),
        base.SaveAs(r"C:\g\R_Layout.SLDPRT"),
    ), r"C:\g\R_Layout.SLDPRT")


def test_an_axis_may_go_through_a_plane_made_earlier_by_its_id():
    assert _layout_like((2, "x1")).check() == []


def test_an_axis_through_a_plane_not_made_is_refused_with_a_sentence():
    problems = _layout_like((2, "x9")).check()
    assert "Axis 'axis1' is through 'x9', which is not a plane made earlier." in problems


def test_an_axis_is_described_by_plane_ids_and_tree_order_alike():
    from gear_generator.gears import base
    assert base.describe(base.Axis("a", "Gear Axis", (2, 3))) == "axis    'Gear Axis' through planes 2 and 3"
    assert base.describe(base.Axis("a", "S2 Axis", (2, "x1"))) == "axis    'S2 Axis' through plane 2 and x1"
    assert base.describe(base.Axis("a", "S2 Axis", ("y1", "x1"))) == "axis    'S2 Axis' through y1 and x1"


def test_the_runner_hands_the_axis_its_planes_as_planned():
    fake = FakeSolidWorks()
    result = swbuild.build(fake, _layout_like((2, "x1")), never_exists)
    assert result.ok, result.log_lines()
    assert ("insert_axis", ("axis1", "S2 Axis", (2, "x1"))) in fake.calls


def test_the_strips_own_axis_still_goes_through_planes_2_and_3():
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(), never_exists)
    assert ("insert_axis", ("axis", "Gear Axis", (2, 3))) in fake.calls


# -- W4 interfaces: what an assembly kept, frames, same-named documents, progress ----------------


def test_an_assembly_build_records_the_name_each_component_kept():
    result = swbuild.build(FakeSolidWorks(), _assembly_plan(), never_exists)
    assert result.components == {"gear1": "gear1-1", "gear2": "gear2-1"}


IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _turned(degrees, flipped=False):
    import math
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    rows = ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
    if flipped:                                  # rot_x(180) · rot_z: a part on a Z- shaft
        rows = (rows[0], tuple(-v for v in rows[1]), tuple(-v for v in rows[2]))
    return tuple(v for row in rows for v in row)


@pytest.mark.parametrize("flipped", [False, True])
def test_a_gear_turned_whole_pitches_is_the_same_placement(flipped):
    at = (63.75, 0.0, 5.0)
    pitch = 360.0 / 68
    assert swbuild.same_frame(_turned(10, flipped), at, _turned(10 + 3 * pitch, flipped), at, pitch)
    assert swbuild.same_frame(_turned(10, flipped), at, _turned(10 - pitch, flipped), at, pitch)
    assert not swbuild.same_frame(_turned(10, flipped), at, _turned(10 + pitch / 2, flipped), at, pitch)
    assert not swbuild.same_frame(_turned(10, flipped), at, _turned(10 + pitch, flipped), at)   # no pitch: exact


def test_a_frame_moved_or_tipped_is_not_the_same_placement():
    assert swbuild.same_frame(IDENTITY, (0.0, 0.0, 0.0), IDENTITY, (0.0, 0.0, 5e-7))
    assert not swbuild.same_frame(IDENTITY, (0.0, 0.0, 0.0), IDENTITY, (0.0, 2e-6, 0.0))
    assert not swbuild.same_frame(_turned(0), (0, 0, 0), _turned(0, flipped=True), (0, 0, 0), 360.0 / 17)


def test_a_document_of_the_same_name_open_from_another_folder_is_found():
    docs = [DocInfo("Gear_m1.5_N17.SLDPRT", r"C:\Other\Gear_m1.5_N17.SLDPRT", 1),
            DocInfo("Gear_m1.5_N68.SLDPRT", r"C:\Parts\R\Gear_m1.5_N68.SLDPRT", 1),
            DocInfo("Part1", "", 1)]
    wanted = [r"C:\Parts\R\gear_m1.5_n17.SLDPRT", r"c:\parts\r\Gear_m1.5_N68.SLDPRT"]
    assert swbuild.same_named_elsewhere(docs, wanted) == [(docs[0].path, wanted[0])]


def test_progress_is_one_step_per_job_never_a_shared_default():
    first, second = swbuild.Progress(), swbuild.Progress()
    first.say(swbuild.Step(swbuild.STAGE_PART, "Gear_m1.5_N68", 2, 4))
    assert first.step == swbuild.Step("part", "Gear_m1.5_N68", 2, 4) and second.step is None


def test_the_fake_reopens_a_saved_document_holding_what_it_was_saved_with():
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(), never_exists)
    swbuild.build(fake, _layout_like((2, "x1")), never_exists)
    fake.open_document(PATH)
    assert swbuild.planned_changes(fake.equations(), SPUR.variables(GearSpec(), SPUR.derive(GearSpec())),
                                   DEGREES) == []
    assert fake.active.path == PATH and fake.documents()[-1].title == "Gear_m1.5_N25.SLDPRT"
    fake.open_document(r"C:\g\R_Layout.SLDPRT")
    assert fake.feature_names() == ["S2 X Plane", "S2 Axis"]
