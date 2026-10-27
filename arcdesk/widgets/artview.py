"""The easel — the window that shows what JARVIS drew, and takes edits.

Kept deliberately small: a canvas, one line of text, and a save button. The point
is that "make the ear bigger" has somewhere to happen and you can see the result
immediately, without opening a folder.

Click-through is irrelevant here on purpose — this is a normal window you close.
It is not an overlay.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)


class ArtWindow(QWidget):
    def __init__(self, theme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle("Arc Desk · sketch")
        self.resize(760, 620)
        self.setMinimumSize(430, 380)
        self._sketch = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setMinimumHeight(320)
        self.canvas.setStyleSheet("background:#0a1420;border:1px solid rgba(34,211,238,.22);"
                                  "border-radius:12px;")
        lay.addWidget(self.canvas, 1)

        self.hint = QLabel("say or type what to change — “make it purple”, “bigger”, "
                           "“add a sun”, “undo”")
        self.hint.setStyleSheet("color:#6b8ba3;font-size:11px;")
        lay.addWidget(self.hint)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("make it purple and bigger, add a sun")
        self.input.returnPressed.connect(self._submit)
        self.save_btn = QPushButton("Save PNG")
        self.save_btn.clicked.connect(self._save)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        row.addWidget(self.input, 1)
        row.addWidget(self.save_btn)
        row.addWidget(self.close_btn)
        lay.addLayout(row)

        self._apply_style()

    # ------------------------------------------------------------------ api
    # set by the main window: callable(instruction) -> str
    on_edit = None
    _path = ""
    _photo_path = ""

    def show_sketch(self, sketch) -> None:
        self._sketch = sketch
        self._refresh()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def show_photo(self, path: str, caption: str = "") -> None:
        """Show a REAL photograph in the same window.

        Same canvas, different content: `_sketch` is cleared so a follow-up
        "make it purple" cannot silently edit a photograph that was never a
        drawing — it answers "nothing is drawn yet", which is the truth.
        """
        pm = QPixmap(str(path))
        if pm.isNull():
            self.hint.setText(f"could not open {path}")
            return
        self._sketch = None
        self._photo_path = str(path)
        self.canvas.setPixmap(pm.scaled(self.canvas.size(),
                                        Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
        self.hint.setText(caption[:200] or f"photo · {path}")
        self.setWindowTitle("Arc Desk · photo")
        self.show()
        self.raise_()
        self.activateWindow()

    def _refresh(self) -> None:
        img = self._sketch.render(900, 640)
        pm = QPixmap.fromImage(img)
        self.canvas.setPixmap(pm.scaled(self.canvas.size(),
                                        Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if getattr(self, "_photo_path", "") and self._sketch is None:
            pm = QPixmap(self._photo_path)
            if not pm.isNull():
                self.canvas.setPixmap(pm.scaled(
                    self.canvas.size(), Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                return
        # `hasattr` was always true — __init__ sets `_sketch = None` — so the first
        # resize of an empty easel called `None.render(…)`. Qt swallows an exception
        # raised inside an override, so the window just looked broken (and left Qt with a
        # half-painted widget). A sketch is not optional here: draw one first.
        if self._sketch is not None:
            self._refresh()

    # -------------------------------------------------------------- actions
    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        if callable(self.on_edit):
            reply = self.on_edit(text)
            self.hint.setText(reply[:160])
        self._refresh()

    def _save(self) -> None:
        from .. import art
        self._path = art.save_sketch(self._sketch)
        self.hint.setText(f"saved · {self._path}")

    # ---------------------------------------------------------------- style
    def _apply_style(self) -> None:
        accent = getattr(self.theme, "accent", "#22d3ee")
        self.setStyleSheet(f"""
            QWidget {{ background:#070d16; color:#dbeafe;
                       font-family:'Segoe UI',Inter,sans-serif; font-size:13px; }}
            QLineEdit {{ background:#0d1a28; border:1px solid rgba(34,211,238,.3);
                         border-radius:8px; padding:8px 10px; color:#e6f3ff; }}
            QLineEdit:focus {{ border:1px solid {accent}; }}
            QPushButton {{ background:rgba(34,211,238,.14); border:1px solid rgba(34,211,238,.35);
                           border-radius:8px; padding:8px 14px; color:#a5f3fc; }}
            QPushButton:hover {{ background:rgba(34,211,238,.24); }}
            QLabel {{ background:transparent; }}
        """)
