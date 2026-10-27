"""Digital marketing, with arithmetic instead of adjectives.

Everything here is either a **calculation** (funnel maths, sample size, keyword
density, Flesch reading ease) or a **checklist** (channel playbooks, launch steps).
Nothing here invents benchmarks: if you ask "what CTR should I expect", the honest
answer is "it depends on the channel and the offer — here is how to measure your
own", and that is exactly what the tool returns.

Numbers you feed in come back as real numbers out, and every derived figure shows
the formula it used, so it can be checked by hand.
"""
from __future__ import annotations

import math
import re
from urllib.parse import urlencode, urlparse

CHANNELS = {
    "instagram": ["3 reels a week, same hook shape",
                  "reply to every comment in the first hour",
                  "one carousel that teaches something, not a photo dump",
                  "link in bio points at one page, not five"],
    "youtube": ["title = the promise, thumbnail = the proof",
                "first 15 s repeat the title in plain words",
                "one video per format, never two formats in one upload",
                "pin a comment with the next step"],
    "google": ["one landing page per intent, not one homepage for everything",
               "write the title people actually type",
               "local businesses: Business Profile first, ads second",
               "measure calls, not clicks"],
    "email": ["subject under 45 characters",
              "one idea, one link",
              "send on a schedule you can keep for a year",
              "clean the list quarterly, dead addresses hurt deliverability"],
    "whatsapp": ["broadcast only to people who asked",
                 "one offer, one deadline",
                 "reply within minutes — that is the whole channel",
                 "never forward spam; it is the fastest way to get blocked"],
    "blog": ["one question per article, answered completely",
             "internal links to your own next article",
             "update the top three posts every quarter",
             "schema markup for anything local"],
}


def funnel(impressions: float = 0, clicks: float = 0, leads: float = 0,
           sales: float = 0, spend: float = 0, revenue: float = 0) -> str:
    """The whole funnel, computed. Show the formula with every line."""
    imp, clk = max(0.0, float(impressions)), max(0.0, float(clicks))
    ld, sl = max(0.0, float(leads)), max(0.0, float(sales))
    cost, rev = max(0.0, float(spend)), max(0.0, float(revenue))
    if not imp and not clk and not cost:
        return ("Give me at least impressions, clicks or spend — for example: "
                "'funnel 20000 impressions, 400 clicks, 60 leads, 12 sales, "
                "spend 5000, revenue 24000'.")
    lines = ["Funnel, computed:"]

    def rate(label: str, num: float, den: float, note: str) -> None:
        if den > 0:
            lines.append(f"  · {label}: {100 * num / den:.2f}%   ({note})")

    if imp:
        rate("CTR", clk, imp, f"{clk:.0f} clicks ÷ {imp:.0f} impressions")
    if clk:
        rate("click → lead", ld, clk, f"{ld:.0f} leads ÷ {clk:.0f} clicks")
    if ld:
        rate("lead → sale", sl, ld, f"{sl:.0f} sales ÷ {ld:.0f} leads")
    if imp and sl:
        rate("impression → sale", sl, imp, "the only number that pays rent")
    if cost:
        if clk:
            lines.append(f"  · CPC: {cost / clk:,.2f}   (spend ÷ clicks)")
        if ld:
            lines.append(f"  · CPL: {cost / ld:,.2f}   (spend ÷ leads)")
        if sl:
            lines.append(f"  · CAC: {cost / sl:,.2f}   (spend ÷ sales)")
        if imp:
            lines.append(f"  · CPM: {1000 * cost / imp:,.2f}   "
                         f"(spend ÷ impressions × 1000)")
    if cost and rev:
        lines.append(f"  · ROAS: {rev / cost:.2f}×   (revenue ÷ spend)")
        lines.append(f"  · profit before other costs: {rev - cost:,.2f}")
    elif rev:
        lines.append(f"  · revenue: {rev:,.2f} (no spend given, so no ROAS)")
    lines.append("")
    lines.append("If a rate looks bad, fix the step above it, not the ad. "
                 "Nothing here compares you to an industry average — "
                 "those numbers are not mine to invent.")
    return "\n".join(lines)


def utm(url: str = "", source: str = "instagram", medium: str = "social",
        campaign: str = "launch", term: str = "", content: str = "") -> str:
    """A tagged link you can actually paste. Rebuilds the query cleanly."""
    base = (url or "").strip()
    if not base:
        return ("Give me the link too — for example: 'utm for "
                "https://mysite.com/rooms source instagram medium social "
                "campaign monsoon'.")
    if not re.match(r"^https?://", base, flags=re.I):
        base = "https://" + base
    parsed = urlparse(base)
    existing = dict(pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair)
    tag = {"utm_source": source, "utm_medium": medium, "utm_campaign": campaign}
    if term:
        tag["utm_term"] = term
    if content:
        tag["utm_content"] = content
    existing.update({k: v.replace(" ", "-") for k, v in tag.items() if v})
    built = parsed._replace(query=urlencode(existing)).geturl()
    return ("Tagged link:\n  " + built +
            "\n\nUse the same three values everywhere or the reports will not "
            "add up. Lowercase, no spaces — spaces become %20 and break grouping.")


