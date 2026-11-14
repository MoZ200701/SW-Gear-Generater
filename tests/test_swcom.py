"""The parts of the SolidWorks link that are decidable without SolidWorks.

The version gate and the session choice are pure functions over plain data
precisely so they can be tested here, on a machine with no CAD package at all.
"""

import threading
import time

import pytest

from gear_generator import swcom
from gear_generator.swcom import (
    Candidate,
    NotRunning,
    SolidWorksError,
    WrongVersion,
    choose,
    is_solidworks_moniker,
    parse_revision,
    pid_from_moniker,
    release_year,
)


def session(major, minor=0, patch=0, pid=1000, has_doc=False):
    return Candidate(
        moniker=f"SolidWorks_PID_{pid}",
        pid=pid,
        revision=(major, minor, patch),
        has_active_doc=has_doc,
    )


# -- reading a version ------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [("34.0.0", (34, 0, 0)), ("34", (34,)), ("34.1.0", (34, 1, 0)), (" 33.3.0 ", (33, 3, 0))],
)
def test_parse_revision(text, expected):
    assert parse_revision(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "twenty-six", "34.x.0"])
def test_parse_revision_refuses_what_is_not_a_version(text):
    with pytest.raises(SolidWorksError, match="Could not read a version"):
        parse_revision(text)


@pytest.mark.parametrize("major,year", [(32, 2024), (33, 2025), (34, 2026), (35, 2027)])
def test_release_year_follows_the_yearly_convention(major, year):
    assert release_year(major) == year


# -- recognising a session --------------------------------------------------


@pytest.mark.parametrize("name", ["SolidWorks_PID_31392", "solidworks_pid_7"])
def test_a_session_moniker_is_recognised(name):
    assert is_solidworks_moniker(name)


@pytest.mark.parametrize(
    "name", ["", "!SolidWorks", "SolidWorksDocMgr", "SolidWorks_PID_", "SolidWorks_PID_x"]
)
def test_anything_else_is_not_a_session(name):
    assert not is_solidworks_moniker(name)


def test_the_pid_comes_out_of_the_moniker():
    """No round-trip to a session we may be about to discard."""
    assert pid_from_moniker("SolidWorks_PID_31392") == 31392


# -- choosing which session to drive ----------------------------------------


def test_nothing_running_says_so():
    with pytest.raises(NotRunning, match="No running SolidWorks"):
        choose([])


def test_only_older_versions_are_refused_by_name():
    with pytest.raises(WrongVersion) as raised:
        choose([session(30), session(31)])
    message = str(raised.value)
    assert "SolidWorks 2022" in message
    assert "SolidWorks 2023" in message
    assert "2024" in message


def test_the_supported_versions_are_taken():
    assert choose([session(34)]).revision == (34, 0, 0)
    assert choose([session(32)]).revision == (32, 0, 0)
    assert choose([session(31), session(32)]).revision == (32, 0, 0)


def test_an_older_session_alongside_a_supported_one_is_ignored():
    assert choose([session(33), session(34)]).revision == (34, 0, 0)


def test_a_newer_release_is_used_not_refused():
    """The whole point of a floor rather than an equality: 2027 must just work."""
    assert choose([session(34), session(35)]).revision == (35, 0, 0)


def test_a_service_pack_beats_the_base_release():
    assert choose([session(34, 0, 0), session(34, 1, 0)]).revision == (34, 1, 0)


def test_a_session_with_a_document_open_wins_a_tie():
    """Almost certainly the window the user is looking at."""
    quiet = session(34, pid=100, has_doc=False)
    busy = session(34, pid=200, has_doc=True)
    assert choose([quiet, busy]).pid == 200


def test_the_choice_is_deterministic_when_nothing_separates_them():
    assert choose([session(34, pid=300), session(34, pid=100)]).pid == 100


def test_a_release_newer_than_tested_is_flagged_but_still_chosen():
    chosen = choose([session(36)])
    assert chosen.revision == (36, 0, 0)
    assert swcom.is_newer_than_tested(chosen.revision)
    assert not swcom.is_newer_than_tested((34, 0, 0))


@pytest.mark.parametrize("revision,ok", [((31, 9, 9), False), ((32, 0, 0), True), ((34, 0, 0), True), ((40, 0), True)])
def test_the_floor_is_a_floor(revision, ok):
    assert swcom.meets_minimum(revision) is ok


# -- degrading without pywin32 ----------------------------------------------


def test_finding_sessions_without_pywin32_says_why(monkeypatch):
    monkeypatch.setattr(swcom, "pythoncom", None)
    assert swcom.is_available() is False
    assert swcom.unavailable_reason()
    with pytest.raises(swcom.NotAvailable):
        swcom.find_candidates()


def test_the_diagnostic_reports_a_missing_pywin32_rather_than_crashing(monkeypatch, capsys):
    monkeypatch.setattr(swcom, "pythoncom", None)
    assert swcom.main([]) == swcom.EXIT_NOT_AVAILABLE
    assert "pip install pywin32" in capsys.readouterr().out


# -- the worker thread ------------------------------------------------------


class FakeSession:
    def __init__(self):
        self.calls = []


def test_the_worker_runs_work_on_its_own_thread_and_returns_plain_data():
    worker = swcom.Worker(connect_fn=FakeSession)
    try:
        call = worker.submit(lambda s: "answer")
        value, error = call.wait(timeout=5)
        assert (value, error) == ("answer", None)
    finally:
        worker.shutdown()


def test_a_failure_comes_back_as_a_value_not_a_dead_thread():
    def explode(_session):
        raise RuntimeError("SolidWorks said no")

    worker = swcom.Worker(connect_fn=FakeSession)
    try:
        value, error = worker.submit(explode).wait(timeout=5)
        assert value is None
        assert isinstance(error, RuntimeError)

        # The thread must still be alive and usable afterwards.
        assert worker.submit(lambda s: 1).wait(timeout=5) == (1, None)
    finally:
        worker.shutdown()


def test_a_failed_call_drops_the_session_so_the_next_one_reconnects():
    made = []

    def connect_fn():
        made.append(object())
        return made[-1]

    def explode(_session):
        raise RuntimeError("connection lost")

    worker = swcom.Worker(connect_fn=connect_fn)
    try:
        worker.submit(lambda s: None).wait(timeout=5)
        assert len(made) == 1
        worker.submit(explode).wait(timeout=5)
        worker.submit(lambda s: None).wait(timeout=5)
        assert len(made) == 2
    finally:
        worker.shutdown()


def test_a_connection_failure_is_reported_not_raised_on_the_thread():
    def refuse():
        raise swcom.NotRunning("nothing there")

    worker = swcom.Worker(connect_fn=refuse)
    try:
        value, error = worker.submit(lambda s: 1).wait(timeout=5)
        assert value is None
        assert isinstance(error, swcom.NotRunning)
    finally:
        worker.shutdown()


