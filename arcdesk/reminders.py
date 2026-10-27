"""Reminders that actually fire — one JSON file, no cloud, no account.

    "remind me in 20 minutes to stretch"
    "remind me at 18:30 to call amma"
    "remind me tomorrow 9am to send the invoice"

The rules, in the same spirit as the rest of the app:

  * **local only** — a list in `reminders.json` inside the app's data folder;
  * **no silent edits** — a reminder is only removed when it is delivered or when the
    user cancels it;
  * **it says when it does not understand** — "remind me about the thing" without a
    time is refused with the reason, not silently scheduled for later;
  * **one reminder, one announcement** — `due()` is a checkpoint, not a stream, so a
    five-second poll cannot repeat the same reminder twice.

The parser is deliberately small: `comms.parse_when` already understands "in 20
minutes", "18:30", "tomorrow 9am" and "friday 4pm", and there is no reason to write a
second, worse one.
"""
from __future__ import annotations

import json
import re
import time

from . import comms, config

KEEP_DONE_DAYS = 7


def _path():
    return config.data_dir() / "reminders.json"


def _load() -> list[dict]:
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict) and "due" in r]
    except Exception:
        pass
    return []


def _save(items: list[dict]) -> None:
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items[-200:], indent=1), encoding="utf-8")
    except Exception:
        pass


def _clean(what: str) -> str:
    """'reminder to drink water' → 'drink water'. The trigger words are not the reminder."""
    w = (what or "").strip(" ,.-")
    w = re.sub(r"^\s*(reminder|reminders|note)\s*[:,]?\s*", "", w, flags=re.I)
    w = re.sub(r"^\s*to\s+", "", w, flags=re.I)
    return w.strip(" ,.-")


def split(text: str) -> tuple[str, str]:
    """Split 'remind me in 20 minutes to stretch' into ('in 20 minutes', 'stretch')."""
    t = (text or "").strip()
    t = re.sub(r"^\s*(hey\s+arc[,\s]*)?(please\s+)?remind\s+me\s*", "", t, flags=re.I)
    if not t:
        return "", ""
    # "in 20 minutes to X" / "at 18:30 to X" / "tomorrow 9am to X"
    m = re.match(r"(?P<when>.+?)\s+to\s+(?P<what>.+)$", t, flags=re.I)
    if m and comms.parse_when(m.group("when")):
        return m.group("when").strip(), _clean(m.group("what"))
    # "to X in 20 minutes" (the other word order)
    m = re.match(r"to\s+(?P<what>.+?)\s+(?P<when>in\s+\d+\s*\w+|at\s+\d{1,2}(:\d{2})?\s*\w*)$",
                 t, flags=re.I)
    if m and comms.parse_when(m.group("when")):
        return m.group("when").strip(), _clean(m.group("what"))
    # "drink water at 14:00" / "send the invoice tomorrow 9am" — time last
    m = re.match(r"(?P<what>.+?)[,\s]+(?P<when>(?:at|by|tomorrow|today|tonight|"
                 r"in|on|next)\b.+)$", t, flags=re.I)
    if m and comms.parse_when(m.group("when")):
        return m.group("when").strip(), _clean(m.group("what"))
    return t, ""


def add(text: str) -> str:
    """Schedule one reminder. Returns a spoken-friendly sentence."""
    when_text, what = split(text)
    if not what:
        what = "reminder"
    due = comms.parse_when(when_text) if when_text else None
    if due is None:
        return ("I need a time for that. Say it like \"remind me in 20 minutes to "
                "stretch\" or \"remind me at 18:30 to call amma\".")
    stamp = due.timestamp()
    if stamp <= time.time() - 30:
        return f"That time ({due.strftime('%H:%M')}) has already passed."
    items = _load()
    item = {"id": int(stamp), "due": stamp, "text": what[:160],
            "created": time.time(), "done": 0, "said": 0}
    # the same reminder twice in one second is one reminder
    items = [r for r in items if not (r.get("due") == item["due"]
                                      and r.get("text") == item["text"])]
    items.append(item)
    _save(items)
    when = due.strftime("%H:%M")
    today = time.strftime("%Y-%m-%d") == due.strftime("%Y-%m-%d")
    label = when if today else due.strftime("%a %d %b at %H:%M")
    return f"Reminder set for {label}: {what}."


def items(include_done: bool = False) -> list[dict]:
    now = time.time()
    out = []
    for r in _load():
        if not include_done and (r.get("done") or r.get("due", 0) < now - 86400):
            continue
        out.append(r)
    return sorted(out, key=lambda r: r.get("due", 0))


def list_text() -> str:
    rows = items()
    if not rows:
        return "No reminders waiting."
    lines = ["Reminders:"]
    for r in rows:
        when = time.strftime("%a %d %b %H:%M", time.localtime(r["due"]))
        lines.append(f"  · {when} — {r['text']}")
    return "\n".join(lines)


def cancel(which: str = "") -> str:
    """Cancel by number from `list`, by id, or by a word from the text."""
    items_all = _load()
    live = [r for r in items_all if not r.get("done")]
    if not live:
        return "There is nothing to cancel."
    target = None
    key = (which or "").strip()
    if key.isdigit():
        n = int(key)
        if 1 <= n <= len(live):
            target = sorted(live, key=lambda r: r["due"])[n - 1]
        else:
            target = next((r for r in live if int(r["id"]) == n), None)
    elif key:
        low = key.lower()
        target = next((r for r in sorted(live, key=lambda r: r["due"])
                       if low in str(r["text"]).lower()), None)
    if target is None:
        return "I could not tell which reminder. Say the number from the list, or a word from it."
    items_all = [r for r in items_all if r is not target]
    _save(items_all)
    return f"Cancelled: {target['text']}."


def due(now: float | None = None) -> list[dict]:
    """Reminders whose time has come and that have not been announced yet."""
    now = time.time() if now is None else now
    items_all = _load()
    found, changed = [], False
    for r in items_all:
        if r.get("done") or r.get("said"):
            continue
        if r.get("due", 0) <= now:
            r["said"] = 1
            r["done"] = 1
            found.append(r)
            changed = True
    if changed:
        _save(items_all)        # rewrite with the said/done flags
    return found


def clear_done() -> int:
    cutoff = time.time() - KEEP_DONE_DAYS * 86400
    items_all = _load()
    keep = [r for r in items_all if not (r.get("done") and r.get("due", 0) < cutoff)]
    removed = len(items_all) - len(keep)
    _save(keep)
    return removed
