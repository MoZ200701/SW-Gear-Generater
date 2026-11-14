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

    For W4's own tests: ``frames`` may also be keyed by a component's Name2
    (what ``find_component`` was asked for), and ``place_component`` writes
    both; ``exists`` answers "is it on disk" from what was saved (or put in
    ``saved`` by a test), so a job's pre-flight sees what an earlier job left.

    For the W4 review's: ``raises`` maps a call's name to ``(n, exception)``:
    the n-th call of that name raises that exception, whatever its type (a
    stand-in for ``pywintypes.com_error`` or anything unexpected, part-way
    through a job). ``touched`` collects the saved documents (lower-cased
    paths) a call has modified since they were opened — an equation added or
    deleted (the trig check), a global set, a component moved, a rebuild —
    so a test can see which documents SolidWorks would now mark modified.
    Every feature a build makes (not only planes and axes) is kept with the
    saved document, so ``feature_names`` on a reopened part lists them.
    """

    def __init__(self, trig=DEGREES, fail_on=None, rename=None, rebuild_ok=True, statuses=None, values=None,
                 interference=(0, 0.0), open_docs=(), missing_components=(), frames=None, clashes=(), raises=None):
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
        self.found = {}                # handle -> the Name2 find_component found it by
        self.raises = dict(raises or {})
        self.counts = {}
        self.current = ""              # the document calls act on: an opened or saved path, "" for a new one
        self.touched = set()

    def _log(self, name, *args):
        self.calls.append((name, args))
        self.counts[name] = self.counts.get(name, 0) + 1
        planned = self.raises.get(name)
        if planned is not None and planned[0] == self.counts[name]:
            raise planned[1]
        reason = self.fail_on.get(name)
        if reason and (not isinstance(reason, tuple) or reason[0] in args):
            raise SolidWorksError(reason if isinstance(reason, str) else reason[1])

    def active_document(self):
        return self.active

    def begin_build(self):
        self._log("begin_build")

    def end_build(self):
        self._log("end_build")

    def _touch(self):
        if self.current:
            self.touched.add(_key(self.current))

    def new_part(self, template=""):
        self._log("new_part", template)
        self.equations_text, self.made, self.current = [], [], ""
        return DocInfo(title="Part1", path="", doc_type=1)

    def new_assembly(self, template=""):
        self._log("new_assembly", template)
        self.equations_text, self.made, self.current = [], [], ""
        return DocInfo(title="Assem1", path="", doc_type=2)

    def document_path(self):
        return ""

    def set_rebuild_suppressed(self, suppressed):
        self._log("suppress", suppressed)
        self.suppressed = suppressed

    def rebuild(self):
        self._log("rebuild", self.suppressed)
        self._touch()
        return self.rebuild_ok

    def save_as(self, path):
        self._log("save_as", path)
        self.saved[_key(path)] = (self.equations_text, self.made)
        self.current = path
        self.touched.discard(_key(path))
        return path

    def detect_trig_units(self):
        self._log("detect_trig_units")
        self._touch()                  # it adds an equation and deletes it: SolidWorks marks the document modified
        return self.trig

    def add_global_variable(self, name, expression):
        self._log("add_global_variable", name, expression)
        self.equations_text.append(f'"{name}"= {expression}')
        return len(self.equations_text) - 1

    def set_global_variable(self, name, expression):
        self._log("set_global_variable", name, expression)
        self._touch()
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

    def _made(self, name):
        kept = self.rename.get(name, name)
        self.made.append(kept)
        return kept

    def close_sketch(self, handle, name):
        self._log("close_sketch", handle, name)
        return self._made(name)

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
        return self._made(name), depth_dim

    def cut_extrude(self, handle, sketch, name):
        self._log("cut_extrude", name)
        return self._made(name)

    def circular_pattern(self, handle, name, axis, feature, count, count_dim):
        self._log("circular_pattern", name, count)
        return self._made(name), count_dim

    def ref_plane(self, handle, name, plane, offset, flip, offset_dim):
        self._log("ref_plane", name, round(offset, 6), flip)
        kept = self.rename.get(name, name)
        self.made.append(kept)
        return kept, offset_dim

    def sweep_cut(self, handle, profile, path, name, twist, reverse, twist_dim):
        self._log("sweep_cut", name, round(twist, 6), reverse)
        return self._made(name), twist_dim

    def mirror_body(self, handle, name, plane):
        self._log("mirror_body", name, plane)
        return self._made(name)

    def ref_plane_normal(self, handle, name, line, point):
        self._log("ref_plane_normal", name, line, point)
        return self._made(name)

    def revolve(self, handle, sketch, name, axis):
        self._log("revolve", name, axis)
        return self._made(name)

    def loft_cut(self, handle, name, profiles):
        self._log("loft_cut", name, *profiles)
        return self._made(name)

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
        self._touch()
        self.frames[handle] = (tuple(rotation), tuple(at))
        if handle in self.found:
            self.frames[self.found[handle]] = (tuple(rotation), tuple(at))

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
        self.current = path
        if not any(_key(d.path) == _key(path) for d in self.open_docs):
            self.open_docs.append(info)
        self.active = info
        return info

    def find_component(self, handle, name):
        self._log("find_component", handle, name)
        if name in self.missing_components:
            title = self.active.title if self.active else "the assembly"
            raise SolidWorksError(f"{name} is not in {title} any more: it was renamed or deleted in SolidWorks.")
        self.found[handle] = name
        return name

    def component_frame(self, handle):
        self._log("component_frame", handle)
        identity = ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
        return self.frames.get(handle, self.frames.get(self.found.get(handle), identity))

    def interferences(self):
        self._log("interferences")
        return list(self.clashes)

    def exists(self, path):
        return _key(path) in self.saved


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


def test_a_raise_that_is_not_a_solidworks_error_is_a_failure_and_still_restores_the_flag():
    """W4 review B1: once the document is made, build() keeps its word that every problem is a failure."""
    fake = FakeSolidWorks()

    def boom(*_args):
        raise RuntimeError("the COM server went away")

    fake.sketch_circle = boom
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.ok and result.document == "Part1" and not result.saved
    assert result.failures == [("the build", "it stopped on an unexpected RuntimeError: the COM server went away.")]
    assert fake.suppressed is False
    assert names(fake)[-1] == "end_build" and "save_as" not in names(fake)


def test_a_save_that_raises_anything_is_the_saves_failure():
    fake = FakeSolidWorks()

    def gone(_path):
        raise RuntimeError("(-2147023170, 'The remote procedure call failed.', None, None)")

    fake.save_as = gone
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.saved and result.failures[0][0] == "save"
    assert result.failures[0][1].startswith("it stopped on an unexpected RuntimeError: ")


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


# -- W4: build_gearbox ----------------------------------------------------------------------------


from gear_generator import findings  # noqa: E402
from gear_generator.gears import base as ops  # noqa: E402
from gear_generator.gears.base import GlobalVariable  # noqa: E402

W = "C:\\W\\"
P17, P68, P68B = W + "Gear_m1.5_N17.SLDPRT", W + "Gear_m1.5_N68.SLDPRT", W + "Gear_m1.5_N68_r2.SLDPRT"
LAYOUT, ASM = W + "R_Layout.SLDPRT", W + "R.SLDASM"
S17, S68 = GearSpec().with_values(teeth="17"), GearSpec().with_values(teeth="68")
AT2 = (63.75, 0.0, 0.0)
TURNED2 = _turned(180.0 / 68)


def _layout_plan(path=LAYOUT):
    return BuildPlan("layout", "", (
        ops.NewPart(""),
        ops.AddGlobal("S2 X", "63.75"),
        ops.RefPlane("x1", "S2 X Plane", 3, 63.75),
        ops.Axis("axis1", "S1 Axis", (2, 3)),
        ops.Axis("axis2", "S2 Axis", (2, "x1")),
        ops.Rebuild(),
        ops.SaveAs(path),
    ), path)


LAYOUT_VALUES = (GlobalVariable("S2 X", "63.75"),)
LAYOUT_FEATURES = ("S2 X Plane", "S1 Axis", "S2 Axis")


def _gearbox_assembly(parts=(P17, P68), layout=LAYOUT, path=ASM):
    steps = [ops.NewAssembly(""), ops.AddComponent("layout", layout), ops.Place("layout", IDENTITY, (0.0, 0.0, 0.0)),
             ops.Fix("layout")]
    frames = [(IDENTITY, (0.0, 0.0, 0.0)), (TURNED2, AT2)]
    for index, part in enumerate(parts, 1):
        rotation, at = frames[(index - 1) % 2]
        steps += [ops.AddComponent(f"gear{index}", part, at), ops.Place(f"gear{index}", rotation, at),
                  ops.Fix(f"gear{index}")]
    return BuildPlan("gearbox", "", tuple(steps) + (ops.Rebuild(), ops.SaveAs(path)), path)


def _values(spec):
    return tuple(SPUR.variables(spec, SPUR.derive(spec)))


def _record_steps():
    steps = []
    return steps, steps.append


GEARS = {"gear1": "G1", "gear2": "G2"}


def _build(fake=None, **kwargs):
    fake = fake or FakeSolidWorks()
    kwargs.setdefault("parts", [plan(S17, path=P17), plan(S68, path=P68)])
    kwargs.setdefault("layout", _layout_plan())
    kwargs.setdefault("assembly", _gearbox_assembly())
    kwargs.setdefault("gears", GEARS)
    kwargs.setdefault("exists", fake.exists)
    return fake, swbuild.build_gearbox(fake, **kwargs)


def _saved_part(fake, spec, path):
    """A part as an earlier build left it: built and saved, so the fake reopens it holding its globals."""
    swbuild.build(fake, plan(spec, path=path), fake.exists)
    fake.calls.clear()


def test_a_gearbox_builds_parts_then_layout_then_assembly_then_checks_interference():
    fake, result = _build()
    assert result.ok, result.log_lines()
    order = [n for n in names(fake) if n in ("new_part", "new_assembly", "interferences")]
    assert order == ["new_part", "new_part", "new_part", "new_assembly", "interferences"]
    assert [r.saved for r in result.parts.built] == [P17, P68]
    assert result.layout.saved == LAYOUT and result.assembly.saved == ASM
    assert result.components == {"layout": "layout-1", "gear1": "gear1-1", "gear2": "gear2-1"}
    lines = result.log_lines()
    assert lines[-1] == "ok      no interference between the gears"
    assert "open_document" not in names(fake) and "close_document" not in names(fake)


def test_the_progress_steps_come_in_the_pinned_order_with_stems_not_paths():
    fake = FakeSolidWorks()
    _saved_part(fake, S17, P17)
    steps, say = _record_steps()
    _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))], progress=say)
    assert steps == [swbuild.Step("check", "Gear_m1.5_N17", 1, 1), swbuild.Step("part", "Gear_m1.5_N68", 1, 1),
                     swbuild.Step("layout", "R_Layout"), swbuild.Step("assembly", "R"),
                     swbuild.Step("interference", "R")]


def test_a_progress_object_records_the_last_step_of_its_own_job():
    progress = swbuild.Progress()
    _build(progress=progress.say)
    assert progress.step == swbuild.Step("interference", "R")


@pytest.mark.parametrize("case,sentence", [
    ("new path exists", r"C:\W\Gear_m1.5_N68.SLDPRT already exists, and a build never overwrites a file."),
    ("two new paths", r"C:\W\Gear_m1.5_N17.SLDPRT is named twice in this job, so one document would take the "
                      "place of the other."),
    ("reused missing", r"C:\W\Old.SLDPRT is no longer there, so it cannot be reused: it was moved, renamed or "
                       "deleted since it was built."),
    ("same name, two folders", r"C:\W\Gear_m1.5_N17.SLDPRT and C:\Other\Gear_m1.5_N17.SLDPRT have the same file "
                               "name, and SolidWorks keeps one document per file name, so they cannot both be in "
                               "one job."),
    ("open elsewhere", r"C:\Other\Gear_m1.5_N68.SLDPRT is open in SolidWorks, and it has the same file name as "
                       r"C:\W\Gear_m1.5_N68.SLDPRT, which this job would make; SolidWorks keeps one document per "
                       "file name, so close Gear_m1.5_N68.SLDPRT in SolidWorks and try again."),
    ("assembly without layout", "The assembly is built around its layout part, and this build has neither a "
                                "layout part to make nor one to reuse."),
    ("stray insert", r"The assembly would insert C:\W\Stray.SLDPRT, which this build neither makes nor reuses."),
    ("unsound plan", "The build plan for R_Layout.SLDPRT is not sound: Axis 'axis2' is through 'x9', which is not "
                     "a plane made earlier."),
])
def test_every_preflight_refusal_is_a_sentence_and_nothing_is_touched(case, sentence):
    fake = FakeSolidWorks()
    kwargs = {}
    if case == "new path exists":
        fake.saved[_key(P68)] = ([], [])
    elif case == "two new paths":
        kwargs["parts"] = [plan(S17, path=P17), plan(S68, path=P17)]
    elif case == "reused missing":
        kwargs["reuse"] = [swbuild.DocumentValues(W + "Old.SLDPRT", ())]
    elif case == "same name, two folders":
        fake.saved[_key(r"C:\Other\Gear_m1.5_N17.SLDPRT")] = ([], [])
        kwargs["reuse"] = [swbuild.DocumentValues(r"C:\Other\Gear_m1.5_N17.SLDPRT", ())]
    elif case == "open elsewhere":
        fake.open_docs = [DocInfo("Gear_m1.5_N68.SLDPRT", r"C:\Other\Gear_m1.5_N68.SLDPRT", 1)]
    elif case == "assembly without layout":
        kwargs["layout"] = None
    elif case == "stray insert":
        kwargs["assembly"] = _gearbox_assembly(parts=(P17, W + "Stray.SLDPRT"))
    elif case == "unsound plan":
        broken = _layout_plan()
        kwargs["layout"] = BuildPlan("layout", "", tuple(
            ops.Axis("axis2", "S2 Axis", (2, "x9")) if isinstance(op, ops.Axis) and op.id == "axis2" else op
            for op in broken.ops), LAYOUT)
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake, **kwargs)
    assert str(raised.value) == sentence
    assert fake.calls == []


def test_a_reused_part_that_holds_other_values_is_refused_naming_it_and_nothing_is_made():
    fake = FakeSolidWorks()
    _saved_part(fake, S68.with_values(teeth="69"), P68)
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake, parts=[plan(S17, path=P17)], reuse=[swbuild.DocumentValues(P68, _values(S68))])
    assert str(raised.value).startswith("Gear_m1.5_N68.SLDPRT does not hold what the workbook asks of it, so it "
                                        'cannot be reused: "No. of Teeth" is 69 there and 68 here')
    assert "new_part" not in names(fake) and "save_as" not in names(fake)
    assert "set_global_variable" not in names(fake)


def test_a_reused_part_missing_a_global_is_refused_with_its_name_in_the_sentence():
    fake = FakeSolidWorks()
    fake.saved[_key(P68)] = (['"Module"= 1.5'], [])
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake, parts=[plan(S17, path=P17)], reuse=[swbuild.DocumentValues(P68, _values(S68))])
    assert str(raised.value).startswith('Gear_m1.5_N68.SLDPRT cannot be reused: "')
    assert "is not in this part, so it was not built by this tool or its equations were edited." in str(raised.value)
    assert "new_part" not in names(fake)


def test_a_reused_layout_that_lost_a_plane_is_refused():
    fake = FakeSolidWorks()
    fake.saved[_key(LAYOUT)] = (['"S2 X"= 63.75'], ["S1 Axis", "S2 Axis"])
    for path, spec in ((P17, S17), (P68, S68)):
        _saved_part(fake, spec, path)
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake, parts=[], reuse=[swbuild.DocumentValues(P17, _values(S17)),
                                      swbuild.DocumentValues(P68, _values(S68))],
               layout=swbuild.DocumentValues(LAYOUT, LAYOUT_VALUES, LAYOUT_FEATURES))
    assert str(raised.value) == ('R_Layout.SLDPRT cannot be reused: "S2 X Plane" is no longer in it; it was renamed '
                                 "or deleted in SolidWorks.")
    assert "new_assembly" not in names(fake)


def test_a_reused_document_solidworks_will_not_open_is_refused_with_its_sentence():
    fake = FakeSolidWorks(fail_on={"open_document": r"SolidWorks would not open C:\W\Gear_m1.5_N68.SLDPRT (error 2)."})
    _saved_part(fake, S68, P68)
    with pytest.raises(swbuild.BuildError, match=r"would not open C:\\W\\Gear_m1.5_N68.SLDPRT \(error 2\)\."):
        _build(fake, parts=[plan(S17, path=P17)], reuse=[swbuild.DocumentValues(P68, _values(S68))])
    assert "new_part" not in names(fake)


def test_reused_parts_and_layout_are_opened_and_checked_before_anything_is_built_and_inserted_after():
    fake = FakeSolidWorks()
    for path, spec in ((P17, S17), (P68, S68)):
        _saved_part(fake, spec, path)
    swbuild.build(fake, _layout_plan(), fake.exists)
    fake.calls.clear()
    _, result = _build(fake, parts=[], reuse=[swbuild.DocumentValues(P17, _values(S17)),
                                              swbuild.DocumentValues(P68, _values(S68))],
                       layout=swbuild.DocumentValues(LAYOUT, LAYOUT_VALUES, LAYOUT_FEATURES))
    assert result.ok, result.log_lines()
    assert result.checked == [P17, P68, LAYOUT] and result.layout_reused == LAYOUT and result.layout is None
    called = names(fake)
    assert called.count("open_document") == 3 and called.index("new_assembly") > max(
        i for i, n in enumerate(called) if n == "open_document")
    assert called.count("new_part") == 0 and "set_global_variable" not in called
    assert not result.parts.ok          # an empty batch, as pinned; the gearbox is still ok
    assert "ok      layout R_Layout.SLDPRT reused" in result.log_lines()
    assert "ok      checked Gear_m1.5_N17.SLDPRT: it holds what the workbook asks, so it is reused" in result.log_lines()


@pytest.mark.parametrize("route,ok", [("opened", True), ("closed", True), (None, False), ("neither", False)])
def test_inserting_reused_parts_follows_the_reuse_route(monkeypatch, route, ok):
    monkeypatch.setattr(findings, "REUSE_ADD_ROUTE", route, raising=False)
    fake = FakeSolidWorks()
    _saved_part(fake, S17, P17)
    if ok:
        _, result = _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
        assert result.ok and "open_document" in names(fake)      # "closed" is opened anyway, by the live check
        return
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
    assert str(raised.value) == ("Putting a document built earlier into a new assembly has not been settled on "
                                 f"SolidWorks yet (findings.REUSE_ADD_ROUTE is {route!r}), so this build, which "
                                 "reuses Gear_m1.5_N17.SLDPRT, cannot start; run probe tier 7 first.")
    assert fake.calls == []


def test_a_reused_part_needs_no_reuse_route_when_no_assembly_is_built(monkeypatch):
    monkeypatch.setattr(findings, "REUSE_ADD_ROUTE", None, raising=False)
    fake = FakeSolidWorks()
    _saved_part(fake, S17, P17)
    _, result = _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))],
                       layout=None, assembly=None)
    assert result.ok and result.checked == [P17]


def test_a_part_that_fails_skips_the_layout_and_the_assembly():
    fake = FakeSolidWorks(fail_on={"circular_pattern": "FeatureCircularPattern5 would not pattern the cut."})
    _, result = _build(fake)
    assert not result.ok
    assert len(result.parts.built) == 1 and result.parts.skipped == [P68]
    assert result.layout is None and result.assembly is None
    assert result.skipped == "the layout part and the assembly, because a part failed"
    assert result.log_lines()[-1] == "SKIPPED the layout part and the assembly, because a part failed"
    assert names(fake).count("new_part") == 1 and "new_assembly" not in names(fake)


def test_a_layout_that_fails_keeps_the_parts_and_skips_the_assembly():
    fake = FakeSolidWorks(fail_on={"insert_axis": ("S2 Axis", "InsertAxis2 would not make S2 Axis.")})
    _, result = _build(fake)
    assert not result.ok and [r.saved for r in result.parts.built] == [P17, P68]
    assert result.layout is not None and not result.layout.ok and not result.layout.saved
    assert result.assembly is None and result.skipped == "the assembly, because the layout part failed"
    assert "new_assembly" not in names(fake)


def test_an_assembly_that_fails_keeps_the_parts_and_the_layout_and_checks_no_interference():
    fake = FakeSolidWorks(fail_on={"place_component": ("gear2", "gear2-1 did not take its frame.")})
    _, result = _build(fake)
    assert not result.ok
    assert [r.saved for r in result.parts.built] == [P17, P68] and result.layout.saved == LAYOUT
    assert not result.assembly.ok and not result.assembly.saved and result.skipped == ""
    assert "interferences" not in names(fake) and result.clashes == []
    assert not any("interference" in line for line in result.log_lines())


def test_an_assembly_that_cannot_even_be_made_keeps_the_parts_and_the_layout_on_the_result():
    """SolidWorks 2026, probe/workbook_assembly_check.py 2026-11-13: an assembly template that was not there
    raised out of build_gearbox after the parts and the layout had saved, so nothing reached the record."""
    fake = FakeSolidWorks(fail_on={"new_assembly": "There is no assembly template at 'C:\\T\\No.asmdot'."})
    _, result = _build(fake)
    assert not result.ok and [r.saved for r in result.parts.built] == [P17, P68] and result.layout.saved == LAYOUT
    assembly = result.assembly
    assert assembly is not None and not assembly.saved and assembly.document == ""
    assert assembly.failures == [("new assembly", "There is no assembly template at 'C:\\T\\No.asmdot'.")]
    assert "FAIL    new assembly: There is no assembly template at 'C:\\T\\No.asmdot'." in result.log_lines()
    assert "interferences" not in names(fake)
    assert "FAIL    the rebuild reported an error" not in assembly.log_lines()   # nothing was made to rebuild


def test_a_later_part_that_cannot_be_made_keeps_the_parts_before_it():
    fake = FakeSolidWorks()
    calls = {"n": 0}
    real = fake.new_part

    def second_fails(template=""):
        calls["n"] += 1
        if calls["n"] == 2:
            raise swbuild.SolidWorksError("SolidWorks would not make a new part from C:\\T\\Part.prtdot.")
        return real(template)
    fake.new_part = second_fails
    _, result = _build(fake)
    assert [r.saved for r in result.parts.built] == [P17, ""] and result.parts.built[1].failures[0][0] == "new part"
    assert result.skipped == "the layout part and the assembly, because a part failed"


def test_a_layout_that_cannot_be_made_is_a_failed_layout():
    fake = FakeSolidWorks()
    calls = {"n": 0}
    real = fake.new_part

    def third_fails(template=""):
        calls["n"] += 1
        if calls["n"] == 3:
            raise swbuild.SolidWorksError("There is no part template at 'C:\\T\\No.prtdot'.")
        return real(template)
    fake.new_part = third_fails
    _, result = _build(fake)
    assert result.layout is not None and result.layout.failures[0][0] == "new part" and not result.layout.saved
    assert result.skipped == "the assembly, because the layout part failed"


def test_a_clash_names_the_gears_and_leaves_the_build_ok():
    fake = FakeSolidWorks(clashes=[(("gear1-1", "gear2-1"), 12.3454), ((), 1.5), (("layout-1", "gear2-1"), 0.25)])
    _, result = _build(fake)
    assert result.ok
    assert result.clashes[0] == swbuild.Clash(("gear1-1", "gear2-1"), ("G1", "G2"), 12.3454)
    assert result.clashes[2].gears == ("layout-1", "G2")
    lines = result.log_lines()
    assert "CHECK   G1 and G2 interfere, 12.345 mm³; look where they meet" in lines
    assert ("CHECK   an interference of 1.500 mm³ between components SolidWorks did not name; look at each mesh"
            in lines)
    assert "ok      no interference between the gears" not in lines


def test_an_interference_check_that_raises_is_kept_and_the_build_still_stands():
    fake = FakeSolidWorks(fail_on={"interferences": "Assem1 has no interference detection manager."})
    _, result = _build(fake)
    assert result.ok and result.interference_error == "Assem1 has no interference detection manager."
    assert "CHECK   interference could not be checked: Assem1 has no interference detection manager." \
        in result.log_lines()


def test_build_parts_alone_makes_no_layout_and_no_assembly():
    fake, result = _build(layout=None, assembly=None)
    assert result.ok and result.layout is None and result.assembly is None and result.skipped == ""
    assert "new_assembly" not in names(fake) and "interferences" not in names(fake)


def test_a_gearbox_build_refuses_an_old_solidworks():
    fake = FakeSolidWorks()
    fake.revision = (31, 0, 0)
    with pytest.raises(swbuild.BuildError, match="2024"):
        _build(fake)


# -- W4: update_gearbox ---------------------------------------------------------------------------


def _built_gearbox(**fake_kwargs):
    """A fake SolidWorks after a clean gearbox build: every file saved, the gears where the build put them."""
    fake, result = _build(FakeSolidWorks(**fake_kwargs))
    assert result.ok, result.log_lines()
    fake.calls.clear()
    fake.frames = {"layout-1": (IDENTITY, (0.0, 0.0, 0.0)), "gear1-1": (IDENTITY, (0.0, 0.0, 0.0)),
                   "gear2-1": (TURNED2, AT2)}
    return fake


def _placements(g2=(TURNED2, AT2), teeth2=68):
    return [swbuild.Placement("G1", "gear1-1", IDENTITY, (0.0, 0.0, 0.0), 360.0 / 17),
            swbuild.Placement("G2", "gear2-1", g2[0], g2[1], 360.0 / teeth2)]


S69 = S68.with_values(teeth="69")
MOVED2 = (_turned(0.0), (64.5, 0.0, 0.0))


def _update(fake, **kwargs):
    kwargs.setdefault("parts", [swbuild.DocumentValues(P17, _values(S17)), swbuild.DocumentValues(P68, _values(S69))])
    kwargs.setdefault("layout", swbuild.DocumentValues(LAYOUT, (GlobalVariable("S2 X", "64.5"),), LAYOUT_FEATURES))
    kwargs.setdefault("assembly", ASM)
    kwargs.setdefault("placements", _placements(MOVED2, 69))
    kwargs.setdefault("exists", fake.exists)
    return swbuild.update_gearbox(fake, **kwargs)


def _after_last_open(fake, path):
    called = fake.calls
    start = max(i for i, (n, a) in enumerate(called) if n == "open_document" and a == (path,))
    return [n for n, _ in called[start:]]


def test_update_sets_values_then_re_places_only_what_differs_and_rebuilds_the_assembly_once():
    fake = _built_gearbox()
    result = _update(fake)
    assert result.ok, result.log_lines()
    sets = [a for n, a in fake.calls if n == "set_global_variable"]
    assert ("No. of Teeth", "69") in sets and ("S2 X", "64.5") in sets
    assert [r.changed for r in result.parts] == [[], ["No. of Teeth"]] and result.layout.changed == ["S2 X"]
    assert result.placed == ["G2"] and [a for n, a in fake.calls if n == "place_component"] == [("placed2",)]
    assert result.found == {"G1": (IDENTITY, (0.0, 0.0, 0.0)), "G2": (TURNED2, AT2)}
    assert _after_last_open(fake, ASM).count("rebuild") == 1 and result.rebuilt
    assert result.changed == [P68, LAYOUT, ASM]
    assert "save_as" not in names(fake) and "close_document" not in names(fake)
    assert fake.frames["gear2-1"] == MOVED2
    lines = result.log_lines()
    assert "ok      re-placed G2" in lines and "ok      no interference between the gears" in lines
    assert lines[-1] == ("not saved: Gear_m1.5_N68.SLDPRT, R_Layout.SLDPRT, R.SLDASM changed in SolidWorks; save "
                         "there to keep it")


def test_update_steps_check_every_document_then_values_then_place_then_interference():
    fake = _built_gearbox()
    steps, say = _record_steps()
    _update(fake, progress=say)
    assert steps == [swbuild.Step("check", "Gear_m1.5_N17", 1, 4), swbuild.Step("check", "Gear_m1.5_N68", 2, 4),
                     swbuild.Step("check", "R_Layout", 3, 4), swbuild.Step("check", "R", 4, 4),
                     swbuild.Step("values", "Gear_m1.5_N68"),     # N17 holds its values already: not touched
                     swbuild.Step("values", "R_Layout"), swbuild.Step("place", "R"),
                     swbuild.Step("interference", "R")]


def test_a_gear_turned_whole_pitches_is_left_where_it_is():
    fake = _built_gearbox()
    fake.frames["gear2-1"] = (_turned(180.0 / 68 + 5 * 360.0 / 68), AT2)
    result = _update(fake, parts=[], layout=None, placements=_placements())
    assert result.ok and result.placed == [] and "place_component" not in names(fake)
    # nothing changed and nothing moved: the assembly is only read, not rebuilt (W4 review S2)
    assert result.changed == [] and not result.rebuilt and "rebuild" not in names(fake)
    assert "interferences" not in names(fake)
    assert "ok      every gear is where the workbook puts it" in result.log_lines()
    assert result.log_lines()[-1] == "nothing changed in SolidWorks"


def test_a_gear_dragged_in_solidworks_is_found_where_it_was_and_put_back():
    fake = _built_gearbox()
    fake.frames["gear1-1"] = (_turned(7.0), (1.0, 2.0, 0.0))
    result = _update(fake, parts=[], layout=None, placements=_placements())
    assert result.placed == ["G1"] and result.found["G1"] == (_turned(7.0), (1.0, 2.0, 0.0))
    assert fake.frames["gear1-1"] == (IDENTITY, (0.0, 0.0, 0.0))


@pytest.mark.parametrize("case,sentence", [
    ("missing path", r"C:\W\Gear_m1.5_N68.SLDPRT is no longer there, so Update SolidWorks cannot change it: it was "
                     "moved, renamed or deleted since it was built."),
    ("missing global", 'R_Layout.SLDPRT cannot be updated: "S3 X" is not in this part, so it was not built by this '
                       "tool or its equations were edited."),
    ("lost plane", 'R_Layout.SLDPRT cannot be updated: "S2 X Plane" is no longer in it; it was renamed or deleted '
                   "in SolidWorks."),
    ("missing component", "gear2-1 is not in R.SLDASM any more: it was renamed or deleted in SolidWorks."),
    ("does not evaluate", "Gear_m1.5_N68.SLDPRT cannot be updated: the new values do not evaluate: "),
    ("open elsewhere", r"C:\Old\R.SLDASM is open in SolidWorks, and it has the same file name as C:\W\R.SLDASM, "
                       "which this job would change; SolidWorks keeps one document per file name, so close R.SLDASM "
                       "in SolidWorks and try again."),
    ("no assembly", "Gears can only be re-placed in an assembly, and Update SolidWorks was given none."),
    ("one component twice", "gear2-1 is recorded for both G1 and G2, so one of them would be placed twice."),
])
def test_every_check_refusal_changes_nothing(case, sentence):
    fake = _built_gearbox()
    kwargs = {}
    if case == "missing path":
        del fake.saved[_key(P68)]
    elif case == "missing global":
        kwargs["layout"] = swbuild.DocumentValues(LAYOUT, (GlobalVariable("S2 X", "64.5"),
                                                           GlobalVariable("S3 X", "132.5")), LAYOUT_FEATURES)
    elif case == "lost plane":
        fake.saved[_key(LAYOUT)][1].remove("S2 X Plane")
    elif case == "missing component":
        fake.missing_components = {"gear2-1"}
    elif case == "does not evaluate":
        kwargs["parts"] = [swbuild.DocumentValues(P68, (GlobalVariable("No. of Teeth", '"Nowhere" * 2'),))]
    elif case == "open elsewhere":
        fake.open_docs = [DocInfo("R.SLDASM", r"C:\Old\R.SLDASM", 2)]
    elif case == "no assembly":
        kwargs["assembly"] = ""
    elif case == "one component twice":
        kwargs["placements"] = [swbuild.Placement("G1", "gear2-1", IDENTITY, (0.0, 0.0, 0.0)),
                                swbuild.Placement("G2", "gear2-1", IDENTITY, (0.0, 0.0, 0.0))]
    with pytest.raises(swbuild.BuildError) as raised:
        _update(fake, **kwargs)
    assert str(raised.value).startswith(sentence) if case == "does not evaluate" else str(raised.value) == sentence
    called = names(fake)
    assert "set_global_variable" not in called and "place_component" not in called and "rebuild" not in called
    assert "save_as" not in called


@pytest.mark.parametrize("route", [None, "something else"])
def test_re_placing_without_a_settled_route_is_refused_before_anything_changes(monkeypatch, route):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", route, raising=False)
    fake = _built_gearbox()
    with pytest.raises(swbuild.BuildError) as raised:
        _update(fake)
    assert str(raised.value) == ("Moving a fixed component has not been settled on SolidWorks yet "
                                 f"(findings.REPLACE_FIXED_ROUTE is {route!r}), so Update SolidWorks cannot re-place "
                                 "the gears; run probe tier 7 first.")
    assert fake.calls == []


def test_values_alone_need_no_re_placing_route(monkeypatch):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", None, raising=False)
    fake = _built_gearbox()
    result = _update(fake, layout=None, assembly="", placements=[])
    assert result.ok and result.changed == [P68]


def test_the_unfix_route_unfixes_places_and_fixes_each_moved_gear(monkeypatch):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", "UnfixComponent, Transform2 put, FixComponent",
                        raising=False)
    fake = _built_gearbox()
    result = _update(fake)
    assert result.ok
    moves = [(n, a) for n, a in fake.calls if n in ("unfix_component", "place_component", "fix_component")]
    assert moves == [("unfix_component", ("placed2",)), ("place_component", ("placed2",)),
                     ("fix_component", ("placed2",))]


def test_the_transform_route_places_a_fixed_gear_without_unfixing_it():
    assert findings.REPLACE_FIXED_ROUTE == "Transform2 put"
    fake = _built_gearbox()
    _update(fake)
    assert "unfix_component" not in names(fake) and "fix_component" not in names(fake)


def test_re_placing_restores_the_rebuild_flag_before_the_one_rebuild():
    fake = _built_gearbox()
    _update(fake)
    tail = [(n, a) for n, a in fake.calls[[n for n, _ in fake.calls].index("place_component") - 1:]]
    assert tail[0] == ("suppress", (True,)) and ("suppress", (False,)) in tail
    assert tail.index(("suppress", (False,))) < tail.index(("rebuild", (False,)))
    assert fake.suppressed is False


def test_a_part_that_fails_stops_the_update_and_says_what_changed_and_what_was_left():
    fake = _built_gearbox(fail_on={"set_global_variable": ("No. of Teeth", "\"No. of Teeth\" reads '68'.")})
    result = _update(fake, parts=[swbuild.DocumentValues(P17, _values(S17.with_values(teeth="18"))),
                                  swbuild.DocumentValues(P68, _values(S69))])
    assert not result.ok and len(result.parts) == 1 and result.layout is None
    assert result.failures[0][0] == 'Gear_m1.5_N17.SLDPRT "No. of Teeth"'
    assert result.skipped == "1 more part, the layout part and the assembly, because Gear_m1.5_N17.SLDPRT failed"
    assert "place_component" not in names(fake) and "open_document" not in _after_last_open(fake, P17)[1:]
    assert result.log_lines()[-1].startswith("SKIPPED 1 more part")


def test_a_layout_that_fails_stops_before_the_assembly():
    fake = _built_gearbox(fail_on={"set_global_variable": ("S2 X", '"S2 X" reads 63.75.')})
    result = _update(fake)
    assert not result.ok and result.changed == [P68] and result.layout is not None
    assert result.skipped == "the assembly, because R_Layout.SLDPRT failed"
    assert "place_component" not in names(fake)


def test_a_failed_assembly_rebuild_is_a_failure_and_no_interference_is_checked():
    fake = _built_gearbox()
    fake.rebuild_ok = False
    result = _update(fake, parts=[], layout=None)          # G2 is re-placed, so the assembly is rebuilt
    assert not result.ok and result.failures == [("R.SLDASM", "SolidWorks reported an error rebuilding R.")]
    assert "interferences" not in names(fake)


def test_an_update_clash_names_the_gears_from_the_placements():
    fake = _built_gearbox(clashes=[(("gear1-1", "gear2-1"), 3.0)])
    result = _update(fake)
    assert result.ok and result.clashes == [swbuild.Clash(("gear1-1", "gear2-1"), ("G1", "G2"), 3.0)]
    assert "CHECK   G1 and G2 interfere, 3.000 mm³; look where they meet" in result.log_lines()


def test_with_parts_not_settled_beside_their_assembly_an_open_assembly_must_be_closed_first(monkeypatch):
    monkeypatch.setattr(findings, "OPEN_PART_BESIDE_ASSEMBLY", False, raising=False)
    fake = _built_gearbox()
    fake.open_docs = [DocInfo("R.SLDASM", ASM, 2)]
    with pytest.raises(swbuild.BuildError) as raised:
        _update(fake)
    assert str(raised.value) == ("Close R.SLDASM in SolidWorks, then press Update SolidWorks again: changing a part "
                                 "while its assembly is open has not been settled on this SolidWorks "
                                 "(findings.OPEN_PART_BESIDE_ASSEMBLY).")
    assert fake.calls == []


@pytest.mark.parametrize("beside", [False, None])
def test_with_parts_not_settled_beside_their_assembly_the_assembly_opens_after_the_values(monkeypatch, beside):
    monkeypatch.setattr(findings, "OPEN_PART_BESIDE_ASSEMBLY", beside, raising=False)
    fake = _built_gearbox()
    fake.missing_components = {"gear2-1"}
    result = _update(fake)
    called = names(fake)
    assert called.index("open_document") < called.index("set_global_variable")
    first_asm = next(i for i, (n, a) in enumerate(fake.calls) if n == "open_document" and a == (ASM,))
    assert first_asm > max(i for i, n in enumerate(called) if n == "set_global_variable")
    assert not result.ok and result.failures[0] == (
        "R.SLDASM", "gear2-1 is not in R.SLDASM any more: it was renamed or deleted in SolidWorks.")
    assert result.changed == [P68, LAYOUT]


def test_an_update_with_nothing_given_changes_nothing():
    fake = FakeSolidWorks()
    result = swbuild.update_gearbox(fake, exists=fake.exists)
    assert result.ok and fake.calls == [] and result.log_lines() == ["nothing changed in SolidWorks"]


def test_an_update_refuses_an_old_solidworks():
    fake = FakeSolidWorks()
    fake.revision = (31, 0, 0)
    with pytest.raises(swbuild.BuildError, match="2024"):
        swbuild.update_gearbox(fake, exists=fake.exists)


# -- W4: what the first run on SolidWorks 2026 found (probe/gearbox_smoke.py, 2026-11-13) -----------------


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_the_reuse_check_writes_nothing_and_reads_the_trig_units_from_the_text(trig):
    fake = FakeSolidWorks(trig=trig)
    _saved_part(fake, S17, P17)
    _, result = _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
    assert result.ok, result.log_lines()
    called = names(fake)
    assert "detect_trig_units" not in called[:called.index("new_part")]
    assert "add_global_variable" not in called[:called.index("new_part")]


def test_a_document_update_changes_still_has_its_trig_units_measured_before_its_values_are_set():
    fake = _built_gearbox()
    _update(fake)
    called = names(fake)
    assert "detect_trig_units" in called[:called.index("set_global_variable")]


def test_interferences_between_the_same_components_are_one_clash_with_their_volumes_summed():
    fake = FakeSolidWorks(clashes=[(("gear1-1", "gear2-1"), 54.0), (("gear2-1", "gear1-1"), 27.0),
                                   (("gear1-1", "gear2-1"), 10.5), ((), 0.5), ((), 0.25)])
    _, result = _build(fake)
    assert result.clashes == [swbuild.Clash(("gear1-1", "gear2-1"), ("G1", "G2"), 91.5),
                              swbuild.Clash((), (), 0.5), swbuild.Clash((), (), 0.25)]
    assert "CHECK   G1 and G2 interfere, 91.500 mm³; look where they meet" in result.log_lines()


# -- W4 review: nothing escapes a job once it has saved something (B1) ----------------------------------------


class ComErrorLookAlike(Exception):
    """Stands in for ``pywintypes.com_error`` reaching swbuild unwrapped (or anything else unexpected)."""


RPC = ComErrorLookAlike(-2147023170, "The remote procedure call failed.", None, None)


def test_a_raise_on_the_third_save_keeps_the_two_parts_saved_before_it_on_the_result():
    """The review's w4r_crash: the third save_as raised a non-SolidWorksError and build_gearbox raised with it, so
    the two parts SolidWorks had saved never reached the record."""
    fake = FakeSolidWorks(raises={"save_as": (2, RPC)})
    _, result = _build(fake)
    assert [r.saved for r in result.parts.built] == [P17, ""] and not result.ok
    assert result.parts.built[1].failures[0][0] == "save"
    assert result.parts.built[1].failures[0][1].startswith("it stopped on an unexpected ComErrorLookAlike: ")
    assert result.skipped == "the layout part and the assembly, because a part failed"
    assert "new_assembly" not in names(fake)


def test_a_raise_making_the_first_part_is_a_failed_part_not_a_raise():
    fake = FakeSolidWorks(raises={"new_part": (1, RPC)})
    _, result = _build(fake)
    assert len(result.parts.built) == 1 and result.parts.built[0].failures[0][0] == "new part"
    assert result.parts.skipped == [P68] and not result.ok


def test_a_raise_between_documents_is_a_failure_on_the_result_and_what_saved_stays():
    def say(step):
        if step.stage == "layout":
            raise RPC
    fake = FakeSolidWorks()
    _, result = _build(fake, progress=say)
    assert [r.saved for r in result.parts.built] == [P17, P68] and result.layout is None
    assert result.failures == [("the layout part", "it stopped on an unexpected ComErrorLookAlike: (-2147023170, "
                                                   "'The remote procedure call failed.', None, None).")]
    assert result.skipped == "the assembly, because the job stopped during the layout part"
    assert not result.ok
    assert result.log_lines()[-2:] == ["FAIL    the layout part: " + result.failures[0][1],
                                       "SKIPPED the assembly, because the job stopped during the layout part"]


def test_a_raise_in_the_interference_check_is_said_and_the_build_stands():
    fake = FakeSolidWorks(raises={"interferences": (1, RPC)})
    _, result = _build(fake)
    assert result.ok and result.interference_error.startswith("it stopped on an unexpected ComErrorLookAlike")


def test_the_reuse_check_still_refuses_before_anything_is_made():
    """The pre-flight (paths, the reused documents checked live) may still raise: nothing is made by then."""
    fake = FakeSolidWorks(raises={"open_document": (1, RPC)})
    _saved_part(fake, S17, P17)
    with pytest.raises(ComErrorLookAlike):
        _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
    assert "new_part" not in names(fake)


def test_an_update_that_raises_part_way_keeps_what_it_changed_on_the_result():
    fake = _built_gearbox()
    fake.raises = {"set_global_variable": (fake.counts.get("set_global_variable", 0) + 2, RPC)}   # S2 X
    result = _update(fake)
    assert result.changed == [P68] and result.layout is not None and result.layout.changed == []
    assert result.failures[0][0] == 'R_Layout.SLDPRT "S2 X"'
    assert result.skipped == "the assembly, because R_Layout.SLDPRT failed" and "place_component" not in names(fake)


def test_an_update_whose_assembly_raises_keeps_the_values_it_set():
    fake = _built_gearbox()
    fake.raises = {"component_frame": (fake.counts.get("component_frame", 0) + 1, RPC)}
    result = _update(fake)
    assert result.changed == [P68, LAYOUT] and result.placed == []
    assert result.failures[0][0] == "R.SLDASM" and "ComErrorLookAlike" in result.failures[0][1]
    assert result.rebuilt                                 # the values changed, so the assembly is still rebuilt


def test_an_update_raise_between_documents_is_a_failure_on_the_result():
    def say(step):
        if step.stage == "place":
            raise RPC
    fake = _built_gearbox()
    result = _update(fake, progress=say)
    assert result.changed == [P68, LAYOUT] and not result.ok
    assert result.failures[0][0] == "R.SLDASM" and result.failures[0][1].startswith("it stopped on an unexpected")


# -- W4 review: Update touches only the documents it changes (S2) ---------------------------------------------


def test_an_update_leaves_a_part_that_holds_its_values_untouched_and_unmeasured():
    """W4 review S2: on SolidWorks 2026 every Update marked every part modified, because the check measured each
    part's trig units (an equation added and deleted)."""
    fake = _built_gearbox()
    fake.touched.clear()
    result = _update(fake)
    assert result.ok and result.changed == [P68, LAYOUT, ASM]
    assert fake.touched == {_key(P68), _key(LAYOUT), _key(ASM)}           # not Gear_m1.5_N17
    assert result.parts[0].changed == [] and result.parts[0].trig == DEGREES and result.parts[0].unchanged
    measured = [i for i, (n, _) in enumerate(fake.calls) if n == "detect_trig_units"]
    assert len(measured) == 2                         # once in each document Update changes, by update_variables
    opened = [a[0] for n, a in fake.calls if n == "open_document"]
    assert opened.count(P17) == 1                     # read in the check, and never opened again to change it


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_an_update_that_changes_nothing_touches_nothing(trig):
    fake = _built_gearbox(trig=trig)
    fake.touched.clear()
    result = _update(fake, parts=[swbuild.DocumentValues(P17, _values(S17)), swbuild.DocumentValues(P68, _values(S68))],
                     layout=swbuild.DocumentValues(LAYOUT, LAYOUT_VALUES, LAYOUT_FEATURES), placements=_placements())
    assert result.ok and result.changed == [] and fake.touched == set()
    assert "detect_trig_units" not in names(fake) and "rebuild" not in names(fake)
    assert [r.trig for r in result.parts] == [trig, trig]
    assert result.log_lines()[-1] == "nothing changed in SolidWorks"


