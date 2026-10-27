"""Voice out — the text is cleaned, chunked, and cancellable.

TTS failures are embarrassing rather than fatal, so they are the kind of thing that
ships broken: a path read aloud letter by letter, two replies talking over each
other, or a 900-character utterance you cannot interrupt. Each check below locks
one of those.

No audio device is needed: the synthesiser is replaced by a recorder.

Run:  python tests/test_voice.py
"""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk.ai import voice as V  # noqa: E402


class Recorder(V.Voice):
    """Stands in for the OS engine: records what would have been said."""

    def __init__(self, cfg, delay: float = 0.05):
        super().__init__(cfg)
        self.said: list[str] = []
        self.delay = delay
        self._mu = threading.Lock()

    def _speak_blocking(self, text: str, wav: str = "") -> bool:  # noqa: D102
        with self._mu:
            self.said.append(text)
        time.sleep(self.delay)
        return True


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    ok = True
    cfg = {"ai": {"voice": True}}

    # ---------- 1. the written form is not the spoken form -------------
    print("1) sanitise() makes a log line sayable")
    s = V.sanitise("**Done.** `draw` wrote #9aa7b4 to "
                   "C:\\Users\\me\\Pictures\\arc_elephant_17.png")
    ok &= check("no asterisks or backticks", any(c in s for c in "*`"), False)
    ok &= check("no windows path", "Users" in s or "C:" in s, False)
    ok &= check("colour is spoken, not hexed", "9aa7b4" in s, False)
    ok &= check("markdown heading stripped", V.sanitise("### Title").strip(), "Title")
    ok &= check("url becomes a phrase", V.sanitise("see https://x.com/a for more"),
                "see a link for more")
    ok &= check("symbols spoken", "%" in V.sanitise("90%") or "percent" in V.sanitise("90%"), True)
    ok &= check("no space before punctuation", ", ." in V.sanitise("a , b ."), False)

    # ---------- 2. limits -------------------------------------------------
    print("2) length is bounded, at a sentence boundary")
    long_text = ("This is a sentence. " * 200)
    capped = V.sanitise(long_text)
    ok &= check("capped at ~SPEAK_LIMIT", len(capped) <= V.SPEAK_LIMIT + 1, True)
    ok &= check("ends like speech", capped.endswith((".", "…")), True)

    # ---------- 3. chunking ----------------------------------------------
    print("3) chunks() never splits a word")
    text = V.sanitise("The elephant is drawn and saved. " * 12)
    parts = V.chunks(text)
    ok &= check("more than one chunk", len(parts) > 1, True)
    ok &= check("each chunk within target", max(len(p) for p in parts) <= V.CHUNK + 40, True)
    ok &= check("reassembles losslessly", " ".join(parts), text)
    ok &= check("empty stays empty", V.chunks("   "), [])

    # ---------- 4. language ----------------------------------------------
    print("4) language is chosen from the text")
    ok &= check("tamil detected", V.speech_lang("நான் தயார்"), "ta")
    ok &= check("hindi detected", V.speech_lang("मैं तैयार हूँ"), "hi")
    ok &= check("english is engine default", V.speech_lang("I am ready"), "")

    # ---------- 5. voice off means silent --------------------------------
    print("5) voice disabled in settings means nothing is said")
    muted = Recorder({"ai": {"voice": False}})
    muted.speak("this should not be spoken")
    time.sleep(0.2)
    ok &= check("nothing recorded", muted.said, [])

    # ---------- 6. a new sentence cancels the old one --------------------
    print("6) a second speak() silences the first mid-flight")
    v = Recorder(cfg, delay=0.08)
    v.speak("First sentence. " * 8)        # many chunks
    time.sleep(0.10)                        # let it start
    v.speak("Second sentence.")
    if v._worker:
        v._worker.join(timeout=10)
    time.sleep(0.5)
    firsts = [t for t in v.said if t.startswith("First")]
    ok &= check("first sentence was cut short", len(firsts) < 8, True)
    ok &= check("second sentence was spoken", "Second sentence." in v.said, True)
    ok &= check("worker finished", v._worker.is_alive() if v._worker else False, False)

    # ---------- 7. stop() is silent and immediate ------------------------
    print("7) stop() kills the queue without starting anything new")
    v2 = Recorder(cfg, delay=0.08)
    v2.speak("Counting one. Counting two. Counting three. Counting four. "
             "Counting five. Counting six.")
    time.sleep(0.10)
    v2.stop()
    n_at_stop = len(v2.said)
    time.sleep(0.6)
    ok &= check("no further chunks after stop()", len(v2.said) - n_at_stop <= 1, True)
    ok &= check("not speaking afterwards", v2.speaking, False)

    # ---------- 8. interrupting ------------------------------------------
    print("8) stop phrases are recognised")
    for phrase in ("stop", "Stop!", "shut up", "be quiet", "chup"):
        ok &= check(f"{phrase!r}", V.is_stop_phrase(phrase), True)
    for phrase in ("stop the music", "stop the timer", "don't stop", ""):
        ok &= check(f"{phrase!r} is not an interrupt", V.is_stop_phrase(phrase), False)

    # ---------- 9. real engine, if this machine has one ------------------
    print("9) the local engine (skipped when absent)")
    real = V.Voice(cfg)
    if real.tts_available:
        ok &= check("engine reports a label", real.tts_label() in
                    ("SAPI (Windows)", "say", "espeak"), True)
        ok &= check("voices() returns a list", isinstance(real.voices(), list), True)
    else:
        print("   --   no TTS engine on this machine, skipped")

    print("\n" + ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
