"""Numbers ARC must never hallucinate: arithmetic, units, market quotes.

A language model guesses "18% of 4500" and guesses it plausibly wrong. These
checks lock the exact-answer paths, and — just as important — lock the refusals:
no eval, no unit mixing, no prediction dressed up as a prophecy.

Network rows are skipped when offline instead of failing the build.

Run:  python tests/test_knows.py
"""
from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import knows as K  # noqa: E402


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<46} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def online() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3).close()
        return True
    except OSError:
        return False


def main() -> int:
    ok = True

    print("1) arithmetic is computed, not guessed")
    ok &= check("plain expression", K.calc("(1234*0.18)+56"), "278.12")
    ok &= check("percent of", K.calc("18% of 4500"), "810")
    ok &= check("functions and powers", K.calc("sqrt(144)+2**10"), "1,036")
    ok &= check("thousands separator", "," in K.calc("123456"), True)
    ok &= check("comparison answers yes/no", K.calc("2+2 == 4"), "yes")

    print("2) the calculator refuses to become a shell")
    bad = K.calc("__import__('os').system('echo hi')")
    ok &= check("import refused", bad.startswith("ERROR"), True)
    ok &= check("no traceback leaked", "Traceback" in bad, False)

    print("3) unit conversion, with kinds checked")
    ok &= check("km to mile", K.convert(5, "km", "mile"), "5 km is 3.10686 mile")
    ok &= check("fahrenheit to celsius", K.convert(100, "f", "c"), "100.0 °F is 37.8 °C")
    ok &= check("freezing point", K.convert(0, "c", "f"), "0.0 °C is 32.0 °F")
    mixed = K.convert(1, "kg", "km")
    ok &= check("mass vs length refused", mixed.startswith("ERROR"), True)
    ok &= check("unknown unit refused", K.convert(1, "furlong", "km").startswith("ERROR"), True)

    if not online():
        print("4) market rows skipped (offline)")
    else:
        print("4) live market rows answer and stay honest")
        q = K.stock("nifty")
        ok &= check("quote has a number", any(ch.isdigit() for ch in q), True)
        ok &= check("quote is labelled not-advice", "not investment advice" in q, True)
        p = K.project("reliance", 5)
        ok &= check("projection says it is a trend", "trend" in p.lower()
                    or "straight-line" in p.lower(), True)
        ok &= check("projection has a band", "±2σ" in p or "2σ" in p, True)
        ok &= check("no 'will be' promise", "will be" in p.lower(), False)
        ok &= check("unknown ticker admits it", "will not guess" in K.stock("zzzznotreal"), True)
        ms = K.market_summary()
        ok &= check("summary mentions nifty", "NSEI" in ms or "nifty" in ms.lower(), True)

    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
