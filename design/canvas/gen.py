# Emits the artboards of design/UI-DESIGN.md, drawn from the app itself: every
# word on a card is ui_text.explainer's, every readout and derived row
# ui_text's, and every picture preview.layout's, so an artboard cannot say
# something the window does not. What is only here is the HTML, and the SVG
# diagrams (DIAGRAMS), which are widgets.draw_diagram's strokes as paths — a
# change to one belongs in the other; which field borrows which diagram is read
# out of widgets.py itself. Run it with the venv:
#     .venv/bin/python design/canvas/gen.py
# It writes the .dc.html artboards and canvas.json beside itself; render.py
# turns them into design/renders/*.png.
import ast, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                              # ui.py, beside this file
sys.path.insert(0, os.path.join(HERE, "..", "..", "src"))             # the app's own maths
from ui import *
from gear_generator.gears import KINDS, kind_for, spur, pair as pairs
from gear_generator.spec import GearSpec, PairSpec, pair_stems
from gear_generator import findings, preview as layout_of, ui_text
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
    # a tooth, its pitch line, and the cutting rack's datum line x·m further out
    "profile_shift": _svg(f'<path d="M4 46 H11 L17 14 H31 L37 46 H52"></path>'
                          f'<path d="M4 36 H52 M4 27 H52" stroke="{BORDER}" stroke-dasharray="3 2"></path>'
                          f'<path d="M45 27 V36" stroke="{ACCENT}" stroke-width="1.8"></path><path d="M42 27 H48 M42 36 H48" stroke="{ACCENT}"></path>'
                          f'<text x="49" y="34" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">x</text>'),
    # the gear from the side, axis across: its teeth leaning β off the axis
    "helix_angle": _svg(f'<path d="M14 8 H42 V48 H14 Z"></path>'
                        f'<path d="M14 26 L42 10 M14 48 L42 32" stroke="{BORDER}"></path>'
                        f'<path d="M14 37 L42 21" stroke="{ACCENT}" stroke-width="1.8"></path>'
                        f'<path d="M14 37 H40" stroke="{BORDER}" stroke-dasharray="3 2"></path>'
                        f'<path d="M26 37 A12 12 0 0 0 24.39 31" stroke="{ACCENT}"></path>'
                        f'<text x="28" y="36" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">β</text>'),
    # a right-hand and a left-hand gear, axes upright, their teeth leaning the two ways
    "hand": _svg(f'<path d="M8 10 H24 V42 H8 Z M32 10 H48 V42 H32 Z"></path>'
                 f'<path d="M8 40 L24 24 M8 28 L24 12 M32 24 L48 40 M32 12 L48 28" stroke="{ACCENT}" stroke-width="1.8"></path>'
                 f'<text x="13" y="54" font-family="{MONO}" font-size="10" fill="{HEADER_TEXT}" stroke="none">R</text>'
                 f'<text x="37" y="54" font-family="{MONO}" font-size="10" fill="{HEADER_TEXT}" stroke="none">L</text>'),
    # a herringbone from the side: two toothed halves, their teeth leaning apart, the hub between
    "groove": _svg(f'<path d="M8 10 H22 V46 H8 Z M34 10 H48 V46 H34 Z M22 16 H34 M22 40 H34"></path>'
                   f'<path d="M10 24 L20 16 M10 34 L20 26 M10 44 L20 36 M36 16 L46 24 M36 26 L46 34 M36 36 L46 44" stroke="{BORDER}"></path>'
                   f'<path d="M22 51 H34" stroke="{ACCENT}" stroke-width="1.8"></path><path d="M22 48 V54 M34 48 V54" stroke="{ACCENT}"></path>'
                   f'<text x="38" y="55" font-family="{MONO}" font-size="10" fill="{ACCENT}" stroke="none">g</text>'),
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
    # a pinion and its wheel, each with an arrow round it the other way: they turn together
    "motion": _svg(f'<circle cx="14" cy="30" r="8"></circle><circle cx="38" cy="30" r="16"></circle>'
                   f'<path d="M19.5 20.47 A11 11 0 0 0 3 30" stroke="{ACCENT}" stroke-width="1.8"></path>'
                   f'<path d="M5 27 L3 30 L1 27" stroke="{ACCENT}"></path>'
                   f'<path d="M28.5 13.55 A19 19 0 0 1 52.55 17.79" stroke="{ACCENT}" stroke-width="1.8"></path>'
                   f'<path d="M52.15 14.2 L52.55 17.79 L49.09 16.78" stroke="{ACCENT}"></path>'),
    # the standard modules as a scale: tall ticks are series 1, short ones series 2
    "series": _svg(f'<path d="M4 34 H52"></path>'
                   f'<path d="M6 34 V22 M14 34 V22 M22 34 V22 M30 34 V22 M38 34 V22 M46 34 V22" stroke="{ACCENT}" stroke-width="1.8"></path>'
                   f'<path d="M10 34 V28 M18 34 V28 M26 34 V28 M34 34 V28 M42 34 V28 M50 34 V28" stroke="{READOUT}"></path>'
                   f'<text x="6" y="46" font-family="{MONO}" font-size="8" fill="{HEADER_TEXT}" stroke="none">1</text>'
                   f'<text x="20" y="46" font-family="{MONO}" font-size="8" fill="{HEADER_TEXT}" stroke="none">1.5</text>'
                   f'<text x="38" y="46" font-family="{MONO}" font-size="8" fill="{HEADER_TEXT}" stroke="none">2.5</text>'),
}

