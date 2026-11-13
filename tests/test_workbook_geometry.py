"""Positions and phases (docs/PLAN-WORKBOOK.md §3.3), held to the gears' own outlines.

The phase formulas are not trusted on their algebra: two outlines placed by
them must not overlap, and the same two with one turned half a pitch must.
That is tried at awkward directions and turns, for outside meshes, a pinion in
a ring, helical gears whose faces are offset along the axis, herringbones of
different widths on both halves, and gears and rings on Z- shafts.
"""

import math

import pytest

from gear_generator.gears import kind_for, pair as pairs
from gear_generator.spec import GearSpec
from gear_generator.workbook import geometry
from gear_generator.workbook.model import Box, Gear, GearboxSpec, Mesh, Shaft


def outline(spec):
    kind = kind_for(spec)
    return kind.outline(spec, kind.derive(spec))


def turned(points, angle, dx=0.0, dy=0.0, mirror=False):
    c, s = math.cos(angle), math.sin(angle)
    out = []
    for x, y in points:
        if mirror:
            y = -y
        out.append((x * c - y * s + dx, x * s + y * c + dy))
    return out


def inside(point, polygon):
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit


def interference(a, b):
    """Vertices of either outline inside the other: zero for gears that mesh with backlash."""
    return sum(inside(p, a) for p in b[::3]) + sum(inside(p, b) for p in a[::3])


def ring_interference(ring, pinion):
    """A pinion's vertices outside the ring's tooth line are in the ring's metal."""
    return sum(not inside(p, ring) for p in pinion[::3])


def spur(teeth, module="2", **kw):
    return GearSpec(module=module, teeth=str(teeth), face_width="10", bore="", **kw)


@pytest.mark.parametrize("zp,zq", [(17, 68), (20, 21), (13, 40), (24, 24)])
@pytest.mark.parametrize("phi,theta_p", [(0.0, 0.0), (0.7, 0.3), (2.5, -1.1), (-2.0, 4.0)])
def test_outside_meshes_by_their_outlines(zp, zq, phi, theta_p):
    p, q = spur(zp), spur(zq)
    centre = pairs.describe(2.0, zp, zq)[0]
    g_q = geometry.external_space(theta_p, zp, zq, phi)
    a = turned(outline(p), theta_p)
    b = turned(outline(q), g_q, centre * math.cos(phi), centre * math.sin(phi))
    assert interference(a, b) == 0
    wrong = turned(outline(q), g_q + math.pi / zq, centre * math.cos(phi), centre * math.sin(phi))
    assert interference(a, wrong) > 0


@pytest.mark.parametrize("zq", [17, 18, 51, 68])
def test_the_outside_formula_is_pair_mesh_angle_at_zero(zq):
    pitch = 2 * math.pi / zq
    assert math.isclose(geometry.external_space(0.0, 17, zq, 0.0) % pitch,
                        math.radians(pairs.mesh_angle(zq)) % pitch, abs_tol=1e-12)


@pytest.mark.parametrize("zp,zr", [(20, 60), (17, 51), (24, 72)])
@pytest.mark.parametrize("phi,theta_r", [(0.0, 0.0), (1.3, 0.2), (-2.4, 3.0)])
def test_a_pinion_in_a_ring_by_their_outlines(zp, zr, phi, theta_r):
    ring = GearSpec(module="2", teeth=str(zr), face_width="10", bore="", teeth_side="internal")
    centre = 2.0 * (zr - zp) / 2.0
    g_p = geometry.pinion_space(theta_r, zr, zp, phi)
    r = turned(outline(ring), theta_r)
    p = turned(outline(spur(zp)), g_p, centre * math.cos(phi), centre * math.sin(phi))
    assert ring_interference(r, p) == 0
    wrong = turned(outline(spur(zp)), g_p + math.pi / zp, centre * math.cos(phi), centre * math.sin(phi))
    assert ring_interference(r, wrong) > 0
    # And the other way round: the ring placed against the pinion lands where it started, to a pitch.
    pitch = 2 * math.pi / zr
    back = geometry.ring_space(g_p, zp, zr, phi)
    assert math.isclose((back - theta_r) % pitch, 0.0, abs_tol=1e-9) or math.isclose(
        (back - theta_r) % pitch, pitch, abs_tol=1e-9)


@pytest.mark.parametrize("zp", [17, 20, 24])
def test_the_ring_formula_is_pair_internal_mesh_angle_at_zero(zp):
    pitch = 2 * math.pi / zp
    assert math.isclose(geometry.pinion_space(0.0, 60, zp, 0.0) % pitch,
                        math.radians(pairs.internal_mesh_angle(zp)) % pitch, abs_tol=1e-12)


# -- through the workbook: placing, helical offsets, a Z- shaft ------------------------------------


def box(shafts, gears, meshes):
    return GearboxSpec(box=Box(name="T"), shafts=tuple(shafts), gears=tuple(gears), meshes=tuple(meshes))


