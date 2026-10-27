"""Focus sessions — a timer that knows the difference between 25 minutes and 25 minutes of work.

    "start a focus session"            → 25 minutes
    "focus for 50 minutes"             → longer block
    "how long is left"                 → remaining time, honestly
    "stop focus"                       → ends the block and logs it

No gamification, no badges, no cloud. What it does have is a log of *completed*
blocks with the wall-clock times, so "how did this week go" is answered from data
rather than a feeling. A block ends when the clock says so, not when the window is
in front — the point of a timer is to be an outside referee.
"""
from __future__ import annotations

import json
import time

from . import config

DEFAULT_MINUTES = 25
MAX_MINUTES = 180


def _path():
    return config.data_dir() / "focus.json"


def _load() -> dict:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("sessions", [])
            raw.setdefault("active", None)
            return raw
    except Exception:
        pass
    return {"sessions": [], "active": None}


def _save(state: dict) -> None:
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        state["sessions"] = state.get("sessions", [])[-500:]
        path.write_text(json.dumps(state, indent=1), encoding="utf-8")
    except Exception:
        pass


def start(minutes: int = DEFAULT_MINUTES, label: str = "") -> str:
    """Begin a block. Refuses to clobber one that is already running."""
    state = _load()
    if state.get("active"):
        left = remaining(state["active"])
        return f"A session is already running — {left} left. Say stop focus first."
    try:
        mins = max(1, min(MAX_MINUTES, int(minutes)))
    except Exception:
        mins = DEFAULT_MINUTES
    started = time.time()
    state["active"] = {"start": started, "minutes": mins, "label": (label or "")[:80]}
    _save(state)
    unit = "minute" if mins == 1 else "minutes"
    return (f"Focus started: {mins} {unit}{', ' + label if label else ''}. "
            f"I will stay quiet until {time.strftime('%H:%M', time.localtime(started + mins * 60))}.")


def remaining(active: dict | None = None, now: float | None = None) -> str:
    state = _load()
    active = active or state.get("active")
    if not active:
        return "no session running"
    now = time.time() if now is None else now
    left = active["start"] + active["minutes"] * 60 - now
    if left <= 0:
        return "time is up"
    m, s = divmod(int(left), 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


def status() -> str:
    state = _load()
    active = state.get("active")
    if not active:
        return ("No focus session running. Say \"start a focus session\" for "
                f"{DEFAULT_MINUTES} minutes, or \"focus for 50 minutes\".")
    elapsed = int((time.time() - active["start"]) / 60)
    unit = "minute" if active["minutes"] == 1 else "minutes"
    return (f"Focus session: {active['minutes']} {unit}, {elapsed} in, "
            f"{remaining(active)} left" + (f" — {active['label']}" if active.get("label") else "") + ".")


def finish(completed: bool = True) -> str:
    """Close the running block and log it."""
    state = _load()
    active = state.get("active")
    if not active:
        return "There is no focus session to stop."
    spent = max(1, int((time.time() - active["start"]) / 60))
    state["sessions"].append({
        "start": active["start"],
        "minutes": spent,
        "planned": active["minutes"],
        "label": active.get("label", ""),
        "completed": 1 if completed else 0,
    })
    state["active"] = None
    _save(state)
    if completed:
        return (f"Focus block done: {spent} of {active['minutes']} "
                f"{'minute' if active['minutes'] == 1 else 'minutes'}.")
    return f"Stopped after {spent} {'minute' if spent == 1 else 'minutes'}."


def check() -> str | None:
    """Called by the app's clock. Returns a message when a block has run out."""
    state = _load()
    active = state.get("active")
    if not active:
        return None
    if time.time() >= active["start"] + active["minutes"] * 60:
        label = active.get("label") or ""
        finish(completed=True)
        return (f"Your {active['minutes']}-minute focus block is done"
                + (f" — {label}" if label else "") + ". Take a break.")
    return None


def stats(days: int = 7) -> str:
    state = _load()
    cutoff = time.time() - days * 86400
    recent = [s for s in state.get("sessions", []) if s.get("start", 0) >= cutoff]
    if not recent:
        return f"No focus sessions logged in the last {days} days."
    total = sum(int(s.get("minutes", 0)) for s in recent)
    done = sum(1 for s in recent if s.get("completed"))
    today = time.strftime("%Y-%m-%d")
    today_min = sum(int(s.get("minutes", 0)) for s in recent
                    if time.strftime("%Y-%m-%d", time.localtime(s.get("start", 0))) == today)
    return (f"Focus, last {days} days: {total} minutes across {len(recent)} blocks "
            f"({done} finished) · today {today_min} minutes.")