def test_new_values_that_evaluate_in_one_trig_unit_only_are_measured_to_decide():
    odd = (GlobalVariable("No. of Teeth", "69", radian_expression='"Nowhere" * 2'),)
    fake = _built_gearbox(trig=DEGREES)
    result = _update(fake, parts=[swbuild.DocumentValues(P68, odd)], layout=None, assembly="", placements=[])
    assert result.ok and result.changed == [P68]
    fake = _built_gearbox(trig=RADIANS)
    with pytest.raises(swbuild.BuildError, match="Gear_m1.5_N68.SLDPRT cannot be updated: the new values do not "
                                                 "evaluate: "):
        _update(fake, parts=[swbuild.DocumentValues(P68, odd)], layout=None, assembly="", placements=[])
    assert "set_global_variable" not in names(fake)


def test_an_update_notes_each_files_time_before_it_changes_anything():
    fake = _built_gearbox()
    times = {_key(P17): 1.0, _key(P68): 2.0, _key(LAYOUT): 3.0}

    def mtime(path):
        if _key(path) not in times:
            raise OSError("not there")
        return times[_key(path)]
    result = _update(fake, mtime=mtime)
    assert result.mtimes == {P17: 1.0, P68: 2.0, LAYOUT: 3.0}         # the assembly's time could not be read
