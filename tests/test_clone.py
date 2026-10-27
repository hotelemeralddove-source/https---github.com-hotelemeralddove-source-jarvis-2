"""Your voice, or an honest reason you are not hearing it.

The ask: *"naan enna language-la pesunalum, reply antha language-la varanum, aana
voice naan upload panna clip-oda voice-la irukanum"* — voice cloning, per language.

This test covers the decisions, not the 1-2 GB models (they cannot run here):

  * language routing: Tamil/Indic -> IndicF5, English -> XTTS, and an honest
    fallback (piper / SAPI) when neither is installed;
  * Tamil NEVER silently goes to XTTS, which cannot pronounce it;
  * a reference clip is trimmed to real speech, normalised, resampled to 24 kHz,
    and an edited clip with cuts is stitched rather than refused;
  * a clip with too little speech is refused with a sentence;
  * the transcript is stored, because IndicF5 needs it;
  * `speak()` returns False (so the caller falls back) instead of raising;
  * the plan tells the truth about what is installed.

Run:  python tests/test_clone.py
"""
from __future__ import annotations

import math
import os
import sys
import tempfile
import wave
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="arcdesk-clone-")
os.environ["ARCDESK_HOME"] = HOME
# A test must never start a pip install of an audio decoder: that turned a one-line
# assertion into a 20-second network call, and on a Windows laptop it hung.
os.environ["ARCDESK_NO_DECODER_INSTALL"] = "1"
# A model this machine already has must not change what this test measures:
# ARCDESK_MODELS means "look only here", so the answer is the same everywhere.
os.environ["ARCDESK_MODELS"] = tempfile.mkdtemp(prefix="arcdesk-models-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import clone  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:34]!r}")
    ok &= bool(good)


def tone(seconds: float, sr: int = 16000, freq: float = 180.0,
         amp: float = 0.25, silence_after: float = 0.0) -> list[float]:
    n = int(seconds * sr)
    out = [amp * math.sin(2 * math.pi * freq * i / sr) for i in range(n)]
    out += [0.0] * int(silence_after * sr)
    return out


def write(samples: list[float], sr: int, name: str) -> str:
    p = Path(HOME) / name
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(int(max(-1, min(1, s)) * 32767).to_bytes(2, "little",
                                                                       signed=True)
                               for s in samples))
    return str(p)


NO_ENGINES = {"indicf5": {"available": False, "module": "transformers", "model": "",
                          "why": "missing it"},
              "xtts": {"available": False, "module": "TTS", "model": "", "why": "missing it"},
              "piper": {"available": False, "module": "piper", "model": "", "why": "no piper"}}
ALL_ENGINES = {k: {"available": True, "module": "x", "model": "/models/x", "why": ""}
               for k in ("indicf5", "xtts", "piper")}

print("\n0) probing engines is cached (route() runs on every sentence)")
real_engines = clone.engines
probes = []
real_importable = clone._importable
clone._importable = lambda m: (probes.append(m), real_importable(m))[1]
clone.refresh()
import time as _t
t0 = _t.perf_counter()
for _ in range(100):
    clone.route("en")
elapsed = (_t.perf_counter() - t0) * 1000
first_round = len(probes)
check("100 routes do not re-import engines", first_round, 2)
# The real assertion is the line above: no re-import, no child process. The number is a
# sanity bound, and 20 ms for 100 calls was measured on an idle machine — six test
# processes on an overloaded build host made it flake without anything being slower.
check("and are fast (under 60 ms total)", elapsed < 60, True)
clone.refresh()
clone.route("en")
check("refresh() does re-probe", len(probes) > first_round, True)
clone._importable = real_importable

print("\n1) language routing, with nothing installed")
clone.engines = lambda: NO_ENGINES
clone.reference = lambda: None
check("Tamil falls back to SAPI", clone.route("ta"), "sapi")
check("English falls back to SAPI", clone.route("en"), "sapi")
check("regional code works", clone.route("ta-IN"), "sapi")
check("unknown code does not crash", clone.route(""), "sapi")

print("\n2) engines installed but no reference clip yet -> still no cloning")
clone.engines = lambda: ALL_ENGINES
check("Tamil without a clip -> piper", clone.route("ta"), "piper")
check("English without a clip -> piper", clone.route("en"), "piper")

print("\n3) engines installed AND a reference clip -> the cloned voice")
clone.reference = lambda: Path(HOME) / "reference.wav"
check("Tamil -> IndicF5", clone.route("ta"), "indicf5")
check("Hindi -> IndicF5", clone.route("hi"), "indicf5")
check("Kannada -> IndicF5", clone.route("kn"), "indicf5")
check("English -> XTTS", clone.route("en"), "xtts")
check("Tamil never goes to XTTS", clone.route("ta") != "xtts", True)
check("XTTS is not asked for a language it lacks", "ta" not in clone.XTTS_LANGS, True)
check("IndicF5 covers Tamil", "ta" in clone.INDIC_LANGS, True)

