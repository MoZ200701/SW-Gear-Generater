"""The build's order, against a fake SolidWorks that records every call."""

import copy
import math
from dataclasses import dataclass

import pytest

from gear_generator import findings, swbuild, swcom
from gear_generator.gears import KINDS
from gear_generator.gears.base import BuildPlan, CloseSketch, Dimension, LinkDimension, SaveAs
from gear_generator.gears.equations import DEGREES, RADIANS, split_equation
from gear_generator.spec import GearSpec
from gear_generator.swcom import ComponentGone, DocInfo, SolidWorksError

SPUR = KINDS["spur"]
PATH = r"C:\Gears\Gear_m1.5_N25.SLDPRT"


def _key(path):
    return path.replace("/", "\\").lower()


@dataclass
class FakeMate:
    """One mate the fake holds (W5-PLAN §3.1): ``a`` and ``b`` are ``(component Name2, target)`` — ``("asm",
    "plane2")`` for the assembly's own plane, target ``""`` for a lock's bare component — ``link`` the global its
    D1 is linked to, ``status`` what AddMate5 answered, ``code``/``warning`` what GetErrorCode2 reads."""

    name: str
    kind: str
    a: tuple
    b: tuple
    value: float = 0.0
    ratio: tuple = (1.0, 1.0)
    flip: bool = False
    link: str = ""
    suppressed: bool = False
    status: int = 1
    code: int = 0
    warning: bool = True

    @property
    def axis(self):
        """An anchor's axis mate: a coincident between two axes of two components (the gear's, the layout's)."""
        return (self.kind == "coincident" and "asm" not in (self.a[0], self.b[0])
                and self.a[1].endswith("Axis") and self.b[1].endswith("Axis"))

    @property
    def along(self):
        """An anchor's place along its shaft: its origin on, or at a distance from, a component's plane."""
        return self.kind in ("point", "point distance") and self.a[1] == "origin" and self.b[0] != "asm"


