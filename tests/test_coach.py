"""The coach — a mentor that does not pretend, and never plays therapist.

The tests are about the two failure modes that matter in a program people talk to
when they are low:

1. **Inventing**. It must not diagnose, must not estimate a mood it did not record,
   must not dress a guess up as a measurement.
2. **Missing the moment**. A crisis message must get real phone numbers, immediately,
   not a productivity tip.

Run:  python tests/test_coach.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import coach  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<56} {str(got)[:44]!r}")
    ok &= bool(good)


print("1) a crisis message gets real numbers, not advice")
crisis = coach.respond("sometimes i think i want to die and i don't see the point")
for token in ("14416", "1800-599-0019", "112"):
    check(f"names a real helpline ({token})", token in crisis, True)
check("says plainly that it is software", "software" in crisis.lower(), True)
check("does not diagnose", any(word in crisis.lower()
                               for word in ("disorder", "depression diagnosis", "you have")),
      False)
check("flags the journal as not-therapy", coach.limits().startswith("I am a local assistant"),
      True)

print("2) a heavy day is heard before it is solved")
low = coach.respond("i feel low today, everything is too much")
check("picks the listening mode", coach.mood_of("i feel low"), "low")
check("validates instead of fixing", "do not have to" in low or "normal" in low, True)
check("asks at most a question or two", low.count("?"), 1)
check("no toxic positivity", "cheer up" not in low.lower() and "just be positive"
      not in low.lower(), True)
check("offers to just talk", "talk to me" in low.lower(), True)

print("3) the mentor gives a frame, not a prophecy")
mentor = coach.respond("mentor me on getting direct hotel bookings", "mentor")
check("has a finishable action", "today" in mentor.lower(), True)
check("asks for the facts it lacks", "constraint" in mentor.lower(), True)
check("labels its own limits", "framework, not a prophecy" in mentor.lower(), True)

print("4) the analyst keeps fact, inference and guess apart")
thin = coach.respond("analyse our occupancy", "analyst")
check("says when there are no numbers", "none given yet" in thin, True)
rich = coach.respond("analyse 70.8 68.0 65.1 61.4", "analyst")
check("echoes the real numbers back", "70.8" in rich, True)
check("marks the guess as a guess", "guess" in rich.lower(), True)
check("names what would change its mind", "change my mind" in rich.lower(), True)

print("5) decisions get a test, not a verdict")
decision = coach.respond("should i take the second hotel contract or wait for the bigger one",
                         "decide")
check("asks if it is reversible", "reversible" in decision.lower(), True)
check("asks what is being optimised", "optimis" in decision.lower() or "optimiz" in
      decision.lower(), True)
check("names the cost of not deciding", "doing nothing" in decision.lower(), True)
check("states its confidence", "confidence" in decision.lower(), True)
check("promises nothing", "guaranteed" in decision.lower(), False)

print("6) a goal becomes seven days")
plan = coach.respond("i want to open a rooftop cafe", "plan")
check("seven days are listed", sum(f"Day {i}" in plan for i in range(1, 8)), 7)
check("it refuses to invent the market", "will not pretend" in plan.lower(), True)

print("7) the journal is local, and the reflection counts only real entries")
empty = coach.reflection(7)
check("no entries = no invented pattern", "nothing to count" in empty.lower(), True)
coach.journal("today was heavy and i feel low, too many bookings and no sleep")
coach.journal("better today, the new menu worked")
coach.journal("calm and grateful")
entries = coach.reflection(7)
check("counts what exists", "3 entries" in entries, True)
check("names the heavy days", "heavy days" in entries, True)
journal_file = coach._journal_path()
check("journal lives on this machine", journal_file.exists(), True)
check("journal is a plain local file", journal_file.suffix, ".jsonl")
check("entry text is stored, not summarised away",
      "new menu worked" in journal_file.read_text(encoding="utf-8"), True)

print("8) mode detection and language")
check("“should i …” is a decision", coach.respond("should i buy the bus or lease it").count(
    "reversible") > 0, True)
check("“i feel low” is listened to", "normal" in coach.respond("i feel low").lower()
      or "heavy" in coach.respond("i feel low").lower(), True)
tangled = coach.respond("machi i feel tired da", "listen")
check("answers a Tanglish speaker in kind", "Machi" in tangled, True)
check("check-in is short and human", "journal" in coach.respond(action="checkin").lower(),
      True)

print()
print("ALL PASS" if ok else "FAIL")
raise SystemExit(0 if ok else 1)