def test_polling_returns_at_once_whether_or_not_the_answer_is_ready():
    """The interface polls this on a timer, so it must never wait for anything."""
    started = threading.Event()
    release = threading.Event()

    def slow(_session):
        started.set()
        release.wait(5)
        return 42

    worker = swcom.Worker(connect_fn=FakeSession)
    try:
        call = worker.submit(slow)
        assert started.wait(5)

        # The job is definitely still running, so poll must say "not yet"
        # rather than block until it finishes.
        began = time.monotonic()
        assert call.poll() is None
        assert time.monotonic() - began < 0.5

        release.set()
        assert call.wait(timeout=5) == (42, None)
        assert call.poll() == (42, None)
    finally:
        release.set()
        worker.shutdown()


def test_the_worker_reports_being_busy_while_a_call_is_in_flight():
    """Two interleaved refresh sequences would corrupt a part, so the window
    disables Export on this rather than queueing a second one."""
    started = threading.Event()
    release = threading.Event()

    def slow(_session):
        started.set()
        release.wait(5)
        return None

    worker = swcom.Worker(connect_fn=FakeSession)
    try:
        call = worker.submit(slow)
        assert started.wait(5)
        assert worker.busy() is True
        release.set()
        call.wait(timeout=5)
        for _ in range(100):
            if not worker.busy():
                break
            time.sleep(0.01)
        assert worker.busy() is False
    finally:
        release.set()
        worker.shutdown()


# -- W4: the members a workbook's layout part and static assembly use, against a fake COM world ----------
#
# Late binding reaches a zero-argument member as an attribute and calls only members given arguments
# (swcom.call), so the fakes below expose GetTitle, ActiveDoc, FirstFeature … as attributes and OpenDoc6,
# Select2, AddComponent5 … as methods, as SolidWorks does through pywin32.

from gear_generator import findings  # noqa: E402

W = "C:\\W\\"


class Out:
    """A by-reference integer, as swcom._out_long makes one with pywin32."""

    def __init__(self):
        self.value = 0


@pytest.fixture
def com(monkeypatch):
    monkeypatch.setattr(swcom, "_out_long", Out)
    monkeypatch.setattr(swcom, "_null_dispatch", lambda: None)
    monkeypatch.setattr(swcom.time, "sleep", lambda _seconds: None)
    return App()


class Feature:
    def __init__(self, doc, name, type_name="RefPlane", specific=None):
        self.doc, self.Name, self.GetTypeName2 = doc, name, type_name
        self.GetFirstSubFeature = None
        self.GetSpecificFeature2 = specific

    @property
    def GetNextFeature(self):
        features = self.doc.features
        index = features.index(self)
        return features[index + 1] if index + 1 < len(features) else None

    def Select2(self, append, mark):
        self.doc.app.log.append(("Select2", self.Name, append))
        self.doc.selected.append(self.Name)
        return True


class Selection:
    def __init__(self, doc):
        self.doc = doc

    def GetSelectedObjectCount2(self, mark):
        return len(self.doc.selected)


class Extension:
    def __init__(self, doc):
        self.doc = doc

    def SelectByID2(self, name, kind, x, y, z, append, mark, callout, option):
        self.doc.app.log.append(("SelectByID2", name, kind, append))
        if kind == "PLANE" and any(f.Name == name for f in self.doc.features):
            self.doc.selected.append(name)
            return True
        return False


class Transform:
    def __init__(self, data):
        self.ArrayData = tuple(data)


class Component:
    def __init__(self, name, model=None, path="", state=2, data=None):
        self.Name2, self.GetModelDoc2, self.GetPathName = name, model, path
        self.GetSuppression2 = state
        self.Transform2 = Transform(data or (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0))


class Root:
    def __init__(self, doc):
        self.doc = doc

    @property
    def GetChildren(self):
        return tuple(self.doc.components)


class Configuration:
    def __init__(self, doc):
        self.doc = doc

    def GetRootComponent3(self, resolve):
        return Root(self.doc)


class Interference:
    def __init__(self, components, volume_m3):
        self.Components, self.Volume = components, volume_m3

    @property
    def GetComponents(self):
        return self.Components


class Manager:
    def __init__(self, items, fail=False):
        self.items, self.fail, self.done, self.options = items, fail, 0, {}

    def __setattr__(self, name, value):
        if name[0].isupper():
            self.options[name] = value
        object.__setattr__(self, name, value)

    @property
    def GetInterferences(self):
        if self.fail:
            raise RuntimeError("the manager went away")
        return tuple(self.items)

    def Done(self):
        object.__setattr__(self, "done", self.done + 1)


class Doc:
    def __init__(self, app, path, doc_type=1, title=None):
        self.app, self.GetPathName, self.GetType = app, path, doc_type
        self.GetTitle = title or path.rsplit("\\", 1)[-1]
        self.features = [Feature(self, n) for n in ("Front Plane", "Top Plane", "Right Plane")]
        self.features.append(Feature(self, "Origin", "OriginProfileFeature"))
        self.selected, self.components, self.manager = [], [], None
        self.SelectionManager, self.Extension = Selection(self), Extension(self)
        self.GetActiveConfiguration = Configuration(self)
        self.GetSaveFlag, self.fails = False, False

    def ForceRebuild3(self, top_only):
        """As probe assembly_rebuild_scope found it on 2026 and 2024: the document is marked modified; a FULL
        rebuild of an assembly marks every component's document too; a component in error fails it either way."""
        self.app.log.append(("ForceRebuild3", self.GetTitle, top_only))
        return self._rebuilt(full=not top_only)

    @property
    def EditRebuild3(self):                    # a zero-argument member: late binding reads it as an attribute
        self.app.log.append(("EditRebuild3", self.GetTitle))
        return self._rebuilt(full=False)

    def _rebuilt(self, full):
        self.GetSaveFlag = True
        models = [c.GetModelDoc2 for c in self.components if c.GetModelDoc2 is not None]
        if full:
            for model in models:
                model.GetSaveFlag = True
        return not (self.fails or any(model.fails for model in models))

    @property
    def GetNext(self):
        docs = self.app.docs
        index = docs.index(self)
        return docs[index + 1] if index + 1 < len(docs) else None

    @property
    def FirstFeature(self):
        return self.features[0] if self.features else None

    @property
    def InterferenceDetectionManager(self):
        return self.manager

    def ClearSelection2(self, everything):
        self.selected = []

    def InsertAxis2(self, auto):
        self.app.log.append(("InsertAxis2", tuple(self.selected)))
        if len(self.selected) != 2:
            return False
        self.features.append(Feature(self, f"Axis{len(self.features)}", "RefAxis"))
        return True

    def GetComponentByName(self, name):
        return next((c for c in self.components if c.Name2 == name), None)

    def GetComponents(self, top):
        return tuple(self.components)

    def FeatureByName(self, name):
        component = self.GetComponentByName(name)
        return None if component is None else Feature(self, name, "Reference", specific=component)

    def AddComponent5(self, path, option, configuration, use_name, name, x, y, z):
        model = self.app.inserts.get(path, self.app.find(path))
        if model is False:
            return None
        component = Component(path.rsplit("\\", 1)[-1].rsplit(".", 1)[0] + "-1", model=model,
                              path=getattr(model, "GetPathName", ""))
        self.components.append(component)
        return component


