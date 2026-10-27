"""The library — what JARVIS actually knows without a network, and how it says so.

"JARVIS knows everything" is the ambition. This module is the honest version of it:
a curated, **sourced, dated** fact pack that ships on disk, plus a librarian who is
clear about the edge of the shelf.

Three rules, enforced by tests/test_world.py:

  1. **Every entry has a source and a date.** No "scientists say" with nothing behind
     it. If a fact changes (population, temperature, prices), the date is the point.
  2. **No number that moves is presented as current.** Anything that drifts carries
     `moves=True` and is answered as "as of <year>", not as today's truth.
  3. **No medical dose, no legal verdict, no price.** Health entries describe
     mechanisms and public first-aid guidance; law entries name the statute and say
     "ask a lawyer"; money entries teach the arithmetic.

What is *not* here: today's news, live prices, tomorrow's weather, or a guess. Those
need a source — `unknown()` says so and puts the source one sentence away.
"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

# id, domain, question forms, answer, source, as_of, moves?
# `moves=True` means the fact changes with time and must be spoken with its date.
ENTRIES: tuple[tuple, ...] = (
    # ------------------------------------------------------------- india
    ("india-states", "india", ("how many states in india", "states and union territories",
                               "how many ut"),
     "India has 28 states and 8 union territories. Jammu and Kashmir was reorganised "
     "into two union territories in October 2019.", "Government of India reorganisation acts", 2024, False),
    ("india-capital", "india", ("capital of india", "india capital"),
     "New Delhi is the capital of India; Delhi is the National Capital Territory that "
     "contains it.", "Constitution / NCT of Delhi Act", 2024, False),
    ("india-time", "india", ("what is ist", "indian standard time", "time zone of india"),
     "India Standard Time is UTC+05:30, one zone for the whole country, with no daylight "
     "saving.", "Indian Standard Time Act, 1947", 2024, False),
    ("india-population", "india", ("population of india", "what is india's population",
                                   "india population", "how many people in india"),
     "About 1.43 billion people — India passed China as the most populous country in 2023.",
     "UN World Population Prospects", 2024, True),
    ("india-coastline", "india", ("how long is india's coastline", "coastline of india"),
     "About 7,517 km including the islands — 5,423 km mainland plus the Andaman, Nicobar "
     "and Lakshadweep groups.", "Ministry of Home Affairs", 2024, False),
    ("india-highest", "india", ("highest peak in india", "tallest mountain in india"),
     "Kanchenjunga, 8,586 m, on the Sikkim–Nepal border. Nanda Devi is the highest peak "
     "entirely inside India.", "Survey of India", 2024, False),
    ("india-longest-river", "india", ("longest river in india", "which river is longest in india"),
     "The Ganga is the longest river flowing within India (about 2,525 km); the Indus and "
     "Brahmaputra are longer overall but mostly outside India.",
     "Central Water Commission", 2024, False),
    ("india-largest-state", "india", ("largest state by area", "biggest state in india"),
     "Rajasthan by area (about 342,239 km²); Uttar Pradesh by population.",
     "Census of India", 2011, True),
    ("karnataka-capital", "india", ("capital of karnataka", "karnataka capital"),
     "Bengaluru. Karnataka was formed on 1 November 1956 as Mysore State and renamed "
     "Karnataka in 1973.", "States Reorganisation Act, 1956", 2024, False),
    ("belagavi", "india", ("where is belagavi", "belgaum", "belagavi"),
     "Belagavi (Belgaum) is in north-west Karnataka, about 15.85°N 74.50°E and roughly "
     "750 m above sea level, close to the Goa and Maharashtra borders.",
     "Survey of India / district gazetteer", 2024, False),
    ("karnataka-peak", "india", ("highest peak in karnataka", "mullayanagiri"),
     "Mullayanagiri in Chikkamagaluru district, about 1,930 m — the highest point in "
     "Karnataka.", "Karnataka forest department", 2024, False),
    ("jog-falls", "india", ("jog falls", "where is jog falls"),
     "Jog Falls is on the Sharavathi river in Shivamogga district, Karnataka, falling in "
     "four streams; it is at its fullest in the south-west monsoon, July to September.",
     "Karnataka Power Corporation", 2024, False),
    ("hampi", "india", ("hampi", "vijayanagara"),
     "Hampi was the capital of the Vijayanagara empire (founded 1336) on the Tungabhadra "
     "river; the ruins are a UNESCO World Heritage Site, listed in 1986.",
     "UNESCO World Heritage List", 2024, False),
    ("monsoon", "india", ("when is the monsoon", "monsoon season india"),
     "The south-west monsoon runs roughly June to September and supplies about three "
     "quarters of India's annual rainfall; the north-east monsoon brings Tamil Nadu's "
     "main rains from October to December.", "India Meteorological Department", 2024, False),
    ("gst-india", "india", ("what is gst", "gst rate", "gst slabs"),
     "The Goods and Services Tax started on 1 July 2017 and replaced a pile of central "
     "and state taxes. The common slabs are 0%, 5%, 12%, 18% and 28%, plus cess on some "
     "goods. Rates are decided by the GST Council and do change.",
     "GST Council", 2024, True),
    ("upi", "india", ("what is upi", "unified payments interface"),
     "UPI is a real-time bank-to-bank payment system run by NPCI, launched in 2016. It "
     "moves money directly between accounts using a virtual address; it is not a wallet "
     "and holds no balance.", "NPCI", 2024, False),
    ("rti", "india", ("right to information", "rti act"),
     "The Right to Information Act, 2005 gives any citizen the right to ask a public "
     "authority for information, with a 30-day reply window in the normal case.",
     "RTI Act, 2005", 2024, False),
    ("it-act-66", "india", ("it act section 66", "unauthorised access law india"),
     "Section 66 of the Information Technology Act, 2000 punishes dishonest or fraudulent "
     "acts done with a computer resource, including unauthorised access. This is why JARVIS "
     "will not build intrusion tools.", "IT Act, 2000", 2024, False),
    ("bnss", "india", ("crpc replaced", "bharatiya nagarik suraksha sanhita", "new criminal laws"),
     "From 1 July 2024 the Indian Penal Code, CrPC and Evidence Act were replaced by the "
     "Bharatiya Nyaya Sanhita, Bharatiya Nagarik Suraksha Sanhita and Bharatiya Sakshya "
     "Adhiniyam. An FIR is now registered under the BNSS.",
     "Bharatiya Nagarik Suraksha Sanhita, 2023", 2024, False),
    ("constitution-days", "india", ("when was constitution adopted", "republic day",
                                    "constitution of india"),
     "The Constitution was adopted on 26 November 1949 and came into force on 26 January "
     "1950 — the day India became a republic. Independence was 15 August 1947.",
     "Constitution of India", 2024, False),

    # ------------------------------------------------------------- world
    ("everest", "world", ("how tall is everest", "mount everest height", "highest mountain"),
     "8,848.86 m above sea level, agreed jointly by Nepal and China in 2020. It grows a "
     "few millimetres a year from tectonic uplift.", "Nepal–China joint survey, 2020", 2020, False),
    ("mariana", "world", ("deepest point in the ocean", "mariana trench"),
     "The Challenger Deep in the Mariana Trench, about 10,935 m down — deeper than "
     "Everest is tall.", "NOAA", 2024, False),
    ("largest-country", "world", ("largest country", "biggest country by area"),
     "Russia, about 17.1 million km² — roughly twice Canada, the second largest.",
     "UN Statistics Division", 2024, False),
    ("smallest-country", "world", ("smallest country", "vatican city"),
     "Vatican City, about 0.49 km² and under a thousand residents.",
     "Vatican City State", 2024, False),
    ("deserts", "world", ("largest desert", "biggest desert"),
     "Antarctica is the largest desert by the rainfall definition (about 14 million km²). "
     "The Sahara is the largest hot desert, about 9.2 million km².",
     "Encyclopaedia Britannica", 2024, False),
    ("nile-amazon", "world", ("longest river in the world", "nile or amazon"),
     "The Nile is usually quoted at about 6,650 km and the Amazon at about 6,400 km, but "
     "the answer depends on where you decide a river starts — surveys still disagree.",
     "USGS", 2024, False),
    ("earth-facts", "world", ("how big is the earth", "circumference of earth", "earth radius"),
     "The Earth's equatorial radius is 6,378 km and the equatorial circumference about "
     "40,075 km. It is an oblate spheroid: wider at the equator than pole to pole.",
     "WGS 84 / NGA", 2024, False),
    ("moon-distance", "world", ("how far is the moon", "distance to the moon"),
     "On average about 384,400 km, drifting about 3.8 cm a year further away "
     "(measured by laser ranging off the Apollo reflectors).", "NASA LLR", 2024, False),
    ("solar-mass", "world", ("how much of the solar system is the sun", "sun mass"),
     "The Sun holds about 99.86% of the mass of the solar system.",
     "NASA planetary fact sheets", 2024, False),
    ("co2", "world", ("co2 level", "carbon dioxide in the atmosphere", "420 ppm"),
     "Atmospheric CO₂ passed 420 parts per million in 2023 and is still rising about "
     "2-3 ppm a year. This number changes every year, so treat the date as part of it.",
     "NOAA Mauna Loa / WMO", 2024, True),
    ("ocean-oxygen", "world", ("do oceans produce oxygen", "where does oxygen come from"),
     "Most of the oxygen in the air comes from the ocean — phytoplankton, not rainforests. "
     "'The Amazon is the lungs of the Earth' is a good slogan and a bad fact.",
     "NOAA / Nature Geoscience", 2024, False),

    # ----------------------------------------------------------- science
    ("light-speed", "science", ("speed of light", "how fast is light"),
     "299,792,458 metres per second in a vacuum — an exact number since 1983, because the "
     "metre is now defined by it.", "BIPM / SI", 2019, False),
    ("light-year", "science", ("what is a light year", "how far is a light year"),
     "The distance light travels in a Julian year: about 9.46 trillion km. It is a "
     "distance, not a time.", "IAU", 2024, False),
    ("gravity", "science", ("standard gravity", "value of g"),
     "9.80665 m/s² is the standard gravity used for definitions. Real local gravity varies "
     "by about 0.5% with latitude and altitude.", "BIPM", 2019, False),
    ("avogadro", "science", ("avogadro number", "mole"),
     "6.02214076 × 10²³ particles per mole, fixed exactly by the 2019 SI redefinition.",
     "BIPM / SI", 2019, False),
    ("absolute-zero", "science", ("absolute zero", "kelvin zero"),
     "−273.15 °C = 0 K. Nothing can be cooled to exactly zero; we get close "
     "(billionths of a kelvin) but never arrive.", "BIPM / SI", 2019, False),
    ("water-boils", "science", ("boiling point of water", "at what temperature does water boil"),
     "100 °C at standard sea-level pressure. On a mountain it boils cooler: about 94 °C at "
     "2,000 m — which is why hill-station tea tastes different.",
     "NIST", 2024, False),
    ("periodic", "science", ("how many elements", "periodic table"),
     "118 confirmed elements, ending at oganesson (118). Elements 113-118 were named in "
     "2016.", "IUPAC", 2024, False),
    ("dna", "science", ("who discovered dna structure", "double helix"),
     "The double helix structure was published in 1953 by Watson and Crick, built on "
     "Rosalind Franklin's and Maurice Wilkins' X-ray diffraction work.",
     "Watson & Crick, Nature 1953; Franklin & Gosling, Photo 51", 1953, False),
    ("photosynthesis", "science", ("how does photosynthesis work", "photosynthesis"),
     "Plants use light to turn CO₂ and water into sugar and oxygen: 6CO₂ + 6H₂O → "
     "C₆H₁₂O₆ + 6O₂, driven by chlorophyll. It happens in the chloroplasts.",
     "Taiz & Zeiger, Plant Physiology (6th ed.)", 2024, False),
    ("brain-ten-percent", "science", ("do we use 10 percent of our brain", "ten percent of brain"),
     "No. Imaging shows essentially all of the brain is active over a day; damage anywhere "
     "tends to produce symptoms. The '10%' line is a myth with no paper behind it.",
     "Society for Neuroscience, Brain Facts", 2024, False),

    # -------------------------------------------------------------- tech
    ("byte-bits", "tech", ("how many bits in a byte", "byte"),
     "8 bits. A nibble is 4 bits. Throughput in bits per second and storage in bytes is why "
     "a '100 Mbps' line downloads at about 12 MB/s.", "IEC 80000", 2024, False),
    ("ipv4-ipv6", "tech", ("ipv4 vs ipv6", "ip address size"),
     "IPv4 addresses are 32-bit (about 4.3 billion, exhausted); IPv6 is 128-bit "
     "(3.4 × 10³⁸) which is why it exists.", "IETF RFC 8200", 2024, False),
    ("https", "tech", ("what does https mean", "https"),
     "HTTP over TLS: the traffic is encrypted and the server proves its identity with a "
     "certificate. The padlock means the connection is private, not that the site is honest.",
     "IETF RFC 8446", 2024, False),
    ("ram-vs-storage", "tech", ("ram vs storage", "difference between ram and ssd"),
     "RAM is fast, volatile working space the CPU reads constantly; storage (SSD/HDD) is "
     "slow, persistent. More RAM keeps more open at once; more storage keeps more forever.",
     "JEDEC DDR5 / NVM Express specifications", 2024, False),
    ("ssd-hdd", "tech", ("ssd or hdd", "ssd vs hdd"),
     "SSDs have no moving parts, are roughly 5-20× faster for random reads and survive "
     "knocks; HDDs are cheaper per terabyte for bulk archives.",
     "JEDEC SSD standards, manufacturer datasheets", 2024, False),
    ("tcp-ip", "tech", ("what is tcp/ip", "tcp ip model"),
     "The four-layer model the internet runs on: link, internet (IP), transport (TCP/UDP), "
     "application (HTTP, DNS…). TCP retries and orders; UDP does not.",
     "IETF", 2024, False),
    ("dns", "tech", ("what is dns", "domain name system"),
     "The phone book of the internet: it turns names into IP addresses, cached at several "
     "levels with a TTL. Most 'the internet is down' moments are DNS.",
     "IETF RFC 1035", 2024, False),
    ("python", "tech", ("who made python", "python history"),
     "Guido van Rossum started Python in 1989 and released 1.0 in 1991; it is named after "
     "Monty Python, not the snake.", "python.org", 2024, False),
    ("linux", "tech", ("who made linux", "linux kernel"),
     "Linus Torvalds released the Linux kernel in 1991 and later created Git in 2005. The "
     "kernel is GPL-2.0; 'Linux' as a complete system is a distribution's packaging.",
     "kernel.org", 2024, False),
    ("git", "tech", ("what is git", "version control"),
     "A distributed version control system: every clone has the full history, commits are "
     "content-addressed hashes, and branches are just pointers.",
     "git-scm.com", 2024, False),
    ("json", "tech", ("what is json", "json format"),
     "A text format of objects, arrays, strings, numbers, booleans and null — specified by "
     "Douglas Crockford and standardised as ECMA-404 / RFC 8259. It has no comments.",
     "RFC 8259", 2024, False),
    ("licences", "tech", ("difference between mit apache gpl", "open source licences"),
     "MIT: do almost anything, keep the notice. Apache-2.0: same plus an explicit patent "
     "grant. GPL: if you distribute a modified version, its source must be GPL too. AGPL "
     "extends that to network use.", "OSI / FSF", 2024, False),
    ("bit-vs-qbit", "tech", ("what is a qubit", "quantum bit"),
     "A qubit holds a superposition of 0 and 1 until measured. It is not 'both at once as "
     "a value' — it is a state with amplitudes, and measurement gives one outcome.",
     "Nielsen & Chuang, Quantum Computation (2010)", 2024, False),

    # ------------------------------------------------------------- money
    ("margin", "money", ("gross vs net margin", "what is net margin"),
     "Gross margin = (revenue − cost of goods) ÷ revenue. Net margin = profit after every "
     "cost, including tax, ÷ revenue. A business can have 60% gross and 2% net.",
     "IFRS Foundation / ICAI accounting standards", 2024, False),
    ("ebitda", "money", ("what is ebitda", "ebitda"),
     "Earnings before interest, tax, depreciation and amortisation — a rough measure of "
     "operating cash generation. It is not profit and ignores the cost of the machines.",
     "IFRS Foundation / ICAI accounting standards", 2024, False),
    ("compound", "money", ("compound interest formula", "compounding"),
     "A = P(1 + r/n)^(nt). At 12% over 10 years, ₹1 lakh becomes about ₹3.1 lakh; at 12% "
     "simple interest it would be ₹2.2 lakh.", "compound-interest identity: A = P(1+r/n)^(nt)", 2024, False),
    ("inflation", "money", ("what is inflation", "inflation meaning"),
     "A sustained rise in the general price level, usually measured by a CPI basket. 6% "
     "inflation halves purchasing power in about 12 years (72 ÷ 6).",
     "RBI / statistics ministries", 2024, False),
    ("repo", "money", ("what is repo rate", "rbi repo"),
     "The rate at which the RBI lends short-term to banks; the Monetary Policy Committee "
     "sets it. It moves — quote the date whenever you quote the number.",
     "Reserve Bank of India", 2024, True),
    ("cac-ltv", "money", ("what is ltv cac", "ltv to cac"),
     "CAC is what one customer costs to acquire. LTV is the gross profit they bring over "
     "their lifetime. Under 3:1, there is no room for a bad month, refunds or staff.",
     "David Skok, SaaS Metrics 2.0", 2024, False),
    ("working-capital", "money", ("what is working capital", "working capital"),
     "Current assets minus current liabilities — the money tied up in running the business "
     "day to day. A profitable business can still die of it.",
     "IFRS Foundation / ICAI accounting standards", 2024, False),

    # ------------------------------------------------------------ health
    ("ors", "health", ("what is ors", "oral rehydration solution"),
     "Oral rehydration salts in clean water replace water and electrolytes lost to "
     "diarrhoea; low-osmolarity ORS is the WHO-preferred formulation. Dehydration kills by "
     "volume loss, so ORS is genuine emergency medicine, not a home remedy.",
     "WHO", 2024, False),
    ("cpr", "health", ("cpr", "what is cpr", "cpr ratio", "how to do cpr",
                       "cardiopulmonary resuscitation"),
     "Adult CPR: 30 chest compressions then 2 rescue breaths, about 100-120 compressions a "
     "minute, hard and deep, on a hard surface. Call emergency services first and follow "
     "their instructions.", "AHA / Red Cross public guidance", 2024, False),
    ("fever", "health", ("is fever dangerous", "fever meaning"),
     "Fever is a regulated rise in body temperature — a response, not a disease. What "
     "matters is the cause and the person's state, not the number alone. JARVIS gives no "
     "personal dose and no diagnosis.", "WHO", 2024, False),
    ("antibiotics", "health", ("do antibiotics work on viruses", "antibiotics for cold"),
     "No. Antibiotics act on bacteria, not viruses, so they do nothing for a cold or flu "
     "and drive resistance. Taking them 'just in case' is how we lose them.",
     "WHO", 2024, False),
    ("burns", "health", ("first aid for burns", "burn treatment"),
     "Cool the burn under cool running water for about 20 minutes, remove rings and tight "
     "clothing, cover loosely. No ice, no toothpaste, no butter. Blistering or a burn "
     "bigger than the palm needs a doctor.", "Red Cross first aid guidance", 2024, False),
    ("handwash", "health", ("how long to wash hands", "hand hygiene"),
     "About 20 seconds with soap — long enough to sing the birthday song twice. Soap and "
     "friction matter more than the water temperature.", "WHO", 2024, False),
    ("bmi", "health", ("what is bmi", "body mass index"),
     "Weight in kg ÷ (height in m)². It is a population screen, not a diagnosis: muscular "
     "people score high, and it says nothing about where fat sits.",
     "WHO", 2024, False),

    # -------------------------------------------------------------- food
    ("cups", "food", ("how many ml in a cup", "cup to ml"),
     "240 ml in a US cup, 250 ml in a metric cup — the 4% difference ruins baking if you "
     "assume the wrong one. 1 tbsp = 15 ml, 1 tsp = 5 ml.", "US NIST / metric practice", 2024, False),
    ("kg-lb", "food", ("kg to pounds", "how many pounds in a kg"),
     "1 kg = 2.20462 lb. A rough mental shortcut: double it and subtract 10%.",
     "NIST", 2024, False),
    ("maillard", "food", ("why does food brown", "maillard reaction"),
     "The Maillard reaction: amino acids and sugars react above roughly 140 °C, creating "
     "hundreds of flavour compounds. It needs a dry surface — which is why a wet steak "
     "boils instead of browning.", "Fennema's Food Chemistry", 2024, False),
    ("salt-water", "food", ("why does salt make water boil faster", "salt boiling"),
     "It does not — dissolved salt raises the boiling point and slows heating. What salt "
     "changes is flavour and, in pasta water, the texture of the surface.",
     "IUPAC Gold Book (colligative properties)", 2024, False),

    # --------------------------------------------------------- myth busts
    ("myth-goldfish", "myths", ("goldfish memory", "three second memory"),
     "Goldfish remember far longer than three seconds — studies show learned responses "
     "retained for months. The '3 seconds' claim has no study behind it.",
     "fish-cognition reviews, Animal Cognition journal", 2024, False),
    ("myth-wall", "myths", ("can you see the great wall from space", "great wall from space"),
     "Not with the naked eye — it is long but far too narrow. Astronauts have repeatedly "
     "said so, including from the ISS.", "NASA", 2024, False),
    ("myth-lightning", "myths", ("lightning never strikes twice", "lightning same place"),
     "It strikes tall structures repeatedly — the Empire State Building is hit roughly 20-25 "
     "times a year. 'Never twice' is a comfort, not a fact.", "NOAA", 2024, False),
)

INDEX: dict[str, tuple] = {e[0]: e for e in ENTRIES}
DOMAINS = ("india", "world", "science", "tech", "money", "health", "food", "myths")


def _tokens(text: str) -> set[str]:
    # "india's population" must tokenise to india + population, not indias
    clean = re.sub(r"['\u2019]s\b", "", (text or "").lower())
    return {w for w in re.findall(r"[a-z0-9]+", clean) if len(w) > 2}


STOP = {"what", "who", "when", "where", "why", "how", "the", "and", "for", "are",
        "does", "did", "was", "were", "is", "of", "in", "on", "to", "a", "an", "tell",
        "me", "about", "many", "much", "long", "india", "indian"}


def search(question: str, limit: int = 3) -> list[tuple[int, tuple]]:
    """Rank entries against a question. Simple, explainable scoring."""
    q = (question or "").lower().strip()
    if not q:
        return []
    toks = _tokens(q) - STOP
    scored: list[tuple[int, tuple]] = []
    for entry in ENTRIES:
        forms = entry[2]
        score = 0
        for form in forms:
            if form in q:
                score += 6 + min(6, len(form.split()))
        hay = " ".join([entry[0].replace("-", " "), entry[3].lower(), " ".join(forms)])
        hits = len(toks & _tokens(hay))
        score += hits * 2
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda row: (-row[0], row[1][0]))
    return scored[:limit]


def _cite(entry: tuple) -> str:
    src, year, moves = entry[4], entry[5], entry[6]
    if moves:
        return f"source: {src} — as of {year}, and this number changes"
    return f"source: {src} ({year})"


def _key_hits(entry: tuple, toks: set[str]) -> int:
    """Hits on the entry's *name or question forms*, not just incidental words in the body."""
    hay = _tokens(entry[0].replace("-", " ") + " " + " ".join(entry[2]))
    return len(toks & hay)


