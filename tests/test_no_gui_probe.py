"""The drawing thread must never pay for an engine probe

    python tests/test_no_gui_probe.py

The report (28.png): the Settings window sat "(Not Responding)" for minutes, then the
app was gone. The status card refreshes every 10 s on the drawing thread, and its voice
line asked `clone.engines()` for a fresh answer — a cold cache means "ask every python
on this PC what it has", which on a machine that already installed the engine takes
minutes. So the drawing thread now asks for the cache only, and the Windows voice list
is probed once at start-up, off-thread, before anyone needs it.
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-noprobe-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {str(got)[:46]!r}")
    if not same:
        print(f"        expected {want!r}")


from arcdesk import clone  # noqa: E402

print("\n1. a cold cache with cached_only=True probes nothing")
clone.refresh()                       # cold
probed: list[str] = []
real_foreign = clone._foreign_python  # noqa: SLF001
clone._foreign_python = lambda key: (probed.append(key), "C:\\probe\\python.exe")[1]
try:
    got = clone.engines(cached_only=True)
finally:
    clone._foreign_python = real_foreign
check("…it returns the (empty) last-known state", got, {})
check("…and asked no interpreter anything", probed, [])

print("\n2. a warm cache answers without re-probing")
clone._CACHE["data"] = {"indicf5": {"available": True}}   # noqa: SLF001
clone._CACHE["at"] = 0.0                                  # noqa: SLF001 — force the cold branch
import time as _time                                        # noqa: E402
clone._CACHE["at"] = _time.monotonic()                     # noqa: SLF001
clone._foreign_python = lambda key: (probed.append(key), "x")[1]
try:
    got = clone.engines(cached_only=True)
finally:
    clone._foreign_python = real_foreign
check("…the warm answer is the warm answer", got.get("indicf5", {}).get("available"), True)
check("…still no probe", probed, [])

print("\n3. the status card's voice line never pays for a probe")
clone.refresh()
from arcdesk.widgets.settings import SettingsDialog  # noqa: E402
# a clip exists, so the line reaches the engines question
from arcdesk import voicelib as _vl  # noqa: E402
clip = Path(os.environ["ARCDESK_HOME"]) / "clip.wav"
import struct as _struct, wave as _wave  # noqa: E402
if not clip.exists():
    with _wave.open(str(clip), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(_struct.pack("<%dh" % 22050, *([1000] * 22050)))
# point the reference at the clip without importing anything heavy
ref_dir = clone.voice_dir()
ref_dir.mkdir(parents=True, exist_ok=True)
(ref_dir / "reference.wav").write_bytes(clip.read_bytes())
clone.refresh()
clone._foreign_python = lambda key: (probed.append(key), "x")[1]
try:
    line = SettingsDialog.reply_voice_line({}, cached_only=True)
finally:
    clone._foreign_python = real_foreign
clone.refresh()
check("…it says it is checking, in words", "checking which engine" in line, True)
check("…and it probed nothing on the way", probed, [])

print("\n4. the voice list is a one-time background cost")
from arcdesk.ai import voice as _voice  # noqa: E402
_voice._VOICE_CACHE = None
check("…unknown until probed", _voice.voice_names_cached(), None)
_voice.voice_names_ensure()             # on Linux: no Windows, empty list, no probe
check("…probed once, remembered forever after",
      _voice.voice_names_cached() is not None, True)

print("\n5. the source keeps the rule in the two hot places")
win_src = (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
set_src = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
run_src = (ROOT / "run.py").read_text(encoding="utf-8")
check("…the status card asks cache-only",
      'self.reply_voice_line(cached_only=True)' in win_src, True)
check("…the accent note reads the cache, not the probe",
      "voice_names_cached()" in set_src, True)
check("…and start-up pays both probes off-thread",
      "voice_names_ensure" in run_src and "arc-warm" in run_src
      and "engines(cached_only=False)" in run_src, True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
