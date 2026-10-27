"""What JARVIS is doing right now — one honest answer, on its own thread.

The complaint was not "it is slow", it was *"I cannot tell whether anything is
happening"*: a request went in, the window sat there, and the only way to find out was
to wait and hope. This module is the answer to that, kept out of the GUI so it can be
tested without one.

Three jobs, and they are deliberately small:

  * a **live line** — "tool: open_app · 1.4 s" — with elapsed time that keeps moving,
    so "stuck" and "working" look different;
  * a **timeline** of finished steps, so after the fact you can see what ran and how
    long it took without reading a log file;
  * a **cancel flag** that the agent checks between steps, so Stop actually stops
    between two tool calls instead of pretending.

Threading: the agent writes, the GUI reads. Every mutation happens under one lock, and
readers get a copy (`snapshot()`), never a live object.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

IDLE, THINKING, TOOL, SPEAKING, DONE, FAILED, CANCELLED = (
    "idle", "thinking", "tool", "speaking", "done", "failed", "cancelled")

KEEP = 24          # how many finished steps are worth remembering


@dataclass
class Step:
    label: str
    started: float = field(default_factory=time.monotonic)
    ended: float = 0.0
    note: str = ""

    @property
    def seconds(self) -> float:
        end = self.ended or time.monotonic()
        return max(0.0, end - self.started)

    def line(self) -> str:
        return f"{self.label} · {self.seconds:.1f} s" + (f" · {self.note}" if self.note else "")


class Activity:
    """The single record of what is happening. One per process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = IDLE
        self._step: Step | None = None
        self._history: list[Step] = []
        self._request = ""
        self._began = 0.0
        self._cancel = threading.Event()
        self._strokes = 0            # bumped on every change, so the GUI can tell

    # ------------------------------------------------------------------ writes
    def begin(self, request: str) -> None:
        """A new request. Clears the previous cancel flag — that is the point of it."""
        with self._lock:
            self._cancel.clear()
            self._history.clear()
            self._request = (request or "").strip()[:200]
            self._began = time.monotonic()
            self._state = THINKING
            self._step = Step("thinking")
            self._strokes += 1

    def step(self, label: str) -> None:
        """Close the running step and open a new one."""
        with self._lock:
            if self._state in (DONE, FAILED, CANCELLED):
                return
            self._close_current()
            self._step = Step(label)
            self._state = SPEAKING if label.startswith("speaking") else TOOL \
                if label.startswith("tool") else THINKING
            self._strokes += 1

    def note(self, text: str) -> None:
        """Attach a short fact to the running step ('denied', 'offline', …)."""
        with self._lock:
            if self._step is not None:
                self._step.note = (text or "")[:60]
            self._strokes += 1

    def finish(self, ok: bool = True, why: str = "") -> None:
        with self._lock:
            self._close_current()
            self._state = CANCELLED if self._cancel.is_set() else (DONE if ok else FAILED)
            if why:
                self._history.append(Step("stopped" if self._cancel.is_set() else "failed",
                                          note=why[:80]))
                self._history[-1].ended = self._history[-1].started
            self._step = None
            self._strokes += 1

    def cancel(self) -> bool:
        """Ask the worker to stop. True if there was something to stop."""
        with self._lock:
            busy = self._state in (THINKING, TOOL, SPEAKING)
            self._cancel.set()
            if busy:
                self._state = CANCELLED
            self._strokes += 1
            return busy

    # ------------------------------------------------------------------ reads
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def busy(self) -> bool:
        return self.state in (THINKING, TOOL, SPEAKING)

    def elapsed(self) -> float:
        with self._lock:
            return max(0.0, time.monotonic() - self._began) if self._began else 0.0

    def snapshot(self) -> dict:
        """A copy for the GUI: state, live line, elapsed seconds, finished steps."""
        with self._lock:
            live = ""
            if self._step is not None:
                # label + any fact about it ("denied", "slow 2.3 s") — the total
                # seconds are added by whoever draws it, so the number never doubles
                live = self._step.label + (f" · {self._step.note}" if self._step.note else "")
            return {
                "state": self._state,
                "busy": self._state in (THINKING, TOOL, SPEAKING),
                "request": self._request,
                "live": live,
                "elapsed": self._elapsed_locked(),
                "history": [s.line() for s in self._history[-KEEP:]],
                "strokes": self._strokes,
                "cancelled": self._cancel.is_set(),
            }

    def line(self) -> str:
        """One sentence for a status bar or a log.

        The elapsed seconds are always there, because a number that keeps growing is
        the difference between "working" and "wedged".
        """
        snap = self.snapshot()
        if snap["state"] == IDLE:
            return "idle"
        if not snap["busy"]:
            first = f"{snap['state']}"
            return f"{first} in {snap['elapsed']:.1f} s ({snap['request'][:40]})"
        return f"{snap['live'] or snap['state']} · {snap['elapsed']:.1f} s"

    # ------------------------------------------------------------------ internals
    def _elapsed_locked(self) -> float:
        return max(0.0, time.monotonic() - self._began) if self._began else 0.0

    def _close_current(self) -> None:
        if self._step is None:
            return
        self._step.ended = time.monotonic()
        if self._step.label != "thinking" or self._step.seconds > 0.3:
            self._history.append(self._step)
        self._step = None


_ONE: Activity | None = None


def activity() -> Activity:
    """The process-wide record. Created on first use so tests can start clean."""
    global _ONE
    if _ONE is None:
        _ONE = Activity()
    return _ONE


def reset() -> Activity:
    """Replace the singleton — used by tests, and by `Settings → clear`."""
    global _ONE
    _ONE = Activity()
    return _ONE
