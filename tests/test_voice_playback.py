"""Pressing "play" on a voice must not make the window die

    python tests/test_voice_playback.py

The report, twice in the project: "select pana application crash aagi, close aaguthu".
The voice library's Hear button used to call `clone.speak` on its own thread — and the
first sentence through a real engine means the child interpreter imports torch and loads
a model. For those minutes the window did not paint and did not answer to Esc: a frozen
window wearing a dead window's face.

So: the button must answer in milliseconds, the work happens on a worker, the window
stays alive to be seen, and the engine itself has a ceiling (a sentence is not a
download; three minutes is already patience).
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-vplay-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {str(got)[:46]!r}")
    if not same:
        print(f"        expected {want!r}")


def pump(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(max(1, int(seconds * 1000)), loop.quit)
    loop.exec()


from arcdesk import config  # noqa: E402
import arcdesk.clone as clone  # noqa: E402
import arcdesk.voicelib as voicelib  # noqa: E402
from arcdesk.widgets.voicelib_dialog import VoiceLibraryDialog  # noqa: E402

cfg = config.load()
dlg = VoiceLibraryDialog(cfg, {})

# stand-ins: a voice that is selected, and an engine that takes a slow first sentence
voicelib.active_reply = lambda: {"id": "test", "name": "test voice", "lang": "en",
                                 "transcript": "hello there"}
real_speak = clone.speak
speak_threads = []
speak_moments = []


def slow_speak(text, lang="en", wav=""):
    speak_threads.append(threading.get_ident())
    speak_moments.append(time.monotonic())
    time.sleep(2.0)                 # the first run through a real engine
    return True


clone.speak = slow_speak
try:
    main_id = threading.get_ident()
    t0 = time.monotonic()
    dlg._hear()
    button_time = time.monotonic() - t0

    print("\n1. the button answers instantly, the window stays alive")
    check("pressing Hear returned in under a second", button_time < 1.0, True)
    check("…and said it is working", "speaking in that voice" in dlg.out.toPlainText(), True)

    print("\n2. the sentence is spoken on a worker, not on the drawing thread")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and "heard:" not in dlg.out.toPlainText():
        pump(0.2)
    check("the answer came back to the window", "heard:" in dlg.out.toPlainText(), True)
    check("…and it was spoken off-thread",
          bool(speak_threads) and speak_threads[0] != main_id, True)

    print("\n3. the engine itself has a ceiling")
    engines_src = (ROOT / "arcdesk" / "engines.py").read_text(encoding="utf-8")
    block = engines_src.split("def sidecar_speak", 1)[1]
    check("a timer sets the cancel while the child runs", "_threading.Timer(180.0, cancel.set)" in block, True)
    check("…and a late engine says so in words",
          "longer than 3 minutes" in block, True)

    print("\n4. the dialog code itself routes through the worker")
    dlg_src = (ROOT / "arcdesk" / "widgets" / "voicelib_dialog.py").read_text(encoding="utf-8")
    hear_block = dlg_src.split("def _hear(self)", 1)[1].split("\nclass ", 1)[0]
    check("clone.speak is only called inside the worker closure",
          hear_block.count("clone.speak(line, lang)") == 1, True)
    check("…and that closure is handed to uiwork",
          'uiwork.run(work, done=done, failed=failed' in hear_block, True)
finally:
    clone.speak = real_speak

dlg.close()
print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
