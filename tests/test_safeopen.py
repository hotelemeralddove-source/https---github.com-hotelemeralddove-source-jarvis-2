"""A window that fails must not be the last thing JARVIS does

    python tests/test_safeopen.py

Every option in the app closes through `safeopen.open_dialog()`. This file makes a dialog that
raises in its CONSTRUCTOR (the crash the person sent was exactly that — a constructor, not
`exec()`), one that raises while it is open, and one whose worker thread raises, and checks
that in all three cases:

    the app is still standing, the reason was written down, and the person is told in words
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
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-safeopen-")

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
    print(f"   {'OK  ' if same else 'FAIL'} {label:<56} {str(got)[:44]!r}")
    if not same:
        print(f"        expected {want!r}")


def pump(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(max(1, int(seconds * 1000)), loop.quit)
    loop.exec()


def auto_close(widget, after_ms: int = 600) -> None:
    """Close a modal window from the outside — the same thing Esc does for a person.

    A modal `exec()` that nothing closes blocks the test exactly as it would block a person;
    these windows are closed on a timer so the run cannot hang.
    """
    def shut() -> None:
        try:
            if widget is not None and widget.isVisible():
                widget.reject() if hasattr(widget, "reject") else widget.close()
        except Exception:                                    # noqa: BLE001
            pass
        for w in app.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible() and w.isModal():
                w.reject()
    QTimer.singleShot(after_ms, shut)


from arcdesk.widgets import safeopen  # noqa: E402


def boom_build() -> QDialog:
    raise RuntimeError("a widget this dialog needs is not there")


def boom_later() -> QDialog:
    dlg = QDialog()
    QTimer.singleShot(100, lambda: (_ for _ in ()).throw(RuntimeError("raised on screen")))
    return dlg


def thread_boom() -> QDialog:
    dlg = QDialog()

    def worker() -> None:
        time.sleep(0.15)
        raise ValueError("a worker thread inside the dialog")

    threading.Thread(target=worker, daemon=True).start()
    return dlg


print("\n1. a dialog whose CONSTRUCTOR raises")
# the modal warning box would block a headless run: watch for it instead of clicking it
shown: list[str] = []
import arcdesk.widgets.safeopen as so  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

real_exec = QMessageBox.exec


def fake_exec(self) -> int:
    shown.append(self.text())
    return int(QMessageBox.StandardButton.Ok)


QMessageBox.exec = fake_exec
QTimer.singleShot(0, lambda: None)
result = safeopen.open_dialog("Settings", boom_build)
pump(0.2)
check("it returns nothing instead of taking the app with it", result, None)
check("the reason is remembered", len(safeopen.last_failures()) >= 1, True)
check("…and the last one names the real error",
      "is not there" in safeopen.last_failures()[-1], True)
check("the person is told in a box", len(shown) >= 1, True)
check("…with the failing window's name in it", "Settings" in shown[-1], True)

print("\n2. a dialog that raises while it is OPEN")
shown.clear()
made: dict = {}


def build_later() -> QDialog:
    dlg = boom_later()
    made["dlg"] = dlg
    auto_close(dlg, 500)
    return dlg


safeopen.open_dialog("the AI setup", build_later)
pump(0.6)
check("the app survived an error on screen", True, True)
check("…and it was written down",
      any("raised on screen" in f for f in safeopen.last_failures()), True)

print("\n3. a dialog whose WORKER THREAD raises")
shown.clear()
before = len(safeopen.last_failures())


def build_thread_boom() -> QDialog:
    dlg = thread_boom()
    made["dlg"] = dlg
    auto_close(dlg, 500)
    return dlg


safeopen.open_dialog("the ears", build_thread_boom)
pump(0.8)
check("a background error is caught too, not printed to a console that is not there",
      len(safeopen.last_failures()) > before, True)

print("\n4. a good dialog still opens normally")
shown.clear()
good = safeopen.open_dialog("a normal window", QDialog, exec_it=False)
check("it returns the window", isinstance(good, QDialog), True)
check("…and nothing was reported", shown, [])
good.close()

print("\n5. the app's own options all go through it")
for name, needle in (
    ("window.open_settings", "open_dialog(\"Settings\""),
    ("window.open_ai_setup", "open_dialog(\"the AI setup\""),
    ("settings engine dialog", "open_dialog(\"the reply-voice engines\""),
    ("settings ears dialog", "open_dialog(\"the ears\""),
):
    folder = ROOT / "arcdesk" / "widgets"
    text = "\n".join(p.read_text(encoding="utf-8") for p in folder.glob("*.py"))
    check(f"{name} is guarded", needle in text, True)

QMessageBox.exec = real_exec
print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
