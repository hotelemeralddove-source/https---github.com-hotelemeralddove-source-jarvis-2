"""Send the model the eight tools that could possibly matter, not all 51.

Why this exists
---------------
Measured, not assumed: the full tool catalogue is ~4 200 tokens of JSON schema
once MCP servers are connected. Three consequences, all of them bad:

  1. a small local model refuses the request outright — "maximum context length
     is 2048 tokens, you requested 4210" is a real error from a real run;
  2. even a big model pays that on every single round, which is the opposite of
     "low RAM, no lag";
  3. with 51 options a 0.5B model picks `system_report` when you asked for the
     time, because 50 distractors beat one good description.

So: score the tools against the sentence, keep the best few, and always include
`list_tools` so the model can ask for the rest instead of guessing. It is a
retrieval step, done with plain keyword overlap and a synonym table — no
embeddings, no model, no network, and it costs microseconds.

The rule this file must never break: when in doubt, include MORE tools. A tool
that was not offered cannot be called, and a missing tool looks exactly like a
model that ignored you.
"""
from __future__ import annotations

import re

# words that carry no routing signal
STOP = {
    "a", "an", "the", "and", "or", "of", "to", "for", "in", "on", "at", "is",
    "it", "my", "me", "i", "you", "please", "can", "could", "would", "will",
    "do", "does", "did", "that", "this", "with", "from", "up", "am", "be",
    "what", "whats", "how", "much", "many", "now", "again", "just", "some",
    "arc", "macha", "da", "yaar", "bro", "please",
}

