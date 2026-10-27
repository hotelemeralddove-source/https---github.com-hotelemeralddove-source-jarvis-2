"""Mirroring the user's language — the difference between an assistant and a form.

People here do not speak one language. They speak Tamil, English, Hindi, and most
often a mix: "macha, system status sollu" — Tamil grammar, English nouns, Latin
letters. An assistant that answers that in formal English is *technically* correct
and completely wrong.

So detection happens on three layers:

  1. **Script** — Tamil (`\\u0B80-\\u0BFF`), Devanagari, Telugu, Kannada, Bengali…
     If it is there, the answer is in that language, in that script.
  2. **Romanised Dravidian** — no Tamil letters at all, but the words are Tamil:
     "enna", "epdi", "sollu", "venum", "illa", "romba", "pannu", "seri", "da", "macha".
     This is the case everyone forgets and it is the most common one here.
  3. **English** — the default, used only when nothing else fires.

`mirror()` turns that into one instruction line for a language model, and
`localise()` translates the fixed phrases ARC says offline (Lite mode has no model to
translate for it). Numbers, file paths and tool arguments are **never** translated —
those must stay exact.
"""
from __future__ import annotations

import re

TAMIL = re.compile(r"[\u0B80-\u0BFF]")
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
TELUGU = re.compile(r"[\u0C00-\u0C7F]")
KANNADA = re.compile(r"[\u0C80-\u0CFF]")
BENGALI = re.compile(r"[\u0980-\u09FF]")
MALAYALAM = re.compile(r"[\u0D00-\u0D7F]")
ARABIC = re.compile(r"[\u0600-\u06FF]")
CJK = re.compile(r"[\u4E00-\u9FFF]")

SCRIPT_LANG = [
    (TAMIL, "ta"), (DEVANAGARI, "hi"), (TELUGU, "te"), (KANNADA, "kn"),
    (BENGALI, "bn"), (MALAYALAM, "ml"), (ARABIC, "ar"), (CJK, "zh"),
]

# Romanised Tamil / Tanglish markers. Weighted: the strong ones are unambiguous,
# the weak ones only count if there are two of them.
TANGLISH_STRONG = {
    "enna", "epdi", "eppadi", "sollu", "sollunga", "venum", "vendum", "illa", "illai",
    "romba", "pannu", "pannunga", "macha", "machan", "seri", "vanakkam", "thambi",
    "thala", "da", "di", "poda", "irukku", "iruku", "aagum", "aagadhu", "kuduthu",
    "podhu", "vachu", "pesu", "kelu", "paru", "paaru", "solliten", "mudiyum",
    "mudiyadhu", "evlo", "yen", "yaaru", "engae", "enga", "nalla", "sari", "konjam",
    "innum", "appuram", "ipo", "ippo", "naalaikku", "indha", "andha", "ithu", "adhu",
}
TANGLISH_WEAK = {"ok", "da", "na", "la", "ku", "ah", "eh", "thaan", "dhaan", "ma",
                 "bro", "mama", "anna", "akka", "super", "vera", "level"}

HINDI_ROMAN = {"kya", "kaise", "kaisa", "hai", "nahi", "karo", "batao", "mujhe",
               "yaar", "bhai", "acha", "theek", "kar", "de", "mera", "tera", "abhi"}

GREETING_HINTS = ("vanakkam", "namaskara", "namaste", "hello", "hi", "hey")

# How to speak, per language. Used verbatim in the model's system prompt.
STYLE = {
    "ta": ("Reply in Tamil, in Tamil script. Warm, casual, like a friend from Chennai. "
           "Keep it to one or two sentences because it will be spoken aloud."),
    "tanglish": ("Reply in Tanglish — Tamil grammar written in Latin letters, mixing "
                 "English technical words the way a Chennai engineer speaks "
                 "(\"system status paakaren, konjam wait pannu\"). Warm and casual. "
                 "Never switch to formal English."),
    "hi": ("Reply in Hindi, in Devanagari script. Friendly and casual, one or two "
           "short sentences because it is spoken aloud."),
    "hinglish": ("Reply in Hinglish — Hindi written in Latin letters, mixed with English "
                 "technical words. Casual and friendly, short sentences."),
    "en": "Reply in English. Warm, dry, concise — the way a competent friend talks.",
}

