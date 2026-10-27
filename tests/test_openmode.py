"""How does it open — a desktop icon, or "hey jarvis"? And who may command it?

The request, in the user's words:

  * *"first time set pannum pothu voice la open pananuma illa desktop icon double click
    panra mathiri venuma nu kekanum"* — one question, two answers, at setup;
  * *"avangaluku ena option venumo atha use panikalam"* — either is fine;
  * *"future la voice la open aaganum na athayum enable or disable panikira mathiri
    settings application kulayum irukum"* — the same choice lives in Settings.

What this test refuses to let slide:

  1. the two answers are not independent switches: "voice" means the microphone **and**
     a startup entry, and setup says so;
  2. choosing "icon" leaves nothing running and nothing listening;
  3. a machine that cannot listen is never told it will;
  4. the derived mode comes from the real flags, not from what was intended;
  5. Settings shows the same choice and writes the same two flags;
  6. switching back to icon really turns the ears off — no half state.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_openmode.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-openmode-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from arcdesk import autostart, config, firstrun  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<56} {str(got)[:32]!r}")
    ok &= bool(good)


# a fake startup entry, so the test never touches the real registry
START = {"on": False}
autostart.set_enabled = lambda v: START.__setitem__("on", bool(v)) or True
autostart.is_enabled = lambda: START["on"]

print("\n1) the question has two answers, and the default is the quiet one")
cfg = config.load()
check("modes defined", firstrun.OPEN_MODES, ("icon", "voice"))
check("a fresh install opens by icon", firstrun.mode_of(cfg), "icon")
check("answers_from reports both flags", sorted(firstrun.answers_from(cfg)),
      ["autostart", "documents", "voice", "wake"])

print("\n2) 'voice' means microphone AND startup — not one of them")
derived = firstrun.set_mode(cfg, "voice", can_listen=True)
check("wake on", derived["wake"], True)
check("autostart on", derived["autostart"], True)
check("mode recorded", derived["open_mode"], "voice")
res = firstrun.apply(cfg, {"open_mode": "voice", "can_listen": True})
check("settings saved", res["saved"], True)
check("wake enabled in settings", cfg["wake"]["enabled"], True)
check("startup entry created", START["on"], True)
check("mode reads back as voice", res["state"]["open_mode"], "voice")
check("the console line says how it opens",
      'voice — "hey jarvis"' in firstrun.summary(res), True)
check("nothing warned when it all worked", res["warnings"], [])

print("\n3) 'icon' turns everything off, and leaves nothing listening")
res = firstrun.apply(cfg, {"open_mode": "icon", "can_listen": True})
check("wake off", cfg["wake"]["enabled"], False)
check("startup entry removed", START["on"], False)
check("mode reads back as icon", res["state"]["open_mode"], "icon")
check("console says icon", "desktop icon" in firstrun.summary(res), True)

print("\n4) a machine that cannot listen is not promised a voice")
derived = firstrun.set_mode(cfg, "voice", can_listen=False)
check("downgraded to icon", derived["open_mode"], "icon")
check("wake stays off", derived["wake"], False)
check("and it warns", "cannot listen" in derived["warnings"][0], True)
res = firstrun.apply(cfg, {"open_mode": "voice", "can_listen": False})
check("apply downgrades too", cfg["wake"]["enabled"], False)
check("warning surfaced to the console", any("cannot listen" in w for w in res["warnings"]),
      True)

print("\n5) the mode is derived from reality, not from the wish")
cfg2 = json.loads(json.dumps(config.DEFAULTS))
cfg2["wake"]["enabled"] = True
START["on"] = False
check("wake on but no startup entry -> icon", firstrun.mode_of(cfg2), "icon")
START["on"] = True
check("both -> voice", firstrun.mode_of(cfg2), "voice")
cfg2["wake"]["enabled"] = False
check("startup but no mic -> icon", firstrun.mode_of(cfg2), "icon")

print("\n6) Settings offers the same choice and writes the same flags")
app = QApplication.instance() or QApplication([sys.argv[0]])
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.settings import SettingsDialog  # noqa: E402

START["on"] = False
cfg3 = json.loads(json.dumps(config.DEFAULTS))
cfg3["wake"]["enabled"] = False
dlg = SettingsDialog(cfg3, get_theme("chill"))
check("starts on icon", dlg.mode_icon.isChecked(), True)
check("microphone box follows it", dlg.wake_on.isChecked(), False)
dlg.mode_voice.setChecked(True)
check("choosing voice arms the mic box", dlg.wake_on.isChecked(), True)
check("and the startup box", dlg.autostart_on.isChecked(), True)
check("the hint explains the cost", "Microphone stays open" in dlg.mode_hint.text(), True)
dlg._save()
check("saved wake", cfg3["wake"]["enabled"], True)
check("saved open_mode", cfg3.get("open_mode"), "voice")
check("startup entry created by settings", START["on"], True)

dlg2 = SettingsDialog(cfg3, get_theme("chill"))
check("reopening shows voice", dlg2.mode_voice.isChecked(), True)
dlg2.mode_icon.setChecked(True)
dlg2._save()
check("switching back turns the mic off", cfg3["wake"]["enabled"], False)
check("...and removes the startup entry", START["on"], False)
check("...and records icon mode", cfg3.get("open_mode"), "icon")
check("no half state: one flag cannot be on alone", firstrun.mode_of(cfg3), "icon")

print("\n7) the voice-lock switch lives here too")
check("lock checkbox exists", hasattr(dlg2, "lock_on"), True)
check("lock is off on a fresh install", dlg2.lock_on.isChecked(), False)
check("lock status is honest", "engine" in dlg2.lock_status.text().lower() or
      "enrolled" in dlg2.lock_status.text().lower(), True)
check("there is a button to enrol from the app", hasattr(dlg2, "open_voice_lock"), True)

print("\n" + ("ALL PASS" if ok else "SOMETHING FAILED"))
sys.exit(0 if ok else 1)
