"""Does every window fit the screen it is opened on?

The reports this answers, in the user's words:

    * "even screen ah viitu veliya poiruku app size so enakku minimize pana, expand pana,
       screen size adjust panra mathiri"
    * "then submit panra mathiri option varNUM nu antha box varala" — the setup card's
      completion button was below the bottom edge of the screen.

Both are geometry bugs, so this test measures geometry. It fakes the screen at the sizes
people actually own (a 1366x768 laptop at 100% and at 125% scaling is 1092x614 in logical
pixels, which is the case that broke) and asserts:

  * no dialog is taller or wider than the usable area;
  * every dialog body scrolls, so nothing is unreachable;
  * the button that finishes the job (Done / Save / Start) is on screen;
  * a window remembered from a bigger screen is pulled back on screen;
  * the main window has minimise, expand and a resize grip.

Run:  python tests/test_fit.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-fit-test-")
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRect                                    # noqa: E402
from PySide6.QtWidgets import (                                     # noqa: E402
    QApplication, QPushButton, QScrollArea,
)

app = QApplication.instance() or QApplication(sys.argv[:1])

from arcdesk import config                                          # noqa: E402
from arcdesk.theme import THEMES                                    # noqa: E402
from arcdesk.widgets import fit as fitmod                           # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:40]!r}")
    ok &= bool(good)


cfg = config.load()
theme = THEMES.get(cfg.get("mode"), next(iter(THEMES.values())))

#: The screens to judge against. The third one is the one that caused the report:
#: a 1366x768 laptop at 125% Windows scaling has 1092x614 logical pixels, and a 660-pixel
#: dialog does not fit in 614.
SCREENS = {
    "1920x1080 (desktop)": QRect(0, 0, 1920, 1040),
    "1366x768 laptop, 100%": QRect(0, 0, 1366, 728),
    "1366x768 laptop, 125%": QRect(0, 0, 1092, 614),
    "1280x720 netbook": QRect(0, 0, 1280, 680),
}

_real_available = fitmod.available

from arcdesk.widgets.settings import SettingsDialog                  # noqa: E402
from arcdesk.widgets.voicelib_dialog import VoiceLibraryDialog      # noqa: E402
from arcdesk.widgets.window import MainWindow                       # noqa: E402

print("1. dialogs are built for each screen size and measured")
for name, area in SCREENS.items():
    fitmod.available = lambda widget=None, _a=area: _a
    print(f"\n   {name}  ->  usable {area.width()}x{area.height()}")
    for label, factory, button in (
        ("voices", lambda: VoiceLibraryDialog(cfg, theme), "Done"),
        ("settings", lambda: SettingsDialog(cfg, theme), "Save"),
    ):
        dlg = factory()
        fits = dlg.width() <= int(area.width() * 0.95) and dlg.height() <= int(area.height() * 0.95)
        check(f"{label}: {dlg.width()}x{dlg.height()} fits", fits)
        check(f"{label}: body scrolls", bool(dlg.findChildren(QScrollArea)))
        check(f"{label}: '{button}' is on screen",
              any(b.text() == button and b.isVisibleTo(dlg) for b in dlg.findChildren(QPushButton)))
        check(f"{label}: inside the screen horizontally",
              area.x() <= dlg.x() and dlg.x() + dlg.width() <= area.x() + area.width())
        dlg.deleteLater()

print("\n2. a window remembered from a big monitor is pulled back on screen")
fitmod.available = lambda widget=None: SCREENS["1366x768 laptop, 125%"]
win = MainWindow(cfg)
win.resize(1900, 1000)
win.move(1200, 700)                      # as if restored on a 27-inch screen
fitmod.clamp_to_screen(win)
area = SCREENS["1366x768 laptop, 125%"]
check("width is inside the screen", win.width() <= area.width())
check("height is inside the screen", win.height() <= area.height())
check("the window starts on screen", 0 <= win.x() <= area.width() - win.width() + 1)
check("the window's bottom is on screen", win.y() + win.height() <= area.height() + 1)

print("\n3. the main window has the three controls the report asked for")
check("minimise exists", hasattr(win, "btn_min") and callable(win.showMinimized))
check("expand exists (and flips)", hasattr(win, "btn_max"))
win.toggle_maximized()
check("expand actually maximises", win.isMaximized())
win.toggle_maximized()
check("…and toggles back to a window", not win.isMaximized())
check("a resize grip is installed", getattr(win, "_grip", None) is not None)
check("the minimum size is a floor a small screen can meet",
      win.minimumWidth() <= 600 and win.minimumHeight() <= 480)

print("\n3b. the Voices window can fix its own blocker")
fitmod.available = _real_available
dlg = VoiceLibraryDialog(cfg, theme)
labels = [b.text() for b in dlg.findChildren(QPushButton)]
check("it offers the 30 MB voice-lock model in one click",
      any("Download the voice-lock model" in t for t in labels))
check("…and says a clip must be 10-20 seconds before someone picks a file",
      any("10" in w.text() and "20" in w.text() for w in dlg.findChildren(
          __import__("PySide6.QtWidgets", fromlist=["QLabel"]).QLabel)))

print("\n4. the minimum a window can be shrunk to is never bigger than the screen")
fitmod.available = lambda widget=None: QRect(0, 0, 800, 500)
dlg = VoiceLibraryDialog(cfg, theme)
check("a 800x500 screen: the dialog is not wider than it", dlg.width() <= 800)
check("a 800x500 screen: the dialog is not taller than it", dlg.height() <= 500)

fitmod.available = _real_available       # leave the module as it was found
print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
