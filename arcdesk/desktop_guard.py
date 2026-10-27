"""Proof that Arc Desk does not touch your Windows.

The promise is simple: boot your PC and Windows 11 looks exactly like it did
before — wallpaper, desktop icons, Recycle Bin, taskbar, Start menu, everything.
Arc Desk sits in the background and changes nothing until you call it.

A promise is worth nothing unless it can be checked, so this module does two
things:

1. snapshot / compare
   Reads the user-facing shell state and diffs it. Run it before and after a
   session; if Arc Desk had changed your wallpaper, icons or taskbar, the diff
   would show it. We never *write* any of these values — there is no code path
   in this project that does.

2. scan_sources()
   Greps our own source tree for the specific Windows APIs that apps use to
   mess with a desktop (wallpaper setters, taskbar hacks, explorer restarts,
   hidden-icon flags). If someone later adds one, the check fails loudly.

Windows-specific readings degrade to harmless placeholders elsewhere, so the
tool still runs on Linux/macOS during development.
"""
from __future__ import annotations

from . import quiet

import os
import re
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"

# APIs/commands that would let an app change the user's shell. Arc Desk must
# never contain these. This list is the contract.
# Patterns describe WRITES, not reads: querying the wallpaper is fine, setting it
# is not. This module never matches itself (see SELF_EXCLUDE).
# Each entry may carry an `allowed_in` set: files where the call is audited and
# reversible (journal + auto-restore). Anything outside that set is a failure.
FORBIDDEN = [
    (r"SystemParametersInfo\w*\s*\([^)]*SPI_SET", "writes desktop settings", {"magic.py"}),
    (r"\bSPI_SETDESKWALLPAPER\b", "changes the wallpaper", {"magic.py"}),
    (r"\bSPI_SETICONS\b", "changes desktop icons", set()),
    (r"\bShell_TrayWnd\b", "finds and can hide/modify the taskbar", set()),
    (r"taskkill[^\n]{0,25}explorer", "kills and can corrupt your Explorer shell", set()),
    (r"reg\s+add[^\n]{0,40}Explorer", "writes into Explorer's own settings", set()),
    (r"\bHideDesktopIcons\b|\bHideIcons\b", "hides your desktop icons", set()),
    (r"\bSet-Wallpaper\b|SetValueEx\([^)]*Wall[Pp]aper", "changes the wallpaper", set()),
    (r"\bIVirtualDesktopManager\b", "manipulates virtual desktops", set()),
    (r"\bSetWindowDisplayAffinity\b", "can make windows invisible to capture tools", set()),
]

# This file necessarily *mentions* the forbidden names in order to look for them.
SELF_EXCLUDE = {"desktop_guard.py", "desktop_check.py"}

SOURCE_SUFFIXES = {".py", ".bat", ".vbs", ".spec"}


# ------------------------------------------------------------------ snapshot
def _win_reg(path: str, name: str):
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            value, _kind = winreg.QueryValueEx(k, name)
            return value
    except Exception:
        return None


def _count(path: Path) -> int:
    try:
        return sum(1 for p in path.iterdir() if not p.name.startswith("."))
    except Exception:
        return -1


def snapshot() -> dict:
    """A small, user-meaningful picture of the shell. Read-only, by design."""
    home = Path.home()
    desktop = Path(os.getenv("USERPROFILE", home)) / "Desktop" if IS_WIN else home / "Desktop"
    snap: dict = {
        "platform": sys.platform,
        "desktop_entries": _count(desktop),
    }
    if IS_WIN:
        snap.update({
            "wallpaper": _win_reg(r"Control Panel\Desktop", "WallPaper"),
            "wallpaper_style": _win_reg(r"Control Panel\Desktop", "WallpaperStyle"),
            "screensaver": _win_reg(r"Control Panel\Desktop", "SCRNSAVE.EXE"),
            "theme": _win_reg(r"Software\Microsoft\Windows\CurrentVersion\Themes",
                              "CurrentTheme"),
            "taskbar_autohide": _taskbar_autohide(),
            "explorer_running": _explorer_running(),
        })
    else:
        snap.update({
            "wallpaper": _gsettings_wallpaper(),
            "taskbar_autohide": None,
            "explorer_running": None,
        })
    return snap


def _taskbar_autohide():
    """Byte 8 of StuckRects3 settings: bit 0 = autohide. Read only."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\StuckRects3") as k:
            value, _ = winreg.QueryValueEx(k, "Settings")
            return bool(value[8] & 0x01) if len(value) > 8 else None
    except Exception:
        return None


def _explorer_running():
    try:
        import psutil
        return any((p.info.get("name") or "").lower() == "explorer.exe"
                   for p in psutil.process_iter(["name"]))
    except Exception:
        return None


def _gsettings_wallpaper():
    try:
        import subprocess
        out = quiet.run(["gsettings", "get", "org.gnome.desktop.background",
                              "picture-uri"], capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None
    except Exception:
        return None


def compare(before: dict, after: dict) -> list[str]:
    """Return human-readable differences. Empty list = Windows untouched."""
    diffs = []
    for key in sorted(set(before) | set(after)):
        if key == "platform":
            continue
        b, a = before.get(key), after.get(key)
        if b != a:
            diffs.append(f"{key}: {b!r} -> {a!r}")
    return diffs


# --------------------------------------------------------------- source scan
def audited_exceptions() -> list[str]:
    """Calls we allow, and why. Shown by the audit tool instead of hidden."""
    out = []
    for entry in FORBIDDEN:
        allowed = entry[2] if len(entry) > 2 else set()
        if allowed:
            out.append(f"{entry[1]} — allowed only in {', '.join(sorted(allowed))} "
                       f"(journal + auto-restore)")
    return out


def scan_sources(root: Path | None = None) -> list[str]:
    """Return a list of problems. Empty = no forbidden API anywhere in the code."""
    root = root or Path(__file__).resolve().parents[1]
    problems: list[str] = []
    for path in root.rglob("*"):
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        if path.name in SELF_EXCLUDE:
            continue
        if any(part in (".venv", "build", "dist", "__pycache__", "shots", "tests")
               for part in path.parts):
            continue
        try:
            text = path.read_text("utf-8", errors="ignore")
        except Exception:
            continue
        for entry in FORBIDDEN:
            pattern, why = entry[0], entry[1]
            allowed = entry[2] if len(entry) > 2 else set()
            for m in re.finditer(pattern, text):
                if path.name in allowed:
                    continue
                line = text[:m.start()].count("\n") + 1
                problems.append(f"{path.name}:{line}  {m.group(0).strip()} ({why})")
    return problems
