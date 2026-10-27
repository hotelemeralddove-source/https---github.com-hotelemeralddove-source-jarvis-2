"""Health information with the safety rails welded on.

What a responsible assistant can and cannot do here is not a grey area:

CAN  explain anatomy, describe what a condition usually involves, list the red
     flags that mean "stop reading and get help", give first-aid steps, and quote
     *published adult reference ranges* for a small set of common medicines — with
     the prescription status and the warnings that come on the label.

CANNOT diagnose, rule anything out, calculate a dose for a particular person, tell
     someone to stop or change a prescription, or replace a clinician. Doses depend
     on weight, kidney and liver function, pregnancy, age and other medicines; a
     number invented here could hurt someone.

So the code has three hard rules, each covered by `tests/test_health.py`:

  1. **No personal dosing.** Any request phrased as "how much should I take" gets an
     explanation plus the pharmacist/doctor route, never a computed number.
  2. **No diagnosis.** Symptoms produce urgency levels and a list of possibilities to
     discuss, never "you have X".
  3. **No invented drug facts.** A medicine outside the small verified set returns
     "I do not have verified data for that", not a plausible guess.

Emergency numbers: India 112 / 108 (ambulance). The rest of the world differs, so the
message names the local emergency number instead of assuming one.
"""
from __future__ import annotations

import re

DISCLAIMER = ("General health information for understanding — not a diagnosis and not "
              "a prescription. A qualified clinician who can examine you is the only "
              "one who can decide treatment.")

EMERGENCY = ("EMERGENCY. Call your local emergency number now — in India 112, ambulance "
             "108. Do not drive yourself. If you are with someone, tell them what is "
             "happening and stay with them until help arrives.")

# ---------------------------------------------------------------- red flags
# (patterns, level, why). Level: emergency | urgent | soon
RED_FLAGS = [
    (r"chest (pain|pressure|tightness)|pain .{0,20}(left|both) arm|jaw pain",
     "emergency", "chest pain with arm or jaw involvement can be a heart attack"),
    (r"(can ?not|cannot|can't|difficulty|trouble) breath|shortness of breath|"
     r"gasping|blue lips", "emergency", "breathing difficulty needs oxygen assessment now"),
    (r"face\b.{0,12}\b(droop|droopy|drooping|numb|paralys)|\bdroop\w* face|"
     r"slurred speech|speech\b.{0,12}\bslurr|weak(ness)?\b.{0,15}\bone side|"
     r"arm\b.{0,15}\b(weak|numb).{0,15}\bone side|\bstroke\b", "emergency",
     "FAST signs of stroke — time lost is brain lost"),
    (r"unconscious|passed out|fainted and (not|still) (waking|responding)|not breathing",
     "emergency", "loss of consciousness"),
    (r"bleeding (heavily|a lot|won't stop|non.?stop)|blood (loss|vomit).{0,20}heavy",
     "emergency", "uncontrolled bleeding"),
    (r"suicid|kill myself|end my life|self.?harm|want to die", "emergency",
     "you deserve immediate human support — please call a crisis line or emergency services"),
    (r"severe (headache).{0,30}(sudden|worst|thunderclap)|worst headache of my life",
     "emergency", "sudden worst-ever headache needs urgent imaging"),
    (r"severe abdominal pain|abdomen hard|rigid belly|blood in (stool|vomit)",
     "urgent", "possible surgical abdomen or GI bleed"),
    (r"high fever.{0,20}(3|4|5) days|fever .{0,10}103|fever .{0,10}39\.\d|"
     r"fever.{0,25}(rash|stiff neck|confusion)", "urgent", "fever with red-flag features"),
    (r"pregnan.{0,30}(bleed|pain|cramp)|no fetal movement", "urgent",
     "pregnancy with bleeding, pain or reduced movement"),
    (r"infant.{0,20}(fever|not feeding|lethargic)|newborn.{0,20}fever", "urgent",
     "young infants deteriorate quickly"),
    (r"cannot (keep|hold) (any )?(water|fluid|food)|vomit.{0,15}(everything|all day)|"
     r"signs? of dehydration|dizzy on standing", "urgent",
     "dehydration risk, especially in children and the elderly"),
    (r"vision (loss|lost)|sudden.{0,15}(blind|blurred vision)|double vision", "urgent",
     "sudden visual change"),
    (r"severe pain .{0,20}(testicle|scrotum)|testicular pain", "urgent",
     "acute scrotal pain is a surgical emergency until proven otherwise"),
]

