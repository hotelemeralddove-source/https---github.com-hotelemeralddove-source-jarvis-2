"""Installing a voice engine must never be able to close the app.

The report: *"piper and innoru voice tool install pananum then application auto close
aaguthu"*. Two ways that used to happen, both now closed:

  1. `pip install` was aimed at the environment the app was RUNNING in. A live process
     with files swapped under it (coqui-tts even pins an older numpy) is a crash waiting
     for the next import.
  2. `__import__("piper")` / `__import__("torch")` was used to answer "is it installed?".
     Loading onnxruntime or torch next to Qt's own DLLs can end the process with **no
     traceback at all** — the window simply disappears.

What is proven here:

  1. asking "is it installed" executes nothing (a module that raises on import still
     answers "installed", and its side effect never happens);
  2. `piper_available()` never imports piper;
  3. piper speaks in a CHILD process, and `piper` is not in this process's modules after;
  4. the Install button never runs `pip` against the interpreter the app is running in;
  5. a crash that Python cannot catch is still recorded (faulthandler), and an unclean
     exit is reported on the next start.

Run:  python tests/test_install_safe.py
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
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import clone, engines, logs, piper_engine, quiet  # noqa: E402

# The licence gate is a network question ("is this model's file readable without a token?").
# These checks are about WHERE an install goes and WHAT it runs, so the gate is stubbed to
# say YES here. The real gate has its own checks: §6 of tests/test_engine_progress.py, and
# tools/engine_get.py gate.
engines._http_status = lambda url="", token="", timeout=12.0: 200       # noqa: SLF001
# The free-space guard runs before an install starts. This test's HOME is a small tmpfs,
# so without this every engine would be refused for the wrong reason; the guard has its
# own checks in tests/test_engine_auto.py (§8).
engines.free_gb = lambda path=None: 999.0                               # noqa: SLF001


ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<58} {got!r}")


print("1. asking whether a package is installed runs no code")
sandbox = Path(tempfile.mkdtemp(prefix="arcdesk-spec-"))
marker = sandbox / "executed.txt"
(sandbox / "boom_module.py").write_text(
    "from pathlib import Path\n"
    f"Path({str(marker)!r}).write_text('ran')\n"
    "raise RuntimeError('this module must never be imported')\n", encoding="utf-8")
sys.path.insert(0, str(sandbox))
try:
    check("a module that raises on import still counts as installed",
          clone._importable("boom_module"), True)            # noqa: SLF001
    check("…and it was never executed", marker.exists(), False)
    check("a module that is not there is still 'missing'",
          clone._importable("definitely_not_a_module_xyz"), False)  # noqa: SLF001
finally:
    sys.path.remove(str(sandbox))
    sys.modules.pop("boom_module", None)

print("\n2. piper_available() does not import piper")
(fake_dir := Path(tempfile.mkdtemp(prefix="arcdesk-piper-"))).mkdir(exist_ok=True)
piper_marker = fake_dir / "piper_imported.txt"
(fake_dir / "piper.py").write_text(
    "from pathlib import Path\n"
    f"Path({str(piper_marker)!r}).write_text('ran')\n"
    "raise SystemExit('importing piper here would have ended the app')\n",
    encoding="utf-8")
sys.path.insert(0, str(fake_dir))
try:
    sys.modules.pop("piper", None)
    from arcdesk.ai import voice
    got = voice.piper_available()          # must not raise, must not import
    check("asking for piper returns a plain True/False", isinstance(got, bool))
    check("…and piper was not imported", piper_marker.exists(), False)
    check("…and 'piper' is not in this process's modules", "piper" in sys.modules, False)
finally:
    sys.path.remove(str(fake_dir))
    sys.modules.pop("piper", None)

print("\n3. piper speaks in a child process")
seen: list[list[str]] = []
real_run = quiet.run


class _Fake:
    returncode = 0
    stdout = "PIPER-OK\n"
    stderr = ""


def fake_run(argv, **kw):
    seen.append(list(argv))
    out = Path(argv[argv.index("-c") + 3])          # the wav path passed to the script
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"RIFF" + b"\0" * 4000)
    return _Fake()


voice_file = Path(tempfile.mkdtemp(prefix="arcdesk-voice-")) / "en_US-ryan.onnx"
voice_file.write_bytes(b"onnx")
out_wav = Path(tempfile.mkdtemp(prefix="arcdesk-wav-")) / "say.wav"
piper_engine.refresh()
real_pyp = piper_engine.python_with_piper
try:
    quiet.run = fake_run                                    # noqa: SLF001
    piper_engine.python_with_piper = lambda refresh=False: sys.executable  # noqa: SLF001
    got = piper_engine.speak("vanakkam macha", str(voice_file), str(out_wav), 1.1)
    check("a sentence produces a wav", got.get("ok"), True)
    check("…through a separate process", len(seen), 1)
    check("…that is an interpreter, not this app", seen[0][0], sys.executable)
    check("…running a tiny -c script", "-c" in seen[0])
    check("…and piper is still NOT loaded in the app", "piper" in sys.modules, False)
    check("the wav really exists on disk", out_wav.stat().st_size > 1000, True)

    quiet.run = lambda argv, **kw: type("R", (), {"returncode": 1, "stdout": "",
                                                  "stderr": "boom\n"})()
    bad = piper_engine.speak("x", str(voice_file), str(Path(tempfile.mkdtemp()) / "b.wav"))
    check("a child that dies is a failed sentence, not a dead app", bad.get("ok"), False)
    check("…and it says why", "piper could not speak" in bad.get("why", ""), True)
    missing = piper_engine.speak("x", str(voice_file), "", python="")
    check("no interpreter at all is reported, not guessed", missing.get("ok"), False)
finally:
    quiet.run = real_run                                     # noqa: SLF001
    piper_engine.python_with_piper = real_pyp                # noqa: SLF001
    piper_engine.refresh()

print("\n4. the Install button never pips into the running app")
calls: list[list[str]] = []
real_sidecar = engines.ensure_sidecar
real_erun = engines._run                                     # noqa: SLF001
try:
    def fake_sidecar(engine, on_line=None, cancel=None, on_progress=None):
        calls.append(["ensure_sidecar", engine])
        return {"ok": True, "engine": engine, "why": "", "lines": ["ok"]}

    def fake_run(argv, *a, **k):
        calls.append(list(argv))
        return {"ok": True, "code": 0, "why": "", "last": ""}

    engines.ensure_sidecar = fake_sidecar                     # noqa: SLF001
    engines._run = fake_run                                   # noqa: SLF001
    for engine in ("piper", "indicf5", "xtts"):
        engines.install(engine)
    check("all three engines go to the private folder", [c[1] for c in calls
                                                        if c[0] == "ensure_sidecar"],
          ["piper", "indicf5", "xtts"])
    check("nothing was installed into this interpreter",
          [c for c in calls if c[0] == sys.executable], [])
    said: list[str] = []
    engines.install("piper", on_line=said.append)
    joined = " ".join(said)
    check("…the reason is on screen, not only in the code", "own folder" in joined, True)
finally:
    engines.ensure_sidecar = real_sidecar                     # noqa: SLF001
    engines._run = real_erun                                  # noqa: SLF001

print("\n5. a native crash still leaves a trail")
logs.install()
logs.watch_crashes()
check("the fault log is created", logs.fault_path().exists(), True)
_fault = getattr(sys, "_arcdesk_fault_file", None)
check("faulthandler is watching (an open file, not just a path)",
      bool(_fault) and not _fault.closed, True)
first = logs.begin_session()
check("a first ever start has nothing to report", first, "")
logs.begin_session()
second = logs.begin_session()
check("a start after an unclean exit SAYS so", "stopped without closing properly" in second,
      True)
logs.end_session()
third = logs.begin_session()
check("after a normal close there is nothing to report", third, "")
logs.end_session()

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
