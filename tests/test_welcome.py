"""First run — the three decisions, and the two ways to decline them.

A setup card is where trust is won or lost: if "Done" silently switches the
microphone on, or if there is no way to skip, the app has already broken its
promise. So the rules are tested, not just drawn:

  1. it appears once (`first_run` flips to false);
  2. "Just use Lite" leaves the wake word OFF;
  3. ticking the box and pressing Done is the only way the mic gets armed;
  4. Esc behaves like "Just use Lite" — the least surprising default;
  5. the voice test button says something and never raises, even with no engine.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_welcome.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-welcome-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk import config  # noqa: E402
from arcdesk.widgets.welcome import WelcomeDialog  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<46} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


class QuietVoice:
    """Stands in for the TTS engine so the test never makes noise."""

    def __init__(self) -> None:
        self.said: list[str] = []
        self.boom = False

    def speak(self, text: str, **kwargs) -> None:
        if self.boom:
            raise RuntimeError("no audio device")
        self.said.append(text)


def main() -> int:
    ok = True
    QApplication.instance() or QApplication([sys.argv[0]])

    keep = []          # Qt owns the C++ side; Python must not collect it mid-run

    print("1) it appears once")
    cfg = config.load()
    cfg["first_run"] = True
    cfg.setdefault("wake", {})["enabled"] = False
    dlg = WelcomeDialog(cfg, QuietVoice())
    keep.append(dlg)
    ok &= check("dialog says first run", cfg["first_run"], True)

    print("2) 'Just use Lite' leaves the microphone off")
    dlg._finish(False)
    saved = config.load()
    ok &= check("first_run cleared", saved.get("first_run"), False)
    ok &= check("wake word still off", saved["wake"]["enabled"], False)

    print("3) ticking the box is the only way to arm the mic")
    cfg2 = config.load()
    cfg2.setdefault("wake", {})["enabled"] = False
    dlg2 = WelcomeDialog(cfg2, QuietVoice())
    keep.append(dlg2)
    dlg2.wake_box.setChecked(True)
    dlg2._finish(True)
    ok &= check("wake word armed by choice", config.load()["wake"]["enabled"], True)

    print("4) Esc is the same as skipping")
    cfg3 = config.load()
    cfg3["first_run"] = True
    cfg3["wake"]["enabled"] = False
    dlg3 = WelcomeDialog(cfg3, QuietVoice())
    keep.append(dlg3)
    dlg3.wake_box.setChecked(True)          # even when ticked…
    dlg3.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                 Qt.KeyboardModifier.NoModifier))
    ok &= check("closing saves nothing", config.load()["wake"]["enabled"], False)

    print("5) the voice test never crashes the card")
    voice = QuietVoice()
    cfg4 = config.load()
    dlg4 = WelcomeDialog(cfg4, voice)
    keep.append(dlg4)
    dlg4._test_voice()
    ok &= check("it spoke a line", len(voice.said), 1)
    voice.boom = True
    dlg4._test_voice()
    ok &= check("a dead engine is reported, not raised", "failed" in dlg4.status.text(), True)
    quiet = WelcomeDialog(config.load(), None)
    keep.append(quiet)
    quiet._test_voice()
    ok &= check("no engine at all is handled", bool(quiet.status.text()), True)

    print()
    print("PASS" if ok else "FAIL")
    # Qt widgets and the QApplication must go down in a defined order; letting the
    # interpreter collect them in arbitrary order is what segfaults headless runs.
    for dlg_ in keep:
        dlg_.close()
        dlg_.deleteLater()
    QApplication.processEvents()
    sys.stdout.flush()
    os._exit(0 if ok else 1)


if __name__ == "__main__":
    sys.exit(main())
