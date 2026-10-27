"""The wake-word matcher — "hey jervis" has to work, "bye jarvis" must never wake.

A speech engine does not give you the words you said. It gives you its best guess,
and that guess changes with accent, microphone and background noise. So the matcher
is a sequence of steps: exact → word-wise → fuzzy → greeting-lost.

The danger of loosening it is that the exit phrase starts firing on the wake word,
or a normal sentence wakes the app. Each check below locks one of those edges.

Run:  python tests/test_phrases.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk.wake import phrases as ph  # noqa: E402

WAKE = "hey jarvis"
EXIT = "bye jarvis"


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<44} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    ok = True

    # ---------- 1. the exact phrase and its spacing variants ----------
    print("1) exact + whitespace/punctuation variants")
    for heard in ("hey jarvis", "hey  jarvis", "Hey Jarvis", "hey jarvis.",
                  "hey, jarvis", "  hey jarvis  "):
        ok &= check(heard, ph.which(heard, WAKE, EXIT), "wake")

    # ---------- 2. how the engine mangles "jarvis" -------------------
    print("2) mishearings of the name")
    for heard in ("hey jervis", "hey jarvas", "hey darvis", "a jarvis", "jarvis",
                  "hey jarvis open notepad"):
        ok &= check(heard, ph.which(heard, WAKE, EXIT), "wake")

    # ---------- 3. the exit phrase wins -----------------------------
    print("3) exit phrase beats the wake phrase")
    for heard in ("bye jarvis", "goodbye jarvis", "bye jarvas", "ok bye jarvis"):
        ok &= check(heard, ph.which(heard, WAKE, EXIT), "exit")

    # ---------- 4. ordinary speech must stay ignored ----------------
    print("4) ordinary speech is ignored (no false wakes)")
    for heard in ("open notepad", "what is the weather", "hey what is the weather",
                  "play music", "how are you", "jar", "hey", "", "   "):
        ok &= check(heard or "(empty)", ph.which(heard, WAKE, EXIT), "")

    # ---------- 5. a custom wake phrase still works ----------------
    print("5) user-edited wake phrase")
    ok &= check("computer draw a cat", ph.which("computer draw a cat", "computer", EXIT), "wake")
    ok &= check("computer", ph.which("computer", "computer", EXIT), "wake")
    ok &= check("hey jarvis", ph.which("hey jarvis", "computer", EXIT), "")

    # ---------- 6. fuzzy can be switched off -----------------------
    print("6) --no-fuzzy keeps only exact / word-wise matches")
    ok &= check("exact still matches", ph.which("hey jarvis", WAKE, EXIT, fuzzy=False), "wake")
    ok &= check("mishear rejected", ph.which("hey jervis", WAKE, EXIT, fuzzy=False), "")
    ok &= check("exit still first", ph.which("bye jarvis", WAKE, EXIT, fuzzy=False), "exit")

    # ---------- 7. the command survives the wake word --------------
    print("7) stripping the wake word leaves the command intact")
    ok &= check("hey jarvis open notepad", ph.strip_phrase("hey jarvis open notepad", WAKE),
                "open notepad")
    ok &= check("hey jarvis draw an elephant",
                ph.strip_phrase("hey jarvis draw an elephant", WAKE), "draw an elephant")
    ok &= check("no phrase to strip", ph.strip_phrase("draw a cat", WAKE), "draw a cat")

    # ---------- 8. confidence is honest ----------------------------
    print("8) confidence falls when the words were mangled")
    exact = ph.confidence("hey jarvis", WAKE)
    mangle = ph.confidence("hey jervis", WAKE)
    ok &= check(f"exact {exact} > misheard {mangle}", exact > mangle, True)
    ok &= check("unrelated text is low", ph.confidence("open notepad", WAKE) < 0.4, True)

    print("\n" + ("ALL PASS" if ok else "FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
