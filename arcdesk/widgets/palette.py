"""Ctrl+J — the command overlay: one line in, one answer out.

This is the "talk to it without talking" surface. It looks like a JARVIS input field
and behaves like a very small terminal:

  * you type a sentence, Enter sends it to the agent — the same agent the microphone
    talks to, so every one of the tools works here too;
  * the answer, any tool it used, and any error land in the transcript above the line;
  * **suggestions** under the input are generated from `tools.TOOLS` as you type
    (fuzzy, so "sysrep" finds `system_report`). Clicking one fills in a sentence
    template — the overlay never runs a tool you cannot see.

The widget owns no state beyond its transcript: the window glues it to the agent in
`_palette_reply` / `_palette_tool` / `_palette_error`.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QTextBrowser,
                               QVBoxLayout, QWidget)

MAX_LINES = 9

# Tools that need an argument get a sentence, not a broken call.
TEMPLATES = {
    "open_app": "open ",
    "open_url": "open ",
    "web_search": "search for ",
    "find_file": "find ",
    "find_files": "find ",
    "remind": "remind me in 20 minutes to ",
    "focus": "focus for 25 minutes",
    "briefing": "good morning",
    "type_text": "type ",
    "set_volume": "set volume 30",
}


def _score(text: str, query: str) -> int:
    """Fuzzy subsequence score — 0 means no match, higher is better."""
    text_l, query_l = text.lower(), (query or "").lower().strip()
    if not query_l:
        return 1
    if query_l in text_l:
        return 1000 - text_l.index(query_l) * 3 - (len(text_l) - len(query_l))
    pos, total, run = 0, 0, 0
    for ch in query_l:
        found = text_l.find(ch, pos)
        if found < 0:
            return 0
        run = run + 1 if found == pos else 0
        total += 10 + run * 6 - min(6, found - pos)
        pos = found + 1
    return max(1, total)


class CommandPalette(QWidget):
    """Frameless command overlay. `submitted(text)` is the only thing the app needs."""

    submitted = Signal(str)

    def __init__(self, theme, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._theme = theme
        self._lines: list[tuple[str, str]] = []
        self._busy = False
        self.setFixedWidth(700)
        self.setMinimumHeight(200)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame(self)
        frame.setObjectName("palFrame")
        outer.addWidget(frame)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(16, 12, 16, 14)
        inner.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.title = QLabel("JARVIS // COMMAND", frame)
        self.title.setObjectName("palTitle")
        self.brain = QLabel("", frame)
        self.brain.setObjectName("palBrain")
        self.brain.setAlignment(Qt.AlignmentFlag.AlignRight)
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.brain)
        inner.addLayout(head)

        self.log = QTextBrowser(frame)
        self.log.setObjectName("palLog")
        self.log.setOpenExternalLinks(False)
        self.log.setFixedHeight(120)
        self.log.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        inner.addWidget(self.log)

        self.hints = QLabel("", frame)
        self.hints.setObjectName("palHints")
        self.hints.setTextFormat(Qt.TextFormat.RichText)
        self.hints.setWordWrap(True)
        self.hints.linkActivated.connect(self._use_hint)
        inner.addWidget(self.hints)

        self.input = QLineEdit(frame)
        self.input.setObjectName("palInput")
        self.input.setPlaceholderText("Say it, or type it — “system report”, “open notepad”…")
        inner.addWidget(self.input)

        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPixelSize(13)
        for widget in (self.input, self.log, self.brain):
            widget.setFont(mono)
        self.input.textChanged.connect(self._refresh_hints)
        self.input.returnPressed.connect(self._submit)

        self.set_theme(theme)

    # -- appearance ------------------------------------------------------
    def set_theme(self, theme) -> None:
        self._theme = theme
        accent = getattr(theme, "accent", "#48f2ff")
        dim = getattr(theme, "dim", "#5f8f9c")
        self.setStyleSheet(f"""
            QFrame#palFrame {{ background: rgba(2, 12, 18, 248);
                               border: 1px solid {QColor(accent).lighter(110).name()}; }}
            QLabel#palTitle {{ color: {accent}; letter-spacing: 3px; font-size: 11px; }}
            QLabel#palBrain {{ color: {dim}; font-size: 11px; }}
            QLabel#palHints {{ color: {dim}; font-size: 11px; }}
            QTextBrowser#palLog {{ background: transparent; color: #cfeef7;
                                   border: none; font-size: 12.5px; }}
            QLineEdit#palInput {{ background: rgba(8, 30, 40, 255); color: #eafcff;
                                  border: 1px solid {dim}; padding: 9px 11px;
                                  font-size: 14px; }}
            QLineEdit#palInput:focus {{ border: 1px solid {accent}; }}
        """)
        self.update()

    def set_brain(self, label: str) -> None:
        self.brain.setText(label or "")

    # -- transcript ------------------------------------------------------
    def show_line(self, text: str, colour: str = "#cfeef7") -> None:
        for para in str(text).splitlines():
            if para.strip():
                self._lines.append((para.rstrip(), colour))
        self._lines = self._lines[-MAX_LINES:]
        self._render_log()

    def failed(self, text: str) -> None:
        self.show_line("! " + str(text), "#ff7b7b")
        self.done()

    def _render_log(self) -> None:
        html = []
        for line, colour in self._lines:
            safe = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            html.append(f'<div style="color:{colour};margin:2px 0">{safe}</div>')
        self.log.setHtml("".join(html))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def done(self) -> None:
        self._busy = False
        self.input.setEnabled(True)
        self.input.setPlaceholderText(
            "Say it, or type it — “system report”, “open notepad”…")
        self.input.setFocus()

    # -- suggestions -----------------------------------------------------
    def _refresh_hints(self, text: str) -> None:
        query = (text or "").strip()
        if len(query) < 2:
            self.hints.setText("")
            return
        try:
            from ..ai import tools
            rows = sorted(tools.TOOLS.items(),
                          key=lambda kv: -_score(kv[0] + " " + kv[1].description, query))
            picks = [(name, tool) for name, tool in rows
                     if _score(name + " " + tool.description, query) > 0][:4]
        except Exception:
            picks = []
        if not picks:
            self.hints.setText("")
            return
        chips = []
        for name, tool in picks:
            phrase = TEMPLATES.get(name, name if not tool.required else name + " ")
            chips.append(f'<a href="{phrase}" style="color:#48f2ff;text-decoration:none">'
                         f'{name}</a>')
        self.hints.setText("try:  " + "   ·   ".join(chips))

    def _use_hint(self, link: str) -> None:
        self.input.setText(link)
        self.input.setFocus()
        self.input.setCursorPosition(len(link))

    # -- behaviour -------------------------------------------------------
    def popup(self) -> None:
        screen = self.screen() or self.parent().screen() if self.parent() else self.screen()
        geo = screen.availableGeometry()
        self.adjustSize()
        self.move(geo.center().x() - self.width() // 2,
                  geo.top() + int(geo.height() * 0.20))
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.input.selectAll()

    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text or self._busy:
            return
        self.show_line("› " + text, "#eafcff")
        self.input.clear()
        self._busy = True
        self.input.setEnabled(False)
        self.input.setPlaceholderText("thinking…")
        self.submitted.emit(text)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)
