"""Double-click JARVIS.bat → a window appears. Every single time.

The report, five times over:

    "jarvis.bat double click pana open aaguthu terminal then jarvis run aaga matiku machi"

Four different defects hid behind that one sentence, and the launcher could not tell them
apart — it accepted "the message was sent" as proof that a window existed.

  1. **The wake was fire-and-forget.** `jarvis_state --wake` and `run.py`'s second-launch
     path both returned success as soon as the bytes left. A hung copy, a copy still
     building its window, or a copy that ignored the event all looked identical: the
     launcher printed "JARVIS was already running — brought it to the front" over an empty
     desktop. Now the app **answers** (`instance.ask`), and the launcher also waits for the
     app's own log line `WAKE · the window is in front` — an answer is not a window.
  2. **`summon()` showed the cinematic, not the app.** It went through `_on_wake()` →
     `awaken()`, which **hides** the window and shows a fullscreen arrival clip. When that
     clip cannot draw — remote session, VM, driver hiccup, second monitor — nothing is on
     screen while the process sits in the tray. `summon()` now shows a plain window.
  3. **The wait was silent.** Up to 30 seconds of a blinking cursor, then either a happy
     message or a log dump. `launch.py --wait` prints a line every second and stops as soon
     as the app proves a window exists.
  4. **A crash explained nothing.** `pythonw.exe` has no console, so the traceback went
     into a log, and closing the launcher window threw away the only clue.
     `launch.py --diagnose` prints numbered PASS/FAIL checks plus the app's own last lines
     — while that window is still open.

Proven here, with the real socket, the real window and the real CLI:

  1. a running app acknowledges a wake, and a copy that accepts but never answers does not;
  2. `summon()` makes the window visible without the cinematic, and writes the log line
     the launcher greps for;
  3. the marker search is time-bounded (an old line from a previous run cannot fake it);
  4. preflight names the things that actually stop an import, and `diagnose()` says whose
     fault it is in one line;
  5. `launch.py --wait` is visible, bounded, and returns 0 only when a window is proven;
  6. `launch.py --diagnose` prints numbered checks and the crash line;
  7. `run.py` answers with a code the launcher can act on (3 = held but dead);
  8. `JARVIS.bat` uses all of it — waits visibly, verifies the wake, and diagnoses a
     failure in a window that stays open.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_open_every_time.py
"""
from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="arcdesk-open-")
os.environ["ARCDESK_HOME"] = HOME
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<62} {got!r}")


# ---------------------------------------------------------------------------
print("1. a running app answers a wake; a hung one does not")
from arcdesk import instance as inst_mod                                  # noqa: E402

# a stand-in for the app: the real Instance class, on a free port, with a callback
cfg = {"wake": {"port": 0}, "instance": {"port": 0}}


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


port = free_port()
seen: list[str] = []
live = inst_mod.Instance({"instance": {"port": port}})
live.on_summon = lambda: seen.append("wake")
check("the app takes the lock", live.acquire(), True)
got = inst_mod.ask(port, connect=1.0, wait=2.0)
check("…the wake is acknowledged", got.get("ack"), True)
check("…and it says it handled it", got.get("handled"), True)
check("…and the app really ran the callback", seen, ["wake"])
seen.clear()
got = inst_mod.ask(port, event="quit", connect=1.0, wait=2.0)
check("an event with nothing to do is answered too (never silence)",
      got.get("ack"), True)
check("…and is honestly 'ignored'", got.get("reply", {}).get("event"), "ignored")
check("…without calling the wake callback", seen, [])

# a copy that accepts and says nothing: the old code called this success
silent = socket.socket()
silent.bind(("127.0.0.1", 0))
silent.listen(4)
silent_port = silent.getsockname()[1]
threading.Thread(target=lambda: [silent.accept() for _ in range(3)], daemon=True).start()
got = inst_mod.ask(silent_port, connect=1.0, wait=1.0)
check("a silent copy is NOT an acknowledged wake", got.get("ack"), False)
check("…though the message did leave", got.get("sent"), True)
silent.close()
live.release()

print("\n2. the window comes up — as a window, not as a cinematic")
from PySide6.QtWidgets import QApplication                              # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer                           # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])
from arcdesk import config, logs                                        # noqa: E402
from arcdesk.widgets.window import MainWindow                           # noqa: E402


def pump(seconds: float) -> None:
    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