def seo_check(text: str = "", keyword: str = "") -> str:
    """Real text statistics: length, readability, keyword use, structure."""
    body = (text or "").strip()
    if not body:
        return "Paste the text (or a file's contents) and I will measure it."
    sentences = [s for s in re.split(r"[.!?]+", body) if s.strip()]
    words = re.findall(r"[A-Za-z0-9'’]+", body)
    syllables = sum(_syllables(w) for w in words)
    n_w, n_s = max(1, len(words)), max(1, len(sentences))
    flesch = 206.835 - 1.015 * (n_w / n_s) - 84.6 * (syllables / n_w)
    avg_sentence = n_w / n_s
    lines = [f"{n_w} words · {n_s} sentences · average {avg_sentence:.1f} words a sentence",
             f"Reading ease (Flesch): {flesch:.0f} — "
             + ("easy" if flesch >= 70 else "moderate" if flesch >= 50 else "hard"),
             f"Headings: {len(re.findall(r'^#{1,6} ', body, flags=re.M))}",
             f"Links: {len(re.findall(r'https?://', body))}"]
    if keyword:
        kw = keyword.lower().strip()
        hits = len(re.findall(rf"\b{re.escape(kw)}\b", body, flags=re.I))
        density = 100 * hits * len(kw.split()) / n_w
        lines.append(f"Keyword {kw!r}: {hits}× · density {density:.2f}% "
                     f"({'too thin' if hits == 0 else 'ok' if density <= 3 else 'stuffing'})")
        first = body.lower().find(kw)
        lines.append("First mention: "
                     + (f"character {first}" if first >= 0 else "not in the text"))
    lines.append("")
    lines.append("Targets I will not fake: there is no universal 'good' density. "
                 "1-2% reads naturally on a page written for humans; going higher "
                 "usually makes it worse for both.")
    return "\n".join(lines)


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 1
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")):
        n -= 1
    return max(1, n)


def sample_size(baseline: float = 0.05, lift: float = 0.2, confidence: float = 0.95) -> str:
    """How many visitors an A/B test needs. Real formula, stated assumptions."""
    p1 = max(0.0001, min(0.9999, float(baseline)))
    delta = p1 * max(0.01, float(lift))
    if delta <= 0:
        return "Give me a baseline conversion rate and the lift you want to detect."
    z = 1.96 if float(confidence) >= 0.95 else 1.645
    n = (z ** 2) * 2 * p1 * (1 - p1) / (delta ** 2)
    n = math.ceil(n)
    days = math.ceil(n / 100) if n else 0
    return (f"Baseline {100 * p1:.2f}%, lift to detect {100 * delta:.2f} points "
            f"(a relative {100 * float(lift):.0f}%), {100 * float(confidence):.0f}% "
            f"confidence:\n"
            f"  · {n:,} visitors per variant ({2 * n:,} total)\n"
            f"  · at 100 visitors a day that is {days} days — do not stop early\n\n"
            f"Stopping the test when it 'looks winning' is how people ship noise. "
            f"This formula assumes two independent proportions and one primary "
            f"metric; test one thing at a time.")


def plan(business: str = "", weeks: int = 4, channels: str = "instagram,google") -> str:
    """A weekly playbook per channel. Actions, not vibes."""
    name = business.strip() or "[your business]"
    chans = [c.strip() for c in (channels or "").split(",") if c.strip() in CHANNELS]
    if not chans:
        chans = ["instagram", "google"]
    lines = [f"{weeks}-week plan for {name}", ""]
    for ch in chans:
        lines.append(f"{ch.upper()}")
        for step in CHANNELS[ch]:
            lines.append(f"  · {step}")
        lines.append("")
    lines.append("Weekly rhythm, same every week:")
    lines.append("  Mon  decide the one offer · Tue-Wed make the pieces · "
                 "Thu publish · Fri reply and measure · Sat improve one thing")
    lines.append("")
    lines.append("Measure three numbers only: reach, replies, and money in. "
                 "Everything else is a distraction for the first 90 days.")
    return "\n".join(lines)


def email_sequence(product: str = "") -> str:
    """Five emails, in the order that works: usefulness first, ask last."""
    p = product.strip() or "your product"
    beats = [("Day 0", "Deliver the thing you promised. No pitch.", "the free value"),
             ("Day 1", f"The problem {p} solves, in one story.", "one proof"),
             ("Day 3", "The objection, answered head-on.", "price / trust / timing"),
             ("Day 5", "A short case: before, after, how long it took.", "one number"),
             ("Day 7", "The offer, with a real deadline.", "one link")]
    return (f"5-email sequence for {p}:\n" +
            "\n".join(f"  {day}: {what}   → include: {inc}" for day, what, inc in beats) +
            "\n\nHonest note: a deadline that resets every week is a lie your "
            "customers will notice. Only use one you will actually honour.")
