"""Slow work has exactly one home, and it is not the thread that draws the window.

The report this file answers, twice: *"again ithu mathiri front la vanthu struck aagi
nikithu"* — a dialog appears in front, and then nothing moves. Every version of that
complaint has had the same shape:

    a QPushButton or a QDialog constructor -> a function that waits
       (a child python, a 1.5 GB download, a socket, a sleep) -> the event loop stops
       -> no repaint, no Esc, no Cancel, and the Windows busy ring spins for ever.

There is no way to make waiting free. There is a way to make it **not happen in the
thread that paints**, and that is what this module provides, in four small pieces:

    run(work, done=…)     run it on a worker; deliver the answer to the UI thread
    busy_cursor()         point at a waiting cursor for the duration — and always put the
                          cursor back, even when the work raises (a cursor nobody restored
                          is the ring in the screenshot)
    clear_stuck_cursors() undo any override left behind by anything, anywhere
    StallWatch            a 100 ms heartbeat on the UI thread: if it ever misses by more
                          than `threshold_ms`, the log says which line was responsible

The last one is the part that makes the next report cheap. Instead of "it hung again",
the log contains:

    UI · the window was frozen for 2.3 s — main thread was in widgets/window.py:1237

Deliberately no Qt threading primitives beyond a Signal: a `Signal` emitted from a worker
thread is delivered queued to the receiver's thread, which is the one Qt-guaranteed way
to touch widgets from a worker without a crash that only happens on someone else's PC.
"""
from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
import traceback

from PySide6.QtCore import QObject, Qt, QTimer, Signal

#: Where a stall is worth writing down. 400 ms is past "a slow paint" and well before
#: "the user has started clicking again and thinks it is broken".
STALL_MS = 400

#: How many stalls to keep for the app to show in its own words.
KEEP_STALLS = 5


# --------------------------------------------------------------------------- jobs
class _Bridge(QObject):
    """Lives in the UI thread. The worker only ever emits on it."""

    finished = Signal(object, object)          # result, error text (one of them is None)


_ROOT: QObject | None = None


def _root() -> QObject:
    """The C++ parent of every bridge.

    It is created on the UI thread and lives for the whole process, so a bridge's C++
    object can never be deleted from a worker thread. That deletion is the bug this
    process used to die with: the last reference to a finished Job was dropped on the
    worker's own stack (the worker's `run` frame), the parentless bridge went with it,
    Qt tore down per-thread state on the wrong thread ("QThreadStorage: entry destroyed
    before end of thread"), and the heap corruption then landed wherever the next
    allocation happened to be — for the user, an access violation inside
    `window.py eventFilter`, the app "just closing" while Settings was open.
    """
    global _ROOT
    if _ROOT is None:
        _ROOT = QObject()
    return _ROOT


class Job:
    """One piece of work, and the honest way to ask it to stop."""

    def __init__(self, work, name: str, done=None, failed=None) -> None:
        self.name = name
        self.done = done
        self.failed = failed
        self.cancel = threading.Event()
        self.started = time.monotonic()
        self.finished_at = 0.0
        self.error = ""
        self._bridge = _Bridge(_root())
        self._bridge.finished.connect(self._deliver, Qt.ConnectionType.QueuedConnection)
        self._thread = threading.Thread(target=self._run, args=(work,),
                                       name=name, daemon=True)
        # Holds the Job (and with it the bridge's Python wrapper) until the UI thread
        # reaps it in `_deliver`. A worker thread must never be the one to drop the
        # last reference: if it were, the bridge's C++ object — created here on the UI
        # thread — would be deleted from the worker, and that is the corruption above.
        # The C++ object itself is additionally safe under `_root()` no matter what.
        self._self_ref = None

    # -- worker side ------------------------------------------------------
    def _run(self, work) -> None:
        try:
            result, error = work(self.cancel), None
        except BaseException as exc:                             # noqa: BLE001
            result = None
            error = f"{type(exc).__name__}: {exc}"
        try:
            self._bridge.finished.emit(result, error)
        except RuntimeError:
            pass                                                 # the app is closing

    # -- UI side ----------------------------------------------------------
    def _deliver(self, result, error) -> None:
        self.finished_at = time.monotonic()
        self.error = error or ""
        _LIVE.discard(self)
        try:
            if error:
                if self.failed is not None:
                    self.failed(error)
            elif self.done is not None:
                self.done(result)
        except Exception:                                        # noqa: BLE001
            _note("WARNING", f"a finished job ({self.name}) raised while being applied:\n"
                             + traceback.format_exc())
        # UI thread, always: break the connection (it holds the Job) and the self
        # reference, so the Job is reaped here — never on a worker's stack.
        try:
            self._bridge.finished.disconnect(self._deliver)
        except Exception:                                        # noqa: BLE001
            pass
        self._self_ref = None

    # -- use --------------------------------------------------------------
    def start(self) -> "Job":
        self._thread.start()
        self._self_ref = self
        return self

    def alive(self) -> bool:
        return self._thread.is_alive()

    def seconds(self) -> float:
        end = self.finished_at or time.monotonic()
        return end - self.started


