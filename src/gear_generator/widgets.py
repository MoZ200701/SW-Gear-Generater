"""The controls §5 of the design asks for, drawn by hand.

Every one of these exists because a themed Tk widget would not take the colour,
the border or the height the design gives it. They are small on purpose: a
frame, a label, and where a shape is needed, a canvas. None of them knows
anything about airfoils — they take a variable and a callback, and that is all.

Three of them — :class:`Check`, :class:`Button` and :class:`Segmented` — answer
``configure(state=...)`` the way a ttk widget does, so the handlers in
:mod:`gui` that enable and disable controls read exactly as they did before.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from . import theme
from .theme import px

# ------------------------------------------------------------------- pieces


class Rule(tk.Frame):
    """A one-pixel line across whatever it is put in."""

    def __init__(self, parent: tk.Misc, color: str = theme.RULE, **kwargs) -> None:
        super().__init__(parent, height=max(1, px(1)), bg=color, bd=0,
                         highlightthickness=0, **kwargs)


class Box(tk.Frame):
    """A white, bordered rectangle: a panel body, a card, the tracker."""

    def __init__(self, parent: tk.Misc, bg: str = theme.WHITE,
                 border: str = theme.BORDER_SOFT, **kwargs) -> None:
        super().__init__(
            parent, bg=bg, bd=0, highlightthickness=max(1, px(1)),
            highlightbackground=border, highlightcolor=border, **kwargs
        )


# -------------------------------------------------------------------- icons
#
# Stroke drawings on a 16 px grid, per §5: no emoji, no glyph font, nothing
# that depends on a character being present on the machine.

def _scaled(points: Sequence[Tuple[float, float]], size: int) -> List[float]:
    out: List[float] = []
    for x, y in points:
        out.extend((x * size / 16.0, y * size / 16.0))
    return out


def draw_icon(canvas: tk.Canvas, name: str, color: str, size: int) -> None:
    """Draw one 16-grid icon at the canvas's own size, in ``color``."""
    canvas.delete("icon")
    width = max(1, int(round(1.5 * size / 16.0)))
    common = dict(fill=color, width=width, capstyle="round", joinstyle="round", tags="icon")

    def line(points, smooth=False):
        canvas.create_line(*_scaled(points, size), smooth=smooth, **common)

    def oval(x0, y0, x1, y1, **kw):
        canvas.create_oval(*_scaled(((x0, y0), (x1, y1)), size),
                           outline=color, width=width, tags="icon", **kw)

    if name == "folder":
        line([(2, 12.6), (2, 4.4), (6.4, 4.4), (7.9, 6.3), (13.8, 6.3),
              (13.8, 12.6), (2, 12.6)])
    elif name == "cursor":
        line([(3, 2.4), (12.6, 8), (8.4, 9.1), (6.2, 13.2), (3, 2.4)])
    elif name == "sidebar":
        line([(2.4, 3), (13.6, 3), (13.6, 13), (2.4, 13), (2.4, 3)])
        line([(10, 3), (10, 13)])
    elif name == "info":
        oval(2, 2, 14, 14)
        line([(8, 7.4), (8, 11.2)])
        line([(8, 4.9), (8, 5.1)])
    elif name == "tick":
        line([(3.4, 8.4), (6.5, 11.5), (12.6, 4.6)])
    elif name == "chevron":
        line([(4, 6.2), (8, 10.2), (12, 6.2)])
    elif name == "refresh":
        canvas.create_arc(
            *_scaled(((2.6, 2.6), (13.4, 13.4)), size), start=40, extent=280,
            style="arc", outline=color, width=width, tags="icon",
        )
        line([(12.4, 2.4), (12.9, 6.2), (9.2, 5.4)])
    elif name == "plus":
        line([(8, 3.2), (8, 12.8)])
        line([(3.2, 8), (12.8, 8)])
    elif name == "link":
        # Two half-rings and the bar between them: a chain link, for taking
        # hold of curves the app did not put in the part itself.
        for box, start in ((((2.2, 4.6), (9.0, 11.4)), 90), (((7.0, 4.6), (13.8, 11.4)), 270)):
            canvas.create_arc(*_scaled(box, size), start=start, extent=180,
                              style="arc", outline=color, width=width, tags="icon")
        line([(5.6, 8), (10.4, 8)])


