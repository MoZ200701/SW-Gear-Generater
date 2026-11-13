"""The layout part and the static assembly as plans, and each gear's frame (docs/PLAN-WORKBOOK.md §4.2–§4.3).

The frames are held to the parts themselves, not to geometry's algebra: each
part is modelled from its own build plan (``built_turn``: the plane its
section is sketched on, the sweep's twist and direction, a mirror), carried
into the assembly by the :class:`layout.Frame` this module plans — its
rotation and origin applied to the part's local points, nothing else — and
two meshing gears cut at several heights must not overlap, and must overlap
with one of them turned half a pitch.
"""

import math

import pytest

from gear_generator import findings, swbuild
from gear_generator.gears import equations, kind_for, pair as pairs
from gear_generator.gears.base import (AddComponent, AddGlobal, Axis, Fix, LinkDimension, NewAssembly, NewPart, Place,
                                       Rebuild, RefPlane, SaveAs, Unfix)
from gear_generator.workbook import assess, checks, layout
from gear_generator.workbook.model import Shaft, replace
from test_workbook_geometry import (FACINGS, built_turn, interference, outline, outside_pair, ring_interference,
                                    ring_pair)
from test_workbook_model import reducer

FOLDER = "C:\\Parts\\Reducer_12to1\\"

# Tier 7's answers on 2026 and 2024, as the probe agent's working tree has them; set here so these tests do not
# depend on whether findings.py has them committed yet.
TIER_7 = {"LAYOUT_PLUS_FLIP": {"right": False, "top": False}, "LAYOUT_NEGATED_LINK": "minus",
          "LAYOUT_AXIS_Z_SIGN": -1, "REPLACE_FIXED_ROUTE": "Transform2 put"}


@pytest.fixture(autouse=True)
def tier_7(monkeypatch):
    for name, value in TIER_7.items():
        monkeypatch.setattr(findings, name, value, raising=False)


def shafts_of(spec):
    return layout.shaft_layouts(spec)


def with_shafts(*shafts):
    return replace(reducer(), shafts=tuple(shafts))


# -- shafts, sides and globals ---------------------------------------------------------------------


def test_the_reducer_lays_out_two_planes_and_three_axes():
    s1, s2, s3 = shafts_of(reducer())
    assert (s1.x_side, s1.y_side, s2.x_side, s2.y_side, s3.x_side, s3.y_side) == (
        "base", "base", "plus", "base", "plus", "base")
    assert (s2.x_global, s2.x_plane, s2.y_global, s2.y_plane, s2.axis_name) == ("S2 X", "S2 X Plane", "", "",
                                                                                "S2 Axis")
    assert layout.layout_globals((s1, s2, s3)) == (equations_var("S2 X", "63.75"), equations_var("S3 X", "131.75"))
    assert layout.layout_features((s1, s2, s3)) == ("S1 Axis", "S2 X Plane", "S2 Axis", "S3 X Plane", "S3 Axis")


def equations_var(name, value):
    from gear_generator.gears.base import GlobalVariable
    return GlobalVariable(name, value)


@pytest.mark.parametrize("value,expected", [(0.0, "base"), (5e-10, "base"), (-5e-10, "base"), (1e-6, "plus"),
                                            (-0.01, "minus"), (131.75, "plus")])
def test_side(value, expected):
    assert layout.side(value) == expected


def test_a_shaft_record_mirrors_a_shaft_layout_field_for_field():
    from dataclasses import asdict, fields
    from gear_generator import store
    assert [f.name for f in fields(layout.ShaftLayout)] == [f.name for f in fields(store.ShaftEntry)]
    s2 = shafts_of(reducer())[1]
    assert layout.ShaftLayout(**asdict(store.ShaftEntry(**asdict(s2)))) == s2


def test_shafts_a_later_phase_lays_out_are_refused_with_a_sentence():
    spec = reducer()
    with pytest.raises(ValueError, match=r"S3's axis is X\+: .* until phase W6\."):
        shafts_of(with_shafts(spec.shafts[0], spec.shafts[1], replace(spec.shafts[2], axis="X+")))
    with pytest.raises(ValueError, match="P is mounted on S2: .* phase W7"):
        shafts_of(with_shafts(*spec.shafts, Shaft("P", "S2", "10", "0")))