#: Jobs nobody else holds a reference to would be garbage collected mid-flight, and the
#: answer would never arrive. This set is that reference.
_LIVE: set[Job] = set()


def run(work, done=None, failed=None, name: str = "arc-work") -> Job:
    """Run `work(cancel)` on a daemon thread and deliver its result to the UI thread.

    `work` takes one argument — a `threading.Event` — so long jobs can stop when the
    dialog is cancelled. Call this from the UI thread. Anything the function returns
    arrives in `done(result)`; anything it raises arrives in `failed("ErrorType: text")`.
    """
    job = Job(work, name, done=done, failed=failed)
    _LIVE.add(job)
    return job.start()


def busy() -> int:
    """How many jobs are still running (used by the tests and by the app's quiet state)."""
    return len([j for j in _LIVE if j.alive()])


# ------------------------------------------------------------------------ cursor
def clear_stuck_cursors() -> int:
    """Put the cursor back to normal, however many overrides were left behind.

    A `setOverrideCursor` whose `restore` never runs is the ring in `20.png`: the app is
    not doing anything any more, but it still says "waiting". Cheap, idempotent, and called
    when a dialog closes and when the window is activated again.
    """
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:                                            # noqa: BLE001
        return 0
    removed = 0
    while QApplication.overrideCursor() is not None and removed < 32:
        QApplication.restoreOverrideCursor()
        removed += 1
    if removed:
        _note("WARNING", f"UI · put the cursor back ({removed} override(s) had been left on)")
    return removed


@contextlib.contextmanager
def busy_cursor():
    """A waiting cursor that is always undone — including when the work raises."""
    from PySide6.QtWidgets import QApplication
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        yield
    finally:
        clear_stuck_cursors()


#: The sweep timer. Held here on purpose: a QTimer with no parent and no reference is
#: garbage collected at the next collection, and the sweep would silently stop.
_HYGIENE: QTimer | None = None


def install_cursor_hygiene(interval_ms: int = 2000) -> QTimer:
    """Take the waiting cursor away as soon as nothing is actually running.

    The invariant this enforces is small and worth writing down: **only `uiwork` may set
    an override cursor**, and while no job is running there must be none. If something
    still leaves one behind — a third-party dialog, a modal message box, a future
    regression — this takes it back within two seconds instead of for ever.
    """
    global _HYGIENE
    if _HYGIENE is not None:
        return _HYGIENE
    timer = QTimer()
    _HYGIENE = timer
    timer.setInterval(max(250, int(interval_ms)))

    def sweep() -> None:
        if busy() == 0:
            clear_stuck_cursors()

    timer.timeout.connect(sweep)
    timer.start()
    return timer


