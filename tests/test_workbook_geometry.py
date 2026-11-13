"""Positions and phases (docs/PLAN-WORKBOOK.md §3.3), held to the gears' own outlines.

The phase formulas are not trusted on their algebra: two outlines placed by
them must not overlap, and the same two with one turned half a pitch must.
That is tried at awkward directions and turns, for outside meshes, a pinion in
a ring, helical gears whose faces are offset along the axis, herringbones of
different widths on both halves, and gears and rings on Z- shafts. Each
outline is turned as the part's own build plan sweeps it (:func:`built_turn`),
never by geometry's twist, so the two cannot share a wrong assumption.
"""

import math

import pytest

from gear_generator import findings
from gear_generator.gears import crossed, kind_for, pair as pairs
from gear_generator.gears.base import Line, MirrorBody, OpenSketch, RefPlane, SweepCut
from gear_generator.spec import GearSpec
from gear_generator.workbook import checks, geometry
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


def built_turn(gear_spec):
    """How the part is built, read off its own build plan: a function from local height z — mm from the front
    face along the blank — to how far the tooth space there is turned from +X about the part's +Z, radians.

    Nothing here asks geometry or ``HelicalDerived`` where the section is or which way it turns. It reads the
    ops SolidWorks is sent — the plane the space is sketched on, the sweep path, the sweep's twist and reverse
    flag, a mirror — through the probe findings that say which way each flag goes. A spur's space is cut
    straight, on +X at every height. (W3 once modelled the helical section on the front face here, sharing
    geometry's assumption; the part draws it one overrun behind it, and only the plan says so.)
    """
    assert findings.EXTRUDE_Z_SIGN == 1, "this reads a part whose blank runs from its front face along +Z"
    kind = kind_for(gear_spec)
    ops = kind.plan(gear_spec, kind.derive(gear_spec), "", "", r"C:\t.SLDPRT").ops
    sweep = next((op for op in ops if isinstance(op, SweepCut)), None)
    if sweep is None:
        return lambda z: 0.0
    sketch = next(op for op in ops if isinstance(op, OpenSketch) and op.id == sweep.profile)
    plane = next(op for op in ops if isinstance(op, RefPlane) and op.id == sketch.plane)
    assert plane.plane == 1                                   # parallel to the Front plane
    plus = (not plane.flip) if findings.REF_PLANE_UNFLIPPED_IS_PLUS_Z else plane.flip
    z_section = plane.offset if plus else -plane.offset
    start = next(i for i, op in enumerate(ops) if isinstance(op, OpenSketch) and op.id == sweep.path)
    path = next(op for op in ops[start:] if isinstance(op, Line) and not op.construction)
    to_z = (lambda y: -y) if findings.TOP_SKETCH_Y_IS_MINUS_Z else (lambda y: y)
    z_start, z_end = to_z(path.start[1]), to_z(path.end[1])
    assert math.isclose(z_start, z_section, abs_tol=1e-12)    # the sweep starts on the section's plane
    turn = findings.TWIST_TURN["plus z" if z_end > z_start else "minus z"] * (-1 if sweep.reverse else 1)
    rate = turn * math.radians(sweep.twist) / abs(z_end - z_start)       # about +Z, per mm of +z
    mirrored = any(isinstance(op, MirrorBody) and op.plane == plane.id for op in ops)

    def at(z):
        if mirrored:                                          # the far half is the near one mirrored at the plane
            z = z_section - abs(z - z_section)
        return rate * (z - z_section)
    return at


def section(placed, theta, plane, gear_spec):
    """The gear's own transverse outline at a global height, turned as the part is built (:func:`built_turn`),
    not by geometry's own twist or space_angle, so a wrong twist in geometry cannot draw itself right.

    Turned θ on its axis, and mirrored for a Z- axis: a part on Z- is the same part turned over.
    """
    face = float(gear_spec.face_width)
    front = placed.z - placed.sigma * face / 2.0
    z_local = placed.sigma * (plane - front)
    assert -1e-9 <= z_local <= face + 1e-9
    angle = placed.sigma * (theta + built_turn(gear_spec)(z_local))
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