def plane_position(plan, plane_name, globals_):
    """Where a plane of the plan lands along its base plane's normal, as SolidWorks puts it: its offset is
    whatever its linked equation evaluates to, and unflipped is the side LAYOUT_PLUS_FLIP says."""
    plane = next(op for op in plan.ops if isinstance(op, RefPlane) and op.name == plane_name)
    link = next(op for op in plan.ops if isinstance(op, LinkDimension) and op.dimension == f"Offset@{plane_name}")
    offset = equations.evaluate(link.expression, globals_)
    base = {3: "right", 2: "top"}[plane.plane]
    plus = findings.LAYOUT_PLUS_FLIP[base]
    assert offset >= 0, "a plane's offset is a distance"
    assert offset == pytest.approx(plane.offset)
    return offset if plane.flip == plus else -offset


@pytest.mark.parametrize("form", ["minus", "times minus one", "abs", None])
@pytest.mark.parametrize("flips", [{"right": False, "top": False}, {"right": True, "top": False},
                                   {"right": False, "top": True}])
def test_every_plane_lands_on_its_coordinate_whatever_the_findings_say(monkeypatch, form, flips):
    monkeypatch.setattr(findings, "LAYOUT_NEGATED_LINK", form, raising=False)
    monkeypatch.setattr(findings, "LAYOUT_PLUS_FLIP", flips, raising=False)
    spec = with_shafts(Shaft("A", x="0", y="0", role="input"), Shaft("B", x="-40", y="25.5"),
                       Shaft("C", x="12.25", y="-30"), Shaft("D", x="-7", y="0", axis="Z-"))
    shafts = shafts_of(spec)
    plan = layout.layout_plan(shafts, "", r"C:\P\T_Layout.SLDPRT")
    assert plan.check() == []
    values = plan.values()
    for s in shafts:
        for coordinate, name, plane in (("x", s.x_global, s.x_plane), ("y", s.y_global, s.y_plane)):
            if name:
                assert plane_position(plan, plane, values) == pytest.approx(getattr(s, coordinate)), plane
    # Signed globals, unless no negated link works: then each holds |v| and its plane is linked plainly.
    assert values["B X"] == (-40.0 if form else 40.0) and values["C Y"] == (-30.0 if form else 30.0)


def test_a_negative_coordinate_flips_its_plane_and_negates_its_link():
    spec = with_shafts(Shaft("S1", x="0", y="0", role="input"), Shaft("S2", x="-63.75", y="0"))
    plan = layout.layout_plan(shafts_of(spec), "", r"C:\P\T_Layout.SLDPRT")
    plane = next(op for op in plan.ops if isinstance(op, RefPlane))
    assert (plane.id, plane.name, plane.plane, plane.offset) == ("x2", "S2 X Plane", layout.RIGHT, 63.75)
    assert plane.flip is (not findings.LAYOUT_PLUS_FLIP["right"])
    assert LinkDimension("Offset@S2 X Plane", '- "S2 X"') in plan.ops
    assert AddGlobal("S2 X", "-63.75") in plan.ops


@pytest.mark.parametrize("form,minus", [("minus", '- "S2 X"'), ("times minus one", '-1 * "S2 X"'),
                                        ("abs", 'abs ( "S2 X" )'), (None, '"S2 X"')])
def test_link_expression_follows_the_finding(monkeypatch, form, minus):
    monkeypatch.setattr(findings, "LAYOUT_NEGATED_LINK", form, raising=False)
    assert layout.link_expression("S2 X", True) == '"S2 X"'
    assert layout.link_expression("S2 X", False) == minus


@pytest.mark.parametrize("sign,first", [(-1, "top"), (1, "right")])
def test_each_axis_is_made_through_the_planes_in_the_order_that_reads_plus_z(monkeypatch, sign, first):
    """LAYOUT_AXIS_Z_SIGN is the sign read with the Right-parallel plane selected first; each part's Gear Axis
    reads +Z, and so must a layout axis a gear is later mated to."""
    monkeypatch.setattr(findings, "LAYOUT_AXIS_Z_SIGN", sign, raising=False)
    spec = with_shafts(Shaft("S1", x="0", y="0", role="input"), Shaft("S2", x="10", y="0"),
                       Shaft("S3", x="0", y="-4"), Shaft("S4", x="5", y="6"))
    axes = [op for op in layout.layout_plan(shafts_of(spec), "", r"C:\P\T.SLDPRT").ops if isinstance(op, Axis)]
    top_first = first == "top"
    expected = [(layout.TOP, layout.RIGHT), (layout.TOP, "x2"), ("y3", layout.RIGHT), ("y4", "x4")]
    expected = [p if top_first else (p[1], p[0]) for p in expected]
    assert [(a.id, a.name) for a in axes] == [(f"axis{i}", f"S{i} Axis") for i in range(1, 5)]
    assert [a.planes for a in axes] == expected


