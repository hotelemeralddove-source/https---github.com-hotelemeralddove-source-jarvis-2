"""Security — **defensive only**. Read this paragraph before the code.

Arc Desk will not contain, install, generate or point at:

  * password crackers, hash crackers, brute-force or "password breaker" tooling;
  * credential harvesters, keyloggers, session stealers, token grabbers;
  * exploits, C2 frameworks, ransomware, or anything that hides itself;
  * "access anything anywhere" — meaning someone else's account, device, network or
    data without their permission.

Two reasons, and neither is squeamishness:

  1. **It is illegal here.** Under India's IT Act (s.66) and most other
     jurisdictions, unauthorised access to a computer system is a criminal offence
     even if nothing is damaged and even if it was "just to check". Shipping the
     tool makes the person who ships it liable too.
  2. **It would poison the product.** A desktop assistant that can quietly open a
     door is a backdoor with a friendly face; antivirus vendors would be right to
     flag the whole app, and you would be trusting a program that can be turned
     against you.

What *is* here is what actually protects a person: knowing whether a password is
weak, spotting a phishing message, checking your own machine's posture, and a
recovery plan that works on the worst day. Every check is read-only and local.
"""
from __future__ import annotations

import math
import os
import re
import subprocess

from . import quiet

COMMON = {
    "password", "123456", "12345678", "qwerty", "india123", "letmein", "admin",
    "welcome", "iloveyou", "monkey", "dragon", "abc123", "password1", "123456789",
    "passw0rd", "qwerty123", "aarav", "krishna", "ganesh", "shiva", "cricket",
}


def password_strength(secret: str = "") -> str:
    """Entropy and crack-time estimates for **your own** password.

    The password is never written to disk, never logged, and never sent anywhere:
    this function only looks at its length and character classes, then forgets it.
    """
    pw = secret or ""
    if not pw:
        return ("Give me a password to check — yours, and nothing you are currently "
                "using anywhere important. Nothing is saved: the length and character "
                "classes are measured, then the string is dropped.")
    classes = 0
    classes += 1 if re.search(r"[a-z]", pw) else 0
    classes += 1 if re.search(r"[A-Z]", pw) else 0
    classes += 1 if re.search(r"\d", pw) else 0
    classes += 1 if re.search(r"[^A-Za-z0-9]", pw) else 0
    alphabet = {1: 26, 2: 52, 3: 62, 4: 95}.get(classes, 26)
    entropy = len(pw) * math.log2(alphabet) if pw else 0
    # attack rates, stated so you can check the arithmetic
    offline = 10 ** 10        # a modern GPU guessing a fast hash
    online = 10 ** 2          # a throttled login form, 100 tries a second
    guesses = 2 ** entropy / 2
    def human(seconds: float) -> str:
        if seconds < 1:
            return "instantly"
        value = float(seconds)
        for unit, size in (("seconds", 60), ("minutes", 60), ("hours", 24),
                           ("days", 365), ("years", 1000)):
            if value < size:
                text = f"{value:,.0f}" if value >= 10 else f"{value:.1f}"
                return f"{text} {unit}"
            value /= size
        # value is now in thousands of years; past ~1e9 the number stops meaning anything
        if value > 1e9:
            return "longer than the age of the universe"
        return f"{value:,.0f} thousand years"
    problems = []
    low = pw.lower()
    if len(pw) < 12:
        problems.append("shorter than 12 characters")
    if low in COMMON or any(w in low for w in ("password", "qwerty", "admin")):
        problems.append("contains a password everyone tries first")
    if re.fullmatch(r"\d+", pw):
        problems.append("digits only — a date or a phone number guesses in seconds")
    if re.search(r"(.)\1{2,}", pw):
        problems.append("repeats a character three or more times")
    if re.search(r"(19|20)\d{2}", pw):
        problems.append("contains a year — birthdays are the first thing tried")
    lines = [f"{len(pw)} characters · {classes} character classes · "
             f"≈ {entropy:.0f} bits of entropy",
             f"  offline attack (10 billion guesses a second): {human(guesses / offline)}",
             f"  online login (100 attempts a second): {human(guesses / online)}"]
    if problems:
        lines.append("Weak points:")
        lines += [f"  · {p}" for p in problems]
    lines.append("")
    if problems:
        lines.append("Fix: four unrelated words beats one clever word. "
                     "'monsoon-tandoor-pencil-harbour' is stronger and easier to "
                     "remember than 'P@ssw0rd2024'.")
    else:
        lines.append("Length is doing the heavy lifting — keep it that way, and do "
                     "not reuse it on a second site.")
    lines.append("This is an estimate from length and classes, not a guarantee about "
                 "any specific cracking rig. Entropy maths, not magic.")
    return "\n".join(lines)


PHISH = [
    (r"\b(urgent|immediately|within 24 hours|account (will be|has been) (closed|suspended))\b",
     2, "manufactured urgency"),
    (r"\b(verify|confirm|re-?activate|update)\b.{0,24}\b(account|password|card|kyc)\b",
     2, "asks you to confirm credentials"),
    (r"\b(password|otp|pin|cvv|aadhaar|pan)\b", 2, "asks for a secret"),
    (r"https?://\d+\.\d+\.\d+\.\d+", 3, "link to a raw IP address"),
    (r"(bit\.ly|tinyurl|t\.co|rb\.gy|is\.gd)", 1, "shortened link hides the destination"),
    (r"@(?!gmail|outlook|yahoo|icloud)[a-z0-9-]+\.[a-z]{2,}", 1,
     "unusual sender domain"),
    (r"\b(click here|act now|limited time)\b", 1, "pressure phrasing"),
    (r"\b(congratulations|you have won|lottery|prize)\b", 2, "too-good-to-be-true setup"),
]


