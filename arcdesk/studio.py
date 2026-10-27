"""Content creation — structure you can trust, words you still have to own.

What this module will not do: invent engagement numbers, fake testimonials, or
promise that a caption "will go viral". What it does instead is the part that is
actually mechanical — the skeleton, the word budget, the hook order, the posting
plan, the checklist — and it measures what it writes (real word counts, real
reading time) so the draft is never padded with lies.

With a local model connected, ARC fills the brackets. Offline, you get the same
document with the decisions marked `[like this]` instead of guessed at.

Output files are new files in the app's own work folder; nothing is overwritten.
"""
from __future__ import annotations

import time

from . import config

WORDS_PER_MINUTE = 220        # measured reading speed for plain prose, not a promise

KINDS: dict[str, dict] = {
    "blog": {"label": "blog post", "words": 900,
             "sections": ["Hook — the problem in the reader's words",
                          "Why it happens", "What most people try, and why it fails",
                          "The method, step by step", "A concrete example",
                          "What to do this week", "Close — one action"]},
    "instagram": {"label": "Instagram caption", "words": 90,
                  "sections": ["Hook line (first 8 words decide the scroll)",
                               "One idea", "One proof or detail",
                               "Call to action", "Hashtag block"]},
    "reel": {"label": "reel / short script", "words": 120,
             "sections": ["0-2s hook — say the promise",
                          "2-8s problem", "8-20s demo or proof",
                          "20-27s twist", "27-30s call to action"]},
    "youtube": {"label": "YouTube script", "words": 800,
                "sections": ["Title + thumbnail promise", "0-15s hook",
                             "Setup — what the viewer gets", "Chapters (3-5 acts)",
                             "Payoff", "One ask"]},
    "email": {"label": "email", "words": 150,
              "sections": ["Subject (6 words max)", "Preview text",
                           "One reason to read", "The offer", "One link", "Sign-off"]},
    "ad": {"label": "ad copy", "words": 60,
           "sections": ["Headline", "Sub-headline", "Proof", "Offer", "CTA"]},
    "product": {"label": "product description", "words": 120,
                "sections": ["What it is", "Who it is for", "What changes for them",
                             "Specs or contents", "Care / delivery", "CTA"]},
    "speech": {"label": "speech", "words": 600,
               "sections": ["Opening image", "The stake", "Three points",
                            "A story that lands", "Close — the ask"]},
    "whatsapp": {"label": "WhatsApp promo", "words": 70,
                 "sections": ["Greeting with their name", "One offer",
                              "Deadline", "Reply word"]},
    "thankyou": {"label": "thank-you note", "words": 60,
                 "sections": ["Name", "The specific thing they did",
                              "What it made possible", "One warm close"]},
}

TONES = ("friendly", "professional", "bold", "funny", "calm", "inspiring")
HOOK_STYLES = ("number", "mistake", "question", "before-after", "contrarian", "how-to")
CHANNELS = ("instagram", "youtube", "blog", "email", "whatsapp", "linkedin", "ads")


def _slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in (text or "draft")]
    slug = "".join(keep).strip("_")
    return (slug[:40] or "draft")


def words(text: str) -> int:
    return len([w for w in (text or "").split() if any(ch.isalnum() for ch in w)])


def read_time(text: str) -> str:
    n = words(text)
    seconds = round(n / WORDS_PER_MINUTE * 60)
    return f"{n} words · about {max(1, seconds // 60)} min {seconds % 60:02d} s to read aloud"


def kinds_text() -> str:
    return "Formats I can lay out:\n" + "\n".join(
        f"  · {key} — {v['label']}, target {v['words']} words"
        for key, v in KINDS.items())


