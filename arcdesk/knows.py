"""Things JARVIS should know how to work out — without a language model.

The model is good at explaining, bad at arithmetic and worse at numbers it was not
given. So the numbers get their own code, computed here, exact, offline where
possible:

  * **calc**      — a real expression evaluator. No `eval()`, no name lookups, no
                    imports: an AST whitelist of arithmetic, comparisons and a
                    handful of math functions. `(1234*0.18)+56` is instant and right.
  * **convert**   — units, offline, exact definitions (1 inch = 2.54 cm, not 2.5).
  * **rates**     — currency, needs the network, and says so when it has none.
  * **stock**     — a quote from a public endpoint (no key). NSE symbols work
                    (`RELIANCE.NS`, `^NSEI` for Nifty).
  * **project**   — a least-squares line through recent closes, **plus the error
                    band and a straight warning** that a line is not a prophecy.
                    Nobody can predict a market; pretending otherwise is the one
                    thing a desktop assistant must not do.

Everything returns a string for the model (and therefore for the user) to read.
"""
from __future__ import annotations

import ast
import json
import math
import operator
import re
import urllib.parse
import urllib.request

MAX_EXPR = 200


# ------------------------------------------------------------------ calc
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
_FUNCS = {
    "sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log,
    "log10": math.log10, "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
    "pow": pow, "sum": sum,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("only numbers are allowed")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Compare):
        left = _eval(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in _CMP:
                raise ValueError("unsupported comparison")
            right = _eval(comparator)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _FUNCS.get(node.func.id)
        if fn is None:
            raise ValueError(f"unknown function {node.func.id}")
        return fn(*[_eval(a) for a in node.args])
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval(e) for e in node.elts]
    raise ValueError("that expression is not simple arithmetic")


def calc(expression: str) -> str:
    """Evaluate arithmetic exactly. Refuses anything that is not arithmetic."""
    expr = (expression or "").strip()
    if not expr:
        return "ERROR: nothing to calculate"
    if len(expr) > MAX_EXPR:
        return "ERROR: expression too long"
    # people type what they think: ×, ÷, ^, percentages
    expr = (expr.replace("×", "*").replace("÷", "/").replace("^", "**")
            .replace(",", ""))
    pct = re.fullmatch(r"(.+?)\s*(?:%|percent)\s+of\s+(.+)", expr, re.I)
    if pct:
        expr = f"({pct.group(1).replace('%', '')}/100)*({pct.group(2)})"
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"(\1/100)", expr)
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except Exception as exc:
        return f"ERROR: {exc}"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, float):
        return f"{value:,.6g}"
    return f"{value:,}"


# ------------------------------------------------------------------ units
UNITS = {
    # length (metres)
    "mm": ("length", 0.001), "cm": ("length", 0.01), "m": ("length", 1.0),
    "km": ("length", 1000.0), "inch": ("length", 0.0254), "in": ("length", 0.0254),
    "ft": ("length", 0.3048), "foot": ("length", 0.3048), "feet": ("length", 0.3048),
    "mile": ("length", 1609.344), "mi": ("length", 1609.344), "yard": ("length", 0.9144),
    # mass (grams)
    "mg": ("mass", 0.001), "g": ("mass", 1.0), "kg": ("mass", 1000.0),
    "ton": ("mass", 1_000_000.0), "lb": ("mass", 453.59237), "pound": ("mass", 453.59237),
    "oz": ("mass", 28.349523125),
    # data (bytes)
    "byte": ("data", 1.0), "kb": ("data", 1024.0), "mb": ("data", 1024.0 ** 2),
    "gb": ("data", 1024.0 ** 3), "tb": ("data", 1024.0 ** 4),
    # time (seconds)
    "sec": ("time", 1.0), "second": ("time", 1.0), "min": ("time", 60.0),
    "minute": ("time", 60.0), "hour": ("time", 3600.0), "day": ("time", 86400.0),
    "week": ("time", 604800.0),
}
ALIASES = {"kgs": "kg", "kilogram": "kg", "grams": "g", "kms": "km", "kilo": "kg",
           "litre": "l", "liter": "l", "l": ("volume", 0.001), "ml": ("volume", 1e-6)}
UNITS.update({k: v for k, v in ALIASES.items() if isinstance(v, tuple)})
ALIASES = {k: v for k, v in ALIASES.items() if isinstance(v, str)}


