"""Language mirroring — ARC answers in the language it was spoken to.

The failure this locks down: the user types Tanglish in a friendly mood and gets
back formal English. Detection is deliberately conservative — a bare "ok" or a
word that exists in both languages ("naan" the bread) must not flip the reply
into Tamil.

Run:  python tests/test_lang.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import lang as L  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<48} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    ok = True

    print("1) scripts are told apart by their alphabet")
    ok &= check("tamil script", L.detect("நான் தயார்"), "ta")
    ok &= check("hindi script", L.detect("मैं तैयार हूँ"), "hi")
    ok &= check("english", L.detect("what is my cpu usage"), "en")
    ok &= check("empty", L.detect("   "), "en")

    print("2) romanised speech is recognised, not guessed")
    ok &= check("tanglish", L.detect("system status sollu macha"), "tanglish")
    ok &= check("tanglish short", L.detect("enna panra"), "tanglish")
    ok &= check("hinglish", L.detect("mujhe batao kya hai"), "hinglish")
    ok &= check("plain english stays english", L.detect("open notepad"), "en")
    ok &= check("one ambiguous word is not enough", L.detect("the naan recipe"), "en")

    print("3) the reply language follows the question")
    code, style = L.mirror("enna panra macha")
    ok &= check("mirror returns the code", code, "tanglish")
    ok &= check("mirror returns a style line", style == L.STYLE["tanglish"], True)
    code_en, style_en = L.mirror("open notepad")
    ok &= check("english question, english style", code_en, "en")
    ok &= check("styles differ per language", style != style_en, True)

    print("4) each code has a style line and a name")
    for code in ("ta", "tanglish", "hi", "hinglish", "en"):
        ok &= check(f"style for {code}", bool(L.STYLE.get(code)), True)
        ok &= check(f"name for {code}", bool(L.name_language(code)), True)
    ok &= check("tts lang tamil", L.tts_lang("ta"), "ta")
    ok &= check("tts lang tanglish is english voice",
                L.tts_lang("tanglish"), "en")

    print("5) the style instruction tells the model what to do")
    style = L.STYLE["tanglish"]
    ok &= check("mentions tamil words", "Tamil" in style or "tamil" in style, True)
    ok &= check("forbids formality", "formal" in style.lower(), True)

    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
