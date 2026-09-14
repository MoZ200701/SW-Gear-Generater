"""The only module that talks to SolidWorks.

Everything COM-shaped is confined here, behind plain data. ``pywin32`` is
imported inside a ``try`` so this module imports anywhere — the tests run on
Linux — and :func:`is_available` reports whether it is really usable.

Everything below about this connection was established by probe rather than
guessed, and each point is load-bearing:

* **Attach through the Running Object Table, never a ProgID.** A machine can
  carry SolidWorks 2024, 2025 and 2026 side by side. The unversioned
  ``SldWorks.Application`` ProgID resolves to whichever registered last, which
  is not necessarily the one on screen. Every live session instead publishes a
  moniker named ``SolidWorks_PID_<pid>``, and that name is the same across
  versions.
* **The table hands back an IUnknown.** ``dynamic.Dispatch`` cannot ask it for
  type information until it has been asked for its IDispatch face.
* **A zero-argument method is a property get.** Late binding turns
  ``RevisionNumber()`` into a plain string attribute and ``ActiveDoc`` into a
  document object, and *invoking* either raises "Member not found". Only
  members that take arguments are called. That is what :func:`call` encodes.
* **Some calls need their arguments typed by hand.** An absent COM object is a
  null of dispatch type, not a bare ``None``, and an out parameter is a
  by-reference integer. Both were found by probe on SolidWorks 2026, and both
  are silent until they are not.
"""

from __future__ import annotations

import math
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypeVar

from . import findings
from .gears.equations import DEGREES, RADIANS, equation_text, split_equation

try:  # pragma: no cover - exercised only on Windows with pywin32 present
    import pythoncom
    import win32com.client.dynamic as _dynamic
    from win32com.client import VARIANT

    _IMPORT_ERROR: Optional[str] = None
except ImportError as exc:  # pragma: no cover - the Linux and no-pywin32 path
    pythoncom = None  # type: ignore[assignment]
    _dynamic = None  # type: ignore[assignment]
    VARIANT = None  # type: ignore[assignment]
    _IMPORT_ERROR = str(exc)

T = TypeVar("T")

# SolidWorks majors advance by one a year: 32 is 2024, 33 is 2025, 34 is 2026.
MINIMUM_MAJOR = 34
HIGHEST_TESTED_MAJOR = 34
_YEAR_OFFSET = 1992

MONIKER_PREFIX = "solidworks_pid_"
_MONIKER = re.compile(r"^SolidWorks_PID_(\d+)$", re.IGNORECASE)

# The API holds every length in metres and every angle in radians, whatever the
# document is set to. Everything crossing this boundary is converted here, and
# only here.
MM_PER_METRE = 1000.0

# swDocumentTypes_e, as GetType reports it.
DOC_PART = 1
DOC_ASSEMBLY = 2


class SolidWorksError(Exception):
    """Something about the SolidWorks connection did not work."""


class NotAvailable(SolidWorksError):
    """pywin32 is not installed, or this is not Windows."""


class NotRunning(SolidWorksError):
    """No SolidWorks session is reachable."""


class WrongVersion(SolidWorksError):
    """Every reachable session is older than this app supports."""


def is_available() -> bool:
    return pythoncom is not None


def unavailable_reason() -> str:
    if is_available():
        return ""
    return _IMPORT_ERROR or "pywin32 is not installed, so SolidWorks cannot be reached."


# -- pure helpers, testable without SolidWorks ------------------------------


def parse_revision(text: str) -> Tuple[int, ...]:
    """``"34.0.0"`` -> ``(34, 0, 0)``."""
    parts = str(text).strip().split(".")
    try:
        numbers = tuple(int(p) for p in parts if p != "")
    except ValueError:
        raise SolidWorksError(f"Could not read a version out of {text!r}.") from None
    if not numbers:
        raise SolidWorksError(f"Could not read a version out of {text!r}.")
    return numbers


def release_year(major: int) -> int:
    """The marketing year for a major revision. Display only, never a decision.

    Holds for the 2024, 2025 and 2026 installs this was checked against. Being
    display-only, a broken convention costs one wrong word in a message and
    nothing else.
    """
    return major + _YEAR_OFFSET


def version_label(revision: Sequence[int]) -> str:
    return f"SolidWorks {release_year(revision[0])} (revision {'.'.join(str(n) for n in revision)})"


def is_solidworks_moniker(name: str) -> bool:
    return bool(_MONIKER.match(name or ""))


def pid_from_moniker(name: str) -> int:
    match = _MONIKER.match(name or "")
    if match is None:
        raise SolidWorksError(f"{name!r} is not a SolidWorks moniker.")
    return int(match.group(1))


@dataclass(frozen=True)
class Candidate:
    """One reachable session, described without holding a COM pointer."""

    moniker: str
    pid: int
    revision: Tuple[int, ...]
    has_active_doc: bool = False
    app: Any = field(default=None, compare=False, repr=False)


def meets_minimum(revision: Sequence[int]) -> bool:
    return bool(revision) and revision[0] >= MINIMUM_MAJOR


def is_newer_than_tested(revision: Sequence[int]) -> bool:
    return bool(revision) and revision[0] > HIGHEST_TESTED_MAJOR


def choose(candidates: Sequence[Candidate]) -> Candidate:
    """Pick the session to drive: the newest one that clears the floor.

    Never refuses a version for being too new. A 2027 install reports 35 and is
    used exactly as 2026 is; the realistic failure there is changed behaviour,
    not a missing member, and locking the user out would cost everything and buy
    nothing.
    """
    if not candidates:
        raise NotRunning(
            "No running SolidWorks was found. Open SolidWorks and try again."
        )

    usable = [c for c in candidates if meets_minimum(c.revision)]
    if not usable:
        found = ", ".join(sorted({version_label(c.revision) for c in candidates}))
        raise WrongVersion(
            f"Found {found}. This needs SolidWorks {release_year(MINIMUM_MAJOR)} "
            f"(revision {MINIMUM_MAJOR}) or newer."
        )

    # Newest first; a session with a document open wins a tie, because that is
    # almost certainly the window the user is looking at. PID last, only so the
    # choice is deterministic when nothing else separates them.
    return sorted(usable, key=lambda c: (c.revision, c.has_active_doc, -c.pid), reverse=True)[0]


# -- talking to COM ---------------------------------------------------------


def call(obj: Any, name: str, *args: Any) -> Any:
    """Reach a member of a late-bound COM object.

    Attribute access already invokes a zero-argument member, so ``Name``,
    ``RevisionNumber`` and ``GetNextFeature`` all come back as their results.
    Testing ``callable`` and invoking would be wrong: a member returning a
    document is itself callable, and calling it raises "Member not found".
    """
    member = getattr(obj, name)
    return member(*args) if args else member