LEVEL_ORDER = {"emergency": 0, "urgent": 1, "soon": 2, "self-care": 3}

LEVEL_TEXT = {
    "emergency": "EMERGENCY — go to an emergency department or call an ambulance now.",
    "urgent": "URGENT — be seen the same day (walk-in clinic, or your doctor's urgent line).",
    "soon": "SOON — book an appointment in the next few days; go sooner if it worsens.",
    "self-care": "SELF-CARE is reasonable for now, with the watch-points below.",
}

NEXT_STEPS = {
    "emergency": EMERGENCY,
    "urgent": ("While you arrange to be seen: do not eat or drink if abdominal pain is "
               "severe, keep a note of the time symptoms started, and take your medicine "
               "list with you."),
    "soon": ("Write down when it started, what makes it better or worse, and anything "
             "you have already taken. That history is what shortens the appointment."),
    "self-care": ("Rest, fluids, and watch for the red flags above. If it is not clearly "
                  "improving in 48 hours, get it looked at."),
}

# --------------------------------------------------------------- medicines
# Published adult reference information only. `range` is what the label says, not a
# prescription for this person, and `rx` marks prescription-only medicines.
DRUGS: dict[str, dict] = {
    "paracetamol": {
        "also": ["acetaminophen", "dolo", "crocin", "calpol"],
        "class": "pain reliever / fever reducer",
        "rx": False,
        "range": "Adults: 500–1000 mg per dose, up to 3–4 g in 24 hours. "
                 "Never combine two paracetamol products at once.",
        "warn": ["Overdose damages the liver and can be silent for days — the daily cap "
                 "is not a suggestion.",
                 "Lower limits apply with liver disease, low body weight, or regular alcohol."],
        "avoid": "liver disease, malnutrition, heavy alcohol use (ask a pharmacist first)",
    },
    "ibuprofen": {
        "also": ["brufen", "nsaid", "combiflam (with paracetamol)"],
        "class": "anti-inflammatory pain reliever (NSAID)",
        "rx": False,
        "range": "Adults: 200–400 mg per dose every 6–8 hours with food; "
                 "max 1200 mg/day without medical advice.",
        "warn": ["Can irritate or bleed the stomach — take with food.",
                 "Avoid in kidney disease, uncontrolled blood pressure, heart failure, and "
                 "in the last trimester of pregnancy.",
                 "Do not stack with other NSAIDs (diclofenac, naproxen, aspirin)."],
        "avoid": "stomach ulcers, kidney disease, third trimester of pregnancy",
    },
    "cetirizine": {
        "also": ["zyrtec", "allergy tablet", "levocetirizine is different"],
        "class": "antihistamine for allergy",
        "rx": False,
        "range": "Adults: 10 mg once daily; 5 mg if kidney function is reduced.",
        "warn": ["Can make you drowsy — be careful driving until you know how it hits you.",
                 "Avoid alcohol with it."],
        "avoid": "severe kidney disease (dose adjustment needed)",
    },
    "ors": {
        "also": ["oral rehydration salts", "electral"],
        "class": "rehydration",
        "rx": False,
        "range": "Sip one sachet dissolved in the stated volume of clean water after each "
                 "loose stool; small frequent sips for children.",
        "warn": ["Mixing it stronger than the packet says is harmful, not better.",
                 "If the person cannot drink, is drowsy, or has not passed urine for many "
                 "hours, that is urgent care, not ORS."],
        "avoid": "severe dehydration or inability to drink — needs IV fluids",
    },
    "omeprazole": {
        "also": ["prilosec", "pantoprazole is similar"],
        "class": "acid suppressant (PPI)",
        "rx": False,
        "range": "Adults: 20 mg once daily before food, typically for up to 14 days "
                 "without medical advice.",
        "warn": ["Long-term use should be reviewed by a doctor.",
                 "Persistent difficulty swallowing, weight loss or vomiting blood is not "
                 "heartburn — get it investigated."],
        "avoid": "unexplained weight loss, vomiting blood, long-term use without review",
    },
    "amoxicillin": {
        "also": ["antibiotic", "amoxil", "clavam (with clavulanate)"],
        "class": "antibiotic (penicillin)",
        "rx": True,
        "range": "Prescription only. The dose depends on the infection, weight and kidney "
                 "function — it is prescribed, not chosen.",
        "warn": ["Antibiotics do nothing for viral colds and flu, and misuse drives "
                 "resistance.",
                 "Finish the course exactly as prescribed; do not save leftovers.",
                 "Allergic reaction (rash, swelling, wheeze) → emergency care."],
        "avoid": "penicillin allergy; never share or reuse a leftover course",
    },
    "metformin": {
        "also": ["glycomet", "diabetes tablet"],
        "class": "blood-sugar medicine (type 2 diabetes)",
        "rx": True,
        "range": "Prescription only; usually started low and increased, taken with food.",
        "warn": ["Needs kidney function checks.",
                 "Stop and call a doctor if you get severe vomiting, diarrhoea or become "
                 "very unwell (rare lactic acidosis risk).",
                 "Does not replace diet, activity or monitoring."],
        "avoid": "significant kidney disease, severe illness or dehydration",
    },
    "atorvastatin": {
        "also": ["statin", "cholesterol tablet"],
        "class": "cholesterol-lowering (statin)",
        "rx": True,
        "range": "Prescription only; taken at a fixed time daily.",
        "warn": ["Muscle pain with dark urine → contact a doctor promptly.",
                 "Grapefruit in large amounts interacts.",
                 "Do not stop on your own — the benefit is from continuity."],
        "avoid": "pregnancy, active liver disease",
    },
    "salbutamol": {
        "also": ["asthalin", "inhaler", "albuterol"],
        "class": "reliever inhaler (asthma)",
        "rx": True,
        "range": "Prescription only: usually 1–2 puffs when needed. Needing it more than "
                 "a couple of times a week means the preventer plan needs review.",
        "warn": ["Increasing use is a warning sign, not a solution.",
                 "A severe attack (cannot speak full sentences, blue lips) is an emergency."],
        "avoid": "uncontrolled fast heart rhythms",
    },
    "iron folic acid": {
        "also": ["ifa tablet", "ferrous", "anaemia tablet"],
        "class": "iron + folate supplement",
        "rx": False,
        "range": "Common public-health adult dose is one tablet daily; anaemia treatment "
                 "doses are prescribed after a blood test.",
        "warn": ["Causes dark stools and constipation — that is expected, not bleeding.",
                 "Iron is dangerous to children in overdose; keep it locked away."],
        "avoid": "iron overload conditions; confirm the anaemia type first",
    },
}

