# Emits the artboards the window of design/UI-DESIGN.md §2 was designed on, from
# the app's own maths and the design builders in ui.py (Airfoil Converter's,
# unchanged). The copy and the diagrams here are now also in the app itself —
# ui_text.explainer and widgets.draw_diagram — so a change belongs in both.
# Run it with the venv:
#     .venv/bin/python design/canvas/gen.py
# It writes Main, SingleGear and FieldGuide .dc.html and canvas.json beside itself.
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                              # ui.py, beside this file
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))             # the app's own maths
from ui import *
from gear_generator.gears import KINDS, spur, pair as pairs
from gear_generator.spec import GearSpec, PairSpec, pair_stems
from gear_generator import ui_text

K = KINDS["spur"]
HEADER_TEXT, READOUT = "#505050", "#8f8f8f"
CARD_BG, CARD_BORDER = "#fafafa", "#cfcfcf"

SIDE_ICON = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1.5"></rect><path d="M10 3v10"></path></svg>'
REFRESH_ICON = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13.2 6.6A5.4 5.4 0 1 0 12.6 10.6"></path><path d="M12.4 2.4l.5 3.8-3.7-.8"></path></svg>'
INFO_ICON = f'<span style="width: 15px; flex-shrink: 0; display: inline-flex; justify-content: center; color: {MUTED};"><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="8" cy="8" r="6.3"></circle><path d="M8 7.2v4"></path><path d="M8 4.8v0.2"></path></svg></span>'

# ------------------------------------------------------------------ pieces

def gfield(text, unit="", w="84px", placeholder=False, grow=False, focused=False, disabled=False):
    """ui.field with the focus border the Tk Field paints (#2b2b2b) when it has the caret."""
    width = "flex-grow: 1; min-width: 0;" if grow else f"width: {w};"
    bg = DISABLED_BG if disabled else "#ffffff"
    border = ACCENT if focused else ("#e3e3e3" if disabled else BORDER)
    color = FAINT if (disabled or placeholder) else INK
    unit_html = f'<span style="color: {READOUT}; font-family: {SANS}; font-size: 11.5px;">{unit}</span>' if unit else ""
    caret = f'<span style="width: 1px; height: 14px; background: {INK}; margin-left: 1px;"></span>' if focused else ""
    just = "space-between" if unit else "flex-start"
    return (f'<div style="{width} height: 26px; box-sizing: border-box; border: 1px solid {border}; border-radius: 2px; background: {bg}; '
            f'padding: 0 8px; display: flex; align-items: center; justify-content: {just}; font-family: {MONO}; font-size: 12.5px; color: {color}; overflow: hidden; white-space: nowrap;">'
            f'<span style="display: inline-flex; align-items: center;">{text}{caret}</span>{unit_html}</div>')

def dot(color, size=7):
    return f'<span style="width: {size}px; height: {size}px; flex-shrink: 0; border-radius: 50%; background: {color};"></span>'

def readout_header(readout, *buttons):
    return (f'<span style="display: flex; align-items: center; gap: 8px;">'
            f'<span style="font-size: 11.5px; color: {READOUT};">{readout}</span>' + "".join(buttons) + '</span>')

def caption(text):
    return f'<div style="flex-shrink: 0; font-size: 12px; color: {MUTED}; padding: 2px 2px 0 2px;">{text}</div>'

def section_caption(text):
    return f'<div style="flex-shrink: 0; font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: {HEADER_TEXT}; padding: 6px 2px 0 2px;">{text}</div>'

def rule(margin="2px 0"):
    return f'<div style="height: 1px; background: {TRACK}; margin: {margin};"></div>'

# ------------------------------------------------------------ the gear maths

def gear(z, module="1.5", angle="20", bore="10"):
    spec = GearSpec(module=module, teeth=str(z), pressure_angle=angle, bore=bore)
    derived = K.derive(spec)
    return spec, derived, K.outline(spec, derived), K.validate(spec, derived)

def n(v, places=3):
    return ui_text._n(v, places)

# ---------------------------------------------------------- the mesh preview

def _path(points, cx, cy, scale, rot=0.0):
    c, s = math.cos(rot), math.sin(rot)
    parts, last = [], None
    for x, y in points:
        xr, yr = x * c - y * s, x * s + y * c
        px, py = round(cx + xr * scale, 1), round(cy - yr * scale, 1)
        if (px, py) == last:
            continue
        parts.append(f"{'M' if not parts else 'L'}{px} {py}")
        last = (px, py)
    return " ".join(parts) + " Z"

