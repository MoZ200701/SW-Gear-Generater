"""The Workbook window (docs/PLAN-WORKBOOK.md §5, design/UI-DESIGN.md §9).

A second window beside the strip, linked to one ``.xlsx``. It reads the file,
shows every gear and every problem with the cell it is in, re-reads the file
each time it is saved in Excel and says what changed, and builds the gears as
parts through the strip's own SolidWorks worker.

Every word on it comes from :mod:`ui_text` and every decision from
:mod:`workbook` — this module only lays out widgets and wires handlers, as
:mod:`gui` does for the strip. Artboards ``WorkbookReady`` and
``WorkbookError`` in ``design/canvas`` are drawn from the same functions.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog
from typing import Any, Callable, Dict, List, Optional

from . import __version__, store, swbuild, swcom, theme, ui_text, widgets
from .gears.base import Diagnostic
from .theme import px
from . import preview
from .workbook import build as wb_build, checks as wb_checks, export as wb_export, fixes as wb_fixes
from .workbook import link as wb_link, model as wb_model, xlsx

WINDOW_WIDTH = 1080          # two columns: the workbook and its checks, and the end view and speeds (W3)
LEFT_WIDTH = 610
END_VIEW = (392, 300)        # the end view's canvas, px
# One colour per face height in the end view, so the stages read apart; the first is the ink.
PLANE_COLOURS = ("#3c3c3c", "#2f6db5", "#b35c00", "#6a3d9a", "#1a7f37")
POLL_MS = 1000
STATE_COLOURS = {ui_text.GEAR_STATE_BUILDS: theme.OK, ui_text.GEAR_STATE_SHARES: theme.OK,
                 ui_text.GEAR_STATE_LATER: theme.READOUT, ui_text.GEAR_STATE_ERROR: theme.ERROR}
TABLE_HEAD = ("Gear", "Shaft", "Kind", "Teeth", "Module", "Face", "Part", "")
TABLE_WIDTHS = (40, 44, 56, 44, 52, 40, 0, 128)     # 0: the column that takes the room left
PATH_CHARS = 52     # a path longer than this is shortened in the middle, so the window keeps its width


def open_in_excel(path: str) -> None:
    """The workbook in whatever opens .xlsx files here: Excel on Windows and the Mac."""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606 - the user's own file
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def clock_text() -> str:
    return time.strftime("%H:%M:%S")


class WorkbookWindow(tk.Toplevel):
    """One linked workbook. ``app`` is the strip (:class:`gui.GearApp`), for its worker, output folder and records."""

    def __init__(self, master: tk.Misc, app: Any, path: str, poll_ms: int = POLL_MS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        super().__init__(master)
        self.app = app
        self.fonts = theme.fonts()
        self.link = wb_link.Link(os.path.abspath(path), clock)
        self.poll_ms = poll_ms
        self.reading: Optional[wb_link.Reading] = None
        self.parts: wb_build.PartsPlan = wb_build.PartsPlan()
        self.diagnostics: List[Diagnostic] = []
        self.changes: List[str] = []
        self.changes_at = ""
        self.read_at = ""
        self.error = ""                # the last read's trouble ("" once a read is good); Build waits on it
        self.note: Optional[tuple] = None    # the last build's (sentence, ok), until the file changes
        self.chosen: List[wb_fixes.Fix] = []  # fixes taken but not yet written: Export writes them
        self.report: Optional[wb_checks.Report] = None
        self.effective: Optional[wb_model.GearboxSpec] = None    # the read, with the chosen fixes made
        self.recalc = False            # exported into a workbook with formulas: wait for Excel to recalculate
        self._pending: Optional[Any] = None
        self._build_context: Dict[str, Any] = {}
        self._after: Optional[str] = None

        self.title(f"Workbook — {os.path.basename(path)}")
        self.configure(bg=theme.WINDOW)
        self.minsize(px(WINDOW_WIDTH), px(420))
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.counts = tk.StringVar(value="")
        self.parts_readout = tk.StringVar(value="")
        self.checks_readout = tk.StringVar(value="")
        self.changes_readout = tk.StringVar(value="")
        self.read_line = tk.StringVar(value="")
        self.status = tk.StringVar(value="")
        self.view_readout = tk.StringVar(value="")
        self.speeds_readout = tk.StringVar(value="")
        self._last_digest = ""
        record = store.load_link_record(self.link.path)
        if record is not None and record.own_digest:
            # After an Export into a workbook with formulas, Build waits for Excel's save — across a reopen too.
            self.link.own_digest = record.own_digest
            self._pending_recalc = record.recalc
        else:
            self._pending_recalc = False
        self._layout()
        self.reread()
        self._after = self.after(self.poll_ms, self._tick)

    # ---------------------------------------------------------------- layout

    def _layout(self) -> None:
        f = self.fonts
        body = tk.Frame(self, bg=theme.WINDOW)
        body.pack(fill="both", expand=True, padx=px(12), pady=px(12))
        body.columnconfigure(0, weight=1)

        head = tk.Frame(body, bg=theme.WINDOW)
        head.grid(row=0, column=0, sticky="ew", pady=(0, px(8)))
        head.columnconfigure(0, weight=1)
        self.name_label = tk.Label(head, text=os.path.basename(self.link.path), bg=theme.WINDOW, fg=theme.INK,
                                   font=f.body_bold, anchor="w")
        self.name_label.grid(row=0, column=0, sticky="w")
        line = tk.Frame(head, bg=theme.WINDOW)
        line.grid(row=1, column=0, sticky="w")
        self.link_dot = widgets.Dot(line, theme.OK, bg=theme.WINDOW)
        self.link_dot.pack(side="left", padx=(0, px(6)))
        tk.Label(line, textvariable=self.read_line, bg=theme.WINDOW, fg=theme.READOUT,
                 font=f.readout).pack(side="left")
        buttons = tk.Frame(head, bg=theme.WINDOW)
        buttons.grid(row=0, column=1, rowspan=2, sticky="e")
        # Shown only when the file has gone: link the window to it again where it now is.
        self.locate_button = widgets.Button(buttons, "Locate…", command=self.locate, bg=theme.WINDOW)
        widgets.Button(buttons, "Open in Excel", command=self._open_in_excel, bg=theme.WINDOW).pack(
            side="left", padx=(0, px(8)))
        widgets.Button(buttons, "Re-read", command=self.reread, bg=theme.WINDOW).pack(side="left")

        head.grid_configure(columnspan=2)
        body.columnconfigure(0, weight=1, minsize=px(LEFT_WIDTH))
        body.columnconfigure(1, weight=0)
        right = tk.Frame(body, bg=theme.WINDOW)
        right.grid(row=1, column=1, rowspan=5, sticky="nsew", padx=(px(8), 0))
        view = widgets.Panel(right, "End view, from your origin", self.view_readout)
        view.grid(row=0, column=0, sticky="ew", pady=(0, px(8)))
        self.canvas = tk.Canvas(view.body, width=px(END_VIEW[0]), height=px(END_VIEW[1]), bg=theme.WHITE,
                                highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0)
        speeds = widgets.Panel(right, "Speeds", self.speeds_readout)
        speeds.grid(row=1, column=0, sticky="ew")
        self.speeds_body = speeds.body
        self.speeds_body.columnconfigure(0, weight=1)

        box = widgets.Panel(body, "Workbook", self.counts)
        box.grid(row=1, column=0, sticky="ew", pady=(0, px(8)))
        box.body.columnconfigure(1, weight=1)
        self.box_values: Dict[str, tk.Label] = {}
        for row, (key, text) in enumerate((("file", "File"), ("name", "Name"), ("folder", "Output folder"),
                                           ("type", "Worked out as"))):
            tk.Label(box.body, text=text, bg=theme.WHITE, fg=theme.LABEL, font=f.label, anchor="w",
                     width=0).grid(row=row, column=0, sticky="w", padx=(0, px(24)), pady=(0, px(2)))
            cell = tk.Frame(box.body, bg=theme.WHITE)
            cell.grid(row=row, column=1, sticky="w", pady=(0, px(2)))
            self.box_values[key] = tk.Label(cell, text="", bg=theme.WHITE, fg=theme.INK, font=f.mono_tiny,
                                            anchor="w")
            self.box_values[key].pack(side="left")
            if key == "folder":
                self.folder_hint = tk.Label(cell, text="", bg=theme.WHITE, fg=theme.MUTED, font=f.hint)
                self.folder_hint.pack(side="left", padx=(px(10), 0))

        gears = widgets.Panel(body, "Gears", self.parts_readout)
        gears.grid(row=2, column=0, sticky="ew", pady=(0, px(8)))
        self.table = gears.body
        for col, width in enumerate(TABLE_WIDTHS):
            self.table.columnconfigure(col, minsize=px(width), weight=1 if width == 0 else 0)

        checks = widgets.Panel(body, "Checks", self.checks_readout)
        checks.grid(row=3, column=0, sticky="ew", pady=(0, px(8)))
        self.checks_body = checks.body
        self.checks_body.columnconfigure(0, weight=1)

        since = widgets.Panel(body, "Since the last read", self.changes_readout)
        since.grid(row=4, column=0, sticky="ew", pady=(0, px(8)))
        self.changes_body = since.body
        self.changes_body.columnconfigure(0, weight=1)

        body.rowconfigure(5, weight=1)
        tk.Frame(body, bg=theme.WINDOW).grid(row=5, column=0, sticky="nsew")
        foot = tk.Frame(body, bg=theme.WINDOW)
        foot.grid(row=6, column=0, columnspan=2, sticky="ew")
        foot.columnconfigure(1, weight=1)
        self.status_dot = widgets.Dot(foot, theme.OK, size=8, bg=theme.WINDOW)
        self.status_dot.grid(row=0, column=0, sticky="n", pady=(px(5), 0), padx=(0, px(8)))
        self.status_label = tk.Label(foot, textvariable=self.status, bg=theme.WINDOW, fg=theme.OK, font=f.label,
                                     anchor="w", justify="left", wraplength=px(WINDOW_WIDTH - 420))
        self.status_label.grid(row=0, column=1, sticky="w")
        self.export_button = widgets.Button(foot, "Export", command=self.export, height=32, bg=theme.WINDOW)
        self.export_button.grid(row=0, column=2, sticky="e", padx=(px(12), 0))
        widgets.Button(foot, "Export as…", command=self.export_as, height=32, bg=theme.WINDOW).grid(
            row=0, column=3, sticky="e", padx=(px(8), 0))
        self.build_button = widgets.Button(foot, "Build parts", command=self.build_parts, primary=True, height=32,
                                           bg=theme.WINDOW)
        self.build_button.grid(row=0, column=4, sticky="e", padx=(px(8), 0))

    def _clear(self, frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _line(self, parent: tk.Misc, row: int, text: str, colour: str, mono: bool = False) -> None:
        f = self.fonts
        tk.Label(parent, text=text, bg=theme.WHITE, fg=colour, font=f.mono_tiny if mono else f.hint, anchor="w",
                 justify="left", wraplength=px(LEFT_WIDTH - 40)).grid(row=row, column=0, sticky="w")

    # ---------------------------------------------------------------- reading

    def reread(self) -> None:
        """Read the file now, whatever the poll thinks. A half-saved file is waited for by the poll instead."""
        try:
            self._show(self.link.read())
        except xlsx.NotReady as exc:
            self._show(wb_link.Reading(error=f"{exc} It will be read again in a moment."))
        except Exception as exc:  # noqa: BLE001 - a button must never raise out of Tk
            self._show(wb_link.Reading(error=f"The workbook could not be read — {type(exc).__name__}: {exc}"))

    def _tick(self) -> None:
        """The poll: the file, then a build in flight. Never raises into Tk's loop."""
        try:
            reading = self.link.poll()
            if reading is not None:
                self._show(reading)
            else:
                self._refresh_read_line()           # "open in Excel" follows Excel between saves
        except Exception as exc:  # noqa: BLE001 - never kill the timer
            self._show(wb_link.Reading(error=f"The workbook could not be read — {type(exc).__name__}: {exc}"))
        try:
            self._collect_build()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"The build could not be collected — {type(exc).__name__}: {exc}", ok=False)
        if self.winfo_exists():
            self._after = self.after(self.poll_ms, self._tick)

    def _refresh_read_line(self) -> None:
        if not self.read_at:
            return
        line = "linked · " + ui_text.workbook_read_line(self.read_at, self.link.open_in_excel)
        record = store.load_link_record(self.link.path)
        if record is not None and record.parts and self.reading is not None and self.reading.ok:
            line += (" · parts built from this version" if record.digest == self.reading.digest
                     else " · changed since its parts were built")
        self.read_line.set(line)

    def _show(self, reading: wb_link.Reading) -> None:
        self.read_at = clock_text()
        if not reading.ok:
            # Keep showing the last good read, but nothing is built from it while the file is in trouble.
            self.error = reading.error
            self.link_dot.set_color(theme.ERROR)
            gone = reading.error.startswith("The workbook is no longer at")
            if gone and not self.locate_button.winfo_ismapped():
                self.locate_button.pack(side="left", padx=(0, px(8)), before=self.locate_button.master.winfo_children()[1])
            self._refresh_read_line()
            self._refresh_state()
            return
        self.error = ""
        if self.locate_button.winfo_ismapped():
            self.locate_button.pack_forget()
        self.link_dot.set_color(theme.OK)
        self.reading = reading
        if reading.changes:
            self.changes, self.changes_at = reading.changes, self.read_at
        elif not self.changes_at:
            self.changes_at = self.read_at
        if reading.own and self._pending_recalc:
            self.recalc, self._pending_recalc = True, False      # reopened on the app's own unrecalculated write
        moved_on = bool(self._last_digest) and reading.digest != self._last_digest
        self._last_digest = reading.digest
        if not reading.own and moved_on:
            self.recalc = False               # an outside save: Excel has recalculated whatever it holds
            self.note = None                  # the file has moved on from the last build's or export's sentence
            if self.chosen:
                self._recheck_chosen(reading)
        elif not self.changes_at:
            self.changes_at = self.read_at
        self._plan()
        self._refresh_read_line()
        self._paint()

    def _plan(self) -> None:
        """The parts and the gearbox checks, from the last good read with the chosen fixes made, and the output
        folder as it is now (it can change on the strip)."""
        spec = self.reading.spec
        for fix in self.chosen:
            spec = wb_fixes.apply(spec, fix)
        self.effective = spec
        skip_rows = wb_build.rows_with_errors(self.reading.diagnostics)
        self.parts = wb_build.plan_parts(spec, self._folder(spec), self._template(spec), skip_rows=skip_rows)
        bad_rows = skip_rows | wb_build.rows_with_errors(self.parts.diagnostics)
        skip_gears = {g.id for g in spec.gears if g.row in bad_rows}
        self.report = wb_checks.check(spec, skip_gears)
        self.diagnostics = self.reading.diagnostics + self.parts.diagnostics + self.report.diagnostics

    def _folder(self, spec: wb_model.GearboxSpec) -> str:
        return spec.box.output_folder or self.app.out_folder.get().strip()

    def _template(self, spec: wb_model.GearboxSpec) -> str:
        return spec.box.part_template or self.app.part_template.get().strip()

    def _state(self):
        folder = self._folder(self.reading.spec) if self.reading is not None else ""
        return ui_text.workbook_state(self.parts, self.diagnostics, error=self.error, folder=folder,
                                      folder_exists=bool(folder) and os.path.isdir(folder),
                                      building=self._pending is not None, note=self.note,
                                      chosen=len(self.chosen), recalc=self.recalc)

    def _refresh_state(self) -> None:
        text, ok, enabled = self._state()
        self._set_status(text, ok)
        self.build_button.configure(state="normal" if enabled else "disabled")
        can_export = self.reading is not None and not self.error and self._pending is None
        self.export_button.configure(state="normal" if can_export else "disabled")

    def locate(self) -> None:
        """The file was moved or renamed: point the window at it again."""
        path = filedialog.askopenfilename(title="Where is the workbook now?", parent=self,
                                          filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")])
        if not path:
            return
        self.link = wb_link.Link(os.path.abspath(path), self.link.clock)
        self.app.recent.remember_workbook(path)
        store.save_recent(self.app.recent)
        self.title(f"Workbook — {os.path.basename(path)}")
        self.name_label.configure(text=os.path.basename(path))
        self.changes, self.changes_at = [], ""
        self.reread()

    # ---------------------------------------------------------------- painting

    def _paint(self) -> None:
        spec = self.effective or self.reading.spec
        f = self.fonts
        self.counts.set(ui_text.workbook_counts(spec))
        self.box_values["file"].configure(text=ui_text.short_path(self.link.path, PATH_CHARS))
        self.box_values["name"].configure(text=spec.box.name or "—")
        folder = self._folder(spec)
        self.box_values["folder"].configure(text=ui_text.short_path(folder, PATH_CHARS - 20) if folder else "—")
        self.folder_hint.configure(text="from the Box sheet" if spec.box.output_folder
                                   else ("the strip's Output" if folder else "set one on the Box sheet"))
        self.box_values["type"].configure(text=self.report.worked_out_as if self.report else "—", font=f.label)

        self.parts_readout.set(ui_text.workbook_parts_readout(self.parts))
        self._clear(self.table)
        for col, text in enumerate(TABLE_HEAD):
            tk.Label(self.table, text=text, bg=theme.WHITE, fg=theme.READOUT, font=f.tiny, anchor="w").grid(
                row=0, column=col, sticky="w", padx=(0, px(10)))
        rows = ui_text.workbook_gear_rows(spec, self.parts, self.diagnostics)
        for r, (gear, shaft, kind, teeth, module, face, part, state, what) in enumerate(rows, start=1):
            for col, text in enumerate((gear, shaft, kind, teeth, module, face, part or "—")):
                font = f.label if col == 2 else f.mono_tiny
                colour = theme.LABEL if col == 2 else theme.INK
                tk.Label(self.table, text=text, bg=theme.WHITE, fg=colour, font=font, anchor="w").grid(
                    row=r, column=col, sticky="w", padx=(0, px(10)), pady=px(1))
            cell = tk.Frame(self.table, bg=theme.WHITE)
            cell.grid(row=r, column=7, sticky="w")
            widgets.Dot(cell, STATE_COLOURS[state], bg=theme.WHITE).pack(side="left", padx=(0, px(6)))
            tk.Label(cell, text=what, bg=theme.WHITE, font=f.hint,
                     fg=theme.ERROR if state == ui_text.GEAR_STATE_ERROR else theme.MUTED).pack(side="left")
        if not rows:
            tk.Label(self.table, text="No gears yet: add rows to the Gears sheet and save.", bg=theme.WHITE,
                     fg=theme.MUTED, font=f.hint, anchor="w").grid(row=1, column=0, columnspan=8, sticky="w")

        self.checks_readout.set(ui_text.workbook_checks_readout(self.diagnostics))
        self._clear(self.checks_body)
        r = 0
        for fix in self.chosen:
            line = tk.Frame(self.checks_body, bg=theme.WHITE)
            line.grid(row=r, column=0, sticky="w", pady=(0, px(4)))
            tk.Label(line, text=f"Chosen, not yet written: {fix.title}", bg=theme.WHITE, fg=theme.INK,
                     font=f.hint).pack(side="left")
            widgets.Button(line, "Undo", command=lambda x=fix: self.unchoose(x), height=20).pack(
                side="left", padx=(px(8), 0))
            r += 1
        ordered = [d for d in self.diagnostics if d.is_error] + [d for d in self.diagnostics if not d.is_error]
        offered = self.report.fixes if self.report else {}
        for d in ordered:
            self._line(self.checks_body, r, d.message, theme.ERROR if d.is_error else theme.MUTED)
            r += 1
            for fix in offered.get(d.field, []) if d.is_error else []:
                choice = tk.Frame(self.checks_body, bg=theme.WHITE)
                choice.grid(row=r, column=0, sticky="w", padx=(px(14), 0), pady=(px(2), px(2)))
                widgets.Button(choice, fix.title, command=lambda x=fix: self.choose(x), height=22).grid(
                    row=0, column=0, sticky="w")
                tk.Label(choice, text=fix.detail, bg=theme.WHITE, fg=theme.MUTED, font=f.mono_tiny,
                         wraplength=px(LEFT_WIDTH - 70), justify="left", anchor="w").grid(
                    row=1, column=0, sticky="w", pady=(px(2), 0))
                r += 1
        if not ordered and not self.chosen:
            self._line(self.checks_body, 0, "No problems: every row reads, and every gear works out.", theme.MUTED)
        self._draw_end_view()
        self._paint_speeds()

        self.changes_readout.set(ui_text.workbook_changes_readout(self.changes, self.changes_at))
        self._clear(self.changes_body)
        for r, change in enumerate(self.changes):
            self._line(self.changes_body, r, change, theme.INK, mono=True)
        if not self.changes:
            self._line(self.changes_body, 0, "Nothing changed.", theme.MUTED)

        self._refresh_state()
        self._fit()

    def _draw_end_view(self) -> None:
        c = self.canvas
        c.delete("all")
        report = self.report
        if report is None or not report.layout.placed:
            reason = report.layout.later[0] if report is not None and report.layout.later else "Nothing to draw yet."
            c.create_text(px(12), px(12), text=reason, anchor="nw", fill=theme.MUTED, font=self.fonts.hint,
                          width=px(END_VIEW[0] - 24))
            self.view_readout.set("")
            return
        view = preview.layout_gearbox(report.layout.placed, report.theta, px(END_VIEW[0]), px(END_VIEW[1]), step=2)
        for gear, plane, points in view.outlines:
            colour = PLANE_COLOURS[plane % len(PLANE_COLOURS)]
            c.create_polygon(*[v for xy in points for v in xy], outline=colour, fill="", width=1)
        for gear, plane, x, y, r in view.rims:
            c.create_oval(x - r, y - r, x + r, y + r, outline=PLANE_COLOURS[plane % len(PLANE_COLOURS)])
        for name, x, y in view.shafts:
            c.create_line(x - px(5), y, x + px(5), y, fill=theme.INK)
            c.create_line(x, y - px(5), x, y + px(5), fill=theme.INK)
            c.create_text(x + px(6), y + px(6), text=name, anchor="nw", fill=theme.INK, font=self.fonts.mono_tiny)
        if view.origin is not None:
            ox, oy = view.origin
            c.create_line(ox, oy, ox + px(26), oy, fill=theme.ERROR, arrow="last")
            c.create_line(ox, oy, ox, oy - px(26), fill=theme.OK, arrow="last")
            c.create_oval(ox - px(2.5), oy - px(2.5), ox + px(2.5), oy + px(2.5), fill=theme.INK, outline="")
        self.view_readout.set(" · ".join(f"z {ui_text._n(z, 1)}" for z in view.planes)
                              + (" · origin" if view.origin else " · origin off view"))

    def _paint_speeds(self) -> None:
        self._clear(self.speeds_body)
        report = self.report
        if report is None:
            return
        motion = report.motion
        if motion.later:
            self._line(self.speeds_body, 0, motion.later, theme.MUTED)
            self.speeds_readout.set("")
            return
        r = 0
        for shaft in (self.effective or self.reading.spec).shafts:
            speed = motion.speeds.get(shaft.id)
            if speed is None:
                text = f"{shaft.id:<4}  not driven"
            else:
                torque = motion.torques.get(shaft.id)
                torque_text = f" · {torque:.2f} N·m" if torque is not None else ""
                text = f"{shaft.id:<4}  {abs(float(speed)):.1f} rpm {motion.turns(shaft.id)}{torque_text}"
            tk.Label(self.speeds_body, text=text, bg=theme.WHITE, fg=theme.INK, font=self.fonts.mono_tiny,
                     anchor="w").grid(row=r, column=0, sticky="w")
            r += 1
        self.speeds_readout.set("seen from +Z" if motion.speeds else "no input")

    def _recheck_chosen(self, reading: wb_link.Reading) -> None:
        """After an outside save, keep a chosen fix only if the new read still offers exactly that fix.

        Compared on the save itself, not on the change list: inserting or sorting rows changes no value, and
        a fix's own edits name items, not rows, so an unchanged fix is still right however the rows moved.
        """
        spec = reading.spec
        skip_rows = wb_build.rows_with_errors(reading.diagnostics)
        skip_gears = {g.id for g in spec.gears if g.row in skip_rows}
        offered = [f for fs in wb_checks.check(spec, skip_gears).fixes.values() for f in fs]
        kept = [f for f in self.chosen if f in offered]
        if len(kept) < len(self.chosen):
            self.note = ("The workbook changed, so the fix you chose no longer applies as it was and was set "
                         "aside; choose again from Checks.", False)
        self.chosen = kept

    def choose(self, fix: wb_fixes.Fix) -> None:
        """Take a fix: the window checks the gearbox with it at once; Export writes it."""
        if fix not in self.chosen:
            self.chosen.append(fix)
        self.note = None
        self._plan()
        self._paint()

    def unchoose(self, fix: wb_fixes.Fix) -> None:
        if fix in self.chosen:
            self.chosen.remove(fix)
        self._plan()
        self._paint()

    def export(self, out_path: str = "") -> None:
        """Write the chosen fixes and the Results sheet: into the workbook, or a copy at ``out_path``."""
        if self.reading is None or self.error or self._pending is not None:
            return
        try:
            done = wb_export.export(self.link.path, self.reading.spec, list(self.chosen), self.report,
                                    out_path=out_path, expected_digest=self.reading.digest)
        except (xlsx.XlsxError, OSError) as exc:
            self.note = (str(exc), False)
            if "changed since it was last read" in str(exc):
                self.reread()
            self._refresh_state()
            return
        what = ui_text._plural(len(done.written), 'cell') + (" and the Results sheet" if done.results else "")
        parts = [f"Exported {what}" + (f" to {os.path.basename(out_path)}" if out_path else "") + "."]
        if done.added_headers:
            parts.append("Added the column " + ", ".join(done.added_headers) + ".")
        if done.refused:
            parts.append("Not written — change them in Excel: "
                         + "; ".join(f"{cell} ({why})" for cell, why in done.refused)
                         + ". Results were not written, since the fix is only partly in the workbook.")
        if out_path:
            self.note = (" ".join(parts), not done.refused)
        else:
            self.link.own_digest = done.digest
            self.chosen = []
            self.recalc = done.has_formulas and bool(done.written)
            record = store.load_link_record(self.link.path) or store.LinkRecord(workbook=self.link.path)
            record.own_digest, record.recalc = done.digest, self.recalc
            try:
                store.save_link_record(record)
            except OSError:
                pass                          # only a convenience: this session still knows
            self.note = (" ".join(parts), not done.refused)
            self.reread()
            return
        self._refresh_state()

    def export_as(self) -> None:
        path = filedialog.asksaveasfilename(title="Export the workbook as", parent=self, defaultextension=".xlsx",
                                            initialfile=os.path.splitext(os.path.basename(self.link.path))[0]
                                            + " (fixed).xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if path:
            self.export(out_path=path)

    def _fit(self) -> None:
        """The designed width, always (paths are shortened so nothing pushes it wider), and tall enough for what
        it now holds — grown when a save brings more errors or changes, never shrunk below what the user chose."""
        self.update_idletasks()
        height = max(self.winfo_reqheight(), self.winfo_height() if self.winfo_ismapped() else 0)
        width = max(px(WINDOW_WIDTH), self.winfo_reqwidth())     # never narrower than what it holds
        # Kept on the screen: grown wider or taller, it moves left or up rather than off the edge.
        x = max(0, min(self.winfo_x(), self.winfo_screenwidth() - width))
        y = max(0, min(self.winfo_y(), self.winfo_screenheight() - height))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _set_status(self, text: str, ok: bool = True) -> None:
        colour = theme.OK if ok else theme.ERROR
        self.status.set(text)
        self.status_label.configure(fg=colour)
        self.status_dot.set_color(colour)

    # ---------------------------------------------------------------- building

    def build_parts(self) -> None:
        if self._pending is not None or self.reading is None:
            return
        # Planned again now: the strip's output folder or template may have changed since the last read.
        self._plan()
        text, ok, enabled = self._state()
        if not enabled:
            self._refresh_state()
            return
        worker = self.app._worker  # noqa: SLF001 - the strip's one SolidWorks thread, shared on purpose
        if worker is None:
            self._set_status("SolidWorks cannot be reached from here, so nothing was built. "
                             + swcom.unavailable_reason(), ok=False)
            return
        if self.app._pending_build is not None:  # noqa: SLF001
            self._set_status("The strip is building in SolidWorks; build the workbook when it has finished.",
                             ok=False)
            return
        existing = [j.path for j in self.parts.jobs if os.path.exists(j.path)]
        if existing:
            self._set_status(f"{existing[0]} already exists, and a build never overwrites a file. Give the gear a "
                             "Part name, or change the output folder.", ok=False)
            return
        jobs = list(self.parts.jobs)
        plans = [j.plan for j in jobs]
        self._build_context = {"jobs": jobs, "digest": self.reading.digest}
        self._pending = worker.submit(lambda session: swbuild.build_many(session, plans))
        self._refresh_state()

    def _collect_build(self) -> None:
        if self._pending is None:
            return
        answer = self._pending.poll()
        if answer is None:
            return
        value, error = answer
        self._pending, context = None, self._build_context
        if error is not None:
            message = str(error) if isinstance(error, swcom.SolidWorksError) else \
                f"The build hit a problem in SolidWorks — {type(error).__name__}: {error}"
            self.note = (message, False)
        else:
            self.note = self._finish(value, context)
        if self.reading is not None:
            self._plan()                       # what is on disk now decides what Build may do next
        self._refresh_read_line()
        self._refresh_state()

    def _finish(self, many: swbuild.ManyResult, context: Dict[str, Any]) -> tuple:
        from .gui import _log
        _log(many.log_lines())
        text, ok = ui_text.many_status(many)
        built_parts = []
        for job, result in zip(context["jobs"], many.built):
            if not (result.ok and result.saved):
                continue
            note, _, _ = self.app._write_sidecar(  # noqa: SLF001 - the strip's record writer, unchanged
                job.spec, job.derived, job.plan, result, workbook=self.link.path,
                workbook_gears=list(job.gear_ids))
            if note:
                text, ok = f"{text} {note}", False
            built_parts.append({"path": result.saved, "gears": list(job.gear_ids)})
        store.save_recent(self.app.recent)    # _write_sidecar remembered each record; keep them
        if built_parts:
            record = store.load_link_record(self.link.path) or store.LinkRecord(workbook=self.link.path)
            record.digest, record.parts, record.last_built = context.get("digest", ""), built_parts, store.now()
            record.written_by = f"gear-generator {__version__}"
            try:
                store.save_link_record(record)
            except OSError as exc:
                text, ok = f"{text} The workbook's record could not be written beside it: {exc}", False
        return text, ok

    # ---------------------------------------------------------------- the rest

    def _open_in_excel(self) -> None:
        try:
            open_in_excel(self.link.path)
        except OSError as exc:
            self._set_status(f"The workbook could not be opened: {exc}", ok=False)

    def close(self) -> None:
        if self._pending is not None:
            # The parts are being made: closing now would leave them without their records.
            self._set_status("A build is still running in SolidWorks; this window closes once it has finished.",
                             ok=False)
            return
        if self._after is not None:
            try:
                self.after_cancel(self._after)
            except tk.TclError:
                pass
        self.destroy()


# -------------------------------------------------------------------- opening one


def open_workbook(app: Any, path: str = "") -> Optional[WorkbookWindow]:
    """Ask for a workbook (unless given one), remember it, and open its window."""
    if not path:
        path = filedialog.askopenfilename(title="Import a gearbox workbook", parent=app,
                                          filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")])
    if not path:
        return None
    app.recent.remember_workbook(path)
    store.save_recent(app.recent)
    root = app.winfo_toplevel()
    for child in root.winfo_children():          # the same workbook twice is one window, brought forward
        if isinstance(child, WorkbookWindow) and store.same_path(child.link.path, os.path.abspath(path)):
            child.deiconify()
            child.lift()
            return child
    return WorkbookWindow(root, app, path)


def new_workbook(app: Any) -> Optional[WorkbookWindow]:
    """Write a blank workbook from the schema where the user says, open it in Excel, and link it."""
    path = filedialog.asksaveasfilename(title="Save a new gearbox workbook", parent=app, defaultextension=".xlsx",
                                        initialfile="Gearbox.xlsx", filetypes=[("Excel workbook", "*.xlsx")])
    if not path:
        return None
    name = os.path.splitext(os.path.basename(path))[0]
    try:
        if os.path.exists(path):
            raise xlsx.XlsxError(f"{path} already exists, and a new workbook never overwrites a file.")
        xlsx.write_new(path, wb_model.to_sheets(wb_model.template(name)))
    except (xlsx.XlsxError, OSError) as exc:
        app._set_status(str(exc), ok=False)  # noqa: SLF001
        return None
    window = open_workbook(app, path)
    try:
        open_in_excel(path)
    except OSError:
        pass
    return window
