"""Data mining on the user's own files — statistics that can be checked by hand.

No pandas, no numpy: this is a few hundred lines of arithmetic over a CSV or JSON
file, so it starts in milliseconds and adds zero megabytes to the app.

What it will do: describe columns, find missing values, compute mean/median/spread,
Pearson correlation, IQR outliers, group-by totals, and a least-squares trend.

What it will not do: claim causation from a correlation, invent a row that is not in
the file, or hide the sample size. Every answer includes `n`, because a correlation
of 0.9 over six rows is a rumour, not a finding.
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path


def _load(path: str) -> tuple[list[str], list[dict]]:
    p = Path(os.path.expanduser((path or "").strip().strip('"')))
    if not p.exists():
        raise FileNotFoundError(f"no file at {p}")
    suffix = p.suffix.lower()
    if suffix in (".json", ".jsonl", ".ndjson"):
        raw = p.read_text(encoding="utf-8", errors="replace")
        if suffix in (".jsonl", ".ndjson"):
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        else:
            data = json.loads(raw)
            rows = data if isinstance(data, list) else data.get("rows", [data])
        rows = [r for r in rows if isinstance(r, dict)]
        cols: list[str] = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        return cols, rows
    with p.open(newline="", encoding="utf-8", errors="replace") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delim = "\t" if "\t" in sample.splitlines()[0] else ","
        reader = csv.DictReader(fh, delimiter=delim)
        rows = [dict(r) for r in reader]
        return list(reader.fieldnames or []), rows


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _numbers(rows: list[dict], col: str) -> list[float]:
    out = []
    for r in rows:
        v = _num(r.get(col))
        if v is not None:
            out.append(v)
    return out


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _median(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def profile(path: str = "", limit_cols: int = 14) -> str:
    """Describe every column: type, missing, spread. The first thing to run."""
    try:
        cols, rows = _load(path)
    except Exception as exc:
        return f"I could not read that: {exc}"
    if not rows:
        return "The file has no rows."
    lines = [f"{len(rows):,} rows · {len(cols)} columns · {Path(path).name}"]
    for col in cols[:limit_cols]:
        values = [r.get(col) for r in rows]
        missing = sum(1 for v in values if v in (None, ""))
        nums = _numbers(rows, col)
        uniq = len({str(v) for v in values if v not in (None, "")})
        if len(nums) >= max(3, len(values) // 2):
            lines.append(f"  {col:<18} numeric  n={len(nums)}  "
                         f"mean {_mean(nums):,.2f}  median {_median(nums):,.2f}  "
                         f"sd {_stdev(nums):,.2f}  "
                         f"min {min(nums):,.2f}  max {max(nums):,.2f}"
                         + (f"  missing {missing}" if missing else ""))
        else:
            lines.append(f"  {col:<18} text     unique {uniq}"
                         + (f"  missing {missing}" if missing else ""))
    if len(cols) > limit_cols:
        lines.append(f"  … {len(cols) - limit_cols} more columns")
    lines.append("")
    lines.append("Missing values are counted, never filled in. A filled-in number is "
                 "a made-up number.")
    return "\n".join(lines)


def correlate(path: str = "", x: str = "", y: str = "") -> str:
    """Pearson r, with n, and the sentence that stops people over-reading it."""
    try:
        _, rows = _load(path)
    except Exception as exc:
        return f"I could not read that: {exc}"
    if not (x and y):
        return "Name two numeric columns, e.g. 'correlate sales.csv price units'."
    pairs = []
    for r in rows:
        a, b = _num(r.get(x)), _num(r.get(y))
        if a is not None and b is not None:
            pairs.append((a, b))
    n = len(pairs)
    if n < 3:
        return f"Only {n} complete pairs for {x} and {y} — too few to say anything."
    mx, my = _mean([p[0] for p in pairs]), _mean([p[1] for p in pairs])
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    syy = sum((b - my) ** 2 for _, b in pairs)
    if sxx == 0 or syy == 0:
        return f"One of the columns never changes, so no correlation exists. (n={n})"
    r = sxy / math.sqrt(sxx * syy)
    strength = ("very weak" if abs(r) < 0.2 else "weak" if abs(r) < 0.4
                else "moderate" if abs(r) < 0.6 else "strong" if abs(r) < 0.8
                else "very strong")
    direction = "rises with" if r > 0 else "falls as"
    return (f"{x} {direction} {y}: r = {r:+.3f} ({strength}, n={n})\n"
            f"  r² = {r * r:.3f} — {100 * r * r:.0f}% of the variation in {y} tracks "
            f"{x} linearly; the rest is everything else.\n"
            f"  This is association, not cause. To argue cause you need a mechanism, "
            f"a time order, and a way to rule out the third variable.")


def outliers(path: str = "", column: str = "") -> str:
    """The IQR rule — stated, because 'outlier' means different things to people."""
    try:
        _, rows = _load(path)
    except Exception as exc:
        return f"I could not read that: {exc}"
    vals = _numbers(rows, column)
    if len(vals) < 5:
        return f"Only {len(vals)} numbers in {column!r} — not enough to call anything an outlier."
    s = sorted(vals)
    q1 = s[len(s) // 4]
    q3 = s[(3 * len(s)) // 4]
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    found = [v for v in s if v < low or v > high]
    lines = [f"{column}: {len(vals)} values · Q1 {q1:,.2f} · Q3 {q3:,.2f} · IQR {iqr:,.2f}",
             f"Fence: below {low:,.2f} or above {high:,.2f} (1.5 × IQR, the usual rule)"]
    if found:
        lines.append(f"{len(found)} outside: " + ", ".join(f"{v:,.2f}" for v in found[:12])
                     + (" …" if len(found) > 12 else ""))
        lines.append("Check them before deleting: a genuine record is not an error.")
    else:
        lines.append("Nothing outside the fence.")
    return "\n".join(lines)


def groupby(path: str = "", key: str = "", value: str = "", agg: str = "sum") -> str:
    """Totals or averages per group, sorted. Shows the group sizes too."""
    try:
        _, rows = _load(path)
    except Exception as exc:
        return f"I could not read that: {exc}"
    if not key:
        return "Name the grouping column, e.g. 'group sales.csv by city sum revenue'."
    buckets: dict[str, list[float]] = {}
    for r in rows:
        k = str(r.get(key, "")).strip() or "(blank)"
        v = _num(r.get(value)) if value else 1.0
        if v is None:
            continue
        buckets.setdefault(k, []).append(v)
    if not buckets:
        return f"No numeric values found for {value or 'count'}."
    rows_out = []
    for k, xs in buckets.items():
        amount = sum(xs) if agg.lower() != "mean" else _mean(xs)
        rows_out.append((amount, k, len(xs)))
    rows_out.sort(reverse=True)
    head = f"{key} → {'sum' if agg.lower() != 'mean' else 'mean'} of {value or 'rows'}"
    lines = [head]
    for amount, k, count in rows_out[:15]:
        lines.append(f"  {str(k)[:24]:<24} {amount:>14,.2f}   (n={count})")
    if len(rows_out) > 15:
        lines.append(f"  … {len(rows_out) - 15} more groups")
    return "\n".join(lines)


def trend(path: str = "", value: str = "", periods: int = 0) -> str:
    """Least-squares slope through the values in file order (or by a date column)."""
    try:
        _, rows = _load(path)
    except Exception as exc:
        return f"I could not read that: {exc}"
    vals = _numbers(rows, value)
    if len(vals) < 4:
        return f"Only {len(vals)} values in {value!r}; a trend needs at least 4."
    xs = list(range(len(vals)))
    mx, my = _mean(xs), _mean(vals)
    sxx = sum((a - mx) ** 2 for a in xs)
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, vals))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_tot = sum((b - my) ** 2 for b in vals)
    ss_res = sum((b - (intercept + slope * a)) ** 2 for a, b in zip(xs, vals))
    r2 = 0.0 if ss_tot == 0 else 1 - ss_res / ss_tot
    lines = [f"{value}: slope {slope:+,.3f} per row over {len(vals)} rows "
             f"(r² {r2:.3f})",
             f"  from about {vals[0]:,.2f} to {vals[-1]:,.2f}"]
    if periods and int(periods) > 0:
        lines.append(f"  mechanical projection {int(periods)} rows ahead: "
                     f"{intercept + slope * (len(vals) - 1 + int(periods)):,.2f}")
        lines.append("  That projection is a straight line, not a forecast. If r² is "
                     "low, it is arithmetic cosplay — use it only as a baseline.")
    return "\n".join(lines)


def report(path: str = "") -> str:
    """Everything above, in one pass: the fastest way to understand a new file."""
    try:
        cols, rows = _load(path)
    except Exception as exc:
        return f"I could not read that: {exc}"
    parts = [profile(path)]
    numeric = [c for c in cols if len(_numbers(rows, c)) >= max(3, len(rows) // 2)]
    if len(numeric) >= 2:
        parts.append("\nStrongest pair correlations (only when |r| ≥ 0.3):")
        best = []
        for i, a in enumerate(numeric[:8]):
            for b in numeric[:8][i + 1:]:
                try:
                    text = correlate(path, a, b)
                except Exception:
                    continue
                if "r = +0." in text or "r = -0." in text:
                    try:
                        r = float(text.split("r = ")[1].split(" ")[0])
                    except Exception:
                        continue
                    if abs(r) >= 0.3:
                        best.append((abs(r), a, b, r))
        best.sort(reverse=True)
        for _, a, b, r in best[:5]:
            parts.append(f"  · {a} ↔ {b}: r = {r:+.3f}")
        if not best:
            parts.append("  nothing above 0.3 — the file is not telling one simple story")
    return "\n".join(parts)