def _arrow_line(x0, x1, y, color=HEADER_TEXT):
    """A dimension line with filled arrowheads at both ends."""
    return (f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{color}" stroke-width="1"></line>'
            f'<path d="M{x0} {y} l7 -3 v6 z" fill="{color}"></path>'
            f'<path d="M{x1} {y} l-7 -3 v6 z" fill="{color}"></path>')

def preview(gears, width=436, height=210, labels=("A", "B")):
    """Both gears meshed at the centre distance their teeth make, one scale, with the dimension that matters.

    ``gears`` is one or two (derived, outline) pairs. Two gears: the second is turned so a tooth
    points at the first's centre, and the centre distance is dimensioned below. One gear: the pitch
    diameter is dimensioned, since that is what module × teeth comes to.
    """
    pad, dim_zone, top = 14, 46, 8
    ras = [d.ra for d, _ in gears]
    C = (gears[0][0].d + gears[1][0].d) / 2 if len(gears) == 2 else 0.0
    extent = ras[0] + C + ras[-1] if C else 2 * ras[0]
    gear_h = height - dim_zone - top
    scale = min((width - 2 * pad) / extent, gear_h / (2 * max(ras)))
    cy = top + gear_h / 2
    left = (width - extent * scale) / 2
    cxs = [left + ras[0] * scale]
    if C:
        cxs.append(cxs[0] + C * scale)
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" style="display: block; flex-shrink: 0;">']
    # pitch circles first, faint and dashed, so the two touching at the pitch point is what says "meshed"
    for (d, _), cx in zip(gears, cxs):
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{d.rp * scale:.1f}" stroke="{BORDER_SOFT}" stroke-width="1" stroke-dasharray="3 3"></circle>')
    for index, ((d, o), cx) in enumerate(zip(gears, cxs)):
        rot = 0.0 if index == 0 else math.pi + (math.pi / d.teeth if d.teeth % 2 == 0 else 0.0)
        out.append(f'<path d="{_path(o, cx, cy, scale, rot)}" stroke="{HEADER_TEXT}" stroke-width="1" stroke-linejoin="round"></path>')
        if d.bore > 0:
            out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{d.bore / 2 * scale:.1f}" stroke="{HEADER_TEXT}" stroke-width="1"></circle>')
        # centre mark and the gear's letter
        out.append(f'<path d="M{cx - 5:.1f} {cy:.1f} h10 M{cx:.1f} {cy - 5:.1f} v10" stroke="{READOUT}" stroke-width="1"></path>')
        if len(gears) > 1:
            out.append(f'<text x="{cx + 8:.1f}" y="{cy - 8:.1f}" font-family="{SANS}" font-size="11" fill="{READOUT}">{labels[index]}</text>')
    y_dim = cy + max(ras) * scale + 24
    if C:
        x0, x1 = cxs
        for x in (x0, x1):
            out.append(f'<line x1="{x:.1f}" y1="{cy + 6:.1f}" x2="{x:.1f}" y2="{y_dim + 4:.1f}" stroke="{BORDER}" stroke-width="1"></line>')
        out.append(_arrow_line(f"{x0:.1f}", f"{x1:.1f}", f"{y_dim:.1f}"))
        label = f"C {n(C)} mm"
    else:
        cx, d = cxs[0], gears[0][0]
        x0, x1 = cx - d.rp * scale, cx + d.rp * scale
        for x in (x0, x1):
            out.append(f'<line x1="{x:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y_dim + 4:.1f}" stroke="{BORDER}" stroke-width="1"></line>')
        out.append(_arrow_line(f"{x0:.1f}", f"{x1:.1f}", f"{y_dim:.1f}"))
        label = f"PD {n(d.d)} mm"
    out.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{y_dim - 6:.1f}" text-anchor="middle" font-family="{MONO}" font-size="11.5" fill="{INK}">{label}</text>')
    out.append('</svg>')
    return "".join(out)

# ------------------------------------------------------------ derived rows

def value_row(label_text, values, widths=(104, 96)):
    cells = f'<span style="width: {widths[0]}px; flex-shrink: 0; font-size: 12px; color: {LABEL};">{label_text}</span>'
    for v in values:
        cells += f'<span style="width: {widths[1]}px; flex-shrink: 0; font-family: {MONO}; font-size: 11.5px; color: {INK};">{v}</span>'
    return f'<div style="display: flex; align-items: center; gap: 8px; height: 18px;">{cells}</div>'