# phrase -> tools. Checked as a substring of the normalised sentence, which is
# why the phrases are short: "vol" would fire on "volume" and "revolver" both,
# so the table stays explicit instead of clever.
SYNONYMS: dict[str, tuple[str, ...]] = {
    # apps and windows
    "open": ("open_app",), "launch": ("open_app",), "start app": ("open_app",),
    "close": ("close_app",), "kill": ("close_app",), "quit app": ("close_app",),
    "switch to": ("windows",), "which window": ("windows",), "window": ("windows",),
    # web
    "search": ("web_search",), "google": ("web_search",), "look up": ("web_search",),
    "website": ("open_url",), "browser": ("open_url",), "link": ("open_url",),
    "youtube": ("open_url",), "play": ("open_url", "media"),
    # sound and screen
    "volume": ("set_volume",), "loud": ("set_volume",), "sound": ("set_volume",),
    "mute": ("mute",), "silence": ("mute",), "unmute": ("mute",),
    "brightness": ("brightness",), "dim": ("brightness",),
    "song": ("media",), "music": ("media", "open_url"), "pause": ("media",),
    "next track": ("media",), "skip": ("media",),
    "screenshot": ("screenshot",), "screen shot": ("screenshot",),
    "capture": ("screenshot",), "grab the screen": ("screenshot",),
    # machine state
    "ram": ("system_report",), "memory": ("system_report",),
    "cpu": ("system_report",), "battery": ("system_report",),
    "disk": ("system_report",), "temp": ("system_report",),
    "status": ("system_report", "arc_mode"), "health": ("system_report",),
    "time": ("time", "timer"), "clock": ("time",), "date": ("time",),
    "timer": ("timer",), "remind": ("remind", "timer", "calendar"),
    "reminder": ("remind",), "reminders": ("remind",), "remind me": ("remind",),
    "focus": ("focus",), "pomodoro": ("focus",), "deep work": ("focus",),
    "briefing": ("briefing",), "brief me": ("briefing",), "good morning": ("briefing",),
    # the studio, business and travel layer
    "blog": ("content",), "caption": ("content",), "hashtags": ("content",),
    "reel": ("content", "video_studio"), "content": ("content",),
    "post": ("content", "image_studio"),
    "funnel": ("marketing",), "utm": ("marketing",), "seo": ("marketing",),
    "marketing": ("marketing",), "campaign": ("marketing",), "ads": ("marketing",),
    "swot": ("strategy",), "strategy": ("strategy",), "canvas": ("strategy",),
    "break even": ("strategy",), "okr": ("strategy",), "margin": ("strategy",),
    "hotel": ("hotel",), "occupancy": ("hotel",), "revpar": ("hotel",),
    "adr": ("hotel",), "housekeeping": ("hotel",), "menu": ("hotel",),
    "travel": ("travel",), "trip": ("travel",), "itinerary": ("travel",),
    "map": ("travel",), "places": ("travel",), "distance": ("travel",),
    "palette": ("craft",), "kolam": ("craft",),
    "design": ("craft",), "logo": ("craft",), "colours": ("craft",),
    "dataset": ("mine",), "correlate": ("mine",),
    "outliers": ("mine",), "analytics": ("mine",), "data": ("mine",),
    "mentor": ("mentor",), "scamper": ("mentor",), "brainstorm": ("mentor",),
    "pre-mortem": ("mentor",), "ideas": ("mentor", "content"),
    "future": ("foresight",), "scenario": ("foresight",), "news": ("foresight",),
    "password": ("secure",), "phishing": ("secure",), "secure": ("secure",),
    "security": ("secure",), "hack": ("secure",), "backup": ("secure",),
    # what ARC knows
    "what is": ("facts",), "who is": ("facts",), "tell me about": ("facts",),
    "define": ("facts",), "wikipedia": ("facts",), "fact": ("facts",),
    "library": ("facts",), "knowledge": ("facts",),
    # the studio
    "denoise": ("audio_studio",), "grade": ("video_studio", "image_studio"),
    "collage": ("image_studio",), "waveform": ("audio_studio",),
    "colour grade": ("video_studio", "image_studio"), "mix": ("audio_studio",),
    # the open-source catalogue
    "package": ("packages",), "packages": ("packages",), "github": ("packages",),
    "open source": ("packages",), "alternative": ("packages",),
    "not installed": ("packages",),
    # maths, units, money
    "calculate": ("calc",), "plus": ("calc",), "minus": ("calc",),
    "times": ("calc",), "divided": ("calc",), "percent": ("calc",),
    "square root": ("calc",), "sum of": ("calc",),
    "convert": ("convert", "edit_file"), "how many km": ("convert",), "in miles": ("convert",),
    "in kg": ("convert",), "celsius": ("convert",), "fahrenheit": ("convert",),
    "exchange rate": ("rates",), "dollar": ("rates",), "rupee": ("rates",),
    "forex": ("rates",),
    "stock": ("stock", "project"), "share price": ("stock",), "ticker": ("stock",),
    "nifty": ("stock", "market_summary"), "sensex": ("stock", "market_summary"),
    "bank nifty": ("stock",), "market": ("market_summary",), "bitcoin": ("stock",),
    "gold rate": ("stock",), "silver rate": ("stock",), "ethereum": ("stock",),
    "predict": ("foresight", "project"), "forecast": ("foresight", "project"),
    "trend": ("foresight", "project"),
    "target price": ("project",),
    # any file format: read, review, edit, generate
    "summarise": ("read_file",), "summarize": ("read_file",), "summary": ("read_file",),
    "outline": ("read_file",), "transcript": ("read_file",),
    "review": ("read_file",), "missing": ("read_file",), "improve": ("read_file",),
    "pdf": ("read_file", "edit_file"), "docx": ("read_file", "edit_file"),
    "word document": ("read_file", "edit_file"), "spreadsheet": ("read_file", "edit_file"),
    "excel": ("read_file", "edit_file"), "xlsx": ("read_file", "edit_file"),
    "slides": ("read_file", "edit_file"), "powerpoint": ("read_file", "edit_file"),
    "pptx": ("read_file", "edit_file"), "csv": ("read_file", "edit_file"),
    "mp3": ("read_file", "edit_file"), "wav": ("read_file", "edit_file"),
    "mp4": ("read_file", "edit_file", "make_media"), "mov": ("read_file", "edit_file"),
    "voice note": ("read_file",), "audio file": ("read_file", "edit_file"),
    "photo": ("read_file", "edit_file", "make_media"),
    "resize": ("edit_file",), "crop": ("edit_file",), "rotate": ("edit_file",),
    "trim": ("edit_file",), "thumbnail": ("edit_file", "image_studio"),
    "watermark": ("edit_file",),
    "subtitles": ("edit_file",), "compress": ("edit_file",), "grayscale": ("edit_file",),
    "greyscale": ("edit_file",),
    "edit the": ("edit_file",), "change the": ("edit_file",),
    "generate": ("make_media",), "make an image": ("make_media",),
    "make a video": ("make_media",), "wallpaper": ("make_media",),
    "poster": ("craft", "make_media"), "animate": ("make_media",),
    "restyle": ("make_media",),
    # market depth and health
    "analyse": ("market",), "analyze": ("market",), "should i buy": ("market",),
    "should i sell": ("market",), "buy or sell": ("market",), "watchlist": ("market",),
    "position size": ("market",), "how many shares": ("market",), "risk": ("market",),
    "screener": ("market",), "momentum": ("market",),
    "symptom": ("health",), "symptoms": ("health",), "medicine": ("health",),
    "tablet": ("health",), "dosage": ("health",), "dose": ("health",),
    "paracetamol": ("health",), "ibuprofen": ("health",), "antibiotic": ("health",),
    "anatomy": ("health",), "body part": ("health",), "organ": ("health",),
    "first aid": ("health",), "cpr": ("health",), "choking": ("health",),
    "burn": ("health",), "fever": ("health",), "chest pain": ("health",),
    # the projector
    "hologram": ("holo",), "holographic": ("holo",), "holo deck": ("holo",),
    "server view": ("holo",), "projector": ("holo",), "telemetry": ("holo",),
    # notes and files
    "note": ("note", "read_notes"), "remember": ("note",), "write down": ("note",),
    "what did i note": ("read_notes",), "my notes": ("read_notes",),
    "find": ("find_file",), "where is": ("find_file",), "locate": ("find_file",),
    "find my": ("find_file",), "where is my": ("find_file",),
    "search my files": ("find_file",), "my files": ("find_file",),
    "file": ("file_op", "read_file", "find_file"), "folder": ("file_op",),
    "read the file": ("read_file",), "delete": ("file_delete",),
    "copy": ("file_op",),
    # eyes and hands
    "click": ("click_text", "click_at", "ui_act"),
    "type": ("type_text",), "keypress": ("press",), "hotkey": ("press",),
    "what does it say": ("screen_text",), "read the screen": ("screen_text",),
    "error on screen": ("screen_text", "look"), "ocr": ("screen_text",),
    "on my screen": ("look", "screen_text"), "look at": ("look",),
    "what is this": ("look",), "summarise this page": ("look",),
    "read this": ("look", "read_file"),
    "button": ("ui_controls", "ui_act"), "checkbox": ("ui_controls", "ui_act"),
    "fill in": ("ui_act",), "form": ("ui_controls", "ui_act"),
    # people
    "email": ("email_send", "email_draft"), "mail": ("email_send", "email_draft"),
    "whatsapp": ("whatsapp_send",), "message": ("whatsapp_send", "email_draft"),
    "calendar": ("calendar",), "meeting": ("calendar",), "appointment": ("calendar",),
    "schedule": ("calendar", "timer"),
    # arc itself
    "draw": ("draw", "art_edit"), "sketch": ("draw",), "paint": ("draw",),
    "picture": ("draw", "make_media", "edit_file", "read_file"),
    "colour": ("art_edit",), "color": ("art_edit",),
    "make it": ("art_edit",), "bigger": ("art_edit",),
    "theme": ("arc_mode",), "mode": ("arc_mode", "magic"), "magic": ("magic",),
    "charms": ("charms",), "widget": ("charms",),
    "lock": ("lock_screen",), "shutdown": ("power",), "restart": ("power",),
    "clipboard": ("clipboard",), "what did i copy": ("clipboard",),
    "command": ("run_command",), "shell": ("run_command",),
    "log": ("action_log",), "what have you done": ("action_log",),
    "mcp": ("mcp_servers",), "plugins": ("mcp_servers",),
    # learning
    "when i say": ("teach_macro",), "teach": ("teach_macro",),
    "what have i taught": ("macros",), "my macros": ("macros",),
}

