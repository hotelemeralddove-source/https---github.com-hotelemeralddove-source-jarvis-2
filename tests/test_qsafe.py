"""The crash the person sent must not be able to happen again

    python tests/test_qsafe.py

fault.log said:

    Windows fatal exception: code 0xc0000374        (heap corruption)
    Current thread … settings.py in open_ears
    CRITICAL qt  QThread: Destroyed while thread '' is still running

A `QThread` destroyed while it runs is a use-after-free in C++; the abort lands wherever
the next allocation happens, which is why it looked like "every option closes the app".
This test closes the exact doors that were open:

    close a download window while its thread is running  -> the thread must stop or be
                                                            left parentless and referenced,
                                                            and the app must keep standing
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
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-qsafe-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QThread, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {str(got)[:42]!r}")
    if not same:
        print(f"        expected {want!r}")


def pump(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(max(1, int(seconds * 1000)), loop.quit)
    loop.exec()


from arcdesk import config  # noqa: E402
from arcdesk.widgets import qsafe  # noqa: E402


class _Sleeper(QThread):
    """Stands in for a real download: runs until cancelled, exactly like the real ones."""
    def __init__(self) -> None:
        super().__init__()
        self.cancel = threading.Event()

    def stop(self) -> None:
        self.cancel.set()

    def run(self) -> None:
        self.cancel.wait(30)


print("\n1. closing the window while the worker runs")
from arcdesk.widgets.ears_dialog import EarsDialog  # noqa: E402
from arcdesk.widgets.brain_dialog import BrainDialog  # noqa: E402

cfg = config.load()
dlg = EarsDialog(None, parent=None)
w = _Sleeper()
w.finished.connect(lambda w=w: qsafe.unregister(w))          # what _start() does
qsafe.register(w)
dlg._worker = w
w.start()
pump(0.3)
check("the worker is running", w.isRunning(), True)
check("…and registered", qsafe.count() >= 1, True)

dlg.reject()                                                 # the crash was exactly this line
pump(0.5)
check("the app is still standing", True, True)
check("the worker stopped with the window", w.isRunning(), False)
check("the registry is empty", qsafe.count(), 0)
dlg.deleteLater()

print("\n2. the same door, on the brain window")
dlg2 = BrainDialog(cfg)
w2 = _Sleeper()
w2.finished.connect(lambda w=w2: qsafe.unregister(w2))
qsafe.register(w2)
dlg2._worker = w2
w2.start()
pump(0.3)
check("the worker is running", w2.isRunning(), True)
dlg2.close()
pump(0.5)
check("…and it stopped when the window closed", w2.isRunning(), False)
check("the app is still standing", True, True)
dlg2.deleteLater()

print("\n3. a worker that refuses to stop is left alone, not destroyed")
class _Stubborn(QThread):
    """Ignores its stop request: the guard must give up, not kill it."""
    def __init__(self) -> None:
        super().__init__()
        self._kill = threading.Event()

    def stop(self) -> None:
        pass                                                 # deliberately does not stop

    def run(self) -> None:
        while not self._kill.wait(0.1):
            pass


w3 = _Stubborn()
qsafe.register(w3)
w3.start()
pump(0.2)
qsafe.stop_worker(w3, wait_ms=300)                          # gives up after 0.3 s
pump(0.3)
check("it was not killed (killing is the abort)", not w3.isFinished(), True)
check("…so it is still referenced and cannot free its own memory",
      qsafe.count() >= 1, True)
w3._kill.set()
w3.wait(2000)
qsafe.unregister(w3)
pump(0.2)
check("…and it goes away cleanly when it can", w3.isFinished(), True)

print("\n4. the dialogs really do route through the guard")
ears_src = (ROOT / "arcdesk" / "widgets" / "ears_dialog.py").read_text(encoding="utf-8")
brain_src = (ROOT / "arcdesk" / "widgets" / "brain_dialog.py").read_text(encoding="utf-8")
check("EarsDialog.closeEvent stops the worker first", "qsafe.shut" in ears_src, True)
check("EarsDialog.reject does too", ears_src.count("qsafe.shut") >= 2, True)
check("the ears worker is parentless", "w = _Worker()\n" in ears_src, True)
check("BrainDialog.closeEvent stops the worker first", "qsafe.shut" in brain_src, True)
check("…and its reject does", brain_src.count("qsafe.shut") >= 2, True)
check("the brain worker is parentless", '_Worker("install", self._key())' in brain_src, True)

print("\n5. the brain worker does not size itself")
# the old code called make_fit(self, …) inside _Worker.__init__, where self is a QThread.
import re  # noqa: E402
init_block = re.search(r"class _Worker\(QThread\):(.*?)class BrainDialog", brain_src, re.S).group(1)
check("no make_fit call inside the QThread",
      re.search(r"^\s+make_fit\(", init_block, re.M) is None, True)
check("…sizing happens on the dialog", "make_fit(self, preferred=(800, 660)" in brain_src, True)

print("\n6. 'hear the reply voice' hops threads with a signal, not a timer")
set_src = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
hear_block = re.search(r"def _hear_reply\(self\).*?(?=\n    def )", set_src, re.S).group(0)
check("no QTimer.singleShot call inside the worker closure",
      re.search(r"QTimer\.singleShot\s*\(", hear_block) is None, True)
check("…a signal carries the answer back", "self.heard_ready.emit(line)" in hear_block, True)
check("…and the dialog listens for it", "self.heard_ready.connect(self._heard)" in set_src, True)

print("\n7. the app quit path stops every worker")
run_src = (ROOT / "run.py").read_text(encoding="utf-8")
check("aboutToQuit stops the shared registry",
      "qsafe.stop_all()" in run_src, True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
