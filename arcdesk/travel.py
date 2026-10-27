"""Travel ideas, a place finder and map links — a real dataset, not vibes.

Every place here carries its own latitude and longitude, so "what is near me" is a
haversine calculation, and "show me on a map" is a real OpenStreetMap link that
needs no key, no account and no internet from ARC itself — your browser opens it.

Honesty rules for this module:

  * coordinates are **place centroids** (the town or the monument), good to a few
    hundred metres — the map link is the authority, and the answer says so;
  * "best months" is seasonal guidance for the region, not a weather forecast;
  * the money range is a **planning band by tier**, not a quotation, and it says so;
  * nothing here is sponsored, ranked by payment, or scraped from a booking site.
"""
from __future__ import annotations

import math

# name, lat, lon, region, tags, best months, suggested days, tier (1 cheap, 3 premium)
PLACES: tuple[tuple, ...] = (
    # ---------------------------------------------------------------- Karnataka
    ("Belagavi", 15.8497, 74.4977, "Karnataka, India", ("hills", "history", "city"),
     "Oct-Mar", 2, 1, "Fort, old markets, and the best base for the Badami belt"),
    ("Hampi", 15.3350, 76.4600, "Karnataka, India", ("heritage", "history", "photography"),
     "Nov-Feb", 3, 2, "Vijayanagara ruins across a boulder landscape; sunrise at Matanga"),
    ("Badami", 15.9167, 75.6833, "Karnataka, India", ("heritage", "caves", "history"),
     "Nov-Feb", 1, 1, "Rock-cut cave temples above an Agastya lake tank"),
    ("Pattadakal", 15.9485, 75.8156, "Karnataka, India", ("heritage", "unesco"),
     "Nov-Feb", 1, 1, "UNESCO Chalukyan temple group, quiet, 22 km from Badami"),
    ("Aihole", 15.9404, 75.8815, "Karnataka, India", ("heritage", "history"),
     "Nov-Feb", 1, 1, "Over a hundred early temples in one village"),
    ("Gokak Falls", 16.1667, 74.8167, "Karnataka, India", ("waterfall", "monsoon"),
     "Jul-Jan", 1, 1, "Wide falls over sandstone, with a 19th-century suspension bridge"),
    ("Gokarna", 14.5479, 74.3188, "Karnataka, India", ("beach", "temple", "backpack"),
     "Nov-Feb", 3, 1, "Temple town on one side, cliff beaches on the other"),
    ("Murudeshwar", 14.0944, 74.4845, "Karnataka, India", ("temple", "beach"),
     "Oct-Mar", 1, 2, "Shiva statue over the sea; scuba and snorkel operators nearby"),
    ("Jog Falls", 14.2280, 74.7967, "Karnataka, India", ("waterfall", "monsoon"),
     "Jul-Sep (full), Nov-Jan (clear)", 1, 1, "Sharavathi falling in four streams"),
    ("Coorg (Madikeri)", 12.4244, 75.7382, "Karnataka, India", ("hills", "coffee", "rain"),
     "Oct-Mar", 3, 2, "Coffee estates, mist mornings, Abbey and Raja's Seat"),
    ("Chikmagalur", 13.3161, 75.7720, "Karnataka, India", ("hills", "coffee", "trek"),
     "Sep-Feb", 2, 2, "Mullayanagiri, Hebbe Falls, estate stays"),
    ("Sakleshpur", 12.9417, 75.7850, "Karnataka, India", ("hills", "rain", "railway"),
     "Sep-Feb", 2, 1, "Green route trek along the rail line, plantation stays"),
    ("Kemmanagundi", 13.4420, 75.7560, "Karnataka, India", ("hills", "garden"),
     "Sep-Feb", 1, 1, "Rose garden and Hebbe Falls above Chikmagalur"),
    ("Kudremukh", 13.1296, 75.2558, "Karnataka, India", ("trek", "hills", "wildlife"),
     "Oct-Feb", 2, 1, "Trek through shola grassland; permits matter here, check locally"),
    ("Dandeli", 15.2459, 74.6200, "Karnataka, India", ("rafting", "wildlife", "forest"),
     "Oct-Mar", 2, 2, "White-water rafting on the Kali, plus coracle and jungle camps"),
    ("Kabini", 11.9375, 76.2700, "Karnataka, India", ("wildlife", "safari"),
     "Oct-May", 2, 3, "Best odds of a tiger sighting by water; book safari early"),
    ("Bandipur", 11.6667, 76.6333, "Karnataka, India", ("wildlife", "safari", "forest"),
     "Oct-May", 2, 2, "Dry deciduous forest, elephants on the Ooty road at dusk"),
    ("Nagarhole", 12.0000, 76.2000, "Karnataka, India", ("wildlife", "forest"),
     "Oct-May", 2, 2, "Coracle safaris and dense forest; quieter than Bandipur"),
    ("Mysuru", 12.2958, 76.6394, "Karnataka, India", ("heritage", "city", "food"),
     "Oct-Feb", 2, 2, "Palace, Devaraja Market, and the cleanest city walks in India"),
    ("Srirangapatna", 12.4234, 76.6880, "Karnataka, India", ("heritage", "history"),
     "Oct-Feb", 1, 1, "Tipu's island fort and the river ghats, 15 km from Mysuru"),
    ("Shravanabelagola", 12.8600, 76.4900, "Karnataka, India", ("pilgrimage", "heritage"),
     "Oct-Feb", 1, 1, "614 steps to the Bahubali monolith; bare feet, early start"),
    ("Udupi", 13.3409, 74.7421, "Karnataka, India", ("temple", "food", "beach"),
     "Oct-Mar", 2, 1, "Krishna temple and the food culture that came out of it"),
    ("Malpe", 13.3494, 74.7030, "Karnataka, India", ("beach", "island", "food"),
     "Oct-Mar", 1, 1, "Boats to St Mary's Island basalt columns; fish thali at the port"),
    ("Mangaluru", 12.9141, 74.8560, "Karnataka, India", ("city", "beach", "food"),
     "Oct-Mar", 2, 2, "Neer dosa, ice-cream parlours, temples and a working port"),
    ("Karkala", 13.2167, 74.9833, "Karnataka, India", ("heritage", "pilgrimage"),
     "Oct-Feb", 1, 1, "42-foot Gommateshwara on a granite hill"),
    ("Dharmasthala", 12.9500, 75.3833, "Karnataka, India", ("pilgrimage", "temple"),
     "all year", 1, 1, "Free meals, river ghats, and a queue system that actually works"),
    ("Kukke Subramanya", 12.9167, 75.4667, "Karnataka, India", ("pilgrimage", "hills"),
     "all year", 1, 1, "River temple at the foot of Kumara Parvatha"),
    ("Sringeri", 13.4167, 75.2500, "Karnataka, India", ("pilgrimage", "temple", "hills"),
     "Oct-Feb", 1, 1, "Sharada Peetham on the Tunga; quiet, green, unhurried"),
    ("Kollur", 13.7167, 74.8000, "Karnataka, India", ("pilgrimage", "temple"),
     "all year", 1, 1, "Mookambika temple below the Western Ghats"),
    ("Kundapura", 13.6272, 74.6900, "Karnataka, India", ("temple", "beach", "food"),
     "Oct-Mar", 1, 1, "Anegudde and the coast road south"),
    ("Karwar", 14.8137, 74.1297, "Karnataka, India", ("beach", "island"),
     "Oct-Mar", 2, 2, "Netrani Island diving from a calm bay"),
    ("Bengaluru", 12.9716, 77.5946, "Karnataka, India", ("city", "food", "startup"),
     "all year", 2, 2, "Lalbagh, old markets, and the best coffee in the south"),
    ("Nandi Hills", 13.3702, 77.6835, "Karnataka, India", ("sunrise", "hills", "cycling"),
     "Sep-Feb", 1, 1, "Sunrise above the clouds, 60 km from the city; leave at 4 am"),
    ("Shivanasamudra", 12.3000, 77.1667, "Karnataka, India", ("waterfall", "monsoon"),
     "Jul-Jan", 1, 1, "Twin falls on the Kaveri, one of Asia's oldest hydel sites"),
    ("Talakadu", 12.1833, 77.0167, "Karnataka, India", ("heritage", "history"),
     "Oct-Feb", 1, 1, "Sand-buried temples on the Kaveri, best after the rains"),
    ("B R Hills", 11.9900, 77.1400, "Karnataka, India", ("wildlife", "hills"),
     "Oct-May", 2, 2, "Soliga hills, a tiger reserve and a temple at the top"),
    ("Vijayapura (Bijapur)", 16.8302, 75.7100, "Karnataka, India", ("heritage", "unesco"),
     "Nov-Feb", 2, 1, "Gol Gumbaz's whispering gallery and Adil Shahi architecture"),
    ("Bidar", 17.9104, 77.5199, "Karnataka, India", ("heritage", "history", "craft"),
     "Nov-Feb", 2, 1, "Bidriware metalwork, the fort, and almost no tourists"),
    # ------------------------------------------------------------------- India
    ("Goa (Panaji)", 15.4909, 73.8278, "Goa, India", ("beach", "music", "food"),
     "Nov-Feb", 4, 2, "Old quarters in Panaji, north for parties, south for quiet"),
    ("Palolem", 15.0100, 74.0233, "Goa, India", ("beach", "quiet"),
     "Nov-Feb", 3, 2, "Crescent bay, kayaks, and dolphins at 7 am"),
    ("Taj Mahal, Agra", 27.1751, 78.0421, "Uttar Pradesh, India", ("heritage", "unesco"),
     "Oct-Mar", 1, 3, "Sunrise entry, east gate queue, no tripod without permission"),
    ("Jaipur", 26.9124, 75.7873, "Rajasthan, India", ("heritage", "city", "craft"),
     "Oct-Mar", 3, 2, "Amber, Hawa Mahal, and block-printing workshops"),
    ("Udaipur", 24.5854, 73.7125, "Rajasthan, India", ("lake", "heritage", "wedding"),
     "Sep-Mar", 3, 3, "Lake Pichola at golden hour; rooftop everything"),
    ("Jaisalmer", 26.9157, 70.9083, "Rajasthan, India", ("desert", "heritage", "camp"),
     "Nov-Feb", 3, 2, "Sand dunes, camel country, and a living fort"),
    ("Varanasi", 25.3176, 82.9739, "Uttar Pradesh, India", ("pilgrimage", "history"),
     "Oct-Mar", 2, 2, "Ghats at dawn, aarti at dusk; the lanes are the point"),
    ("Rishikesh", 30.0869, 78.2676, "Uttarakhand, India", ("adventure", "yoga", "river"),
     "Sep-Nov, Feb-Jun", 3, 2, "Rafting, yoga, and the Ganga at the foothills"),
    ("Leh", 34.1526, 77.5771, "Ladakh, India", ("snow", "adventure", "himalaya"),
     "Jun-Sep", 5, 3, "Acclimatise two days before anything; permits for Pangong"),
    ("Manali", 32.2396, 77.1887, "Himachal, India", ("hills", "snow", "adventure"),
     "Mar-Jun, Sep-Nov", 4, 2, "Old Manali cafés, Solang, and the Rohtang road"),
    ("Dharamshala", 32.2190, 76.3234, "Himachal, India", ("hills", "tibetan", "trek"),
     "Mar-Jun, Sep-Nov", 3, 2, "McLeod Ganj, Triund trek, and real momos"),
    ("Darjeeling", 27.0360, 88.2627, "West Bengal, India", ("hills", "tea", "train"),
     "Oct-Dec, Mar-May", 3, 2, "Toy train, Tiger Hill sunrise, first-flush tea"),
    ("Gangtok", 27.3389, 88.6065, "Sikkim, India", ("hills", "monastery", "clean"),
     "Oct-Dec, Mar-May", 4, 2, "Monasteries, Tsomgo lake, permits for north Sikkim"),
    ("Shillong", 25.5788, 91.8933, "Meghalaya, India", ("hills", "rain", "music"),
     "Sep-May", 3, 2, "Living root bridges nearby, waterfalls everywhere in monsoon"),
    ("Kaziranga", 26.5775, 93.1711, "Assam, India", ("wildlife", "safari", "rhino"),
     "Nov-Apr", 2, 3, "Two-thirds of the world's one-horned rhino; book jeep early"),
    ("Munnar", 10.0889, 77.0595, "Kerala, India", ("hills", "tea", "honeymoon"),
     "Sep-Mar", 3, 2, "Tea estates at 1,600 m; Eravikulam park needs a booking"),
    ("Alleppey", 9.4981, 76.3388, "Kerala, India", ("backwater", "houseboat", "food"),
     "Sep-Mar", 2, 2, "Houseboats overnight; smaller shikara boats are cheaper and quieter"),
    ("Thekkady", 9.5833, 77.1500, "Kerala, India", ("wildlife", "spice", "backwater"),
     "Oct-Mar", 2, 2, "Periyar lake safari, spice walks, bamboo rafting"),
    ("Pondicherry", 11.9416, 79.8083, "Puducherry, India", ("beach", "french", "slow"),
     "Oct-Feb", 3, 2, "White Town on a cycle, Auroville, and breakfast that lasts hours"),
    ("Mahabalipuram", 12.6208, 80.1945, "Tamil Nadu, India", ("heritage", "unesco", "beach"),
     "Oct-Feb", 1, 1, "Shore temple and rock-cut caves an hour from Chennai"),
    ("Madurai", 9.9252, 78.1198, "Tamil Nadu, India", ("temple", "food", "city"),
     "Oct-Feb", 2, 1, "Meenakshi temple at 5 am is a different building"),
    ("Kanyakumari", 8.0883, 77.5385, "Tamil Nadu, India", ("sunrise", "coast", "history"),
     "Oct-Feb", 1, 1, "Three seas, one sunrise, and the Vivekananda rock"),
    ("Tirupati", 13.6288, 79.4192, "Andhra Pradesh, India", ("pilgrimage", "temple"),
     "Sep-Feb", 2, 1, "Book darshan online; the queue is the whole experience"),
    ("Puri", 19.8135, 85.8312, "Odisha, India", ("temple", "beach", "food"),
     "Oct-Feb", 2, 1, "Jagannath temple, Chandrabhaga beach, and Odia thali"),
    ("Konark", 19.8876, 86.0945, "Odisha, India", ("heritage", "unesco"),
     "Oct-Feb", 1, 1, "Sun temple wheels; pair with Puri in one day"),
    ("Khajuraho", 24.8318, 79.9199, "Madhya Pradesh, India", ("heritage", "unesco"),
     "Oct-Mar", 2, 2, "Temple carvings; the western group at opening time"),
    ("Amritsar", 31.6340, 74.8723, "Punjab, India", ("temple", "food", "history"),
     "Oct-Mar", 2, 2, "Golden Temple at 4 am, langar, and the Wagah border"),
    ("Mumbai", 19.0760, 72.8777, "Maharashtra, India", ("city", "food", "sea"),
     "Nov-Feb", 3, 3, "Walk the old south; the local train is the fastest education"),
    ("Delhi", 28.6139, 77.2090, "Delhi, India", ("city", "history", "food"),
     "Oct-Mar", 3, 2, "Humayun's tomb, Old Delhi food lanes, and the metro"),
    ("Port Blair", 11.6234, 92.7265, "Andaman, India", ("island", "beach", "diving"),
     "Nov-Apr", 6, 3, "Havelock and Neil islands; ferries book out weeks ahead"),
    ("Kavaratti", 10.5669, 72.6420, "Lakshadweep, India", ("island", "lagoon", "diving"),
     "Oct-Mar", 5, 3, "Entry is permit-based; only a few operators, plan early"),
    # ------------------------------------------------------------------ world
    ("Kathmandu", 27.7172, 85.3240, "Nepal", ("hills", "temple", "trek"),
     "Oct-Nov, Mar-Apr", 4, 2, "Durbar squares, and the trailhead for everything"),
    ("Colombo", 6.9271, 79.8612, "Sri Lanka", ("city", "coast", "food"),
     "Dec-Mar", 3, 2, "Galle Face at sunset; the hill train leaves from Fort"),
    ("Malé", 4.1755, 73.5093, "Maldives", ("island", "lagoon", "diving"),
     "Nov-Apr", 5, 3, "Guesthouse islands cost a fraction of the resort islands"),
    ("Phuket", 7.8804, 98.3923, "Thailand", ("beach", "island", "food"),
     "Nov-Apr", 4, 2, "Old town, and boats to the Phi Phi group"),
    ("Bangkok", 13.7563, 100.5018, "Thailand", ("city", "food", "temple"),
     "Nov-Feb", 3, 2, "Street food, river boats, and the best-value hotels in Asia"),
    ("Hanoi", 21.0278, 105.8342, "Vietnam", ("city", "food", "history"),
     "Oct-Apr", 3, 1, "Old quarter chaos, egg coffee, and Ha Long as a side trip"),
    ("Singapore", 1.3521, 103.8198, "Singapore", ("city", "food", "family"),
     "all year", 3, 3, "Hawker centres are the food; the MRT is the transport"),
    ("Tokyo", 35.6762, 139.6503, "Japan", ("city", "food", "design"),
     "Mar-Apr, Oct-Nov", 6, 3, "Neighbourhoods over landmarks: Shimokitazawa, Yanaka"),
    ("Kyoto", 35.0116, 135.7681, "Japan", ("heritage", "garden", "slow"),
     "Mar-Apr, Oct-Nov", 4, 3, "Temples at 7 am, before the buses"),
    ("Bali", -8.4095, 115.1889, "Indonesia", ("beach", "hills", "surf"),
     "Apr-Oct", 6, 2, "Ubud for green, Canggu for surf, Nusa Penida for cliffs"),
    ("Dubai", 25.2048, 55.2708, "UAE", ("city", "desert", "shopping"),
     "Nov-Mar", 4, 3, "Old creek abra, desert at dusk, and avoid August heat"),
    ("Istanbul", 41.0082, 28.9784, "Türkiye", ("city", "history", "food"),
     "Apr-Jun, Sep-Nov", 4, 2, "Two continents, ferries as transport, breakfast as ritual"),
    ("Cairo", 30.0444, 31.2357, "Egypt", ("history", "unesco", "desert"),
     "Oct-Apr", 4, 2, "Giza at opening, then the museum; the metro is easy"),
    ("Cape Town", -33.9249, 18.4241, "South Africa", ("coast", "wine", "hills"),
     "Nov-Mar", 6, 3, "Table Mountain weather decides your week, not the plan"),
    ("Paris", 48.8566, 2.3522, "France", ("city", "art", "food"),
     "Apr-Jun, Sep-Oct", 4, 3, "Walk the arrondissements; book the big museums online"),
    ("Rome", 41.9028, 12.4964, "Italy", ("history", "food", "city"),
     "Apr-Jun, Sep-Oct", 4, 3, "Early mornings beat every queue"),
    ("Barcelona", 41.3874, 2.1686, "Spain", ("city", "beach", "design"),
     "May-Jun, Sep-Oct", 4, 3, "Gaudí by day, the Gothic quarter by night"),
    ("Lisbon", 38.7223, -9.1393, "Portugal", ("city", "coast", "food"),
     "Mar-Jun, Sep-Oct", 4, 2, "Trams, tiles, and Sintra an hour away"),
    ("Prague", 50.0755, 14.4378, "Czechia", ("city", "history", "cheap"),
     "Apr-Jun, Sep-Oct", 3, 2, "Old Town at 7 am; the castle hill at 5 pm"),
    ("Reykjavík", 64.1466, -21.9426, "Iceland", ("nature", "aurora", "road"),
     "Jun-Aug (light), Sep-Mar (aurora)", 6, 3, "A car, not a tour; weather app is law"),
    ("New York", 40.7128, -74.0060, "USA", ("city", "art", "food"),
     "Apr-Jun, Sep-Nov", 5, 3, "Walk north to south once; the grid does the rest"),
    ("London", 51.5074, -0.1278, "UK", ("city", "museum", "theatre"),
     "May-Sep", 5, 3, "Free museums are the real budget hack"),
    ("Sydney", -33.8688, 151.2093, "Australia", ("coast", "city", "walk"),
     "Oct-Apr", 5, 3, "Bondi to Coogee walk; ferries instead of taxis"),
)

