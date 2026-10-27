"""Business strategy — the frameworks, filled with *your* facts, never invented ones.

A SWOT is worthless if a machine invents the strengths. So each tool here returns a
**structured canvas with the right questions in the right slots**, plus the
arithmetic that can be answered from numbers you give me (break-even, margins, unit
economics, decision weighting).

Rule this module keeps: if a cell needs a fact about your business, it stays a
question. The value is in finishing it, and a filled-in template beats a paragraph
of confident-sounding filler.
"""
from __future__ import annotations


def _clean(text: str, fallback: str) -> str:
    return (text or "").strip() or fallback


def swot(subject: str = "") -> str:
    s = _clean(subject, "[your business]")
    return f"""SWOT · {s}

STRENGTHS — what is true today, provable
  1. What do customers thank you for, in their words?
  2. What do you do faster or cheaper than the alternative, and by how much?
  3. What do you own that a competitor cannot copy this quarter?

WEAKNESSES — inside your control
  1. Where does the customer wait, repeat themselves, or give up?
  2. Which single person, if they left, breaks something?
  3. What number do you not know that you should? (that is a weakness too)

OPPORTUNITIES — outside, but reachable
  1. Which demand is going unmet right now, near you?
  2. What changed this year that makes something newly possible or cheap?
  3. Which adjacent customer would pay more for the same work?

THREATS — outside, not in your control
  1. Who can undercut you, and what would it cost them?
  2. What rule, platform or supplier could change your costs overnight?
  3. What happens to revenue if your top channel halves?

Then force the ranking: circle ONE strength to lead with this quarter, ONE weakness
to fix, ONE opportunity to test small. A SWOT with twenty items and no decision is a
wall decoration."""


def five_forces(industry: str = "") -> str:
    i = _clean(industry, "[your industry]")
    return f"""Porter's five forces · {i}

1. RIVALRY — how many real alternatives does the customer have?
   Ask: what do they do today instead of buying from you? (often "nothing" — that is
   the real competitor)

2. NEW ENTRANTS — what does it cost someone to start doing this next month?
   Ask: is there any licence, relationship, or asset that takes years to build?

3. BUYER POWER — can one customer move your month?
   Ask: what is your largest customer as a share of revenue? Above 30% is a warning.

4. SUPPLIER POWER — who can raise your price or drop you?
   Ask: for each key input, how many alternatives have you actually contacted?

5. SUBSTITUTES — what solves the same job a completely different way?
   Ask: if your category vanished, what would your customer do on Monday?

Score each 1 (weak pressure, good for you) to 5 (brutal). Add them up: 5-10 is
comfortable, 11-17 is normal, 18-25 means the industry, not your effort, decides
your margin. I am not guessing your scores — you know them."""


def bmc(business: str = "") -> str:
    b = _clean(business, "[your business]")
    return f"""Business Model Canvas · {b}

  CUSTOMER SEGMENTS     who exactly, and who you deliberately refuse
  VALUE PROPOSITION     the change in their life, in one sentence, no adjectives
  CHANNELS              how they find you, and how they buy
  CUSTOMER RELATIONS    what keeps them, after the sale
  REVENUE STREAMS       what they pay for, how often, how much
  KEY RESOURCES         what you must own: skill, stock, licence, software
  KEY ACTIVITIES        the three things that actually make the money
  KEY PARTNERS          who you depend on, and what happens if they stop
  COST STRUCTURE        fixed vs variable, per month, in real numbers

Fastest way to use this: fill COST STRUCTURE first, then REVENUE, then everything
else. If the two numbers do not survive each other, the model is not a model yet."""


