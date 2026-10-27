"""Open a window, and never let that be the last thing the app does.

The report was six words long and it was the important one:

    "YENTHA OPTIONS KULA PONALUM AUTO CRASH MATHIRI CLOSE AAGUTHU"

Every option, and the app closes. Reading twelve dialogs one at a time does not find a fault
that all of them share — but it does tell you what the fix has to be: **a dialog must not be
able to end the process**. Whatever a dialog does while it is being built, while it is open,
or while it is being thrown away, the app stays, and the person is told in words what went
wrong, with the trace that explains it.

So every `…Dialog(...).exec()` in this app goes through `open_dialog()`:

  * build + run in a `try`, so an exception is a message, not a disappearing window;
  * `sys.excepthook` and `threading.excepthook` are watched for the duration, so an error on
    a dialog's worker thread — which Python would otherwise print to a console that a
    `pythonw` start does not have — lands in the same place;
  * the traceback is written to the log and to the crash bundle, so the next report has the
    line in it;
  * a toast/note in the console says which option failed, so it is not a mystery window.

It cannot catch a native abort (a segfault inside a driver, a `QThread` destroyed while
running). Nothing in Python can. What it does do is make everything else survivable — and
the crash report that gets sent afterwards has the reason in it.
"""
from __future__ import annotations

import sys
import threading
from typing import Any, Callable

_SEEN: list[str] = []


def _remember(text: str) -> None:
    short = text.strip().splitlines()[-1][:200] if text.strip() else ""
    if short and short not in _SEEN:
        _SEEN.append(short)
        del _SEEN[:-8]


def last_failures() -> list[str]:
    return list(_SEEN)


def _record(name: str, detail: str) -> str:
    """Write it down: log, crash bundle, and the console. Returns the line for the person."""
    _remember(detail)
    message = f"{name} could not open: {detail.strip().splitlines()[-1][:160]}"
    try:
        import logging
        logging.getLogger("arcdesk.ui").error("%s\n%s", name, detail)
    except Exception:                                            # noqa: BLE001
        pass
    try:
        from .. import logs
        logs.note(f"UI · {message}")
        if logs.crash_streak() >= 1:
            logs.crash_bundle()          # the file the "send it as it is" report comes from
    except Exception:                                            # noqa: BLE001
        pass
    return message


def open_dialog(name: str, build: Callable[[], Any], parent=None,
                exec_it: bool = True) -> Any | None:
    """Build and show one window. Returns the window (or None if it could not be built).

    `build` is a function so that the construction itself is inside the `try` — the crash
    the person saw was in a constructor, not in `exec()`.
    """
    import traceback

    problems: list[str] = []

    def hook(tp, val, tb) -> None:                               # noqa: ANN001
        problems.append("".join(traceback.format_exception(tp, val, tb)))

    def thread_hook(args) -> None:                               # noqa: ANN001
        problems.append("".join(traceback.format_exception(
            args.exc_type, args.exc_value, args.exc_traceback)))

    old_hook, old_thread = sys.excepthook, getattr(threading, "excepthook", None)
    sys.excepthook = hook
    if old_thread is not None:
        threading.excepthook = thread_hook

    dialog = None
    try:
        dialog = build()
        if dialog is None:
            return None
        if exec_it:
            dialog.exec()
        else:
            dialog.show()
        return dialog
    except Exception:                                            # noqa: BLE001
        problems.append(traceback.format_exc())
        return None
    finally:
        sys.excepthook = old_hook
        if old_thread is not None:
            threading.excepthook = old_thread
        if problems:
            detail = problems[0]
            message = _record(name, detail)
            # tell the person, in the app, in one line — and keep the app
            try:
                from PySide6.QtWidgets import QMessageBox
                box = QMessageBox(parent)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("JARVIS is still running")
                box.setText(message)
                box.setInformativeText(
                    "The rest of JARVIS is unaffected — this was one window, and it has "
                    "been written to the log with the exact line. Nothing was changed by "
                    "it.\n\nIf it happens every time, use Help → send the crash report; the "
                    "reason is now inside it.")
                box.setDetailedText(detail[-4000:])
                box.exec()
            except Exception:                                    # noqa: BLE001
                pass
        # a dialog that was built and then raised must not leak its window
        if dialog is not None and problems:
            try:
                dialog.close()
                dialog.deleteLater()
            except Exception:                                    # noqa: BLE001
                pass


def run_button(name: str, action: Callable[[], Any]) -> None:
    """For a button that opens something: same guard, no dialog object to keep."""
    import traceback
    try:
        action()
    except Exception:                                            # noqa: BLE001
        _record(name, traceback.format_exc())
