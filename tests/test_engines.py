"""The neural engine — installed from inside the app, and never claimed early

    python tests/test_engines.py

Why this file exists: a cloned voice is not a preference, it is a model. The user's rule is
"it must sound like a real person, no TTS" — so the part of the app that fetches the model
has to be as honest as the part that speaks. Three things must be impossible:

    1. saying "installed" when only the pip package landed (the weights are the model),
    2. saying "installed" when the person pressed Stop,
    3. showing "system voice" with no way to fix it from the screen.

The real download is 1.5-3.4 GB, so the child processes are faked here. The logic, the
wording, and the dialog are real.
"""
from __future__ import annotations

import os
# Unit tests, no network: the licence gate asks Hugging Face for a real file, and the
# answer depends on whether THIS machine has a token. That is a property of the machine,
# not of the code under test, so the gate is switched off here and tested on its own in
# tests/test_engine_auto.py.
os.environ.setdefault("ARCDESK_OFFLINE", "1")
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-engines-")
# a scratch folder that exists on Windows too ("/tmp" does not, and that is how this
# test failed there while passing here)
_TMP = Path(tempfile.mkdtemp(prefix="arc-engines-")).as_posix()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from arcdesk import clone, engines  # noqa: E402

# The licence gate is a network question ("is this model's file readable without a token?").
# These checks are about WHERE an install goes and WHAT it runs, so the gate is stubbed to
# say YES here. The real gate has its own checks: §6 of tests/test_engine_progress.py, and
# tools/engine_get.py gate.
engines._http_status = lambda url="", token="", timeout=12.0: 200       # noqa: SLF001
# The free-space guard is checked before a download starts, and this test's HOME is a
# small tmpfs. It has its own checks in tests/test_engine_auto.py (§5); here it would
# only refuse every install for the wrong reason.
engines.free_gb = lambda path=None: 999.0                               # noqa: SLF001

from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.engine_dialog import EngineDialog  # noqa: E402

ok = True


def wait_for_list(dialog, seconds: float = 8.0) -> None:
    """Wait for the engine list to arrive.

    Since fix49 the dialog asks for the engine state on a worker and fills the list when
    the answer comes back (that is the whole point: no child process on the drawing
    thread). So the list is empty for a moment after construction — this pumps the real
    event loop instead of asserting against a frozen snapshot.
    """
    import time as _time

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    deadline = _time.monotonic() + seconds
    loop = QEventLoop()
    beat = QTimer()
    beat.setInterval(25)

    def poll() -> None:
        if dialog.picker.count() or _time.monotonic() > deadline:
            loop.quit()

    beat.timeout.connect(poll)
    beat.start()
    QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()
    beat.stop()
    QApplication.processEvents()


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:46]!r}")
    ok &= bool(good)


READY = {"on": False}          # flipped by the fake warm-up, like a real model landing


def fake_engines():
    return {"indicf5": {"available": READY["on"], "why": "" if READY["on"] else "missing",
                        "model": ""},
            "xtts": {"available": False, "why": "missing", "model": ""},
            "piper": {"available": False, "why": "piper is not installed", "model": ""}}


clone.engines = fake_engines          # the probe the installer consults
clone.refresh = lambda: None

CALLS: list[list[str]] = []


def ok_run(argv, on_line, cancel=None, on_progress=None):
    CALLS.append(list(argv))
    on_line("fake: " + " ".join(argv[2:4]))
    if "-c" in argv:                      # the warm-up = the weights
        READY["on"] = True
    return {"ok": True, "code": 0, "why": "", "last": "fake done"}


print("1) every engine is described honestly before anything is downloaded")
st = engines.status()
# three now: piper (the small, easy one), IndicF5 and XTTS-v2 (the big clones)
check("three engines", len(st), 3)
check("the small one is listed first, so the easy answer is on top",
      next(iter(st)), "piper")
check("piper's price is stated before it starts", st["piper"]["size_mb"] <= 120, True)
check("IndicF5 is for Tamil and Hindi", st["indicf5"]["langs"], "Tamil, Hindi")
check("XTTS is for English", st["xtts"]["langs"], "English")
check("the sizes are on the tin", (st["indicf5"]["size_mb"], st["xtts"]["size_mb"]),
      (1500, 1900))
check("nothing is ready yet", engines.any_ready(), False)
check("and the app says so in words", "system voice" in engines.line_for_voice(), True)
check("summary names both engines", "IndicF5" in engines.summary()
      and "XTTS-v2" in engines.summary(), True)

