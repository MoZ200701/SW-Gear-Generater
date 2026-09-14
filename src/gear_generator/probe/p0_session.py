"""Tier 0: the session, the templates, and making and closing a document.

Everything later stands on these. They are also the cheapest place to find out
that the machine is not what the plan assumed — a template moved, a document
that will not close without asking.
"""

from __future__ import annotations

import os

from ..swcom import call
from . import scaffold as sc
from .harness import Px, probe


@probe("attach", tier=0, members=("ISldWorks.RevisionNumber", "ISldWorks.GetFirstDocument"))
def attach(px: Px) -> None:
    """The session answers, and says what it is."""
    app = sc.app(px)
    revision = str(call(app, "RevisionNumber"))
    px.fact("revision", revision)
    px.fact("version", px.session.label)
    px.check(px.session.revision[0] >= 34, f"revision {revision} is SolidWorks 2026 or newer")
    px.fact("open_at_start", sc.open_titles(px))


@probe("templates", needs=("attach",), tier=0,
       members=("ISldWorks.GetUserPreferenceStringValue", "ISldWorks.GetDocumentTemplate"))
def templates(px: Px) -> None:
    """Where the default part and assembly templates are, by two routes and a fallback."""
    app = sc.app(px)
    kinds = (
        (sc.SW_DOC_PART, sc.SW_DEFAULT_TEMPLATE_PART, "part_template", ".prtdot"),
        (sc.SW_DOC_ASSEMBLY, sc.SW_DEFAULT_TEMPLATE_ASSEMBLY, "assembly_template", ".asmdot"),
    )
    for doc_type, preference, key, extension in kinds:
        got_doc, from_doc = px.attempt(
            f"GetDocumentTemplate({doc_type}, '', 0, 0, 0)",
            lambda: call(app, "GetDocumentTemplate", doc_type, "", 0, 0.0, 0.0),
        )
        got_pref, from_pref = px.attempt(
            f"GetUserPreferenceStringValue({preference})",
            lambda: call(app, "GetUserPreferenceStringValue", preference),
        )
        routes = (
            ("GetDocumentTemplate", from_doc if got_doc else None),
            ("GetUserPreferenceStringValue", from_pref if got_pref else None),
            ("fallback", sc.FALLBACK_TEMPLATES[doc_type]),
        )
        chosen = None
        for route, path in routes:
            if isinstance(path, str) and path and os.path.isfile(path):
                chosen = (route, path)
                break
            if path:
                px.note(f"{route} gave {path!r}, which is not a file on this machine")
        px.require(chosen is not None, f"a {key.replace('_', ' ')} exists on disk")
        px.fact(f"{key}_route", chosen[0])
        px.fact(key, chosen[1])
        px.shared[key] = chosen[1]
        px.check(chosen[1].lower().endswith(extension), f"the {key.replace('_', ' ')} is a {extension} file")


@probe("new_document", needs=("templates",), tier=0,
       members=("ISldWorks.NewDocument", "IModelDoc2.GetTitle", "IModelDoc2.GetType", "ISldWorks.ActiveDoc",
                "IFeature.GetTypeName2"))
def new_document(px: Px) -> None:
    """NewDocument makes an active part with three reference planes."""
    with sc.scratch(px) as doc:
        title = str(call(doc, "GetTitle"))
        px.fact("new_part_title", title)
        px.check(int(call(doc, "GetType")) == sc.SW_DOC_PART, "NewDocument from the part template makes a part")
        active = call(sc.app(px), "ActiveDoc")
        px.check(active is not None and str(call(active, "GetTitle")) == title, "the new part is the active document")
        planes = sc.planes(doc)
        px.fact("plane_names_in_tree_order", [str(call(p, "Name")) for p in planes])
        px.check(len(planes) == 3, "the part has exactly three reference planes")
        px.fact("new_part_features", [(n, t) for n, t in sc.new_features(doc, [])])
        px.fact("new_part_path", str(call(doc, "GetPathName")))


@probe("close_document", needs=("new_document",), tier=0,
       members=("ISldWorks.CloseDoc", "IModelDoc2.GetSaveFlag", "ISketchManager.InsertSketch",
                "ISketchManager.CreatePoint"))
def close_document(px: Px) -> None:
    """CloseDoc closes a modified, never-saved part without asking."""
    doc = sc.new_document(px)
    title = str(call(doc, "GetTitle"))
    px.check(sc.select_plane(doc, 1), "the first reference plane selects by tree order")
    px.fact("select_routes_so_far", dict(sc.SELECT_ROUTES))
    manager = sc.sketch_manager(doc)
    px.attempt("InsertSketch(True) to open", lambda: call(manager, "InsertSketch", True))
    px.attempt("CreatePoint(0.01, 0.01, 0)", lambda: call(manager, "CreatePoint", 0.01, 0.01, 0.0))
    px.attempt("InsertSketch(True) to close", lambda: call(manager, "InsertSketch", True))
    got, dirty = px.attempt("GetSaveFlag", lambda: call(doc, "GetSaveFlag"))
    px.fact("modified_before_close", dirty if got else None)
    result = call(sc.app(px), "CloseDoc", title)
    px.fact("close_doc_returns", result if isinstance(result, (bool, int, type(None))) else repr(result))
    px.check(title not in sc.open_titles(px), "CloseDoc closed the modified part without a prompt")


@probe("activate_document", needs=("new_document",), tier=0, members=("ISldWorks.ActivateDoc3",))
def activate_document(px: Px) -> None:
    """ActivateDoc3 brings a document back to the front, with its out parameter."""
    with sc.scratch(px) as first:
        with sc.scratch(px) as second:
            first_title = str(call(first, "GetTitle"))
            px.check(str(call(call(sc.app(px), "ActiveDoc"), "GetTitle")) == str(call(second, "GetTitle")),
                     "the second new part is active")
            got, value = px.attempt(
                "ActivateDoc3(title, False, 0, out long)",
                lambda: call(sc.app(px), "ActivateDoc3", first_title, False, 0, sc.out_long()),
            )
            px.fact("activate_doc3_returns_shape", type(value).__name__ if got else None)
            active = call(sc.app(px), "ActiveDoc")
            px.check(active is not None and str(call(active, "GetTitle")) == first_title,
                     "ActivateDoc3 made the first part active again")
