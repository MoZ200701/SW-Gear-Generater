"""Turning a COM failure into something a report can hold.

``pythoncom.com_error`` carries four things in ``args``: the HRESULT, its text,
an ``excepinfo`` tuple with the server's own description, and ``argerror`` —
the 1-based position of the argument the dispatcher choked on. That last one is
what settles an arity or a type question without guessing, so it is kept.

Pure: nothing here imports pywin32, so it is tested on Linux with look-alikes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

KNOWN = {
    0x80004005: "E_FAIL",
    0x80070057: "E_INVALIDARG",
    0x8000FFFF: "E_UNEXPECTED",
    0x80020003: "DISP_E_MEMBERNOTFOUND",
    0x80020004: "DISP_E_PARAMNOTFOUND",
    0x80020005: "DISP_E_TYPEMISMATCH",
    0x80020006: "DISP_E_UNKNOWNNAME",
    0x80020008: "DISP_E_BADVARTYPE",
    0x80020009: "DISP_E_EXCEPTION",
    0x8002000A: "DISP_E_OVERFLOW",
    0x8002000E: "DISP_E_BADPARAMCOUNT",
    0x80010001: "RPC_E_CALL_REJECTED",
    0x8001010A: "RPC_E_SERVERCALL_RETRYLATER",
    0x800706BA: "RPC_S_SERVER_UNAVAILABLE",
    0x800706BE: "RPC_S_CALL_FAILED",
}


def _unsigned(hresult: Any) -> Optional[int]:
    try:
        return int(hresult) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return None


def hresult_name(hresult: Any) -> str:
    value = _unsigned(hresult)
    if value is None:
        return ""
    return KNOWN.get(value, f"0x{value:08X}")


def describe_error(exc: BaseException) -> Dict[str, Any]:
    """``{type, hresult, name, text, argerror}`` for any exception, COM or not."""
    out: Dict[str, Any] = {"type": type(exc).__name__, "hresult": "", "name": "", "text": str(exc), "argerror": None}
    args = getattr(exc, "args", ())
    looks_like_com = (
        isinstance(args, tuple) and len(args) >= 2 and _unsigned(args[0]) is not None
        and (type(exc).__name__ == "com_error" or len(args) == 4)
    )
    if not looks_like_com:
        return out
    value = _unsigned(args[0])
    out["hresult"] = f"0x{value:08X}"
    out["name"] = hresult_name(value)
    text = str(args[1]) if args[1] is not None else ""
    if len(args) >= 3 and isinstance(args[2], tuple) and len(args[2]) >= 3 and args[2][2]:
        text = f"{text}: {args[2][2]}" if text else str(args[2][2])
        scode = _unsigned(args[2][5]) if len(args[2]) >= 6 else None
        if scode:
            out["scode"] = f"0x{scode:08X}"
            out["scode_name"] = hresult_name(scode)
    out["text"] = text
    if len(args) >= 4 and args[3] is not None:
        try:
            out["argerror"] = int(args[3])
        except (TypeError, ValueError):
            out["argerror"] = None
    return out


def one_line(exc: BaseException) -> str:
    """The same, as one sentence fragment for a report line."""
    info = describe_error(exc)
    parts = [info["name"] or info["type"]]
    if info["text"]:
        parts.append(info["text"])
    if info.get("argerror"):
        parts.append(f"argument {info['argerror']}")
    return " — ".join(parts)