INDEX = {p[0]: p for p in PLACES}


def _find_place(name: str):
    key = (name or "").strip().lower()
    if key in INDEX:
        return INDEX[key]
    for p in PLACES:
        if key and (key in p[0].lower() or p[0].lower().startswith(key)):
            return p
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def map_link(place: str, zoom: int = 12) -> str:
    """An OpenStreetMap link — no key, no account, opens in your browser."""
    p = _find_place(place)
    if p is None:
        q = (place or "").strip()
        if not q:
            return "Which place? Say 'map of Hampi'."
        return ("Not in my dataset, so no coordinates from me — here is a search "
                f"instead: https://www.openstreetmap.org/search?query={q.replace(' ', '+')}")
    name, lat, lon = p[0], p[1], p[2]
    return (f"{name} · {lat:.4f}, {lon:.4f} · {p[3]}\n"
            f"  https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}\n"
            f"  Coordinates are the place centroid — the map is the authority.")


def distance(a: str, b: str) -> str:
    pa, pb = _find_place(a), _find_place(b)
    if not pa or not pb:
        missing = a if not pa else b
        return f"I do not have coordinates for {missing!r} — give me a place from the list."
    km = haversine_km(pa[1], pa[2], pb[1], pb[2])
    hours = km / 45          # honest average for Indian highway driving, stated
    return (f"{pa[0]} → {pb[0]}: {km:,.0f} km straight line "
            f"(about {hours:,.1f} h of driving at an average 45 km/h — road distance "
            f"is always longer, check the map links)\n"
            f"  {pa[0]}: https://www.openstreetmap.org/?mlat={pa[1]}&mlon={pa[2]}"
            f"#map=9/{pa[1]}/{pa[2]}\n"
            f"  {pb[0]}: https://www.openstreetmap.org/?mlat={pb[1]}&mlon={pb[2]}"
            f"#map=9/{pb[1]}/{pb[2]}")


