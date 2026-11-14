"""The three workbooks of W4's Windows demonstration (probe/workbook_assembly_check.py), as Excel saved them.

Each must keep reading and assessing clean, and planning a whole build, so the demonstration can be rerun on
any SolidWorks: the 12 : 1 reducer, Arc_Move (S2 placed by formulas from an angle cell, off both base planes,
S3 following it by formula) and Risky_Placements (a helical pair across Z+ and Z-, herringbones of unequal face
widths, a helical pinion in a helical ring whose shaft is Z-). Arc_Move and Risky_Placements were written by
``xlsx.write_new`` and then opened and saved in Excel 16 on Windows (2026-11-13).
"""

import math
import os

import pytest

from gear_generator.workbook import assess, gearbox, layout, link, xlsx

HERE = os.path.join(os.path.dirname(__file__), "fixtures", "excel-windows")


def assessed(name):
    reading = link.Link(os.path.join(HERE, name)).read()
    assert reading.ok, reading.error
    return reading, assess.assess(reading.spec, reading.diagnostics, reading.spec.box.output_folder,
                                  reading.spec.box.part_template)


@pytest.mark.parametrize("name", ["Reducer_12to1.xlsx", "Arc_Move.xlsx", "Risky_Placements.xlsx"])
def test_each_demonstration_workbook_reads_assesses_and_plans_clean(name):
    reading, a = assessed(name)
    assert a.errors == [] and a.lay_out_refusal() == ""
    plan = gearbox.plan_gearbox(a, None, exists=lambda p: False, read_sidecar=lambda p: None)
    assert plan.refusal == "" and plan.revision == 0 and plan.assembly is not None
    assert set(plan.frames) == {g.id for g in reading.spec.gears}


def test_arc_move_places_s2_by_formula_off_both_base_planes():
    book = xlsx.read(os.path.join(HERE, "Arc_Move.xlsx"))
    shafts = book.sheets["Shafts"]
    assert all(shafts.cell(row, col).formula for row in (3, 4) for col in (3, 4))      # C3 D3 C4 D4
    reading, a = assessed("Arc_Move.xlsx")
    s = {x.shaft: x for x in layout.shaft_layouts(a.spec)}
    assert math.hypot(s["S2"].x, s["S2"].y) == pytest.approx(40, abs=1e-9)
    assert (s["S3"].x - s["S2"].x, s["S3"].y - s["S2"].y) == pytest.approx((40, 0), abs=1e-9)
    assert {s["S2"].x_side, s["S2"].y_side, s["S3"].x_side, s["S3"].y_side} == {layout.PLUS}


def test_risky_placements_has_each_risky_mesh():
    reading, a = assessed("Risky_Placements.xlsx")
    sigma = {x.shaft: x.sigma for x in layout.shaft_layouts(a.spec)}
    gears = {g.id: g for g in a.spec.gears}

    def across(m):
        return sigma[gears[m.a].shaft] != sigma[gears[m.b].shaft]
    kinds = {(gears[m.a].kind_word(), gears[m.b].kind_word(), gears[m.b].side or "external"): across(m)
             for m in a.spec.meshes}
    assert kinds == {("helical", "helical", "external"): True, ("herringbone", "herringbone", "external"): True,
                     ("helical", "helical", "internal"): True}
    assert gears["G3"].face_width != gears["G4"].face_width
    assert sigma[gears["G6"].shaft] == -1                     # the ring's shaft is Z-
