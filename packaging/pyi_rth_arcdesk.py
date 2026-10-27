"""PyInstaller runtime hook — runs before `run.py`, inside the frozen app.

Why this exists: `ArcDesk.exe` is built with `console=False`, so it has no console and
no way to say anything. If it dies before `run.py` reaches `logs.ensure_streams()` —
a missing DLL, a bad first import, a permission problem in `%APPDATA%` — the user sees
one thing: **a window that never appears**. That is the least debuggable failure this
program can have, and it is exactly the one a frozen build produces most often.

So the very first code that runs in the bundle makes the log survive:

    %APPDATA%\\ArcDesk\\logs\\arcdesk.log

Everything after this point — including a crash in the bootloader's own script — lands in
a file instead of nowhere. The hook is defensive on purpose: it must never be the reason
the app fails to start.
"""
from __future__ import annotations

import sys


def _install() -> None:
    try:
        from arcdesk import logs
    except Exception:                                  # noqa: BLE001
        return
    try:
        logs.ensure_streams()      # stdout/stderr are None under a windowed build
    except Exception:                                  # noqa: BLE001
        pass
    try:
        logs.install()
    except Exception:                                  # noqa: BLE001
        pass
    try:
        sys.stderr.write("")       # proves the redirect landed somewhere real
    except Exception:                                  # noqa: BLE001
        pass


_install()
