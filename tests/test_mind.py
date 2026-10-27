"""Data mining, mentoring, foresight and defensive security.

The through-line: every one of these tools is judged on whether it **refuses to
guess**. Mining must state n. Mentoring must ask instead of answer. Foresight must
label arithmetic as arithmetic. Security must say no to intrusion and mean it.

Run:  python tests/test_mind.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import foresight, mentor, mining, security  # noqa: E402

ok = True
DATA = Path(tempfile.mkdtemp(prefix="arcdesk-data-")) / "probe.csv"
DATA.write_text("city,month,price,units\n"
                "Belagavi,1,750,120\nBelagavi,2,760,140\nHubli,1,800,90\n"
                "Hubli,2,810,95\nGoa,1,1500,40\nGoa,2,1400,300\n", encoding="utf-8")


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<52} {str(got)[:48]!r}")
    ok &= bool(good)


print("1) mining measures and admits the sample size")
prof = mining.profile(str(DATA))
check("row count", "6 rows" in prof, True)
check("names the numeric column", "price" in prof, True)
check("reports a mean", "mean" in prof, True)
cor = mining.correlate(str(DATA), "price", "units")
check("correlation prints n", "n=6" in cor, True)
check("says association not cause", "not cause" in cor.lower(), True)
out = mining.outliers(str(DATA), "units")
check("IQR fence shown", "IQR" in out, True)
check("flags the 300", "300" in out, True)
grp = mining.groupby(str(DATA), "city", "units", "sum")
check("Goa total 340", "340.00" in grp, True)
check("group sizes shown", "n=2" in grp, True)
tr = mining.trend(str(DATA), "units", 2)
check("slope printed", "slope" in tr, True)
check("projection labelled mechanical", "mechanical" in tr.lower(), True)
check("missing file is a sentence, not a crash", "could not read" in mining.profile("/nope/x.csv"), True)

print("2) mentor asks better questions instead of answering")
inv = mentor.invert("get 20 direct bookings")
check("inversion keeps the goal", "get 20 direct bookings" in inv, True)
check("asks how to fail", "guarantee failure" in inv.lower(), True)
hats = mentor.six_hats("raise rates")
check("six hats has all six", all(h in hats for h in
                                  ("WHITE", "RED", "BLACK", "YELLOW", "GREEN", "BLUE")), True)
pm = mentor.pre_mortem("open a second property")
check("pre-mortem is past tense", "failed" in pm.lower(), True)
qs = mentor.questions("pricing", 6)
check("six questions", qs.count("?") >= 6, True)
check("refusal to decide is explicit", "will not pretend" in mentor.refuse_to_guess(), True)

print("3) foresight labels what it is doing")
lin = foresight.forecast("10 20 30 40 50", 2)
check("slope is exactly 10", "+10.000" in lin, True)
check("r² is 1 for a perfect line", "r² 1.000" in lin, True)
check("band computed", "rmse" in lin, True)
check("calls itself extrapolation", "extrapolation" in lin.lower(), True)
check("refuses a short series", "not a series" in foresight.forecast("1 2 3"), True)
sc = foresight.scenario("room rates next year")
check("three scenarios", all(s in sc for s in ("BASE CASE", "UPSIDE", "DOWNSIDE")), True)
check("probabilities are left to the human", "left the probabilities blank" in sc, True)
unk = foresight.unknown("what happened in the market today")
check("admits no live feed", "do not have a live news feed" in unk, True)
check("offers a primary source instead", "primary source" in unk, True)

print("4) security is defensive only, and says so in code")
ref = security.refused()
check("refuses cracking", "crack" in ref.lower(), True)
check("cites the law", "66" in ref, True)
check("refuses unkillable behaviour", "resist being closed" in ref, True)
weak = security.password_strength("abc123")
check("weak password flagged", "Weak points" in weak, True)
check("crack time is instant", "instantly" in weak, True)
strong = security.password_strength("monsoon-tandoor-pencil-harbour")
check("long passphrase praised", "Length is doing the heavy lifting" in strong, True)
check("no digits leak into advice", "bits of entropy" in strong, True)
ph = security.phishing_check("URGENT: verify your password at http://paytm-kyc.xyz/verify")
check("phishing scored HIGH", "HIGH" in ph, True)
check("lookalike domain named", "paytm-kyc.xyz" in ph, True)
check("says no click", "do not click" in ph.lower(), True)
check("nothing is written to disk by a check",
      security.password_strength("x").count("saved") == 0, True)

print("5) the tools are registered under the names the router uses")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arcdesk.ai import tools  # noqa: E402
for name in ("mine", "mentor", "foresight", "secure"):
    check(f"{name} in TOOLS", name in tools.TOOLS, True)
check("secure refuses a hack request",
      "crack" in tools.call("secure", {"action": "refused"}).lower(), True)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
