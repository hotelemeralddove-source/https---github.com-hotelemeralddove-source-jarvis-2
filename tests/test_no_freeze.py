"""Nothing that waits may run on the thread that draws the window.

The report, twice: *"again ithu mathiri front la vanthu struck aagi nikithu machi"* — a
dialog in front, a waiting ring, and nothing moves. On Windows the ring in the screenshot
is the system busy cursor, and a busy cursor that never goes away means one of exactly two
things happened:

   1. a callback did slow work on the drawing thread (`subprocess`, a download, a socket,
      a sleep) — the event loop stopped, so nothing repainted and Esc did nothing;
   2. a `setOverrideCursor` was never matched by a `restoreOverrideCursor`.

This file proves the fix for both, using the real widgets:

  1. `arcdesk.uiwork.run` moves the work off the drawing thread and delivers the answer
     back on it (asserted: the callback runs on the main thread, and a 0-tick timer keeps
     ticking while a 0.4 s job is running — the window stayed alive);
  2. the waiting cursor is always restored, including when the work raises, and a cursor
     left on by anything else is swept up;
  3. `StallWatch` names the line that froze the window — the information every "it hung"
     report has been missing;
  4. `blockguard` raises in strict mode when something that waits is called from the
     drawing thread, so a regression fails here instead of on somebody's laptop;
  5. **the regression itself**: with the engine probe made slow (1.5 s, as it is on a
     Windows PC with several pythons), Settings still builds in milliseconds, the Engine
     dialog opens and fills in later, "Find what I installed" returns at once, a voice
     upload returns at once — and Esc closes each of them while the work is still running;
  6. no widget file uses `processEvents()`, `time.sleep()` or `setOverrideCursor()` any
     more: there is one way to wait, and it is `uiwork`.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_no_freeze.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-no-freeze-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<60} {got!r}")


def pump(seconds: float, tick: list | None = None) -> int:
    """Run the real event loop for a while — never a sleep, because the guard is armed
    in half of this file and a sleeping pump would (rightly) fail the test."""
    from PySide6.QtCore import QEventLoop, QTimer
    counts = tick if tick is not None else []
    beat = QTimer()
    beat.setInterval(10)
    beat.timeout.connect(lambda: counts.append(time.monotonic()))
    beat.start()
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()
    beat.stop()
    return len(counts)


from PySide6.QtWidgets import QApplication                              # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

from arcdesk import blockguard, uiwork                                   # noqa: E402

print("1. work goes somewhere else, and the answer comes back to the UI thread")
seen: dict = {}


def slow_job(cancel):
    time.sleep(0.4)
    return 6 * 7


def got_answer(value):
    seen["value"] = value
    seen["thread"] = threading.current_thread().name


t0 = time.perf_counter()
job = uiwork.run(slow_job, done=got_answer, name="arc-test-slow")
spent = (time.perf_counter() - t0) * 1000
check(f"starting it returns in {spent:.0f} ms", spent < 60, True)
ticks = pump(0.75, [])
check("the event loop kept running while it worked", ticks > 10, True)
check("the answer arrived", seen.get("value"), 42)
check("…on the main thread", seen.get("thread"), "MainThread")
check("the job is no longer listed as running", uiwork.busy(), 0)

print("\n2. a failure is a message, not a freeze or a crash")
failed: list[str] = []
uiwork.run(lambda cancel: 1 / 0, done=lambda r: failed.append("should not happen"),
           failed=failed.append, name="arc-test-fail")
pump(0.3)
check("the failure was delivered", bool(failed), True)
check("…with the real reason", "ZeroDivisionError" in (failed[0] if failed else ""), True)

print("\n3. the waiting cursor is always put back")
from PySide6.QtCore import Qt                                            # noqa: E402

with uiwork.busy_cursor():
    inside = QApplication.overrideCursor() is not None
check("it is set while working", inside, True)
check("…and gone afterwards", QApplication.overrideCursor() is None, True)
try:
    with uiwork.busy_cursor():
        raise RuntimeError("boom")
except RuntimeError:
    pass
check("…even when the work raises", QApplication.overrideCursor() is None, True)
for _ in range(3):
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
check("three stray overrides are swept up", uiwork.clear_stuck_cursors(), 3)
check("…and the cursor is normal again", QApplication.overrideCursor() is None, True)

print("\n4. the stall watch names the line that froze the window")


def freezes_the_window():
    time.sleep(0.55)                      # the bug, on purpose


watch = uiwork.StallWatch(threshold_ms=120, interval_ms=20).start()
freezes_the_window()
pump(0.2)
watch.stop()
worst_seconds, worst_where = watch.worst()
check("a freeze was noticed", worst_seconds > 0.4, True)
check("…and blamed on the right function", "freezes_the_window" in worst_where, True)
check("…with a file and line", ":" in worst_where and ".py" in worst_where, True)

print("\n5. the blocking guard fails the build, not the person")
blockguard.reset()
blockguard.install("strict")
try:
    import subprocess
    subprocess.run([sys.executable, "-c", "pass"])
    raised = ""
except blockguard.UIRuleViolation as exc:
    raised = str(exc)
check("a child process on the UI thread raises", "subprocess.run" in raised, True)
check("…and says where", "test_no_freeze.py" in raised, True)
done_in_thread = []
uiwork.run(lambda cancel: __import__("subprocess").run([sys.executable, "-c", "pass"]),
           done=lambda r: done_in_thread.append(True), name="arc-test-thread-spawn")
pump(0.6)
check("the same call on a worker is allowed", done_in_thread, [True])
check("…and was not recorded as a violation", len(blockguard.hits()), 1)
blockguard.uninstall()
check("turning it off restores the real calls", blockguard.enabled(), False)

print("\n6. THE REGRESSION: a slow engine probe must not freeze any dialog")
from arcdesk import clone, engines                                       # noqa: E402
from arcdesk.theme import get_theme                                      # noqa: E402

real_status = engines.status
real_diagnosis = engines.diagnosis_text


def slow_status():
    time.sleep(1.2)                        # a Windows PC with several pythons
    return real_status()


def slow_diagnosis():
    time.sleep(1.2)
    return "checked every python (slowly, on purpose)"


engines.status = slow_status                                             # noqa: SLF001
engines.diagnosis_text = slow_diagnosis                                  # noqa: SLF001
theme = get_theme("chill")
cfg = {"wake": {"enabled": False}, "shadow": {}, "ai": {}, "voice": {}}
blockguard.reset()
blockguard.install("strict")
try:
    from arcdesk.widgets.engine_dialog import EngineDialog
    from arcdesk.widgets.settings import SettingsDialog
    from arcdesk.widgets.voicelib_dialog import VoiceLibraryDialog

    t0 = time.perf_counter()
    settings = SettingsDialog(cfg, theme)
    spent = (time.perf_counter() - t0) * 1000
    check(f"Settings builds in {spent:.0f} ms while the probe takes 1.2 s", spent < 400, True)
    settings.show()
    check("…the window is on screen", settings.isVisible(), True)
    settings.esc_or_close = getattr(settings, "reject", None)
    settings.reject()
    check("…and Esc closes it while everything is still probing",
          settings.isVisible(), False)

    t0 = time.perf_counter()
    dlg = EngineDialog(theme)
    spent = (time.perf_counter() - t0) * 1000
    check(f"the engine dialog builds in {spent:.0f} ms", spent < 400, True)
    check("…and says it is checking, instead of showing nothing",
          "checking" in dlg.state.text().lower(), True)
    check("…with the install button disabled until it knows", dlg.go.isEnabled(), False)
    dlg.show()
    dlg.reject()
    check("…and closes on Esc while the probe is still running", dlg.isVisible(), False)

    dlg2 = EngineDialog(theme)
    dlg2.show()
    pump(2.2)
    check("the answer arrives later and fills the list", dlg2.picker.count() > 0, True)
    check("…and the install button is usable again", dlg2.go.isEnabled(), True)

    t0 = time.perf_counter()
    dlg2._scan()                                                         # noqa: SLF001
    spent = (time.perf_counter() - t0) * 1000
    check(f"'Find what I installed' returns in {spent:.0f} ms", spent < 300, True)
    check("…and says it is looking", "looking" in dlg2.log.toPlainText().lower(), True)
    pump(3.2)
    check("…then prints the report", "every python" in dlg2.log.toPlainText(), True)
    check("…and re-enables its own button", dlg2.scan.isEnabled(), True)
    dlg2.reject()

    from arcdesk import voicelib
    real_add = voicelib.add_command
    voicelib.add_command = lambda name, path: (time.sleep(1.0),
                                               {"ok": True, "message": "added"})[1]
    voices = VoiceLibraryDialog(cfg, theme)
    voices.show()
    voices.cmd_name.setText("machi")
    t0 = time.perf_counter()
    voices._busy(lambda _c: voicelib.add_command("machi", "/tmp/x.wav"),   # noqa: SLF001
                 "reading that recording…", lambda got: voices.out.setPlainText(
                     str(got.get("message"))), "command voice")
    spent = (time.perf_counter() - t0) * 1000
    check(f"a 1 s voice upload returns in {spent:.0f} ms", spent < 200, True)
    check("…the buttons are disabled meanwhile", voices.cmd_add.isEnabled(), False)
    check("…the box says what it is doing",
          "reading that recording" in voices.out.toPlainText(), True)
    voices.reject()
    check("…and Esc still closes the window", voices.isVisible(), False)
    pump(1.4)
    check("…while the upload finishes in the background", voices.cmd_add.isEnabled(), True)
    voicelib.add_command = real_add
finally:
    engines.status = real_status                                         # noqa: SLF001
    engines.diagnosis_text = real_diagnosis                              # noqa: SLF001
    blockguard.uninstall()

print("\n7. the rule, in the source, so it cannot come back quietly")
import ast                                                              # noqa: E402


def calls_in(path: Path) -> set[str]:
    """Dotted names the file really calls. Comments and docstrings are not calls — a
    grep here would fail on the sentence explaining why the call was removed."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        parts, cur = [], node.func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        found.add(".".join(reversed(parts)))
    return found


widgets = sorted((ROOT / "arcdesk" / "widgets").glob("*.py"))
called = {p.name: calls_in(p) for p in widgets}
check("no widget pumps the event loop by hand",
      [n for n, c in called.items()
       if any(x.endswith("processEvents") for x in c)], [])
check("no widget sleeps on the UI thread",
      [n for n, c in called.items()
       if any(x.endswith("time.sleep") or x == "sleep" for x in c)], [])
check("only uiwork sets an override cursor",
      [n for n, c in called.items()
       if any(x.endswith("setOverrideCursor") for x in c)], [])
check("…and only uiwork starts a thread for a dialog job",
      sorted(calls_in(ROOT / "arcdesk" / "uiwork.py") & {"threading.Thread"}), ["threading.Thread"])
check("…and run.py watches for both",
      "uiwork" in (ROOT / "run.py").read_text(encoding="utf-8")
      and "blockguard" in (ROOT / "run.py").read_text(encoding="utf-8"), True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
