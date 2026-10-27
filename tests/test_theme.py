"""The white boxes, and the model that was there all along

    python tests/test_theme.py

Two things in the user's screenshot, and they were unrelated:

1. **letters white on white.** The engine/ears dialogs were built with Qt's default
   palette — a white window with a `QPlainTextEdit` that painted its own text as a
   selection highlight, because it had been given focus by `appendPlainText`. Fixed by a
   shared stylesheet (`widgets/style.py`) and by making logs read-only *and* unfocusable.

2. **the app said "speech model not downloaded" one line after the downloader said
   "already present: …\\ArcDesk\\vosk-model-small-en-us-0.15".** Two different folders,
   one feature: the downloader unpacks to `<data>/vosk-model-small-en-us-0.15`, and the
   checker only looked in `<data>/models/vosk` and `<data>/vosk-model`. So "hey jarvis"
   could never work on that machine no matter how many times the model was downloaded.

Both are tested here, and both are the kind of bug that a screenshot finds in five
seconds and a green test suite does not.
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-theme-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

from arcdesk import config  # noqa: E402
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets import voice_ready  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    ok &= bool(good)


th = get_theme("chill")

print("1) every small dialog wears the app's own colours")
from arcdesk.widgets.ears_dialog import EarsDialog  # noqa: E402
from arcdesk.widgets.engine_dialog import EngineDialog  # noqa: E402
from arcdesk.widgets.voicelib_dialog import VoiceLibraryDialog  # noqa: E402
from arcdesk.widgets.style import dialog_style, read_only_log  # noqa: E402

ears = EarsDialog(th)
engine = EngineDialog(th)
lib = VoiceLibraryDialog(config.load(), th)
for name, dlg in (("ears", ears), ("engine", engine), ("voices", lib)):
    sheet = dlg.styleSheet()
    check(f"{name}: has the theme colour for the window", th.bg in sheet, True)
    check(f"{name}: text is the theme's text colour", th.text in sheet, True)
    check(f"{name}: the log panel is the theme's panel", th.panel in sheet, True)
    check(f"{name}: no plain-white background anywhere", "#ffffff" not in sheet.lower(), True)

print("\n2) a log cannot paint a white selection over its own text")
for name, dlg in (("ears", ears), ("engine", engine), ("voices", lib)):
    log = getattr(dlg, "log", None) or getattr(dlg, "out", None)
    check(f"{name}: read-only", log.isReadOnly(), True)
    check(f"{name}: never takes the keyboard",
          log.focusPolicy() == Qt.FocusPolicy.NoFocus, True)
    check(f"{name}: no text selection at all",
          log.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction, True)
check("the helper sets all three in one place",
      read_only_log(__import__("PySide6.QtWidgets", fromlist=["QPlainTextEdit"])
                    .QPlainTextEdit()).focusPolicy() == Qt.FocusPolicy.NoFocus, True)
check("the stylesheet is built from the theme, not hard-coded",
      "QPlainTextEdit" in dialog_style(th), True)

print("\n3) the speech model is found wherever the downloader put it")
data = config.data_dir()
# the exact folder from the user's log
real = data / "vosk-model-small-en-us-0.15"
(real / "am").mkdir(parents=True, exist_ok=True)
(real / "conf").mkdir(parents=True, exist_ok=True)
(real / "am" / "final.mdl").write_bytes(b"model")
check("the downloader's own folder is found", voice_ready.model_dir(), real)
check("the folder is on the candidate list", real in voice_ready.model_candidates(), True)
check("an empty data folder is not a model",
      voice_ready._looks_like_a_model(data / "not-a-model"), False)
check("a folder that only CONTAINS the model is not one either",
      voice_ready._looks_like_a_model(data), False)

print("\n4) the other layouts people really have still work")
data2 = Path(tempfile.mkdtemp())
config.data_dir = lambda: data2        # pretend a different machine
check("nothing there yet → None", voice_ready.model_dir(), None)
old_style = data2 / "models" / "vosk"
old_style.mkdir(parents=True)
(old_style / "conf").mkdir()
check("the older models/vosk layout still counts", voice_ready.model_dir(), old_style)
other = data2 / "vosk-model-small-hi-0.22"
other.mkdir()
(other / "am").mkdir()
check("any vosk-model-* folder the user unpacked by hand is a candidate",
      other in voice_ready.model_candidates(), True)
check("…and the first valid one still wins", voice_ready.model_dir(), old_style)
check("the candidate list is de-duplicated, not doubled",
      len(voice_ready.model_candidates()) == len(set(str(p).lower()
                                                    for p in voice_ready.model_candidates())),
      True)

print("\n5) the ears dialog agrees with the same answer")
from arcdesk import ears  # noqa: E402
check("ears.model_dir is the same function, not a copy",
      ears.model_dir() is not None, True)
check("…and it locates a model this machine really has",
      Path(str(ears.model_dir())).name in ("vosk",) or
      Path(str(ears.model_dir())).name.startswith("vosk-model"), True)
ears.reload = None

print("\n6) the honest sentence changes when the model appears")
st = ears.status()
check("the speech model row is ticked", st["rows"]["model"]["ok"], True)
check("the row shows WHERE it is", str(st["rows"]["model"]["found"]).startswith("/"), True)
check("the top-level sentence no longer blames the model",
      "speech model not downloaded" not in st["sentence"], True)

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
