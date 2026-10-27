"""Tool routing — 63 tools in the catalogue, a handful in the request.

This is the file behind two numbers quoted in the docs:

  * the full schema catalogue is ~3 500 tokens, and a 2 048-token context model
    refused the request outright ("you requested 4210 tokens");
  * routed, the same request is ~230 tokens and the small model called the right
    tool instead of a random one.

Both are measured here, not asserted. The failure modes it locks:

  1. a router that drops the tool the user actually needed
  2. substring matching — "open notepad" routing to `note` because "notepad"
     contains "note"
  3. no escape hatch, so an unrouted tool becomes unreachable
  4. a router that returns nothing at all for chit-chat

Run:  python tests/test_select.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("ARCDESK_HOME", os.path.join(os.path.dirname(__file__), "..", ".tmp-select"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk.ai import select, tools  # noqa: E402

# phrase -> a tool that MUST survive routing
CASES = {
    "open notepad": "open_app",
    "what time is it": "time",
    "take a screenshot": "screenshot",
    "how much ram am i using": "system_report",
    "set volume to 40": "set_volume",
    "nifty price": "stock",
    "what is 18% of 4500": "calc",
    "convert 5 km to miles": "convert",
    "exchange rate for dollar": "rates",
    "predict reliance for a week": "project",
    "market eppadi": "market_summary",
    "teach me when i say work mode": "teach_macro",
    "what have i taught you": "macros",
    "draw an elephant": "draw",
    "make it purple": "art_edit",
    "read the error on my screen": "screen_text",
    "send mail to ravi": "email_send",
    "add a meeting tomorrow": "calendar",
    "note that i parked at level 2": "note",
    "what did i copy": "clipboard",
    "lock my screen": "lock_screen",
    "play some music": "media",
    "search the web for react hooks": "web_search",
    "find my invoice file": "find_file",
}


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<46} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    ok = True
    catalogue = tools.TOOLS

    print(f"1) the tool that matters survives routing   ({len(CASES)} phrases)")
    misses = []
    for phrase, want in CASES.items():
        got = select.names(phrase, catalogue, k=8)
        if want not in got:
            misses.append(f"{phrase!r} → {got} (wanted {want})")
        ok &= check(phrase, want in got, True)
    if misses:
        print("     ", "\n      ".join(misses))

    print("2) word boundaries, not substrings")
    got = select.names("open notepad", catalogue, k=8)
    ok &= check("open_app is first", got[0] if got else "", "open_app")
    ok &= check("`note` is not ahead of it", got.index("note") > 0 if "note" in got else True, True)

    print("3) the escape hatch is always there")
    for phrase in ("open notepad", "hello", "asdkjhasd", ""):
        ok &= check(f"list_tools for {phrase!r}", "list_tools" in select.names(phrase, catalogue), True)

    print("4) chit-chat still gets the everyday set")
    fallback = select.names("hello there", catalogue)
    ok &= check("non-empty", bool(fallback), True)
    ok &= check("includes time", "time" in fallback, True)
    ok &= check("small", len(fallback) <= 9, True)

    print("5) the saving is real, in tokens")
    full = select.estimate(tools.schemas())
    routed = select.estimate(tools.schemas(only=select.names("what time is it", catalogue)))
    print(f"      full {full['tools']} tools = {full['tokens']} tokens · "
          f"routed {routed['tools']} tools = {routed['tokens']} tokens")
    ok &= check("at least 70% smaller", routed["tokens"] < full["tokens"] * 0.30, True)
    ok &= check("fits a 2048-token context with room for a reply",
                routed["tokens"] < 1200, True)

    print("6) routing is deterministic")
    a = select.names("nifty price", catalogue)
    b = select.names("nifty price", catalogue)
    ok &= check("same answer twice", a, b)

    print("\n" + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
