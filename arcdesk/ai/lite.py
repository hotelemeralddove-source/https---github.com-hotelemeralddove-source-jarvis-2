"""JARVIS Lite — the zero-setup, zero-RAM, fully offline brain.

There is no LLM here: it is intent matching over the same tool registry the real
model uses. Why it exists:

  * the app is useful the second you install it, with no API key and no model
  * if the internet dies or you unplug, ARC does not go dead
  * it is the fallback when a provider errors out mid-conversation

It will never write you an essay, and it says so honestly when it does not
understand, instead of hallucinating.
"""
from __future__ import annotations

import re

def _who() -> str:
    """The name this installation answers to (JARVIS unless changed in Settings)."""
    try:
        from .. import config, identity
        return identity.name(config.load())
    except Exception:
        from ..identity import DEFAULT_NAME
        return DEFAULT_NAME
import uuid


def _call(tool: str, **args) -> dict:
    """Build a tool-call record. The first parameter is NOT called `name` on
    purpose: tools like find_file take an argument called `name`, and Python
    would bind it to this parameter instead — a TypeError that silently made the
    file-search branch unreachable."""
    return {
        "id": "lite_" + uuid.uuid4().hex[:8],
        "type": "function",
        "function": {"name": tool, "arguments": __import__("json").dumps(args)},
    }


NUM = re.compile(r"(\d+(?:\.\d+)?)")


def _quoteish(text: str) -> str:
    """The last few words of a sentence — used as the 'word from the reminder' key."""
    words = re.findall(r"[A-Za-z0-9']+", text or "")
    tail = [w for w in words if w.lower() not in
            ("cancel", "delete", "remove", "drop", "reminder", "reminders", "the", "my")]
    return " ".join(tail[-2:]) if tail else ""

# Common things people actually say. Keeps "open google" instant and offline.
SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "chatgpt": "https://chat.openai.com",
    "arena": "https://arena.ai",
    "arena ai": "https://arena.ai",
    "stack overflow": "https://stackoverflow.com",
    "wikipedia": "https://www.wikipedia.org",
}

MODE_WORDS = {"focus": "focus", "chill": "chill", "gaming": "gaming", "game": "gaming",
              "night": "night", "dark": "night"}


def _num(text: str, default=None):
    m = NUM.search(text)
    return float(m.group(1)) if m else default


PATH_RE = re.compile(
    r"(?P<q>[\"'][^\"']+[\"'])"                      # quoted, spaces allowed
    r"|(?P<p>(?:[A-Za-z]:\\|~/|/)[^\s\"']+)"         # absolute or home path
    r"|(?P<n>[^\s\"']+\.(?:pdf|docx?|xlsx?|pptx?|csv|tsv|json|jsonl|txt|md|py|log|"
    r"png|jpe?g|gif|webp|bmp|tiff?|wav|mp3|m4a|flac|ogg|aac|opus|mp4|mov|mkv|avi|webm))",
    re.I)

EXTRA_FMT = {"mp3", "wav", "m4a", "flac", "ogg", "png", "jpg", "jpeg", "webp", "pdf",
             "mp4", "gif", "txt"}


def _path_in(text: str) -> str:
    """The best file candidate in the sentence: absolute beats relative."""
    matches = list(PATH_RE.finditer(text or ""))
    if not matches:
        return ""
    ranked = sorted(matches, key=lambda m: 0 if (m.group("q") or m.group("p")) else 1)
    m = ranked[0]
    raw = (m.group("q") or m.group("p") or m.group("n") or "").strip("\"'")
    return raw.strip().rstrip(".,;:")


def _paths_in(text: str) -> list[str]:
    """Every file candidate in the sentence, in order, de-duplicated."""
    seen, out = set(), []
    for match in PATH_RE.finditer(text or ""):
        raw = (match.group("q") or match.group("p") or match.group("n") or "").strip()
        raw = raw.strip("\"'").rstrip(".,;:")
        if raw and raw not in seen:
            seen.add(raw)
            out.append(raw)
    return out


def _known_drug(low: str) -> str:
    """A medicine this build actually has verified data for, or "" — no guessing."""
    try:
        from .. import health
        for name in health.DRUGS:
            if re.search(rf"\b{re.escape(name)}\b", low):
                return name
            for alias in health.DRUGS[name].get("also", []):
                label = alias.split(" (")[0].strip()
                if label and re.search(rf"\b{re.escape(label)}\b", low):
                    return name
    except Exception:
        pass
    return ""


def _drug_in(low: str) -> str:
    """The medicine name to send to the health tool: known first, else the phrase."""
    known = _known_drug(low)
    if known:
        return known
    m = re.search(r"\b(?:for|of|is|about|take|does)\s+([a-z][a-z \-]{2,24})", low)
    if m:
        return m.group(1).strip()
    m = re.search(r"^([a-z][a-z \-]{2,24})\s+(?:dose|dosage|tablet|medicine)", low)
    return m.group(1).strip() if m else ""


def _symbol_in(low: str) -> str:
    m = re.search(r"\b(nifty|sensex|banknifty|reliance|tcs|infy|wipro|hdfc|icici|"
                  r"bitcoin|btc|ethereum|gold|silver)\b", low)
    return m.group(1) if m else "nifty"


def _edit_op(low: str) -> str:
    for word, op in (("resize", "resize"), ("crop", "crop"), ("rotate", "rotate"),
                     ("thumbnail", "thumbnail"), ("watermark", "watermark"),
                     ("subtitle", "subtitles"), ("extract audio", "extract_audio"),
                     ("split", "split"), ("merge", "merge"), ("compress", "compress"),
                     ("greyscale", "greyscale"), ("grayscale", "greyscale"),
                     ("blur", "blur"), ("trim", "trim"), ("gif", "gif"),
                     ("convert", "convert")):
        if word in low:
            return op
    return "convert"


def _backup_source(low: str, text: str) -> str:
    """Which folder the user means. Never the backup target, never a guess at a path."""
    explicit = re.search(r"\bfrom\s+([a-z]:\\[^\s]*|/[^\s]+|~[^\s]*)", text, re.I)
    if explicit:
        return explicit.group(1)
    for word, folder in (("document", "Documents"), ("photo", "Pictures"),
                         ("picture", "Pictures"), ("image", "Pictures"),
                         ("desktop", "Desktop"), ("download", "Downloads"),
                         ("music", "Music"), ("video", "Videos")):
        if re.search(rf"\b{word}s?\b", low):
            return f"~/{folder}"
    bare = re.search(r"(?<!to\s)(?<!onto\s)([a-z]:\\[^\s]*|/[^\s]+)", text, re.I)
    if bare and not re.search(r"\bto\s+" + re.escape(bare.group(1)), text, re.I):
        return bare.group(1)
    return "~"


def _edit_args(low: str) -> dict:
    """Pull the numbers out of the sentence: 800x600, 90 degrees, first 10 seconds."""
    args: dict = {}
    size = re.search(r"(\d{2,5})\s*[x×]\s*(\d{2,5})", low)
    if size:
        args["width"], args["height"] = int(size.group(1)), int(size.group(2))
    else:
        one = re.search(r"(?:width|to|at)\s*(\d{2,5})\s*(?:px|pixels)?", low)
        if one:
            args["width"] = int(one.group(1))
    angle = re.search(r"(\d{1,3})\s*(?:degrees|deg)", low)
    if angle:
        args["angle"] = int(angle.group(1))
    span = re.search(r"(?:first|for|last)\s*(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds?)", low)
    if span:
        args["duration"] = float(span.group(1))
    start = re.search(r"(?:from|starting at)\s*(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?)", low)
    if start:
        args["start"] = float(start.group(1))
    if re.search(r"\bto\s+(mp3|wav|mp4|gif|png|jpg|jpeg|pdf|webm|m4a|ogg)\b", low):
        args["fmt"] = re.search(r"\bto\s+(mp3|wav|mp4|gif|png|jpg|jpeg|pdf|webm|m4a|ogg)\b",
                                low).group(1)
    fps = re.search(r"(\d{1,2})\s*fps", low)
    if fps:
        args["fps"] = int(fps.group(1))
    return args


_PHOTO_FILLER = {"show", "me", "give", "get", "find", "fetch", "send", "see", "a", "an",
                 "the", "real", "actual", "genuine", "true", "some", "please", "one",
                 "photo", "photograph", "picture", "pic", "image", "kudu", "kodu"}


def _tidy_subject(text: str) -> str:
    """Strip the polite scaffolding: "show me a real elephant photo" -> "elephant"."""
    words = re.sub(r"\s+", " ", text or "").strip(" .").split()
    while words and words[0] in _PHOTO_FILLER:
        words.pop(0)
    while words and words[-1] in _PHOTO_FILLER:
        words.pop()
    subject = " ".join(words).strip(" .")
    return "" if (not subject or subject in _PHOTO_FILLER) else subject


