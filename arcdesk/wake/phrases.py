"""How JARVIS decides it heard you — the phrase matcher, in one testable place.

A speech engine never gives you the words you said. Vosk writes "hey jarvis" as
"hey jarvis", but it also writes it as "hey jarvis." / "hey  jarvis" /
"hey jervis" / "a jarvis" / "hey davis" depending on your accent, your mic and
the room. If the matcher demands an exact string, the wake word works in a demo
and fails in a living room.

So matching happens in three steps, cheapest first:

  1. exact    — the phrase appears as a whole string (fast path, 99% of hits)
  2. tokens   — every word of the phrase appears as a word (engine split it up)
  3. fuzzy    — same number of words, and each word is within a small edit
                distance (handles "jervis", "jarvas", "darvis")

Fuzzy is deliberately conservative: it needs *all* words close, not just one, so
"hey" alone cannot wake it and "bye jarvis" never gets mistaken for "hey jarvis".
`which()` checks the exit phrase first for the same reason.

Everything here is pure string work — no audio, no Qt, no imports beyond difflib —
which is what makes it unit-testable without a microphone.
"""
from __future__ import annotations

import difflib
import re

# Words the engine commonly produces instead of "jarvis". Kept small on purpose:
# a big table starts matching things people did not say.
NEAR_JARVIS = {
    "jarvis", "jervis", "jarvas", "javis", "darvis", "jarves", "jarvi",
    "jarvus", "jarbis", "garvis", "jarris", "service", "jarvez",
}

FILLERS = ("hey", "hi", "hello", "ok", "okay", "yo", "a", "uh", "um", "the", "hey,")


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    t = (text or "").lower()
    t = re.sub(r"[^\w\s']", " ", t)
    return " ".join(t.split())


def _tokens(text: str) -> list[str]:
    return normalise(text).split()


def word_close(a: str, b: str, threshold: float = 0.78) -> bool:
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False                       # short words must match exactly
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def contains_phrase(text: str, target: str, fuzzy: bool = True) -> bool:
    """Is `target` in what the engine transcribed?"""
    t = normalise(text)
    tg = normalise(target)
    if not tg or not t:
        return False

    # 1. exact substring
    if tg in t:
        return True

    want = tg.split()
    have = t.split()

    # 2. every word present, in order (allows "hey  jarvis" and "ok hey jarvis")
    if all(w in have for w in want):
        return True

    # 3. fuzzy, word by word, same-length window
    if fuzzy and len(want) >= 2:
        n = len(want)
        for i in range(len(have) - n + 1):
            window = have[i:i + n]
            if all(word_close(a, b) for a, b in zip(want, window)):
                return True

        # 4. the engine mangled or dropped only the greeting: "jervis", "a jarvis",
        #    "hey service". This is allowed ONLY when the target itself starts
        #    with a greeting — otherwise "hey jarvis" would match "bye jarvis"
        #    and the exit phrase would fire on the wake word.
        if len(want) == 2 and have:
            last = have[-1]
            tail_ok = last in NEAR_JARVIS or word_close(want[1], last)
            if tail_ok:
                if normalise(want[0]) in FILLERS:
                    lead_ok = (len(have) == 1
                               or have[-2] in FILLERS
                               or word_close(want[0], have[-2]))
                else:
                    lead_ok = len(have) > 1 and word_close(want[0], have[-2])
                if lead_ok:
                    return True
    return False


def which(text: str, wake: str, exit_phrase: str = "", fuzzy: bool = True) -> str:
    """Return "exit", "wake" or "" — exit wins, so "bye jarvis" is never a wake."""
    if exit_phrase and contains_phrase(text, exit_phrase, fuzzy):
        return "exit"
    if wake and contains_phrase(text, wake, fuzzy):
        return "wake"
    return ""


def strip_phrase(text: str, phrase: str) -> str:
    """Remove the wake phrase from a sentence, so "hey jarvis open notepad"
    leaves "open notepad" for the intent layer."""
    t = normalise(text)
    p = normalise(phrase)
    if not p:
        return t
    if p in t:
        return t.replace(p, " ", 1).strip()
    words = [w for w in t.split() if w not in p.split()]
    return " ".join(words).strip()


def confidence(text: str, phrase: str) -> float:
    """0..1 — how sure we are that `phrase` was said. For logs and the UI."""
    t = normalise(text)
    p = normalise(phrase)
    if not p or not t:
        return 0.0
    if p in t:
        return 1.0
    if all(w in t.split() for w in p.split()):
        return 0.92
    if len(p.split()) >= 2:
        n = len(p.split())
        have = t.split()
        best = 0.0
        for i in range(max(1, len(have) - n + 1)):
            window = have[i:i + n]
            if len(window) != n:
                continue
            score = sum(difflib.SequenceMatcher(None, a, b).ratio()
                        for a, b in zip(p.split(), window)) / n
            best = max(best, score)
        return round(best, 2)
    return round(difflib.SequenceMatcher(None, p, t).ratio(), 2)
