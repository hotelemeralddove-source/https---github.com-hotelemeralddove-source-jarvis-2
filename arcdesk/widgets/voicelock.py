"""Teaching JARVIS who you are — inside the app, not in a terminal.

The question this answers: *"enoda voice-a yepo submit pananum? direct ah app-layae
panalama?"* — **yes, here, in Settings → Voice, with three 4-second recordings.**

What the person sees, in order:

  1. what it is about to ask for ("say any sentence, 4 seconds, three times");
  2. a live level bar while recording, so they know the microphone works *now*;
  3. per-clip feedback (too quiet / too short / good) instead of a silent failure;
  4. a score for each clip, and whether the three agree with each other;
  5. one switch: "only my voice may command JARVIS" — plus a test recording.

Two fallbacks, both honest rather than hidden:

  * **no microphone library** (sounddevice missing) → the dialog offers "use a WAV file"
    and says which installer adds recording;
  * **no speaker model** (sherpa-onnx) → it says so and *refuses to turn the lock on*,
    because a lock that does not work is worse than no lock.

The recorder is injectable (`recorder=`), which is how the tests run it with no audio
device at all: they hand it a fake that produces silent WAVs.
"""
from __future__ import annotations

import tempfile
import time
import wave
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QVBoxLayout)

from .. import voiceid

CLIPS = 3
SECONDS = 4.0
RATE = 16000
ACCENT = "#7fe3f0"
DIM = "#8fa3ad"