print("\n2) one click installs: packages first, then the weights")
engines._run = ok_run                   # noqa: SLF001 — the seam exists for this
seen: list[str] = []
got = engines.install("indicf5", on_line=seen.append)
check("it worked", got["ok"], True)
check("it said the size before starting", "1.5 GB" in seen[0], True)
# torch now installs first, from the CPU-only index — a ~200 MB wheel instead of the
# ~2.5 GB CUDA build PyPI serves to Windows, which is what "downloading but never
# downloading" actually was.
check("a torch install was run", any("torch" in c for c in CALLS), True)
check("…from the CPU-only index", any(engines._TORCH_CPU_INDEX in c            # noqa: SLF001
                                      for c in CALLS), True)
joined = [p for c in CALLS for p in c]
check("…and the other packages were installed too",
      [p for p in ("transformers", "soundfile") if p in joined],
      ["transformers", "soundfile"])
check("the weights were fetched last", "-c" in CALLS[-1], True)
# fix41: not one byte is installed into the interpreter the app is running in — a live
# process with files swapped under it is what closed the window.
check("inside the app's private folder, not this interpreter",
      all(c[0] != sys.executable for c in CALLS), True)
check("the streamed lines reach the caller", len(seen) >= 5, True)
check("ready is reported only now", engines.status()["indicf5"]["ready"], True)
check("and the honest line changes", "clone engine ready" in engines.line_for_voice(), True)

print("\n3) a package that installs but weights that fail is NOT 'installed'")
READY["on"] = False
CALLS.clear()


def warm_fails(argv, on_line, cancel=None, on_progress=None):
    CALLS.append(list(argv))
    if "-c" in argv:
        on_line("OSError: cannot reach huggingface.co")
        return {"ok": False, "code": 1, "why": "exit code 1",
                "last": "OSError: cannot reach huggingface.co"}
    return ok_run(argv, on_line, cancel, on_progress)


engines._run = warm_fails             # noqa: SLF001
seen.clear()
got = engines.install("indicf5", on_line=seen.append)
check("not ok", got["ok"], False)
check("it blames the weights, not the network in general", got["why"], "exit code 1")
check("the real error line is kept", any("huggingface" in l for l in seen), True)
check("it warns that nothing is ready", any("nothing is ready" in l for l in seen), True)
check("still not ready", engines.status()["indicf5"]["ready"], False)
check("still says system voice", "system voice" in engines.line_for_voice(), True)

print("\n4) Stop means stopped — never 'installed'")
cancel = threading.Event()
cancel.set()


def cancelled_run(argv, on_line, cancel=None, on_progress=None):
    return {"ok": False, "code": -2, "why": "cancelled", "last": ""}


engines._run = cancelled_run          # noqa: SLF001
got = engines.install("xtts", cancel=cancel)
check("not ok", got["ok"], False)
check("it says cancelled", got["why"], "cancelled")
check("nothing became ready", engines.status()["xtts"]["ready"], False)

print("\n5) an unknown engine is refused, not guessed")
check("refused", engines.install("magic")["ok"], False)

print("\n6) the install route is stated for this build")
m = engines.method()
check("a run-from-source build can use pip", m["can_install"], True)
check("it knows where the bundled script is", Path(m["bat"]).name, "install_clone.bat")
sys.frozen = True                     # what an installed ArcDesk.exe looks like
_real_external = engines.external_python
engines.external_python = lambda: ""
m2 = engines.method()
check("a frozen build does not pretend pip works", m2["pip"] and not m2["can_install"], True)
check("...it asks for Python once, plainly", "python.org" in m2["why"], True)
check("...and then refuses honestly", engines.install("indicf5")["ok"], False)
engines.external_python = lambda: "/usr/bin/python3"
m3 = engines.method()
check("with a Python present the .exe CAN install (private folder)", m3["can_install"], True)
check("...and has nothing to apologise for", m3["why"], "")
del sys.frozen

print("\n7) the dialog: sizes on the buttons, live output, real verdicts")
dlg = EngineDialog(get_theme("chill"))
wait_for_list(dlg)
check("one entry per engine", dlg.picker.count(), 3)
check("the first entry is the easy one", dlg.picker.itemText(0).startswith("Piper"), True)
# the picker opens on Piper now; IndicF5 is selected to check the big-engine wording
indic = dlg.picker.findData("indicf5")
dlg.picker.setCurrentIndex(indic)
check("the button carries the size", "1.5 GB" in dlg.go.text(), True)
check("the state line names the language", "Tamil" in dlg.state.text(), True)
dlg.picker.setCurrentIndex(0)
check("…and the easy engine's button carries its own size",
      "0.1 GB" in dlg.go.text() or "60" in dlg.go.text(), True)
check("the log starts empty", dlg.log.toPlainText(), "")
dlg._finished({"ok": True, "engine": "indicf5", "why": "", "lines": []})
check("a real install says done", "is installed" in dlg.verdict.text(), True)
check("…and the list jumps to the engine it is talking about",
      dlg.picker.currentData(), "indicf5")
