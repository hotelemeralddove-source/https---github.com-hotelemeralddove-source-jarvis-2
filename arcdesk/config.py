"""Settings + file paths. JSON on disk, atomic writes, no database.

Stored in %APPDATA%\\ArcDesk on Windows, ~/.config/ArcDesk elsewhere.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

APP_NAME = "ArcDesk"

DEFAULTS: dict[str, Any] = {
    "mode": "chill",
    "animations": True,
    "fps_cap": None,            # None = follow the mode's own cap
    "effects": None,            # None = follow the mode's own scale
    "window": {"w": 1000, "h": 690, "x": None, "y": None},
    "shortcuts": [
        {"label": "FILES", "target": "explorer"},
        {"label": "NOTES", "target": "notepad"},
        {"label": "CALC", "target": "calc"},
        {"label": "TASKS", "target": "taskmgr"},
    ],
    "weather": {
        "enabled": False,       # OFF by default -> fully offline app
        "lat": 15.8497,         # Belagavi, default to the user's city
        "lon": 74.4977,
        "city": "Belagavi",
        "refresh_min": 20,
    },
    "ai": {
        "name": "JARVIS",          # what it calls itself out loud (Settings -> Brain)
        "enabled": True,
        "provider": "auto",      # auto | groq | gemini | openai | ollama | custom | lite
        "model": "",             # blank = provider default
        "api_key": "",           # prefer env vars: GROQ_API_KEY / GEMINI_API_KEY / OPENAI_API_KEY
        "base_url": "",
        "voice": True,
        "nudges": False,            # speak up unprompted (battery, disk, long session)           # speak replies via the OS voice
        # -10..10, 0 is the engine's normal speed. -2 is deliberately unhurried: the first
        # complaint about the voice was "speed ah pesuthu, ena solluthu nu puriyala".
        "voice_rate": -2,
        "voice_accent": "en-IN",     # which accent to look for among the installed voices
        "voice_pause_ms": 180,       # the breath between sentences
        "voice_clone": True,        # use the imported reference voice when possible
        # "my voice (quick)": pitch the reply onto the imported clip's own pitch. No engine,
        # no download, works the moment a clip is imported — see voicematch.py.
        "voice_match": True,
        "voice_engine": "auto",         # -5 .. 5
    },
    "wake": {
        "enabled": False,               # off by default: nothing listens to your mic
        "phrase": "hey jarvis",
        "engine": "auto",               # auto | vosk | openwakeword
        "port": 8765,
        # Patience, not a stopwatch: 12 s to start speaking, 1.8 s of silence to end,
        # and never a cut mid-sentence before 30 s. The old 7 s / 1.1 s pair is what made
        # JARVIS feel like it was not listening.
        "command_seconds": 12,
        "silence_seconds": 1.8,
        "max_command_seconds": 30,
        "converse": True,               # keep listening after an answer (6 turns)
        "converse_turns": 6,
        "voice_lock": False,        # only the enrolled voice may command it
        "barge_in": True,               # talking over JARVIS stops it
        "autostart_daemon": True,       # app spawns the daemon when enabled
    },
    "first_run": True,          # show the one-page welcome/setup card once
    "shadow": {
        # FALSE, and it matters. This used to default to True, which meant a person who
        # double-clicked the desktop icon got no window, no card, nothing — the honest
        # report for that is "installed, but it does not work". Stealth is what *booting
        # with Windows* asks for: the Run entry passes --shadow every boot (keep it that
        # way), and the desktop shortcut passes --show. A deliberate click must always
        # produce something on screen.
        "enabled": False,
        "hotkey_palette": "ctrl+alt+j",
        "hotkey_quit": "ctrl+alt+q",
        "hotkeys": True,
        "awaken": True,           # cinematic screen takeover when the wake word fires
        "awaken_mode": "chill",   # mode to land in after the awakening
        "tray": True,             # one normal tray icon, like any background app
        "preserve_windows": True, # never alter wallpaper / icons / taskbar / theme
        # What "BYE JARVIS" does to the application itself. The default is "exit" because
        # the promise is "the app opens and closes by voice", not "the app hides".
        #   hide  -> app stays in the background (instantest to reopen, tray icon stays)
        #   exit  -> app really quits; a small launcher daemon stays armed so
        #            "hey jarvis" can start it again. If nothing could hear you after
        #            closing (no mic library / no engine) this FALLS BACK to hide
        #            instead of quitting into silence.
        #   quit  -> app quits and nothing stays behind; reopen from the shortcut
        "bye_action": "exit",
        "relaunch_on_wake": True, # only used when bye_action = exit
    },
    # Floating charms (orbs, planets, butterflies, little bots) that draw straight onto
    # the desktop. They used to be ON by default, and the user's verdict on that was
    # blunt: "default ah desktop la floating icons varuthu". A first install should look
    # like nothing at all until asked; Settings -> Look turns them on.
    # Cinematic sound: generated in-app (arcdesk/sfx.py), one short cue per moment.
    # ON by default because it was asked for; every cue is one switch away from
    # silence, and a machine with no audio device simply plays nothing.
    "sfx": {
        "enabled": True,
        "volume": 0.55,
    },
    # How it talks to you: "Hi commander", "Thank you, commander", a task-related
    # acknowledgement, and a progress line only when the request is genuinely slow.
    "companion": {
        "enabled": True,
        "honorific": "commander",
        "greet": True,
        "farewell": True,
        "acks": True,
        "progress": True,
        "announce_done": False,
    },
    "charms": {
        "enabled": False,
        "user_choice": False,      # True once a person has actually toggled them
        "items": [
            {"kind": "reactor", "x": 120, "y": 160, "scale": 1.15, "speed": 1.0},
            {"kind": "planet", "x": 1420, "y": 240, "scale": 1.0, "speed": 0.7},
            {"kind": "butterfly", "x": 300, "y": 560, "scale": 0.8, "speed": 1.6},
            {"kind": "bot", "x": 1180, "y": 520, "scale": 0.9, "speed": 1.1},
        ],
    },
    "magic": {
        "enabled": True,              # "Hey JARVIS" -> full screen JARVIS workspace
        "exit_phrase": "bye jarvis",  # say this to return to normal Windows
        "wallpaper": True,            # swap the desktop wallpaper while active
        "restore_on_start": True,     # heal an interrupted session
    },
    "cost": {
        "enabled": True,
        "max_class": "free",      # local | free | paid   (paid only if you change this)
    },
    "mcp": {
        "enabled": True,
        "servers": [
            # {"name": "files", "command": "npx",
            #  "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/you/Documents"],
            #  "enabled": false}
        ],
    },
    # ---- the Vault: where your work lives (see vault.py)
    "vault": {
        "root": "",              # "" = %APPDATA%\ArcDesk\vault ; or any folder you like
        "portable": False,       # True = keep the vault next to the program (USB stick)
        "follow_answers": True,  # save each JARVIS answer into the open project as it happens
    },
    "autostart": False,
    "battery_saver": True,
    "minimise_to_tray_on_close": True,
}


def data_dir() -> Path:
    """Where settings, logs and caches live.

    Overridable with ARCDESK_HOME — that is what makes two things possible:
    a portable copy that keeps everything in its own folder (USB stick), and
    tests that cannot pollute the real settings of the person running them.
    """
    override = os.getenv("ARCDESK_HOME")
    if override:
        d = Path(override).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        return d
    if os.name == "nt":
        base = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path() -> Path:
    return data_dir() / "settings.json"


def weather_cache_path() -> Path:
    return data_dir() / "weather_cache.json"


# Kept for backwards compatibility (imported by a few modules at import time).
# NOT used by load()/save(): those call settings_path() every time, so a process that
# moves its data folder (or a tool that switches ARCDESK_HOME, like tools/move.py and
# the tests) reads and writes the folder it is actually pointing at.
SETTINGS_PATH = settings_path()
WEATHER_CACHE_PATH = weather_cache_path()


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _migrate(cfg: dict[str, Any]) -> dict[str, Any]:
    """One-way fixes for settings files written by an older build.

    Only rules that are true for everybody belong here, and each one records that it
    ran, so a person who turns the feature back on is never overruled twice.

    Rule 1 (2026-10): charms were ON by default. Anybody whose file says `enabled: true`
    without `user_choice: true` never chose that — it was the default talking — so it is
    switched off once and marked. Toggling them in Settings sets `user_choice`, and from
    then on this rule stays out of the way.
    """
    charms = cfg.get("charms")
    if isinstance(charms, dict):
        if charms.get("enabled") and not charms.get("user_choice") \
                and not charms.get("migrated_off"):
            charms["enabled"] = False
            charms["migrated_off"] = True

    # Rule 2 (2026-10, same shape): "start hidden" was the default AND `--shadow` was
    # written into the settings file. One boot with Windows therefore left every later
    # double-click starting a process with no window and only a tray icon — reported,
    # correctly, as "it installs but it does not work". Anybody who ticked the box in
    # Settings has `user_choice`, and is never touched again.
    shadow = cfg.get("shadow")
    if isinstance(shadow, dict):
        if shadow.get("enabled") and not shadow.get("user_choice") \
                and not shadow.get("migrated_off"):
            shadow["enabled"] = False
            shadow["migrated_off"] = True
    return cfg


def load() -> dict[str, Any]:
    try:
        # utf-8-sig: Windows PowerShell writes a BOM unless told not to, and a BOM
        # would otherwise throw here and silently reset every setting.
        raw = json.loads(settings_path().read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError("settings root is not an object")
        return _migrate(_merge(DEFAULTS, raw))
    except FileNotFoundError:
        return _migrate(json.loads(json.dumps(DEFAULTS)))
    except Exception:
        # Corrupt settings must never stop the app from booting.
        return _migrate(json.loads(json.dumps(DEFAULTS)))


def save(cfg: dict[str, Any]) -> None:
    """Atomic write: a crash mid-save can never leave a broken settings file.

    Keys starting with an underscore are "this launch only" (--shadow, --show and the
    other command-line switches). They are stripped here because a switch must never
    become a saved preference: that is how one `--shadow` boot used to turn every later
    double-click into a window that never appears.
    """
    try:
        cfg = {k: v for k, v in cfg.items() if not k.startswith("_")}
        target = settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        os.replace(tmp, target)
    except Exception:
        pass
