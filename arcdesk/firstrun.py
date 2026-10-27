"""The first five minutes, spelled out.

A new install has four decisions in it, and each one has a real cost that the user is
entitled to see *before* ticking the box:

    wake word      → a microphone is open and a 60–150 MB daemon runs
    autostart      → something starts with your account, every day, forever
    documents      → ARC reads Word/Excel/PDF once, read-only, to make search work
    voice reply    → your machine talks out loud in a room other people are in

This module is the *logic* of that wizard, kept out of the dialog so it can be tested
without a screen: `answers_from()` reads the current state, `apply()` performs exactly
the four side effects and nothing else, and returns a list of lines describing what it
did — including the things it deliberately did **not** do.

The dialog (`widgets/welcome.py`) is a thin skin over this, which is why the same rules
hold whether the user clicks through the wizard, edits settings, or says
"start with windows" out loud.
"""
from __future__ import annotations

from . import autostart, config

# The four answers, with the default a cautious person would choose.
DEFAULTS = {
    "wake": False,        # the microphone is OFF until somebody says so
    "autostart": False,   # never add a startup entry on someone's behalf
    "documents": False,   # reading files is opt-in even when it is read-only
    "voice": True,        # speaking is the product; silence is the surprise
}

# The one question the wizard asks in words a person can answer:
#
#   "icon"  → I double-click the shortcut when I need you.  Nothing runs in the
#             background, no microphone, no startup entry.  The honest default.
#   "voice" → You are always there; "hey jarvis" opens you.  That *means* a startup
#             entry and an open microphone, and setup says so before doing it.
#
# The two are not independent switches in a person's head, so `open_mode` sets both
# `wake` and `autostart` together and explains the cost. Settings exposes the same
# choice, which is why this lives here and not in the dialog.
OPEN_MODES = ("icon", "voice")


def reveal_window(just_finished_setup: bool, hidden_boot: bool) -> bool:
    """Should the main window be on screen right now?

    Two ways to get this wrong, and both happened:

    * stealth mode hides the window at boot (that is the promised resting state), so
      after the setup card was answered the app went invisible and "nothing opened";
    * the only thing left to click was the ✕, which saved nothing and brought the card
      back on the next double-click.

    The rule: **answering the setup card means the person is looking at the screen right
    now**, so show the window once. If they chose the voice mode, "bye jarvis" puts it
    away again and later launches stay silent. `hidden_boot` is kept in the signature so
    the caller cannot forget which of the two situations it is in.
    """
    return bool(just_finished_setup) or not bool(hidden_boot)


def answers_from(cfg: dict) -> dict:
    """What is true right now — so the wizard opens showing reality, not aspirations."""
    wake = bool(cfg.get("wake", {}).get("enabled"))
    voice = bool(cfg.get("ai", {}).get("voice", True))
    docs = bool(cfg.get("docs", {}).get("index_on_start", False))
    try:
        boot = autostart.is_enabled()
    except Exception:
        boot = False
    return {"wake": wake, "autostart": boot, "documents": docs, "voice": voice}


def mode_of(cfg: dict) -> str:
    """What the app does right now, derived from the two real flags."""
    wake = bool(cfg.get("wake", {}).get("enabled"))
    try:
        boot = autostart.is_enabled()
    except Exception:
        boot = bool(cfg.get("autostart", False))
    return "voice" if (wake and boot) else "icon"


def set_mode(cfg: dict, mode: str, can_listen: bool | None = None) -> dict:
    """Turn the open-mode choice into the two flags it really is.

    Returns answers suitable for `apply()`. When `can_listen` is known False, a
    request for "voice" is downgraded to "icon" with a warning instead of arming a
    microphone that cannot work — the first "hey jarvis" failing is worse than an
    honest "your machine cannot listen yet".
    """
    mode = str(mode or "icon").lower()
    warnings: list[str] = []
    if mode not in OPEN_MODES:
        warnings.append(f"unknown open mode {mode!r} — using the icon")
        mode = "icon"
    if mode == "voice" and can_listen is False:
        warnings.append("voice open was requested, but this machine cannot listen yet "
                        "(no microphone library or speech engine) — leaving it on the icon")
        mode = "icon"
    return {"open_mode": mode,
            "wake": mode == "voice",
            "autostart": mode == "voice",
            "warnings": warnings}


def should_show(cfg: dict) -> bool:
    """The wizard appears once. `first_run` is the only flag that decides it."""
    return bool(cfg.get("first_run", True))