dlg._finished({"ok": False, "engine": "indicf5", "why": "cancelled", "lines": []})
check("a cancel says stopped, not done", dlg.verdict.text().startswith("Stopped"), True)
dlg._finished({"ok": False, "engine": "indicf5", "why": "exit code 1", "lines": []})
check("a failure admits it and keeps saying system voice",
      "system voice" in dlg.verdict.text(), True)

print("\n8) it is reachable from the two screens that mention it")
settings_src = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
voice_src = (ROOT / "arcdesk" / "widgets" / "voicelib_dialog.py").read_text(encoding="utf-8")
check("Settings → Voice opens it", "from .engine_dialog import EngineDialog" in settings_src,
      True)
check("the voice library opens it too",
      "from .engine_dialog import EngineDialog" in voice_src, True)
check("no command prompt is asked of the user in the honest line",
      "install_clone.bat" in (ROOT / "arcdesk" / "engines.py").read_text(encoding="utf-8"),
      True)
check("the engine module never claims ready without the weights",
      "weights did not arrive" in (ROOT / "arcdesk" / "engines.py").read_text(
          encoding="utf-8"), True)

print("\n9) the installed .exe: the engine goes in a private folder, one button")
import shutil  # noqa: E402

engines.external_python = lambda: "/usr/bin/python3"
check("nothing is ready in that folder yet", engines.sidecar_ready("indicf5"), False)
check("the app can say where it would live", "engine_env" in str(engines.sidecar_dir()), True)
check("the helper script ships with the app", engines.script_path("clone_speak.py").is_file(),
      True)


def venv_ok(target, on_line, cancel=None):
    (target / "bin").mkdir(parents=True, exist_ok=True)
    (target / "bin" / "python").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    return {"ok": True, "code": 0, "why": "", "last": "venv made"}


engines._make_venv = venv_ok        # noqa: SLF001
CALLS.clear()
engines._run = ok_run               # noqa: SLF001
sys.frozen = True
seen.clear()
got = engines.install("indicf5", on_line=seen.append)
check("one click installed it", got["ok"], True)
check("it built its own environment first", any("private engine folder" in l for l in seen),
      True)
check("it pip-installed WITH the borrowed python", "pip" in CALLS[0], True)
# frozen build: venv, then torch from the CPU index, then the rest, then the weights
check("it downloaded the weights too", "-c" in CALLS[-1], True)
check("…and torch still came from the CPU-only index",
      any(engines._TORCH_CPU_INDEX in c for c in CALLS), True)   # noqa: SLF001
check("now the folder counts as ready", engines.sidecar_ready("indicf5"), True)
check("...and only for the engine that finished", engines.sidecar_ready("xtts"), False)
del sys.frozen

print("\n10) the app then speaks through that folder, and only then")
written: list[list[str]] = []


def run_and_write(argv, on_line, cancel=None, on_progress=None):
    written.append(list(argv))
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
        out.write_bytes(b"RIFF" + b"\0" * 4000)
    return {"ok": True, "code": 0, "why": "", "last": ""}


engines._run = run_and_write        # noqa: SLF001
got = engines.sidecar_speak("vanakkam macha", "ta", _TMP + "/ref.wav", "vanakkam", _TMP + "/o.wav")
check("it spoke", got["ok"], True)
_argv = " ".join(written[-1])
check("with the engine that was installed", "--engine indicf5" in _argv, True)
check("and the sentence it was given", "--text vanakkam macha" in _argv, True)
check("the transcript travelled too", "--transcript vanakkam" in _argv, True)
check("a missing engine is refused, not guessed",
      engines.sidecar_speak("hi", "en", _TMP + "/ref.wav", "", _TMP + "/x.wav",
                            "xtts")["ok"], False)

# and clone.speak actually reaches it: no local packages, but a ready folder
from arcdesk import clone as _clone  # noqa: E402
_clone.refresh()
ref_path = Path(_clone.reference()) if _clone.reference() else None
if ref_path is None:
    ref_path = _clone.voice_dir() / "reference.wav"
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_bytes(b"RIFF" + b"\0" * 2000)
_clone.refresh()
check("the reference is in place", Path(_clone.reference()).exists(), True)
check("Tamil now routes to the cloned engine", _clone.route("ta"), "indicf5")
# The scenario is "no local packages, but a ready engine folder", so the in-process
# importer is pinned to NO. Without this the answer depends on whether the machine running
# the test happens to have transformers/torch installed — a developer's laptop does, and
# then speak() tries to load a real model instead of handing the sentence to the folder.
_real_local = _clone._local_engine                                      # noqa: SLF001
_clone._local_engine = lambda key: False                                # noqa: SLF001
try:
    check("speak() produced the wav through the folder",
          _clone.speak("vanakkam", "ta", wav=_TMP + "/spoken.wav"), True)
finally:
    _clone._local_engine = _real_local                                  # noqa: SLF001
check("...using the helper script",
      any("clone_speak.py" in a[1] for a in written), True)

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