IDENTITY9 = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _rot_z(degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (c, -s, 0.0, s, c, 0.0, 0.0, 0.0, 1.0)


def _mul(r1, r2):
    return tuple(sum(r1[i * 3 + k] * r2[k * 3 + j] for k in range(3)) for i in range(3) for j in range(3))


def _apply(r, v):
    return tuple(sum(r[i * 3 + k] * v[k] for k in range(3)) for i in range(3))


def _compose(f1, f2):
    """``f1 ∘ f2`` for frames (rotation by rows, origin): ``v ↦ R1 (R2 v + t2) + t1``."""
    (r1, t1), (r2, t2) = f1, f2
    moved = _apply(r1, t2)
    return _mul(r1, r2), tuple(moved[i] + t1[i] for i in range(3))


def _inverse(f):
    r, t = f
    rt = tuple(r[j * 3 + i] for i in range(3) for j in range(3))
    back = _apply(rt, t)
    return rt, tuple(-x for x in back)


def _frame_off(f1, f2):
    """(largest rotation-entry difference, largest origin difference in mm) between two frames."""
    return (max(abs(a - b) for a, b in zip(f1[0], f2[0])), max(abs(a - b) for a, b in zip(f1[1], f2[1])))


class FakeSolidWorks:
    """Records every call. ``fail_on`` maps a call's name to a sentence it raises (or ``(arg, sentence)`` to
    raise only when that argument is passed).

    W4's members are configurable from the start: ``open_docs`` are the
    documents open before the job (``documents()``), and a document saved or
    opened joins them (``close_all`` empties them, as closing SolidWorks
    without saving would); ``saved`` is each file as saved and ``memory``
    each open document as it is now, so a change not saved is lost when it
    is closed, and ``has_unsaved_changes`` (``GetSaveFlag``) reads whether
    the document just opened differs from its file; a saved document keeps
    its globals and the planes and axes it made, and ``open_document`` brings
    them back, so ``planned_changes`` and ``feature_names`` see what a build
    left; ``missing_components`` are Name2s ``find_component`` will not find;
    ``frames`` maps a handle to the (rotation, at) ``component_frame`` reads,
    and ``place_component`` writes it; ``clashes`` is what ``interferences()``
    returns.

    For W4's own tests: ``frames`` may also be keyed by a component's Name2
    (what ``find_component`` was asked for), and ``place_component`` writes
    both; ``exists`` answers "is it on disk" from what was saved (or put in
    ``saved`` by a test), so a job's pre-flight sees what an earlier job left.

    For the W4 review's: ``raises`` maps a call's name to ``(n, exception)``:
    the n-th call of that name raises that exception, whatever its type (a
    stand-in for ``pywintypes.com_error`` or anything unexpected, part-way
    through a job). ``touched`` collects the saved documents (lower-cased
    paths) a call has modified since they were opened — an equation added or
    deleted (the trig check), a global set, a component moved, a rebuild —
    so a test can see which documents SolidWorks would now mark modified.
    Every feature a build makes (not only planes and axes) is kept with the
    saved document, so ``feature_names`` on a reopened part lists them.

    Rebuilding, as probe assembly_rebuild_scope found it on SolidWorks 2026
    and 2024: ``rebuild`` (and the rebuild ``place_component`` makes of its
    own) asks :func:`swcom.rebuild_call` for the member, as ``Session`` does,
    and acts as SolidWorks did. On a part it marks the part. On an assembly
    (a new one, or a saved ``.sldasm``) it marks the assembly, and a FULL
    rebuild (``ForceRebuild3(False)``) marks every component document too
    (``assembly_components`` keeps each saved assembly's inserted paths); any
    component in ``failed_documents`` makes it return False, top-only or not.
    A put alone marks nothing (``findings.PUT_MARKS_ASSEMBLY_MODIFIED``).
    Running interference detection marks the assembly (the probe saw the
    reads after a put mark it, frame reads and the check together; which of
    them is not isolated, and the fake pins it on the check). The kind each rebuild
    was asked for (``kind``) and the member it took are kept in
    ``rebuild_kinds`` and ``rebuild_members``. Nothing unprobed is modelled:
    not a rebuild under ``CommandInProgress``, not what a top-only rebuild
    does to mates.

    W5, the train's mates (W5-PLAN §3.1 as W5-DECISIONS rules it). ``add_mate`` keeps a :class:`FakeMate` per
    mate in the document it is made in — saved with it, back on ``open_document``, lost by ``close_all`` unless
    saved — keyed by the components' Name2s. Its AddMate5 status is 1, or 5 with code 46 (``warning`` False on the
    new mate, True on those it fights) when: a lock's follower already has an axis or along mate; an axis or
    along mate is added to a lock follower; a second axis mate goes on one component; or a gear mate joins two
    bodies (components locked together are one) already joined through gear mates. ``mate_status``,
    ``mate_states``, ``constrained_status`` (4 for a component in a flagged mate, 3 if fixed, else 2),
    ``find_mate`` (``MateGone`` when the mate is not there), ``set_mate_suppressed`` and ``set_gear_ratio`` (the
    remake: the mate goes to the end of the tree under its old name; any other route refused as swcom refuses
    it) answer from those. Overrides doctor them per test: ``mate_statuses={name: n}``, ``mate_codes={name:
    (code, warning)}``, ``constrained={Name2 or handle: n}``. So a default ``FakeSolidWorks()`` answers clean
    mate states for an undoctored plan. ``link_dimension`` remembers which global a mate's D1 is linked to.

    A rebuild of an assembly holding mates (``rebuild`` and every put's own) solves them as far as the fake can:
    each anchor with an unsuppressed axis mate goes to its shaft's axis as the layout document's ``"<Shaft> X"``
    / ``"<Shaft> Y"`` globals now say (0 where there is none: a base-side shaft), and along it to its Face Z
    global (or the mate's value) — signed as the mate was made — turned 13° the wrong way about its own axis if
    its X/Y moved (standing in for SolidWorks' swing); a follower under an unsuppressed lock keeps its frame
    relative to its anchor through that. ``place_component`` reads the frame back after its rebuild and raises
    as ``swcom.place_component`` would when a mate pulled the gear off it. A put on a gear held by an
    unsuppressed lock moves that gear alone, leaves its partner where it was and reports nothing, as SolidWorks
    did (W5-DECISIONS, "a lock does not hold against a put"); ``locked_puts`` lists each such put, so a test
    catches app code that puts with a lock on. ``slips`` (Name2s) turns those gears 5° on every later
    ``rebuild()`` of the assembly: a put that does not hold. Nothing else is solved: a gear mate turns nothing
    (no solver, no drive, no drag).
    """

    def __init__(self, trig=DEGREES, fail_on=None, rename=None, rebuild_ok=True, statuses=None, values=None,
                 interference=(0, 0.0), open_docs=(), missing_components=(), frames=None, clashes=(), raises=None,
                 failed_documents=(), mate_statuses=None, mate_codes=None, constrained=None):
        self.interference = interference
        self.revision = (34, 0, 0)
        self.calls = []
        self.trig = trig
        self.fail_on = fail_on or {}
        self.rename = rename or {}
        self.rebuild_ok = rebuild_ok
        self.statuses = statuses or {}
        self.values_override = values or {}
        self.suppressed = False
        self.equations_text = []
        self.active = None
        self.handles = set()
        self.open_docs = list(open_docs)
        self.missing_components = set(missing_components)
        self.frames = dict(frames or {})
        self.clashes = list(clashes)
        self.made = []                 # planes and axes made in the current document, by kept name
        self.saved = {}                # lower-cased path -> (equations_text, made) as saved: the file
        self.memory = {}               # lower-cased path -> (equations_text, made) as open in SolidWorks now
        self.found = {}                # handle -> the Name2 find_component found it by
        self.raises = dict(raises or {})
        self.counts = {}
        self.current = ""              # the document calls act on: an opened or saved path, "" for a new one
        self.touched = set()
        self.kind = 1                  # the GetType of a new document: 1 part, 2 assembly
        self.adding = []               # the paths inserted into the new assembly so far
        self.assembly_components = {}  # lower-cased .sldasm path -> the paths it was saved with
        self.failed_documents = {_key(p) for p in failed_documents}
        self.rebuild_kinds = []        # the ``kind`` each rebuild was asked with
        self.rebuild_members = []      # what rebuild_call gave each rebuild, a put's own included
        self.assembly_kinds = []       # the ``kind`` each assembly rebuild (a put's own included) was asked with
        # W5
        self.mates = []                # the current document's FakeMates, in tree order
        self.saved_mates = {}          # lower-cased path -> its mates as saved
        self.memory_mates = {}         # lower-cased path -> its mates as open in SolidWorks now
        self.component_names = {}      # handle -> the Name2 add_component gave or find_component found
        self.component_paths = {}      # Name2 -> the file it was inserted from
        self.fixed = set()             # Name2s fixed in place
        self.mate_handles = {}         # handle -> the mate name add_mate made or find_mate found under it
        self.mate_statuses = dict(mate_statuses or {})
        self.mate_codes = dict(mate_codes or {})
        self.constrained = dict(constrained or {})
        self.locked_puts = []          # Name2s put while an unsuppressed lock held them
        self.slips = set()

    def _log(self, name, *args):
        self.calls.append((name, args))
        self.counts[name] = self.counts.get(name, 0) + 1
        planned = self.raises.get(name)
        if planned is not None and planned[0] == self.counts[name]:
            raise planned[1]
        reason = self.fail_on.get(name)
        if reason and (not isinstance(reason, tuple) or reason[0] in args):
            raise SolidWorksError(reason if isinstance(reason, str) else reason[1])

    def active_document(self):
        return self.active

    def begin_build(self):
        self._log("begin_build")

    def end_build(self):
        self._log("end_build")

    def _touch(self):
        if self.current:
            self.touched.add(_key(self.current))

    def new_part(self, template=""):
        self._log("new_part", template)
        self.equations_text, self.made, self.current = [], [], ""
        self.kind, self.mates = 1, []
        return DocInfo(title="Part1", path="", doc_type=1)

    def new_assembly(self, template=""):
        self._log("new_assembly", template)
        self.equations_text, self.made, self.current = [], [], ""
        self.kind, self.adding, self.mates = 2, [], []
        return DocInfo(title="Assem1", path="", doc_type=2)

    def document_path(self):
        return ""

    def set_rebuild_suppressed(self, suppressed):
        self._log("suppress", suppressed)
        self.suppressed = suppressed

    def rebuild(self, kind=None):
        self._log("rebuild", self.suppressed)
        self.rebuild_kinds.append(kind)
        rebuilt = self._rebuilt(kind)
        if self.slips and self._is_assembly() and self.mates:
            for name in sorted(self.slips):
                self.turn(name, 5.0)
        return rebuilt

    def _is_assembly(self):
        return self.current.lower().endswith(".sldasm") if self.current else self.kind == 2

    def _rebuilt(self, kind=None):
        """What a rebuild of the current document does to the marks, and what it returns (see the class)."""
        from gear_generator import swcom
        member, args = swcom.rebuild_call(swcom.DOC_ASSEMBLY if self._is_assembly() else swcom.DOC_PART, kind)
        self.rebuild_members.append((member, args))
        if self._is_assembly():
            self.assembly_kinds.append(kind)
        self._touch()
        if not self._is_assembly():
            return self.rebuild_ok
        components = self.assembly_components.get(_key(self.current), []) if self.current else self.adding
        if (member, args) == ("ForceRebuild3", (False,)):
            self.touched.update(_key(p) for p in components)
        if self.mates:
            self._solve()
        if any(_key(p) in self.failed_documents for p in components):
            return False
        return self.rebuild_ok

    def save_as(self, path):
        self._log("save_as", path)
        self.saved[_key(path)] = (list(self.equations_text), list(self.made))
        self.memory[_key(path)] = (self.equations_text, self.made)
        self.saved_mates[_key(path)] = copy.deepcopy(self.mates)
        self.memory_mates[_key(path)] = self.mates
        if path.lower().endswith(".sldasm"):
            self.saved_frames = dict(self.frames)        # where the components are in the file
            if not self.current:
                self.assembly_components[_key(path)] = list(self.adding)
        self.current = path
        self.touched.discard(_key(path))
        if not any(_key(d.path) == _key(path) for d in self.open_docs):
            # A document a build saves stays open in SolidWorks (nothing is closed), as on 2026 and 2024.
            self.open_docs.append(DocInfo(title=path.replace("/", "\\").rsplit("\\", 1)[-1], path=path,
                                          doc_type=2 if path.lower().endswith(".sldasm") else 1))
        return path

    def close_all(self):
        """SolidWorks closed without saving (or every document closed): nothing is open, and what a document held
        in memory since its last save is gone — reopened, it holds its file again."""
        self.open_docs = []
        self.memory = {}
        self.memory_mates = {}
        self.touched.clear()
        self.frames = dict(getattr(self, "saved_frames", self.frames))

    def detect_trig_units(self):
        self._log("detect_trig_units")
        self._touch()                  # it adds an equation and deletes it: SolidWorks marks the document modified
        return self.trig

    def add_global_variable(self, name, expression):
        self._log("add_global_variable", name, expression)
        self.equations_text.append(f'"{name}"= {expression}')
        return len(self.equations_text) - 1

    def set_global_variable(self, name, expression):
        self._log("set_global_variable", name, expression)
        self._touch()
        for i, text in enumerate(self.equations_text):
            if split_equation(text)[0] == name:
                self.equations_text[i] = f'"{name}"= {expression}'

    def link_dimension(self, dimension, expression):
        self._log("link_dimension", dimension, expression)
        owner = dimension.partition("@")[2]
        for mate in self.mates:
            if mate.name == owner:
                mate.link = expression.replace('"', "").strip()
        return 0

    def equations(self):
        return [(text, 0.0) for text in self.equations_text]

    def equation_values(self):
        from gear_generator.gears.equations import evaluate_all
        values = evaluate_all([split_equation(t) for t in self.equations_text], self.trig)
        values.update(self.values_override)
        return values

    def insert_axis(self, handle, name, planes):
        self._log("insert_axis", handle, name, tuple(planes))
        kept = self.rename.get(name, name)
        self.made.append(kept)
        return kept

    def open_sketch(self, handle, plane):
        self._log("open_sketch", handle, plane)

    def _made(self, name):
        kept = self.rename.get(name, name)
        self.made.append(kept)
        return kept

    def close_sketch(self, handle, name):
        self._log("close_sketch", handle, name)
        return self._made(name)

    def sketch_status(self, name):
        return self.statuses.get(name, 3)

    def sketch_circle(self, handle, centre, radius, construction=False):
        self._log("sketch_circle", handle)

    def sketch_arc(self, handle, centre, start, end, direction=1, construction=False):
        self._log("sketch_arc", handle)

    def sketch_line(self, handle, start, end, construction=False):
        self._log("sketch_line", handle)

    def sketch_point(self, handle, at):
        self._log("sketch_point", handle)

    def sketch_equation_curve(self, handle, x, y, t1, t2, start, end):
        self._log("sketch_equation_curve", handle)

    def add_relation(self, kind, refs):
        self._log("add_relation", kind, *refs)
        return "already one point" if refs == ("L+.start", "I+.start") else ""

    def dimension(self, name, refs, at):
        self._log("dimension", name)
        return self.rename.get(name, name)

    def extrude(self, handle, sketch, name, depth, depth_dim):
        self._log("extrude", name)
        return self._made(name), depth_dim

    def cut_extrude(self, handle, sketch, name):
        self._log("cut_extrude", name)
        return self._made(name)

    def circular_pattern(self, handle, name, axis, feature, count, count_dim):
        self._log("circular_pattern", name, count)
        return self._made(name), count_dim

    def ref_plane(self, handle, name, plane, offset, flip, offset_dim):
        self._log("ref_plane", name, round(offset, 6), flip)
        kept = self.rename.get(name, name)
        self.made.append(kept)
        return kept, offset_dim

    def sweep_cut(self, handle, profile, path, name, twist, reverse, twist_dim):
        self._log("sweep_cut", name, round(twist, 6), reverse)
        return self._made(name), twist_dim

    def mirror_body(self, handle, name, plane):
        self._log("mirror_body", name, plane)
        return self._made(name)

    def ref_plane_normal(self, handle, name, line, point):
        self._log("ref_plane_normal", name, line, point)
        return self._made(name)

    def revolve(self, handle, sketch, name, axis):
        self._log("revolve", name, axis)
        return self._made(name)

    def loft_cut(self, handle, name, profiles):
        self._log("loft_cut", name, *profiles)
        return self._made(name)

    def add_component(self, handle, path, at):
        self._log("add_component", handle, path)
        self.adding.append(path)
        self.component_names[handle] = f"{handle}-1"
        self.component_paths[f"{handle}-1"] = path
        return f"{handle}-1"

    def fix_component(self, handle):
        self._log("fix_component", handle)
        self.fixed.add(self._name2(handle))

    def unfix_component(self, handle):
        self._log("unfix_component", handle)
        self.fixed.discard(self._name2(handle))

    def add_mate(self, handle, kind, a, b, value=0.0, name="", ratio=(1.0, 1.0), flip=False):
        self._log("add_mate", kind, a, b, *((ratio, flip) if kind == "gear" else ()))
        kept = name or f"Mate{len(self.calls)}"
        self._keep_mate(handle, kept, kind, a, b, value, ratio, flip)
        return kept, ("D7" if kind in ("distance", "angle", "axis angle", "point distance") else "")

    def place_component(self, handle, rotation, at, kind=None):
        self._log("place_component", handle)
        if getattr(findings, "PUT_MARKS_ASSEMBLY_MODIFIED", False):
            self._touch()
        put = (tuple(rotation), tuple(at))
        name = self._name2(handle)
        if any(m.kind == "lock" and not m.suppressed and name in (m.a[0], m.b[0]) for m in self.mates):
            self.locked_puts.append(name)          # held, its partner left where it was, nothing reported
        self.frames[handle] = put
        self.frames[name] = put
        if handle in self.found:
            self.frames[self.found[handle]] = put
        self._rebuilt(kind)            # Session.place_component's rebuild of its own, after the put
        if self.mates:
            # Session.place_component reads the frame back after that rebuild.
            rotation_off, origin_off = _frame_off(self.frames[name], put)
            if rotation_off > 1e-6 or origin_off > 1e-6:
                raise SolidWorksError(f"{name} did not take its frame (rotation off {rotation_off:.1e}, origin "
                                      f"{origin_off:.1e} mm).")

    def interference_count(self):
        self._log("interference_count")
        self._touch()                  # interference detection marks the assembly (see interferences)
        return self.interference

    def set_custom_property(self, name, value):
        self._log("set_custom_property", name, value)

    # -- W4

    def documents(self):
        return list(self.open_docs)

    def feature_names(self):
        return list(self.made)

    def open_document(self, path):
        self._log("open_document", path)
        doc_type = 2 if path.lower().endswith(".sldasm") else 1
        info = DocInfo(title=path.replace("/", "\\").rsplit("\\", 1)[-1], path=path, doc_type=doc_type)
        is_open = any(_key(d.path) == _key(path) for d in self.open_docs)
        if not (is_open and _key(path) in self.memory):
            # Loaded from its file: what it holds in memory is what was saved.
            eq, made = self.saved.get(_key(path), ([], []))
            self.memory[_key(path)] = (list(eq), list(made))
        self.equations_text, self.made = self.memory[_key(path)]
        if not (is_open and _key(path) in self.memory_mates):
            self.memory_mates[_key(path)] = copy.deepcopy(self.saved_mates.get(_key(path), []))
        self.mates = self.memory_mates[_key(path)]
        self.current = path
        if not is_open:
            self.open_docs.append(info)
        self.active = info
        return info

    def has_unsaved_changes(self):
        """``GetSaveFlag`` on the document just opened: True when what it holds in memory is not what was saved,
        or a call has modified it since (``touched``)."""
        self._log("has_unsaved_changes")
        key = _key(self.current)
        return key in self.touched or self.memory.get(key) != self.saved.get(key)

    def find_component(self, handle, name):
        self._log("find_component", handle, name)
        if name in self.missing_components:
            title = self.active.title if self.active else "the assembly"
            raise ComponentGone(f"{name} is not in {title} any more: it was renamed or deleted in SolidWorks.")
        self.found[handle] = name
        self.component_names[handle] = name
        return name

    def component_frame(self, handle):
        self._log("component_frame", handle)
        identity = ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
        name = self.found.get(handle) or self.component_names.get(handle)
        if name in self.frames:                    # a component's frame by its Name2 first: the solve moves those
            return self.frames[name]
        return self.frames.get(handle, identity)

    def interferences(self):
        """Marks the assembly modified. Probe assembly_rebuild_scope saw the assembly marked after a put by the reads
        that followed it (``flags_after_reads``: the frame reads and interferences() together), without isolating
        which; the fake pins it here, on the interference check."""
        self._log("interferences")
        self._touch()
        return list(self.clashes)

    def exists(self, path):
        return _key(path) in self.saved

    # -- W5: the train's mates (see the class)

    def _name2(self, handle):
        if handle in self.component_paths:         # already a Name2
            return handle
        return self.found.get(handle) or self.component_names.get(handle) or f"{handle}-1"

    def _ref(self, ref, bare):
        if bare:
            return self._name2(ref), ""
        handle, _, target = ref.partition(":")
        return ("asm" if handle == "asm" else self._name2(handle)), target

    def _bodies(self):
        """Components joined by unsuppressed locks are one body; bodies joined by gear mates, one train."""
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                x = parent[x]
            return x
        return parent, find

    def _keep_mate(self, handle, kept, kind, a, b, value, ratio, flip):
        mate = FakeMate(kept, kind, self._ref(a, kind == "lock"), self._ref(b, kind == "lock"), value,
                        tuple(ratio), flip)
        live = [m for m in self.mates if not m.suppressed]
        fights = []
        if kind == "lock":
            fights = [m for m in live if (m.axis or m.along) and m.a[0] == mate.b[0]]
        elif mate.axis or mate.along:
            gear = mate.a[0]
            fights = [m for m in live if m.kind == "lock" and m.b[0] == gear]
            if mate.axis:
                fights += [m for m in live if m.axis and m.a[0] == gear]
        elif kind == "gear":
            parent, find = self._bodies()
            for m in live:
                if m.kind in ("lock", "gear"):
                    parent[find(m.a[0])] = find(m.b[0])
            if find(mate.a[0]) == find(mate.b[0]):
                fights = [m for m in live if m.kind == "gear" and find(m.a[0]) == find(mate.a[0])]
        if fights:
            mate.status, mate.code, mate.warning = findings.ADD_MATE_OVER_DEFINED, 46, False
            for fought in fights:
                fought.code, fought.warning = 46, True
        self.mates.append(mate)
        self.mate_handles[handle] = kept

    def mate(self, name, path=None):
        """A test's look at one mate: in the document at ``path`` (as open now), else in the current one."""
        mates = self.memory_mates.get(_key(path), []) if path else self.mates
        return next((m for m in mates if m.name == name), None)

    def user_mate(self, path, name, suppressed=False):
        """A mate the user added by hand in SolidWorks (an angle mate driving a gear, say), in the open document."""
        self.memory_mates[_key(path)].append(FakeMate(name, "angle", ("gear1-1", "plane2"), ("layout-1", "plane3"),
                                                      suppressed=suppressed))

    def drop_mate(self, path, name):
        """A mate deleted (or renamed) by the user in SolidWorks, in the open document."""
        mates = self.memory_mates[_key(path)]
        mates.remove(next(m for m in mates if m.name == name))

    def turn(self, name, degrees):
        """A component turned about its own axis (``R · rot_z``), as a drag in SolidWorks would leave it."""
        rotation, at = self.frames[name]
        self.frames[name] = (_mul(rotation, _rot_z(degrees)), at)

    def _values_of(self, path):
        from gear_generator.gears.equations import evaluate_all
        if not path:
            return {}
        texts = self.memory[_key(path)][0] if _key(path) in self.memory else self.saved.get(_key(path), ([], []))[0]
        return evaluate_all([split_equation(t) for t in texts], self.trig)

    def _solve(self):
        live = [m for m in self.mates if not m.suppressed]
        own = self.equation_values() if self.equations_text else {}
        for axis in (m for m in live if m.axis):
            gear, (layout, target) = axis.a[0], axis.b
            shaft = target[:-len("Axis")].strip()
            values = self._values_of(self.component_paths.get(layout))
            old = self.frames.get(gear, (IDENTITY9, (0.0, 0.0, 0.0)))
            x, y = values.get(f"{shaft} X", 0.0), values.get(f"{shaft} Y", 0.0)
            z = old[1][2]
            for along in (m for m in live if m.along and m.a[0] == gear):
                sign = -1.0 if along.value < 0 else 1.0
                z = sign * own[along.link] if along.link in own else along.value
            moved = math.hypot(x - old[1][0], y - old[1][1]) > 1e-9
            new = (_mul(old[0], _rot_z(-13.0)) if moved else old[0], (x, y, z))
            if _frame_off(new, old) == (0.0, 0.0):
                continue
            for lock in (m for m in live if m.kind == "lock" and m.a[0] == gear):
                follower = self.frames.get(lock.b[0], (IDENTITY9, (0.0, 0.0, 0.0)))
                self.frames[lock.b[0]] = _compose(new, _compose(_inverse(old), follower))
            self.frames[gear] = new

    def mate_status(self, name):
        if name in self.mate_statuses:
            return self.mate_statuses[name]
        mate = self.mate(name)
        return None if mate is None else mate.status

    def mate_states(self):
        self._log("mate_states")
        out = []
        for m in self.mates:
            code, warning = self.mate_codes.get(m.name, (m.code, m.warning))
            out.append(swcom.MateState(m.name, code, warning if code else True, m.suppressed))
        return out

    def constrained_status(self, handle):
        self._log("constrained_status", handle)
        name = self._name2(handle)
        for key in (name, handle):
            if key in self.constrained:
                return self.constrained[key]
        if any(m.code and not m.suppressed and name in (m.a[0], m.b[0]) for m in self.mates):
            return findings.COMPONENT_OVER_DEFINED
        return findings.COMPONENT_FULLY_DEFINED if name in self.fixed else findings.COMPONENT_UNDER_DEFINED

    def find_mate(self, handle, name):
        self._log("find_mate", handle, name)
        if self.mate(name) is None:
            title = self.active.title if self.active else "the assembly"
            raise swcom.MateGone(f'The mate "{name}" is not in {title} any more: it was renamed or deleted in '
                                 "SolidWorks.")
        self.mate_handles[handle] = name
        return name

    def set_mate_suppressed(self, handle, suppressed):
        self._log("set_mate_suppressed", handle, suppressed)
        self.mate(self.mate_handles[handle]).suppressed = bool(suppressed)

    def set_gear_ratio(self, handle, a, b, ratio):
        self._log("set_gear_ratio", handle, a, b, tuple(ratio))
        route = getattr(findings, "GEAR_MATE_RATIO_ROUTE", None)
        if route != "remake":
            raise SolidWorksError(f"findings.GEAR_MATE_RATIO_ROUTE is {route!r}, so the gear mate keeps its ratio.")
        old = self.mate(self.mate_handles[handle])
        self.mates.remove(old)                     # deleted, and made again at the end of the tree, its name kept
        self._keep_mate(handle, old.name, "gear", a, b, 0.0, tuple(float(n) for n in ratio), old.flip)


def plan(spec=None, recipe="A", path=PATH):
    spec = spec or GearSpec()
    return SPUR.plan(spec, SPUR.derive(spec), recipe, "", path)


def names(fake):
    return [name for name, _ in fake.calls]


def never_exists(_path):
    return False


# -- order ------------------------------------------------------------------


@pytest.mark.parametrize("recipe", ["A", "B"])
def test_a_clean_build_suppresses_first_rebuilds_once_then_saves(recipe):
    fake = FakeSolidWorks()
    result = swbuild.build(fake, plan(recipe=recipe), never_exists)
    called = names(fake)
    assert result.ok, result.failures
    assert called[:3] == ["begin_build", "new_part", "detect_trig_units"]
    first_geometry = next(i for i, n in enumerate(called) if n in ("insert_axis", "open_sketch"))
    assert called.index("suppress") < first_geometry
    assert called.count("rebuild") == 1
    assert fake.calls[called.index("rebuild")] == ("rebuild", (False,))
    assert called[-1] == "save_as" and called.index("rebuild") < called.index("save_as")
    assert result.saved == PATH
    assert "ok      rebuilt once" in result.log_lines()


def test_every_global_is_added_before_any_link():
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(), never_exists)
    called = names(fake)
    last_global = max(i for i, n in enumerate(called) if n == "add_global_variable")
    first_link = called.index("link_dimension")
    assert last_global < first_link
    assert called.count("add_global_variable") == 24


def test_the_measured_trig_units_choose_the_expressions():
    fake = FakeSolidWorks(trig=RADIANS)
    result = swbuild.build(fake, plan(), never_exists)
    base = next(args for name, args in fake.calls if name == "add_global_variable" and args[0] == "Base Diameter")
    assert "180" in base[1] and result.ok and result.trig == RADIANS


def test_manual_steps_are_counted_in_the_log():
    result = swbuild.build(FakeSolidWorks(), plan(), never_exists)
    lines = result.log_lines()
    assert "MANUAL  1 step(s) to do by hand" in lines
    assert any(line.startswith("MANUAL  Assign a material") for line in lines)


# -- failures ----------------------------------------------------------------


def test_the_flag_is_restored_and_the_build_stops_at_the_failing_op():
    fake = FakeSolidWorks(fail_on={"cut_extrude": "FeatureCut4 would not cut the tooth space."})
    result = swbuild.build(fake, plan(), never_exists)
    called = names(fake)
    assert not result.ok
    assert result.stopped_at.startswith("cut ")
    assert result.failures[0][1] == "FeatureCut4 would not cut the tooth space."
    assert "circular_pattern" not in called
    assert fake.suppressed is False
    assert called.count("rebuild") == 1
    assert "save_as" not in called
    assert called[-1] == "end_build"
    assert any(line.startswith("FAIL    cut") for line in result.log_lines())


