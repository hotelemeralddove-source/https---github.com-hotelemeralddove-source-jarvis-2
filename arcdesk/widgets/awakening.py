"""The awakening — the "magic begin" moment.

When the wake word fires, the whole screen goes through a short cinematic before
the app appears: rings expand from the centre, HUD scan lines sweep, corner
brackets lock on, and `ARC // ONLINE` prints.

Performance contract (this is a full-screen animation, so it gets rules):
  * lives for ~1.9 s and then deletes itself — nothing keeps running
  * painted from cached layers; only the sweep and rings move
  * click-through and Esc-cancellable: it can never trap the user
  * refuses to run if the effect scale says we are in Gaming mode
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QLinearGradient, QPainter,
                           QPen)
from PySide6.QtWidgets import QWidget

from ..theme import Theme
from ..ticker import ticker

DURATION = 1.9


class Awakening(QWidget):
    finished = Signal()

    def __init__(self, theme: Theme, message: str = "JARVIS // ONLINE") -> None:
        super().__init__()
        self._theme = theme
        self._message = message
        self._t = 0.0
        self._done = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry() if screen else QRectF(0, 0, 1280, 720).toRect())
        self._connect_ticker()

    def _connect_ticker(self) -> None:
        ticker().tick.connect(self._on_tick)

    # -- animation -------------------------------------------------------
    def _on_tick(self, dt: float) -> None:
        self._t += dt
        if self._t >= DURATION and not self._done:
            self._done = True
            try:
                ticker().tick.disconnect(self._on_tick)
            except (RuntimeError, TypeError):
                pass
            self.hide()
            self.finished.emit()
            QTimer.singleShot(0, self.deleteLater)
            return
        self.update()

    def cancel(self) -> None:
        """Abort without emitting finished() — used when the exit phrase arrives
        while the cinematic is still playing."""
        self._done = True
        try:
            ticker().tick.disconnect(self._on_tick)
        except (RuntimeError, TypeError):
            pass
        self.hide()
        QTimer.singleShot(0, self.deleteLater)

    def advance(self, seconds: float) -> None:
        """Used by --screenshot to render a mid-animation frame."""
        self._t = seconds
        self.update()

    # -- paint -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        th = self._theme
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        p = min(1.0, self._t / DURATION)

        accent = th.q("accent")
        accent2 = th.q("accent2")

        # ---- background dim + vertical gradient flash ------------------
        veil = int(215 * (1.0 - max(0.0, (p - 0.72) / 0.28)))
        q.fillRect(0, 0, w, h, QColor(2, 6, 12, max(0, veil)))
        grad = QLinearGradient(0, 0, 0, h)
        flash = max(0.0, 0.35 * math.sin(p * math.pi))
        grad.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(),
                                    int(60 * flash)))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        q.fillRect(0, 0, w, int(h * 0.55), grad)

        # ---- expanding rings -------------------------------------------
        for i in range(4):
            local = max(0.0, min(1.0, (p - i * 0.10) / 0.62))
            if local <= 0:
                continue
            r = (0.06 + local * 0.72) * max(w, h) * 0.62
            alpha = int(190 * (1.0 - local) ** 1.4)
            if alpha <= 2:
                continue
            col = accent if i % 2 == 0 else accent2
            q.setPen(QPen(QColor(col.red(), col.green(), col.blue(), alpha),
                          max(1.0, 3.2 - i * 0.6)))
            q.setBrush(Qt.BrushStyle.NoBrush)
            q.drawEllipse(QPointF(cx, cy), r, r)

        # ---- HUD scan lines sweeping outward ---------------------------
        q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 90), 1.0))
        for i in range(14):
            off = (p * 1.6 + i * 0.07) % 1.0
            y = cy - max(w, h) * 0.55 + off * max(w, h) * 1.10
            if 0 < y < h:
                q.drawLine(QPointF(0, y), QPointF(w, y))

        # ---- radial burst rays (the "power up" moment) -----------------
        burst = max(0.0, min(1.0, (p - 0.10) / 0.35)) * (1.0 - max(0.0, (p - 0.62) / 0.30))
        if burst > 0.01:
            q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(),
                                 int(150 * burst)), 1.2))
            reach = max(w, h) * (0.18 + p * 0.42)
            for i in range(48):
                ang = math.radians(i * 7.5 + self._t * 26.0)
                r0 = 78 + 30 * math.sin(i * 1.7)
                q.drawLine(QPointF(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                           QPointF(cx + math.cos(ang) * reach, cy + math.sin(ang) * reach))

        # ---- corner brackets (lock on at 35 %) -------------------------
        if p > 0.35:
            grow = min(1.0, (p - 0.35) / 0.30)
            arm = 46 * grow
            pad = 28 + (1 - grow) * 26
            q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(),
                                 int(200 * grow)), 2.0))
            for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                x = pad if sx > 0 else w - pad
                y = pad if sy > 0 else h - pad
                q.drawLine(QPointF(x, y), QPointF(x + sx * arm, y))
                q.drawLine(QPointF(x, y), QPointF(x, y + sy * arm))

        # ---- centre reactor spark --------------------------------------
        core = QRectF(cx - 34, cy - 34, 68, 68)
        q.setPen(QPen(QColor(255, 255, 255, int(200 * (1 - abs(0.5 - p) * 2))), 1.4))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.drawEllipse(core)
        for i in range(3):
            start = int(((self._t * 300) + i * 120) % 360 * 16)
            q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 210),
                          max(1.4, 5.0 - i * 1.2),
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            q.drawArc(core.adjusted(i * 9, i * 9, -i * 9, -i * 9), start, 90 * 16)

        # ---- title ------------------------------------------------------
        if p > 0.28:
            shown = min(len(self._message), int((p - 0.28) * 26))
            text = self._message[:shown]
            f = QFont("Segoe UI", 1)
            f.setPixelSize(max(15, int(min(w, h) * 0.030)))
            f.setWeight(QFont.Weight.Bold)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 9.0)
            q.setFont(f)
            fm = q.fontMetrics()
            tw = fm.horizontalAdvance(text)
            q.setPen(QColor(th.text if p < 0.86 else th.accent))
            q.drawText(QPointF(cx - tw / 2.0, cy + max(64, h * 0.10)), text)

            sub = "SYSTEM TRANSFORMATION IN PROGRESS"
            f2 = QFont("Segoe UI", 1)
            f2.setPixelSize(max(8, int(min(w, h) * 0.011)))
            f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
            q.setFont(f2)
            if p > 0.5:
                fm2 = q.fontMetrics()
                sw = fm2.horizontalAdvance(sub)
                q.setPen(QColor(th.dim).lighter(150))
                q.drawText(QPointF(cx - sw / 2.0, cy + max(96, h * 0.145)), sub)

        # ---- closing white-out -----------------------------------------
        if p > 0.93:
            out = int(90 * ((p - 0.93) / 0.07))
            q.fillRect(0, 0, w, h, QColor(255, 255, 255, min(255, out)))
        q.end()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._t = DURATION
