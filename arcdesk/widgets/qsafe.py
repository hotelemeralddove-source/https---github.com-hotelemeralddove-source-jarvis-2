"""QThread workers may outlive their button, but never their owner's death.

The crash this module exists for was in `fault.log`, not in a test:

    Windows fatal exception: code 0xc0000374
    Current thread … settings.py in open_ears
    …
    CRITICAL qt  QThread: Destroyed while thread '' is still running

0xc0000374 is heap corruption. The line above it says why: a `QThread` whose C++ object
was destroyed while its thread was still running. In PySide6 the destroy happens the moment
Python garbage-collects the last reference — so "close the dialog while a download runs"
is not a warning, it is a use-after-free, and the abort lands wherever the next allocation
happens to be (here: the next time `open_ears` ran, which is why it looked like *the
option* was crashing the app).

The rule this module enforces:

  1. workers are parentless and owned by a module-level set, so no dialog's death can
     destroy a thread that is still running;
  2. closing the window stops the worker first (cancel, then wait, then move on);
  3. `stop_all()` runs when the app quits, so nothing is left writing files behind the
     person who closed the tray icon.

`EngineDialog` already had its own copy of this (see its `_LIVE_WORKERS`); this module is
the shared home so the other download dialogs get the same guarantee instead of each
inventing it — and forgetting, the way the crash came from.
"""
from __future__ import annotations

import threading

_LIVE: set = set()
_LIVE_LOCK = threading.Lock()


def register(worker) -> None:
    with _LIVE_LOCK:
        _LIVE.add(worker)


def unregister(worker) -> None:
    """Drop the reference only once the thread has fully stopped.

    `finished` fires when the thread function has returned, but the thread is not
    quite dead yet: the worker's `run` frame — holding the last Python reference —
    is released on the worker's own stack a moment later. If that were the last
    reference, the QThread's C++ object would be deleted from a still-exiting
    thread, which is the 0xc0000374 this module was written against. `wait()`
    returns the instant the thread is truly over, so from here on every thread
    that deletes this worker is telling the truth.
    """
    try:
        if hasattr(worker, "wait"):
            worker.wait(1000)
    except Exception:                                            # noqa: BLE001
        pass
    with _LIVE_LOCK:
        _LIVE.discard(worker)


def count() -> int:
    with _LIVE_LOCK:
        return len(_LIVE)


def stop_worker(worker, wait_ms: int = 6000) -> None:
    """Ask one worker to finish, and give it a moment to actually finish.

    Idempotent: safe to call from `closeEvent` *and* `reject` *and* quit. A worker that
    does not stop in time is left running — deliberately. It is parentless and referenced
    by the set, so it cannot destroy anything, and the `finished` signal removes it.
    (Killing it is worse: a stuck download keeps writing files, but a terminated C++
    thread is the abort this whole module exists to prevent.)
    """
    if worker is None:
        return
    try:
        stop = getattr(worker, "stop", None)
        if callable(stop):
            stop()
        elif hasattr(worker, "cancel"):
            worker.cancel.set()
        if worker.wait(wait_ms):
            unregister(worker)
    except Exception:                                            # noqa: BLE001
        pass


def stop_all(wait_ms: int = 8000) -> int:
    """Called when the app quits. Returns how many workers were still running."""
    with _LIVE_LOCK:
        workers = list(_LIVE)
    for w in workers:
        stop_worker(w, wait_ms)
    with _LIVE_LOCK:
        _LIVE.clear()
    return len(workers)


def shut(worker_attr: str, dialog) -> None:
    """The one line a dialog's `closeEvent` and `reject` both reduce to.

    Takes the attribute by name because the three download dialogs all keep their worker
    at `self._worker`, and the guard must stay identical across them — that is the whole
    point of the shared home.
    """
    worker = getattr(dialog, worker_attr, None)
    if worker is None:
        return
    stop_worker(worker)
    setattr(dialog, worker_attr, None)