NAME_WEIGHT = 3
DESC_WEIGHT = 1
SYNONYM_WEIGHT = 5
# One shared word in a long description is coincidence, not a signal: "hello
# there" scored 1 on `ui_act` ("…whether…") and that was the whole shortlist.
MIN_SCORE = 2

_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or "").lower()) if len(t) > 1 and t not in STOP}


# Tokenising 87 descriptions on every request was measurable: routing cost ~75 ms per
# sentence, which is 75 ms of the user's "why is the answer slow". The bag for a tool
# never changes while the process runs, so it is computed once and kept.
_BAG_CACHE: dict[str, tuple[int, set[str]]] = {}


def _bag(tool) -> set[str]:
    """The words that describe a tool: its name, hyphen split, plus its blurb."""
    desc = tool.description or ""
    stamp = (hash(desc), len(desc))
    cached = _BAG_CACHE.get(tool.name)
    if cached is not None and cached[0] == stamp[0]:
        return cached[1]
    name_words = set(tool.name.replace("__", "_").split("_"))
    words = (name_words - {""}) | tokens(desc)
    _BAG_CACHE[tool.name] = (stamp[0], words)
    return words


def synonym_hits(text: str) -> set[str]:
    """Phrase table lookup, on word boundaries.

    Plain substring matching routed "open notepad" to `note`, because "notepad"
    contains "note". A router that mis-fires on a substring is worse than no
    router, so every phrase is matched as whole words.
    """
    low = " ".join((text or "").lower().split())
    hits: set[str] = set()
    for phrase, names in SYNONYMS.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", low):
            hits.update(names)
    return hits