# -- every kind on every pair of facings, the part read from its own plan -----------------------------
#
# A plain helical gear or ring draws its tooth space on the Profile Plane, one overrun behind its front face,
# not on the front face. Counting the twist from the front face is a turn the same as sliding the part one
# overrun along its axis: two gears facing the same way slide together and still mesh; across Z+ and Z- they
# slide apart and the teeth run into each other. W3's tests modelled the part the same wrong way and passed.
# These cases are the review's (2026-11-13) reproduction, kept.

FACINGS = [("Z+", "Z+"), ("Z-", "Z-"), ("Z+", "Z-"), ("Z-", "Z+")]


def _at(axis, z):
    """The At that puts a face's middle at global height z on a shaft at the origin's height."""
    return str(z if axis == "Z+" else -z)


def outside_pair(kind, facing, hands=("", ""), faces=("20", "16"), heights=(10.0, 13.0), beta=""):
    zp, zq = 20, 31
    centre = pairs.describe(2.0, zp, zq, 20.0, float(beta or 0))[0]
    common = dict(module="2", helix_angle=beta) if beta else dict(module="2")
    return box([Shaft("P", x="0", y="0", axis=facing[0], role="input", speed="100"),
                Shaft("Q", x=str(centre * 0.8), y=str(-centre * 0.6), axis=facing[1])],
               [Gear("A", "P", _at(facing[0], heights[0]), kind, teeth=str(zp), face_width=faces[0], hand=hands[0],
                     **common),
                Gear("B", "Q", _at(facing[1], heights[1]), kind, teeth=str(zq), face_width=faces[1], hand=hands[1],
                     **common)],
               [Mesh("A", "B")])


def ring_pair(kind, facing, hands=("", ""), faces=("10", "10"), beta=""):
    zr, zp = 60, 19
    centre = pairs.describe(2.0, zp, zr, 20.0, float(beta or 0), mesh="internal")[0]
    common = dict(module="2", helix_angle=beta) if beta else dict(module="2")
    return box([Shaft("R", x="0", y="0", axis=facing[0], role="input", speed="100"),
                Shaft("P", x=str(centre * math.cos(2.2)), y=str(centre * math.sin(2.2)), axis=facing[1])],
               [Gear("Ring", "R", _at(facing[0], 5.0), kind, side="internal", teeth=str(zr), face_width=faces[0],
                     hand=hands[0], **common),
                Gear("Pin", "P", _at(facing[1], 5.0), kind, teeth=str(zp), face_width=faces[1], hand=hands[1],
                     **common)],
               [Mesh("Ring", "Pin")])


def checks_clean(spec):
    report = checks.check(spec)
    return [d.message for d in report.diagnostics if d.is_error]


@pytest.mark.parametrize("facing", FACINGS)
def test_spur_gears_mesh_on_every_facing(facing):
    spec = outside_pair("spur", facing)
    assert checks_clean(spec) == []
    meshes_at_every_shared_height(spec, "A", "B")


@pytest.mark.parametrize("facing", FACINGS)
@pytest.mark.parametrize("hands", [("right", "left"), ("left", "right")])
@pytest.mark.parametrize("heights", [(10.0, 10.0), (10.0, 13.0), (10.0, 5.5)])
def test_helical_gears_mesh_on_every_facing_with_their_faces_offset(facing, hands, heights):
    """Opposite hands on parallel shafts whichever way each faces: a helix turned over keeps its hand."""
    spec = outside_pair("helical", facing, hands, heights=heights, beta="20")
    assert checks_clean(spec) == []
    meshes_at_every_shared_height(spec, "A", "B")


@pytest.mark.parametrize("facing", [("Z+", "Z-"), ("Z-", "Z+")])
def test_helical_gears_of_the_same_hand_facing_opposite_ways_are_refused_and_do_clash(facing):
    spec = outside_pair("helical", facing, ("right", "right"), beta="20")
    assert any("both right-handed" in e for e in checks_clean(spec))
    with pytest.raises(AssertionError):
        meshes_at_every_shared_height(spec, "A", "B")