def section(placed, theta, plane, gear_spec):
    """The gear's own transverse outline at a global height — worked out here from how the part is built,
    not from geometry's own space_angle, so a wrong twist in geometry cannot draw itself right.

    The part's section is drawn on its front face and turns hand · 360 · z / lead degrees about its own +Z at
    local height z (helical.py's convention, RIGHT_HAND_TURN); turned θ on its axis, and mirrored for a Z- axis.
    """
    kind = kind_for(gear_spec)
    derived = kind.derive(gear_spec)
    face = float(gear_spec.face_width)
    front = placed.z - placed.sigma * face / 2.0
    z_local = placed.sigma * (plane - front)
    twist = 0.0
    if gear_spec.kind in ("helical", "herringbone"):
        # The part says how its Front-plane face is turned from the section drawn; from there the helix turns
        # hand · 360/lead degrees per mm, and a herringbone's far half is the near half mirrored at mid-face.
        front_turn = math.radians(derived.face_rotations()[0])
        if gear_spec.kind == "herringbone":
            z_local = min(z_local, face - z_local)
        twist = front_turn + derived.hand_sign * 2.0 * math.pi * z_local / derived.lead
    angle = placed.sigma * (theta + twist)
    return turned(outline(gear_spec), angle, placed.x, placed.y, mirror=placed.sigma < 0)


def specs(spec):
    return {g.id: g.gear_spec(spec.box) for g in spec.gears}


def test_the_example_reducer_is_placed_and_meshed():
    centre_1 = pairs.describe(1.5, 17, 68)[0]
    centre_2 = pairs.describe(2.0, 17, 51)[0]
    spec = box([Shaft("S1", x="0", y="0"), Shaft("S2", x=str(centre_1), y="0"),
                Shaft("S3", x=str(centre_1 + centre_2 * math.cos(1.0)), y=str(centre_2 * math.sin(1.0)))],
               [Gear("G1", "S1", "7.5", teeth="17", module="1.5", face_width="15"),
                Gear("G2", "S2", "7.5", teeth="68", module="1.5", face_width="15"),
                Gear("G3", "S2", "27", teeth="17", module="2", face_width="20"),
                Gear("G4", "S3", "27", teeth="51", module="2", face_width="20")],
               [Mesh("G1", "G2"), Mesh("G3", "G4")])
    lay = geometry.layout(spec)
    assert lay.later == [] and lay.problems == {}
    theta = geometry.phases(spec, lay.placed)
    g = specs(spec)
    for a, b in (("G1", "G2"), ("G3", "G4")):
        pa, pb = lay.placed[a], lay.placed[b]
        plane = geometry.mesh_plane(pa, pb)
        assert interference(section(pa, theta[a], plane, g[a]), section(pb, theta[b], plane, g[b])) == 0
        assert interference(section(pa, theta[a], plane, g[a]),
                            section(pb, theta[b] + math.pi / pb.teeth, plane, g[b])) > 0
    assert geometry.faces_overlap(lay.placed["G1"], lay.placed["G2"]) == 15


def helical_pair(offset, axis_q="Z+"):
    m, beta, zp, zq = 2.0, 15.0, 20, 31
    centre = pairs.describe(m, zp, zq, 20.0, beta)[0]
    return box([Shaft("P", x="0", y="0"), Shaft("Q", x=str(centre), y="0", axis=axis_q)],
               [Gear("A", "P", "10", "helical", teeth=str(zp), module="2", face_width="20", helix_angle="15",
                     hand="right"),
                Gear("B", "Q", str(10 + offset) if axis_q == "Z+" else str(-(10 + offset)), "helical",
                     teeth=str(zq), module="2", face_width="20", helix_angle="15", hand="left")],
               [Mesh("A", "B")])


def meshes_at_every_shared_height(spec, a_id, b_id, ring=False):
    """Placed and turned by geometry, the two sections clear at heights across the shared face, and clash
    turned half a pitch; returns the heights tried."""
    lay = geometry.layout(spec)
    assert lay.later == [] and lay.problems == {}
    theta = geometry.phases(spec, lay.placed)
    a, b = lay.placed[a_id], lay.placed[b_id]
    g = specs(spec)
    lo, hi = max(a.z_range[0], b.z_range[0]), min(a.z_range[1], b.z_range[1])
    planes = [lo + 0.5, lo + (hi - lo) * 0.3, (lo + hi) / 2, lo + (hi - lo) * 0.7, hi - 0.5]
    for plane in planes:
        sa = section(a, theta[a_id], plane, g[a_id])
        right = section(b, theta[b_id], plane, g[b_id])
        wrong = section(b, theta[b_id] + math.pi / b.teeth, plane, g[b_id])
        if ring:
            assert ring_interference(sa, right) == 0, plane
            assert ring_interference(sa, wrong) > 0, plane
        else:
            assert interference(sa, right) == 0, plane
            assert interference(sa, wrong) > 0, plane
    return planes