class Spec:
    def __init__(self, path):
        self.path, self.Silent, self.Error = path, False, 0


class App:
    def __init__(self):
        self.docs, self.disk, self.log, self.active = [], {}, [], None
        self.activates, self.errors, self.inserts = True, {}, {}

    def find(self, path):
        return next((d for d in self.docs if d.GetPathName.lower() == path.lower()), None)

    def saved(self, path, doc_type=1):
        self.disk[path.lower()] = Doc(self, path, doc_type)
        return self.disk[path.lower()]

    def opened(self, path, doc_type=1, active=True):
        doc = Doc(self, path, doc_type)
        self.docs.append(doc)
        if active:
            self.active = doc
        return doc

    @property
    def GetFirstDocument(self):
        return self.docs[0] if self.docs else None

    @property
    def ActiveDoc(self):
        return self.active

    def _open(self, path):
        open_doc = self.find(path)
        if open_doc is not None:
            return open_doc, 0, swcom.findings.OPEN_DOC_ALREADY_OPEN_WARNING
        if path in self.errors:
            return None, self.errors[path], 0
        doc = self.disk.get(path.lower())
        if doc is None:
            return None, 2, 0
        self.docs.append(doc)
        self.active = doc
        return doc, 0, 0

    def OpenDoc6(self, path, doc_type, options, configuration, errors, warnings):
        self.log.append(("OpenDoc6", path, doc_type, options, configuration))
        doc, errors.value, warnings.value = self._open(path)
        return doc

    def GetOpenDocSpec(self, path):
        self.log.append(("GetOpenDocSpec", path))
        return Spec(path)

    def OpenDoc7(self, spec):
        self.log.append(("OpenDoc7", spec.path, spec.Silent))
        doc, spec.Error, _ = self._open(spec.path)
        return doc

    def OpenDoc(self, path, doc_type):
        self.log.append(("OpenDoc", path, doc_type))
        return self._open(path)[0]

    def ActivateDoc3(self, title, use_user_preferences, option, errors):
        self.log.append(("ActivateDoc3", title))
        if self.activates:
            self.active = next(d for d in self.docs if d.GetTitle == title)
        return self.active

    def GetUserPreferenceToggle(self, which):
        return False

    def SetUserPreferenceToggle(self, which, value):
        pass


def _session(app):
    return swcom.Session(app, (34, 0, 0), 1)


def _calls(app, name):
    return [entry for entry in app.log if entry[0] == name]


# -- open_document


def test_a_closed_part_is_opened_silently_then_activated_and_becomes_the_build_document(com):
    com.opened(W + "Other.SLDPRT")
    part = com.saved(W + "Gear_m1.5_N68.SLDPRT")
    session = _session(com)
    info = session.open_document(W + "Gear_m1.5_N68.SLDPRT")
    assert info == swcom.DocInfo("Gear_m1.5_N68.SLDPRT", W + "Gear_m1.5_N68.SLDPRT", 1)
    assert _calls(com, "OpenDoc6") == [("OpenDoc6", W + "Gear_m1.5_N68.SLDPRT", 1, findings.OPEN_DOC_SILENT, "")]
    assert _calls(com, "ActivateDoc3") == [("ActivateDoc3", "Gear_m1.5_N68.SLDPRT")]
    assert session._doc() is part


def test_a_part_already_open_behind_another_is_still_brought_forward(com):
    part = com.opened(W + "Gear_m1.5_N68.SLDPRT")
    com.opened(W + "Other.SLDPRT")
    session = _session(com)
    session.open_document(W + "gear_m1.5_n68.sldprt")
    assert com.active is part and _calls(com, "ActivateDoc3") == [("ActivateDoc3", "Gear_m1.5_N68.SLDPRT")]


@pytest.mark.parametrize("route", ["OpenDoc6", "OpenDoc7", "OpenDoc"])
def test_an_assembly_opens_by_its_own_route(com, monkeypatch, route):
    monkeypatch.setattr(findings, "OPEN_ASSEMBLY_ROUTE", route, raising=False)
    com.saved(W + "R.SLDASM", doc_type=2)
    info = _session(com).open_document(W + "R.SLDASM")
    assert info.is_assembly
    assert [entry[0] for entry in com.log if entry[0] != "ActivateDoc3"] == (
        ["GetOpenDocSpec", "OpenDoc7"] if route == "OpenDoc7" else [route])
    if route == "OpenDoc7":
        assert _calls(com, "OpenDoc7") == [("OpenDoc7", W + "R.SLDASM", True)]
    else:
        assert com.log[0][2] == swcom.DOC_ASSEMBLY


def test_a_same_named_document_from_another_folder_is_refused_before_anything_is_asked(com):
    com.opened(r"C:\Other\Gear_m1.5_N68.SLDPRT")
    com.saved(W + "Gear_m1.5_N68.SLDPRT")
    with pytest.raises(SolidWorksError) as raised:
        _session(com).open_document(W + "Gear_m1.5_N68.SLDPRT")
    assert str(raised.value) == (r"C:\Other\Gear_m1.5_N68.SLDPRT is open in SolidWorks, and it has the same file "
                                 r"name as C:\W\Gear_m1.5_N68.SLDPRT; SolidWorks keeps one document per file name, "
                                 "so close Gear_m1.5_N68.SLDPRT in SolidWorks and try again.")
    assert com.log == []


@pytest.mark.parametrize("error,sentence", [
    (65536, r"SolidWorks would not open C:\W\Gear.SLDPRT: a document of the same file name is open from another "
            "folder (error 65536); close it in SolidWorks and try again."),
    (2, r"SolidWorks would not open C:\W\Gear.SLDPRT (error 2)."),
])
def test_an_open_that_fails_says_what_solidworks_answered(com, error, sentence):
    com.errors[W + "Gear.SLDPRT"] = error
    with pytest.raises(SolidWorksError) as raised:
        _session(com).open_document(W + "Gear.SLDPRT")
    assert str(raised.value) == sentence
    assert _calls(com, "ActivateDoc3") == []


@pytest.mark.parametrize("name,value,sentence", [
    ("OPEN_DOC_ROUTE", None, "Opening Gear.SLDPRT by its path has not been settled on SolidWorks yet "
                             "(findings.OPEN_DOC_ROUTE is None); run probe tier 7 first."),
    ("OPEN_DOC_ROUTE", "OpenDoc9", "Opening Gear.SLDPRT by its path has not been settled on SolidWorks yet "
                                   "(findings.OPEN_DOC_ROUTE is 'OpenDoc9'); run probe tier 7 first."),
    ("OPEN_DOC_SILENT", None, "Opening Gear.SLDPRT by its path has not been settled on SolidWorks yet "
                              "(findings.OPEN_DOC_ROUTE is 'OpenDoc6'); run probe tier 7 first."),
    ("UPDATE_OPEN_ROUTE", None, "Opening Gear.SLDPRT by its path has not been settled on SolidWorks yet "
                                "(findings.UPDATE_OPEN_ROUTE is None); run probe tier 7 first."),
])
def test_an_unsettled_open_route_is_refused_not_guessed(com, monkeypatch, name, value, sentence):
    monkeypatch.setattr(findings, name, value, raising=False)
    com.saved(W + "Gear.SLDPRT")
    with pytest.raises(SolidWorksError) as raised:
        _session(com).open_document(W + "Gear.SLDPRT")
    assert str(raised.value) == sentence and com.log == []