def ask(question: str = "") -> str:
    """Answer from the library, with the source attached, or say plainly that I cannot."""
    hits = search(question, 3)
    toks = _tokens(question) - STOP
    # One specific word ("what is cpr") is a precise question, so it clears a lower bar —
    # but only when that word is in the entry's own name or forms, never a passing mention.
    specific = bool(hits) and len(toks) == 1 and _key_hits(hits[0][1], toks) >= 1
    if not hits or (hits[0][0] < 4 and not specific):
        own = ask_library(question)
        if own:
            return own
        return unknown(question)
    best = hits[0][1]
    lines = [best[3], "", _cite(best)]
    others = [e for score, e in hits[1:] if score >= 4]
    if others:
        lines.append("")
        lines.append("Also in the library:")
        for e in others:
            first = e[3].split(". ")[0]
            lines.append(f"  · {first}.  ({e[4]}, {e[5]})")
    lines.append("")
    lines.append(f"(That is one of {len(ENTRIES)} sourced entries on this disk — "
                 f"ask 'what do you know' for the shelf.)")
    return "\n".join(lines)


def unknown(question: str = "") -> str:
    """The most valuable sentence an assistant can say."""
    q = (question or "").strip()
    wiki = f"https://en.wikipedia.org/wiki/Special:Search?search={quote_plus(q)}"
    web = f"https://duckduckgo.com/?q={quote_plus(q)}"
    return (f"I do not know that one, and I will not improvise it.\n\n"
            f"My offline library covers {len(ENTRIES)} dated facts across "
            f"{len(DOMAINS)} domains (India, world, science, tech, money, health, food, "
            f"myths) plus your own files and live machine readings. Anything outside "
            f"that — today's news, a person's current role, a price — needs a source.\n\n"
            f"Three honest moves:\n"
            f"  1. Open the source and read it yourself:\n"
            f"     {wiki}\n"
            f"     {web}\n"
            f"  2. Paste the text here and ask me to analyse it — I am good at that.\n"
            f"  3. Ask 'what do you know about <topic>' to see what is already on disk.")


