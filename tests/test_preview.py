"""Where the Derived panel puts the gears, checked without a canvas."""

import math

import pytest

from gear_generator import preview
from gear_generator.gears import KINDS
from gear_generator.spec import GearSpec

SPUR = KINDS["spur"]


def _gear(teeth, **values):
    spec = GearSpec(teeth=str(teeth), **values)
    derived = SPUR.derive(spec)
    return derived, SPUR.outline(spec, derived)


def _both():
    return [_gear(20), _gear(60)]


def test_one_gear_is_centred_and_its_pitch_diameter_dimensioned():
    derived, _ = _gear(25)
    made = preview.layout([derived])
    assert made.centre_distance == 0
    placed = made.gears[0]
    assert placed.x == pytest.approx(made.width / 2)
    assert placed.rotation == 0
    # The whole gear fits, with the dimension zone left clear under it.
    assert placed.y - placed.tip_radius * made.scale >= preview.TOP - 1e-9
    assert made.dimension.text == "PD 37.5 mm"
    assert made.dimension.x1 - made.dimension.x0 == pytest.approx(derived.d * made.scale)
    assert made.dimension.y + preview.DIM_OVERRUN <= made.height


def test_a_pair_is_drawn_at_the_centre_distance_its_teeth_make():
    (a, _), (b, _) = _both()
    made = preview.layout([a, b])
    assert made.centre_distance == pytest.approx(60.0)     # m (20 + 60) / 2
    first, second = made.gears
    assert (first.label, second.label) == ("A", "B")
    assert second.x - first.x == pytest.approx(60.0 * made.scale)
    assert first.y == second.y
    assert made.dimension.text == "C 60 mm"
    assert (made.dimension.x0, made.dimension.x1) == (first.x, second.x)
    assert made.dimension.text_x == pytest.approx((first.x + second.x) / 2)


def test_both_gears_and_the_gap_between_them_fit_the_canvas():
    (a, _), (b, _) = _both()
    made = preview.layout([a, b])
    first, second = made.gears
    assert first.x - a.ra * made.scale >= preview.PAD - 1e-9
    assert second.x + b.ra * made.scale <= made.width - preview.PAD + 1e-9
    assert second.y + b.ra * made.scale <= made.height - preview.DIM_ZONE + preview.DIM_DROP


def test_the_second_gear_is_turned_so_a_tooth_faces_the_first():
    """An even count is turned half a pitch past the half turn; an odd one is not."""
    assert preview.mesh_rotation(60) == pytest.approx(math.pi + math.pi / 60)
    assert preview.mesh_rotation(61) == pytest.approx(math.pi)


def test_gear_b_reaches_exactly_to_c_minus_its_tip_radius():
    """A tooth tip pointing at A's centre is what says the two are meshed."""
    (a, _), (b, b_outline) = _both()
    made = preview.layout([a, b])
    first, second = made.gears
    points = preview.points_on(b_outline, second, made.scale)
    nearest = min(math.hypot(x - first.x, y - first.y) for x, y in points) / made.scale
    assert nearest == pytest.approx(60.0 - b.ra, abs=1e-6)     # C − ra_B = 13.5 mm


def test_the_two_outlines_do_not_cross():
    """The tooth goes into the space: no point of either outline is inside the other."""
    (a, a_outline), (b, b_outline) = _both()
    made = preview.layout([a, b])
    first, second = made.gears
    a_points = preview.points_on(a_outline, first, made.scale)
    b_points = preview.points_on(b_outline, second, made.scale)
    # Only the teeth that are in mesh can possibly touch: the band between the
    # far edge of B's nearest tooth and A's tip circle.
    band = (first.x + (made.centre_distance - b.ra) * made.scale - 1,
            first.x + a.ra * made.scale + 1)
    inside = [p for p in b_points if band[0] <= p[0] <= band[1]]
    assert inside, "no part of gear B reaches gear A, so nothing was checked"
    for point in inside:
        assert not _inside(point, a_points), f"gear B runs through gear A at {point}"
    for point in [p for p in a_points if band[0] <= p[0] <= band[1]]:
        assert not _inside(point, b_points), f"gear A runs through gear B at {point}"


def _inside(point, polygon):
    """Ray casting, the plainest one: is the point within the closed outline?"""
    x, y = point
    hits = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) / (y1 - y0) * (x1 - x0):
            hits = not hits
    return hits


def test_a_preview_of_no_gear_or_three_is_refused_in_a_sentence():
    with pytest.raises(ValueError, match="one gear or two"):
        preview.layout([])


# -- rings and bevel gears -------------------------------------------------------


def test_a_pinion_is_drawn_inside_its_ring_turned_half_a_pitch():
    from gear_generator.gears import kind_for

    pinion_spec, ring_spec = GearSpec(module="2", teeth="20"), GearSpec(module="2", teeth="60", teeth_side="internal")
    pinion, ring = SPUR.derive(pinion_spec), kind_for(ring_spec).derive(ring_spec)
    made = preview.layout([pinion, ring])
    first, second = made.gears
    assert made.centre_distance == pytest.approx(40.0)
    assert first.x - second.x == pytest.approx(40.0 * made.scale)
    assert first.rotation == pytest.approx(math.pi / 20)
    assert second.bore_radius == pytest.approx(ring.rim / 2.0)          # the rim circle
    assert second.x + ring.rim / 2.0 * made.scale <= made.width - preview.PAD + 1e-9
    assert made.dimension.text == "C 40 mm"