def test_with_the_ask_route_an_open_document_is_activated_and_a_closed_one_is_asked_for(com, monkeypatch):
    monkeypatch.setattr(findings, "UPDATE_OPEN_ROUTE", "ask", raising=False)
    part = com.opened(W + "Gear.SLDPRT", active=False)
    com.opened(W + "Other.SLDPRT")
    com.saved(W + "Closed.SLDPRT")
    session = _session(com)
    session.open_document(W + "Gear.SLDPRT")
    assert com.active is part and _calls(com, "OpenDoc6") == []
    with pytest.raises(SolidWorksError) as raised:
        session.open_document(W + "Closed.SLDPRT")
    assert str(raised.value) == (r"Open C:\W\Closed.SLDPRT in SolidWorks, then try again: this SolidWorks cannot be "
                                 "asked to open a document by its path (findings.UPDATE_OPEN_ROUTE).")


def test_documents_walks_to_the_end_of_solidworks_list_however_long(com):
    """Third W4 review item 1 (w4x_documents_cap): the walk stopped at 200, and one large assembly loads more; a
    document holding Update's unsaved changes then missed the list and passed as loaded from its file."""
    for index in range(260):
        com.opened(W + f"Doc{index}.SLDPRT", active=False)
    listed = _session(com).documents()
    assert len(listed) == 260 and listed[-1].path == W + "Doc259.SLDPRT"
    # open_document's own same-name check walks the same way: a clash past the 200th document is still refused.
    com.saved(W + "Sub\\Doc250.SLDPRT")
    with pytest.raises(SolidWorksError, match="same file name"):
        _session(com).open_document(W + "Sub\\Doc250.SLDPRT")


def test_a_list_of_documents_that_never_ends_is_refused_with_a_sentence(com, monkeypatch):
    monkeypatch.setattr(swcom, "DOCUMENT_WALK_LIMIT", 5)
    for index in range(5):
        com.opened(W + f"Doc{index}.SLDPRT", active=False)
    assert len(_session(com).documents()) == 5                      # the end reached at the limit: all listed
    com.opened(W + "Doc5.SLDPRT", active=False)
    with pytest.raises(swcom.DocumentsUnknown) as raised:
        _session(com).documents()
    assert str(raised.value) == ("SolidWorks listed 5 open documents without coming to the end of its list, so which "
                                 "documents it holds open cannot be known here, and nothing that depends on it is "
                                 "started; restart SolidWorks and try again.")


def test_unsaved_changes_are_read_from_the_save_flag_of_the_document_just_opened(com):
    part = com.saved(W + "Gear.SLDPRT")
    other = com.opened(W + "Other.SLDPRT")
    other.GetSaveFlag = True                                         # what is on screen is not what is asked about
    part.GetSaveFlag = False
    session = _session(com)
    session.open_document(W + "Gear.SLDPRT")
    assert session.has_unsaved_changes() is False
    part.GetSaveFlag = True
    assert session.has_unsaved_changes() is True


def test_a_document_that_does_not_come_forward_is_refused(com):
    com.opened(W + "Other.SLDPRT")
    com.saved(W + "Gear.SLDPRT")
    com.activates = False
    com.disk[(W + "Gear.SLDPRT").lower()].app = com
    original = com._open

    def open_behind(path):                         # opened, but left behind the other document
        doc, error, warning = original(path)
        com.active = com.docs[0]
        return doc, error, warning

    com._open = open_behind
    with pytest.raises(SolidWorksError) as raised:
        _session(com).open_document(W + "Gear.SLDPRT")
    assert str(raised.value) == ("SolidWorks opened Gear.SLDPRT but left Other.SLDPRT active after ActivateDoc3, so "
                                 "it is not changed.")


@pytest.mark.parametrize("path,sentence", [
    (W + "Notes.txt", r"C:\W\Notes.txt is neither a SolidWorks part nor an assembly, so it is not opened."),
    (W + "Odd.SLDASM", r"C:\W\Odd.SLDASM opened as a document of type 1, not as an assembly."),
])
def test_what_is_not_the_document_asked_for_is_refused(com, path, sentence):
    com.saved(W + "Odd.SLDASM", doc_type=1)
    with pytest.raises(SolidWorksError) as raised:
        _session(com).open_document(path)
    assert str(raised.value) == sentence


# -- find_component, component_frame


def _assembly(com, *components):
    asm = com.opened(W + "R.SLDASM", doc_type=2)
    asm.components.extend(components)
    session = _session(com)
    session.begin_build()
    session.open_document(W + "R.SLDASM")
    return session, asm


@pytest.mark.parametrize("route", swcom.COMPONENT_FIND_ROUTES)
def test_a_component_is_found_by_its_recorded_name_by_every_route(com, monkeypatch, route):
    monkeypatch.setattr(findings, "COMPONENT_FIND_ROUTE", route, raising=False)
    model = com.opened(W + "Gear_m1.5_N68.SLDPRT", active=False)
    wanted = Component("Gear_m1.5_N68-1", model=model)
    session, _ = _assembly(com, Component("Gear_m1.5_N17-1"), wanted)
    assert session.find_component("placed2", "Gear_m1.5_N68-1") == "Gear_m1.5_N68-1"
    assert session._handles["placed2"] == {"component": wanted, "path": W + "Gear_m1.5_N68.SLDPRT"}


@pytest.mark.parametrize("route", swcom.COMPONENT_FIND_ROUTES)
def test_a_component_renamed_or_deleted_is_named_in_the_sentence(com, monkeypatch, route):
    monkeypatch.setattr(findings, "COMPONENT_FIND_ROUTE", route, raising=False)
    session, _ = _assembly(com, Component("Gear_m1.5_N17-1"))
    with pytest.raises(SolidWorksError) as raised:
        session.find_component("placed2", "Gear_m1.5_N68-1")
    assert str(raised.value) == "Gear_m1.5_N68-1 is not in R.SLDASM any more: it was renamed or deleted in SolidWorks."


def test_an_unsettled_find_route_is_refused(com, monkeypatch):
    monkeypatch.setattr(findings, "COMPONENT_FIND_ROUTE", None, raising=False)
    session, _ = _assembly(com, Component("G-1"))
    with pytest.raises(SolidWorksError, match=r"\(findings.COMPONENT_FIND_ROUTE is None\); run probe tier 7 first\."):
        session.find_component("placed1", "G-1")