def phishing_check(message: str = "") -> str:
    """Heuristics on a message you received. A score with reasons, not a verdict."""
    text = (message or "").strip()
    if len(text) < 10:
        return ("Paste the message (or the link) and I will look for the usual signs.")
    score, reasons = 0, []
    for pattern, weight, why in PHISH:
        if re.search(pattern, text, flags=re.I):
            score += weight
            reasons.append(why)
    links = re.findall(r"https?://[^\s)>\"]+", text)
    if links:
        hosts = {re.sub(r"^https?://([^/]+).*", r"\1", link) for link in links}
        brands = ("paytm", "phonepe", "sbi", "hdfc", "icici", "amazon", "flipkart",
                  "netflix", "google", "microsoft", "apple", "irctc")
        for host in hosts:
            for brand in brands:
                if brand in host and not re.search(rf"(^|\.){brand}\.(com|in|co\.in)$", host):
                    score += 3
                    reasons.append(f"lookalike domain for {brand}: {host}")
    level = ("LOW — nothing obvious" if score <= 1 else
             "MEDIUM — treat with care" if score <= 4 else
             "HIGH — do not click, do not reply")
    lines = [f"Risk: {level} (score {score})"]
    if reasons:
        lines.append("Signals:")
        lines += [f"  · {r}" for r in dict.fromkeys(reasons)]
    else:
        lines.append("No standard signals fired — which is not the same as safe.")
    lines += ["",
              "What to do either way: never open the link. Go to the company's site "
              "by typing the address yourself, and call the number on the card or "
              "the bill. Real organisations do not ask for OTPs, PINs or passwords."]
    return "\n".join(lines)


def _ps(command: str, timeout: float = 8.0) -> str:
    if os.name != "nt":
        return ""
    try:
        out = quiet.run(["powershell", "-NoProfile", "-Command", command],
                             capture_output=True, text=True, timeout=timeout,
                             errors="replace")
        return (out.stdout or "").strip()
    except Exception:
        return ""


def own_machine() -> str:
    """Check this PC's posture, read-only. Nothing is changed by this function."""
    lines = ["Your machine, checked read-only:"]
    if os.name != "nt":
        lines.append("  · not Windows: firewall and Defender checks are Windows-only")
        lines.append("  · this run proves the code path, not your security posture")
        return "\n".join(lines)
    defenders = _ps("(Get-MpComputerStatus).RealTimeProtectionEnabled")
    lines.append(f"  · Defender real-time protection: "
                 f"{'ON' if defenders.strip().lower().startswith('true') else 'OFF or unavailable'}")
    firewall = _ps("(Get-NetFirewallProfile | Select-Object -ExpandProperty Enabled) -join ','")
    if firewall:
        states = [s.strip() for s in firewall.split(",") if s.strip()]
        on = sum(1 for s in states if s.lower() == "true")
        lines.append(f"  · firewall profiles on: {on}/{len(states)}")
    bitlocker = _ps("(Get-BitLockerVolume -MountPoint $env:SystemDrive).ProtectionStatus")
    if bitlocker:
        lines.append(f"  · disk encryption: {bitlocker} (2 = on, 1 = off, 0 = unknown)")
    updates = _ps("(Get-HotFix | Sort-Object InstalledOn -Descending | "
                  "Select-Object -First 1).InstalledOn")
    if updates:
        lines.append(f"  · last Windows update installed: {updates}")
    lines += ["",
              "These are status readings, not a score. A missing value means the "
              "command could not be run here — it is not a 'pass'."]
    return "\n".join(lines)


def recovery_plan() -> str:
    """The boring plan that saves you on the worst day."""
    return """If you lose access tomorrow, this is what saves you

  1. **A password manager** (Bitwarden, KeePassXC — both free and open source).
     One strong passphrase you remember, everything else generated and unique.
  2. **Two-factor everywhere it matters** — email first, then bank, then socials.
     An authenticator app or a hardware key beats SMS; SIM swaps are routine.
  3. **Recovery codes printed** and kept somewhere a burglar would not look.
     Stored only on the same phone you might lose is not a backup.
  4. **3-2-1 backups**: three copies, two kinds of media, one off-site.
     Test a restore once a quarter — an untested backup is a hope.
  5. **A second email address** you control, used for recovery only.
  6. **Tell one person** where the codes are. Dead-man switches fail less often
     than secrets nobody else can reach."""


def refused() -> str:
    """The explicit no, so it is never a surprise."""
    return ("What Arc Desk will not do, and why:\n"
            "  ✗ crack, brute-force or 'break' passwords — that is unauthorised "
            "access under s.66 IT Act and elsewhere, and shipping it makes the "
            "shipper liable\n"
            "  ✗ harvest credentials, cookies or tokens from any device\n"
            "  ✗ install or generate exploits, keyloggers, rats, ransomware\n"
            "  ✗ 'access anything anywhere' — someone else's account, router, phone "
            "or network without permission\n"
            "  ✗ hide its own process or resist being closed (that is malware "
            "behaviour, and this app is the opposite)\n\n"
            "What it does instead: your own passwords measured, phishing spotted, "
            "your own machine audited, and a recovery plan that works.\n"
            "If you are learning security legally: build a lab VM you own, use "
            "Kali/Parrot there, and only ever test systems you own or have written "
            "permission for. Do not ask this app to be the weapon.")
