"""Shortcut tiles: launch a handful of apps straight from the HUD.

Kept deliberately small: no icon files on disk (labels only), no background
process watching, one subprocess per click and nothing else.
"""
from __future__ import annotations

import subprocess

from .. import quiet
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

DEFAULT_SHORTCUTS = [
    {"label": "FILES", "target": "explorer"},
    {"label": "NOTES", "target": "notepad"},
    {"label": "CALC", "target": "calc"},
    {"label": "TASKS", "target": "taskmgr"},
]

WIN_BUILTINS = {
    "explorer": "explorer.exe",
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "taskmgr": "taskmgr.exe",
    "settings": "ms-settings:",
    "paint": "mspaint.exe",
}


class ShortcutTile(QPushButton):
    assign_requested = Signal(object)   # the tile itself

    def __init__(self, label: str, target: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.target = target
        self.setObjectName("tile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _p: self.assign_requested.emit(self))

    def set_entry(self, label: str, target: str) -> None:
        self.target = target
        self.setText(label)
        self.setToolTip(f"{label.title()}  ·  {target}")


class ShortcutShelf(QWidget):
    status = Signal(str)

    def __init__(self, entries: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tiles: list[ShortcutTile] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        head = QLabel("SHORTCUTS")
        head.setObjectName("hint")
        f = head.font()
        f.setPixelSize(9)
        f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 2.2)
        head.setFont(f)
        outer.addWidget(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        for entry in (entries or DEFAULT_SHORTCUTS)[:6]:
            tile = ShortcutTile(str(entry.get("label", "APP")).upper(),
                                str(entry.get("target", "")))
            tile.clicked.connect(lambda _=False, t=tile: self._launch(t))
            tile.assign_requested.connect(self._assign)
            row.addWidget(tile)
            self._tiles.append(tile)
        row.addStretch(1)
        outer.addLayout(row)

    # -- launch ----------------------------------------------------------
    def _launch(self, tile: ShortcutTile) -> None:
        target = (tile.target or "").strip()
        if not target:
            return
        try:
            if sys.platform == "win32":
                cmd = WIN_BUILTINS.get(target.lower(), target)
                if cmd.startswith("ms-") or target.startswith(("http", "ms-")):
                    import os
                    os.startfile(cmd)  # noqa: S606
                else:
                    quiet.popen([cmd], close_fds=True)
            elif sys.platform == "darwin":
                quiet.popen(["open", target])
            else:
                quiet.popen(["xdg-open", target], close_fds=True)
            self.status.emit(f"LAUNCHED · {tile.text()}")
        except Exception as exc:
            self.status.emit(f"LAUNCH FAILED · {type(exc).__name__}")

    # -- reassign --------------------------------------------------------
    def _assign(self, tile: ShortcutTile) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pick an app or file for this tile",
            str(Path.home()), "Programs (*.exe *.lnk *.bat);;All files (*)")
        if not path:
            return
        label = Path(path).stem.upper()[:8]
        tile.set_entry(label, path)
        self.status.emit(f"ASSIGNED · {label}")
        self.entries_changed()

    def entries_changed(self) -> None:
        self.changed = True

    changed = False

    def dump(self) -> list[dict]:
        return [{"label": t.text(), "target": t.target} for t in self._tiles]


class Card(QFrame):
    """Thin helper so the window code does not repeat the card wrapper."""

    def __init__(self, inner: QWidget | None = None, margins=(18, 14, 18, 14)) -> None:
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*margins)
        if inner is not None:
            lay.addWidget(inner)
        self.body = lay