def near(place: str, radius_km: float = 150, tag: str = "", limit: int = 8) -> str:
    """What is actually near a place — computed from coordinates, not a listicle."""
    base = _find_place(place)
    if base is None:
        return f"I do not have coordinates for {place!r}. Try 'near Belagavi'."
    tag = (tag or "").lower().strip()
    rows = []
    for p in PLACES:
        if p[0] == base[0]:
            continue
        if tag and tag not in p[4]:
            continue
        km = haversine_km(base[1], base[2], p[1], p[2])
        if km <= float(radius_km):
            rows.append((km, p))
    if not rows:
        return (f"Nothing within {radius_km:.0f} km of {base[0]}"
                + (f" tagged {tag!r}" if tag else "") +
                ". Try a bigger radius, or drop the tag.")
    rows.sort(key=lambda row: row[0])
    out = [f"Within {float(radius_km):.0f} km of {base[0]}"
           + (f", tagged {tag}" if tag else "") + f" ({len(rows)} found):"]
    for km, p in rows[:int(limit)]:
        out.append(f"  · {p[0]:<22} {km:5.0f} km  {', '.join(p[4][:3])}  "
                   f"best {p[5]}, {p[6]} day(s)")
    out.append("")
    out.append("Distances are straight-line from place centroids; add roughly 20-35% "
               "for real roads in hill country.")
    return "\n".join(out)


