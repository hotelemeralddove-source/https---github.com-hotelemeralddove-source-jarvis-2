"""Hotel, resort and restaurant management — the arithmetic owners actually run on.

Occupancy, ADR, RevPAR, TRevPAR and GOPPAR are not opinions: they are divisions.
This module does them properly, shows each formula, and refuses to invent the
inputs. Where a number depends on your property (staff cost, commission, OTA share),
it stays a variable you supply.

Checklists here are operational SOPs — housekeeping turnaround, front desk, F&B
opening — written to be printed and ticked, not admired.
"""
from __future__ import annotations


def _f(value) -> float:
    try:
        return max(0.0, float(value))
    except Exception:
        return 0.0


def kpis(rooms: int = 0, sold: int = 0, room_revenue: float = 0,
         other_revenue: float = 0, costs: float = 0) -> str:
    """The five numbers every owner should know by heart, computed honestly."""
    nights = _f(rooms)
    occupied = _f(sold)
    if nights <= 0:
        return ("Give me the room count and rooms sold, e.g. 'hotel kpi 24 rooms "
                "17 sold 42500 revenue'.")
    occ = 100 * occupied / nights
    adr = room_revenue / occupied if occupied else 0.0
    revpar = room_revenue / nights
    trevpar = (room_revenue + other_revenue) / nights
    goppar = (room_revenue + other_revenue - costs) / nights
    lines = [f"Occupancy: {occ:.1f}%   (rooms sold {occupied:.0f} ÷ {nights:.0f} available)",
             f"ADR: {adr:,.2f}   (room revenue ÷ rooms sold)" if occupied
             else "ADR: not computable — no rooms sold",
             f"RevPAR: {revpar:,.2f}   (room revenue ÷ rooms available)",
             f"TRevPAR: {trevpar:,.2f}   (all revenue ÷ rooms available)"]
    if costs:
        lines.append(f"GOPPAR: {goppar:,.2f}   ((revenue − costs) ÷ rooms available)")
        if room_revenue + other_revenue > 0:
            lines.append(f"Total gross margin: "
                         f"{100 * (room_revenue + other_revenue - costs) / (room_revenue + other_revenue):.1f}%")
    else:
        lines.append("GOPPAR: needs your costs — give them and I will compute it.")
    lines += ["",
              "Read them in this order: occupancy, then ADR, then RevPAR. Chasing "
              "occupancy with discounts raises the first and lowers the third — "
              "RevPAR is the one that pays salaries.",
              "Rule of thumb worth checking against your own books: dropping ADR by "
              "10% needs roughly 11% more rooms sold just to stand still."]
    return "\n".join(lines)


def rate_calendar(base_rate: float = 0, weekend_uplift: float = 0.20,
                  season_uplift: float = 0.0) -> str:
    """Suggested rate ladder. Suggestions, labelled as suggestions."""
    base = _f(base_rate) or 2000.0
    wk = base * (1 + weekend_uplift)
    season = wk * (1 + season_uplift)
    rows = [("Mon-Thu", base), ("Fri-Sat", wk), ("Peak season weekend", season),
            ("Long weekend (3+ nights, 4 weeks out)", wk * 0.95)]
    lines = ["Rate ladder (starting point, not a market price — your own pickup "
             "data decides)"]
    for label, rate in rows:
        lines.append(f"  {label:<42} {rate:,.0f}")
    lines += ["",
              "How to use it: publish the ladder, then watch pickup for two weeks. "
              "If a night sells out more than 14 days early, that rate was too low. "
              "If it sits empty inside 7 days, it was too high — not the season's fault.",
              "Never discount the rack rate publicly; move the value instead "
              "(breakfast, late checkout, airport drop). Public discounts teach "
              "customers to wait."]
    return "\n".join(lines)


