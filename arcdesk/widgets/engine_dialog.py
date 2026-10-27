"""Get the reply-voice engine — in the app, one click, no command prompt.

The point of this screen: a cloned voice is not a preference, it is a 1.5 GB model. So the
person gets one button per engine, the size written on the button, live output while it
downloads, a Stop button that actually stops, and a result line that is either "ready" or
the real reason it is not. No "installing…" that never ends, and no success message that
the app cannot back up.
"""
from __future__ import annotations

import os
import threading

import time

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from .. import engines


def _mb_per_second(speed: str | None) -> float | None:
    """'3.1 MB/s' -> 3.1, so the estimate comes from this download, not from a guess."""
    if not speed:
        return None
    try:
        amount, unit = speed.replace("/s", "").split()
        scale = {"B": 1e-6, "KB": 1e-3, "MB": 1.0, "GB": 1000.0}.get(unit.upper())
        return float(amount) * scale if scale else None
    except Exception:                                            # noqa: BLE001
        return None


#: Every download thread that is still running. A QThread destroyed while it runs is not an
#: error message — it is `QThread: Destroyed while thread is still running` followed by the
#: process going away, which is exactly the "application crash aagi close aaguthu" report.
#: Parented to the DIALOG, a worker died with the window (close it, or let Settings be
#: destroyed, and Qt killed a live thread). These are parentless and held here instead.
_LIVE_WORKERS: set["_Worker"] = set()


def stop_all_workers(wait_ms: int = 8000) -> int:
    """Stop every running download thread — called when the app quits. Returns how many."""
    stopped = 0
    for worker in list(_LIVE_WORKERS):
        try:
            worker.stop()
            if not worker.wait(wait_ms):
                worker.terminate()          # last resort: a stuck thread must not abort us
                worker.wait(1500)
            stopped += 1
        except Exception:                                        # noqa: BLE001
            pass
        finally:
            _LIVE_WORKERS.discard(worker)
    return stopped


class _Worker(QThread):
    line = Signal(str)
    progress = Signal(dict)
    done = Signal(dict)
    # a gated model needs one thing before a byte can move, and asking for it *during*
    # the run is the whole difference between "download aaga matiku" and a download.
    need_token = Signal(str, str)          # engine, licence url

    def __init__(self, engine: str, parent: QWidget | None = None, lang: str = "",
                 missing_only: bool = False) -> None:
        super().__init__(parent)
        self.engine = engine
        self.lang = lang
        # True = the engine's packages are already on this PC and only the weights /
        # voice files are absent. Downloading the whole thing again would be a second
        # copy of torch next to the one the person built themselves.
        self.missing_only = missing_only
        self.cancel = threading.Event()
        self._answer: str | None = None
        self._answered = threading.Event()
        # NOTE: there used to be a `make_fit(self, …)` call here. `self` is a QThread, not
        # a dialog, so it raised AttributeError: '_Worker' object has no attribute
        # 'layout' — on the GUI thread, inside the button's slot, AFTER the bar had been
        # shown and Stop enabled but BEFORE the thread started. The download therefore
        # never began, and the screen sat at 0 % for ever (26.png). Sizing belongs to the
        # dialog and is done in EngineDialog.__init__.

    def _ask(self, engine: str, url: str) -> str | None:
        """Called on this thread; the dialog answers from the GUI thread."""
        self.need_token.emit(engine, url)
        if not self._answered.wait(300):
            return None
        return self._answer

    def answer(self, value: str | None) -> None:
        self._answer = value
        self._answered.set()

    def run(self) -> None:  # pragma: no cover - real process, exercised by the app
        try:
            self._work()
        except Exception as exc:                                 # noqa: BLE001
            # Without this, a raise inside the thread means `done` is never emitted: the
            # bar sits at whatever it reached, Stop does nothing (there is nothing to
            # cancel), and the screen is stuck for ever. "Hang aagi nikkithu" again.
            self.done.emit({"ok": False, "engine": self.engine,
                            "why": f"{type(exc).__name__}: {exc}", "lines": []})

    def _work(self) -> None:
        if self.missing_only:
            result = engines.missing_only(self.engine, on_line=self.line.emit,
                                          on_progress=self.progress.emit,
                                          cancel=self.cancel)
            if result.get("needs_token") and not self.cancel.is_set():
                # gated weights: ask for the token inside this same run, like `auto` does
                answer = self._ask(self.engine, str(result.get("url") or ""))
                if answer:
                    engines.set_token(answer)
                    result = engines.missing_only(self.engine, on_line=self.line.emit,
                                                  on_progress=self.progress.emit,
                                                  cancel=self.cancel)
        else:
            result = engines.auto(self.engine, lang=self.lang, on_line=self.line.emit,
                                  cancel=self.cancel, on_progress=self.progress.emit,
                                  ask_token=self._ask)
        self.done.emit(result)

    def stop(self) -> None:
        self.cancel.set()
        self._answered.set()      # never leave a gated run waiting for an answer