def _photo_subject(low: str) -> str:
    """The thing a person wants a photograph OF, or "" when they said no such thing.

    Deliberately narrow: the word photo/photograph/picture must be present. A
    plain "make me an image of a dog" stays with the image generator; "real photo
    of an elephant" comes here, because a drawing is exactly what they rejected.
    """
    word = r"(?:photo|photograph|picture|pic|image)"
    if not re.search(rf"\b{word}\b", low):
        return ""
    if re.search(r"\b(make|create|generate|draw|design|render)\b", low) and \
            not re.search(r"\b(real|actual|true|genuine)\b", low):
        return ""                        # that is a generation request, not a search
    tail = r"\s+(?:please|now|machi|bro|da|for me)\b.*$"
    m = re.search(rf"\b(?:real|actual|genuine)?\s*{word}\s+(?:of|showing|about)\s+"
                  rf"(?:an?|the|my|our)?\s*([a-z][a-z' -]{{1,40}})", low)
    if m:
        return _tidy_subject(re.sub(tail, "", m.group(1)))
    m = re.search(rf"\b(?:real|actual|genuine)\s+{word}\s+(?:of\s+)?"
                  rf"(?:an?|the)?\s*([a-z][a-z' -]{{1,40}})", low)
    if m:
        return _tidy_subject(re.sub(tail, "", m.group(1)))
    m = re.search(rf"([a-z][a-z' -]{{1,40}}?)\s+{word}\b", low)
    if m:
        return _tidy_subject(re.sub(tail, "", m.group(1)))
    return ""