def test_the_layout_plan_is_sound_and_saves_last():
    plan = layout.layout_plan(shafts_of(reducer()), r"C:\T\Part.PRTDOT", r"C:\P\Reducer_12to1_Layout.SLDPRT")
    assert plan.check() == []
    assert plan.ops[0] == NewPart(r"C:\T\Part.PRTDOT")
    assert plan.ops[-2:] == (Rebuild(), SaveAs(r"C:\P\Reducer_12to1_Layout.SLDPRT"))
    assert plan.values() == {"S2 X": 63.75, "S3 X": 131.75}
    # every global comes before any feature
    first_feature = next(i for i, op in enumerate(plan.ops) if not isinstance(op, (NewPart, AddGlobal)))
    assert all(not isinstance(op, AddGlobal) for op in plan.ops[first_feature:])


@pytest.mark.parametrize("name", sorted(TIER_7))
def test_a_finding_not_yet_committed_refuses_with_a_sentence(monkeypatch, name):
    monkeypatch.delattr(findings, name, raising=False)
    with pytest.raises(ValueError, match=rf"probe tier 7: findings\.{name}, which says .*, is not settled yet\."):
        shafts = shafts_of(reducer())
        layout.layout_plan(shafts, "", r"C:\P\T.SLDPRT")
        layout.assembly_plan(r"C:\P\T.SLDPRT", (), "", r"C:\P\T.SLDASM")


def test_a_finding_this_version_does_not_know_is_refused(monkeypatch):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", "drag it", raising=False)
    with pytest.raises(ValueError, match="REPLACE_FIXED_ROUTE is 'drag it'"):
        layout.assembly_plan(r"C:\P\L.SLDPRT", (), "", r"C:\P\A.SLDASM")


# -- the assembly ----------------------------------------------------------------------------------


def frame_at(x):
    return layout.Frame(layout.IDENTITY, (x, 0.0, 0.0))


def test_the_assembly_inserts_the_layout_first_at_identity_and_fixed():
    parts = [("gear1", r"C:\P\A.SLDPRT", frame_at(0.0)), ("gear2", r"C:\P\B.SLDPRT", frame_at(10.0)),
             ("gear3", r"C:\P\A.SLDPRT", frame_at(20.0))]
    plan = layout.assembly_plan(r"C:\P\R_Layout.SLDPRT", parts, r"C:\T\Asm.ASMDOT", r"C:\P\R.SLDASM")
    assert plan.check() == []
    assert plan.ops[:4] == (NewAssembly(r"C:\T\Asm.ASMDOT"), AddComponent("layout", r"C:\P\R_Layout.SLDPRT",
                                                                          (0.0, 0.0, 0.0)),
                            Place("layout", layout.IDENTITY, (0.0, 0.0, 0.0)), Fix("layout"))
    assert plan.ops[4:7] == (AddComponent("gear1", r"C:\P\A.SLDPRT", (0.0, 0.0, 0.0)),
                             Place("gear1", layout.IDENTITY, (0.0, 0.0, 0.0)), Fix("gear1"))
    # the shared part goes in as often as it appears
    assert [op.path for op in plan.ops if isinstance(op, AddComponent)].count(r"C:\P\A.SLDPRT") == 2
    assert plan.ops[-2:] == (Rebuild(), SaveAs(r"C:\P\R.SLDASM"))
    assert not any(isinstance(op, Unfix) for op in plan.ops)


def test_the_assembly_unfixes_before_placing_where_a_fixed_component_will_not_move(monkeypatch):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", layout.REPLACE_UNFIXED, raising=False)
    plan = layout.assembly_plan(r"C:\P\L.SLDPRT", [("gear1", r"C:\P\A.SLDPRT", frame_at(5.0))], "",
                                r"C:\P\R.SLDASM")
    assert plan.check() == []
    assert [type(op).__name__ for op in plan.ops[1:9]] == ["AddComponent", "Unfix", "Place", "Fix"] * 2


def test_a_gear_handle_cannot_be_the_layouts():
    with pytest.raises(ValueError, match="layout"):
        layout.assembly_plan(r"C:\P\L.SLDPRT", [("layout", r"C:\P\A.SLDPRT", frame_at(0.0))], "", r"C:\P\R.SLDASM")


def test_stems():
    assert layout.stems("Reducer_12to1", 0) == ("Reducer_12to1", "Reducer_12to1_Layout")
    assert layout.stems("Reducer_12to1", 2) == ("Reducer_12to1_r2", "Reducer_12to1_r2_Layout")
    assert layout.stems("Reducer: 12/1", 3) == ("Reducer_ 12_1_r3", "Reducer_ 12_1_r3_Layout")
    for bad in (1, -1):
        with pytest.raises(ValueError, match="no revision"):
            layout.stems("R", bad)


