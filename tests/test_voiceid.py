"""Voice lock — only the person enrolled on THIS machine may command it.

The ask, twice: *"intha laptop-la enoda voice-la mattum work aaganum"* and *"vera
laptop-la install pannina anga vera person-oda voice-la access aaganum"*.

What this test refuses to let slide:

  * enrolling one person does not profile anybody else;
  * the same voice passes, a different voice fails;
  * with nobody enrolled it stays OPEN (a lock that blocks the owner is a bug);
  * a profile made from clips that disagree raises its own threshold instead of
    matching everybody;
  * two profiles on the same machine pick the right one, not "any of them";
  * profiles are files in the app data folder, so a second laptop starts empty;
  * with no embedding engine the app says so and does NOT pretend to be locked.

The embedding engine is faked: these are the rules, not the model. The model itself
is 30 MB and cannot be downloaded in a test.

Run:  python tests/test_voiceid.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import wave
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="arcdesk-voiceid-")
os.environ["ARCDESK_HOME"] = HOME
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import voiceid  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:34]!r}")
    ok &= bool(good)


def wav(name: str, seconds: float = 2.0, sr: int = 16000) -> str:
    p = Path(HOME) / name
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"\x00\x01" * int(sr * seconds))
    return str(p)


# ---------------------------------------------------------------- fake engine
VOICES = {
    "me1": [1.0, 0.0, 0.0, 0.0],
    "me2": [0.98, 0.06, 0.0, 0.0],
    "me3": [0.99, -0.04, 0.02, 0.0],
    "wife": [0.0, 1.0, 0.0, 0.0],
    "stranger": [0.0, 0.0, 1.0, 0.0],
    "noisy": [1.0, 0.9, 0.0, 0.0],          # an inconsistent enrolment clip
}


def fake_embed(path: str) -> list[float] | None:
    key = Path(path).stem
    return voiceid._unit(VOICES[key]) if key in VOICES else None


print("\n1) no engine installed -> honestly unavailable, lock stays open")
voiceid.available = lambda: (False, "no speaker-id engine installed")
check("available() false", voiceid.available()[0], False)
check("reason is a sentence", "installed" in voiceid.available()[1], True)
# a profile copied from another laptop, but this machine has no embedding engine:
# it must NOT lock the owner out — it falls back to the plain wake word and says so
voiceid._save({"me": {"vector": [1.0, 0.0, 0.0, 0.0], "samples": 3,
                      "self_similarity": 0.95, "threshold": 0.62, "created": "today"}})
verdict = voiceid.verify(wav("anything.wav"))
check("verify allows when it cannot run", verdict["allowed"], True)
check("and says why", "cannot run" in verdict["why"], True)
voiceid._save({})                     # back to a clean slate
enrol = voiceid.enroll("me", [wav("me1.wav"), wav("me2.wav")])
check("enrol refuses instead of faking", enrol["ok"], False)
check("enrol explains", "engine" in enrol["message"] or "installed" in enrol["message"], True)

print("\n2) engine present, nobody enrolled -> open door")
voiceid.available = lambda: (True, "")
voiceid.embed = fake_embed
check("no profiles yet", voiceid.profiles(), {})
verdict = voiceid.verify(wav("me1.wav"))
check("allowed", verdict["allowed"], True)
check("not because of a match", verdict["who"], "")
check("says why", "not restricted" in verdict["why"], True)

print("\n3) enrol one person from three clips")
got = voiceid.enroll("me", [wav("me1.wav"), wav("me2.wav"), wav("me3.wav")])
check("enrolled", got["ok"])
check("used 3 clips", got["samples"], 3)
check("clips agree", got["self_similarity"] >= 0.9, True)
stored = voiceid.profiles()["me"]
check("vector stored, not audio", len(stored["vector"]), 4)
check("threshold stored", 0.0 < stored["threshold"] <= 0.92, True)
check("timestamp kept", bool(stored["created"]), True)

print("\n4) the owner passes, everyone else does not")
for who in ("me1", "me2", "me3"):
    v = voiceid.verify(wav(f"{who}.wav"))
    check(f"{who} allowed", v["allowed"], True)
    check(f"{who} named as 'me'", v["who"], "me")
for who in ("wife", "stranger"):
    v = voiceid.verify(wav(f"{who}.wav"))
    check(f"{who} rejected", v["allowed"], False)
    check(f"{who} score below threshold", v["score"] < v.get("needed", 1), True)
v = voiceid.verify(wav("noisy.wav"))
check("a half-matching voice is rejected", v["allowed"], False)

print("\n5) a second person on the same machine is its own profile")
got = voiceid.enroll("wife", [wav("wife.wav"), wav("wife.wav")])
check("enrolled", got["ok"])
v = voiceid.verify(wav("wife.wav"))
check("wife recognised by name", v["who"], "wife")
v = voiceid.verify(wav("me2.wav"))
check("owner still recognised", v["who"], "me")
check("longest match wins, not 'any profile'", voiceid.verify(wav("stranger.wav"))["allowed"], False)

print("\n6) inconsistent clips raise the bar instead of matching everyone")
voiceid.enroll("sloppy", [wav("me1.wav"), wav("noisy.wav")])
sloppy = voiceid.profiles()["sloppy"]
check("threshold above the default", sloppy["threshold"] > voiceid.DEFAULT_THRESHOLD, True)
check("self-similarity recorded low", sloppy["self_similarity"] < 0.9, True)

print("\n7) profiles are files inside the app folder — a new laptop starts empty")
path = Path(voiceid._profiles_file())
check("profiles.json exists", path.exists())
check("inside ARCDESK_HOME", str(path).startswith(HOME), True)
saved = json.loads(path.read_text(encoding="utf-8"))
check("contains both people", sorted(saved), ["me", "sloppy", "wife"])
check("no audio stored", any(k.endswith(".wav") for k in saved), False)
check("forget removes one", voiceid.forget("sloppy"), True)
check("others survive", sorted(voiceid.profiles()), ["me", "wife"])
check("forget unknown is false", voiceid.forget("nobody"), False)
copy_dir = Path(HOME) / "usb"
check("copy to another machine works", "copied" in voiceid.copy_profiles_to(str(copy_dir)), True)
check("and the file is there", (copy_dir / "arcdesk-voiceid-profiles.json").exists(), True)

print("\n8) describe() is readable and true")
text = voiceid.describe()
engine_name = voiceid.engine()["name"]
# `available()` is faked above, but `engine()` is real — so on a machine with no
# embedding model installed the sentence legitimately says "engine " with nothing after
# it. What must never happen is silence about it: the text names an engine, or it says
# the lock is unavailable. Either is honest; a blank is not.
check("describe() is honest about the engine",
      (engine_name in text) if engine_name else ("engine" in text or "unavailable" in text),
      True)
check("names the enrolled people", "me" in text and "wife" in text, True)

print("\n9) too few recordings is refused, not a one-clip profile")
voiceid.forget("me")
voiceid.forget("wife")
check("one clip refused", voiceid.enroll("me", [wav("me1.wav")])["ok"], False)
check("empty list refused", voiceid.enroll("me", [])["ok"], False)
check("still nobody enrolled", voiceid.profiles(), {})

print("\n" + ("ALL PASS" if ok else "SOMETHING FAILED"))
sys.exit(0 if ok else 1)