def break_even(fixed: float = 0, price: float = 0, variable: float = 0,
               units_label: str = "units") -> str:
    """Real arithmetic. No rounding away the uncomfortable part."""
    f, p, v = float(fixed), float(price), float(variable)
    if p <= 0:
        return "Give me the selling price per unit as well, e.g. 'break even 90000 750 320'."
    margin = p - v
    if margin <= 0:
        return (f"At price {p:,.0f} and variable cost {v:,.0f} you lose {abs(margin):,.0f} "
                f"on every sale. No volume fixes that — raise the price or cut the cost.")
    units = f / margin
    return (f"Break-even: {units:,.1f} {units_label} "
            f"(round up to {int(units) + 1})\n"
            f"  · contribution per unit: {margin:,.2f}  (price {p:,.0f} − variable {v:,.0f})\n"
            f"  · contribution margin: {100 * margin / p:.1f}%\n"
            f"  · revenue at break-even: {units * p:,.0f}\n"
            f"  · every unit after that adds {margin:,.2f} before tax\n\n"
            f"Sanity check: is {int(units) + 1} {units_label} a month realistic with your "
            f"current capacity? If not, the fixed cost is the thing to change.")


def unit_econ(price: float = 0, cogs: float = 0, cac: float = 0,
              repeat: float = 1.0) -> str:
    """Unit economics, including the number people avoid: payback."""
    p, c, a = float(price), float(cogs), float(cac)
    r = max(1.0, float(repeat))
    if p <= 0:
        return "Give me price, cogs and cac — e.g. 'unit econ 750 320 400 3'."
    gross = p - c
    ltv = gross * r
    lines = [f"Gross profit per sale: {gross:,.2f}  ({100 * gross / p:.1f}% margin)"]
    if a > 0:
        lines.append(f"Acquisition cost: {a:,.2f}")
        lines.append(f"Payback: {a / gross:.2f} orders before you are square")
        lines.append(f"LTV:CAC over {r:.0f} orders: {ltv / a:.2f}×  "
                     + ("healthy" if ltv / a >= 3 else "thin — under 3× leaves no room "
                        "for refunds, staff or a bad month"))
    else:
        lines.append("No acquisition cost given, so no LTV:CAC — that number is the "
                     "whole game, and it is worth measuring before you scale spend.")
    lines.append(f"Lifetime gross profit: {ltv:,.2f} over {r:.0f} order(s)")
    return "\n".join(lines)


def okr(objective: str = "", period: str = "this quarter") -> str:
    o = _clean(objective, "[the change you want]")
    return f"""OKR · {o} · {period}

OBJECTIVE (qualitative, one line, no numbers): {o}

Then exactly three key results, each a number that exists today and a target:
  1. from ___ to ___ by ___   (a count: customers, orders, properties)
  2. from ___ to ___ by ___   (a rate: conversion, occupancy, retention)
  3. from ___ to ___ by ___   (a cost or speed: minutes, rupees per order)

Test each one: could a stranger verify it from your records without asking you? If
not, it is a wish, not a key result. Three is the limit; the fourth always becomes
the excuse for missing the other three."""


def decision_matrix(options: str = "", criteria: str = "") -> str:
    """Weighted scoring, with the weights made explicit before the scores."""
    opts = [o.strip() for o in (options or "").split(",") if o.strip()]
    crit = [c.strip() for c in (criteria or "").split(",") if c.strip()]
    if len(opts) < 2:
        return ("Give me at least two options, e.g. 'decide new menu, staff training, "
                "renovate' and the criteria: 'cost, speed, risk, upside'.")
    crit = crit or ["cost", "speed", "risk", "upside"]
    lines = ["Decision matrix", "",
             "Step 1 — weight the criteria (they must add to 10). Write them down "
             "*before* scoring, or the scoring will invent its own weights:",
             "\n".join(f"   {c:<12} ___ /10" for c in crit), "",
             "Step 2 — score each option 1-5 per criterion, multiply by the weight:",
             "   " + " | ".join(f"{o[:18]:<18}" for o in opts)]
    for c in crit:
        lines.append(f"   {c:<12}" + " | ".join("____ × __" for _ in opts))
    lines += ["", "Step 3 — add the columns. If the winner is within 10% of the runner "
                  "up, the criteria are too vague: pick the one you would defend "
                  "to a customer, not the one that scored 0.5 higher.", ""]
    return "\n".join(lines)


MODES = {"swot": swot, "forces": five_forces, "bmc": bmc, "okr": okr}


def canvas(kind: str = "swot", subject: str = "") -> str:
    return MODES.get((kind or "swot").lower(), swot)(subject)
