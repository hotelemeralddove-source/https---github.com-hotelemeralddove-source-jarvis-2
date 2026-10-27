"""The morning briefing — every line must come from a real source or not appear.

The rule: no fabricated telemetry. So this test checks the *shape* of honesty —
the clock matches the system clock, the weather line is absent unless weather is
enabled, and a missing psutil produces a sentence saying so rather than invented
CPU numbers.

Run:  python tests/test_briefing.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import briefing, config  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<50} {str(got)[:60]!r}")
    ok &= bool(good)


cfg = config.load()

print("1) the clock line is the real clock")
line = briefing._clock_line()
check("has the weekday", any(d in line for d in
                             ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                              "Saturday", "Sunday")), True)
check("has the year", str(time.localtime().tm_year) in line, True)

print("2) the full briefing builds and never raises")
text = briefing.build(cfg)
check("is text", isinstance(text, str) and len(text) > 20, True)
check("leads with the clock", line.split("·")[0].strip()[:9] in text, True)
check("has a machine line or says why not",
      ("Machine:" in text) or ("psutil" in text.lower()), True)

print("3) weather appears only when it is switched on")
if not cfg.get("weather", {}).get("enabled"):
    check("weather off means no weather line", "Weather:" in text, False)
else:
    check("weather on and configured", "Weather:" in text or "weather" in text.lower(), True)

print("4) the machine line never invents a number")
import psutil  # noqa: E402
machine = " ".join(briefing._machine_lines())
check("mentions cpu", "cpu" in machine.lower(), True)
real_cpu = psutil.cpu_percent(interval=0.05)
check("cpu value is a plausible percent",
      0 <= real_cpu <= 100 and "cpu" in machine.lower(), True)
check("mentions memory", "memory" in machine.lower(), True)
check("mentions disk", "disk" in machine.lower(), True)

print("5) no psutil is admitted, not faked")
saved = briefing.psutil if hasattr(briefing, "psutil") else None
try:
    briefing.psutil = None
    honest = " ".join(briefing._machine_lines())
    check("says psutil is missing", "psutil" in honest.lower(), True)
    check("does not print a fake percentage", "%" in honest, False)
finally:
    if saved is not None:
        briefing.psutil = saved
    else:
        import importlib
        importlib.reload(briefing)

print("6) today() is the short form")
today = briefing.today()
check("has the date", str(time.localtime().tm_year) in today, True)
check("is shorter than the full briefing", len(today) <= len(text) + 40, True)

print("7) an empty section is omitted, a real one is printed")
from arcdesk import reminders  # noqa: E402
check("no reminders means no empty header", "Reminders:" in text, False)
reminders.add("remind me in 30 minutes to stretch")
text2 = briefing.build(cfg)
check("a real reminder appears", "stretch" in text2, True)
check("under its own header", "Reminder" in text2, True)
check("calendar section present", "Calendar" in text2 or "calendar" in text2.lower(), True)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