def ideas(tag: str = "", budget: str = "", months: str = "", limit: int = 6) -> str:
    """A short list by mood, not by payment."""
    t = (tag or "").lower().strip()
    b = (budget or "").lower().strip()
    m = (months or "").lower().strip()
    tier_want = {"cheap": 1, "budget": 1, "mid": 2, "medium": 2, "premium": 3, "luxury": 3}.get(b)
    rows = []
    for p in PLACES:
        if t and t not in p[4]:
            continue
        if tier_want and p[7] != tier_want:
            continue
        if m and m not in p[5].lower() and "all year" not in p[5].lower():
            continue
        rows.append(p)
    if not rows:
        return (f"Nothing matched tag={t or 'any'} budget={b or 'any'} "
                f"months={m or 'any'}. Tags I know: "
                + ", ".join(sorted({x for p in PLACES for x in p[4]})))
    out = [f"{min(int(limit), len(rows))} ideas:"]
    for p in rows[:int(limit)]:
        out.append(f"  · {p[0]} ({p[3]}) — {p[8]}\n"
                   f"      tags: {', '.join(p[4])} · best {p[5]} · "
                   f"{p[6]} day(s) · tier {'₹' * p[7]}")
    return "\n".join(out)


def itinerary(place: str, days: int = 3, pace: str = "medium") -> str:
    """Day-by-day from real places around a base. Not a curated fantasy."""
    base = _find_place(place)
    if base is None:
        return f"I do not have {place!r} in my dataset. Try 'itinerary for Hampi 3 days'."
    days = max(1, min(14, int(days)))
    per_day = {"slow": 1, "medium": 2, "fast": 3}.get((pace or "medium").lower(), 2)
    ring = []
    for p in PLACES:
        if p[0] == base[0]:
            continue
        km = haversine_km(base[1], base[2], p[1], p[2])
        ring.append((km, p))
    ring.sort(key=lambda row: row[0])
    # the ring is by distance, so a short trip stays local and a long one keeps
    # walking outward instead of repeating the same three towns
    ring = [row for row in ring if row[0] <= 180] or ring
    lines = [f"{base[0]} · {days} day(s), {pace} pace",
             f"Base: {base[0]} — {base[8]}",
             f"Map: https://www.openstreetmap.org/?mlat={base[1]}&mlon={base[2]}"
             f"#map=11/{base[1]}/{base[2]}", ""]
    pool = [p for _, p in ring]
    seen = 0                      # a pointer, so no place appears twice
    for d in range(days):
        lines.append(f"Day {d + 1}")
        if d == 0:
            lines.append(f"  · arrive, walk {base[0]} centre, eat where the queue is local")
        picks = pool[seen: seen + per_day]
        seen += len(picks)
        for p in picks:
            km = haversine_km(base[1], base[2], p[1], p[2])
            lines.append(f"  · {p[0]} ({km:.0f} km) — {p[8]}")
        if not picks and d:
            lines.append("  · rest day inside the base: nothing booked, nothing missed")
    lines += ["",
              "Reality checks: hills roads average 30-35 km/h, so 90 km is half a day. "
              "Computed from my own coordinates — verify opening days on the map link, "
              "because I do not have live timings."]
    return "\n".join(lines)