def test_a_raise_that_is_not_a_solidworks_error_is_a_failure_and_still_restores_the_flag():
    """W4 review B1: once the document is made, build() keeps its word that every problem is a failure."""
    fake = FakeSolidWorks()

    def boom(*_args):
        raise RuntimeError("the COM server went away")

    fake.sketch_circle = boom
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.ok and result.document == "Part1" and not result.saved
    assert result.failures == [("the build", "it stopped on an unexpected RuntimeError: the COM server went away.")]
    assert fake.suppressed is False
    assert names(fake)[-1] == "end_build" and "save_as" not in names(fake)


def test_a_save_that_raises_anything_is_the_saves_failure():
    fake = FakeSolidWorks()

    def gone(_path):
        raise RuntimeError("(-2147023170, 'The remote procedure call failed.', None, None)")

    fake.save_as = gone
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.saved and result.failures[0][0] == "save"
    assert result.failures[0][1].startswith("it stopped on an unexpected RuntimeError: ")


def test_a_name_solidworks_did_not_keep_stops_before_the_link_that_uses_it():
    fake = FakeSolidWorks(rename={"Blank Sketch": "Sketch1"})
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.ok
    assert "'Sketch1' instead of 'Blank Sketch'" in result.failures[0][1]
    assert "link_dimension" not in names(fake)
    assert "save_as" not in names(fake)


def test_a_global_that_disagrees_with_the_maths_fails_and_is_not_saved():
    fake = FakeSolidWorks(values={"Base Diameter": 12.0})
    result = swbuild.build(fake, plan(), never_exists)
    assert not result.ok and "Base Diameter" in result.failures[0][0]
    assert "save_as" not in names(fake)


def test_a_failed_rebuild_is_not_saved():
    fake = FakeSolidWorks(rebuild_ok=False)
    result = swbuild.build(fake, plan(), never_exists)
    assert "save_as" not in names(fake)
    assert "FAIL    the rebuild reported an error" in result.log_lines()


def test_an_under_defined_sketch_is_a_check_not_a_failure():
    fake = FakeSolidWorks(statuses={"Tooth Space Sketch": 2})
    result = swbuild.build(fake, plan(), never_exists)
    assert result.ok and result.saved
    assert "CHECK   Tooth Space Sketch is under-defined, not fully defined" in result.log_lines()


def test_an_existing_file_is_refused_before_anything_is_made():
    fake = FakeSolidWorks()
    with pytest.raises(swbuild.BuildError, match="already exists"):
        swbuild.build(fake, plan(), lambda path: True)
    assert fake.calls == []


def test_an_old_solidworks_is_refused():
    fake = FakeSolidWorks()
    fake.revision = (31, 5, 0)
    with pytest.raises(swbuild.BuildError, match="2024"):
        swbuild.build(fake, plan(), never_exists)


def test_an_unsound_plan_is_refused():
    good = plan()
    broken = BuildPlan(good.kind, good.recipe, good.ops[:-2] + (SaveAs(PATH),), good.path)
    with pytest.raises(swbuild.BuildError, match="not sound"):
        swbuild.build(FakeSolidWorks(), broken, never_exists)


# -- kept names ---------------------------------------------------------------


def test_the_reported_features_and_dimensions_are_the_kept_ones():
    result = swbuild.build(FakeSolidWorks(), plan(), never_exists)
    assert result.features[:3] == ["Gear Axis", "Blank Sketch", "Blank"]
    assert result.dimensions["OD@Blank Sketch"] == "OD@Blank Sketch"
    assert result.dimensions["Width@Blank"] == "Width@Blank"
    assert result.dimensions["Count@Teeth"] == "Count@Teeth"


# -- pairs ---------------------------------------------------------------------


def _assembly_plan():
    from gear_generator.gears import base
    return BuildPlan("pair", "", (
        base.NewAssembly(""),
        base.AddGlobal("Centre Distance", "60"),
        base.AddComponent("gear1", r"C:\g\a.SLDPRT"),
        base.AddComponent("gear2", r"C:\g\b.SLDPRT", (60.0, 0.0, 0.0)),
        base.Fix("gear1"),
        base.Mate("dist", "distance", "gear2:Gear Axis", "gear1:plane3", 60.0, "Centre Distance"),
        base.LinkDimension("D1@Centre Distance", '"Centre Distance"'),
        base.Rebuild(),
        base.SaveAs(r"C:\g\Pair.SLDASM"),
    ), r"C:\g\Pair.SLDASM")


def test_a_pair_builds_both_parts_then_the_assembly_linking_the_kept_dimension():
    fake = FakeSolidWorks()
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok, result.log_lines()
    assert names(fake).count("new_part") == 2 and names(fake).count("new_assembly") == 1
    link = [args for name, args in fake.calls if name == "link_dimension"][-1]
    assert link == ("D7@Centre Distance", '"Centre Distance"')


def test_a_clean_pair_is_checked_for_interference_after_the_assembly():
    fake = FakeSolidWorks()
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok and names(fake)[-1] == "interference_count"
    assert "no interference between the gears" in result.assembly.done
    assert not result.assembly.checks


def test_interfering_teeth_are_a_check_not_a_failure():
    fake = FakeSolidWorks(interference=(3, 12.5))
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok
    assert result.assembly.checks == ["the gears interfere in 3 places, 12.500 mm³; look along the gear axis at the mesh"]
    assert "CHECK   the gears interfere in 3 places, 12.500 mm³; look along the gear axis at the mesh" \
        in result.log_lines()


def test_an_interference_check_that_raises_is_reported_and_the_pair_still_stands():
    fake = FakeSolidWorks(fail_on={"interference_count": "no manager"})
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert result.ok and result.assembly.checks == ["interference could not be checked: no manager"]


def test_a_pair_skips_the_assembly_when_a_part_fails():
    fake = FakeSolidWorks(fail_on={"circular_pattern": "no pattern"})
    result = swbuild.build_pair(fake, plan(path=r"C:\g\a.SLDPRT"), plan(path=r"C:\g\b.SLDPRT"),
                                _assembly_plan(), never_exists)
    assert not result.ok
    assert result.gear_b is None and result.assembly is None
    assert "new_assembly" not in names(fake) and "interference_count" not in names(fake)
    assert "SKIPPED" in result.log_lines()[-1]


# -- update values ---------------------------------------------------------------


def _built_fake(spec):
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(spec), never_exists)
    fake.calls.clear()
    fake.active = DocInfo(title="Gear_m1.5_N25.SLDPRT", path=PATH, doc_type=1)
    return fake


def test_update_values_changes_only_what_differs_in_one_rebuild():
    spec = GearSpec()
    fake = _built_fake(spec)
    wanted = spec.with_values(teeth="40")
    variables = SPUR.variables(wanted, SPUR.derive(wanted))
    result = swbuild.update_variables(fake, variables, PATH.lower())
    assert result.ok and result.changed == ["No. of Teeth"]
    assert names(fake).count("rebuild") == 1
    assert names(fake).index("suppress") < names(fake).index("set_global_variable")
    assert fake.suppressed is False


def test_update_values_refuses_the_wrong_document():
    fake = _built_fake(GearSpec())
    fake.active = DocInfo(title="Other.SLDPRT", path=r"C:\Other.SLDPRT", doc_type=1)
    with pytest.raises(swbuild.BuildError, match="Other.SLDPRT"):
        swbuild.update_variables(fake, SPUR.variables(GearSpec(), SPUR.derive(GearSpec())), PATH)
    assert "set_global_variable" not in names(fake)


def test_update_values_refuses_a_part_without_the_globals():
    fake = FakeSolidWorks()
    fake.active = DocInfo(title="Gear.SLDPRT", path=PATH, doc_type=1)
    with pytest.raises(swbuild.BuildError, match="not in this part"):
        swbuild.update_variables(fake, SPUR.variables(GearSpec(), SPUR.derive(GearSpec())), PATH)


def test_nothing_to_change_means_no_rebuild():
    spec = GearSpec()
    fake = _built_fake(spec)
    result = swbuild.update_variables(fake, SPUR.variables(spec, SPUR.derive(spec)), PATH)
    assert result.changed == [] and "rebuild" not in names(fake)


@pytest.mark.parametrize("built,wanted,word", [
    ({"kind": "spur", "recipe": "A", "bore": "10"}, {"kind": "spur", "recipe": "B", "bore": "10"}, "recipe"),
    ({"kind": "spur", "recipe": "A", "bore": "10"}, {"kind": "spur", "recipe": "A", "bore": ""}, "bore"),
    ({"kind": "spur", "recipe": "A", "bore": ""}, {"kind": "spur", "recipe": "A", "bore": "0"}, ""),
    ({"kind": "spur", "recipe": "A", "bore": "8"}, {"kind": "spur", "recipe": "A", "bore": "12"}, ""),
])
def test_structural_changes_are_named(built, wanted, word):
    text = swbuild.structural_change(built, wanted)
    assert (word in text.lower()) if word else text == ""


def test_a_relation_that_already_holds_is_logged_as_such():
    result = swbuild.build(FakeSolidWorks(), plan(recipe="A"), never_exists)
    assert "ok      coincident L+.start I+.start (already one point)" in result.log_lines()


# -- W4 interfaces: an axis through planes made in the plan ---------------------------------


def _layout_like(axis_planes):
    from gear_generator.gears import base
    return BuildPlan("layout", "", (
        base.NewPart(""),
        base.RefPlane("x1", "S2 X Plane", 3, 63.75),
        base.Axis("axis1", "S2 Axis", axis_planes),
        base.Rebuild(),
        base.SaveAs(r"C:\g\R_Layout.SLDPRT"),
    ), r"C:\g\R_Layout.SLDPRT")


def test_an_axis_may_go_through_a_plane_made_earlier_by_its_id():
    assert _layout_like((2, "x1")).check() == []


def test_an_axis_through_a_plane_not_made_is_refused_with_a_sentence():
    problems = _layout_like((2, "x9")).check()
    assert "Axis 'axis1' is through 'x9', which is not a plane made earlier." in problems


def test_an_axis_is_described_by_plane_ids_and_tree_order_alike():
    from gear_generator.gears import base
    assert base.describe(base.Axis("a", "Gear Axis", (2, 3))) == "axis    'Gear Axis' through planes 2 and 3"
    assert base.describe(base.Axis("a", "S2 Axis", (2, "x1"))) == "axis    'S2 Axis' through plane 2 and x1"
    assert base.describe(base.Axis("a", "S2 Axis", ("y1", "x1"))) == "axis    'S2 Axis' through y1 and x1"


def test_the_runner_hands_the_axis_its_planes_as_planned():
    fake = FakeSolidWorks()
    result = swbuild.build(fake, _layout_like((2, "x1")), never_exists)
    assert result.ok, result.log_lines()
    assert ("insert_axis", ("axis1", "S2 Axis", (2, "x1"))) in fake.calls


def test_the_strips_own_axis_still_goes_through_planes_2_and_3():
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(), never_exists)
    assert ("insert_axis", ("axis", "Gear Axis", (2, 3))) in fake.calls


# -- W4 interfaces: what an assembly kept, frames, same-named documents, progress ----------------


def test_an_assembly_build_records_the_name_each_component_kept():
    result = swbuild.build(FakeSolidWorks(), _assembly_plan(), never_exists)
    assert result.components == {"gear1": "gear1-1", "gear2": "gear2-1"}


IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def _turned(degrees, flipped=False):
    import math
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    rows = ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))
    if flipped:                                  # rot_x(180) · rot_z: a part on a Z- shaft
        rows = (rows[0], tuple(-v for v in rows[1]), tuple(-v for v in rows[2]))
    return tuple(v for row in rows for v in row)


@pytest.mark.parametrize("flipped", [False, True])
def test_a_gear_turned_whole_pitches_is_the_same_placement(flipped):
    at = (63.75, 0.0, 5.0)
    pitch = 360.0 / 68
    assert swbuild.same_frame(_turned(10, flipped), at, _turned(10 + 3 * pitch, flipped), at, pitch)
    assert swbuild.same_frame(_turned(10, flipped), at, _turned(10 - pitch, flipped), at, pitch)
    assert not swbuild.same_frame(_turned(10, flipped), at, _turned(10 + pitch / 2, flipped), at, pitch)
    assert not swbuild.same_frame(_turned(10, flipped), at, _turned(10 + pitch, flipped), at)   # no pitch: exact


def test_a_frame_moved_or_tipped_is_not_the_same_placement():
    assert swbuild.same_frame(IDENTITY, (0.0, 0.0, 0.0), IDENTITY, (0.0, 0.0, 5e-7))
    assert not swbuild.same_frame(IDENTITY, (0.0, 0.0, 0.0), IDENTITY, (0.0, 2e-6, 0.0))
    assert not swbuild.same_frame(_turned(0), (0, 0, 0), _turned(0, flipped=True), (0, 0, 0), 360.0 / 17)


def test_a_document_of_the_same_name_open_from_another_folder_is_found():
    docs = [DocInfo("Gear_m1.5_N17.SLDPRT", r"C:\Other\Gear_m1.5_N17.SLDPRT", 1),
            DocInfo("Gear_m1.5_N68.SLDPRT", r"C:\Parts\R\Gear_m1.5_N68.SLDPRT", 1),
            DocInfo("Part1", "", 1)]
    wanted = [r"C:\Parts\R\gear_m1.5_n17.SLDPRT", r"c:\parts\r\Gear_m1.5_N68.SLDPRT"]
    assert swbuild.same_named_elsewhere(docs, wanted) == [(docs[0].path, wanted[0])]


def test_progress_is_one_step_per_job_never_a_shared_default():
    first, second = swbuild.Progress(), swbuild.Progress()
    first.say(swbuild.Step(swbuild.STAGE_PART, "Gear_m1.5_N68", 2, 4))
    assert first.step == swbuild.Step("part", "Gear_m1.5_N68", 2, 4) and second.step is None


def test_the_fake_reopens_a_saved_document_holding_what_it_was_saved_with():
    fake = FakeSolidWorks()
    swbuild.build(fake, plan(), never_exists)
    swbuild.build(fake, _layout_like((2, "x1")), never_exists)
    fake.open_document(PATH)
    assert swbuild.planned_changes(fake.equations(), SPUR.variables(GearSpec(), SPUR.derive(GearSpec())),
                                   DEGREES) == []
    assert fake.active.path == PATH and "Gear_m1.5_N25.SLDPRT" in [d.title for d in fake.documents()]
    fake.open_document(r"C:\g\R_Layout.SLDPRT")
    assert fake.feature_names() == ["S2 X Plane", "S2 Axis"]


# -- W4: build_gearbox ----------------------------------------------------------------------------


from gear_generator import findings  # noqa: E402
from gear_generator.gears import base as ops  # noqa: E402
from gear_generator.gears.base import GlobalVariable  # noqa: E402

W = "C:\\W\\"
P17, P68, P68B = W + "Gear_m1.5_N17.SLDPRT", W + "Gear_m1.5_N68.SLDPRT", W + "Gear_m1.5_N68_r2.SLDPRT"
LAYOUT, ASM = W + "R_Layout.SLDPRT", W + "R.SLDASM"
S17, S68 = GearSpec().with_values(teeth="17"), GearSpec().with_values(teeth="68")
AT2 = (63.75, 0.0, 0.0)
TURNED2 = _turned(180.0 / 68)


def _layout_plan(path=LAYOUT):
    return BuildPlan("layout", "", (
        ops.NewPart(""),
        ops.AddGlobal("S2 X", "63.75"),
        ops.RefPlane("x1", "S2 X Plane", 3, 63.75),
        ops.Axis("axis1", "S1 Axis", (2, 3)),
        ops.Axis("axis2", "S2 Axis", (2, "x1")),
        ops.Rebuild(),
        ops.SaveAs(path),
    ), path)


