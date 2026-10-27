"""Is it called JARVIS everywhere a person hears it?

    "nan kooda ARC nu sola vendam, JARVIS nu solanum"   — the user, twice.

`arcdesk/identity.py` is the one place the name lives, and this test holds the two ends
together: what it says about itself, what the window offers to click, and what the
persona prompt instructs the model to say. A rename that misses one of those is how a
product ends up introducing itself under two names.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-name-test-")
sys.path.insert(0, str(ROOT))

from arcdesk import config, identity                                  # noqa: E402
from arcdesk.ai import persona                                        # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:44]!r}")
    ok &= bool(good)


cfg = config.load()

print("1. one name, one place")
check("the default name is JARVIS", identity.name(cfg), "JARVIS")
check("the introduction says it", identity.intro(cfg),
      "I am JARVIS, and this is my voice on your machine.")
check("a blank setting falls back instead of saying nothing",
      identity.name({"ai": {"name": "   "}}), "JARVIS")
cfg2 = {"ai": {"name": "FRIDAY"}}
check("and it can be changed", identity.name(cfg2), "FRIDAY")
check("…in the prompt too", "You are FRIDAY" in persona.system_prompt(cfg2))

print("\n2. the prompt tells the model what to say, and what not to")
prompt = persona.system_prompt(cfg)
check('the prompt says "You are JARVIS"', "You are JARVIS" in prompt)
check('…and forbids "I am ARC"', 'never "I am ARC"' in prompt)
check("the product is still Arc Desk", "Arc Desk" in prompt)

print("\n3. the window does not call it ARC anywhere a person reads")
win_src = (ROOT / "arcdesk" / "widgets" / "window.py").read_text(encoding="utf-8")
check("the ask button says ASK JARVIS", '"ASK JARVIS' in win_src)
check("no 'ASK ARC' left", "ASK ARC" in win_src, False)

print("\n4. brand and persona are not the same word")
check("relabel keeps ARC DESK", identity.relabel("ARC DESK is the window"), "ARC DESK is the window")
check("relabel keeps ARC Lite", identity.relabel("ARC Lite answers offline"), "ARC Lite answers offline")
check("relabel still fixes a stale sentence", identity.relabel("ASK ARC"),
      f"ASK {identity.DEFAULT_NAME}")

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
