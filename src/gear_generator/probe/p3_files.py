"""Tier 3: where a document lives, and saving it somewhere new.

The tool refuses to overwrite a file, so what SaveAs3 does to an existing one
is worth knowing rather than assuming: the API help says it overwrites.
"""

from __future__ import annotations

import os
from typing import Any

from ..swcom import call
from . import scaffold as sc
from .harness import Px, probe

# swSaveAsVersion_e and swSaveAsOptions_e, from swconst.tlb on SolidWorks 2026.
SAVE_AS_CURRENT_VERSION = 0
SAVE_AS_SILENT = 1


def _flag(result: Any) -> Any:
    """SaveAs3 with by-reference outs comes back as a tuple whose first item is the flag."""
    return result[0] if isinstance(result, tuple) and result else result


@probe("save_as", needs=("new_document",), tier=3,
       members=("IModelDocExtension.SaveAs3", "IModelDoc2.GetPathName", "IModelDoc2.GetTitle"))
def save_as(px: Px) -> None:
    """SaveAs3 writes a new part where asked, silently, and the document follows it."""
    folder = sc.env_scratch_folder(px)
    px.require(bool(folder) and folder[1:3] == ":\\", f"the scratch folder is on a drive: {folder!r}")
    path = os.path.join(folder, "Probe Save.SLDPRT")
    px.require(not os.path.exists(path), f"{path} does not exist yet")
    with sc.scratch(px) as doc:
        ext = sc.extension(doc)
        got, result = px.attempt(
            "SaveAs3(path, current version, silent, null, null, out long, out long)",
            lambda: call(ext, "SaveAs3", path, SAVE_AS_CURRENT_VERSION, SAVE_AS_SILENT, sc.null(), sc.null(),
                         sc.out_long(), sc.out_long()),
        )
        px.fact("save_as3_result", repr(result) if got else "raised")
        px.fact("save_as3_result_is_tuple", isinstance(result, tuple))
        px.check(got and bool(_flag(result)), "SaveAs3 says it saved")
        px.check(os.path.isfile(path), "the file is on disk")
        title = str(call(doc, "GetTitle"))
        px.shared.setdefault("created", []).append(title)
        px.fact("title_after_save", title)
        saved_at = str(call(doc, "GetPathName"))
        px.fact("path_after_save", saved_at)
        px.check(saved_at.lower() == path.lower(), "GetPathName now names the new file")

        size = os.path.getsize(path)
        got, again = px.attempt("SaveAs3 onto the same path",
                                lambda: call(ext, "SaveAs3", path, SAVE_AS_CURRENT_VERSION, SAVE_AS_SILENT,
                                             sc.null(), sc.null(), sc.out_long(), sc.out_long()))
        px.fact("save_as3_onto_existing_file", {"flag": _flag(again) if got else "raised", "size_before": size,
                                                "size_after": os.path.getsize(path)})

    got, other = px.attempt("IModelDoc2.SaveAs3 on another new part", lambda: _doc_save_as3(px, folder))
    px.fact("imodeldoc2_save_as3", other if got else "raised")


def _doc_save_as3(px: Px, folder: str) -> Any:
    path = os.path.join(folder, "Probe Save Doc.SLDPRT")
    with sc.scratch(px) as doc:
        result = call(doc, "SaveAs3", path, SAVE_AS_CURRENT_VERSION, SAVE_AS_SILENT)
        px.shared.setdefault("created", []).append(str(call(doc, "GetTitle")))
        return {"returned": result, "on_disk": os.path.isfile(path)}
