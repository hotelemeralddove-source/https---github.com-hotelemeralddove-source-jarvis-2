"""One timer to drive every animation in the app.

This is the single most important file for keeping CPU/GPU cost down.
Instead of N widgets each owning a QTimer at their own rate, there is one
shared QTimer. Widgets only repaint when they are visible, and the whole
ticker drops to 10 fps in Gaming mode or stops entirely when animations
are paused.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal


class FrameTicker(QObject):
    tick = Signal(float)  # seconds since previous tick (clamped)

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._emit)
        self._fps = 30
        self._base_fps = 30          # what was asked for, before any self-protection
        self._paused = False
        self._last = time.perf_counter()
        # Measured cost of one frame: how long the handlers took. This is the number
        # that explains "romba slow": if a frame costs more than the interval, the app
        # is permanently behind and every click feels late.
        self._frame_ms = 0.0
        self._slow_frames = 0
        self._fast_frames = 0
        self._auto = True
        self._apply()

    # -- control ---------------------------------------------------------
    def set_fps(self, fps: int) -> None:
        fps = max(1, min(120, int(fps)))
        if fps == self._fps:
            return
        self._fps = fps
        self._apply()

    def set_paused(self, paused: bool) -> None:
        if paused == self._paused:
            return
        self._paused = paused
        self._apply()

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def fps(self) -> int:
        return 0 if self._paused else self._fps

    # -- cost ------------------------------------------------------------
    @property
    def frame_ms(self) -> float:
        """Milliseconds the last frame's handlers took (smoothed)."""
        return self._frame_ms

    def stats(self) -> dict:
        budget = 1000.0 / max(1, self._fps)
        return {"fps": self.fps, "base": self._base_fps, "frame_ms": round(self._frame_ms, 2),
                "load": round(self._frame_ms / budget, 2) if budget else 0.0,
                "paused": self._paused, "auto": self._auto}

    def set_base_fps(self, fps: int) -> None:
        """What the person asked for. Adaptive slowdown works inside this ceiling."""
        self._base_fps = max(1, min(120, int(fps)))
        self._fps = self._base_fps
        self._slow_frames = self._fast_frames = 0
        self._apply()

    def set_auto(self, on: bool) -> None:
        self._auto = bool(on)
        if not on:
            self._fps = self._base_fps
            self._apply()

    # -- internals -------------------------------------------------------
    def _apply(self) -> None:
        if self._paused:
            self._timer.stop()
            return
        self._timer.setInterval(max(8, int(1000 / self._fps)))
        if not self._timer.isActive():
            self._last = time.perf_counter()
            self._timer.start()

    def _emit(self) -> None:
        start = time.perf_counter()
        dt = start - self._last
        self._last = start
        # Clamp: after sleep/resume or a stall, never hand widgets a 4-second dt.
        self.tick.emit(min(dt, 0.1))
        cost = (time.perf_counter() - start) * 1000.0
        # smoothed, so one odd frame does not change the frame rate
        self._frame_ms = self._frame_ms * 0.8 + cost * 0.2 if self._frame_ms else cost
        if self._auto:
            self._adapt()

    def _adapt(self) -> None:
        """Drop the frame rate when the machine cannot afford it, and come back later.

        A laptop that cannot draw 30 frames a second should not try: the queue grows,
        clicks land late, and the app *feels* frozen while it is only behind. Half the
        frame rate is invisible; a one-second input lag is not.
        """
        budget = 1000.0 / max(1, self._fps)
        if self._frame_ms > budget * 0.55:
            self._slow_frames += 1
            self._fast_frames = 0
        elif self._frame_ms < budget * 0.25:
            self._fast_frames += 1
            self._slow_frames = 0
        if self._slow_frames >= 45 and self._fps > 12:
            self._fps = max(12, int(self._fps * 0.75))
            self._slow_frames = 0
            self._apply()
        elif self._fast_frames >= 300 and self._fps < self._base_fps:
            self._fps = min(self._base_fps, int(self._fps * 1.25) + 1)
            self._fast_frames = 0
            self._apply()


_ticker: FrameTicker | None = None


def ticker() -> FrameTicker:
    global _ticker
    if _ticker is None:
        _ticker = FrameTicker()
    return _ticker