# -- frames, held to the parts as they are built ---------------------------------------------------


def test_the_part_runs_along_its_own_plus_z():
    """Every frame here assumes the blank runs from its front face along local +Z."""
    assert findings.EXTRUDE_Z_SIGN == 1


def apply(f, point):
    r = f.rotation
    x, y, z = point
    return (r[0] * x + r[1] * y + r[2] * z + f.at[0],
            r[3] * x + r[4] * y + r[5] * z + f.at[1],
            r[6] * x + r[7] * y + r[8] * z + f.at[2])


def is_rotation(r):
    m = [r[0:3], r[3:6], r[6:9]]
    for i in range(3):
        for j in range(3):
            assert sum(m[k][i] * m[k][j] for k in range(3)) == pytest.approx(1.0 if i == j else 0.0, abs=1e-12)
    det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
           + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    assert det == pytest.approx(1.0, abs=1e-12), "a mirror is not a placement"


def section_by_frame(gear_spec, f, height, extra=0.0):
    """The part's own outline where the assembly's plane at global ``height`` cuts it, carried there by the frame
    alone: the local height is found by inverting the frame, the outline turned as the part's plan builds that
    height (``built_turn``), then every local point mapped by R and at. ``extra`` turns the part about its own
    axis first (the half-pitch control)."""
    face = float(gear_spec.face_width)
    # The frame's third row is (0, 0, σ): the local height a global height lies at.
    sigma = f.rotation[8]
    assert f.rotation[6:8] == (0.0, 0.0) and abs(sigma) == 1.0
    z_local = (height - f.at[2]) * sigma
    assert -1e-9 <= z_local <= face + 1e-9, (z_local, face)
    turn = built_turn(gear_spec)(z_local) + extra
    c, s = math.cos(turn), math.sin(turn)
    out = []
    for u, v in outline(gear_spec):
        x, y, z = apply(f, (u * c - v * s, u * s + v * c, z_local))
        assert z == pytest.approx(height, abs=1e-9)
        out.append((x, y))
    return out


def mesh_by_frames(spec, a_id, b_id, ring=False):
    """Assess the spec as the window does, plan the frames, and hold the two parts to them across the face."""
    a = assess.assess(spec, [], FOLDER)
    assert a.errors == [] and a.lay_out_refusal() == ""
    framed = layout.frames(a.report)
    placed = a.report.layout.placed
    specs = {g.id: g.gear_spec(spec.box) for g in spec.gears}
    for gear in (a_id, b_id):
        p, f = placed[gear], framed[gear]
        is_rotation(f.rotation)
        assert f.at == (p.x, p.y, p.z_front)
        # the middle of the face lands on the shaft at the gear's height
        assert apply(f, (0.0, 0.0, p.face / 2)) == pytest.approx((p.x, p.y, p.z), abs=1e-12)
    pa, pb = placed[a_id], placed[b_id]
    lo, hi = max(pa.z_range[0], pb.z_range[0]), min(pa.z_range[1], pb.z_range[1])
    heights = [lo + 0.25, lo + (hi - lo) * 0.3, (lo + hi) / 2, lo + (hi - lo) * 0.7, hi - 0.25]
    count = ring_interference if ring else interference
    for height in heights:
        sa = section_by_frame(specs[a_id], framed[a_id], height)
        right = section_by_frame(specs[b_id], framed[b_id], height)
        wrong = section_by_frame(specs[b_id], framed[b_id], height, math.pi / pb.teeth)
        assert count(sa, right) == 0, height
        assert count(sa, wrong) > 0, height
    return heights


@pytest.mark.parametrize("facing", FACINGS)
def test_spur_gears_mesh_where_their_frames_put_them(facing):
    mesh_by_frames(outside_pair("spur", facing), "A", "B")


@pytest.mark.parametrize("facing", FACINGS)
@pytest.mark.parametrize("hands", [("right", "left"), ("left", "right")])
@pytest.mark.parametrize("heights", [(10.0, 10.0), (10.0, 13.0)])
def test_helical_gears_mesh_where_their_frames_put_them(facing, hands, heights):
    mesh_by_frames(outside_pair("helical", facing, hands, heights=heights, beta="20"), "A", "B")


