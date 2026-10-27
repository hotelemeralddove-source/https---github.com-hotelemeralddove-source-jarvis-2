"""Reminders — parsing, storage, one announcement each, honest refusals.

The bug class this guards: a reminder that speaks twice, one that is silently
dropped because its time had already passed, and a parser that swallows the
trigger words ("reminder to drink water" must not remind you to *say* it).

Run:  python tests/test_reminders.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import reminders  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {got!r}")
    ok &= bool(good)


print("1) 'what' and 'when' are split correctly")
for text, what in (("remind me in 2 minutes to stretch", "stretch"),
                   ("remind me at 18:30 to call amma", "call amma"),
                   ("reminder to drink water at 14:00", "drink water"),
                   ("send the invoice tomorrow 9am", "send the invoice")):
    when, body = reminders.split(text)
    check(text, (bool(when), body), (True, what))

print("2) a missing time is refused with a reason, not guessed")
msg = reminders.add("remind me to stretch")
check("refused", "need a time" in msg.lower(), True)
check("nothing was stored", reminders.items(), [])

print("3) a real reminder round-trips")
msg = reminders.add("remind me in 45 minutes to stretch")
check("add confirms the time", "Reminder set for" in msg, True)
stored = reminders.items()
check("one stored", len(stored), 1)
check("text kept, trigger words gone", stored[0]["text"], "stretch")
check("due in the future", stored[0]["due"] > time.time(), True)
check("listing shows it", "stretch" in reminders.list_text(), True)

print("4) cancel by word, by number, and honestly when there is nothing")
reminders.add("remind me in 50 minutes to call amma")
check("two now", len(reminders.items()), 2)
check("cancel by word", "amma" in reminders.cancel("amma"), True)
check("one left", len(reminders.items()), 1)
check("cancel by number", "stretch" in reminders.cancel("1"), True)
check("empty list", reminders.items(), [])
check("cancel with nothing", "nothing to cancel" in reminders.cancel("1").lower(), True)

print("5) due() announces exactly once, then never again")
state = reminders._load()
state.append({"id": 424242, "due": time.time() - 5, "text": "probe past item",
              "created": time.time(), "done": 0, "said": 0})
reminders._save(state)
first = reminders.due()
second = reminders.due()
check("announced once", len(first), 1)
check("not repeated", len(second), 0)
check("the words are the reminder", "probe past item" in first[0]["text"], True)
check("the flag is written to disk",
      any(r.get("said") for r in reminders._load() if r["text"] == "probe past item"), True)

print("6) the store is a real file")
path = Path(reminders._path())
check("file exists", path.exists(), True)
check("clear_done returns a count", isinstance(reminders.clear_done(), int), True)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