def coverage() -> str:
    counts: dict[str, int] = {}
    for e in ENTRIES:
        counts[e[1]] = counts.get(e[1], 0) + 1
    shelf = ", ".join(f"{d} {n}" for d, n in sorted(counts.items()))
    moving = sum(1 for e in ENTRIES if e[6])
    try:
        import json
        own = len(json.loads(_library_path().read_text(encoding="utf-8")))
    except Exception:
        own = 0
    return (f"On this disk: {len(ENTRIES)} sourced facts — {shelf}.\n"
            f"Your own library: {own} indexed chunk(s) from files you added "
            f"({library_dir()}).\n"
            f"{moving} of them change over time and are always quoted with their year.\n"
            f"Plus, measured live instead of remembered: your clock, CPU, memory, disk, "
            f"network, processes, calendar, reminders, files and focus time.\n\n"
            f"What 'knows everything' honestly means here:\n"
            f"  · a sourced library for stable facts,\n"
            f"  · arithmetic for anything countable,\n"
            f"  · your own files for anything personal,\n"
            f"  · and the word 'I do not know' for the rest, with a source one line away.\n"
            f"A system that claims to know everything is the one you cannot trust.")


def domain(name: str = "", limit: int = 8) -> str:
    key = (name or "").lower().strip()
    if not key:
        return "Domains: " + ", ".join(DOMAINS) + ". Say 'what do you know about tech'."
    rows = [e for e in ENTRIES if e[1] == key]
    if not rows:
        near = [d for d in DOMAINS if key in d or d in key]
        return (f"No domain called {key!r}. " +
                (f"Did you mean {near[0]}?" if near else "Domains: " + ", ".join(DOMAINS)))
    lines = [f"{key.upper()} — {len(rows)} entries"]
    for e in rows[:int(limit)]:
        lines.append(f"  · {e[0].replace('-', ' ')}: {e[3].split('. ')[0]}.  "
                     f"({e[4]}, {e[5]})")
    if len(rows) > int(limit):
        lines.append(f"  … {len(rows) - int(limit)} more")
    return "\n".join(lines)


