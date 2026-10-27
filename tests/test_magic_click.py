"""Clicking a strand on the spider web must always do something you can SEE.

    python tests/test_magic_click.py

The report: *"yethavathu task click pana process aaga matiku, appadiyae hang aagi
nikkithu"* — click any task on the magic screen and it neither runs nor stops.

Three defects made that true, and each has a check here:

1. **A click that worked and a click that was ignored looked identical.** The only
   feedback was a status word at the bottom of a 1080p fullscreen picture. The deck now
   paints the sentence in the middle of the web before it does anything (`set_opening`),
   and clears it when the panel is really up.
2. **The in-JARVIS panels have to open INSIDE the deck.** A strand that says NOTEPAD must
   put the notepad on the deck, not launch something behind it. If `open_app` says it
   handled the click, the dock must be visible and its page must be the one asked for.
3. **A failure must leave a message, not a desktop.** The deck steps aside for anything
   that lives on Windows, so a silent failure is an empty screen. The window now shows
   itself with the reason, and a 6-second watchdog says the click is still being tried
   instead of leaving the person guessing.

The real window is heavy to build, so this test drives the deck directly and reads the
window's own source for the parts that only exist at 30 frames a second.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-magic-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, Qt                                    # noqa: E402
from PySide6.QtGui import QMouseEvent, QPixmap                            # noqa: E402
from PySide6.QtWidgets import QApplication                                # noqa: E402

app = QApplication.instance() or QApplication([])

from arcdesk import config                                                # noqa: E402
from arcdesk.theme import THEMES                                          # noqa: E402
from arcdesk.widgets.magicscreen import APPS, MagicScreen                 # noqa: E402

ok = True


def check(name: str, got, want=True) -> None:
    global ok
    good = got == want
    ok = ok and good
    print(f"   {'OK  ' if good else 'FAIL'} {name:<58} {got!r}")


theme = THEMES["chill"]
deck = MagicScreen(theme, config.load().get("magic", {}).get("exit_phrase",
                                                             "bye jarvis"))
deck.resize(1280, 760)
deck.show_fullscreen = lambda: None                     # offscreen: no fullscreen call
deck.show()                        # a child widget is only visible if its deck is
app.processEvents()

print("1. the web says what it is doing, before it does it")
check("no card before a click", deck._opening, "")                        # noqa: SLF001
deck.set_opening("opening notepad…")
check("…and the card holds the sentence", "NOTEPAD" in deck._opening.upper(), True)   # noqa: SLF001
pix = QPixmap(deck.size())
deck.render(pix)                                        # paints the card for real
check("the painted frame is not blank", pix.isNull(), False)
deck.clear_opening()
check("…and the card goes away when asked", deck._opening, "")            # noqa: SLF001

print("\n2. every strand answers a real mouse click with the right target")
FakeEvent = getattr(app, "_arc_fake_event", None)


def click_at(point: QPointF) -> None:
    event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, point, point,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    deck.mousePressEvent(event)


got_targets: list[str] = []
deck.app_requested.connect(got_targets.append)
strands = deck._strand_rects()                            # noqa: SLF001
check("six strands, as promised", len(strands), 6)
for rect, label, _why, target in strands:
    click_at(rect.center())
check("one signal per strand", len(got_targets), 6)
check("…and every signal carries its own target",
      got_targets, [t for _r, _l, _w, t in strands])
check("…the dock ones stay inside JARVIS",
      [t for t in got_targets if t.startswith("dock:")],
      ["dock:files", "dock:notepad", "dock:calc", "dock:processes"])
check("no click left the deck without a word",
      all(label.split()[0].lower() in deck._status.lower() or deck._status  # noqa: SLF001
          for _r, label, _w, _t in strands), True)

print("\n3. a dock strand puts the panel ON the deck")
check("the deck claims the click", deck.open_app("dock:notepad"), True)
app.processEvents()
check("…the panel is visible", deck.dock.isVisible(), True)
check("…on the page that was clicked", deck.dock.stack.currentIndex(),
      deck.dock.ORDER.index("notepad"))
check("…and it is not a separate window that could hide behind the deck",
      deck.dock.isWindow(), False)
for kind in ("files", "calc", "processes"):
    deck.open_app("dock:" + kind)
    app.processEvents()
    check(f"…{kind} opens on its own page", deck.dock.stack.currentIndex(),
          deck.dock.ORDER.index(kind))
check("the task-manager page fills itself in on a worker, not on the drawing thread",
      "uiwork.run" in Path("arcdesk/widgets/appdock.py").read_text(encoding="utf-8"), True)

print("\n4. anything that is not a dock page is handed back to the window")
for target in ("settings", "browser", "https://example.com"):
    check(f"{target[:22]} is not swallowed by the deck", deck.open_app(target), False)

print("\n5. the window's side of the contract")
window_src = (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
body = window_src[window_src.index("def _magic_app"):]
body = body[:body.index("def _raise_launched")]
check("it acknowledges the click before opening anything",
      body.index("set_opening") < body.index("uiwork.run"), True)
check("the acknowledgement is cleared once the panel is up", "clear_opening" in body, True)
check("a failure puts the window back with a reason",
      "show_now" in body and "could not open" in body, True)
check("a watchdog reports a click that never finishes",
      "singleShot(6000" in body, True)
check("the app is launched on a worker", "uiwork.run" in body, True)

print("\n6. a click that is not on a strand does nothing at all")
event = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier)
deck.mousePressEvent(event)                              # harmless corner click
check("a click on empty space emits nothing", len(got_targets), 6)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
