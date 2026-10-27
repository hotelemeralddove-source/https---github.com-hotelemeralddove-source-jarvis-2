"""Get the ears ready — the one screen that fixes a silent "hey jarvis".

Opened from the setup card and from Settings → Voice. It shows the four things that have
to be true, ticks the ones that are, and downloads the two models (70 MB total) with the
lines visible. Afterwards it re-checks and says what is *still* missing; the app never
claims to be listening on the strength of a download it did not verify.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .. import ears


class _Worker(QThread):
    line = Signal(str)
    done = Signal(dict)

    def run(self) -> None:  # pragma: no cover - real downloads, exercised by the app
        self.done.emit(ears.fix(on_line=self.line.emit, cancel=self.cancel))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cancel = threading.Event()


class EarsDialog(QDialog):
    def closeEvent(self, event) -> None:                     # noqa: ANN001, N802
        # A QThread destroyed while still running is the 0xc0000374 abort, not a
        # warning: this dialog's worker downloads for minutes, and the crash report
        # contained exactly this dialog's worker. Stop it before the window goes.
        from . import qsafe
        qsafe.shut("_worker", self)
        super().closeEvent(event)

    def reject(self) -> None:
        from . import qsafe
        qsafe.shut("_worker", self)
        super().reject()

    def __init__(self, theme: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme or {}
        self.setWindowTitle("Microphone and wake word — what is missing")
        # sized by widgets/fit.py instead of a hard-coded minimum that can be
        # bigger than the screen
        self._worker: _Worker | None = None
        from .style import dialog_style
        if self.theme:
            self.setStyleSheet(dialog_style(self.theme))

        root = QVBoxLayout(self)
        title = QLabel("Can JARVIS hear you?")
        title.setObjectName("h1")
        root.addWidget(title)
        self.intro = QLabel("")
        self.intro.setObjectName("dim")
        self.intro.setWordWrap(True)
        root.addWidget(self.intro)

        self.rows = QLabel("")
        self.rows.setWordWrap(True)
        self.rows.setTextFormat(Qt.TextFormat.PlainText)   # no accidental markup
        root.addWidget(self.rows)

        row = QHBoxLayout()
        self.go = QPushButton("Download what is missing (70 MB)")
        self.go.clicked.connect(self._start)
        row.addWidget(self.go)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.stop_btn)
        again = QPushButton("Check again")
        again.clicked.connect(self.reload)
        row.addWidget(again)
        row.addStretch(1)
        root.addLayout(row)

        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setVisible(False)
        root.addWidget(self.bar)

        from .style import read_only_log
        self.log = read_only_log(QPlainTextEdit())
        root.addWidget(self.log, 1)

        self.verdict = QLabel("")
        self.verdict.setObjectName("verdict")
        self.verdict.setWordWrap(True)
        root.addWidget(self.verdict)

        self.reload()

    # ------------------------------------------------------------------ state
    def reload(self) -> None:
        st = ears.status()
        lines = []
        for key, v in st["rows"].items():
            tick = "✔" if v["ok"] else "✗"
            extra = f" — {v['found']}" if v["found"] and key in ("mic", "engine") else ""
            lines.append(f"  {tick}  {v['label']}{extra}")
        self.rows.setText("\n".join(lines))
        self.intro.setText(st["sentence"])
        size = sum(v["size_mb"] for k, v in st["rows"].items() if not v["ok"])
        if st["ready"]:
            self.go.setText("Re-download the models")
            self.verdict.setText("The ears work. Say \"hey jarvis\" — or use Settings → "
                                 "Voice → Test wake (no mic) to see it trigger.")
        else:
            self.go.setText(f"Download what is missing ({size} MB)")
            if not ears.pods() and (not st["rows"]["engine"]["ok"]
                                    or not st["rows"]["mic"]["ok"]):
                self.verdict.setText(
                    "This installed build does not contain the wake engine, and a compiled "
                    "app cannot add it later. The models can still be downloaded here; if "
                    "the engine line stays ✗, the ears need the source build (or the next "
                    "installer, which includes vosk).")
            else:
                self.verdict.setText("")
        self.go.setEnabled(self._worker is None)

    # ------------------------------------------------------------------ actions
    def _start(self) -> None:
        if self._worker is not None:
            return
        self.log.clear()
        self.bar.setVisible(True)
        self.go.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.verdict.setText("")
        # parentless on purpose: the registry in qsafe owns it, not the window. A
        # QThread parented to this dialog dies with it, and "dies while running" is
        # the abort in fault.log (0xc0000374, seen from open_ears).
        from . import qsafe
        w = _Worker()
        w.line.connect(self.log.appendPlainText)
        w.done.connect(self._finished)
        w.finished.connect(lambda w=w: qsafe.unregister(w))
        qsafe.register(w)
        self._worker = w
        w.start()
        from .fit import make_fit
        make_fit(self, preferred=(740, 640), keep_last=1,
                 minimum=(420, 300))

    def _stop(self) -> None:
        if self._worker is not None:
            self.log.appendPlainText("— stopping, as asked —")
            self._worker.cancel.set()
            self.stop_btn.setEnabled(False)

    def _finished(self, result: dict) -> None:
        from . import qsafe
        qsafe.unregister(self._worker)
        self._worker = None
        self.bar.setVisible(False)
        self.stop_btn.setEnabled(False)
        self.go.setEnabled(True)
        self.reload()          # first: the ticks are facts. The verdict is about the
                              # attempt, so it must not be overwritten by the refresh.
        if result.get("ok"):
            self.verdict.setText("Done — the ears are ready. Say \"hey jarvis\".")
        elif result.get("why") == "cancelled":
            self.verdict.setText("Stopped. Nothing half-downloaded is used; start again any "
                                 "time.")
        else:
            self.verdict.setText(f"Not ready: {result.get('why')}. The lines above say "
                                 f"which piece is missing — nothing will claim to listen "
                                 f"until it is there.")