def test_a_bevel_pair_meets_at_the_apex_with_the_pitch_cones_along_one_line():
    from gear_generator.gears import KINDS as ALL

    bevel = ALL["bevel"]
    a = bevel.derive(GearSpec(kind="bevel", module="3", teeth="20", mate_teeth="40", face_width="20"))
    b = bevel.derive(GearSpec(kind="bevel", module="3", teeth="40", mate_teeth="20", face_width="20"))
    made = preview.layout([a, b])
    assert made.gears[0].x == made.gears[1].x and made.gears[0].y == made.gears[1].y
    assert len(made.polylines) == 4
    (x0, y0), (x1, y1) = made.guides[0]
    (u0, v0), (u1, v1) = made.guides[2]
    assert math.atan2(x1 - x0, y0 - y1) == pytest.approx(math.atan2(u1 - u0, v0 - v1), abs=1e-9)
    assert math.hypot(x1 - x0, y1 - y0) == pytest.approx(math.hypot(u1 - u0, v1 - v0), abs=1e-9)
    for line in made.polylines:
        assert all(-1e-9 <= x <= made.width + 1e-9 and -1e-9 <= y <= made.height + 1e-9 for x, y in line)
    assert made.dimension.text == "R 67.082 mm · Σ 90°"
    single = preview.layout([a])
    assert single.dimension.text == "OD 67.218 mm" and len(single.polylines) == 2


# -- the Workbook window's end view: every placed gear, turned to its phase ------------------


def _workbook_view(width=392, height=300):
    from gear_generator.workbook import geometry
    from gear_generator.workbook.model import Box, Gear, GearboxSpec, Mesh, Shaft
    from gear_generator.gears import pair as pairs
    centre = pairs.describe(2.0, 17, 30)[0]
    ring_centre = 2.0 * (60 - 17) / 2.0
    spec = GearboxSpec(
        box=Box(name="T"),
        shafts=(Shaft("A", x="0", y="0"), Shaft("B", x="0", y=str(centre), axis="Z-"),
                Shaft("R", x=str(ring_centre), y="0")),
        gears=(Gear("P", "A", "5", teeth="17", module="2", face_width="10"),
               Gear("Q", "B", "-5", teeth="30", module="2", face_width="10"),
               Gear("Ring", "R", "20", side="internal", teeth="60", module="2", face_width="10", rim="140"),
               Gear("P2", "A", "20", teeth="17", module="2", face_width="10")),
        meshes=(Mesh("P", "Q"), Mesh("P2", "Ring")))
    lay = geometry.layout(spec)
    assert lay.problems == {}
    theta = geometry.phases(spec, lay.placed)
    return lay, theta, preview.layout_gearbox(lay.placed, theta, width, height)


def test_the_end_view_fits_the_canvas_with_y_up():
    lay, _, view = _workbook_view()
    points = [pt for _, _, outline in view.outlines for pt in outline]
    assert all(0 <= x <= 392 and 0 <= y <= 300 for x, y in points)
    shafts = {name: (x, y) for name, x, y in view.shafts}
    assert set(shafts) == {"A", "B", "R"}
    assert shafts["B"][1] < shafts["A"][1]                  # B is at +Y: higher on the screen
    assert shafts["R"][0] > shafts["A"][0]                  # R is at +X: to the right
    assert view.origin == pytest.approx(shafts["A"])


def test_the_end_view_groups_by_plane_and_rings_get_their_rim():
    _, _, view = _workbook_view()
    assert view.planes == [5.0, 20.0]
    planes = {gear: plane for gear, plane, _ in view.outlines}
    assert planes == {"P": 0, "Q": 0, "Ring": 1, "P2": 1}
    assert [o[0] for o in view.outlines][-2:] in (["Ring", "P2"], ["P2", "Ring"])    # nearest +Z drawn last
    (gear, plane, cx, cy, r), = view.rims
    assert gear == "Ring" and plane == 1 and r == pytest.approx(70.0 * view.scale)


def test_the_end_view_draws_meshed_gears_clear_of_each_other():
    """The view turns each gear by geometry's phase, and mirrors the Z- one: drawn, they do not cross."""
    import math
    lay, theta, view = _workbook_view(800, 600)

    def crossing(view):
        outlines = {gear: outline for gear, _, outline in view.outlines}
        p, q = outlines["P"], outlines["Q"]
        return sum(_inside(pt, q) for pt in p) + sum(_inside(pt, p) for pt in q)

    assert crossing(view) == 0
    wrong = dict(theta, Q=theta["Q"] + math.pi / 30)
    assert crossing(preview.layout_gearbox(lay.placed, wrong, 800, 600)) > 0
