"""Add a brain — the download that replaces "no local model detected".

One screen, three honest lines: what is installed, what it costs, and one button that
does the whole job (packages → weights → start → point the app at it). The log scrolls
while it works, Stop stops, and nothing claims to be ready until the server actually
answers on 127.0.0.1.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .. import brain, identity


class _Worker(QThread):
    line = Signal(str)
    done = Signal(dict)

    def __init__(self, job: str, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.job = job
        self.key = key
        self.cancel = threading.Event()
        # NOTE: there used to be a `make_fit(self, …)` call here. `self` is a QThread, not
        # a dialog, so it raised AttributeError: '_Worker' object has no attribute
        # 'layout' on the GUI thread, before the thread ever started. Sizing belongs to
        # BrainDialog._install, which is where the window is actually being sized.

    def run(self) -> None:  # pragma: no cover - real downloads, exercised by the app
        say = self.line.emit
        try:
            if self.job == "install":
                a = brain.ensure_packages(say, self.cancel)
                if not a["ok"]:
                    self.done.emit({"ok": False, "why": a["why"] or "packages failed"})
                    return
                if self.cancel.is_set():
                    self.done.emit({"ok": False, "why": "cancelled"})
                    return
                b = brain.download(self.key, say, self.cancel)
                if not b["ok"]:
                    self.done.emit(b)
                    return
            c = brain.start_server(self.key, on_line=say)
            self.done.emit(c)
        except Exception as exc:                     # noqa: BLE001
            self.done.emit({"ok": False, "why": f"{type(exc).__name__}: {exc}"})


class BrainDialog(QDialog):
    def closeEvent(self, event) -> None:                     # noqa: ANN001, N802
        # same guarantee as EarsDialog: a running QThread must not be destroyed while it
        # runs, or the next allocation aborts the whole app (0xc0000374 in fault.log).
        from . import qsafe
        qsafe.shut("_worker", self)
        super().closeEvent(event)

    def reject(self) -> None:
        from . import qsafe
        qsafe.shut("_worker", self)
        super().reject()

    def __init__(self, cfg: dict, theme: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.theme = theme or {}
        self.setWindowTitle("Give it a brain — local, free, no account")
        # sized by widgets/fit.py instead of a hard-coded minimum that can be
        # bigger than the screen
        self._worker: _Worker | None = None
        from .style import dialog_style
        if self.theme:
            self.setStyleSheet(dialog_style(self.theme))

        root = QVBoxLayout(self)
        title = QLabel("No local model detected — that is what this fixes")
        title.setObjectName("h1")
        root.addWidget(title)
        intro = QLabel(
            "Lite answers instantly without any model, but it only understands commands. "
            "A brain lets JARVIS talk. It runs on this laptop, needs no account and costs "
            "nothing. One download, kept on disk, reversible.")
        intro.setObjectName("dim")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.sentence = QLabel("")
        self.sentence.setObjectName("dim")
        self.sentence.setWordWrap(True)
        root.addWidget(self.sentence)

        pick = QHBoxLayout()
        pick.addWidget(QLabel("Model:"))
        self.picker = QComboBox()
        for key, spec in brain.MODELS.items():
            self.picker.addItem(f"{spec['label']} · {spec['mb']} MB · "
                                f"{'can use the tools' if spec['tools'] else 'chat only'}",
                                key)
        self.picker.currentIndexChanged.connect(lambda _i: self._show())
        pick.addWidget(self.picker, 1)
        root.addLayout(pick)

        self.detail = QLabel("")
        self.detail.setObjectName("dim")
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)

        row = QHBoxLayout()
        self.go = QPushButton("Install and start")
        self.go.clicked.connect(self._install)
        row.addWidget(self.go)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.stop_btn)
        self.use_btn = QPushButton("Use the running one")
        self.use_btn.clicked.connect(self._use)
        row.addWidget(self.use_btn)
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
    def _key(self) -> str:
        return self.picker.currentData() or brain.DEFAULT_MODEL

    def reload(self) -> None:
        st = brain.status()
        self.sentence.setText(st["sentence"])
        self._show()
        self.use_btn.setEnabled(st["running"] or bool(st["others"]))
        self.go.setEnabled(self._worker is None)

    def _show(self) -> None:
        st = brain.status()
        spec = st["models"][self._key()]
        state = "already downloaded" if spec["present"] else f"{spec['mb']} MB to download"
        self.detail.setText(f"{spec['note']} {state}.")
        # what THIS model needs comes first: a running server that does not have the
        # selected file is no reason to hide the download size
        if not spec["present"]:
            self.go.setText(f"Install and start ({spec['mb']} MB)")
        elif st["running"]:
            self.go.setText("Restart it")
        else:
            self.go.setText("Start it")

    # ------------------------------------------------------------------ actions
    def _install(self) -> None:
        if self._worker is not None:
            return
        self.log.clear()
        self.bar.setVisible(True)
        self.go.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.verdict.setText("")
        # parentless on purpose: the qsafe registry owns it (see EarsDialog._start)
        from . import qsafe
        w = _Worker("install", self._key())
        w.line.connect(self.log.appendPlainText)
        w.done.connect(self._finished)
        w.finished.connect(lambda w=w: qsafe.unregister(w))
        qsafe.register(w)
        self._worker = w
        w.start()
        from .fit import make_fit
        make_fit(self, preferred=(800, 660), keep_last=1, minimum=(420, 300))

    def _stop(self) -> None:
        if self._worker is not None:
            self.log.appendPlainText("— stopping, as asked —")
            stop = getattr(self._worker, "stop", None)
            if callable(stop):
                stop()
            else:
                self._worker.cancel.set()
            self.stop_btn.setEnabled(False)


    def _use(self) -> None:
        """Point the app at this local model — after checking it is really answering.

        The check is a socket, so it runs on a worker: clicking "Use this one" used to be
        able to freeze the dialog for the connect timeout, which is the same complaint as
        the Settings spinner.
        """
        from .. import uiwork
        self.verdict.setText("checking whether it is answering…")

        def work(_cancel):
            return brain.running()

        def apply(up: bool) -> None:
            if up:
                brain.apply_config(self.cfg, self._key())
                self.verdict.setText("Done — the app will use the local brain from your "
                                     "next question. Lite is still there if it ever stops.")
            else:
                self.verdict.setText("Nothing is answering yet — press Install and start "
                                     "first, then this button.")
            self.reload()

        def failed(text: str) -> None:
            self.verdict.setText(f"could not check ({text}) — nothing was changed")

        uiwork.run(work, done=apply, failed=failed, name="arc-brain-running")

    def _finished(self, result: dict) -> None:
        from . import qsafe
        qsafe.unregister(self._worker)
        self._worker = None
        self.bar.setVisible(False)
        self.stop_btn.setEnabled(False)
        self.go.setEnabled(True)
        if result.get("ok"):
            brain.apply_config(self.cfg, self._key())
            self.verdict.setText(
                f"Done — {brain.MODELS[self._key()]['label']} is running on this laptop "
                f"and {identity.name(self.cfg)} will use it from your next question. "
                f"It stays inside Arc Desk's folder; nothing was installed system-wide.")
        elif result.get("why") == "cancelled":
            self.verdict.setText("Stopped. Nothing half-downloaded is used — start again "
                                 "any time.")
        else:
            self.verdict.setText(f"Not running: {result.get('why')}. The lines above say "
                                 f"what happened; Lite keeps working meanwhile.")
        self.reload()