def derived_table(deriveds, tags):
    rows = []
    heads = f'<span style="width: 104px; flex-shrink: 0;"></span>'
    for tag in tags:
        heads += f'<span style="width: 96px; flex-shrink: 0; font-size: 11px; color: {READOUT};">{tag}</span>'
    rows.append(f'<div style="display: flex; align-items: center; gap: 8px; height: 16px;">{heads}</div>')
    columns = [dict(ui_text.derived_rows(d)) for d in deriveds]
    for label_text, _ in ui_text.derived_rows(deriveds[0]):
        rows.append(value_row(label_text, [c[label_text] for c in columns]))
    return f'<div style="display: flex; flex-direction: column;">' + "".join(rows) + '</div>'

def warning(text, error=False):
    return f'<div style="font-size: 12px; color: {ERR if error else MUTED}; line-height: 1.35;">{text}</div>'

# ------------------------------------------------------- the field explainer
#
# One card at the foot of the gear panel that has the caret. It names the field,
# says in two sentences what the number is, and works the typed value out.

def _svg(body, w=56, h=56):
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" stroke="{HEADER_TEXT}" stroke-width="1.2" '
            f'stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0; display: block;">{body}</svg>')

def _gear_glyph(cx, cy, r_out, r_in, teeth, highlight_tooth=None):
    pts, hi = [], []
    for i in range(teeth):
        a0 = 2 * math.pi * i / teeth
        step = 2 * math.pi / teeth
        for frac, r in ((0.0, r_in), (0.18, r_out), (0.5, r_out), (0.68, r_in)):
            a = a0 + frac * step
            pts.append((cx + r * math.cos(a), cy - r * math.sin(a)))
            if i == highlight_tooth and frac in (0.18, 0.5):
                hi.append((cx + r * math.cos(a), cy - r * math.sin(a)))
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"
    out = f'<path d="{d}"></path>'
    if hi:
        # the highlighted tooth: its two tip corners and the root corners either side
        a0 = 2 * math.pi * highlight_tooth / teeth
        step = 2 * math.pi / teeth
        corners = [(cx + r * math.cos(a0 + f * step), cy - r * math.sin(a0 + f * step)) for f, r in ((0.0, r_in), (0.18, r_out), (0.5, r_out), (0.68, r_in))]
        out += f'<path d="M' + " L".join(f"{x:.1f} {y:.1f}" for x, y in corners) + f'" stroke="{ACCENT}" stroke-width="1.8"></path>'
    return out