def _aliases():
    """widgets.DIAGRAM_ALIASES, read from the file so this needs no tkinter."""
    tree = ast.parse(open(os.path.join(HERE, "..", "..", "src", "gear_generator", "widgets.py"), encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DIAGRAM_ALIASES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("widgets.py has no DIAGRAM_ALIASES")


for alias, target in _aliases().items():
    DIAGRAMS.setdefault(alias, DIAGRAMS[target])

FOLDER_TEXT = "D:\\Gears"


def n(v, places=3):
    return ui_text._n(v, places)


# ------------------------------------------------------------ the gear maths

def worked(spec):
    """(spec, derived, outline, diagnostics) of one gear, as the window works it out."""
    kind = kind_for(spec)
    derived = kind.derive(spec)
    return spec, derived, kind.outline(spec, derived), kind.validate(spec, derived)


# ---------------------------------------------------------- the picture

def _arrow_line(x0, x1, y, color=HEADER_TEXT):
    """A dimension line with filled arrowheads at both ends."""
    return (f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="1"></line>'
            f'<path d="M{x0:.1f} {y:.1f} l7 -3 v6 z" fill="{color}"></path>'
            f'<path d="M{x1:.1f} {y:.1f} l-7 -3 v6 z" fill="{color}"></path>')


def _poly(points, closed=False):
    parts = [f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(points)]
    return " ".join(parts) + (" Z" if closed else "")


def picture(gears, labels=("A", "B"), note=""):
    """The Derived panel's picture: preview.layout's placement, stroked as SVG the way _draw_preview strokes it."""
    made = layout_of.layout([d for d, _ in gears], labels=labels, note=note)
    out = [f'<svg width="{made.width}" height="{made.height}" viewBox="0 0 {made.width} {made.height}" fill="none" '
           f'style="display: block; flex-shrink: 0;">']
    for placed in made.gears:
        if placed.pitch_radius > 0:
            out.append(f'<circle cx="{placed.x:.1f}" cy="{placed.y:.1f}" r="{placed.pitch_radius * made.scale:.1f}" '
                       f'stroke="{BORDER_SOFT}" stroke-width="1" stroke-dasharray="3 3"></circle>')
    for guide in made.guides:
        out.append(f'<path d="{_poly(guide)}" stroke="{BORDER_SOFT}" stroke-width="1" stroke-dasharray="3 3"></path>')
    for polyline in made.polylines:
        out.append(f'<path d="{_poly(polyline)}" stroke="{HEADER_TEXT}" stroke-width="1" stroke-linejoin="round"></path>')
    for placed, (_, outline) in zip(made.gears, gears):
        if not made.polylines:
            out.append(f'<path d="{_poly(layout_of.points_on(outline, placed, made.scale), True)}" stroke="{HEADER_TEXT}" '
                       f'stroke-width="1" stroke-linejoin="round"></path>')
        if placed.bore_radius > 0:
            out.append(f'<circle cx="{placed.x:.1f}" cy="{placed.y:.1f}" r="{placed.bore_radius * made.scale:.1f}" '
                       f'stroke="{HEADER_TEXT}" stroke-width="1"></circle>')
        out.append(f'<path d="M{placed.x - 5:.1f} {placed.y:.1f} h10 M{placed.x:.1f} {placed.y - 5:.1f} v10" '
                   f'stroke="{READOUT}" stroke-width="1"></path>')
        if placed.label:
            out.append(f'<text x="{placed.x + 8:.1f}" y="{placed.y - 8:.1f}" font-family="{SANS}" font-size="11" '
                       f'fill="{READOUT}">{placed.label}</text>')
    dim = made.dimension
    for x, top, bottom in dim.extensions:
        out.append(f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{bottom:.1f}" stroke="{BORDER}" stroke-width="1"></line>')
    out.append(_arrow_line(dim.x0, dim.x1, dim.y))
    out.append(f'<text x="{dim.text_x:.1f}" y="{dim.text_y:.1f}" text-anchor="middle" font-family="{MONO}" '
               f'font-size="11.5" fill="{INK}">{dim.text}</text>')
    out.append('</svg>')
    return "".join(out)


# ------------------------------------------------------------ derived rows

def value_row(label_text, values, widths=(104, 96)):
    """A label and its values. Tk's grid widens a column to fit what is in it, so a value never wraps: nor here."""
    cells = f'<span style="width: {widths[0]}px; flex-shrink: 0; font-size: 12px; color: {LABEL};">{label_text}</span>'
    for v in values:
        cells += (f'<span style="min-width: {widths[1]}px; flex-shrink: 0; white-space: nowrap; font-family: {MONO}; '
                  f'font-size: 11.5px; color: {INK};">{v}</span>')
    return f'<div style="display: flex; align-items: center; gap: 8px; height: 18px;">{cells}</div>'


def derived_table(deriveds, tags):
    """Every label once, in the order it first appears, and a dash where a gear has none — as the window does.

    A grid, as Tk's is: a column widens to its longest value and the others keep in line.
    """
    columns = [dict(ui_text.derived_rows(d)) for d in deriveds]
    labels = list(dict.fromkeys(label for d in deriveds for label, _ in ui_text.derived_rows(d)))
    cells = ['<span></span>'] + [f'<span style="font-size: 11px; color: {READOUT}; line-height: 16px;">{tag}</span>'
                                 for tag in tags]
    for label_text in labels:
        cells.append(f'<span style="font-size: 12px; color: {LABEL}; line-height: 18px;">{label_text}</span>')
        cells += [f'<span style="font-family: {MONO}; font-size: 11.5px; color: {INK}; line-height: 18px; '
                  f'white-space: nowrap;">{c.get(label_text, "—")}</span>' for c in columns]
    template = "104px " + " ".join(["minmax(96px, max-content)"] * len(deriveds))
    return (f'<div style="display: grid; grid-template-columns: {template}; column-gap: 8px; justify-content: start;">'
            + "".join(cells) + '</div>')


def warning(text, error=False):
    return f'<div style="font-size: 12px; color: {ERR if error else MUTED}; line-height: 1.35;">{text}</div>'


# ------------------------------------------------------- the field explainer

def explainer(key, d, side_stem, pair=None):
    title, symbol, what, comes_to = ui_text.explainer(key, d, side_stem, pair, FOLDER_TEXT)
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

KIND_SEG = {"spur": "Spur", "helical": "Helical", "herringbone": "Double", "bevel": "Bevel"}


def gear_kind_panel(kind, mode):
    return panel("Gear", ui_text.kind_readout(kind, "A"), [
        row(label("Kind"), seg(["Spur", "Helical", "Double", "Bevel"], KIND_SEG[kind])),
        row(label("Flank"), seg(["Involute", "Arcs"], "Involute", w="200px")),
        row(label("Make"), seg(["Single gear", "Gear pair"], mode, w="200px")),
    ])


def pair_panel(pair, summary, readout, focused="", card=None, d=None):
    """The solver, with the rows this kind of pair has — as _show_helix_rows decides them."""
    kind = pair.gear_a.kind
    bevel, helical = kind == "bevel", kind in ("helical", "herringbone")
    ring = not bevel and pair.mesh_value() == "internal"
    crossed = helical and not ring and pair.shafts_value() == "crossed"

    def f(key, text, **kw):
        return gfield(text, focused=(focused == key), **kw)

    rows = []
    if bevel:
        rows.append(row(label("Cone distance"), f("cone_distance", pair.cone_distance, unit="mm"), hint("apex to heel")))
    else:
        rows.append(row(label("Centre distance"), f("centre_distance", pair.centre_distance, unit="mm")))
    rows += [
        row(label("Ratio"), f("ratio", pair.ratio), hint("3, or 1:3 for driven over driver")),
        row(label("Module"), f("pair_module", pair.module or "any", unit="mm", placeholder=not pair.module),
            hint("blank tries every standard one")),
        row(label("Series"), seg(["Series 1", "1 + 2", "+ fine"], "Series 1", w="220px")),
        row(label("Teeth"), gfield(pair.min_teeth, w="60px"), f'<span style="font-size: 12.5px; color: {LABEL};">to</span>',
            gfield(pair.max_teeth, w="60px"), hint("under min is undercut")),
    ]
    if helical:
        rows.append(row(label("Helix angle"), gfield(pair.helix_angle or "any", unit="°", placeholder=not pair.helix_angle),
                        hint("blank solves it in the range")))
        if not crossed:
            rows.append(row(label("Helix range"), gfield("20" if kind == "herringbone" else "8", w="60px", unit="°", placeholder=True),
                            f'<span style="font-size: 12.5px; color: {LABEL};">to</span>',
                            gfield("40" if kind == "herringbone" else "25", w="60px", unit="°", placeholder=True)))
    if not bevel:
        rows.append(row(label("Mesh"), seg(["External", "Internal"], ui_text.MESH_LABELS[pair.mesh_value()], w="180px")))
    if helical and not ring:
        rows.append(row(label("Shafts"), seg(["Parallel", "Crossed"], ui_text.SHAFTS_LABELS[pair.shafts_value()], w="180px")))
    if bevel or crossed:
        rows.append(row(label("Shaft angle"), f("pair_shaft_angle", pair.shaft_angle, unit="°")))
    if crossed:
        rows.append(row(label("Hands"), seg(["Same", "Opposite"], ui_text.HANDS_PAIRING_LABELS[pair.hands_value()], w="180px")))
    if not bevel and not crossed:
        greyed = ("Gear mate",) if findings.GEAR_MATE_ROUTE is None else ()
        rows.append(row(label("Assembly"), seg(["Fixed", "Gear mate"], ui_text.MOTION_LABELS[pair.motion_value()],
                                               w="180px", disabled=greyed),
                        hint("not yet probed") if greyed else ""))
    rows += [
        row(label("Assembly name"), gfield(pair_stems(pair)[2], w="220px", placeholder=True)),
        row(button("Solve", REFRESH_ICON), hint(summary)),
    ]
    if card:
        rows.append(explainer(card, d, "", pair))
    header = readout_header(readout, button("Candidates", SIDE_ICON, h=20))
    return panel("Pair", "", rows, extra_header=header)


def side_panel(title, spec, d, stem, focused="", card=None, pair=None, side="a"):
    """A gear's fields with the rows this kind has; ``focused`` names the field with the caret, ``card`` its explainer."""
    def f(key, text, **kw):
        return gfield(text, focused=(focused == key), **kw)
    kind = spec.kind
    bevel, helical = kind == "bevel", kind in ("helical", "herringbone")
    ring = spec.is_internal() and not bevel
    pair_mode = pair is not None
    crossed = pair_mode and helical and not ring and pair.shafts_value() == "crossed" and \
        pair.mesh_value() != "internal"
    ring_pair = pair_mode and pair.mesh_value() == "internal" and not bevel
    takes_shift = not bevel and not ring and not (pair_mode and (ring_pair or crossed))
    rows = [
        row(label("Module"), f("module", spec.module, unit="mm"), dropdown("", "72px"), hint("ISO 54")),
        row(label("Teeth"), f("teeth", spec.teeth)),
        row(label("Pressure angle"), f("pressure_angle", spec.pressure_angle, unit="°"), dropdown("", "72px")),
        row(label("Face width"), f("face_width", spec.face_width, unit="mm")),
    ]
    if not ring:
        rows.append(row(label("Bore"), f("bore", spec.bore or "none", unit="mm", placeholder=not spec.bore)))
    rows += [
        row(label("Backlash"), f("backlash", spec.backlash or "0.3 × module", unit="mm", w="150px",
                                 placeholder=not spec.backlash), hint("ISO: 0.02–0.05 × m")),
        row(label("Fillet"), f("fillet", spec.fillet or ("0.15 × module" if ring else "0.38 × module"), unit="mm",
                               w="150px", placeholder=not spec.fillet)),
    ]
    if takes_shift:
        shifted = spec.profile_shift.strip() not in ("", "0")
        rows.append(row(label("Profile shift"), f("profile_shift", spec.profile_shift if shifted else "0", unit="× m",
                                                  placeholder=not shifted), hint("+ cures undercut")))
    if helical:
        rows.append(row(label("Helix angle"), f("helix_angle", spec.helix_angle, unit="°"), dropdown("", "72px"),
                        hint("normal module, α")))
        hand = ui_text.HAND_LABELS[spec.hand_value()]
        follows = pair_mode and side == "b"
        off = tuple(h for h in ("Right", "Left") if h != hand) if follows else ()
        rows.append(row(label("Hand"), seg(["Right", "Left"], hand, w="160px", disabled=off),
                        hint("follows gear A") if follows else ""))
    if kind == "herringbone" and not ring:
        rows.append(row(label("Groove"), f("groove", spec.groove or "none", unit="mm", placeholder=not spec.groove),
                        hint("between the two helices")))
    if not bevel and not pair_mode:
        rows.append(row(label("Teeth side"), seg(["External", "Internal"], "Internal" if ring else "External", w="180px")))
    if ring:
        rows.append(row(label("Rim"), f("rim", spec.rim or "root + 6 × module", unit="mm", w="190px", placeholder=not spec.rim)))
    if bevel and not pair_mode:
        rows.append(row(label("Shaft angle"), f("shaft_angle", spec.shaft_angle, unit="°"), hint("90 for a right angle")))
        rows.append(row(label("Mate teeth"), f("mate_teeth", spec.mate_teeth), hint("the gear it meshes with")))
    rows.append(row(label("Name"), f("name", stem, grow=True, placeholder=True)))
    if card:
        rows.append(explainer(card, d, stem, pair))
    return panel(title, ui_text.gear_readout(spec), rows)


def derived_panel(gears, tags, diagnostics, readout, pair_rows=None, note=""):
    body = [picture(gears, labels=tags, note=note)]
    if pair_rows:
        body.append('<div style="display: flex; flex-direction: column;">' + "".join(value_row(k, [v]) for k, v in pair_rows) + '</div>')
        body.append(rule("0 0 2px 0"))
    body.append(derived_table([d for d, _ in gears], [f"{t} · mm" for t in tags] if len(gears) > 1 else ["mm"]))
    for text, error in diagnostics:
        body.append(warning(text, error))
    return panel("Derived", readout, body)


def output_panel(pair_mode):
    rows = [
        row(label("Folder"), gfield(FOLDER_TEXT, grow=True), button("Browse", FOLDER)),
        row(label("Part template"), gfield("SolidWorks default", grow=True, placeholder=True), button("Browse", FOLDER)),
    ]
    if pair_mode:
        rows.append(row(label("Assembly template"), gfield("SolidWorks default", grow=True, placeholder=True), button("Browse", FOLDER)))
    rows.append(row(button("Open .gear.json", FOLDER), hint("put a built gear back on the form")))
    return panel("Output", FOLDER_TEXT, rows)


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


def column(body, gap=8, width=484, pad=12):
    """The strip as the app draws it: 460 px of content inside 12 px of window ground (a window's own ``pad``)."""
    return (f'<div style="width: {width}px; flex-shrink: 0; box-sizing: border-box; background: #f0f0f0; color: {INK}; '
            f'font-family: {SANS}; font-size: 13px; line-height: 1.3; display: flex; flex-direction: column; gap: {gap}px; padding: {pad}px;">\n' + body + '\n</div>')


def page(body, gap=8):
    return HEAD + column(body, gap) + '\n' + TAIL


def diagnostics_of(sides):
    """``(message, is error)`` for the Derived panel: each gear's own, prefixed A: and B: in a pair."""
    out = []
    for tag, diagnostics in sides:
        prefix = f"{tag}: " if len(sides) > 1 else ""
        out += [(prefix + x.message, x.is_error) for x in diagnostics]
    return list(dict.fromkeys(out))


def pair_board(title_kind, pair, chosen=None, focus=("a", "module"), card=None, note="", status=""):
    """A whole strip in pair mode, from a PairSpec as the window would hold it."""
    spec_a, d_a, o_a, diag_a = worked(pair.gear_a)
    spec_b, d_b, o_b, diag_b = worked(pair.gear_b)
    stem_a, stem_b, stem_pair = pair_stems(pair)
    candidates = pairs.solve_spec(pair)
    summary = ui_text.solve_summary(candidates, chosen)
    bevel = spec_a.kind == "bevel"
    ring = pair.mesh_value() == "internal" and not bevel
    crossed = spec_a.kind in ("helical", "herringbone") and not ring and pair.shafts_value() == "crossed"
    alpha = getattr(d_a, "normal_pressure_angle_deg", d_a.pressure_angle_deg)
    if bevel:
        row_ = pairs.bevel_candidate(d_a.module, d_a.teeth, d_b.teeth, d_a.shaft_angle, alpha)
        centre, ratio, eps, symbol = row_.centre_distance, row_.ratio, row_.contact_ratio, "R"
    elif crossed:
        centre, ratio, eps = pairs.describe_crossed(d_a.module, d_a.teeth, d_b.teeth, d_a.helix_angle_deg,
                                                   d_b.helix_angle_deg, alpha)
        symbol = "C"
    else:
        centre, ratio, eps = pairs.describe(d_a.module, d_a.teeth, d_b.teeth, alpha, getattr(d_a, "helix_angle_deg", 0.0),
                                            mesh="internal" if ring else "external",
                                            shift_1=getattr(d_a, "shift", 0.0), shift_2=getattr(d_b, "shift", 0.0))
        symbol = "C"
    working = None
    if not bevel and not crossed and not ring and (getattr(d_a, "shift", 0.0) or getattr(d_b, "shift", 0.0)):
        working = pairs.working_pressure_angle(d_a.module, d_a.teeth, d_b.teeth, d_a.pressure_angle_deg,
                                               d_a.shift, d_b.shift, d_a.d / d_a.teeth)
    rows = ui_text.pair_derived_rows(centre, ratio, eps, d_a.teeth, d_b.teeth,
                                     "Cone distance" if bevel else "Centre distance", working_angle=working)
    diagnostics = diagnostics_of([("A", diag_a), ("B", diag_b)])
    if not bevel and not crossed and not ring:
        diagnostics += [(message, "cannot be built" in message) for message in pairs.mesh_warnings(d_a, d_b)]
    panel_card = {"a": card if focus[0] == "a" else None, "b": card if focus[0] == "b" else None,
                  "pair": card if focus[0] == "pair" else None}
    readout = ui_text.pair_readout(pair.cone_distance if bevel else pair.centre_distance, pair.ratio, chosen,
                                   "R" if bevel else "C")
    manual = ui_text.manual_steps_line([f"Assign a material to {stem_a}; the build leaves it unset.",
                                        f"Assign a material to {stem_b}; the build leaves it unset."])
    return page("\n".join([
        gear_kind_panel(title_kind, "Gear pair"),
        pair_panel(pair, summary, readout, focused=focus[1] if focus[0] == "pair" else "", card=panel_card["pair"], d=d_a),
        side_panel("Gear A", spec_a, d_a, stem_a, focused=focus[1] if focus[0] == "a" else "", card=panel_card["a"],
                   pair=pair, side="a"),
        side_panel("Gear B", spec_b, d_b, stem_b, focused=focus[1] if focus[0] == "b" else "", card=panel_card["b"],
                   pair=pair, side="b"),
        derived_panel([(d_a, o_a), (d_b, o_b)], ("A", "B"), diagnostics,
                      ui_text.pair_derived_readout(centre, ratio, eps, symbol), pair_rows=rows, note=note),
        output_panel(True),
        sw_bar(ui_text.mode_note("pair", [stem_a, stem_b, stem_pair]), manual),
        footer(status or "Both gears now carry the chosen module and teeth."),
    ]))


def single_board(spec, focus="module", status="Type a gear, or switch to Gear pair to solve one."):
    spec, d, o, diagnostics = worked(spec)
    stem = spec.default_stem()
    return page("\n".join([
        gear_kind_panel(spec.kind, "Single gear"),
        side_panel("Gear", spec, d, stem, focused=focus, card=focus),
        derived_panel([(d, o)], ("",), diagnostics_of([("", diagnostics)]), ui_text.derived_line(d)),
        output_panel(False),
        sw_bar(ui_text.mode_note("single", [stem]),
               ui_text.manual_steps_line([f"Assign a material to {stem}; the build leaves it unset."])),
        footer(status),
    ]))


def chosen_row(pair, test):
    """The first candidate Solve lists that passes ``test``, and the pair with it applied."""
    candidates = pairs.solve_spec(pair)
    row_ = next(c for c in candidates if test(c))
    a, b = pairs.apply(row_, pair.gear_a, pair.gear_b)
    values = pair.to_dict()
    values.update(gear_a=a, gear_b=b)
    return row_, PairSpec(**values)


# -------------------------------------------------------------------- the Workbook window (W2–W4)
#
# Drawn from a real workbook: written by the app's writer, read by its link,
# worked through by workbook.assess with any chosen fixes made, and — for the
# boards after a build — planned by workbook.gearbox, built and updated by
# swbuild's own worker functions against the fake SolidWorks the test suite
# runs them on, and finished into a real link record by gearbox.finish_build
# and update.finish_update. The footer is ui_text.workbook_footer whole, the
# Gears table workbook_gear_rows, the header's tag workbook_built_tag, every
# other line ui_text's, the end view preview.layout_gearbox's; the sizes,
# colours and flows are workbook_gui's own, so the boards say what the window
# would for the same file. Nothing is saved anywhere real: the board's "disk"
# is a set of paths, as the gearbox tests' is.

import copy as copying, dataclasses, hashlib, shutil, tempfile
from gear_generator import __version__, store, swbuild, workbook_gui as wb_gui
from gear_generator.workbook import assess as wb_assess, gearbox as wb_gearbox, link as wb_link, \
    model as wb_model, update as wb_update, xlsx as wb_xlsx
sys.path.insert(0, os.path.join(HERE, "..", "..", "tests"))
from test_swbuild import FakeSolidWorks          # the fake SolidWorks swbuild's own tests run against

WINDOW_WIDTH = wb_gui.WINDOW_WIDTH
MONO_TINY = f"font-family: {MONO}; font-size: 11.5px; color: {INK}; line-height: 20px; white-space: nowrap;"
STAMP = "2026-11-13T14:02:31Z"
_reads = {}


def read_workbook(spec, copy=False):
    """``spec`` through a real file, written once and read by the window's own link: (path, spec, diagnostics,
    digest). The same spec is the same file, so a record's digest matches a later board's read of it; ``copy``
    reads the same file copied to a folder of its own (a copied workbook)."""
    key = (repr(spec), copy)
    if key not in _reads:
        folder = tempfile.mkdtemp(prefix="gen-workbook-")
        path = os.path.join(folder, f"{spec.box.name}.xlsx")
        if copy:
            shutil.copy(read_workbook(spec)[0], path)
        else:
            wb_xlsx.write_new(path, wb_model.to_sheets(spec))
        reading = wb_link.Link(path).read()
        _reads[key] = (path, reading.spec, reading.diagnostics, reading.digest)
    return _reads[key]


def _key(path):
    return path.replace("/", "\\").lower()


class Disk:
    """What SolidWorks saved and the finishes wrote, by path as Windows compares them: the window's existence
    checks and .gear.json reads, answered without a real folder."""

    def __init__(self):
        self.files, self.sidecars = set(), {}

    def add(self, path):
        self.files.add(_key(path))

    def exists(self, path):
        return _key(path) in self.files

    def read_sidecar(self, path):
        return self.sidecars.get(_key(path)) if self.exists(path) else None

    def write(self, finished):                                          # WorkbookWindow._write
        for path, sidecar in finished.sidecars:
            self.add(path)
            self.sidecars[_key(path)] = sidecar


class BoardSolidWorks(FakeSolidWorks):
    """The fake SolidWorks, putting what it saves on the board's disk and keeping each component's frame under
    the Name2 it was inserted as, so Update finds the assembly where the build left it."""

    def __init__(self, disk):
        super().__init__()
        self.disk, self.names = disk, {}

    def save_as(self, path):
        kept = super().save_as(path)
        self.disk.add(path)
        return kept

    def add_component(self, handle, path, at):
        name = super().add_component(handle, path, at)
        self.names[handle] = name
        return name

    def place_component(self, handle, rotation, at):
        super().place_component(handle, rotation, at)
        if handle in self.names:
            self.frames[self.names[handle]] = (tuple(rotation), tuple(at))


class Desk:
    """One session of the window on one folder: the fake SolidWorks, its disk, and the record beside the
    workbook as the last finish left it."""

    def __init__(self):
        self.disk = Disk()
        self.sw = BoardSolidWorks(self.disk)
        self.record = None


def assessed(spec, diagnostics, chosen=()):                            # WorkbookWindow._assess
    return wb_assess.assess(spec, diagnostics, spec.box.output_folder, "", chosen)


def planned(a, record, disk):                                           # WorkbookWindow._plan_solidworks
    """(what the build button would run, what Update SolidWorks would do, the record when it is this workbook's),
    as the window plans them: a copied workbook's record is the other workbook's, so it is not shown and Update
    is not asked (plan_gearbox is given it and tells the copy itself). The record is not passed through
    store.clear_saved: on the board's disk nothing is saved after Update, as in the window until the user saves
    in SolidWorks."""
    here = str(a.read.source_path or a.spec.source_path or "")
    if (record is not None and store.record_owner(record, here, disk.exists)[0] == store.UNSURE
            and any(store.same_path(record.workbook, read[0]) for read in _reads.values())):
        # Each spec the boards read is written to a file of its own, but in the window they are one workbook saved
        # again: its record is its own (a record whose workbook is gone is otherwise asked about: WorkbookMoved).
        record = copying.deepcopy(record)
        store.adopt(record, here)
    ours = None if store.foreign_workbook(record, here, disk.exists) else record
    gearbox = ours.gearbox if ours is not None else None
    has_assembly = gearbox is not None and bool(gearbox.assembly)
    parts_only = not has_assembly and bool(a.parts.refused)
    gate = a.build_refusal() if parts_only else a.lay_out_refusal()
    plan = None if gate else wb_gearbox.plan_gearbox(a, record, parts_only=parts_only, exists=disk.exists,
                                                     read_sidecar=disk.read_sidecar)
    update = None
    if ours is not None and (ours.parts or gearbox is not None) and not wb_gui._update_gate(a, ours):
        update = wb_update.classify(ours, a, exists=disk.exists)
    return plan, update, ours


def press_build(desk, spec):
    """Build pressed on ``spec``: the plan run by swbuild.build_gearbox, finished into the record; the note."""
    path, read_spec, diagnostics, digest = read_workbook(spec)
    plan, _, _ = planned(assessed(read_spec, diagnostics), desk.record, desk.disk)
    result = swbuild.build_gearbox(desk.sw, **plan.build_kwargs(), exists=desk.disk.exists)
    again = desk.record is not None and desk.record.gearbox is not None and bool(desk.record.gearbox.assembly)
    text, ok = ui_text.gearbox_status(plan, result, again=again)
    finished = wb_gearbox.finish_build(plan, result, desk.record, workbook=path, digest=digest,
                                       written_by=f"gear-generator {__version__}", read_sidecar=desk.disk.read_sidecar,
                                       stamp=STAMP)
    desk.disk.write(finished)
    desk.record = finished.record or desk.record
    return ui_text.Note(" ".join([text] + finished.notes), ok)


def press_update(desk, spec):
    """Update SolidWorks pressed on ``spec``: swbuild.update_gearbox, finished into the record; the note."""
    path, read_spec, diagnostics, digest = read_workbook(spec)
    _, update, _ = planned(assessed(read_spec, diagnostics), desk.record, desk.disk)
    result = swbuild.update_gearbox(desk.sw, **update.update_kwargs(), exists=desk.disk.exists)
    meshes = desk.record.gearbox.meshes
    finished = wb_update.finish_update(update, result, desk.record, digest=digest,
                                       read_sidecar=desk.disk.read_sidecar, mtime=lambda _path: 0.0, stamp=STAMP)
    desk.disk.write(finished)
    desk.record = finished.record or desk.record
    text, ok = ui_text.gearbox_update_status(update, result, finished.dragged, meshes=meshes)
    return ui_text.Note(" ".join([text] + finished.notes), ok)


def gears_table(rows):
    # Tk's minsize is a floor, not a width: a column grows to what it holds (built · changes on Update), and the
    # one with no minsize takes what is left.
    widths = " ".join("minmax(0, 1fr)" if w == 0 else f"minmax({w}px, max-content)" for w in wb_gui.TABLE_WIDTHS)
    cells = [f'<span style="font-size: 11px; color: {READOUT}; line-height: 18px;">{h}</span>' for h in wb_gui.TABLE_HEAD]
    for gear, shaft, kind, teeth, module, face, part, state, what in rows:
        cells += [f'<span style="{MONO_TINY}">{v}</span>' for v in (gear, shaft)]
        cells.append(f'<span style="font-size: 12px; color: {LABEL}; line-height: 20px;">{kind}</span>')
        cells += [f'<span style="{MONO_TINY}">{v}</span>' for v in (teeth, module, face)]
        cells.append(f'<span style="{MONO_TINY} overflow: hidden; text-overflow: ellipsis;">{part or "—"}</span>')
        cells.append(f'<span style="display: inline-flex; align-items: center; gap: 6px; font-size: 12px; '
                     f'color: {ERR if state in wb_gui.RED_STATES else MUTED}; line-height: 20px; white-space: nowrap;">'
                     f'{dot(wb_gui.STATE_COLOURS[state])}{what}</span>')
    return (f'<div style="display: grid; grid-template-columns: {widths}; column-gap: 10px; align-items: center;">'
            + "".join(cells) + '</div>')


def check_lines(diagnostics, offered, chosen):
    """The Checks panel as _paint draws it: chosen fixes with Undo, errors first, each error's fix buttons."""
    out = [row(f'<span style="font-size: 12px; color: {INK};">Chosen, not yet written: {fix.title}</span>',
               button("Undo", h=20)) for fix in chosen]
    ordered = [d for d in diagnostics if d.is_error] + [d for d in diagnostics if not d.is_error]
    for d in ordered:
        out.append(warning(d.message, d.is_error))
        for fix in offered.get(d.field, []) if d.is_error else []:
            out.append(f'<div style="display: flex; flex-direction: column; gap: 2px; padding: 2px 0 2px 14px;">'
                       f'<div style="display: flex;">{button(fix.title, h=22)}</div>'
                       f'<span style="font-family: {MONO}; font-size: 11px; color: {MUTED};">{fix.detail}</span></div>')
    if not ordered and not chosen:
        out.append(warning("No problems: every row reads, and every gear works out."))
    return out


def end_view_svg(report):
    w, h = wb_gui.END_VIEW
    if not report.layout.placed:
        reason = report.layout.later[0] if report.layout.later else "Nothing to draw yet."
        return (f'<div style="width: {w}px; height: {h}px; background: #ffffff; font-size: 12px; color: {MUTED}; '
                f'padding: 12px; box-sizing: border-box;">{reason}</div>'), ""
    view = layout_of.layout_gearbox(report.layout.placed, report.theta, w, h, step=2)
    body = []
    for _, plane, points in view.outlines:
        colour = wb_gui.PLANE_COLOURS[plane % len(wb_gui.PLANE_COLOURS)]
        body.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in points)}" fill="none" '
                    f'stroke="{colour}" stroke-width="1"></polygon>')
    for _, plane, x, y, r in view.rims:
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="none" '
                    f'stroke="{wb_gui.PLANE_COLOURS[plane % len(wb_gui.PLANE_COLOURS)]}"></circle>')
    for name, x, y in view.shafts:
        body.append(f'<path d="M{x - 5:.1f} {y:.1f}H{x + 5:.1f}M{x:.1f} {y - 5:.1f}V{y + 5:.1f}" stroke="{INK}"></path>')
    for name, x, y, anchor in view.labels:        # the window's Tk anchors: n/s the top or bottom, w/e the start or end
        baseline = y + 10 if anchor[0] == "n" else y - 3
        body.append(f'<text x="{x:.1f}" y="{baseline:.1f}" text-anchor="{"start" if anchor[1] == "w" else "end"}" '
                    f'font-family="{MONO}" font-size="11" fill="{INK}">{name}</text>')
    if view.origin is not None:
        ox, oy = view.origin
        reach, head = layout_of.ORIGIN_ARROW, layout_of.ARROW_HEAD
        body.append(f'<path d="M{ox:.1f} {oy:.1f}h{reach}m-5 -{head}l5 {head}l-5 {head}" fill="none" stroke="{ERR}"></path>'
                    f'<path d="M{ox:.1f} {oy:.1f}v-{reach}m-{head} 5l{head} -5l{head} 5" fill="none" stroke="{OK}"></path>'
                    f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="2.5" fill="{INK}"></circle>')
    svg = (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="display: block; background: #ffffff;">'
           + "".join(body) + '</svg>')
    return svg, ui_text.end_view_readout(view)


def foot_button(text, primary=False, enabled=True):
    """A 32 px footer button as widgets.Button paints it: a primary one bold with 18 px either side, greyed
    (#b5b5b5, white text) when disabled; a secondary one #f8f8f8, or #f4f4f4 with faint text when disabled."""
    if primary:
        fill = ACCENT if enabled else "#b5b5b5"
        style = f"background: {fill}; color: #ffffff; border: 1px solid {fill}; font-weight: 600; padding: 0 18px;"
    elif enabled:
        style = f"background: #f8f8f8; color: {INK}; border: 1px solid {BORDER}; font-weight: 500; padding: 0 10px;"
    else:
        style = f"background: {DISABLED_BG}; color: {FAINT}; border: 1px solid #e3e3e3; font-weight: 500; padding: 0 10px;"
    return (f'<div style="height: 32px; flex-shrink: 0; box-sizing: border-box; border-radius: 2px; display: flex; '
            f'align-items: center; font-size: 12.5px; {style}">{text}</div>')


def question_dialog(title, text):
    """messagebox.askyesno as Windows draws it over the window: the title bar, the question mark, the question,
    and Yes and No with No the default (workbook_gui.ask_yes_no)."""
    mark = ('<svg width="32" height="32" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#2f6db5"></circle>'
            '<text x="16" y="22.5" text-anchor="middle" font-family="Segoe UI, sans-serif" font-size="19" '
            'font-weight="600" fill="#ffffff">?</text></svg>')
    yes = ('<div style="width: 76px; height: 24px; box-sizing: border-box; border: 1px solid #adadad; background: '
           '#e1e1e1; display: flex; align-items: center; justify-content: center; font-size: 12px;">Yes</div>')
    no = ('<div style="width: 76px; height: 24px; box-sizing: border-box; border: 2px solid #0078d7; background: '
          '#e5f1fb; display: flex; align-items: center; justify-content: center; font-size: 12px;">No</div>')
    return (f'<div style="position: absolute; inset: 0; background: rgba(0, 0, 0, 0.12); display: flex; '
            f'align-items: flex-start; justify-content: center; padding-top: 220px;">'
            f'<div style="width: 520px; background: #ffffff; border: 1px solid #8a8a8a; box-shadow: 0 8px 28px '
            f'rgba(0,0,0,0.28); font-family: Segoe UI, {SANS}; color: #000000;">'
            f'<div style="height: 30px; display: flex; align-items: center; justify-content: space-between; '
            f'padding: 0 0 0 10px; font-size: 12px;"><span>{title}</span><span style="width: 44px; text-align: center; '
            f'font-size: 14px; color: #333;">✕</span></div>'
            f'<div style="display: flex; gap: 14px; padding: 18px 22px 24px 22px; font-size: 12px; line-height: 1.45;">'
            f'<div style="flex-shrink: 0;">{mark}</div><div>{text}</div></div>'
            f'<div style="background: #f0f0f0; padding: 11px 12px; display: flex; justify-content: flex-end; gap: 10px;">'
            f'{yes}{no}</div></div></div>')


def workbook_board(spec, *, clock="14:02:31", open_in_excel=True, before=None, choose=None, desk=None, note=None,
                   ask=False, copy=False, where="", dialog=None, building=None):
    """The window after reading ``spec`` (changes listed against ``before``); ``choose`` picks offered fixes
    (``(field, index)``) as if their buttons were pressed; ``desk`` is what has been built before (its record and
    disk), and ``note`` the last job's sentence; ``ask`` draws the Build again? question the build button asks,
    and ``dialog`` any other ``(title, question)``; ``copy`` reads a copy of the workbook in a folder of its own,
    shown at ``C:\\<where>`` (``Copy`` unless given); ``building`` is a job's last ``swbuild.Step``, with the window
    closed once (WorkbookWindow.close: it stays, and says it closes once the job is on record)."""
    path, read_spec, read_diagnostics, digest = read_workbook(spec, copy)
    folder = read_spec.box.output_folder
    desk = desk or Desk()

    def plan(chosen, read=(read_spec, read_diagnostics)):              # WorkbookWindow._plan and _assess
        state = assessed(read[0], read[1], chosen)
        return state, state.spec, state.parts, state.report, state.diagnostics

    chosen = []
    raw, effective, parts, report, diagnostics = plan(chosen)
    changes, did = [], None
    if before is not None:                                              # WorkbookWindow._show
        _, earlier_spec, earlier_diagnostics, _ = read_workbook(before)
        changes = wb_link.describe_changes(earlier_spec, read_spec)
        did = wb_link.consequence(plan([], (earlier_spec, earlier_diagnostics))[0], raw)
    state = raw
    for field_, index in choose or ():
        chosen.append(report.fixes[field_][index])
        state, effective, parts, report, diagnostics = plan(chosen)
    covered = wb_link.covered_by_fix(did, report) if chosen else []
    build_plan, update, record = planned(state, desk.record, desk.disk)
    footer = ui_text.workbook_footer(state, record=record, plan=build_plan, update=update, folder=folder,
                                     folder_exists=True, note=note, building=building is not None, progress=building)
    if building is not None:                                            # WorkbookWindow._refresh_state, closing
        footer = dataclasses.replace(footer, text=f"{footer.text} {ui_text.closes_when_done()}")
    name = os.path.basename(path)

    header = (f'<div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">'
              f'<div style="display: flex; flex-direction: column; gap: 2px; min-width: 0;">'
              f'<span style="font-size: 15px; font-weight: 600; color: {INK};">{name}</span>'
              f'<span style="display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: {READOUT};">'
              f'{dot(OK)}linked · {ui_text.workbook_read_line(clock, open_in_excel)}'
              f'{ui_text.workbook_built_tag(record, digest)}</span></div>'
              f'<div style="display: flex; gap: 8px; flex-shrink: 0;">{button("Open in Excel")}{button("Re-read")}</div></div>')
    mono = f'font-family: {MONO}; font-size: 11.5px; color: {INK};'
    file_text = ui_text.short_path(f"C:\\{where or ('Copy' if copy else 'Parts')}\\{name}", wb_gui.PATH_CHARS)
    box = panel("Workbook", ui_text.workbook_counts(effective), [
        row(label("File"), f'<span style="{mono}">{file_text}</span>'),
        row(label("Name"), f'<span style="{mono}">{effective.box.name}</span>'),
        row(label("Output folder"), f'<span style="{mono}">{ui_text.short_path(folder, wb_gui.PATH_CHARS - 20)}</span>',
            hint("from the Box sheet")),
        row(label("Worked out as"), f'<span style="font-size: 12.5px; color: {INK};">{report.worked_out_as or "—"}</span>'),
    ], gap=2)
    gears = panel("Gears", ui_text.workbook_parts_readout(parts, record=record),
                  [gears_table(ui_text.workbook_gear_rows(effective, parts, diagnostics, record=record, update=update,
                                                          plan=build_plan))])
    checks = panel("Checks", ui_text.workbook_checks_readout(diagnostics),
                   check_lines(diagnostics, report.fixes, chosen), gap=4)
    since = panel("Since the last read", ui_text.workbook_changes_readout(changes, clock),
                  [f'<div style="{mono} line-height: 1.5;">{c}</div>' for c in ui_text.workbook_change_lines(changes, did, covered)]
                  or [warning("Nothing changed.")],
                  gap=2)
    svg, view_readout = end_view_svg(report)
    view = panel("End view, from your origin", view_readout, [svg])
    lines, speeds_readout = ui_text.workbook_speed_lines(effective, report.motion)
    speeds = panel("Speeds", speeds_readout,
                   [f'<div style="{mono} white-space: pre; line-height: 1.5;">{line}</div>' for line in lines], gap=0)

    colour = OK if footer.ok else ERR
    exporting = building is None                                        # Export waits while a job runs
    buttons = [foot_button("Export", enabled=exporting), foot_button("Export as…", enabled=exporting),
               foot_button(footer.build_label, footer.build_primary, footer.build_enabled)]
    if footer.update_shown:
        buttons.append(foot_button("Update SolidWorks", footer.update_primary, footer.update_enabled))
    # The sentence wraps as WorkbookWindow._wrap_status wraps it: in the room the dot (8 px and 8 px after it) and
    # the buttons (12 px before Export, 8 px before each of the others) leave in the window's width less its body
    # padding, 2 px short of that, and never narrower than STATUS_MIN_WRAP. So the window keeps its width with all
    # four buttons, and a board whose buttons leave too little room is pushed wider, as the window would be.
    foot = (f'<div style="display: flex; align-items: center; gap: 12px;">'
            f'<div style="flex: 1 1 0; display: flex; align-items: flex-start; gap: 8px; font-size: 12.5px; color: {colour}; '
            f'min-width: {8 + 8 + wb_gui.STATUS_MIN_WRAP + 2}px; box-sizing: border-box; padding-right: 2px;">'
            f'<span style="padding-top: 5px; display: flex;">{dot(colour, 8)}</span><span style="line-height: 1.35;">{footer.text}</span></div>'
            f'<div style="display: flex; gap: 8px; flex-shrink: 0;">{"".join(buttons)}</div></div>')
    left = (f'<div style="width: {wb_gui.LEFT_WIDTH}px; flex-grow: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px;">'
            + "".join([box, gears, checks, since]) + '</div>')
    right = (f'<div style="flex-shrink: 0; display: flex; flex-direction: column; gap: 8px;">' + view + speeds + '</div>')
    body = (header + f'<div style="display: flex; gap: 8px; align-items: flex-start;">{left}{right}</div>' + foot)
    window = column(body, width=WINDOW_WIDTH, pad=wb_gui.BODY_PAD)
    if ask:
        dialog = (ui_text.BUILD_AGAIN_TITLE, ui_text.build_again_question(update, build_plan))
    if dialog is not None:
        window = (f'<div style="position: relative; width: {WINDOW_WIDTH}px;">{window}'
                  + question_dialog(*dialog) + '</div>')
    return HEAD + window + "\n" + TAIL


# -------------------------------------------------------------------- the boards

boards = {}

# The pair the docs use throughout: C 60, i 3 → m 1.5, 20 : 60.
base = PairSpec(mode="pair", centre_distance="60", ratio="3", gear_a=GearSpec(teeth="20"), gear_b=GearSpec(teeth="60"))
chosen, spur_pair = chosen_row(base, lambda c: (c.module, c.teeth_driver, c.teeth_driven) == (1.5, 20, 60))
boards["Main"] = ("Gear pair · spur", pair_board("spur", spur_pair, chosen, ("a", "module"), "module",
                                                  status="Both gears now carry module 1.5: 20 and 60 teeth."))

boards["SingleGear"] = ("Single gear · spur", single_board(GearSpec(), "pressure_angle"))

# A pair that needs profile shift: C 47.5 at 32 : 15 on module 2.
shift_base = PairSpec(mode="pair", centre_distance="47.5", ratio="32:15", module="2",
                      gear_a=GearSpec(module="2", teeth="15"), gear_b=GearSpec(module="2", teeth="32"))
chosen, shifted = chosen_row(shift_base, lambda c: c.shifted)
boards["ShiftedPair"] = ("Gear pair · profile shift", pair_board("spur", shifted, chosen, ("a", "profile_shift"),
                                                                  "profile_shift"))

# A helical pair, helix angle solved: C 60 at 2, gear B's hand following A's.
helical = dict(kind="helical", face_width="20")
helix_base = PairSpec(mode="pair", centre_distance="60", ratio="2", gear_a=GearSpec(teeth="20", helix_angle="15", **helical),
                      gear_b=GearSpec(teeth="40", helix_angle="15", hand="left", **helical))
chosen, helical_pair = chosen_row(helix_base, lambda c: c.exact and not c.undercut and not c.shifted)
boards["HelicalPair"] = ("Gear pair · helical", pair_board("helical", helical_pair, chosen, ("b", "hand"), "hand"))

boards["Herringbone"] = ("Single gear · herringbone, grooved", single_board(
    GearSpec(kind="herringbone", module="2", teeth="20", helix_angle="30", face_width="40", groove="8"), "groove"))

# A pinion inside a ring: C 40 at 3.
ring_base = PairSpec(mode="pair", centre_distance="40", ratio="3", mesh="internal",
                     gear_a=GearSpec(module="2", teeth="20"), gear_b=GearSpec(module="2", teeth="60", teeth_side="internal"))
chosen, ring_pair = chosen_row(ring_base, lambda c: c.exact and not c.clashes)
boards["RingPair"] = ("Gear pair · internal", pair_board("spur", ring_pair, chosen, ("pair", "mesh"), "mesh"))

# Crossed, opposite hands, on shafts 30° apart at C 70: the helix angles differ by the shaft angle.
crossed_base = PairSpec(mode="pair", centre_distance="70", ratio="2",
                        module="2", shafts="crossed", shaft_angle="30", hands="opposite",
                        gear_a=GearSpec(teeth="20", module="2", helix_angle="45", **helical),
                        gear_b=GearSpec(teeth="40", module="2", helix_angle="15", hand="left", **helical))
chosen, crossed_pair = chosen_row(crossed_base, lambda c: c.exact)
boards["CrossedPair"] = ("Gear pair · crossed, opposite hands",
                         pair_board("helical", crossed_pair, chosen, ("pair", "hands"), "hands", note="Σ 30°"))

# Straight bevel: R 50 at 4 : 3 on module 2, shafts at 90° — 30 : 40 meets it exactly.
bevel = dict(kind="bevel", module="2", face_width="14")
bevel_base = PairSpec(mode="pair", cone_distance="50", ratio="4:3", module="2", shaft_angle="90",
                      gear_a=GearSpec(teeth="30", mate_teeth="40", **bevel), gear_b=GearSpec(teeth="40", mate_teeth="30", **bevel))
chosen, bevel_pair = chosen_row(bevel_base, lambda c: c.exact)
boards["BevelPair"] = ("Gear pair · bevel", pair_board("bevel", bevel_pair, chosen, ("pair", "cone_distance"),
                                                       "cone_distance"))

# Every card, each worked out for a gear that has the field.
examples = {
    "": worked(GearSpec(teeth="20")),
    "profile_shift": worked(GearSpec(module="2", teeth="15", profile_shift="0.12")),
    "helix_angle": worked(GearSpec(teeth="20", helix_angle="15", **helical)),
    "hand": worked(GearSpec(teeth="20", helix_angle="15", **helical)),
    "groove": worked(GearSpec(kind="herringbone", module="2", teeth="20", helix_angle="30", face_width="40", groove="8")),
    "teeth_side": worked(GearSpec(module="2", teeth="60", teeth_side="internal")),
    "rim": worked(GearSpec(module="2", teeth="60", teeth_side="internal")),
    "shaft_angle": worked(GearSpec(teeth="30", mate_teeth="40", **bevel)),
    "mate_teeth": worked(GearSpec(teeth="30", mate_teeth="40", **bevel)),
}
pair_examples = {"cone_distance": bevel_pair, "pair_shaft_angle": crossed_pair, "mesh": ring_pair,
                 "shafts": crossed_pair, "hands": crossed_pair}
cards = [section_caption("Gear A · Gear B — one card, shown for the field with the caret")]
for key in ui_text.GEAR_EXPLAINERS:
    spec, d, _, _ = examples.get(key, examples[""])
    cards.append(explainer(key, d, spec.default_stem()))
cards.append(section_caption("Pair — the same card under the solver's fields"))
for key in ui_text.PAIR_EXPLAINERS:
    pair = pair_examples.get(key, spur_pair)
    cards.append(explainer(key, worked(pair.gear_a)[1], "", pair))
cards.append(caption("Each card is worked out for a gear that has the field: the spur pair of the main artboard "
                     "(m 1.5, 20 : 60 at C 60) unless it belongs to a shifted, helical, grooved, ring, bevel or crossed one."))
boards["FieldGuide"] = ("Field explainers · every card", page("\n".join(cards)))

# The Workbook window: the 12 : 1 reducer after a save that made G4 wider, after one that broke a cell, and
# after one that moved S2 off its centres, with the two fixes offered and then the move chosen. Then W4: built;
# PLAN-WORKBOOK §6's demonstration edit, before and after Update SolidWorks; and a change Update cannot carry.
reducer = wb_model.GearboxSpec(
    box=wb_model.Box(name="Reducer_12to1", output_folder="C:\\Parts\\Reducer_12to1", efficiency="98"),
    shafts=(wb_model.Shaft("S1", "frame", "0", "0", "0", "Z+", "input", "", "1500", "10"),
            wb_model.Shaft("S2", "frame", "63.75", "0", "0", "Z+"),
            wb_model.Shaft("S3", "frame", "131.75", "0", "0", "Z+", "output")),
    gears=(wb_model.Gear("G1", "S1", "7.5", "spur", "external", "17", "1.5", "", "15", "8"),
           wb_model.Gear("G2", "S2", "7.5", "spur", "external", "68", "1.5", "", "15", "12"),
           wb_model.Gear("G3", "S2", "27", "spur", "external", "17", "2", "", "20", "12"),
           wb_model.Gear("G4", "S3", "27", "spur", "external", "51", "2", "", "20", "16", part_name="OutputGear")),
    meshes=(wb_model.Mesh("G1", "G2"), wb_model.Mesh("G3", "G4")))
wider = wb_model.replace(reducer, gears=reducer.gears[:3] + (wb_model.replace(reducer.gears[3], face_width="22"),))
boards["WorkbookReady"] = ("Workbook · linked, after a save", workbook_board(wider, before=reducer), WINDOW_WIDTH)
broken = wb_model.replace(reducer, gears=(
    reducer.gears[0], wb_model.replace(reducer.gears[1], teeth="68.5"), reducer.gears[2], reducer.gears[3],
    wb_model.Gear("G5", "S3", "47", "spur", "external", "17", "1.5", "", "15", "8"),
    wb_model.Gear("G6", "S2", "60", "bevel", "external", "20", "3", "", "14", "10")))
boards["WorkbookError"] = ("Workbook · a save with an error", workbook_board(broken, before=reducer), WINDOW_WIDTH)
off = wb_model.replace(reducer, shafts=(reducer.shafts[0], wb_model.replace(reducer.shafts[1], x="64"),
                                        wb_model.replace(reducer.shafts[2], x="132")))
boards["WorkbookFix"] = ("Workbook · a mesh off its centres, two fixes offered", workbook_board(off, before=reducer),
                         WINDOW_WIDTH)
boards["WorkbookChosen"] = ("Workbook · the move chosen, waiting for Export",
                            workbook_board(off, before=reducer, choose=[("Meshes!A2", 0)]), WINDOW_WIDTH)

# W4. Build pressed on the reducer; then PLAN-WORKBOOK §6's demonstration edit — S2 X 63.75 → 64.5 and G2's teeth
# 68 → 69, S3 X following to 132.5 as its formula does in the fixture — before and after Update SolidWorks; then,
# on the reducer as built, G1's flank changed to arcs, which needs a new part, and the build button's question.
built_desk = Desk()
built_note = press_build(built_desk, reducer)
boards["WorkbookBuilt"] = ("Workbook · built: the parts, the layout part and the assembly",
                           workbook_board(reducer, desk=built_desk, note=built_note), WINDOW_WIDTH)
edited = wb_model.replace(reducer, shafts=(reducer.shafts[0], wb_model.replace(reducer.shafts[1], x="64.5"),
                                           wb_model.replace(reducer.shafts[2], x="132.5")),
                          gears=(reducer.gears[0], wb_model.replace(reducer.gears[1], teeth="69")) + reducer.gears[2:])
boards["WorkbookUpdate"] = ("Workbook · an edit Update SolidWorks carries",
                            workbook_board(edited, before=reducer, desk=built_desk), WINDOW_WIDTH)
updated_desk = Desk()
press_build(updated_desk, reducer)
updated_note = press_update(updated_desk, edited)
boards["WorkbookUpdated"] = ("Workbook · after Update SolidWorks, not yet saved",
                             workbook_board(edited, before=reducer, desk=updated_desk, note=updated_note), WINDOW_WIDTH)
arcs = wb_model.replace(reducer, gears=(wb_model.replace(reducer.gears[0], flank="arcs"),) + reducer.gears[1:])
boards["WorkbookAgain"] = ("Workbook · a change that needs a new part, and Build again?",
                           workbook_board(arcs, before=reducer, desk=built_desk, ask=True), WINDOW_WIDTH)
# The W4 review's rework of the footer, in the two states it found worst or new. After Update, not yet saved,
# G1's bore cleared (the demonstration's structural step, its window log's state 06): the save asked once — as
# what may no longer be possible, since the second review — both buttons on, and G2's part made new by the new
# revision while Gear_m1.5_N68's changes are not saved. And the reducer's folder copied whole, workbook and
# record: the record is the original's, so Build makes the copy's own gearbox, each part under the name it will
# have (the Gears table shows plan.part_of since the second review).
bored = wb_model.replace(edited, gears=(wb_model.replace(edited.gears[0], bore=""),) + edited.gears[1:])
boards["WorkbookUnsaved"] = ("Workbook · after Update, not yet saved, a change that needs a new part",
                             workbook_board(bored, before=edited, desk=updated_desk), WINDOW_WIDTH)
copy_desk = Desk()
copy_desk.disk = copying.deepcopy(built_desk.disk)
original = "C:\\Parts\\Reducer_12to1.xlsx"         # where the boards' header says the reducer is
copy_desk.disk.add(original)
for key, sidecar in list(copy_desk.disk.sidecars.items()):
    copy_desk.disk.sidecars[key] = dataclasses.replace(sidecar, record=dataclasses.replace(sidecar.record,
                                                                                         workbook=original))
copy_desk.record = dataclasses.replace(copying.deepcopy(built_desk.record), workbook=original)
boards["WorkbookCopy"] = ("Workbook · a copied workbook, the original still there",
                          workbook_board(reducer, desk=copy_desk, copy=True), WINDOW_WIDTH)
# The second review's two questions over the window. The reducer's folder moved by hand, the original's path gone:
# whose the record is is not taken for granted, and the window asks once (N1c), Build planning a gearbox of its
# own until the answer. And the window closed a second time while SolidWorks does not answer its build (N4.3).
moved_desk = Desk()
moved_desk.disk = copying.deepcopy(copy_desk.disk)
moved_desk.disk.files.discard(_key(original))                          # the original is not there any more
moved_desk.record = copying.deepcopy(copy_desk.record)
boards["WorkbookMoved"] = ("Workbook · its record's workbook gone: moved, or a copy?",
                           workbook_board(reducer, desk=moved_desk, copy=True, where="Moved",
                                          dialog=(ui_text.MOVED_TITLE, ui_text.moved_question("", original))),
                           WINDOW_WIDTH)
boards["WorkbookCloseAnyway"] = ("Workbook · closed twice while SolidWorks does not answer",
                                 workbook_board(reducer, building=swbuild.Step(swbuild.STAGE_PART, "Gear_m1.5_N68", 2, 4),
                                                dialog=(ui_text.CLOSE_ANYWAY_TITLE, ui_text.close_anyway_question())),
                                 WINDOW_WIDTH)

layout = []
x = 0
for name, value in boards.items():
    title, html = value[0], value[1]
    width = value[2] if len(value) > 2 else 484
    open(os.path.join(HERE, f"{name}.dc.html"), "w").write(html)
    layout.append({"file": f"{name}.dc.html", "title": title, "x": x, "y": 0, "w": width})
    x += width + 80

canvas = {
    "artboards": layout,
    "annotations": [
        {"id": "note-source", "x": 0, "y": -200, "w": 484,
         "text": "Drawn from the app\nEvery card's words are ui_text.explainer's, every readout and derived row "
                 "ui_text's, and every picture preview.layout's: gen.py only writes the HTML. So an artboard shows "
                 "what the window would, for the same form."},
        {"id": "note-rows", "x": 564, "y": -200, "w": 484,
         "text": "Rows by kind\nProfile shift for external spur and helical gears on parallel shafts; Helix angle and "
                 "Hand for the helical kinds, gear B's hand following gear A's; Groove for a herringbone; Rim for a "
                 "ring; Shaft angle and Mate teeth for a single bevel gear; Hands for a crossed pair; Assembly for a "
                 "pair on parallel shafts."},
    ],
    "launch": {"view": "canvas"},
}
json.dump(canvas, open(os.path.join(HERE, "canvas.json"), "w"), indent=2, ensure_ascii=False)
print(" · ".join(f"{name} {len(value[1])}" for name, value in boards.items()))