class EngineDialog(QDialog):
    """Two engines, their real sizes, their real state, and one button each."""

    def __init__(self, theme: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme or {}
        self.setWindowTitle("Voice engines — what makes a clone sound real")
        # sized by widgets/fit.py instead of a hard-coded minimum that can be
        # bigger than the screen
        self._worker: _Worker | None = None
        from .style import dialog_style
        if self.theme:
            self.setStyleSheet(dialog_style(self.theme))

        root = QVBoxLayout(self)
        title = QLabel("A cloned voice needs a neural engine")
        title.setObjectName("h1")
        root.addWidget(title)
        intro = QLabel(
            "Without one, JARVIS answers in the system voice — and says so. With one, it "
            "speaks in the voice you picked, in that person's own sound.\n"
            "Downloaded once, kept on this computer. Nothing is installed behind your back.")
        intro.setObjectName("dim")
        intro.setWordWrap(True)
        root.addWidget(intro)

        # The honest ordering, on screen: small first, big last, and what to do if the
        # big one will not come down.
        self.hint = QLabel(
            "Easiest: <b>Piper</b> — about 60 MB, no torch, no GPU, ready in a minute.\n"
            "IndicF5 / XTTS-v2 are 1.5–1.9 GB of neural weights: better, much bigger, and "
            "they need a patient connection. If a big download will not finish, Piper "
            "already sounds like a person; the Windows voice needs no download at all.")
        self.hint.setObjectName("dim")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        # A gated model (IndicF5) cannot be downloaded without this, and asking the
        # person to go and set an environment variable would be the dead end this whole
        # screen exists to remove.
        token_row = QHBoxLayout()
        token_label = QLabel("Hugging Face token")
        token_label.setObjectName("dim")
        token_row.addWidget(token_label)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("only for gated models (IndicF5) — paste, then Save")
        token_row.addWidget(self.token, 1)
        self.save_token = QPushButton("Save")
        self.save_token.setToolTip("Remembered in this app's settings, never shown again")
        self.save_token.clicked.connect(self._save_token)
        token_row.addWidget(self.save_token)
        root.addLayout(token_row)
        self.token_hint = QLabel("")
        self.token_hint.setObjectName("dim")
        self.token_hint.setWordWrap(True)
        root.addWidget(self.token_hint)
        self._show_token_state()

        self.picker = QComboBox()
        self.picker.currentIndexChanged.connect(lambda _i: self._show())
        root.addWidget(self.picker)

        self.state = QLabel("")
        self.state.setObjectName("dim")
        self.state.setWordWrap(True)
        root.addWidget(self.state)

        # One button for the person who does not want to choose. It picks the engine the
        # language needs, and it is the button that never dead-ends on a gated model.
        auto_row = QHBoxLayout()
        auto_label = QLabel("Reply voice language")
        auto_label.setObjectName("dim")
        auto_row.addWidget(auto_label)
        self.lang = QComboBox()
        for code, text in (("ta", "Tamil"), ("hi", "Hindi"), ("en", "English")):
            self.lang.addItem(text, code)
        auto_row.addWidget(self.lang)
        self.auto_btn = QPushButton("Download it for me — automatic")
        self.auto_btn.setToolTip("Picks the engine this language needs, downloads it with a "
                                 "real progress bar, and stops only if it truly cannot")
        self.auto_btn.clicked.connect(self._start_auto)
        auto_row.addWidget(self.auto_btn, 1)
        root.addLayout(auto_row)

        row = QHBoxLayout()
        self.go = QPushButton("Install now")
        self.go.clicked.connect(self._start)
        row.addWidget(self.go)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        row.addWidget(self.stop_btn)
        self.check = QPushButton("Check again")
        self.check.clicked.connect(lambda *_a: self.reload())
        row.addWidget(self.check)
        # "I installed it in a terminal but JARVIS asks again": re-scan every python on
        # this PC and adopt the one that already has the packages.
        self.scan = QPushButton("Find what I installed")
        self.scan.setToolTip("Look for a python on this PC that already has the engine — "
                             "if one does, JARVIS uses it instead of downloading again")
        self.scan.clicked.connect(self._scan)
        row.addWidget(self.scan)
        row.addStretch(1)
        root.addLayout(row)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        self.bar.setVisible(False)
        root.addWidget(self.bar)

        # A download is 1.5 GB. "installing…" with a bar that never moves is
        # indistinguishable from a crash, so this line always says something measurable:
        # megabytes so far, the speed, the estimate — or, when the child goes quiet, at
        # least how long it has been working, which proves the app is not stuck.
        self.live = QLabel("")
        self.live.setObjectName("dim")
        self.live.setWordWrap(True)
        self.live.setVisible(False)
        root.addWidget(self.live)

        from .style import read_only_log
        self.log = read_only_log(QPlainTextEdit())
        root.addWidget(self.log, 1)

        self.verdict = QLabel("")
        self.verdict.setObjectName("verdict")
        self.verdict.setWordWrap(True)
        root.addWidget(self.verdict)

        self._ticker = QTimer(self)
        self._ticker.setInterval(500)
        self._ticker.timeout.connect(self._beat)
        self._started = 0.0
        self._last_line_at = 0.0
        self._last_stage = ""
        self._seen: dict = {}
        self._items: dict[str, dict] = {}
        self._verdict_for = ""          # which engine the verdict below is about
        self._awaiting_token = None     # set while a gated download waits for a paste
        self._method: dict = {}
        self._seq = 0
        self._weights_only = False
        # A background probe ("which python already has this?") takes a second or two.
        # The dialog used to read the cache once, paint "not installed", and never look
        # again — so an engine installed in a terminal stayed invisible until the person
        # pressed a button. This re-reads the cheap cached answer and repaints by itself.
        self._helper_engine = ""
        self._helper_label = ""
        self._helper_shown: list[str] = []
        self._seen_version = engines.foreign_version()
        self._shown_signature = ""
        self._auto_left = 4              # repaints caused by a late probe, capped
        self._watch = QTimer(self)
        self._watch.setInterval(1500)
        self._watch.timeout.connect(self._watch_for_found)
        self._watch.start()
        self.reload()

    # ------------------------------------------------------------------ token
    def _show_token_state(self) -> None:
        have = bool(engines.token())
        self.token.setPlaceholderText(
            "token saved — paste a new one to replace it" if have
            else "only for gated models (IndicF5) — paste, then Save")
        if have:
            self.token_hint.setText("A token is saved. gated models (IndicF5) can be "
                                    "downloaded with it.")
        else:
            self.token_hint.setText(
                "IndicF5 is a <b>gated</b> model: Hugging Face refuses it (401) until you "
                "accept its licence once. Everyone else — Piper, XTTS-v2, the Windows "
                "voice — needs no token at all.")

    def _save_token(self) -> None:
        value = self.token.text().strip()
        engines.set_token(value)
        self.token.clear()
        self._show_token_state()
        waiting = self._worker is not None and self._awaiting_token is not None
        if waiting:
            # The download is paused, not dead: hand the token to the thread that asked
            # and it carries on in the same run. No "press Install again".
            self._awaiting_token = None
            self._worker.answer(value)                       # type: ignore[union-attr]
            self.verdict.setText("Token saved — the download is continuing by itself.")
        self.reload()

    # ------------------------------------------------------------------ state
    def reload(self, done_after=None) -> None:
        """Refresh the list **without** stopping the window.

        This used to be, in one synchronous block on the drawing thread:

            clone.refresh()            # forget every cached answer
            engines.status()           # -> clone.engines() -> find_engine_python()
                                       #    -> a child python per interpreter, 20 s cap

        Opening the dialog therefore froze the whole app while it asked every python on
        the PC what it had (the report: "front la vanthu stuck aagi nikithu", 20.png).
        Now the probe runs on a worker and comes back through a Signal; the dialog paints,
        scrolls, and Esc works while it happens. `self._seq` throws away an answer that
        arrives after a newer request.
        """
        from .. import clone, uiwork
        clone.refresh()
        self._seq = getattr(self, "_seq", 0) + 1
        seq = self._seq
        self.state.setText("checking what is installed…  (the window stays usable)")
        self.go.setEnabled(False)

        def work(_cancel):
            return engines.status(), engines.method()

        def apply(pair):
            if seq != self._seq:                      # a newer reload owns the screen
                return
            items, method = pair
            self._items = items
            self._method = method
            self._shown_signature = "|".join(
                f"{key}:{int(bool(v.get('ready')))}:{int(bool(v.get('code')))}"
                for key, v in sorted(items.items()))
            self._fill_picker()
            self._show()
            # `Check again` is a QPushButton: `clicked` emits a bool, so connecting it
            # straight to reload() passed `done_after=False` and this line raised
            #     TypeError: 'bool' object is not callable
            # twice on every refresh of the engine list (see the crash report). A callback
            # is only a callback when it can be called.
            if callable(done_after):
                done_after()

        def failed(text: str) -> None:
            if seq != self._seq:
                return
            self.state.setText(f"could not read the engine state ({text}) — the list below "
                               f"is the last thing that was known. Esc still closes this.")

        uiwork.run(work, done=apply, failed=failed, name="arc-engine-status")

    def _fill_picker(self) -> None:
        keep = self.picker.currentData()
        self.picker.blockSignals(True)
        self.picker.clear()
        # smallest first: the answer to "the download is not going well" should be the
        # first thing in the list, not the last.
        ordered = sorted(self._items.items(), key=lambda kv: kv[1]["size_mb"])
        for key, v in ordered:
            if v["ready"]:
                mark = "✔ ready"
            elif v["size_mb"] <= 200:
                mark = f"easiest · {v['size_mb']} MB"
            else:
                mark = f"missing · {v['size_mb']} MB"
            self.picker.addItem(f"{v['label']} — {v['langs']} — {mark}", key)
        self.picker.blockSignals(False)
        if keep:
            i = self.picker.findData(keep)
            if i >= 0:
                self.picker.setCurrentIndex(i)

    def _scan(self) -> None:
        """Ask every python on this machine what it has, and use a good answer.

        The heavy part is two child processes per interpreter, so it belongs on a worker.
        The dialog says what it is doing the whole time, and can be closed while it runs.
        """
        from .. import clone, uiwork
        self.log.setPlainText("looking for an engine that is already installed…\n"
                              "this asks every python on this PC what it has, and can take "
                              "a while on a slow disk. The window stays usable.\n")
        self.scan.setEnabled(False)
        self.scan.setText("Looking…")
        self.verdict.setText("")

        def work(cancel):
            text = engines.diagnosis_text()
            # piper is the small one, and the one that used to close the app on import —
            # so its report says plainly which interpreter will run it
            from .. import piper_engine
            text += "\n\n" + piper_engine.diagnose()
            clone.refresh()
            return text, engines.status()

        def apply(result):
            text, items = result
            self._items = items
            self._fill_picker()
            self.log.appendPlainText(text)
            self.scan.setEnabled(True)
            self.scan.setText("Find what I installed")
            ready = [v["label"] for v in items.values() if v["ready"]]
            if ready:
                self.verdict.setText(
                    "Found it — " + ", ".join(ready) + ". Nothing needs downloading: JARVIS "
                    "will speak through the python that already has it. Press 'Hear it' on "
                    "the Voice page to check.")
            else:
                half = [f"{val['label']} ({val['python']})" for val in items.values()
                        if val.get("code") and val.get("python")]
                if half:
                    self.verdict.setText(
                        "Found the engine, not everything it needs: " + ", ".join(half) +
                        ". Press the green button — it downloads ONLY the missing part, "
                        "it does not reinstall what you already did.")
                    self._show()
                    return
                self.verdict.setText(
                    "No python on this PC has the engine's packages yet. The list above "
                    "shows every interpreter that was checked and what each one has — if "
                    "your install went into one that is not listed, tell it to this app's "
                    "own python: .venv\\Scripts\\python.exe -m pip install torch "
                    "transformers")
            self._show()

        def failed(text: str) -> None:
            self.scan.setEnabled(True)
            self.scan.setText("Find what I installed")
            self.verdict.setText(f"the search did not finish ({text}). Nothing was changed "
                                 f"— press it again, or use 'Check again'.")

        uiwork.run(work, done=apply, failed=failed, name="arc-engine-scan")

    def _current(self) -> dict:
        return self._items.get(self.picker.currentData() or "", {})

    def _where(self, engine: str) -> str:
        """Which interpreter is doing the work, when it is not this process."""
        try:
            from .. import clone
            info = clone.engines().get(engine, {})
        except Exception:                                        # noqa: BLE001
            return ""
        if info.get("foreign"):
            return f"the python you already installed it into — {info['foreign']}"
        if info.get("code"):
            return "the packages are here; the weights are not (yet)"
        if info.get("sidecar"):
            return f"the app's private engine folder — {info.get('model', '')}"
        return ""

    def _show(self) -> None:
        v = self._current()
        if not v:
            return
        m = self._method or {"can_install": True, "why": ""}
        self._weights_only = False
        if v["ready"]:
            where = self._where(v["id"])
            self.state.setText(f"<b>{v['label']} is ready.</b> {v['why'].rstrip('.')} — "
                               f"replies in {v['langs']} use the voice you picked."
                               + (f"<br><span style='opacity:0.7'>using: {where}</span>"
                                  if where else ""))
            self.go.setText("Reinstall / repair")
        elif v.get("code"):
            # The half-installed state that used to be reported as "not installed" and
            # sent the person back round the same loop: the packages ARE here, only the
            # weights (or the piper voice files) are not.
            self._weights_only = True
            where = f"<br><span style='opacity:0.7'>engine found: {v['python']}</span>" \
                if v.get("python") else ""
            if v["id"] == "piper":
                self.state.setText(
                    "<b>The piper engine is installed — its voice files are not.</b> "
                    "Piper needs one .onnx voice per language (~60 MB each) to say "
                    "anything." + where)
                self.go.setText("Download the voices only (~60 MB)")
            else:
                self.state.setText(
                    f"<b>{v['label']} engine found — {v['problem'].rstrip('.')}.</b> "
                    f"Only that part is downloaded; the packages you installed are left "
                    f"exactly as they are." + where)
                self.go.setText(f"Download only the missing part "
                                f"({v['size_mb'] / 1000:.1f} GB)")
        else:
            self.state.setText(
                f"<b>{v['label']} is not installed.</b> It is the engine for "
                f"{v['langs']} — {v['why'].rstrip('.')}. About "
                f"{v['size_mb'] / 1000:.1f} GB, once. {v['needs'].rstrip('.')}.")
            self.go.setText(f"Install {v['label']} ({v['size_mb'] / 1000:.1f} GB)")
        self.go.setEnabled(m["can_install"] and self._worker is None)
        # the automatic button has the same limit as the manual one: a frozen build with
        # no pip cannot install anything, and pretending otherwise is the kind of lie
        # that ends with someone watching a progress bar that will never move.
        self.auto_btn.setEnabled(m.get("can_install", True) and self._worker is None)
        if not m["can_install"]:
            self.verdict.setText(
                "This build cannot add packages by itself: " + m["why"] +
                ". Double-click install_clone.bat in the app folder — it prints its own "
                "progress and takes one word from you (y / n).")
        elif self._verdict_for != v["id"]:
            self.verdict.setText("")   # a verdict about XTTS must not sit under IndicF5

    # ------------------------------------------------------------------ watching
    def _signature(self) -> str:
        """What the screen would say right now, from cached answers only."""
        try:
            from .. import clone
            have = clone.engines()
        except Exception:                                        # noqa: BLE001
            return ""
        return "|".join(f"{key}:{int(bool(v.get('available')))}:{int(bool(v.get('code')))}"
                        for key, v in sorted(have.items()))

    def _watch_for_found(self) -> None:
        """Repaint when a background probe answers something new. Cheap: cached reads only.

        The old screen read the answer once, before it existed, and then never again — so
        an engine installed in a terminal stayed "not installed" until a button was
        pressed. This watches for that answer, and repaints only when it actually CHANGES
        what the screen would say. A probe that answers "still nothing" must not rebuild
        the screen (that would also fight a person who is mid-click).
        """
        if self._worker is not None or self._awaiting_token is not None:
            return
        if self._auto_left <= 0:
            return
        try:
            version = engines.foreign_version()
        except Exception:                                        # noqa: BLE001
            return
        if version == self._seen_version:
            return
        self._seen_version = version
        if self._signature() == self._shown_signature:
            return
        self._auto_left -= 1
        from .. import clone
        clone.refresh()                  # the probe answer changes what "ready" means
        self.reload()

    # ------------------------------------------------------------------ actions
    def _start_auto(self) -> None:
        """One click: the engine this language needs, downloaded without a decision."""
        if self._worker is not None:
            return
        lang = self.lang.currentData() or "ta"
        engine = engines.pick(lang)
        # "automatic" must not reinstall what is already installed: if the packages are
        # here and only the weights are not, it finishes that install instead.
        have = self._items.get(engine, {})
        self._weights_only = bool(have.get("code")) and not have.get("ready")
        self._begin(engine, engines.SPECS[engine], lang)

    def _start(self) -> None:
        v = self._current()
        if not v or self._worker is not None:
            return
        self._begin(v["id"], v, "")

    def _begin(self, engine: str, v: dict, lang: str) -> None:
        self._awaiting_token = None
        missing_only = bool(self._weights_only)
        # A download belongs to its own process, not to this window: if the window stops
        # answering, or the person closes it, 1.5 GB that is already half-way must not be
        # thrown away. See arcdesk/engine_helper.py.
        from .. import engine_helper
        if not os.environ.get("ARCDESK_NO_HELPER") and engine_helper.available()[0]:
            if self._begin_helper(engine, v, lang, missing_only):
                return
        self.auto_btn.setEnabled(False)
        self.log.clear()
        self.log.appendPlainText(
            (f"finishing {v['label']}: only the missing part, about {v['size_mb']} MB…"
             if missing_only else
             f"installing {v['label']} · about {v['size_mb']} MB…"))
        self.bar.setVisible(True)
        self.live.setVisible(True)
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        self._started = time.monotonic()
        self._last_line_at = self._started
        self._last_stage = ""
        self._seen = {}
        self.live.setText(f"starting · about {v['size_mb']} MB to download · 0 s")
        self._ticker.start()
        self.go.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.verdict.setText("")
        # SPECS entries have no "id" key — only the status rows do. The automatic button
        # passes a SPECS entry, so `v["id"]` raised KeyError there: press "Download it for
        # me", nothing happens, and the window looks hung. The engine name is the id.
        self._verdict_for = str(v.get("id") or engine)
        try:
            # parentless on purpose: the registry owns it, not the window (see _LIVE_WORKERS)
            w = _Worker(engine, None, lang=lang, missing_only=missing_only)
            w.line.connect(self._on_line)
            w.progress.connect(self._on_progress)
            w.done.connect(self._finished)
            w.need_token.connect(self._on_need_token)
            self._worker = w
            _LIVE_WORKERS.add(w)
            w.finished.connect(lambda w=w: _LIVE_WORKERS.discard(w))
            w.start()
        except Exception as exc:                                 # noqa: BLE001
            # A start that fails must say so on this screen instead of leaving a 0 % bar
            # and a Stop button that stops nothing — that state is indistinguishable from
            # a frozen program, and it is exactly what 26.png shows.
            self._worker = None
            self._ticker.stop()
            self.bar.setVisible(False)
            self.live.setVisible(False)
            self.stop_btn.setEnabled(False)
            self.go.setEnabled(True)
            self.auto_btn.setEnabled(True)
            self.verdict.setText(
                f"the download could not even start ({type(exc).__name__}: {exc}). "
                f"Nothing was changed. Press the button again, or use "
                f"install_clone.bat in the app folder — it does the same thing in a "
                f"window that shows every line.")
            self.log.appendPlainText(f"could not start: {type(exc).__name__}: {exc}")
            return

    # ------------------------------------------------------- the background helper
    def _begin_helper(self, engine: str, v: dict, lang: str, missing_only: bool) -> bool:
        """Start the download in its own process and follow it by reading a small file."""
        from .. import engine_helper
        got = engine_helper.start(engine, lang="" if missing_only else lang)
        if not got.get("ok"):
            self.log.appendPlainText(f"could not start the background download: "
                                     f"{got.get('why')}")
            return False
        self.log.clear()
        self.log.appendPlainText(
            f"{v['label']}: downloading in the background (pid {got.get('pid')}). "
            f"This keeps going even if you close this window.")
        self.bar.setVisible(True)
        self.bar.setValue(0)
        self.live.setVisible(True)
        self.live.setText("starting · the download runs in its own process · 0 s")
        self._started = time.monotonic()
        self._last_line_at = self._started
        self._last_stage = ""
        self._helper_engine = engine
        self._helper_label = str(v.get("label") or engine)
        self._helper_shown = []
        self.go.setEnabled(False)
        self.auto_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.verdict.setText("")
        self._verdict_for = str(v.get("id") or engine)
        self._ticker.start()          # polls the helper as well as painting the clock
        return True

    def _poll_helper(self) -> bool:
        """False when nothing is being followed in the background."""
        engine = getattr(self, "_helper_engine", "")
        if not engine:
            return False
        from .. import engine_helper
        data = engine_helper.read(engine)
        if not data:
            return True
        percent = float(data.get("percent") or 0)
        self.bar.setValue(int(max(0.0, min(100.0, percent))))
        bits = []
        if data.get("mb"):
            total = data.get("total_mb") or 0
            bits.append(f"{float(data['mb']):,.0f} MB" +
                        (f" of {float(total):,.0f} MB" if total else ""))
        if data.get("speed"):
            bits.append(str(data["speed"]))
        if data.get("eta"):
            bits.append(f"{data['eta']} left")
        stage = str(data.get("stage") or "working")
        quiet = time.monotonic() - self._last_line_at
        self.live.setText(" · ".join([stage] + bits) + f" · {int(quiet)} s")
        lines = [str(x) for x in (data.get("lines") or [])]
        for line in lines[len(getattr(self, "_helper_shown", [])):]:
            self.log.appendPlainText(str(line))
            self._last_line_at = time.monotonic()
        self._helper_shown = lines
        if data.get("done") or not engine_helper.running(engine):
            self._helper_engine = ""
            self._finish_helper(data, engine)
        return True

    def _finish_helper(self, data: dict, engine: str) -> None:
        """The helper wrote its last word: report it, then re-read the real state."""
        from .. import engine_helper, clone
        self._ticker.stop()
        self.live.setVisible(False)
        self.bar.setVisible(False)
        self.stop_btn.setEnabled(False)
        self.go.setEnabled(True)
        self.auto_btn.setEnabled(True)
        try:
            engine_helper.cancel_path(engine).unlink()
        except Exception:                                        # noqa: BLE001
            pass
        clone.refresh()
        label = getattr(self, "_helper_label", engine)
        if data.get("ok"):
            self.verdict.setText(f"Done — {label} is installed and ready. Replies in that "
                                 f"language now use the voice you chose.")
        elif data.get("why") == "cancelled":
            self.verdict.setText("Stopped. What already arrived is kept — pressing the "
                                 "button again continues from there.")
        else:
            why = data.get("why") or "it did not finish"
            self.verdict.setText(
                f"Not installed ({why}). The download ran in its own process the whole "
                f"time, so nothing you had already fetched was lost — press the button "
                f"again to continue.")
        self.reload()

    # -------------------------------------------------------------- live numbers
    def _on_line(self, text: str) -> None:
        self._last_line_at = time.monotonic()
        if text and not text.startswith(("  ", "\t")):
            self._last_stage = text.strip()[:120]
        self.log.appendPlainText(text)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
        self._beat()

    def _on_progress(self, reading: dict) -> None:
        """A real reading from pip or huggingface: percent, megabytes, speed, estimate."""
        self._seen.update({k: v for k, v in reading.items() if k != "line"})
        self._paint_live()

    def _beat(self) -> None:
        """Ticks every half second, so silence still shows a moving clock."""
        if self._poll_helper():
            return
        if self._worker is None:
            return
        self._paint_live()
        # "yethavathu task click pana … appadiyae hang aagi nikkithu" is a report about
        # SILENCE, not about speed: a stage with no output looks identical to a dead app.
        # After 25 quiet seconds the line says which stage it is on, that the window still
        # answers, and that Stop works.
        quiet = time.monotonic() - max(self._last_line_at, self._started)
        if quiet > 25 and self.verdict.text() == "":
            stage = self._last_stage or "the download"
            self.verdict.setText(
                f"still working — {stage} · {int(quiet)} s with nothing new printed. The "
                f"window is answering: Stop cancels, Esc closes this and JARVIS stays as "
                f"it was. A 1.5 GB model on a home connection can take a long while.")

    def _paint_live(self) -> None:
        seen = self._seen
        percent = seen.get("percent")
        if percent is not None:
            self.bar.setValue(int(percent))
            self.bar.setFormat(f"{percent:.0f}%")
        else:
            self.bar.setValue(0)
            self.bar.setFormat("working")      # not "0%", which looks like nothing happens
        bits = []
        if seen.get("mb") is not None:
            if seen.get("total_mb"):
                bits.append(f"{seen['mb']:.0f} of {seen['total_mb']:.0f} MB")
            else:
                bits.append(f"{seen['mb']:.0f} MB")
        if seen.get("speed"):
            bits.append(seen["speed"])
        rate = _mb_per_second(seen.get("speed"))
        left_mb = None
        if seen.get("total_mb") and seen.get("mb") is not None:
            left_mb = max(0.0, seen["total_mb"] - seen["mb"])
        if rate and left_mb is not None:
            minutes = (left_mb / rate) / 60.0
            bits.append("about " + (f"{minutes:.0f} min" if minutes >= 1 else "under a min")
                        + " left at this speed")
        elif seen.get("eta"):
            bits.append(f"about {seen['eta']} left")
        waited = time.monotonic() - (self._started or time.monotonic())
        mins, secs = divmod(int(waited), 60)
        bits.append(f"{mins} min {secs:02d} s in")
        if not seen:
            bits.append("waiting for the first bytes")
        self.live.setText(" · ".join(bits))

    def closeEvent(self, event) -> None:                     # noqa: ANN001, N802
        """Closing while a download runs stops it first.

        A QThread destroyed while it is still running is an abort, not an error message —
        and the download would keep writing files with nobody watching. Stop, wait a
        moment, then close.
        """
        self._shut_worker()
        super().closeEvent(event)

    def reject(self) -> None:
        self._shut_worker()
        super().reject()

    def _shut_worker(self) -> None:
        if getattr(self, "_helper_engine", ""):
            # deliberately NOT stopped: outliving this window is the whole point
            self._helper_engine = ""
            try:
                self._ticker.stop()
            except Exception:                                    # noqa: BLE001
                pass
            return
        w = self._worker
        if w is None:
            return
        try:
            w.stop()
            if not w.wait(4000):
                # the child process it is waiting on did not die in time; a destroyed
                # running QThread aborts the whole app, so end it here, deliberately.
                w.terminate()
                w.wait(1500)
        except Exception:                                        # noqa: BLE001
            pass
        _LIVE_WORKERS.discard(w)
        self._worker = None
        try:
            self._ticker.stop()
        except Exception:                                        # noqa: BLE001
            pass

    def _stop(self) -> None:
        if getattr(self, "_helper_engine", ""):
            from .. import engine_helper
            engine = self._helper_engine
            self.verdict.setText("stopping… the download is being told to stop.")
            engine_helper.stop(engine)
            self._helper_engine = ""
            data = engine_helper.read(engine) or {}
            self._finish_helper(dict(data, done=True, why="cancelled"), engine)
            return
        self._stop_worker()

    def _stop_worker(self) -> None:
        if self._worker is not None:
            self.log.appendPlainText("— stopping, as asked —")
            self._worker.stop()
            self.stop_btn.setEnabled(False)

    def _on_need_token(self, engine: str, url: str) -> None:
        """A gated model is paused mid-download, waiting for one paste. Say it plainly."""
        self._awaiting_token = engine
        label = engines.SPECS.get(engine, {}).get("label", engine)
        self.verdict.setText(
            f"{label} needs a free token once before it will download — the download is "
            f"<b>paused</b>, not finished and not broken.<br>"
            f"1. open <a href=\"{url or 'https://huggingface.co/ai4bharat/IndicF5'}\">"
            f"{url or 'the model page'}</a> and click <b>Agree</b> (a free account).<br>"
            f"2. make a <b>read</b> token at https://huggingface.co/settings/tokens<br>"
            f"3. paste it in the box above and press <b>Save</b> — the download continues "
            f"by itself, no second Install.")
        self.verdict.setTextFormat(Qt.TextFormat.RichText)
        self.verdict.setOpenExternalLinks(True)
        self.token.setFocus()
        self.stop_btn.setEnabled(True)

    def _finished(self, result: dict) -> None:
        self._worker = None
        try:
            from .. import uiwork
            uiwork.clear_stuck_cursors()      # the desktop ring must never outlive a job
        except Exception:                                        # noqa: BLE001
            pass
        self._awaiting_token = None
        self._ticker.stop()
        self.live.setVisible(False)
        self._verdict_for = result.get("engine", "")
        self.bar.setVisible(False)
        self.stop_btn.setEnabled(False)
        self.go.setEnabled(True)
        self.auto_btn.setEnabled(True)
        if result.get("ok"):
            self.verdict.setText(
                f"Done — {engines.SPECS[result['engine']]['label']} is installed. "
                "Replies in that language now use the voice you chose.")
        elif result.get("needs_token"):
            state = engines.gate(result.get("engine", ""))
            self.verdict.setText(
                "Not downloaded, and it never will be without two minutes of setup: this "
                f"model is gated. Open {state.get('url') or 'the model page'}, click "
                "Agree (free account), make a read token at "
                "https://huggingface.co/settings/tokens, paste it above and press Save — "
                "the download then continues by itself.\nOr skip it: Piper is ~60 MB and "
                "needs no account.")
        elif result.get("why") == "cancelled":
            self.verdict.setText("Stopped. Nothing was half-installed that matters — "
                                 "you can start again whenever you like.")
        else:
            self.verdict.setText(
                f"Not installed ({result.get('why') or 'failed'}). The last line above says "
                "why. JARVIS keeps saying “system voice” until this works — it will not fake it.")
        # Show the engine this verdict is about. The list is size-ordered now, so after
        # installing the big one the picker would otherwise be sitting on Piper and the
        # result would be wiped by _show() as "a verdict about another engine".
        index = self.picker.findData(self._verdict_for)
        if index >= 0:
            self.picker.blockSignals(True)
            self.picker.setCurrentIndex(index)
            self.picker.blockSignals(False)
        self.reload()
