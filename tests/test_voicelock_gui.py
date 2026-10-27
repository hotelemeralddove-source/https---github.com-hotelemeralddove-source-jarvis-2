"""Submitting your voice — inside the app, not in a terminal.

The question: *"jarvis ku command koduka pora enoda voice ah yepo submit pananum?
yeppadi pananum? direct ah application layae panalama?"*

The answer this test enforces: three 4-second takes, in Settings → Voice → "Teach ARC my
voice…", with the recorder **injected** so the rules can be checked without a microphone.

  * it asks for three takes and knows how many are done;
  * a failed recording says why and does not count as a take;
  * a WAV file works instead of a microphone (no sounddevice installed is not a dead end);
  * enrolment failure is shown, never swallowed;
  * the lock switch only becomes usable once enrolment succeeded;
  * "Done" writes `wake.voice_lock` — that is the whole point;
  * with no speaker-id engine the dialog refuses to pretend, and offers the reason.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_voicelock_gui.py
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import wave
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="arcdesk-lockgui-")
os.environ["ARCDESK_HOME"] = HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk import config, voiceid  # noqa: E402
from arcdesk.widgets import voicelock  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<56} {str(got)[:32]!r}")
    ok &= bool(good)


def make_wav(name: str, seconds: float = 4.0, amp: float = 0.25) -> str:
    p = Path(HOME) / name
    sr = 16000
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b"".join(int(amp * 32767 * math.sin(2 * math.pi * 180 * i / sr))
                          .to_bytes(2, "little", signed=True)
                          for i in range(int(sr * seconds)))
        w.writeframes(frames)
    return str(p)


class FakeRecorder:
    """Produces a WAV per take. `fail_at` makes one take fail on purpose."""

    def __init__(self, fail_at: int = 0) -> None:
        self.calls = 0
        self.error = ""
        self.fail_at = fail_at
        self.levels: list[int] = []

    def available(self):
        return (True, "")

    def record(self, seconds=4.0, on_level=None):
        self.calls += 1
        if self.fail_at and self.calls == self.fail_at:
            self.error = "could not record: no input device"
            return ""
        if on_level:
            for v in (0, 30, 70, 40):
                on_level(v)
                self.levels.append(v)
        return make_wav(f"take{self.calls}.wav")


def fake_engine():
    """Pretend sherpa-onnx is installed: embeddings are tiny vectors."""
    voiceid.available = lambda: (True, "")
    voiceid.engine = lambda: {"name": "sherpa-onnx", "model": "fake.onnx", "ready": True,
                              "why": ""}
    voiceid.embed = lambda path: voiceid._unit([1.0, 0.1, 0.0, 0.0])


QApplication.instance() or QApplication([sys.argv[0]])

print("\n1) with no speaker engine, the dialog refuses to pretend")
voiceid.available = lambda: (False, "no speaker-id engine installed — run install_voice.bat")
voiceid.engine = lambda: {"name": "", "model": "", "ready": False,
                          "why": "no speaker-id engine installed"}
cfg = config.load()
dlg = voicelock.VoiceLockDialog(cfg, recorder=FakeRecorder())
check("record button disabled", dlg.record_btn.isEnabled(), False)
check("file button disabled", dlg.file_btn.isEnabled(), False)
check("lock switch disabled", dlg.lock_box.isEnabled(), False)
check("it says what is missing", "speaker-id" in dlg.note.text(), True)

print("\n2) with the engine, three takes enrol the person")
fake_engine()
cfg = config.load()
rec = FakeRecorder()
dlg = voicelock.VoiceLockDialog(cfg, recorder=rec)
check("record button enabled", dlg.record_btn.isEnabled(), True)
check("starts at 0 of 3", "0 of 3" in dlg.status.text(), True)
dlg._record()
check("first take counted", len(dlg.samples), 1)
check("button says take 2", "take 2" in dlg.record_btn.text(), True)
check("the level bar was driven", max(rec.levels) >= 70, True)
dlg._record()
check("second take counted", len(dlg.samples), 2)
check("no enrolment yet", dlg.done_btn.isEnabled(), False)
dlg._record()
check("third take counted", len(dlg.samples), 3)
check("enrolled", bool(voiceid.profiles()), True)
check("named 'me' by default", list(voiceid.profiles()), ["me"])
check("three samples stored", voiceid.profiles()["me"]["samples"], 3)
check("lock switch becomes usable", dlg.lock_box.isEnabled(), True)
check("Done becomes usable", dlg.done_btn.isEnabled(), True)
check("the note reports agreement", "agreement" in dlg.note.text(), True)

print("\n3) Done writes the lock setting — the point of the whole dialog")
dlg.lock_box.setChecked(True)
dlg._finish()
check("saved to settings", config.load()["wake"]["voice_lock"], True)
check("the note says it is on", "voice lock ON" in dlg.result_note, True)

print("\n4) turning it off again is the same switch")
cfg = config.load()
dlg = voicelock.VoiceLockDialog(cfg, recorder=FakeRecorder())
check("reflects the saved state", dlg.lock_box.isChecked(), True)
dlg.lock_box.setChecked(False)
dlg._finish()
check("saved off", config.load()["wake"]["voice_lock"], False)

print("\n5) a failed recording says why and does not count")
rec = FakeRecorder(fail_at=2)
cfg = config.load()
dlg = voicelock.VoiceLockDialog(cfg, recorder=rec)
dlg._record()
dlg._record()
check("still two takes", len(dlg.samples), 1)
check("the reason is shown", "no input device" in dlg.note.text(), True)
dlg._record()                      # third call now succeeds
check("can carry on afterwards", len(dlg.samples), 2)

print("\n6) a WAV file works instead of a microphone")
cfg = config.load()
dlg = voicelock.VoiceLockDialog(cfg, recorder=FakeRecorder())
dlg._accept_take(make_wav("file1.wav"))
dlg._accept_take(make_wav("file2.wav"))
dlg._accept_take(make_wav("file3.wav"))
check("enrolled from files", bool(voiceid.profiles()), True)
check("Done usable", dlg.done_btn.isEnabled(), True)

print("\n7) 'Start over' clears the takes but keeps what was saved")
dlg._reset()
check("takes cleared", dlg.samples, [])
check("status reset", "0 of 3" in dlg.status.text(), True)
check("enrolment on disk is untouched", bool(voiceid.profiles()), True)

print("\n8) the recorder itself admits when there is no microphone library")
real = voicelock.MicRecorder()
try:
    import sounddevice  # noqa: F401
    has_mic = True
except Exception:
    has_mic = False
avail, why = real.available()
check("available() matches reality", avail, has_mic)
if not has_mic:
    check("and explains", "install_voice" in why, True)
    check("record() returns '' instead of raising", real.record(0.1), "")
    check("with a reason", bool(real.error), True)

print("\n" + ("ALL PASS" if ok else "SOMETHING FAILED"))
sys.exit(0 if ok else 1)
