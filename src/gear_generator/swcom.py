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
from .probe import comerr
from .store import same_path

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
# The floor is 2024 because every probe, end-to-end builds included, passed on
# 2024 (probe/results/sw2024). 2025 was never probed but sits between the two.
MINIMUM_MAJOR = 32
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

# The routes probe tier 7 (p7_workbook) tried for each W4 member, in its own
# words: whichever it records in findings.py is the one taken, and every one
# of them is written here so a different answer on another version needs no
# new code. A finding that is None (or a route not listed) is refused, never
# guessed.
PLANE_SELECT_ROUTES = ("Select2 on the feature found by name", "SelectByID2 by name",
                       "Select2 on what InsertRefPlane returned")        # AXIS_PLANE_SELECT_ROUTE
OPEN_ROUTES = ("OpenDoc6", "OpenDoc7", "OpenDoc")                          # OPEN_DOC_ROUTE, OPEN_ASSEMBLY_ROUTE
UPDATE_OPEN_ROUTES = ("open and activate", "ask")                          # UPDATE_OPEN_ROUTE
COMPONENT_FIND_ROUTES = ("GetComponentByName", "GetComponents(True) by Name2",
                         "root component GetChildren by Name2",
                         "FeatureByName then GetSpecificFeature2")          # COMPONENT_FIND_ROUTE
TRANSFORM_ORDERS = ("columns", "rows")                                     # TRANSFORM_ARRAY_ORDER
# Probe assembly_rebuild_scope's routes for an assembly, with the member and its arguments; "none" is not one of
# them (it showed every change but reported no failure and left a put unmarked).
ASSEMBLY_REBUILD_CALLS = {"ForceRebuild3(True)": ("ForceRebuild3", (True,)),
                          "EditRebuild3": ("EditRebuild3", ()),
                          "ForceRebuild3(False)": ("ForceRebuild3", (False,))}     # ASSEMBLY_REBUILD_ROUTE

# swComponentSuppressionState_e, as probe layout_assembly_reopen read it from
# swconst.tlb on SolidWorks 2026: 0 suppressed, 1 lightweight, 2 fully
# resolved, 3 resolved, 4 fully lightweight.
COMPONENT_SUPPRESSED = 0
COMPONENT_LIGHTWEIGHT = (1, 4)

# What a folder in the MateGroup may be skipped by (Session.mate_states): its entries' type name, and every finding that
# says skipping it loses no mate — the walk sees the mates inside a folder as ordinary siblings (probe round P0c,
# mate_folders). A later probe's finding for another case (a reopened assembly, a nested folder) is one more name here.
MATE_FOLDER_TYPE_FINDING = "MATE_FOLDER_TYPE_NAME"
MATE_FOLDER_SKIP_REQUIRES = ("MATE_GROUP_WALK_SEES_MATES_IN_A_FOLDER",)


def mate_folder_type() -> Optional[str]:
    """The type name a MateGroup folder's entries are skipped by, or None (nothing skipped) while that finding or
    any of :data:`MATE_FOLDER_SKIP_REQUIRES` is missing or not True."""
    if any(getattr(findings, name, None) is not True for name in MATE_FOLDER_SKIP_REQUIRES):
        return None
    folder = getattr(findings, MATE_FOLDER_TYPE_FINDING, None)
    return str(folder) if folder else None


# Whether a component is fully resolved (Session.component_resolved), as probe round P0d will settle it: the finding
# naming the read, the routes this code can make, and the finding giving the fully-resolved value(s). Placeholder
# names until P0d is committed: rename here, in one place.
RESOLVED_ROUTE_FINDING = "COMPONENT_RESOLVED_ROUTE"
RESOLVED_VALUES_FINDING = "COMPONENT_FULLY_RESOLVED_STATES"
RESOLVED_ROUTES = ("GetSuppression2",)


class SolidWorksError(Exception):
    """Something about the SolidWorks connection did not work."""


# The kinds of assembly a caller names to rebuild_call; it never infers one.
ASSEMBLY_STATIC = "static"   # fixed components, no mates: the workbook gearbox as W4 builds it
ASSEMBLY_TRAIN = "train"     # the workbook gearbox mated to turn (W5): axis, axial, lock and gear mates
ASSEMBLY_PAIR = "pair"       # everything build_pair makes: centre-distance equation, mesh, shaft and point mates
ASSEMBLY_KINDS = (ASSEMBLY_STATIC, ASSEMBLY_TRAIN, ASSEMBLY_PAIR)


def rebuild_call(doc_type: int, kind: Optional[str] = None) -> Tuple[str, Tuple[Any, ...]]:
    """The member, and its arguments, that rebuild a document of this ``GetType``: the one place that decides.

    The caller says what kind of assembly it is (one of :data:`ASSEMBLY_KINDS`);
    nothing here infers it, and an assembly whose kind was not said is refused
    with a sentence before anything is changed, so a caller that forgets it
    never falls to another kind's route. A part ignores it.

    - A part (or anything that is not an assembly) is rebuilt as it always
      was, ``ForceRebuild3(False)``: a rebuild of a part's own features, and
      top-only on a part was never probed.
    - A PAIR (everything ``build_pair`` makes, with its centre-distance
      equation, mesh, shaft and point mates) takes the full
      ``ForceRebuild3(False)`` probe tiers 4 and 5 proved, as PLAN-GEARBOX
      keeps ``build_pair``; ``findings.PAIR_ASSEMBLY_REBUILD_ROUTE``, should a
      pair probe ever set one, would change it. It never reads the train's
      finding, which is measured on other mates.
    - A TRAIN (the workbook gearbox mated to turn, W5) takes
      ``findings.MATED_ASSEMBLY_REBUILD_ROUTE``, and while that is None the
      full rebuild every mated result on record ran (probe tiers 4, 5 and 8).
    - A STATIC assembly (fixed components, no mates: the W4 gearbox) takes
      ``findings.ASSEMBLY_REBUILD_ROUTE``, which it requires (probe
      assembly_rebuild_scope, SolidWorks 2026 34.1.1 and 2024 32.5.0):
      ``ForceRebuild3(False)`` rebuilt every component and marked each one
      modified, parts nothing had changed among them, while
      ``ForceRebuild3(True)`` marked the assembly alone, still showed a put,
      the layout part's moved axes and a part changed in its own document,
      and still returned False while a component failed to rebuild; a finding
      that is missing, not one of the table's, or at odds with
      ``findings.ASSEMBLY_REBUILD_TOP_ONLY`` is refused.

    A finding value not in :data:`ASSEMBLY_REBUILD_CALLS` is refused with a
    sentence, never guessed.
    """
    if doc_type != DOC_ASSEMBLY:
        return "ForceRebuild3", (False,)
    if kind is None:
        raise SolidWorksError("This assembly was to be rebuilt without saying what kind of assembly it is (fixed, "
                              "a mated train or a pair), so which rebuild it takes cannot be chosen and nothing is "
                              "changed; that is a fault in Gear Generator, not in SolidWorks.")
    if kind not in ASSEMBLY_KINDS:
        raise SolidWorksError(f"{kind!r} is not a kind of assembly Gear Generator rebuilds (it knows "
                              f"{', '.join(ASSEMBLY_KINDS)}), so nothing is changed; that is a fault in Gear "
                              "Generator, not in SolidWorks.")
    if kind in (ASSEMBLY_PAIR, ASSEMBLY_TRAIN):
        name = "PAIR_ASSEMBLY_REBUILD_ROUTE" if kind == ASSEMBLY_PAIR else "MATED_ASSEMBLY_REBUILD_ROUTE"
        route = getattr(findings, name, None)
        if route is None:
            return ASSEMBLY_REBUILD_CALLS["ForceRebuild3(False)"]
        if route not in ASSEMBLY_REBUILD_CALLS:
            raise SolidWorksError(f"findings.{name} is {route!r}, which is not a rebuild this code knows, so no "
                                  f"{'pair' if kind == ASSEMBLY_PAIR else 'mated'} assembly is changed; run its "
                                  "probe again.")
        return ASSEMBLY_REBUILD_CALLS[route]
    route = getattr(findings, "ASSEMBLY_REBUILD_ROUTE", None)
    if route not in ASSEMBLY_REBUILD_CALLS:
        raise SolidWorksError(f"How to rebuild an assembly has not been settled on SolidWorks yet "
                              f"(findings.ASSEMBLY_REBUILD_ROUTE is {route!r}), so no assembly is changed; run probe "
                              "tier 7 first.")
    member, args = ASSEMBLY_REBUILD_CALLS[route]
    top_only = getattr(findings, "ASSEMBLY_REBUILD_TOP_ONLY", None)
    if member == "ForceRebuild3" and top_only is not args[0]:
        raise SolidWorksError(f"findings.ASSEMBLY_REBUILD_ROUTE is {route!r} but findings.ASSEMBLY_REBUILD_TOP_ONLY "
                              f"is {top_only!r}, and the two disagree, so no assembly is changed; run probe tier 7 "
                              "again.")
    return member, args


class NotAvailable(SolidWorksError):
    """pywin32 is not installed, or this is not Windows."""


class NotRunning(SolidWorksError):
    """No SolidWorks session is reachable."""


class ComponentGone(SolidWorksError):
    """A component recorded by its ``Name2`` is not in the assembly any more (renamed or deleted in SolidWorks):
    nothing the app does puts it back, so the way on is a new revision (``swbuild.NotAsBuilt``)."""


class WrongVersion(SolidWorksError):
    """Every reachable session is older than this app supports."""


class MateRefused(SolidWorksError):
    """SolidWorks would not make a mate: ``AddMate5`` answered nothing, or no new mate (or more than one) appeared
    in the MateGroup (W5). A mate that IS made with a status other than ``findings.ADD_MATE_NO_ERROR`` is not this:
    the status is kept (:meth:`Session.mate_status`) and the build's mate check judges it."""


class MateGone(ComponentGone):
    """A mate recorded by its name is not in the assembly any more (renamed or deleted in SolidWorks): as for a
    component, only a new revision puts it back, so Update's check phase turns it into ``swbuild.NotAsBuilt``.
    Sentence: *The mate "G1 meshes G2" is not in Reducer_12to1.SLDASM any more: it was renamed or deleted in
    SolidWorks.*"""


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


_COM_ERRORS: Tuple[type, ...] = (pythoncom.com_error,) if pythoncom is not None else ()

# HRESULTs that mean the session itself has gone: SolidWorks closed or crashed under a call (RPC_S_SERVER_UNAVAILABLE,
# RPC_S_CALL_FAILED, RPC_S_CALL_FAILED_DNE, RPC_E_DISCONNECTED, RPC_E_SERVER_DIED, RPC_E_SERVER_DIED_DNE).
CONNECTION_LOST = frozenset({0x800706BA, 0x800706BE, 0x800706BF, 0x80010108, 0x80010007, 0x80010012})
# A call turned away while SolidWorks is busy, typically with a modal dialog up (RPC_E_CALL_REJECTED,
# RPC_E_SERVERCALL_RETRYLATER).
CALL_REJECTED = frozenset({0x80010001, 0x8001010A})


class ComError(SolidWorksError):
    """A COM call that failed, as a sentence naming the member and what SolidWorks (or COM) said.

    ``str()`` is the sentence. ``args`` stay pywin32's own four (HRESULT, text, excepinfo, argerror), so
    ``probe.comerr.describe_error`` reads a wrapped error exactly as it read a bare ``com_error``: a probe records
    the same evidence as before. ``hresult`` is the unsigned HRESULT (0 when there was none) and ``lost`` whether
    it says the session itself has gone.
    """

    def __init__(self, member: str, error: BaseException) -> None:
        super().__init__(*getattr(error, "args", ()))
        info = comerr.describe_error(error)
        self.member = member
        self.hresult = int(info["hresult"], 16) if info["hresult"] else 0
        self.lost = self.hresult in CONNECTION_LOST
        args = tuple(getattr(error, "args", ()))
        excepinfo = args[2] if len(args) >= 3 and isinstance(args[2], tuple) else ()
        server = str(excepinfo[2]).strip() if len(excepinfo) >= 3 and excepinfo[2] else ""
        said = (server or str(args[1] if len(args) >= 2 and args[1] else info["text"] or "")).strip().rstrip(".")
        said = said or "no reason given"
        name = f" ({info['name']})" if info["name"] else ""
        if self.lost:
            tail = " SolidWorks may have closed or crashed; the next press connects to it again."
        elif self.hresult in CALL_REJECTED:
            tail = " SolidWorks was busy, perhaps with a dialog open; close it in SolidWorks and try again."
        else:
            tail = ""
        self.sentence = f"SolidWorks did not complete {member}: {said}{name}.{tail}"

    def __str__(self) -> str:
        return self.sentence


