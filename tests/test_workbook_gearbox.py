"""Planning a gearbox build and recording it (docs/PLAN-WORKBOOK.md §4.2–§4.5, phase W4)."""

import pytest

from gear_generator import swbuild
from gear_generator.gears.base import BuildPlan, GlobalVariable, NewAssembly, NewPart
from gear_generator.spec import GearSpec
from gear_generator.workbook.build import PartJob
from gear_generator.workbook.gearbox import GearboxPlan, LayoutReuse, PartReuse


def _plan(**changes):
    new = PartJob("Gear_m1.5_N68_r2", r"C:\P\Gear_m1.5_N68_r2.SLDPRT", ("G2",), GearSpec(), None,
                  BuildPlan("spur", "A", (NewPart(""),)))
    kept = PartReuse(r"C:\P\Gear_m1.5_N17.SLDPRT", "Gear_m1.5_N17", ("G1", "G3"), GearSpec(), None,
                     (GlobalVariable("No. of Teeth", "17"),), 0)
    fields = dict(revision=2, name="R_r2", folder=r"C:\P", layout_path=r"C:\P\R_r2_Layout.SLDPRT",
                  assembly_path=r"C:\P\R_r2.SLDASM", build=(new,), reuse=(kept,), shafts=(), frames={},
                  layout=LayoutReuse(r"C:\P\R_r2_Layout.SLDPRT", (GlobalVariable("S2 X", "63.75"),),
                                     ("S2 X Plane", "S2 Axis")),
                  assembly=BuildPlan("assembly", "", (NewAssembly(""),)), handles={"gear1": "G1"},
                  part_of={"G1": kept.path, "G2": new.path, "G3": kept.path})
    fields.update(changes)
    return GearboxPlan(**fields)


def test_a_plan_hands_the_worker_plain_data_for_build_gearbox():
    plan = _plan()
    kwargs = plan.build_kwargs()
    assert kwargs["parts"] == [plan.build[0].plan]
    assert kwargs["reuse"] == [swbuild.DocumentValues(r"C:\P\Gear_m1.5_N17.SLDPRT",
                                                      (GlobalVariable("No. of Teeth", "17"),))]
    assert kwargs["layout"] == swbuild.DocumentValues(r"C:\P\R_r2_Layout.SLDPRT", (GlobalVariable("S2 X", "63.75"),),
                                                      ("S2 X Plane", "S2 Axis"))
    assert kwargs["assembly"] is plan.assembly and kwargs["gears"] == {"gear1": "G1"}
    assert set(kwargs) == set(swbuild.build_gearbox.__code__.co_varnames[1:6])


def test_a_parts_only_plan_has_no_layout_or_assembly():
    plan = _plan(layout=None, assembly=None, layout_path="", assembly_path="")
    assert plan.parts_only and plan.build_kwargs()["layout"] is None


def test_a_refused_plan_cannot_be_run():
    with pytest.raises(ValueError, match="already exists"):
        _plan(refusal=r"C:\P\R_r2.SLDASM already exists.").build_kwargs()
