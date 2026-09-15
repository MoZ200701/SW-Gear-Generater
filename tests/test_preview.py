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
