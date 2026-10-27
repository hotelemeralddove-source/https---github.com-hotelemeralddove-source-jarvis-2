"""Forecasting and "what is happening in the world" — with the honesty built in.

The request behind this module was "predict and give correct answers" and "entire
details of the world, what happened, what is happening, what will happen".

Nobody can do that, and a system that pretends to is the most dangerous kind of
wrong: it sounds certain. So this module splits the question into the three things
that are actually possible:

  1. **What the numbers do next** — a least-squares extrapolation with an honest
     error band, labelled as arithmetic, never as prophecy (`forecast`).
  2. **What could plausibly happen, and why** — scenarios with explicit drivers and
     the assumptions that must hold (`scenario`).
  3. **What I do not know** — the part that keeps ARC trustworthy (`unknown`,
     `verify`, `rules`). It says what it cannot see, and what would settle it.

Live world events need a live source. ARC will not narrate them from memory.
"""
from __future__ import annotations

import math


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def forecast(values: str = "", periods: int = 3) -> str:
    """Extrapolate a series you supply. Real maths, stated error, no oracle voice."""
    try:
        xs = [float(v) for v in str(values).replace(",", " ").split() if v.strip()]
    except Exception:
        return "Give me the numbers in order, e.g. 'forecast 120 140 155 171 190 3'."
    if len(xs) < 4:
        return (f"{len(xs)} values is not a series. I need at least 4, and honestly "
                f"8 or more before the slope means anything.")
    n = len(xs)
    idx = list(range(n))
    mx, my = _mean(idx), _mean(xs)
    sxx = sum((i - mx) ** 2 for i in idx)
    slope = sum((i - mx) * (v - my) for i, v in zip(idx, xs)) / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_tot = sum((v - my) ** 2 for v in xs)
    ss_res = sum((v - (intercept + slope * i)) ** 2 for i, v in zip(idx, xs))
    r2 = 0.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    rmse = math.sqrt(ss_res / max(1, n - 2))
    k = max(1, min(36, int(periods)))
    lines = [f"Series: {n} values, slope {slope:+,.3f} per step, r² {r2:.3f}, "
             f"rmse {rmse:,.2f}", "", "Mechanical extrapolation (±1 rmse):"]
    for step in range(1, k + 1):
        point = intercept + slope * (n - 1 + step)
        lo, hi = point - 1.64 * rmse, point + 1.64 * rmse     # ~90% if errors are normal
        lines.append(f"  step +{step:<2} {point:>12,.2f}    range {lo:>12,.2f} – {hi:>12,.2f}")
    lines += ["",
              "What this is: a straight line through your own numbers, with the "
              "spread of past errors used as the band.",
              "What this is not: a forecast of anything that can change direction — "
              "policy, weather, a competitor, a festival, a rumour.",
              ("With r² below 0.3 the line barely explains the data; treat these "
               "numbers as arithmetic, not information." if r2 < 0.3 else
               "r² is decent, so the trend is at least consistent — the band is the "
               "part to quote, never the centre line.")]
    return "\n".join(lines)


def scenario(question: str = "", horizon: str = "6 months") -> str:
    """Three futures with their logic exposed. Probabilities are yours to set."""
    q = (question or "[your question]").strip()
    return f"""Scenarios · {q} · {horizon}

BASE CASE — the boring continuation
  What happens if nothing changes: ___
  What must hold for this: ___
  Earliest sign it is holding: ___

UPSIDE
  What would have to be true: ___
  Who makes it happen, and why would they:
  The one thing that would unlock it first:

DOWNSIDE
  What breaks first: ___
  What makes it worse quickly:
  What you would do in week one of it:

CROSS-CUTTING
  · Which of the three is cheapest to hedge against?
  · What decision this month would be wrong in two of the three?
  · What are you currently assuming without noticing?

I have left the probabilities blank on purpose. A number I made up would be the
single most misleading thing on this page. If you want the arithmetic instead of the
structure, give me the actual series and ask for a forecast.\n"""


def unknown(question: str = "") -> str:
    """The most useful honest answer JARVIS can give about the outside world."""
    q = (question or "that").strip()
    return (f"About {q!r}: I do not have a live news feed, a database of world events, "
            f"or a way to see what is happening right now. Anything I said from "
            f"memory would be undated and could be out of date — so I will not "
            f"dress it up as knowledge.\n\n"
            f"Three honest ways forward:\n"
            f"  1. **Read the primary source.** Ask me to open it: \"open "
            f"reuters.com\", \"open the PIB press releases\", \"open wikipedia {q}\".\n"
            f"  2. **Bring the numbers here.** Paste the figures or drop the CSV and "
            f"say 'mine this' — then I can compute, and computing is what I am good at.\n"
            f"  3. **Ask what would settle it.** Say 'verify <claim>' and I will give "
            f"you the checklist for checking it in five minutes.")


def verify(claim: str = "") -> str:
    """A claim-checking checklist. Not a verdict — a procedure."""
    c = (claim or "[the claim]").strip()
    return f"""To check: {c}

  1. WHO says it, and what do they gain if you believe it?
  2. WHEN was it said — is there a date on the page, not just in the URL?
  3. WHAT is the primary source — the filing, the dataset, the paper, the notice?
     If there is none, the claim is a report of a report of a rumour.
  4. HOW would it be measured, and is that the number being quoted? (A percentage of
     a percentage is the most common trick in business writing.)
  5. WHO ELSE reports it independently — two sources copying one press release is
     one source.
  6. WHAT would make it false? If nothing would, it is a belief, not a claim.

Say "open <site>" and I will put the source in your browser; I cannot read pages back,
so you stay the judge."""


def rules() -> str:
    return """How JARVIS handles claims about the world

  1. I do not invent facts, dates, prices, events, or numbers. If it is not in a
     source on this machine or something I measured just now, I say I do not know.
  2. A prediction is always labelled a prediction, with its assumptions written
     next to it. Never "will be", always "if X holds, then likely Y".
  3. A calculation is not a forecast, and a forecast is not a fact.
  4. Confidence gets a number only when it comes from data — otherwise it gets the
     word "guess" next to it, out loud.
  5. When you ask for certainty I cannot give, refusing is the answer, not a
     confident-sounding paragraph."""


def now_help() -> str:
    """What JARVIS can genuinely tell you about 'now'."""
    return ("What I know about right now, without the internet:\n"
            "  · the clock, the date, and what is on your calendar\n"
            "  · your CPU, memory, disk, network and battery, measured this second\n"
            "  · your reminders, notes, files and focus time\n"
            "  · anything in a local file you point me at\n\n"
            "What needs a source I do not have: news, prices, sports, weather beyond "
            "an opt-in cached reading, other people's actions. Ask me to open the "
            "source and read it yourself, or paste it in and I will analyse it.")