def outline(kind: str, topic: str, tone: str = "friendly", audience: str = "",
            target_words: int = 0) -> str:
    """The skeleton, with the target word budget split across sections."""
    k = KINDS.get((kind or "blog").lower().strip())
    if k is None:
        return (f"No format called {kind!r}. " + kinds_text())
    tone = tone if tone in TONES else "friendly"
    total = int(target_words or k["words"])
    per = max(25, total // max(1, len(k["sections"])))
    who = audience.strip() or "[who exactly — age, situation, what they already tried]"
    lines = [f"{k['label'].upper()} · {topic or '[topic]'}",
             f"Voice: {tone} · Reader: {who} · Budget: {total} words "
             f"(~{per} per section)",
             ""]
    for i, s in enumerate(k["sections"], 1):
        lines.append(f"{i}. {s}")
        lines.append(f"   → {per} words. Write about: {topic or '[topic]'} "
                     f"from the reader's side of the problem.")
    lines += ["", "Rules while writing:",
              "  · one idea per paragraph; if a sentence needs a comma splice, split it",
              f"  · keep the {tone} voice consistent — do not drift formal halfway",
              "  · every claim gets a number, a name, or is cut",
              "  · no invented statistics. If you do not have the figure, say "
              "'I do not have the figure' and move on"]
    return "\n".join(lines)


def hooks(topic: str, n: int = 6) -> str:
    """Six opening lines in six different shapes. You pick, not me."""
    t = topic.strip() or "your topic"
    pairs = {
        "number": f"3 things about {t} nobody tells you before you start.",
        "mistake": f"The most expensive mistake with {t} is the one that feels safe.",
        "question": f"What if {t} is not hard — just badly explained?",
        "before-after": f"I changed one thing about {t} and the result changed first.",
        "contrarian": f"Most advice about {t} is written by people who never had to do it.",
        "how-to": f"How to do {t} this week, with what you already have.",
    }
    order = [s for s in HOOK_STYLES if s in pairs][:max(1, min(int(n), 6))]
    return "Opening lines (pick one, then delete the rest):\n" + "\n".join(
        f"  {i}. [{style}] {pairs[style]}" for i, style in enumerate(order, 1))


def draft(kind: str, topic: str, tone: str = "friendly", audience: str = "",
          target_words: int = 0) -> str:
    """The outline plus a fully written skeleton you can talk over or edit."""
    body = outline(kind, topic, tone, audience, target_words)
    k = KINDS.get((kind or "blog").lower().strip()) or KINDS["blog"]
    slots = "\n".join(f"[{s.split('—')[0].strip()}]" for s in k["sections"])
    return (body + "\n\n---\n\nDRAFT (fill the brackets, or connect a local model and "
            "ask me to write it)\n\n" + slots +
            "\n\n" + read_time(body))


def hashtags(topic: str, n: int = 12) -> str:
    """Topic words plus broad reach tags. Deterministic, and honest about it.

    These are *candidate* tags built from your own words. Nobody can tell you a
    tag is trending without live data, and this module never claims to.
    """
    base = [w.lower() for w in (topic or "").split() if w.isalnum() and len(w) > 2]
    tags: list[str] = []
    for w in base[:4]:
        tags += [w, w + "ideas", w + "tips", w + "daily", w + "india"]
    tags += ["reels", "explore", "howto", "smallbusiness", "madeinindia", "karnataka"]
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append("#" + t)
    return (f"{min(int(n), len(out))} candidate hashtags (no 'trending' claim — "
            f"that needs live data):\n  " + "  ".join(out[:int(n)]))


def calendar(topic: str, weeks: int = 2, channels: str = "instagram,youtube,blog") -> str:
    """A posting plan with real dates. Weekends get lighter, repeatable formats."""
    weeks = max(1, min(12, int(weeks)))
    chans = [c.strip() for c in (channels or "instagram").split(",") if c.strip()]
    chans = [c for c in chans if c in CHANNELS] or ["instagram"]
    formats = ["hook reel", "carousel", "behind the scenes", "how-to", "proof / case",
               "myth vs fact", "Q&A", "long form"]
    day = time.localtime()
    start = day
    lines = [f"{weeks}-week plan for {topic or '[topic]'}" +
             f" · channels: {', '.join(chans)}", ""]
    stamp = time.mktime(start)
    idx = 0
    for w in range(weeks):
        lines.append(f"Week {w + 1}")
        for d in range(7):
            when = time.localtime(stamp + (w * 7 + d) * 86400)
            weekday = time.strftime("%a %d %b", when)
            if when.tm_wday >= 5:          # real Saturday / Sunday, not day 5 of the row
                lines.append(f"  {weekday}  rest / reply to comments, no post")
                continue
            ch = chans[idx % len(chans)]
            fmt = formats[idx % len(formats)]
            lines.append(f"  {weekday}  {ch:<10} {fmt}")
            idx += 1
        lines.append("")
    lines.append("Rule: one format repeated beats five formats attempted. "
                 "Measure saves and replies, not likes.")
    return "\n".join(lines)


def save(text: str, name: str = "draft") -> str:
    """Write a new file in the app's work folder. Never overwrites an old one."""
    folder = config.data_dir() / "work"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = folder / f"{_slug(name)}_{stamp}.md"
    n = 2
    while path.exists():                       # belt and braces: a new sibling
        path = folder / f"{_slug(name)}_{stamp}_{n}.md"
        n += 1
    path.write_text(text, encoding="utf-8")
    return f"Saved {words(text)} words to {path}"
