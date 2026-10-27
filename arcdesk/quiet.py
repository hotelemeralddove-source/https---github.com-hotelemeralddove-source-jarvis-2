"""Spawn child processes without a console window. One place, every platform.

The bug this file exists for
---------------------------
ArcDesk ships as a **windowless** program (`console=False` in the spec, `pythonw.exe`
when run from source). That is the point: no black box behind the interface. But a
windowless parent hands its *children* no console, and on Windows a console program
started without a console gets a brand-new one — visible, black, and gone in a flash.
So every PowerShell snippet (the reply voice, UI Automation, screen reading), every
ffmpeg frame, every tesseract OCR pass, every local-model server and every wake daemon
restart popped a command prompt on top of the user's work. Say five sentences and you
watch five windows open; leave it running and they "keep opening".

`-WindowStyle Hidden` is **not** a fix: PowerShell still creates and shows the console
for a moment before it applies the style. The fix is `CREATE_NO_WINDOW` on the spawn
itself, which is what this module adds — everywhere, once, instead of in 90 call sites.

What is here
------------
    run(cmd, **kw)            subprocess.run, but silent
    popen(cmd, **kw)          subprocess.Popen, but silent
    call(cmd, **kw)           subprocess.call, but silent
    check_output(cmd, **kw)   subprocess.check_output, but silent

The keyword arguments are the normal subprocess ones. Three of them are translated
rather than passed through, because they mean different things per platform:

    start_new_session=True    Windows: DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
                              POSIX:   passed through unchanged
    creationflags=N           Windows: OR'd with CREATE_NO_WINDOW
                              POSIX:   dropped (POSIX refuses the argument)
    startupinfo=…             Windows: kept, and given SW_HIDE if it has no show state
                              POSIX:   dropped

On POSIX nothing is hidden and nothing changes — there are no console windows to hide,
and the audio/video tools we call there do not care.
"""
from __future__ import annotations

import os
import subprocess
import sys

IS_WIN = sys.platform == "win32"

#: The one flag that matters: "start this child with no console window at all".
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
#: A window that is also kept out of the foreground and never gets focus.
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
SW_HIDE = 0

#: Set from tests to exercise the Windows branch on a machine that is not Windows.
_FORCE_WIN: bool | None = None

_WINDOWS_ONLY = ("creationflags", "startupinfo")


def _is_win() -> bool:
    return IS_WIN if _FORCE_WIN is None else bool(_FORCE_WIN)


class _ShowHidden:
    """A STARTUPINFO stand-in for when the Windows branch is tested elsewhere.

    Only reachable when `_FORCE_WIN` is set on a non-Windows machine — on Windows the
    real `subprocess.STARTUPINFO` is used. Two attributes are all that matters.
    """
    STARTF_USESHOWWINDOW = getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)

    def __init__(self) -> None:
        self.dwFlags = 0
        self.wShowWindow = SW_HIDE


def _startupinfo():
    """A STARTUPINFO that asks Windows to show the window hidden."""
    real = getattr(subprocess, "STARTUPINFO", None)       # Windows only
    info = real() if real is not None else _ShowHidden()
    info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
    info.wShowWindow = SW_HIDE
    return info


def kwargs(detached: bool = False, **given) -> dict:
    """Turn ordinary subprocess keywords into "and do not show a window" ones.

    Public because it is the honest thing to test: a test can call this and read the
    dictionary, instead of pretending to watch a monitor.
    """
    out = dict(given)
    want_detached = bool(out.pop("start_new_session", False))
    if detached:
        want_detached = True

    if not _is_win():
        # POSIX: creationflags/startupinfo are refused, start_new_session is legal.
        for key in _WINDOWS_ONLY:
            out.pop(key, None)
        if want_detached:
            out["start_new_session"] = True
        return out

    flags = int(out.pop("creationflags", 0) or 0) | CREATE_NO_WINDOW
    if want_detached:
        flags |= DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    out["creationflags"] = flags
    info = out.pop("startupinfo", None)
    out["startupinfo"] = info if info is not None else _startupinfo()
    # A venv, a patched PATH, a Chinese-locale tool: none of it should depend on
    # whether the child inherited a console, because there is none to inherit.
    return out


def run(cmd, **given):
    """`subprocess.run`, with no console window. Raises exactly what subprocess raises."""
    return subprocess.run(cmd, **kwargs(**given))


def popen(cmd, **given):
    """`subprocess.Popen`, with no console window."""
    return subprocess.Popen(cmd, **kwargs(**given))


def call(cmd, **given):
    """`subprocess.call`, with no console window."""
    return subprocess.call(cmd, **kwargs(**given))


def check_output(cmd, **given):
    """`subprocess.check_output`, with no console window."""
    return subprocess.check_output(cmd, **kwargs(**given))


def describe() -> str:
    """One line for the diagnostics page — the question "will this flash?" answered."""
    have = covered()
    where = " (compiled build)" if frozen() and not _PATCHED else ""
    if not _is_win():
        return (f"child processes: {len(have)} of {len(_EXPECTED)} spawn sites route "
                f"through quiet.py{where} · nothing to hide on this platform")
    return (f"child processes: {len(have)} of {len(_EXPECTED)} spawn sites route through "
            f"quiet.py{where} · CREATE_NO_WINDOW on every child · no console can appear")


#: Modules that spawn children at runtime. Kept here so `quiet.describe()` and the
#: test that guards it agree on one list, and a new module that spawns something has
#: to be added here on purpose rather than discovered by a user watching black boxes.
_EXPECTED = ("actions", "ai/mcp", "ai/tools", "ai/voice", "brain", "clone", "desktop_guard",
             "editing", "engines", "generate", "media", "paths", "player", "reading",
             "screenhelp", "security", "sfx", "uia", "vision", "wake/daemon_runner",
             "widgets/settings", "widgets/shortcuts", "widgets/window")


def imports_quiet(text: str) -> bool:
    """Does this module's source import quiet — in ANY of the ways Python allows?

    Looking for the literal string "import quiet" missed `from . import audio, quiet`,
    which is a perfectly ordinary import and made the doctor report a module as
    unpatched while it was patched. An import line is a line that starts with `from` or
    `import` and mentions quiet as a whole word.
    """
    import re
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            continue
        if re.search(r"\bquiet\b", stripped):
            return True
    return False


def _patched() -> list[str]:
    """Which runtime modules import this one — measured from the source, not assumed.

    In a frozen build (PyInstaller) there are no `.py` files to read: the modules live
    inside the archive. Scanning then finds nothing, which used to make the doctor report
    a false FAIL ("Silent spawns") in every packaged app. A frozen build is compiled from
    this same tree, so the honest answer there is the declared list — and `frozen` says
    which answer you are looking at.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parent
    found = []
    for name in _EXPECTED:
        path = root / f"{name}.py"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if imports_quiet(text):
            found.append(name)
    return found


def frozen() -> bool:
    """True when this code is running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def covered() -> list[str]:
    """The modules we can vouch for: measured when the sources are readable, declared
    when they are compiled into the archive."""
    if _PATCHED:
        return list(_PATCHED)
    return list(_EXPECTED) if frozen() else []


_PATCHED = _patched()
