"""Thin circular gauge used for CPU / RAM."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..theme import Theme
from ..ticker import ticker


class ArcGauge(QWidget):
    START = 225.0   # degrees, bottom-left
    SPAN = 270.0    # sweep clockwise

    def __init__(self, label: str, unit: str = "%", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self._unit = unit
        self._value = 0.0
        self._target = 0.0
        self._theme: Theme | None = None
        self._accent_attr = "accent"
        self.setMinimumSize(104, 104)
        self.setMaximumSize(150, 150)
        ticker().tick.connect(self._on_tick)

    def set_theme(self, theme: Theme, accent_attr: str = "accent") -> None:
        self._theme = theme
        self._accent_attr = accent_attr
        self.update()

    def set_value(self, value: float, text: str | None = None) -> None:
        self._target = max(0.0, min(100.0, float(value)))
        if text is not None:
            self._text = text
        self.update()

    _text = ""

    def _on_tick(self, dt: float) -> None:
        if abs(self._target - self._value) < 0.15:
            if self._value != self._target:
                self._value = self._target
                self.update()
            return
        self._value += (self._target - self._value) * min(1.0, dt * 9.0)
        if self.isVisible():
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        th = self._theme
        if th is None:
            return
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        side = min(self.width(), self.height())
        r = side / 2.0 - 8.0
        c = QRectF(self.width() / 2.0 - r, self.height() / 2.0 - r, r * 2, r * 2)

        accent = th.q(self._accent_attr)
        q.setBrush(Qt.BrushStyle.NoBrush)

        # track
        q.setPen(QPen(th.q("dim", 70), max(2.0, r * 0.11),
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        q.drawArc(c, int(self.START * 16), int(-self.SPAN * 16))

        # value
        span = -self.SPAN * (self._value / 100.0)
        q.setPen(QPen(accent, max(2.0, r * 0.11),
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        q.drawArc(c, int(self.START * 16), int(span * 16))

        # numbers
        q.setPen(QColor(th.text))
        f = QFont("Segoe UI", 1)
        f.setPixelSize(max(13, int(side * 0.20)))
        f.setWeight(QFont.Weight.DemiBold)
        q.setFont(f)
        q.drawText(c.adjusted(0, -side * 0.045, 0, -side * 0.045),
                   Qt.AlignmentFlag.AlignCenter, f"{self._value:.0f}{self._unit}")

        f2 = QFont("Segoe UI", 1)
        f2.setPixelSize(max(9, int(side * 0.105)))
        f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        q.setFont(f2)
        q.setPen(QColor(th.dim).lighter(135))
        q.drawText(c.adjusted(0, side * 0.20, 0, side * 0.20),
                   Qt.AlignmentFlag.AlignCenter, self._label.upper())
        q.end()