def test_a_route_that_answers_with_another_component_is_refused(com, monkeypatch):
    monkeypatch.setattr(findings, "COMPONENT_FIND_ROUTE", "GetComponentByName", raising=False)
    session, asm = _assembly(com)
    asm.GetComponentByName = lambda name: Component("Other-1")
    with pytest.raises(SolidWorksError) as raised:
        session.find_component("placed1", "G-1")
    assert str(raised.value) == ("Asked for G-1 in R.SLDASM, SolidWorks gave Other-1, so which component is meant "
                                 "cannot be told.")


@pytest.mark.parametrize("state,resolved,sentence", [
    (0, True, "G-1 is suppressed in R.SLDASM, so it cannot be placed; unsuppress it in SolidWorks and try again."),
    (1, True, "G-1 is loaded lightweight in R.SLDASM, and resolving a component is not settled here; set it to "
              "Resolved in SolidWorks and try again."),
    (4, True, "G-1 is loaded lightweight in R.SLDASM, and resolving a component is not settled here; set it to "
              "Resolved in SolidWorks and try again."),
    ("unread", None, "G-1 is loaded lightweight in R.SLDASM, and resolving a component is not settled here; set it "
                     "to Resolved in SolidWorks and try again."),
    ("unread", True, ""),
    (3, False, ""),
])
def test_a_component_that_is_not_resolved_is_refused_with_what_to_do(com, monkeypatch, state, resolved, sentence):
    monkeypatch.setattr(findings, "COMPONENTS_RESOLVED_AFTER_REOPEN", resolved, raising=False)
    component = Component("G-1", state=None if state == "unread" else state)
    session, _ = _assembly(com, component)
    if not sentence:
        assert session.find_component("placed1", "G-1") == "G-1"
        return
    with pytest.raises(SolidWorksError) as raised:
        session.find_component("placed1", "G-1")
    assert str(raised.value) == sentence


def _rows_to_columns(rows):
    return [rows[i * 3 + j] for j in range(3) for i in range(3)]


ROWS = (0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)    # a quarter turn about Z, by rows


@pytest.mark.parametrize("order", ["columns", "rows"])
def test_a_component_frame_is_read_as_place_component_writes_it(com, monkeypatch, order):
    monkeypatch.setattr(findings, "TRANSFORM_ARRAY_ORDER", order, raising=False)
    data = (_rows_to_columns(ROWS) if order == "columns" else list(ROWS)) + [0.06375, -0.002, 0.005, 1.0, 0, 0, 0]
    session, _ = _assembly(com, Component("G-1", data=data))
    session.find_component("placed1", "G-1")
    rotation, at = session.component_frame("placed1")
    assert rotation == ROWS and at == pytest.approx((63.75, -2.0, 5.0))


def test_an_unsettled_frame_layout_is_refused(com, monkeypatch):
    monkeypatch.setattr(findings, "TRANSFORM_ARRAY_ORDER", None, raising=False)
    session, _ = _assembly(com, Component("G-1"))
    session.find_component("placed1", "G-1")
    with pytest.raises(SolidWorksError, match=r"TRANSFORM_ARRAY_ORDER is None"):
        session.component_frame("placed1")


# -- interferences


def _clash_world(com, items, fail=False):
    session, asm = _assembly(com)
    asm.manager = Manager(items, fail)
    return session, asm.manager


def test_each_interference_names_its_components_and_gives_its_volume_and_done_is_called(com):
    a, b = Component("Gear_m1.5_N17-1"), Component("Gear_m1.5_N68-1")
    session, manager = _clash_world(com, [Interference((a, b), 12.5e-9)])
    assert session.interferences() == [(("Gear_m1.5_N17-1", "Gear_m1.5_N68-1"), pytest.approx(12.5))]
    assert manager.done == 1 and manager.options == dict(findings.INTERFERENCE_OPTIONS)


@pytest.mark.parametrize("route,named", [("Components (property)", True), ("GetComponents()", True), (None, False),
                                         ("something else", False)])
def test_the_names_follow_the_route_and_are_empty_where_it_cannot_name_them(com, monkeypatch, route, named):
    monkeypatch.setattr(findings, "INTERFERENCE_NAMES_ROUTE", route, raising=False)
    session, _ = _clash_world(com, [Interference((Component("A-1"), Component("B-1")), 1e-9)])
    assert session.interferences()[0][0] == (("A-1", "B-1") if named else ())


def test_components_that_will_not_name_themselves_leave_the_volume(com):
    item = Interference((object(),), 2e-9)
    session, _ = _clash_world(com, [item])
    assert session.interferences() == [((), pytest.approx(2.0))]


def test_done_is_called_even_when_the_list_cannot_be_read(com):
    session, manager = _clash_world(com, [], fail=True)
    with pytest.raises(RuntimeError):
        session.interferences()
    assert manager.done == 1


# -- add_component reads back the file it took


def test_a_component_inserted_from_the_file_asked_for_is_kept(com):
    part = com.opened(W + "Gear_m1.5_N68.SLDPRT", active=False)
    session, asm = _assembly(com)
    assert session.add_component("gear2", W + "Gear_m1.5_N68.SLDPRT", (63.75, 0.0, 0.0)) == "Gear_m1.5_N68-1"
    assert asm.components[0].GetModelDoc2 is part and "gear2" in session._handles


def test_a_component_that_took_another_folders_file_is_refused(com):
    com.inserts[W + "Gear_m1.5_N68.SLDPRT"] = Doc(com, r"C:\Other\Gear_m1.5_N68.SLDPRT")
    session, _ = _assembly(com)
    with pytest.raises(SolidWorksError) as raised:
        session.add_component("gear2", W + "Gear_m1.5_N68.SLDPRT", (0.0, 0.0, 0.0))
    assert str(raised.value) == (r"AddComponent5 put Gear_m1.5_N68-1 into R.SLDASM from C:\Other\Gear_m1.5_N68.SLDPRT,"
                                 r" not from C:\W\Gear_m1.5_N68.SLDPRT; a document of the same file name may be open "
                                 "from another folder.")


def test_a_lightweight_component_is_checked_by_its_own_path(com):
    session, asm = _assembly(com)
    com.inserts[W + "G.SLDPRT"] = None
    original = asm.AddComponent5

    def lightweight(path, *args):
        component = original(path, *args)
        component.GetPathName = path
        return component

    asm.AddComponent5 = lightweight
    assert session.add_component("gear1", W + "G.SLDPRT", (0.0, 0.0, 0.0)) == "G-1"


def test_a_component_whose_file_cannot_be_read_back_is_refused(com):
    com.inserts[W + "G.SLDPRT"] = None
    session, _ = _assembly(com)
    with pytest.raises(SolidWorksError, match="from a file whose path could not be read, not from"):
        session.add_component("gear1", W + "G.SLDPRT", (0.0, 0.0, 0.0))


# -- insert_axis through planes this build made


def _layout(com):
    doc = com.opened(W + "Part1.SLDPRT")
    session = _session(com)
    session.begin_build()
    x1, y1 = Feature(doc, "S2 X Plane"), Feature(doc, "S2 Y Plane")
    doc.features += [x1, y1]
    session._handles.update({"x1": "S2 X Plane", "y1": "S2 Y Plane"})
    session._plane_objects.update({"x1": x1, "y1": y1})
    return session, doc