# ------------------------------------------------------------------ anatomy
SYSTEMS: dict[str, dict] = {
    "heart": {
        "does": "pumps about 5 litres a minute; coronary arteries feed the muscle itself.",
        "problems": ["blocked coronary arteries (angina, heart attack)",
                     "high blood pressure straining the walls",
                     "rhythm problems from the electrical system",
                     "valves not closing cleanly"],
        "reasons": ["smoking, high LDL cholesterol, diabetes, high blood pressure, "
                    "family history, age",
                    "sometimes none of the above — which is why chest pain is taken "
                    "seriously regardless"],
        "solutions": ["assessment: ECG, blood markers (troponin), echo, stress test",
                      "long-term: blood pressure and sugar control, stopping smoking, "
                      "moving daily, statins/other medicines when indicated"],
    },
    "brain": {
        "does": "processes senses, memory, movement and language on ~20 % of your energy.",
        "problems": ["stroke (blocked or burst vessel)", "migraine",
                     "seizures", "infection (meningitis)", "degeneration over decades"],
        "reasons": ["blood pressure is the single biggest stroke risk",
                    "smoking, diabetes, irregular heart rhythm, high alcohol",
                    "dehydration and sleep loss for headache (but never assume)"],
        "solutions": ["FAST check for stroke → emergency",
                      "imaging (CT/MRI) for sudden or worst-ever symptoms",
                      "control blood pressure; treat migraine with a proper plan"],
    },
    "lungs": {
        "does": "exchange oxygen and CO₂ across ~480 million tiny air sacs.",
        "problems": ["asthma (reversible narrowing)", "COPD (fixed narrowing)",
                     "pneumonia", "clots (pulmonary embolism)", "allergy"],
        "reasons": ["smoking, dust and pollution, infections, allergies, reflux"],
        "solutions": ["spirometry to measure airflow", "inhalers with correct technique",
                      "vaccination, stopping smoking, avoiding triggers"],
    },
    "stomach": {
        "does": "breaks food down with acid and enzymes; absorbs most nutrients in the "
                "small intestine.",
        "problems": ["acid reflux (GERD)", "gastritis/ulcer (often H. pylori)",
                     "irritable bowel", "infection", "gallstones (upper right pain)"],
        "reasons": ["spicy/late meals, alcohol, NSAID painkillers, stress, infection"],
        "solutions": ["food and timing changes first", "test for H. pylori if ulcers are "
                      "suspected", "red flags (bleeding, weight loss, hard belly) → "
                      "same-day care"],
    },
    "kidney": {
        "does": "filters ~180 litres of blood a day and balances salt, water and acid.",
        "problems": ["acute injury (dehydration, medicines, infection)",
                     "chronic disease from diabetes and blood pressure", "stones"],
        "reasons": ["diabetes and hypertension cause most chronic cases",
                    "NSAIDs and dehydration are common avoidable hits"],
        "solutions": ["blood and urine tests (creatinine, eGFR, protein)",
                      "control sugar and pressure; drink enough; review painkillers"],
    },
    "liver": {
        "does": "processes nutrients, makes clotting factors, clears drugs and toxins.",
        "problems": ["fatty liver", "viral hepatitis B/C", "alcohol-related damage",
                     "drug-induced injury (including paracetamol overdose)"],
        "reasons": ["alcohol, weight gain, viral infection, some medicines and supplements"],
        "solutions": ["liver function tests plus ultrasound", "weight and alcohol reduction",
                      "vaccination for hepatitis B; never exceed paracetamol limits"],
    },
    "joints": {
        "does": "cartilage plus fluid lets bones glide; muscles and tendons move them.",
        "problems": ["osteoarthritis (wear)", "inflammatory arthritis",
                     "tendon/ligament strain", "gout (sudden hot swollen joint)"],
        "reasons": ["age and load for wear; immune misfire for inflammatory types; "
                    "uric acid crystals for gout"],
        "solutions": ["examination plus X-ray/blood tests", "strength work is the best "
                      "long-term treatment for most joint pain", "weight reduction"],
    },
    "skin": {
        "does": "barrier, temperature control and vitamin D synthesis.",
        "problems": ["eczema/atopic dermatitis", "fungal infection", "bacterial infection",
                     "acne", "drug rash"],
        "reasons": ["dryness and irritants, sweating, allergens, hormones, medicines"],
        "solutions": ["moisturise and avoid irritants", "targeted creams for flares",
                      "a changing mole or spreading rash needs eyes on it"],
    },
}