DIAGRAMS = {
    # a tooth on its pitch line, the addendum (one module) dimensioned
    "module": _svg(f'<path d="M4 44 H12 L18 16 H30 L36 44 H52"></path>'
                   f'<path d="M4 30 H52" stroke="{BORDER}" stroke-dasharray="3 2"></path>'
                   f'<path d="M45 16 V30" stroke="{ACCENT}" stroke-width="1.8"></path><path d="M42 16 H48 M42 30 H48" stroke="{ACCENT}"></path>'
                   f'<text x="49" y="26" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">m</text>'),
    "teeth": _svg(_gear_glyph(28, 28, 22, 16, 12, highlight_tooth=2)),
    # the pitch point: tangent, pitch circle, and the line of action leaning α off the tangent
    "pressure_angle": _svg(f'<path d="M6 32.6 A40 40 0 0 1 50 32.6" stroke="{BORDER}" stroke-dasharray="3 2"></path>'
                           f'<path d="M4 26 H52"></path>'
                           f'<path d="M8 33.3 L48 18.7" stroke="{ACCENT}" stroke-width="1.8"></path>'
                           f'<path d="M42 26 A14 14 0 0 0 41.2 21.2" stroke="{ACCENT}"></path>'
                           f'<circle cx="28" cy="26" r="1.6" fill="{HEADER_TEXT}" stroke="none"></circle>'
                           f'<text x="45" y="38" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">α</text>'),
    # the gear from the side: a slab, its axis, and the width dimensioned
    "face_width": _svg(f'<rect x="21" y="8" width="14" height="36" rx="1"></rect>'
                       f'<path d="M12 26 H44" stroke="{BORDER}" stroke-dasharray="3 2"></path>'
                       f'<path d="M21 51 H35" stroke="{ACCENT}" stroke-width="1.8"></path><path d="M21 48 V54 M35 48 V54" stroke="{ACCENT}"></path>'
                       f'<text x="40" y="54" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">b</text>'),
    "bore": _svg(_gear_glyph(28, 28, 22, 17, 14) + f'<circle cx="28" cy="28" r="7" stroke="{ACCENT}" stroke-width="1.8"></circle>'),
    # a tooth sitting in the space of the other gear, the gap at the pitch line marked
    "backlash": _svg(f'<path d="M6 8 L15 48 H41 L50 8"></path>'
                     f'<path d="M14 8 L21 44 H35 L42 8"></path>'
                     f'<path d="M4 30 H52" stroke="{BORDER}" stroke-dasharray="3 2"></path>'
                     f'<path d="M11 30 H18.5" stroke="{ACCENT}" stroke-width="1.8"></path>'
                     f'<text x="4" y="24" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">j</text>'),
    # a flank meeting the root circle round a radius
    "fillet": _svg(f'<path d="M52 46 H30 Q22 46 20 38 L14 8"></path><path d="M4 46 H12"></path>'
                   f'<path d="M30 46 Q22 46 20 38" stroke="{ACCENT}" stroke-width="1.8"></path>'
                   f'<text x="30" y="38" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">ρ</text>'),
    "name": _svg(f'<path d="M15 6 H33 L42 15 V50 H15 Z"></path><path d="M33 6 V15 H42"></path>'
                 f'<path d="M21 26 H36 M21 32 H36 M21 38 H31" stroke="{BORDER}"></path>'),
    # two pitch circles touching, the distance between centres dimensioned
    "centre_distance": _svg(f'<circle cx="11" cy="26" r="8"></circle><circle cx="36" cy="26" r="17"></circle>'
                            f'<path d="M8 26 H14 M11 23 V29 M33 26 H39 M36 23 V29" stroke="{READOUT}"></path>'
                            f'<path d="M11 50 H36" stroke="{ACCENT}" stroke-width="1.8"></path><path d="M11 47 V53 M36 47 V53" stroke="{ACCENT}"></path>'
                            f'<text x="41" y="53" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">C</text>'),
    # a pinion and its wheel, one turn against three
    "ratio": _svg(f'<circle cx="14" cy="28" r="8" stroke="{ACCENT}" stroke-width="1.8"></circle><circle cx="38" cy="28" r="16"></circle>'
                  f'<text x="14" y="31.5" text-anchor="middle" font-family="{MONO}" font-size="9" fill="{ACCENT}" stroke="none">3</text>'
                  f'<text x="38" y="31.5" text-anchor="middle" font-family="{MONO}" font-size="9" fill="{HEADER_TEXT}" stroke="none">1</text>'),
    # the standard modules as a scale: tall ticks are series 1, short ones series 2
    "series": _svg(f'<path d="M4 34 H52"></path>'
                   f'<path d="M6 34 V22 M14 34 V22 M22 34 V22 M30 34 V22 M38 34 V22 M46 34 V22" stroke="{ACCENT}" stroke-width="1.8"></path>'
                   f'<path d="M10 34 V28 M18 34 V28 M26 34 V28 M34 34 V28 M42 34 V28 M50 34 V28" stroke="{READOUT}"></path>'
                   f'<text x="6" y="46" font-family="{MONO}" font-size="8" fill="{HEADER_TEXT}" stroke="none">1</text>'
                   f'<text x="20" y="46" font-family="{MONO}" font-size="8" fill="{HEADER_TEXT}" stroke="none">1.5</text>'
                   f'<text x="38" y="46" font-family="{MONO}" font-size="8" fill="{HEADER_TEXT}" stroke="none">2.5</text>'),
}
DIAGRAMS["pair_module"] = DIAGRAMS["series"]
DIAGRAMS["teeth_range"] = DIAGRAMS["teeth"]
DIAGRAMS["assembly_name"] = DIAGRAMS["name"]

