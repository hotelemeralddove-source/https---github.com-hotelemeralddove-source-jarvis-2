"""Focus blocks — start, count down, finish, and the weekly total must be real.

What this guards: a "pomodoro" that reports plausible numbers without measuring
anything. Every value here is compared against the wall clock the module used.

Run:  python tests/test_focus.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import focus  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {got!r}")
    ok &= bool(good)


print("1) nothing running is not an error")
check("status when idle", "no focus" in focus.status().lower(), True)
check("check when idle is silent", focus.check(), None)

print("2) start clamps to sane lengths")
check("default is 25", focus.DEFAULT_MINUTES, 25)
for arg, want in ((0, "1 minute"), (-5, "1 minute"),
                  (10_000, f"{focus.MAX_MINUTES} minutes")):
    focus.finish(completed=False)          # one at a time, on purpose
    check(f"start({arg})", want in focus.start(arg), True)
focus.finish(completed=False)

print("3) a real block counts down from the real clock")
msg = focus.start(2, "invoice report")
check("start names the label", "invoice report" in msg, True)
check("status reports the plan", "2 minutes" in focus.status(), True)
check("status shows time left", "left" in focus.status(), True)
check("nothing is due yet", focus.check(), None)

print("4) finish logs elapsed time, not planned time")
out = focus.finish(completed=True)
check("finish says done", "done" in out.lower(), True)
check("it did not claim 2 minutes", "2 of 2" not in out, True)
check("no session left", "no focus" in focus.status().lower(), True)

print("5) an elapsed block is announced exactly once")
focus.start(1, "probe")
state = focus._load()
state["sessions"].append({"start": time.time() - 120, "minutes": 1,
                          "planned": 1, "label": "probe", "completed": 1})
state["active"] = {"start": time.time() - 120, "minutes": 1, "label": "probe"}
focus._save(state)
announced = focus.check() or ""
check("announced", "done" in announced.lower(), True)
check("not repeated", focus.check(), None)

print("6) the weekly total is the sum of the log")
stats = focus.stats(7)
check("stats mentions the week", "last 7 days" in stats, True)
check("stats mentions today", "today" in stats.lower(), True)
total = sum(int(s.get("minutes", 0)) for s in focus._load()["sessions"])
check("the number is in the sentence", str(total) in stats, True)

print("7) the log is capped so it cannot grow forever")
state = focus._load()
state["sessions"] = [{"start": time.time(), "minutes": 1, "planned": 1,
                      "label": "x", "done": 1} for _ in range(900)]
focus._save(state)
check("500 kept", len(focus._load()["sessions"]) <= 500, True)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