def score(text: str, tool, words: set[str] | None = None,
          hits: set[str] | None = None) -> int:
    """Score one tool. `words` and `hits` may be passed in when scoring many tools —
    computing them 87 times per request was the slow part, not the comparison."""
    words = tokens(text) if words is None else words
    hits = synonym_hits(text) if hits is None else hits
    total = 0
    name_words = set(tool.name.split("_"))
    total += NAME_WEIGHT * len(words & name_words)
    total += DESC_WEIGHT * len(words & (_bag(tool) - name_words))
    if tool.name in hits:
        total += SYNONYM_WEIGHT
    # a tool whose exact name is in the sentence is almost certainly the one
    if tool.name.replace("_", " ") in (text or "").lower():
        total += SYNONYM_WEIGHT
    return total


def shortlist(text: str, tools: dict, k: int = 8,
              always: tuple = ("list_tools",)) -> list:
    """The best k tools for this sentence, plus the escape hatch.

    Ties keep catalogue order, so the result is deterministic — a router that
    changes its mind between two identical requests is impossible to debug.
    """
    words = tokens(text)
    hits = synonym_hits(text)          # once, not once per tool
    ranked = sorted(
        ((score(text, t, words, hits), i, t) for i, t in enumerate(tools.values())),
        key=lambda row: (-row[0], row[1]),
    )
    picked = [t for s, _, t in ranked if s >= MIN_SCORE or t.name in hits][:k]
    # nothing scored — this is chit-chat; give the model the everyday set
    if not picked:
        picked = [tools[n] for n in DEFAULT_NAMES if n in tools]
    have = {t.name for t in picked}
    for name in always:
        if name in tools and name not in have:
            picked.append(tools[name])
            have.add(name)
    return picked


def names(text: str, tools: dict, k: int = 8) -> list[str]:
    return [t.name for t in shortlist(text, tools, k)]


# no signal at all: the handful a friendly assistant needs to hold a conversation
DEFAULT_NAMES = ("time", "system_report", "note", "read_notes", "open_app",
                 "web_search", "timer", "calc")


def estimate(schemas: list) -> dict:
    """Rough token cost of a schema list — 4 chars per token is close enough."""
    import json
    chars = len(json.dumps(schemas))
    return {"tools": len(schemas), "chars": chars, "tokens": round(chars / 4)}
