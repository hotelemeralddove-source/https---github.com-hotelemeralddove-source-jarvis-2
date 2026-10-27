"""Market maths must be exact, and market talk must never become a promise.

Two separate risks, two sets of checks:

  1. **Arithmetic that is wrong.** A position size is a formula. If it is off by a
     decimal the user risks ten times what they intended, so these numbers are
     asserted exactly rather than approximately.
  2. **Language that pretends to know the future.** The module may describe
     momentum; it may not say "buy", "guaranteed", "will reach". Those phrases are
     searched for and the test fails if they appear.

Network rows skip instead of failing when offline — an offline laptop is a
supported configuration, not a bug.

Run:  python tests/test_market.py
"""
from __future__ import annotations

import os
import re
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import market as M  # noqa: E402

PASS = 0
FAIL = 0
SKIP = 0

# words that turn information into advice, or confidence into a lie
FORBIDDEN = [
    r"you should (buy|sell|invest)",
    r"guarantee(d)?",
    r"risk[- ]free",
    r"will definitely",
    r"can't lose",
    r"sure (thing|shot)",
    r"assured returns?",
]


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    if ok:
        PASS += 1
    else:
        FAIL += 1


def skip(label: str, why: str) -> None:
    global SKIP
    print(f"   SKIP {label}   [{why}]")
    SKIP += 1


def online() -> bool:
    try:
        socket.create_connection(("query1.finance.yahoo.com", 443), timeout=4).close()
        return True
    except Exception:
        return False


def no_advice(text: str) -> bool:
    low = text.lower()
    return not any(re.search(pattern, low) for pattern in FORBIDDEN)


def main() -> int:
    print("market — exact arithmetic, honest language\n")
    net = online()

    # 1. maths ------------------------------------------------------------
    print("1. indicators")
    rising = [100 + i for i in range(60)]
    falling = [160 - i for i in range(60)]
    check("sma(20) of a straight line", M.sma(rising, 20) == sum(rising[-20:]) / 20)
    check("sma of too few values is None", M.sma([1, 2], 20) is None)
    check("rsi of a rising series = 100", M.rsi(rising) == 100.0, str(M.rsi(rising)))
    check("rsi of a falling series = 0", M.rsi(falling) == 0.0, str(M.rsi(falling)))
    check("rsi needs enough data", M.rsi([1, 2, 3]) is None)
    check("volatility of a flat line is 0", M.volatility([100.0] * 30) == 0.0)
    check("volatility is positive when it moves",
          (M.volatility([100, 105, 95, 110, 90] * 6) or 0) > 0)
    check("drawdown of a fall from 100 to 50", M.drawdown([100, 80, 50, 60]) == -50.0,
          str(M.drawdown([100, 80, 50, 60])))

    # 2. position sizing ---------------------------------------------------
    # capital 100000, risk 1% = 1000. entry 100, stop 96 → 4 per unit → 250 units.
    print("\n2. position sizing (the part that is pure arithmetic)")
    size = M.position_size(100_000, 1.0, 100.0, 96.0)
    check("risk budget = 1000", size.get("risk_amount") == 1000.0, str(size.get("risk_amount")))
    check("risk per unit = 4", size.get("per_unit_risk") == 4.0, str(size.get("per_unit_risk")))
    check("units = 250", size.get("units") == 250, str(size.get("units")))
    check("exposure = 25000", size.get("exposure") == 25_000.0, str(size.get("exposure")))
    check("exposure is 25% of capital", size.get("exposure_pct") == 25.0)
    check("2R target = 108", size.get("r_multiple_at_2R") == 108.0)

    tight = M.position_size(100_000, 1.0, 100.0, 99.0)
    check("a 1% stop doubles the size to 1000 units", tight.get("units") == 1000,
          str(tight.get("units")))
    check("a zero stop is refused", M.position_size(100_000, 1.0, 100.0, 0)["ok"] is False)
    check("a stop equal to entry is refused",
          M.position_size(100_000, 1.0, 100.0, 100.0)["ok"] is False)
    check("zero capital is refused", M.position_size(0, 1.0, 100.0, 96.0)["ok"] is False)
    check("risk above capital is allowed but capped by units",
          M.position_size(1000, 100.0, 100.0, 50.0).get("units") == 20,
          str(M.position_size(1000, 100.0, 100.0, 50.0).get("units")))

    # 3. screening ---------------------------------------------------------
    print("\n3. screener refuses nonsense")
    bad = M.screen(["X"], rule="make me rich")
    check("unknown rule is an error", bad.startswith("ERROR"), bad[:40])

    # 4. language ----------------------------------------------------------
    print("\n4. language never becomes advice")
    for label, text in (("screen (offline)", M.screen([], rule="uptrend")),
                        ("brief (offline)", M.brief())):
        check(f"{label}: no forbidden phrases", no_advice(text))
        check(f"{label}: carries the disclaimer", "not investment advice" in text.lower())

    # 5. network rows ------------------------------------------------------
    print("\n5. live data (skipped when offline)")
    if net:
        analysis = M.analyse("RELIANCE")
        check("analyse returns a trend", "trend:" in analysis.lower(),
              analysis.splitlines()[1][:44] if "\n" in analysis else "")
        check("analyse carries the disclaimer", "not investment advice" in analysis.lower())
        check("analyse states the volatility caveat", "momentum, not the future" in analysis)
        check("analyse has no forbidden phrases", no_advice(analysis))
        plan = M.plan("RELIANCE", 100_000, 1.0, 4.0)
        check("plan shows units and exposure", "units" in plan and "exposure" in plan)
        check("plan says the stop will be hit sometimes", "noise" in plan)
        store = _tmp_watch()
        quote = M.watchlist("add", "RELIANCE", path=store)
        check("watchlist add works", "watching RELIANCE" in quote, quote[:40])
        listing = M.watchlist("list", path=store)
        check("watchlist lists the symbol", "reliance" in listing.lower())
        check("watchlist list carries the disclaimer", "not investment advice" in listing.lower())
    else:
        skip("live analysis", "no internet")
        offline = M.analyse("RELIANCE")
        check("offline analyse refuses instead of guessing",
              offline.startswith("ERROR") and "internet" in offline.lower(), offline[:44])

    print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'} — {PASS} passed, {FAIL} failed, {SKIP} skipped")
    return 1 if FAIL else 0


def _tmp_watch():
    import tempfile
    from pathlib import Path
    return Path(tempfile.mkdtemp(prefix="arcdesk-watch-")) / "watchlist.json"


if __name__ == "__main__":
    sys.exit(main())