def _dispatch(raw: Any) -> Any:
    return _dynamic.Dispatch(raw.QueryInterface(pythoncom.IID_IDispatch))


def _null_dispatch() -> Any:
    """An absent COM object, typed. A bare None is a type mismatch."""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _out_long() -> Any:
    """A by-reference integer for an out parameter SolidWorks insists on."""
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _type_name(obj: Any) -> str:
    """``GetTypeName2`` first, defaulting to ``?``: naming a failure must not fail."""
    try:
        return str(call(obj, "GetTypeName2"))
    except Exception:  # noqa: BLE001
        return "?"


def _put_indexed(obj: Any, name: str, index: int, value: Any) -> None:
    """An indexed property put, which late binding cannot spell as an assignment.

    ``eqm.Equation(i) = text`` in VBA; through pywin32's dynamic dispatch the
    name is only ever invoked as a get or a call, so the put goes through
    ``Invoke`` (probe equation_set, SolidWorks 2026).
    """
    oleobj = obj._oleobj_  # noqa: SLF001
    oleobj.Invoke(oleobj.GetIDsOfNames(name), 0, pythoncom.DISPATCH_PROPERTYPUT, False, index, value)


def find_candidates(out_unreachable: "Optional[List[Tuple[str, str]]]" = None) -> List[Candidate]:
    """Every reachable session, interrogated. Never launches SolidWorks.

    ``Dispatch("SldWorks.Application")`` would *start* a copy of SolidWorks, so
    the table is the only way in: nothing here creates anything.
    """
    if not is_available():
        raise NotAvailable(unavailable_reason())

    table = pythoncom.GetRunningObjectTable()
    context = pythoncom.CreateBindCtx(0)
    found: List[Candidate] = []
    unreachable: List[Tuple[str, str]] = [] if out_unreachable is None else out_unreachable

    for moniker in table.EnumRunning():
        try:
            name = moniker.GetDisplayName(context, None)
        except pythoncom.com_error:
            continue
        if not is_solidworks_moniker(name):
            continue

        # One unresponsive session — sitting on a modal dialog, say — must not
        # sink the whole scan. It is skipped, but never silently: a session
        # that vanishes without explanation is the hardest kind of bug to
        # place later.
        try:
            app = _dispatch(table.GetObject(moniker))
            revision = parse_revision(call(app, "RevisionNumber"))
            has_doc = call(app, "ActiveDoc") is not None
        except (pythoncom.com_error, SolidWorksError, AttributeError) as exc:
            unreachable.append((name, str(exc)))
            continue

        found.append(
            Candidate(
                moniker=name,
                pid=pid_from_moniker(name),
                revision=revision,
                has_active_doc=has_doc,
                app=app,
            )
        )
    return found


@dataclass(frozen=True)
class DocInfo:
    title: str
    path: str
    doc_type: int

    @property
    def is_part(self) -> bool:
        return self.doc_type == DOC_PART

    @property
    def is_assembly(self) -> bool:
        return self.doc_type == DOC_ASSEMBLY

    @property
    def is_saved(self) -> bool:
        return bool(self.path)


@dataclass(frozen=True)
class FeatureInfo:
    name: str
    type_name: str