# --------------------------------------------------------------- functions
def _level_rank(level: str) -> int:
    return LEVEL_ORDER.get(level, 9)


def triage(symptoms: str) -> str:
    """Urgency, red flags and what to watch — never a diagnosis."""
    said = " ".join((symptoms or "").lower().split())
    if not said:
        return "Tell me the symptoms and how long they have been going on."
    hits = []
    for pattern, level, why in RED_FLAGS:
        if re.search(pattern, said):
            hits.append((level, why))
    level = "self-care"
    for hit_level, _ in sorted(hits, key=lambda h: _level_rank(h[0])):
        level = hit_level
        break
    lines = [f"Urgency: {LEVEL_TEXT[level]}"]
    if hits:
        lines.append("\nRed flags I noticed")
        for _, why in hits[:4]:
            lines.append(f"  - {why}")
    lines.append("\nWhat to do next\n  " + NEXT_STEPS[level])
    lines.append(
        "\nWhat I will not do: name your illness from a sentence. Symptoms overlap "
        "heavily — chest pain can be muscle, reflux or a heart attack, and only an "
        "examination and tests separate them. The value here is the urgency level and "
        "the words to use when you get seen.")
    if level == "self-care":
        lines.append("\nThings worth tracking: when it started, what makes it better or "
                     "worse, temperature, and whether eating/sleeping changed.")
    lines.append("\n" + DISCLAIMER)
    return "\n".join(lines)


def _find_drug(name: str) -> tuple[str, dict] | tuple[None, None]:
    wanted = " ".join((name or "").lower().split())
    if not wanted:
        return None, None
    for key, info in DRUGS.items():
        names = [key] + [str(a) for a in info.get("also", [])]
        for candidate in names:
            label = candidate.split(" (")[0].lower()
            if wanted == label or wanted.startswith(label) or label in wanted:
                return key, info
    return None, None


