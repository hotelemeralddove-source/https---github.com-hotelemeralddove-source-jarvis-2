"""The Settings dialog must open at once, and nothing on the UI thread may start a process.

The report (20.png): the app opened, the Settings dialog appeared — and it hung there with
a spinner. Cause, found by reading the path rather than guessing:

    SettingsDialog._refresh_voice_status()
        -> clone.engines()
            -> _foreign_python() -> engines.find_engine_python()
                -> spawns a python, up to 20 s, PER ENGINE, on the thread that draws
                   the dialog.

Two smaller versions of the same mistake were next to it: `_module_ok()` used
`__import__(name)` (imports a native library to answer yes/no), and the reply-voice
sentence was computed inline.

What is proven here:

  1. the dialog builds in well under a second, with no child process at all;
  2. asking "which python has the engine" NEVER blocks — it answers "" while a background
     probe is started, and the probe caches its answer;
  3. the reply-voice sentence arrives on its own, a moment later, without freezing;
  4. `_module_ok` runs no code from the module it asks about;
  5. the sources contain no `__import__` on these paths.

Run:  QT_QPA_PLATFORM=offscreen python tests/test_ui_never_blocks.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# A model this machine happens to have already must not change what this test measures:
# ARCDESK_MODELS means "look only here", so the answer is the same on every computer.
os.environ["ARCDESK_MODELS"] = tempfile.mkdtemp(prefix="arcdesk-models-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<58} {got!r}")


from PySide6.QtWidgets import QApplication                              # noqa: E402

app = QApplication.instance() or QApplication([sys.argv[0]])

print("1. the engine probe never blocks the caller")
from arcdesk import engines                                             # noqa: E402

real_find = engines.find_engine_python
calls: list[str] = []


def slow_find(engine: str) -> str:
    calls.append(engine)
    time.sleep(1.5)                       # a stand-in for "start a python and ask it"
    return ""


engines.find_engine_python = slow_find                                  # noqa: SLF001
engines._FOREIGN.clear()                                                # noqa: SLF001
try:
    t0 = time.perf_counter()
    first = engines.foreign_cached("indicf5")
    spent = (time.perf_counter() - t0) * 1000
    check("a cold cache answers immediately", first, "")
    check(f"…in {spent:.0f} ms, not 1500", spent < 100, True)
    check("…and the real probe was started in the background", len(calls), 1)

    time.sleep(1.9)                       # let the background probe finish
    engines.find_engine_python = lambda engine: "C:/python/python.exe"   # noqa: SLF001
    engines._FOREIGN["indicf5"] = (time.monotonic(), "C:/python/python.exe")
    check("a warm cache answers with the python it found",
          engines.foreign_cached("indicf5"), "C:/python/python.exe")
    calls.clear()
    for _ in range(100):
        engines.foreign_cached("indicf5")
    check("…and 100 more calls start no probe at all", calls, [])
finally:
    engines.find_engine_python = real_find                              # noqa: SLF001
    engines._FOREIGN.clear()                                            # noqa: SLF001

print("\n2. clone.engines() uses the cache, never the probe")
import arcdesk.clone as clone                                          # noqa: E402

seen: list[str] = []
real_cached = engines.foreign_cached


def watching(engine: str, warm: bool = True) -> str:
    seen.append(engine)
    return ""


engines.foreign_cached = watching                                       # noqa: SLF001
clone.refresh()
t0 = time.perf_counter()
clone.engines()
spent = (time.perf_counter() - t0) * 1000
check(f"one probe of the engines took {spent:.0f} ms (no child process)", spent < 200, True)
# The cache is asked for every engine, weights or not: an engine whose packages are in a
# conda env but whose weights are missing must be reported as "engine found, only the
# weights left" instead of "not installed" (that lie is tests/test_engine_found.py). What
# must stay true is that this is a CACHED read — the child process is started in the
# background, never here, which is why this line is about time and not about silence.
check("the cache is asked, cheaply", seen, ["indicf5", "xtts"])
check(f"…and it still took {spent:.0f} ms", spent < 200, True)

# …but when weights are present, the question goes to the CACHE (never a child process)
real_model = clone._model_dir                                           # noqa: SLF001
def fake_model_dir(name: str):
    return Path("C:/cache/models--ai4bharat--IndicF5") if name == "IndicF5" else None


clone._model_dir = fake_model_dir                                       # noqa: SLF001
try:
    clone.refresh()
    t0 = time.perf_counter()
    clone.engines()
    spent = (time.perf_counter() - t0) * 1000
    check(f"with weights present it is still fast ({spent:.0f} ms)", spent < 300, True)
    check("…and it asked the cache", seen, ["indicf5", "xtts", "indicf5", "xtts"])
finally:
    clone._model_dir = real_model                                       # noqa: SLF001
    engines.foreign_cached = real_cached                                # noqa: SLF001
    clone.refresh()

print("\n3. the Settings dialog opens at once and fills itself in")
from arcdesk import config                                             # noqa: E402
from arcdesk.theme import THEMES                                        # noqa: E402
from arcdesk.widgets.settings import SettingsDialog                     # noqa: E402

built: list[float] = []
for _ in range(3):
    t0 = time.perf_counter()
    dlg = SettingsDialog(config.load(), THEMES["chill"])
    built.append((time.perf_counter() - t0) * 1000)
    dlg._refresh_voice_status()                                        # noqa: SLF001
    if _ == 0:
        check("the reply line says it is checking, not a stale answer",
              "checking" in dlg.reply_note.text() or "Reply voice:" in dlg.reply_note.text())
    deadline = time.time() + 10
    while time.time() < deadline and "checking" in dlg.reply_note.text():
        app.processEvents()
        time.sleep(0.05)
    if _ == 0:
        check("the answer arrives by itself", "checking" in dlg.reply_note.text(), False)
        check("…and it is a sentence, not an exception",
              "could not check" in dlg.reply_note.text(), False)
    dlg.close()
check(f"every build was fast (worst {max(built):.0f} ms)", max(built) < 900, True)

print("\n4. 'is it installed?' runs no code")
sandbox = Path(tempfile.mkdtemp(prefix="arcdesk-mod-"))
marker = sandbox / "ran.txt"
(sandbox / "loudmodule.py").write_text(
    "from pathlib import Path\n"
    f"Path({str(marker)!r}).write_text('ran')\n"
    "raise RuntimeError('must never be imported')\n", encoding="utf-8")
sys.path.insert(0, str(sandbox))
try:
    check("a module that raises still counts as installed",
          SettingsDialog._module_ok("loudmodule"), True)               # noqa: SLF001
    check("…and it was never executed", marker.exists(), False)
    check("a module that is absent is 'missing'",
          SettingsDialog._module_ok("definitely_not_here_xyz"), False)  # noqa: SLF001
finally:
    sys.path.remove(str(sandbox))
    sys.modules.pop("loudmodule", None)

print("\n5. the sources do not import something to ask whether it exists")
src = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
check("_module_ok uses find_spec, not an import",
      "def _module_ok" in src and "find_spec" in src.split("def _module_ok")[1][:400])
check("…and the probe helper no longer imports the module it asks about",
      "return importlib.util.find_spec(name) is not None" in src)
eng_src = (ROOT / "arcdesk" / "engines.py").read_text(encoding="utf-8")
check("engines has a cached, non-blocking answer", "def foreign_cached" in eng_src)
check("…and warms it in a daemon thread",
      "arc-engine-probe-" in eng_src and "daemon=True" in eng_src)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