class Session:
    """One connected SolidWorks. Only ever touched from the worker thread."""

    def __init__(self, app: Any, revision: Tuple[int, ...], pid: int) -> None:
        self._app = app
        self.revision = revision
        self.pid = pid

    @property
    def label(self) -> str:
        return version_label(self.revision)

    def active_document(self) -> Optional[DocInfo]:
        doc = call(self._app, "ActiveDoc")
        return None if doc is None else self._describe(doc)

    def documents(self) -> List[DocInfo]:
        out: List[DocInfo] = []
        doc = call(self._app, "GetFirstDocument")
        guard = 0
        while doc is not None and guard < 200:
            guard += 1
            out.append(self._describe(doc))
            doc = call(doc, "GetNext")
        return out

    @staticmethod
    def _describe(doc: Any) -> DocInfo:
        return DocInfo(
            title=call(doc, "GetTitle"),
            path=call(doc, "GetPathName"),
            doc_type=int(call(doc, "GetType")),
        )

    def _active(self) -> Any:
        doc = call(self._app, "ActiveDoc")
        if doc is None:
            raise SolidWorksError("No document is open in SolidWorks.")
        return doc

    def features(self) -> List[FeatureInfo]:
        """Every feature in the active document, subfeatures included."""
        return self._walk(call(self._active(), "FirstFeature"))

    def _walk(self, first: Any, depth: int = 0) -> List[FeatureInfo]:
        """Features from ``first`` on, each followed by its sub-features.

        Sub-features are stepped with ``GetNextSubFeature``: ``GetNextFeature``
        from a sketch under an extrusion carries on through the main tree, and
        on SolidWorks 2026 that listed every later feature again once per
        absorbed sketch.
        """
        out: List[FeatureInfo] = []
        feature = first
        step = "GetNextFeature" if depth == 0 else "GetNextSubFeature"
        guard = 0
        while feature is not None and guard < 5000:
            guard += 1
            try:
                type_name = str(call(feature, "GetTypeName2"))
            except Exception:  # noqa: BLE001 - a feature that will not describe itself
                type_name = "?"
            out.append(FeatureInfo(name=str(call(feature, "Name")), type_name=type_name))

            if depth < 4:  # a sketch sits under the feature that absorbed it
                try:
                    child = call(feature, "GetFirstSubFeature")
                except Exception:  # noqa: BLE001
                    child = None
                if child is not None:
                    out.extend(self._walk(child, depth + 1))

            feature = call(feature, step)
        return out

    def feature_names(self) -> List[str]:
        return [f.name for f in self.features()]

    def _feature(self, name: str) -> Any:
        doc = self._active()
        feature = call(doc, "FirstFeature")
        guard = 0
        while feature is not None and guard < 5000:
            guard += 1
            if str(call(feature, "Name")) == name:
                return feature
            feature = call(feature, "GetNextFeature")
        raise SolidWorksError(f"No feature called {name!r} is in {call(doc, 'GetTitle')}.")

    def rename_feature(self, current: str, new: str) -> str:
        """Rename, and report the name SolidWorks actually kept.

        SolidWorks quietly appends a digit on a collision, and a record holding
        a name that does not exist is the silent failure this design is built
        to avoid — so the name is read back rather than assumed.
        """
        feature = self._feature(current)
        feature.Name = new
        return str(call(feature, "Name"))

    def set_rebuild_suppressed(self, suppressed: bool) -> None:
        """Hold the rebuild off while a batch of changes goes in.

        Rebuilding per change shows real but transient errors partway through,
        and rebuilds once per change for nothing.
        """
        self._app.CommandInProgress = bool(suppressed)

    def rebuild(self) -> bool:
        """Rebuild the build's document (else the active one). Called once, after the last change."""
        return bool(call(self._doc(), "ForceRebuild3", False))


    # -- the build ---------------------------------------------------------
    #
    # Every member below was written from probe code that ran on SolidWorks
    # 2026 (revision 34.0.0); the probe that settled each point is named in
    # its docstring, and the constants live in :mod:`findings`. They take
    # millimetres and degrees and return plain data. COM pointers made during a
    # build live in a registry keyed by the plan's own ids, cleared at both
    # ends, because an operation is made on the Tk thread and no pointer may
    # cross the queue.

    def begin_build(self) -> None:
        """Start a build: an empty registry, and the dimension dialog turned off.

        The API help for ``AddDimension2`` says to turn off
        ``swInputDimValOnCreate``; left on, the dialog is modal and every COM
        call waits on it.
        """
        self._handles: Dict[str, Any] = {}
        self._open_sketch: Optional[str] = None
        self._build_doc: Any = None  # until new_part or new_assembly, the active document
        self._dim_dialog = bool(call(self._app, "GetUserPreferenceToggle", findings.INPUT_DIM_VAL_ON_CREATE))
        call(self._app, "SetUserPreferenceToggle", findings.INPUT_DIM_VAL_ON_CREATE, False)

    def end_build(self) -> None:
        """Forget the pointers; the document itself stays the build's until the next begin."""
        self._handles = {}
        self._open_sketch = None
        previous = getattr(self, "_dim_dialog", None)
        if previous is not None:
            call(self._app, "SetUserPreferenceToggle", findings.INPUT_DIM_VAL_ON_CREATE, previous)
            self._dim_dialog = None

    def document_path(self) -> str:
        return str(call(self._doc(), "GetPathName") or "")

    def _doc(self) -> Any:
        """The document the build is working in, not whatever is on screen now."""
        doc = getattr(self, "_build_doc", None)
        return doc if doc is not None else self._active()

    # -- documents

    def default_template(self, kind: str = "part") -> str:
        """``GetDocumentTemplate`` for a part or an assembly (probe: templates)."""
        doc_type = DOC_PART if kind == "part" else DOC_ASSEMBLY
        return str(call(self._app, "GetDocumentTemplate", doc_type, "", 0, 0.0, 0.0) or "")

    def _new_document(self, template: str, doc_type: int, noun: str) -> DocInfo:
        template = template or self.default_template("part" if doc_type == DOC_PART else "assembly")
        if not template or not os.path.isfile(template):
            raise SolidWorksError(f"There is no {noun} template at {template!r}.")
        doc = call(self._app, "NewDocument", template, 0, 0.0, 0.0)
        if doc is None:
            raise SolidWorksError(f"SolidWorks would not make a new {noun} from {template}.")
        info = self._describe(doc)
        if info.doc_type != doc_type:
            raise SolidWorksError(f"{template} made a document of type {info.doc_type}, not a {noun}.")
        self._build_doc = doc
        self._set_millimetres(doc, info.title)
        return info

    @staticmethod
    def _set_millimetres(doc: Any, title: str) -> None:
        """Equations are in document units, and the default templates here are inches.

        Probe document_units: a part from the default template read
        swUnitsLinear 3; setting swUnitSystem to MMGS made it 0, and a global of
        30 then drove a dimension to 0.030 m.
        """
        extension = call(doc, "Extension")
        if int(call(extension, "GetUserPreferenceInteger", findings.UNITS_LINEAR, 0)) == findings.LENGTH_MM:
            return
        call(extension, "SetUserPreferenceInteger", findings.UNIT_SYSTEM, 0, findings.UNIT_SYSTEM_MMGS)
        if int(call(extension, "GetUserPreferenceInteger", findings.UNITS_LINEAR, 0)) != findings.LENGTH_MM:
            raise SolidWorksError(f"{title} could not be set to millimetres, so its equations would be wrong.")

    def new_part(self, template: str = "") -> DocInfo:
        return self._new_document(template, DOC_PART, "part")

    def new_assembly(self, template: str = "") -> DocInfo:
        return self._new_document(template, DOC_ASSEMBLY, "assembly")

    def save_as(self, path: str) -> str:
        """Save the build's document to a new path, and report where it went.

        Probe save_as: ``IModelDocExtension.SaveAs3`` returned a plain True and
        silently overwrote an existing file, so an existing path is refused here
        before SolidWorks is asked.
        """
        if os.path.exists(path):
            raise SolidWorksError(f"{path} already exists, and a build never overwrites a file.")
        doc = self._doc()
        saved = call(call(doc, "Extension"), "SaveAs3", path, 0, findings.SAVE_AS_SILENT, _null_dispatch(),
                     _null_dispatch(), _out_long(), _out_long())
        if not saved:
            raise SolidWorksError(f"SolidWorks would not save {call(doc, 'GetTitle')} as {path}.")
        kept = str(call(doc, "GetPathName"))
        if kept.lower() != path.lower():
            raise SolidWorksError(f"SolidWorks saved to {kept!r}, not {path!r}.")
        return kept

    def close_document(self, title: str) -> None:
        """``CloseDoc`` closes without asking, modified or not (probe close_document)."""
        call(self._app, "CloseDoc", title)

    def activate(self, title: str) -> None:
        call(self._app, "ActivateDoc3", title, False, 0, _out_long())

    def document_title(self) -> str:
        return str(call(self._doc(), "GetTitle"))

    # -- equations

    def _equation_manager(self) -> Any:
        manager = call(self._doc(), "GetEquationMgr")
        if manager is None:
            raise SolidWorksError(f"{call(self._doc(), 'GetTitle')} has no equation manager.")
        return manager

    def _add_equation(self, text: str) -> int:
        """``Add2`` (probe equation_add: Add3 returned -1 on a one-configuration part)."""
        manager = self._equation_manager()
        index = int(call(manager, "Add2", -1, text, True))
        if index < 0:
            raise SolidWorksError(f"The Equation Manager refused {text}: Add2 returned -1.")
        read = str(call(manager, "Equation", index))
        if read.replace(" ", "") != text.replace(" ", ""):
            raise SolidWorksError(f"The Equation Manager holds {read!r} where {text!r} was added.")
        return index

    def add_global_variable(self, name: str, expression: str) -> int:
        return self._add_equation(equation_text(name, expression))

    def link_dimension(self, dimension: str, expression: str) -> int:
        """A dimension equation, which is refused until the dimension exists (probe dimension_link)."""
        return self._add_equation(equation_text(dimension, expression))

    def equations(self) -> List[Tuple[str, float]]:
        manager = self._equation_manager()
        return [(str(call(manager, "Equation", i)), float(call(manager, "Value", i)))
                for i in range(int(call(manager, "GetCount")))]

    def equation_values(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for text, value in self.equations():
            try:
                name, _ = split_equation(text)
            except ValueError:
                continue
            out[name] = value
        return out

    def set_global_variable(self, name: str, expression: str) -> None:
        """Change a global in place: an indexed put of ``Equation(i)`` (probe equation_set)."""
        manager = self._equation_manager()
        for index in range(int(call(manager, "GetCount"))):
            try:
                existing, _ = split_equation(str(call(manager, "Equation", index)))
            except ValueError:
                continue
            if existing == name:
                text = equation_text(name, expression)
                _put_indexed(manager, "Equation", index, text)
                read = str(call(manager, "Equation", index))
                if read.replace(" ", "") != text.replace(" ", ""):
                    raise SolidWorksError(f"\"{name}\" reads {read!r} after being set to {text!r}.")
                return
        raise SolidWorksError(f"There is no global variable \"{name}\" in {call(self._doc(), 'GetTitle')}.")

    def delete_equation(self, index: int) -> None:
        call(self._equation_manager(), "Delete", index)

    def detect_trig_units(self) -> str:
        """Measure the document's trig units: add sin ( 90 ), read it, delete it."""
        index = self._add_equation('"Gear Generator Trig Check"= sin ( 90 )')
        manager = self._equation_manager()
        try:
            value = float(call(manager, "Value", index))
        finally:
            call(manager, "Delete", index)
        if abs(value - 1.0) < 1e-9:
            return DEGREES
        if abs(value - math.sin(90.0)) < 1e-9:
            return RADIANS
        raise SolidWorksError(f"sin ( 90 ) came to {value!r}, which is neither degrees nor radians.")

    # -- selecting

    def _selection_context(self) -> str:
        """Where a refused selection happened, so the log says rather than guesses."""
        active = call(self._app, "ActiveDoc")
        title = "nothing" if active is None else str(call(active, "GetTitle"))
        return f"(in {call(self._doc(), 'GetTitle')}, with {title} active and {self._selected()} selected)"

    def _selected(self) -> int:
        return int(call(call(self._doc(), "SelectionManager"), "GetSelectedObjectCount2", -1) or 0)

    def _retry_select(self, attempt: Callable[[], Any], before: int) -> bool:
        """Select2 and Select4 now and then answered False with nothing selected
        just after a document was made (probes close_document, sketch_open_close);
        a moment later the same call worked. Judged by the count, retried briefly."""
        for _ in range(4):
            if attempt() and self._selected() > before:
                return True
            time.sleep(0.25)
        return False

    def _select_feature(self, feature: Any, append: bool = False, mark: int = 0) -> None:
        doc = self._doc()
        if not append:
            call(doc, "ClearSelection2", True)
        before = self._selected()
        if self._retry_select(lambda: call(feature, "Select2", append, mark), before):
            return
        kind = {"RefPlane": "PLANE", "RefAxis": "AXIS", "ProfileFeature": "SKETCH"}.get(
            _type_name(feature), "BODYFEATURE")
        name = str(call(feature, "Name"))
        if call(call(doc, "Extension"), "SelectByID2", name, kind, 0.0, 0.0, 0.0, append, mark,
                _null_dispatch(), 0) and self._selected() > before:
            return
        raise SolidWorksError(f"{name} ({_type_name(feature)}) could not be selected by Select2 or SelectByID2 "
                              f"{self._selection_context()}.")

    def _planes(self, doc: Any = None) -> List[Any]:
        doc = doc if doc is not None else self._doc()
        out = []
        feature = call(doc, "FirstFeature")
        while feature is not None:
            if _type_name(feature) == "RefPlane":
                out.append(feature)
            feature = call(feature, "GetNextFeature")
        return out

    def select_plane_by_order(self, index: int, append: bool = False, mark: int = 0) -> str:
        """The Nth reference plane in tree order, never by its English name."""
        planes = self._planes()
        if not 1 <= index <= len(planes):
            raise SolidWorksError(f"There is no reference plane {index}; the document has {len(planes)}.")
        self._select_feature(planes[index - 1], append, mark)
        return str(call(planes[index - 1], "Name"))

    def _by_name(self, name: str) -> Any:
        """A feature by name, looking one level under each feature too.

        A sketch is top-level until a feature is made from it; after that it
        sits under the extrusion or cut that absorbed it (SolidWorks 2026).
        """
        feature = call(self._doc(), "FirstFeature")
        while feature is not None:
            if str(call(feature, "Name")) == name:
                return feature
            child = call(feature, "GetFirstSubFeature")
            while child is not None:
                if str(call(child, "Name")) == name:
                    return child
                child = call(child, "GetNextSubFeature")
            feature = call(feature, "GetNextFeature")
        raise SolidWorksError(f"No feature called {name!r} is in {call(self._doc(), 'GetTitle')}.")

    def _top_names(self) -> List[str]:
        names = []
        feature = call(self._doc(), "FirstFeature")
        while feature is not None:
            names.append(str(call(feature, "Name")))
            feature = call(feature, "GetNextFeature")
        return names

    def _made_since(self, before: Sequence[str], type_name: str, what: str) -> Any:
        seen = set(before)
        made = []
        feature = call(self._doc(), "FirstFeature")
        while feature is not None:
            if str(call(feature, "Name")) not in seen and _type_name(feature) == type_name:
                made.append(feature)
            feature = call(feature, "GetNextFeature")
        if len(made) != 1:
            raise SolidWorksError(f"{what} added {len(made)} {type_name} features, so which one it is cannot be told.")
        return made[0]

    @staticmethod
    def _rename(feature: Any, name: str) -> str:
        feature.Name = name
        return str(call(feature, "Name"))

    # -- features

    def insert_axis(self, handle: str, name: str, planes: Tuple[int, int]) -> str:
        """Planes 2 and 3 selected, ``InsertAxis2(True)``, the new RefAxis found and named (probe axis)."""
        doc = self._doc()
        before = self._top_names()
        self.select_plane_by_order(planes[0])
        self.select_plane_by_order(planes[1], append=True)
        made = call(doc, "InsertAxis2", True)
        call(doc, "ClearSelection2", True)
        if not made:
            raise SolidWorksError(f"InsertAxis2 would not make {name} from planes {planes[0]} and {planes[1]}.")
        kept = self._rename(self._made_since(before, "RefAxis", "InsertAxis2"), name)
        self._handles[handle] = kept
        return kept

    def open_sketch(self, handle: str, plane: int) -> None:
        doc = self._doc()
        before = self._top_names()
        self.select_plane_by_order(plane)
        manager = call(doc, "SketchManager")
        manager.AddToDB = True
        manager.DisplayWhenAdded = False
        call(manager, "InsertSketch", True)
        sketch = call(manager, "ActiveSketch")
        call(doc, "ClearSelection2", True)
        if sketch is None:
            manager.AddToDB = False
            manager.DisplayWhenAdded = True
            raise SolidWorksError(f"InsertSketch would not open a sketch on plane {plane}.")
        self._handles[handle] = {"before": before, "sketch": sketch, "dimensions": []}
        self._open_sketch = handle

    def close_sketch(self, handle: str, name: str) -> str:
        doc = self._doc()
        manager = call(doc, "SketchManager")
        call(manager, "InsertSketch", True)
        manager.AddToDB = False
        manager.DisplayWhenAdded = True
        self._open_sketch = None
        record = self._handles[handle]
        kept = self._rename(self._made_since(record["before"], "ProfileFeature", "Closing the sketch"), name)
        record["name"] = kept
        return kept

    def sketch_status(self, name: str) -> int:
        """``GetConstrainedStatus``: 2 under, 3 fully, 4 over (probe constrained_status)."""
        return int(call(call(self._by_name(name), "GetSpecificFeature2"), "GetConstrainedStatus"))

    def _manager(self) -> Any:
        return call(self._doc(), "SketchManager")

    def _keep(self, handle: str, entity: Any, what: str, **meta: Any) -> None:
        if entity is None:
            raise SolidWorksError(f"SolidWorks would not draw {what} ({handle}).")
        self._handles[handle] = {"entity": entity, **meta}

    def sketch_circle(self, handle: str, centre: Tuple[float, float], radius: float, construction: bool = False) -> None:
        entity = call(self._manager(), "CreateCircleByRadius", centre[0] / MM_PER_METRE, centre[1] / MM_PER_METRE,
                      0.0, radius / MM_PER_METRE)
        self._keep(handle, entity, "a circle")
        if construction:
            entity.ConstructionGeometry = True

    def sketch_arc(self, handle: str, centre: Tuple[float, float], start: Tuple[float, float],
                   end: Tuple[float, float], direction: int = 1, construction: bool = False) -> None:
        """``CreateArc``: direction +1 is counter-clockwise from the start (probe sketch_entities)."""
        m = MM_PER_METRE
        entity = call(self._manager(), "CreateArc", centre[0] / m, centre[1] / m, 0.0, start[0] / m, start[1] / m,
                      0.0, end[0] / m, end[1] / m, 0.0, direction)
        self._keep(handle, entity, "an arc")
        if construction:
            entity.ConstructionGeometry = True

    def sketch_line(self, handle: str, start: Tuple[float, float], end: Tuple[float, float],
                    construction: bool = False) -> None:
        m = MM_PER_METRE
        entity = call(self._manager(), "CreateLine", start[0] / m, start[1] / m, 0.0, end[0] / m, end[1] / m, 0.0)
        self._keep(handle, entity, "a line")
        if construction:
            entity.ConstructionGeometry = True

    def sketch_point(self, handle: str, at: Tuple[float, float]) -> None:
        entity = call(self._manager(), "CreatePoint", at[0] / MM_PER_METRE, at[1] / MM_PER_METRE, 0.0)
        self._keep(handle, entity, "a point", point=True)

    def sketch_equation_curve(self, handle: str, x: str, y: str, t1: str, t2: str,
                              start: Tuple[float, float], end: Tuple[float, float]) -> None:
        """``CreateEquationSpline2`` with both ends locked, checked against where it should end.

        Probe curve_literal: the expressions are in document units with radian
        trig, and a broken expression makes nothing and raises nothing, which
        is why the ends are checked rather than the call trusted.
        """
        entity = call(self._manager(), "CreateEquationSpline2", x, y, "", t1, t2, False, 0.0, 0.0, 0.0, True, True)
        if entity is None:
            raise SolidWorksError(f"SolidWorks would not make the curve {handle} from x = {x}, y = {y}.")
        points = list(call(entity, "GetPoints2") or ())
        if not points:
            raise SolidWorksError(f"The curve {handle} has no points.")
        got = [(float(call(p, "X")) * MM_PER_METRE, float(call(p, "Y")) * MM_PER_METRE) for p in (points[0], points[-1])]
        for label, wanted, found in (("start", start, got[0]), ("end", end, got[1])):
            if math.hypot(wanted[0] - found[0], wanted[1] - found[1]) > 1e-3:
                raise SolidWorksError(
                    f"The curve {handle} {label}s at ({found[0]:.4f}, {found[1]:.4f}) mm, not at "
                    f"({wanted[0]:.4f}, {wanted[1]:.4f}) mm."
                )
        # Its ends as sketch points, captured now: a line drawn later from the same
        # spot has a point there too, and found by location afterwards the line's
        # point came back and the relation selected one point twice (2026).
        self._handles[handle] = {"entity": entity, "start": self._point_at(start), "end": self._point_at(end),
                                 "curve": True}

    def _origin_point(self) -> Any:
        feature = call(self._doc(), "FirstFeature")
        while feature is not None:
            if _type_name(feature) == "OriginProfileFeature":
                points = call(call(feature, "GetSpecificFeature2"), "GetSketchPoints2")
                if points:
                    return points[0]
            feature = call(feature, "GetNextFeature")
        raise SolidWorksError("The part's origin has no sketch point to relate to.")

    def _point_at(self, where: Tuple[float, float]) -> Any:
        """A curve's end as a sketch point, found by where it is (probe curve_relations)."""
        sketch = self._handles[self._open_sketch]["sketch"]
        best, distance = None, 1e-3
        for point in call(sketch, "GetSketchPoints2") or ():
            gap = math.hypot(float(call(point, "X")) * MM_PER_METRE - where[0],
                             float(call(point, "Y")) * MM_PER_METRE - where[1])
            if gap <= distance:
                best, distance = point, gap
        if best is None:
            raise SolidWorksError(f"No sketch point sits at ({where[0]:.4f}, {where[1]:.4f}) mm.")
        return best

    def _entity(self, ref: str) -> Any:
        if ref == "origin":
            return self._origin_point()
        handle, _, part = ref.partition(".")
        if handle not in self._handles or "entity" not in self._handles[handle]:
            raise SolidWorksError(f"Nothing called {handle!r} has been drawn in this build.")
        record = self._handles[handle]
        entity = record["entity"]
        if not part:
            return entity
        if record.get("curve") and part in ("start", "end"):
            return record[part]
        member = {"start": "GetStartPoint2", "end": "GetEndPoint2", "centre": "GetCenterPoint2"}.get(part)
        if member is None:
            raise SolidWorksError(f"{ref!r} names no part of an entity this build knows.")
        return call(entity, member)

    def _select_entities(self, refs: Sequence[str]) -> None:
        doc = self._doc()
        call(doc, "ClearSelection2", True)
        for position, ref in enumerate(refs):
            entity = self._entity(ref)
            before = self._selected()
            append = position > 0
            if self._retry_select(lambda: call(entity, "Select4", append, _null_dispatch()), before):
                continue
            try:
                x, y = float(call(entity, "X")), float(call(entity, "Y"))
            except Exception:  # noqa: BLE001 - a segment has no location to select by
                x = y = None
            if x is not None and call(call(doc, "Extension"), "SelectByID2", "", "SKETCHPOINT", x, y, 0.0, append, 0,
                                      _null_dispatch(), 0) and self._selected() > before:
                continue
            raise SolidWorksError(f"{ref} could not be selected by Select4 or SelectByID2 {self._selection_context()}.")

    def add_relation(self, kind: str, refs: Sequence[str]) -> str:
        """``SketchAddConstraints`` on the selection; constants from :data:`findings.RELATIONS`.

        Returns a note when there was nothing to add. An entity drawn starting
        exactly on another's end does not get a point of its own there: on
        SolidWorks 2026 a line started on a curve's end had that very point as
        its start, and so did a line started on a line's or an arc's end
        (probe curve_end_points). Coincident with itself already holds, and
        selecting the one point a second time adds nothing to the selection —
        the count stays at 1 — so the relation is skipped, not attempted.
        """
        constant = findings.RELATIONS.get(kind)
        if constant is None:
            raise SolidWorksError(f"There is no verified constant for a {kind} relation.")
        if kind == "coincident" and len(refs) == 2:
            a, b = self._entity(refs[0]), self._entity(refs[1])
            try:
                same = bool(a == b)
            except Exception:  # noqa: BLE001 - objects that will not compare are not the same one
                same = False
            if same:
                return "already one point"
        self._select_entities(refs)
        call(self._doc(), "SketchAddConstraints", constant)
        call(self._doc(), "ClearSelection2", True)
        return ""

    def dimension(self, name: str, refs: Sequence[str], at: Tuple[float, float]) -> str:
        """``AddDimension2`` at a point in metres, then named and read back (probe dimensions)."""
        doc = self._doc()
        self._select_entities(refs)
        display = call(doc, "AddDimension2", at[0] / MM_PER_METRE, at[1] / MM_PER_METRE, 0.0)
        call(doc, "ClearSelection2", True)
        if display is None:
            raise SolidWorksError(f"AddDimension2 would not dimension {' and '.join(refs)} as {name}.")
        dimension = call(display, "GetDimension2", 0)
        dimension.Name = name
        kept = str(call(dimension, "Name"))
        if self._open_sketch:
            self._handles[self._open_sketch]["dimensions"].append(kept)
        return kept

    def feature_dimensions(self, feature_name: str) -> List[Tuple[str, float]]:
        """Every dimension on a feature, as ``(name, SystemValue)``."""
        return [(str(call(d, "Name")), float(call(d, "SystemValue"))) for d in self._dimensions(self._by_name(feature_name))]

    @staticmethod
    def _dimensions(feature: Any) -> List[Any]:
        out = []
        display = call(feature, "GetFirstDisplayDimension")
        guard = 0
        while display is not None and guard < 500:
            guard += 1
            out.append(call(display, "GetDimension2", 0))
            display = call(feature, "GetNextDisplayDimension", display)
        return out

    def _name_dimension_by_value(self, feature: Any, value: float, name: str, what: str,
                                 ignore: Sequence[str] = ()) -> str:
        """Find the one dimension with this value — never assume D1 — and name it."""
        matches = [d for d in self._dimensions(feature)
                   if abs(float(call(d, "SystemValue")) - value) < 1e-9 and str(call(d, "Name")) not in ignore]
        if len(matches) != 1:
            raise SolidWorksError(f"{len(matches)} dimensions of {call(feature, 'Name')} have the {what}'s value, "
                                  "so which one is the " + what + " cannot be told.")
        matches[0].Name = name
        return str(call(matches[0], "Name"))

    def _sketch_feature(self, handle: str) -> Any:
        record = self._handles.get(handle) or {}
        if "name" not in record:
            raise SolidWorksError(f"The sketch {handle!r} has not been closed and named.")
        return self._by_name(record["name"])

    def extrude(self, handle: str, sketch: str, name: str, depth: float, depth_dim: str) -> Tuple[str, str]:
        """A blind boss (probe extrude: volume pi r^2 w, depth dimension D1)."""
        doc = self._doc()
        self._select_feature(self._sketch_feature(sketch))
        m = depth / MM_PER_METRE
        feature = call(call(doc, "FeatureManager"), "FeatureExtrusion3", True, False, False, 0, 0, m, 0.0, False,
                       False, False, False, 0.0, 0.0, False, False, False, False, True, True, True, 0, 0.0, False)
        call(doc, "ClearSelection2", True)
        if feature is None:
            raise SolidWorksError(f"FeatureExtrusion3 would not extrude {sketch} into {name}.")
        kept = self._rename(feature, name)
        dim = self._name_dimension_by_value(feature, m, depth_dim, "depth",
                                            ignore=self._handles[sketch].get("dimensions", ()))
        self._handles[handle] = {"feature": kept}
        return kept, dim

    def cut_extrude(self, handle: str, sketch: str, name: str) -> str:
        """Through all, both directions (probe cut: the default direction removed nothing)."""
        doc = self._doc()
        self._select_feature(self._sketch_feature(sketch))
        end = findings.CUT_END_CONDITION
        feature = call(call(doc, "FeatureManager"), "FeatureCut4", False, False, False, end, end, 0.01, 0.01, False,
                       False, False, False, 0.0, 0.0, False, False, False, False, False, True, True, True, True,
                       False, 0, 0.0, False, False)
        call(doc, "ClearSelection2", True)
        if feature is None:
            raise SolidWorksError(f"FeatureCut4 would not cut {sketch} through the part as {name}.")
        kept = self._rename(feature, name)
        self._handles[handle] = {"feature": kept}
        return kept

    def circular_pattern(self, handle: str, name: str, axis: str, feature: str, count: int,
                         count_dim: str) -> Tuple[str, str]:
        """Axis at mark 1, the feature at mark 4, 360 degrees equal (probe pattern)."""
        doc = self._doc()
        axis_name = self._handles.get(axis)
        seed = (self._handles.get(feature) or {}).get("feature")
        if not isinstance(axis_name, str) or not seed:
            raise SolidWorksError(f"The pattern {name} needs the axis {axis} and the feature {feature} first.")
        self._select_feature(self._by_name(axis_name), mark=1)
        self._select_feature(self._by_name(seed), append=True, mark=4)
        made = call(call(doc, "FeatureManager"), "FeatureCircularPattern5", count, 2 * math.pi, False, "NULL", False,
                    True, False, False, False, False, 1, 0.0, "NULL", False)
        call(doc, "ClearSelection2", True)
        if made is None:
            raise SolidWorksError(f"FeatureCircularPattern5 would not pattern {seed} {count} times about {axis_name}.")
        kept = self._rename(made, name)
        dim = self._name_dimension_by_value(made, float(count), count_dim, "count")
        self._handles[handle] = {"feature": kept}
        return kept, dim

    def volume_mm3(self) -> float:
        props = call(call(self._doc(), "Extension"), "CreateMassProperty")
        return float(call(props, "Volume")) * 1e9

    def features_of_build(self) -> List[FeatureInfo]:
        feature = call(self._doc(), "FirstFeature")
        out = []
        while feature is not None:
            out.append(FeatureInfo(str(call(feature, "Name")), _type_name(feature)))
            feature = call(feature, "GetNextFeature")
        return out

    # -- assemblies

    def add_component(self, handle: str, path: str, at: Tuple[float, float, float]) -> str:
        """``AddComponent5``: the part must already be open (API help); returns ``Name2``."""
        m = MM_PER_METRE
        component = call(self._doc(), "AddComponent5", path, 0, "", False, "", at[0] / m, at[1] / m, at[2] / m)
        if component is None:
            raise SolidWorksError(f"AddComponent5 would not insert {path}.")
        self._handles[handle] = {"component": component, "path": path}
        return str(call(component, "Name2"))

    def fix_component(self, handle: str) -> None:
        """Fix a component, and read back that it is fixed.

        The first component inserted is already fixed (probe
        assembly_components_and_mates). ``FixComponent`` takes no arguments,
        so it is invoked explicitly: :func:`call` would only fetch it, which is
        how an earlier version never ran it at all.
        """
        component = self._handles[handle]["component"]
        if bool(call(component, "IsFixed")):
            return
        doc = self._doc()
        call(doc, "ClearSelection2", True)
        if not call(component, "Select4", False, _null_dispatch(), False):
            raise SolidWorksError(f"{call(component, 'Name2')} could not be selected to fix it.")
        doc.FixComponent()
        call(doc, "ClearSelection2", True)
        if not bool(call(component, "IsFixed")):
            raise SolidWorksError(f"{call(component, 'Name2')} is still floating after FixComponent.")

    def _component_ref(self, ref: str, append: bool) -> None:
        """``gear1:plane2`` or ``gear2:Gear Axis``, selected at mark 1 for a mate."""
        handle, _, target = ref.partition(":")
        component = self._handles[handle]["component"]
        if target.startswith("plane") and target[5:].isdigit():
            planes = self._planes(call(component, "GetModelDoc2"))
            name, kind = str(call(planes[int(target[5:]) - 1], "Name")), "PLANE"
        else:
            name, kind = target, "AXIS"
        doc = self._doc()
        if not append:
            call(doc, "ClearSelection2", True)
        before = self._selected()
        feature = call(component, "FeatureByName", name)
        if feature is not None and self._retry_select(lambda: call(feature, "Select2", append, 1), before):
            return
        asm = os.path.splitext(str(call(doc, "GetTitle")))[0]
        full = f"{name}@{call(component, 'Name2')}@{asm}"
        if call(call(doc, "Extension"), "SelectByID2", full, kind, 0.0, 0.0, 0.0, append, 1, _null_dispatch(), 0) \
                and self._selected() > before:
            return
        raise SolidWorksError(f"{full} could not be selected for a mate.")

    def _mate_names(self) -> List[str]:
        names = []
        feature = call(self._doc(), "FirstFeature")
        while feature is not None:
            if _type_name(feature) == "MateGroup":
                child = call(feature, "GetFirstSubFeature")
                while child is not None:
                    names.append(str(call(child, "Name")))
                    child = call(child, "GetNextSubFeature")
            feature = call(feature, "GetNextFeature")
        return names

    def _mate_feature(self, name: str) -> Any:
        feature = call(self._doc(), "FirstFeature")
        while feature is not None:
            if _type_name(feature) == "MateGroup":
                child = call(feature, "GetFirstSubFeature")
                while child is not None:
                    if str(call(child, "Name")) == name:
                        return child
                    child = call(child, "GetNextSubFeature")
            feature = call(feature, "GetNextFeature")
        raise SolidWorksError(f"No mate called {name!r}.")

    def add_mate(self, handle: str, kind: str, a: str, b: str, value: float = 0.0, name: str = "") -> Tuple[str, str]:
        """``AddMate5`` on two component references; returns ``(mate name, its dimension)``.

        Probe assembly_components_and_mates: coincident, distance and angle
        mates were made this way and the component moved to where they said.
        """
        types = {"coincident": findings.MATE_COINCIDENT, "distance": findings.MATE_DISTANCE,
                 "angle": findings.MATE_ANGLE}
        if kind not in types:
            raise SolidWorksError(f"There is no verified mate type for {kind!r}.")
        before = self._mate_names()
        self._component_ref(a, append=False)
        self._component_ref(b, append=True)
        distance = value / MM_PER_METRE if kind == "distance" else 0.0
        angle = math.radians(value) if kind == "angle" else 0.0
        mate = call(self._doc(), "AddMate5", types[kind], findings.MATE_ALIGN_CLOSEST, False, distance, distance,
                    distance, 1, 1, angle, angle, angle, False, False, 0, _out_long())
        call(self._doc(), "ClearSelection2", True)
        made = [n for n in self._mate_names() if n not in before]
        if mate is None or len(made) != 1:
            raise SolidWorksError(f"AddMate5 would not make a {kind} mate between {a} and {b}.")
        feature = self._mate_feature(made[0])
        kept = self._rename(feature, name) if name else made[0]
        dim = ""
        if kind in ("distance", "angle"):
            wanted = distance if kind == "distance" else angle
            matches = [d for d in self._dimensions(feature) if abs(float(call(d, "SystemValue")) - wanted) < 1e-9]
            dim = str(call(matches[0], "Name")) if len(matches) == 1 else ""
        self._handles[handle] = {"mate": kept}
        return kept, dim

    def component_translation(self, handle: str) -> Tuple[float, float, float]:
        data = call(call(self._handles[handle]["component"], "Transform2"), "ArrayData")
        return (float(data[9]) * MM_PER_METRE, float(data[10]) * MM_PER_METRE, float(data[11]) * MM_PER_METRE)


def connect() -> Session:
    """Attach to the newest reachable SolidWorks that this app supports."""
    chosen = choose(find_candidates())
    return Session(chosen.app, chosen.revision, chosen.pid)


# -- the apartment ----------------------------------------------------------


class Worker:
    """One dedicated apartment-threaded thread, and everything COM on it.

    A COM object belongs to the apartment that made it. Keeping every call on
    a single thread means no interface ever has to be marshalled — and nothing
    COM-shaped is allowed back across the queue, only plain data. It also keeps
    a slow call off the interface: a modal dialog open in SolidWorks blocks a
    call for as long as it stays open, and there is no safe way to cancel one.
    """

    def __init__(self, connect_fn: Callable[[], Any] = connect) -> None:
        self._connect = connect_fn
        self._jobs: "queue.Queue[Optional[Tuple[Callable[[Any], Any], queue.Queue]]]" = queue.Queue()
        self._session: Any = None
        self._busy = threading.Event()
        self._thread = threading.Thread(target=self._pump, name="solidworks", daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        if pythoncom is not None:  # pragma: no branch
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        try:
            while True:
                job = self._jobs.get()
                if job is None:
                    return
                work, outbox = job
                self._busy.set()
                try:
                    if self._session is None:
                        self._session = self._connect()
                    outbox.put((work(self._session), None))
                except BaseException as exc:  # noqa: BLE001 - reported, never swallowed
                    self._session = None
                    outbox.put((None, exc))
                finally:
                    self._busy.clear()
        finally:
            self._session = None
            if pythoncom is not None:  # pragma: no branch
                pythoncom.CoUninitialize()

    def busy(self) -> bool:
        return self._busy.is_set() or not self._jobs.empty()

    def submit(self, work: Callable[[Any], T]) -> "Call":
        outbox: queue.Queue = queue.Queue(maxsize=1)
        self._jobs.put((work, outbox))
        return Call(outbox)

    def forget_session(self) -> None:
        """Drop the cached connection so the next call attaches afresh."""
        self.submit(lambda _session: None)

    def shutdown(self, timeout: float = 5.0) -> None:
        self._jobs.put(None)
        self._thread.join(timeout)


class Call:
    """A submitted job, collected without blocking the interface."""

    def __init__(self, outbox: "queue.Queue") -> None:
        self._outbox = outbox
        self._result: Optional[Tuple[Any, Optional[BaseException]]] = None

    def poll(self) -> Optional[Tuple[Any, Optional[BaseException]]]:
        if self._result is None:
            try:
                self._result = self._outbox.get_nowait()
            except queue.Empty:
                return None
        return self._result

    def wait(self, timeout: Optional[float] = None) -> Tuple[Any, Optional[BaseException]]:
        if self._result is None:
            self._result = self._outbox.get(timeout=timeout)
        return self._result


# -- diagnostic -------------------------------------------------------------

EXIT_OK = 0
EXIT_NOT_AVAILABLE = 2
EXIT_NOT_RUNNING = 3
EXIT_WRONG_VERSION = 4
EXIT_COM_ERROR = 5


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Report what this machine's SolidWorks looks like from here.

    Run as ``python -m gear_generator.swcom``. Everything the live link depends
    on is printed by this one command, which is what makes a failure somewhere
    later cheap to place.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    unknown = [a for a in arguments if a not in ("--templates", "--equations")]
    if unknown:
        print(f"unknown option {unknown[0]}; use --templates or --equations")
        return EXIT_COM_ERROR
    if not is_available():
        print(f"pywin32 is not usable here: {unavailable_reason()}")
        print("Install it with: pip install pywin32")
        return EXIT_NOT_AVAILABLE

    unreachable: List[Tuple[str, str]] = []
    try:
        candidates = find_candidates(unreachable)
    except SolidWorksError as exc:
        print(f"error: {exc}")
        return EXIT_COM_ERROR

    for moniker, reason in unreachable:
        print(f"unreachable: {moniker}  {reason}")

    if not candidates:
        print("No running SolidWorks was found in the Running Object Table.")
        return EXIT_NOT_RUNNING

    print(f"sessions found: {len(candidates)}")
    for candidate in candidates:
        print(f"  {candidate.moniker}  {version_label(candidate.revision)}")

    try:
        chosen = choose(candidates)
    except WrongVersion as exc:
        print(f"\n{exc}")
        return EXIT_WRONG_VERSION
    except NotRunning as exc:
        print(f"\n{exc}")
        return EXIT_NOT_RUNNING

    session = Session(chosen.app, chosen.revision, chosen.pid)
    note = " — newer than tested" if is_newer_than_tested(chosen.revision) else ""
    print(f"\nusing {session.label}, PID {session.pid}{note}")

    if "--templates" in arguments:
        for kind in ("part", "assembly"):
            path = session.default_template(kind)
            state = "exists" if path and os.path.isfile(path) else "MISSING"
            print(f"{kind} template: {path or '(none set)'}  {state}")

    documents = session.documents()
    if not documents:
        print("no documents open")
        return EXIT_OK

    active = session.active_document()
    for doc in documents:
        mark = "*" if active and doc.title == active.title else " "
        where = doc.path or "(never saved)"
        print(f"{mark} {doc.title}  type={doc.doc_type}  {where}")

    if active is None:
        print("\nno active document, so no features listed")
        return EXIT_OK

    if "--equations" in arguments:
        session._build_doc = None  # noqa: SLF001 - read the active document, not a build's
        try:
            listed = session.equations()
        except SolidWorksError as exc:
            print(f"\nerror reading the equations of {active.title}: {exc}")
            return EXIT_COM_ERROR
        print(f"\n{active.title}: {len(listed)} equations")
        for index, (text, value) in enumerate(listed):
            print(f"    {index:>3}  {text}  = {value!r}")

    try:
        features = session.features()
    except SolidWorksError as exc:
        print(f"\nerror walking {active.title}: {exc}")
        return EXIT_COM_ERROR

    print(f"\n{active.title}: {len(features)} features")
    for feature in features:
        print(f"    {feature.name}  ({feature.type_name})")
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