def random_fact() -> str:
    """One entry, picked by the day so it is stable within a day, not random noise."""
    import time
    day = int(time.time() // 86400)
    entry = ENTRIES[day % len(ENTRIES)]
    return f"{entry[3]}\n\n{_cite(entry)}\n(domain: {entry[1]})"


# --------------------------------------------------------------- your library
# The honest way to "know everything": read what is actually on this machine.
# Drop files in the library folder (or point ARC at a folder) and every one of them
# becomes answerable, with the filename quoted in the answer.
PLAIN_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log", ".rst", ".py", ".html",
                  ".ini", ".cfg", ".yaml", ".yml", ".sql", ".tex", ".org"}
# read through `reading.py` so pdf/docx/xlsx/pptx earn their place on the shelf too
LIBRARY_SUFFIXES = PLAIN_SUFFIXES | {".pdf", ".docx", ".xlsx", ".pptx"}
MAX_DOC_BYTES = 2_000_000
CHUNK_CHARS = 900


def library_dir():
    from . import config
    d = config.data_dir() / "library"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _library_path():
    from . import config
    return config.data_dir() / "library_index.json"


def _read_doc(path) -> str:
    try:
        if path.suffix.lower() in PLAIN_SUFFIXES:
            return path.read_text(encoding="utf-8", errors="replace")
        from . import reading
        doc = reading.read(str(path), limit=200_000, ocr=False)
        return doc.text if getattr(doc, "ok", False) and doc.text else ""
    except Exception:
        return ""


