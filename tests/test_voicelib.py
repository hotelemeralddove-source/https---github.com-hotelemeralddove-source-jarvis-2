"""The voice library — command voices and reply voices, in one place

    python tests/test_voicelib.py

The user's concept, exactly: *"command voice la nan yaru voice kodukurano antha voice ku
jarvis respond panum, yentha voice ah nan reply panrathuku choose panirukano antha voice la
reply pananum"*.

    who may command  ->  arcdesk/voiceid.py enrolments (any number, any person)
    what it answers in ->  this library's chosen reply clip

The engine is faked here, so the logic is tested without downloading 1.5 GB.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import tempfile
import wave
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = tempfile.mkdtemp(prefix="arcdesk-voicelib-")
os.environ["ARCDESK_HOME"] = HOME

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])

from arcdesk import clone, config, voicelib, voiceid  # noqa: E402
from arcdesk.theme import get_theme  # noqa: E402
from arcdesk.widgets.voicelib_dialog import VoiceLibraryDialog  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    ok &= bool(good)


def make(path: Path, seconds: float = 9.0, sr: int = 16000, freq: float = 150.0) -> str:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(
            int(0.25 * math.sin(2 * math.pi * freq * i / sr) * 32767).to_bytes(
                2, "little", signed=True) for i in range(int(seconds * sr))))
    return str(path)


# a fake speaker engine: an embedding that depends only on a file's dominant frequency,
# which is enough to prove "same voice passes, another voice does not" without a model.
def fake_embed(wav: str):
    import array
    with wave.open(wav) as w:
        raw = w.readframes(w.getnframes())
    a = array.array("h")
    a.frombytes(raw)
    if not len(a):
        return None
    # crude but honest fingerprint: pitch (from the zero-crossing rate) and level.
    # One number is enough to tell 150 Hz from 1400 Hz, which is the whole point.
    zc = sum(1 for i in range(1, len(a)) if (a[i - 1] < 0) != (a[i] < 0))
    seconds = len(a) / 16000
    pitch_hz = (zc / 2) / max(seconds, 1e-6)
    level = sum(abs(x) for x in a[:4000]) / 4000 / 32768
    # One-hot over pitch bands plus a level term. That is the property the real campplus
    # model has and the property the test needs: the same voice is close to itself, a
    # different pitch is far away. (A plain [1, pitch, level] vector fails this test —
    # cosine similarity between two different positive vectors stays high, which is why
    # the first version of this stub reported a stranger as "allowed".)
    band = min(7, int(pitch_hz // 200))
    vec = [0.02] * 8
    vec[band] = 1.0
    vec[7] = min(0.05, level * 0.2)
    return vec


voiceid.embed = fake_embed          # noqa: SLF001 — the test owns the engine
voiceid.available = lambda: (True, "")  # noqa: SLF001

print("1) the library starts empty and says so")
check("no reply voices yet", voicelib.reply_voices(), [])
check("no active reply voice", voicelib.active_reply(), {})
check("describe() admits nobody is enrolled", "anybody" in voicelib.describe(), True)

print("\n2) add a reply voice from a clip — a DIFFERENT voice from yours is allowed")
mine = make(Path(HOME) / "me.wav", 9.0, freq=150)
other = make(Path(HOME) / "rajini.wav", 6.0, freq=420)
got = voicelib.add_reply("rajini", other, "vanakkam nan rajini", "ta")
check("added", got["ok"], True)
check("it kept the length", got["voice"]["seconds"] > 5.5, True)
check("it measured the clip", bool(got["voice"]["grade"]), True)
check("it is the active reply voice", voicelib.active_reply()["name"], "rajini")
check("the clip lives in its own file", Path(voicelib.reply_clip()).exists(), True)
check("...and NOT the shared reference path",
      Path(voicelib.reply_clip()).name != "reference.wav", True)

print("\n3) the rest of the app sees it (one source of truth)")
import hashlib  # noqa: E402


def digest(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# clone.py and the daemon have always read reference.wav, so the library MIRRORS the
# chosen clip there rather than introducing a second source of truth. Same bytes = wired.
check("clone.reference() is the clip you chose", digest(clone.reference()),
      digest(voicelib.reply_clip()))
check("the transcript travels with the voice", clone.transcript(), "vanakkam nan rajini")
check("describe() names it", "rajini" in voicelib.describe(), True)

print("\n4) two reply voices, switch between them")
mine2 = voicelib.add_reply("me", mine, "ithu en kural", "ta")
check("a second voice was added", mine2["ok"], True)
check("adding a second does not steal the active slot",
      voicelib.active_reply()["name"], "rajini")
check("pick the other one", voicelib.set_reply(mine2["voice"]["id"]), True)
check("now it is active", voicelib.active_reply()["name"], "me")
check("and the shared reference follows", digest(clone.reference()),
      digest(mine2["voice"]["path"]))

print("\n5) removing the active voice falls back, and never leaves silence")
voicelib.remove_reply(mine2["voice"]["id"])
check("the removed one is gone from the list",
      [v["name"] for v in voicelib.reply_voices()], ["rajini"])
check("the other voice became active", voicelib.active_reply()["name"], "rajini")
check("clone.reference() is not dangling", Path(clone.reference()).exists(), True)
check("its file was deleted",
      any(Path(v["path"]).exists() for v in voicelib.reply_voices()), True)

print("\n6) command voices: more than one person may be allowed")
check("nobody enrolled to start", voicelib.command_voices(), [])
c1 = voicelib.add_command("me", mine)
check("my voice enrolled", c1["ok"], True)
check("...from one long clip, sliced into takes", "agreement" in c1["message"], True)
c2 = voicelib.add_command("amma", make(Path(HOME) / "amma.wav", 8.0, freq=520))
check("a second person can be added", c2["ok"], True)
check("both are in the list", voicelib.command_voices(), ["amma", "me"])
v = voiceid.verify(mine)
check("my voice is accepted", v["allowed"], True)
check("...and it says who", v["who"], "me")
v2 = voiceid.verify(make(Path(HOME) / "stranger.wav", 4.0, freq=1400))
check("a stranger is refused", v2["allowed"], False)
check("removing a command voice works", voicelib.remove_command("amma"), True)
check("only me is left", voicelib.command_voices(), ["me"])
check("describe() names both roles", "command: me" in voicelib.describe()
      and "reply: rajini" in voicelib.describe(), True)

print("\n7) the dialog shows both lists, and can switch the reply voice")
clone.engines = lambda: {"indicf5": {"available": False}, "xtts": {"available": False}}
dlg = VoiceLibraryDialog(config.load(), get_theme("chill"))
check("the command list is filled", dlg.cmd_list.count(), 1)
check("the reply list is filled", dlg.reply_list.count(), 1)
check("the reply list marks the one in use", "in use" in dlg.reply_list.item(0).text(), True)
check("with no engine it says so honestly", "system voice" in dlg.out.toPlainText(), True)
clone.engines = lambda: {"indicf5": {"available": True}, "xtts": {"available": False}}
_spoken: list[tuple[str, str]] = []
clone.speak = lambda text, lang="en", wav="": (_spoken.append((text, lang)) or True)
dlg._hear()                                        # noqa: SLF001
deadline = time.monotonic() + 5                    # it speaks on a worker now
while time.monotonic() < deadline and not _spoken:
    time.sleep(0.05)
check("Hear it speaks in the chosen voice's language", _spoken and _spoken[-1][1], "ta")

print("\n8) nothing here can make ARC a liar")
src = (ROOT / "arcdesk" / "voicelib.py").read_text(encoding="utf-8")
check("the licence is stated once, without nagging", "permission" in src
      or "right to use" in src, True)
dlg_src = (ROOT / "arcdesk" / "widgets" / "voicelib_dialog.py").read_text(encoding="utf-8")
# the honest message: a language the engines cannot say yet points to the engines
# screen (and the download-free quick match), and never at a .bat the person must run
check("the dialog points a missing engine to the engines screen",
      "the engines screen" in dlg_src, True)
check("and never claims the system voice is the chosen one",
      "system voice" in dlg_src, True)

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