# ------------------------------------------------------------------- stall watch
class StallWatch(QObject):
    """A heartbeat that notices when the UI thread was not allowed to run.

    The heartbeat is a `QTimer` on the UI thread. If it is late, the UI thread was busy —
    and `sys._current_frames()` still points at whatever it was busy *in*, which is the one
    piece of information every "it hung" report has been missing.
    """

    def __init__(self, threshold_ms: int = STALL_MS, interval_ms: int = 100) -> None:
        super().__init__()
        self.threshold_ms = int(threshold_ms)
        self._last = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(max(20, int(interval_ms)))
        self._timer.timeout.connect(self._beat)
        self.stalls: list[tuple[float, str]] = []
        # A heartbeat can only tell *that* the UI thread stopped. To say *where*, the
        # frames have to be sampled while it is stopped — so one cheap daemon thread
        # reads the main thread's stack every 50 ms into a small ring. That is the only
        # way to blame the right line: by the time the heartbeat fires, the freeze is
        # already over and the main thread is back in the event loop.
        self._samples: list[tuple[float, str]] = []
        self._stop = threading.Event()
        self._sampler: threading.Thread | None = None

    # -- lifecycle --------------------------------------------------------
    def start(self) -> "StallWatch":
        self._last = time.monotonic()
        self._timer.start()
        if self._sampler is None or not self._sampler.is_alive():
            self._stop.clear()
            self._sampler = threading.Thread(target=self._sample_loop,
                                             name="arc-ui-sampler", daemon=True)
            self._sampler.start()
        return self

    def stop(self) -> None:
        self._timer.stop()
        self._stop.set()

    def _sample_loop(self) -> None:
        ident = threading.main_thread().ident
        while not self._stop.wait(0.05):
            try:
                frame = sys._current_frames().get(ident)
                now = time.monotonic()
                self._samples.append((now, self._describe(frame)))
                del self._samples[:-40]
            except Exception:                                    # noqa: BLE001
                return

    def _during(self, started: float, ended: float) -> str:
        """The stack the UI thread was in while it was frozen (closest to the middle)."""
        middle = (started + ended) / 2.0
        window = [(at, where) for at, where in self._samples if started <= at <= ended]
        if not window:
            return ""
        return min(window, key=lambda pair: abs(pair[0] - middle))[1]

    # -- the check --------------------------------------------------------
    def _beat(self) -> None:
        now = time.monotonic()
        started = self._last
        gap_ms = (now - started) * 1000.0
        self._last = now
        if gap_ms > self.threshold_ms:
            where = self._during(started, now) or self.blame()
            self.stalls.append((gap_ms / 1000.0, where))
            del self.stalls[:-KEEP_STALLS]
            _note("WARNING", f"UI · the window was frozen for {gap_ms / 1000.0:.1f} s — "
                             f"main thread was in {where}")

    @staticmethod
    def blame() -> str:
        """Which line the UI thread is inside right now. Read from the live frame."""
        try:
            frame = sys._current_frames().get(threading.main_thread().ident)
        except Exception:                                        # noqa: BLE001
            return "unknown"
        return StallWatch._describe(frame)

    @staticmethod
    def _describe(frame) -> str:
        """`file:line in function`, skipping this module's own frames."""
        skip = (os.path.basename(__file__), "blockguard.py")
        while frame is not None:
            name = os.path.basename(frame.f_code.co_filename)
            if name not in skip:
                rel = frame.f_code.co_filename
                parts = rel.replace("\\", "/").split("/")
                if "arcdesk" in parts:
                    rel = "/".join(parts[parts.index("arcdesk"):])
                elif parts:
                    rel = "/".join(parts[-2:])
                return f"{rel}:{frame.f_lineno} in {frame.f_code.co_name}"
            frame = frame.f_back
        return "unknown"

    def worst(self) -> tuple[float, str]:
        return max(self.stalls, key=lambda s: s[0]) if self.stalls else (0.0, "")

    def report(self) -> str:
        if not self.stalls:
            return "the window never froze for longer than " + f"{self.threshold_ms} ms"
        lines = ["the window froze because the code below ran in the drawing thread:"]
        for seconds, where in self.stalls:
            lines.append(f"  {seconds:.2f} s  {where}")
        return "\n".join(lines)


#: The one watch the app uses. `install()` fills it in.
WATCH: StallWatch | None = None


def install(threshold_ms: int = STALL_MS) -> StallWatch:
    """Start watching the UI thread. Called once, from `run.py`, after the window exists."""
    global WATCH
    if WATCH is None:
        WATCH = StallWatch(threshold_ms)
    WATCH.start()
    return WATCH


def stalls() -> str:
    return WATCH.report() if WATCH is not None else "the watchdog was never started"


# --------------------------------------------------------------------------- notes
def _note(level: str, text: str) -> None:
    try:
        from . import logs
        logs.note(text)
    except Exception:                                            # noqa: BLE001
        print(f"{level}: {text}")