def drug(name: str, question: str = "") -> str:
    """Published label information — and a firm line about personal dosing."""
    key, info = _find_drug(name)
    if not info:
        return (f"I do not have verified information for '{name}', and I will not guess "
                "about a medicine. Check the packet insert, ask a pharmacist (free in most "
                "pharmacies), or look it up in a national formulary. If you tell me the "
                "generic name I may know it.")
    asks_dose = bool(re.search(r"how (much|many)|dose for me|for my (weight|kidney|child)|"
                               r"can i (take|give) (double|two)|should i take", question.lower()))
    lines = [f"{key.title()} — {info['class']}"
             + ("  ·  PRESCRIPTION ONLY" if info["rx"] else "  ·  available over the counter"),
             f"  Label range: {info['range']}"]
    if info.get("warn"):
        lines.append("  Important:")
        lines += [f"    - {w}" for w in info["warn"]]
    if info.get("avoid"):
        lines.append(f"  Ask first if: {info['avoid']}")
    if info["rx"]:
        lines.append("  This needs a prescription — the dose is decided by a clinician who "
                     "knows your weight, kidneys and other medicines.")
    if asks_dose:
        lines.append(
            "\nYou are asking how much *you* should take. I will not calculate that: the "
            "same drug is a normal dose for one person and too much for another, and a "
            "wrong number from an assistant is a real injury. Take the packet to a "
            "pharmacist — they will do this for free in two minutes — or call your doctor.")
    lines.append("\n" + DISCLAIMER)
    return "\n".join(lines)


def anatomy(part: str) -> str:
    said = " ".join((part or "").lower().split())
    key = next((k for k in SYSTEMS if k in said), "")
    if not key:
        return ("I can explain these systems: " + ", ".join(SYSTEMS) +
                ". Name one, or describe the body part.")
    info = SYSTEMS[key]
    lines = [f"{key.title()}",
             f"  What it does: {info['does']}",
             "  Common problems:",
             *[f"    - {p}" for p in info["problems"]],
             "  Why they happen:",
             *[f"    - {r}" for r in info["reasons"]],
             "  How they are usually approached:",
             *[f"    - {s}" for s in info["solutions"]],
             "\nThis is how the system works in general. Your case depends on examination "
             "and tests — that is the difference between a textbook and a doctor.",
             DISCLAIMER]
    return "\n".join(lines)


def first_aid(topic: str) -> str:
    said = " ".join((topic or "").lower().split())
    guides = {
        "bleeding": ["Press hard and continuously with a clean cloth — do not lift to peek.",
                     "Raise the limb if possible; keep pressure for at least 10 minutes.",
                     "Bleeding that soaks through, or is spurting, is an emergency."],
        "burn": ["Cool with running water for 20 minutes — not ice, not toothpaste.",
                 "Remove rings/tight items before swelling; cover loosely with cling film.",
                 "Blisters larger than a coin, face/hands/joints, or any child → medical care."],
        "choking": ["Ask 'are you choking?' If they cannot speak or cough: 5 back blows, "
                    "then 5 abdominal thrusts, repeat.",
                    "If they collapse, start CPR and call emergency services.",
                    "Anyone who needed thrusts must be checked afterwards."],
        "cpr": ["Call emergency services first, speakerphone on.",
                "Push hard and fast in the centre of the chest, 100–120 per minute, "
                "about 5–6 cm deep, letting it come back up fully.",
                "Use an AED if one is nearby — it talks you through it."],
        "fever": ["Fluids, light clothing, rest; measure and write down the temperature.",
                  "Fever with stiff neck, rash, confusion, or in an infant under 3 months "
                  "is urgent care."],
        "fracture": ["Do not try to straighten it. Support it in the position found.",
                     "Ice wrapped in cloth, and get an X-ray.",
                     "Deformed limb, numbness, or an open wound → emergency."],
    }
    key = next((k for k in guides if k in said), "")
    if not key:
        return ("I have first-aid steps for: " + ", ".join(guides) +
                ". For anything life-threatening, call emergency services first and "
                "follow their instructions.")
    return (f"First aid — {key}\n" + "\n".join(f"  {i}. {s}"
                                              for i, s in enumerate(guides[key], 1))
            + "\n\nIf the person is unconscious, not breathing, or bleeding heavily, "
              "stop reading and call emergency services (India 112 / 108).\n" + DISCLAIMER)


def describe() -> str:
    return (f"health information: triage with red flags, {len(DRUGS)} common medicines "
            f"with published ranges, {len(SYSTEMS)} body systems, first aid for "
            f"bleeding/burns/choking/CPR/fever/fractures. No diagnosis, no personal "
            f"dosing, no guesses.")