@pytest.mark.parametrize("facing", FACINGS)
@pytest.mark.parametrize("faces", [("20", "30"), ("30", "20")])
def test_herringbones_of_unequal_widths_mesh_on_every_facing(facing, faces):
    """Apexes level; facing the same way the hands are opposite, facing opposite ways the typed hands match."""
    hands = ("right", "left") if facing[0] == facing[1] else ("right", "right")
    spec = outside_pair("herringbone", facing, hands, faces=faces, heights=(15.0, 15.0), beta="30")
    assert checks_clean(spec) == []
    planes = meshes_at_every_shared_height(spec, "A", "B")
    assert min(planes) < 15 < max(planes)


@pytest.mark.parametrize("facing", FACINGS)
def test_a_spur_pinion_in_a_ring_meshes_on_every_facing(facing):
    spec = ring_pair("spur", facing)
    assert checks_clean(spec) == []
    meshes_at_every_shared_height(spec, "Ring", "Pin", ring=True)


@pytest.mark.parametrize("facing", FACINGS)
@pytest.mark.parametrize("hand", ["right", "left"])
def test_a_helical_pinion_in_a_helical_ring_meshes_on_every_facing(facing, hand):
    """The same hand as its ring whichever way each faces."""
    spec = ring_pair("helical", facing, (hand, hand), faces=("12", "10"), beta="15")
    assert checks_clean(spec) == []
    meshes_at_every_shared_height(spec, "Ring", "Pin", ring=True)


@pytest.mark.parametrize("facing", FACINGS)
def test_a_herringbone_pinion_in_a_herringbone_ring_meshes_on_every_facing(facing):
    hands = ("right", "right") if facing[0] == facing[1] else ("right", "left")
    spec = ring_pair("herringbone", facing, hands, faces=("30", "20"), beta="30")
    assert checks_clean(spec) == []
    meshes_at_every_shared_height(spec, "Ring", "Pin", ring=True)


HELICAL_PARTS = [
    GearSpec(kind=kind, module=module, teeth=teeth, face_width=face, helix_angle=beta, hand=hand, bore="",
             teeth_side=side)
    for kind, beta in (("helical", "15"), ("herringbone", "30"))
    for hand in ("right", "left")
    for side, teeth, module, face in (("external", "20", "2", "20"), ("external", "13", "1.5", "9"),
                                      ("internal", "60", "2", "16"))
]


@pytest.mark.parametrize("gear_spec", HELICAL_PARTS, ids=lambda s: f"{s.kind}-{s.teeth_side}-{s.teeth}-{s.hand}")
def test_geometry_turns_each_height_as_the_plan_builds_it(gear_spec):
    """geometry's twist, at every height of the face, is the turn the part's own plan sweeps there; and for a
    plain helical gear crossed.twist_at (which places crossed pairs) says the same."""
    spec = box([Shaft("S", x="0", y="0")], [Gear("G", "S", "0", gear_spec.kind, side=gear_spec.teeth_side,
                                                teeth=gear_spec.teeth, module=gear_spec.module,
                                                face_width=gear_spec.face_width, helix_angle=gear_spec.helix_angle,
                                                hand=gear_spec.hand)], [])
    placed = geometry.layout(spec).placed["G"]
    built = built_turn(placed.spec)
    face = float(gear_spec.face_width)
    for z in (0.0, 0.3 * face, face / 2.0, 0.8 * face, face):
        assert placed.twist(placed.z_front + z) == pytest.approx(built(z), abs=1e-12), z
        if gear_spec.kind == "helical":
            assert math.radians(crossed.twist_at(placed.derived, z)) == pytest.approx(built(z), abs=1e-12)
    front, far = placed.derived.face_rotations()
    assert (math.radians(front), math.radians(far)) == pytest.approx((built(0.0), built(face)), abs=1e-12)
    if gear_spec.kind == "helical":
        # The Front-plane face is already a module's worth of helix round: the section is drawn behind it.
        assert built(0.0) == pytest.approx(placed.hand_sign * 2 * math.pi * float(gear_spec.module) / placed.lead)


