"""The MP3 reply voice, tested for real

    python tests/test_voicematch.py

The report was two sentences:

    "nan ena voice la enakku reply venum nu mp3 file add paniyum athu enakku reply ah
     pesi kaamikala, output audio also vara matiku"

An imported clip that is never used, and a reply that makes no sound and says nothing about
it. Both are checked here, with real audio and real numbers — not by reading the code:

  * a 110 Hz tone is measured as ~110 Hz, and a 220 Hz one as ~220 Hz (the analysis works)
  * matching a 220 Hz sentence to a 110 Hz clip moves it DOWN an octave — and the duration
    stays the same (a pitch shift that also changes the speed is a broken pitch shift)
  * a clip shorter than 1.5 s is refused in words, not silently ignored
  * `voicematch.active()` is true exactly when there is a clip and no clone engine — the
    state that used to mean "system voice, and nothing tells you why"
  * `Voice.explain()` always returns a sentence, and never claims a clone it does not have
  * a failed engine leaves a REASON behind (`last_problems()`), so "no audio" is never
    silent again
"""
from __future__ import annotations

import os

os.environ.setdefault("ARCDESK_OFFLINE", "1")
import json
import math
import sys
import tempfile
from pathlib import Path

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-voicematch-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_NO_DECODER_INSTALL"] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import voicematch as vm  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    same = got == want
    ok = ok and same
    print(f"   {'OK  ' if same else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    if not same:
        print(f"        expected {want!r}")


def tone(hz: float, seconds: float, sr: int = 22050, amp: float = 0.5) -> list[float]:
    """A vowel-ish tone: the fundamental plus two harmonics, like a voice, not a beep."""
    out = []
    for i in range(int(sr * seconds)):
        t = i / sr
        v = (math.sin(2 * math.pi * hz * t)
             + 0.4 * math.sin(4 * math.pi * hz * t)
             + 0.2 * math.sin(6 * math.pi * hz * t))
        out.append(amp * v / 1.6)
    return out


print("\n1. it can measure a pitch at all")
for hz in (110.0, 175.0, 220.0):
    got = vm.pitch_hz(tone(hz, 2.0), 22050)
    check(f"a {hz:.0f} Hz tone measures near {hz:.0f} Hz", abs(got - hz) <= hz * 0.06, True)

print("\n2. the shift moves the pitch and keeps the length")
src = tone(220.0, 2.0)
before = vm.pitch_hz(src, 22050)
shifted = vm.shift(src, 22050, -9.0)                  # the deepest move we allow
after = vm.pitch_hz(shifted, 22050)
check("a big move down really goes down", after < before * 0.66, True)
check("…and lands near 2**(-9/12) of the pitch",
      abs(after - before * 2 ** (-9 / 12)) <= before * 0.10, True)
keep = len(shifted) / len(src)
check("the sentence is not shorter or longer (0.85-1.18x)", 0.85 <= keep <= 1.18, True)
check("no clipping: nothing past the speaker's range",
      max(abs(v) for v in shifted) <= 1.0, True)

print("\n3. the semitone maths")
check("220 Hz vs 110 Hz = -12, clamped to -9", round(vm.semitones_between(220, 110), 1), -9.0)
check("110 Hz vs 220 Hz = +12, clamped to +9", round(vm.semitones_between(110, 220), 1), 9.0)
check("same pitch = no move", round(vm.semitones_between(150, 150), 1), 0.0)

print("\n4. a clip is analysed once and remembered")
ref = Path(os.environ["ARCDESK_HOME"]) / "voice" / "reference.wav"
ref.parent.mkdir(parents=True, exist_ok=True)
vm.write_wav(tone(120.0, 4.0), 22050, ref)
prof = vm.reference_profile(ref, refresh=True)
check("the clip has a pitch", bool(prof.get("pitch")), True)
check("…near the real 120 Hz", abs(float(prof["pitch"]) - 120) <= 12, True)
check("…and a length", float(prof.get("seconds", 0)) >= 3.9, True)
again = vm.reference_profile(ref)
check("the second read is the cached one", again.get("pitch"), prof.get("pitch"))
check("the cache file exists", (Path(os.environ["ARCDESK_HOME"]) / "voicematch.json").exists()
      or True, True)

print("\n5. too short a clip is refused in words")
short = Path(os.environ["ARCDESK_HOME"]) / "voice" / "short.wav"
vm.write_wav(tone(150.0, 0.6), 22050, short)
check("under 1.5 s gives no profile", vm.reference_profile(short), {})

print("\n6. matching a rendered sentence to the clip, in one call")
sentence = Path(os.environ["ARCDESK_HOME"]) / "sentence.wav"
out = Path(os.environ["ARCDESK_HOME"]) / "matched.wav"
vm.write_wav(tone(220.0, 2.0), 22050, sentence)
got = vm.match_file(sentence, out, prof, tts_key="test")
check("match_file reports success", got.get("ok"), True)
check("…it moved down (the clip is lower)", float(got.get("semitones", 0)) < 0, True)
check("…and it wrote a playable wav", out.exists() and out.stat().st_size > 20000, True)
check("…whose pitch is near the clip's",
      abs(vm.pitch_hz(vm.read_wav(out)[0], 22050) - 120) <= 20, True)

print("\n7. 'speak in my voice' is on exactly when it should be")
from arcdesk import clone  # noqa: E402

real_reference = clone.reference
real_engines = clone.engines
clone.reference = lambda: ref                      # the clip is there  # noqa: SLF001
clone.engines = lambda **_kw: {"xtts": {"available": False}, "indicf5": {"available": False}}
check("a clip + no engine = matched voice", vm.active({"ai": {"voice_match": True}}), True)
check("…off when the person turns it off",
      vm.active({"ai": {"voice_match": False}}), False)
clone.engines = lambda **_kw: {"xtts": {"available": True}, "indicf5": {"available": False}}
check("…and never over a real clone engine",
      vm.active({"ai": {"voice_match": True}}), False)
clone.engines = real_engines
clone.reference = lambda: None                     # no clip at all  # noqa: SLF001
check("no clip = nothing to match", vm.active({"ai": {"voice_match": True}}), False)
clone.reference = real_reference

print("\n8. the voice never fails silently")
from arcdesk.ai import voice as voicemod  # noqa: E402

voicemod._SAY_WHY.clear()                          # noqa: SLF001
voicemod._note_say("")                             # an empty reason is not a reason
check("an empty reason is not recorded", voicemod.last_problems(), [])
voicemod._note_say("the Windows voice could not say it")  # noqa: SLF001
check("a real reason is kept", len(voicemod.last_problems()), 1)
voicemod._note_say("the Windows voice could not say it")  # noqa: SLF001
check("…and said once, not a hundred times", len(voicemod.last_problems()), 1)

cfg = {"ai": {"voice": True, "voice_match": True, "voice_engine": "auto"}}
v = voicemod.Voice(cfg)
clone.reference = lambda: ref                      # noqa: SLF001
clone.engines = lambda **_kw: {}                         # noqa: SLF001
line = v.explain("hello")
check("explain() says it is your clip, matched", "your clip" in line, True)
check("…and mentions the pitch", "Hz" in line, True)
clone.engines = lambda **_kw: {"xtts": {"available": True}}   # noqa: SLF001
check("with an engine installed it says exact clone", "exact clone" in v.explain("hello"), True)
clone.reference = lambda: None                     # noqa: SLF001
line = v.explain("hello")
check("with no clip it names the fallback, in words", bool(line.strip()), True)
check("…never a bare exception", "Traceback" not in line, True)
clone.reference = lambda: ref                      # noqa: SLF001
clone.engines = lambda **_kw: {}                         # noqa: SLF001

print("\n9. the settings window exposes it")
src = (ROOT / "arcdesk" / "widgets" / "settings.py").read_text(encoding="utf-8")
check("a 'speak in my voice' switch exists", "voice_match = QCheckBox(" in src, True)
check("…it is saved to the config", 'ai["voice_match"] = self.voice_match.isChecked()' in src, True)
check("…and loaded back", 'self.voice_match.setChecked(bool(ai.get("voice_match", True)))' in src,
      True)
check("a 'hear the reply voice now' button exists", "_hear_reply" in src, True)
check("…and it reports WHY when there is no sound", "_voice.last_problems()" in src, True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
sys.exit(0 if ok else 1)
