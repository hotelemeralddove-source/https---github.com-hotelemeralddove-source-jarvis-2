"""ARC Lite must understand the phrases people actually say — no model needed.

Lite is the always-available brain: no key, no download, no network. That makes
its intent matching the floor of the whole product. This test is the floor's
floor: 32 real phrasings, measured. It exists because the first run of this
measurement scored 86% and two of the misses were *crashes*, not wrong guesses:

  * "find report.docx" raised TypeError — `_call(name, **args)` collided with
    the tool's own `name` parameter, which made the whole branch unreachable
  * "go to youtube", "close spotify", "what is using my ram" had no pattern

Run:  python tests/test_lite_intents.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk.ai import tools  # noqa: E402
from arcdesk.ai.lite import respond  # noqa: E402

CASES: list[tuple[str, str]] = [
    # launching
    ("open notepad", "open_app"),
    ("open chrome", "open_app"),
    ("launch calculator", "open_app"),
    ("open google", "open_url"),
    ("go to youtube", "open_url"),
    ("visit github", "open_url"),
    ("search for best laptops", "web_search"),
    # system
    ("how is my cpu doing", "system_report"),
    ("system report", "system_report"),
    ("what's using my ram", "running_apps"),
    ("what is eating my memory", "running_apps"),
    ("close spotify", "close_app"),
    ("kill chrome", "close_app"),
    # controls
    ("set volume to 40", "set_volume"),
    ("mute", "mute"),
    ("play next song", "media"),
    ("brightness 70", "brightness"),
    ("take a screenshot", "screenshot"),
    ("lock my screen", "lock_screen"),
    ("shut down the pc", "power"),
    # time / timers
    ("timer 10 minutes", "timer"),
    ("set a timer for 5 min", "timer"),
    ("what time is it", "time"),
    # the arc itself
    ("enter magic mode", "magic"),
    ("bye jarvis", "magic"),
    ("show charms", "charms"),
    ("focus mode", "arc_mode"),
    # memory / files
    ("note that I need milk", "note"),
    ("read my notes", "read_notes"),
    ("find report.docx", "find_file"),
    ("where is budget.xlsx", "find_file"),
    ("what's the weather", "weather"),
]


# --------------------------------------------------------------------------------------
# Static guard: EVERY tool name lite.py can emit must exist in the registry.
# This is how `find_files` (a name that does not exist — the registry has `find_file`)
# survived several waves: that branch raised "unknown tool", so no phrase test ever
# proved it worked. Reading the source catches the whole category at once, including
# branches nobody has written a phrase for.
import re  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_LITE_SRC = _Path(__file__).resolve().parents[1] / "arcdesk" / "ai" / "lite.py"
_emitted = set(re.findall(r'_call\(\s*"([a-z_0-9]+)"', _LITE_SRC.read_text(encoding="utf-8")))
_bogus = sorted(n for n in _emitted if n not in tools.TOOLS)


def main() -> int:
    ok = True
    hits = 0
    misses: list[str] = []
    bad_tools: list[str] = []

    for text, want in CASES:
        try:
            _reply, calls = respond(text)
        except Exception as exc:                      # a crash is worse than a miss
            misses.append(f"{text!r} raised {type(exc).__name__}")
            continue
        got = calls[0]["function"]["name"] if calls else None
        if got == want:
            hits += 1
        else:
            misses.append(f"{text!r} → {got} (wanted {want})")
        if got and got not in tools.TOOLS:
            bad_tools.append(f"{text!r} → {got} is not a real tool")

    acc = hits / len(CASES)
    print(f"1) intent accuracy      : {hits}/{len(CASES)} = {acc * 100:.0f}%  "
          f"{'OK' if acc >= 0.95 else 'FAIL'}")
    for m in misses:
        print("   ", m)
    ok &= acc >= 0.95 and not bad_tools

    print(f"0) static: every tool lite can call exists : {len(_emitted)} names, "
          f"{len(_bogus)} unknown  {'OK' if not _bogus else 'FAIL'}")
    for b in _bogus:
        print("   ", b)
    ok &= not _bogus and bool(_emitted)

    print(f"2) every target exists  : {len(bad_tools)} bogus tool names  "
          f"{'OK' if not bad_tools else 'FAIL'}")
    for b in bad_tools:
        print("   ", b)
    ok &= not bad_tools

    # 3. an unknown phrase must produce words, not a crash and not silence
    reply, calls = respond("write me a poem about the ocean")
    honest = bool(reply) and not calls and ("Lite" in reply or "brain" in reply)
    print(f"3) honest fallback      : {len(reply)} chars, {len(calls)} calls  "
          f"{'OK' if honest else 'FAIL'}")
    ok &= honest

    print("\nPASS" if ok else "\nFAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
