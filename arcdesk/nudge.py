"""The "sir, your battery" instinct — off by default, quiet by design.

A companion that speaks without being asked is the difference between software and
a colleague. It is also the fastest way to become nagware, so the rules here are
deliberately strict:

  * **opt-in** — `ai.nudges` is false until the user turns it on;
  * **one line, once** — a nudge that has been said is written down and not repeated
    for hours (or until the condition clears and comes back);
  * **quiet hours** — nothing between 22:30 and 07:00 unless it is the battery;
  * **no nagging about the same thing** — the battery has to actually drop 5 % before
    it speaks again;
  * **say it, do not act** — a nudge never closes a window or changes a setting.

The logic is pure: `evaluate(snapshot, state, now)` takes numbers in and returns a
nudge out, so `tests/test_nudge.py` can test a flat battery at 3 a.m. without one.
"""
from __future__ import annotations

import json
import time

from . import config

# how long before the same nudge may repeat, in seconds
COOLDOWN = {
    "battery": 45 * 60,
    "disk": 24 * 60 * 60,
    "session": 3 * 60 * 60,
    "memory": 60 * 60,
}

QUIET_FROM, QUIET_TO = 22.5, 7.0          # 22:30 → 07:00, local time
URGENT = {"battery"}                       # allowed through quiet hours


def _state_path():
    return config.data_dir() / "nudges.json"


def load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def snapshot() -> dict:
    """The numbers a nudge can be based on. Missing values are simply absent."""
    out: dict = {}
    try:
        import psutil
    except Exception:
        return out
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            out["battery"] = int(battery.percent)
            out["plugged"] = bool(battery.power_plugged)
    except Exception:
        pass
    try:
        usage = psutil.disk_usage("/" if not hasattr(psutil, "WINDOWS") else "C:\\")
        out["disk_free_pct"] = round(100 - usage.percent, 1)
    except Exception:
        pass
    try:
        out["memory_pct"] = int(psutil.virtual_memory().percent)
    except Exception:
        pass
    return out


def _hour(now: float) -> float:
    t = time.localtime(now)
    return t.tm_hour + t.tm_min / 60.0


def in_quiet_hours(now: float) -> bool:
    h = _hour(now)
    if QUIET_FROM > QUIET_TO:             # wraps midnight
        return h >= QUIET_FROM or h < QUIET_TO
    return QUIET_FROM <= h < QUIET_TO


def evaluate(snap: dict, state: dict, now: float | None = None,
             session_minutes: float = 0.0) -> dict | None:
    """Return the single most useful nudge right now, or None.

    Ordering matters: a battery about to die outranks a tidy-up suggestion.
    """
    now = time.time() if now is None else now
    quiet = in_quiet_hours(now)

    def allowed(kind: str) -> bool:
        if quiet and kind not in URGENT:
            return False
        last = float(state.get(kind, {}).get("at", 0) or 0)
        return (now - last) >= COOLDOWN.get(kind, 3600)

    def note(kind: str, message: str, value=None) -> dict:
        return {"kind": kind, "message": message, "value": value}

    battery = snap.get("battery")
    if battery is not None and not snap.get("plugged", False) and battery <= 20:
        last_value = state.get("battery", {}).get("value")
        dropped = last_value is None or battery <= int(last_value) - 5
        if allowed("battery") and (dropped or last_value is None):
            return note("battery", f"Battery is at {battery} percent. Worth plugging in.",
                        battery)

    free = snap.get("disk_free_pct")
    if free is not None and free < 8 and allowed("disk"):
        return note("disk", f"Only {free:.0f} percent of the disk is free. "
                            "Nothing is broken — it is just getting tight.", free)

    if session_minutes >= 90 and allowed("session"):
        hours = session_minutes / 60
        return note("session", f"You have been at this for {hours:.1f} hours. "
                               "Stretch, I will keep watch.", round(hours, 1))

    memory = snap.get("memory_pct")
    if memory is not None and memory >= 92 and allowed("memory"):
        return note("memory", f"Memory is at {memory} percent. If something feels slow, "
                              "that is why.", memory)

    return None


def check(session_minutes: float = 0.0) -> dict | None:
    """The impure wrapper: read the machine, honour the setting, remember what was said."""
    cfg = config.load()
    if not cfg.get("ai", {}).get("nudges", False):
        return None
    nudge = evaluate(snapshot(), load_state(), session_minutes=session_minutes)
    if not nudge:
        return None
    state = load_state()
    state[nudge["kind"]] = {"at": time.time(), "value": nudge.get("value")}
    save_state(state)
    return nudge


def describe() -> str:
    words = {"battery": "battery under 20 %", "disk": "less than 8 % disk free",
             "session": "a session longer than 90 minutes", "memory": "memory over 92 %"}
    return ("I speak up (only if you turn nudges on) about: "
            + ", ".join(words.values()) + ". Never between 22:30 and 07:00, "
            "except the battery.")
