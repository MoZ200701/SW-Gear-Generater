"""The bridge between the window's variables and the spec dataclasses.

Only the parts that are data. This box has no tkinter, so ``gui.py`` is read by
path and parsed with ``ast`` rather than imported: the tables and the poll
loop's invariants are checked without a display, and without Tk installed.
"""

import ast
import dataclasses
import pathlib

from gear_generator.spec import GearSpec, PairSpec

GUI = pathlib.Path(__file__).resolve().parent.parent / "src" / "gear_generator" / "gui.py"
TREE = ast.parse(GUI.read_text(encoding="utf-8"))


def _constant(name):
    for node in TREE.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not a module-level constant in gui.py any more")


def _app_class():
    for node in ast.walk(TREE):
        if isinstance(node, ast.ClassDef) and node.name == "GearApp":
            return node
    raise AssertionError("GearApp is not in gui.py any more")


def _self_attributes(node, store=False):
    wanted = ast.Store if store else ast.Load
    return {
        child.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
        and isinstance(child.value, ast.Name)
        and child.value.id == "self"
        and isinstance(child.ctx, wanted)
    }


# -- the tables -------------------------------------------------------------


def test_the_gear_table_covers_every_field_of_the_gear_spec():
    """A field added to GearSpec and forgotten here would be silently dropped."""
    mapped = {field for field, _ in _constant("GEAR_VARS")} | set(_constant("GEAR_COMPOUND"))
    assert mapped == {f.name for f in dataclasses.fields(GearSpec)}


def test_the_pair_table_covers_every_field_of_the_pair_spec():
    mapped = {field for field, _ in _constant("PAIR_VARS")} | set(_constant("PAIR_COMPOUND"))
    assert mapped == {f.name for f in dataclasses.fields(PairSpec)}


def test_no_table_names_a_variable_twice():
    for table in ("GEAR_VARS", "PAIR_VARS"):
        attrs = [attr for _, attr in _constant(table)]
        assert len(attrs) == len(set(attrs)), table


def test_the_compound_fields_are_not_also_mapped_as_plain_variables():
    assert {f for f, _ in _constant("GEAR_VARS")}.isdisjoint(_constant("GEAR_COMPOUND"))
    assert {f for f, _ in _constant("PAIR_VARS")}.isdisjoint(_constant("PAIR_COMPOUND"))


def test_every_pair_variable_is_made_in_the_constructor():
    init = next(n for n in _app_class().body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    made = _self_attributes(init, store=True)
    assert {attr for _, attr in _constant("PAIR_VARS")} <= made


# -- what the poll loop is allowed to reach for ------------------------------


def test_every_pending_call_is_set_up_before_the_first_tick():
    """A poll method reading an attribute the constructor never set raises on
    every tick, the tick catches it, and the window never hears back from
    SolidWorks. Airfoil Converter had exactly that bug."""
    app = _app_class()
    methods = {n.name: n for n in app.body if isinstance(n, ast.FunctionDef)}
    read = set()
    for name, node in methods.items():
        if name.startswith(("_tick", "_collect")):
            read |= _self_attributes(node)

    pending = {name for name in read if name.startswith("_pending")}
    assert pending, "the poll loop no longer has a pending call to check"
    assert pending <= _self_attributes(methods["__init__"], store=True)