LAYOUT_VALUES = (GlobalVariable("S2 X", "63.75"),)
LAYOUT_FEATURES = ("S2 X Plane", "S1 Axis", "S2 Axis")


def _gearbox_assembly(parts=(P17, P68), layout=LAYOUT, path=ASM):
    steps = [ops.NewAssembly(""), ops.AddComponent("layout", layout), ops.Place("layout", IDENTITY, (0.0, 0.0, 0.0)),
             ops.Fix("layout")]
    frames = [(IDENTITY, (0.0, 0.0, 0.0)), (TURNED2, AT2)]
    for index, part in enumerate(parts, 1):
        rotation, at = frames[(index - 1) % 2]
        steps += [ops.AddComponent(f"gear{index}", part, at), ops.Place(f"gear{index}", rotation, at),
                  ops.Fix(f"gear{index}")]
    return BuildPlan("gearbox", "", tuple(steps) + (ops.Rebuild(), ops.SaveAs(path)), path)


def _values(spec):
    return tuple(SPUR.variables(spec, SPUR.derive(spec)))


def _record_steps():
    steps = []
    return steps, steps.append


GEARS = {"gear1": "G1", "gear2": "G2"}


def _build(fake=None, **kwargs):
    fake = fake or FakeSolidWorks()
    kwargs.setdefault("parts", [plan(S17, path=P17), plan(S68, path=P68)])
    kwargs.setdefault("layout", _layout_plan())
    kwargs.setdefault("assembly", _gearbox_assembly())
    kwargs.setdefault("gears", GEARS)
    kwargs.setdefault("exists", fake.exists)
    return fake, swbuild.build_gearbox(fake, **kwargs)


def _saved_part(fake, spec, path):
    """A part as an earlier build left it: built and saved, so the fake reopens it holding its globals."""
    swbuild.build(fake, plan(spec, path=path), fake.exists)
    fake.calls.clear()


def test_a_gearbox_builds_parts_then_layout_then_assembly_then_checks_interference():
    fake, result = _build()
    assert result.ok, result.log_lines()
    order = [n for n in names(fake) if n in ("new_part", "new_assembly", "interferences")]
    assert order == ["new_part", "new_part", "new_part", "new_assembly", "interferences"]
    assert [r.saved for r in result.parts.built] == [P17, P68]
    assert result.layout.saved == LAYOUT and result.assembly.saved == ASM
    assert result.components == {"layout": "layout-1", "gear1": "gear1-1", "gear2": "gear2-1"}
    lines = result.log_lines()
    assert lines[-1] == "ok      no interference between the gears"
    assert "open_document" not in names(fake) and "close_document" not in names(fake)


def test_the_progress_steps_come_in_the_pinned_order_with_stems_not_paths():
    fake = FakeSolidWorks()
    _saved_part(fake, S17, P17)
    steps, say = _record_steps()
    _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))], progress=say)
    assert steps == [swbuild.Step("check", "Gear_m1.5_N17", 1, 1), swbuild.Step("part", "Gear_m1.5_N68", 1, 1),
                     swbuild.Step("layout", "R_Layout"), swbuild.Step("assembly", "R"),
                     swbuild.Step("interference", "R")]


def test_a_progress_object_records_the_last_step_of_its_own_job():
    progress = swbuild.Progress()
    _build(progress=progress.say)
    assert progress.step == swbuild.Step("interference", "R")


@pytest.mark.parametrize("case,sentence", [
    ("new path exists", r"C:\W\Gear_m1.5_N68.SLDPRT already exists, and a build never overwrites a file."),
    ("two new paths", r"C:\W\Gear_m1.5_N17.SLDPRT is named twice in this job, so one document would take the "
                      "place of the other."),
    ("reused missing", r"C:\W\Old.SLDPRT is no longer there, so it cannot be reused: it was moved, renamed or "
                       "deleted since it was built."),
    ("same name, two folders", r"C:\W\Gear_m1.5_N17.SLDPRT and C:\Other\Gear_m1.5_N17.SLDPRT have the same file "
                               "name, and SolidWorks keeps one document per file name, so they cannot both be in "
                               "one job."),
    ("open elsewhere", r"C:\Other\Gear_m1.5_N68.SLDPRT is open in SolidWorks, and it has the same file name as "
                       r"C:\W\Gear_m1.5_N68.SLDPRT, which this job would make; SolidWorks keeps one document per "
                       "file name, so close Gear_m1.5_N68.SLDPRT in SolidWorks and try again."),
    ("assembly without layout", "The assembly is built around its layout part, and this build has neither a "
                                "layout part to make nor one to reuse."),
    ("stray insert", r"The assembly would insert C:\W\Stray.SLDPRT, which this build neither makes nor reuses."),
    ("unsound plan", "The build plan for R_Layout.SLDPRT is not sound: Axis 'axis2' is through 'x9', which is not "
                     "a plane made earlier."),
])
def test_every_preflight_refusal_is_a_sentence_and_nothing_is_touched(case, sentence):
    fake = FakeSolidWorks()
    kwargs = {}
    if case == "new path exists":
        fake.saved[_key(P68)] = ([], [])
    elif case == "two new paths":
        kwargs["parts"] = [plan(S17, path=P17), plan(S68, path=P17)]
    elif case == "reused missing":
        kwargs["reuse"] = [swbuild.DocumentValues(W + "Old.SLDPRT", ())]
    elif case == "same name, two folders":
        fake.saved[_key(r"C:\Other\Gear_m1.5_N17.SLDPRT")] = ([], [])
        kwargs["reuse"] = [swbuild.DocumentValues(r"C:\Other\Gear_m1.5_N17.SLDPRT", ())]
    elif case == "open elsewhere":
        fake.open_docs = [DocInfo("Gear_m1.5_N68.SLDPRT", r"C:\Other\Gear_m1.5_N68.SLDPRT", 1)]
    elif case == "assembly without layout":
        kwargs["layout"] = None
    elif case == "stray insert":
        kwargs["assembly"] = _gearbox_assembly(parts=(P17, W + "Stray.SLDPRT"))
    elif case == "unsound plan":
        broken = _layout_plan()
        kwargs["layout"] = BuildPlan("layout", "", tuple(
            ops.Axis("axis2", "S2 Axis", (2, "x9")) if isinstance(op, ops.Axis) and op.id == "axis2" else op
            for op in broken.ops), LAYOUT)
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake, **kwargs)
    assert str(raised.value) == sentence
    assert fake.calls == []


def test_a_reused_part_that_holds_other_values_is_named_and_nothing_is_made():
    """W4 review B2's last corner: not a refusal any more but a result naming the part, with its file's time, so
    the finish records it and the next plan makes the part new rather than fail this check on every press."""
    fake = FakeSolidWorks()
    _saved_part(fake, S68.with_values(teeth="69"), P68)
    _, result = _build(fake, parts=[plan(S17, path=P17)], reuse=[swbuild.DocumentValues(P68, _values(S68))],
                       mtime=lambda path: 1234.5)
    ((path, why),) = result.mismatched
    assert path == P68 and why.startswith("Gear_m1.5_N68.SLDPRT does not hold what the workbook asks of it, so it "
                                          'cannot be reused: "No. of Teeth" is 69 there and 68 here')
    assert result.mtimes == {P68: 1234.5} and not result.ok and result.checked == []
    assert "new_part" not in names(fake) and "save_as" not in names(fake)
    assert "set_global_variable" not in names(fake)
    assert f"FAIL    checked Gear_m1.5_N68.SLDPRT: {why}" in result.log_lines()


def test_a_reused_part_missing_a_global_is_named_with_the_global_in_the_sentence():
    fake = FakeSolidWorks()
    fake.saved[_key(P68)] = (['"Module"= 1.5'], [])
    _saved_part(fake, S17, P17)
    _, result = _build(fake, parts=[], reuse=[swbuild.DocumentValues(P68, _values(S68)),
                                             swbuild.DocumentValues(P17, _values(S17))])
    ((path, why),) = result.mismatched
    assert path == P68 and why.startswith('Gear_m1.5_N68.SLDPRT cannot be reused: "')
    assert "is not in this part, so it was not built by this tool or its equations were edited." in why
    assert result.checked == [P17]                          # every document is still checked, so one press finds all
    assert "new_part" not in names(fake)


def test_a_reused_layout_that_lost_a_plane_is_named():
    fake = FakeSolidWorks()
    fake.saved[_key(LAYOUT)] = (['"S2 X"= 63.75'], ["S1 Axis", "S2 Axis"])
    for path, spec in ((P17, S17), (P68, S68)):
        _saved_part(fake, spec, path)
    _, result = _build(fake, parts=[], reuse=[swbuild.DocumentValues(P17, _values(S17)),
                                              swbuild.DocumentValues(P68, _values(S68))],
                       layout=swbuild.DocumentValues(LAYOUT, LAYOUT_VALUES, LAYOUT_FEATURES))
    assert result.mismatched == [(LAYOUT, 'R_Layout.SLDPRT cannot be reused: "S2 X Plane" is no longer in it; it was '
                                          "renamed or deleted in SolidWorks.")]
    assert "new_assembly" not in names(fake) and result.layout_reused == ""


def test_a_reused_document_solidworks_will_not_open_is_refused_with_its_sentence():
    fake = FakeSolidWorks(fail_on={"open_document": r"SolidWorks would not open C:\W\Gear_m1.5_N68.SLDPRT (error 2)."})
    _saved_part(fake, S68, P68)
    with pytest.raises(swbuild.BuildError, match=r"would not open C:\\W\\Gear_m1.5_N68.SLDPRT \(error 2\)\."):
        _build(fake, parts=[plan(S17, path=P17)], reuse=[swbuild.DocumentValues(P68, _values(S68))])
    assert "new_part" not in names(fake)


def test_reused_parts_and_layout_are_opened_and_checked_before_anything_is_built_and_inserted_after():
    fake = FakeSolidWorks()
    for path, spec in ((P17, S17), (P68, S68)):
        _saved_part(fake, spec, path)
    swbuild.build(fake, _layout_plan(), fake.exists)
    fake.calls.clear()
    _, result = _build(fake, parts=[], reuse=[swbuild.DocumentValues(P17, _values(S17)),
                                              swbuild.DocumentValues(P68, _values(S68))],
                       layout=swbuild.DocumentValues(LAYOUT, LAYOUT_VALUES, LAYOUT_FEATURES))
    assert result.ok, result.log_lines()
    assert result.checked == [P17, P68, LAYOUT] and result.layout_reused == LAYOUT and result.layout is None
    called = names(fake)
    assert called.count("open_document") == 3 and called.index("new_assembly") > max(
        i for i, n in enumerate(called) if n == "open_document")
    assert called.count("new_part") == 0 and "set_global_variable" not in called
    assert not result.parts.ok          # an empty batch, as pinned; the gearbox is still ok
    assert "ok      layout R_Layout.SLDPRT reused" in result.log_lines()
    assert "ok      checked Gear_m1.5_N17.SLDPRT: it holds what the workbook asks, so it is reused" in result.log_lines()


@pytest.mark.parametrize("route,ok", [("opened", True), ("closed", True), (None, False), ("neither", False)])
def test_inserting_reused_parts_follows_the_reuse_route(monkeypatch, route, ok):
    monkeypatch.setattr(findings, "REUSE_ADD_ROUTE", route, raising=False)
    fake = FakeSolidWorks()
    _saved_part(fake, S17, P17)
    if ok:
        _, result = _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
        assert result.ok and "open_document" in names(fake)      # "closed" is opened anyway, by the live check
        return
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
    assert str(raised.value) == ("Putting a document built earlier into a new assembly has not been settled on "
                                 f"SolidWorks yet (findings.REUSE_ADD_ROUTE is {route!r}), so this build, which "
                                 "reuses Gear_m1.5_N17.SLDPRT, cannot start; run probe tier 7 first.")
    assert fake.calls == []


def test_a_reused_part_needs_no_reuse_route_when_no_assembly_is_built(monkeypatch):
    monkeypatch.setattr(findings, "REUSE_ADD_ROUTE", None, raising=False)
    fake = FakeSolidWorks()
    _saved_part(fake, S17, P17)
    _, result = _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))],
                       layout=None, assembly=None)
    assert result.ok and result.checked == [P17]


def test_a_part_that_fails_skips_the_layout_and_the_assembly():
    fake = FakeSolidWorks(fail_on={"circular_pattern": "FeatureCircularPattern5 would not pattern the cut."})
    _, result = _build(fake)
    assert not result.ok
    assert len(result.parts.built) == 1 and result.parts.skipped == [P68]
    assert result.layout is None and result.assembly is None
    assert result.skipped == "the layout part and the assembly, because a part failed"
    assert result.log_lines()[-1] == "SKIPPED the layout part and the assembly, because a part failed"
    assert names(fake).count("new_part") == 1 and "new_assembly" not in names(fake)


def test_a_layout_that_fails_keeps_the_parts_and_skips_the_assembly():
    fake = FakeSolidWorks(fail_on={"insert_axis": ("S2 Axis", "InsertAxis2 would not make S2 Axis.")})
    _, result = _build(fake)
    assert not result.ok and [r.saved for r in result.parts.built] == [P17, P68]
    assert result.layout is not None and not result.layout.ok and not result.layout.saved
    assert result.assembly is None and result.skipped == "the assembly, because the layout part failed"
    assert "new_assembly" not in names(fake)


def test_an_assembly_that_fails_keeps_the_parts_and_the_layout_and_checks_no_interference():
    fake = FakeSolidWorks(fail_on={"place_component": ("gear2", "gear2-1 did not take its frame.")})
    _, result = _build(fake)
    assert not result.ok
    assert [r.saved for r in result.parts.built] == [P17, P68] and result.layout.saved == LAYOUT
    assert not result.assembly.ok and not result.assembly.saved and result.skipped == ""
    assert "interferences" not in names(fake) and result.clashes == []
    assert not any("interference" in line for line in result.log_lines())


def test_an_assembly_that_cannot_even_be_made_keeps_the_parts_and_the_layout_on_the_result():
    """SolidWorks 2026, probe/workbook_assembly_check.py 2026-11-13: an assembly template that was not there
    raised out of build_gearbox after the parts and the layout had saved, so nothing reached the record."""
    fake = FakeSolidWorks(fail_on={"new_assembly": "There is no assembly template at 'C:\\T\\No.asmdot'."})
    _, result = _build(fake)
    assert not result.ok and [r.saved for r in result.parts.built] == [P17, P68] and result.layout.saved == LAYOUT
    assembly = result.assembly
    assert assembly is not None and not assembly.saved and assembly.document == ""
    assert assembly.failures == [("new assembly", "There is no assembly template at 'C:\\T\\No.asmdot'.")]
    assert "FAIL    new assembly: There is no assembly template at 'C:\\T\\No.asmdot'." in result.log_lines()
    assert "interferences" not in names(fake)
    assert "FAIL    the rebuild reported an error" not in assembly.log_lines()   # nothing was made to rebuild


def test_a_later_part_that_cannot_be_made_keeps_the_parts_before_it():
    fake = FakeSolidWorks()
    calls = {"n": 0}
    real = fake.new_part

    def second_fails(template=""):
        calls["n"] += 1
        if calls["n"] == 2:
            raise swbuild.SolidWorksError("SolidWorks would not make a new part from C:\\T\\Part.prtdot.")
        return real(template)
    fake.new_part = second_fails
    _, result = _build(fake)
    assert [r.saved for r in result.parts.built] == [P17, ""] and result.parts.built[1].failures[0][0] == "new part"
    assert result.skipped == "the layout part and the assembly, because a part failed"


