"""Pressing Install must start a download — and the screen must never be left half-busy

    python tests/test_engine_install_starts.py

The report (26.png): the engine screen showed "installing IndicF5 · about 1500 MB…",
a 0 % bar, a live line counting seconds, Stop enabled — and nothing ever happened. Then
the whole thing looked hung.

Cause, found by pressing the button instead of reading the code:

    _Worker.__init__  ->  make_fit(self, …)      # self is a QThread, not a dialog
                      ->  scroll_body(self)     ->  self.layout()
                      ->  AttributeError: '_Worker' object has no attribute 'layout'

That raise happened on the GUI thread inside the button's slot, AFTER the progress bar was
shown and Stop was enabled, and BEFORE `w.start()`. So the bar could never move, no worker
existed, and Stop stopped nothing. Every existing test built the dialog and never pressed
Install — which is why 92 green tests shipped a dead button.

What this file refuses to let happen again:

    1. a press really starts a thread, and that thread really calls the engine backend;
    2. a raise while building or running the worker is reported on screen, with the
       buttons usable again (never a 0 % bar with no worker behind it);
    3. after the run finishes — success, failure, or Stop — the screen is usable;
    4. closing the window mid-download stops the thread instead of destroying it;
    5. silence reports itself: after a quiet minute the screen says which stage it is on.

No network, no child processes: the backend is stubbed where it is read.
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-starts-")
os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = "1"
# This file is about the IN-PROCESS route (the thread, its crash reporting, Stop, closing).
# The background helper is the default in the app and has its own file:
# tests/test_engine_background.py.
os.environ["ARCDESK_NO_HELPER"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from arcdesk import engines  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {got!r}")
    if not same:
        print(f"        expected {want!r}")


def pump(seconds: float) -> None:
    """Run the real event loop for a while (queued signals need it)."""
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets import engine_dialog as ed  # noqa: E402

# ---------------------------------------------------------------- the backend stubs
CALLS: list[dict] = []


def fake_auto(engine="", lang="", on_line=None, on_progress=None, cancel=None,
              ask_token=None, tries=2, pause=3.0):
    CALLS.append({"engine": engine, "lang": lang})
    if on_line:
        on_line("downloading the engine for ta: IndicF5 (Tamil, Hindi)")
        on_line("asking Hugging Face what ai4bharat/IndicF5 contains")
    if on_progress:
        on_progress({"percent": 12.0, "mb": 180.0, "total_mb": 1500.0,
                     "speed": "2.0 MB/s", "eta": "11:00"})
    time.sleep(0.15)
    return {"ok": True, "engine": engine, "lines": ["fine"]}


engines.auto = fake_auto                     # noqa: SLF001
engines.missing_only = lambda engine, on_line=None, on_progress=None, cancel=None: (
    CALLS.append({"engine": engine, "lang": "missing-only"})
    or {"ok": True, "engine": engine, "lines": ["fine"]})   # noqa: SLF001

print("\n1. the very bug that shipped: building the worker must not raise")
try:
    w = ed._Worker("indicf5", None, lang="ta")               # noqa: SLF001
    check("a worker can be built", isinstance(w, ed._Worker), True)
    check("…and it is not pretending to be a dialog", hasattr(w, "layout"), False)
except Exception as exc:                                     # noqa: BLE001
    check("a worker can be built", f"{type(exc).__name__}: {exc}", "no error")

print("\n2. pressing Install starts a real thread, and it reaches the engine")
dialog = ed.EngineDialog(get_theme("chill"))
pump(0.4)
if not dialog.picker.count():                                # the status worker may be slow
    pump(2.0)
dialog._items = {                                            # noqa: SLF001
    "piper": {"id": "piper", "label": "Piper", "langs": "English, Hindi", "size_mb": 60,
              "why": "small", "needs": "a voice per language", "ready": False,
              "code": False, "python": "", "voices": 0, "problem": "",
              "model": "", "local": "", "token_from": ""},
    "indicf5": {"id": "indicf5", "label": "IndicF5", "langs": "Tamil, Hindi",
                "size_mb": 1500, "why": "cloned Tamil", "needs": "a GPU to feel instant",
                "ready": False, "code": False, "python": "", "voices": 0, "problem": "",
                "model": "", "local": "", "token_from": ""},
}
dialog._method = {"can_install": True, "why": ""}            # noqa: SLF001
dialog._fill_picker()                                        # noqa: SLF001
dialog.picker.setCurrentIndex(dialog.picker.findData("indicf5"))
dialog._show()                                               # noqa: SLF001
check("the install button is usable before the press", dialog.go.isEnabled(), True)

spent_before = len(CALLS)
t0 = time.perf_counter()
dialog._start()                                              # <- the press
press_ms = (time.perf_counter() - t0) * 1000
check(f"the press returns at once ({press_ms:.0f} ms, no waiting on the UI thread)",
      press_ms < 250, True)
check("…a worker exists", dialog._worker is not None, True)  # noqa: SLF001
check("…the bar is up", dialog.bar.isVisibleTo(dialog), True)
check("…and Stop is the button that can act now", dialog.stop_btn.isEnabled(), True)
pump(1.2)
check("…and the backend was really called", len(CALLS) - spent_before, 1)
check("…with the engine that was on screen", CALLS[-1]["engine"], "indicf5")
check("…the log shows the engine's own lines", "asking Hugging Face" in dialog.log.toPlainText(), True)
check("…the bar moved off zero", dialog.bar.value() > 0, True)
check("…and the run ended with the screen usable", dialog.go.isEnabled(), True)
check("…with nothing left running", dialog._worker, None)    # noqa: SLF001
check("…and a verdict that says it worked", "Done" in dialog.verdict.text(), True)

print("\n3. the automatic button is one press too, and it never lies about the thread")
spent_before = len(CALLS)
dialog.lang.setCurrentIndex(max(0, dialog.lang.findData("ta")))
dialog._start_auto()                                         # noqa: SLF001
check("the automatic press made a worker", dialog._worker is not None, True)  # noqa: SLF001
pump(1.2)
check("…and it downloaded something", len(CALLS) - spent_before >= 1, True)
check("…then released the screen", dialog._worker, None)     # noqa: SLF001

print("\n4. a raise anywhere in the run is reported, not swallowed")
real_auto = engines.auto


def boom(*a, **k):                                           # noqa: ANN002, ANN003
    raise RuntimeError("the wire died halfway")


engines.auto = boom                                          # noqa: SLF001
try:
    # this machine may have transformers installed, which would send the press down the
    # "only the weights are missing" path (_missing_only) instead of `auto`. Pin the
    # question this section is about: a plain install whose thread raises.
    dialog._weights_only = False                             # noqa: SLF001
    dialog._items["indicf5"]["code"] = False                 # noqa: SLF001
    dialog._start()                                          # noqa: SLF001
    pump(1.5)
    verdict = dialog.verdict.text()
    check("a crash inside the thread reaches the screen", "wire died halfway" in verdict, True)
    check("…and the buttons work again", dialog.go.isEnabled(), True)
    check("…with no worker left behind", dialog._worker, None)   # noqa: SLF001
finally:
    engines.auto = real_auto                                 # noqa: SLF001

print("\n5. a press that cannot even build a worker says so, and frees the screen")
real_worker = ed._Worker


class Broken:
    def __init__(self, *a, **k):                             # noqa: ANN002, ANN003
        raise AttributeError("'_Worker' object has no attribute 'layout'")


ed._Worker = Broken                                          # noqa: SLF001
try:
    dialog.go.setEnabled(True)
    dialog._start()                                          # noqa: SLF001
finally:
    ed._Worker = real_worker                                 # noqa: SLF001
said = dialog.verdict.text()
check("the reason is on screen, in words", "could not even start" in said, True)
check("…and it names the error", "AttributeError" in said, True)
check("…the bar is gone instead of stuck at 0 %", dialog.bar.isVisibleTo(dialog), False)
check("…Stop is off, because there is nothing to stop", dialog.stop_btn.isEnabled(), False)
check("…and Install works again", dialog.go.isEnabled(), True)

print("\n6. silence reports itself instead of looking frozen")
dialog._start()                                              # noqa: SLF001
pump(1.0)
check("the run finished", dialog._worker, None)              # noqa: SLF001
dialog._start()                                              # noqa: SLF001
dialog._last_line_at = time.monotonic() - 40                 # a stage that went quiet
dialog._started = time.monotonic() - 40
dialog.verdict.setText("")
dialog._beat()                                               # noqa: SLF001
check("a quiet stage says so, with the stage it is on",
      "still working" in dialog.verdict.text(), True)
check("…and says the window is answering", "Stop cancels" in dialog.verdict.text(), True)

print("\n7. closing the window mid-download stops the thread, it does not orphan it")
real_auto2 = engines.auto


def slow(*a, **k):                                           # noqa: ANN002, ANN003
    cancel = k.get("cancel")
    for _ in range(60):
        if cancel is not None and cancel.is_set():
            return {"ok": False, "why": "cancelled", "lines": []}
        time.sleep(0.05)
    return {"ok": True, "lines": []}


engines.auto = slow                                          # noqa: SLF001
try:
    dialog._start()                                          # noqa: SLF001
    running = dialog._worker                                 # noqa: SLF001
    check("a download is running", running is not None, True)
    dialog.reject()
    check("closing stopped it", dialog._worker, None)         # noqa: SLF001
    check("…and the thread really ended", running.isRunning() if running else True, False)
finally:
    engines.auto = real_auto2                                # noqa: SLF001

print("\n8. Stop answers even while the child is silent")
import threading  # noqa: E402

flag = threading.Event()
threading.Timer(0.6, flag.set).start()
t0 = time.perf_counter()
got = engines._run([sys.executable, "-c", "import time; time.sleep(30)"],  # noqa: SLF001
                   lambda _l: None, flag)
spent = time.perf_counter() - t0
check("a silent child is cancelled promptly", got.get("why"), "cancelled")
check(f"…in {spent:.1f} s, not when it finally prints", spent < 8.0, True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
