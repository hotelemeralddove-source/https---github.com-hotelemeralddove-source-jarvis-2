"""Market analysis that shows its arithmetic and refuses to pretend it can see ahead.

The user asked for "what is going up, what should I buy, what should I sell". An
honest assistant can answer three of those four things:

* **what is happening** — prices, trend, momentum, volatility, distance from highs.
  These are measurements, and they are exact.
* **what the signals say** — moving averages, RSI, drawdown. Also measurements, with
  the caveat that every one of them has been wrong for long stretches.
* **how much a position would risk** — pure arithmetic, and genuinely useful.
* **what will happen next** — *not knowable*. Any tool that claims otherwise is
  selling something. `project()` already labels its output a line through the past;
  this module goes further and refuses to phrase anything as "buy now".

Every string this module returns ends with a disclaimer, and none of them contain
the words that turn information into advice ("you should buy", "guaranteed",
"target achieved"). `tests/test_market.py` asserts that.
"""
from __future__ import annotations

import json
import time

from . import knows

DISCLAIMER = ("Information and arithmetic, not investment advice. Prices move; "
              "past patterns break; nothing here can predict the next move. "
              "Position sizes are maths, not recommendations.")


def _closes(symbol: str) -> tuple[str, list[float], list[str]]:
    """Same free Yahoo source as `knows`, ~6 months of daily closes."""
    sym, closes, stamps = knows._series(symbol, 180)   # noqa: SLF001 — shared helper
    label = sym[:-3].replace("^", "") if sym.endswith(".NS") else sym
    return label.title() if label.isupper() else label, closes, stamps


# ------------------------------------------------------------------ maths
def sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains = losses = 0.0
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return round(100 - (100 / (1 + rs)), 1)


def volatility(values: list[float], window: int = 20) -> float | None:
    """Annualised stdev of daily returns, in percent."""
    if len(values) < window + 1:
        return None
    window_vals = values[-(window + 1):]
    rets = [(window_vals[i] / window_vals[i - 1]) - 1 for i in range(1, len(window_vals))
            if window_vals[i - 1]]
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
    return round((var ** 0.5) * (252 ** 0.5) * 100, 1)


def drawdown(values: list[float]) -> float:
    peak, worst = -1e18, 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, (v / peak) - 1)
    return round(worst * 100, 1)