@pytest.mark.parametrize("route,how", [("Select2 on the feature found by name", "Select2"),
                                       ("SelectByID2 by name", "SelectByID2"),
                                       ("Select2 on what InsertRefPlane returned", "Select2")])
def test_an_axis_goes_through_planes_made_in_this_build_selected_by_the_settled_route(com, monkeypatch, route, how):
    monkeypatch.setattr(findings, "AXIS_PLANE_SELECT_ROUTE", route, raising=False)
    session, doc = _layout(com)
    assert session.insert_axis("axis2", "S2 Axis", ("y1", "x1")) == "S2 Axis"
    assert _calls(com, "InsertAxis2") == [("InsertAxis2", ("S2 Y Plane", "S2 X Plane"))]
    assert [entry[1] for entry in com.log if entry[0] == how] == ["S2 Y Plane", "S2 X Plane"]
    assert doc.features[-1].Name == "S2 Axis" and session._handles["axis2"] == "S2 Axis"


def test_an_axis_through_a_base_plane_and_a_made_one_selects_them_in_the_order_given(com):
    session, _ = _layout(com)
    session.insert_axis("axis2", "S2 Axis", (2, "x1"))
    assert _calls(com, "InsertAxis2") == [("InsertAxis2", ("Top Plane", "S2 X Plane"))]


@pytest.mark.parametrize("name,planes,sentence", [
    ("AXIS_PLANE_SELECT_ROUTE", ("y1", "x1"),
     "The axis S2 Axis goes through a plane made in this build, and how to select such a plane has not been settled "
     "on SolidWorks yet (findings.AXIS_PLANE_SELECT_ROUTE is None); run probe tier 7 first."),
    ("AXIS_THROUGH_BASE_PLANE", (2, "x1"),
     "The axis S2 Axis goes through a base plane and a plane made in this build, which has not been settled on "
     "SolidWorks yet (findings.AXIS_THROUGH_BASE_PLANE); run probe tier 7 first."),
])
def test_an_axis_through_made_planes_without_its_finding_is_refused(com, monkeypatch, name, planes, sentence):
    monkeypatch.setattr(findings, name, None, raising=False)
    session, _ = _layout(com)
    with pytest.raises(SolidWorksError) as raised:
        session.insert_axis("axis2", "S2 Axis", planes)
    assert str(raised.value) == sentence and com.log == []


def test_an_axis_through_a_plane_not_made_is_refused(com):
    session, _ = _layout(com)
    with pytest.raises(SolidWorksError, match=r"^The plane 'x9' has not been made in this build\.$"):
        session.insert_axis("axis2", "S2 Axis", (2, "x9"))


def test_the_strips_axis_through_planes_2_and_3_is_unchanged(com, monkeypatch):
    monkeypatch.setattr(findings, "AXIS_PLANE_SELECT_ROUTE", None, raising=False)
    session, _ = _layout(com)
    session.insert_axis("axis", "Gear Axis", (2, 3))
    assert _calls(com, "InsertAxis2") == [("InsertAxis2", ("Top Plane", "Right Plane"))]


def test_a_refused_axis_names_the_planes_it_was_given(com, monkeypatch):
    session, doc = _layout(com)
    doc.InsertAxis2 = lambda auto: False
    with pytest.raises(SolidWorksError) as raised:
        session.insert_axis("axis2", "S2 Axis", (2, "x1"))
    assert str(raised.value) == "InsertAxis2 would not make S2 Axis from plane 2 and S2 X Plane."


def test_a_missing_template_is_named_as_typed(com, monkeypatch):
    sw = swcom.Session(com, (34, 0, 0), 1)
    with pytest.raises(swcom.SolidWorksError) as raised:
        sw.new_assembly("C:\\T\\No such template.asmdot")
    assert str(raised.value) == "There is no assembly template at C:\\T\\No such template.asmdot."
    monkeypatch.setattr(swcom.Session, "default_template", lambda self, kind="part": "")
    with pytest.raises(swcom.SolidWorksError) as raised:
        sw.new_part("")
    assert str(raised.value).startswith("SolidWorks names no default part template")
    monkeypatch.setattr(swcom.Session, "default_template", lambda self, kind="part": "C:\\SW\\Part.prtdot")
    with pytest.raises(swcom.SolidWorksError) as raised:
        sw.new_part("")
    assert str(raised.value) == "SolidWorks' default part template, C:\\SW\\Part.prtdot, is not there."


# -- COM errors as sentences (W4 review B1) ------------------------------------------------------------------


class com_error(Exception):  # noqa: N801 - pywin32's name, so probe.comerr reads it as it reads the real one
    pass


class Raising:
    def __init__(self, error):
        self.error = error

    def SaveAs3(self, *args):  # noqa: N802 - a COM member's name
        raise self.error


RPC_FAILED = com_error(-2147023170, "The remote procedure call failed.", None, None)


@pytest.fixture
def com_errors(monkeypatch):
    monkeypatch.setattr(swcom, "_COM_ERRORS", (com_error,))
    swcom.CONNECTION.lost = False
    yield
    swcom.CONNECTION.lost = False


def test_a_com_error_comes_out_of_call_as_a_solidworks_error_with_a_sentence(com_errors):
    from gear_generator.probe import comerr
    with pytest.raises(swcom.ComError) as raised:
        swcom.call(Raising(RPC_FAILED), "SaveAs3", "C:\\P\\Gear.SLDPRT")
    error = raised.value
    assert isinstance(error, SolidWorksError)
    assert str(error) == ("SolidWorks did not complete SaveAs3: The remote procedure call failed "
                          "(RPC_S_CALL_FAILED). SolidWorks may have closed or crashed; the next press connects to it "
                          "again.")
    assert error.lost and error.hresult == 0x800706BE and error.__cause__ is RPC_FAILED
    # a probe reads the same evidence from it as from the bare com_error
    assert comerr.describe_error(error)["hresult"] == "0x800706BE" and error.args == RPC_FAILED.args
    assert swcom.CONNECTION.lost


def test_a_rejected_call_and_a_failed_member_say_so(com_errors):
    rejected = com_error(-2147418111, "Call was rejected by callee.", None, None)
    with pytest.raises(swcom.ComError) as raised:
        swcom.call(Raising(rejected), "SaveAs3", 0)
    assert str(raised.value) == ("SolidWorks did not complete SaveAs3: Call was rejected by callee "
                                 "(RPC_E_CALL_REJECTED). SolidWorks was busy, perhaps with a dialog open; close it in "
                                 "SolidWorks and try again.")
    failed = com_error(-2147352567, "Exception occurred.", (0, "SolidWorks", "Bad argument", None, 0, -2147024809), 3)
    with pytest.raises(swcom.ComError) as raised:
        swcom.call(Raising(failed), "SaveAs3", 0)
    assert str(raised.value) == ("SolidWorks did not complete SaveAs3: Bad argument "
                                 "(DISP_E_EXCEPTION).")
    assert not raised.value.lost and not swcom.CONNECTION.lost


