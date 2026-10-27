"""Read the documents once, in the background, without ever blocking the window.

The wizard can turn document search on, and that promise has to be kept without a
frozen progress bar: a folder with 3,000 PDFs takes minutes, and the user should be
typing while it happens.

So this is deliberately tiny — one daemon thread, one start guard, a status string the
window can show, and a callback for when it finishes. It reads only; if it fails, the
failure is reported as text rather than thrown at a thread nobody is watching.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_thread: threading.Thread | None = None
status: dict = {"state": "idle", "detail": "", "count": 0, "seconds": 0.0}


def running() -> bool:
    return bool(_thread and _thread.is_alive())


def start(win=None, roots: str = "", ocr: bool = False) -> bool:
    """Start the index once. Returns False when it is already running."""
    global _thread
    with _lock:
        if running():
            return False
        status.update({"state": "working", "detail": "reading documents…"})

        def work() -> None:
            from . import deepsearch
            try:
                data = deepsearch.index(roots, ocr=ocr)
                if data.get("error"):
                    status.update({"state": "failed", "detail": data["error"]})
                else:
                    stat = data.get("stats", {})
                    status.update({"state": "done", "count": stat.get("found", 0),
                                   "seconds": stat.get("seconds", 0.0),
                                   "detail": f"{stat.get('found', 0)} documents "
                                             f"searchable"})
                    if win is not None:
                        _tell(win, f"Document search is ready — {stat.get('found', 0)} "
                                   f"documents indexed in {stat.get('seconds', 0):.1f} s. "
                                   f"Ask 'which file mentions…'")
            except Exception as exc:                      # never crash a silent thread
                status.update({"state": "failed", "detail": f"{type(exc).__name__}: {exc}"})
                if win is not None:
                    _tell(win, f"Document indexing stopped: {type(exc).__name__}. "
                               f"Search still works on whatever was read.")

        _thread = threading.Thread(target=work, daemon=True, name="arc-docs")
        _thread.start()
        return True


def _tell(win, text: str) -> None:
    try:
        win.console.add_note(text)
    except Exception:
        pass