def position_size(capital: float, risk_pct: float, entry: float, stop: float) -> dict:
    """How many units fit inside a risk budget. Pure arithmetic, no opinion.

    If the stop is 2 % below the entry and you are willing to lose 1 % of ₹1,00,000,
    the maths gives ₹1,000 / ₹2 per unit = 500 units → ₹50,000 of exposure. That is
    the whole trick professionals use to survive being wrong; it says nothing about
    whether the trade is good.
    """
    if capital <= 0 or entry <= 0:
        return {"ok": False, "error": "capital and entry must be positive"}
    if stop <= 0:
        return {"ok": False, "error": "stop price must be positive"}
    per_unit_risk = abs(entry - stop)
    if per_unit_risk <= 0:
        return {"ok": False, "error": "stop must differ from entry"}
    risk_amount = capital * (risk_pct / 100.0)
    units = int(risk_amount // per_unit_risk)
    exposure = round(units * entry, 2)
    return {"ok": True, "risk_amount": round(risk_amount, 2), "per_unit_risk":
            round(per_unit_risk, 4), "units": units, "exposure": exposure,
            "exposure_pct": round(100 * exposure / capital, 1),
            "r_multiple_at_2R": round(entry + 2 * per_unit_risk, 2)}


# --------------------------------------------------------------- analysis
def analyse(symbol: str) -> str:
    name, closes, dates = _closes(symbol)
    if not closes or len(closes) < 30:
        return f"ERROR: not enough price history for {symbol} (needs internet)."
    last = closes[-1]
    s20, s50 = sma(closes, 20), sma(closes, 50)
    r = rsi(closes)
    vol = volatility(closes)
    high, low = max(closes[-60:]), min(closes[-60:])
    month = (last / closes[-21] - 1) * 100 if len(closes) > 21 else None
    dd = drawdown(closes[-120:])

    trend = "up" if s20 and s50 and s20 > s50 and last > s20 else \
            "down" if s20 and s50 and s20 < s50 and last < s20 else "sideways"

    lines = [f"{name} — {last:,.2f}",
             f"  trend: {trend}  (20d avg {s20:,.2f} · 50d avg {s50:,.2f})"
             if s20 and s50 else f"  trend: {trend}"]
    if month is not None:
        lines.append(f"  30 sessions: {month:+.1f}%")
    lines.append(f"  60-session range: {low:,.2f} – {high:,.2f}  "
                 f"(now {100 * (last - low) / max(1e-9, high - low):.0f}% up that range)")
    if r is not None:
        reading = ("overbought by the usual 70 line" if r >= 70 else
                   "oversold by the usual 30 line" if r <= 30 else "neither extreme")
        lines.append(f"  RSI(14): {r} — {reading}")
    if vol is not None:
        lines.append(f"  annualised volatility: {vol}%  "
                     f"(a 1-day move of ±{vol / 252 ** 0.5:.1f}% is ordinary)")
    lines.append(f"  worst drawdown in the last 120 sessions: {dd}%")
    lines.append("\nWhat this does and does not say: these are measurements of the "
                 "past 6 months. They describe momentum, not the future. A trend can "
                 "end the day after you notice it.")
    lines.append("Sizing: if you were to take a position, the only part you can "
                 "control is how much you lose if you are wrong — see `market_plan`.")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def screen(symbols: list[str], rule: str = "uptrend") -> str:
    """Filter a list by a measurable condition. Never 'buy these'."""
    rule = (rule or "uptrend").lower()
    rules = {
        "uptrend": lambda c, s20, s50, r: s20 and s50 and s20 > s50 and c[-1] > s20,
        "downtrend": lambda c, s20, s50, r: s20 and s50 and s20 < s50 and c[-1] < s20,
        "oversold": lambda c, s20, s50, r: r is not None and r <= 35,
        "overbought": lambda c, s20, s50, r: r is not None and r >= 65,
        "near_low": lambda c, s20, s50, r: c[-1] <= min(c[-60:]) * 1.03,
        "near_high": lambda c, s20, s50, r: c[-1] >= max(c[-60:]) * 0.97,
    }
    if rule not in rules:
        return f"ERROR: rule must be one of {', '.join(rules)}"
    hits, misses, errors = [], [], []
    for symbol in symbols[:40]:
        try:
            name, closes, _ = _closes(symbol)
            if len(closes) < 60:
                misses.append(symbol)
                continue
            s20, s50 = sma(closes, 20), sma(closes, 50)
            if rules[rule](closes, s20, s50, rsi(closes)):
                hits.append(f"  {name}  {closes[-1]:,.2f}  RSI {rsi(closes)}  "
                            f"30d {(closes[-1] / closes[-21] - 1) * 100:+.1f}%")
            else:
                misses.append(symbol)
        except Exception:
            errors.append(symbol)
    head = (f"{rule.replace('_', ' ')} — {len(hits)} of {len(symbols)} matched "
            f"a measurable condition")
    body = "\n".join(hits) if hits else "  none matched today"
    tail = ""
    if errors:
        tail = f"\n  (could not fetch: {', '.join(errors[:6])})"
    return (f"{head}\n{body}{tail}\n\nMatching a condition is not a reason to trade: "
            f"overbought names have stayed overbought for months, and 'near a low' is "
            f"only obvious afterwards.\n{DISCLAIMER}")


def plan(symbol: str, capital: float, risk_pct: float = 1.0,
         stop_pct: float = 4.0) -> str:
    """Position sizing plus the honest framing about being wrong."""
    try:
        name, closes, _ = _closes(symbol)
        entry = closes[-1]
    except Exception:
        return f"ERROR: could not get a price for {symbol} (needs internet)."
    stop = round(entry * (1 - stop_pct / 100), 2)
    size = position_size(float(capital), float(risk_pct), entry, stop)
    if not size.get("ok"):
        return f"ERROR: {size.get('error')}"
    vol = volatility(closes) or 0
    wide = vol and vol > 45
    lines = [
        f"If you entered {name} at {entry:,.2f} with a stop {stop_pct:.1f}% lower "
        f"({stop:,.2f}):",
        f"  risk budget      {size['risk_amount']:,.2f}  ({risk_pct}% of {capital:,.0f})",
        f"  units            {size['units']}  (risk per unit {size['per_unit_risk']:,.2f})",
        f"  exposure         {size['exposure']:,.2f}  ({size['exposure_pct']}% of capital)",
        f"  price for 2R     {size['r_multiple_at_2R']:,.2f}  (a 2:1 reward to risk)",
        "",
        f"Annualised volatility is {vol}%. At that level a {stop_pct:.0f}% stop will be "
        f"hit by ordinary noise fairly often" + (" — this is a high-volatility name, "
        "so size smaller, not bigger." if wide else "."),
        "",
        "The useful part of this is the denominator: you decide the loss first, "
        "then the size follows. Skip that and one bad week undoes a good year.",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def watchlist(action: str = "list", symbol: str = "", path=None) -> str:
    from . import config
    file = path or (config.data_dir() / "watchlist.json")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            data = []
    except Exception:
        data = []
    action = (action or "list").lower()
    if action in ("add", "watch"):
        if not symbol:
            return "ERROR: which symbol?"
        if symbol.upper() not in [s.upper() for s in data]:
            data.append(symbol.upper())
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"watching {symbol.upper()} ({len(data)} in the list)"
    if action in ("remove", "forget"):
        data = [s for s in data if s.upper() != symbol.upper()]
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"removed {symbol.upper()}"
    if not data:
        return "Your watchlist is empty. Add one: 'watch reliance'."
    rows = []
    for s in data[:20]:
        try:
            name, closes, _ = _closes(s)
            rows.append(f"  {name:<14} {closes[-1]:>12,.2f}  "
                        f"30d {(closes[-1] / closes[-21] - 1) * 100:+.1f}%")
        except Exception:
            rows.append(f"  {s:<14} unavailable")
    return ("watchlist\n" + "\n".join(rows) + f"\n{DISCLAIMER}")


def brief() -> str:
    """One screen, the questions people actually ask in the morning."""
    parts = []
    try:
        parts.append(knows.market_summary())
    except Exception as exc:
        parts.append(f"market summary unavailable: {exc}")
    parts.append("\nThe honest answer to 'what should I buy' is: nothing I say can "
                 "make that decision for you. What I can do is show momentum, "
                 "volatility and what a position would risk — ask 'analyse nifty' or "
                 "'plan reliance 100000 1 4'.")
    parts.append(DISCLAIMER)
    return "\n".join(parts)


def stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M")