def ingest(path: str = "", limit: int = 400) -> str:
    """Index a folder (or the library folder) into searchable chunks."""
    import json
    from pathlib import Path
    root = Path(path).expanduser() if str(path).strip() else library_dir()
    if not root.exists():
        return f"No such folder: {root}"
    docs, files = [], 0
    for item in sorted(root.rglob("*")):
        if files >= limit:
            break
        if not item.is_file():
            continue
        if item.suffix.lower() not in LIBRARY_SUFFIXES:
            continue
        try:
            if item.stat().st_size > MAX_DOC_BYTES:
                continue
        except OSError:
            continue
        text = _read_doc(item)
        if not text.strip():
            continue
        files += 1
        for start in range(0, len(text), CHUNK_CHARS):
            piece = text[start:start + CHUNK_CHARS].strip()
            # 12 characters, not 80: a one-line price list is still knowledge
            if len(piece) >= 12:
                docs.append({"file": item.name, "path": str(item), "text": piece})
    try:
        _library_path().write_text(json.dumps(docs[:4000], indent=0), encoding="utf-8")
    except Exception as exc:
        return f"I could not write the library index: {exc}"
    return (f"Indexed {files} file(s) into {len(docs)} searchable chunks from {root}.\n"
            f"Ask me anything that is inside them — the answer quotes the file name.")