# Fixed sentences Lite can say without a model. Kept tiny on purpose: a wrong
# translation is worse than an English sentence.
PHRASES = {
    "noted": {"en": "Noted.", "tanglish": "Note pannitten.", "ta": "குறிப்பெடுத்துவிட்டேன்.",
              "hi": "नोट कर लिया।", "hinglish": "Note kar liya."},
    "done": {"en": "Done.", "tanglish": "Aayiduchu.", "ta": "முடிந்தது.",
             "hi": "हो गया।", "hinglish": "Ho gaya."},
    "stopped": {"en": "Stopped.", "tanglish": "Niruthiten.", "ta": "நிறுத்திவிட்டேன்.",
                "hi": "रोक दिया।", "hinglish": "Rok diya."},
    "no_idea": {
        "en": "I did not catch that. Say it again?",
        "tanglish": "Puriyala macha, innoru thadava sollu?",
        "ta": "புரியல, மறுபடியும் சொல்லுங்க?",
        "hi": "समझ नहीं आया, फिर से कहिए?",
        "hinglish": "Samajh nahi aaya, phir se bolo?",
    },
    "cannot": {
        "en": "I cannot do that, and I will not pretend I did.",
        "tanglish": "Adhu ennala mudiyadhu, poi solla maaten.",
        "ta": "அது என்னால் முடியாது, பொய் சொல்ல மாட்டேன்.",
        "hi": "वो मैं नहीं कर सकता, और झूठ नहीं बोलूंगा।",
        "hinglish": "Wo main nahi kar sakta, jhooth nahi bolunga.",
    },
    "working": {
        "en": "On it.",
        "tanglish": "Paakaren, konjam.",
        "ta": "பார்க்கிறேன், கொஞ்சம்.",
        "hi": "देख रहा हूँ।",
        "hinglish": "Dekh raha hoon.",
    },
}


def tts_lang(code: str) -> str:
    """Map JARVIS's language code to the language tag the TTS engine is asked for.

    Romanised codes (tanglish, hinglish) are written in Latin letters. Handing
    "enna panra" to a Tamil voice produces gibberish, because the voice expects
    Tamil script — so romanised speech goes to the English engine, which is the
    same rule voice.speech_lang() already applies by looking at the script.
    """
    return {"ta": "ta", "hi": "hi"}.get(code, "en")


def detect(text: str) -> str:
    """Return one of: ta, tanglish, hi, hinglish, en."""
    t = (text or "").strip()
    if not t:
        return "en"
    for pattern, code in SCRIPT_LANG:
        if pattern.search(t):
            return code

    words = re.findall(r"[a-z']+", t.lower())
    if not words:
        return "en"
    wordset = set(words)

    strong = len(wordset & TANGLISH_STRONG)
    weak = len(wordset & TANGLISH_WEAK)
    if strong >= 1 and len(words) <= 3:
        return "tanglish"
    if strong >= 2 or (strong >= 1 and weak >= 1):
        return "tanglish"
    if strong >= 1 and len(words) >= 4:
        return "tanglish"

    hindi = len(wordset & HINDI_ROMAN)
    if hindi >= 2:
        return "hinglish"
    return "en"


def mirror(text: str) -> tuple[str, str]:
    """(language code, one instruction line for the model)."""
    code = detect(text)
    return code, STYLE.get(code, STYLE["en"])


def localise(key: str, code: str) -> str:
    """Translate one of the fixed phrases. Falls back to English, never to gibberish."""
    table = PHRASES.get(key) or {}
    return table.get(code) or table.get("en") or ""


def greeting(code: str) -> str:
    return {"ta": "வணக்கம்.", "tanglish": "Vanakkam macha.", "hi": "नमस्ते।",
            "hinglish": "Namaste yaar.", "en": "Hello."}.get(code, "Hello.")


def name_language(code: str) -> str:
    return {"ta": "Tamil", "tanglish": "Tanglish", "hi": "Hindi",
            "hinglish": "Hinglish", "en": "English"}.get(code, code)