# -- the pair assemblies built and interference-checked on SolidWorks, unchanged ---------------------
#
# pair.assembly_plan neither reads geometry nor face_rotations: its parts face the same way, fronts (or a
# herringbone's mid-planes) coplanar, gear 1 unturned and gear 2 turned the mesh angle. Those angles are pinned
# here as they were before the twist was counted from the Profile Plane (p5_internal's helical ring among
# them), and geometry, laying the same pair out the same way, must turn gear 2 the same, to a pitch.

SOLIDWORKS_PAIRS = [
    # (gear 1 as the plan takes it, gear 2, the Mesh Angle the plan sends)
    (GearSpec(kind="helical", module="2", teeth="20", helix_angle="15", face_width="10", hand="right", bore="8"),
     GearSpec(kind="helical", module="2", teeth="60", helix_angle="15", face_width="10", hand="right",
              teeth_side="internal", bore=""), 9.0),
    (GearSpec(kind="helical", module="2", teeth="20", helix_angle="15", face_width="20", hand="right"),
     GearSpec(kind="helical", module="2", teeth="40", helix_angle="15", face_width="20", hand="left"), 4.5),
    (GearSpec(kind="helical", module="2", teeth="17", helix_angle="20", face_width="20", hand="left"),
     GearSpec(kind="helical", module="2", teeth="31", helix_angle="20", face_width="14", hand="right"), 360 / 31),
    (GearSpec(kind="herringbone", module="2", teeth="20", helix_angle="30", face_width="20", hand="right"),
     GearSpec(kind="herringbone", module="2", teeth="31", helix_angle="30", face_width="30", hand="left"), 360 / 31),
    (GearSpec(module="2", teeth="20", face_width="10", bore="8"),
     GearSpec(module="2", teeth="60", face_width="10", teeth_side="internal"), 9.0),
]


@pytest.mark.parametrize("gear_a,gear_b,pinned", SOLIDWORKS_PAIRS)
def test_the_solidworks_pair_assemblies_turn_gear_2_as_geometry_does(gear_a, gear_b, pinned):
    plan = pairs.assembly_plan(gear_a, gear_b, r"C:\a.SLDPRT", r"C:\b.SLDPRT", "", r"C:\p.SLDASM")
    sent = {op.name: float(op.expression) for op in plan.ops if type(op).__name__ == "AddGlobal"}
    mate = next(op for op in plan.ops if getattr(op, "id", "") == "mesh")
    assert sent[pairs.MESH_ANGLE] == pytest.approx(pinned, abs=1e-9) and mate.value == pytest.approx(pinned)
    centre = sent[pairs.CENTRE_DISTANCE]

    # The same pair in a workbook: gear 1 (the ring, round a pinion) at the origin on the input, gear 2 on +X.
    first, second = (gear_b, gear_a) if gear_b.is_internal() else (gear_a, gear_b)
    herringbone = gear_a.kind == "herringbone"
    w1, w2 = first.face_width_mm(), second.face_width_mm()

    def row(name, shaft, g, middle):
        return Gear(name, shaft, str(middle), g.kind, side=g.teeth_side, teeth=g.teeth, module=g.module,
                    face_width=g.face_width, helix_angle=g.helix_angle, hand=g.hand)
    spec = box([Shaft("S1", x="0", y="0", role="input"), Shaft("S2", x=str(centre), y="0")],
               [row("G1", "S1", first, w1 / 2), row("G2", "S2", second, w1 / 2 if herringbone else w2 / 2)],
               [Mesh("G1", "G2")])
    lay = geometry.layout(spec)
    theta = geometry.phases(spec, lay.placed)
    assert theta["G1"] == 0.0
    pitch = 360.0 / second.teeth_count()
    off = (math.degrees(theta["G2"]) - pinned) % pitch
    assert min(off, pitch - off) < 1e-9
    meshes_at_every_shared_height(spec, "G1", "G2", ring=first.is_internal())
