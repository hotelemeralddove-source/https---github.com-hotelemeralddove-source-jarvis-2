"""Speed, clarity and the work you can see.

Three complaints, three measurements:

  1. "speed ah pesuthu, ena solluthu nu puriyala" — the voice ran at SAPI rate +1 and
     was handed one long string. Now: a slower default, a breath between sentences and
     SSML the engine can actually pace. Checked here: the document is valid XML, it
     carries the rate, and it really has breaks between sentences.
  2. "holo ok, aana ena work nadakutho theriyala" — the magic screen now draws the
     activity record. Checked: a request and its steps appear on screen.
  3. "romba lag aaguthu" — measured, then fixed: heavy modules no longer load until they
     are used, and the full-screen hologram halves its own work when a machine is behind.
     Checked: those modules are absent from sys.modules after a window import, and the
     quality governor steps down and back up.

Run:  python tests/test_perf.py
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-perf-test-")
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication                              # noqa: E402

app = QApplication.instance() or QApplication(sys.argv[:1])

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    ok &= bool(good)


print("1. the voice is slower, clearer, and paced like a person")
from arcdesk.ai import voice                                            # noqa: E402
from arcdesk import config                                              # noqa: E402

cfg = config.load()
check("the default rate is unhurried (-2, was +1)",
      voice.sapi_rate(cfg["ai"].get("voice_rate", voice.DEFAULT_RATE)), -2)
check("a rate of 0 is still available for people who like it", voice.sapi_rate(0), 0)
check("an absurd setting is clamped, not obeyed", voice.sapi_rate(99), 10)

doc = voice.ssml("Hello commander. The report is ready. Shall I open it?",
                 rate=-2, pause_ms=180, lang="en-IN")
ET.fromstring(doc)                                   # raises if it is not valid XML
check("the SSML document is valid XML", True)
check("it carries the slower rate", 'rate="-24%"' in doc)
check("it puts a breath between sentences", doc.count("<break") >= 2)
check("…and the breath is the configured length", 'time="180ms"' in doc)
check("SAPI gets a full language tag", voice._sapi_lang("ta"), "ta-IN")
check("text is XML-escaped, not pasted", "&lt;" in voice.ssml("a < b"))
check("a sentence per chunk, not one long breath",
      len(voice.chunks("One. Two. Three. Four.")), 4)

print("\n2. it picks the right accent among the installed voices")
installed = ["Microsoft David Desktop", "Microsoft Heera - English (India)",
             "Microsoft Kalpana - English (India)"]
check("Indian English wins over American", voice.pick_voice(installed, "en-IN"),
      "Microsoft Heera - English (India)")
check("a name set in Settings wins over both",
      voice.pick_voice(installed, "en-IN", "Microsoft David Desktop"),
      "Microsoft David Desktop")
check("no match means the engine's own voice, not a wrong accent forced",
      voice.pick_voice(["Microsoft David Desktop"], "ta-IN"), "")

print("\n3. the magic screen shows what JARVIS is doing")
from arcdesk import activity                                            # noqa: E402
from arcdesk.theme import THEMES                                        # noqa: E402
from arcdesk.widgets.magicscreen import MagicScreen                     # noqa: E402

theme = THEMES.get(cfg.get("mode"), next(iter(THEMES.values())))
screen = MagicScreen(theme)
screen.resize(1366, 768)
act = activity.activity()
act.begin("clean my downloads folder")
act.step("tool · list_downloads")
act.note("42 files")
screen._poll_work()
check("the request is on screen", "CLEAN MY DOWNLOADS FOLDER" in screen._status)
check("…and the step in progress", "list_downloads" in screen._now)
act.step("tool · move_files")
screen._poll_work()
check("a finished step stays in the list", any("list_downloads" in s for s in screen._work))
check("it paints without raising", bool(screen.grab()))

print("\n4. the expensive things do not load until they are needed")
mods_before = set(sys.modules)
importlib.import_module("arcdesk.widgets.window")                        # noqa: F401
new = set(sys.modules) - mods_before
check("importing the window does not drag in Pillow", "PIL" in new, False)
check("…nor numpy", "numpy" in new, False)
check("…nor the whole accessibility layer", "arcdesk.uia" in new, False)
check("…nor smtplib (lazy in comms)", "smtplib" in new, False)
check("what it does import is small enough to start quickly", len(new) < 400)

from arcdesk.ai import tools                                            # noqa: E402
check("the tools module still provides its tools", len(tools.TOOLS) > 40)
check("and the lazy helpers resolve", callable(tools._vision) and callable(tools._uia))

print("\n5. a slow machine gets a cheaper hologram, and it comes back")
from arcdesk.widgets.holo import HoloDeck                               # noqa: E402

deck = HoloDeck(theme)
deck.resize(1920, 1080)


def frame_ms(frames: int = 3) -> float:
    deck.grab()
    t = time.time()
    for _ in range(frames):
        deck.grab()
    return (time.time() - t) / frames * 1000


full = frame_ms()
deck.note_load(0.9)
deck.note_load(0.9)
check("sustained load lowers the render quality", deck.quality, 0.6)
cheap = frame_ms()
check(f"…and it is cheaper ({full:.1f} ms -> {cheap:.1f} ms)", cheap < full)
deck.note_load(0.1)
deck.note_load(0.1)
deck.note_load(0.1)
check("when the machine catches up, full quality returns", deck.quality, 1.0)

print("\n6. the apps on the magic screen open INSIDE the deck")
from arcdesk.widgets.appdock import AppDock, _Calc                           # noqa: E402

dock = AppDock(theme)
check("the dock starts closed", dock.isVisible(), False)
dock.open("notepad")
check("notepad opens in the dock", dock.isVisible() and dock.title.text(), "NOTEPAD")
dock.open("processes")
check("the process list fills itself", bool(dock._pages["processes"].lines.toPlainText()))

calc = _Calc(theme)
check("arithmetic is right", calc.evaluate("12*8"), "96")
check("brackets are honoured", calc.evaluate("(2+3)*4"), "20")
check("a float that is whole prints as an int", calc.evaluate("10/2"), "5")
check("dividing by zero is explained, not crashed", calc.evaluate("1/0"),
      "cannot divide by zero")
check("it cannot be talked into running code", calc.evaluate("__import__('os')"), "")

print("\n7. magic mode appears at once, and its tiles are owned or raised")
from arcdesk.widgets.magicscreen import APPS as MAGIC_APPS                  # noqa: E402

targets = {label: target for label, target in MAGIC_APPS}
check("notepad is an in-deck app, not a Windows launch",
      targets.get("NOTEPAD"), "dock:notepad")
check("calc, files and task manager too",
      [targets.get(k) for k in ("CALC", "FILES", "TASK MGR")],
      ["dock:calc", "dock:files", "dock:processes"])
check("the browser still goes to Windows (it must)", targets.get("BROWSER", "").startswith("http"))

src = (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
check("the wallpaper no longer blocks the screen",
      src.index("self._magic_screen.show_fullscreen()")
      < src.index("self._magic_wallpaper_async()"))
check("a launched Windows app is raised over the fullscreen deck",
      "_raise_launched" in src and "_actions.windows(\"focus\"" in src)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