BANDS = {1: (1500, 3000), 2: (4000, 8000), 3: (12000, 30000)}


def budget(days: int = 3, tier: int = 2, people: int = 2, travel_extra: float = 0) -> str:
    """A planning band, clearly labelled as a band."""
    d = max(1, int(days))
    t = max(1, min(3, int(tier)))
    n = max(1, int(people))
    low, high = BANDS[t]
    stay = low * d * n
    top = high * d * n
    extra = max(0.0, float(travel_extra))
    return (f"{d} day(s), {n} person(s), tier {'₹' * t} — planning band, not a quotation:\n"
            f"  · per person per day: {low:,} – {high:,}\n"
            f"  · stay + food + local travel: {stay:,.0f} – {top:,.0f}\n"
            f"  · travel to/from: {extra:,.0f}\n"
            f"  · total: {stay + extra:,.0f} – {top + extra:,.0f}\n\n"
            "These bands are my own planning ranges for India, not live prices; "
            "season, weekends and festivals move them a lot. For overseas trips the "
            "flight is usually the dominant number and it is not included.")


def places_text(limit: int = 20) -> str:
    return (f"{len(PLACES)} places with coordinates in the dataset. "
            f"Showing {min(int(limit), len(PLACES))}:\n" +
            "\n".join(f"  · {p[0]} — {p[3]} · {', '.join(p[4])}"
                      for p in PLACES[:int(limit)]))
