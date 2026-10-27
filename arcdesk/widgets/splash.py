"""Something on screen within a fraction of a second of the double-click.

"app open aagavum time aagutha machi" — on a cold Windows start a frozen app has to load
several hundred DLLs, and Explorer plus antivirus take their turn. Nothing can make that
instant, but a launch that shows *nothing* for two seconds reads as "it did not open",
which is the same complaint as the hidden window.

So: a small frameless card with the app's own name, shown before the main window is built,
closed the moment the real window appears (or after 8 seconds, whichever comes first, so a
failure can never leave it on screen).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class Splash(QWidget):
    def __init__(self, name: str = "JARVIS") -> None:
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        box = QVBoxLayout(self)
        box.setContentsMargins(22, 16, 22, 16)
        title = QLabel("ARC DESK")
        title.setStyleSheet("color:#7ef0ff;font-weight:700;letter-spacing:3px;"
                            "background:transparent;")
        box.addWidget(title)
        line = QLabel(f"starting {name}…")
        line.setStyleSheet("color:#b9cbd2;background:transparent;")
        box.addWidget(line)
        self.setFixedWidth(220)
        self._place()

    def _place(self) -> None:
        try:
            area = QGuiApplication.primaryScreen().availableGeometry()
        except Exception:                                        # noqa: BLE001
            return
        self.adjustSize()
        self.move(area.center().x() - self.width() // 2,
                  area.center().y() - self.height() // 2)
