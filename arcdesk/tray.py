"""Status-bar tray: the app's always-there handle, and its safe exit."""
from __future__ import annotations


from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .theme import THEMES
from .widgets.window import MainWindow


def reactor_icon(theme_key: str = "chill", size: int = 64) -> QIcon:
    """Icon drawn at runtime -> keeps the app asset-free (no .ico to ship)."""
    th = THEMES.get(theme_key, THEMES["chill"])
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    q = QPainter(pm)
    q.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QPointF(size / 2, size / 2)
    accent = th.q("accent")
    grad = QRadialGradient(c, size * 0.48)
    grad.setColorAt(0.0, QColor(255, 255, 255, 240))
    grad.setColorAt(0.45, accent)
    grad.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
    q.setPen(Qt.PenStyle.NoPen)
    q.setBrush(grad)
    q.drawEllipse(c, size * 0.46, size * 0.46)
    q.setBrush(Qt.BrushStyle.NoBrush)
    q.setPen(QPen(QColor(255, 255, 255, 200), max(1.0, size * 0.045)))
    r = size * 0.40
    q.drawArc(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), 30 * 16, 120 * 16)
    q.drawArc(QRectF(c.x() - r, c.y() - r, r * 2, r * 2), 210 * 16, 120 * 16)
    q.end()
    return QIcon(pm)


class ArcTray(QSystemTrayIcon):
    def __init__(self, win: MainWindow) -> None:
        super().__init__(reactor_icon(win.theme.key), win)
        self.win = win
        self.setToolTip("Arc Desk")
        self._menu = QMenu()
        self.setContextMenu(self._menu)
        self._rebuild()
        self.activated.connect(self._on_activated)

    def _rebuild(self) -> None:
        m = self._menu
        m.clear()
        m.addAction("Show Arc Desk").triggered.connect(self._show)
        m.addAction("Awaken  (magic begin)").triggered.connect(self._awaken)
        m.addAction("Command palette").triggered.connect(
            lambda: self.win.palette.popup())
        m.addSeparator()
        for key, th in THEMES.items():
            a = m.addAction(f"{th.label} mode")
            a.setCheckable(True)
            a.setChecked(key == self.win.theme.key)
            a.triggered.connect(lambda _=False, k=key: self._mode(k))
        m.addSeparator()
        m.setStyleSheet(self.win.styleSheet())
        m.addAction("Check: is my Windows untouched?").triggered.connect(
            self.win.verify_untouched)
        m.addSeparator()
        m.addAction("Quit").triggered.connect(self._quit)

    def _awaken(self) -> None:
        self.win.awaken()

    def _mode(self, key: str) -> None:
        self.win.set_mode(key)
        self._rebuild()

    def _show(self) -> None:
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()

    def _quit(self) -> None:
        self.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            if self.win.isVisible():
                self.win.hide()
            else:
                self._show()