def guide(key, d, side_stem, pair=None):
    """(title, symbol, what it is, what the typed value comes to) for one field.

    ``d`` is the SpurDerived of the gear the caret is in; ``pair`` a PairSpec in pair mode.
    """
    m, z = d.module, d.teeth
    rim = (d.df - d.bore) / 2 if d.bore else None
    G = {
        "module": ("Module", "m",
                   "Tooth size, in mm: the pitch diameter divided by the number of teeth. A bigger module means bigger, "
                   "stronger teeth and fewer of them for the same diameter. Two gears mesh only if their modules match.",
                   f"m {n(m)} × z {z} = PD {n(d.d)} mm · tooth depth {n(d.h)} · circular pitch {n(d.p)}"),
        "teeth": ("Teeth", "z",
                  "How many teeth go round the gear. With the module it sets the size, PD = m × z, and the ratio between two "
                  "gears is the ratio of their tooth counts. Fewer than 17 undercuts the root at 20°.",
                  f"z {z} → PD {n(d.d)} mm · OD {n(d.da)} mm · " + ("undercut" if d.undercut else f"no undercut ({d.undercut_limit} or more)")),
        "pressure_angle": ("Pressure angle", "α",
                           "The slant of the flank: the angle between the line along which the teeth push on each other and the "
                           "tangent to the pitch circle. 20° is the standard; 14.5° runs quieter but undercuts sooner, 25° is "
                           "stronger but loads the bearings more. Meshing gears must share it.",
                           f"{n(d.pressure_angle_deg, 2)}° → base diameter {n(d.db)} mm · undercut below {d.undercut_limit} teeth"),
        "face_width": ("Face width", "b",
                       "How thick the gear is along its axis: the depth it is extruded. Wider carries more load; "
                       "6 to 12 × module is usual for a spur gear.",
                       f"{n(d.face_width)} mm = {n(d.face_width / m, 1)} × module"),
        "bore": ("Bore", "",
                 "The hole through the centre for the shaft. Blank makes a solid disc. Leave a rim between the bore and "
                 "the root circle: the form warns under one module, and two to three is usual.",
                 f"{n(d.bore)} mm → rim {n(rim)} mm to the root circle" if rim else "blank → a solid disc, no bore feature"),
        "backlash": ("Backlash", "j",
                     "How much each tooth is thinned at the pitch circle so the pair does not bind: the space grows by this "
                     "and the tooth shrinks by it, on both gears, so the play in the mesh is twice the number. Blank uses "
                     "0.3 × module, the default the equations carry; ISO asks 0.02–0.05 × m for a precise pair.",
                     f"blank → {n(d.backlash)} mm (0.3 m) · tooth {n(d.s)} · space {n(d.space)} · play in the mesh {n(2 * d.backlash)}"),
        "fillet": ("Fillet", "ρ",
                   "The radius where each flank meets the root circle. It rounds off the sharp inside corner where a tooth "
                   "would otherwise crack. Blank uses 0.38 × module.",
                   f"blank → {n(d.fillet)} mm (0.38 m)"),
        "name": ("Name", "",
                 "The file the part is saved as, without .SLDPRT. Blank uses the name shown, built from module and teeth; "
                 "in a pair the smaller gear is the pinion.",
                 f"{side_stem}.SLDPRT in D:\\Gears"),
    }
    if pair is not None:
        C = pair.centre_distance_mm()
        sums = " · ".join(f"{int(round(2 * C / mm))} at m {n(mm)}" for mm in (1.5, 1.25, 1.0))
        G.update({
            "centre_distance": ("Centre distance", "C",
                                "Shaft to shaft, centre to centre. Standard gears sit at C = m (z₁ + z₂) / 2, their pitch circles "
                                "touching, so C fixes how many teeth the pair has between them once a module is chosen.",
                                f"{n(C)} mm → z₁ + z₂ = {sums}"),
            "ratio": ("Ratio", "i",
                      "Turns of the driver for one turn of the driven gear, z₂ / z₁. 3 or 3:1 makes the second gear three "
                      "times the first; 1:3 makes it a third.",
                      f"{pair.ratio} → 20 : 60"),
            "pair_module": ("Module", "m",
                            "Pin the module the solver may use, or leave it blank to try every standard one in the chosen series.",
                            "blank → 1 · 1.25 · 1.5 · 2 · 2.5 · 3 · 4 … from Series 1"),
            "series": ("Series", "",
                       "Which standard modules the solver tries. Series 1 is the preferred set (1, 1.25, 1.5, 2, 2.5 …); "
                       "1 + 2 adds the in-between sizes (1.125, 1.375 …); + fine adds 0.5, 0.6, 0.7, 0.8 and 0.9 for small gears.",
                       "Series 1 → 18 modules from 1 to 50 (ISO 54)"),
            "teeth_range": ("Teeth", "min to max",
                            "The tooth counts the solver may give either gear. Below 17 a 20° pinion undercuts; the maximum "
                            "keeps the list short.",
                            "17 to 200 → 64 candidates at C 60, i 3 · 3 exact"),
            "assembly_name": ("Assembly name", "",
                              "The file the assembly is saved as, without .SLDASM. Blank uses the name shown, built from the module "
                              "and both tooth counts.",
                              "Pair_m1.5_20T_60T.SLDASM in D:\\Gears"),
        })
    return G[key]

