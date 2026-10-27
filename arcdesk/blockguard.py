"""Catch the bug while it is running, not in a screenshot two weeks later.

`uiwork` gives slow work somewhere else to live. This file makes sure nobody quietly puts
it back: it wraps the handful of calls that cost real time — starting a child process,
opening a socket, importing a heavy package, sleeping — and, when one of them is called
**on the UI thread**, it writes down exactly where:

    UI · widgets/engine_dialog.py:235 called subprocess.run on the drawing thread

Two modes, because the two uses are different:

    ARCDESK_UI_GUARD=1        warn:  log it, carry on. This is what the shipped app does,
                                     so a violation is visible in the crash log instead of
                                     being an invisible 3-second freeze.
    ARCDESK_UI_GUARD=strict   raise: the tests run this way, so a regression fails the
                                     build instead of being reported by a person.

What is deliberately *not* guarded: file reads, `find_spec`, `shutil.which`. They are
fast enough on a warm file system, and flagging them would train everyone to ignore this.
The rule is about the things that take seconds: child processes, sockets, downloads, and
waiting.
"""
from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
import urllib.request

#: name -> original callable. Empty means the guard is off.
_ORIGINALS: dict[str, object] = {}
_HITS: list[str] = []
_ACTIVE = False
_STRICT = False
_DEPTH = 12


class UIRuleViolation(RuntimeError):
    """Raised in strict mode: something that waits was called from the drawing thread."""


def enabled() -> bool:
    return _ACTIVE


def strict() -> bool:
    return _STRICT


def hits() -> list[str]:
    return list(_HITS)


def reset() -> None:
    del _HITS[:]


# ------------------------------------------------------------------ where was it?
def _repo_file(path: str) -> bool:
    return "arcdesk" in path.replace("\\", "/")


def where(depth: int = 3) -> str:
    """Where it was called, and by whom — `file:line in function` for 3 project frames.

    One frame is not enough for a report: `backends.py:63 in _port_open` says what the call
    was but not which dialog made it. Three frames is the shortest chain that usually
    names the button.
    """
    frame = None
    try:
        frame = _current()[0]
    except Exception:                                            # noqa: BLE001
        return "unknown"
    skip = {"blockguard.py", "uiwork.py"}
    found: list[str] = []
    while frame is not None and len(found) < depth:
        path = frame.f_code.co_filename
        name = os.path.basename(path)
        if _repo_file(path) and name not in skip:
            parts = path.replace("\\", "/").split("/")
            short = "/".join(parts[parts.index("arcdesk"):]) if "arcdesk" in parts else path
            found.append(f"{short}:{frame.f_lineno} in {frame.f_code.co_name}")
        frame = frame.f_back
    return " <- ".join(found) or "unknown"


def _current():
    """The stack of the calling thread, without importing inspect (which is slow)."""
    import sys
    return sys._getframe(1),                                    # noqa: SLF001


def _on_ui_thread() -> bool:
    return threading.current_thread() is threading.main_thread()


def _record(what: str) -> None:
    line = f"{what} on the drawing thread at {where()}"
    if line in _HITS:
        return
    _HITS.append(line)
    try:
        from . import logs
        logs.note("UI · " + line)
    except Exception:                                            # noqa: BLE001
        print("UI · " + line)


def _wrap(module, attr: str, what: str):
    original = getattr(module, attr)

    def guarded(*args, **kwargs):
        if _ACTIVE and _on_ui_thread():
            _record(what)
            if _STRICT:
                raise UIRuleViolation(
                    f"{what} was called from the UI thread at {where()} — this is the "
                    f"freeze that leaves the window stuck in front with a spinner. Move "
                    f"it to arcdesk.uiwork.run().")
        return original(*args, **kwargs)

    guarded.__name__ = getattr(original, "__name__", attr)
    guarded.__doc__ = getattr(original, "__doc__", None)
    guarded._arcdesk_original = original                       # noqa: SLF001
    return guarded


_TARGETS = (
    (subprocess, "run", "subprocess.run"),
    (subprocess, "Popen", "subprocess.Popen"),
    (subprocess, "check_output", "subprocess.check_output"),
    (subprocess, "check_call", "subprocess.check_call"),
    (subprocess, "call", "subprocess.call"),
    (urllib.request, "urlopen", "urllib.request.urlopen"),
    (socket, "create_connection", "socket.create_connection"),
    (time, "sleep", "time.sleep"),
)


def install(mode: str | None = None) -> bool:
    """Turn it on. `mode` is "warn", "strict", or "off" (the env var wins by default)."""
    global _ACTIVE, _STRICT
    want = (mode or os.environ.get("ARCDESK_UI_GUARD", "off")).strip().lower()
    if want in ("", "0", "off", "no", "false"):
        return False
    _STRICT = want.startswith("strict") or want == "raise"
    for module, attr, what in _TARGETS:
        if attr in _ORIGINALS:
            continue
        _ORIGINALS[attr] = getattr(module, attr)
        setattr(module, attr, _wrap(module, attr, what))
    _ACTIVE = True
    return True


def uninstall() -> None:
    global _ACTIVE, _STRICT
    for module, attr, _what in _TARGETS:
        original = _ORIGINALS.pop(attr, None)
        if original is not None:
            setattr(module, attr, original)
    _ACTIVE = False
    _STRICT = False


def report() -> str:
    if not _HITS:
        return "nothing that waits was called on the drawing thread"
    lines = ["these calls ran on the drawing thread — each one can freeze the window:"]
    lines += [f"  {hit}" for hit in _HITS]
    return "\n".join(lines)
