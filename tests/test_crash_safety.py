"""A crash must never take the window with it — and must leave something to read

    python tests/test_crash_safety.py

The report: *"yethavathu select pana application crash aagi, close aaguthu"* — pick
something, the app disappears. Three separate things are checked here, because a crash of
this shape has three parts and only one of them is the bug itself:

    1. **the engine never runs inside the window's process.** `transformers` + `torch` +
       a *repo's own code* (`trust_remote_code=True`) next to Qt's DLLs, on the drawing
       thread, freezes the screen for tens of seconds and on Windows can end the process
       with no traceback. That is the "it closed by itself" class this project has hit
       before with piper. All clone speech now goes to a child process;
    2. **a crash leaves a file the person can send** — `crash-report.txt`, with the log and
       the native fault log tail. A native crash prints nothing, so this is the only trace;
    3. **two crashes in a row cannot leave the app unopenable** — the next start pauses the
       heavy visuals (a GPU driver that dies on the deck crashes before the window is drawn)
       and says so out loud, changing none of the person's settings.

Run:  python tests/test_crash_safety.py
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import json
import sys
import tempfile
import time as _time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-crash-")
os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import clone, logs  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {str(got)[:40]!r}")
    if not same:
        print(f"        expected {want!r}")


print("\n1. the engine never runs inside the window's process")
called: list[str] = []
real_sidecar = clone._sidecar_speak                                     # noqa: SLF001
real_local = clone._local_engine                                        # noqa: SLF001
real_route = clone.route
real_ref = clone.reference
ref = Path(tempfile.mkdtemp()) / "reference.wav"
ref.write_bytes(b"RIFF")


def fake_sidecar(text, lang, ref_path, wav, engine, engmod, python=""):
    called.append(python or "(the private folder)")
    return True


try:
    clone.reference = lambda: ref                                       # noqa: SLF001
    clone.route = lambda lang="ta", *a, **k: "indicf5"                  # noqa: SLF001
    clone._local_engine = lambda key: True                              # noqa: SLF001
    clone._sidecar_speak = fake_sidecar                                 # noqa: SLF001

    # nothing installed anywhere, but the packages ARE importable here
    from arcdesk import engines as _engines
    real_ready = _engines.sidecar_ready
    _engines.sidecar_ready = lambda key: False                          # noqa: SLF001
    clone.refresh()
    clone._CACHE["data"] = {"indicf5": {"available": True, "foreign": "", "code": True},
                            "xtts": {"available": False, "foreign": "", "code": False}}
    got = clone.speak("vanakkam macha", "ta", wav=str(Path(tempfile.mkdtemp()) / "o.wav"))
    check("it spoke", got, True)
    check("…in a child process, using this same python", called[-1], sys.executable)
    check("…and the in-process model path was not used", clone._indicf5(          # noqa: SLF001
        "x", "ta", ref, ""), False)

    # an engine the person installed elsewhere: that interpreter is the child
    clone._CACHE["data"] = {"indicf5": {"available": True, "code": True,
                                        "foreign": "/opt/conda/envs/indicf5/bin/python"},
                            "xtts": {"available": False, "foreign": "", "code": False}}
    clone.speak("vanakkam", "ta", wav=str(Path(tempfile.mkdtemp()) / "o.wav"))
    check("…their own interpreter is preferred when it has it", called[-1],
          "/opt/conda/envs/indicf5/bin/python")

    # the app's private folder wins over everything (that is what the button fills)
    _engines.sidecar_ready = lambda key: True                           # noqa: SLF001
    clone.speak("vanakkam", "ta", wav=str(Path(tempfile.mkdtemp()) / "o.wav"))
    check("…the private engine folder wins when it is ready", called[-1],
          "(the private folder)")
    _engines.sidecar_ready = real_ready                                 # noqa: SLF001
finally:
    clone._sidecar_speak = real_sidecar                                 # noqa: SLF001
    clone._local_engine = real_local                                    # noqa: SLF001
    clone.route = real_route                                            # noqa: SLF001
    clone.reference = real_ref                                          # noqa: SLF001
    clone.refresh()

print("\n2. both in-process engines refuse to run")
check("IndicF5 in-process is refused", clone._indicf5("x", "ta", ref, ""), False)  # noqa: SLF001
check("XTTS in-process is refused", clone._xtts("x", "en", ref, ""), False)        # noqa: SLF001
src = (ROOT / "arcdesk" / "clone.py").read_text(encoding="utf-8")
check("…and `speak` does not call them at all",
      "return _indicf5(" in src or "return _xtts(" in src, False)
check("…the escape hatch is off unless a human sets it",
      "ARCDESK_ALLOW_INPROCESS_TTS" in src, True)

print("\n3. a crash leaves a file that can be sent")
folder = logs.log_path().parent
(folder / "arcdesk.log").write_text("INFO the last thing before it went\n" * 5,
                                    encoding="utf-8")
(folder / "fault.log").write_text("Fatal Python error: Segmentation fault\n",
                                  encoding="utf-8")
bundle = logs.crash_bundle()
check("a crash report is written", bundle is not None and Path(bundle).exists(), True)
text = Path(bundle).read_text(encoding="utf-8") if bundle else ""
check("…it carries the native fault", "Segmentation fault" in text, True)
check("…and the log tail", "the last thing before it went" in text, True)
check("…and says what to do with it", "send it as it is" in text, True)
check("…it names the python and the Qt that died",
      "environment: " in text and "python " in text
      and ("Qt " in text or "PySide6" not in text), True)
check("…it is NOT inside the log folder (it is easy to find)", 
      Path(bundle).parent == folder.parent, True)

print("\n4. two crashes in a row cannot leave the app unopenable")
sp = logs.session_path()
sp.parent.mkdir(parents=True, exist_ok=True)
sp.write_text(json.dumps({"pid": 1, "started": "2026-10-25 10:00:00", "clean": False,
                          "crash_streak": 1}), encoding="utf-8")
note = logs.begin_session()
check("the next start is told the last one crashed", bool(note), True)
check("…and the streak goes up", logs.crash_streak(), 2)
sp.write_text(json.dumps({"pid": 1, "started": "2026-10-25 10:00:00", "clean": False,
                          "crash_streak": 2}), encoding="utf-8")
logs.begin_session()
check("a third crash keeps counting", logs.crash_streak(), 3)
logs.end_session()
check("a proper close resets it", logs.crash_streak(), 0)
note2 = logs.begin_session()
check("…so a normal restart is not called a crash", note2, "")

print("\n4b. a session the LAUNCHER stopped is explained, not called a crash")
sp = logs.session_path()
sp.write_text(json.dumps({"pid": 4242, "started": "2026-10-27 10:04:52", "clean": False,
                          "crash_streak": 3}), encoding="utf-8")
stop_path = Path(os.environ["ARCDESK_HOME"]) / "ArcDesk" / "logs" / "launcher-stop.json"
stop_path.parent.mkdir(parents=True, exist_ok=True)
stop_path.write_text(json.dumps({"pids": [4242], "ts": _time.time(),
                                 "at": "2026-10-27 10:05:14"}), encoding="utf-8")
note = logs.begin_session()
check("…the next start says the launcher closed it",
      "launcher closed JARVIS" in note, True)
check("…and calls it expected, not a crash", "expected, not a crash" in note, True)
check("…the safe streak does NOT escalate", logs.crash_streak(), 0)
check("…and run.py shows a LAUNCHER note, not CRASH",
      "LAUNCHER · " in (ROOT / "run.py").read_text(encoding="utf-8"), True)
from tools import jarvis_state as js          # noqa: E402
stop_path.unlink()
js.record_stop(777)
data = json.loads(stop_path.read_text(encoding="utf-8"))
check("…jarvis_state.record_stop writes the pid for the next start to read",
      777 in data["pids"], True)
stop_path.write_text(json.dumps({"pids": [4242], "ts": _time.time() - 3600,
                                 "at": "2026-10-27 09:00:00"}), encoding="utf-8")
sp.write_text(json.dumps({"pid": 4242, "started": "2026-10-27 10:04:52", "clean": False,
                          "crash_streak": 1}), encoding="utf-8")
note = logs.begin_session()
check("…a stale marker does not excuse a real crash",
      "stopped without closing properly" in note, True)
check("…and the streak climbs again", logs.crash_streak(), 2)
stop_path.unlink()
logs.end_session()
check("…and a proper close resets the streak", logs.crash_streak(), 0)

print("\n5. the safeguard is wired into the start-up, not just written down")
run_src = (ROOT / "run.py").read_text(encoding="utf-8")
check("start-up writes the bundle", "logs.crash_bundle()" in run_src, True)
check("…reads the streak", "logs.crash_streak()" in run_src, True)
check("…and pauses the visuals on the second strike",
      'cfg["effects"] = 0.0' in run_src, True)
check("…telling the person why", "heavy visuals paused" in run_src, True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