def explainer(key, d, side_stem, pair=None):
    title, symbol, what, comes_to = guide(key, d, side_stem, pair)
    sym = f'<span style="font-family: {MONO}; font-weight: 400; color: {MUTED};"> · {symbol}</span>' if symbol else ""
    return (f'<div style="display: flex; align-items: flex-start; gap: 10px; box-sizing: border-box; border: 1px solid {CARD_BORDER}; '
            f'border-radius: 2px; background: {CARD_BG}; padding: 8px 10px;">{DIAGRAMS[key]}'
            f'<div style="display: flex; flex-direction: column; gap: 4px; min-width: 0;">'
            f'<span style="font-size: 12.5px; font-weight: 600; color: {INK};">{title}{sym}</span>'
            f'<span style="font-size: 12px; color: {HEADER_TEXT}; line-height: 1.35;">{what}</span>'
            f'<span style="font-family: {MONO}; font-size: 11.5px; color: {INK}; margin-top: 2px;">'
            f'<span style="font-family: {SANS}; color: {READOUT};">here </span>{comes_to}</span>'
            f'</div></div>')

# ------------------------------------------------------------------ panels

def gear_kind_panel(mode):
    return panel("Gear", "Spur · involute curve", [
        row(label("Kind"), seg(["Spur", "Bevel", "Helical", "Internal"], "Spur", disabled=("Bevel", "Helical", "Internal")), hint("later")),
        row(label("Flank"), seg(["Involute", "Arcs"], "Involute", w="200px")),
        row(label("Make"), seg(["Single gear", "Gear pair"], mode, w="200px")),
    ])

def pair_panel(summary):
    header = readout_header("C 60 mm · i 3 · m1.5 20:60", button("Candidates", SIDE_ICON, h=20))
    return panel("Pair", "", [
        row(label("Centre distance"), gfield("60", "mm")),
        row(label("Ratio"), gfield("3"), hint("3, or 1:3 for driven over driver")),
        row(label("Module"), gfield("any", "mm", placeholder=True), hint("blank tries every standard one")),
        row(label("Series"), seg(["Series 1", "1 + 2", "+ fine"], "Series 1", w="220px")),
        row(label("Teeth"), gfield("17", w="60px"), f'<span style="font-size: 12.5px; color: {LABEL};">to</span>', gfield("200", w="60px"), hint("under min is undercut")),
        row(label("Assembly name"), gfield("Pair_m1.5_20T_60T", w="220px", placeholder=True)),
        row(button("Solve", REFRESH_ICON), hint(summary)),
    ], extra_header=header)

def side_panel(title, spec, d, stem, focused="", card=None, pair=None):
    """A gear's fields; ``focused`` names the field with the caret and ``card`` shows its explainer."""
    def f(key, text, **kw):
        return gfield(text, focused=(focused == key), **kw)
    rows = [
        row(label("Module"), f("module", spec.module, unit="mm"), dropdown("", "72px"), hint("ISO 54")),
        row(label("Teeth"), f("teeth", spec.teeth)),
        row(label("Pressure angle"), f("pressure_angle", spec.pressure_angle, unit="°"), dropdown("", "72px")),
        row(label("Face width"), f("face_width", spec.face_width, unit="mm")),
        row(label("Bore"), f("bore", spec.bore or "none", unit="mm", placeholder=not spec.bore)),
        row(label("Backlash"), f("backlash", "0.3 × module", unit="mm", w="150px", placeholder=True), hint("ISO: 0.02–0.05 × m")),
        row(label("Fillet"), f("fillet", "0.38 × module", unit="mm", w="150px", placeholder=True)),
        row(label("Name"), f("name", stem, grow=True, placeholder=True)),
    ]
    if card:
        rows.append(explainer(card, d, stem, pair))
    return panel(title, ui_text.gear_readout(spec), rows)

