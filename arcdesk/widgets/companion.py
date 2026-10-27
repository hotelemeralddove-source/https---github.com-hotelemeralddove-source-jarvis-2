"""The Mini Companion — a small painted robot that shows what JARVIS is doing.

States: idle (bob + blink), listening (rings expand), thinking (spin),
speaking (mouth bars). Clicking it opens the console.

Cost: one 130x130 widget, a handful of primitives per frame, on the shared
ticker. No sprite sheets on disk, no video, no QML.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..theme import Theme
from ..ticker import ticker

IDLE, LISTENING, THINKING, SPEAKING = "idle", "listening", "thinking", "speaking"


class Companion(QWidget):
    clicked = Signal()

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._t = 0.0
        self._state = IDLE
        self._blink = 0.0
        self._next_blink = 3.0
        self._mouth = 0.0
        self.setFixedSize(150, 150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("JARVIS — click to talk")
        ticker().tick.connect(self._on_tick)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.update()

    def advance(self, seconds: float) -> None:
        self._t += seconds
        self.update()

    # -- animation -------------------------------------------------------
    def _on_tick(self, dt: float) -> None:
        self._t += dt
        self._next_blink -= dt
        if self._next_blink <= 0:
            self._blink = 1.0
            self._next_blink = 2.4 + (self._t % 3.0)
        if self._blink > 0:
            self._blink = max(0.0, self._blink - dt * 6.0)
        if self._state == SPEAKING:
            self._mouth = 0.5 + 0.5 * math.sin(self._t * 18.0)
        else:
            self._mouth = max(0.0, self._mouth - dt * 4.0)
        if self.isVisible():
            self.update()

    # -- paint -----------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802
        th = self._theme
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        s = min(w, h) / 128.0
        q.scale(s, s)
        w, h = 128.0, 128.0
        cx, cy = w / 2.0, h / 2.0
        accent = th.q("accent")
        accent2 = th.q("accent2")

        bob = math.sin(self._t * 1.6) * 2.5 if self._state != THINKING else 0.0
        cy += bob

        # --- state rings -------------------------------------------------
        if self._state == LISTENING:
            for i in range(2):
                phase = (self._t * 0.9 + i * 0.5) % 1.0
                r = 26 + phase * 34
                col = QColor(accent.red(), accent.green(), accent.blue(),
                             int(120 * (1.0 - phase)))
                q.setPen(QPen(col, 1.4))
                q.setBrush(Qt.BrushStyle.NoBrush)
                q.drawEllipse(QPointF(cx, cy), r, r)
        elif self._state == THINKING:
            q.setPen(QPen(accent2, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            q.setBrush(Qt.BrushStyle.NoBrush)
            start = int((self._t * 420.0) % 360 * 16)
            q.drawArc(QRectF(cx - 34, cy - 34, 68, 68), start, 100 * 16)

        # --- antenna -----------------------------------------------------
        ant_col = accent if self._state != THINKING else accent2
        q.setPen(QPen(QColor(ant_col.red(), ant_col.green(), ant_col.blue(), 200), 1.6))
        q.drawLine(QPointF(cx, cy - 27), QPointF(cx, cy - 38))
        pulse = 0.55 + 0.45 * math.sin(self._t * (3.0 if self._state == LISTENING else 2.0))
        q.setPen(Qt.PenStyle.NoPen)
        glow = QRadialGradient(QPointF(cx, cy - 40), 8)
        glow.setColorAt(0.0, QColor(ant_col.red(), ant_col.green(), ant_col.blue(),
                                    int(220 * pulse)))
        glow.setColorAt(1.0, QColor(ant_col.red(), ant_col.green(), ant_col.blue(), 0))
        q.setBrush(glow)
        q.drawEllipse(QPointF(cx, cy - 40), 8, 8)
        q.setBrush(QColor(255, 255, 255, int(180 + 70 * pulse)))
        q.drawEllipse(QPointF(cx, cy - 40), 2.2, 2.2)

        # --- head / body -------------------------------------------------
        body = QRectF(cx - 22, cy - 22, 44, 40)
        grad = QRadialGradient(QPointF(cx, cy - 8), 40)
        base = QColor(th.panel).lighter(135)
        grad.setColorAt(0.0, base.lighter(120))
        grad.setColorAt(1.0, base.darker(140))
        q.setBrush(grad)
        q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 170), 1.3))
        q.drawRoundedRect(body, 13, 13)

        # --- eyes --------------------------------------------------------
        eye_h = 5.0 * (1.0 - 0.9 * self._blink)
        eye_y = cy - 6
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(255, 255, 255, 235))
        for dx in (-8.0, 8.0):
            q.drawRoundedRect(QRectF(cx + dx - 3.4, eye_y - eye_h / 2, 6.8, max(1.0, eye_h)), 2.6, 2.6)
        # eye glow
        eg = QRadialGradient(QPointF(cx, eye_y), 20)
        eg.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 70))
        eg.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        q.setBrush(eg)
        q.drawEllipse(QPointF(cx, eye_y), 20, 12)

        # --- mouth -------------------------------------------------------
        if self._state == SPEAKING:
            bars = 4
            for i in range(bars):
                bh = 1.5 + 5.0 * abs(math.sin(self._t * 12.0 + i * 1.3)) * self._mouth
                bx = cx - 8 + i * 5.0
                q.setBrush(QColor(accent2.red(), accent2.green(), accent2.blue(), 220))
                q.drawRoundedRect(QRectF(bx, cy + 9 - bh / 2, 2.6, bh), 1.2, 1.2)
        else:
            q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 150), 1.2))
            q.drawArc(QRectF(cx - 6, cy + 4, 12, 7), 200 * 16, 140 * 16)

        q.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