win_cfg = config.load()
win_cfg.setdefault("wake", {})["enabled"] = False
win_cfg.setdefault("magic", {})["enabled"] = False
win = MainWindow(win_cfg)
win.hide()
pump(0.1)
check("the window starts hidden (the stealth case that produced the report)",
      win.isVisible(), False)

before = time.time()
win.summon()
pump(0.2)
check("summon() makes it visible", win.isVisible(), True)
check("…and does not open the arrival cinematic",
      getattr(win, "_awakening", None), None)
mark = inst_mod.__name__ and "" or ""
from arcdesk import open_now as on                                       # noqa: E402
mark = on.window_mark_since(before)
check("…and writes the line the launcher looks for", bool(mark), True)
check("…which names the window", "the window is in front" in mark, True)

print("\n3. the proof is time-bounded: yesterday's line cannot fake today's")
scratch = Path(HOME) / "scratch.log"
old_line = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 3600))
scratch.write_text(f"{old_line} NOTE arcdesk WAKE · the window is in front — an hour ago\n",
                   encoding="utf-8")
check("a marker from an hour ago is not accepted",
      on.window_mark_since(time.time() - 60, scratch), "")
check("…but the same line is found when that IS the window we waited for",
      bool(on.window_mark_since(time.time() - 3700, scratch)), True)
new_line = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
with scratch.open("a", encoding="utf-8") as handle:
    handle.write(f"{new_line} NOTE arcdesk WAKE · the window is in front — now\n")
check("a marker written now is accepted", bool(on.window_mark_since(time.time() - 30,
                                                                   scratch)), True)
# The line the background copy writes at every login says the window is NOT shown. Counting
# it as proof would let the launcher report success while the desktop is empty.
stealth = Path(HOME) / "stealth.log"
now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
stealth.write_text(f"{now} NOTE arcdesk BOOT · stealth: the window is not shown "
                   f"(that is what --shadow asks for)\n", encoding="utf-8")
check("the stealth line is NOT treated as a window",
      on.window_mark_since(time.time() - 30, stealth), "")

print("\n4. a crash is explained in one line")
tail = ("2026-10-25 10:00:00 NOTE arcdesk BOOT · starting\n"
        "Traceback (most recent call last):\n"
        '  File "run.py", line 1, in <module>\n'
        "ModuleNotFoundError: No module named 'PySide6'\n")
reason = on.crash_reason(tail)
check("it finds the real error, not the last line",
      "No module named 'PySide6'" in reason, True)
check("an empty log does not pretend to know", on.crash_reason(""), "")

print("\n5. preflight + verdict")
checks = on.preflight(ROOT)
check("it returns named checks", [c["name"] for c in checks][0], "run.py is here")
check("…all of them have a fix line when they fail",
      all(c["fix"] for c in checks), True)
check("…and this checkout passes", [c["name"] for c in checks if not c["ok"]], [])
check("a broken install is named as one",
      on.whose_fault([{"ok": False, "name": "PySide6", "fix": "pip install"}], {}),
      "broken install")
check("…a live app is not an error",
      on.whose_fault([], {"live": True}), "already running")
check("…a dead socket is 'a stuck copy'",
      on.whose_fault([], {"stale_pids": [123]}), "a stuck copy is in the way")
lines = on.numbers([{"name": "run.py is here", "ok": True, "detail": "x", "fix": ""},
                    {"name": "PySide6", "ok": False, "detail": "no module", "fix": "pip"}])
check("the report is numbered and says PASS/FAIL",
      (lines[0].strip().startswith("1."), "[PASS]" in lines[0], "[FAIL]" in lines[1]),
      (True, True, True))

print("\n6. launch.py: visible, bounded, and honest")
argv = on.launch_argv(ROOT)
check("it starts run.py", argv[1].endswith("run.py"), True)
check("…with --show, because a double-click means a person", argv[-1], "--show")
check("…and never --shadow", "--shadow" in argv, False)
check("…using the private .venv when there is one",
      Path(argv[0]).parent.name in ("Scripts", "bin") or argv[0] == sys.executable, True)

empty_log = Path(HOME) / "empty.log"
empty_log.write_text("nothing yet\n", encoding="utf-8")
proc = subprocess.run([sys.executable, str(ROOT / "tools" / "launch.py"),
                       "--wait", "2", "--log", str(empty_log), "--since",
                       str(time.time())],
                      capture_output=True, text=True, timeout=90, env={**os.environ})