def test_a_layout_that_cannot_be_made_is_a_failed_layout():
    fake = FakeSolidWorks()
    calls = {"n": 0}
    real = fake.new_part

    def third_fails(template=""):
        calls["n"] += 1
        if calls["n"] == 3:
            raise swbuild.SolidWorksError("There is no part template at 'C:\\T\\No.prtdot'.")
        return real(template)
    fake.new_part = third_fails
    _, result = _build(fake)
    assert result.layout is not None and result.layout.failures[0][0] == "new part" and not result.layout.saved
    assert result.skipped == "the assembly, because the layout part failed"


def test_a_clash_names_the_gears_and_leaves_the_build_ok():
    fake = FakeSolidWorks(clashes=[(("gear1-1", "gear2-1"), 12.3454), ((), 1.5), (("layout-1", "gear2-1"), 0.25)])
    _, result = _build(fake)
    assert result.ok
    assert result.clashes[0] == swbuild.Clash(("gear1-1", "gear2-1"), ("G1", "G2"), 12.3454)
    assert result.clashes[2].gears == ("layout-1", "G2")
    lines = result.log_lines()
    assert "CHECK   G1 and G2 interfere, 12.345 mm³; look where they meet" in lines
    assert ("CHECK   an interference of 1.500 mm³ between components SolidWorks did not name; look at each mesh"
            in lines)
    assert "ok      no interference between the gears" not in lines


def test_an_interference_check_that_raises_is_kept_and_the_build_still_stands():
    fake = FakeSolidWorks(fail_on={"interferences": "Assem1 has no interference detection manager."})
    _, result = _build(fake)
    assert result.ok and result.interference_error == "Assem1 has no interference detection manager."
    assert "CHECK   interference could not be checked: Assem1 has no interference detection manager." \
        in result.log_lines()


def test_build_parts_alone_makes_no_layout_and_no_assembly():
    fake, result = _build(layout=None, assembly=None)
    assert result.ok and result.layout is None and result.assembly is None and result.skipped == ""
    assert "new_assembly" not in names(fake) and "interferences" not in names(fake)


def test_a_gearbox_build_refuses_an_old_solidworks():
    fake = FakeSolidWorks()
    fake.revision = (31, 0, 0)
    with pytest.raises(swbuild.BuildError, match="2024"):
        _build(fake)


# -- W4: update_gearbox ---------------------------------------------------------------------------


def _built_gearbox(**fake_kwargs):
    """A fake SolidWorks after a clean gearbox build: every file saved, the gears where the build put them."""
    fake, result = _build(FakeSolidWorks(**fake_kwargs))
    assert result.ok, result.log_lines()
    fake.calls.clear()
    fake.frames = {"layout-1": (IDENTITY, (0.0, 0.0, 0.0)), "gear1-1": (IDENTITY, (0.0, 0.0, 0.0)),
                   "gear2-1": (TURNED2, AT2)}
    return fake


def _placements(g2=(TURNED2, AT2), teeth2=68):
    return [swbuild.Placement("G1", "gear1-1", IDENTITY, (0.0, 0.0, 0.0), 360.0 / 17),
            swbuild.Placement("G2", "gear2-1", g2[0], g2[1], 360.0 / teeth2)]


S69 = S68.with_values(teeth="69")
MOVED2 = (_turned(0.0), (64.5, 0.0, 0.0))


def _update(fake, **kwargs):
    kwargs.setdefault("parts", [swbuild.DocumentValues(P17, _values(S17)), swbuild.DocumentValues(P68, _values(S69))])
    kwargs.setdefault("layout", swbuild.DocumentValues(LAYOUT, (GlobalVariable("S2 X", "64.5"),), LAYOUT_FEATURES))
    kwargs.setdefault("assembly", ASM)
    kwargs.setdefault("placements", _placements(MOVED2, 69))
    kwargs.setdefault("exists", fake.exists)
    return swbuild.update_gearbox(fake, **kwargs)


def _after_last_open(fake, path):
    called = fake.calls
    start = max(i for i, (n, a) in enumerate(called) if n == "open_document" and a == (path,))
    return [n for n, _ in called[start:]]


def test_update_sets_values_then_re_places_only_what_differs_and_rebuilds_the_assembly_once():
    fake = _built_gearbox()
    result = _update(fake)
    assert result.ok, result.log_lines()
    sets = [a for n, a in fake.calls if n == "set_global_variable"]
    assert ("No. of Teeth", "69") in sets and ("S2 X", "64.5") in sets
    assert [r.changed for r in result.parts] == [[], ["No. of Teeth"]] and result.layout.changed == ["S2 X"]
    assert result.placed == ["G2"] and [a for n, a in fake.calls if n == "place_component"] == [("placed2",)]
    assert result.found == {"G1": (IDENTITY, (0.0, 0.0, 0.0)), "G2": (TURNED2, AT2)}
    assert _after_last_open(fake, ASM).count("rebuild") == 1 and result.rebuilt
    assert result.changed == [P68, LAYOUT, ASM]
    assert "save_as" not in names(fake) and "close_document" not in names(fake)
    assert fake.frames["gear2-1"] == MOVED2
    lines = result.log_lines()
    assert "ok      re-placed G2" in lines and "ok      no interference between the gears" in lines
    assert lines[-1] == ("not saved: Gear_m1.5_N68.SLDPRT, R_Layout.SLDPRT, R.SLDASM changed in SolidWorks; save "
                         "there to keep it")


def test_update_steps_check_every_document_then_values_then_place_then_interference():
    fake = _built_gearbox()
    steps, say = _record_steps()
    _update(fake, progress=say)
    assert steps == [swbuild.Step("check", "Gear_m1.5_N17", 1, 4), swbuild.Step("check", "Gear_m1.5_N68", 2, 4),
                     swbuild.Step("check", "R_Layout", 3, 4), swbuild.Step("check", "R", 4, 4),
                     swbuild.Step("values", "Gear_m1.5_N68"),     # N17 holds its values already: not touched
                     swbuild.Step("values", "R_Layout"), swbuild.Step("place", "R"),
                     swbuild.Step("interference", "R")]


def test_a_gear_turned_whole_pitches_is_left_where_it_is():
    fake = _built_gearbox()
    fake.frames["gear2-1"] = (_turned(180.0 / 68 + 5 * 360.0 / 68), AT2)
    result = _update(fake, parts=[], layout=None, placements=_placements())
    assert result.ok and result.placed == [] and "place_component" not in names(fake)
    # nothing changed and nothing moved: the assembly is only read, not rebuilt (W4 review S2)
    assert result.changed == [] and not result.rebuilt and "rebuild" not in names(fake)
    assert "interferences" not in names(fake)
    assert "ok      every gear is where the workbook puts it" in result.log_lines()
    assert result.log_lines()[-1] == "nothing changed in SolidWorks"


def test_a_gear_dragged_in_solidworks_is_found_where_it_was_and_put_back():
    fake = _built_gearbox()
    fake.frames["gear1-1"] = (_turned(7.0), (1.0, 2.0, 0.0))
    result = _update(fake, parts=[], layout=None, placements=_placements())
    assert result.placed == ["G1"] and result.found["G1"] == (_turned(7.0), (1.0, 2.0, 0.0))
    assert fake.frames["gear1-1"] == (IDENTITY, (0.0, 0.0, 0.0))


@pytest.mark.parametrize("case,sentence", [
    ("missing path", r"C:\W\Gear_m1.5_N68.SLDPRT is no longer there, so Update SolidWorks cannot change it: it was "
                     "moved, renamed or deleted since it was built."),
    ("missing global", 'R_Layout.SLDPRT cannot be updated: "S3 X" is not in this part, so it was not built by this '
                       "tool or its equations were edited."),
    ("lost plane", 'R_Layout.SLDPRT cannot be updated: "S2 X Plane" is no longer in it; it was renamed or deleted '
                   "in SolidWorks."),
    ("missing component", "gear2-1 is not in R.SLDASM any more: it was renamed or deleted in SolidWorks."),
    ("does not evaluate", "Gear_m1.5_N68.SLDPRT cannot be updated: the new values do not evaluate: "),
    ("open elsewhere", r"C:\Old\R.SLDASM is open in SolidWorks, and it has the same file name as C:\W\R.SLDASM, "
                       "which this job would change; SolidWorks keeps one document per file name, so close R.SLDASM "
                       "in SolidWorks and try again."),
    ("no assembly", "Gears can only be re-placed in an assembly, and Update SolidWorks was given none."),
    ("one component twice", "gear2-1 is recorded for both G1 and G2, so one of them would be placed twice."),
])
def test_every_check_refusal_changes_nothing(case, sentence):
    fake = _built_gearbox()
    kwargs = {}
    if case == "missing path":
        del fake.saved[_key(P68)]
    elif case == "missing global":
        kwargs["layout"] = swbuild.DocumentValues(LAYOUT, (GlobalVariable("S2 X", "64.5"),
                                                           GlobalVariable("S3 X", "132.5")), LAYOUT_FEATURES)
    elif case == "lost plane":
        fake.memory[_key(LAYOUT)][1].remove("S2 X Plane")            # deleted in SolidWorks, the layout still open
    elif case == "missing component":
        fake.missing_components = {"gear2-1"}
    elif case == "does not evaluate":
        kwargs["parts"] = [swbuild.DocumentValues(P68, (GlobalVariable("No. of Teeth", '"Nowhere" * 2'),))]
    elif case == "open elsewhere":
        fake.open_docs = [DocInfo("R.SLDASM", r"C:\Old\R.SLDASM", 2)]
    elif case == "no assembly":
        kwargs["assembly"] = ""
    elif case == "one component twice":
        kwargs["placements"] = [swbuild.Placement("G1", "gear2-1", IDENTITY, (0.0, 0.0, 0.0)),
                                swbuild.Placement("G2", "gear2-1", IDENTITY, (0.0, 0.0, 0.0))]
    with pytest.raises(swbuild.BuildError) as raised:
        _update(fake, **kwargs)
    assert str(raised.value).startswith(sentence) if case == "does not evaluate" else str(raised.value) == sentence
    called = names(fake)
    assert "set_global_variable" not in called and "place_component" not in called and "rebuild" not in called
    assert "save_as" not in called
    # What only a new revision gets past (W4 review S4.6) is told apart by its type, naming the document.
    not_as_built = {"missing global": LAYOUT, "lost plane": LAYOUT, "missing component": ASM}
    assert isinstance(raised.value, swbuild.NotAsBuilt) == (case in not_as_built)
    if case in not_as_built:
        assert raised.value.path == not_as_built[case]


@pytest.mark.parametrize("route", [None, "something else"])
def test_re_placing_without_a_settled_route_is_refused_before_anything_changes(monkeypatch, route):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", route, raising=False)
    fake = _built_gearbox()
    with pytest.raises(swbuild.BuildError) as raised:
        _update(fake)
    assert str(raised.value) == ("Moving a fixed component has not been settled on SolidWorks yet "
                                 f"(findings.REPLACE_FIXED_ROUTE is {route!r}), so Update SolidWorks cannot re-place "
                                 "the gears; run probe tier 7 first.")
    assert fake.calls == []


def test_values_alone_need_no_re_placing_route(monkeypatch):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", None, raising=False)
    fake = _built_gearbox()
    result = _update(fake, layout=None, assembly="", placements=[])
    assert result.ok and result.changed == [P68]


def test_the_unfix_route_unfixes_places_and_fixes_each_moved_gear(monkeypatch):
    monkeypatch.setattr(findings, "REPLACE_FIXED_ROUTE", "UnfixComponent, Transform2 put, FixComponent",
                        raising=False)
    fake = _built_gearbox()
    result = _update(fake)
    assert result.ok
    moves = [(n, a) for n, a in fake.calls if n in ("unfix_component", "place_component", "fix_component")]
    assert moves == [("unfix_component", ("placed2",)), ("place_component", ("placed2",)),
                     ("fix_component", ("placed2",))]


def test_the_transform_route_places_a_fixed_gear_without_unfixing_it():
    assert findings.REPLACE_FIXED_ROUTE == "Transform2 put"
    fake = _built_gearbox()
    _update(fake)
    assert "unfix_component" not in names(fake) and "fix_component" not in names(fake)


def test_re_placing_restores_the_rebuild_flag_before_the_one_rebuild():
    fake = _built_gearbox()
    _update(fake)
    tail = [(n, a) for n, a in fake.calls[[n for n, _ in fake.calls].index("place_component") - 1:]]
    assert tail[0] == ("suppress", (True,)) and ("suppress", (False,)) in tail
    assert tail.index(("suppress", (False,))) < tail.index(("rebuild", (False,)))
    assert fake.suppressed is False


def test_a_part_that_fails_stops_the_update_and_says_what_changed_and_what_was_left():
    fake = _built_gearbox(fail_on={"set_global_variable": ("No. of Teeth", "\"No. of Teeth\" reads '68'.")})
    result = _update(fake, parts=[swbuild.DocumentValues(P17, _values(S17.with_values(teeth="18"))),
                                  swbuild.DocumentValues(P68, _values(S69))])
    assert not result.ok and len(result.parts) == 1 and result.layout is None
    assert result.failures[0][0] == 'Gear_m1.5_N17.SLDPRT "No. of Teeth"'
    assert result.skipped == "1 more part, the layout part and the assembly, because Gear_m1.5_N17.SLDPRT failed"
    assert "place_component" not in names(fake) and "open_document" not in _after_last_open(fake, P17)[1:]
    assert result.log_lines()[-1].startswith("SKIPPED 1 more part")


def test_a_layout_that_fails_stops_before_the_assembly():
    fake = _built_gearbox(fail_on={"set_global_variable": ("S2 X", '"S2 X" reads 63.75.')})
    result = _update(fake)
    assert not result.ok and result.changed == [P68] and result.layout is not None
    assert result.skipped == "the assembly, because R_Layout.SLDPRT failed"
    assert "place_component" not in names(fake)


def test_a_failed_assembly_rebuild_is_a_failure_and_no_interference_is_checked():
    fake = _built_gearbox()
    fake.rebuild_ok = False
    result = _update(fake, parts=[], layout=None)          # G2 is re-placed, so the assembly is rebuilt
    assert not result.ok and result.failures == [("R.SLDASM", "SolidWorks reported an error rebuilding R.")]
    assert "interferences" not in names(fake)


def test_an_update_clash_names_the_gears_from_the_placements():
    fake = _built_gearbox(clashes=[(("gear1-1", "gear2-1"), 3.0)])
    result = _update(fake)
    assert result.ok and result.clashes == [swbuild.Clash(("gear1-1", "gear2-1"), ("G1", "G2"), 3.0)]
    assert "CHECK   G1 and G2 interfere, 3.000 mm³; look where they meet" in result.log_lines()


def test_with_parts_not_settled_beside_their_assembly_an_open_assembly_must_be_closed_first(monkeypatch):
    monkeypatch.setattr(findings, "OPEN_PART_BESIDE_ASSEMBLY", False, raising=False)
    fake = _built_gearbox()
    fake.open_docs = [DocInfo("R.SLDASM", ASM, 2)]
    with pytest.raises(swbuild.BuildError) as raised:
        _update(fake)
    assert str(raised.value) == ("Close R.SLDASM in SolidWorks, then press Update SolidWorks again: changing a part "
                                 "while its assembly is open has not been settled on this SolidWorks "
                                 "(findings.OPEN_PART_BESIDE_ASSEMBLY).")
    assert fake.calls == []


@pytest.mark.parametrize("beside", [False, None])
def test_with_parts_not_settled_beside_their_assembly_the_assembly_opens_after_the_values(monkeypatch, beside):
    monkeypatch.setattr(findings, "OPEN_PART_BESIDE_ASSEMBLY", beside, raising=False)
    fake = _built_gearbox()
    fake.close_all()                       # the assembly is not open: Update may go ahead, values first
    fake.missing_components = {"gear2-1"}
    result = _update(fake)
    called = names(fake)
    assert called.index("open_document") < called.index("set_global_variable")
    first_asm = next(i for i, (n, a) in enumerate(fake.calls) if n == "open_document" and a == (ASM,))
    assert first_asm > max(i for i, n in enumerate(called) if n == "set_global_variable")
    assert not result.ok and result.failures[0] == (
        "R.SLDASM", "gear2-1 is not in R.SLDASM any more: it was renamed or deleted in SolidWorks.")
    assert result.changed == [P68, LAYOUT]


