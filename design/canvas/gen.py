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


def column(body, gap=8, width=484):
    """The strip as the app draws it: 460 px of content inside 12 px of window ground."""
    return (f'<div style="width: {width}px; flex-shrink: 0; box-sizing: border-box; background: #f0f0f0; color: {INK}; '
            f'font-family: {SANS}; font-size: 13px; line-height: 1.3; display: flex; flex-direction: column; gap: {gap}px; padding: 12px;">\n' + body + '\n</div>')


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


# -------------------------------------------------------------------- the Workbook window (W3)
#
# Drawn from a real workbook: written by the app's writer, read by its reader,
# planned by workbook.build, checked by workbook.checks with any chosen fixes
# made, the end view laid out by preview.layout_gearbox, and every line of text
# from ui_text — so the board says what the window would for the same file.
# The sizes are the window's own (workbook_gui), so the two cannot drift.

import tempfile
from gear_generator import workbook_gui as wb_gui
from gear_generator.workbook import build as wb_build, checks as wb_checks, fixes as wb_fixes, \
    link as wb_link, model as wb_model, xlsx as wb_xlsx

WINDOW_WIDTH = wb_gui.WINDOW_WIDTH
STATE_COLOURS = {ui_text.GEAR_STATE_BUILDS: OK, ui_text.GEAR_STATE_SHARES: OK,
                 ui_text.GEAR_STATE_LATER: READOUT, ui_text.GEAR_STATE_ERROR: ERR}
MONO_TINY = f"font-family: {MONO}; font-size: 11.5px; color: {INK}; line-height: 20px; white-space: nowrap;"


def read_workbook(spec):
    """``spec`` through a real file: written, then read back, so cells and diagnostics are the app's own."""
    folder = tempfile.mkdtemp(prefix="gen-workbook-")
    path = os.path.join(folder, f"{spec.box.name}.xlsx")
    wb_xlsx.write_new(path, wb_model.to_sheets(spec))
    return path, wb_model.from_book(wb_xlsx.read(path))


