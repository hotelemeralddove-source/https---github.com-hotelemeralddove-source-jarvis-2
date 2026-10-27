"""Settings → Voice → "Voices…" — two lists, because there are two questions.

    COMMAND VOICES   who may say "hey jarvis" and be obeyed   (any number of people)
    REPLY VOICE      which voice ARC answers in              (any voice you have a clip of)

The user asked for exactly this: command in my voice, reply in the voice I choose — and no
robotic TTS. The honesty is on the screen: a reply voice needs a clone engine installed
(IndicF5 / XTTS), and until one is, JARVIS says "system voice" rather than pretending.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from .. import voicelib
from ..theme import Theme


def _heading(text: str) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setPixelSize(10)
    f.setWeight(f.Weight.Bold)
    lab.setFont(f)
    return lab


class VoiceLibraryDialog(QDialog):
    def __init__(self, cfg: dict, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.theme = theme
        self.setWindowTitle("Arc Desk · voices")
        # 660 was taller than the usable height of a 768-pixel laptop at 125% scaling, and
        # the Done button — the only way out — sat below the bottom edge. See make_fit().
        from .style import dialog_style
        if theme:
            self.setStyleSheet(dialog_style(theme))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)

        title = QLabel("VOICES")
        f = title.font()
        f.setPixelSize(11)
        f.setWeight(f.Weight.Bold)
        title.setFont(f)
        lay.addWidget(title)
        lay.addWidget(QLabel(
            "Two different things. Who may COMMAND JARVIS, and which voice it ANSWERS in."))

        # ------------------------------------------------------------ command
        lay.addWidget(_heading("1 · WHO MAY COMMAND IT"))
        self.cmd_list = QListWidget()
        self.cmd_list.setMaximumHeight(90)
        lay.addWidget(self.cmd_list)
        row = QHBoxLayout()
        self.cmd_name = QLineEdit()
        self.cmd_name.setPlaceholderText("name (e.g. me, amma, ravi)")
        row.addWidget(self.cmd_name, 1)
        self.cmd_add = QPushButton("Add a voice…")
        self.cmd_add.clicked.connect(self._add_command)
        row.addWidget(self.cmd_add)
        self.cmd_del = QPushButton("Remove")
        self.cmd_del.clicked.connect(self._del_command)
        row.addWidget(self.cmd_del)
        lay.addLayout(row)
        self.cmd_note = QLabel("")
        self.cmd_note.setWordWrap(True)
        lay.addWidget(self.cmd_note)

        # -------------------------------------------------------------- reply
        lay.addWidget(_heading("2 · THE VOICE JARVIS ANSWERS IN"))
        self.reply_list = QListWidget()
        self.reply_list.setMaximumHeight(110)
        lay.addWidget(self.reply_list)
        hint = QLabel("Use a 10–20 second clip of one person talking, no music. "
                      "4 seconds is the minimum; a longer clip sounds much closer.")
        hint.setWordWrap(True)
        hint.setObjectName("dim")
        lay.addWidget(hint)

        row2 = QHBoxLayout()
        self.reply_name = QLineEdit()
        self.reply_name.setPlaceholderText("name for this voice (e.g. rajini, me)")
        row2.addWidget(self.reply_name, 1)
        self.reply_add = QPushButton("Add a voice…")
        self.reply_add.clicked.connect(self._add_reply)
        row2.addWidget(self.reply_add)
        row2.addStretch(1)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        self.use = QPushButton("Answer in this voice")
        self.use.clicked.connect(self._use_reply)
        row3.addWidget(self.use)
        self.hear = QPushButton("Hear it")
        self.hear.clicked.connect(self._hear)
        row3.addWidget(self.hear)
        self.reply_del = QPushButton("Remove")
        self.reply_del.clicked.connect(self._del_reply)
        row3.addWidget(self.reply_del)
        row3.addStretch(1)
        lay.addLayout(row3)

        lay.addWidget(_heading("WHAT IT SAYS IN THAT CLIP"))
        self.transcript = QLineEdit()
        self.transcript.setPlaceholderText("type the words spoken in the clip (needed by IndicF5)")
        lay.addWidget(self.transcript)
        self.lang = QComboBox()
        for label, code in (("Auto (from the script)", "auto"), ("Tamil", "ta"),
                            ("Hindi", "hi"), ("English", "en")):
            self.lang.addItem(label, code)
        lay.addWidget(self.lang)

        # ---- the one-click fix for "the upload was refused" ---------------
        # A refusal that only says "run python tools/voice_setup.py" is a dead end for
        # anyone who installed the app with an installer and has no terminal. The model
        # is 30 MB; the app can fetch it, visibly, from here.
        self.model_row = QWidget()
        model_lay = QHBoxLayout(self.model_row)
        model_lay.setContentsMargins(0, 0, 0, 0)
        self.model_btn = QPushButton("Download the voice-lock model (30 MB)…")
        self.model_btn.setToolTip("Needed before a COMMAND voice can be enrolled. "
                                  "One file, downloaded once, stays on this PC.")
        self.model_btn.clicked.connect(self._get_model)
        model_lay.addWidget(self.model_btn)
        self.model_note = QLabel("")
        self.model_note.setObjectName("dim")
        self.model_note.setWordWrap(True)
        model_lay.addWidget(self.model_note, 1)
        lay.addWidget(self.model_row)

        from .style import read_only_log
        self.out = read_only_log(QPlainTextEdit())
        self.out.setFixedHeight(130)
        lay.addWidget(self.out)

        row4 = QHBoxLayout()
        self.engine_btn = QPushButton("The engine that makes it sound real…")
        self.engine_btn.setToolTip("IndicF5 for Tamil/Hindi, XTTS for English — downloaded "
                                  "once, from here, one click.")
        self.engine_btn.clicked.connect(self.open_engines)
        row4.addWidget(self.engine_btn)
        row4.addStretch(1)
        done = QPushButton("Done")
        done.clicked.connect(self.accept)
        # Disabled while a recording is being read, so one upload cannot start twice.
        # (Done stays enabled on purpose: closing is always allowed.)
        self._while_busy = (self.cmd_add, self.reply_add, self.cmd_del, self.reply_del)
        row4.addWidget(done)
        lay.addLayout(row4)

        self._reload()

        # Body scrolls, the engine + Done row stays pinned on screen, and the dialog never
        # starts bigger than the display. This is what made "Add a voice" look broken:
        # the button was there, the confirmation was below the screen.
        from .fit import make_fit
        make_fit(self, preferred=(760, 700), keep_last=1, minimum=(430, 320))

    # ------------------------------------------------------------------ lists
    def _reload(self) -> None:
        self.cmd_list.clear()
        for name in voicelib.command_voices():
            self.cmd_list.addItem(QListWidgetItem(name))
        self.reply_list.clear()
        active = voicelib.active_reply().get("id", "")
        for entry in voicelib.reply_voices():
            label = (f"{entry['name']}  ·  {entry.get('seconds', 0):g} s · "
                     f"{entry.get('grade', '')}"
                     + ("   ← in use" if entry.get("id") == active else ""))
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.get("id", ""))
            self.reply_list.addItem(item)
        self.cmd_note.setText(
            ("Nobody is enrolled: any voice may command JARVIS." if not voicelib.command_voices()
             else "Enrolled: " + ", ".join(voicelib.command_voices())
                  + ". The lock must also be ON (the switch on the Voice tab)."))
        self.out.setPlainText(voicelib.describe() + "\n\n" + self._engine_line())
        self._refresh_model_row()

    def _refresh_model_row(self) -> None:
        """Show the download button only while the speaker model is actually missing."""
        try:
            from .. import voiceid
            why = str(voiceid.engine().get("why") or "")
        except Exception:
            why = ""
        needs = "speaker" in why.lower() and ("not downloaded" in why.lower()
                                              or "no speaker-id" in why.lower())
        self.model_row.setVisible(needs)
        self.model_note.setText(why if needs else "")

    def _get_model(self) -> None:
        """Fetch the speaker model in the background, saying what it is doing."""
        import threading

        self.model_btn.setEnabled(False)
        self.out.setPlainText("downloading the speaker-embedding model (~30 MB)…")

        from .. import uiwork

        def work(_cancel):
            from .. import voiceid
            return voiceid.download_model()

        def done(got) -> None:
            self.model_btn.setEnabled(True)
            self.out.setPlainText(str(got.get("message", "")))
            if not got.get("ok"):
                QMessageBox.warning(self, "The model did not download",
                                    str(got.get("message", "")))
            self._reload()

        def failed(text: str) -> None:
            self.model_btn.setEnabled(True)
            self.out.setPlainText(f"the model did not download ({text})")
            self._reload()

        uiwork.run(work, done=done, failed=failed, name="arc-voice-model")

    def _engine_line(self) -> str:
        """One honest sentence about the engine, then the way to get it."""
        try:
            from .. import engines
            return engines.line_for_voice()
        except Exception:
            return "No clone engine is installed, so replies use the system voice."

    def open_engines(self) -> None:
        from .engine_dialog import EngineDialog
        from .safeopen import open_dialog
        open_dialog("the reply-voice engines", lambda: EngineDialog(self.theme, parent=self),
                    parent=self)
        self._reload()

    # -------------------------------------------------------------- commands
    def _add_command(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "A recording of the voice allowed to command JARVIS", "",
            "Audio or video (*.wav *.mp3 *.m4a *.mp4 *.mkv *.webm *.ogg *.flac);;All files (*)")
        if not path:
            return
        name = self.cmd_name.text()

        def apply(got):
            self.out.setPlainText(str(got.get("message", "")))
            if not got.get("ok", True):
                # Louder than the log box: a refusal in a scroll area is easy to miss, and
                # "I clicked and nothing happened" was the report.
                QMessageBox.warning(self, "That voice was not added", str(got.get("message")))
            self._reload()

        self._busy(lambda _cancel: voicelib.add_command(name, path),
                   "reading that recording…  (you can still close this window)",
                   apply, "command voice")

    def _busy(self, work, note: str, done, what: str) -> None:
        """Run a slow import on a worker, with the screen saying so.

        The first upload on a fresh PC may install a ~2 MB audio decoder
        (arcdesk/audio.py), which takes a few seconds — and this used to do it on the
        drawing thread behind `processEvents()`, which is the pattern that leaves a
        window frozen in front with a waiting cursor (`20.png`). Now:

          * the work runs in `arcdesk.uiwork`, so the dialog paints and Esc works;
          * the line in the box says what is happening and that closing is allowed;
          * `done(got)` is called on the UI thread with the answer;
          * the buttons are disabled while it runs, so the same upload cannot be
            started twice and produce two half-finished voices.
        """
        from .. import uiwork
        self.out.setPlainText(note)
        for widget in getattr(self, "_while_busy", ()):
            widget.setEnabled(False)

        def finish(got):
            for widget in getattr(self, "_while_busy", ()):
                widget.setEnabled(True)
            done(got)

        def failed(text: str) -> None:
            for widget in getattr(self, "_while_busy", ()):
                widget.setEnabled(True)
            self.out.setPlainText(f"could not read that recording ({text}).\n"
                                  f"Nothing was changed. The file type may be unsupported "
                                  f"— a .wav or .mp3 always works.")

        uiwork.run(work, done=finish, failed=failed, name=f"arc-voice-{what.replace(' ', '-')}")

    def _del_command(self) -> None:
        item = self.cmd_list.currentItem()
        if item is None:
            return
        voicelib.remove_command(item.text())
        self._reload()

    # ------------------------------------------------------------------ reply
    def _add_reply(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "A recording of the voice JARVIS should answer in", "",
            "Audio or video (*.wav *.mp3 *.m4a *.mp4 *.mkv *.webm *.ogg *.flac);;All files (*)")
        if not path:
            return
        name = self.reply_name.text()
        heard = self.transcript.text()
        lang = self.lang.currentData() or "auto"

        def apply(got):
            if not got.get("ok"):
                self.out.setPlainText("could not add that voice:\n"
                                      + str(got.get("message")))
                QMessageBox.warning(self, "That voice was not added",
                                    str(got.get("message")))
                return
            voicelib.set_reply(got["voice"]["id"])
            self.out.setPlainText(got["message"] + "\n\n" + voicelib.describe())
            self._reload()

        self._busy(lambda _cancel: voicelib.add_reply(name, path, heard, lang),
                   "reading that recording…  (the first one may install a small decoder, "
                   "and you can still close this window)",
                   apply, "reply voice")

    def _use_reply(self) -> None:
        item = self.reply_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Pick one", "Choose a voice in the list first.")
            return
        if voicelib.set_reply(item.data(Qt.ItemDataRole.UserRole)):
            self.out.setPlainText("now answering in that voice.\n\n" + voicelib.describe())
        self._reload()

    def _del_reply(self) -> None:
        item = self.reply_list.currentItem()
        if item is None:
            return
        voicelib.remove_reply(item.data(Qt.ItemDataRole.UserRole))
        self._reload()

    def _hear(self) -> None:
        """Say one sentence in the picked voice — off the drawing thread.

        The old version called `clone.speak` right here, on the button's own thread. The
        first sentence through a freshly-installed engine means the child interpreter
        imports torch and loads the model — minutes — and for those minutes this window
        does not paint, does not answer to Esc, and looks dead. "Play pana app close
        aaguthu" was a frozen window wearing a dead window's face.
        """
        from .. import clone, uiwork
        entry = voicelib.active_reply()
        if not entry:
            self.out.setPlainText("add a reply voice first")
            return
        lang = entry.get("lang") or "auto"
        if lang == "auto":
            lang = "ta" if any("\u0b80" <= ch <= "\u0bff" for ch in entry.get("transcript", "")) \
                else ("hi" if any("\u0900" <= ch <= "\u097f" for ch in entry.get("transcript", ""))
                      else "en")
        line = {"ta": "vanakkam, ithu nee kodutha kural.",
                "hi": "namaste, yah wahi aawaz hai.",
                "en": "hello, this is the voice you gave me."}.get(lang, "hello")
        self.out.setPlainText("speaking in that voice… the first sentence can take a "
                              "minute — the window stays usable, Esc still closes")
        self.hear.setEnabled(False)

        def work(_cancel):
            return clone.speak(line, lang)

        def done(ok):
            self.hear.setEnabled(True)
            if ok:
                self.out.setPlainText("heard: " + line)
            else:
                self.out.setPlainText(
                    "nothing spoke. No engine can say that language yet — Settings → "
                    "Voice → the engines screen will. The quick match (your clip's "
                    "pitch, no download) works in the meantime.")

        def failed(text):
            self.hear.setEnabled(True)
            self.out.setPlainText(f"could not speak ({text}) — nothing was changed")

        uiwork.run(work, done=done, failed=failed, name="arc-hear-reply-voice")