def test_an_update_with_nothing_given_changes_nothing():
    fake = FakeSolidWorks()
    result = swbuild.update_gearbox(fake, exists=fake.exists)
    assert result.ok and fake.calls == [] and result.log_lines() == ["nothing changed in SolidWorks"]


def test_an_update_refuses_an_old_solidworks():
    fake = FakeSolidWorks()
    fake.revision = (31, 0, 0)
    with pytest.raises(swbuild.BuildError, match="2024"):
        swbuild.update_gearbox(fake, exists=fake.exists)


# -- W4: what the first run on SolidWorks 2026 found (probe/gearbox_smoke.py, 2026-11-13) -----------------


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_the_reuse_check_writes_nothing_and_reads_the_trig_units_from_the_text(trig):
    fake = FakeSolidWorks(trig=trig)
    _saved_part(fake, S17, P17)
    _, result = _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
    assert result.ok, result.log_lines()
    called = names(fake)
    assert "detect_trig_units" not in called[:called.index("new_part")]
    assert "add_global_variable" not in called[:called.index("new_part")]


def test_a_document_update_changes_still_has_its_trig_units_measured_before_its_values_are_set():
    fake = _built_gearbox()
    _update(fake)
    called = names(fake)
    assert "detect_trig_units" in called[:called.index("set_global_variable")]


def test_interferences_between_the_same_components_are_one_clash_with_their_volumes_summed():
    fake = FakeSolidWorks(clashes=[(("gear1-1", "gear2-1"), 54.0), (("gear2-1", "gear1-1"), 27.0),
                                   (("gear1-1", "gear2-1"), 10.5), ((), 0.5), ((), 0.25)])
    _, result = _build(fake)
    assert result.clashes == [swbuild.Clash(("gear1-1", "gear2-1"), ("G1", "G2"), 91.5),
                              swbuild.Clash((), (), 0.5), swbuild.Clash((), (), 0.25)]
    assert "CHECK   G1 and G2 interfere, 91.500 mm³; look where they meet" in result.log_lines()


# -- W4 review: nothing escapes a job once it has saved something (B1) ----------------------------------------


class ComErrorLookAlike(Exception):
    """Stands in for ``pywintypes.com_error`` reaching swbuild unwrapped (or anything else unexpected)."""


RPC = ComErrorLookAlike(-2147023170, "The remote procedure call failed.", None, None)


def test_a_raise_on_the_third_save_keeps_the_two_parts_saved_before_it_on_the_result():
    """The review's w4r_crash: the third save_as raised a non-SolidWorksError and build_gearbox raised with it, so
    the two parts SolidWorks had saved never reached the record."""
    fake = FakeSolidWorks(raises={"save_as": (2, RPC)})
    _, result = _build(fake)
    assert [r.saved for r in result.parts.built] == [P17, ""] and not result.ok
    assert result.parts.built[1].failures[0][0] == "save"
    assert result.parts.built[1].failures[0][1].startswith("it stopped on an unexpected ComErrorLookAlike: ")
    assert result.skipped == "the layout part and the assembly, because a part failed"
    assert "new_assembly" not in names(fake)


def test_a_raise_making_the_first_part_is_a_failed_part_not_a_raise():
    fake = FakeSolidWorks(raises={"new_part": (1, RPC)})
    _, result = _build(fake)
    assert len(result.parts.built) == 1 and result.parts.built[0].failures[0][0] == "new part"
    assert result.parts.skipped == [P68] and not result.ok


def test_a_raise_between_documents_is_a_failure_on_the_result_and_what_saved_stays():
    def say(step):
        if step.stage == "layout":
            raise RPC
    fake = FakeSolidWorks()
    _, result = _build(fake, progress=say)
    assert [r.saved for r in result.parts.built] == [P17, P68] and result.layout is None
    assert result.failures == [("the layout part", "it stopped on an unexpected ComErrorLookAlike: (-2147023170, "
                                                   "'The remote procedure call failed.', None, None).")]
    assert result.skipped == "the assembly, because the job stopped during the layout part"
    assert not result.ok
    assert result.log_lines()[-2:] == ["FAIL    the layout part: " + result.failures[0][1],
                                       "SKIPPED the assembly, because the job stopped during the layout part"]


def test_a_raise_in_the_interference_check_is_said_and_the_build_stands():
    fake = FakeSolidWorks(raises={"interferences": (1, RPC)})
    _, result = _build(fake)
    assert result.ok and result.interference_error.startswith("it stopped on an unexpected ComErrorLookAlike")


def test_the_reuse_check_still_refuses_before_anything_is_made():
    """The pre-flight (paths, the reused documents checked live) may still raise: nothing is made by then."""
    fake = FakeSolidWorks(raises={"open_document": (1, RPC)})
    _saved_part(fake, S17, P17)
    with pytest.raises(ComErrorLookAlike):
        _build(fake, parts=[plan(S68, path=P68)], reuse=[swbuild.DocumentValues(P17, _values(S17))])
    assert "new_part" not in names(fake)


def test_an_update_that_raises_part_way_keeps_what_it_changed_on_the_result():
    fake = _built_gearbox()
    fake.raises = {"set_global_variable": (fake.counts.get("set_global_variable", 0) + 2, RPC)}   # S2 X
    result = _update(fake)
    assert result.changed == [P68] and result.layout is not None and result.layout.changed == []
    assert result.failures[0][0] == 'R_Layout.SLDPRT "S2 X"'
    assert result.skipped == "the assembly, because R_Layout.SLDPRT failed" and "place_component" not in names(fake)


def test_an_update_whose_assembly_raises_keeps_the_values_it_set():
    fake = _built_gearbox()
    fake.raises = {"component_frame": (fake.counts.get("component_frame", 0) + 1, RPC)}
    result = _update(fake)
    assert result.changed == [P68, LAYOUT] and result.placed == []
    assert result.failures[0][0] == "R.SLDASM" and "ComErrorLookAlike" in result.failures[0][1]
    assert result.rebuilt                                 # the values changed, so the assembly is still rebuilt


def test_an_update_raise_between_documents_is_a_failure_on_the_result():
    def say(step):
        if step.stage == "place":
            raise RPC
    fake = _built_gearbox()
    result = _update(fake, progress=say)
    assert result.changed == [P68, LAYOUT] and not result.ok
    assert result.failures[0][0] == "R.SLDASM" and result.failures[0][1].startswith("it stopped on an unexpected")


# -- W4 review: Update touches only the documents it changes (S2) ---------------------------------------------


def test_an_update_leaves_a_part_that_holds_its_values_untouched_and_unmeasured():
    """W4 review S2: on SolidWorks 2026 every Update marked every part modified, because the check measured each
    part's trig units (an equation added and deleted)."""
    fake = _built_gearbox()
    fake.touched.clear()
    result = _update(fake)
    assert result.ok and result.changed == [P68, LAYOUT, ASM]
    assert fake.touched == {_key(P68), _key(LAYOUT), _key(ASM)}           # not Gear_m1.5_N17
    assert result.parts[0].changed == [] and result.parts[0].trig == DEGREES and result.parts[0].unchanged
    measured = [i for i, (n, _) in enumerate(fake.calls) if n == "detect_trig_units"]
    assert len(measured) == 2                         # once in each document Update changes, by update_variables
    opened = [a[0] for n, a in fake.calls if n == "open_document"]
    assert opened.count(P17) == 1                     # read in the check, and never opened again to change it


@pytest.mark.parametrize("trig", [DEGREES, RADIANS])
def test_an_update_that_changes_nothing_touches_nothing(trig):
    fake = _built_gearbox(trig=trig)
    fake.touched.clear()
    result = _update(fake, parts=[swbuild.DocumentValues(P17, _values(S17)), swbuild.DocumentValues(P68, _values(S68))],
                     layout=swbuild.DocumentValues(LAYOUT, LAYOUT_VALUES, LAYOUT_FEATURES), placements=_placements())
    assert result.ok and result.changed == [] and fake.touched == set()
    assert "detect_trig_units" not in names(fake) and "rebuild" not in names(fake)
    assert [r.trig for r in result.parts] == [trig, trig]
    assert result.log_lines()[-1] == "nothing changed in SolidWorks"


def test_a_part_whose_text_is_the_degree_form_but_whose_unit_is_radians_does_not_hold_its_values():
    """W4 review N5: the read-only decision took the text alone, so a part holding the degree form of its trig
    globals whose angle unit was later set to radians — its geometry evaluating cos(20 rad) — was called correct,
    reused, and left alone by Update. The values SolidWorks evaluates now decide too."""
    fake = FakeSolidWorks(trig=DEGREES)
    _saved_part(fake, S17, P17)
    fake.trig = RADIANS                                    # the document's unit set to radians since it was built
    trig_globals = [v.name for v in _values(S17) if v.expression_for(DEGREES) != v.expression_for(RADIANS)]
    assert trig_globals                                    # a spur part has some: the case is real
    _, result = _build(fake, parts=[], reuse=[swbuild.DocumentValues(P17, _values(S17))], layout=None, assembly=None)
    ((path, why),) = result.mismatched
    assert path == P17 and why.startswith(
        "Gear_m1.5_N17.SLDPRT does not hold what the workbook asks of it, so it cannot be reused: its equations are "
        f'written for degrees, but SolidWorks evaluates them otherwise ("{trig_globals[0]}" is ')
    assert why.endswith("here), so its angle unit was changed since they were written.")
    # Update no longer leaves it alone: it measures the unit and writes the radian forms.
    fake.calls.clear()
    result = _update(fake, parts=[swbuild.DocumentValues(P17, _values(S17))], layout=None, assembly="",
                     placements=[])
    assert result.ok and result.changed == [P17] and result.parts[0].trig == RADIANS
    assert "detect_trig_units" in names(fake)
    held = dict(split_equation(t) for t in fake.memory[_key(P17)][0])
    assert all(held[v.name].replace(" ", "") == v.expression_for(RADIANS).replace(" ", "") for v in _values(S17))


def test_a_part_whose_unit_and_text_agree_is_still_left_alone_in_either_unit():
    for trig in (DEGREES, RADIANS):
        fake = FakeSolidWorks(trig=trig)
        _saved_part(fake, S17, P17)
        result = _update(fake, parts=[swbuild.DocumentValues(P17, _values(S17))], layout=None, assembly="",
                         placements=[])
        assert result.ok and result.changed == [] and "detect_trig_units" not in names(fake)


def test_new_values_that_evaluate_in_one_trig_unit_only_are_measured_to_decide():
    odd = (GlobalVariable("No. of Teeth", "69", radian_expression='"Nowhere" * 2'),)
    fake = _built_gearbox(trig=DEGREES)
    result = _update(fake, parts=[swbuild.DocumentValues(P68, odd)], layout=None, assembly="", placements=[])
    assert result.ok and result.changed == [P68]
    fake = _built_gearbox(trig=RADIANS)
    with pytest.raises(swbuild.BuildError, match="Gear_m1.5_N68.SLDPRT cannot be updated: the new values do not "
                                                 "evaluate: "):
        _update(fake, parts=[swbuild.DocumentValues(P68, odd)], layout=None, assembly="", placements=[])
    assert "set_global_variable" not in names(fake)


def test_an_update_notes_each_files_time_before_it_changes_anything():
    fake = _built_gearbox()
    times = {_key(P17): 1.0, _key(P68): 2.0, _key(LAYOUT): 3.0}

    def mtime(path):
        if _key(path) not in times:
            raise OSError("not there")
        return times[_key(path)]
    result = _update(fake, mtime=mtime)
    assert result.mtimes == {P17: 1.0, P68: 2.0, LAYOUT: 3.0}         # the assembly's time could not be read


def test_every_same_named_document_open_elsewhere_is_named_in_one_refusal():
    """Review S3: a refusal that concerns several files names all of them."""
    fake = FakeSolidWorks(open_docs=[DocInfo("Gear_m1.5_N17.SLDPRT", r"C:\Other\Gear_m1.5_N17.SLDPRT", 1),
                                     DocInfo("R.SLDASM", r"C:\Other\R.SLDASM", 2)])
    with pytest.raises(swbuild.BuildError) as raised:
        _build(fake)
    assert str(raised.value) == (r"C:\Other\Gear_m1.5_N17.SLDPRT is open in SolidWorks, and it has the same file name "
                                 r"as C:\W\Gear_m1.5_N17.SLDPRT, which this job would make; C:\Other\R.SLDASM is open "
                                 r"in SolidWorks, and it has the same file name as C:\W\R.SLDASM, which this job would "
                                 "make; SolidWorks keeps one document per file name, so close Gear_m1.5_N17.SLDPRT and "
                                 "R.SLDASM in SolidWorks and try again.")
    assert fake.calls == []


# -- probe assembly_rebuild_scope: an assembly rebuild marks the assembly, never parts it did not change ---------
#
# The W4 rerun on SolidWorks 2026 failed three checks for one fault: the app rebuilt assemblies with
# ForceRebuild3(False), which marks every component modified, so SolidWorks asked to save parts no job had changed
# (parts earlier revisions share among them). The fake marks what probe assembly_rebuild_scope saw each rebuild
# mark (its docstring), choosing the member through swcom.rebuild_call as Session does; FULL is the route the app
# used to take for the static gearbox, to show the fault.

FULL = {"ASSEMBLY_REBUILD_ROUTE": "ForceRebuild3(False)", "ASSEMBLY_REBUILD_TOP_ONLY": False}
R1_LAYOUT, R1_ASM = W + "R_r1_Layout.SLDPRT", W + "R_r1.SLDASM"


def _full_rebuild(monkeypatch):
    for name, value in FULL.items():
        monkeypatch.setattr(findings, name, value)


def _build_again(fake):
    """Revision 1 of the gearbox: G1's part reused from revision 0 (shared by both assemblies), G2 a new part."""
    _, result = _build(fake, parts=[plan(S68, path=P68B)], reuse=[swbuild.DocumentValues(P17, _values(S17))],
                       layout=_layout_plan(R1_LAYOUT), assembly=_gearbox_assembly((P17, P68B), R1_LAYOUT, R1_ASM))
    assert result.ok, result.log_lines()
    return result


def test_a_fresh_build_leaves_every_part_and_the_layout_as_saved():
    fake, result = _build()
    assert result.ok and result.assembly.rebuilt
    # Every part and the layout read as saved; the assembly reads modified, because a read after its save marks it
    # (probe assembly_rebuild_scope's flags_after_reads; the fake pins it on the interference check), with nothing
    # lost by not saving it.
    assert fake.touched == {_key(ASM)}


def test_a_fresh_build_with_the_old_full_rebuild_left_every_part_marked(monkeypatch):
    _full_rebuild(monkeypatch)
    fake, result = _build()
    assert result.ok and fake.touched == {_key(P17), _key(P68), _key(LAYOUT), _key(ASM)}   # the rerun's fault


def test_a_build_again_leaves_the_part_it_reuses_as_saved():
    """W4 rerun failure 2: the superseded G1 part, which nothing changed, read modified after _r2."""
    fake = _built_gearbox()
    fake.touched.clear()
    _build_again(fake)
    assert fake.touched == {_key(R1_ASM)}            # the mark of the reads after its save alone


def test_a_build_again_with_the_old_full_rebuild_marked_the_shared_part(monkeypatch):
    fake = _built_gearbox()
    fake.touched.clear()
    _full_rebuild(monkeypatch)
    _build_again(fake)
    assert _key(P17) in fake.touched


def _update_r1(fake, **kwargs):
    kwargs.setdefault("parts", [swbuild.DocumentValues(P17, _values(S17)), swbuild.DocumentValues(P68B, _values(S69))])
    kwargs.setdefault("layout", swbuild.DocumentValues(R1_LAYOUT, (GlobalVariable("S2 X", "64.5"),), LAYOUT_FEATURES))
    kwargs.setdefault("assembly", R1_ASM)
    return _update(fake, **kwargs)