def menu_cost(items: str = "", target_food_cost: float = 30.0) -> str:
    """Recipe costing from 'name qty*price' lines. Real maths, real warning."""
    raw = [line.strip() for line in (items or "").split(";") if line.strip()]
    if not raw:
        return ("Give the ingredients with quantities and prices: "
                "'rice 2*60; dal 1*110; oil 0.2*180; gas 1*25' — then a selling price.")
    total = 0.0
    lines = ["Ingredient cost"]
    for line in raw:
        qty_bits = line.rsplit(None, 1)
        try:
            qty_price = qty_bits[-1].split("*")
            qty, price = float(qty_price[0]), float(qty_price[1])
            name = " ".join(qty_bits[:-1]) or "item"
        except Exception:
            lines.append(f"  ?  {line}  → use 'name 2*60'")
            continue
        cost = qty * price
        total += cost
        lines.append(f"  {name:<20} {qty:g} × {price:,.2f} = {cost:,.2f}")
    lines.append(f"  {'TOTAL':<20} {total:,.2f}")
    if target_food_cost > 0:
        minimum = total / (target_food_cost / 100)
        lines += ["",
                  f"At a {target_food_cost:.0f}% food cost target the plate must sell "
                  f"at {minimum:,.0f} or more.",
                  f"  · at {minimum:,.0f}: food cost {target_food_cost:.0f}%",
                  f"  · at {minimum * 1.2:,.0f}: food cost "
                  f"{100 * total / (minimum * 1.2):.0f}%"]
    lines += ["",
              "Do not forget the costs that are not on the plate: gas, staff time, "
              "wastage, and the 15-25% a delivery platform keeps. Those live in the "
              "price, not in this ingredient sum."]
    return "\n".join(lines)


SOP = {
    "housekeeping": ["Strip and inspect linen under light — stains the guest sees are "
                     "the ones you missed",
                     "Bathroom first, then bed, then surfaces: dirt travels outward",
                     "Restock to the standard card, count it, not 'looks fine'",
                     "Photograph anything damaged before reporting it",
                     "Final check at the door: mirror, floor corners, remote, smell",
                     "Mark the room ready in the system only after that check"],
    "frontdesk": ["Confirm name, nights, rate and breakfast before handing the key",
                  "Take an ID and a phone number that actually rings",
                  "Explain Wi-Fi, checkout time and one local recommendation",
                  "Log every special request where the next shift will see it",
                  "Night shift: reconcile payments, check arrivals for tomorrow, "
                  "note anything broken for maintenance"],
    "fnb": ["Taste one dish from every section at the start of service",
            "Check the chiller temperature and write the number down",
            "Count the cash float before the doors open, not after",
            "Note the three things that ran out — that is tomorrow's prep list",
            "Close: clean, cover, label, date, refrigerate"],
    "maintenance": ["Water, power, gas and internet: test all four every morning",
                    "Keep one spare of every consumable that stops a room selling",
                    "Log the fix, the cost and who did it",
                    "Walk the property once a week as if you were a guest with a camera"],
}


def sop(department: str = "housekeeping") -> str:
    key = (department or "housekeeping").lower().strip()
    steps = SOP.get(key)
    if not steps:
        return ("I have SOPs for: " + ", ".join(SOP) +
                ". Say 'hotel sop frontdesk'.")
    return f"{key.upper()} · standard operating procedure\n" + "\n".join(
        f"  ☐ {s}" for s in steps) + "\n\nPrint it, tick it, date it. An SOP nobody " \
        "signs is a suggestion."


JOURNEY = {
    "before": ["Booking confirmation within 5 minutes, with directions in the local language",
               "One message 48 h before: arrival time, weather, what to pack",
               "Answer the 'is there parking' question before it is asked",
               "Upsell once, gently, with a photo and a price"],
    "arrival": ["Name on arrival, not 'booking ID please'",
                "Room shown, not just handed over",
                "One question: 'what brings you here?' — it changes the whole stay",
                "Wi-Fi and checkout time spoken aloud, not pointed at a card"],
    "during": ["One genuine check-in on day 2, not a survey",
               "Fix problems within the hour, and say when it will be fixed",
               "Recommend one thing a local would actually do",
               "Remember one detail and use it once"],
    "after": ["Thank-you message within 24 h, no template smell",
              "Ask for the review only if the stay went well; ask for feedback if not",
              "Add a reason to come back that is not a discount",
              "Log what they liked — that is your best marketing research"],
}


def guest_journey(stage: str = "") -> str:
    key = (stage or "").lower().strip()
    if key in JOURNEY:
        return f"{key.upper()}\n" + "\n".join(f"  ☐ {s}" for s in JOURNEY[key])
    return "\n\n".join(f"{k.upper()}\n" + "\n".join(f"  ☐ {s}" for s in v)
                       for k, v in JOURNEY.items())
