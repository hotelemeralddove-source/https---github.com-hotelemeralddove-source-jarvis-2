"""The download must not live or die with the window

    python tests/test_engine_background.py

Three times the same report: *"download aaga matiku … antha circel desktop la vanthu hang
aagi stuck aaiduthu"*. A 1.5 GB download that runs **inside** the window's process is thrown
away when the window stops answering, is closed, or is killed — and a frozen window is
exactly when a person presses X.

So the download lives in its own detached process (`tools/engine_get.py install …`) and
reports through a small JSON file. A ten-line stand-in helper is used here, so this file
checks the CONTRACT in a second instead of behind a real download:

    1. it starts detached, as a different process;
    2. what it writes can be read from the drawing thread (no child, no wait, no pipe);
    3. the screen follows it: percent, megabytes, speed, ETA, its log lines;
    4. closing the dialog does NOT stop it — that is the whole point;
    5. Stop does stop it, and the verdict says what arrived is kept;
    6. piper's own voice download works (it raised `TypeError: unsupported operand type(s)
       for +: 'PosixPath' and 'str'` for every language, so piper could never be installed
       by anybody at all).
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-bg-")
os.environ["ARCDESK_NO_FOREIGN_PYTHON"] = "1"
os.environ.pop("ARCDESK_NO_HELPER", None)          # the helper route is the product

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from arcdesk import engine_helper  # noqa: E402

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
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def wait_for(cond, seconds: float = 40.0, step: float = 0.2) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        pump(step)
    return cond()


# ------------------------------------------------------------------ the stand-in helper
FAKE_SRC = '''import json, os, sys, time
from pathlib import Path

progress = Path(sys.argv[1])
pid = os.getpid()
stop = progress.with_name(progress.stem + ".stop")
for step in range(150):                       # ~30 s at 0.2 s, like a real download
    if stop.exists():
        progress.write_text(json.dumps({"pid": pid, "engine": "piper", "done": True,
                                        "ok": False, "why": "cancelled", "percent": 0,
                                        "stage": "stopped by you"}))
        sys.exit(0)
    mb = step * 6.0
    progress.write_text(json.dumps({
        "pid": pid, "engine": "piper", "stage": "downloading the voices",
        "percent": min(99.0, mb / 60.0 * 100), "mb": mb, "total_mb": 60.0,
        "speed": "12.0 MB/s", "eta": "0:04", "done": False, "why": "", "ok": False,
        "lines": ["downloading the voices", "6.0 MB of 60 MB"],
    }))
    time.sleep(0.2)
progress.write_text(json.dumps({"pid": pid, "engine": "piper", "stage": "done",
                                "percent": 100.0, "mb": 60.0, "total_mb": 60.0,
                                "done": True, "ok": True, "why": "", "lines": ["ready"]}))
'''
FAKE = Path(tempfile.mkdtemp(prefix="arcdesk-fake-helper-")) / "fake_helper.py"
FAKE.write_text(FAKE_SRC, encoding="utf-8")


def start_fake() -> dict:
    return engine_helper.start("piper", argv=[sys.executable, str(FAKE),
                                              str(engine_helper.progress_path("piper"))])


print("\n1. a real helper process, detached, with a file to read")
can, why = engine_helper.available()
check("this app can start a background download", can, True)
if why:
    print(f"        (why not: {why})")
check("the download script is where the app looks for it", engine_helper.script().is_file(),
      True)
started = start_fake()
check("it started", started.get("ok"), True)
check("…as a different process", int(started.get("pid") or 0) > 0, True)
check("…and it is alive on its own", engine_helper.running("piper"), True)

print("\n2. reading it is a file read, not a wait")
t0 = time.perf_counter()
for _ in range(20):
    engine_helper.read("piper")
spent_ms = (time.perf_counter() - t0) * 1000 / 20
check(f"one reading costs {spent_ms:.1f} ms (safe on the drawing thread)", spent_ms < 15, True)

print("\n3. the numbers arrive by themselves")
# step 0 of a download is legitimately 0 % / 0 MB, so wait for a real number, not for
# the file to merely exist
moved = wait_for(lambda: float(engine_helper.read("piper").get("percent") or 0) > 0,
                 seconds=25)
data = engine_helper.read("piper")
check("the file reports what the download is doing", moved, True)
check("…a percent a bar can show", float(data.get("percent") or 0) > 0, True)
check("…megabytes", float(data.get("mb") or 0) > 0, True)
check("…and a stage a person can read", str(data.get("stage")), "downloading the voices")

print("\n4. closing the dialog must NOT stop a background download")
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.engine_dialog import EngineDialog  # noqa: E402

dialog = EngineDialog(get_theme("chill"))
pump(0.5)
dialog._items = {"piper": {"id": "piper", "label": "Piper", "langs": "English, Hindi",
                           "size_mb": 60, "why": "", "needs": "", "ready": False,
                           "code": True, "python": "/usr/bin/python3", "voices": 0,
                           "problem": "a piper voice (.onnx, ~30 MB, one per language)",
                           "model": "", "local": "", "token_from": ""}}
dialog._method = {"can_install": True, "why": ""}
dialog._fill_picker()
dialog.picker.setCurrentIndex(dialog.picker.findData("piper"))
dialog._show()

pid = int(engine_helper.read("piper").get("pid") or 0)
real_start = engine_helper.start
engine_helper.start = lambda engine, lang="", argv=None: {"ok": True, "pid": pid, "why": ""}
try:
    attached = dialog._begin_helper("piper", dialog._current(), "", True)
finally:
    engine_helper.start = real_start
check("the screen can attach to a download already running", attached, True)
check("…the bar is up", dialog.bar.isVisibleTo(dialog), True)
dialog._beat()                                     # one poll: it must read, not block
check("…the bar shows the helper's percent", dialog.bar.value() > 0, True)
check("…and the live line says the stage", "downloading the voices" in dialog.live.text(), True)
dialog.reject()
pump(1.0)
check("closing the window wrote NO stop request", engine_helper.cancel_path("piper").exists(),
      False)
check("…the same process is still the one responsible",
      int(engine_helper.read("piper").get("pid") or 0), pid)
check("…and it is still working after the window went away", engine_helper.running("piper"),
      True)
check("…the dialog let go of it instead of killing it", dialog._helper_engine, "")

print("\n5. Stop stops it, and the verdict keeps what arrived")
engine_helper.stop("piper")
wait_for(lambda: not engine_helper.running("piper"), seconds=20)
check("it is gone", engine_helper.running("piper"), False)
check("…a stop file was left for it to read (the polite route)",
      engine_helper.cancel_path("piper").exists(), True)
data = engine_helper.read("piper")
check("…and its last word says cancelled", data.get("why") or data.get("done"), "cancelled")
try:
    engine_helper.cancel_path("piper").unlink()
except OSError:
    pass

print("\n5b. a run that finishes says so by itself")
start_fake()
wait_for(lambda: engine_helper.read("piper").get("done"), seconds=40)
final = engine_helper.read("piper")
check("the finished file says done", bool(final.get("done")), True)
check("…and it is not called 'running' any more", engine_helper.running("piper"), False)

print("\n6. piper's own voice download works (it raised TypeError for every language)")
from arcdesk import engines  # noqa: E402
warm = engines._PIPER_WARM                                  # noqa: SLF001
check("the script no longer adds a string to a Path",
      'open(out + ".part"' in warm, False)
check("…it builds a .part Path instead", 'out.with_name(out.name + ".part")' in warm, True)
check("…and it checks the size before keeping a file", "part.stat().st_size != total" in warm,
      True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
