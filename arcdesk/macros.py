"""Teaching JARVIS new commands by talking to it.

This is the feature nobody ships: the assistant's vocabulary is not fixed at build
time. You say *"when I say work mode, open vs code and open slack and set volume 40"*
once, and from then on **"work mode"** does all of it — offline, in about 200 ms,
without a model.

How it works:

    teach("when i say work mode, open vs code and set volume 40")
      → split the action list on "and" / "," / "then"
      → run each fragment through the SAME offline intent matcher Lite uses
      → keep the ones that resolved to a real tool call
      → store {trigger: {steps: [...]}} in macros.json

    "work mode" (later, any time)
      → exact or fuzzy trigger match
      → execute the steps in order, with a short gap so windows can appear
      → journal every step

Two rules, both deliberate:

1. **A macro cannot contain a dangerous tool.** Only non-destructive actions are
   allowed (`MACRO_SAFE`). The confirmation gate lives in the agent loop; a recorded
   macro would bypass it, so anything that could delete, close or power off is
   refused at *teach* time with an explanation — not silently dropped at run time.
2. **A macro says what it will do before it runs.** `describe()` returns the step
   list so the user can see "open_app(code), set_volume(40)" and delete it if wrong.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path

from . import config

# Anything here is repeatable and non-destructive. Deliberately absent: power,
# close_app, file_delete, run_command, email_send, whatsapp_send.
MACRO_SAFE = {
    "open_app", "open_url", "web_search", "set_volume", "mute", "media", "brightness",
    "arc_mode", "magic", "charms", "note", "draw", "art_edit", "type_text", "press",
    "windows", "screenshot", "clipboard", "calendar", "screen_text", "click_text",
    "timer", "find_file",
}

SPLIT = re.compile(r"\s*(?:,|;|\band then\b|\bthen\b|\band\b)\s*", re.I)
TEACH = re.compile(
    r"^(?:teach(?:me)?(?: that)?[: ]|when(?:ever)? i say |when i say |if i say |"
    r"remember(?: that)?[: ]|new macro[: ])\s*", re.I)
SEPARATOR = re.compile(r"\s*(?:,|:|=|->|means?|should)\s+", re.I)


def macros_path() -> Path:
    return Path(config.data_dir()) / "macros.json"


def load() -> dict:
    try:
        path = macros_path()
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save(data: dict) -> None:
    try:
        path = macros_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _steps_for(fragment: str) -> list[dict]:
    """One phrase → the tool calls Lite would make for it."""
    from .ai import lite
    _, calls = lite.respond(fragment)
    steps = []
    for call in calls or []:
        fn = call.get("function", {})
        name = fn.get("name", "")
        if name not in MACRO_SAFE:
            continue
        steps.append({"tool": name, "args": json.loads(fn.get("arguments") or "{}"),
                      "said": fragment.strip()})
    return steps


def teach(instruction: str) -> str:
    """Parse and store a new voice macro. Returns a sentence for the user."""
    text = (instruction or "").strip()
    if not text:
        return "ERROR: tell me the trigger and the actions, e.g. 'when I say work mode, open code and set volume 40'"
    body = TEACH.sub("", text).strip()
    parts = SEPARATOR.split(body, maxsplit=1)
    if len(parts) < 2:
        return ("ERROR: I need a trigger and the steps — say it like "
                "'when I say <trigger>, <action> and <action>'")
    trigger, actions = parts[0].strip().lower(), parts[1].strip()
    if not trigger or not actions:
        return "ERROR: the trigger or the actions came out empty"

    fragments = [f for f in SPLIT.split(actions) if f.strip()]
    steps: list[dict] = []
    skipped: list[str] = []
    for fragment in fragments:
        got = _steps_for(fragment)
        if got:
            steps.extend(got)
        elif fragment.strip():
            skipped.append(fragment.strip())
    if not steps:
        return (f"ERROR: none of those are things I can repeat safely. "
                f"I will not record '{actions}' — destructive actions are never macros.")

    data = load()
    data[trigger] = {"steps": steps, "created": int(time.time()),
                     "used": data.get(trigger, {}).get("used", 0)}
    save(data)
    names = ", ".join(f"{s['tool']}" for s in steps)
    msg = f"Learned '{trigger}': {len(steps)} step(s) — {names}."
    if skipped:
        msg += f" I ignored {', '.join(skipped)} (not a repeatable action)."
    return msg


def find(phrase: str) -> tuple[str, dict] | None:
    """Exact hit, then a tolerant one so 'workmode' and 'work mode' are the same."""
    data = load()
    key = " ".join((phrase or "").lower().split())
    if not key:
        return None
    if key in data:
        return key, data[key]
    for trigger in data:
        if " ".join(trigger.split()) == key:
            return trigger, data[trigger]
    close = difflib.get_close_matches(key, list(data), n=1, cutoff=0.82)
    if close:
        return close[0], data[close[0]]
    return None


def run(phrase: str, gap: float = 0.6) -> str:
    """Execute a stored macro by its trigger phrase."""
    found = find(phrase)
    if not found:
        return f"ERROR: no macro called '{phrase}'"
    trigger, entry = found
    from . import actions
    from .ai import tools
    results: list[str] = []
    for step in entry.get("steps", []):
        try:
            out = tools.call(step["tool"], step.get("args") or {})
        except Exception as exc:
            out = f"ERROR: {type(exc).__name__}: {exc}"
        results.append(f"{step['tool']}: {' '.join(str(out).split())[:90]}")
        actions.journal("macro_step", f"{trigger} → {step['tool']}", str(out))
        if gap and step is not entry["steps"][-1]:
            time.sleep(gap)
    data = load()
    if trigger in data:
        data[trigger]["used"] = data[trigger].get("used", 0) + 1
        save(data)
    return f"Ran '{trigger}'. " + "; ".join(results)


def describe(name: str = "") -> str:
    """What a macro will do, in words — before you trust it."""
    data = load()
    if not data:
        return "no macros yet — say 'when I say work mode, open code and set volume 40'"
    picked = {name: data[name]} if name and name in data else data
    if not picked:
        return f"no macro called '{name}'"
    lines = []
    for trigger, entry in picked.items():
        steps = ", ".join(f"{s['tool']}({', '.join(f'{k}={v}' for k, v in s['args'].items())})"
                          for s in entry.get("steps", []))
        lines.append(f"{trigger} → {steps}  [used {entry.get('used', 0)}x]")
    return "\n".join(lines)


def forget(name: str) -> str:
    data = load()
    hit = next((k for k in data if k.lower() == (name or "").lower().strip()), None)
    if not hit:
        return f"ERROR: no macro called '{name}'"
    data.pop(hit)
    save(data)
    return f"forgot '{hit}'"
