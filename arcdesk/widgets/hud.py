"""HUD pieces: clock card and the mode pill bar."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from ..theme import MODE_ORDER, THEMES, Theme


class ClockCard(QWidget):
    """Painted, not styled: one widget, three text lines, one repaint/second."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._weather = "WEATHER · OFFLINE"
        self._weather_ok = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.update)
        self._timer.start()
        self.setMinimumHeight(148)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_weather(self, text: str, ok: bool) -> None:
        self._weather = text
        self._weather_ok = ok
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        th = self._theme
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        from datetime import datetime
        t = datetime.now()

        # time
        f = QFont("Segoe UI", 1)
        f.setPixelSize(int(h * 0.42))
        f.setWeight(QFont.Weight.Light)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -1.0)
        q.setFont(f)
        q.setPen(QColor(th.text))
        q.drawText(QRectF(0, h * 0.10, w, h * 0.46),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   t.strftime("%H:%M"))

        fm = q.fontMetrics()
        tw = fm.horizontalAdvance(t.strftime("%H:%M"))
        f2 = QFont("Segoe UI", 1)
        f2.setPixelSize(int(h * 0.15))
        f2.setWeight(QFont.Weight.DemiBold)
        q.setFont(f2)
        q.setPen(th.q("accent"))
        q.drawText(QRectF(tw + 10, h * 0.10, w - tw, h * 0.46),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                   t.strftime("%S"))

        # date
        f3 = QFont("Segoe UI", 1)
        f3.setPixelSize(int(h * 0.115))
        f3.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0)
        q.setFont(f3)
        q.setPen(QColor(th.dim).lighter(160))
        q.drawText(QRectF(0, h * 0.58, w, h * 0.18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   t.strftime("%A, %d %B %Y").upper())

        # weather / status line with a dot
        dot_col = th.q("accent") if self._weather_ok else QColor(th.dim)
        q.setPen(QPen(dot_col, 1))
        q.setBrush(dot_col)
        q.drawEllipse(QRectF(2, h * 0.83, 6, 6))
        f4 = QFont("Segoe UI", 1)
        f4.setPixelSize(int(h * 0.105))
        f4.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        q.setFont(f4)
        q.setPen(QColor(th.dim).lighter(150))
        q.drawText(QRectF(16, h * 0.78, w - 16, h * 0.18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   self._weather.upper())
        q.end()


class ModeBar(QWidget):
    mode_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key in MODE_ORDER:
            btn = QPushButton(THEMES[key].label.upper())
            btn.setObjectName("pill")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(THEMES[key].hint)
            self._group.addButton(btn)
            lay.addWidget(btn)
            self._buttons[key] = btn
            btn.clicked.connect(lambda _=False, k=key: self.mode_changed.emit(k))
        lay.addStretch(1)

    def set_mode(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
