"""The event filter must survive dead windows

    python tests/test_event_filter.py

The crash:

    WARNING qt  QWindowsContext::windowsProc: No Qt Window found for event 0x46 (…), hwnd=…
    (a minute of it)
    Windows fatal exception: access violation
    File "…/window.py", line 1853 in eventFilter

Windows keeps delivering messages to windows Qt has already abandoned, and the old
application-level filter met them — one of them chasing a pointer into freed memory,
which is an access violation, not an exception. This test checks the doors the filter
now has:

  * an event whose receiver is already deleted is answered "not me", not chased
  * a deleted C++ object behind the focus is answered "not me" by a guard, not by a fault
  * a fabricated dead event cannot take the loop down
  * Esc still works: from the chat field, and inside a dialog (where the dialog wins)
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-efilter-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import shiboken6  # noqa: E402
from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit  # noqa: E402

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


def esc(target) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                      Qt.KeyboardModifier.NoModifier)
    app.sendEvent(target, event)


def key(target, keyid: int) -> None:
    event = QKeyEvent(QEvent.Type.KeyPress, keyid, Qt.KeyboardModifier.NoModifier)
    app.sendEvent(target, event)


from arcdesk import config  # noqa: E402
from arcdesk.widgets.window import MainWindow  # noqa: E402

cfg = config.load()
win = MainWindow(cfg)
win.show()
pump(0.3)
check("the window is up", win.isVisible(), True)

print("\n1. an event whose RECEIVER is already deleted is answered 'not me'")
field = QLineEdit(win)
field.show()
pump(0.2)
shiboken6.delete(field)                      # the C++ object is gone; the wrapper lingers
pump(0.2)
event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier)
# Qt's dispatch hands the filter a registered wrapper for the dead object (no Python
# conversion to raise first) — calling the Python override directly reproduces exactly
# that: a live event, a deleted receiver, the body to decide.
try:
    result = type(win).eventFilter(win, field, event)
    raised = False
except Exception as exc:                     # noqa: BLE001
    raised = True
    print("        raised:", exc)
check("no exception chasing the dead receiver", raised, False)
check("…and the event was passed on", result, False)
check("JARVIS is still standing", win.isVisible(), True)

print("\n2. a deleted C++ object behind the focus is guarded, not fatal")
win.show()
pump(0.2)
field2 = QLineEdit(win)
field2.show()
win.activateWindow()
field2.setFocus()
pump(0.2)
shiboken6.delete(field2)                     # C++ gone, a stale pointer may remain
pump(0.2)
real_focus = app.focusWidget
app.focusWidget = lambda: field2             # Qt still points at the dead object
try:
    esc(win)
    raised = False
except Exception as exc:                     # noqa: BLE001
    raised = True
    print("        raised:", exc)
finally:
    app.focusWidget = real_focus
pump(0.3)
check("no exception from a dead focus object", raised, False)
check("…and the filter did its job (Esc still means hide)", win.isVisible(), False)

print("\n3. Esc from the chat field hides the window, as before")
win.show()
pump(0.2)
try:
    win.console.focus_input()
    pump(0.1)
    focused = app.focusWidget()
    if focused is not None:
        esc(focused)
    else:
        esc(win)
    pump(0.3)
    from_chat = not win.isVisible()
except Exception as exc:                     # noqa: BLE001
    print("        raised:", exc)
    from_chat = False
check("Esc from the focused field hides JARVIS", from_chat, True)

print("\n4. inside a dialog, the dialog owns Esc")
win.show()
pump(0.2)
dlg = QDialog(win)
inner = QLineEdit(dlg)
inner.show()
dlg.setModal(True)
dlg.show()
inner.setFocus()
pump(0.3)
esc(inner)
pump(0.3)
check("…the dialog closed itself", dlg.isVisible(), False)
check("…and JARVIS was not hidden underneath", win.isVisible(), True)

print("\n5. a fabricated dead event cannot take the loop down")
class _DeadEvent:
    def type(self):
        raise RuntimeError("Internal C++ object (QEvent) already deleted")


result = type(win).eventFilter(win, win, _DeadEvent())
check("the filter returns False, not an exception", result, False)

print("\n6. the source keeps its doors")
src = (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
check("…installed on the window, not the application",
      "app.installEventFilter(self)" not in src, True)
check("…guards with shiboken6.isValid", src.count("shiboken6.isValid") >= 3, True)
check("…and shields the whole body",
      "except Exception:\n            return False" in src, True)
check("…and still asks the two cheap questions first",
      "if kind != QEvent.Type.KeyPress and obj is not self.reactor:" in src, True)
check("…and the hot path makes no C virtual call (no super().eventFilter)",
      "super().eventFilter" not in src, True)

win.close()
print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