@pytest.mark.parametrize("axis_q", ["Z+", "Z-"])
@pytest.mark.parametrize("offset", [0.0, 4.0, -7.5])
def test_helical_gears_offset_along_the_axis_mesh_at_every_shared_height(offset, axis_q):
    meshes_at_every_shared_height(helical_pair(offset, axis_q), "A", "B")


def herringbone_pair(axis_q, hand_q, faces=("20", "30"), groove=""):
    m, beta, zp, zq = 2.0, 30.0, 20, 31
    centre = pairs.describe(m, zp, zq, 20.0, beta)[0]
    at_q = "15" if axis_q == "Z+" else "-15"           # both apexes at Z = 15
    return box([Shaft("P", x="0", y="0"), Shaft("Q", x=str(centre * 0.8), y=str(-centre * 0.6), axis=axis_q)],
               [Gear("A", "P", "15", "herringbone", teeth=str(zp), module="2", face_width=faces[0],
                     helix_angle="30", hand="right", groove=groove),
                Gear("B", "Q", at_q, "herringbone", teeth=str(zq), module="2", face_width=faces[1],
                     helix_angle="30", hand=hand_q, groove=groove)],
               [Mesh("A", "B")])


@pytest.mark.parametrize("axis_q,hand_q", [("Z+", "left"), ("Z-", "right")])
def test_herringbones_of_different_widths_mesh_on_both_halves(axis_q, hand_q):
    """The section is drawn at the apex, so a herringbone's phase does not depend on its width; turned over
    onto a Z- axis, the half nearest its front is at the other end, so its hand must be the same as its mate's."""
    planes = meshes_at_every_shared_height(herringbone_pair(axis_q, hand_q), "A", "B")
    assert min(planes) < 15 < max(planes)              # both halves were tried


@pytest.mark.parametrize("axis_q,hand_q", [("Z+", "right"), ("Z-", "left")])
def test_herringbones_with_the_wrong_hands_do_not_mesh_across_the_face(axis_q, hand_q):
    """The hand rule the checks enforce, held to the outlines: one half meshes, the other cannot."""
    with pytest.raises(AssertionError):
        meshes_at_every_shared_height(herringbone_pair(axis_q, hand_q), "A", "B")


@pytest.mark.parametrize("ring_axis,pinion_axis", [("Z-", "Z+"), ("Z+", "Z-"), ("Z-", "Z-")])
def test_a_pinion_in_a_ring_with_z_minus_axes(ring_axis, pinion_axis):
    zr, zp = 60, 19
    centre = 2.0 * (zr - zp) / 2.0
    spec = box([Shaft("R", x="0", y="0", axis=ring_axis),
                Shaft("P", x=str(centre * math.cos(2.2)), y=str(centre * math.sin(2.2)), axis=pinion_axis)],
               [Gear("Ring", "R", "5" if ring_axis == "Z+" else "-5", side="internal", teeth=str(zr), module="2",
                     face_width="10"),
                Gear("Pin", "P", "5" if pinion_axis == "Z+" else "-5", teeth=str(zp), module="2",
                     face_width="10")],
               [Mesh("Ring", "Pin")])
    meshes_at_every_shared_height(spec, "Ring", "Pin", ring=True)


def test_a_spur_on_a_z_minus_shaft_is_mirrored_and_meshes():
    centre = pairs.describe(2.0, 17, 30)[0]
    spec = box([Shaft("P", x="0", y="0"), Shaft("Q", x=str(centre * 0.6), y=str(centre * 0.8), axis="Z-")],
               [Gear("A", "P", "5", teeth="17", module="2", face_width="10"),
                Gear("B", "Q", "-5", teeth="30", module="2", face_width="10")],
               [Mesh("A", "B")])
    lay = geometry.layout(spec)
    b = lay.placed["B"]
    assert b.sigma == -1 and b.z == 5.0                               # At runs along the Z- axis
    theta = geometry.phases(spec, lay.placed)
    plane = geometry.mesh_plane(lay.placed["A"], b)
    g = specs(spec)
    assert interference(section(lay.placed["A"], theta["A"], plane, g["A"]), section(b, theta["B"], plane, g["B"])) == 0
    assert interference(section(lay.placed["A"], theta["A"], plane, g["A"]),
                        section(b, theta["B"] + math.pi / b.teeth, plane, g["B"])) > 0


def test_shafts_a_later_phase_lays_out_are_said_not_guessed():
    spec = box([Shaft("S", x="0", y="0", axis="X+"), Shaft("C", x="0", y="0"),
                Shaft("P", "C", x="24", y="0", copies="3")], [], [])
    later = geometry.layout(spec).later
    assert any("W6" in s for s in later) and any("W7" in s for s in later)
