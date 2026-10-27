"""How it talks to you — a companion, not a command line with a voice.

The request, in the user's words:

    "human aid response mathiri venum… 'hey jarvis' nu nan solum pothu reply voice la
     'hi commander' nu jarvis solanum, 'bye' solum pothu 'thank you commander' sollanum,
     task assign pana athuku related ah pesanum, oru companion mathiri pesanum"

So there are five moments, and each has one short line:

    greeting   "hey jarvis"                    → "Hi commander."
    ack        a task was assigned             → "Opening Notepad, commander."
    progress   it is taking a while            → "Still on it, commander."
    done       it finished                     → "Done, commander."
    farewell   "bye jarvis"                    → "Thank you, commander."

Rules that keep it from becoming annoying, which is the usual failure of a talking
assistant:

* **short** — one clause. It is a companion, not a narrator;
* **never over the answer** — the acknowledgement is only spoken when the request is
  genuinely slow (the caller decides, see `Window._ack_timer`); a Lite reply in 4 ms
  gets silence as its acknowledgement;
* **the honourific is a setting** (`companion.honorific`, default "commander") and the
  name comes from `identity` (JARVIS), so neither is typed twice;
* **every line can be switched off** in Settings → Look & sound.

Nothing here speaks by itself: it returns text, and the caller says it through the reply
voice, so the cloned voice is used for these lines too.
"""
from __future__ import annotations

import itertools
import random
import re

from . import identity

DEFAULTS = {
    "enabled": True,
    "honorific": "commander",
    "greet": True,
    "farewell": True,
    "acks": True,
    "progress": True,
    "announce_done": False,     # the cue is enough unless somebody asks for words too
}

# What the task is about, from the words people actually say. Ordered: the first match
# wins, so the specific ones come before the general ones.
_TASK_PATTERNS: list[tuple[str, str]] = [
    # the app name stops at "and" / "then" / a comma — "open notepad and tell me my cpu"
    # must acknowledge Notepad, not the whole sentence
    (r"\b(?:open|launch|start)\s+(?:the\s+)?([a-z0-9.+-][a-z0-9 .+-]{1,19}?)"
     r"(?=\s+(?:and|then)\b|[,.]|$)", "opening {thing}"),
    (r"\b(?:close|quit|kill)\s+(?:the\s+)?([a-z0-9.+-][a-z0-9 .+-]{1,19}?)"
     r"(?=\s+(?:and|then)\b|[,.]|$)", "closing {thing}"),
    (r"\b(cpu|ram|memory|system report|machine|temperature|battery)\b",
     "checking the machine"),
    (r"\b(screenshot|screen ?shot)\b", "capturing the screen"),
    (r"\b(time|date|what day)\b", "checking the clock"),
    (r"\b(weather|temperature outside|rain)\b", "checking the weather"),
    (r"\b(volume|mute|louder|quieter|sound)\b", "adjusting the volume"),
    (r"\b(search|google|look up|find out)\b", "searching"),
    (r"\b(note|remember|save this|write down)\b", "writing that down"),
    (r"\b(file|folder|document|find the)\b", "looking through your files"),
    (r"\b(timer|remind|alarm|in \d+ minutes?)\b", "setting that up"),
    (r"\b(play|pause|song|music|video)\b", "on the media controls"),
    (r"\b(fix|repair|clean|tidy|speed up|slow)\b", "on the machine itself"),
    (r"\b(who are you|your name|what can you do)\b", "that one is about me"),
]


def _cfg(cfg: dict | None) -> dict:
    out = dict(DEFAULTS)
    got = ((cfg or {}).get("companion") or {})
    if isinstance(got, dict):
        for k, v in got.items():
            out[k] = v
    return out


def honorific(cfg: dict | None = None) -> str:
    got = str(_cfg(cfg).get("honorific") or "").strip()
    return got or "commander"


def enabled(cfg: dict | None = None) -> bool:
    return bool(_cfg(cfg).get("enabled", True))


def _ok(cfg: dict | None, key: str) -> bool:
    return enabled(cfg) and bool(_cfg(cfg).get(key, True))


# --------------------------------------------------------------------------- lines
def greeting(cfg: dict | None = None, vary: bool = False) -> str:
    """What it says the moment the wake word lands.

    The first one is the line that was asked for, word for word, because it is the line
    people will judge the whole thing by. The others rotate only if `vary=True`, so a
    test can always assert a fixed answer.
    """
    who = honorific(cfg)
    options = [
        f"Hi {who}.",
        f"Hi {who}. {identity.name(cfg)} online.",
        f"At your service, {who}.",
    ]
    return random.choice(options) if vary else options[0]


def farewell(cfg: dict | None = None) -> str:
    who = honorific(cfg)
    return f"Thank you, {who}."


_PROGRESS = ("Still on it, {who}.", "Working on that, {who}.", "One moment, {who}.")
_PROGRESS_TURN = itertools.count()


def progress(cfg: dict | None = None) -> str:
    """Rotates instead of picking at random — same variety, but the first one is
    always "Still on it", so a long job reads as a sequence rather than a stutter,
    and a test can pin it down."""
    who = honorific(cfg)
    return _PROGRESS[next(_PROGRESS_TURN) % len(_PROGRESS)].format(who=who)


def done(cfg: dict | None = None, ok: bool = True) -> str:
    who = honorific(cfg)
    return f"Done, {who}." if ok else f"That did not work, {who}."


def ack(cfg: dict | None = None, request: str = "") -> str:
    """A short, *task-related* acknowledgement — not "OK, commander" for everything.

    "Opening Notepad, commander" is the difference between a companion and a beep.
    """
    who = honorific(cfg)
    said = (request or "").strip().lower()
    for pattern, template in _TASK_PATTERNS:
        m = re.search(pattern, said)
        if not m:
            continue
        if "{thing}" in template:
            thing = (m.group(1) or "").strip(" .")
            if not thing:
                continue
            # one word is a name ("Notepad"); several words are a sentence fragment
            word = thing if " " in thing else thing.capitalize()
            line = template.format(thing=word)
            # not str.capitalize(): that lowercases "Notepad" into "notepad"
            return f"{line[0].upper() + line[1:]}, {who}."
        line = template
        return f"{line[0].upper() + line[1:]}, {who}."
    if re.match(r"^(hi|hello|hey|vanakkam)\b", said):
        return greeting(cfg)
    if said.endswith("?"):
        return f"Let me think about that, {who}."
    return f"On it, {who}."


# --------------------------------------------------------------------------- checks
def phrases(cfg: dict | None = None) -> dict[str, str]:
    """Every fixed line in one place — used by the tests and by the Settings preview."""
    return {
        "greeting": greeting(cfg),
        "progress": f"Still on it, {honorific(cfg)}.",
        "done": done(cfg),
        "failed": done(cfg, ok=False),
        "farewell": farewell(cfg),
        "ack_open": ack(cfg, "open notepad"),
        "ack_report": ack(cfg, "what is my cpu usage"),
        "ack_unknown": ack(cfg, "do the thing we talked about"),
    }


def describe(cfg: dict | None = None) -> str:
    state = "on" if enabled(cfg) else "off"
    return (f"companion voice: {state} · calls you \"{honorific(cfg)}\" · "
            f"name \"{identity.name(cfg)}\"")