def test_an_update_marks_only_the_part_it_changed_the_layout_and_the_assembly():
    """W4 rerun failure 1: after an Update that gave G2 69 teeth and moved S2, all six documents read modified."""
    fake = _built_gearbox()
    _build_again(fake)
    fake.touched.clear()
    result = _update_r1(fake)
    assert result.ok, result.log_lines()
    assert result.changed == [P68B, R1_LAYOUT, R1_ASM] and result.placed == ["G2"]
    # G1's part, shared with revision 0, and every document of revision 0 read as saved.
    assert fake.touched == {_key(P68B), _key(R1_LAYOUT), _key(R1_ASM)}


def test_an_update_with_the_old_full_rebuild_marked_every_part(monkeypatch):
    fake = _built_gearbox()
    _build_again(fake)
    fake.touched.clear()
    _full_rebuild(monkeypatch)
    _update_r1(fake)
    assert {_key(P17), _key(P68B), _key(R1_LAYOUT), _key(R1_ASM)} <= fake.touched


def test_a_pure_move_marks_only_the_layout_and_the_assembly():
    """W4 rerun failure 3 (demonstration b): a move that changed no part marked all four gear parts modified."""
    fake = _built_gearbox()
    fake.touched.clear()
    result = _update(fake, parts=[swbuild.DocumentValues(P17, _values(S17)), swbuild.DocumentValues(P68, _values(S68))],
                     placements=_placements((TURNED2, (64.5, 0.0, 0.0))))
    assert result.ok, result.log_lines()
    assert result.changed == [LAYOUT, ASM] and result.placed == ["G2"]
    assert fake.touched == {_key(LAYOUT), _key(ASM)}


def test_a_put_alone_marks_nothing_its_rebuild_marks_the_assembly():
    assert findings.PUT_MARKS_ASSEMBLY_MODIFIED is False
    fake = _built_gearbox()
    fake.open_document(ASM)
    fake.touched.clear()
    fake.find_component("g2", "gear2-1")
    fake.place_component("g2", TURNED2, (64.5, 0.0, 0.0), kind=swcom.ASSEMBLY_STATIC)
    assert fake.touched == {_key(ASM)}


def test_a_component_that_fails_still_fails_the_assemblys_top_only_rebuild():
    fake = _built_gearbox()
    fake.failed_documents = {_key(P68)}
    result = _update(fake)
    assert not result.rebuilt and ("R.SLDASM", "SolidWorks reported an error rebuilding R.") in result.failures


UNSETTLED = [({"ASSEMBLY_REBUILD_ROUTE": None}, "How to rebuild an assembly has not been settled on SolidWorks yet "
              "(findings.ASSEMBLY_REBUILD_ROUTE is None), so no assembly is changed; run probe tier 7 first."),
             ({"ASSEMBLY_REBUILD_ROUTE": "ForceRebuild3(maybe)"},
              "How to rebuild an assembly has not been settled on SolidWorks yet (findings.ASSEMBLY_REBUILD_ROUTE is "
              "'ForceRebuild3(maybe)'), so no assembly is changed; run probe tier 7 first."),
             ({"ASSEMBLY_REBUILD_TOP_ONLY": None},
              "findings.ASSEMBLY_REBUILD_ROUTE is 'ForceRebuild3(True)' but findings.ASSEMBLY_REBUILD_TOP_ONLY is None, "
              "and the two disagree, so no assembly is changed; run probe tier 7 again.")]
CHANGES = ("new_part", "new_assembly", "set_global_variable", "add_global_variable", "place_component", "rebuild",
           "save_as", "detect_trig_units")


@pytest.mark.parametrize("unsettled, sentence", UNSETTLED)
def test_an_update_refuses_an_unsettled_assembly_rebuild_before_changing_anything(monkeypatch, unsettled, sentence):
    fake = _built_gearbox()
    for name, value in unsettled.items():
        monkeypatch.setattr(findings, name, value)
    fake.touched.clear()
    with pytest.raises(swbuild.BuildError) as raised:
        _update(fake)
    assert str(raised.value) == sentence
    assert not any(n in CHANGES for n in names(fake)) and fake.touched == set()


@pytest.mark.parametrize("unsettled, sentence", UNSETTLED)
def test_a_static_build_refuses_an_unsettled_assembly_rebuild_before_making_anything(monkeypatch, unsettled,
                                                                                    sentence):
    for name, value in unsettled.items():
        monkeypatch.setattr(findings, name, value)
    for make in (lambda fake: _build(fake),
                 lambda fake: swbuild.build(fake, _gearbox_assembly(), never_exists)):
        fake = FakeSolidWorks()
        with pytest.raises(swbuild.BuildError) as raised:
            make(fake)
        assert str(raised.value) == sentence
        assert not any(n in CHANGES for n in names(fake))


def test_parts_alone_are_built_whatever_the_assembly_route_says(monkeypatch):
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_ROUTE", None)
    fake, result = _build(layout=None, assembly=None)
    assert result.ok and [r.saved for r in result.parts.built] == [P17, P68]


# -- three kinds of assembly (the reviews of 9c39fb8 and 31d1ac9): a pair keeps the full rebuild tiers 4 and 5 ran,
# a mated workbook train takes MATED_ASSEMBLY_REBUILD_ROUTE (full while None), the static gearbox top-only.
#
# Probe assembly_rebuild_scope tried fixed components only. The train's finding is measured on the workbook train's
# mates (axis coincident, an axial distance linked to a global, locks, gear mates); a pair has other mates (its
# centre-distance equation, mesh, shaft and point mates), so a pair never reads it, and PLAN-GEARBOX keeps
# build_pair as it is. A pair build does not depend on the tier-7 workbook finding either.

FULL_CALL = ("ForceRebuild3", (False,))
TOP_CALL = ("ForceRebuild3", (True,))
PAIR_PATHS = (r"C:\g\a.SLDPRT", r"C:\g\b.SLDPRT", "", r"C:\g\Pair.SLDASM")
PAIR, TRAIN, STATIC = swcom.ASSEMBLY_PAIR, swcom.ASSEMBLY_TRAIN, swcom.ASSEMBLY_STATIC


def _pair_kinds():
    """Every kind of pair assembly the app builds, by its own planners."""
    from gear_generator.gears import pair
    from test_gears_bevel import spec as bevel_spec
    from test_gears_crossed import gears as crossed_gears

    spur_a, spur_b = GearSpec(module="1.5", teeth="20"), GearSpec(module="1.5", teeth="60")
    hel_a = GearSpec(kind="helical", module="2", teeth="20", helix_angle="15")
    hel_b = hel_a.with_values(teeth="40", hand="left")
    her_a = GearSpec(kind="herringbone", module="2", teeth="20", helix_angle="30", face_width="20")
    her_b = her_a.with_values(teeth="40", hand="left", face_width="16")
    pinion, ring = GearSpec(module="2", teeth="20"), GearSpec(module="2", teeth="60", teeth_side="internal")
    cross_a, cross_b = crossed_gears()
    out = {}
    for name, (a, b) in (("spur", (spur_a, spur_b)), ("helical", (hel_a, hel_b)), ("herringbone", (her_a, her_b)),
                         ("ring", (pinion, ring))):
        out[f"{name}, fixed"] = pair.assembly_plan(a, b, *PAIR_PATHS)
        out[f"{name}, gear mate"] = pair.assembly_plan(a, b, *PAIR_PATHS, motion="gear mate")
    for route in (pair.ROUTE_MATES, pair.ROUTE_FIXED):
        out[f"crossed, {route}"] = pair.crossed_assembly_plan(cross_a, cross_b, *PAIR_PATHS, 90.0, route)
    out["bevel"] = pair.assembly_plan(bevel_spec(), bevel_spec("40", "20"), *PAIR_PATHS)
    return out


@pytest.fixture
def gear_mates_settled(monkeypatch):
    """The gear-mate findings, and neither the train's nor a pair's rebuild finding: what the full route is pinned
    under, whatever the W5 probe batch later sets the train's to (a test that wants one set sets it)."""
    for name, value in (("GEAR_MATE_ROUTE", "mates"), ("MATE_GEAR", 10), ("GEAR_MATE_NUMERATOR_FIRST", True),
                        ("GEAR_MATE_EXTERNAL_FLIP", False)):
        monkeypatch.setattr(findings, name, value)
    monkeypatch.setattr(findings, "MATED_ASSEMBLY_REBUILD_ROUTE", None, raising=False)
    monkeypatch.setattr(findings, "PAIR_ASSEMBLY_REBUILD_ROUTE", None, raising=False)


def _build_pair(fake, assembly):
    return swbuild.build_pair(fake, plan(S17, path=PAIR_PATHS[0]), plan(S68, path=PAIR_PATHS[1]), assembly,
                              never_exists)


@pytest.mark.parametrize("findings_set", [{}, {"ASSEMBLY_REBUILD_ROUTE": None}, {"ASSEMBLY_REBUILD_ROUTE": "guess"},
                                          {"MATED_ASSEMBLY_REBUILD_ROUTE": "ForceRebuild3(True)"},
                                          {"MATED_ASSEMBLY_REBUILD_ROUTE": "ForceRebuild3(True)",
                                           "ASSEMBLY_REBUILD_ROUTE": None}])
def test_every_pair_kind_rebuilds_and_puts_in_full_whatever_the_workbook_findings(monkeypatch, gear_mates_settled,
                                                                                  findings_set):
    """The same COM members as at e57aca7 for all eleven: neither the tier-7 finding nor the train's moves a pair."""
    for name, value in findings_set.items():
        monkeypatch.setattr(findings, name, value, raising=False)
    kinds = _pair_kinds()
    assert len(kinds) == 11
    for name, assembly in kinds.items():
        assert assembly.check() == [], name
        fake = FakeSolidWorks()
        result = _build_pair(fake, assembly)
        assert result.ok and result.assembly.ok, (name, result.log_lines())
        start = names(fake).index("new_assembly")
        puts = names(fake)[start:].count("place_component")
        # The assembly's members: one per put (its own rebuild) and its one rebuild, every one the full rebuild.
        assert fake.rebuild_members[-(puts + 1):] == [FULL_CALL] * (puts + 1), name
        assert fake.assembly_kinds == [PAIR] * (puts + 1), name


def test_a_crossed_pair_placed_fixed_has_no_mate_and_is_still_built_as_a_pair(gear_mates_settled):
    fixed = _pair_kinds()["crossed, fixed"]
    assert not swbuild.is_mated(fixed) and swbuild.workbook_assembly_kind(fixed) == STATIC   # alone: static
    fake = FakeSolidWorks()
    _build_pair(fake, fixed)
    assert set(fake.assembly_kinds) == {PAIR} and fake.rebuild_members[-1] == FULL_CALL


@pytest.mark.parametrize("train_route, wanted", [(None, FULL_CALL), ("ForceRebuild3(True)", TOP_CALL)])
def test_a_plan_with_mates_built_outside_build_pair_is_a_train(gear_mates_settled, monkeypatch, train_route, wanted):
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_ROUTE", None)            # a train does not lean on tier 7
    monkeypatch.setattr(findings, "MATED_ASSEMBLY_REBUILD_ROUTE", train_route, raising=False)
    mated = _pair_kinds()["spur, gear mate"]
    assert swbuild.workbook_assembly_kind(mated) == TRAIN
    fake = FakeSolidWorks()
    result = swbuild.build(fake, mated, never_exists)
    assert result.ok and fake.rebuild_kinds == [TRAIN] and set(fake.rebuild_members) == {wanted}


def test_with_the_trains_route_set_a_train_is_top_only_and_a_pair_still_full(monkeypatch, gear_mates_settled):
    monkeypatch.setattr(findings, "MATED_ASSEMBLY_REBUILD_ROUTE", "ForceRebuild3(True)", raising=False)
    mated = _pair_kinds()["spur, gear mate"]
    train = FakeSolidWorks()
    swbuild.build(train, mated, never_exists)
    pair_fake = FakeSolidWorks()
    _build_pair(pair_fake, mated)
    assert set(train.rebuild_members) == {TOP_CALL}
    assert pair_fake.rebuild_members[-1] == FULL_CALL and set(pair_fake.assembly_kinds) == {PAIR}


def test_a_pair_route_once_set_is_taken_by_pairs_alone(monkeypatch, gear_mates_settled):
    monkeypatch.setattr(findings, "PAIR_ASSEMBLY_REBUILD_ROUTE", "ForceRebuild3(True)", raising=False)
    mated = _pair_kinds()["spur, gear mate"]
    pair_fake, train = FakeSolidWorks(), FakeSolidWorks()
    _build_pair(pair_fake, mated)
    swbuild.build(train, mated, never_exists)
    assert pair_fake.rebuild_members[-1] == TOP_CALL and set(train.rebuild_members) == {FULL_CALL}


def test_the_static_gearbox_still_rebuilds_and_puts_top_only():
    fake, result = _build()
    assert result.ok
    start = names(fake).index("new_assembly")
    puts = names(fake)[start:].count("place_component")
    assert puts == 3 and fake.rebuild_members[-(puts + 1):] == [TOP_CALL] * (puts + 1)
    assert fake.assembly_kinds == [STATIC] * (puts + 1)


@pytest.mark.parametrize("name, sentence", [
    ("PAIR_ASSEMBLY_REBUILD_ROUTE", "findings.PAIR_ASSEMBLY_REBUILD_ROUTE is 'guess', which is not a rebuild this "
                                    "code knows, so no pair assembly is changed; run its probe again."),
    ("MATED_ASSEMBLY_REBUILD_ROUTE", "findings.MATED_ASSEMBLY_REBUILD_ROUTE is 'guess', which is not a rebuild this "
                                     "code knows, so no mated assembly is changed; run its probe again."),
])
def test_an_unknown_route_refuses_its_own_kind_before_anything_is_made(monkeypatch, gear_mates_settled, name,
                                                                       sentence):
    """The review of 31d1ac9: the refusal came after both gears were saved (new_part, save_as, new_part, save_as),
    leaving files with no sidecars that the next Build refused to overwrite. Each finding refuses its own kind."""
    monkeypatch.setattr(findings, name, "guess", raising=False)
    mated = _pair_kinds()["spur, gear mate"]
    refused = (lambda fake: _build_pair(fake, mated)) if name.startswith("PAIR") else \
        (lambda fake: swbuild.build(fake, mated, never_exists))
    fake = FakeSolidWorks()
    with pytest.raises(swbuild.BuildError) as raised:
        refused(fake)
    assert str(raised.value) == sentence
    assert not any(n in CHANGES for n in names(fake)) and fake.saved == {}
    built = (lambda fake: swbuild.build(fake, mated, never_exists)) if name.startswith("PAIR") else \
        (lambda fake: _build_pair(fake, mated))
    other = FakeSolidWorks()
    assert built(other).ok                                    # the other kind does not read it


def test_no_rebuild_member_is_called_but_through_the_one_decision():
    """The review of 9c39fb8: every ForceRebuild3 / EditRebuild3 the app makes goes through swcom.rebuild_call and
    its table, so the route is decided in one place (the probes call COM raw on purpose and are left out)."""
    import ast
    import pathlib

    import gear_generator

    root = pathlib.Path(gear_generator.__file__).parent
    members = {"ForceRebuild3", "EditRebuild3"}
    found = []
    for path in sorted(root.rglob("*.py")):
        if "probe" in path.relative_to(root).parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = set()
        for node in ast.walk(tree):
            inside = (isinstance(node, ast.FunctionDef) and node.name == "rebuild_call") or (
                isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ASSEMBLY_REBUILD_CALLS"
                                                     for t in node.targets))
            if inside:
                allowed.update(id(n) for n in ast.walk(node))
        for node in ast.walk(tree):
            named = (isinstance(node, ast.Constant) and node.value in members) or (
                isinstance(node, ast.Attribute) and node.attr in members)
            if named and id(node) not in allowed:
                found.append(f"{path.relative_to(root)}:{node.lineno}")
    assert found == []