@pytest.mark.parametrize("facing", FACINGS)
@pytest.mark.parametrize("faces", [("20", "30"), ("30", "20")])
def test_herringbones_of_unequal_widths_mesh_where_their_frames_put_them(facing, faces):
    hands = ("right", "left") if facing[0] == facing[1] else ("right", "right")
    heights = mesh_by_frames(outside_pair("herringbone", facing, hands, faces=faces, heights=(15.0, 15.0),
                                          beta="30"), "A", "B")
    assert min(heights) < 15 < max(heights)          # both halves


@pytest.mark.parametrize("facing", FACINGS)
def test_a_spur_ring_and_its_pinion_mesh_where_their_frames_put_them(facing):
    mesh_by_frames(ring_pair("spur", facing), "Ring", "Pin", ring=True)


@pytest.mark.parametrize("facing", FACINGS)
@pytest.mark.parametrize("hand", ["right", "left"])
def test_a_helical_ring_and_its_pinion_mesh_where_their_frames_put_them(facing, hand):
    mesh_by_frames(ring_pair("helical", facing, (hand, hand), faces=("12", "10"), beta="15"), "Ring", "Pin",
                   ring=True)


@pytest.mark.parametrize("facing", FACINGS)
def test_a_herringbone_ring_and_its_pinion_mesh_where_their_frames_put_them(facing):
    hands = ("right", "right") if facing[0] == facing[1] else ("right", "left")
    mesh_by_frames(ring_pair("herringbone", facing, hands, faces=("30", "20"), beta="30"), "Ring", "Pin",
                   ring=True)


def test_the_reducer_meshes_where_its_frames_put_it_and_g2_turns_the_pair_mesh_angle():
    spec = reducer()
    for a_id, b_id in (("G1", "G2"), ("G3", "G4")):
        mesh_by_frames(spec, a_id, b_id)
    framed = layout.frames(assess.assess(spec, [], FOLDER).report)
    r = framed["G2"].rotation
    assert math.degrees(math.atan2(r[3], r[0])) == pytest.approx(pairs.mesh_angle(68), abs=1e-9)
    assert framed["G1"].rotation == layout.IDENTITY and framed["G2"].at == (63.75, 0.0, 0.0)
    assert framed["G4"].at == (131.75, 0.0, 17.0)                      # At 27 less half its 20 mm face


def test_a_gear_on_z_minus_is_turned_over_about_x_not_y():
    """rot_x(180°) keeps a space at θ on −θ seen from +Z, as geometry's mirror does; rot_y would put it at π−θ."""
    spec = outside_pair("spur", ("Z+", "Z-"))
    a = assess.assess(spec, [], FOLDER)
    p, f = a.report.layout.placed["B"], layout.frames(a.report)["B"]
    theta = a.report.theta["B"]
    x, y, _ = apply(f, (1.0, 0.0, 0.0))
    assert math.atan2(y - p.y, x - p.x) == pytest.approx(math.atan2(math.sin(-theta), math.cos(-theta)), abs=1e-12)
    assert apply(f, (0.0, 0.0, 1.0))[2] == pytest.approx(f.at[2] - 1.0)


def test_pitch_and_the_shared_comparison_of_frames():
    a = assess.assess(reducer(), [], FOLDER)
    p = a.report.layout.placed["G2"]
    assert layout.pitch(p) == pytest.approx(360 / 68)
    f = layout.frame(p, a.report.theta["G2"])
    turned = layout.frame(p, a.report.theta["G2"] + 3 * 2 * math.pi / 68)
    half = layout.frame(p, a.report.theta["G2"] + math.pi / 68)
    assert swbuild.same_frame(f.rotation, f.at, turned.rotation, turned.at, layout.pitch(p))
    assert not swbuild.same_frame(f.rotation, f.at, half.rotation, half.at, layout.pitch(p))


def test_kind_for_every_case_above_is_built_by_a_plan():
    """The cases above reach every kind of part whose section the frames carry."""
    seen = set()
    for kind in ("spur", "helical", "herringbone"):
        for spec in (outside_pair(kind, ("Z+", "Z+"), ("right", "left") if kind != "spur" else ("", ""),
                                  beta="20" if kind != "spur" else ""),
                     ring_pair(kind, ("Z+", "Z+"), ("right", "right") if kind != "spur" else ("", ""),
                               beta="15" if kind != "spur" else "")):
            for g in spec.gears:
                seen.add(type(kind_for(g.gear_spec(spec.box))).__name__)
    assert seen == {"SpurGear", "HelicalGear", "HerringboneGear", "InternalSpurGear", "InternalHelicalGear",
                    "InternalHerringboneGear"}


def test_checks_agree_the_cases_are_clean():
    assert [d for d in checks.check(outside_pair("helical", ("Z+", "Z-"), ("right", "left"), beta="20")).diagnostics
            if d.is_error] == []