check("--wait with no window exits 1", proc.returncode, 1)
check("…and says so", "no window after" in (proc.stdout or ""), True)
check("…after printing progress, not silence",
      (proc.stdout or "").count("still waiting") >= 1, True)

# the log the app writes, the way the app writes it
now_line = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
empty_log.write_text(f"{now_line} NOTE arcdesk BOOT · the window is shown\n",
                     encoding="utf-8")
proc = subprocess.run([sys.executable, str(ROOT / "tools" / "launch.py"), "--wait", "3",
                       "--log", str(empty_log), "--since", str(time.time() - 2)],
                      capture_output=True, text=True, timeout=90, env={**os.environ})
check("--wait with a fresh marker exits 0", proc.returncode, 0)
check("…and reports how long it took", "the window is up after" in (proc.stdout or ""), True)

proc = subprocess.run([sys.executable, str(ROOT / "tools" / "launch.py"), "--diagnose"],
                      capture_output=True, text=True, timeout=120, env={**os.environ})
check("--diagnose exits 0 on a healthy checkout", proc.returncode, 0)
body = proc.stdout or ""
check("…with numbered checks", "what I checked" in body and "[PASS]" in body, True)
check("…a verdict line", "verdict:" in body, True)
check("…and the app's own last lines", "the app's own log, last lines" in body, True)

print("\n7. run.py answers with something the launcher can act on")
run_py = (ROOT / "run.py").read_text(encoding="utf-8")
check("it asks the running copy and waits for the answer", "wake_now(cfg)" in run_py, True)
check("…an answered wake is success", "_finish(0)" in run_py, True)
check("…a silent one is exit code 3", "_finish(3)" in run_py, True)
check("it does not pretend: no bare 'another_instance_running' success path",
      "another_instance_running(cfg)" in run_py, False)

print("\n8. JARVIS.bat uses all of it")
bat = (ROOT / "JARVIS.bat").read_bytes().decode("ascii")
check("the wait is visible", ("--ensure" in bat) and ("launch.py" in bat), True)
check("…and the repair-start is the default path", "launch.py\" --ensure --wait 25" in bat, True)
check("the wake is verified with a window, not an answer",
      ":broughtnothing" in bat and "launch.py\" --wait 6" in bat, True)
check("a copy that answers but shows nothing is replaced by a fresh one",
      "--kill-stale" in bat and ":broughtnothing" in bat, True)
check("a failure is diagnosed, not dumped", "launch.py\" --diagnose" in bat, True)
check("…and the window stays open to read it", "pause" in bat, True)
check("the retry is bounded, so it can never spin forever", "if %WAITED% geq 3" in bat, True)
check("it still waits before claiming success", "--status" in bat, True)
check("it never passes --shadow", '\"--shadow\"' in bat or "'--shadow'" in bat, False)

print("\n9. --ensure: the double-click path, including a crash")
# a folder whose run.py dies at once — the silent-crash case
bad = Path(HOME) / "badroot"
bad.mkdir(exist_ok=True)
(bad / "run.py").write_text(
    'print("about to die")\nraise SystemExit("no display")\n', encoding="utf-8")
(bad / "requirements.txt").write_text("py\n", encoding="utf-8")

before_line = on.log_offset()
proc = subprocess.run([sys.executable, str(ROOT / "tools" / "launch.py"), "--ensure",
                       "--wait", "25", "--root", str(bad)],
                      capture_output=True, text=True, timeout=180, env={**os.environ})
body = proc.stdout or ""
check("a crashing install is a failure, not a success", proc.returncode, 1)
check("…and it is noticed in seconds, not after 25 s",
      "it exited after" in body, True)
check("…the process's own words are shown", "about to die" in body, True)
check("…the verdict is 'started, then closed itself'",
      "started, then closed itself" in body, True)
check("…and the numbered checks still print", "[PASS] run.py is here" in body, True)
check("the child's output is in the spawn log, not thrown away",
      "about to die" in on.spawn_text(40), True)

print("\n10. a line from the previous run can never prove this one")
scratch2 = Path(HOME) / "two-runs.log"
now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
scratch2.write_text(f"{now} NOTE arcdesk BOOT · the window is shown\n", encoding="utf-8")
offset = scratch2.stat().st_size
with scratch2.open("a", encoding="utf-8") as handle:
    handle.write(f"{now} NOTE arcdesk WAKE · the window is in front — this run\n")
