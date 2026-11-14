"""The Workbook window (docs/PLAN-WORKBOOK.md §5, design/UI-DESIGN.md §9).

A second window beside the strip, linked to one ``.xlsx``. It reads the file
and checks the whole gearbox: every gear and every problem with the cell it is
in, the fixes offered for centres that are off, an end view from the origin
and each shaft's speed. It re-reads the file each time it is saved in Excel
and says what changed and what that did to the checks; Export writes the fixes
taken and the Results sheet back into the workbook (or a copy). Through the
strip's own SolidWorks worker it builds the gearbox — its parts, the layout
part and the static assembly (or, while rows a later phase builds hold the
layout back, the parts alone) — and Update SolidWorks carries a later edit of
the workbook into what was built, or offers to build it again as the next
revision (docs/PLAN-WORKBOOK.md §4.2–§4.5, phase W4).

Every decision comes from :mod:`workbook` — what is checked and what may be
built from :func:`workbook.assess.assess`, what a press would build from
:func:`workbook.gearbox.plan_gearbox` and what Update would change from
:func:`workbook.update.classify` — and every word from :mod:`ui_text`: the
footer is :func:`ui_text.workbook_footer` whole (its sentence and colour, the
build button's label and action, Update SolidWorks shown, enabled and
primary). This module lays out widgets and wires handlers, as :mod:`gui` does
for the strip. A few placeholders are still written here (*Nothing changed.*,
the chosen-fix line), and ``gen.py`` repeats the ones its artboards show.

**Threads.** On the Tk thread, on every re-plan (a read, Re-read, a fix
chosen or undone, a job collected, a press): ``store.read_link_record`` (it
never moves a file), ``store.clear_saved`` in memory, ``assess``, then
``plan_gearbox`` and, when something is on record, ``classify`` — pure but for
existence checks and reading ``.gear.json`` files, never SolidWorks. A press
submits exactly one job to the worker, ``swbuild.build_gearbox`` or
``swbuild.update_gearbox``, with its own ``swbuild.Progress``; the poll shows
its last step and, once it has answered, the Tk thread runs
``gearbox.finish_build`` / ``update.finish_update`` and writes the sidecars and
the record through ``store.open_link_record`` / ``store.save_link_record``.

**Closing while a job runs** does not stop it, nor drop what it saves: the
window stays (saying it will close), collects the answer, writes the sidecars
and the record, and then closes — unless the job's sentence is a fault, which
it stays open to show.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import __version__, store, swbuild, swcom, theme, ui_text, widgets
from .gears.base import Diagnostic
from .theme import px
from . import preview
from .workbook import assess as wb_assess, build as wb_build, checks as wb_checks, export as wb_export
from .workbook import fixes as wb_fixes, gearbox as wb_gearbox, link as wb_link, model as wb_model
from .workbook import update as wb_update, xlsx

WINDOW_WIDTH = 1080          # two columns: the workbook and its checks, and the end view and speeds (W3)
LEFT_WIDTH = 610
END_VIEW = (392, 300)        # the end view's canvas, px
# One colour per face height in the end view, so the stages read apart; the first is the ink.
PLANE_COLOURS = ("#3c3c3c", "#2f6db5", "#b35c00", "#6a3d9a", "#1a7f37")
POLL_MS = 1000
STATE_COLOURS = {ui_text.GEAR_STATE_BUILDS: theme.OK, ui_text.GEAR_STATE_SHARES: theme.OK,
                 ui_text.GEAR_STATE_LATER: theme.READOUT, ui_text.GEAR_STATE_ERROR: theme.ERROR,
                 ui_text.GEAR_STATE_BUILT: theme.OK, ui_text.GEAR_STATE_CHANGES: theme.ACCENT,
                 ui_text.GEAR_STATE_NEW_PART: theme.ERROR}
RED_STATES = (ui_text.GEAR_STATE_ERROR, ui_text.GEAR_STATE_NEW_PART)     # the "what" in red, as Checks' errors
TABLE_HEAD = ("Gear", "Shaft", "Kind", "Teeth", "Module", "Face", "Part", "")
TABLE_WIDTHS = (40, 44, 56, 44, 52, 40, 0, 128)     # 0: the column that takes the room left
PATH_CHARS = 52     # a path longer than this is shortened in the middle, so the window keeps its width
FOOTER_COLUMNS = {"build_button": 4, "update_button": 5}    # Export, Export as…, then these two


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


def ask_yes_no(parent: tk.Misc, title: str, question: str) -> bool:
    """A yes/no question whose answer defaults to No (tests replace this)."""
    return bool(messagebox.askyesno(title, question, parent=parent, default=messagebox.NO, icon=messagebox.QUESTION))


def _update_gate(a: wb_assess.Assessment, record: store.LinkRecord) -> str:
    """Whether ``classify`` may be asked (its docstring's precondition), as ``ui_text.workbook_footer`` gates
    Update SolidWorks: the whole-gearbox gate once a layout is on record, Build parts' gate for parts alone, and
    never the output folder, which Update writes nothing to. The footer still decides what the button does; this
    only keeps ``classify`` from being asked about a read the gate refuses."""
    loose = a if a.folder else dataclasses.replace(a, folder="-")
    return loose.lay_out_refusal() if record.gearbox is not None else loose.build_refusal()


JOB_BUILD, JOB_UPDATE = "build", "update"


@dataclasses.dataclass
class Job:
    """One press in SolidWorks: what was submitted, and what its finish needs on the Tk thread.

    ``plan`` (a build) or ``update`` (an update) is what was run; ``record``
    the planning read it was planned from; ``digest`` the read it was planned
    from; ``progress`` the worker's last step."""

    kind: str
    digest: str
    plan: Optional[wb_gearbox.GearboxPlan] = None
    update: Optional[wb_update.UpdatePlan] = None
    record: Optional[store.LinkRecord] = None
    progress: swbuild.Progress = dataclasses.field(default_factory=swbuild.Progress)

    @property
    def updating(self) -> bool:
        return self.kind == JOB_UPDATE


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
        self.consequence: Optional[wb_link.Consequence] = None    # what the changes did to the checks
        self._raw: Optional[wb_assess.Assessment] = None    # the last good read worked through, no fixes made
        self.state: Optional[wb_assess.Assessment] = None   # the last good read with the chosen fixes made
        self.read_at = ""
        self.error = ""                # the last read's trouble ("" once a read is good); Build waits on it
        self.note: Optional[tuple] = None    # (sentence, ok) of the last build, export or fix set aside
        self.chosen: List[wb_fixes.Fix] = []  # fixes taken but not yet written: Export writes them
        self.report: Optional[wb_checks.Report] = None
        self.effective: Optional[wb_model.GearboxSpec] = None    # the read, with the chosen fixes made
        self.recalc = False            # Export wrote cells into a workbook with formulas: wait for Excel's save
        self._results_waiting = False  # an Export left Results out for a formula cell: due after Excel's save
        self.results_due = False
        # What a press would do, planned on every re-plan (see the module's docstring), and the record it read.
        self.record: Optional[store.LinkRecord] = None
        self.record_problem = ""       # why the record beside the workbook cannot be read ("" when it can)
        self.plan: Optional[wb_gearbox.GearboxPlan] = None      # what the build button would run
        self.update: Optional[wb_update.UpdatePlan] = None      # what Update SolidWorks would do
        self.plan_trouble = ""         # planning itself raised: said, and both buttons held
        self._pending: Optional[Any] = None    # the worker's answer to come (gui.GearApp looks at this too)
        self._job: Optional[Job] = None
        self._close_when_done = False
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
        self._pending_recalc = False
        self._adopt_own_write()
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
        self.export_as_button = widgets.Button(foot, "Export as…", command=self.export_as, height=32,
                                               bg=theme.WINDOW)
        self.export_as_button.grid(row=0, column=3, sticky="e", padx=(px(8), 0))
        self._foot = foot
        # The build button's label, action and weight, and whether Update SolidWorks shows, are the footer's.
        self.build_button = self._footer_button(ui_text.BUILD_LABELS[ui_text.BUILD], self.press_build, True, 4)
        self.update_button = self._footer_button("Update SolidWorks", self.press_update, False, 5)
        self.update_button.grid_remove()

    def _footer_button(self, text: str, command: Callable[[], None], primary: bool, column: int) -> widgets.Button:
        button = widgets.Button(self._foot, text, command=command, primary=primary, height=32, bg=theme.WINDOW)
        button.grid(row=0, column=column, sticky="e", padx=(px(8), 0))
        return button

    def _shape_button(self, name: str, text: str, primary: bool, enabled: bool, shown: bool = True) -> None:
        """Give a footer button its label, weight and state. A button's weight is set when it is made, so one
        that changes weight (Build becomes Build again…, secondary, once an assembly is built) is made again."""
        button: widgets.Button = getattr(self, name)
        if button._primary != primary:  # noqa: SLF001 - its own flag; widgets.Button sets it once
            command, was_shown = button.command, bool(button.winfo_manager())
            button.destroy()
            button = self._footer_button(text, command, primary, FOOTER_COLUMNS[name])
            if not was_shown:
                button.grid_remove()
            setattr(self, name, button)
        if button.label.cget("text") != text:
            button.set_text(text)
        button.configure(state="normal" if enabled else "disabled")
        if shown and not button.winfo_manager():
            button.grid()
        elif not shown and button.winfo_manager():
            button.grid_remove()

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
        """The poll: the file, then a job in flight. Never raises into Tk's loop."""
        try:
            reading = self.link.poll()
            if reading is not None:
                self._show(reading)
            else:
                self._refresh_read_line()           # "open in Excel" follows Excel between saves
                if self._saved_since() and self.reading is not None and self.reading.ok:
                    self._plan()                    # a document Update left unsaved has been saved since
                    self._paint()
        except Exception as exc:  # noqa: BLE001 - never kill the timer
            self._show(wb_link.Reading(error=f"The workbook could not be read — {type(exc).__name__}: {exc}"))
        updating = self._job is not None and self._job.updating
        try:
            self._collect_job()
        except Exception as exc:  # noqa: BLE001
            self._set_status(ui_text.collect_failed(exc, updating), ok=False)
        if self._closed():
            return
        self._after = self.after(self.poll_ms, self._tick)

    def _closed(self) -> bool:
        try:
            return not self.winfo_exists()
        except tk.TclError:
            return True

    def _saved_since(self) -> bool:
        """Whether a document the record says Update left unsaved is newer on disk now (saved in SolidWorks):
        a cheap look at those files' times only, so the footer stops asking for the save without a re-read."""
        if self.record is None or not self.record.unsaved or self._pending is not None:
            return False
        return store.clear_saved(store.LinkRecord(unsaved=dict(self.record.unsaved)))

    def _refresh_read_line(self) -> None:
        if not self.read_at:
            return
        line = "linked · " + ui_text.workbook_read_line(self.read_at, self.link.open_in_excel)
        if self.reading is not None and self.reading.ok:
            line += ui_text.workbook_built_tag(self.record, self.reading.digest)
        self.read_line.set(line)

    def _adopt_own_write(self) -> None:
        """After an Export into a workbook with formulas, Build waits for Excel's save — across a reopen too: the
        record keeps the hash of the app's own write and whether it waits."""
        try:
            record = store.read_link_record(self.link.path)
        except store.StoreError:
            record = None                     # said by the footer once the window has read the file
        if record is not None and record.own_digest:
            self.link.own_digest = record.own_digest
            self._pending_recalc = record.recalc

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
            if self._results_waiting:
                self.results_due, self._results_waiting = True, False
            if self.chosen:
                self._recheck_chosen(reading)
        elif not self.changes_at:
            self.changes_at = self.read_at
        self._plan()
        # What the save did is read against the file as it was, not as a chosen fix would make it, as the
        # cell list is: a fix set aside by this save is said in the footer, not here.
        raw = self._assess(reading.spec, reading.diagnostics) if self.chosen else self.state
        if reading.changes:
            self.consequence = wb_link.consequence(self._raw, raw) if self._raw is not None else None
        self._raw = raw
        self._refresh_read_line()
        self._paint()

    def _plan(self) -> None:
        """The parts and the gearbox checks, from the last good read with the chosen fixes made, and the output
        folder as it is now (it can change on the strip); then what a press would build or update."""
        self.state = state = self._assess(self.reading.spec, self.reading.diagnostics, self.chosen,
                                          provisional=self.recalc)
        self.effective, self.parts, self.report, self.diagnostics = (state.spec, state.parts, state.report,
                                                                     state.diagnostics)
        self._plan_solidworks()

    def _plan_solidworks(self) -> None:
        """What the build button and Update SolidWorks would do now, on the Tk thread: the record read without
        moving anything, the documents Update left unsaved that have been saved since dropped (in memory), then
        ``plan_gearbox`` and, with something on record, ``classify``. Nothing here reaches SolidWorks, and only
        existence checks and ``.gear.json`` reads reach the disk."""
        newer = False
        try:
            record, problem = store.read_link_record(self.link.path), ""
        except store.UnknownSchema as exc:
            record, problem, newer = None, str(exc), True
        except store.StoreError as exc:
            record, problem = None, str(exc)      # broken: Build goes ahead, and its finish sets the file aside
        if record is not None:
            store.clear_saved(record)
        self.record, self.record_problem = record, problem
        self.plan = self.update = None
        self.plan_trouble = ""
        a = self.state
        if a is None or newer:
            return                                # a newer record holds both buttons: nothing to plan
        gearbox = record.gearbox if record is not None else None
        has_assembly = gearbox is not None and bool(gearbox.assembly)
        parts_only = not has_assembly and bool(a.parts.refused)      # Build parts: W2's batch, through reuse
        try:
            gate = a.build_refusal() if parts_only else a.lay_out_refusal()
            if not gate:
                self.plan = wb_gearbox.plan_gearbox(a, record, part_template=self._strip("part_template"),
                                                    assembly_template=self._strip("assembly_template"),
                                                    parts_only=parts_only)
            if record is not None and (record.parts or gearbox is not None) and not _update_gate(a, record):
                self.update = wb_update.classify(record, a)
        except Exception as exc:  # noqa: BLE001 - planning is pure and should never raise; if it does, say so
            self.plan = self.update = None
            self.plan_trouble = ui_text.planning_failed(exc)

    def _strip(self, name: str) -> str:
        """One of the strip's own settings (its Output panel's templates), as it is now."""
        var = getattr(self.app, name, None)
        return var.get().strip() if var is not None else ""

    def _assess(self, spec: wb_model.GearboxSpec, read_diagnostics: List[Diagnostic],
                chosen=(), provisional: bool = False) -> wb_assess.Assessment:
        """A read worked through by :func:`workbook.assess.assess`, the one pipeline the boards and W4 share.
        ``provisional`` while Excel has yet to recalculate the app's own Export (``recalc``): no fixes then."""
        return wb_assess.assess(spec, read_diagnostics, self._folder(spec), self._template(spec), chosen,
                                provisional=provisional)

    def _folder(self, spec: wb_model.GearboxSpec) -> str:
        return spec.box.output_folder or self.app.out_folder.get().strip()

    def _template(self, spec: wb_model.GearboxSpec) -> str:
        return spec.box.part_template or self.app.part_template.get().strip()

    def footer(self) -> ui_text.Footer:
        """The footer, decided whole by :func:`ui_text.workbook_footer`: nothing about it is decided here."""
        folder = self._folder(self.reading.spec) if self.reading is not None else ""
        job = self._job
        return ui_text.workbook_footer(
            self.state if self.reading is not None else None, record=self.record,
            record_problem=self.record_problem, plan=self.plan, update=self.update,
            error=self.error or self.plan_trouble, folder=folder,
            folder_exists=bool(folder) and os.path.isdir(folder),
            building=job is not None and not job.updating, updating=job is not None and job.updating,
            progress=job.progress.step if job is not None else None, note=self.note, results_due=self.results_due)

    def _refresh_state(self) -> None:
        footer = self.footer()
        text = footer.text
        if self._close_when_done and self._job is not None:
            text = f"{text} {ui_text.closes_when_done(self._job.updating)}"
        self._set_status(text, footer.ok)
        self._shape_button("build_button", footer.build_label, footer.build_primary, footer.build_enabled)
        self._shape_button("update_button", "Update SolidWorks", footer.update_primary, footer.update_enabled,
                           shown=footer.update_shown)
        # Not from a provisional read either: anything written from Excel's old formula values would be wrong.
        can_export = self.reading is not None and not self.error and self._pending is None and not self.recalc
        self.export_button.configure(state="normal" if can_export else "disabled")
        self.export_as_button.configure(state="normal" if can_export else "disabled")

    def locate(self) -> None:
        """The file was moved or renamed: point the window at it again, and carry the record of what was built
        to its new place (the old one is left where it is)."""
        path = filedialog.askopenfilename(title="Where is the workbook now?", parent=self,
                                          filetypes=[("Excel workbook", "*.xlsx"), ("All files", "*.*")])
        if not path:
            return
        old, new = self.link.path, os.path.abspath(path)
        carried = ""
        try:
            store.carry_link_record(old, new)
        except store.StoreError as exc:
            carried = ui_text.record_not_carried(str(exc))
        except OSError as exc:
            carried = ui_text.record_not_carried(f"it could not be written beside the new one: {exc}")
        self.link = wb_link.Link(new, self.link.clock)
        self._pending_recalc = False
        self._adopt_own_write()
        self.app.recent.remember_workbook(path)
        store.save_recent(self.app.recent)
        self.title(f"Workbook — {os.path.basename(path)}")
        self.name_label.configure(text=os.path.basename(path))
        self.changes, self.changes_at = [], ""
        self.consequence, self._raw = None, None
        self._results_waiting = self.results_due = False
        self._last_digest = ""
        self.note = (carried, False) if carried else None
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

        self.parts_readout.set(ui_text.workbook_parts_readout(self.parts, record=self.record))
        self._clear(self.table)
        for col, text in enumerate(TABLE_HEAD):
            tk.Label(self.table, text=text, bg=theme.WHITE, fg=theme.READOUT, font=f.tiny, anchor="w").grid(
                row=0, column=col, sticky="w", padx=(0, px(10)))
        rows = ui_text.workbook_gear_rows(spec, self.parts, self.diagnostics, record=self.record, update=self.update)
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
                     fg=theme.ERROR if state in RED_STATES else theme.MUTED).pack(side="left")
        if not rows:
            tk.Label(self.table, text="No gears yet: add rows to the Gears sheet and save.", bg=theme.WHITE,
                     fg=theme.MUTED, font=f.hint, anchor="w").grid(row=1, column=0, columnspan=8, sticky="w")

        self.checks_readout.set(ui_text.workbook_checks_readout(self.diagnostics, provisional=self.recalc))
        self._clear(self.checks_body)
        r = 0
        if self.recalc:
            self._line(self.checks_body, r, ui_text.CHECKS_PROVISIONAL, theme.INK)
            r += 1
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
        if not ordered and not self.chosen and not self.recalc:
            self._line(self.checks_body, 0, "No problems: every row reads, and every gear works out.", theme.MUTED)
        self._draw_end_view()
        self._paint_speeds()

        self.changes_readout.set(ui_text.workbook_changes_readout(self.changes, self.changes_at))
        self._clear(self.changes_body)
        covered = wb_link.covered_by_fix(self.consequence, self.report) if self.chosen else []
        for r, change in enumerate(ui_text.workbook_change_lines(self.changes, self.consequence, covered)):
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
        view = preview.layout_gearbox(report.layout.placed, report.theta, px(END_VIEW[0]), px(END_VIEW[1]), step=2,
                                      unit=px(100) / 100)
        for gear, plane, points in view.outlines:
            colour = PLANE_COLOURS[plane % len(PLANE_COLOURS)]
            c.create_polygon(*[v for xy in points for v in xy], outline=colour, fill="", width=1)
        for gear, plane, x, y, r in view.rims:
            c.create_oval(x - r, y - r, x + r, y + r, outline=PLANE_COLOURS[plane % len(PLANE_COLOURS)])
        for name, x, y in view.shafts:
            c.create_line(x - px(5), y, x + px(5), y, fill=theme.INK)
            c.create_line(x, y - px(5), x, y + px(5), fill=theme.INK)
        for name, x, y, anchor in view.labels:          # beside each cross, clear of the origin's arrows
            c.create_text(x, y, text=name, anchor=anchor, fill=theme.INK, font=self.fonts.mono_tiny)
        if view.origin is not None:
            ox, oy = view.origin
            c.create_line(ox, oy, ox + px(preview.ORIGIN_ARROW), oy, fill=theme.ERROR, arrow="last")
            c.create_line(ox, oy, ox, oy - px(preview.ORIGIN_ARROW), fill=theme.OK, arrow="last")
            c.create_oval(ox - px(2.5), oy - px(2.5), ox + px(2.5), oy + px(2.5), fill=theme.INK, outline="")
        self.view_readout.set(ui_text.end_view_readout(view) + ui_text.provisional_tag(self.recalc))

    def _paint_speeds(self) -> None:
        self._clear(self.speeds_body)
        report = self.report
        if report is None:
            return
        lines, readout = ui_text.workbook_speed_lines(self.effective or self.reading.spec, report.motion)
        colour = theme.MUTED if report.motion.later else theme.INK
        for r, text in enumerate(lines):
            if report.motion.later:
                self._line(self.speeds_body, r, text, colour)
            else:
                tk.Label(self.speeds_body, text=text, bg=theme.WHITE, fg=colour, font=self.fonts.mono_tiny,
                         anchor="w").grid(row=r, column=0, sticky="w")
        self.speeds_readout.set(readout + (ui_text.provisional_tag(self.recalc) if readout else ""))

    def _recheck_chosen(self, reading: wb_link.Reading) -> None:
        """After an outside save, keep a chosen fix only if the new read still offers exactly that fix.

        Compared on the save itself, not on the change list: inserting or sorting rows changes no value, and
        a fix's own edits name items, not rows, so an unchanged fix is still right however the rows moved.
        """
        offered = [f for fs in self._assess(reading.spec, reading.diagnostics).report.fixes.values() for f in fs]
        kept = [f for f in self.chosen if f in offered]
        if len(kept) < len(self.chosen):
            self.note = ("The workbook changed, so the fix you chose no longer applies as it was and was set "
                         "aside; choose again from Checks.", False)
        self.chosen = kept

    def choose(self, fix: wb_fixes.Fix) -> None:
        """Take a fix: the window checks the gearbox with it at once; Export writes it."""
        if self.recalc:
            return                            # none is offered from a provisional read; never take one from it
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
        if self.reading is None or self.error or self._pending is not None or self.recalc:
            # Export as… can be pressed before a read fails (its file dialog keeps the poll running): say so.
            why = (ui_text.export_busy(self._job is not None and self._job.updating) if self._pending is not None
                   else self.error or ("the workbook has not been read yet." if self.reading is None
                                       else ui_text.EXPORT_WAITS))
            self._set_status(f"Nothing was exported: {why}", ok=False)
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
        self.note = ui_text.export_note(done, os.path.basename(out_path) if out_path else "")
        if not out_path:
            # The app's own write, whether or not Results went in after the cells: never an outside save.
            self.link.own_digest = done.digest
            if done.written or not done.refused:
                self.chosen = []
            # else nothing reached the file (every cell the fix names holds a formula): the fix stays chosen,
            # with Undo, so nothing on screen moves but the sentence saying why
            self.recalc = done.has_formulas and bool(done.written)
            if done.results:
                self._results_waiting = self.results_due = False
            elif done.formulas and done.written:
                self._results_waiting, self.results_due = True, False
            self._record_own_write(done.digest)
            self.reread()
            return
        self._refresh_state()

    def _record_own_write(self, digest: str) -> None:
        """Keep the hash of the app's own write, and whether it waits for Excel, in the record beside the
        workbook, so a reopen knows them. Only a convenience — this session already knows — so a newer record
        is left alone without a word; one that cannot be read is set aside, said after the Export's sentence."""
        try:
            record = store.open_link_record(self.link.path)
        except store.UnknownSchema:
            return
        except store.StoreError as exc:
            record = None
            if self.note is not None:
                self.note = (f"{self.note[0]} {exc}", self.note[1])
        record = record or store.LinkRecord(workbook=self.link.path)
        record.own_digest, record.recalc = digest, self.recalc
        try:
            store.save_link_record(record)
        except (store.StoreError, OSError):
            pass

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

    # ---------------------------------------------------------------- building and updating

    def press_build(self) -> None:
        """The build button: Build, Build parts or Build again…, as the footer decided (``build_action``, never
        the label). Planned again first: the strip's output folder or templates may have changed, or a file."""
        if self._pending is not None or self.reading is None:
            return
        self._plan()
        footer = self.footer()
        if not footer.build_enabled:
            self._paint()
            return
        if footer.build_action == ui_text.BUILD_AGAIN:
            self._build_again()
        else:
            self._start_build()

    def press_update(self) -> None:
        """Update SolidWorks: carry the workbook into what was built, or — when the change needs a new part, a
        new layout or a file has gone — ask, then build the next revision instead."""
        if self._pending is not None or self.reading is None:
            return
        self._plan()
        footer = self.footer()
        if not footer.update_enabled or self.update is None:
            self._paint()
            return
        if self.update.needs_new_revision:
            self._build_again()
            return
        if not self._worker_free(updating=True):
            return
        update = self.update
        job = Job(JOB_UPDATE, self.reading.digest, update=update, record=self.record)
        kwargs = update.update_kwargs()
        self._submit(job, lambda session: swbuild.update_gearbox(session, **kwargs, progress=job.progress.say))

    def _build_again(self) -> None:
        """Ask (default No) whether to build the next revision, with what it makes, reuses and shares; then build
        it — unless the workbook changed while the question was open."""
        if not self._worker_free():
            return
        again, digest = self.plan, self.reading.digest
        question = ui_text.build_again_question(self.update, again)
        if not ask_yes_no(self, ui_text.BUILD_AGAIN_TITLE, question):
            self.note = (ui_text.NOTHING_CHANGED, True)
            self._refresh_state()
            return
        # The poll ran while the question was open: build only what was asked about.
        if self._pending is not None or self.reading is None or self.error:
            self._refresh_state()
            return
        self._plan()
        footer = self.footer()
        if (self.reading.digest != digest or self.plan is None or again is None
                or self.plan.name != again.name or not footer.build_enabled):
            self.note = (ui_text.ASKED_TOO_LATE, False)
            self._paint()
            return
        self._start_build()

    def _start_build(self) -> None:
        """One worker job for the whole plan: ``swbuild.build_gearbox`` (parts, layout part, assembly, interference;
        or the parts alone for Build parts), reusing what is built."""
        plan = self.plan
        if plan is None or plan.refusal:
            self._refresh_state()
            return
        if not self._worker_free():
            return
        job = Job(JOB_BUILD, self.reading.digest, plan=plan, record=self.record)
        kwargs = plan.build_kwargs()
        self._submit(job, lambda session: swbuild.build_gearbox(session, **kwargs, progress=job.progress.say))

    def _worker_free(self, updating: bool = False) -> bool:
        """The strip's one SolidWorks thread is there and not building for the strip; else say why."""
        worker = self.app._worker  # noqa: SLF001 - the strip's one SolidWorks thread, shared on purpose
        if worker is None:
            self._set_status(ui_text.job_unreachable(swcom.unavailable_reason(), updating), ok=False)
            return False
        if getattr(self.app, "_pending_build", None) is not None:
            self._set_status(ui_text.strip_busy(updating), ok=False)
            return False
        return True

    def _submit(self, job: Job, work: Callable[[Any], Any]) -> None:
        self.note = None
        self._job = job
        self._pending = self.app._worker.submit(work)  # noqa: SLF001
        self._refresh_state()

    def _collect_job(self) -> None:
        """The poll's half for a job: its progress while it runs, then its finish once it has answered."""
        if self._pending is None:
            return
        answer = self._pending.poll()
        if answer is None:
            self._refresh_state()                    # the worker's last step, in the footer
            return
        value, error = answer
        job, self._pending, self._job = self._job, None, None
        if error is not None:
            self.note = (ui_text.job_failed(error, job.updating), False)
        elif job.updating:
            self.note = self._finish_update(job, value)
        else:
            self.note = self._finish_build(job, value)
        if self._close_when_done:
            self._close_when_done = False
            if self.note[1]:
                self.close()
                return
        if self.reading is not None and self.reading.ok:
            self._plan()                             # what is on disk and on record now decides what is next
            self._refresh_read_line()
            self._paint()
        else:
            self._refresh_state()

    def _open_record(self) -> Tuple[Optional[store.LinkRecord], bool, List[str]]:
        """The record read just before writing it: (the record, or None for a fresh one; whether it may be
        written; what to say). A newer record is left alone; a broken one has been set aside by the read."""
        try:
            return store.open_link_record(self.link.path), True, []
        except store.UnknownSchema as exc:
            return None, False, [str(exc)]
        except store.StoreError as exc:
            return None, True, [str(exc)]

    def _write(self, finished: wb_gearbox.Finished, may_write: bool) -> List[str]:
        """The sidecars, then the record, as a finish asks; the faults, as sentences."""
        faults: List[str] = []
        for path, sidecar in finished.sidecars:
            try:
                store.save(path, sidecar)
                self.app.recent.remember(path)
            except OSError as exc:
                faults.append(ui_text.sidecar_unwritten(path, exc))
        if finished.sidecars:
            store.save_recent(self.app.recent)
        if finished.record is not None and may_write:
            try:
                store.save_link_record(finished.record)
            except store.StoreError as exc:
                faults.append(str(exc))
            except OSError as exc:
                faults.append(ui_text.record_unwritten(store.link_record_path(self.link.path), exc))
        return faults + list(finished.notes)

    def _finish_build(self, job: Job, result: swbuild.GearboxResult) -> Tuple[str, bool]:
        """What a build saved, on record: the parts' sidecars and the record beside the workbook (merged, the
        gearbox block as soon as the layout saved), then the build's sentence."""
        from .gui import _log
        _log(result.log_lines())
        text, ok = ui_text.gearbox_status(job.plan, result)
        record, may_write, notes = self._open_record()
        finished = wb_gearbox.finish_build(job.plan, result, record, workbook=self.link.path, digest=job.digest,
                                           written_by=f"gear-generator {__version__}")
        if record is None and finished.record is not None:
            # A fresh record: keep what this session knows of its own last Export.
            finished.record.own_digest, finished.record.recalc = self.link.own_digest, self.recalc
        faults = self._write(finished, may_write)
        if not may_write:
            faults, notes = notes + faults, []
        return " ".join([text] + notes + faults), ok and not faults

    def _finish_update(self, job: Job, result: swbuild.GearboxUpdate) -> Tuple[str, bool]:
        """What an update changed, on record: the changed parts' sidecars, the new frames and shafts, and every
        document it changed marked unsaved until it is saved in SolidWorks; then the update's sentence."""
        from .gui import _log
        _log(result.log_lines())
        record, may_write, notes = self._open_record()
        base = record if record is not None else job.record     # gone or set aside since the press: as planned
        finished = wb_update.finish_update(job.update, result, base, digest=job.digest)
        gearbox = job.record.gearbox if job.record is not None else None
        text, ok = ui_text.gearbox_update_status(job.update, result, finished.dragged,
                                                 meshes=gearbox.meshes if gearbox is not None else None)
        faults = self._write(finished, may_write)
        if not may_write:
            faults, notes = notes + faults, []
        return " ".join([text] + notes + faults), ok and not faults

    # ---------------------------------------------------------------- the rest

    def _open_in_excel(self) -> None:
        try:
            open_in_excel(self.link.path)
        except OSError as exc:
            self._set_status(f"The workbook could not be opened: {exc}", ok=False)

    def close(self) -> None:
        if self._pending is not None:
            # SolidWorks is saving files: closing now would leave them off the record. The window stays, says it
            # will close, and closes once the job's finish has written the sidecars and the record.
            self._close_when_done = True
            self._refresh_state()
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