class _Ole:
    """A dispatch's ``_oleobj_`` whose Invoke raises what it is given."""

    def __init__(self, error):
        self.error = error

    def GetIDsOfNames(self, name):  # noqa: N802 - pywin32's name
        return 7

    def Invoke(self, *args):  # noqa: N802 - pywin32's name
        raise self.error


class _Raw:
    def __init__(self, error):
        self._oleobj_ = _Ole(error)


class _PyCom:
    DISPATCH_PROPERTYPUT, DISPATCH_METHOD, VT_ARRAY, VT_R8 = 4, 1, 0x2000, 5


def test_an_indexed_put_goes_through_the_same_wrapper_as_call(com_errors, monkeypatch):
    """W4 review N4.1: every global set is an indexed put through Invoke, which reached COM directly — a failure
    read "it stopped on an unexpected com_error" and never marked the session lost."""
    monkeypatch.setattr(swcom, "pythoncom", _PyCom)
    with pytest.raises(swcom.ComError) as raised:
        swcom._put_indexed(_Raw(RPC_FAILED), "Equation", 3, '"No. of Teeth"= 69')
    assert str(raised.value) == ("SolidWorks did not complete setting Equation(3): The remote procedure call failed "
                                 "(RPC_S_CALL_FAILED). SolidWorks may have closed or crashed; the next press connects "
                                 "to it again.")
    assert swcom.CONNECTION.lost


def test_placing_a_component_goes_through_the_same_wrapper_as_call(com_errors, monkeypatch):
    """W4 review N4.1: place_component's CreateTransform Invoke reached COM directly too."""
    monkeypatch.setattr(swcom, "pythoncom", _PyCom)
    monkeypatch.setattr(swcom, "VARIANT", lambda kind, value: value)

    class Assembly:
        GetType = swcom.DOC_ASSEMBLY

    class App:
        GetMathUtility = _Raw(RPC_FAILED)          # late binding reads a zero-argument member as a property
        ActiveDoc = Assembly()                     # place_component settles its rebuild before the put

    session = swcom.Session(App(), (34, 0, 0), 1)
    session._handles = {"gear1": {"component": object()}}
    with pytest.raises(swcom.ComError) as raised:
        session.place_component("gear1", (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0), (0.0, 0.0, 0.0), mated=False)
    assert str(raised.value).startswith("SolidWorks did not complete CreateTransform: The remote procedure call failed")
    assert swcom.CONNECTION.lost


def test_a_property_put_goes_through_the_same_wrapper_as_call(com_errors):
    rejected = com_error(-2147418111, "Call was rejected by callee.", None, None)

    class Feature:
        def __setattr__(self, name, value):
            raise rejected

    with pytest.raises(swcom.ComError) as raised:
        swcom._put(Feature(), "Name", "Gear")
    assert str(raised.value).startswith("SolidWorks did not complete setting Name: Call was rejected by callee")
    assert not swcom.CONNECTION.lost


def test_anything_else_passes_through_call_untouched(com_errors):
    with pytest.raises(ZeroDivisionError):
        swcom.call(Raising(ZeroDivisionError("no")), "SaveAs3", 0)


def test_a_job_that_kept_a_lost_connection_as_a_failure_still_drops_the_session():
    """build_gearbox turns a lost connection into a failure on its result and returns: the worker drops the session
    anyway, so the next press attaches afresh instead of calling a dead SolidWorks."""
    made = []

    def connect_fn():
        made.append(object())
        return made[-1]

    def kept(_session):
        swcom.CONNECTION.lost = True          # what call() sets when it wraps an RPC failure
        return "a partial result"

    worker = swcom.Worker(connect_fn=connect_fn)
    try:
        assert worker.submit(kept).wait(timeout=5) == ("a partial result", None)
        worker.submit(lambda s: None).wait(timeout=5)
        assert len(made) == 2
        worker.submit(lambda s: None).wait(timeout=5)
        assert len(made) == 2
    finally:
        worker.shutdown()


# -- the one rebuild: a part as always, an assembly top-only (probe assembly_rebuild_scope)


def _gearbox_world(com):
    """An assembly open and active, its layout and two gears loaded as its components, nothing modified."""
    assembly = com.opened(W + "R.SLDASM", doc_type=2)
    parts = [com.opened(W + name, active=False) for name in ("R_Layout.SLDPRT", "Gear_m1.5_N17.SLDPRT",
                                                              "Gear_m1.5_N68.SLDPRT")]
    for part in parts:
        assembly.components.append(Component(part.GetTitle.rsplit(".", 1)[0] + "-1", model=part,
                                             path=part.GetPathName))
    com.active = assembly
    return assembly, parts


def _marked(com):
    return [d.GetTitle for d in com.docs if d.GetSaveFlag]


def test_an_assembly_rebuilds_top_only_and_marks_only_itself(com):
    """W4 rerun on 2026: ForceRebuild3(False) marked every part of the assembly modified, untouched ones too."""
    assembly, _parts = _gearbox_world(com)
    assert _session(com).rebuild(mated=False) is True
    assert _calls(com, "ForceRebuild3") == [("ForceRebuild3", "R.SLDASM", True)]
    assert _marked(com) == ["R.SLDASM"]


def test_a_part_rebuilds_as_it_always_did(com):
    part = com.opened(W + "Gear_m1.5_N68.SLDPRT")
    assert _session(com).rebuild() is True
    assert _calls(com, "ForceRebuild3") == [("ForceRebuild3", "Gear_m1.5_N68.SLDPRT", False)]
    assert part.GetSaveFlag


def test_a_part_rebuilds_as_always_even_while_the_assembly_route_is_unsettled(com, monkeypatch):
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_ROUTE", None)
    com.opened(W + "Gear_m1.5_N68.SLDPRT")
    assert _session(com).rebuild() is True
    assert swcom.rebuild_call(swcom.DOC_PART) == ("ForceRebuild3", (False,))


def test_a_component_in_error_still_fails_the_top_only_rebuild(com):
    _assembly, parts = _gearbox_world(com)
    parts[2].fails = True
    assert _session(com).rebuild(mated=False) is False
    assert _marked(com) == ["R.SLDASM"]


def test_the_edit_rebuild_route_is_taken_when_the_finding_names_it(com, monkeypatch):
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_ROUTE", "EditRebuild3")
    _gearbox_world(com)
    assert _session(com).rebuild(mated=False) is True
    assert _calls(com, "EditRebuild3") == [("EditRebuild3", "R.SLDASM")] and _calls(com, "ForceRebuild3") == []
    assert _marked(com) == ["R.SLDASM"]


class _Utility:
    """IMathUtility whose CreateTransform, invoked as a method, makes the transform from the 16 numbers."""

    class _Ole:
        def __init__(self, log):
            self.log = log

        def GetIDsOfNames(self, name):  # noqa: N802 - pywin32's name
            return 9

        def Invoke(self, dispid, lcid, flags, result, data):  # noqa: N802 - pywin32's name
            self.log.append(("CreateTransform",))
            return Transform(data)

    def __init__(self, log):
        self._oleobj_ = self._Ole(log)


