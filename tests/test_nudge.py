"""Proactive nudges — the ones that must stay quiet.

An assistant that speaks first is either a colleague or a nuisance, and the
difference is entirely in the rules. Each check below locks one of them:

  1. off by default — no setting, no speech;
  2. a flat battery is urgent and gets through quiet hours;
  3. everything else is silent at 2 a.m.;
  4. the same nudge does not repeat inside its cooldown;
  5. a battery that has barely moved does not re-trigger;
  6. the most urgent thing wins when two conditions are true at once;
  7. a nudge never instructs an action on its own (it is words, not a tool call).

Run:  python tests/test_nudge.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-nudge-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import config, nudge  # noqa: E402

# Quiet hours are local time, so the fake "now"s must be built from the machine's own
# clock. The old version computed them from UTC epoch arithmetic: on a UTC machine they
# read 12:00/02:00, but in Asia/Calcutta the same instants are 17:30/07:30, and 07:30
# is not quiet — the "waits at 2 a.m." checks then failed on a perfectly good build.
import datetime as _dt                                            # noqa: E402

_day = _dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
NOON = _day.timestamp() + 12 * 3600
NIGHT = _day.timestamp() + 26 * 3600      # 02:00 the next morning


def check(label: str, got, want) -> bool:
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<48} {got!r}"
          + ("" if good else f"  (want {want!r})"))
    return good


def main() -> int:
    ok = True

    print("1) nothing is said unless the user asked for it")
    cfg = config.load()
    cfg.setdefault("ai", {})["nudges"] = False
    config.save(cfg)
    nudge.save_state({})
    ok &= check("check() is silent by default", nudge.check(), None)

    print("2) a dying battery is urgent, even at 2 a.m.")
    flat = {"battery": 12, "plugged": False}
    out = nudge.evaluate(flat, {}, now=NIGHT)
    ok &= check("speaks at night", bool(out), True)
    ok &= check("says the number", "12 percent" in (out or {}).get("message", ""), True)

    print("3) everything else respects quiet hours")
    disk = {"disk_free_pct": 3.0}
    ok &= check("disk at 2 a.m. waits", nudge.evaluate(disk, {}, now=NIGHT), None)
    ok &= check("same disk at noon speaks", bool(nudge.evaluate(disk, {}, now=NOON)), True)
    ok &= check("long session at 2 a.m. waits",
                nudge.evaluate({}, {}, now=NIGHT, session_minutes=180), None)

    print("4) a nudge does not repeat inside its cooldown")
    state = {"battery": {"at": NOON - 600, "value": 12}}      # said 10 minutes ago
    ok &= check("battery repeats only after 45 min",
                nudge.evaluate(flat, state, now=NOON), None)

    print("5) a barely-moved battery does not re-trigger")
    state = {"battery": {"at": NOON - 3600, "value": 18}}     # an hour ago, at 18 %
    ok &= check("11 % after 18 % is still quiet",
                nudge.evaluate({"battery": 17, "plugged": False}, state, now=NOON), None)
    ok &= check("13 % after 18 % speaks",
                bool(nudge.evaluate({"battery": 13, "plugged": False}, state, now=NOON)), True)

    print("6) urgency order: battery beats disk")
    both = {"battery": 9, "plugged": False, "disk_free_pct": 2.0}
    out = nudge.evaluate(both, {}, now=NOON)
    ok &= check("battery wins", (out or {}).get("kind"), "battery")

    print("7) a nudge is words, never an action")
    out = nudge.evaluate({"battery": 8, "plugged": False}, {}, now=NOON)
    ok &= check("no tool name in the message", "tool" in (out or {}).get("message", "").lower(), False)
    ok &= check("has a kind", sorted((out or {}).get("kind", "")) != [], True)
    ok &= check("office hours are quiet-free", nudge.in_quiet_hours(NOON), False)
    ok &= check("night is quiet", nudge.in_quiet_hours(NIGHT), True)

    print()
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