def derived_panel(gears, tags, diagnostics, readout, pair_rows=None):
    body = [preview([(d, o) for d, o in gears], labels=tags)]
    if pair_rows:
        body.append('<div style="display: flex; flex-direction: column;">' + "".join(value_row(k, [v]) for k, v in pair_rows) + '</div>')
        body.append(rule("0 0 2px 0"))
    body.append(derived_table([d for d, _ in gears], [f"{t} · mm" for t in tags] if len(gears) > 1 else ["mm"]))
    for text, error in diagnostics:
        body.append(warning(text, error))
    return panel("Derived", readout, body)

def output_panel(pair_mode):
    rows = [
        row(label("Folder"), gfield("D:\\Gears", grow=True), button("Browse", FOLDER)),
        row(label("Part template"), gfield("SolidWorks default", grow=True, placeholder=True), button("Browse", FOLDER)),
    ]
    if pair_mode:
        rows.append(row(label("Assembly template"), gfield("SolidWorks default", grow=True, placeholder=True), button("Browse", FOLDER)))
    rows.append(row(button("Open .gear.json", FOLDER), hint("put a built gear back on the form")))
    return panel("Output", "D:\\Gears", rows)

def sw_bar(note, manual):
    header = (f'<span style="display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: {READOUT};">'
              f'{dot(OK)}SolidWorks 2026 — no document open</span>')
    rows = [row(INFO_ICON, f'<span style="font-size: 12px; color: {INK}; line-height: 1.35;">{note}</span>', gap=8, align="flex-start")]
    if manual:
        rows.append(row('<span style="width: 15px; flex-shrink: 0;"></span>', f'<span style="font-size: 12px; color: {MUTED}; line-height: 1.35;">{manual}</span>', gap=8, align="flex-start"))
    return panel("SolidWorks", "", rows, gap=4, extra_header=header)

def footer(status, update=False):
    buttons = (button("Update values", h=32) if update else "") + button("Build", primary=True, h=32)
    return (f'<div style="margin-top: auto; display: flex; align-items: center; justify-content: space-between; gap: 12px;">'
            f'<div style="display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: {OK}; min-width: 0;">{dot(OK, 8)}'
            f'<span style="overflow: hidden; white-space: nowrap; text-overflow: ellipsis;">{status}</span></div>'
            f'<div style="display: flex; gap: 8px; flex-shrink: 0;">{buttons}</div></div>')

# -------------------------------------------------------------------- pages

HEAD = f'''<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
  <style>
    body {{ margin: 0; background: #f0f0f0; }}
    a {{ color: {ACCENT}; }} a:hover {{ color: #000000; }}
  </style>
</helmet>
'''
TAIL = '''</x-dc>
</body>
</html>
'''

def column(min_height, body, gap=8, width=484):
    """The strip as the app draws it: 460 px of content inside 12 px of window ground."""
    return (f'<div style="width: {width}px; min-height: {min_height}px; flex-shrink: 0; box-sizing: border-box; background: #f0f0f0; color: {INK}; '
            f'font-family: {SANS}; font-size: 13px; line-height: 1.3; display: flex; flex-direction: column; gap: {gap}px; padding: 12px;">\n' + body + '\n</div>')

def page(min_height, body, gap=8):
    return HEAD + column(min_height, body, gap) + '\n' + TAIL

# -- the pair the docs use throughout: C 60, i 3 → m 1.5, 20 : 60
spec_a, d_a, o_a, diag_a = gear(20)
spec_b, d_b, o_b, diag_b = gear(60)
pair_spec = PairSpec(mode="pair", centre_distance="60", ratio="3", gear_a=spec_a, gear_b=spec_b)
stem_a, stem_b, stem_pair = pair_stems(pair_spec)
candidates = pairs.solve_spec(pair_spec)
C, ratio, eps = pairs.describe(1.5, 20, 60, 20.0)
summary = f"{ui_text.solve_summary(candidates)} · m1.5 20 : 60 chosen"
diagnostics = [("A: " + x.message, x.is_error) for x in diag_a] + [("B: " + x.message, x.is_error) for x in diag_b]