check("an older line beyond the offset is ignored",
      "this run" in on.window_mark_from(offset, scratch2), True)
check("…and reading from 0 finds the older one instead",
      "BOOT · the window is shown" in on.window_mark_from(0, scratch2), True)

print("\n11. --ensure really starts this app and proves the window")
sys.path.insert(0, str(ROOT / "tools"))                                  # noqa: E402
import jarvis_state                                                      # noqa: E402

jarvis_state.stop_all(wait=4.0)
proc = subprocess.run([sys.executable, str(ROOT / "tools" / "launch.py"), "--ensure",
                       "--wait", "30"], capture_output=True, text=True, timeout=240,
                      env={**os.environ})
body = proc.stdout or ""
check("it exits 0", proc.returncode, 0)
check("…with a proven window, not a hope", "the window is up after" in body, True)
check("…after saying what it is doing", "1. checking this install" in body, True)
check("…and the app really is running", jarvis_state.live(), True)
jarvis_state.stop_all(wait=6.0)
# Not `live()`: the wake daemon listens on the neighbouring port and outlives the window,
# so "something answers" stays true after the app has gone. The honest question is "is a
# run.py of ours still alive", which is what pids() answers.
for _ in range(20):
    if not jarvis_state.pids():
        break
    time.sleep(0.5)
check("…and it can be closed again", jarvis_state.pids(), [])

print("\n12. a frozen copy that answers its socket is replaced, not spared")
# The 2026-10-26 report: four pythonw.exe in Task Manager, one of them
# "Not Responding". A copy whose GUI has frozen can still answer its lock
# socket (the socket runs on its own thread), so the old replacement path -
# "ask to quit, then kill-stale" - saw that it was ANSWERING, called it
# healthy, spared it, and piled a fresh copy behind it on every double-click.
launch_src = (ROOT / "tools" / "launch.py").read_text(encoding="utf-8")
seg = launch_src.split("answered but no window appeared")[1].split("time.sleep(1.0)")[0]
seg_code = "\n".join(l for l in seg.splitlines() if not l.strip().startswith("#"))
check("…the replacement path closes by pid (stop_all)", "stop_all" in seg_code, True)
check("…and no longer asks 'is it answering?' (kill_stale)", "kill_stale" not in seg_code, True)
seg2 = launch_src.split("2b. closing")[1].split("time.sleep(1.0)")[0]
seg2_code = "\n".join(l for l in seg2.splitlines() if not l.strip().startswith("#"))
check("…and the same for leftovers found after the port check", "stop_all" in seg2_code, True)
jarvis_bat2 = (ROOT / "JARVIS.bat").read_bytes().decode("ascii", "replace")
bn = jarvis_bat2.rsplit(":broughtnothing", 1)[1].split("goto :launch")[0]
check("…and JARVIS.bat's no-window branch closes it too (--stop)", "--stop" in bn, True)

print("\n13. a frozen ArcDesk.exe is its own launcher: a held lock never eats a double-click")
run_src13 = (ROOT / "run.py").read_text(encoding="utf-8")
check("…it asks the holder to quit over the socket first",
      '"from": "relaunch"' in run_src13, True)
check("…then names the holder by the lock port (netstat, not a run.py scan)",
      "_holder_pid(port)" in run_src13, True)
check("…closes it by pid", "taskkill" in run_src13, True)
check("…records the stop so the next start calls it an action, not a crash",
      "_record_stop(holder)" in run_src13, True)
check("…and relaunches a fresh copy of itself",
      "_sp.Popen(fresh" in run_src13 and "frozen" in run_src13, True)
import re as _re
_m = _re.search(r"def _holder_pid\(.*?(?=\ndef )", run_src13, _re.S)
assert _m, "_holder_pid source"
_ns = {}
exec(_m.group(0), {"sys": sys, "__name__": "holder-test"}, _ns)
_sample = ("  Proto  Local Address          Foreign Address        State           PID\n"
           "  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       980\n"
           "  TCP    127.0.0.1:8766         0.0.0.0:0              LISTENING       4242\n"
           "  TCP    127.0.0.1:54321        127.0.0.1:8766         TIME_WAIT       0\n")
check("…the parser finds the pid listening on the lock port",
      _ns["_holder_pid"](8766, _text=_sample), 4242)
check("…and none for a port that has no holder", _ns["_holder_pid"](9999, _text=_sample), 0)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
win.close()
raise SystemExit(0 if ok else 1)