def respond(text: str) -> tuple[str, list[dict]]:
    """Return (spoken_reply, tool_calls). Reply may be empty if tools must run first."""
    t = (text or "").strip()
    low = t.lower()

    if not t:
        return ("I did not catch that.", [])

    # --- teaching comes before everything: "teach me ..." is unambiguous ---
    if re.match(r"^(teach(?: me)?(?: that)?|when(?:ever)? i say|remember that)\b", low):
        return ("", [_call("teach_macro", instruction=t)])

    # --- a macro the user taught me ("work mode") -------------------------
    try:
        from .. import macros as _macros
        if getattr(_macros, "load", None) and _macros.find(t):
            _lang = _lang_code(t)
            return (_lang_phrase("working", _lang), [_call("macros", action="run", name=t)])
    except Exception:
        pass

    # --- greetings / identity -------------------------------------------
    # anchored: "run command echo hi" must not be mistaken for a greeting
    if (re.match(r"^(hi|hii|hello|hey|vanakkam|namaskara)\b", low)
            and "jarvis" not in low and len(low) < 30):
        return ("JARVIS Lite online. Ask me to open an app, check the system, set a timer, "
                "or switch modes.", [])
    if "who are you" in low or "your name" in low or "nee yaaru" in low:
        return (f"I am {_who()}, the assistant inside Arc Desk. Right now I am running in Lite "
                "mode, which is offline and rule-based. Connect a brain to get full "
                "conversation.", [])

    # --- how the user is feeling: answered here, never sent to a model ----
    # Safety comes before routing. A model can talk itself out of offering help.
    if re.search(r"\b(kill myself|end my life|want to die|suicidal|suicide|self.?harm|"
                 r"hurt myself|better off dead|no reason to live)\b", low):
        return ("", [_call("coach", mode="listen", text=t)])
    if re.search(r"\b(i feel|i'?m feeling|feeling (low|sad|anxious|tired|alone|lonely)|"
                 r"i am (sad|depressed|anxious|exhausted|burnt out|burned out|lonely)|"
                 r"romba (tired|sad)|stress(ed)?|panic|overwhelmed|can.?t sleep)\b", low):
        return ("", [_call("coach", mode="listen", text=t)])

    # --- searching INSIDE documents ---------------------------------------
    # Before the general "find file" block: "which file mentions the invoice" is a
    # content question, and answering it with a filename search would be wrong.
    if re.search(r"\b(index|scan|search|look through)\b.{0,20}\b(documents?|files?|"
                 r"docs?|pdfs?|word files?|folder)\b.{0,20}\b(inside|content|text|words)\b", low) or \
            re.search(r"\bindex (my |the )?(documents?|papers?|notes?)\b|"
                      r"\bsearch (inside|within) (my|the)\b|"
                      r"\bscroll (through )?my documents\b", low):
        query = ""
        found = re.search(r"\bfor\s+(.+)$", t, re.I) or re.search(r"\babout\s+(.+)$", t, re.I)
        if found:
            query = found.group(1).strip(" .?")
        if re.search(r"\bocr\b", low):
            return ("", [_call("search_inside", action="ocr", roots="", query=query)])
        if re.search(r"\b(index|scan|rebuild)\b", low) and not query:
            return ("", [_call("search_inside", action="index", roots="")])
        return ("", [_call("search_inside", action="search", query=query)])
    if re.search(r"\b(which|what|whose)\b.{0,24}\b(file|document|doc|pdf|sheet|note)s?\b"
                 r".{0,20}\b(mention|mentions|talk about|talks about|say|says|contain|"
                 r"contains|has|have|reference|references)\b", low) or \
            re.search(r"\bwhere did i (write|note|mention)\b|"
                      r"\bwhere (have|did) i (written|written down|noted)\b|"
                      r"\bin which (file|document)\b", low):
        query = re.sub(r"^\s*(which|what|whose)\b", "", t, flags=re.I)
        query = re.sub(r"\b(file|files|document|documents|doc|pdf|sheet|note)s?\b", " ", query,
                       flags=re.I)
        query = re.sub(r"\b(mention|mentions|mentioning|talk about|talks about|talked about|"
                       r"say|says|said|contain|contains|containing|has|have|reference|"
                       r"references|with)\b", " ", query, flags=re.I)
        query = re.sub(r"\b(where did i|where have i|i|my|written|noted|write|note)\b", " ",
                       query, flags=re.I).strip(" .?,")
        query = re.sub(r"^(?:about|on|the|a|an)\s+", "", query, flags=re.I).strip()
        if query:
            return ("", [_call("search_inside", action="search", query=query)])

    # --- "idhu enna error da": read the error and name it ------------------
    # Deliberately above the general knowledge block: "what is this error" is a
    # diagnosis request, not a question for the facts library.
    if re.search(r"\b(what(?:'s| is)? (?:this|that|the) (?:error|exception|message|"
                 r"popup)|what does (?:this|that) (?:error )?mean|explain (?:this|that|the)"
                 r"(?: error)?|why (?:is|isn.?t|does|doesn.?t|didn.?t).{0,24}work(?:ing)?|"
                 r"why did (?:it|this) (?:fail|crash|stop))\b", low) or \
            re.search(r"\b(idhu|ithu|indha)\s+enna\s+(error|problem|issue)\b|"
                      r"\benna\s+(error|problem)\s*(da|machi)?\b|"
                      r"\b(yen|why)\s+(varudhu|aagudhu|aaguthu|varuthu)\b", low):
        where = "text"
        if re.search(r"\b(on (?:my |the )?screen|screen.?la|screen la)\b", low):
            where = "screen"
        elif re.search(r"\bcopied|clipboard\b", low):
            where = "clipboard"
        return ("", [_call("explain", text=t, where=where)])

    # --- playback: instant, and never a model round-trip ----------------
    if re.search(r"\b(stop|pause|unpause|resume|next|skip|previous)\b", low) and \
            re.search(r"\b(music|song|songs|video|movie|player|playback|paatu|padam|"
                      r"audio|track)\b", low):
        if re.search(r"\bstop\b", low):
            return ("", [_call("play", action="stop")])
        if re.search(r"\b(next|skip)\b", low):
            return ("", [_call("media", action="next")])
        if re.search(r"\b(previous|prev|back)\b", low):
            return ("", [_call("media", action="previous")])
        return ("", [_call("play", action="pause")])
    if re.search(r"\b(what.?s playing|what is playing|now playing|which song|"
                 r"what song is (this|playing))\b", low):
        return ("", [_call("play", action="status")])

    # "play <x>", "put on <x>", "song podu", "<x> play pannu"
    play_hit = (re.match(r"^\s*(?:arc[ ,]*)?(?:please\s+)?(?:play|put on|start playing)\b",
                         low)
                or re.search(r"\b(song|paatu|padal|music|video|padam)\s+(podu|podunga|"
                             r"kaattu|kelu)\b", low)
                or re.search(r"\bplay\s+pann?u\b", low))
    if play_hit and not re.search(r"\b(game|chess|cricket|match|video game)\b", low):
        kind = "video" if re.search(r"\b(video|movie|film|padam)\b", low) else "audio"
        if re.search(r"\b(any|some|random|something)\b", low) and \
                not re.search(r"\b(of|from|by)\b", low):
            query = ""
        else:
            query = re.sub(r"^\s*(?:arc[ ,]*)?(?:please\s+)?(?:play|put on|start playing)\s+",
                           "", t, flags=re.I)
            query = re.sub(r"\b(?:the\s+)?(?:song|paatu|padal|music|video|padam)\b\s*", " ",
                           query, flags=re.I)
            query = re.sub(r"\bplay\s+pann?u\b", " ", query, flags=re.I)
            query = re.sub(r"\b(podu|podunga|kaattu|kelu)\b", " ", query, flags=re.I)
            query = re.sub(r"\b(?:for me|please)\b", " ", query, flags=re.I)
        query = " ".join(query.split()).strip(" .?!")
        return ("", [_call("play", action="play", query=query, kind=kind)])

    # --- scanning: music, video, and external disks ---------------------
    if re.search(r"\b(scan|index|look through|check)\b", low) and re.search(
            r"\b(external|removable|usb|pen ?drive|flash ?drive|hard ?disk|hard ?drive|"
            r"drive|disk|music|songs|videos|movies|media|folder)\b", low) and not \
            re.search(r"\b(stack|packages|tools|mcp)\b", low):
        roots = ""
        drive = (re.search(r"\b([A-Za-z]):\\", t)
                 or re.search(r"\b([A-Za-z])\s+(?:drive|disk|hard ?disk)\b", t, re.I))
        quoted = _path_in(t)
        if drive:
            roots = f"{drive.group(1).upper()}:\\"
        elif quoted:
            roots = quoted
        return ("", [_call("library", action="scan", roots=roots)])
    if re.search(r"\b(which|what|list|show)\b.{0,12}\b(drives|disks|external)\b", low):
        return ("", [_call("library", action="drives")])
    if re.search(r"\b(what|which)\b.{0,16}\b(songs?|music|videos?|movies?)\b.{0,12}"
                 r"\b(have|indexed|scanned)\b|\bmy (music|songs|videos) library\b", low):
        return ("", [_call("library", action="search", query="")])
    # Scoped to MEDIA on purpose: this used to match "find my report" and send it to the
    # music library, which then honestly said it had no such song — a wrong answer to a
    # question that `find_file` could have answered. Caught by tests/test_vault.py.
    if re.search(r"\b(do i have|find my|search my)\b.{0,26}"
                 r"\b(songs?|tracks?|music|videos?|movies?|clips?|episodes?|albums?)\b", low):
        query = re.sub(r"\b(do i have|find my|search my|the|song|track|video|music|"
                       r"please|called|named|a|an)\b", " ", t, flags=re.I)
        return ("", [_call("library", action="search",
                           query=" ".join(query.split()).strip(" .?!"))])

    # --- think it through, then do it -----------------------------------
    if re.search(r"\b(help me decide|should i|should we|which is better|confused between|"
                 r"decide between)\b", low):
        return ("", [_call("coach", mode="decide", text=t)])
    if re.search(r"\b(mentor me|be my mentor|guide me|give me advice|advice on)\b", low):
        return ("", [_call("coach", mode="mentor", text=t)])
    if re.search(r"\b(give me a plan|7.?day plan|seven.?day plan|plan my|help me plan)\b",
                 low):
        return ("", [_call("coach", mode="plan", text=t)])
    if re.search(r"\b(check.?in with me|weekly check|reflect on my week)\b", low):
        return ("", [_call("coach", action="checkin")])
    if re.search(r"\b(how (am i|have i) (doing|been)|my mood (this|last) week|"
                 r"reflect on my week)\b", low):
        return ("", [_call("coach", action="reflection", text=t)])

    # --- exact numbers, units and markets -------------------------------
    # These must never reach a language model: a 0.5B model answers "18% of
    # 4500" with a confident wrong number, and `knows.py` answers it exactly.
    m = re.search(r"([\d.,]+)\s*(?:%|percent)\s*(?:of|on|for)\s*([\d.,]+)", low)
    if m:
        return ("", [_call("calc", expression=f"{m.group(1)}% of {m.group(2)}")])
    if re.match(r"^(what(?:'s| is)?\s+)?[\d.,]+\s*[-+*/x×÷^%]\s*[\d.,]+", low) \
            or re.match(r"^(calculate|compute|what is)\s+[\d.,(]", low):
        expr = re.sub(r"^(what(?:'s| is)?|calculate|compute)\s+", "", low).strip()
        expr = expr.replace("x", "*").replace("×", "*").replace("÷", "/")
        return ("", [_call("calc", expression=expr)])

    m = re.search(r"(?:convert\s+)?([\d.]+)\s*(km|kilometres?|kilometers?|miles?|mi|kg|kgs?"
                  r"|kilograms?|lb|lbs?|pounds?|metres?|meters?|m|ft|feet|inches?|cm|litres?"
                  r"|liters?|gallons?|c|f|celsius|fahrenheit)\s*(?:to|in|into)\s*"
                  r"(km|kilometres?|kilometers?|miles?|mi|kg|kgs?|kilograms?|lb|lbs?|pounds?"
                  r"|metres?|meters?|m|ft|feet|inches?|cm|litres?|liters?|gallons?|c|f"
                  r"|celsius|fahrenheit)\b", low)
    if m:
        return ("", [_call("convert", value=float(m.group(1)),
                           from_unit=m.group(2), to_unit=m.group(3))])

    if re.search(r"\b(nifty|sensex|bank ?nifty|market|share market|stock market)\b", low) \
            and re.search(r"\b(market|summary|how|eppadi|epdi|status|today)\b", low):
        return ("", [_call("market_summary")])
    # a bare number series is not a ticker — "forecast 120 140 155" is arithmetic
    _series = len(re.findall(r"\d+(?:\.\d+)?", low)) >= 4
    if not _series and re.search(r"\b(predict|forecast|target|trend)\b", low) \
            and re.search(r"\b(nifty|sensex|reliance|tcs|infy|stock|share|"
                          r"banknifty|bitcoin|gold|crude|[a-z]{3,12})\b", low):
        sym = re.search(r"\b(?:predict|forecast|target|trend)\s+(?:for\s+)?([a-z]{3,12})\b", low)
        return ("", [_call("project", symbol=(sym.group(1) if sym else "nifty"), days=7)])
    # forex first: "dollar rate" is a currency question, not a ticker
    if re.search(r"\b(exchange rate|dollar rate|rupee rate|usd|inr|forex)\b", low):
        return ("", [_call("rates", base="INR", symbols="USD,EUR")])
    if re.search(r"\b(price|quote|rate|value)\b", low) and \
            re.search(r"\b(nifty|sensex|bitcoin|btc|gold|silver|ethereum)\b", low):
        sym = re.search(r"\b(nifty|sensex|bitcoin|btc|gold|silver|ethereum)\b", low)
        return ("", [_call("stock", symbol=sym.group(1))])

    # --- the day layer: reminders, focus, briefing, file search ----------
    if re.search(r"\bremind\s+me\b", low) or (re.search(r"\breminder\b", low)
                                               and re.search(r"\b(add|set|new)\b", low)):
        return ("", [_call("remind", action="add", text=t)])

    if re.search(r"\b(my\s+)?reminders?\b", low) and re.search(
            r"\b(list|show|what|any|due|waiting)\b", low):
        return ("", [_call("remind", action="list")])

    if re.search(r"\b(cancel|delete|remove|drop)\b.{0,16}\breminder\b", low) \
            or re.search(r"\breminder\b.{0,16}\b(cancel|delete|remove)\b", low):
        return ("", [_call("remind", action="cancel", which=_quoteish(t))])

    if re.search(r"\b(stop|end|cancel)\b.{0,10}\bfocus\b", low):
        return ("", [_call("focus", action="stop")])

    if re.search(r"\bhow long\b.{0,16}\b(left|remaining)\b", low) \
            or re.search(r"\bfocus\b.{0,12}\b(left|status|remaining)\b", low):
        return ("", [_call("focus", action="status")])

    if re.search(r"\b(focus|pomodoro)\b", low) and re.search(
            r"\b(stats|total|week|history)\b", low):
        return ("", [_call("focus", action="stats")])

    if re.search(r"\b(focus|pomodoro|deep work)\b", low) and re.search(
            r"\b(start|begin|for|session|block)\b", low):
        mins = NUM.search(low)
        label = ""
        m = re.search(r"focus(?:ing)?\s+on\s+([a-z0-9 ,'\-]{3,40}?)"
                      r"(?:\s+for\b|\s+\d|$)", low)
        if m:
            candidate = m.group(1).strip(" ,.")
            if not re.search(r"\b(minutes?|mins?|hours?|hrs?|session|block)\b", candidate):
                label = candidate
        return ("", [_call("focus", action="start",
                           minutes=str(int(float(mins.group(1)))) if mins else "",
                           label=label)])


    # "type good morning" is typing practice, not a request for a briefing
    if not re.search(r"\b(type|write|say|note|draft|print|spell)\b", low) and \
            re.search(r"^\s*(good morning|good afternoon|good evening)|\b(brief me|"
                      r"briefing|morning brief)\b", low):
        return ("", [_call("briefing", what="full")])

    if re.search(r"\b(what.{0,8}(today|on today|is today)|today.{0,10}(schedule|plan))\b",
                 low):
        return ("", [_call("briefing", what="today")])

    if re.search(r"\b(find|search|locate|where is|where's)\b", low) and re.search(
            r"\b(file|files|folder|document|documents|pdf|photo|image|video|download|"
            r"invoice|note|resume|cv)\b", low):
        kind = ""
        for word in ("pdf", "word", "excel", "sheet", "image", "photo", "video",
                     "audio", "code", "text"):
            if re.search(rf"\b{word}\b", low):
                kind = word
                break
        query = t
        m = re.search(r"\b(?:find|search(?: for)?|locate|where is|where's)\b\s+"
                      r"(?:my\s+|the\s+|a\s+)?(.+)$", t, flags=re.I)
        if m:
            query = m.group(1)
            query = re.sub(r"\b(files?|folders?|documents?)\b", " ", query, flags=re.I)
            query = re.sub(r"\b(pdf|word|excel|image|photo|video|audio)\b", " ", query,
                           flags=re.I).strip(" ,.")
        return ("", [_call("find_file", query=query, kind=kind)])

    # "find my report" — no file noun, but the intent is unmistakable. Previously this
    # fell through to the generic "I only handle direct commands" answer, which is not
    # true: `find_file` can answer it. Media words are excluded above (that is `library`).
    m = re.search(r"^\s*(?:find|locate|search for)\s+my\s+(.+)$", t, flags=re.I)
    if m and not re.search(r"\b(songs?|tracks?|music|videos?|movies?|phone|keys?)\b", low):
        return ("", [_call("find_file", query=m.group(1).strip(" .?!"), kind="")])

    # --- the open-source catalogue --------------------------------------
    # Deliberately narrow: "packages"/"github"/"open source" as the subject, or a
    # role word next to "missing/installed". Otherwise the word "see" alone would
    # hijack "can you see my screen".
    _ROLES = (("brain", "brain"), ("ears", "ears"), ("mouth", "mouth"),
              ("wake", "wake"), ("recall", "recall"), ("glue", "glue"),
              ("ship", "ship"), ("flow", "flow"), ("vision", "see"), ("ocr", "see"))
    _subject = bool(re.search(r"\b(github|open[\s-]?source|packages?|repos?|stack)\b", low))
    _role = next((role for word, role in _ROLES
                  if re.search(rf"\b{word}\b", low)), "")
    _ask = re.search(r"\b(which|what|any|scan|check|missing|install|alternative|"
                     r"list|show|recommend|need|count|summary|how many|"
                     r"how do i)\b", low)
    _gap = re.search(r"\b(missing|not installed|absent|gap|gaps)\b", low)
    if (_subject and _ask) or (_role and (_gap or _subject)):
        if _gap:
            return ("", [_call("packages", action="plan", role=_role)])
        if re.search(r"\b(scan|installed|on my pc|detected)\b", low):
            return ("", [_call("packages", action="scan", role=_role)])
        if re.search(r"\b(how many|count|summary|all of them)\b", low):
            return ("", [_call("packages", action="all")])
        return ("", [_call("packages", action="search", query=t, role=_role)])

    # --- security: ask for the wrong thing, get the honest no -----------
    if re.search(r"\b(hack|hacking|crack|cracking|brute ?force|keylogger|"
                 r"steal (a )?password|break into|bypass (a )?(login|password)|"
                 r"hollow operations?|access anything|root (a |the )?(phone|router)|"
                 r"sniff (the )?(wifi|network))\b", low):
        return ("", [_call("secure", action="refused")])

    if re.search(r"\b(phishing|scam message|is this (email|message|link) (safe|real))\b",
                 low):
        return ("", [_call("secure", action="phishing", text=t)])

    if re.search(r"\b(password|passphrase)\b", low) and re.search(
            r"\b(strength|strong|weak|secure|entropy|check|good)\b", low):
        m = re.search(r"(?:password|passphrase)\s*(?:is|:)?\s*[\"']?([^\"']{3,})", t,
                      flags=re.I)
        return ("", [_call("secure", action="password",
                           text=(m.group(1).strip() if m else ""))])

    if re.search(r"\b(secure|harden|lock down)\b.{0,16}\b(pc|laptop|computer|"
                 r"machine|windows|system)\b", low) or re.search(
            r"\b(am i|is my (pc|laptop))\b.{0,12}\b(secure|safe|protected)\b", low):
        return ("", [_call("secure", action="machine")])

    if re.search(r"\b(recovery codes?|3-?2-?1|backup plan|two[- ]factor|2fa)\b", low) \
            and re.search(r"\b(plan|set ?up|how|advice|do i)\b", low):
        return ("", [_call("secure", action="recovery")])

    # --- the studio layer: content, marketing, strategy, hotels, travel -----
    if re.search(r"\b(hashtags?|tags)\b", low) and re.search(
            r"\b(for|about|on)\b", low):
        topic = re.split(r"\b(?:for|about|on)\b", t, maxsplit=1)[-1].strip()
        return ("", [_call("content", action="hashtags", topic=topic)])

    if re.search(r"\b(content|posting|editorial) calendar\b", low) or (
            re.search(r"\bcalendar\b", low) and re.search(r"\b(content|posts?|social)\b", low)):
        return ("", [_call("content", action="calendar", topic=t)])

    if re.search(r"\b(hooks?|opening lines?|first line)\b", low) and re.search(
            r"\b(write|give|make|suggest|need)\b", low):
        return ("", [_call("content", action="hooks", topic=t)])

    if re.search(r"\b(write|draft|compose|create)\b", low) and re.search(
            r"\b(blog|article|post|caption|reel|script|email|ad|advert|product "
            r"description|speech|promo|message|note)\b", low):
        kind = ("instagram" if re.search(r"\b(caption|insta|instagram)\b", low) else
                "reel" if re.search(r"\breel\b", low) else
                "youtube" if re.search(r"\byoutube\b", low) else
                "email" if re.search(r"\bemail\b", low) else
                "ad" if re.search(r"\b(ad|advert|advertisement)\b", low) else
                "product" if re.search(r"\bproduct description\b", low) else
                "speech" if re.search(r"\bspeech\b", low) else
                "whatsapp" if re.search(r"\bwhatsapp\b", low) else "blog")
        return ("", [_call("content", action="draft", kind=kind, topic=t)])

    if re.search(r"\butm\b", low):
        link = re.search(r"(https?://\S+|[\w.-]+\.[a-z]{2,}(?:/\S*)?)", t, flags=re.I)
        return ("", [_call("marketing", action="utm",
                           url=(link.group(1) if link else ""))])

    if re.search(r"\b(funnel|conversion rate|roas|cac|cpl|ctr)\b", low):
        nums = [float(x) for x in NUM.findall(low)]
        keys = ["impressions", "clicks", "leads", "sales", "spend", "revenue"]
        return ("", [_call("marketing", action="funnel",
                           **dict(zip(keys, nums)))])

    if re.search(r"\bseo\b|\breadability\b", low):
        return ("", [_call("marketing", action="seo", text=t)])

    if re.search(r"\b(a/?b|split) test\b|\bsample size\b", low):
        return ("", [_call("marketing", action="sample")])

    if re.search(r"\bmarketing plan\b|\bpromote\b|\bget (more )?(customers|sales|"
                 r"bookings|traffic)\b", low):
        return ("", [_call("marketing", action="plan", business=t)])

    if re.search(r"\bswot\b", low):
        subject = re.sub(r"\b(swot|for|about|of|my|the|do|a)\b", " ", t, flags=re.I)
        return ("", [_call("strategy", action="swot",
                           subject=" ".join(subject.split()) or t)])

    if re.search(r"\b(five forces|porters?|porter's)\b", low):
        return ("", [_call("strategy", action="forces", subject=t)])

    if re.search(r"\b(business model|canvas|bmc)\b", low):
        return ("", [_call("strategy", action="bmc", subject=t)])

    if re.search(r"\bokrs?\b", low):
        return ("", [_call("strategy", action="okr", subject=t)])

    if re.search(r"\bbreak[- ]?even\b", low):
        nums = [float(x) for x in NUM.findall(low.replace(",", ""))]
        keys = ["fixed", "price", "variable"]
        return ("", [_call("strategy", action="break", **dict(zip(keys, nums)))])

    if re.search(r"\b(unit economics|ltv|cac ratio|margin per (unit|sale))\b", low):
        nums = [float(x) for x in NUM.findall(low.replace(",", ""))]
        keys = ["price", "cogs", "cac", "repeat"]
        return ("", [_call("strategy", action="unit", **dict(zip(keys, nums)))])

    if re.search(r"\b(occupancy|revpar|adr|goppar|trevpar)\b", low):
        nums = [float(x) for x in NUM.findall(low.replace(",", ""))]
        keys = ["rooms", "sold", "room_revenue", "other_revenue", "costs"]
        args = {k: (int(v) if k in ("rooms", "sold") else v)
                for k, v in zip(keys, nums)}
        return ("", [_call("hotel", action="kpi", **args)])

    if re.search(r"\b(food cost|menu cost|recipe cost|dish cost)\b", low):
        return ("", [_call("hotel", action="menu", items=t)])

    if re.search(r"\b(housekeeping|front ?desk|checklist|sop)\b", low) and re.search(
            r"\b(hotel|room|staff|checklist|sop|procedure)\b", low):
        dep = ("frontdesk" if re.search(r"\bfront ?desk\b", low) else
               "fnb" if re.search(r"\b(f&b|restaurant|kitchen)\b", low) else
               "maintenance" if re.search(r"\b(maintenance|repair)\b", low)
               else "housekeeping")
        return ("", [_call("hotel", action="sop", department=dep)])

    if re.search(r"\b(map of|show .{0,12}on (a )?map|location of|coordinates)\b", low):
        place = re.sub(r"\b(map of|show|on a map|on the map|location of|coordinates|"
                       r"where is|please)\b", " ", t, flags=re.I).strip(" ,?.")
        return ("", [_call("travel", action="map", place=place or t)])

    if re.search(r"\b(distance|how far)\b", low) and re.search(r"\bfrom\b|\bto\b", low):
        m = re.search(r"from\s+(.+?)\s+to\s+(.+)$", t, flags=re.I)
        a, b = (m.group(1), m.group(2)) if m else (t, "")
        return ("", [_call("travel", action="distance", place=a.strip(), near=b.strip())])

    if re.search(r"\b(itinerary|day plan|trip plan|plan a trip|days? in|"
                 r"\dtrip to|\sday trip|trip to)\b", low):
        m = NUM.search(low)
        place = re.sub(r"\b(plan|a|an|the|day|days|trip|itinerary|to|for|of|"
                       r"\d+|please)\b", " ", t, flags=re.I)
        place = " ".join(place.split()) or t
        return ("", [_call("travel", action="itinerary", place=place,
                           days=int(float(m.group(1))) if m else 3)])

    if re.search(r"\b(where should i (go|travel|visit)|travel ideas?|"
                 r"places to visit|trip ideas?)\b", low):
        tag = next((w for w in ("beach", "hills", "heritage", "wildlife", "temple",
                                "waterfall", "trek", "island", "desert", "pilgrimage")
                    if re.search(rf"\b{w}", low)), "")
        return ("", [_call("travel", action="ideas", tag=tag)])

    if re.search(r"\b(near me|nearby|what.{0,10}near|around)\b", low) and re.search(
            r"\b(place|places|visit|see|eat|stay|temple|beach|fort)\b", low):
        return ("", [_call("travel", action="near", place=t)])

    if re.search(r"\b(trip|travel|holiday) (budget|cost)\b|\bhow much .{0,14}trip\b",
                 low):
        nums = [float(x) for x in NUM.findall(low)]
        return ("", [_call("travel", action="budget",
                           days=int(nums[0]) if nums else 3)])

    if re.search(r"\b(palette|colou?r scheme|colou?rs that match)\b", low):
        hexes = re.findall(r"#[0-9a-f]{3,6}", low)
        return ("", [_call("craft", action="palette", base=hexes[0] if hexes else "#48f2ff")])

    if re.search(r"\b(kolam|rangoli|muggu)\b", low):
        return ("", [_call("craft", action="kolam", base="#f4d06f")])

    if re.search(r"\b(poster|flyer|banner)\b", low) and re.search(
            r"\b(make|create|design|draw|generate)\b", low):
        return ("", [_call("craft", action="poster", title=t)])

    if re.search(r"\b(logo|monogram|brand mark)\b", low) and re.search(
            r"\b(make|design|create|generate|need)\b", low):
        return ("", [_call("craft", action="monogram", name=t)])

    if re.search(r"\b(csv|xlsx?|spreadsheet|dataset)\b", low) and re.search(
            r"\b(analy[sz]e|profile|mine|correlat|outlier|trend|summari[sz]e|report)\b",
            low):
        path = _path_in(t) or ""
        act = ("correlate" if "correlat" in low else
               "outliers" if "outlier" in low else
               "trend" if "trend" in low else "report")
        return ("", [_call("mine", action=act, path=str(path))])

    if re.search(r"\b(scamper|six (thinking )?hats|pre-?mortem|five whys|"
                 r"first principles|second.order|lateral thinking|brainstorm|"
                 r"mentor me|think (better|deeper))\b", low):
        act = ("scamper" if "scamper" in low else
               "six_hats" if "hat" in low else
               "pre_mortem" if "mortem" in low else
               "five_whys" if "whys" in low else
               "first_principles" if "first principle" in low else
               "second_order" if "second" in low else "questions")
        return ("", [_call("mentor", action=act, subject=t)])

    _nums = re.findall(r"\d+(?:\.\d+)?", t)
    if re.search(r"\b(forecast|projection|extrapolat)\b", low) or (
            re.search(r"\btrend\b", low) and len(_nums) >= 3):
        return ("", [_call("foresight", action="forecast", values=" ".join(_nums))])

    if re.search(r"\b(predict|what will happen|future of|scenarios?|"
                 r"going to happen|what happens (next|in)|should i expect)\b", low):
        return ("", [_call("foresight", action="scenario", question=t)])

    if re.search(r"\b(what.{0,8}(happened|is happening|is going on)|latest news|"
                 r"current affairs|today.{0,8}news)\b", low):
        return ("", [_call("foresight", action="unknown", question=t)])

    # --- the library: what ARC actually knows --------------------------
    if (re.match(r"^(fetch|look ?up|wikipedia|wiki)\b", low)
            or re.search(r"\b(fetch|look ?up|wikipedia|wiki)\b.{0,12}\b(about|on|for|who|what)\b", low)) \
            and not re.search(r"\b(my|our|file|folder)\b", low):
        topic = re.sub(r"\b(fetch|look ?up|wikipedia|wiki|about|on|for|please)\b",
                       " ", t, flags=re.I)
        topic = " ".join(topic.split()).strip(" ?.!")
        if topic:
            return ("", [_call("facts", action="fetch", topic=topic)])

    if re.search(r"\b(index|add|import|learn)\b.{0,24}\b(folder|library|notes|files?)\b",
                 low):
        path = _path_in(t) or ""
        return ("", [_call("facts", action="ingest", path=str(path))])

    if re.search(r"\bwhat do you know\b", low):
        about = re.sub(r"^.*?\bwhat do you know\b\s*(about|of)?\s*", "", t,
                       flags=re.I).strip()
        if not about or about.lower() in ("you know", "you", "everything", "all"):
            return ("", [_call("facts", action="coverage")])
        if about.lower() in ("india", "world", "science", "tech", "money", "health",
                             "food", "myths"):
            return ("", [_call("facts", action="domain", domain=about.lower())])
        return ("", [_call("facts", action="ask", question=about)])

    if re.search(r"\btell me a (random )?fact\b|\bsurprise me\b", low):
        return ("", [_call("facts", action="random")])

    # generic "what is / who is / how many" — only if nothing specific matched above
    if re.search(r"\b(what is|what are|whats|who is|who was|who won|who's|when did|"
                 r"where is|how tall|how many|how long is|define|meaning of|"
                 r"tell me about|which is bigger)\b", low) and not \
            (re.search(r"\b(my|screen|clipboard|cpu|ram|memory|disk|battery|weather|"
                       r"time|date|file|error|window|this|that|it)\b", low) or
             re.search(r"\.(?:pdf|docx?|xlsx?|pptx?|txt|csv|png|jpe?g|mp[34]|wav|mkv|zip)\b",
                       low)):
        q = re.sub(r"^\s*(hey |ok |arc |please )+", "", t, flags=re.I)
        return ("", [_call("facts", action="ask", question=q)])

    # --- the hologram deck ----------------------------------------------
    if re.search(r"\b(hologram|holographic|holo deck|holodeck|server view|"
                 r"projector)\b", low):
        if re.search(r"\b(close|hide|exit|stop|off)\b", low):
            return ("", [_call("holo", action="close")])
        return ("", [_call("holo", action="show")])

    # --- the studio: real video, audio and image work --------------------
    _files = _paths_in(t)
    if _files and re.search(r"\b(reel|short|status video|story video|teaser|slideshow|"
                            r"montage|vlog|movie)\b", low):
        template = ("story" if re.search(r"\bstory|status\b", low) else
                    "cinematic_teaser" if "teaser" in low else
                    "slideshow" if re.search(r"slideshow|montage|photos?\b", low) else
                    "travel_vlog" if "vlog" in low else "reel_hook")
        title = ""
        found = re.search(r"(?:titled|called|with the title|title)\s+[\"']?([^\"']{2,80})",
                          t, re.I)
        if found:
            title = found.group(1).strip(" .")
        return ("", [_call("video_studio", action="template",
                           clips="|".join(_files), template=template, title=title)])

    if _files and re.search(r"\b(cinematic|teal|noir|vintage|cyberpunk|vhs|dream|grain|"
                            r"vignette|slowmo|grade|graded|colour grade|color grade)\b", low):
        look = next((name for name in ("teal_orange", "cinematic", "noir", "vintage",
                                       "cyberpunk", "vhs", "dream", "grain", "vignette",
                                       "slowmo")
                     if re.search(name.split("_")[0], low)), "cinematic")
        if "grade" in low and not re.search(r"\b(cinematic|noir|vintage|cyberpunk|vhs)\b",
                                            low):
            look = "cinematic"
        if _files[0].lower().endswith((".mp4", ".mov", ".mkv", ".avi", ".webm", ".gif")):
            return ("", [_call("video_studio", action="look", path=_files[0], look=look)])
        return ("", [_call("image_studio", action="look", path=_files[0], look=look)])

    if _files and re.search(r"\b(denoise|noise|hiss|clean (up )?(the )?audio|background "
                            r"noise|hummy?)\b", low):
        return ("", [_call("audio_studio", action="denoise", path=_files[0])])
    if _files and re.search(r"\b(louder|loudness|normalise|normalize|lufs|podcast loud|"
                            r"instagram loud)\b", low):
        target = -16.0 if "podcast" in low else -14.0
        return ("", [_call("audio_studio", action="loudnorm", path=_files[0],
                           target_lufs=target)])
    if len(_files) >= 2 and re.search(r"\b(mix|mixing|blend|duck|under the voice)\b", low):
        return ("", [_call("audio_studio", action="mix", clips="|".join(_files[:2]),
                           gains="-3,-16", duck="duck" in low or "under" in low)])
    if _files and re.search(r"\b(waveform|waveform image|audio visual)\b", low):
        return ("", [_call("audio_studio", action="waveform", path=_files[0])])
    if _files and re.search(r"\b(chapters?|where does (the )?speech|timecodes?)\b", low):
        return ("", [_call("audio_studio", action="chapters", path=_files[0])])
    if _files and re.search(r"\b(instagram|insta) (post|square)\b", low):
        return ("", [_call("image_studio", action="card", path=_files[0],
                           template="instagram_post")])
    if _files and re.search(r"\b(instagram )?story (card|image|cover)|status image\b", low):
        return ("", [_call("image_studio", action="card", path=_files[0],
                           template="instagram_story")])
    if _files and re.search(r"\b(youtube )?(thumbnail|thumb)\b", low):
        return ("", [_call("image_studio", action="card", path=_files[0],
                           template="youtube_thumb")])
    if _files and re.search(r"\b(collage|grid|contact sheet|mood ?board)\b", low):
        cols = 3 if len(_files) > 4 else 2
        rows = max(1, (len(_files) + cols - 1) // cols)
        return ("", [_call("image_studio", action="collage", images="|".join(_files),
                           cols=cols, rows=rows)])
    if re.search(r"\b(studio|catalog|templates?|transitions?|transitions|looks?|effects?|"
                 r"filters?|presets?)\b", low) and re.search(
                     r"\b(what|show|list|which|available)\b", low):
        kind = ("video" if re.search(r"\b(video|transition)\b", low) else
                "audio" if re.search(r"\b(audio|sound|effect)\b", low) else "image")
        return ("", [_call("image_studio", action="catalog")] if kind == "image"
                 else [_call("video_studio", action="catalog")] if kind == "video"
                 else [_call("audio_studio", action="catalog")])

    # --- files: any format, read / review / edit -------------------------
    # A filename in the sentence is the strongest signal there is, so it is checked
    # before verbs like "read", which otherwise mean "read the screen".
    doc_path = _path_in(t)
    if doc_path:
        if re.search(r"\b(review|evaluate|critique|what.{0,12}missing|improve|feedback)\b", low):
            return ("", [_call("read_file", path=doc_path, mode="review")])
        if re.search(r"\b(outline|contents|structure|sections|table of contents)\b", low):
            return ("", [_call("read_file", path=doc_path, mode="outline")])
        if re.search(r"\b(edit|resize|crop|rotate|trim|convert|gif|greyscale|grayscale|"
                     r"compress|thumbnail|watermark|subtitles|extract|split|merge)\b", low):
            return ("", [_call("edit_file", path=doc_path, op=_edit_op(low),
                               **_edit_args(low))])
        if re.search(r"\b(read|open|summar\w*|what.{0,12}(in|inside)|tell me about|"
                     r"explain)\b", low):
            return ("", [_call("read_file", path=doc_path, mode="summary")])

    # --- make an image or a clip ----------------------------------------
    m = re.search(r"\b(?:make|create|generate|render|draw)\s+(?:me\s+)?(?:an?\s+)?"
                  r"(video|clip|animation|gif|image|picture|poster|wallpaper)\b"
                  r"(?:\s+(?:of|for|about|showing|with))?\s*(.*)", t, re.I)
    if m:
        kind = "video" if m.group(1).lower() in ("video", "clip", "animation") else "image"
        prompt = (m.group(2) or "").strip(" .") or t
        return ("", [_call("make_media", prompt=prompt, kind=kind)])

    # --- health: never a diagnosis, never a dose -------------------------
    if re.search(r"\b(first aid|cpr|choking|burn|bleeding heavily)\b", low):
        return ("", [_call("health", what="first_aid", query=low)])
    if re.search(r"\b(medicine|tablet|drug|dose|dosage|medication|mg)\b", low) or \
            (_known_drug(low) and re.search(r"\b(how|when|can|is|safe|take|many|much|works?|"
                                            r"side effects?)\b", low)):
        return ("", [_call("health", what="medicine", query=_drug_in(low), question=t)])
    if re.search(r"\b(anatomy|body part|organ|kidney|liver|heart|lungs?|stomach|brain|"
                 r"joints?|skin)\b", low) and re.search(r"\b(how|what|why|work|explain|"
                                                         r"function)\b", low):
        return ("", [_call("health", what="anatomy", query=low)])
    if re.search(r"\b(symptom|symptoms|i have|i am having|i'm having|feeling|it hurts|"
                 r"pain|ache|fever|headache|nausea|vomit|cough|rash|cramp|swelling)\b", low):
        return ("", [_call("health", what="triage", query=t)])

    # --- market depth: measurements, not predictions ---------------------
    m = re.match(r"^watch\s+([a-z0-9 &.^\-]{2,18})$", low)
    if m:
        return ("", [_call("market", what="watch", action="add", symbol=m.group(1).strip())])
    if re.search(r"\bwatchlist\b", low):
        return ("", [_call("market", what="watch", action="list")])
    m = re.search(r"\b(?:analyse|analyze|should i buy|should i sell|buy or sell|"
                  r"what about)\s+(?:of\s+)?([a-z][a-z0-9 &.^\-]{1,18})\b", low)
    if m and not re.search(r"\b(market|news|today|nifty)\b.{0,6}$", low):
        return ("", [_call("market", what="analyse", symbol=m.group(1).strip())])
    m = re.search(r"\b(?:position size|how many shares|sizing|risk)\b.*?(\d[\d,]{2,})", low)
    if m:
        cap = float(m.group(1).replace(",", ""))
        risk = _num(low.split(m.group(1))[-1], 1.0)
        return ("", [_call("market", what="plan", symbol=_symbol_in(low),
                           capital=cap, risk_pct=risk)])

    # --- backup and start-with-windows ------------------------------------
    if re.search(r"\bstart(ing)? with (windows|my account|login|the pc)\b|"
                 r"\b(open|launch) (arc )?(at|on) (login|startup|boot)\b|"
                 r"\bautostart\b", low):
        off = re.search(r"\b(off|stop|don.?t|disable|remove|no)\b", low)
        return ("", [_call("autostart", action="off" if off else "on")])
    if re.search(r"\b(back ?up|backup|copy my (files|photos|documents|pictures|work))\b", low):
        where = ""
        found = re.search(r"\b(?:to|onto|into)\s+([a-z]:\\[^\s]*|/[^\s]+)", t, re.I)
        if found:
            where = found.group(1)
        elif re.search(r"\b(external|pen ?drive|hard ?disk|usb)\b", low):
            where = ""
        if re.search(r"\b(drive list|which disks|where can i)\b", low):
            return ("", [_call("backup", action="drives")])
        source = _backup_source(low, t)
        if re.search(r"\bverify|check the (backup|copy)\b", low):
            return ("", [_call("backup", action="verify",
                               target=where or (_path_in(t) if _path_in(t) != source else ""))])
        if re.search(r"\bplan|preview|how (much|big)|what would\b", low):
            return ("", [_call("backup", action="plan", source=source, target=where)])
        return ("", [_call("backup", action="copy", source=source, target=where)])

    # --- why is this machine slow ----------------------------------------
    if re.search(r"\b(why|y is|yen)\b.{0,18}\b(slow|sluggish|laggy|lagging|freez\w*|"
                 r"hang\w*)\b", low) or \
            re.search(r"\b(slow|laggy|sluggish)\b.{0,14}\b(pc|laptop|computer|machine|"
                      r"system|windows)\b", low) or \
            re.search(r"\b(pc|laptop|computer|machine|windows)\b.{0,16}\b(slow|laggy|"
                      r"sluggish|freezing)\b", low) or \
            re.search(r"\b(yen|why)\s+(slow|aaguthu|aagudhu|varudhu|irukku)\b", low) or \
            re.search(r"\bcool-?a irukku\b|\bheat aaguthu\b", low) or \
            re.search(r"\b(heating up|getting hot|too hot|overheat\w*|fan (is )?(loud|"
                      r"running|spinning)|temperature)\b", low):
        if re.search(r"\bstartup|start up|boot\b", low):
            return ("", [_call("pc_health", action="startup")])
        return ("", [_call("pc_health", action="scan", text=t)])
    if re.search(r"\b(startup items|startup apps|what starts at (login|boot)|"
                 r"autostart list)\b", low):
        return ("", [_call("pc_health", action="startup")])
    if re.search(r"\bpc health\b|\bpc check\b|\bcheck (my|the) (pc|laptop|computer|system)\b|"
                 r"\bis my (pc|laptop|computer) (ok|okay|fine)\b|"
                 r"\bhow is my pc\b|\bhealth check\b", low):
        return ("", [_call("pc_health",
                           action="quick" if re.search(r"\bquick\b", low) else "scan",
                           text=t)])

    # --- the Vault: where work is saved ---------------------------------
    # Placed above the system block on purpose: "save my work to the desktop" contains
    # the word "desktop", and the system block would otherwise answer a different
    # question. Both word orders are covered.
    # "where do my files save?" / "where is my vault?" — but NOT "where is report.pdf",
    # which is a file search. Hence the guard on find/search/a filename-ish token.
    if re.search(r"\bwhere\b", low) and re.search(
            r"\b(vault|work|workspace|files?|notes?|progress|stored|saved|save|kept)\b", low) \
            and not re.search(r"\b(export|copy out|take out|find|search)\b", low) \
            and not re.search(r"\.[a-z]{2,4}\b", low):
        m = re.search(r"(?:project|work on|working on)\s+(?:called\s+|named\s+)?(.+)$", t, re.I)
        if m:
            return ("", [_call("vault", action="resume", project=m.group(1).strip())])
        return ("", [_call("vault", action="where")])

    if re.search(r"\b(start|create|new|begin|open)\b.{0,12}\bproject\b", low):
        m = re.search(r"\bproject\b\s*(?:called|named|for|about)?\s*(.+)$", t, re.I)
        name = (m.group(1).strip() if m else "").strip(" .")
        if name:
            return ("", [_call("vault", action="create", project=name)])
        return ("", [_call("vault", action="list")])

    if re.search(r"\b(save|note down|remember|log)\b", low) and re.search(
            r"\b(this|that|it|my work|my progress|note|update)\b", low):
        said = re.sub(r"^\W*(save|note|remember|log)( this| that| it)?[\s,:-]*", "",
                      t, flags=re.I).strip()
        return ("", [_call("vault", action="save", text=said or t)])

    if re.search(r"\b(export|copy out|take out|send out)\b", low) and re.search(
            r"\b(project|work|vault|it|this)\b", low):
        dest = ""
        for word in ("desktop", "documents", "downloads", "pictures"):
            if word in low:
                dest = word
                break
        m = re.search(r"\b(?:to|into|onto)\s+([a-z]:\\[^\s]+|/[^\s]+)", t, re.I)
        if m:
            dest = m.group(1)
        proj = ""
        pm = re.search(r"\bproject\s+(?:called\s+|named\s+)?([\w .-]+?)\s+(?:to|into)\b",
                       t, re.I)
        if pm:
            proj = pm.group(1).strip()
        return ("", [_call("vault", action="export", project=proj, dest=dest)])

    if re.search(r"\b(add|attach|import|copy)\b", low) and re.search(
            r"\b(project|vault|this work)\b", low):
        m = re.search(r"([a-z]:\\[^\s]+|~[/\\][^\s]+|/[^\s]+)", t, re.I)
        if m:
            return ("", [_call("vault", action="add", path=m.group(1))])

    if re.search(r"\b(resume|continue where|where was i|what was i doing)\b", low):
        m = re.search(r"\bproject\s+(?:called\s+|named\s+)?(.+)$", t, re.I)
        return ("", [_call("vault", action="resume",
                           project=(m.group(1).strip() if m else ""))])

    if re.search(r"\b(my projects|list projects|all projects|vault)\b", low) and \
            not re.search(r"\b(where|delete|remove)\b", low):
        return ("", [_call("vault", action="list")])

    # --- system ---------------------------------------------------------
    # "what is eating my ram" is a question about *processes*, not a summary —
    # asking for the heavier list first is what the user meant.
    if re.search(r"\b(using|eating|hogging|taking)\b.{0,14}\b(ram|memory|cpu)\b", low) \
            or re.search(r"\b(running|processes|apps running|heavy|top)\b", low):
        return ("", [_call("running_apps")])
    if re.search(r"\b(cpu|ram|memory|system|status|performance|speed|slow)\b", low):
        return ("", [_call("system_report")])

    # --- time -----------------------------------------------------------
    if re.search(r"\b(time|date|what day|clock)\b", low):
        return ("", [_call("time")])

    # --- magic mode (say hi / bye to ARC) --------------------------------
    if re.search(r"\b(bye|goodbye|exit|leave)\b.{0,12}\bjarvis\b", low) or \
            re.search(r"\b(normal mode|back to normal|stop magic|magic off|exit magic)\b", low):
        return ("", [_call("magic", action="off")])
    if re.search(r"\b(hey|hi|hello)\b.{0,12}\bjarvis\b", low) or \
            re.search(r"\b(magic mode|magic on|transform|start magic)\b", low):
        return ("", [_call("magic", action="on")])

    # --- charms ---------------------------------------------------------
    if re.search(r"\bcharms?\b|\bfloating objects?\b", low):
        if re.search(r"\b(hide|off|stop|remove)\b", low):
            return ("", [_call("charms", action="hide")])
        if re.search(r"\b(edit|move|resize|arrange)\b", low):
            return ("", [_call("charms", action="edit")])
        return ("", [_call("charms", action="show")])

    # --- arc modes ------------------------------------------------------
    for word, mode in MODE_WORDS.items():
        if re.search(rf"\b{word}\b", low) and re.search(r"\b(mode|switch|set|go)\b", low):
            return ("", [_call("arc_mode", mode=mode)])
    if "mode" in low and re.search(r"\b(switch|change|next)\b", low):
        return ("Tell me which mode: focus, chill, gaming or night.", [])

    # --- power ----------------------------------------------------------
    if re.search(r"\b(shut ?down|power off)\b", low):
        return ("", [_call("power", action="shutdown")])
    if re.search(r"\b(restart|reboot)\b", low):
        return ("", [_call("power", action="restart")])
    if re.search(r"\b(sleep|suspend)\b", low):
        return ("", [_call("power", action="sleep")])
    if re.search(r"\b(cancel|abort)\b.*\b(shutdown|restart)\b", low):
        return ("", [_call("power", action="cancel")])
    if re.search(r"\block\b", low):
        return ("", [_call("lock_screen")])

    # --- volume / media --------------------------------------------------
    if "mute" in low:
        return ("", [_call("mute", mute=True)])
    if re.search(r"\bvolume\b", low):
        return ("", [_call("set_volume", level=int(_num(low, 50)))])
    if re.search(r"\b(pause|play|resume|next song|previous song|skip)\b", low):
        act = ("next" if "next" in low or "skip" in low else
               "previous" if "previous" in low else "play_pause")
        return ("", [_call("media", action=act)])

    if re.search(r"\bbrightness\b", low):
        return ("", [_call("brightness", level=int(_num(low, 60)))])
    if re.search(r"\b(screenshot|screen shot|capture)\b", low):
        return ("", [_call("screenshot")])

    # --- closing apps ---------------------------------------------------
    m = re.match(r"^(?:close|kill|quit|exit|stop)\s+(?!magic|jarvis)([\w .\-]{2,30})$", low)
    if m:
        return ("", [_call("close_app", app=m.group(1).strip())])

    # --- eyes ------------------------------------------------------------
    if re.search(r"\b((what(?:'s| is)? (?:on|in))|read|scan|look at)\b.{0,14}screen\b", low) or \
            re.search(r"\bwhat does (it|this|the screen) say\b", low):
        return ("", [_call("screen_text")])

    m = re.match(r"^click\s+(?:on\s+)?(?:the\s+)?(.{1,60}?)(?:\s+button)?$", low)
    if m and not re.search(r"\b(mouse|here|there)\b", m.group(1)):
        return ("", [_call("click_text", text=m.group(1).strip())])

    # --- people ----------------------------------------------------------
    m = re.match(r"^(?:whats? ?app|wa)\s+(\+?[\d ]{8,18})\s*(?:saying|:\s*)?(.{0,200})$", low)
    if m:
        return ("", [_call("whatsapp_send", number=m.group(1).strip(),
                           message=m.group(2).strip() or "hi")])

    m = re.match(r"^(?:send\s+)?(?:an?\s+)?e-?mail\s+(?:to\s+)?([\w.+-]+@[\w.-]+)"
                 r"\s*(?:about|saying|regarding)?\s*(.{0,200})$", low)
    if m:
        subject = m.group(2).strip() or "hello"
        return ("", [_call("email_send", to=m.group(1).strip(), subject=subject[:80],
                           body=subject)])

    m = re.match(r"^(?:e-?mail|mail)\s+([\w.+-]+@[\w.-]+)", low)
    if m:
        return (f"Opening a draft to {m.group(1)} — no password needed.",
                [_call("email_draft", to=m.group(1).strip())])

    # --- calendar ---------------------------------------------------------
    if re.search(r"\b(calendar|schedule|agenda|meetings?)\b", low) and \
            not re.search(r"\b(add|create|schedule|book|set up|new)\b", low):
        return ("", [_call("calendar", action="list", days=7)])

    if re.search(r"\b(add|create|schedule|book|set up|new)\b", low) and \
            (re.search(r"\b(calendar|event|meeting|appointment)\b", low) or
             re.search(r"\b(tomorrow|tonight|\d{1,2}(?::\d{2})?\s?(?:am|pm))\b", low)):
        when, span = _cal_when(low)
        if when:
            title = _cal_title(low, span)
            return ("", [_call("calendar", action="add", title=title or "event", when=when)])

    # --- doing things on the desktop ------------------------------------
    # "open notepad and type hello" is one sentence and two actions.
    m = re.match(r"^open\s+([\w .\-]{2,30}?)\s+and\s+(?:type|write|enter)\s+(.+)$", low)
    if m:
        return ("", [_call("open_app", app=m.group(1).strip()),
                     _call("type_text", text=m.group(2).strip(), delay=1.5)])

    if re.search(r"\b(what'?s open|which windows|list windows|open windows|window list)\b", low) \
            or re.search(r"\b(list|show)\b.{0,12}\bwindows\b", low):
        return ("", [_call("windows", action="list")])

    m = re.search(r"\b(?:switch|focus|go)\s+to\s+(?:the\s+)?([\w .\-]{2,40})$", low)
    if m and m.group(1).strip().lower() not in SITES:
        return ("", [_call("windows", action="focus", title=m.group(1).strip())])

    if re.search(r"\bminimi[sz]e\s+(?:everything|all|all windows|the desktop)\b", low):
        return ("", [_call("windows", action="minimize_all")])

    m = re.match(r"^type\s+(.{1,400})$", low)
    if m:
        return ("", [_call("type_text", text=m.group(1).strip())])

    m = re.match(r"^(?:press|hit|send)\s+([\w+ .\-]{2,24})$", low)
    if m and not re.search(r"\b(it|that|this)\b", m.group(1)):
        return ("", [_call("press", keys=m.group(1).strip())])

    m = re.match(r"^(?:make|create)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+"
                 r"(?:called\s+|named\s+)?(.+)$", low)
    if m:
        return ("", [_call("file_op", action="mkdir", path=m.group(1).strip())])

    m = re.match(r"^(?:write|save)\s+(.+?)\s+(?:in)?to\s+(?:the\s+)?(?:file\s+)?(.+)$", low)
    if m:
        return ("", [_call("file_op", action="write", path=m.group(2).strip(),
                           text=m.group(1).strip())])

    m = re.match(r"^(?:read|show me)\s+(?:the\s+)?file\s+(.+)$", low)
    if m:
        return ("", [_call("read_file", path=m.group(1).strip())])

    m = re.match(r"^delete\s+(?:the\s+)?file\s+(.+)$", low)
    if m:
        return ("", [_call("file_delete", path=m.group(1).strip())])

    m = re.match(r"^(?:run command|run in (?:the )?shell|shell)\s+(.+)$", low)
    if m:
        return ("", [_call("run_command", command=m.group(1).strip())])

    if re.search(r"\bwhat (?:have|did) you (?:do|done|just do)\b|\baction log\b", low):
        return ("", [_call("action_log")])

    # --- real photographs ------------------------------------------------
    # "draw an elephant" gets a sketch; "a REAL elephant" gets a photograph
    # somebody actually took, with its photographer and licence. No model, no GPU.
    wanted_photo = _photo_subject(low)
    if wanted_photo:
        # "aane photo" / "haathi photo": the drawing engine already knows the
        # Tamil/Hindi names, so reuse that table instead of searching Commons
        # for a word it does not index.
        from .. import art as _art
        words = wanted_photo.split()
        for i, w in enumerate(words):
            if w in _art.ALIAS:
                words[i] = _art.ALIAS[w]
                break
        return ("", [_call("photo", query=" ".join(words))])

    # --- drawing --------------------------------------------------------
    # "draw an elephant" works with no model at all: the vector engine is local.
    m = re.search(r"\b(draw|sketch|paint|render)\b\s+(?:me\s+)?"
                  r"(?:an?\s+|the\s+|a\s+)?([a-z]+)", low)
    if m:
        from .. import art as _art
        subject = (m.group(2) or "elephant").strip()
        if subject not in _art.ALIAS:
            near = [k for k in _art.SUBJECTS if subject and subject in k]
            subject = near[0] if near else "elephant"
        colour = next((c for c in _art.PALETTE if re.search(rf"\b{c}\b", low)), "")
        return ("", [_call("draw", subject=subject, colour=colour)])
    if getattr(__import__("arcdesk.ai.tools", fromlist=["current_sketch"]),
               "current_sketch", None) is not None and re.search(
            r"\b(it|this|picture|drawing|art|sketch)\b"
            r"|\b(bigger|smaller|larger|left|right|undo|rotate|purple|blue|red|green"
            r"|orange|pink|yellow|add a sun|add a cloud|add a tree|remove)\b", low):
        return ("", [_call("art_edit", instruction=t)])

    # --- timers ---------------------------------------------------------
    if re.search(r"\b(timer|remind|reminder|alarm)\b", low):
        minutes = _num(low, 5)
        if "hour" in low:
            minutes = minutes * 60
        label = "timer"
        m = re.search(r"(?:to|for)\s+(.+)$", t, re.I)
        if m and not NUM.fullmatch(m.group(1).strip()):
            label = m.group(1).strip()[:60]
        return ("", [_call("timer", minutes=minutes, label=label)])

    # --- notes ----------------------------------------------------------
    if re.search(r"\b(note|remember this|save this)\b", low):
        body = re.sub(r"^(note|remember this|save this)[:,\s]*", "", t, flags=re.I).strip()
        if not body:
            return ("What should I note down?", [])
        return ("", [_call("note", text=body)])
    if re.search(r"\b(read|show|my) notes\b", low) or "notes" in low and "read" in low:
        return ("", [_call("read_notes")])

    # --- weather --------------------------------------------------------
    if re.search(r"\b(weather|temperature|rain|hot|climate)\b", low):
        return ("", [_call("weather")])

    # --- files / clipboard ----------------------------------------------
    if (re.search(r"\bfind\b.*\b(file|pdf|photo|document)\b", low)
            or "search file" in low
            or re.search(r"\b(find|locate|where is)\s+[\w .\-]+\.[a-z0-9]{2,5}\b", low)):
        m = re.search(r"(?:named|called)\s+([\w .\-]{2,40})", t, re.I)
        name = m.group(1) if m else re.sub(r"^(find|locate|where is|search file)\s+", "",
                                           low).strip()
        return ("", [_call("find_file", name=name or t.split()[-1])])
    if "clipboard" in low:
        return ("", [_call("clipboard", action="get")])

    # --- launching ------------------------------------------------------
    m = re.match(r"^(?:open|launch|start|run|go to|goto|visit)\s+(.+)$", low)
    if m:
        what = m.group(1).strip()
        alias = what.removeprefix("up ").strip()
        if alias in SITES:
            return ("", [_call("open_url", url=SITES[alias])])
        if what.startswith(("http", "www.")) or ".com" in what or ".ai" in what:
            return ("", [_call("open_url", url=what)])
        if re.search(r"\b(browser|search)\b", what):
            q = re.sub(r"\b(browser|search|for)\b", "", what).strip()
            return ("", [_call("web_search", query=q or what)])
        return ("", [_call("open_app", app=what)])
    if low.strip() in SITES:
        return ("", [_call("open_url", url=SITES[low.strip()])])
    if low.startswith("search ") or "google " in low:
        q = re.sub(r"^(search|google)\s+", "", low).strip()
        return ("", [_call("web_search", query=q)])

    # --- honest fallback ------------------------------------------------
    if re.search(r"\b(macros?|what have i taught you)\b", low):
        return ("", [_call("macros", action="list")])

    _code = _lang_code(t)
    if _code != "en":
        hint = _lang_phrase("no_idea", _code)
        if hint:
            return (hint, [])
    _fallback = ("I am in Lite mode, so I only handle direct commands like: open notepad, "
            "system status, set volume 30, timer 10 minutes, night mode, screenshot, "
            "note buy milk. For real conversation, add a brain from the ⋯ menu — "
            "Groq and Gemini are free.")
    return (_fallback, [])


CAL_NOISE = {"add", "create", "schedule", "book", "set", "up", "new", "an", "a", "the",
             "to", "my", "calendar", "event", "events", "appointment", "on", "at", "for"}


def _cal_when(low: str) -> tuple[str, str]:
    """Pull the time phrase out of a sentence. Returns (when, matched span)."""
    m = re.search(r"\b(\d{1,2}(?::\d{2})?\s?(?:am|pm))\b", low) or \
        re.search(r"\b(?:at|by)\s+(\d{1,2}(?::\d{2})?)", low)
    time_part = m.group(1).strip() if m else ""
    if not time_part:
        m2 = re.search(r"\bin\s+(\d+\s*(?:minutes?|hours?|days?))", low)
        if m2:
            return f"in {m2.group(1)}", m2.group(0)
    if "tomorrow" in low:
        return (f"tomorrow {time_part}".strip(), "tomorrow")
    if time_part:
        return time_part, m.group(0)
    m3 = re.search(r"\bon\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", low)
    if m3:
        return (f"{m3.group(1)} {time_part}".strip(), m3.group(0))
    return "", ""


def _cal_title(low: str, when_span: str) -> str:
    text = low.replace(when_span, " ") if when_span else low
    text = re.sub(r"\b(?:at|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?", " ", text)
    words = [w for w in re.split(r"\s+", text) if w and w not in CAL_NOISE]
    return " ".join(words).strip()[:60]


def _lang_code(text: str) -> str:
    try:
        from .. import lang as _l
        return _l.detect(text)
    except Exception:
        return "en"


def _lang_phrase(key: str, code: str) -> str:
    try:
        from .. import lang as _l
        return _l.localise(key, code)
    except Exception:
        return ""


def summarise_tool_result(name: str, result: str, args: dict | None = None) -> str:
    """Turn a raw tool string into one spoken sentence."""
    ok = not result.lower().startswith("error")
    if not ok:
        return result.replace("ERROR: ", "That failed: ", 1)[:240]
    if name == "time":
        return result.capitalize() + "."
    if name in ("system_report", "running_apps"):
        return result
    if name == "screenshot":
        return "Screen captured."
    if name == "timer":
        return result
    if name == "arc_mode":
        return result
    if name == "note":
        return "Noted."
    if name == "set_volume":
        return result
    return result[:240]
