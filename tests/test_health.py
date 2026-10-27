"""The health module is judged on what it refuses.

A wrong dosage is an injury and a wrong diagnosis is worse, so this file tests the
rails, not the friendliness:

  * emergencies must be recognised as emergencies (chest pain with arm pain, stroke
    signs, suicidal statements) — missing one is the dangerous failure;
  * a question phrased "how much should *I* take" must never produce a personal
    number, only the published label range plus a pharmacist;
  * a medicine outside the verified set must be refused, not guessed;
  * no output may claim to diagnose ("you have X").

Run:  python tests/test_health.py
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arcdesk import health as H  # noqa: E402

PASS = 0
FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    print(f"   {'OK  ' if ok else 'FAIL'} {label}" + (f"   [{detail}]" if detail else ""))
    if ok:
        PASS += 1
    else:
        FAIL += 1


DIAGNOSIS = re.compile(r"\byou (probably |definitely |clearly )?(have|are suffering from)\b",
                       re.I)


def main() -> int:
    print("health — the rails matter more than the answers\n")

    # 1. emergencies -------------------------------------------------------
    print("1. red flags escalate to emergency")
    emergencies = {
        "chest pain and pain in my left arm": "heart attack",
        "my face is drooping and speech is slurred": "stroke",
        "he is unconscious and not breathing": "unconscious",
        "i want to kill myself": "crisis",
        "worst headache of my life, came on suddenly": "headache",
        "bleeding heavily from my hand and it won't stop": "bleeding",
    }
    for symptom, why in emergencies.items():
        out = H.triage(symptom)
        check(f"emergency: {why}", "EMERGENCY" in out, out.splitlines()[0][:40])
        check(f"emergency: {why} → tells them to call", "112" in out or "emergency number" in out)
        check(f"emergency: {why} → no diagnosis", not DIAGNOSIS.search(out))

    # 2. urgency levels ----------------------------------------------------
    print("\n2. non-emergencies are not escalated or dismissed")
    soon = H.triage("sore throat and mild cough for two days")
    check("mild symptoms get self-care", "SELF-CARE" in soon or "SOON" in soon,
          soon.splitlines()[0][:44])
    urgent = H.triage("high fever for 4 days with a stiff neck")
    check("fever + stiff neck is urgent", "URGENT" in urgent or "EMERGENCY" in urgent,
          urgent.splitlines()[0][:44])
    check("triage states what it will not do", "name your illness from a sentence" in soon)
    check("triage carries the disclaimer", "not a diagnosis" in soon.lower())

    # 3. medicines ---------------------------------------------------------
    print("\n3. medicines: published ranges, no personal dose")
    para = H.drug("paracetamol", "how much should i take")
    check("paracetamol recognised", "Paracetamol" in para)
    check("paracetamol gives the label range", "500–1000 mg" in para)
    check("paracetamol refuses a personal dose",
          "will not calculate that" in para)
    check("paracetamol warns about the liver", "liver" in para.lower())
    check("paracetamol marked over the counter", "OVER THE COUNTER" in para.upper())

    amox = H.drug("amoxicillin", "")
    check("antibiotic flagged PRESCRIPTION ONLY", "PRESCRIPTION ONLY" in amox)
    check("antibiotic says finish the course", "finish the course" in amox.lower())

    for alias in ("dolo", "crocin", "calpol", "acetaminophen"):
        check(f"alias '{alias}' resolves to paracetamol", "Paracetamol" in H.drug(alias, ""))

    unknown = H.drug("ivermectin-for-covid", "")
    check("unknown drug is refused", "do not have verified information" in unknown)
    check("unknown drug suggests a pharmacist", "pharmacist" in unknown.lower())
    check("unknown drug invents nothing", "mg" not in unknown.lower())

    for name, info in H.DRUGS.items():
        check(f"{name}: has a range and a warning",
              bool(info.get("range")) and bool(info.get("warn")))
        if not info.get("rx"):
            check(f"{name}: OTC drug still warns", len(info.get("warn", [])) >= 1)

    # 4. anatomy -----------------------------------------------------------
    print("\n4. anatomy explains, never diagnoses")
    for part in ("heart", "kidney", "brain", "lungs", "liver", "joints", "skin", "stomach"):
        out = H.anatomy(part)
        check(f"anatomy: {part}", "What it does" in out and "not a diagnosis" in out.lower())
    unknown_part = H.anatomy("spleen")
    check("unknown organ lists what is known", "I can explain these systems" in unknown_part)

    # 5. first aid ---------------------------------------------------------
    print("\n5. first aid")
    for topic in ("bleeding", "burn", "choking", "cpr", "fever", "fracture"):
        out = H.first_aid(topic)
        check(f"first aid: {topic}", "First aid" in out and "not a diagnosis" in out.lower())
    check("first aid unknown topic lists options", "I have first-aid steps for" in
          H.first_aid("sprained ego"))
    check("cpr says call first", "Call emergency services first" in H.first_aid("cpr"))

    # 6. blanket rules -----------------------------------------------------
    print("\n6. blanket rules across every output")
    samples = [H.triage("headache"), H.drug("ibuprofen", "how much"),
               H.anatomy("heart"), H.first_aid("burn"), H.describe()]
    check("no output diagnoses the user",
          not any(DIAGNOSIS.search(text) for text in samples))
    check("every output ends with the disclaimer",
          all("not a diagnosis" in text.lower() for text in samples[:-1]))
    check("describe() states the limits", "no personal" in H.describe().lower())

    # 7. tool dispatch -----------------------------------------------------
    print("\n7. the text beats a wrong label (measured misroute)")
    from arcdesk.ai import tools as T
    misrouted = T.call("health", {"what": "first_aid", "query": "paracetamol dosage entha"})
    check("model asked first_aid, text said paracetamol → medicine",
          "Paracetamol" in misrouted and "Label range" in misrouted)
    burn = T.call("health", {"what": "triage", "query": "first aid for a burn"})
    check("first-aid words still reach first aid", "First aid — burn" in burn)
    emergency = T.call("health", {"what": "medicine", "query": "chest pain and sweating"})
    check("a symptom beats a medicine label", "EMERGENCY" in emergency)

    print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'} — {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