class _Placeable(Component):
    """A component whose Transform2 put is logged."""

    def __setattr__(self, name, value):
        if name == "Transform2" and hasattr(self, "log"):
            self.log.append(("Transform2 put", self.Name2))
        object.__setattr__(self, name, value)


def _placing(com, monkeypatch):
    monkeypatch.setattr(swcom, "pythoncom", _PyCom)
    monkeypatch.setattr(swcom, "VARIANT", lambda kind, value: value)
    com.GetMathUtility = _Utility(com.log)
    assembly, parts = _gearbox_world(com)
    gear = _Placeable("Gear_m1.5_N68-1", model=parts[2], path=parts[2].GetPathName)
    gear.log = com.log
    assembly.components[2] = gear
    session = _session(com)
    session._handles = {"gear2": {"component": gear}}
    return session, gear


def test_a_put_is_rebuilt_top_only_and_still_read_back(com, monkeypatch):
    session, gear = _placing(com, monkeypatch)
    turned = (0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    session.place_component("gear2", turned, (64.5, 0.0, 0.0), mated=False)
    assert [e for e in com.log if e[0] in ("CreateTransform", "Transform2 put", "ForceRebuild3")] == [
        ("CreateTransform",), ("Transform2 put", "Gear_m1.5_N68-1"), ("ForceRebuild3", "R.SLDASM", True)]
    assert _marked(com) == ["R.SLDASM"]                         # the gear's own part is not marked
    assert gear.Transform2.ArrayData[9:12] == pytest.approx((0.0645, 0.0, 0.0))


@pytest.mark.parametrize("route, top_only, sentence", [
    (None, True, "How to rebuild an assembly has not been settled on SolidWorks yet "
                 "(findings.ASSEMBLY_REBUILD_ROUTE is None), so no assembly is changed; run probe tier 7 first."),
    ("none", True, "How to rebuild an assembly has not been settled on SolidWorks yet "
                   "(findings.ASSEMBLY_REBUILD_ROUTE is 'none'), so no assembly is changed; run probe tier 7 first."),
    ("ForceRebuild3(True)", None, "findings.ASSEMBLY_REBUILD_ROUTE is 'ForceRebuild3(True)' but "
                                  "findings.ASSEMBLY_REBUILD_TOP_ONLY is None, and the two disagree, so no assembly is "
                                  "changed; run probe tier 7 again."),
    ("ForceRebuild3(True)", False, "findings.ASSEMBLY_REBUILD_ROUTE is 'ForceRebuild3(True)' but "
                                   "findings.ASSEMBLY_REBUILD_TOP_ONLY is False, and the two disagree, so no assembly "
                                   "is changed; run probe tier 7 again."),
])
def test_an_unsettled_assembly_rebuild_is_refused_before_anything_is_changed(com, monkeypatch, route, top_only,
                                                                              sentence):
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_ROUTE", route)
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_TOP_ONLY", top_only)
    session, gear = _placing(com, monkeypatch)
    before = gear.Transform2.ArrayData
    with pytest.raises(swcom.SolidWorksError) as raised:
        session.rebuild(mated=False)
    assert str(raised.value) == sentence
    with pytest.raises(swcom.SolidWorksError) as raised:
        session.place_component("gear2", (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0), (64.5, 0.0, 0.0), mated=False)
    assert str(raised.value) == sentence
    assert gear.Transform2.ArrayData == before                 # refused before the put, not after it
    assert not any(e[0] in ("CreateTransform", "Transform2 put", "ForceRebuild3", "EditRebuild3") for e in com.log)
    assert _marked(com) == []


# -- a MATED assembly keeps the full rebuild (the review of 9c39fb8): the caller says which kind it is


@pytest.mark.parametrize("workbook_route", ["ForceRebuild3(True)", None])
def test_a_mated_assembly_rebuilds_in_full_as_it_always_did(com, monkeypatch, workbook_route):
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_ROUTE", workbook_route)
    monkeypatch.setattr(findings, "MATED_ASSEMBLY_REBUILD_ROUTE", None, raising=False)     # until the W5 batch sets it
    _gearbox_world(com)
    assert _session(com).rebuild(mated=True) is True
    assert _calls(com, "ForceRebuild3") == [("ForceRebuild3", "R.SLDASM", False)]
    assert swcom.rebuild_call(swcom.DOC_ASSEMBLY, mated=True) == ("ForceRebuild3", (False,))


def test_a_put_in_a_mated_assembly_is_rebuilt_in_full(com, monkeypatch):
    session, _gear = _placing(com, monkeypatch)
    monkeypatch.setattr(findings, "ASSEMBLY_REBUILD_ROUTE", None)        # a pair never leans on the workbook finding
    monkeypatch.setattr(findings, "MATED_ASSEMBLY_REBUILD_ROUTE", None, raising=False)
    session.place_component("gear2", (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0), (64.5, 0.0, 0.0), mated=True)
    assert _calls(com, "ForceRebuild3") == [("ForceRebuild3", "R.SLDASM", False)]


def test_a_mated_route_once_set_is_taken_and_an_unknown_one_refused(com, monkeypatch):
    monkeypatch.setattr(findings, "MATED_ASSEMBLY_REBUILD_ROUTE", "EditRebuild3", raising=False)
    assert swcom.rebuild_call(swcom.DOC_ASSEMBLY, mated=True) == ("EditRebuild3", ())
    monkeypatch.setattr(findings, "MATED_ASSEMBLY_REBUILD_ROUTE", "guess", raising=False)
    _gearbox_world(com)
    with pytest.raises(swcom.SolidWorksError) as raised:
        _session(com).rebuild(mated=True)
    assert str(raised.value) == ("findings.MATED_ASSEMBLY_REBUILD_ROUTE is 'guess', which is not a rebuild this code "
                                 "knows, so no mated assembly is changed; run probe tier 8 again.")
    assert _calls(com, "ForceRebuild3") == [] and _marked(com) == []


def test_an_assembly_whose_kind_is_not_said_is_refused_before_anything_is_changed(com, monkeypatch):
    """The review of 31d1ac9: with mated defaulting to False, a caller that forgot it put a mated assembly on the
    unprobed top-only route. Now an assembly's kind must be said; a part's need not."""
    session, gear = _placing(com, monkeypatch)
    before = gear.Transform2.ArrayData
    sentence = ("This assembly was to be rebuilt without saying whether its components are mated or fixed, so which "
                "rebuild it takes cannot be chosen and nothing is changed; that is a fault in Gear Generator, not in "
                "SolidWorks.")
    for act in (lambda: session.rebuild(),
                lambda: session.place_component("gear2", (1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0), (64.5, 0.0, 0.0))):
        with pytest.raises(swcom.SolidWorksError) as raised:
            act()
        assert str(raised.value) == sentence
    assert gear.Transform2.ArrayData == before and _marked(com) == []
    assert not any(e[0] in ("CreateTransform", "Transform2 put", "ForceRebuild3", "EditRebuild3") for e in com.log)
    assert swcom.rebuild_call(swcom.DOC_PART) == ("ForceRebuild3", (False,))