def apply(cfg: dict, answers: dict) -> dict:
    """Do exactly what was asked. Returns {changed, notes, warnings, state}."""
    wanted = dict(DEFAULTS)
    answers = dict(answers or {})
    extra_warnings: list[str] = []
    # `open_mode` is the human-level answer; it decides the two flags underneath.
    if answers.get("open_mode") in OPEN_MODES:
        derived = set_mode(cfg, answers["open_mode"],
                           can_listen=answers.get("can_listen"))
        answers["wake"] = derived["wake"]
        answers["autostart"] = derived["autostart"]
        extra_warnings += derived["warnings"]
    wanted.update({k: bool(v) for k, v in answers.items() if k in DEFAULTS})
    before = answers_from(cfg)
    notes: list[str] = []
    warnings: list[str] = list(extra_warnings)
    changed: list[str] = []

    # ---- 1. voice replies ------------------------------------------------
    cfg.setdefault("ai", {})["voice"] = wanted["voice"]
    if wanted["voice"] != before["voice"]:
        changed.append("voice replies " + ("on" if wanted["voice"] else "off"))
        notes.append("Voice replies are " + ("on" if wanted["voice"] else "off") +
                     " — Settings → Voice changes the engine and speed.")

    # ---- 2. wake word ----------------------------------------------------
    cfg.setdefault("wake", {})["enabled"] = wanted["wake"]
    if wanted["wake"] != before["wake"]:
        changed.append("wake word " + ("armed" if wanted["wake"] else "off"))
        notes.append("Wake word is " + ("armed — the microphone is open, and Ctrl+Alt+Q "
                                        "still quits at any time."
                                        if wanted["wake"] else
                                        "off. Nothing is listening. Turn it on whenever "
                                        "you like."))

    # ---- 3. start with the account --------------------------------------
    if wanted["autostart"] != before["autostart"]:
        try:
            ok = autostart.set_enabled(wanted["autostart"])
        except Exception as exc:                       # never break setup on this
            ok = False
            warnings.append(f"autostart could not be changed: {exc}")
        if ok:
            changed.append("autostart " + ("on" if wanted["autostart"] else "off"))
            notes.append("Start with your account: " + ("on — one per-user entry, no "
                                                        "admin, removable from Task Manager."
                                                        if wanted["autostart"] else "off."))
        elif not warnings:
            warnings.append("the autostart setting did not take — the system refused the "
                            "write, so I am reporting it as off rather than pretending.")
    try:
        cfg["autostart"] = autostart.is_enabled()
    except Exception:
        cfg["autostart"] = wanted["autostart"]

    # ---- 4. documents ----------------------------------------------------
    docs = cfg.setdefault("docs", {})
    docs["index_on_start"] = wanted["documents"]
    docs.setdefault("ocr", False)
    if wanted["documents"] != before["documents"]:
        changed.append("document search " + ("on" if wanted["documents"] else "off"))
        notes.append("Document search is " + ("on — I will read Documents, Desktop and "
                                              "Downloads once, read-only, in the background. "
                                              "Nothing is uploaded and nothing is changed."
                                              if wanted["documents"] else
                                              "off. Say 'index my documents' whenever you "
                                              "want it."))

    cfg["first_run"] = False
    try:
        config.save(cfg)
        saved = True
    except Exception as exc:
        saved = False
        warnings.append(f"settings could not be written: {exc}")

    state = answers_from(cfg)
    state["open_mode"] = mode_of(cfg)
    if answers.get("open_mode") == "voice" and not state["autostart"]:
        warnings.append("\"hey jarvis\" will work while Arc Desk is running, but it will not "
                        "start by itself — the startup entry could not be created on this "
                        "machine. Open it once from the shortcut, then tell me again.")
    return {"changed": changed, "notes": notes, "warnings": warnings,
            "state": state, "saved": saved}


def summary(result: dict) -> str:
    """One paragraph for the console: what changed, what did not, and what it cost."""
    lines = []
    if result["changed"]:
        lines.append("Set up: " + ", ".join(result["changed"]))
    else:
        lines.append("Nothing changed — everything was already how you left it.")
    lines += result["notes"]
    lines += [f"⚠ {w}" for w in result["warnings"]]
    state = result.get("state") or {}
    lines.append("Opens by: " + ("voice — \"hey jarvis\"" if state.get("open_mode") == "voice"
                                  else "desktop icon (double-click)") +
                 " · wake word " + ("on" if state.get("wake") else "off") +
                 " · start with Windows " + ("on" if state.get("autostart") else "off") +
                 " · document search " + ("on" if state.get("documents") else "off") +
                 " · voice " + ("on" if state.get("voice") else "off"))
    if not result.get("saved", True):
        lines.append("These choices apply to this session only — the settings file could "
                     "not be written.")
    return "\n".join(lines)


def steps() -> list[dict]:
    """The questions, in order, for a UI that wants to render them generically."""
    return [
        {"key": "voice", "title": "Should I speak?",
         "detail": "Replies read aloud through your machine's voice. Off means text only.",
         "default": DEFAULTS["voice"], "cost": "nothing extra; it is the OS voice"},
        {"key": "wake", "title": "Should I listen for the wake word?",
         "detail": "The microphone stays open so 'hey jarvis' works without touching "
                   "anything. Ctrl+Alt+Q quits instantly.",
         "default": DEFAULTS["wake"], "cost": "a 60–150 MB daemon, and a live microphone"},
        {"key": "autostart", "title": "Should I start with your account?",
         "detail": "One per-user entry, no admin. Removable from Task Manager or here.",
         "default": DEFAULTS["autostart"], "cost": "it runs at every login until you say no"},
        {"key": "documents", "title": "Should I read your documents so search works?",
         "detail": "Word, Excel, PowerPoint, PDF and text, in Documents/Desktop/Downloads. "
                   "Read-only: nothing is uploaded, renamed or changed.",
         "default": DEFAULTS["documents"], "cost": "a few seconds once, then instant search"},
    ]