class _Connection:
    """Whether a call since the last job began said the session has gone (``ComError.lost``). One per process;
    every COM call is on the worker's one thread, which reads and resets it around each job."""

    lost = False


CONNECTION = _Connection()


def call(obj: Any, name: str, *args: Any) -> Any:
    """Reach a member of a late-bound COM object.

    Attribute access already invokes a zero-argument member, so ``Name``,
    ``RevisionNumber`` and ``GetNextFeature`` all come back as their results.
    Testing ``callable`` and invoking would be wrong: a member returning a
    document is itself callable, and calling it raises "Member not found".

    A ``pywintypes.com_error`` comes out as :class:`ComError`, a
    :class:`SolidWorksError` whose text is a sentence naming the member: so
    every caller that turns a SolidWorks refusal into a failure on a result
    (a build, an update) also catches an RPC failure, a call rejected while a
    modal dialog is up, or a member that failed, instead of letting it escape
    and lose what the job had saved (W4 review B1). It happens here, at the
    one place every COM call passes, rather than in each Session method.
    """
    def reach() -> Any:
        member = getattr(obj, name)
        return member(*args) if args else member

    return _guarded(name, reach)


def _guarded(member: str, action: Callable[[], Any]) -> Any:
    """Run one COM action — a call, a property put, a raw ``Invoke`` — turning a ``pywintypes.com_error`` into
    :class:`ComError` naming ``member`` and setting :data:`CONNECTION` ``.lost`` when it says the session has gone.
    :func:`call` goes through it, and so does every COM action that cannot be spelled as a call: :func:`_put`,
    :func:`_put_indexed` (every global set) and ``place_component``'s ``CreateTransform`` (every component
    placed). Before the second W4 review (N4) those two reached COM directly: an error there read "it stopped
    on an unexpected com_error: (-2147023170, …)" rather than a sentence, and never marked the session lost, so
    the next press failed its pre-flight against a dead session instead of connecting again."""
    try:
        return action()
    except _COM_ERRORS as exc:
        error = ComError(member, exc)
        if error.lost:
            CONNECTION.lost = True
        raise error from exc


def _put(obj: Any, name: str, value: Any) -> None:
    """A property put (``feature.Name = new`` in VBA) through :func:`_guarded`, so a COM error is a sentence."""
    _guarded(f"setting {name}", lambda: setattr(obj, name, value))


def _dispatch(raw: Any) -> Any:
    return _dynamic.Dispatch(raw.QueryInterface(pythoncom.IID_IDispatch))


def _null_dispatch() -> Any:
    """An absent COM object, typed. A bare None is a type mismatch."""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _out_long() -> Any:
    """A by-reference integer for an out parameter SolidWorks insists on."""
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def _out_text() -> Any:
    """A by-reference string for an out parameter; ``Get6`` filled it (probe custom_properties)."""
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BSTR, "")


def _out_bool() -> Any:
    """A by-reference boolean for an out parameter, as ``Get6`` takes them (probe custom_properties)."""
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_BOOL, False)


def _type_name(obj: Any) -> str:
    """``GetTypeName2`` first, defaulting to ``?``: naming a failure must not fail."""
    try:
        return str(call(obj, "GetTypeName2"))
    except Exception:  # noqa: BLE001
        return "?"


def _read(obj: Any, name: str) -> Any:
    """A zero-argument member, read, and invoked if what comes back is a method.

    Late binding turns most zero-argument members into property gets, but not
    all: probe tier 7 read ``IInterference.Components`` and
    ``GetActiveConfiguration`` through this same test (p4_interference.member),
    recording which form each took.
    """
    value = call(obj, name)
    if type(value).__name__ in ("method", "function"):
        return value()
    return value


def _doc_of(result: Any) -> Any:
    """A document from a call that may hand back ``(doc, out, out)`` or the document alone (probe tier 7)."""
    return result[0] if isinstance(result, tuple) and result else result