def convert(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between units. Temperature is special; everything else is a ratio."""
    f = ALIASES.get((from_unit or "").strip().lower(), (from_unit or "").strip().lower())
    t = ALIASES.get((to_unit or "").strip().lower(), (to_unit or "").strip().lower())
    try:
        value = float(value)
    except Exception:
        return "ERROR: give me a number to convert"

    if f in ("c", "celsius") and t in ("f", "fahrenheit"):
        return f"{value} °C is {value * 9 / 5 + 32:.1f} °F"
    if f in ("f", "fahrenheit") and t in ("c", "celsius"):
        return f"{value} °F is {(value - 32) * 5 / 9:.1f} °C"

    if f not in UNITS or t not in UNITS:
        return (f"ERROR: I know these units: {', '.join(sorted(set(UNITS)))}. "
                "For currency, ask for exchange rates.")
    f_kind, f_scale = UNITS[f]
    t_kind, t_scale = UNITS[t]
    if f_kind != t_kind:
        return f"ERROR: {f} is {f_kind} and {t} is {t_kind} — those do not convert"
    result = value * f_scale / t_scale
    return f"{value:g} {f} is {result:,.6g} {t}"


# ------------------------------------------------------------------ network
def _get_json(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "ArcDesk/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def rates(base: str = "INR", symbols: str = "") -> str:
    """Free, keyless exchange rates."""
    base = (base or "INR").upper()[:3]
    try:
        data = _get_json(f"https://open.er-api.com/v6/latest/{base}")
    except Exception as exc:
        return f"ERROR: no exchange rates without internet ({type(exc).__name__})"
    table = data.get("rates") or {}
    if not table:
        return "ERROR: the rate service returned nothing"
    wanted = [s.strip().upper() for s in (symbols or "USD,EUR,GBP,INR").split(",")]
    picked = [f"1 {base} = {table[s]:.4g} {s}" for s in wanted if s in table]
    stamp = data.get("time_last_update_utc", "")
    return "; ".join(picked) + (f"  ({stamp})" if stamp else "")


MARKET_ALIAS = {
    "nifty": "^NSEI", "nifty 50": "^NSEI", "nifty50": "^NSEI",
    "sensex": "^BSESN", "bank nifty": "^NSEBANK", "banknifty": "^NSEBANK",
    "s&p": "^GSPC", "sp500": "^GSPC", "nasdaq": "^IXIC", "dow": "^DJI",
    "gold": "GC=F", "silver": "SI=F", "crude": "CL=F", "bitcoin": "BTC-USD",
    "btc": "BTC-USD", "ethereum": "ETH-USD", "usd inr": "INR=X",
}


def _series(symbol: str, days: int = 30) -> tuple[str, list[float], list[str]]:
    sym = MARKET_ALIAS.get((symbol or "").strip().lower(), (symbol or "").strip().upper())
    if not sym:
        raise ValueError("no symbol given")
    if re.fullmatch(r"[A-Z]{2,15}", sym):
        sym = sym + ".NS"           # bare Indian tickers: RELIANCE -> RELIANCE.NS
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(sym)}?range={days}d&interval=1d")
    data = _get_json(url)
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        raise ValueError(f"no data for {sym}")
    node = result[0]
    closes = [c for c in (node.get("indicators", {}).get("quote") or [{}])[0].get("close", [])
              if isinstance(c, (int, float))]
    stamps = node.get("timestamp") or []
    if not closes:
        raise ValueError(f"no prices for {sym}")
    return sym, closes, [str(s) for s in stamps]


def stock(symbol: str = "") -> str:
    """A quote, a 1-month move, and a reminder that this is information, not advice."""
    try:
        sym, closes, _ = _series(symbol, 30)
    except Exception as exc:
        return (f"ERROR: could not fetch {symbol or 'that symbol'} "
                f"({type(exc).__name__}). Market data needs internet; I will not guess a price.")
    last = closes[-1]
    prev = closes[-2] if len(closes) > 1 else last
    change = (last - prev) / prev * 100 if prev else 0.0
    month = (last - closes[0]) / closes[0] * 100 if closes[0] else 0.0
    low, high = min(closes), max(closes)
    return (f"{sym}: {last:,.2f} ({change:+.2f}% today, {month:+.1f}% in 30 days; "
            f"range {low:,.2f}–{high:,.2f}). Information, not investment advice.")


def _linfit(values: list[float]) -> tuple[float, float, float]:
    n = len(values)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, values)) / denom
    intercept = my - slope * mx
    resid = [y - (intercept + slope * x) for x, y in zip(xs, values)]
    rmse = math.sqrt(sum(r * r for r in resid) / n)
    return slope, intercept, rmse


def project(symbol: str = "", days: int = 7) -> str:
    """A straight-line projection with its own error band, stated as a guess."""
    try:
        sym, closes, _ = _series(symbol, 60)
    except Exception as exc:
        return (f"ERROR: no data to project ({type(exc).__name__}) — "
                "and I will not invent a number.")
    if len(closes) < 10:
        return f"ERROR: only {len(closes)} prices for {sym}; too few to fit anything"
    days = max(1, min(int(days or 7), 30))
    slope, intercept, rmse = _linfit(closes)
    n = len(closes)
    target = intercept + slope * (n - 1 + days)
    lo, hi = target - 2 * rmse, target + 2 * rmse
    pct = (target - closes[-1]) / closes[-1] * 100
    direction = "up" if slope > 0 else "down" if slope < 0 else "flat"
    confidence = "wide" if rmse > abs(target) * 0.08 else "moderate"
    return (f"{sym} has trended {direction} over 60 sessions. A straight-line fit "
            f"puts it near {target:,.2f} in {days} days ({pct:+.1f}%), with a "
            f"±2σ band of {lo:,.2f}–{hi:,.2f} ({confidence} confidence). "
            f"This is a line through past prices, not a prediction of the future — "
            f"nobody knows the next print.")


def market_summary() -> str:
    """The four numbers people actually ask for, in one line each."""
    out = []
    for name in ("nifty", "sensex", "bitcoin", "usd inr"):
        try:
            out.append(stock(name))
        except Exception:
            continue
    return "\n".join(out) or "ERROR: market data needs internet"
