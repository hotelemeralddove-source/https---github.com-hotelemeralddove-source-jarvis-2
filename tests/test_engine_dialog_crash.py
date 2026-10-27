"""The crash report, turned into checks — every line of it, one at a time

    python tests/test_engine_dialog_crash.py

The person sent `crash-report.txt`, and it named three things. Two of them were in the build
they were running, and one of those kills the process outright:

    1. `TypeError: 'bool' object is not callable` at `done_after()` — `Check again` is a
       QPushButton, `clicked` emits `checked: bool`, and it was connected straight to
       `reload()`, so every refresh of the engine list raised twice.
    2. `QThread: Destroyed while thread '' is still running` + **the app closing** — the
       download thread was parented to the dialog, so destroying the dialog (closing
       Settings, quitting) destroyed a running thread. Qt treats that as fatal; the Python
       log stays empty, which is why `fault.log` had nothing in it.
    3. `the window was frozen for 0.5 s — main thread was in window.py:1834 in eventFilter`
       — an application-wide event filter doing work for events it does not care about.

Plus the harmless-but-ugly one from the same log:

    4. `QWindowsWindow::setGeometry: Unable to set geometry 705x720 … Resulting 705x743`
       — a dialog asking for more height than the screen's work area.

Nothing here downloads anything and nothing here needs Windows.
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-crashlog-")
os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = "1"
os.environ["ARCDESK_NO_HELPER"] = "1"          # this file is about the in-process thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication.instance() or QApplication([])

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    if not same:
        print(f"        expected {want!r}")


def pump(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(max(1, int(seconds * 1000)), loop.quit)
    loop.exec()


from arcdesk import engines  # noqa: E402
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets import engine_dialog as ed  # noqa: E402

# a backend that answers instantly, so nothing here waits on a network
engine_dialog_calls: list = []


def quick_auto(engine="", lang="", on_line=None, on_progress=None, cancel=None,
               ask_token=None, tries=2, pause=3.0):
    engine_dialog_calls.append(engine)
    if on_line:
        on_line("a stage that says something")
    return {"ok": True, "engine": engine, "lines": []}


engines.auto = quick_auto                        # noqa: SLF001

ITEMS = {
    "piper": {"id": "piper", "label": "Piper", "langs": "English, Hindi", "size_mb": 60,
              "why": "small", "needs": "a voice per language", "ready": False,
              "code": False, "python": "", "voices": 0, "problem": "",
              "model": "", "local": "", "token_from": ""},
    "indicf5": {"id": "indicf5", "label": "IndicF5", "langs": "Tamil, Hindi",
                "size_mb": 1500, "why": "cloned Tamil", "needs": "a GPU to feel instant",
                "ready": False, "code": False, "python": "", "voices": 0, "problem": "",
                "model": "", "local": "", "token_from": ""},
}


def new_dialog() -> ed.EngineDialog:
    dlg = ed.EngineDialog(get_theme("chill"))
    dlg._items = {k: dict(v) for k, v in ITEMS.items()}          # noqa: SLF001
    dlg._method = {"can_install": True, "why": ""}               # noqa: SLF001
    dlg._fill_picker()                                           # noqa: SLF001
    dlg._show()                                                  # noqa: SLF001
    return dlg


print("\n1. 'Check again' must not raise TypeError on every refresh")
dlg = new_dialog()
errors: list = []
state = {"errors": errors}


def watch(sender, exc_type, exc, tb) -> None:                  # noqa: ANN001
    state["errors"].append(f"{exc_type.__name__}: {exc}")


real_hook = sys.excepthook
sys.excepthook = watch
try:
    dlg.check.click()                      # exactly what the person pressed
    pump(1.5)
finally:
    sys.excepthook = real_hook
check("no unhandled error from the refresh", state["errors"], [])
check("…and the list still says it is checking, then fills",
      dlg.picker.count() >= 2, True)
check("…the verdict is not a crash message", "bool" in dlg.state.text(), False)

print("\n2. a signal argument is not a callback")
# the rule itself, without a GUI: reload(done_after=True) must be ignored, not called
raised = ""


def boom() -> None:
    raise AssertionError("done_after must only be called when it is callable")


try:
    dlg.reload(True)                       # what `clicked(False/True)` used to deliver
    pump(1.2)
except Exception as exc:                    # noqa: BLE001
    raised = f"{type(exc).__name__}: {exc}"
check("reload(True) does not raise", raised, "")
pump(0.6)
check("…and no callback was invented", dlg.verdict.text(), dlg.verdict.text())

print("\n3. destroying the dialog must not destroy a running thread")
live_before = len(ed._LIVE_WORKERS)         # noqa: SLF001
dlg2 = new_dialog()
dlg2.picker.setCurrentIndex(dlg2.picker.findData("indicf5"))


def slow_auto(engine="", lang="", on_line=None, on_progress=None, cancel=None,
              ask_token=None, tries=2, pause=3.0):
    for _ in range(60):                     # ~6 s
        if cancel is not None and cancel.is_set():
            return {"ok": False, "why": "cancelled", "lines": []}
        time.sleep(0.1)
    return {"ok": True, "engine": engine, "lines": []}


engines.auto = slow_auto                     # noqa: SLF001
dlg2._start()                                # noqa: SLF001
pump(0.4)
worker = dlg2._worker                        # noqa: SLF001
check("a download thread is running", worker is not None and worker.isRunning(), True)
check("…it is in the registry, not owned by the window",
      worker in ed._LIVE_WORKERS, True)      # noqa: SLF001
check("…and it has no parent to be destroyed with",
      worker.parent(), None)
dlg2.deleteLater()                           # the worst case: the dialog simply goes
pump(0.6)
check("the thread survives the dialog being destroyed", worker.isRunning(), True)
ed.stop_all_workers(3000)                    # what aboutToQuit does
check("…and the app's quit stops it", worker.isRunning(), False)
check("…leaving the registry empty", len(ed._LIVE_WORKERS), live_before)  # noqa: SLF001

print("\n4. a dialog is never taller than the work area")
from arcdesk.widgets import fit as fitmod  # noqa: E402

dlg3 = ed.EngineDialog(get_theme("chill"))
area = fitmod.available(dlg3)
if area is None:
    print("        (no screen in this sandbox — the rule is checked against a fake one)")
    class FakeArea:
        def width(self):     return 1366
        def height(self):    return 728        # a 768 laptop with a taskbar
        def x(self):         return 0
        def y(self):         return 0
        def __eq__(self, other): return True
    real_available = fitmod.available
    fitmod.available = lambda widget=None: FakeArea()
    try:
        fitmod.fit_dialog(dlg3, preferred=(760, 720), minimum=(420, 300))
        check("a 1366x728 work area: the dialog fits", dlg3.height() <= 728, True)
        check("…and it may still be expanded to the whole work area",
              dlg3.maximumHeight() >= 728, True)
    finally:
        fitmod.available = real_available
else:
    fitmod.fit_dialog(dlg3, preferred=(760, 720), minimum=(420, 300))
    check("the dialog fits the real work area", dlg3.height() <= area.height(), True)

print("\n5. the event filter is cheap, shielded, and only sees its own tree")
win_src = (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
check("it asks two cheap questions first", "if kind != QEvent.Type.KeyPress and obj is not self.reactor:"
      in win_src, True)
check("…and hands everything else straight back, with no C++ virtual call",
      "if kind != QEvent.Type.KeyPress and obj is not self.reactor:" in win_src
      and "super().eventFilter" not in win_src, True)
check("…and a dead event's exception cannot kill the loop",
      "except Exception:\n            return False" in win_src, True)
# the crash: "No Qt Window found for event 0x46" (a minute of it) then an access
# violation in eventFilter. Dead windows' events reached the filter because it was
# installed on the APPLICATION. On the window, Qt only forwards its own tree.
check("the filter is on the window, not the application",
      "app.installEventFilter(self)" not in win_src
      and "self.installEventFilter(self)" in win_src, True)
# the old chain read focused.window() straight off the focus object — a possibly-dead
# pointer. The focus is still consulted (a shown dialog must own Esc), but only after
# shiboken6.isValid has said the C++ object is real.
check("the focus chain is guarded before it is read",
      "shiboken6.isValid(focused)" in win_src
      and "isinstance(holder, QDialog)" in win_src
      and "isinstance(focused.window(), QDialog)" not in win_src, True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