# ------------------------------------------------------- explainer diagrams
#
# The same idea as the icons above, four times the size: stroke drawings on a
# 56 px grid, one per field of the form, drawn straight onto a canvas rather
# than loaded from a file. They are ``design/canvas/gen.py``'s ``DIAGRAMS``
# translated from SVG paths, so a change to one belongs in both places.
#
# Three strokes: the drawing itself in #505050, the one dimension the field is
# about in #2b2b2b and a little thicker, and anything that is only there for
# reference — a pitch line, an axis — dashed in #c6c6c6.

DIAGRAM_SIZE = 56

# Fields whose diagram is another field's.
DIAGRAM_ALIASES = {"pair_module": "series", "teeth_range": "teeth", "assembly_name": "name"}


def _gear_teeth(cx: float, cy: float, r_out: float, r_in: float, teeth: int,
                first: int = 0, span: int = 0) -> List[Tuple[float, float]]:
    """A toothed circle on the 56 grid, or — with ``span`` — one tooth of it.

    Four points a tooth: up at the root, along the tip, and back down. Coarse
    on purpose; at 56 px a real involute and this are the same picture.
    """
    corners = ((0.0, r_in), (0.18, r_out), (0.5, r_out), (0.68, r_in))
    step = 2 * math.pi / teeth
    points = []
    for index in range(first, first + (span or teeth)):
        for fraction, radius in corners:
            angle = index * step + fraction * step
            points.append((cx + radius * math.cos(angle), cy - radius * math.sin(angle)))
    return points


