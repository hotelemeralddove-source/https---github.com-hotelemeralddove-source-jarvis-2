"""A tiny model of you — so JARVIS stops asking the same thing twice.

Not a vector database and not a "memory" feature that burns 300 MB. One JSON file,
a few dozen keys, ~2 KB on disk, injected into the prompt as four lines. That is
enough to turn "open my editor" into a real command and to stop the answer being
written for a stranger.

Two ways it fills up:

  * explicit — "my name is Arun", "I use VS Code", "remember I prefer Tanglish";
  * teaching — `set` through the `profile` tool, or by editing the file.

The rule that keeps this safe: **the profile is only ever read, never executed.**
Nothing in it becomes a command, a path, or a shell string. A hostile file can at
worst make ARC think your name is Kevin.
"""
from __future__ import annotations

import json
import re
import time

from . import config

# key -> (human label, what it is for). Anything not in here is refused, so the
# file cannot quietly grow junk that later gets pasted into the prompt.
FIELDS: dict[str, str] = {
    "name": "what to call the user",
    "language": "reply language: tamil, tanglish, hindi, hinglish, english",
    "editor": "their code editor",
    "browser": "their browser",
    "music": "music app they use",
    "city": "city, for weather and time",
    "volume": "the volume level they actually like",
    "work_start": "when their work day usually starts",
    "work_end": "when it usually ends",
    "projects": "what they are building, one line",
}

LIMIT = 600          # characters of summary that go into the prompt
MAX_VALUE = 120      # nothing longer belongs in a profile


def _path():
    return config.data_dir() / "profile.json"


def load() -> dict:
    """Read the profile. A corrupt file is ignored, never fatal."""
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        clean = {}
        for key, value in raw.items():
            if key in FIELDS and isinstance(value, (str, int, float)):
                clean[key] = str(value)[:MAX_VALUE]
            elif key == "updated":
                clean[key] = str(value)
        return clean
    except Exception:
        return {}


def save(data: dict) -> bool:
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in data.items() if k in FIELDS or k == "updated"}
        payload["updated"] = time.strftime("%Y-%m-%d %H:%M")
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def get(key: str) -> str:
    return load().get(key, "")


def set(key: str, value: str) -> str:
    key = (key or "").strip().lower()
    if key not in FIELDS:
        return (f"ERROR: '{key}' is not something I keep. I can remember: "
                + ", ".join(sorted(FIELDS)))
    value = " ".join(str(value or "").split())[:MAX_VALUE]
    if not value:
        return forget(key)
    data = load()
    data[key] = value
    if not save(data):
        return "ERROR: could not write the profile file"
    return f"Remembered: your {key} is {value}."


def forget(key: str) -> str:
    key = (key or "").strip().lower()
    data = load()
    if key in data:
        data.pop(key, None)
        save(data)
        return f"Forgot your {key}."
    return f"I had nothing saved for '{key}'."


def describe() -> str:
    """What the `profile` tool shows: every field, set or not."""
    data = load()
    lines = []
    for key in sorted(FIELDS):
        value = data.get(key)
        lines.append(f"{key}: {value}" if value else f"{key}: — ({FIELDS[key]})")
    if data.get("updated"):
        lines.append(f"last updated: {data['updated']}")
    return "\n".join(lines)


def summary() -> str:
    """The four lines that go into the system prompt. Empty when nothing is known."""
    data = load()
    bits = []
    if data.get("name"):
        bits.append(f"name is {data['name']}")
    for key in ("editor", "browser", "music", "city", "projects"):
        if data.get(key):
            bits.append(f"{key}: {data[key]}")
    if data.get("language"):
        bits.append(f"prefers replies in {data['language']}")
    if data.get("volume"):
        bits.append(f"usual volume {data['volume']}")
    if data.get("work_start") and data.get("work_end"):
        bits.append(f"works {data['work_start']}–{data['work_end']}")
    if not bits:
        return ""
    text = "What I know about the user (do not recite this list, just use it): " + "; ".join(bits) + "."
    return text[:LIMIT]


# --------------------------------------------------------------------- learning
# Deliberately narrow. A loose pattern here is how an assistant starts "learning"
# that your name is "and" or that your editor is "the".
PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:[Mm]y name is|[Cc]all me|[Ii] am|[Ii]'m)\s+([A-Za-z][\w'-]{1,20})\b"), "name"),
    (re.compile(r"\b[Ii] (?:use|code in|work in)\s+(vs ?code|vscode|pycharm|neovim|vim|"
                r"sublime|intellij|android studio|zed|emacs)\b", re.I), "editor"),
    (re.compile(r"\b[Ii] (?:use|browse in|browse with)\s+(chrome|firefox|edge|brave|safari|arc)\b",
                re.I), "browser"),
    (re.compile(r"\b[Ii] (?:listen to music on|use)\s+(spotify|youtube music|apple music|wynk|"
                r"gaana|jiosaavn)\b", re.I), "music"),
    (re.compile(r"\b[Ii] live in\s+([A-Z][\w' -]{2,24})\b"), "city"),
    (re.compile(r"\b(?:[Rr]eply|[Tt]alk|[Aa]nswer|[Ss]peak)(?: to me)? in\s+(tamil|tanglish|hindi|hinglish|"
                r"english)\b", re.I), "language"),
    (re.compile(r"\b(?:[Ii] prefer|[Kk]eep|[Ss]et my)\s+(?:the\s+)?volume (?:at|to)\s+(\d{1,3})\b", re.I),
     "volume"),
    (re.compile(r"\b[Ii] (?:start|begin) work (?:at|around)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", re.I),
     "work_start"),
]

FIXES = {"vscode": "VS Code", "vs code": "VS Code", "pycharm": "PyCharm",
         "neovim": "Neovim", "intellij": "IntelliJ", "android studio": "Android Studio",
         "chrome": "Chrome", "firefox": "Firefox", "edge": "Edge", "spotify": "Spotify"}


def learn(text: str) -> str:
    """Pull a durable fact out of a sentence. Returns a confirmation, or "".

    Only fires on explicit first-person statements, never on questions — "do I
    use vim?" must not teach it that you use vim.
    """
    said = " ".join((text or "").split())
    if not said or said.endswith("?") or said.endswith("?"):
        return ""
    for pattern, key in PATTERNS:
        match = pattern.search(said)
        if not match:
            continue
        value = match.group(1).strip()
        if key in ("editor", "browser", "music"):
            value = FIXES.get(value.lower(), value)
        if key == "language":
            value = value.lower()
        if key == "name" and value.lower() in {
                "going", "not", "sorry", "here", "fine", "good", "a", "an", "the", "your",
                "my", "so", "very", "just", "still", "also", "new", "sure", "ok", "okay",
                "tired", "busy", "hungry", "late", "done", "back", "out", "in", "on"}:
            continue
        current = get(key)
        if current.lower() == value.lower():
            return ""
        return set(key, value)
    return ""


def reset() -> str:
    try:
        _path().unlink(missing_ok=True)
    except Exception:
        return "ERROR: could not delete the profile"
    return "Profile cleared. I have forgotten what I knew about you."


def tools_entry() -> dict:
    """The data the `profile` tool exposes — kept here so tools.py stays short."""
    return {"get": describe, "set": set, "forget": forget, "clear": reset}
