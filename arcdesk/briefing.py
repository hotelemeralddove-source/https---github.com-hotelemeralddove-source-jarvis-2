"""One command, every morning: what today actually looks like.

    "good morning"        → the whole briefing
    "brief me"            → the same
    "what is today"       → date, time, and what is scheduled

Every line comes from something real: the clock, `psutil`, the calendar files ARC
wrote itself, the reminder list, the focus log, the weather client (only if the user
turned weather on and there is a network), and the market client (only if a network
answered). When a source is not available the section is **left out**, not filled with
a guess — the honest version of a briefing is shorter, not wrong.

The output is plain text with short lines so it reads well on screen *and* survives
being read aloud by TTS without turning into a wall of numbers.
"""
from __future__ import annotations

import os
import time

from . import config, focus, reminders

try:                       # module level so a test can prove the honest branch
    import psutil
except Exception:          # pragma: no cover - a Windows box without psutil
    psutil = None

WEEKDAY = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _clock_line() -> str:
    now = time.localtime()
    hour = now.tm_hour
    part = ("morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17
            else "evening" if 17 <= hour < 22 else "night")
    return f"Good {part} — it is {time.strftime('%H:%M')} on {WEEKDAY[now.tm_wday]}, {time.strftime('%d %B %Y')}."


def _calendar_lines(days: int = 1) -> list[str]:
    try:
        from . import comms
        listed = comms.list_events(days=days)
    except Exception:
        return []
    if not listed:
        return []
    text = str(listed).strip()
    if "no events" in text.lower() or not text:
        return ["Calendar: nothing scheduled."]
    rows = [ln.strip(" ·") for ln in text.splitlines() if ln.strip()]
    rows = [ln for ln in rows if not ln.lower().startswith(("events", "here"))]
    return ["Calendar:"] + [f"  · {ln}" for ln in rows[:6]]


def _reminder_lines() -> list[str]:
    rows = reminders.items()
    if not rows:
        return []
    out = ["Reminders:"]
    for r in rows[:5]:
        out.append(f"  · {time.strftime('%H:%M', time.localtime(r['due']))} — {r['text']}")
    return out


def _machine_lines() -> list[str]:
    """Real machine numbers, or an honest one-liner saying why there are none."""
    if psutil is None:
        return ["Machine: no psutil here, so no numbers from me."]
    try:
        cpu = psutil.cpu_percent(interval=0.12)
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
        return [f"Machine: cpu {cpu:.0f}%, memory {vm.percent:.0f}%, "
                f"disk {100 * du.used / max(1, du.total):.0f}% of "
                f"{du.total / 1e9:.0f} GB used."]
    except Exception:
        return []


def _weather_line(cfg: dict) -> list[str]:
    """Weather only if the user turned it on — and only from the app's own cache."""
    if not (cfg.get("weather") or {}).get("enabled"):
        return []
    try:
        import json
        data = json.loads(config.weather_cache_path().read_text(encoding="utf-8"))
        if time.time() - float(data.get("ts", 0)) < 6 * 3600:
            return [f"Weather (cached {time.strftime('%H:%M', time.localtime(float(data['ts'])))}): "
                    f"{data.get('text', '')}"]
    except Exception:
        pass
    return []


def _focus_line() -> list[str]:
    try:
        line = focus.stats(days=1)
    except Exception:
        return []
    return [line] if "No focus sessions" not in line else []


def build(cfg: dict | None = None) -> str:
    """The briefing, assembled from what is actually available."""
    cfg = cfg or {}
    lines = [_clock_line()]
    for block in (_weather_line(cfg), _calendar_lines(), _reminder_lines(),
                  _focus_line()):
        lines.extend(block)
    lines.extend(_machine_lines())
    lines.append("Say \"remind me in 20 minutes to stretch\", \"start a focus session\", "
                 "or \"show me the hologram\".")
    return "\n".join(lines)


def today() -> str:
    """Just the date and what is on it — the short version."""
    now = time.localtime()
    head = f"{WEEKDAY[now.tm_wday]}, {time.strftime('%d %B %Y')} · {time.strftime('%H:%M')}"
    body = _calendar_lines(days=1) or []
    body += _reminder_lines() or []
    if not body:
        return head + "\nNothing on the calendar and no reminders waiting."
    return "\n".join([head] + body)