# -- the review of 31d1ac9: an assembly's kind is always said; one that is not is refused ---------------------

UNSAID = ("This assembly was to be rebuilt without saying what kind of assembly it is (fixed, a mated train or a "
          "pair), so which rebuild it takes cannot be chosen and nothing is changed; that is a fault in Gear "
          "Generator, not in SolidWorks.")


def test_an_assembly_rebuild_or_put_whose_kind_is_not_said_is_refused():
    fake = _built_gearbox()
    fake.open_document(ASM)
    fake.touched.clear()
    with pytest.raises(SolidWorksError) as raised:
        fake.rebuild()
    assert str(raised.value) == UNSAID
    fake.find_component("g2", "gear2-1")
    with pytest.raises(SolidWorksError) as raised:
        fake.place_component("g2", TURNED2, (64.5, 0.0, 0.0))
    assert str(raised.value) == UNSAID
    with pytest.raises(SolidWorksError, match="'mated' is not a kind of assembly Gear Generator rebuilds"):
        fake.rebuild(kind="mated")


def test_a_part_rebuilds_whether_or_not_a_kind_is_said():
    fake = FakeSolidWorks()
    fake.new_part()
    assert fake.rebuild() is True and fake.rebuild_members == [FULL_CALL]


def test_every_static_site_says_its_kind():
    fake, result = _build()
    assert result.ok and fake.assembly_kinds and set(fake.assembly_kinds) == {STATIC}   # build_gearbox: 3 puts, 1 rebuild
    fake.calls.clear()
    fake.assembly_kinds.clear()
    fake.frames = {"layout-1": (IDENTITY, (0.0, 0.0, 0.0)), "gear1-1": (IDENTITY, (0.0, 0.0, 0.0)),
                   "gear2-1": (TURNED2, AT2)}
    update = _update(fake)
    assert update.ok and update.placed == ["G2"]
    assert fake.assembly_kinds == [STATIC, STATIC]               # update_gearbox: its put, then its one rebuild


def test_every_put_in_the_app_and_its_scripts_names_its_kind():
    """A put is always on an assembly, so every place_component call says kind=… (a rebuild's document is known
    only at run time: the fake refuses an assembly rebuild with no kind, which the build and update tests meet)."""
    import ast
    import pathlib

    import gear_generator

    root = pathlib.Path(gear_generator.__file__).parent
    scripts = pathlib.Path(__file__).resolve().parents[1] / "probe"
    missing = []
    for path in sorted(list(root.rglob("*.py")) + list(scripts.glob("*.py"))):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "place_component" and \
                    not any(k.arg == "kind" for k in node.keywords):
                missing.append(f"{path.name}:{node.lineno}")
    assert missing == []


# -- W5: the train (W5-PLAN §1.4, §3.1; W5-INTERFACES.md; W5-DECISIONS.md) --------------------------------------------
#
# A 12 : 1 reducer as workbook.motion.motion_assembly_plan's docstring orders it, written by hand here (package B
# writes the planner): G1 (17) on S1 at the origin, G2 (68) and G3 (17) on S2 — G3 locked to G2 — and G4 (51) on S3,
# every shaft Z+; G1 and G2 coincident with the Front plane, G4 20 mm along S3 on the global "G4 Face Z".

P51 = W + "Gear_m1.5_N51.SLDPRT"
S51 = GearSpec().with_values(teeth="51")
T_LAYOUT, T_ASM = W + "T_Layout.SLDPRT", W + "T.SLDASM"
TEETH = {"G1": 17, "G2": 68, "G3": 17, "G4": 51}
TRAIN_GEARS = {"gear1": "G1", "gear2": "G2", "gear3": "G3", "gear4": "G4"}
TRAIN_PARTS = {"gear1": P17, "gear2": P68, "gear3": P17, "gear4": P51}


def _train_frames(s3=(63.75, 51.0), z4=20.0):
    return {"G1": (_rot_z(0.0), (0.0, 0.0, 0.0)), "G2": (_rot_z(180.0 / 68), (63.75, 0.0, 0.0)),
            "G3": (_rot_z(0.0), (63.75, 0.0, 20.0)), "G4": (_rot_z(180.0 / 51), (s3[0], s3[1], z4))}


def _train_layout_plan(path=T_LAYOUT):
    return BuildPlan("layout", "", (
        ops.NewPart(""),
        ops.AddGlobal("S2 X", "63.75"), ops.AddGlobal("S3 X", "63.75"), ops.AddGlobal("S3 Y", "51"),
        ops.RefPlane("x2", "S2 X Plane", 3, 63.75), ops.RefPlane("x3", "S3 X Plane", 3, 63.75),
        ops.RefPlane("y3", "S3 Y Plane", 2, 51.0),
        ops.Axis("axis1", "S1 Axis", (2, 3)), ops.Axis("axis2", "S2 Axis", (2, "x2")),
        ops.Axis("axis3", "S3 Axis", ("x3", "y3")),
        ops.Rebuild(), ops.SaveAs(path),
    ), path)


T_LAYOUT_FEATURES = ("S2 X Plane", "S3 X Plane", "S3 Y Plane", "S1 Axis", "S2 Axis", "S3 Axis")


def _train_layout_values(s3x="63.75"):
    return swbuild.DocumentValues(T_LAYOUT, (GlobalVariable("S2 X", "63.75"), GlobalVariable("S3 X", s3x),
                                             GlobalVariable("S3 Y", "51")), T_LAYOUT_FEATURES)


def _train_plan(path=T_ASM, follower_on_axis=False, loop=False, second_axis=False):
    frames = _train_frames()
    steps = [ops.NewAssembly(""), ops.AddGlobal("G4 Face Z", "20"),
             ops.AddComponent("layout", T_LAYOUT), ops.Place("layout", IDENTITY, (0.0, 0.0, 0.0)), ops.Fix("layout")]
    for handle, gear in TRAIN_GEARS.items():
        rotation, at = frames[gear]
        steps += [ops.AddComponent(handle, TRAIN_PARTS[handle], at), ops.Place(handle, rotation, at), ops.Fix(handle)]
    steps += [ops.Unfix("gear1"),
              ops.Mate("axis1", "coincident", "gear1:Gear Axis", "layout:S1 Axis", name="G1 on S1 Axis"),
              ops.Mate("along1", "point", "gear1:origin", "layout:plane1", name="G1 along S1"),
              ops.Unfix("gear2"),
              ops.Mate("axis2", "coincident", "gear2:Gear Axis", "layout:S2 Axis", name="G2 on S2 Axis"),
              ops.Mate("along2", "point", "gear2:origin", "layout:plane1", name="G2 along S2"),
              ops.Unfix("gear3"),
              ops.Mate("lock1", "lock", "gear2", "gear3", name="G3 locked to G2")]
    if follower_on_axis:
        steps.append(ops.Mate("axis9", "coincident", "gear3:Gear Axis", "layout:S2 Axis", name="G3 on S2 Axis"))
    if second_axis:
        steps.append(ops.Mate("axis8", "coincident", "gear1:Gear Axis", "layout:S2 Axis", name="G1 on S2 Axis"))
    steps += [ops.Unfix("gear4"),
              ops.Mate("axis3", "coincident", "gear4:Gear Axis", "layout:S3 Axis", name="G4 on S3 Axis"),
              ops.Mate("along3", "point distance", "gear4:origin", "layout:plane1", 20.0, name="G4 along S3"),
              ops.LinkDimension("D1@G4 along S3", '"G4 Face Z"'),
              ops.Mate("mesh1", "gear", "gear1:Gear Axis", "gear2:Gear Axis", name="G1 meshes G2", ratio=(17.0, 68.0)),
              ops.Mate("mesh2", "gear", "gear3:Gear Axis", "gear4:Gear Axis", name="G3 meshes G4", ratio=(17.0, 51.0))]
    if loop:
        steps.append(ops.Mate("mesh3", "gear", "gear4:Gear Axis", "gear1:Gear Axis", name="G4 meshes G1",
                              ratio=(51.0, 17.0)))
    return BuildPlan("gearbox", "", tuple(steps) + (ops.Rebuild(), ops.SaveAs(path)), path)


TRAIN_MATES = ["G1 on S1 Axis", "G1 along S1", "G2 on S2 Axis", "G2 along S2", "G3 locked to G2", "G4 on S3 Axis",
               "G4 along S3", "G1 meshes G2", "G3 meshes G4"]


def _build_train(fake=None, **kwargs):
    fake = fake or FakeSolidWorks()
    kwargs.setdefault("parts", [plan(S17, path=P17), plan(S68, path=P68), plan(S51, path=P51)])
    kwargs.setdefault("layout", _train_layout_plan())
    kwargs.setdefault("assembly", _train_plan())
    kwargs.setdefault("gears", TRAIN_GEARS)
    kwargs.setdefault("exists", fake.exists)
    return fake, swbuild.build_gearbox(fake, **kwargs)


def _close(f1, f2, tolerance=1e-9):
    rotation_off, origin_off = _frame_off(f1, f2)
    return rotation_off <= tolerance and origin_off <= tolerance


def test_the_train_plans_here_are_sound():
    for doctored in ({}, {"follower_on_axis": True}, {"loop": True}, {"second_axis": True}):
        assert _train_plan(**doctored).check() == [], doctored
    assert _train_layout_plan().check() == []


# -- the fake's own model of mates


def test_the_fake_keeps_a_trains_mates_with_its_document_and_reopens_them():
    fake, result = _build_train()
    assert result.ok, result.log_lines()
    assert [m.name for m in fake.saved_mates[_key(T_ASM)]] == TRAIN_MATES
    assert fake.mate("G4 along S3").link == "G4 Face Z"
    assert fake.mate("G3 locked to G2").a == ("gear2-1", "") and fake.mate("G3 locked to G2").b == ("gear3-1", "")
    fake.close_all()
    fake.open_document(T_ASM)
    assert [m.name for m in fake.mates] == TRAIN_MATES and fake.mate("G4 along S3").link == "G4 Face Z"


def test_an_undoctored_train_reads_clean_in_the_fake():
    fake, result = _build_train()
    assert all(fake.mate_status(name) == findings.ADD_MATE_NO_ERROR for name in TRAIN_MATES)
    assert fake.mate_states() == [swcom.MateState(name) for name in TRAIN_MATES]
    assert [fake.constrained_status(n) for n in ("gear1-1", "gear2-1", "gear3-1", "gear4-1")] == [2, 2, 2, 2]
    assert fake.constrained_status("layout-1") == findings.COMPONENT_FULLY_DEFINED      # the layout stays fixed
    for gear, frame in _train_frames().items():                          # mated where W4 placed them: nothing moved
        assert _close(fake.frames[f"gear{gear[1]}-1"], frame)


@pytest.mark.parametrize("doctored, flagged, fought", [
    ({"follower_on_axis": True}, "G3 on S2 Axis", ["G3 locked to G2"]),
    ({"second_axis": True}, "G1 on S2 Axis", ["G1 on S1 Axis"]),
    ({"loop": True}, "G4 meshes G1", ["G1 meshes G2", "G3 meshes G4"]),
])
def test_the_fake_flags_what_tier_eight_saw_over_define_a_train(doctored, flagged, fought):
    fake = FakeSolidWorks()
    swbuild.build(fake, _train_plan(**doctored), never_exists)
    assert fake.mate_status(flagged) == findings.ADD_MATE_OVER_DEFINED
    states = {s.name: s for s in fake.mate_states()}
    assert (states[flagged].code, states[flagged].warning) == (46, False)
    assert [n for n, s in states.items() if s.code and s.warning] == fought
    assert fake.constrained_status(fake.mate(flagged).a[0]) == findings.COMPONENT_OVER_DEFINED


def _reopened_train(fake):
    fake.open_document(T_LAYOUT)
    fake.open_document(T_ASM)
    for index in range(1, 5):
        fake.find_component(f"placed{index}", f"gear{index}-1")


def test_a_layout_move_carries_the_anchor_to_its_new_axis_swung_the_wrong_way_and_its_follower_with_it():
    fake, _ = _build_train()
    fake.open_document(T_LAYOUT)
    fake.set_global_variable("S2 X", "64.5")
    _reopened_train(fake)
    g3_before = fake.frames["gear3-1"]
    fake.rebuild(kind=swcom.ASSEMBLY_TRAIN)
    rotation, at = fake.frames["gear2-1"]
    assert at == (64.5, 0.0, 0.0)
    assert swbuild.turn_between(_train_frames()["G2"][0], rotation) == pytest.approx(math.radians(-13.0))
    relative = _compose(_inverse(fake.frames["gear2-1"]), fake.frames["gear3-1"])
    assert _close(relative, _compose(_inverse(_train_frames()["G2"]), g3_before))     # the lock held it
    assert _close(fake.frames["gear4-1"], _train_frames()["G4"])                      # S3 did not move


def test_a_face_z_global_moves_its_anchor_along_its_shaft_and_nothing_else():
    fake, _ = _build_train()
    _reopened_train(fake)
    fake.set_global_variable("G4 Face Z", "25")
    fake.rebuild(kind=swcom.ASSEMBLY_TRAIN)
    assert fake.frames["gear4-1"] == (_train_frames()["G4"][0], (63.75, 51.0, 25.0))
    assert _close(fake.frames["gear3-1"], _train_frames()["G3"])


def test_a_put_on_a_gear_held_by_a_lock_moves_it_alone_and_says_nothing_as_solidworks_did():
    """W5-DECISIONS, on P0's lock_on_put_turns: with the lock on, a Transform2 put moved one gear, its locked partner
    did not follow, and SolidWorks reported nothing."""
    fake, _ = _build_train()
    _reopened_train(fake)
    turned = (_mul(_train_frames()["G2"][0], _rot_z(7.0)), _train_frames()["G2"][1])
    fake.place_component("placed2", *turned, kind=swcom.ASSEMBLY_TRAIN)          # no raise
    assert _close(fake.frames["gear2-1"], turned) and _close(fake.frames["gear3-1"], _train_frames()["G3"])
    assert fake.locked_puts == ["gear2-1"]
    fake.find_mate("lock", "G3 locked to G2")
    fake.set_mate_suppressed("lock", True)
    fake.place_component("placed3", *_train_frames()["G3"], kind=swcom.ASSEMBLY_TRAIN)
    assert fake.locked_puts == ["gear2-1"]                                         # suppressed: an honest put


def test_a_put_an_anchors_mates_pull_back_raises_as_place_component_would():
    fake, _ = _build_train()
    _reopened_train(fake)
    with pytest.raises(SolidWorksError, match=r"^gear4-1 did not take its frame \(rotation off .*, origin .* mm\)\.$"):
        fake.place_component("placed4", _train_frames()["G4"][0], (70.0, 51.0, 20.0), kind=swcom.ASSEMBLY_TRAIN)
    with pytest.raises(SolidWorksError, match="did not take its frame"):
        fake.place_component("placed4", _train_frames()["G4"][0], (63.75, 51.0, 30.0), kind=swcom.ASSEMBLY_TRAIN)


def test_the_fake_finds_suppresses_and_remakes_mates_by_name(monkeypatch):
    fake, _ = _build_train()
    _reopened_train(fake)
    with pytest.raises(swcom.MateGone, match='^The mate "Angle1" is not in T.SLDASM any more'):
        fake.find_mate("m", "Angle1")
    fake.find_mate("m", "G3 meshes G4")
    with pytest.raises(SolidWorksError):
        fake.set_gear_ratio("m", "placed3:Gear Axis", "placed4:Gear Axis", (18, 50))       # the route is None
    monkeypatch.setattr(findings, "GEAR_MATE_RATIO_ROUTE", "remake")
    fake.set_gear_ratio("m", "placed3:Gear Axis", "placed4:Gear Axis", (18, 50))
    assert fake.mate("G3 meshes G4").ratio == (18.0, 50.0) and fake.mates[-1].name == "G3 meshes G4"