def draw_diagram(canvas: tk.Canvas, name: str, size: int = DIAGRAM_SIZE) -> None:
    """Draw one explainer diagram at the canvas's own size."""
    canvas.delete("diagram")
    key = DIAGRAM_ALIASES.get(name, name)
    k = size / float(DIAGRAM_SIZE)
    mono = theme.fonts().mono_family

    def width_of(design: float) -> int:
        return max(1, int(round(design * k)))

    def line(points, color: str = theme.HEADER_TEXT, w: float = 1.2, dash=None,
             smooth: bool = False, closed: bool = False) -> None:
        pts = list(points) + ([points[0]] if closed else [])
        flat = [value * k for point in pts for value in point]
        canvas.create_line(*flat, fill=color, width=width_of(w), dash=dash, smooth=smooth,
                           capstyle="round", joinstyle="round", tags="diagram")

    def circle(cx: float, cy: float, r: float, color: str = theme.HEADER_TEXT,
               w: float = 1.2, fill: str = "") -> None:
        canvas.create_oval((cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k,
                           outline=color, width=width_of(w), fill=fill, tags="diagram")

    def arc(cx: float, cy: float, r: float, start: float, extent: float,
            color: str = theme.HEADER_TEXT, w: float = 1.2, dash=None) -> None:
        canvas.create_arc((cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k,
                          start=start, extent=extent, style="arc", outline=color,
                          width=width_of(w), dash=dash, tags="diagram")

    def label(x: float, y: float, text: str, color: str = theme.ACCENT, size_px: float = 10,
              anchor: str = "sw") -> None:
        canvas.create_text(x * k, y * k, text=text, fill=color, anchor=anchor,
                           font=(mono, -max(6, int(round(size_px * k)))), tags="diagram")

    def ticks(x0: float, x1: float, y: float, reach: float = 3) -> None:
        """The two short bars that cap a dimension."""
        for x in (x0, x1):
            line([(x, y - reach), (x, y + reach)], theme.ACCENT)

    def quad(start, control, end, steps: int = 10):
        """A quadratic curve as points, since a Tk line is straight or a spline through all of it."""
        out = []
        for step in range(steps + 1):
            t = step / steps
            u = 1 - t
            out.append((u * u * start[0] + 2 * u * t * control[0] + t * t * end[0],
                        u * u * start[1] + 2 * u * t * control[1] + t * t * end[1]))
        return out

    dashed = (3, 2)
    if key == "module":
        # a tooth on its pitch line, one module of addendum dimensioned
        line([(4, 44), (12, 44), (18, 16), (30, 16), (36, 44), (52, 44)])
        line([(4, 30), (52, 30)], theme.BORDER, dash=dashed)
        line([(45, 16), (45, 30)], theme.ACCENT, 1.8)
        line([(42, 16), (48, 16)], theme.ACCENT)
        line([(42, 30), (48, 30)], theme.ACCENT)
        label(49, 27, "m")
    elif key == "teeth":
        line(_gear_teeth(28, 28, 22, 16, 12), closed=True)
        line(_gear_teeth(28, 28, 22, 16, 12, first=2, span=1), theme.ACCENT, 1.8)
    elif key == "pressure_angle":
        # the pitch point: the tangent, the pitch circle under it, and the line
        # of action leaning α off the tangent
        arc(28, 66, 40, 56.6, 66.8, theme.BORDER, dash=dashed)
        line([(4, 26), (52, 26)])
        line([(8, 33.3), (48, 18.7)], theme.ACCENT, 1.8)
        arc(28, 26, 14, 0, 20, theme.ACCENT)
        circle(28, 26, 1.6, theme.HEADER_TEXT, 1, fill=theme.HEADER_TEXT)
        label(45, 39, "α")
    elif key == "face_width":
        # the gear from the side, its width dimensioned
        line([(21, 8), (35, 8), (35, 44), (21, 44)], closed=True)
        line([(12, 26), (44, 26)], theme.BORDER, dash=dashed)
        line([(21, 51), (35, 51)], theme.ACCENT, 1.8)
        ticks(21, 35, 51)
        label(40, 55, "b")
    elif key == "bore":
        line(_gear_teeth(28, 28, 22, 17, 14), closed=True)
        circle(28, 28, 7, theme.ACCENT, 1.8)
    elif key == "backlash":
        # a tooth sitting in the other gear's space, the gap at the pitch line
        line([(6, 8), (15, 48), (41, 48), (50, 8)])
        line([(14, 8), (21, 44), (35, 44), (42, 8)])
        line([(4, 30), (52, 30)], theme.BORDER, dash=dashed)
        line([(11, 30), (18.5, 30)], theme.ACCENT, 1.8)
        label(4, 25, "j")
    elif key == "fillet":
        # a flank meeting the root circle round a radius
        fillet = quad((30, 46), (22, 46), (20, 38))
        line([(52, 46)] + fillet + [(14, 8)])
        line([(4, 46), (12, 46)])
        line(fillet, theme.ACCENT, 1.8)
        label(30, 39, "ρ")
    elif key == "name":
        # a document
        line([(15, 6), (33, 6), (42, 15), (42, 50), (15, 50)], closed=True)
        line([(33, 6), (33, 15), (42, 15)])
        for y in (26, 32):
            line([(21, y), (36, y)], theme.BORDER)
        line([(21, 38), (31, 38)], theme.BORDER)
    elif key == "centre_distance":
        # two pitch circles touching, the distance between centres dimensioned
        circle(11, 26, 8)
        circle(36, 26, 17)
        for cx in (11, 36):
            line([(cx - 3, 26), (cx + 3, 26)], theme.READOUT)
            line([(cx, 23), (cx, 29)], theme.READOUT)
        line([(11, 50), (36, 50)], theme.ACCENT, 1.8)
        ticks(11, 36, 50)
        label(41, 54, "C")
    elif key == "ratio":
        # a pinion and its wheel: three turns against one
        circle(14, 28, 8, theme.ACCENT, 1.8)
        circle(38, 28, 16)
        label(14, 28, "3", theme.ACCENT, 9, anchor="center")
        label(38, 28, "1", theme.HEADER_TEXT, 9, anchor="center")
    elif key == "series":
        # the standard modules as a scale: tall ticks series 1, short series 2
        line([(4, 34), (52, 34)])
        for x in (6, 14, 22, 30, 38, 46):
            line([(x, 34), (x, 22)], theme.ACCENT, 1.8)
        for x in (10, 18, 26, 34, 42, 50):
            line([(x, 34), (x, 28)], theme.READOUT)
        for x, text in ((6, "1"), (20, "1.5"), (38, "2.5")):
            label(x, 47, text, theme.HEADER_TEXT, 8)


class Explainer(tk.Frame):
    """The card at the foot of a panel: what the field with the caret means.

    A diagram at the left and three lines at the right — the field's name and
    symbol, what the number is, and what the typed value comes to. The words
    are :func:`ui_text.explainer`'s; this only lays them out, so a card that
    says the wrong thing is a bug in the text, not in the window.
    """

    def __init__(self, parent: tk.Misc, text_width: int, bg: str = theme.TRACKER_BG,
                 border: str = theme.TRACKER_BORDER) -> None:
        super().__init__(parent, bg=bg, bd=0, highlightthickness=max(1, px(1)),
                         highlightbackground=border, highlightcolor=border)
        f = theme.fonts()
        self._bg = bg
        self._field = ""
        self.columnconfigure(1, weight=1)

        side = px(DIAGRAM_SIZE)
        self.diagram = tk.Canvas(self, width=side, height=side, bg=bg,
                                 highlightthickness=0, bd=0)
        self.diagram.grid(row=0, column=0, rowspan=3, sticky="nw",
                          padx=(px(10), px(10)), pady=px(8))

        head = tk.Frame(self, bg=bg)
        head.grid(row=0, column=1, sticky="w", padx=(0, px(10)), pady=(px(8), 0))
        self.name = tk.Label(head, text="", bg=bg, fg=theme.INK, font=f.label_bold)
        self.name.grid(row=0, column=0, sticky="w")
        self.symbol = tk.Label(head, text="", bg=bg, fg=theme.MUTED, font=f.mono_small)
        self.symbol.grid(row=0, column=1, sticky="w")

        self.what = tk.Label(self, text="", bg=bg, fg=theme.HEADER_TEXT, font=f.hint,
                             anchor="w", justify="left", wraplength=px(text_width))
        self.what.grid(row=1, column=1, sticky="w", padx=(0, px(10)), pady=(px(4), 0))

        worked = tk.Frame(self, bg=bg)
        worked.grid(row=2, column=1, sticky="w", padx=(0, px(10)), pady=(px(4), px(8)))
        tk.Label(worked, text="here", bg=bg, fg=theme.READOUT, font=f.readout).grid(
            row=0, column=0, sticky="nw")
        self.worked = tk.Label(worked, text="", bg=bg, fg=theme.INK, font=f.mono_tiny,
                               anchor="w", justify="left", wraplength=px(text_width - 32))
        self.worked.grid(row=0, column=1, sticky="w", padx=(px(6), 0))

    @property
    def field(self) -> str:
        """Which field the card is showing, or ``""`` before the first one."""
        return self._field

    def show(self, field: str, name: str, symbol: str, what: str, worked: str) -> None:
        self._field = field
        draw_diagram(self.diagram, field, px(DIAGRAM_SIZE))
        self.name.configure(text=name)
        self.symbol.configure(text=f" · {symbol}" if symbol else "")
        self.what.configure(text=what)
        self.worked.configure(text=worked)


class Icon(tk.Canvas):
    def __init__(self, parent: tk.Misc, name: str, color: str = theme.INK,
                 size: int = 14, bg: str = theme.WHITE) -> None:
        side = px(size)
        super().__init__(parent, width=side, height=side, bg=bg,
                         highlightthickness=0, bd=0)
        self._icon_name = name
        self._size = side
        self.set_color(color)

    def set_color(self, color: str) -> None:
        draw_icon(self, self._icon_name, color, self._size)

    def set_background(self, color: str) -> None:
        self.configure(bg=color)


class Dot(tk.Canvas):
    """The 7–8 px disc that carries a state colour in the header and the footer."""

    def __init__(self, parent: tk.Misc, color: str, size: int = 7,
                 bg: str = theme.WHITE) -> None:
        side = px(size)
        super().__init__(parent, width=side, height=side, bg=bg,
                         highlightthickness=0, bd=0)
        self._side = side
        self._id = self.create_oval(0, 0, side - 1, side - 1, outline="", fill=color)

    def set_color(self, color: str) -> None:
        self.itemconfigure(self._id, fill=color)


# ------------------------------------------------------------------- panels


class Panel(tk.Frame):
    """A titled box with a readout in its header, per §5.

    The readout is the panel's state in one short line — it is what lets the
    strip stay this dense without the user having to read the fields back to
    find out what the panel is set to.
    """

    def __init__(self, parent: tk.Misc, title: str,
                 readout: Optional[tk.StringVar] = None,
                 header_pad: int = 12) -> None:
        super().__init__(parent, bg=theme.BORDER_SOFT, bd=0,
                         highlightthickness=0)
        f = theme.fonts()
        border = max(1, px(1))
        inner = tk.Frame(self, bg=theme.WHITE, bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=border, pady=border)
        inner.columnconfigure(0, weight=1)

        header = tk.Frame(inner, bg=theme.HEADER_BG, height=px(26), bd=0,
                          highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(1, weight=1)
        tk.Label(
            header, text=title.upper(), bg=theme.HEADER_BG,
            fg=theme.HEADER_TEXT, font=f.header,
        ).grid(row=0, column=0, sticky="w", padx=(px(header_pad), 0), pady=px(5))
        self.header = header

        self.readout_label = tk.Label(
            header, textvariable=readout, text="" if readout else "",
            bg=theme.HEADER_BG, fg=theme.READOUT, font=f.readout, anchor="e",
        )
        self.readout_label.grid(row=0, column=1, sticky="e", padx=(px(8), px(header_pad)))

        Rule(inner).grid(row=1, column=0, sticky="ew")

        self.body = tk.Frame(inner, bg=theme.WHITE, bd=0, highlightthickness=0)
        self.body.grid(row=2, column=0, sticky="nsew", padx=px(12), pady=px(8))
        inner.rowconfigure(2, weight=1)

    def header_slot(self) -> tk.Frame:
        """Room at the right of the header for a button, ahead of the readout."""
        slot = tk.Frame(self.header, bg=theme.HEADER_BG)
        slot.grid(row=0, column=2, sticky="e", padx=(px(8), px(12)), pady=px(2))
        return slot


# ------------------------------------------------------------------- fields


class Field(tk.Frame):
    """A 26 px text field: mono text, an optional unit, an optional placeholder.

    The placeholder is a label sitting on top of an empty field rather than
    text put into the variable. The form is read straight out of these
    variables by :meth:`gui.ConverterApp._spec`, and a placeholder that could
    be read back as a value would be a silent wrong number.
    """

    def __init__(self, parent: tk.Misc, variable: tk.StringVar, width: int = 84,
                 unit: str = "", placeholder: Optional[str] = None, prefix: str = "",
                 mono: bool = True, grow: bool = False, height: int = 26) -> None:
        super().__init__(parent, bg=theme.WHITE, bd=0,
                         highlightthickness=max(1, px(1)),
                         highlightbackground=theme.BORDER,
                         highlightcolor=theme.BORDER,
                         height=px(height))
        f = theme.fonts()
        self.variable = variable
        self._enabled = True
        self._marked = False
        self._grow = grow
        if not grow:
            self.configure(width=px(width))
        self.grid_propagate(False)
        self.pack_propagate(False)

        self._prefix_label = None
        if prefix:
            self._prefix_label = tk.Label(self, text=prefix, bg=theme.WHITE,
                                          fg=theme.READOUT, font=f.tiny)
            self._prefix_label.pack(side="left", padx=(px(8), 0))

        self._unit_label = None
        if unit:
            self._unit_label = tk.Label(self, text=unit, bg=theme.WHITE,
                                        fg=theme.READOUT, font=f.readout)
            self._unit_label.pack(side="right", padx=(0, px(8)))

        self.entry = tk.Entry(
            self, textvariable=variable, bd=0, highlightthickness=0,
            relief="flat", bg=theme.WHITE, fg=theme.INK,
            disabledbackground=theme.DISABLED_BG, disabledforeground=theme.FAINT,
            readonlybackground=theme.DISABLED_BG,
            insertbackground=theme.INK, font=f.mono if mono else f.label,
            width=1, justify="left",
        )
        left = 0 if prefix else px(8)
        right = 0 if unit else px(8)
        self.entry.pack(side="left", fill="both", expand=True, padx=(left, right))

        # A field that will only know its placeholder later — Target chord
        # shows the source chord, which arrives with the file — is built with
        # the label already there and nothing in it.
        self._placeholder = None
        if placeholder is not None:
            self._placeholder = tk.Label(
                self, text=placeholder, bg=theme.WHITE, fg=theme.FAINT,
                font=f.mono if mono else f.label, anchor="w",
            )
            self._placeholder.bind("<Button-1>", lambda _e: self.entry.focus_set())
            variable.trace_add("write", lambda *_: self._show_placeholder())
            self.entry.bind("<FocusIn>", self._on_focus, add="+")
            self.entry.bind("<FocusOut>", self._on_blur, add="+")
            self.after_idle(self._show_placeholder)

        self.entry.bind("<FocusIn>", lambda _e: self._paint_border(), add="+")
        self.entry.bind("<FocusOut>", lambda _e: self._paint_border(), add="+")

    # -- placeholder

    def set_placeholder(self, text: str) -> None:
        if self._placeholder is None:
            return
        self._placeholder.configure(text=text)
        if text:
            self._show_placeholder()
        else:
            self._placeholder.place_forget()

    def _show_placeholder(self) -> None:
        if self._placeholder is None or not self._placeholder.cget("text"):
            return
        empty = not self.variable.get() and self.focus_get() is not self.entry
        if empty and self._enabled:
            self._placeholder.place(in_=self.entry, x=0, rely=0.5, anchor="w")
        else:
            self._placeholder.place_forget()

    def _on_focus(self, _event: tk.Event) -> None:
        if self._placeholder is not None:
            self._placeholder.place_forget()

    def _on_blur(self, _event: tk.Event) -> None:
        self._show_placeholder()

    # -- state

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        bg = theme.WHITE if enabled else theme.DISABLED_BG
        fg = theme.READOUT if enabled else theme.FAINT
        self.configure(bg=bg)
        self.entry.configure(state="normal" if enabled else "disabled", bg=bg)
        for label in (self._prefix_label, self._unit_label):
            if label is not None:
                label.configure(bg=bg, fg=fg)
        if self._placeholder is not None:
            self._placeholder.configure(bg=bg)
            self._show_placeholder()
        self._paint_border()

    def set_marked(self, marked: bool) -> None:
        """Mark a field as filled by a pick, per §6: an ink border, not a tint."""
        self._marked = marked
        self._paint_border()

    def _paint_border(self) -> None:
        if not self._enabled:
            color = theme.RULE
        elif self.focus_get() is self.entry or self._marked:
            color = theme.ACCENT
        else:
            color = theme.BORDER
        self.configure(highlightbackground=color, highlightcolor=color)


# ------------------------------------------------------------- segmented row


class Segmented(tk.Frame):
    """A row of segments over one variable — every radio row in the old window.

    Which segments exist is fixed; which can be *chosen* is not (``Loaded``
    only means something once a curve file is open), so a segment can be turned
    off on its own without leaving the row.
    """

    def __init__(self, parent: tk.Misc, variable: tk.StringVar,
                 values: Sequence[str], labels: Optional[Dict[str, str]] = None,
                 command: Optional[Callable[[], None]] = None, mono: bool = False,
                 height: int = 22, width: Optional[int] = None,
                 bg: str = theme.WHITE) -> None:
        super().__init__(parent, bg=theme.TRACK, bd=0,
                         highlightthickness=max(1, px(1)),
                         highlightbackground=theme.BORDER_SOFT,
                         highlightcolor=theme.BORDER_SOFT)
        f = theme.fonts()
        self.variable = variable
        self.command = command
        self._values = tuple(values)
        self._font = f.mono_small if mono else f.hint
        self._enabled = True
        self._off: set = set()
        self._cells: Dict[str, Tuple[tk.Frame, tk.Label]] = {}
        if width:
            # Fixing one axis in Tk fixes both, so the height the segments
            # would have taken has to be given back to it explicitly.
            border = max(1, px(1))
            self.configure(width=px(width),
                           height=px(height) + 2 * px(2) + 2 * border)
            self.grid_propagate(False)

        pad = px(2)
        for column, value in enumerate(self._values):
            self.columnconfigure(column, weight=1, uniform="seg")
            cell = tk.Frame(self, bg=theme.TRACK, bd=0, height=px(height),
                            highlightthickness=max(1, px(1)),
                            highlightbackground=theme.TRACK,
                            highlightcolor=theme.TRACK)
            cell.grid(row=0, column=column, sticky="nsew",
                      padx=(pad, 0) if column == 0 else (pad, 0),
                      pady=pad)
            if column == len(self._values) - 1:
                cell.grid_configure(padx=(pad, pad))
            cell.grid_propagate(False)
            cell.columnconfigure(0, weight=1)
            cell.rowconfigure(0, weight=1)
            text = (labels or {}).get(value, value)
            label = tk.Label(cell, text=text, bg=theme.TRACK,
                             fg=theme.HEADER_TEXT, font=self._font)
            label.grid(row=0, column=0, sticky="nsew")
            for widget in (cell, label):
                widget.bind("<Button-1>", lambda _e, v=value: self._choose(v))
            self._cells[value] = (cell, label)

        variable.trace_add("write", lambda *_: self._paint())
        self._paint()

    def _choose(self, value: str) -> None:
        if not self._enabled or value in self._off or self.variable.get() == value:
            return
        self.variable.set(value)
        if self.command is not None:
            self.command()

    def _paint(self) -> None:
        f = theme.fonts()
        current = self.variable.get()
        for value, (cell, label) in self._cells.items():
            chosen = value == current
            if not self._enabled:
                bg, fg, ring = theme.DISABLED_BG, theme.FAINT, theme.DISABLED_BG
                if chosen:
                    ring = theme.RULE
            elif chosen:
                bg, fg, ring = theme.WHITE, theme.INK, theme.BORDER
            elif value in self._off:
                bg, fg, ring = theme.TRACK, theme.GLYPH_OFF, theme.TRACK
            else:
                bg, fg, ring = theme.TRACK, theme.HEADER_TEXT, theme.TRACK
            cell.configure(bg=bg, highlightbackground=ring, highlightcolor=ring)
            bold = self._font is f.mono_small
            label.configure(
                bg=bg, fg=fg,
                font=(f.mono_bold if bold else f.label_bold) if chosen else self._font,
            )
        self.configure(bg=theme.DISABLED_BG if not self._enabled else theme.TRACK)

    def set_option_enabled(self, value: str, enabled: bool) -> None:
        if enabled:
            self._off.discard(value)
        else:
            self._off.add(value)
        self._paint()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._paint()

    def configure(self, cnf=None, **kwargs):  # noqa: D401 - matches ttk's spelling
        state = kwargs.pop("state", None)
        if state is not None:
            self.set_enabled(state != "disabled")
        return super().configure(cnf, **kwargs)

    config = configure


# --------------------------------------------------------------- check, box


class Check(tk.Frame):
    """A 15 px box and a label, per §5. Toggles from either."""

    def __init__(self, parent: tk.Misc, variable: tk.BooleanVar, text: str,
                 command: Optional[Callable[[], None]] = None,
                 bg: str = theme.WHITE) -> None:
        super().__init__(parent, bg=bg, bd=0, highlightthickness=0)
        f = theme.fonts()
        self.variable = variable
        self.command = command
        self._enabled = True
        self._bg = bg
        side = px(15)
        self.canvas = tk.Canvas(self, width=side, height=side, bg=bg,
                                highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0)
        self.label = tk.Label(self, text=text, bg=bg, fg=theme.LABEL, font=f.label)
        self.label.grid(row=0, column=1, padx=(px(7), 0))
        for widget in (self.canvas, self.label):
            widget.bind("<Button-1>", lambda _e: self._toggle())
        variable.trace_add("write", lambda *_: self._paint())
        self._paint()

    def _toggle(self) -> None:
        if not self._enabled:
            return
        self.variable.set(not self.variable.get())
        if self.command is not None:
            self.command()

    def _paint(self) -> None:
        side = px(15)
        c = self.canvas
        c.delete("all")
        checked = bool(self.variable.get())
        if not self._enabled:
            fill, outline = theme.DISABLED_BG, theme.BORDER_SOFT
        elif checked:
            fill, outline = theme.ACCENT, theme.ACCENT
        else:
            fill, outline = theme.WHITE, theme.READOUT
        c.create_rectangle(0, 0, side - 1, side - 1, fill=fill, outline=outline,
                           width=max(1, px(1)))
        if checked:
            width = max(1, int(round(2.2 * side / 16.0)))
            c.create_line(
                *_scaled(((3.6, 8.2), (6.4, 11.2), (12.2, 4.8)), side),
                fill=theme.WHITE if self._enabled else theme.FAINT,
                width=width, capstyle="round", joinstyle="round",
            )
        self.label.configure(fg=theme.LABEL if self._enabled else theme.FAINT)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._paint()

    def set_background(self, color: str) -> None:
        self._bg = color
        for widget in (self, self.canvas, self.label):
            widget.configure(bg=color)
        self._paint()

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop("state", None)
        if state is not None:
            self.set_enabled(state != "disabled")
        return super().configure(cnf, **kwargs)

    config = configure


# ------------------------------------------------------------------ buttons


class Button(tk.Frame):
    """A secondary or primary button, with an optional 14 px stroke icon.

    It answers ``configure(state=...)``, because the window enables and
    disables buttons from several handlers that predate it.
    """

    def __init__(self, parent: tk.Misc, text: str,
                 command: Optional[Callable[[], None]] = None, icon: str = "",
                 primary: bool = False, height: int = 26,
                 bg: str = theme.WHITE) -> None:
        super().__init__(parent, bd=0, highlightthickness=max(1, px(1)))
        f = theme.fonts()
        self.command = command
        self._primary = primary
        self._enabled = True
        self._hover = False
        # A button is as wide as its text and as tall as the design says, and
        # Tk will not fix one axis without the other — so the height is made
        # out of padding rather than taken away from the geometry manager.
        font = f.label_bold if primary else f.label
        pad = px(18 if primary else 10)
        tall = max(0, (px(height) - font.metrics("linespace")) // 2)
        self._icon = Icon(self, icon, theme.INK, 14, theme.WHITE) if icon else None
        if self._icon is not None:
            self._icon.pack(side="left", padx=(pad, px(6)), pady=tall)
        self.label = tk.Label(self, text=text, font=font)
        self.label.pack(side="left", padx=(0 if self._icon is not None else pad, pad),
                        pady=tall)

        for widget in (self, self.label) + ((self._icon,) if self._icon else ()):
            widget.bind("<Button-1>", self._press)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        self._paint()

    def _press(self, _event: tk.Event) -> None:
        if self._enabled and self.command is not None:
            self.command()

    def _enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._paint()

    def _leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._paint()

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)

    def set_icon(self, name: str) -> None:
        if self._icon is not None:
            self._icon._icon_name = name  # noqa: SLF001 - its own kind of widget
            self._icon.set_color(self.label.cget("fg"))

    def _paint(self) -> None:
        if self._primary:
            fill = theme.INK if self._hover and self._enabled else theme.ACCENT
            border, text = fill, theme.WHITE
            if not self._enabled:
                fill = border = theme.GLYPH_OFF
        elif not self._enabled:
            fill, border, text = theme.DISABLED_BG, theme.RULE, theme.FAINT
        else:
            fill = theme.HEADER_BG if self._hover else theme.SECONDARY_BG
            border, text = theme.BORDER, theme.INK
        self.configure(bg=fill, highlightbackground=border, highlightcolor=border)
        self.label.configure(bg=fill, fg=text)
        if self._icon is not None:
            self._icon.set_background(fill)
            self._icon.set_color(text)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._paint()

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop("state", None)
        if state is not None:
            self.set_enabled(state != "disabled")
        return super().configure(cnf, **kwargs)

    config = configure


# ------------------------------------------------------- the pick tracker's
#                                                          three glyphs


class StepGlyph(tk.Canvas):
    """Done, active, or still to come — the whole point of the tracker."""

    def __init__(self, parent: tk.Misc, bg: str = theme.TRACKER_BG,
                 size: int = 16) -> None:
        side = px(size)
        super().__init__(parent, width=side, height=side, bg=bg,
                         highlightthickness=0, bd=0)
        self._side = side
        self.set_state("pending")

    def set_state(self, state: str) -> None:
        side = self._side
        self.delete("all")
        inset = max(1, int(round(side * 0.06)))
        box = (inset, inset, side - inset - 1, side - inset - 1)
        if state == "done":
            self.create_oval(*box, fill=theme.OK, outline="")
            self.create_line(
                *_scaled(((4.2, 8.2), (6.9, 10.9), (11.8, 5.4)), side),
                fill=theme.WHITE, width=max(1, int(round(2.0 * side / 16.0))),
                capstyle="round", joinstyle="round",
            )
        elif state == "active":
            self.create_oval(*box, outline=theme.ACCENT,
                             width=max(1, int(round(2.0 * side / 16.0))))
            middle = side / 2.0
            radius = side * 0.16
            self.create_oval(middle - radius, middle - radius,
                             middle + radius, middle + radius,
                             fill=theme.ACCENT, outline="")
        else:
            self.create_oval(*box, outline=theme.GLYPH_OFF,
                             width=max(1, int(round(1.5 * side / 16.0))))


class Outline(tk.Canvas):
    """The loaded section, 110 × 14, so the file's name is not the only proof."""

    def __init__(self, parent: tk.Misc, width: int = 110, height: int = 14,
                 bg: str = theme.WHITE) -> None:
        super().__init__(parent, width=px(width), height=px(height), bg=bg,
                         highlightthickness=0, bd=0)
        self._width = px(width)
        self._height = px(height)

    def show(self, points: Optional[Iterable[Tuple[float, float]]]) -> None:
        self.delete("all")
        if not points:
            return
        pts = list(points)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        span_x = (max(xs) - min(xs)) or 1.0
        span_y = (max(ys) - min(ys)) or 1.0
        # The chord fills the width; the thickness is drawn to the same scale
        # unless it would not fit, which no aerofoil does.
        scale = min(self._width / span_x, self._height / span_y)
        left = (self._width - span_x * scale) / 2.0
        middle = self._height / 2.0
        flat: List[float] = []
        for x, y in pts:
            flat.append(left + (x - min(xs)) * scale)
            flat.append(middle - (y - (min(ys) + span_y / 2.0)) * scale)
        self.create_line(*flat, fill=theme.HEADER_TEXT, width=max(1, px(1)),
                         capstyle="round", joinstyle="round")