def gears_table(rows):
    widths = " ".join("minmax(0, 1fr)" if w == 0 else f"{w}px" for w in wb_gui.TABLE_WIDTHS)
    cells = [f'<span style="font-size: 11px; color: {READOUT}; line-height: 18px;">{h}</span>' for h in wb_gui.TABLE_HEAD]
    for gear, shaft, kind, teeth, module, face, part, state, what in rows:
        cells += [f'<span style="{MONO_TINY}">{v}</span>' for v in (gear, shaft)]
        cells.append(f'<span style="font-size: 12px; color: {LABEL}; line-height: 20px;">{kind}</span>')
        cells += [f'<span style="{MONO_TINY}">{v}</span>' for v in (teeth, module, face)]
        cells.append(f'<span style="{MONO_TINY} overflow: hidden; text-overflow: ellipsis;">{part or "—"}</span>')
        cells.append(f'<span style="display: inline-flex; align-items: center; gap: 6px; font-size: 12px; '
                     f'color: {ERR if state == ui_text.GEAR_STATE_ERROR else MUTED}; line-height: 20px; white-space: nowrap;">'
                     f'{dot(STATE_COLOURS[state])}{what}</span>')
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
        body.append(f'<path d="M{x - 5:.1f} {y:.1f}H{x + 5:.1f}M{x:.1f} {y - 5:.1f}V{y + 5:.1f}" stroke="{INK}"></path>'
                    f'<text x="{x + 6:.1f}" y="{y + 16:.1f}" font-family="{MONO}" font-size="11" fill="{INK}">{name}</text>')
    if view.origin is not None:
        ox, oy = view.origin
        body.append(f'<path d="M{ox:.1f} {oy:.1f}h26m-5 -3l5 3l-5 3" fill="none" stroke="{ERR}"></path>'
                    f'<path d="M{ox:.1f} {oy:.1f}v-26m-3 5l3 -5l3 5" fill="none" stroke="{OK}"></path>'
                    f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="2.5" fill="{INK}"></circle>')
    svg = (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="display: block; background: #ffffff;">'
           + "".join(body) + '</svg>')
    return svg, ui_text.end_view_readout(view)


def workbook_board(spec, *, clock="14:02:31", open_in_excel=True, before=None, choose=None, note=None):
    """The window after reading ``spec`` (changes listed against ``before``); ``choose`` picks offered fixes
    (``(field, index)``) as if their buttons were pressed."""
    path, (read_spec, read_diagnostics) = read_workbook(spec)
    changes = wb_link.describe_changes(read_workbook(before)[1][0], read_spec) if before is not None else []
    folder = read_spec.box.output_folder

    def plan(chosen):                                                   # WorkbookWindow._plan
        effective = read_spec
        for fix in chosen:
            effective = wb_fixes.apply(effective, fix)
        skip_rows = wb_build.rows_with_errors(read_diagnostics)
        parts = wb_build.plan_parts(effective, folder, skip_rows=skip_rows)
        bad_rows = skip_rows | wb_build.rows_with_errors(parts.diagnostics)
        report = wb_checks.check(effective, {g.id for g in effective.gears if g.row in bad_rows})
        return effective, parts, report, read_diagnostics + parts.diagnostics + report.diagnostics

    chosen = []
    effective, parts, report, diagnostics = plan(chosen)
    for field_, index in choose or ():
        chosen.append(report.fixes[field_][index])
        effective, parts, report, diagnostics = plan(chosen)
    name = os.path.basename(path)
    status, ok, enabled = ui_text.workbook_state(parts, diagnostics, folder=folder, chosen=len(chosen), note=note)

    header = (f'<div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">'
              f'<div style="display: flex; flex-direction: column; gap: 2px; min-width: 0;">'
              f'<span style="font-size: 15px; font-weight: 600; color: {INK};">{name}</span>'
              f'<span style="display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: {READOUT};">'
              f'{dot(OK)}linked · {ui_text.workbook_read_line(clock, open_in_excel)}</span></div>'
              f'<div style="display: flex; gap: 8px; flex-shrink: 0;">{button("Open in Excel")}{button("Re-read")}</div></div>')
    mono = f'font-family: {MONO}; font-size: 11.5px; color: {INK};'
    file_text = ui_text.short_path(f"C:\\Parts\\{name}", wb_gui.PATH_CHARS)
    box = panel("Workbook", ui_text.workbook_counts(effective), [
        row(label("File"), f'<span style="{mono}">{file_text}</span>'),
        row(label("Name"), f'<span style="{mono}">{effective.box.name}</span>'),
        row(label("Output folder"), f'<span style="{mono}">{ui_text.short_path(folder, wb_gui.PATH_CHARS - 20)}</span>',
            hint("from the Box sheet")),
        row(label("Worked out as"), f'<span style="font-size: 12.5px; color: {INK};">{report.worked_out_as or "—"}</span>'),
    ], gap=2)
    gears = panel("Gears", ui_text.workbook_parts_readout(parts),
                  [gears_table(ui_text.workbook_gear_rows(effective, parts, diagnostics))])
    checks = panel("Checks", ui_text.workbook_checks_readout(diagnostics),
                   check_lines(diagnostics, report.fixes, chosen), gap=4)
    since = panel("Since the last read", ui_text.workbook_changes_readout(changes, clock),
                  [f'<div style="{mono} line-height: 1.5;">{c}</div>' for c in changes] or [warning("Nothing changed.")],
                  gap=2)
    svg, view_readout = end_view_svg(report)
    view = panel("End view, from your origin", view_readout, [svg])
    lines, speeds_readout = ui_text.workbook_speed_lines(effective, report.motion)
    speeds = panel("Speeds", speeds_readout,
                   [f'<div style="{mono} white-space: pre; line-height: 1.5;">{line}</div>' for line in lines], gap=0)

    colour = OK if ok else ERR
    foot = (f'<div style="display: flex; align-items: center; justify-content: space-between; gap: 12px;">'
            f'<div style="display: flex; align-items: flex-start; gap: 8px; font-size: 12.5px; color: {colour}; '
            f'min-width: 0; max-width: {WINDOW_WIDTH - 420}px;">'
            f'<span style="padding-top: 5px; display: flex;">{dot(colour, 8)}</span><span style="line-height: 1.35;">{status}</span></div>'
            f'<div style="display: flex; gap: 8px; flex-shrink: 0;">{button("Export", h=32)}{button("Export as…", h=32)}'
            f'{button("Build parts", primary=enabled, disabled=not enabled, h=32)}</div></div>')
    left = (f'<div style="width: {wb_gui.LEFT_WIDTH}px; flex-grow: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px;">'
            + "".join([box, gears, checks, since]) + '</div>')
    right = (f'<div style="flex-shrink: 0; display: flex; flex-direction: column; gap: 8px;">' + view + speeds + '</div>')
    body = (header + f'<div style="display: flex; gap: 8px; align-items: flex-start;">{left}{right}</div>' + foot)
    return HEAD + column(body, width=WINDOW_WIDTH) + "\n" + TAIL


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
# after one that moved S2 off its centres, with the two fixes offered and then the move chosen.
reducer = wb_model.GearboxSpec(
    box=wb_model.Box(name="Reducer_12to1", output_folder="C:\\Parts\\Reducer_12to1\\", efficiency="98"),
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
