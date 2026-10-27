"""Double-click this on Windows: ArcDesk opens with no console window behind it.

Windows runs a `.pyw` file with `pythonw.exe`, which is the whole point — `python.exe`
would leave a black command prompt sitting behind the app for as long as it runs, and
that is exactly what "there is a command prompt open behind ARC" looks like.

Two things this file has to do that `run.py` does not:

1. **Give the app somewhere to print.** Under `pythonw.exe`, `sys.stdout` and
   `sys.stderr` are `None`, and the first `print()` in `run.py` would raise
   `AttributeError: 'NoneType' object has no attribute 'write'` — the app would die
   before it drew anything. So both are pointed at a log file first.
2. **Survive a crash with evidence.** A windowless app that dies silently is
   undebuggable, so the traceback goes to the same log, and the log's path is printed
   on the next console run of `run.py` if anything went wrong.

The log lives next to the settings: `%APPDATA%\\ArcDesk\\logs\\arcdesk.log`.

Nothing here is Windows-only: double-clicking it on Linux/macOS runs the same code
and simply writes the log file instead of a console.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _open_log():
    """Point a missing stdout/stderr at the log, keep a real one if there is one.

    The real implementation lives in `arcdesk/logs.py` so that `run.py` gets the same
    protection when it is started by any other windowless route (the .vbs starter, the
    Startup shortcut, the installed .exe). This is the thin wrapper.
    """
    from arcdesk import logs
    logs.ensure_streams()
    return sys.stdout          # the file, or the real console if this one had one


def main() -> int:
    _open_log()
    try:
        from run import main as run_main
        return int(run_main())
    except SystemExit:
        raise
    except BaseException:                                          # noqa: BLE001
        # Nothing to show and nowhere to say it, except the log — so write it, and
        # write it before anything else has a chance to swallow it.
        traceback.print_exc()
        try:
            sys.stdout.flush()
        except Exception:                                          # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