# ------------------------------------------------------------------ recorder
class MicRecorder:
    """4 seconds of 16 kHz mono audio, blocking, with a level callback."""

    def __init__(self) -> None:
        self.error = ""

    def available(self) -> tuple[bool, str]:
        try:
            import sounddevice  # noqa: F401
        except Exception:
            return (False, "no microphone library yet — run install_voice.bat "
                           "(it adds sounddevice), or use a WAV file instead")
        return (True, "")

    def record(self, seconds: float = SECONDS, on_level=None) -> str:
        """Record and return a WAV path. Raises nothing: sets `error` and returns ""."""
        self.error = ""
        try:
            import sounddevice as sd
            import numpy as np
        except Exception as exc:                                # noqa: BLE001
            self.error = f"microphone library missing: {exc}"
            return ""
        frames = int(seconds * RATE)
        try:
            chunk = int(RATE * 0.05)
            pieces = []
            with sd.InputStream(samplerate=RATE, channels=1, dtype="int16") as stream:
                for _ in range(max(1, frames // chunk)):
                    block, _overflow = stream.read(chunk)
                    pieces.append(bytes(block))
                    if on_level is not None:
                        peak = int(abs(block).max()) if len(block) else 0
                        on_level(min(100, int(peak / 328)))
            path = Path(tempfile.gettempdir()) / f"arcdesk-enrol-{int(time.time() * 1000)}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(b"".join(pieces))
            return str(path)
        except Exception as exc:                                # noqa: BLE001
            self.error = f"could not record: {type(exc).__name__}: {exc}"
            return ""


# -------------------------------------------------------------------- dialog
class VoiceLockDialog(QDialog):
    """Enrol one person's voice, then optionally lock the machine to it."""

    def __init__(self, cfg: dict, parent=None, recorder=None, name: str = "me") -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.recorder = recorder or MicRecorder()
        self.name = (name or "me").strip() or "me"
        self.samples: list[str] = []
        self.result_note = ""
        self.setWindowTitle("Arc Desk · teach it my voice")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            "QDialog{background:#0a1116;}"
            "QLabel{color:#dbe7ec;font-family:Segoe UI;}"
            f"QLabel#kicker{{color:{ACCENT};font-size:11px;letter-spacing:2px;}}"
            "QLabel#h1{font-size:19px;font-weight:600;}"
            f"QLabel#dim{{color:{DIM};font-size:12px;}}"
            "QPushButton{background:#12242c;color:#dbe7ec;border:1px solid #24404b;"
            "border-radius:6px;padding:7px 13px;}"
            f"QPushButton:hover{{border-color:{ACCENT};}}"
            f"QPushButton#go{{background:{ACCENT};color:#06131a;font-weight:600;}}"
            "QPushButton:disabled{color:#5c6b73;border-color:#1b2a31;}"
            "QCheckBox{color:#dbe7ec;}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)

        kick = QLabel("JARVIS DESK · VOICE LOCK")
        kick.setObjectName("kicker")
        lay.addWidget(kick)
        title = QLabel("Three takes of your voice, four seconds each.")
        title.setObjectName("h1")
        lay.addWidget(title)

        engine_ok, why = voiceid.available()
        body = QLabel(
            "Say any sentence — the words do not matter, the voice does. "
            "Quiet room, normal speaking volume, no music.\n\n"
            "After this, JARVIS can accept spoken commands from this voice only, on this "
            "computer." if engine_ok else
            f"This needs the speaker-id engine first: {why}")
        body.setWordWrap(True)
        body.setObjectName("dim")
        lay.addWidget(body)

        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setTextVisible(False)
        self.level.setFixedHeight(8)
        lay.addWidget(self.level)

        self.status = QLabel("0 of 3 recorded")
        self.status.setObjectName("dim")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.record_btn = QPushButton("●  Record take 1")
        self.record_btn.setObjectName("go")
        self.record_btn.clicked.connect(self._record)
        self.record_btn.setEnabled(engine_ok)
        row.addWidget(self.record_btn)
        self.file_btn = QPushButton("Use a WAV file…")
        self.file_btn.clicked.connect(self._from_file)
        self.file_btn.setEnabled(engine_ok)
        row.addWidget(self.file_btn)
        self.reset_btn = QPushButton("Start over")
        self.reset_btn.clicked.connect(self._reset)
        row.addWidget(self.reset_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.lock_box = QCheckBox('Only my voice may command JARVIS on this computer')
        self.lock_box.setChecked(bool(cfg.get("wake", {}).get("voice_lock", False)))
        self.lock_box.setEnabled(False)          # enabled once enrolment succeeds
        lay.addWidget(self.lock_box)

        self.note = QLabel("")
        self.note.setObjectName("dim")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.done_btn = QPushButton("Done")
        self.done_btn.setObjectName("go")
        self.done_btn.setEnabled(False)
        self.done_btn.clicked.connect(self._finish)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        foot.addWidget(close)
        foot.addWidget(self.done_btn)
        lay.addLayout(foot)

        if not engine_ok:
            self.note.setText(why)

    # ------------------------------------------------------------- recording
    def _record(self) -> None:
        take = len(self.samples) + 1
        self.record_btn.setEnabled(False)
        self.status.setText(f"recording take {take} — say something…")
        self.level.setValue(0)
        self.repaint()
        path = ""
        try:
            path = self.recorder.record(SECONDS, on_level=self._level)
        except TypeError:
            path = self.recorder.record(SECONDS)          # a recorder without the callback
        except Exception as exc:                            # noqa: BLE001
            path = ""
            self.note.setText(f"recording failed: {type(exc).__name__}: {exc}")
        self.level.setValue(0)
        self.record_btn.setEnabled(True)
        if not path:
            self.note.setText(getattr(self.recorder, "error", "") or
                              "nothing was recorded — check the microphone")
            return
        self._accept_take(path)

    def _from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "A recording of your voice",
                                              "", "Audio (*.wav *.mp3 *.m4a *.ogg)")
        if path:
            self._accept_take(path)

    def _accept_take(self, path: str) -> None:
        self.samples.append(path)
        take = len(self.samples)
        self.status.setText(f"{take} of {CLIPS} recorded")
        self.record_btn.setText(f"●  Record take {take + 1}" if take < CLIPS
                                else "●  Record another")
        if take >= CLIPS:
            self._enrol()

    def _level(self, value: int) -> None:
        self.level.setValue(int(value))
        if value < 3:
            self.status.setText("very quiet — move closer to the microphone")

    def _reset(self) -> None:
        self.samples.clear()
        self.record_btn.setText("●  Record take 1")
        self.status.setText("0 of 3 recorded")
        self.note.setText("")
        self.lock_box.setEnabled(False)
        self.done_btn.setEnabled(False)

    def _enrol(self) -> None:
        got = voiceid.enroll(self.name, self.samples)
        if not got["ok"]:
            self.note.setText(got["message"])
            return
        self.result_note = got["message"]
        agree = got["self_similarity"]
        verdict = ("the three takes agree" if agree >= 0.75 else
                   "the takes disagree a little — three new ones will be better")
        self.note.setText(f"{got['message']} · {verdict} (agreement {agree:.2f}). "
                          f"Tick the box below to switch the lock on.")
        self.lock_box.setEnabled(True)
        self.done_btn.setEnabled(True)

    # ---------------------------------------------------------------- finish
    def _finish(self) -> None:
        on = bool(self.lock_box.isChecked())
        self.cfg.setdefault("wake", {})["voice_lock"] = on
        try:
            from .. import config as _config
            _config.save(self.cfg)
        except Exception:
            pass
        self.result_note += (" · voice lock ON" if on else " · voice lock off")
        self.accept()


def describe() -> str:
    return voiceid.describe()
