"""Single-window tkinter front end for the gear generator."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import __version__, findings, preview, store, swbuild, swcom, theme, ui_text, widgets
from .gears import KINDS, PLANNED_KINDS, pair as pairs, standards
from .gears.base import Diagnostic, GeometryError, Point2
from .gears.equations import literal
from .spec import (
    MODE_PAIR,
    MODE_SINGLE,
    RECIPE_ARCS,
    RECIPE_INVOLUTE,
    GearSpec,
    InputError,
    PairSpec,
    pair_stems,
)

OK_COLOR = theme.OK
ERROR_COLOR = theme.ERROR

# The window is a portrait strip beside SolidWorks, with the pair candidates in
# a flyout docked to its right — the same frame as Airfoil Converter's.
STRIP_WIDTH = 460
FLYOUT_WIDTH = 360

# Typing is re-derived this long after the last keystroke, so a field being
# typed into does not redraw the preview once per character.
DEBOUNCE_MS = 120

# The explainer card's text column: the panel body, less the card's own border
# and padding and the 56 px diagram beside it.
EXPLAINER_TEXT_WIDTH = STRIP_WIDTH - 114

SIDES = ("a", "b")

# Every GearSpec field, and the key of the per-side variable holding it. Kept as
# data so a test can prove it covers the dataclass exactly: a field added
# without a line here would be silently dropped from every build.
GEAR_VARS = (
    ("module", "module"),
    ("teeth", "teeth"),
    ("pressure_angle", "pressure_angle"),
    ("face_width", "face_width"),
    ("bore", "bore"),
    ("backlash", "backlash"),
    ("fillet", "fillet"),
    ("helix_angle", "helix_angle"),
    ("hand", "hand"),
    ("name", "name"),
)
# Shared by both gears, or fixed in this version.
GEAR_COMPOUND = ("kind", "recipe", "profile_shift")

# Every PairSpec field, and the app attribute holding it.
PAIR_VARS = (
    ("mode", "mode"),
    ("centre_distance", "centre_distance"),
    ("ratio", "ratio"),
    ("module", "pair_module"),
    ("series", "series"),
    ("min_teeth", "min_teeth"),
    ("max_teeth", "max_teeth"),
    ("helix_angle", "pair_helix_angle"),
    ("helix_min", "helix_min"),
    ("helix_max", "helix_max"),
    ("assembly_name", "assembly_name"),
)
PAIR_COMPOUND = ("gear_a", "gear_b")

KIND_VALUES = tuple(KINDS) + tuple(PLANNED_KINDS)
MODE_VALUES = (MODE_SINGLE, MODE_PAIR)
MODE_LABELS = {MODE_SINGLE: "Single gear", MODE_PAIR: "Gear pair"}
SERIES_LABELS = ui_text.SERIES_LABELS

# Tabbing or arrowing through a field is not an edit.
NAVIGATION_KEYS = frozenset(
    {
        "Tab", "ISO_Left_Tab", "Left", "Right", "Up", "Down", "Home", "End",
        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    }
)


def _read_key(session) -> tuple:
    """The cheapest question worth asking every second."""
    document = session.active_document()
    return (session.pid, document.title if document else "", document.path if document else "")


def _read_snapshot(session) -> dict:
    """Everything the bar draws, as plain data. No COM object comes back."""
    document = session.active_document()
    return {
        "key": _read_key(session),
        "version": session.label,
        "newer_than_tested": swcom.is_newer_than_tested(session.revision),
        "title": document.title if document else "",
        "path": document.path if document else "",
        "doc_type": document.doc_type if document else 0,
        "is_part": bool(document and document.is_part),
    }


class GearApp(ttk.Frame):
    def __init__(self, master: tk.Misc, scale: float = 1.0) -> None:
        super().__init__(master, padding=0)
        self.scale = scale
        self.fonts = theme.setup(master, scale)
        master.configure(background=theme.WINDOW)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.recent = store.load_recent()
        defaults = GearSpec()

        self.kind = tk.StringVar(value="spur")
        recipe = self.recent.recipe if self.recent.recipe in (RECIPE_INVOLUTE, RECIPE_ARCS) else findings.DEFAULT_RECIPE
        self.recipe = tk.StringVar(value=recipe)
        self.mode = tk.StringVar(value=self.recent.mode if self.recent.mode in MODE_VALUES else MODE_SINGLE)

        self.gear_vars: Dict[str, Dict[str, tk.StringVar]] = {
            side: {attr: tk.StringVar(value=getattr(defaults, field)) for field, attr in GEAR_VARS}
            for side in SIDES
        }
        self.gear_vars["b"]["teeth"].set("50")

        pair_defaults = PairSpec()
        self.centre_distance = tk.StringVar(value=pair_defaults.centre_distance)
        self.ratio = tk.StringVar(value=pair_defaults.ratio)
        self.pair_module = tk.StringVar(value=pair_defaults.module)
        self.series = tk.StringVar(value=pair_defaults.series)
        self.min_teeth = tk.StringVar(value=pair_defaults.min_teeth)
        self.max_teeth = tk.StringVar(value=pair_defaults.max_teeth)
        self.pair_helix_angle = tk.StringVar(value=pair_defaults.helix_angle)
        self.helix_min = tk.StringVar(value=pair_defaults.helix_min)
        self.helix_max = tk.StringVar(value=pair_defaults.helix_max)
        self.assembly_name = tk.StringVar(value=pair_defaults.assembly_name)

        self.out_folder = tk.StringVar(value=self.recent.folder)
        self.part_template = tk.StringVar(value=self.recent.part_template)
        self.assembly_template = tk.StringVar(value=self.recent.assembly_template)
        self.status = tk.StringVar(value="Type a gear, or switch to Gear pair to solve one.")

        # Derived text: each is a panel's state in one line, worked out by
        # ui_text and only put here.
        self.kind_readout = tk.StringVar(value="")
        self.gear_readouts = {side: tk.StringVar(value="") for side in SIDES}
        self.derived_readout = tk.StringVar(value="")
        self.pair_readout = tk.StringVar(value="")
        self.solve_summary = tk.StringVar(value="")
        self.output_readout = tk.StringVar(value="")
        self.sw_headline = tk.StringVar(value="looking for SolidWorks")
        self.sw_status = tk.StringVar(value="")
        self.mode_note = tk.StringVar(value="")
        self.card_title = tk.StringVar(value="No candidate chosen")
        self.card_detail = tk.StringVar(value="")

        # The explainer card follows the caret: one card at the foot of the
        # panel that has it, and which field it is showing.
        self.cards: Dict[str, widgets.Explainer] = {}
        self._card_panel = "a"
        self._card_field = "module"

        # Worked out from the form, for the build and the preview.
        self._derived: Dict[str, Any] = {side: None for side in SIDES}
        self._side_stems: Dict[str, str] = {side: "" for side in SIDES}
        self._outlines: Dict[str, List[Point2]] = {side: [] for side in SIDES}
        self._diagnostics: Dict[str, List[Diagnostic]] = {side: [] for side in SIDES}
        self._derive_after: Optional[str] = None
        self._candidates: List[pairs.Candidate] = []
        self._chosen: Optional[pairs.Candidate] = None
        self._applying = False
        self._flyout_open = False

        # The record opened from disk, if any; it decides whether Update values shows.
        self._loaded: Optional[store.Sidecar] = None
        self._loaded_path = ""

        # The link to SolidWorks. None until the first look, and dropped again
        # whenever a call fails, so a reopened session is picked up on its own.
        self._worker: Optional[swcom.Worker] = None
        self._pending: Optional[Any] = None
        self._pending_kind = ""
        self._pending_build: Optional[Any] = None
        self._build_context: Optional[Dict[str, Any]] = None
        self._tick_failure = ""
        self._snapshot: Optional[dict] = None
        self._quiet_ticks = 0

        self._build()
        self._watch_form()
        self._show_card("a", "module")
        self._on_mode_changed()
        self._refresh_link_labels()
        self._derive_now()
        self._start_link()

    # ---------------------------------------------------------------- layout
    #
    # Panels top to bottom in a 460 px strip, a footer pinned under them, and
    # the pair candidates in a flyout to the right. Every control comes from
    # :mod:`widgets` and every colour and size from :mod:`theme`.

    def _build(self) -> None:
        self.columnconfigure(0, weight=0, minsize=theme.px(STRIP_WIDTH + 24))
        self.columnconfigure(3, weight=1, minsize=theme.px(FLYOUT_WIDTH))
        self.rowconfigure(0, weight=1)

        # The strip is a page: nothing inside it scrolls on its own, but the
        # whole page scrolls when the screen is shorter than it is.
        self._page = tk.Canvas(self, bg=theme.WINDOW, highlightthickness=0, bd=0,
                               width=theme.px(STRIP_WIDTH + 24))
        self._page.grid(row=0, column=0, sticky="nsew")
        self._page_bar = ttk.Scrollbar(self, orient="vertical", style="Af.Vertical.TScrollbar",
                                       command=self._page.yview)
        self._page.configure(yscrollcommand=self._page_bar.set)

        strip = tk.Frame(self._page, bg=theme.WINDOW)
        self._page_window = self._page.create_window(
            (0, 0), window=strip, anchor="nw", width=theme.px(STRIP_WIDTH + 24)
        )
        self._build_strip(strip)
        strip.bind("<Configure>", self._fit_page)
        self._page.bind("<Configure>", self._fit_page)
        self._page.bind_all("<MouseWheel>", self._on_wheel, add="+")
        self.after_idle(self._size_page)

        self._flyout_edge = tk.Frame(self, bg=theme.BORDER_SOFT, width=max(1, theme.px(1)))
        self._flyout_edge.grid(row=0, column=2, sticky="ns")
        self.flyout = tk.Frame(self, bg=theme.SECONDARY_BG)
        self.flyout.grid(row=0, column=3, sticky="nsew")
        self._build_flyout(self.flyout)
        self._flyout_edge.grid_remove()
        self.flyout.grid_remove()
        self.columnconfigure(3, minsize=0)

    def _size_page(self) -> None:
        strip = self._page.nametowidget(self._page.itemcget(self._page_window, "window"))
        room = _work_area_height(self.winfo_toplevel()) - theme.px(40)
        self._page.configure(height=min(strip.winfo_reqheight(), room))

    def _relayout(self) -> None:
        if hasattr(self, "_page"):
            self.after(50, self._fit_page)

    def _fit_page(self, _event: Optional[tk.Event] = None) -> None:
        strip = self._page.nametowidget(self._page.itemcget(self._page_window, "window"))
        wanted = strip.winfo_reqheight()
        visible = self._page.winfo_height()
        self._page.itemconfigure(self._page_window, height=max(wanted, visible))
        self._page.configure(scrollregion=(0, 0, self._page.winfo_width(), max(wanted, visible)))
        if wanted > visible:
            self._page_bar.grid(row=0, column=1, sticky="ns")
        else:
            self._page_bar.grid_remove()
            self._page.yview_moveto(0)

    def _on_wheel(self, event: tk.Event) -> None:
        if not self._page_bar.winfo_ismapped():
            return
        over = self.winfo_containing(event.x_root, event.y_root)
        while over is not None:
            if over is self.flyout:
                return
            over = getattr(over, "master", None)
        self._page.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _build_strip(self, strip: tk.Misc) -> None:
        strip.columnconfigure(0, weight=1)
        strip.rowconfigure(0, weight=1)
        body = tk.Frame(strip, bg=theme.WINDOW)
        body.grid(row=0, column=0, sticky="nsew", padx=theme.px(12), pady=theme.px(12))
        body.columnconfigure(0, weight=1, minsize=theme.px(STRIP_WIDTH))

        self.gear_panel = self._build_gear_kind(body)
        self.pair_panel = self._build_pair(body)
        self.side_panels = {side: self._build_side(body, side) for side in SIDES}
        self.derived_panel = self._build_derived(body)
        self.output_panel = self._build_output(body)
        self.sw_panel = self._build_sw_bar(body)
        # Top to bottom, the order of the work: what kind of gear, the solver
        # that fills the gears in, the gears themselves, what they come to,
        # where they go, and SolidWorks. The Pair panel is not here at all in
        # single mode, so the strip is the shorter list rather than a greyed
        # one.
        order = [self.gear_panel, self.pair_panel, self.side_panels["a"], self.side_panels["b"],
                 self.derived_panel, self.output_panel, self.sw_panel]
        for row, panel in enumerate(order):
            panel.grid(row=row, column=0, sticky="ew", pady=(0, theme.px(8)))

        row = len(order)
        body.rowconfigure(row, weight=1)
        tk.Frame(body, bg=theme.WINDOW).grid(row=row, column=0, sticky="nsew")
        self._build_footer(body).grid(row=row + 1, column=0, sticky="ew")

    # -- the pieces every panel is made of

    def _row_label(self, parent: tk.Misc, row: int, text: str) -> tk.Label:
        label = tk.Label(parent, text=text, bg=theme.WHITE, fg=theme.LABEL,
                         font=self.fonts.label, anchor="w")
        label.grid(row=row, column=0, sticky="w", pady=(0, theme.px(6)))
        return label

    def _cell(self, parent: tk.Misc, row: int, column: int = 1, **grid) -> tk.Frame:
        frame = tk.Frame(parent, bg=theme.WHITE)
        grid.setdefault("sticky", "w")
        grid.setdefault("pady", (0, theme.px(6)))
        frame.grid(row=row, column=column, **grid)
        return frame

    def _hint(self, parent: tk.Misc, text: str = "", **options) -> tk.Label:
        return tk.Label(parent, text=text, bg=theme.WHITE, fg=theme.MUTED, font=self.fonts.hint, **options)

    def _combo(self, parent: tk.Misc, variable: tk.StringVar, values, width: int, mono: bool = True):
        holder = tk.Frame(parent, bg=theme.WHITE, width=theme.px(width), height=theme.px(26))
        holder.grid_propagate(False)
        holder.pack_propagate(False)
        box = ttk.Combobox(holder, textvariable=variable, values=values, state="readonly",
                           style="Mono.TCombobox" if mono else "Af.TCombobox")
        box.pack(fill="both", expand=True)
        return holder, box

    @staticmethod
    def _set_title(panel: widgets.Panel, title: str) -> None:
        panel.header.winfo_children()[0].configure(text=title.upper())

    # -- Gear: what kind, which recipe, one gear or two

    def _build_gear_kind(self, parent: tk.Misc) -> widgets.Panel:
        panel = widgets.Panel(parent, "Gear", self.kind_readout)
        body = panel.body
        body.columnconfigure(0, minsize=theme.px(118))
        body.columnconfigure(1, weight=1)

        self._row_label(body, 0, "Kind")
        kinds = self._cell(body, 0, sticky="ew")
        kinds.columnconfigure(0, weight=1)
        self.kind_seg = widgets.Segmented(
            kinds, self.kind, KIND_VALUES, labels=ui_text.KIND_LABELS, command=self._schedule_derive,
        )
        self.kind_seg.grid(row=0, column=0, sticky="ew")
        for planned in PLANNED_KINDS:
            self.kind_seg.set_option_enabled(planned, False)
        self._hint(kinds, "later").grid(row=0, column=1, padx=(theme.px(8), 0))

        self._row_label(body, 1, "Flank")
        widgets.Segmented(
            body, self.recipe, (RECIPE_INVOLUTE, RECIPE_ARCS), labels=ui_text.RECIPE_LABELS,
            command=self._schedule_derive, width=200,
        ).grid(row=1, column=1, sticky="w", pady=(0, theme.px(6)))

        self._row_label(body, 2, "Make")
        widgets.Segmented(
            body, self.mode, MODE_VALUES, labels=MODE_LABELS, command=self._on_mode_changed, width=200,
        ).grid(row=2, column=1, sticky="w")
        return panel

    # -- Gear A and Gear B

    def _build_side(self, parent: tk.Misc, side: str) -> widgets.Panel:
        panel = widgets.Panel(parent, f"Gear {side.upper()}", self.gear_readouts[side])
        body = panel.body
        body.columnconfigure(0, minsize=theme.px(118))
        body.columnconfigure(1, weight=1)
        v = self.gear_vars[side]
        fields: Dict[str, widgets.Field] = {}

        self._row_label(body, 0, "Module")
        cell = self._cell(body, 0)
        fields["module"] = widgets.Field(cell, v["module"], width=84, unit="mm")
        fields["module"].grid(row=0, column=0)
        pick = tk.StringVar(value="")
        holder, box = self._combo(cell, pick, [ui_text._n(m, 4) for m in standards.modules(standards.SERIES_ALL)], 72)
        holder.grid(row=0, column=1, padx=(theme.px(8), 0))
        box.bind("<<ComboboxSelected>>", lambda _e, s=side, p=pick: self._pick_value(s, "module", p))
        self._hint(cell, "ISO 54").grid(row=0, column=2, padx=(theme.px(8), 0))

        self._row_label(body, 1, "Teeth")
        cell = self._cell(body, 1)
        fields["teeth"] = widgets.Field(cell, v["teeth"], width=84)
        fields["teeth"].grid(row=0, column=0)

        self._row_label(body, 2, "Pressure angle")
        cell = self._cell(body, 2)
        fields["pressure_angle"] = widgets.Field(cell, v["pressure_angle"], width=84, unit="°")
        fields["pressure_angle"].grid(row=0, column=0)
        angle = tk.StringVar(value="")
        holder, box = self._combo(cell, angle, standards.PRESSURE_ANGLES, 72)
        holder.grid(row=0, column=1, padx=(theme.px(8), 0))
        box.bind("<<ComboboxSelected>>", lambda _e, s=side, p=angle: self._pick_value(s, "pressure_angle", p))

        self._row_label(body, 3, "Face width")
        cell = self._cell(body, 3)
        fields["face_width"] = widgets.Field(cell, v["face_width"], width=84, unit="mm")
        fields["face_width"].grid(row=0, column=0)

        self._row_label(body, 4, "Bore")
        cell = self._cell(body, 4)
        fields["bore"] = widgets.Field(cell, v["bore"], width=84, unit="mm", placeholder="none")
        fields["bore"].grid(row=0, column=0)

        self._row_label(body, 5, "Backlash")
        cell = self._cell(body, 5)
        fields["backlash"] = widgets.Field(cell, v["backlash"], width=150, unit="mm", placeholder="0.3 × module")
        fields["backlash"].grid(row=0, column=0)
        self._hint(cell, "ISO: 0.02–0.05 × m").grid(row=0, column=1, padx=(theme.px(8), 0))

        self._row_label(body, 6, "Fillet")
        cell = self._cell(body, 6)
        fields["fillet"] = widgets.Field(cell, v["fillet"], width=150, unit="mm", placeholder="0.38 × module")
        fields["fillet"].grid(row=0, column=0)

        self._row_label(body, 7, "Name")
        cell = self._cell(body, 7, sticky="ew", pady=0)
        cell.columnconfigure(0, weight=1)
        fields["name"] = widgets.Field(cell, v["name"], grow=True, placeholder="")
        fields["name"].grid(row=0, column=0, sticky="ew")

        # The card for whichever of these fields has the caret. It is a row of
        # this panel, so the strip reflows when the caret crosses to the other
        # gear rather than two cards of the same sentences standing open.
        card = widgets.Explainer(body, EXPLAINER_TEXT_WIDTH)
        card.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(theme.px(8), 0))
        self.cards[side] = card
        for name, field in fields.items():
            self._explains(field, side, name)

        if side == "a":
            self.fields_a = fields
        else:
            self.fields_b = fields
        return panel

    def _side_fields(self, side: str) -> Dict[str, widgets.Field]:
        return self.fields_a if side == "a" else self.fields_b

    # -- the explainer card
    #
    # One card, at the foot of the panel whose field has the caret; the other
    # panels' cards are taken out of the grid, so the strip is no taller for
    # them. What it says is ui_text's, worked out again on every derive.

    def _explains(self, field: widgets.Field, panel: str, name: str) -> None:
        """Putting the caret in this field brings up that card."""
        field.entry.bind("<FocusIn>", lambda _e: self._show_card(panel, name), add="+")

    def _show_card(self, panel: str, field: str) -> None:
        self._card_panel, self._card_field = panel, field
        for key, card in self.cards.items():
            card.grid() if key == panel else card.grid_remove()
        self._refresh_card()
        self._relayout()

    def _refresh_card(self) -> None:
        """Fill the card in from the form as it stands."""
        card = self.cards.get(self._card_panel)
        if card is None:
            return
        side = "a" if self._card_panel == "pair" else self._card_panel
        pair = self._pair_spec() if self.mode.get() == MODE_PAIR else None
        card.show(self._card_field, *ui_text.explainer(
            self._card_field, self._derived[side], self._side_stems[side], pair, self.out_folder.get()))

    def _pick_value(self, side: str, attr: str, picked: tk.StringVar) -> None:
        """A dropdown beside a field writes into the field, and then lets go."""
        if picked.get():
            self.gear_vars[side][attr].set(picked.get())
        picked.set("")

    # -- Derived: what the numbers come to, drawn and listed

    def _build_derived(self, parent: tk.Misc) -> widgets.Panel:
        panel = widgets.Panel(parent, "Derived", self.derived_readout)
        body = panel.body
        body.columnconfigure(0, weight=1)

        # One picture for the whole panel, the body's full width: in pair mode
        # the two gears meshed, in single mode the one gear, dimensioned.
        self.preview = tk.Canvas(body, width=theme.px(preview.WIDTH), height=theme.px(preview.HEIGHT),
                                 bg=theme.WHITE, highlightthickness=0, bd=0)
        self.preview.grid(row=0, column=0, sticky="w", pady=(0, theme.px(6)))

        # The pair's own three values, above the per-gear columns and ruled off
        # from them: they belong to neither gear.
        self.pair_rows = tk.Frame(body, bg=theme.WHITE)
        self.pair_rows.grid(row=1, column=0, sticky="ew")
        self.pair_rows.columnconfigure(0, minsize=theme.px(104))
        self.pair_rows.columnconfigure(1, minsize=theme.px(96))
        self._pair_row_widgets: List[tk.Widget] = []
        self.pair_rule = widgets.Rule(body, color=theme.TRACK)
        self.pair_rule.grid(row=2, column=0, sticky="ew", pady=theme.px(4))

        self.derived_rows = tk.Frame(body, bg=theme.WHITE)
        self.derived_rows.grid(row=3, column=0, sticky="nw")
        self.derived_rows.columnconfigure(0, minsize=theme.px(104))
        for column in (1, 2):
            self.derived_rows.columnconfigure(column, minsize=theme.px(96))
        self._derived_widgets: List[tk.Widget] = []

        self.warning_frame = tk.Frame(body, bg=theme.WHITE)
        self.warning_frame.grid(row=4, column=0, sticky="ew", pady=(theme.px(4), 0))
        self._warning_widgets: List[tk.Widget] = []
        return panel

    # -- Pair: the solver

    def _build_pair(self, parent: tk.Misc) -> widgets.Panel:
        panel = widgets.Panel(parent, "Pair", self.pair_readout)
        slot = panel.header_slot()
        # The candidates belong to the solver, so the button that shows them
        # sits in its header rather than in the SolidWorks bar's.
        self.candidates_button = widgets.Button(slot, "Candidates", command=self._toggle_flyout,
                                                icon="sidebar", height=20, bg=theme.HEADER_BG)
        self.candidates_button.grid(row=0, column=0)

        body = panel.body
        body.columnconfigure(0, minsize=theme.px(118))
        body.columnconfigure(1, weight=1)
        self.pair_fields: List[widgets.Field] = []

        def field(row: int, label: str, variable: tk.StringVar, explains: str = "",
                  **options) -> Tuple[tk.Frame, widgets.Field]:
            self._row_label(body, row, label)
            cell = self._cell(body, row)
            made = widgets.Field(cell, variable, **options)
            made.grid(row=0, column=0)
            self.pair_fields.append(made)
            if explains:
                self._explains(made, "pair", explains)
            return cell, made

        field(0, "Centre distance", self.centre_distance, "centre_distance", width=84, unit="mm")
        cell, _ = field(1, "Ratio", self.ratio, "ratio", width=84)
        self._hint(cell, "3, or 1:3 for driven over driver").grid(row=0, column=1, padx=(theme.px(8), 0))
        cell, _ = field(2, "Module", self.pair_module, "pair_module", width=84, unit="mm", placeholder="any")
        self._hint(cell, "blank tries every standard one").grid(row=0, column=1, padx=(theme.px(8), 0))

        self._row_label(body, 3, "Series")
        # A segmented row takes no caret, so choosing a series is what shows its
        # card — the nearest thing to putting the caret in it.
        self.series_seg = widgets.Segmented(
            body, self.series, standards.SERIES, labels=SERIES_LABELS, width=220,
            command=lambda: (self._show_card("pair", "series"), self._schedule_derive()),
        )
        self.series_seg.grid(row=3, column=1, sticky="w", pady=(0, theme.px(6)))

        self._row_label(body, 4, "Teeth")
        cell = self._cell(body, 4)
        low = widgets.Field(cell, self.min_teeth, width=60)
        low.grid(row=0, column=0)
        tk.Label(cell, text="to", bg=theme.WHITE, fg=theme.LABEL, font=self.fonts.label).grid(
            row=0, column=1, padx=theme.px(8))
        high = widgets.Field(cell, self.max_teeth, width=60)
        high.grid(row=0, column=2)
        self._hint(cell, "under min is undercut").grid(row=0, column=3, padx=(theme.px(8), 0))
        self.pair_fields.extend((low, high))
        for made in (low, high):
            self._explains(made, "pair", "teeth_range")

        cell, _ = field(5, "Assembly name", self.assembly_name, "assembly_name", width=220, placeholder="")
        self.assembly_field = self.pair_fields[-1]

        solve = tk.Frame(body, bg=theme.WHITE)
        solve.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(theme.px(2), 0))
        solve.columnconfigure(1, weight=1)
        self.solve_button = widgets.Button(solve, "Solve", command=self._solve, icon="refresh")
        self.solve_button.grid(row=0, column=0, sticky="w")
        tk.Label(solve, textvariable=self.solve_summary, bg=theme.WHITE, fg=theme.MUTED,
                 font=self.fonts.hint, anchor="w").grid(row=0, column=1, sticky="w", padx=(theme.px(8), 0))

        card = widgets.Explainer(body, EXPLAINER_TEXT_WIDTH)
        card.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(theme.px(8), 0))
        self.cards["pair"] = card
        return panel

    # -- Output: where the parts go, and what they are made from

    def _build_output(self, parent: tk.Misc) -> widgets.Panel:
        panel = widgets.Panel(parent, "Output", self.output_readout)
        body = panel.body
        body.columnconfigure(0, minsize=theme.px(118))
        body.columnconfigure(1, weight=1)

        self._row_label(body, 0, "Folder")
        cell = self._cell(body, 0, sticky="ew")
        cell.columnconfigure(0, weight=1)
        widgets.Field(cell, self.out_folder, grow=True).grid(row=0, column=0, sticky="ew")
        widgets.Button(cell, "Browse", command=self._browse_folder, icon="folder").grid(
            row=0, column=1, padx=(theme.px(8), 0))

        self._row_label(body, 1, "Part template")
        cell = self._cell(body, 1, sticky="ew")
        cell.columnconfigure(0, weight=1)
        widgets.Field(cell, self.part_template, grow=True, placeholder="SolidWorks default").grid(
            row=0, column=0, sticky="ew")
        widgets.Button(cell, "Browse", command=lambda: self._browse_template(self.part_template, "part"),
                       icon="folder").grid(row=0, column=1, padx=(theme.px(8), 0))

        self.asm_label = self._row_label(body, 2, "Assembly template")
        self.asm_cell = self._cell(body, 2, sticky="ew")
        self.asm_cell.columnconfigure(0, weight=1)
        widgets.Field(self.asm_cell, self.assembly_template, grow=True, placeholder="SolidWorks default").grid(
            row=0, column=0, sticky="ew")
        widgets.Button(self.asm_cell, "Browse",
                       command=lambda: self._browse_template(self.assembly_template, "assembly"),
                       icon="folder").grid(row=0, column=1, padx=(theme.px(8), 0))

        record = tk.Frame(body, bg=theme.WHITE)
        record.grid(row=3, column=0, columnspan=2, sticky="ew")
        record.columnconfigure(1, weight=1)
        widgets.Button(record, "Open .gear.json", command=self._open_record, icon="folder").grid(
            row=0, column=0, sticky="w")
        self.record_hint = self._hint(record, "put a built gear back on the form", anchor="w")
        self.record_hint.grid(row=0, column=1, sticky="w", padx=(theme.px(8), 0))
        return panel

    # -- the SolidWorks bar

    def _build_sw_bar(self, parent: tk.Misc) -> widgets.Panel:
        panel = widgets.Panel(parent, "SolidWorks")
        slot = panel.header_slot()
        self.sw_dot = widgets.Dot(slot, theme.FAINT, bg=theme.HEADER_BG)
        self.sw_dot.grid(row=0, column=0, padx=(0, theme.px(6)))
        tk.Label(slot, textvariable=self.sw_headline, bg=theme.HEADER_BG, fg=theme.READOUT,
                 font=self.fonts.readout).grid(row=0, column=1)

        body = panel.body
        body.columnconfigure(1, weight=1)
        widgets.Icon(body, "info", theme.MUTED, 14).grid(row=0, column=0, sticky="nw")
        tk.Label(body, textvariable=self.mode_note, bg=theme.WHITE, fg=theme.INK, font=self.fonts.hint,
                 justify="left", anchor="w", wraplength=theme.px(STRIP_WIDTH - 60)).grid(
            row=0, column=1, sticky="w", padx=(theme.px(8), 0))
        self.manual_label = tk.Label(body, text="", bg=theme.WHITE, fg=theme.MUTED, font=self.fonts.hint,
                                     justify="left", anchor="w", wraplength=theme.px(STRIP_WIDTH - 60))
        self.manual_label.grid(row=1, column=1, sticky="w", padx=(theme.px(8), 0), pady=(theme.px(4), 0))
        return panel

    # -- the footer

    def _build_footer(self, parent: tk.Misc) -> tk.Frame:
        footer = tk.Frame(parent, bg=theme.WINDOW)
        footer.columnconfigure(1, weight=1)
        self.status_dot = widgets.Dot(footer, theme.OK, size=8, bg=theme.WINDOW)
        self.status_dot.grid(row=0, column=0, padx=(0, theme.px(8)))
        self.status_label = tk.Label(footer, textvariable=self.status, bg=theme.WINDOW, fg=theme.OK,
                                     font=self.fonts.label, anchor="w", justify="left",
                                     wraplength=theme.px(STRIP_WIDTH - 200))
        self.status_label.grid(row=0, column=1, sticky="w")
        self.update_button = widgets.Button(footer, "Update values", command=self._update_values,
                                            height=32, bg=theme.WINDOW)
        self.update_button.grid(row=0, column=2, sticky="e", padx=(theme.px(8), 0))
        self.update_button.grid_remove()
        self.build_button = widgets.Button(footer, "Build", command=self._build_gear, primary=True,
                                           height=32, bg=theme.WINDOW)
        self.build_button.grid(row=0, column=3, sticky="e", padx=(theme.px(8), 0))
        return footer

    # -- the flyout: pair candidates

    def _build_flyout(self, parent: tk.Misc) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        pad = theme.px(12)

        head = tk.Frame(parent, bg=theme.SECONDARY_BG)
        head.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, 0))
        head.columnconfigure(0, weight=1)
        tk.Label(head, text="PAIR CANDIDATES", bg=theme.SECONDARY_BG, fg=theme.HEADER_TEXT,
                 font=self.fonts.header).grid(row=0, column=0, sticky="w")
        widgets.Button(head, "Hide", command=self._toggle_flyout, height=20,
                       bg=theme.SECONDARY_BG).grid(row=0, column=1, sticky="e")

        tk.Label(parent, textvariable=self.solve_summary, bg=theme.SECONDARY_BG, fg=theme.MUTED,
                 font=self.fonts.readout, anchor="w").grid(row=1, column=0, sticky="nw", padx=pad,
                                                           pady=(theme.px(8), theme.px(8)))

        holder = widgets.Box(parent, bg=theme.WHITE)
        holder.grid(row=2, column=0, sticky="nsew", padx=pad)
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        self.candidate_tree = ttk.Treeview(holder, columns=("module", "teeth", "error"), show="headings",
                                           height=14, selectmode="browse", style="Af.Treeview")
        for column, title, width in (("module", "MODULE", 70), ("teeth", "TEETH", 90), ("error", "ERROR", 150)):
            self.candidate_tree.heading(column, text=title)
            self.candidate_tree.column(column, width=theme.px(width), stretch=column == "error")
        self.candidate_tree.grid(row=0, column=0, sticky="nsew")
        self.candidate_tree.bind("<<TreeviewSelect>>", self._on_candidate_selected)
        scroll = ttk.Scrollbar(holder, orient="vertical", style="Af.Vertical.TScrollbar",
                               command=self.candidate_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.candidate_tree.configure(yscrollcommand=scroll.set)
        self.candidate_tree.tag_configure("exact", foreground=OK_COLOR)
        self.candidate_tree.tag_configure("near", foreground=theme.INK)

        card = widgets.Box(parent, bg=theme.WHITE)
        card.grid(row=3, column=0, sticky="ew", padx=pad, pady=(theme.px(8), pad))
        inner = tk.Frame(card, bg=theme.WHITE)
        inner.pack(fill="both", expand=True, padx=theme.px(10), pady=theme.px(8))
        tk.Label(inner, textvariable=self.card_title, bg=theme.WHITE, fg=theme.INK,
                 font=self.fonts.label_bold, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(inner, textvariable=self.card_detail, bg=theme.WHITE, fg=theme.MUTED,
                 font=self.fonts.readout, anchor="w", justify="left",
                 wraplength=theme.px(FLYOUT_WIDTH - 44)).grid(row=1, column=0, sticky="w", pady=(theme.px(4), 0))
        tk.Label(inner, text="Click a row to put its module and teeth on both gears. Nothing else "
                             "on the form changes.",
                 bg=theme.WHITE, fg=theme.MUTED, font=self.fonts.readout, anchor="w", justify="left",
                 wraplength=theme.px(FLYOUT_WIDTH - 44)).grid(row=2, column=0, sticky="w", pady=(theme.px(4), 0))

    def _toggle_flyout(self, show: Optional[bool] = None) -> None:
        """Show or hide the candidates, growing the window rather than the strip."""
        wanted = (not self._flyout_open) if show is None else show
        if wanted == self._flyout_open:
            return
        self._flyout_open = wanted
        root = self.winfo_toplevel()
        root.update_idletasks()
        width, height = root.winfo_width(), root.winfo_height()
        delta = theme.px(FLYOUT_WIDTH) + max(1, theme.px(1))
        if wanted:
            self.columnconfigure(3, minsize=theme.px(FLYOUT_WIDTH))
            self._flyout_edge.grid()
            self.flyout.grid()
            root.geometry(f"{width + delta}x{height}")
        else:
            self._flyout_edge.grid_remove()
            self.flyout.grid_remove()
            self.columnconfigure(3, minsize=0)
            root.geometry(f"{max(width - delta, theme.px(STRIP_WIDTH + 24))}x{height}")
        self.candidates_button.set_text("Hide candidates" if wanted else "Candidates")

    # ----------------------------------------------------------- interaction

    def _set_status(self, message: str, ok: bool = True) -> None:
        self.status.set(message)
        color = OK_COLOR if ok else ERROR_COLOR
        self.status_label.configure(foreground=color)
        self.status_dot.set_color(color)

    def _watch_form(self) -> None:
        """Every field re-derives the gear, a moment after the last keystroke."""
        for side in SIDES:
            for var in self.gear_vars[side].values():
                var.trace_add("write", lambda *_: self._schedule_derive())
        for var in (self.kind, self.recipe, self.centre_distance, self.ratio, self.pair_module,
                    self.series, self.min_teeth, self.max_teeth, self.pair_helix_angle, self.helix_min,
                    self.helix_max, self.assembly_name, self.out_folder):
            var.trace_add("write", lambda *_: self._schedule_derive())

    def _on_mode_changed(self) -> None:
        pair_mode = self.mode.get() == MODE_PAIR
        self._set_title(self.side_panels["a"], "Gear A" if pair_mode else "Gear")
        if pair_mode:
            self.pair_panel.grid()
            self.side_panels["b"].grid()
            self.asm_label.grid()
            self.asm_cell.grid()
        else:
            # The solver is not disabled in single mode, it is not there: one
            # gear has no pair to solve, and a greyed panel is only clutter.
            self.pair_panel.grid_remove()
            self.side_panels["b"].grid_remove()
            self.asm_label.grid_remove()
            self.asm_cell.grid_remove()
            # Hide came with the Pair panel, so the candidates go with it.
            self._toggle_flyout(False)
            if self._card_panel != "a":
                self._show_card("a", "module")
        self.solve_button.configure(state="normal" if pair_mode else "disabled")
        self._derive_now()
        self._relayout()

    def _schedule_derive(self) -> None:
        if self._derive_after is not None:
            self.after_cancel(self._derive_after)
        self._derive_after = self.after(DEBOUNCE_MS, self._derive_now)

    def _active_sides(self) -> Tuple[str, ...]:
        return SIDES if self.mode.get() == MODE_PAIR else ("a",)

    def _gear_spec(self, side: str) -> GearSpec:
        """One gear on the form, as data. Every value goes across as the text typed."""
        values = {field: self.gear_vars[side][attr].get() for field, attr in GEAR_VARS}
        values.update(kind=self.kind.get(), recipe=self.recipe.get(), profile_shift="0")
        return GearSpec(**values)

    def _pair_spec(self) -> PairSpec:
        values: Dict[str, Any] = {field: getattr(self, attr).get() for field, attr in PAIR_VARS}
        values["gear_a"] = self._gear_spec("a")
        values["gear_b"] = self._gear_spec("b")
        return PairSpec(**values)

    def _stems(self) -> List[str]:
        if self.mode.get() == MODE_PAIR:
            return list(pair_stems(self._pair_spec()))
        return [self._gear_spec("a").stem()]

    def _derive_now(self) -> None:
        """Work the gear out again and redraw everything that depends on it."""
        self._derive_after = None
        kind = KINDS.get(self.kind.get())
        self.kind_readout.set(ui_text.kind_readout(self.kind.get(), self.recipe.get()))
        try:
            # A placeholder is the name the file will get: in a pair that is
            # Pinion_ or Gear_ by size, not each gear's own default.
            stems = dict(zip(SIDES, self._stems())) if self.mode.get() == MODE_PAIR else {}
        except InputError:
            stems = {}
        for side in SIDES:
            spec = self._gear_spec(side)
            self.gear_readouts[side].set(ui_text.gear_readout(spec))
            self._side_stems[side] = stems.get(side) or spec.default_stem()
            self._side_fields(side)["name"].set_placeholder(self._side_stems[side])
            self._derived[side], self._outlines[side], self._diagnostics[side] = None, [], []
            if kind is None:
                self._diagnostics[side] = [Diagnostic("error", "That kind of gear comes in a later version.")]
                continue
            try:
                diagnostics = kind.validate(spec)
                self._diagnostics[side] = diagnostics
                if any(d.is_error for d in diagnostics):
                    continue
                derived = kind.derive(spec)
                self._derived[side] = derived
                self._outlines[side] = kind.outline(spec, derived)
            except (GeometryError, InputError, ValueError) as exc:
                self._diagnostics[side] = [Diagnostic("error", str(exc))]
                self._derived[side] = None

        self._show_derived()
        self._draw_preview()
        self._refresh_pair_readout()
        self._refresh_card()
        self.output_readout.set(ui_text.output_readout(self.out_folder.get()))
        try:
            self.mode_note.set(ui_text.mode_note(self.mode.get(), self._stems(), *self._update_target()))
        except InputError:
            self.mode_note.set("Build will make a new part.")
        ready = all(self._derived[side] is not None for side in self._active_sides())
        busy = self._pending_build is not None
        self.build_button.configure(state="normal" if ready and not busy else "disabled")
        self._show_update_button()
        self._relayout()

    def _pair_values(self) -> Optional[Tuple[float, float, float]]:
        """``(centre distance, ratio, contact ratio)`` of the pair on the form.

        ``None`` unless both gears work out, which is also when the Derived
        panel has a pair to say anything about.
        """
        a, b = self._derived["a"], self._derived["b"]
        if self.mode.get() != MODE_PAIR or a is None or b is None:
            return None
        return pairs.describe(a.module, a.teeth, b.teeth, a.pressure_angle_deg)

    def _show_derived(self) -> None:
        for widget in self._derived_widgets + self._warning_widgets + self._pair_row_widgets:
            widget.destroy()
        self._derived_widgets, self._warning_widgets, self._pair_row_widgets = [], [], []

        sides = self._active_sides()
        shown = [side for side in sides if self._derived[side] is not None]
        first = self._derived[shown[0]] if shown else None
        pair = self._pair_values()
        if pair is not None:
            self.derived_readout.set(ui_text.pair_derived_readout(*pair))
        else:
            self.derived_readout.set(ui_text.derived_line(first) if first is not None else "")

        # The pair's own values, above the two columns and ruled off from them.
        if pair is not None:
            rows = ui_text.pair_derived_rows(*pair, self._derived["a"].teeth, self._derived["b"].teeth)
            for row, (label, value) in enumerate(rows):
                name = tk.Label(self.pair_rows, text=label, bg=theme.WHITE, fg=theme.LABEL,
                                font=self.fonts.hint, anchor="w")
                name.grid(row=row, column=0, sticky="w")
                text = tk.Label(self.pair_rows, text=value, bg=theme.WHITE, fg=theme.INK,
                                font=self.fonts.mono_tiny, anchor="w")
                text.grid(row=row, column=1, sticky="w", padx=(theme.px(8), 0))
                self._pair_row_widgets.extend((name, text))
            self.pair_rows.grid()
            self.pair_rule.grid()
        else:
            self.pair_rows.grid_remove()
            self.pair_rule.grid_remove()

        if shown:
            columns = [dict(ui_text.derived_rows(self._derived[side])) for side in shown]
            labels = [label for label, _ in ui_text.derived_rows(first)]
            for index, side in enumerate(shown):
                caption = f"{side.upper()} · mm" if len(sides) > 1 else "mm"
                head = tk.Label(self.derived_rows, text=caption, bg=theme.WHITE, fg=theme.READOUT,
                                font=self.fonts.tiny, anchor="w")
                head.grid(row=0, column=1 + index, sticky="w", padx=(theme.px(8), 0))
                self._derived_widgets.append(head)
            for row, label in enumerate(labels, start=1):
                name = tk.Label(self.derived_rows, text=label, bg=theme.WHITE, fg=theme.LABEL,
                                font=self.fonts.hint, anchor="w")
                name.grid(row=row, column=0, sticky="w")
                self._derived_widgets.append(name)
                for index, values in enumerate(columns):
                    value = tk.Label(self.derived_rows, text=values[label], bg=theme.WHITE, fg=theme.INK,
                                     font=self.fonts.mono_tiny, anchor="w")
                    value.grid(row=row, column=1 + index, sticky="w", padx=(theme.px(8), 0))
                    self._derived_widgets.append(value)

        lines: List[Tuple[str, str]] = []
        for side in sides:
            prefix = f"{side.upper()}: " if len(sides) > 1 else ""
            for diagnostic in self._diagnostics[side]:
                lines.append((prefix + diagnostic.message, diagnostic.level))
        for row, (text, level) in enumerate(dict.fromkeys(lines)):
            label = tk.Label(self.warning_frame, text=text, bg=theme.WHITE,
                             fg=theme.ERROR if level == "error" else theme.MUTED,
                             font=self.fonts.hint, anchor="w", justify="left",
                             wraplength=theme.px(STRIP_WIDTH - 30))
            label.grid(row=row, column=0, sticky="w")
            self._warning_widgets.append(label)

    def _draw_preview(self) -> None:
        """The gears themselves: in pair mode meshed, at one scale, dimensioned.

        Where everything goes is :mod:`preview`'s, in design pixels; this turns
        those into the screen's pixels and strokes them. Nothing is drawn until
        every gear in the mode works out, because half a pair drawn alone would
        be at a scale the other half is about to change.
        """
        canvas = self.preview
        canvas.delete("all")
        width, height = theme.px(preview.WIDTH), theme.px(preview.HEIGHT)
        sides = self._active_sides()
        if any(not self._outlines[side] for side in sides):
            canvas.create_text(width / 2, height / 2, text="no gear", fill=theme.FAINT,
                               font=self.fonts.hint)
            return

        k = width / float(preview.WIDTH)          # design pixels to this screen's
        line = max(1, theme.px(1))
        made = preview.layout([self._derived[side] for side in sides],
                              labels=[side.upper() for side in sides])
        scale = made.scale * k
        # The pitch circles first and faintest: the two touching at the pitch
        # point is what says the pair is meshed.
        for placed in made.gears:
            x, y, r = placed.x * k, placed.y * k, placed.pitch_radius * scale
            canvas.create_oval(x - r, y - r, x + r, y + r, outline=theme.BORDER_SOFT,
                               width=line, dash=(3, 3))
        for side, placed in zip(sides, made.gears):
            flat = [value * k for point in preview.points_on(self._outlines[side], placed, made.scale)
                    for value in point]
            canvas.create_line(*flat, fill=theme.HEADER_TEXT, width=line)
            x, y = placed.x * k, placed.y * k
            if placed.bore_radius > 0:
                r = placed.bore_radius * scale
                canvas.create_oval(x - r, y - r, x + r, y + r, outline=theme.HEADER_TEXT, width=line)
            arm = theme.px(5)
            canvas.create_line(x - arm, y, x + arm, y, fill=theme.READOUT, width=line)
            canvas.create_line(x, y - arm, x, y + arm, fill=theme.READOUT, width=line)
            if placed.label:
                canvas.create_text(x + theme.px(8), y - theme.px(8), text=placed.label, anchor="sw",
                                   fill=theme.READOUT, font=self.fonts.tiny)

        dimension = made.dimension
        for x, top, bottom in dimension.extensions:
            canvas.create_line(x * k, top * k, x * k, bottom * k, fill=theme.BORDER, width=line)
        canvas.create_line(dimension.x0 * k, dimension.y * k, dimension.x1 * k, dimension.y * k,
                           fill=theme.HEADER_TEXT, width=line, arrow="both",
                           arrowshape=(theme.px(7), theme.px(7), theme.px(3)))
        canvas.create_text(dimension.text_x * k, dimension.text_y * k, text=dimension.text,
                           anchor="s", fill=theme.INK, font=self.fonts.mono_tiny)

    def _refresh_pair_readout(self) -> None:
        self.pair_readout.set(ui_text.pair_readout(self.centre_distance.get(), self.ratio.get(), self._chosen))

    # -- solving a pair

    def _solve(self) -> None:
        if self.mode.get() != MODE_PAIR:
            return
        try:
            candidates = pairs.solve_spec(self._pair_spec())
        except (InputError, ValueError) as exc:
            self._set_status(str(exc), ok=False)
            return
        self._candidates = candidates
        self._chosen = None
        self.solve_summary.set(ui_text.solve_summary(candidates))
        self.candidate_tree.delete(*self.candidate_tree.get_children())
        for index, candidate in enumerate(candidates):
            module, teeth, error, tag = ui_text.candidate_row(candidate)
            self.candidate_tree.insert("", "end", iid=str(index), values=(module, teeth, error), tags=(tag,))
        self.card_title.set("No candidate chosen")
        self.card_detail.set("")
        self._toggle_flyout(True)
        self._refresh_pair_readout()
        self._set_status(ui_text.solve_summary(candidates) + ". Choose one in the list.", ok=bool(candidates))

    def _on_candidate_selected(self, _event: Optional[tk.Event] = None) -> None:
        selected = self.candidate_tree.selection()
        if not selected:
            return
        candidate = self._candidates[int(selected[0])]
        spec_a, spec_b = pairs.apply(candidate, self._gear_spec("a"), self._gear_spec("b"))
        self._applying = True
        try:
            for side, spec in (("a", spec_a), ("b", spec_b)):
                self.gear_vars[side]["module"].set(spec.module)
                self.gear_vars[side]["teeth"].set(spec.teeth)
        finally:
            self._applying = False
        self._chosen = candidate
        self.solve_summary.set(ui_text.solve_summary(self._candidates, candidate))
        centre, ratio, epsilon = pairs.describe(candidate.module, candidate.teeth_driver,
                                                candidate.teeth_driven, spec_a.pressure_angle_deg())
        self.card_title.set(f"m{ui_text._n(candidate.module, 4)} · {candidate.teeth_driver} : {candidate.teeth_driven}")
        self.card_detail.set(
            f"C {ui_text._n(centre)} mm · i {ui_text._n(ratio, 4)} · contact ratio "
            f"{ui_text.contact_ratio_text(epsilon)}" + (" · non-standard module" if not candidate.standard else "")
            + (" · undercut" if candidate.undercut else "")
        )
        self._derive_now()
        self._set_status(f"Both gears now carry module {ui_text._n(candidate.module, 4)}: "
                         f"{candidate.teeth_driver} and {candidate.teeth_driven} teeth.")

    # -- files

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose the folder the gears are saved in")
        if path:
            self.out_folder.set(os.path.normpath(path))

    def _browse_template(self, variable: tk.StringVar, what: str) -> None:
        pattern = "*.prtdot" if what == "part" else "*.asmdot"
        path = filedialog.askopenfilename(
            title=f"Choose a SolidWorks {what} template",
            filetypes=[(f"{what.title()} template", pattern), ("All files", "*.*")],
        )
        if path:
            variable.set(os.path.normpath(path))

    def _open_record(self) -> None:
        path = filedialog.askopenfilename(title="Open a gear record",
                                          filetypes=[("Gear record", "*.gear.json"), ("All files", "*.*")])
        if path:
            self._load_record(path)

    def _load_record(self, path: str) -> None:
        """Put a built gear back on the form, and remember it for Update values."""
        try:
            sidecar = store.load(path)
        except store.StoreError as exc:
            self._set_status(str(exc), ok=False)
            return
        if sidecar is None:
            self._set_status(f"There is no gear record at {path}.", ok=False)
            return
        spec = GearSpec.from_dict(sidecar.record.spec)
        self.mode.set(MODE_SINGLE)
        self._on_mode_changed()
        if spec.recipe in (RECIPE_INVOLUTE, RECIPE_ARCS):
            self.recipe.set(spec.recipe)
        for field, attr in GEAR_VARS:
            self.gear_vars["a"][attr].set(getattr(spec, field))
        self._loaded, self._loaded_path = sidecar, path
        self.recent.remember(path)
        store.save_recent(self.recent)
        self.record_hint.configure(text=os.path.basename(path))
        self._derive_now()
        self._set_status(f"Opened {os.path.basename(path)}. Open its part in SolidWorks to update its values.")

    # -- building
    #
    # A build is planned here, on the Tk thread, from the form as it stands; the
    # plan is plain data, so it crosses to the worker as one job and nothing
    # COM-shaped comes back. The poll collects the result, writes the records
    # beside the parts, and says what happened in one sentence.

    def _update_target(self) -> Tuple[int, str]:
        """How many variables Update values would change, and in which document.

        Only for the part an opened record describes, while it is the active
        document, and only for a change the equations can carry.
        """
        sidecar, snapshot = self._loaded, self._snapshot
        if sidecar is None or not snapshot or self.mode.get() != MODE_SINGLE:
            return 0, ""
        if not store.same_path(snapshot.get("path", ""), sidecar.part_path) or self._derived["a"] is None:
            return 0, ""
        spec = self._gear_spec("a")
        kind = KINDS.get(spec.kind)
        if kind is None or swbuild.structural_change(sidecar.record.spec, spec.to_dict()):
            return 0, ""
        trig = sidecar.record.trig or findings.TRIG_DEFAULT
        held = {name: "".join(expression.split()) for name, expression in sidecar.record.variables}
        count = sum(1 for v in kind.variables(spec, self._derived["a"])
                    if held.get(v.name) != "".join(v.expression_for(trig).split()))
        return count, snapshot.get("title", "")

    def _show_update_button(self) -> None:
        if self._update_target()[0] and self._pending_build is None:
            self.update_button.grid()
        else:
            self.update_button.grid_remove()

    def _build_gear(self) -> None:
        if self._pending_build is not None:
            return
        if self._worker is None:
            self._set_status("SolidWorks cannot be reached from here, so nothing was built. "
                             + swcom.unavailable_reason(), ok=False)
            return
        folder = self.out_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            self._set_status("Choose an output folder that exists before building.", ok=False)
            return
        try:
            context = self._plan_pair(folder) if self.mode.get() == MODE_PAIR else self._plan_single(folder)
        except (InputError, GeometryError, ValueError) as exc:
            self._set_status(str(exc), ok=False)
            return
        existing = [path for path in context["paths"] if os.path.exists(path)]
        if existing:
            self._set_status(f"{existing[0]} already exists, and a build never overwrites a file. "
                             "Change the name or the folder.", ok=False)
            return
        self._build_context = context
        self._pending_build = self._worker.submit(context.pop("job"))
        self._set_status(f"Building {', '.join(os.path.basename(p) for p in context['paths'])} in SolidWorks…")
        self._derive_now()

    def _plan_single(self, folder: str) -> Dict[str, Any]:
        spec, derived = self._gear_spec("a"), self._derived["a"]
        if derived is None:
            raise InputError("The gear on the form does not work out yet, so it cannot be built.")
        kind = KINDS[spec.kind]
        path = os.path.join(folder, spec.stem() + ".SLDPRT")
        plan = kind.plan(spec, derived, kind.recipe_for(spec), self.part_template.get().strip(), path)
        return {"job_kind": MODE_SINGLE, "paths": [path], "plans": [plan], "specs": [spec], "derived": [derived],
                "job": lambda session: swbuild.build(session, plan)}

    def _plan_pair(self, folder: str) -> Dict[str, Any]:
        pair = self._pair_spec()
        if self._derived["a"] is None or self._derived["b"] is None:
            raise InputError("Both gears must work out before a pair can be built.")
        stem_a, stem_b, stem_pair = pair_stems(pair)
        spec_a, spec_b = pair.gear_a, pair.gear_b
        path_a, path_b = os.path.join(folder, stem_a + ".SLDPRT"), os.path.join(folder, stem_b + ".SLDPRT")
        path_pair = os.path.join(folder, stem_pair + ".SLDASM")
        template = self.part_template.get().strip()
        plans = []
        for spec, side, path in ((spec_a, "a", path_a), (spec_b, "b", path_b)):
            kind = KINDS[spec.kind]
            plans.append(kind.plan(spec, self._derived[side], kind.recipe_for(spec), template, path))
        assembly = pairs.assembly_plan(spec_a, spec_b, path_a, path_b, self.assembly_template.get().strip(), path_pair)
        plan_a, plan_b = plans
        return {"job_kind": MODE_PAIR, "paths": [path_a, path_b, path_pair], "plans": plans,
                "specs": [spec_a, spec_b], "derived": [self._derived["a"], self._derived["b"]],
                "job": lambda session: swbuild.build_pair(session, plan_a, plan_b, assembly)}

    def _update_values(self) -> None:
        if self._pending_build is not None or self._worker is None:
            return
        sidecar = self._loaded
        if sidecar is None:
            self._set_status("Open a gear's .gear.json first, so the tool knows which part to update.", ok=False)
            return
        spec, derived = self._gear_spec("a"), self._derived["a"]
        if derived is None:
            self._set_status("The gear on the form does not work out yet, so nothing was updated.", ok=False)
            return
        reason = swbuild.structural_change(sidecar.record.spec, spec.to_dict())
        if reason:
            self._set_status(reason, ok=False)
            return
        variables = KINDS[spec.kind].variables(spec, derived)
        part = sidecar.part_path
        self._build_context = {"job_kind": "update", "spec": spec, "derived": derived, "variables": variables,
                               "sidecar": sidecar, "record_path": self._loaded_path}
        self._pending_build = self._worker.submit(lambda session: swbuild.update_variables(session, variables, part))
        self._set_status(f"Updating the values in {sidecar.part_title}…")
        self._derive_now()

    def _collect_build(self) -> None:
        if self._pending_build is None:
            return
        answer = self._pending_build.poll()
        if answer is None:
            return
        value, error = answer
        context, self._pending_build, self._build_context = self._build_context or {}, None, None
        try:
            if error is not None:
                if isinstance(error, swcom.SolidWorksError):
                    self._set_status(str(error), ok=False)
                else:
                    self._set_status(f"The build hit a problem in SolidWorks — {type(error).__name__}: {error}",
                                     ok=False)
            elif context.get("job_kind") == "update":
                self._finish_update(context, value)
            elif context.get("job_kind") == MODE_PAIR:
                self._finish_pair(context, value)
            else:
                self._finish_single(context, value)
        finally:
            self._derive_now()

    def _finish_single(self, context: Dict[str, Any], result: swbuild.BuildResult) -> None:
        _log(result.log_lines())
        text, ok = ui_text.build_status(result)
        if result.saved:
            note, sidecar, path = self._write_sidecar(context["specs"][0], context["derived"][0],
                                                      context["plans"][0], result)
            text, ok = (text + " " + note, ok and sidecar is not None) if note else (text, ok)
            if sidecar is not None:
                self._loaded, self._loaded_path = sidecar, path
                self.record_hint.configure(text=os.path.basename(path))
        self._remember_output()
        self._set_status(text, ok)

    def _finish_pair(self, context: Dict[str, Any], result: swbuild.PairResult) -> None:
        _log(result.log_lines())
        text, ok = ui_text.pair_status(result)
        parts = [result.gear_a, result.gear_b]
        paths = context["paths"]
        assembly = result.assembly.saved if result.assembly is not None else ""
        spec_a, spec_b = context["specs"]
        centre = equations_literal(spec_a.module_mm() * (spec_a.teeth_count() + spec_b.teeth_count()) / 2.0)
        ratio = equations_literal(spec_b.teeth_count() / spec_a.teeth_count())
        for index, part in enumerate(parts):
            if part is None or not part.saved:
                continue
            note, sidecar, _ = self._write_sidecar(context["specs"][index], context["derived"][index],
                                                   context["plans"][index], part, partner=paths[1 - index],
                                                   assembly=assembly, centre_distance=centre, ratio=ratio)
            if note:
                text, ok = text + " " + note, False
        self._remember_output()
        self._set_status(text, ok)

    def _finish_update(self, context: Dict[str, Any], result: swbuild.UpdateResult) -> None:
        text, ok = ui_text.update_status(result)
        if result.ok and result.changed:
            variables = [[v.name, v.expression_for(result.trig)] for v in context["variables"]]
            updated = store.updated_sidecar(context["sidecar"], context["spec"].to_dict(),
                                            context["derived"].to_dict(), variables)
            try:
                store.save(context["record_path"], updated)
                self._loaded = updated
            except OSError as exc:
                text, ok = text + f" Its record could not be written: {exc}", False
        self._set_status(text, ok)

    def _write_sidecar(self, spec: GearSpec, derived: Any, plan: Any, result: swbuild.BuildResult,
                       **pair: str) -> Tuple[str, Optional[store.Sidecar], str]:
        """Write the record beside a saved part. Returns (a note if it went wrong, the record, its path)."""
        path = store.sidecar_path(result.saved)
        note = ""
        try:
            previous = store.load(path)
        except store.UnknownSchema as exc:
            return str(exc), None, path
        except store.StoreError as exc:
            previous, note = None, str(exc)
        kind = KINDS[spec.kind]
        sidecar = store.built_sidecar(
            result.saved, os.path.basename(result.saved), kind=spec.kind, recipe=plan.recipe,
            spec=spec.to_dict(), derived=derived.to_dict(),
            variables=[[v.name, v.expression_for(result.trig)] for v in kind.variables(spec, derived)],
            features=result.features, dimensions=sorted(result.dimensions.values()), manual_steps=result.manual,
            template=getattr(plan.ops[0], "template", ""), trig=result.trig,
            written_by=f"gear-generator {__version__}", previous=previous, **pair,
        )
        try:
            store.save(path, sidecar)
        except OSError as exc:
            return f"Its record could not be written beside it: {exc}", None, path
        self.recent.remember(path)
        return note, sidecar, path

    def _remember_output(self) -> None:
        self.recent.folder = self.out_folder.get().strip()
        self.recent.part_template = self.part_template.get().strip()
        self.recent.assembly_template = self.assembly_template.get().strip()
        self.recent.recipe = self.recipe.get()
        self.recent.mode = self.mode.get()
        store.save_recent(self.recent)

    # ------------------------------------------------------ the live link

    POLL_MS = 1000
    SLOW_EVERY = 5

    def _start_link(self) -> None:
        if not swcom.is_available():
            self.sw_status.set("pywin32 is not installed, so gears can be designed here but not built.")
            self._refresh_link_labels()
            return
        self._worker = swcom.Worker()
        self.after(200, self._tick)

    def _tick(self) -> None:
        """One turn of the poll. Never blocks, never raises into the loop.

        Each collector is guarded on its own, so one that throws every time
        cannot starve the others; the trouble is reported once per reason.
        """
        for collect in (self._collect_build, self._collect):
            try:
                collect()
            except Exception as exc:  # noqa: BLE001 - never kill the timer
                self._tick_trouble(exc)
        try:
            if self._worker is not None and self._pending is None and self._pending_build is None:
                self._quiet_ticks += 1
                if self._quiet_ticks >= self.SLOW_EVERY:
                    self._quiet_ticks = 0
                    self._ask("snapshot", _read_snapshot)
                else:
                    self._ask("key", _read_key)
        except Exception as exc:  # noqa: BLE001 - never kill the timer
            self._tick_trouble(exc)
        self.after(self.POLL_MS, self._tick)

    def _tick_trouble(self, exc: BaseException) -> None:
        reason = f"{type(exc).__name__}: {exc}"
        if reason == self._tick_failure:
            return
        self._tick_failure = reason
        try:
            self._set_status(f"The SolidWorks poll hit a problem — {reason}", ok=False)
        except Exception:  # noqa: BLE001
            pass

    def _ask(self, kind: str, work) -> None:
        if self._worker is None or self._pending is not None:
            return
        self._pending_kind = kind
        self._pending = self._worker.submit(work)

    def _collect(self) -> None:
        if self._pending is None:
            return
        answer = self._pending.poll()
        if answer is None:
            return
        value, error = answer
        kind, self._pending, self._pending_kind = self._pending_kind, None, ""
        if error is not None:
            self._snapshot = None
            self.sw_status.set(self._link_message(error))
            self._refresh_link_labels()
            return
        if kind == "key":
            if self._snapshot is None or value != self._snapshot.get("key"):
                self._ask("snapshot", _read_snapshot)
            return
        previous, self._snapshot = self._snapshot, value
        if previous != value:
            self.sw_status.set("")
            self._refresh_link_labels()
            self._derive_now()

    @staticmethod
    def _link_message(error: BaseException) -> str:
        if isinstance(error, swcom.NotRunning):
            return "SolidWorks is not running, so gears can be designed but not built."
        if isinstance(error, swcom.WrongVersion):
            return str(error)
        if isinstance(error, swcom.NotAvailable):
            return "pywin32 is not installed, so gears can be designed but not built."
        return f"SolidWorks could not be reached: {error}"

    def _refresh_link_labels(self) -> None:
        headline, state = ui_text.link_headline(swcom.is_available(), self._snapshot)
        self.sw_headline.set(headline)
        self.sw_dot.set_color({"ok": theme.OK, "bad": theme.ERROR}.get(state, theme.FAINT))


def equations_literal(value: float) -> str:
    return literal(round(value, 9))


def _log(lines: Sequence[str]) -> None:
    """The build log on the console, when there is one; a windowed exe has no stdout."""
    stream = sys.stdout
    if stream is None:
        return
    try:
        for line in lines:
            print(line, file=stream)
    except (OSError, ValueError, UnicodeError):
        pass


def _declare_dpi_aware() -> None:
    """Ask Windows for real pixels, before Tk opens a window."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _work_area(root: tk.Tk) -> Tuple[int, int, int]:
    """``(left, top, height)`` of the screen minus the taskbar, wherever the taskbar is."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        try:
            if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.bottom - rect.top
        except (AttributeError, OSError):
            pass
    return 0, 0, root.winfo_screenheight()


def _work_area_height(root: tk.Tk) -> int:
    """The screen minus the taskbar, which is what a window can actually use."""
    return _work_area(root)[2]


def _scale_to_dpi(root: tk.Tk) -> float:
    """Grow Tk's fonts to the screen we just admitted to. Returns the scale factor."""
    dpi = root.winfo_fpixels("1i")
    if dpi <= 0:
        return 1.0
    root.tk.call("tk", "scaling", dpi / 72.0)
    factor = dpi / 96.0
    if factor <= 1.01:
        return 1.0
    for name in tkfont.names(root):
        try:
            f = tkfont.nametofont(name, root)
        except tk.TclError:
            continue
        size = f.cget("size")
        if size < 0:
            f.configure(size=int(round(size * factor)))
    return factor


def main() -> None:
    _declare_dpi_aware()
    theme.register_bundled_fonts()
    root = tk.Tk()
    root.title(f"Gear Generator {__version__}")
    scale = _scale_to_dpi(root)
    root.configure(background=theme.WINDOW)
    root.minsize(int((STRIP_WIDTH + 24) * scale), int(480 * scale))
    app = GearApp(root, scale=scale)

    root.update_idletasks()
    app._size_page()
    root.update_idletasks()
    left, top, height = _work_area(root)
    room = height - int(round(40 * scale))
    # Placed at the top of the work area: left to Windows, a window sized to the
    # screen cascades down by its offset and its footer, Build with it, starts
    # below the bottom edge.
    root.geometry(f"{root.winfo_reqwidth()}x{min(root.winfo_reqheight(), room)}+{left}+{top}")
    root.mainloop()


if __name__ == "__main__":
    main()