main = page(2160, "\n".join([
    gear_kind_panel("Gear pair"),
    pair_panel(summary),
    side_panel("Gear A", spec_a, d_a, stem_a, focused="module", card="module", pair=pair_spec),
    side_panel("Gear B", spec_b, d_b, stem_b),
    derived_panel([(d_a, o_a), (d_b, o_b)], ("A", "B"), diagnostics,
                  f"C {n(C)} mm · i {n(ratio)} · contact ratio {ui_text.contact_ratio_text(eps)}",
                  pair_rows=[("Centre distance", f"{n(C)} mm"), ("Ratio", f"{n(ratio)}  ·  20 : 60"), ("Contact ratio", ui_text.contact_ratio_text(eps))]),
    output_panel(True),
    sw_bar(ui_text.mode_note("pair", [stem_a, stem_b, stem_pair]),
           ui_text.manual_steps_line([f"Assign a material to {stem_a}; the build leaves it unset.", f"Assign a material to {stem_b}; the build leaves it unset.", "Look along the gear axis and check the teeth mesh without clashing."])),
    footer("Both gears now carry module 1.5: 20 and 60 teeth."),
]))
open(os.path.join(HERE, "Main.dc.html"), "w").write(main)

# -- single mode: the default gear, the caret in Pressure angle
spec_s, d_s, o_s, diag_s = gear(25)
single = page(1380, "\n".join([
    gear_kind_panel("Single gear"),
    side_panel("Gear", spec_s, d_s, spec_s.default_stem(), focused="pressure_angle", card="pressure_angle"),
    derived_panel([(d_s, o_s)], ("",), [(x.message, x.is_error) for x in diag_s], ui_text.derived_line(d_s)),
    output_panel(False),
    sw_bar(ui_text.mode_note("single", [spec_s.default_stem()]), ""),
    footer("Type a gear, or switch to Gear pair to solve one."),
]))
open(os.path.join(HERE, "SingleGear.dc.html"), "w").write(single)

# -- every explainer, as the copy for whoever wires it up
cards = [section_caption("Gear A · Gear B — one card, shown for the field with the caret")]
for key in ("module", "teeth", "pressure_angle", "face_width", "bore", "backlash", "fillet", "name"):
    cards.append(explainer(key, d_a, stem_a, pair_spec))
cards.append(section_caption("Pair — the same card under the solver's fields"))
for key in ("centre_distance", "ratio", "pair_module", "series", "teeth_range", "assembly_name"):
    cards.append(explainer(key, d_a, stem_a, pair_spec))
cards.append(caption("Worked values are for Gear A of the pair on the main artboard: m 1.5, 20 teeth, 20°, bore 10, at C 60 and i 3."))
field_guide = page(1900, "\n".join(cards))
open(os.path.join(HERE, "FieldGuide.dc.html"), "w").write(field_guide)

canvas = {
    "artboards": [
        {"file": "Main.dc.html", "title": "Gear pair · new order", "x": 0, "y": 0, "w": 484, "h": 2160},
        {"file": "SingleGear.dc.html", "title": "Single gear · new order", "x": 564, "y": 0, "w": 484, "h": 1380},
        {"file": "FieldGuide.dc.html", "title": "Field explainers · all states", "x": 1128, "y": 0, "w": 484, "h": 1900},
    ],
    "annotations": [
        {"id": "note-order", "x": 0, "y": -250, "w": 484,
         "text": "Order, top to bottom, follows the work\nGear (what kind, one or two) · Pair (solve it: this fills the gears, so it comes before them; its Candidates button moves up here from the SolidWorks bar) · Gear A and Gear B (type or adjust) · Derived (what that comes to) · Output · SolidWorks · Build.\nToday Pair sits under Derived, so a pair is solved by going down, then back up, then down again."},
        {"id": "note-explainer", "x": 564, "y": -250, "w": 484,
         "text": "What the numbers mean, as you type\nOne card at the foot of the gear panel follows the caret: the field's name and symbol, two sentences on what it is, and the typed value worked out — m 1.5 × z 20 = PD 30 mm. The Tk field already knows when it has focus; the card swaps its text on that.\nThe third artboard has every card's copy and diagram."},
        {"id": "note-derived", "x": 0, "y": 2260, "w": 484,
         "text": "Derived, in pair mode\nBoth gears drawn at one scale, meshed at the centre distance their teeth make, the pitch circles dashed and touching at the pitch point. The centre distance is dimensioned below; a single gear gets its pitch diameter the same way. The values sit under it in two columns, with the pair's own three above them."},
    ],
    "launch": {"view": "canvas"},
}
json.dump(canvas, open(os.path.join(HERE, "canvas.json"), "w"), indent=2, ensure_ascii=False)
print("Main", len(main), "Single", len(single), "Guide", len(field_guide), "| candidates", len(candidates), "eps", round(eps, 3))