def _library_search(question: str, limit: int = 2) -> list[dict]:
    import json
    try:
        docs = json.loads(_library_path().read_text(encoding="utf-8"))
    except Exception:
        return []
    toks = _tokens(question) - STOP
    if not toks:
        return []
    scored = []
    for doc in docs:
        text_tokens = _tokens(doc.get("text", ""))
        hits = len(toks & text_tokens)
        if hits:
            scored.append((hits, doc))
    scored.sort(key=lambda row: -row[0])
    return [d for score, d in scored[:limit] if score >= 2]


def ask_library(question: str = "") -> str:
    hits = _library_search(question)
    if not hits:
        return ""
    lines = ["From your own library:"]
    for doc in hits:
        snippet = re.sub(r"\s+", " ", doc["text"])
        index = snippet.lower().find(next(iter(_tokens(question) - STOP), ""))
        start = max(0, index - 120)
        lines.append(f"  · {doc['file']}: …{snippet[start:start + 320]}…")
    lines.append("Quoted, not paraphrased — open the file to read the rest.")
    return "\n".join(lines)


# ------------------------------------------------------------ a live source
def fetch(topic: str = "", sentences: int = 4) -> str:
    """Pull a Wikipedia summary, cache it, and cite it with a date.

    This is the honest answer to 'know everything': go and read, then say where it
    came from. Needs the internet; says so plainly when it does not have it.
    """
    import json
    import time
    import urllib.request
    from urllib.parse import quote

    title = (topic or "").strip()
    if not title:
        return "What should I look up? e.g. 'fetch Vikram Sarabhai'."
    cache_path = library_dir() / "wiki_cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    key = title.lower()
    cached = cache.get(key)
    if cached and time.time() - cached.get("at", 0) < 7 * 86400:
        return (f"{cached['title']} — {cached['extract']}\n\n"
                f"source: {cached['url']} (cached {time.strftime('%d %b %Y', time.localtime(cached['at']))})")
    url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
           + quote(title.replace(" ", "_")))
    try:
        request = urllib.request.Request(url, headers={
            "User-Agent": "ArcDesk/1.0 (local desktop assistant; offline-first)"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8", "replace"))
    except Exception as exc:
        return (f"I could not reach the source ({type(exc).__name__}). I have no internet "
                f"or Wikipedia is blocked, so I will not answer from memory.\n"
                f"Try again later, or paste the text and I will analyse it.")
    extract = (data.get("extract") or "").strip()
    if not extract:
        return f"Wikipedia has no summary for {title!r}. Try a different spelling."
    parts = re.split(r"(?<=[.!?])\s+", extract)[:max(1, int(sentences))]
    entry = {"title": data.get("title", title), "extract": " ".join(parts),
             "url": (data.get("content_urls", {}).get("desktop", {}).get("page")
                     or f"https://en.wikipedia.org/wiki/{quote(title)}"),
             "at": time.time()}
    cache[key] = entry
    try:
        cache_path.write_text(json.dumps(cache, indent=0), encoding="utf-8")
    except Exception:
        pass
    return (f"{entry['title']} — {entry['extract']}\n\n"
            f"source: {entry['url']} (read just now, {time.strftime('%d %b %Y')})\n"
            f"Cached locally for a week; ask 'what do you know' to see the shelf.")
