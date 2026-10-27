"""Travel and craft — real coordinates, real colour maths, valid SVG.

Two things get checked here that are easy to fake and easy to get wrong: distance
(a wrong haversine puts a day trip 300 km off) and colour contrast (a palette that
looks fine on the maker's monitor and unreadable on a phone).

Run:  python tests/test_travel_craft.py
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arcdesk import craft, travel  # noqa: E402

ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<52} {str(got)[:50]!r}")
    ok &= bool(good)


print("1) the dataset is real data, not stubs")
check("places loaded", len(travel.PLACES) >= 60, True)
check("every place has 9 fields", all(len(p) == 9 for p in travel.PLACES), True)
check("coordinates are plausible",
      all(-90 <= p[1] <= 90 and -180 <= p[2] <= 180 for p in travel.PLACES), True)
check("no duplicate names", len({p[0] for p in travel.PLACES}) == len(travel.PLACES), True)
check("every place has tags", all(p[4] for p in travel.PLACES), True)
check("Belagavi present", "Belagavi" in travel.INDEX, True)

print("2) distance is haversine, and roughly right")
km = travel.haversine_km(15.8497, 74.4977, 15.3350, 76.4600)   # Belagavi → Hampi
check("Belagavi → Hampi is 200-240 km", 200 <= km <= 240, True)
zero = travel.haversine_km(12.0, 77.0, 12.0, 77.0)
check("same point is 0 km", round(zero, 6), 0.0)
text = travel.distance("Belagavi", "Hampi")
check("distance text names both", "Belagavi" in text and "Hampi" in text, True)
check("it says straight line", "straight line" in text, True)
check("unknown place is admitted", "do not have coordinates" in travel.distance("Atlantis", "Hampi"), True)

print("3) map links are real and need no key")
link = travel.map_link("Hampi")
check("openstreetmap", "openstreetmap.org" in link, True)
check("has the latitude", "15.33" in link, True)
check("no api key", "key=" not in link, True)
check("unknown place falls back to search",
      "search?query=" in travel.map_link("Some Village Nowhere"), True)

print("4) near() computes from coordinates")
near = travel.near("Belagavi", 200, "heritage")
check("Badami is within 200 km", "Badami" in near, True)
check("Pattadakal too", "Pattadakal" in near, True)
check("states the radius", "200 km" in near, True)
check("no tag clutter", "tier" not in near.lower(), True)
check("too small a radius is honest", "Nothing within 5 km" in travel.near("Hampi", 5), True)

print("5) itinerary does not repeat a place on two days")
it = travel.itinerary("Coorg (Madikeri)", 3, "slow")
picks = re.findall(r"· (\w[\w ()]*?) \(\d+ km\)", it)
check("some places chosen", len(picks) >= 2, True)
check("no repeats", len(picks) == len(set(picks)), True)
check("map link included", "openstreetmap" in it, True)
check("it admits no live timings", "do not have live timings" in it, True)

print("6) budget is a band and says so")
b = travel.budget(3, 2, 2, 6000)
check("labelled a planning band", "planning band" in b, True)
check("not a quotation", "not a quotation" in b, True)
check("the arithmetic is right", "24,000" in b, True)     # 4000 × 3 × 2

print("7) colour maths is measured, not eyeballed")
pal = craft.palette("#48f2ff", "triad")
check("five roles listed", sum(role in pal for role in
                               ("background", "surface", "primary", "accent", "ink")) == 5, True)
check("contrast is printed", "contrast vs background" in pal, True)
check("passes AA", "passes WCAG AA" in pal, True)
check("white on dark is high contrast",
      craft.contrast_ratio("#000000", "#ffffff") > 20, True)
check("same colour is 1:1", round(craft.contrast_ratio("#777777", "#777777"), 2), 1.0)

print("8) SVG output is well formed and writes new files")
for name, svg in (("poster", craft.poster("ARC", "test", "#48f2ff")),
                  ("kolam", craft.kolam(5, "#f4d06f", 7)),
                  ("border", craft.border("kolam", 300, "#f4d06f")),
                  ("monogram", craft.monogram("ARC", "#48f2ff"))):
    check(f"{name} is svg", svg.startswith("<svg") and svg.rstrip().endswith("</svg>"), True)
    check(f"{name} has geometry", len(svg) > 300, True)
same = craft.kolam(5, "#f4d06f", 7) == craft.kolam(5, "#f4d06f", 7)
different = craft.kolam(5, "#f4d06f", 7) != craft.kolam(5, "#f4d06f", 8)
check("kolam seed is reproducible", same, True)
check("a different seed differs", different, True)
first = craft.save(craft.poster("ARC"), "probe poster")
second = craft.save(craft.poster("ARC"), "probe poster")
check("saves are new files, never overwrites", first != second, True)

print("\nPASS" if ok else "\nFAIL")
raise SystemExit(0 if ok else 1)
