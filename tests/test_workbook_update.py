"""What Update SolidWorks changes, and recording it (docs/PLAN-WORKBOOK.md §4.5, phase W4)."""

import pytest

from gear_generator import swbuild
from gear_generator.gears.base import GlobalVariable
from gear_generator.spec import GearSpec
from gear_generator.workbook.update import PartUpdate, UpdatePlan


def _update(**changes):
    part = PartUpdate(r"C:\P\Gear_m1.5_N68.SLDPRT", ("G2",), GearSpec(), None,
                      (GlobalVariable("No. of Teeth", "69"),), changed=True)
    fields = dict(parts=(part,), layout=swbuild.DocumentValues(r"C:\P\R_Layout.SLDPRT"),
                  assembly=r"C:\P\R.SLDASM",
                  placements=(swbuild.Placement("G2", "Gear_m1.5_N68-1", (1, 0, 0, 0, 1, 0, 0, 0, 1),
                                                (64.5, 0, 0), 360 / 69),))
    fields.update(changes)
    return UpdatePlan(**fields)


def test_an_update_plan_hands_the_worker_plain_data_for_update_gearbox():
    plan = _update()
    kwargs = plan.update_kwargs()
    assert kwargs["parts"] == [swbuild.DocumentValues(r"C:\P\Gear_m1.5_N68.SLDPRT",
                                                      (GlobalVariable("No. of Teeth", "69"),))]
    assert kwargs["layout"] is plan.layout and kwargs["assembly"] == r"C:\P\R.SLDASM"
    assert kwargs["placements"] == list(plan.placements)
    assert set(kwargs) == set(swbuild.update_gearbox.__code__.co_varnames[1:5])
    assert not plan.record_matches and plan.changed_parts == plan.parts


@pytest.mark.parametrize("changes", [{"structural": ("G2's bore was added.",)},
                                     {"missing": (r"C:\P\Gear_m1.5_N68.SLDPRT",)}])
def test_a_change_update_cannot_carry_is_never_run(changes):
    plan = _update(**changes)
    assert plan.needs_new_revision
    with pytest.raises(ValueError):
        plan.update_kwargs()
