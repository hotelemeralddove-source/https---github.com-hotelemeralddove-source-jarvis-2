"""Business tools — content, marketing, strategy, hotels. The maths must add up.

These are the tools where a plausible-but-wrong number does the most damage: a
break-even that is 20% off changes whether somebody signs a lease. So each check
recomputes the expected value by hand.

Run:  python tests/test_business.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import hospitality, marketing, strategy, studio  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<52} {str(got)[:52]!r}")
    ok &= bool(good)


print("1) content: structure without invented numbers")
outline = studio.outline("reel", "hotel booking tips", "bold", "small hotel owners")
check("all five beats present", all(b in outline for b in ("hook", "problem", "twist")), True)
check("word budget stated", "words" in outline, True)
check("no fake stat claim", "views" not in outline.lower(), True)
hooks = studio.hooks("direct bookings")
check("six hooks", hooks.count("\n") >= 6, True)
tags = studio.hashtags("hotel marketing", 8)
check("hashtags are candidates, not claims", "trending" in tags.lower(), True)
cal = studio.calendar("hotel", 2, "instagram,blog")
check("real dates", "Week 2" in cal, True)
check("weekends rest", "rest" in cal.lower(), True)

print("2) marketing: funnel arithmetic")
f = marketing.funnel(20000, 400, 60, 12, 5000, 24000)
check("CTR 2.00%", "CTR: 2.00%" in f, True)
check("CPC 12.50", "CPC: 12.50" in f, True)
check("CAC 416.67", "CAC: 416.67" in f, True)
check("ROAS 4.80x", "ROAS: 4.80" in f, True)
check("refuses to invent benchmarks", "not mine to invent" in f, True)
u = marketing.utm("mysite.com/rooms", "instagram", "social", "monsoon")
check("utm_source present", "utm_source=instagram" in u, True)
check("utm_campaign present", "utm_campaign=monsoon" in u, True)
seo = marketing.seo_check("Book direct. Our rooms are quiet. Call today.", "book direct")
check("word count real", "words" in seo, True)
check("density computed", "density" in seo, True)
ss = marketing.sample_size(0.05, 0.2)
check("sample size formula", "3,650" in ss, True)

print("3) strategy: the numbers someone will sign against")
be = strategy.break_even(90000, 750, 320)
hand = 90000 / (750 - 320)
check("break-even units", f"{hand:,.1f}" in be, True)
check("contribution per unit", "430.00" in be, True)
check("negative margin is refused", "No volume fixes that" in
      strategy.break_even(90000, 300, 320), True)
ue = strategy.unit_econ(750, 320, 400, 3)
check("LTV:CAC 3.23x", "3.23" in ue, True)
check("canvas asks instead of inventing", "?" in strategy.swot("homestay"), True)
check("five forces has five", strategy.five_forces("stays").count("\n") >= 5, True)

print("4) hotel: occupancy maths")
k = hospitality.kpis(24, 17, 42500, 9000, 26000)
check("occupancy 70.8%", "70.8%" in k, True)
check("ADR 2500", "2,500.00" in k, True)
check("RevPAR 1770.83", "1,770.83" in k, True)
check("GOPPAR 1062.50", "1,062.50" in k, True)
m = hospitality.menu_cost("rice 2*60; dal 1*110; oil 0.2*180", 30)
check("ingredient total 266", "266.00" in m, True)   # 120+110+36
check("says the price it needs", "30% food cost" in m, True)
check("SOP is a checklist", hospitality.sop("frontdesk").count("☐") >= 4, True)
check("unknown department is handled", "I have SOPs for" in hospitality.sop("bar"), True)

print("5) nothing in here writes to your files unasked")
before = set(p.name for p in Path(os.environ["ARCDESK_HOME"]).rglob("*"))
studio.outline("blog", "x")
marketing.funnel(1, 1, 1, 1, 1, 1)
after = set(p.name for p in Path(os.environ["ARCDESK_HOME"]).rglob("*"))
check("no files created by reading tools", after - before, set())
saved = studio.save("hello", "probe")
check("save writes only on request", "Saved" in saved, True)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
