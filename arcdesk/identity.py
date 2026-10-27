"""What the assistant calls itself — one setting, used everywhere it speaks.

The user asked for this twice, in their own words:

    "athu pesum pothu 'I am ARC' nu soluthu; 'I am JARVIS' nu sonna semaya irukkum"
    "nan kooda ARC nu sola vendam, JARVIS nu solanum"

So the name lives here and nowhere else. `DEFAULT_NAME` is what a fresh install says;
`cfg["ai"]["name"]` overrides it (Settings → Voice → "what it calls itself"), and an empty
or whitespace-only value falls back rather than producing a blank introduction.

The *product* is still Arc Desk — "ARC DESK" in the header, "Arc Desk" in the installer.
One is the machine you installed; the other is who answers when you talk to it.
"""
from __future__ import annotations

#: What a fresh installation says. Also the fallback for a blank setting.
DEFAULT_NAME = "JARVIS"

#: Words that are the product, not the persona. `relabel()` leaves these alone.
_BRAND = ("ARC DESK", "Arc Desk", "ARC Lite")


def name(cfg: dict | None = None) -> str:
    """The name this installation answers to. Never empty."""
    try:
        chosen = ((cfg or {}).get("ai") or {}).get("name") or ""
    except AttributeError:
        chosen = ""
    chosen = str(chosen).strip()
    return chosen or DEFAULT_NAME


def intro(cfg: dict | None = None) -> str:
    """The one sentence it introduces itself with, spoken or shown on a card."""
    return f"I am {name(cfg)}, and this is my voice on your machine."


def relabel(text: str) -> str:
    """Return `text` with the old persona name replaced, product names untouched."""
    out = text
    for brand in _BRAND:
        out = out.replace(brand, "\x00" + brand)     # park the brand names out of the way
    out = out.replace("I am ARC", f"I am {DEFAULT_NAME}")
    out = out.replace("ASK ARC", f"ASK {DEFAULT_NAME}")
    return out.replace("\x00", "")