print("\n4) an Indic language with only XTTS available drops to piper, not to XTTS")
weird = {"indicf5": {"available": False, "module": "transformers", "model": "", "why": "no"},
         "xtts": {"available": True, "module": "TTS", "model": "/models/x", "why": ""},
         "piper": {"available": True, "module": "piper", "model": "", "why": ""}}
clone.engines = lambda: weird
check("Tamil -> piper (real Tamil, wrong voice)", clone.route("ta"), "piper")
check("English -> xtts (clone works)", clone.route("en"), "xtts")

print("\n4b) a plain WAV imports even with NO ffmpeg on the machine")
# The Windows CI runner has no ffmpeg. A 16 kHz WAV went through the ffmpeg branch and
# the import failed with "ffmpeg is needed" — for a file Python reads perfectly well.
_saved_ff = clone._ffmpeg
clone._ffmpeg = lambda: ""
try:
    plain = write(tone(9.0, 16000, silence_after=0.5), 16000, "plain16k.wav")
    got_plain = clone.import_reference(plain)
    check("imported a 16 kHz WAV without ffmpeg", got_plain["ok"], True)
    check("...and it is now 24 kHz as promised",
          wave.open(str(Path(clone.voice_dir()) / "reference.wav")).getframerate(), 24000)
    mp3ish = Path(HOME) / "fake.mp3"
    mp3ish.write_bytes(b"not really an mp3")
    # Since the app brought its own decoders the sentence changed: a codec it cannot
    # read is reported as a decoder problem (and this test forbids installing one), so
    # the message must name the fix — a .wav — rather than blame the person.
    bad = clone.import_reference(str(mp3ish))["message"].lower()
    check("a codec it cannot read still explains itself",
          ("wav" in bad) and ("could not read" in bad or "decoder" in bad), True)
finally:
    clone._ffmpeg = _saved_ff

print("\n5) a clean 8 s clip becomes the reference")
clean = write(tone(8.0, 16000, silence_after=1.0), 16000, "clean.wav")
got = clone.import_reference(clean, "this is my voice")
check("imported", got["ok"])
check("about 8 s kept", 7.0 <= got["seconds"] <= 8.2, True)
ref = Path(clone.voice_dir()) / "reference.wav"
check("reference.wav written", ref.exists())
check("transcript stored", (Path(clone.voice_dir()) / "reference.txt").read_text(encoding="utf-8").strip(),
      "this is my voice")
with wave.open(str(ref)) as w:
    check("mono", w.getnchannels(), 1)
    check("24 kHz, which the engines expect", w.getframerate(), clone.SAMPLE_RATE)
    check("16-bit", w.getsampwidth(), 2)
with wave.open(str(ref)) as w:
    frames = w.readframes(w.getnframes())
    import array
    a = array.array("h")
    a.frombytes(frames)
    peak = max(abs(v) for v in a) / 32768
check("peaks under 0 dBFS (no clipping)", peak <= 0.80, True)
check("loud enough to clone", peak > 0.10, True)

print("\n6) an edited clip with cuts is stitched, not refused")
cut = (tone(1.2, 16000, silence_after=1.8) + tone(1.4, 16000, freq=200, silence_after=2.0)
       + tone(1.3, 16000, freq=160, silence_after=1.5) + tone(1.5, 16000, freq=190))
got = clone.import_reference(write(cut, 16000, "cut.wav"))
check("imported anyway", got["ok"])
check("stitched from several pieces", "stitched" in got["message"], True)
check("long enough to use", got["seconds"] >= clone.MIN_SECONDS, True)

print("\n7) too little speech is refused with a sentence")
tiny = write(tone(0.4, 16000, silence_after=2.0), 16000, "tiny.wav")
got = clone.import_reference(tiny)
check("refused", got["ok"], False)
check("says how much is needed", "at least" in got["message"], True)
check("no such file is a sentence too", clone.import_reference("/nope/missing.wav")["ok"], False)

print("\n8) never raises, always falls back")
clone.reference = lambda: None
check("speak() without a reference is False", clone.speak("hello there", "en"), False)
clone.reference = lambda: Path(HOME) / "reference.wav"
clone.engines = lambda: NO_ENGINES
check("speak() without an engine is False", clone.speak("hello there", "en"), False)
check("empty text is False", clone.speak("   ", "en"), False)

print("\n9) the plan is honest about what is installed")
clone.engines = lambda: NO_ENGINES
plan = clone.plan()
check("reports three engines", len(plan["engines"]) >= 3, True)
check("each has a reason when missing",
      all(("why" in e) for e in plan["engines"].values()), True)
check("lists the real limits", len(plan["limits"]) >= 3, True)
check("says Tamil needs IndicF5",
      any("IndicF5" in x or "Tamil" in x for x in plan["limits"]), True)
check("describe() mentions Tamil routing", "Tamil" in clone.describe(), True)

print("\n" + ("ALL PASS" if ok else "SOMETHING FAILED"))
sys.exit(0 if ok else 1)