def _by_ref(value: Any) -> int:
    """What SolidWorks wrote into a by-reference integer (or the integer itself, if it came back plain)."""
    value = getattr(value, "value", value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_sentence(exc: BaseException) -> str:
    """What a raise says, as a sentence to follow another: a SolidWorks refusal (``ComError`` included) as it came,
    anything else named, since it is not a sentence of ours."""
    text = str(exc).strip()
    if isinstance(exc, SolidWorksError) and text:
        return text if text.endswith(".") else text + "."
    text = text.rstrip(".")
    return f"It stopped on an unexpected {type(exc).__name__}" + (f": {text}." if text else ".")


def _base_name(path: str) -> str:
    """A Windows path's file name, wherever this runs (``os.path.basename`` keeps backslashes on Linux)."""
    return os.path.basename(str(path).replace("\\", "/"))


def _file_name(path: str) -> str:
    """A path's file name, lower-cased, as SolidWorks keys open documents (probe add_component_same_name_elsewhere)."""
    return _base_name(path).lower()


def _segment_name(segment: Any) -> str:
    try:
        return str(call(segment, "GetName"))
    except Exception:  # noqa: BLE001 - an entity that will not name itself cannot be selected by name
        return ""


def _put_indexed(obj: Any, name: str, index: int, value: Any) -> None:
    """An indexed property put, which late binding cannot spell as an assignment.

    ``eqm.Equation(i) = text`` in VBA; through pywin32's dynamic dispatch the
    name is only ever invoked as a get or a call, so the put goes through
    ``Invoke`` (probe equation_set, SolidWorks 2026).
    """
    oleobj = obj._oleobj_  # noqa: SLF001
    _guarded(f"setting {name}({index})", lambda: oleobj.Invoke(oleobj.GetIDsOfNames(name), 0,
                                                               pythoncom.DISPATCH_PROPERTYPUT, False, index, value))


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


@dataclass(frozen=True)
class MateState:
    """One mate of the build's assembly as SolidWorks holds it after a rebuild (W5; :meth:`Session.mate_states`).

    Defined here rather than in ``swbuild`` (W5-PLAN §1.4 put it there) because ``swcom`` returns it and must not
    import ``swbuild``; ``swbuild.MateState`` is this class. ``name`` is the mate's ``IFeature.Name``; ``code`` its
    ``IFeature.GetErrorCode2`` — any non-zero is a problem, whatever the number, since 2024 and 2026 give different
    numbers for the same mates (``findings.MATE_ERROR_2024``) — ``warning`` the ``IsWarning`` that comes with it
    (False marks the mate at fault when several are flagged; True when the code is 0), and ``suppressed`` its
    ``IFeature.IsSuppressed2`` in this configuration (``findings.THIS_CONFIGURATION``)."""

    name: str
    code: int = 0
    warning: bool = True
    suppressed: bool = False


# The most documents ``Session.documents`` walks before it calls the list a runaway (one whose ``GetNext`` never
# answers nothing). Far beyond any assembly's documents: it is a guard against a loop, not a limit on work.
DOCUMENT_WALK_LIMIT = 100_000


class DocumentsUnknown(SolidWorksError):
    """SolidWorks' list of open documents did not come to an end (:data:`DOCUMENT_WALK_LIMIT`)."""


class Session:
    """One connected SolidWorks. Only ever touched from the worker thread."""

    def __init__(self, app: Any, revision: Tuple[int, ...], pid: int) -> None:
        self._app = app
        self.revision = revision
        self.pid = pid
        # AddMate5's status out-parameter for every mate this session made, by the name it kept (W5: mate_status).
        self._mate_statuses: Dict[str, int] = {}

    @property
    def label(self) -> str:
        return version_label(self.revision)

    def active_document(self) -> Optional[DocInfo]:
        doc = call(self._app, "ActiveDoc")
        return None if doc is None else self._describe(doc)

    def documents(self) -> List[DocInfo]:
        """Every document SolidWorks holds open, by ``GetFirstDocument``/``GetNext`` to the end of its list.

        A job's pre-flight reads it twice over: decision 7's same-name check,
        and which documents were open before the job (the marks a job settles,
        second W4 review N2). So it walks until ``GetNext`` answers nothing:
        one large assembly loads hundreds of documents, and a list cut short
        (it stopped at 200 before the third review) let a document holding
        Update's unsaved changes pass as loaded from its file. Only a runaway
        list — :data:`DOCUMENT_WALK_LIMIT` documents and no end — is refused,
        with a sentence (:class:`DocumentsUnknown`)."""
        return [self._describe(doc) for doc in self._walk_documents()]

    def _walk_documents(self) -> List[Any]:
        out: List[Any] = []
        doc = call(self._app, "GetFirstDocument")
        while doc is not None:
            if len(out) >= DOCUMENT_WALK_LIMIT:
                raise DocumentsUnknown(
                    f"SolidWorks listed {DOCUMENT_WALK_LIMIT} open documents without coming to the end of its list, "
                    "so which documents it holds open cannot be known here, and nothing that depends on it is "
                    "started; restart SolidWorks and try again.")
            out.append(doc)
            doc = call(doc, "GetNext")
        return out

    def has_unsaved_changes(self) -> bool:
        """Whether the build document (the one ``open_document`` just opened) holds changes not saved to its file:
        ``IModelDoc2.GetSaveFlag`` (probe close_document, tier 0: True on a part modified and never saved, 2026
        and 2024). A job counts a document it opened as loaded from its file only when this is False, so a
        document holding unsaved changes never has its unsaved mark cleared (third W4 review, item 1)."""
        return bool(call(self._doc(), "GetSaveFlag"))

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
        _put(feature, "Name", new)
        return str(call(feature, "Name"))

    def set_rebuild_suppressed(self, suppressed: bool) -> None:
        """Hold the rebuild off while a batch of changes goes in.

        Rebuilding per change shows real but transient errors partway through,
        and rebuilds once per change for nothing.
        """
        self._app.CommandInProgress = bool(suppressed)

    def rebuild(self, kind: Optional[str] = None) -> bool:
        """Rebuild the build's document (else the active one). Called once, after the last change.

        Which rebuild is :func:`rebuild_call`'s to say, by the document's
        ``GetType`` and the kind of assembly the caller says it is (``kind``,
        one of :data:`ASSEMBLY_KINDS`): a part as always, a pair or a train
        fully until a finding says otherwise, a static one top-only
        (``findings.ASSEMBLY_REBUILD_ROUTE``), so a rebuild after an Update or a
        workbook build marks the assembly modified and leaves every part it did
        not change as it was.
        """
        doc = self._doc()
        member, args = rebuild_call(int(call(doc, "GetType")), kind)
        return bool(call(doc, member, *args))


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
        self._mate_statuses = {}                  # a status is this build's: never one a mate of an earlier build left
        self._plane_objects: Dict[str, Any] = {}  # a RefPlane handle -> what InsertRefPlane returned
        self._open_sketch: Optional[str] = None
        self._build_doc: Any = None  # until new_part, new_assembly or open_document, the active document
        self._dim_dialog = bool(call(self._app, "GetUserPreferenceToggle", findings.INPUT_DIM_VAL_ON_CREATE))
        call(self._app, "SetUserPreferenceToggle", findings.INPUT_DIM_VAL_ON_CREATE, False)

    def end_build(self) -> None:
        """Forget the pointers; the document itself stays the build's until the next begin."""
        self._handles = {}
        self._plane_objects = {}
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
        asked = template
        template = template or self.default_template("part" if doc_type == DOC_PART else "assembly")
        if not template:
            raise SolidWorksError(f"SolidWorks names no default {noun} template (Tools > Options > Default "
                                  f"Templates), so no {noun} can be made; name one there, or give a template.")
        if not os.path.isfile(template):
            # The path as it is typed: a repr doubled every backslash of a Windows path in the sentence the
            # window shows (SolidWorks 2026, probe/workbook_assembly_check.py 2026-11-13).
            raise SolidWorksError(f"There is no {noun} template at {template}." if asked else
                                  f"SolidWorks' default {noun} template, {template}, is not there.")
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
        """Bring an open document forward, and make it the one this session reads and changes.

        Without forgetting the last build's document, a volume or body count
        asked for after activating a part would still be of the assembly built
        last (probe internal_end_to_end, SolidWorks 2026: GetBodies2 was asked
        of an assembly).
        """
        call(self._app, "ActivateDoc3", title, False, 0, _out_long())
        self._build_doc = None

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
        _put(feature, "Name", name)
        return str(call(feature, "Name"))

    # -- features

    def insert_axis(self, handle: str, name: str, planes: "Tuple[int | str, int | str]") -> str:
        """Two planes selected in the order given, ``InsertAxis2(True)``, the new RefAxis found and named (probe axis).

        An ``int`` is the Nth reference plane in tree order, as the strip's
        "Gear Axis" uses planes 2 and 3. A ``str`` is the handle of a plane this
        build made (``ref_plane`` keeps its name in ``_handles``), selected by
        ``findings.AXIS_PLANE_SELECT_ROUTE``. Probe tier 7
        axis_through_named_planes, SolidWorks 2026 (34.0.0) and 2024 (32.5.0): all three routes
        in :data:`PLANE_SELECT_ROUTES` — ``IFeature.Select2`` on the feature
        found by name, ``SelectByID2 "<name>", "PLANE"``, and ``Select2`` on
        what ``InsertRefPlane`` returned — made the axis where the planes cross,
        and it followed both planes' globals; whichever the finding names is
        taken. An int beside a str (a shaft at X = 0 or Y = 0, through the base
        plane itself) also needs ``AXIS_THROUGH_BASE_PLANE`` (probe
        axis_through_base_planes). Without those findings a str plane is
        refused rather than guessed. The order of selection sets which way the
        axis points (``findings.LAYOUT_AXIS_Z_SIGN``), so it is never changed here.
        Through the app on 2026 (gearbox_smoke 2026-11-13): a layout part's axes
        through Top then Right, and through a Top-parallel plane on the minus
        side then a Right-parallel one on the plus side, each crossed z = 0
        where the shaft is, to 1e-9 mm, and read +Z.
        """
        named = any(isinstance(p, str) for p in planes)
        route = getattr(findings, "AXIS_PLANE_SELECT_ROUTE", None)
        if named and route not in PLANE_SELECT_ROUTES:
            raise SolidWorksError(f"The axis {name} goes through a plane made in this build, and how to select such a "
                                  "plane has not been settled on SolidWorks yet (findings.AXIS_PLANE_SELECT_ROUTE is "
                                  f"{route!r}); run probe tier 7 first.")
        if named and any(not isinstance(p, str) for p in planes) \
                and getattr(findings, "AXIS_THROUGH_BASE_PLANE", None) is not True:
            raise SolidWorksError(f"The axis {name} goes through a base plane and a plane made in this build, which "
                                  "has not been settled on SolidWorks yet (findings.AXIS_THROUGH_BASE_PLANE); "
                                  "run probe tier 7 first.")
        doc = self._doc()
        before = self._top_names()
        labels = []
        for index, plane in enumerate(planes):
            if isinstance(plane, str):
                labels.append(self._select_made_plane(plane, route, append=index > 0))
            else:
                self.select_plane_by_order(plane, append=index > 0)
                labels.append(f"plane {plane}")
        made = call(doc, "InsertAxis2", True)
        call(doc, "ClearSelection2", True)
        if not made:
            if not named:
                raise SolidWorksError(f"InsertAxis2 would not make {name} from planes {planes[0]} and {planes[1]}.")
            raise SolidWorksError(f"InsertAxis2 would not make {name} from {labels[0]} and {labels[1]}.")
        kept = self._rename(self._made_since(before, "RefAxis", "InsertAxis2"), name)
        self._handles[handle] = kept
        return kept

    def _select_made_plane(self, ref: str, route: str, append: bool) -> str:
        """A plane this build made, selected by ``route`` (one of :data:`PLANE_SELECT_ROUTES`); returns its name."""
        name = self._handles.get(ref)
        if not isinstance(name, str):
            raise SolidWorksError(f"The plane {ref!r} has not been made in this build.")
        if route == PLANE_SELECT_ROUTES[0]:
            self._select_feature(self._by_name(name), append=append)
            return name
        doc = self._doc()
        if not append:
            call(doc, "ClearSelection2", True)
        before = self._selected()
        if route == PLANE_SELECT_ROUTES[1]:
            attempt = lambda: call(call(doc, "Extension"), "SelectByID2", name, "PLANE", 0.0, 0.0, 0.0,  # noqa: E731
                                   append, 0, _null_dispatch(), 0)
        else:
            returned = getattr(self, "_plane_objects", {}).get(ref)
            if returned is None:
                raise SolidWorksError(f"InsertRefPlane gave nothing back for {name}, so it cannot be selected by "
                                      "what it returned.")
            attempt = lambda: call(returned, "Select2", append, 0)  # noqa: E731
        if self._retry_select(attempt, before):
            return name
        raise SolidWorksError(f"{name} could not be selected by {route} {self._selection_context()}.")

    def open_sketch(self, handle: str, plane: "int | str") -> None:
        """On the Nth reference plane in tree order, or on a plane this build made, by its handle."""
        doc = self._doc()
        before = self._top_names()
        if isinstance(plane, str):
            name = self._handles.get(plane)
            if not isinstance(name, str):
                raise SolidWorksError(f"The plane {plane!r} has not been made in this build.")
            self._select_feature(self._by_name(name))
        else:
            self.select_plane_by_order(plane)
        manager = call(doc, "SketchManager")
        _put(manager, "AddToDB", True)
        _put(manager, "DisplayWhenAdded", False)
        call(manager, "InsertSketch", True)
        sketch = call(manager, "ActiveSketch")
        call(doc, "ClearSelection2", True)
        if sketch is None:
            _put(manager, "AddToDB", False)
            _put(manager, "DisplayWhenAdded", True)
            raise SolidWorksError(f"InsertSketch would not open a sketch on plane {plane}.")
        self._handles[handle] = {"before": before, "sketch": sketch, "dimensions": []}
        self._open_sketch = handle

    def close_sketch(self, handle: str, name: str) -> str:
        doc = self._doc()
        manager = call(doc, "SketchManager")
        call(manager, "InsertSketch", True)
        _put(manager, "AddToDB", False)
        _put(manager, "DisplayWhenAdded", True)
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
            _put(entity, "ConstructionGeometry", True)

    def sketch_arc(self, handle: str, centre: Tuple[float, float], start: Tuple[float, float],
                   end: Tuple[float, float], direction: int = 1, construction: bool = False) -> None:
        """``CreateArc``: direction +1 is counter-clockwise from the start (probe sketch_entities)."""
        m = MM_PER_METRE
        entity = call(self._manager(), "CreateArc", centre[0] / m, centre[1] / m, 0.0, start[0] / m, start[1] / m,
                      0.0, end[0] / m, end[1] / m, 0.0, direction)
        self._keep(handle, entity, "an arc")
        if construction:
            _put(entity, "ConstructionGeometry", True)

    def sketch_line(self, handle: str, start: Tuple[float, float], end: Tuple[float, float],
                    construction: bool = False) -> None:
        m = MM_PER_METRE
        entity = call(self._manager(), "CreateLine", start[0] / m, start[1] / m, 0.0, end[0] / m, end[1] / m, 0.0)
        # Its segment name and its sketch, so a feature made after the sketch is
        # closed can select it by name (probes revolve and ref_plane_normal).
        self._keep(handle, entity, "a line", sketch=self._open_sketch, segment=_segment_name(entity))
        if construction:
            _put(entity, "ConstructionGeometry", True)

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

    def _sketch_point_in_model(self, at: Tuple[float, float]) -> Tuple[float, float, float]:
        """A point of the open sketch, in model metres, through the sketch's own transform (reading/05)."""
        sketch = self._handles[self._open_sketch]["sketch"] if self._open_sketch else None
        x, y = at[0] / MM_PER_METRE, at[1] / MM_PER_METRE
        if sketch is None:
            return x, y, 0.0
        data = [float(v) for v in call(call(call(sketch, "ModelToSketchTransform"), "Inverse"), "ArrayData")]
        scale = data[12] if len(data) > 12 and data[12] else 1.0
        return (scale * (data[0] * x + data[3] * y) + data[9], scale * (data[1] * x + data[4] * y) + data[10],
                scale * (data[2] * x + data[5] * y) + data[11])

    def dimension(self, name: str, refs: Sequence[str], at: Tuple[float, float]) -> str:
        """``AddDimension2`` at a point, then named and read back (probe dimensions).

        ``at`` is in the sketch's own coordinates and is handed over in the
        model's: on SolidWorks 2026 an angle dimension on the Top plane placed at
        sketch coordinates read 150° for a 30° angle, and placed at the same
        point in model coordinates read 30° (probe axis_from_sketch_line). On
        the Front plane, and planes parallel to it, the two are the same.
        """
        doc = self._doc()
        self._select_entities(refs)
        where = self._sketch_point_in_model(at)
        display = call(doc, "AddDimension2", where[0], where[1], where[2])
        call(doc, "ClearSelection2", True)
        if display is None:
            raise SolidWorksError(f"AddDimension2 would not dimension {' and '.join(refs)} as {name}.")
        dimension = call(display, "GetDimension2", 0)
        _put(dimension, "Name", name)
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

    def ref_plane(self, handle: str, name: str, plane: int, offset: float, flip: bool,
                  offset_dim: str) -> Tuple[str, str]:
        """``InsertRefPlane(8 | flip 256, d, 0, 0, 0, 0)`` on the Nth plane; returns ``(name, offset dimension)``.

        Probe ref_plane_offset, SolidWorks 2026: from the Front plane the
        unflipped plane was at +d on Z and the flipped one at -d, both facing +Z;
        the offset was the plane's only dimension, D1, and followed a global.
        """
        doc = self._doc()
        before = self._top_names()
        self.select_plane_by_order(plane)
        m = offset / MM_PER_METRE
        constraint = findings.REF_PLANE_DISTANCE | (findings.REF_PLANE_FLIP if flip else 0)
        made = call(call(doc, "FeatureManager"), "InsertRefPlane", constraint, m, 0, 0.0, 0, 0.0)
        call(doc, "ClearSelection2", True)
        if made is None:
            raise SolidWorksError(f"InsertRefPlane would not make {name} {offset:g} mm from plane {plane}.")
        feature = self._made_since(before, "RefPlane", "InsertRefPlane")
        kept = self._rename(feature, name)
        dim = self._name_dimension_by_value(feature, m, offset_dim, "offset")
        self._handles[handle] = kept
        # Kept too for AXIS_PLANE_SELECT_ROUTE "Select2 on what InsertRefPlane returned"; _handles holds the name,
        # which open_sketch, circular_pattern and mirror_body read as a str.
        self.__dict__.setdefault("_plane_objects", {})[handle] = made
        return kept, dim

    def sweep_cut(self, handle: str, profile: str, path: str, name: str, twist: float, reverse: bool,
                  twist_dim: str) -> Tuple[str, str]:
        """A cut of one sketch along another with a constant twist; returns ``(name, twist dimension)``.

        Probes sweep_twist and sweep_cut_ends, SolidWorks 2026: profile at mark
        1, path at mark 4, ``InsertCutSwept5`` with twist control 8 and the twist
        in radians. A negative twist turned the same way as a positive one, so
        the other hand is ``D1ReverseTwistDir`` set through the feature's
        definition. The twist was the sweep's one dimension; it is named before
        the definition is touched.
        """
        doc = self._doc()
        self._select_feature(self._sketch_feature(profile), mark=findings.SWEEP_PROFILE_MARK)
        self._select_feature(self._sketch_feature(path), append=True, mark=findings.SWEEP_PATH_MARK)
        angle = math.radians(twist)
        before = self._top_names()
        made = call(call(doc, "FeatureManager"), "InsertCutSwept5", False, False, findings.TWIST_CONSTANT_ALONG_PATH,
                    False, False, 0, 0, False, 0.0, 0.0, 0, 0, True, True, angle, True, False, False, False, False,
                    0.0, findings.SWEEP_DIRECTION)
        call(doc, "ClearSelection2", True)
        if made is None:
            raise SolidWorksError(f"InsertCutSwept5 would not sweep {profile} along {path} as {name}.")
        feature = self._made_since(before, "SweepCut", "InsertCutSwept5")
        kept = self._rename(feature, name)
        dim = self._name_dimension_by_value(feature, angle, twist_dim, "twist")
        if reverse:
            data = call(feature, "GetDefinition")
            if data is None or not call(data, "AccessSelections", doc, _null_dispatch()):
                raise SolidWorksError(f"The definition of {kept} ({_type_name(feature)}) could not be opened to "
                                      "reverse its twist.")
            _put(data, "D1ReverseTwistDir", True)
            if not call(feature, "ModifyDefinition", data, doc, _null_dispatch()):
                raise SolidWorksError(f"ModifyDefinition would not reverse the twist of {kept} ({_type_name(feature)}).")
        self._handles[handle] = {"feature": kept}
        return kept, dim

    def _select_segment(self, ref: str, append: bool, mark: int) -> None:
        """A line of a closed sketch, by ``LineN@Sketch`` (probes revolve, ref_plane_normal)."""
        record = self._handles.get(ref) or {}
        sketch = (self._handles.get(record.get("sketch") or "") or {}).get("name")
        if not record.get("segment") or not sketch:
            raise SolidWorksError(f"The line {ref!r} is not a line of a closed sketch this build made.")
        doc = self._doc()
        before = self._selected() if append else 0
        if not append:
            call(doc, "ClearSelection2", True)
        full = f"{record['segment']}@{sketch}"
        if not (call(call(doc, "Extension"), "SelectByID2", full, "EXTSKETCHSEGMENT", 0.0, 0.0, 0.0, append, mark,
                     _null_dispatch(), 0) and self._selected() > before):
            raise SolidWorksError(f"{full} could not be selected {self._selection_context()}.")

    def _select_sketch_point(self, ref: str, append: bool, mark: int) -> None:
        """An end of a closed sketch's line, by its location in model space (probe ref_plane_normal)."""
        handle = ref.partition(".")[0]
        record = self._handles.get(handle) or {}
        sketch = (self._handles.get(record.get("sketch") or "") or {}).get("sketch")
        if sketch is None:
            raise SolidWorksError(f"{ref!r} is not a point of a sketch this build made.")
        point = self._entity(ref)
        x, y = float(call(point, "X")), float(call(point, "Y"))
        data = [float(v) for v in call(call(call(sketch, "ModelToSketchTransform"), "Inverse"), "ArrayData")]
        scale = data[12] if len(data) > 12 and data[12] else 1.0
        model = (scale * (data[0] * x + data[3] * y) + data[9], scale * (data[1] * x + data[4] * y) + data[10],
                 scale * (data[2] * x + data[5] * y) + data[11])
        doc = self._doc()
        before = self._selected()
        if not (call(call(doc, "Extension"), "SelectByID2", "", "EXTSKETCHPOINT", model[0], model[1], model[2], append,
                     mark, _null_dispatch(), 0) and self._selected() > before):
            raise SolidWorksError(f"The point {ref} could not be selected at its place {self._selection_context()}.")

    def revolve(self, handle: str, sketch: str, name: str, axis: str) -> str:
        """A full turn about a line of the sketch; the sketch, then the line at mark 16, selected.

        Probe revolve, SolidWorks 2026: FeatureRevolve2 (20 arguments) made a
        Revolution of 2 pi r A about the centreline, and with a second
        centreline in the sketch the one meant had to be selected at mark 16.
        """
        doc = self._doc()
        self._select_feature(self._sketch_feature(sketch))
        self._select_segment(axis, append=True, mark=findings.REVOLVE_AXIS_MARK)
        before = self._top_names()
        made = call(call(doc, "FeatureManager"), "FeatureRevolve2", True, True, False, False, False, False, 0, 0,
                    2.0 * math.pi, 0.0, False, False, 0.0, 0.0, 0, 0.0, 0.0, True, True, True)
        call(doc, "ClearSelection2", True)
        if made is None:
            raise SolidWorksError(f"FeatureRevolve2 would not revolve {sketch} about {axis} into {name}.")
        kept = self._rename(self._made_since(before, findings.REVOLVE_TYPE, "FeatureRevolve2"), name)
        self._handles[handle] = {"feature": kept}
        return kept

    def ref_plane_normal(self, handle: str, name: str, line: str, point: str) -> str:
        """A plane square to a closed sketch's line, through a point on it (probe ref_plane_normal).

        The line at mark 0, the point by its model location at mark 1, and
        InsertRefPlane(perpendicular 2, 0, coincident 4, 0, 0, 0). On SolidWorks
        2026 the plane's sketch had its origin at the point, x along the cone's
        outward radial, y along +Y, and kept that frame as the line moved.
        """
        doc = self._doc()
        self._select_segment(line, append=False, mark=0)
        self._select_sketch_point(point, append=True, mark=1)
        before = self._top_names()
        made = call(call(doc, "FeatureManager"), "InsertRefPlane", findings.REF_PLANE_PERPENDICULAR, 0.0,
                    findings.REF_PLANE_COINCIDENT, 0.0, 0, 0.0)
        call(doc, "ClearSelection2", True)
        if made is None:
            raise SolidWorksError(f"InsertRefPlane would not make {name} square to {line} through {point}.")
        kept = self._rename(self._made_since(before, "RefPlane", "InsertRefPlane"), name)
        self._handles[handle] = kept
        return kept

    def loft_cut(self, handle: str, name: str, profiles: Sequence[str]) -> str:
        """A cut lofted through closed sketches, each at mark 1 in order (probe loft_cut_sections)."""
        doc = self._doc()
        for position, sketch in enumerate(profiles):
            self._select_feature(self._sketch_feature(sketch), append=position > 0, mark=findings.LOFT_PROFILE_MARK)
        before = self._top_names()
        made = call(call(doc, "FeatureManager"), "InsertCutBlend", False, False, False, 1.0, 0, 0, False, 0.0, 0.0,
                    0, True, True)
        call(doc, "ClearSelection2", True)
        if made is None:
            raise SolidWorksError(f"InsertCutBlend would not loft a cut through {', '.join(profiles)} as {name}.")
        kept = self._rename(self._made_since(before, findings.LOFT_CUT_TYPE, "InsertCutBlend"), name)
        self._handles[handle] = {"feature": kept}
        return kept

    def mirror_body(self, handle: str, name: str, plane: str) -> str:
        """The part's body mirrored about a plane this build made, merged into one.

        Probe mirror_body_merge, SolidWorks 2026: the plane at mark 2 and the
        body at mark 256, ``InsertMirrorFeature2(True, False, True, False, 0)``,
        made one body of twice the volume; the body at mark 1 mirrored nothing.
        """
        doc = self._doc()
        plane_name = self._handles.get(plane)
        if not isinstance(plane_name, str):
            raise SolidWorksError(f"The mirror {name} needs the plane {plane} first.")
        bodies = call(doc, "GetBodies2", 0, True)
        if not bodies or len(bodies) != 1:
            raise SolidWorksError(f"The mirror {name} needs exactly one solid body; the part has {len(bodies or ())}.")
        self._select_feature(self._by_name(plane_name), mark=findings.MIRROR_PLANE_MARK)
        data = call(call(doc, "SelectionManager"), "CreateSelectData")
        _put(data, "Mark", findings.MIRROR_BODY_MARK)
        before_count = self._selected()
        if not call(bodies[0], "Select2", True, data) or self._selected() <= before_count:
            raise SolidWorksError(f"The body could not be selected to mirror {self._selection_context()}.")
        before = self._top_names()
        made = call(call(doc, "FeatureManager"), "InsertMirrorFeature2", True, False, True, False, 0)
        call(doc, "ClearSelection2", True)
        if made is None:
            raise SolidWorksError(f"InsertMirrorFeature2 would not mirror the body about {plane_name}.")
        kept = self._rename(self._made_since(before, "MirrorSolid", "InsertMirrorFeature2"), name)
        self._handles[handle] = {"feature": kept}
        return kept

    def center_of_mass_mm(self) -> Tuple[float, float, float]:
        """The build document's centre of mass in mm (probe center_of_mass: metres, a three-element array)."""
        centre = call(call(call(self._doc(), "Extension"), "CreateMassProperty"), "CenterOfMass")
        if centre is None or len(centre) < 3:
            raise SolidWorksError(f"CenterOfMass returned {centre!r} for {call(self._doc(), 'GetTitle')}.")
        return (float(centre[0]) * MM_PER_METRE, float(centre[1]) * MM_PER_METRE, float(centre[2]) * MM_PER_METRE)

    def solid_body_count(self) -> int:
        bodies = call(self._doc(), "GetBodies2", 0, True)
        return len(bodies) if bodies else 0

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
        """``AddComponent5``: the part must already be open; returns ``Name2``, after checking the file it took.

        Probe add_component_opened_part, SolidWorks 2026 and 2024: a part saved and
        closed was refused (None), the same part opened by ``OpenDoc6`` first
        went in, and one file inserted twice was ``<stem>-1`` and ``<stem>-2``
        (``findings.REUSE_ADD_ROUTE``). Probe add_component_same_name_elsewhere:
        SolidWorks keeps one document per file name, so a part of the same name
        from another folder was refused too; but which file a component took
        is what a build must never get wrong (W4 decision 7), so the inserted
        component's path is read back (:meth:`_component_path`) and compared.
        """
        m = MM_PER_METRE
        doc = self._doc()
        component = call(doc, "AddComponent5", path, 0, "", False, "", at[0] / m, at[1] / m, at[2] / m)
        if component is None:
            raise SolidWorksError(f"AddComponent5 would not insert {path}.")
        kept = str(call(component, "Name2"))
        took = self._component_path(component)
        if not same_path(took, path):
            raise SolidWorksError(f"AddComponent5 put {kept} into {call(doc, 'GetTitle')} from "
                                  f"{took or 'a file whose path could not be read'}, not from {path}; a document "
                                  "of the same file name may be open from another folder.")
        self._handles[handle] = {"component": component, "path": path}
        return kept

    @staticmethod
    def _component_path(component: Any) -> str:
        """The file a component refers to, or ``""`` when it cannot be read.

        ``IComponent2.GetModelDoc2`` then ``IModelDoc2.GetPathName``: on
        SolidWorks 2026 (34.0.0, probe/gearbox_smoke.py 2026-11-13) it gave the
        inserted path for both gears of a strip pair, for parts built in the
        same job, for one part inserted twice, for a body-less layout part and
        for parts reused from an earlier build and opened by path. A component
        whose model is not loaded (lightweight) gives no model, so
        ``IComponent2.GetPathName`` is asked instead; probe/gear_pairs_check.py
        has read components' paths that way on 2026 and 2024, but no
        lightweight component has yet reached this fallback.
        """
        try:
            model = call(component, "GetModelDoc2")
        except Exception:  # noqa: BLE001 - fall through to the component's own path
            model = None
        if model is not None:
            path = str(call(model, "GetPathName") or "")
            if path:
                return path
        try:
            return str(call(component, "GetPathName") or "")
        except Exception:  # noqa: BLE001 - a path that cannot be read is reported by the caller
            return ""

    def fix_component(self, handle: str) -> None:
        """Fix a component, and read back that it is fixed.

        Whether the first component inserted comes in fixed depends on the
        install: on SolidWorks 2024 it does, on 2026 with the current MMGS
        assembly template it does not (probe assembly_components_and_mates,
        ``first_component_fixed_on_insert``), so ``IsFixed`` is read rather than
        assumed. ``FixComponent`` takes no arguments,
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

    def unfix_component(self, handle: str) -> None:
        """Let a component move: select it, ``UnfixComponent``, and read back that it floats.

        ``UnfixComponent`` takes no arguments and so is invoked explicitly, as
        ``FixComponent`` is; probe gear_mate saw the selected component float
        after it. The first component inserted may come in fixed — on 2024 it
        does, on 2026 with the current MMGS assembly template it does not (probe
        assembly_components_and_mates) — so ``IsFixed`` is read first.
        """
        component = self._handles[handle]["component"]
        if not bool(call(component, "IsFixed")):
            return
        doc = self._doc()
        call(doc, "ClearSelection2", True)
        if not call(component, "Select4", False, _null_dispatch(), False):
            raise SolidWorksError(f"{call(component, 'Name2')} could not be selected to unfix it.")
        doc.UnfixComponent()
        call(doc, "ClearSelection2", True)
        if bool(call(component, "IsFixed")):
            raise SolidWorksError(f"{call(component, 'Name2')} is still fixed after UnfixComponent.")

    def _component_ref(self, ref: str, append: bool) -> None:
        """``gear1:plane2`` or ``gear2:Gear Axis``, selected at mark 1 for a mate; ``asm:plane2`` the assembly's own.

        The assembly's own planes are taken by tree order, as a part's are, and
        selected the same way; probe gear_mate mated components to them.
        """
        handle, _, target = ref.partition(":")
        if handle == "asm":
            if not (target.startswith("plane") and target[5:].isdigit()):
                raise SolidWorksError(f"The assembly's own {target!r} is not a plane this tool can select.")
            self.select_plane_by_order(int(target[5:]), append=append, mark=1)
            return
        component = self._handles[handle]["component"]
        if target == "origin":
            self._select_component_origin(component, append)
            return
        if target.startswith("plane") and target[5:].isdigit():
            planes = self._planes(call(component, "GetModelDoc2"))
            name, kind = str(call(planes[int(target[5:]) - 1], "Name")), "PLANE"
        else:
            # The tool names its axis "Gear Axis" and its planes "Mid Plane" and "Profile Plane".
            name, kind = target, "AXIS" if target.endswith("Axis") else "PLANE"
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

    def _select_component_origin(self, component: Any, append: bool) -> None:
        """A component's origin point, by ``Point1@<origin>@<component>@<assembly>`` (probe nonparallel_mates)."""
        part = call(component, "GetModelDoc2")
        feature = call(part, "FirstFeature")
        origin = ""
        while feature is not None and not origin:
            if _type_name(feature) == "OriginProfileFeature":
                origin = str(call(feature, "Name"))
            feature = call(feature, "GetNextFeature")
        if not origin:
            raise SolidWorksError(f"{call(component, 'Name2')} has no origin to mate to.")
        doc = self._doc()
        if not append:
            call(doc, "ClearSelection2", True)
        before = self._selected()
        asm = os.path.splitext(str(call(doc, "GetTitle")))[0]
        full = f"{findings.ORIGIN_POINT}@{origin}@{call(component, 'Name2')}@{asm}"
        if not self._retry_select(lambda: call(call(doc, "Extension"), "SelectByID2", full, "EXTSKETCHPOINT", 0.0, 0.0,
                                               0.0, append, 1, _null_dispatch(), 0), before):
            raise SolidWorksError(f"{full} could not be selected for a mate.")

    def place_component(self, handle: str, rotation: Sequence[float], at: Tuple[float, float, float],
                        kind: Optional[str] = None) -> None:
        """Set a component's frame: a rotation given by rows, and its origin in mm (probe nonparallel_mates).

        ``IMathUtility.CreateTransform`` answered "member not found" to late
        binding's property get, so it is invoked as the method it is, with the
        16 numbers as a double array — the rotation in columns, then the
        translation in metres, the scale and three zeros — and put on
        ``Transform2``. Then the document is rebuilt as :func:`rebuild_call`
        says for the kind of assembly the caller names (``kind``: a pair or a
        train fully, as always, until a finding says otherwise), top-only for
        a static assembly: probe assembly_rebuild_scope saw the
        put show without any rebuild, but a put alone left the assembly
        unmarked (``findings.PUT_MARKS_ASSEMBLY_MODIFIED``), and the full
        rebuild this used to make marked every component modified. The frame
        is read back.
        """
        component = self._handles[handle]["component"]
        doc = self._doc()
        # Settled before the put, so a rebuild that cannot be made refuses with nothing moved.
        member, args = rebuild_call(int(call(doc, "GetType")), kind)
        m = MM_PER_METRE
        columns = [float(rotation[i * 3 + j]) for j in range(3) for i in range(3)]
        data = columns + [at[0] / m, at[1] / m, at[2] / m, 1.0, 0.0, 0.0, 0.0]
        utility = call(self._app, "GetMathUtility")
        oleobj = utility._oleobj_  # noqa: SLF001 - the method, not the property get
        raw = _guarded("CreateTransform", lambda: oleobj.Invoke(
            oleobj.GetIDsOfNames("CreateTransform"), 0, pythoncom.DISPATCH_METHOD, True,
            VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, data)))
        if raw is None:
            raise SolidWorksError("CreateTransform made no transform.")
        transform = raw if hasattr(raw, "ArrayData") else _guarded("CreateTransform", lambda: _dynamic.Dispatch(raw))
        _put(component, "Transform2", transform)
        call(doc, member, *args)
        got = [float(v) for v in call(call(component, "Transform2"), "ArrayData")]
        error = max(abs(got[i] - data[i]) for i in range(9))
        moved = max(abs(got[9 + i] - data[9 + i]) for i in range(3)) * m
        if error > 1e-6 or moved > 1e-6:
            raise SolidWorksError(f"{call(component, 'Name2')} did not take its frame "
                                  f"(rotation off {error:.1e}, origin {moved:.1e} mm).")

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

    def add_mate(self, handle: str, kind: str, a: str, b: str, value: float = 0.0, name: str = "",
                 ratio: Tuple[float, float] = (1.0, 1.0), flip: bool = False) -> Tuple[str, str]:
        """``AddMate5`` on two component references; returns ``(mate name, its dimension)``.

        Probe assembly_components_and_mates: coincident, distance and angle
        mates were made this way and the component moved to where they said.
        A ``gear`` mate is :meth:`_gear_mate`'s.
        """
        if kind == "gear":
            return self._gear_mate(handle, a, b, ratio, flip, name)
        if kind == "lock":
            return self._lock_mate(handle, a, b, name)
        # Probe nonparallel_mates: a point on a point or a plane is a coincident
        # mate, a point's distance from a plane a distance mate, and the angle
        # between two axes an angle mate, each with its value as dimension D1.
        types = {"coincident": findings.MATE_COINCIDENT, "distance": findings.MATE_DISTANCE,
                 "angle": findings.MATE_ANGLE, "point": findings.MATE_COINCIDENT,
                 "point distance": findings.MATE_DISTANCE, "axis angle": findings.MATE_ANGLE}
        if kind not in types:
            raise SolidWorksError(f"There is no verified mate type for {kind!r}.")
        before = self._mate_names()
        self._component_ref(a, append=False)
        self._component_ref(b, append=True)
        distance = abs(value) / MM_PER_METRE if types[kind] == findings.MATE_DISTANCE else 0.0
        angle = math.radians(value) if types[kind] == findings.MATE_ANGLE else 0.0
        # A point distance is taken along the plane's normal; a negative one is flipped (probe nonparallel_mates).
        flip = kind == "point distance" and value < 0
        mate, status = self._add_mate5(types[kind], findings.MATE_ALIGN_CLOSEST, flip, distance, distance,
                                       distance, 1, 1, angle, angle, angle, False, False, 0)
        call(self._doc(), "ClearSelection2", True)
        made = [n for n in self._mate_names() if n not in before]
        if mate is None or len(made) != 1:
            raise MateRefused(f"AddMate5 would not make a {kind} mate between {a} and {b}.")
        feature = self._mate_feature(made[0])
        kept = self._rename(feature, name) if name else made[0]
        self._mate_statuses[kept] = status
        dim = ""
        if types[kind] != findings.MATE_COINCIDENT:
            wanted = distance if types[kind] == findings.MATE_DISTANCE else angle
            matches = [d for d in self._dimensions(feature) if abs(float(call(d, "SystemValue")) - wanted) < 1e-9]
            dim = str(call(matches[0], "Name")) if len(matches) == 1 else ""
        self._handles[handle] = {"mate": kept}
        return kept, dim

    def _gear_mate(self, handle: str, a: str, b: str, ratio: Tuple[float, float], flip: bool,
                   name: str) -> Tuple[str, str]:
        """A gear mate between two axes, ``a`` turning ``ratio[0]`` teeth to ``b``'s ``ratio[1]``.

        Probe gear_mate settled the ``swMateType_e`` value, that the ratio's
        numerator goes with the first selection, and that ``Flip`` off turns
        the gears opposite ways; without those findings this refuses rather
        than guess them. The arguments are ``AddMate5``'s own order, the gear
        ratio being the seventh and eighth, which the other mates pass as 1 and 1.
        """
        if findings.GEAR_MATE_ROUTE is None or findings.MATE_GEAR is None or findings.GEAR_MATE_NUMERATOR_FIRST is None:
            raise SolidWorksError("A gear mate has not been settled on SolidWorks yet; run the gear_mate probe first.")
        before = self._mate_names()
        self._component_ref(a, append=False)
        self._component_ref(b, append=True)
        numerator, denominator = ratio if findings.GEAR_MATE_NUMERATOR_FIRST else (ratio[1], ratio[0])
        mate, status = self._add_mate5(findings.MATE_GEAR, findings.MATE_ALIGN_CLOSEST, flip, 0.0, 0.0, 0.0,
                                       float(numerator), float(denominator), 0.0, 0.0, 0.0, False, False, 0)
        call(self._doc(), "ClearSelection2", True)
        made = [n for n in self._mate_names() if n not in before]
        if mate is None or len(made) != 1:
            raise MateRefused(f"AddMate5 would not make a gear mate between {a} and {b}.")
        kept = self._rename(self._mate_feature(made[0]), name) if name else made[0]
        self._mate_statuses[kept] = status
        self._handles[handle] = {"mate": kept}
        return kept, ""

    def _add_mate5(self, *args: Any) -> Tuple[Any, int]:
        """``AddMate5`` on what is selected, with a by-reference status as its last argument: the mate (or None)
        and the status SolidWorks wrote. pywin32 may hand back ``(mate, status)`` or the mate alone with the
        status in the out parameter; both are read, as probe tier 8's ``add_mate`` read them
        (``findings.ADD_MATE_NO_ERROR``, ``ADD_MATE_OVER_DEFINED``: a mate made over-defining is still made)."""
        status = _out_long()
        result = call(self._doc(), "AddMate5", *args, status)
        if isinstance(result, tuple):
            mate = result[0] if result else None
            return mate, _by_ref(result[1]) if len(result) > 1 else _by_ref(status)
        return result, _by_ref(status)

    @staticmethod
    def _settled(name: str, what: str, wanted: Any = None) -> Any:
        """A W5 finding, read with getattr: its value, or a sentence refusing ``what`` (nothing changed) when it is
        missing, None, or not ``wanted`` (when one is given)."""
        value = getattr(findings, name, None)
        if value is None or (wanted is not None and value != wanted):
            raise SolidWorksError(f"{what} has not been settled on SolidWorks yet (findings.{name} is {value!r}), so "
                                  "nothing is changed; run probe tier 8 first.")
        return value

    def _mate_group(self) -> List[Any]:
        """Every sub-feature of the build document's MateGroup, in tree order (``findings.MATE_FIND_ROUTE`` "mate
        group": ``FirstFeature`` → the ``MateGroup`` → ``GetFirstSubFeature`` / ``GetNextSubFeature``, as probe
        lock_mate_rename found every kind of mate by its name); ``[]`` with no MateGroup."""
        self._settled("MATE_FIND_ROUTE", "Finding a mate by its name", "mate group")
        out: List[Any] = []
        feature = call(self._doc(), "FirstFeature")
        while feature is not None:
            if _type_name(feature) == "MateGroup":
                child = call(feature, "GetFirstSubFeature")
                while child is not None:
                    out.append(child)
                    child = call(child, "GetNextSubFeature")
            feature = call(feature, "GetNextFeature")
        return out

    @staticmethod
    def _is_mate(feature: Any) -> bool:
        """Whether a MateGroup sub-feature is a mate: every mate tier 8 read had a ``GetTypeName2`` starting
        "Mate" (MateCoincident, MateDistanceDim, MateLock, MateGearDim, MatePlanarAngleDim, in probe/results), so
        anything else there — a folder — is not one (W5-INTERFACES §7 A). One whose type cannot be read counts as
        a mate, so an Update never overlooks a mate it cannot name the kind of."""
        type_name = _type_name(feature)
        return type_name == "?" or type_name.startswith("Mate")

    def _kept_mate(self, handle: str) -> Tuple[str, Any]:
        """A mate kept under ``handle`` (``add_mate`` or ``find_mate``), found again by its name: (name, feature)."""
        kept = self._handles.get(handle) if hasattr(self, "_handles") else None
        if not kept or "mate" not in kept:
            raise SolidWorksError(f"No mate is kept as {handle!r}, so it cannot be changed; that is a fault in Gear "
                                  "Generator, not in SolidWorks.")
        name = kept["mate"]
        feature = next((f for f in self._mate_group() if self._is_mate(f) and str(call(f, "Name")) == name), None)
        if feature is None:
            raise MateGone(f'The mate "{name}" is not in {call(self._doc(), "GetTitle")} any more: it was renamed or '
                           "deleted in SolidWorks.")
        return name, feature

    def _is_suppressed(self, feature: Any) -> bool:
        """``IsSuppressed2(findings.THIS_CONFIGURATION, null dispatch)``: a tuple or list back, its first item (as
        probe tier 8's ``is_suppressed`` read it)."""
        configuration = self._settled("THIS_CONFIGURATION", "Reading whether a mate is suppressed")
        value = call(feature, "IsSuppressed2", configuration, _null_dispatch())
        value = value[0] if isinstance(value, tuple) and value else value
        return bool(value[0] if isinstance(value, (list, tuple)) and value else value)

    # -- W5: the workbook gearbox that turns (docs/notes-workbook/W5-PLAN.md §1.5, W5-INTERFACES.md)
    #
    # Interfaces only, pinned in the W5 interface commit; Agent A writes each body from probe tier 8's committed
    # findings (findings.py, "the workbook gearbox that turns (tier 8)" and "tier 8 items 7-13"), each read with
    # getattr and refused with a sentence when missing. Every one runs on the worker thread, acts on the build
    # document (``_doc``), goes through ``call`` / ``_guarded`` / ``_put`` (W4's N3), and raises SolidWorksError
    # with a full sentence; none saves, closes or overwrites a document. Also Agent A's, in the existing members:
    # ``add_mate`` / ``_gear_mate`` keep AddMate5's status out-parameter by the kept name (never raising on it, so
    # the strip's pairs behave as before) and raise :class:`MateRefused` where they now raise a bare
    # SolidWorksError for "would not make".

    def _lock_mate(self, handle: str, a: str, b: str, name: str) -> Tuple[str, str]:
        """A LOCK mate between two components given as bare handles, ``a`` the anchor and ``b`` the follower
        (``findings.COMPOUND_LOCK_ROUTE`` "lock alone", ``MATE_LOCK``): ``ClearSelection2``; for ``a`` then ``b``,
        ``SelectionManager.CreateSelectData`` with ``Mark = 1`` and ``IComponent2.Select4(append, data, False)``,
        the selected count read back (``findings.LOCK_SELECT_ROUTE``); ``AddMate5(MATE_LOCK, MATE_ALIGN_CLOSEST,
        False, 0, 0, 0, 1, 1, 0, 0, 0, False, False, 0, status)``; exactly one new mate in the MateGroup, else
        :class:`MateRefused`; renamed to ``name`` when one is given (``findings.MATE_RENAME_ROUTE``); the status
        kept as for every mate. Returns ``(kept name, "")`` — a lock has no dimension."""
        self._settled("COMPOUND_LOCK_ROUTE", "Locking a compound gear to its anchor", "lock alone")
        self._settled("LOCK_SELECT_ROUTE", "Selecting two components for a lock mate",
                      "Select4 with a mark-1 select data")
        lock = self._settled("MATE_LOCK", "A lock mate's type")
        align = self._settled("MATE_ALIGN_CLOSEST", "A mate's closest alignment")
        if name:
            self._settled("MATE_RENAME_ROUTE", "Renaming a mate", "IFeature.Name put")
        components = []
        for ref in (a, b):
            kept = self._handles.get(ref, {}).get("component")
            if kept is None:
                raise SolidWorksError(f"A lock mate takes two components, and {ref!r} is not one this build placed; "
                                      "that is a fault in Gear Generator, not in SolidWorks.")
            components.append(kept)
        doc = self._doc()
        before = self._mate_names()
        call(doc, "ClearSelection2", True)
        for position, component in enumerate(components):
            data = call(call(doc, "SelectionManager"), "CreateSelectData")
            _put(data, "Mark", 1)
            count = self._selected()
            if not self._retry_select(lambda c=component, d=data, append=position > 0: call(c, "Select4", append, d,
                                                                                               False), count):
                call(doc, "ClearSelection2", True)
                raise SolidWorksError(f"{call(component, 'Name2')} could not be selected for the lock mate "
                                      f"{name or f'between {a} and {b}'} {self._selection_context()}.")
        mate, status = self._add_mate5(lock, align, False, 0.0, 0.0, 0.0, 1, 1, 0.0, 0.0, 0.0, False, False, 0)
        call(doc, "ClearSelection2", True)
        made = [n for n in self._mate_names() if n not in before]
        if mate is None or len(made) != 1:
            raise MateRefused(f"AddMate5 would not make a lock mate between {a} and {b}.")
        kept_name = self._rename(self._mate_feature(made[0]), name) if name else made[0]
        self._mate_statuses[kept_name] = status
        self._handles[handle] = {"mate": kept_name}
        return kept_name, ""

    def mate_status(self, name: str) -> Optional[int]:
        """The status out-parameter ``AddMate5`` gave when this session made the mate now called ``name``
        (``findings.ADD_MATE_NO_ERROR`` 1 is sound, ``ADD_MATE_OVER_DEFINED`` 5 made but over-defining), or None
        for a mate this session did not make. Reads nothing from SolidWorks."""
        return self._mate_statuses.get(name)

    def mate_states(self, *, others: Optional[List[str]] = None) -> List[MateState]:
        """Every mate of the build document, in tree order (``findings.MATE_FIND_ROUTE`` "mate group": walk
        ``FirstFeature`` to the ``MateGroup``, then ``GetFirstSubFeature`` / ``GetNextSubFeature``): its
        ``Name``; ``GetErrorCode2`` with a by-reference bool for ``IsWarning`` (a tuple back, or the out
        parameter's ``.value``); ``IsSuppressed2(findings.THIS_CONFIGURATION, null dispatch)`` (a tuple or list
        back: its first item). An assembly with no MateGroup has no mates: ``[]``. A sub-feature that is not a
        mate (:meth:`_is_mate`) is left out; given ``others`` (a list), each one's name is appended to it, so a
        caller can refuse what no probe has read — except a folder's two entries, ``GetTypeName2`` equal to
        ``findings.MATE_FOLDER_TYPE_NAME`` (probe round P0c, mate_folders: the folder and its "…___EndTag___"
        marker, the mates inside it listed as ordinary following siblings, so this walk still sees each one).
        Skipping is safe only because the walk still sees the mates inside (:func:`mate_folder_type`); with any
        finding it needs missing, a folder is listed like any other entry that is not a mate."""
        folder = mate_folder_type()
        out: List[MateState] = []
        for feature in self._mate_group():
            if not self._is_mate(feature):
                if others is not None and not (folder is not None and _type_name(feature) == folder):
                    others.append(str(call(feature, "Name")))
                continue
            flag = _out_bool()
            answer = call(feature, "GetErrorCode2", flag)
            if isinstance(answer, tuple):
                code = answer[0] if answer else 0
                warning = answer[1] if len(answer) > 1 else getattr(flag, "value", True)
            else:
                code, warning = answer, getattr(flag, "value", True)
            code = _by_ref(code)
            out.append(MateState(name=str(call(feature, "Name")), code=code,
                                 warning=bool(warning) if code else True, suppressed=self._is_suppressed(feature)))
        return out

    def constrained_status(self, handle: str) -> int:
        """``IComponent2.GetConstrainedStatus`` of a kept component (``add_component`` or ``find_component``'s
        handle), read and, if a method comes back, called: ``findings.COMPONENT_UNDER_DEFINED`` 2 for a gear free to
        turn, ``COMPONENT_FULLY_DEFINED`` 3, ``COMPONENT_OVER_DEFINED`` 4."""
        self._settled("COMPONENT_UNDER_DEFINED", "Reading whether a gear is free to turn")
        kept = self._handles.get(handle, {}).get("component") if hasattr(self, "_handles") else None
        if kept is None:
            raise SolidWorksError(f"No component is kept as {handle!r}, so whether it is free to turn cannot be read; "
                                  "that is a fault in Gear Generator, not in SolidWorks.")
        value = _read(kept, "GetConstrainedStatus")
        try:
            return int(value)
        except (TypeError, ValueError):
            raise SolidWorksError(f"SolidWorks answered {value!r} when asked whether {call(kept, 'Name2')} is free to "
                                  "turn, which is not a constrained status.") from None

    def find_mate(self, handle: str, name: str) -> str:
        """Find a mate of the build document by its name (``findings.MATE_FIND_ROUTE``) and keep it as ``handle``,
        so :meth:`set_mate_suppressed` and :meth:`set_gear_ratio` act on it; returns its name as read back.
        Missing: :class:`MateGone` with its sentence. A folder of the same name is not a mate (:meth:`_is_mate`)."""
        for feature in self._mate_group():
            if self._is_mate(feature) and str(call(feature, "Name")) == name:
                self._handles[handle] = {"mate": name}
                return str(call(feature, "Name"))
        raise MateGone(f'The mate "{name}" is not in {call(self._doc(), "GetTitle")} any more: it was renamed or '
                       "deleted in SolidWorks.")

    def set_mate_suppressed(self, handle: str, suppressed: bool) -> None:
        """Suppress or unsuppress a kept mate (one ``add_mate`` made under ``handle``, or ``find_mate`` found):
        ``IFeature.SetSuppression2(findings.FEATURE_SUPPRESS or FEATURE_UNSUPPRESS, THIS_CONFIGURATION, None)``
        (``findings.SUPPRESSION_ROUTE``), then ``IsSuppressed2`` read back; one that did not take raises with a
        sentence naming the mate. Does not rebuild."""
        what = "Suppressing a mate" if suppressed else "Turning a suppressed mate back on"
        self._settled("SUPPRESSION_ROUTE", what, "SetSuppression2 this configuration, None")
        action = self._settled("FEATURE_SUPPRESS" if suppressed else "FEATURE_UNSUPPRESS", what)
        configuration = self._settled("THIS_CONFIGURATION", what)
        name, feature = self._kept_mate(handle)
        call(feature, "SetSuppression2", action, configuration, None)
        if self._is_suppressed(feature) != bool(suppressed):
            title = call(self._doc(), "GetTitle")
            if suppressed:
                raise SolidWorksError(f"SolidWorks would not suppress the mate {name} in {title}: it still reads it "
                                      "turned on.")
            raise SolidWorksError(f"SolidWorks would not turn the mate {name} back on in {title}: it still reads it "
                                  "suppressed.")

    def gear_mate_ratio(self, handle: str) -> Tuple[float, float]:
        """A kept gear mate's ratio as SolidWorks holds it now, as ``(teeth of its first selection, of its second)``
        — the order ``add_mate`` and :meth:`set_gear_ratio` take it in — so Update judges a gear mate live, as it
        judges frames, never by the record (a remake lost with an unsaved close leaves the old ratio).

        Read only, by the calls the probes made: ``IFeature.GetDefinition`` (read, invoked if a method comes back),
        then its ``IGearMateFeatureData.GearRatioNumerator`` and ``GearRatioDenominator`` (likewise), which hold the
        two counts the other way round from AddMate5 (``findings.GEAR_MATE_DEFINITION_READS_NUMERATOR_SECOND``):
        probe gear_mate_ratio's remake at 17 : 60 read Numerator 60, Denominator 17. ``ModifyDefinition`` is never
        called: on SolidWorks 2024 it leaves an assembly that cannot be closed
        (``findings.MODIFIED_GEAR_MATE_CLOSES_ON_2024``). A read with no modify closed cleanly on 2024
        (probe/results/sw2024/probe-results-20261114-071324): gear_mate_ratio read the definition after the remake
        and again in the reopened train, and each time the train then closed with nothing left open; gear_mate_update
        read it in the train reopened after an unsaved close (17 : 51 back, the remake lost) and after a saved one
        (18 : 50), each left with nothing open. Missing finding, no definition or a count that is not a number: a
        sentence."""
        order = getattr(findings, "GEAR_MATE_DEFINITION_READS_NUMERATOR_SECOND", None)
        if order is None:
            raise SolidWorksError("Reading a gear mate's ratio has not been settled on SolidWorks yet "
                                  "(findings.GEAR_MATE_DEFINITION_READS_NUMERATOR_SECOND is None), so nothing is "
                                  "changed; run probe tier 8 first.")
        name, feature = self._kept_mate(handle)
        title = call(self._doc(), "GetTitle")
        data = _read(feature, "GetDefinition")
        if data is None:
            raise SolidWorksError(f"SolidWorks gave no definition for the gear mate {name} in {title}, so its ratio "
                                  "cannot be read.")
        try:
            numerator = float(_read(data, "GearRatioNumerator"))
            denominator = float(_read(data, "GearRatioDenominator"))
        except (TypeError, ValueError):
            raise SolidWorksError(f"The gear mate {name} in {title} gave a ratio that is not two numbers.") from None
        return (denominator, numerator) if order else (numerator, denominator)

    def set_gear_ratio(self, handle: str, a: str, b: str, ratio: Tuple[int, int]) -> None:
        """Give a kept gear mate a new ratio, ``ratio[0]`` the teeth of its first selection (W5-PLAN D7), by
        ``findings.GEAR_MATE_RATIO_ROUTE``. ``a`` and ``b`` are the mate's two references in its selection order,
        as ``add_mate`` takes them (``placed1:Gear Axis``, components kept by ``find_component``). ``"remake"``
        deletes it (``findings.MATE_DELETE_ROUTE``, "Select2 then EditDelete()") and makes it again between ``a``
        and ``b`` with ``AddMate5`` (``_gear_mate``: the same name, ``findings.GEAR_MATE_FLIP``), keeping
        ``handle``; None refuses with a
        sentence that changing a gear mate's ratio is not settled. ``"modify definition"`` is refused with a
        sentence too, whatever the finding says (W5-DECISIONS: it leaves an assembly SolidWorks 2024 cannot close,
        ``findings.MODIFIED_GEAR_MATE_CLOSES_ON_2024``). Does not rebuild.

        Every finding is read, and every refusal made, before the mate is touched. The remake is probe
        gear_mate_ratio's (and P1b's gear_mate_update's): ``ClearSelection2``, the mate's ``Select2(False, 0)``,
        ``EditDelete()`` (invoked: it takes no arguments, as ``FixComponent``), the name read gone from the
        MateGroup, then :meth:`_gear_mate` between ``a`` and ``b`` at ``ratio`` with ``GEAR_MATE_FLIP`` and the
        old name (``MATE_RENAME_ROUTE``), the two components found again by ``GetComponentByName`` after the
        delete, as the probe did. After the delete, whatever stops the remake says the open assembly has lost the
        gear mate and how to get it back; only SolidWorks' own refusal is a :class:`MateRefused`."""
        route = getattr(findings, "GEAR_MATE_RATIO_ROUTE", None)
        name = self._handles.get(handle, {}).get("mate", handle) if hasattr(self, "_handles") else handle
        if route is None:
            raise SolidWorksError(f"Changing a gear mate's ratio has not been settled on SolidWorks yet "
                                  f"(findings.GEAR_MATE_RATIO_ROUTE is None), so {name} keeps its ratio; build the "
                                  "gearbox again for a new tooth count.")
        if route == "modify definition":
            raise SolidWorksError(f"{name} is not given its new ratio through its definition: on SolidWorks 2024 that "
                                  "leaves an assembly that cannot be closed (findings.MODIFIED_GEAR_MATE_CLOSES_ON_2024), "
                                  "so Gear Generator never does it; build the gearbox again for a new tooth count.")
        if route != "remake":
            raise SolidWorksError(f"findings.GEAR_MATE_RATIO_ROUTE is {route!r}, which is not a way of changing a gear "
                                  f"mate's ratio this code knows, so {name} keeps its ratio; run its probe again.")
        what = "Giving a gear mate a new ratio"
        if getattr(findings, "GEAR_MATE_RATIO_REMAKE_WORKS", None) is not True:
            raise SolidWorksError(f"{what} by making it again has not been settled on SolidWorks yet "
                                  f"(findings.GEAR_MATE_RATIO_REMAKE_WORKS is "
                                  f"{getattr(findings, 'GEAR_MATE_RATIO_REMAKE_WORKS', None)!r}), so nothing is "
                                  "changed; run probe tier 8 first.")
        self._settled("MATE_DELETE_ROUTE", what, "Select2 then EditDelete()")
        self._settled("MATE_RENAME_ROUTE", what, "IFeature.Name put")
        flip = getattr(findings, "GEAR_MATE_FLIP", None)
        if flip is None or findings.GEAR_MATE_ROUTE is None or findings.MATE_GEAR is None \
                or findings.GEAR_MATE_NUMERATOR_FIRST is None:
            raise SolidWorksError(f"{what} has not been settled on SolidWorks yet (a gear mate's Flip or its ratio's "
                                  "order is not in findings.py), so nothing is changed; run probe tier 8 first.")
        name, feature = self._kept_mate(handle)
        doc = self._doc()
        title = call(doc, "GetTitle")
        refs = []                                  # (handle, the Name2 to find it by again after the delete)
        for ref in (a, b):
            kept = self._handles.get(ref.partition(":")[0], {}).get("component")
            if kept is None:
                raise SolidWorksError(f"A gear mate is made between two components, and {ref!r} is not one this job "
                                      "found, so nothing is changed; that is a fault in Gear Generator, not in "
                                      "SolidWorks.")
            refs.append((ref.partition(":")[0], str(call(kept, "Name2"))))
        call(doc, "ClearSelection2", True)
        call(feature, "Select2", False, 0)
        _guarded("EditDelete", lambda: doc.EditDelete())
        call(doc, "ClearSelection2", True)
        if name in self._mate_names():
            raise SolidWorksError(f"SolidWorks would not delete the gear mate {name} in {title} to give it its new "
                                  "ratio, so it keeps its old one.")
        lost = f"The open {title} has lost the gear mate {name}: it was deleted to give it its new ratio"
        restore = f"The saved {title} still has it: close {title} in SolidWorks without saving to bring it back."
        try:
            # As the probe's remake (gear_mate_ratio, P1b): the two components found again by GetComponentByName
            # after the delete, then the gear mate made between them.
            for ref, component_name in refs:
                found = call(doc, "GetComponentByName", component_name)
                if found is None:
                    raise SolidWorksError(f"{component_name} could not be found again in {title} after the delete.")
                self._handles[ref] = dict(self._handles[ref], component=found)
            kept, _ = self._gear_mate(handle, a, b, (float(ratio[0]), float(ratio[1])), bool(flip), name)
        except MateRefused as exc:              # SolidWorks' own refusal: the one failure that is a MateRefused
            raise MateRefused(f"{lost}, and SolidWorks would not make it again. {restore} {_as_sentence(exc)}") \
                from None
        except Exception as exc:  # noqa: BLE001 - a COM or selection failure: an ordinary failure, still said
            raise SolidWorksError(f"{lost}, and making it again stopped. {restore} {_as_sentence(exc)}") from exc
        if kept != name:
            raise SolidWorksError(f"The open {title} has lost the gear mate {name} by that name: it was made again with "
                                  f"its new ratio, and SolidWorks named it {kept}. {restore}")

    def set_custom_property(self, name: str, value: str) -> None:
        """A text custom property on the build's part, added or replaced, and read back.

        Probe custom_properties settled ``Add3``'s type and option (from
        swconst.tlb) and the read that gives a value back; without those
        findings this refuses rather than guess.
        """
        if findings.CUSTOM_PROPERTY_ROUTE is None or findings.CUSTOM_INFO_TEXT is None:
            raise SolidWorksError("Custom properties have not been settled on SolidWorks yet; "
                                  "run the custom_properties probe first.")
        manager = call(call(self._doc(), "Extension"), "CustomPropertyManager", "")
        if manager is None:
            raise SolidWorksError(f"{call(self._doc(), 'GetTitle')} has no custom property manager.")
        call(manager, "Add3", name, findings.CUSTOM_INFO_TEXT, value, findings.CUSTOM_PROPERTY_REPLACE)
        if findings.PROPERTY_READ_ROUTE == "Get":
            kept = call(manager, "Get", name)
        else:
            out = _out_text()
            call(manager, "Get6", name, False, out, _out_text(), _out_bool(), _out_bool())
            kept = out.value
        if str(kept) != value:
            raise SolidWorksError(f"The custom property {name!r} reads back {kept!r}, not {value!r}.")

    def interference_count(self) -> Tuple[int, float]:
        """How many interferences the build's assembly has, and their volume in mm³.

        Probe interference, SolidWorks 2026: two cylinders overlapping by a lens
        counted one interference of exactly the lens's volume, and none apart.
        ``GetInterferenceCount``, ``GetInterferences`` and ``Volume`` are
        property gets through late binding; ``Done`` is a method, and is called
        whatever the count came to.
        """
        doc = self._doc()
        manager = call(doc, "InterferenceDetectionManager")
        if manager is None:
            raise SolidWorksError(f"{call(doc, 'GetTitle')} has no interference detection manager.")
        for name, value in findings.INTERFERENCE_OPTIONS:
            setattr(manager, name, value)
        try:
            count = int(call(manager, "GetInterferenceCount"))
            items = list(call(manager, "GetInterferences") or ())
            volume = sum(float(call(item, "Volume")) for item in items) * 1e9
        finally:
            manager.Done()
        return count, volume

    def component_translation(self, handle: str) -> Tuple[float, float, float]:
        data = call(call(self._handles[handle]["component"], "Transform2"), "ArrayData")
        return (float(data[9]) * MM_PER_METRE, float(data[10]) * MM_PER_METRE, float(data[11]) * MM_PER_METRE)

    # -- W4: a workbook's layout part and static assembly (docs/PLAN-WORKBOOK.md §4.2–§4.5)
    #
    # Written from probe tier 7 (p7_workbook.py), which agreed on SolidWorks 2026 (34.0.0) and 2024 (32.5.0); each finding is read with getattr
    # so a finding not (yet) in findings.py is refused with a sentence rather than guessed. Every one runs on the
    # worker thread, takes and returns millimetres, and raises SolidWorksError with a full sentence; none ever
    # closes, saves or overwrites a document.

    def _open_documents(self) -> List[Any]:
        return self._walk_documents()

    def open_document(self, path: str) -> DocInfo:
        """Open a saved part or assembly by path, make it the active document and this session's build document.

        Probe open_and_activate_part, SolidWorks 2026 (34.0.0) and 2024 (32.5.0) alike:
        ``OpenDoc6(path, type, swOpenDocOptions_Silent 1, "", out errors, out
        warnings)`` returned the document itself (not a tuple) with errors 0
        and made a closed part active over another document; on a part already
        open it returned the same document with warning 128
        (``OPEN_DOC_ALREADY_OPEN_WARNING``) and did *not* bring it forward, so
        ``ActivateDoc3`` always follows. Probe open_part_from_assembly: the
        same for a part loaded only as a component of an open assembly. Probe
        layout_assembly_reopen: an assembly by the same call
        (``OPEN_ASSEMBLY_ROUTE``), every component fully resolved. The route
        is ``findings.OPEN_DOC_ROUTE`` (an assembly's ``OPEN_ASSEMBLY_ROUTE``),
        any of :data:`OPEN_ROUTES` (OpenDoc7 and OpenDoc as the probe tried
        them, UNVERIFIED: neither has opened a document for the app). With
        ``UPDATE_OPEN_ROUTE`` "ask" nothing is opened: the document must
        already be open, and is only activated.

        Run through the app on SolidWorks 2026 (34.0.0, probe/gearbox_smoke.py
        2026-11-13): closed parts, a layout part and an assembly opened and
        activated, and an assembly already open (a component "dragged" in it)
        opened again and brought forward, each then changed by Update.

        A document of the same file name open from another folder is refused
        before anything is asked, naming both paths (gearbox_smoke: refused,
        with OpenDoc6 never called): probe
        add_component_same_name_elsewhere saw ``OpenDoc6`` answer it with no
        document and error ``SAME_NAME_OPEN_ERROR`` (65536,
        swFileWithSameTitleAlreadyOpen), which is worded the same way if it
        happens anyway. The active document's path is read back and compared;
        then ``_build_doc`` is this document, so ``equations``,
        ``set_global_variable``, ``rebuild`` and ``find_component`` act on it.
        """
        lowered = str(path).lower()
        if not lowered.endswith((".sldprt", ".sldasm")):
            raise SolidWorksError(f"{path} is neither a SolidWorks part nor an assembly, so it is not opened.")
        doc_type = DOC_ASSEMBLY if lowered.endswith(".sldasm") else DOC_PART
        how = getattr(findings, "UPDATE_OPEN_ROUTE", None)
        if how not in UPDATE_OPEN_ROUTES:
            raise SolidWorksError(f"Opening {_base_name(path)} by its path has not been settled on SolidWorks "
                                  f"yet (findings.UPDATE_OPEN_ROUTE is {how!r}); run probe tier 7 first.")
        for other in self._open_documents():
            other_path = str(call(other, "GetPathName") or "")
            if other_path and _file_name(other_path) == _file_name(path) and not same_path(other_path, path):
                raise SolidWorksError(self._same_name_sentence(other_path, path))
        if how == "ask":
            doc = next((d for d in self._open_documents() if same_path(str(call(d, "GetPathName") or ""), path)),
                       None)
            if doc is None:
                raise SolidWorksError(f"Open {path} in SolidWorks, then try again: this SolidWorks cannot be asked "
                                      "to open a document by its path (findings.UPDATE_OPEN_ROUTE).")
        else:
            doc = self._open_by_route(path, doc_type)
        info = self._describe(doc)
        if not same_path(info.path, path):
            raise SolidWorksError(f"SolidWorks opened {info.path or info.title} when asked for {path}.")
        if info.doc_type != doc_type:
            noun = "an assembly" if doc_type == DOC_ASSEMBLY else "a part"
            raise SolidWorksError(f"{path} opened as a document of type {info.doc_type}, not as {noun}.")
        call(self._app, "ActivateDoc3", info.title, False, 0, _out_long())
        active = call(self._app, "ActiveDoc")
        active_path = "" if active is None else str(call(active, "GetPathName") or "")
        if not same_path(active_path, path):
            now = "nothing" if active is None else str(call(active, "GetTitle"))
            raise SolidWorksError(f"SolidWorks opened {info.title} but left {now} active after ActivateDoc3, so "
                                  "it is not changed.")
        self._build_doc = doc
        return info

    @staticmethod
    def _same_name_sentence(open_path: str, path: str) -> str:
        title = _base_name(open_path)
        return (f"{open_path} is open in SolidWorks, and it has the same file name as {path}; SolidWorks keeps one "
                f"document per file name, so close {title} in SolidWorks and try again.")

    def _open_by_route(self, path: str, doc_type: int) -> Any:
        """``OpenDoc6`` (or the route the finding names), silently; the document, or a sentence."""
        name = "OPEN_ASSEMBLY_ROUTE" if doc_type == DOC_ASSEMBLY else "OPEN_DOC_ROUTE"
        route = getattr(findings, name, None)
        silent = getattr(findings, "OPEN_DOC_SILENT", None)
        if route not in OPEN_ROUTES or (route == "OpenDoc6" and silent is None):
            raise SolidWorksError(f"Opening {_base_name(path)} by its path has not been settled on SolidWorks "
                                  f"yet (findings.{name} is {route!r}); run probe tier 7 first.")
        error = 0
        if route == "OpenDoc6":
            errors, warnings = _out_long(), _out_long()
            result = call(self._app, "OpenDoc6", path, doc_type, silent, "", errors, warnings)
            if isinstance(result, tuple) and len(result) >= 2:
                error = _by_ref(result[1])
            else:
                error = _by_ref(errors)
        elif route == "OpenDoc7":
            spec = call(self._app, "GetOpenDocSpec", path)
            _put(spec, "Silent", True)
            result = call(self._app, "OpenDoc7", spec)
            error = _by_ref(getattr(spec, "Error", 0))
        else:
            result = call(self._app, "OpenDoc", path, doc_type)
        doc = _doc_of(result)
        same_name = getattr(findings, "SAME_NAME_OPEN_ERROR", None)
        if same_name and error & same_name == same_name:
            raise SolidWorksError(f"SolidWorks would not open {path}: a document of the same file name is open "
                                  f"from another folder (error {error}); close it in SolidWorks and try again.")
        if doc is None or error:
            raise SolidWorksError(f"SolidWorks would not open {path} (error {error}).")
        return doc

    def find_component(self, handle: str, name: str, *, lightweight_ok: bool = False) -> str:
        """Find a component of the build's assembly by the ``Name2`` recorded when it was inserted, and keep it as
        ``handle`` (so ``place_component``, ``fix_component``, ``unfix_component`` and ``component_frame`` work on
        it). Returns ``Name2`` as read back.

        Probe layout_assembly_reopen, SolidWorks 2026 (34.0.0) and 2024 (32.5.0): five
        components saved, closed and reopened by ``OpenDoc6`` were each found by
        ``IAssemblyDoc.GetComponentByName``, and by every other route in
        :data:`COMPONENT_FIND_ROUTES` (``GetComponents(True)``, the root
        component's ``GetChildren``, ``FeatureByName`` then
        ``GetSpecificFeature2``); ``findings.COMPONENT_FIND_ROUTE`` names the
        one taken. Each came back fully resolved (``GetSuppression2`` 2,
        ``COMPONENTS_RESOLVED_AFTER_REOPEN``), so none is resolved here; but a
        user's 2024 may open components lightweight, and resolving one is not
        probed, so the state is read and a suppressed or lightweight
        component is refused with what to do. Through the app on 2026
        (gearbox_smoke 2026-11-13): five components of a reopened assembly
        found by GetComponentByName, each state read without error.

        ``lightweight_ok`` (keyword): the lightweight refusal is left to the caller, which then reads
        :meth:`component_resolved` itself (a turning Update's check phase, with its own sentence); a suppressed
        component is refused all the same.
        """
        route = getattr(findings, "COMPONENT_FIND_ROUTE", None)
        if route not in COMPONENT_FIND_ROUTES:
            raise SolidWorksError(f"Finding {name} in a saved assembly has not been settled on SolidWorks yet "
                                  f"(findings.COMPONENT_FIND_ROUTE is {route!r}); run probe tier 7 first.")
        doc = self._doc()
        title = str(call(doc, "GetTitle"))
        component = self._component_by(route, doc, name)
        if component is None:
            raise ComponentGone(f"{name} is not in {title} any more: it was renamed or deleted in SolidWorks.")
        kept = str(call(component, "Name2"))
        if kept != name:
            raise SolidWorksError(f"Asked for {name} in {title}, SolidWorks gave {kept}, so which component is meant "
                                  "cannot be told.")
        try:
            state: Optional[int] = int(_read(component, "GetSuppression2"))
        except Exception:  # noqa: BLE001 - unread is judged by the finding below
            state = None
        if state == COMPONENT_SUPPRESSED:
            raise SolidWorksError(f"{name} is suppressed in {title}, so it cannot be placed; unsuppress it in "
                                  "SolidWorks and try again.")
        if not lightweight_ok and (state in COMPONENT_LIGHTWEIGHT or (
                state is None and getattr(findings, "COMPONENTS_RESOLVED_AFTER_REOPEN", None) is not True)):
            raise SolidWorksError(f"{name} is loaded lightweight in {title}, and resolving a component is not "
                                  "settled here; set it to Resolved in SolidWorks and try again.")
        self._handles[handle] = {"component": component, "path": self._component_path(component)}
        return kept

    def component_resolved(self, handle: str) -> bool:
        """Whether a kept component is fully resolved, read by the route probe round P0d settles
        (:data:`RESOLVED_ROUTE_FINDING`, one of :data:`RESOLVED_ROUTES`) and judged by its fully-resolved values
        (:data:`RESOLVED_VALUES_FINDING`). P0c drove a train whose components were lightweight and one gear turned
        -24° where 2.5° was right, so a turning Update reads this before anything changes. Either finding missing,
        or a route this code does not know: a sentence (callers read it only when the route finding is set)."""
        route = getattr(findings, RESOLVED_ROUTE_FINDING, None)
        values = getattr(findings, RESOLVED_VALUES_FINDING, None)
        if route not in RESOLVED_ROUTES or not values:
            raise SolidWorksError(f"Reading whether a component is fully resolved has not been settled on SolidWorks "
                                  f"yet (findings.{RESOLVED_ROUTE_FINDING} is {route!r}, findings."
                                  f"{RESOLVED_VALUES_FINDING} is {values!r}), so nothing is changed; run its probe "
                                  "first.")
        kept = self._handles.get(handle, {}).get("component") if hasattr(self, "_handles") else None
        if kept is None:
            raise SolidWorksError(f"No component is kept as {handle!r}, so whether it is resolved cannot be read; that "
                                  "is a fault in Gear Generator, not in SolidWorks.")
        value = _read(kept, route)
        try:
            return int(value) in tuple(int(v) for v in values)
        except (TypeError, ValueError):
            raise SolidWorksError(f"SolidWorks answered {value!r} when asked whether {call(kept, 'Name2')} is "
                                  "resolved, which is not a state this code knows.") from None

    @staticmethod
    def _component_by(route: str, doc: Any, name: str) -> Any:
        """A component of ``doc`` called ``name`` by one route of :data:`COMPONENT_FIND_ROUTES`, or None."""
        def by_name2(listed: Any) -> Any:
            return next((c for c in list(listed or ()) if str(call(c, "Name2")) == name), None)

        if route == COMPONENT_FIND_ROUTES[0]:
            return call(doc, "GetComponentByName", name)
        if route == COMPONENT_FIND_ROUTES[1]:
            return by_name2(call(doc, "GetComponents", True))
        if route == COMPONENT_FIND_ROUTES[2]:
            root = call(_read(doc, "GetActiveConfiguration"), "GetRootComponent3", True)
            return None if root is None else by_name2(_read(root, "GetChildren"))
        feature = call(doc, "FeatureByName", name)
        return None if feature is None else call(feature, "GetSpecificFeature2")

    def component_frame(self, handle: str) -> Tuple[Tuple[float, ...], Tuple[float, float, float]]:
        """A kept component's frame as ``place_component`` takes it: the rotation's 9 numbers by rows, and its
        origin in mm.

        ``IComponent2.Transform2.ArrayData``: 9 rotation numbers, then the
        translation in metres. Probe nonparallel_mates, SolidWorks 2026: the
        rotation is in columns (``findings.TRANSFORM_ARRAY_ORDER``), as
        ``place_component`` writes it; probe layout_assembly_reopen read frames
        back this way to 2e-16 after a save and reopen. Through the app on 2026
        (gearbox_smoke 2026-11-13) every frame read back equal to what
        ``place_component`` put, to 1e-6, before and after a save and reopen.
        "rows" is taken as it says, should a version ever answer so.
        """
        order = getattr(findings, "TRANSFORM_ARRAY_ORDER", None)
        if order not in TRANSFORM_ORDERS:
            raise SolidWorksError(f"How SolidWorks lays out a component's frame has not been settled "
                                  f"(findings.TRANSFORM_ARRAY_ORDER is {order!r}); run the probe first.")
        component = self._handles[handle]["component"]
        data = [float(v) for v in call(call(component, "Transform2"), "ArrayData")]
        if len(data) < 12:
            raise SolidWorksError(f"The frame of {call(component, 'Name2')} has {len(data)} numbers, not 16.")
        if order == "columns":
            rotation = tuple(data[j * 3 + i] for i in range(3) for j in range(3))
        else:
            rotation = tuple(data[:9])
        return rotation, (data[9] * MM_PER_METRE, data[10] * MM_PER_METRE, data[11] * MM_PER_METRE)

    def interferences(self) -> List[Tuple[Tuple[str, ...], float]]:
        """Every interference in the build's assembly: the ``Name2`` of each component in it, and its volume in mm³.

        As :meth:`interference_count` (probe interference: the options, then
        ``GetInterferences`` and ``IInterference.Volume`` in m³ read as
        properties, and ``Done``, a method, whatever happens). Probe
        interference_components, SolidWorks 2026 and 2024: ``IInterference.Components``
        read as a property gave a tuple of the two components, whose ``Name2``
        named the two overlapping cylinders and not a third clear of them
        (``findings.INTERFERENCE_NAMES_ROUTE`` "Components (property)"; the
        probe's other route, "GetComponents()", is taken if a version answers
        so, UNVERIFIED). Where the names cannot be read — no route, or the read
        fails — they are ``()`` and only the volume is given.

        One interference is one region of contact, not one pair: on 2026
        (gearbox_smoke 2026-11-13) a 24-tooth gear turned half a pitch against
        a 16-tooth one gave three, each naming the same two components (and
        never the body-less layout); ``swbuild`` merges them.
        """
        route = getattr(findings, "INTERFERENCE_NAMES_ROUTE", None) or ""
        doc = self._doc()
        manager = call(doc, "InterferenceDetectionManager")
        if manager is None:
            raise SolidWorksError(f"{call(doc, 'GetTitle')} has no interference detection manager.")
        out: List[Tuple[Tuple[str, ...], float]] = []
        try:
            for name, value in findings.INTERFERENCE_OPTIONS:
                setattr(manager, name, value)
            for item in list(call(manager, "GetInterferences") or ()):
                out.append((self._interference_names(item, route), float(call(item, "Volume")) * 1e9))
        finally:
            manager.Done()
        return out

    @staticmethod
    def _interference_names(item: Any, route: str) -> Tuple[str, ...]:
        try:
            if route.startswith("Components"):
                listed = _read(item, "Components")
            elif route.startswith("GetComponents"):
                listed = _read(item, "GetComponents")
            else:
                return ()
            return tuple(str(call(component, "Name2")) for component in list(listed or ()))
        except Exception:  # noqa: BLE001 - unnamed is an answer: the volume still says there is a clash
            return ()


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
                CONNECTION.lost = False
                try:
                    if self._session is None:
                        self._session = self._connect()
                    value = work(self._session)
                    if CONNECTION.lost:
                        # The job turned the lost connection into a failure on its result (a build keeps what it
                        # saved), so nothing raised here: drop the session anyway, and the next job attaches afresh.
                        self._session = None
                    outbox.put((value, None))
                except BaseException as exc:  # noqa: BLE001 - reported, never swallowed
                    self._session = None
                    outbox.put((None, exc))
                finally:
                    CONNECTION.lost = False
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
