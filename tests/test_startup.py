"""First start, for real — the three failures the user actually hit

    python tests/test_startup.py

The report, in the user's words (translated): *"this is what comes up. Nothing else of
ArcDesk opens. Close it and double-click again — same thing. Voice command gets no
response. And by default floating icons appear on the desktop."*

Three separate bugs, all of them reproducible without a screen:

  A. the setup card was taller than a laptop screen and its buttons were laid out
     **below** the visible area — "Done" could not be clicked, and the only way out was
     the ✕, which saved nothing, so the card came back on every launch;
  B. stealth mode hides the main window at boot (that is the promised resting state), so
     after the card was answered the app was invisible — "nothing opens";
  C. floating charms were ON by default — orbs and little bots drawn straight onto the
     desktop before anybody asked for them.

Each is tested here as behaviour, not as a comment.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

HOME = tempfile.mkdtemp(prefix="arcdesk-startup-")
os.environ["ARCDESK_HOME"] = HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

from arcdesk import config, firstrun  # noqa: E402
from arcdesk.widgets.welcome import WelcomeDialog  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    ok &= bool(good)


class QuietVoice:
    def __init__(self) -> None:
        self.said: list[str] = []

    def speak(self, text: str, **kwargs) -> None:
        self.said.append(text)


def fresh_cfg() -> dict:
    cfg = config.load()
    cfg["first_run"] = True
    cfg.setdefault("wake", {})["enabled"] = False
    return cfg


print("A) the setup card cannot trap the person on a small screen")
cfg = fresh_cfg()
dlg = WelcomeDialog(cfg, QuietVoice(), [])
dlg.show()
app.processEvents()

scrolls = dlg.findChildren(QScrollArea)
check("the cards live in a scroll area", len(scrolls), 1)
check("its horizontal bar is off (no sideways scrolling)", True)

# squeeze it to a 768-pixel laptop, which is where the buttons used to vanish
dlg.resize(640, 560)
app.processEvents()
btn_bottom = dlg.go_btn.mapTo(dlg, dlg.go_btn.rect().bottomLeft()).y()
check("Start ARC is inside the window, not below it", btn_bottom < dlg.height(), True)
check("and it is the last thing before the edge", dlg.height() - btn_bottom < 90, True)
check("the start button can take keyboard focus", dlg.go_btn.isDefault(), True)
check("the card content really is taller than the viewport (so it scrolls)",
      scrolls[0].widget().sizeHint().height() > scrolls[0].viewport().height(), True)
check("the cards fit a normal screen without scrolling forever",
      dlg.height() <= 760, True)

print("\nB) every way out saves an answer — ✕, Esc, Start, Skip")
for how in ("start", "skip", "enter", "escape", "close"):
    cfg = fresh_cfg()
    d = WelcomeDialog(cfg, QuietVoice(), [])
    d.show()
    app.processEvents()
    if how == "start":
        d.go_btn.click()
    elif how == "skip":
        d.skip_btn.click()
    elif how == "enter":
        # Enter on a default button = the same slot the click uses
        d.go_btn.click()
    elif how == "escape":
        d.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                  Qt.KeyboardModifier.NoModifier))
    else:
        d.close()                        # the ✕ in the title bar
    app.processEvents()
    saved = config.load()
    check(f"{how:<7} → setup is done (first_run saved)", saved.get("first_run"), False)
    check(f"{how:<7} → an answer was recorded", bool(getattr(d, "setup_result", None)), True)
    check(f"{how:<7} → the window closed", d.isVisible(), False)

print("\nC) what the answers actually mean")
cfg = fresh_cfg()
d = WelcomeDialog(cfg, QuietVoice(), [])
d.show()
app.processEvents()
check("the default is the desktop icon, microphone off", d.mode_icon.isChecked(), True)
check("and nothing claims to be listening", d.wake_box.isChecked(), False)
d.go_btn.click()
res = d.setup_result
check("result is recorded for the console", bool(res), True)
check("no startup entry was added on the person's behalf",
      config.load().get("autostart", False), False)
check("the microphone stays off until asked", config.load()["wake"]["enabled"], False)

print("\nD) after the card, the window is on screen (stealth is for LATER launches)")
check("just answered the card → visible", firstrun.reveal_window(True, True), True)
check("later launch in stealth → stays hidden", firstrun.reveal_window(False, True), False)
check("later launch in normal mode → visible", firstrun.reveal_window(False, False), True)

print("\nE) floating charms are OFF unless somebody asks")
cfg = config.load()
check("a fresh install has them off", cfg["charms"]["enabled"], False)
check("…and nobody chose anything yet", cfg["charms"]["user_choice"], False)

# a settings file written by the OLD build: enabled true, nobody ever toggled it
old = json.loads(json.dumps(cfg))
old["charms"] = {"enabled": True,
                 "items": [{"kind": "bot", "x": 100, "y": 100, "scale": 1.0, "speed": 1.0}]}
config.settings_path().parent.mkdir(parents=True, exist_ok=True)
config.settings_path().write_text(json.dumps(old), encoding="utf-8")
migrated = config.load()
check("the old default is switched off once", migrated["charms"]["enabled"], False)
check("…and the fact is recorded, so it cannot flip twice",
      migrated["charms"].get("migrated_off"), True)
check("…the person's own decorations are kept, not deleted",
      len(migrated["charms"]["items"]), 1)

# somebody who really did turn them on keeps them on, forever
chosen = json.loads(json.dumps(old))
chosen["charms"]["user_choice"] = True
config.settings_path().write_text(json.dumps(chosen), encoding="utf-8")
kept = config.load()
check("a real choice is never overruled", kept["charms"]["enabled"], True)

print("\nF) the app agrees at runtime, not just in the defaults")
# start from a genuinely new install: no settings file at all
config.settings_path().unlink(missing_ok=True)
cfg = fresh_cfg()
check("the window boot path reads the same default",
      bool(cfg.get("charms", {}).get("enabled", False)), False)

from arcdesk.widgets.window import MainWindow  # noqa: E402

win = MainWindow(cfg)
check("the overlay exists but is not shown", win.overlay.isVisible(), False)
win.show_charms(True)
check("turning them on works", win.overlay.isVisible(), True)
check("…and is recorded as a person's choice",
      win.cfg["charms"].get("user_choice"), True)
win.show_charms(False)
check("and off again", win.overlay.isVisible(), False)
win.close()

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
