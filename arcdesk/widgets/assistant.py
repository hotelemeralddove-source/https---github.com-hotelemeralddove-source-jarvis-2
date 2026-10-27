"""The JARVIS console — where you actually talk to the assistant.

A QTextBrowser transcript (one widget, not N message widgets: cheap and scrolls
well), a single-line input, a mic button and suggestion chips.
"""
from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

SUGGESTIONS = [
    ("SYSTEM REPORT", "system report"),
    ("OPEN NOTEPAD", "open notepad"),
    ("FOCUS MODE", "switch to focus mode"),
    ("TIMER 10 MIN", "timer 10 minutes"),
    ("SCREENSHOT", "take a screenshot"),
]


class AssistantConsole(QWidget):
    submitted = Signal(str)
    mic_requested = Signal()
    settings_requested = Signal()
    reset_requested = Signal()
    replay_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("console")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # ---- header ----------------------------------------------------
        head = QHBoxLayout()
        head.setSpacing(10)
        title = QLabel("JARVIS CONSOLE")
        title.setObjectName("consoleTitle")
        f = title.font()
        f.setPixelSize(10)
        f.setWeight(f.Weight.Bold)
        f.setLetterSpacing(f.SpacingType.AbsoluteSpacing, 2.6)
        title.setFont(f)
        head.addWidget(title)

        self.status = QLabel("booting…")
        self.status.setObjectName("consoleStatus")
        fs = self.status.font()
        fs.setPixelSize(9)
        fs.setLetterSpacing(fs.SpacingType.AbsoluteSpacing, 1.4)
        self.status.setFont(fs)
        head.addWidget(self.status)
        head.addStretch(1)

        for text, tip, slot in (
            ("C", "Clear conversation", self.reset_requested.emit),
            ("▶", "Replay last answer aloud", self.replay_requested.emit),
            ("*", "Assistant settings", self.settings_requested.emit),
        ):
            b = QPushButton(text)
            b.setObjectName("iconBtn")
            b.setFixedSize(26, 24)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            head.addWidget(b)
        lay.addLayout(head)

        # ---- what is happening RIGHT NOW ---------------------------------
        # The question this answers, in the user's words: "ena work nadakuthu nu
        # therinja nalla irukum" — and "task assign pana work aagutha nu theriya
        # matiku". So: the current step in words, and a seconds counter that keeps
        # moving. A clock that advances is the difference between "working" and
        # "wedged", and it costs one 150 ms timer.
        live = QHBoxLayout()
        live.setSpacing(8)
        self.dot = QLabel("●")
        self.dot.setObjectName("liveDot")
        self.dot.setFixedWidth(12)
        live.addWidget(self.dot)
        self.live = QLabel("idle — nothing running")
        self.live.setObjectName("liveLine")
        self.live.setWordWrap(False)
        live.addWidget(self.live, 1)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setFixedSize(58, 24)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setToolTip("Stop the current request (Esc also works)")
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        live.addWidget(self.stop_btn)
        lay.addLayout(live)

        # The step-by-step of the CURRENT request, kept in one line and updated in
        # place: "▸ tool: open_app  ✔ tool: system_report 1.2 s". The transcript keeps
        # the history; this answers "is it still going?" at a glance.
        self.proc = QLabel("")
        self.proc.setObjectName("procLine")
        self.proc.setWordWrap(True)
        lay.addWidget(self.proc)
        self._steps: list[str] = []

        # ---- transcript -------------------------------------------------
        self.view = QTextBrowser()
        self.view.setObjectName("transcript")
        self.view.setOpenExternalLinks(True)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setMinimumHeight(190)
        lay.addWidget(self.view, 1)
        self._last_arc = ""
        self._busy = False
        self._tick = QTimer(self)
        self._tick.setInterval(150)
        self._tick.timeout.connect(self.refresh_activity)

        # ---- suggestion chips -------------------------------------------
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for label, command in SUGGESTIONS:
            c = QPushButton(label)
            c.setObjectName("chip2")
            c.setCursor(Qt.CursorShape.PointingHandCursor)
            c.clicked.connect(lambda _=False, cmd=command: self._submit(cmd))
            chips.addWidget(c)
        chips.addStretch(1)
        lay.addLayout(chips)

        # ---- input ------------------------------------------------------
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName("chatInput")
        self.input.setPlaceholderText("Talk to JARVIS…  (e.g. open notepad, what's my cpu usage)")
        self.input.returnPressed.connect(lambda: self._submit(self.input.text()))
        row.addWidget(self.input, 1)

        self.mic = QPushButton("MIC")
        self.mic.setObjectName("micBtn")
        self.mic.setFixedSize(42, 34)
        self.mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic.setToolTip("Hold a conversation (Windows dictation)")
        self.mic.clicked.connect(self.mic_requested.emit)
        row.addWidget(self.mic)

        self.send = QPushButton("SEND")
        self.send.setObjectName("sendBtn")
        self.send.setFixedSize(64, 34)
        self.send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send.clicked.connect(lambda: self._submit(self.input.text()))
        row.addWidget(self.send)
        lay.addLayout(row)

    # -- api -------------------------------------------------------------
    def _submit(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.input.clear()
        self.submitted.emit(text)

    def focus_input(self) -> None:
        self.input.setFocus(Qt.FocusReason.ShortcutFocusReason)

    @property
    def last_answer(self) -> str:
        return self._last_arc

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self.send.setEnabled(not busy)
        self.send.setText("…" if busy else "SEND")
        self.stop_btn.setVisible(bool(busy))
        if busy:
            self.status.setText("WORKING")
            self._tick.start()
        else:
            self._tick.stop()
            self.status.setText("READY")
        self.refresh_activity()

    def refresh_activity(self) -> None:
        """Draw whatever the activity record says, including elapsed seconds."""
        from .. import activity as _activity
        snap = _activity.activity().snapshot()
        state = snap["state"]
        if state == "idle":
            self.live.setText("idle — nothing running")
            self.dot.setProperty("state", "idle")
        elif snap["busy"]:
            self.live.setText(f"{snap['live'] or state}   ·   {snap['elapsed']:.1f} s")
            self.dot.setProperty("state", state)
        else:
            self.live.setText(f"{state} in {snap['elapsed']:.1f} s")
            self.dot.setProperty("state", state)
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)

    def begin_task(self, text: str) -> None:
        """A new request: clear the process strip, keep the transcript."""
        self._steps = []
        self.proc.setText("")
        self.proc.setVisible(True)

    def step_running(self, label: str) -> None:
        self._steps.append("▸ " + label)
        self._render_steps()

    def step_done(self, label: str, seconds: float) -> None:
        # replace the running entry for this label with a finished one
        want = "▸ " + label
        mark = f"✔ {label} {seconds:.1f} s"
        for i in range(len(self._steps) - 1, -1, -1):
            if self._steps[i] == want:
                self._steps[i] = mark
                break
        else:
            self._steps.append(mark)
        self._render_steps()

    def _render_steps(self) -> None:
        tail = self._steps[-6:]
        self.proc.setText(("   ·   ".join(tail)) if tail else "")

    def add_step(self, text: str) -> None:
        """A finished step, kept in the transcript so the trail survives the request."""
        self.view.append(f'<div class="row step"><div class="meta">STEP</div>'
                         f'<div class="msg">{html.escape(text)}</div></div>')
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    # -- transcript ------------------------------------------------------
    def _bubble(self, who: str, text: str, cls: str) -> None:
        stamp = time.strftime("%H:%M")
        self.view.append(
            f'<div class="row {cls}"><div class="meta">{who} · {stamp}</div>'
            f'<div class="msg">{html.escape(text).replace(chr(10), "<br>")}</div></div>'
        )
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def add_user(self, text: str) -> None:
        self._bubble("YOU", text, "user")

    def add_arc(self, text: str) -> None:
        self._last_arc = text
        self._bubble("JARVIS", text, "arc")

    def add_tool(self, name: str, args: str, result: str) -> None:
        short = result if len(result) <= 150 else result[:150] + "…"
        self.view.append(
            f'<div class="row tool"><div class="meta">TOOL · {html.escape(name)} '
            f'{html.escape(args)[:80]}</div>'
            f'<div class="msg">{html.escape(short)}</div></div>'
        )
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def add_note(self, text: str) -> None:
        self.view.append(f'<div class="row note"><div class="msg">{html.escape(text)}</div></div>')
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_view(self) -> None:
        self.view.clear()

    def apply_doc_style(self, th) -> None:
        """Transcript bubbles are HTML, so they get their own stylesheet."""
        from PySide6.QtGui import QColor
        dim = QColor(th.dim).lighter(155).name()
        self.view.document().setDefaultStyleSheet(f"""
            .row {{ margin: 0 0 8px 0; }}
            .meta {{ font-size: 8.5px; letter-spacing: 1.3px; color: {dim}; }}
            .msg {{ font-size: 12.5px; line-height: 145%; margin-top: 2px; }}
            .user .msg {{ color: {th.text}; }}
            .user .meta {{ color: {dim}; }}
            .arc .msg {{ color: {th.accent}; }}
            .tool .msg {{ color: {dim}; font-size: 10.5px; }}
            .note .msg {{ color: {dim}; font-style: italic; font-size: 10.5px; }}
            .step .msg {{ color: {dim}; font-size: 10px; }}
            .step .meta {{ font-size: 8px; letter-spacing: 1.4px; color: {dim}; }}
        """)

    def styles(self, th) -> str:
        from PySide6.QtGui import QColor
        dim = QColor(th.dim).lighter(150).name()
        return f"""
            QWidget#console {{ background: transparent; }}
            QLabel#consoleTitle {{ color: {th.accent}; }}
            QLabel#consoleStatus {{ color: {dim}; }}
            QTextBrowser#transcript {{
                background: rgba(0,0,0,0.28);
                border: 1px solid rgba({QColor(th.accent).red()},{QColor(th.accent).green()},
                                        {QColor(th.accent).blue()},0.16);
                border-radius: 12px; padding: 8px; color: {th.text};
                font-size: 12px;
            }}
            QLineEdit#chatInput {{
                background: rgba({QColor(th.accent).red()},{QColor(th.accent).green()},
                                 {QColor(th.accent).blue()},0.08);
                border: 1px solid rgba({QColor(th.accent).red()},{QColor(th.accent).green()},
                                       {QColor(th.accent).blue()},0.30);
                border-radius: 10px; padding: 8px 12px; color: {th.text};
                selection-background-color: {th.accent};
            }}
            QLineEdit#chatInput:focus {{ border-color: {th.accent}; }}
            QPushButton#sendBtn {{ background: {th.accent}; color: #04090f;
                                   border: none; border-radius: 10px;
                                   font-size: 10px; font-weight: 700;
                                   letter-spacing: 1.4px; }}
            QPushButton#sendBtn:disabled {{ background: rgba({QColor(th.accent).red()},
                                            {QColor(th.accent).green()},
                                            {QColor(th.accent).blue()},0.30);
                                            color: {dim}; }}
            QPushButton#micBtn {{ background: transparent; color: {dim};
                                  border: 1px solid rgba({QColor(th.accent).red()},
                                  {QColor(th.accent).green()},{QColor(th.accent).blue()},0.30);
                                  border-radius: 10px; font-size: 9px; font-weight: 700; letter-spacing: 0.6px; }}
            QPushButton#micBtn:hover {{ color: {th.accent}; border-color: {th.accent}; }}
            QLabel#liveLine {{ color: {dim}; font-size: 10px; letter-spacing: 0.8px; }}
            QLabel#procLine {{ color: {dim}; font-size: 9.5px; letter-spacing: 0.4px; }}
            QLabel#liveDot {{ color: {dim}; font-size: 11px; }}
            QLabel#liveDot[state="thinking"] {{ color: {th.accent}; }}
            QLabel#liveDot[state="tool"] {{ color: {th.accent}; }}
            QLabel#liveDot[state="speaking"] {{ color: {th.accent}; }}
            QLabel#liveDot[state="done"] {{ color: #6ede8a; }}
            QLabel#liveDot[state="failed"] {{ color: #ef7a7a; }}
            QLabel#liveDot[state="cancelled"] {{ color: #efc86a; }}
            QPushButton#stopBtn {{ background: rgba(239,122,122,0.16); color: #ef9a9a;
                                   border: 1px solid rgba(239,122,122,0.45);
                                   border-radius: 8px; font-size: 9px;
                                   font-weight: 700; letter-spacing: 1.2px; }}
            QPushButton#stopBtn:hover {{ background: rgba(239,122,122,0.30); }}
            QPushButton#chip2 {{ background: rgba({QColor(th.accent).red()},
                                 {QColor(th.accent).green()},{QColor(th.accent).blue()},0.07);
                                 color: {dim}; border: 1px solid rgba({QColor(th.accent).red()},
                                 {QColor(th.accent).green()},{QColor(th.accent).blue()},0.20);
                                 border-radius: 9px; padding: 4px 9px;
                                 font-size: 8.5px; font-weight: 600; letter-spacing: 1.1px; }}
            QPushButton#chip2:hover {{ color: {th.accent}; border-color: {th.accent}; }}
            QPushButton#iconBtn {{ background: transparent; color: {dim}; border: none;
                                   border-radius: 7px; font-size: 12px; }}
            QPushButton#iconBtn:hover {{ color: {th.accent}; background: rgba(
                                        {QColor(th.accent).red()},{QColor(th.accent).green()},
                                        {QColor(th.accent).blue()},0.14); }}
        """
