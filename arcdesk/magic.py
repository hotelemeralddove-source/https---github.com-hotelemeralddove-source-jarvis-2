"""Magic Mode — the "total system change" feeling, without breaking your Windows.

WHAT THIS DOES
  Enter  : swaps the desktop wallpaper to an ARC one, and shows our own fullscreen
           ARC workspace that *covers* the taskbar.
  Exit   : puts the old wallpaper back and disappears.

WHAT THIS DELIBERATELY DOES NOT DO
  We never replace Explorer as the shell, never kill explorer.exe, never change the
  taskbar's own settings. Those are the things that actually break a Windows install
  (lost Start menu, no file dialogs, black screen if the app dies, breakage on
  updates). Covering the taskbar with a topmost window gives the same "whole screen
  changed" feeling with zero OS risk.

SAFETY: THE JOURNAL
  Before touching anything we write `magic_journal.json` containing what the value
  was. Every exit path — normal, Esc, Ctrl+Alt+Q, even Task Manager kill — leaves
  that file behind until the restore succeeds. `restore_if_needed()` runs at app
  start, so an interrupted session heals itself on the next boot.

  Also: we only ever touch HKCU (current user), never HKLM. No admin rights.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from . import config

IS_WIN = sys.platform == "win32"

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

JOURNAL = config.data_dir() / "magic_journal.json"
ARC_WALLPAPER = config.data_dir() / "arc_wallpaper.png"


# ------------------------------------------------------------- wallpaper API
def get_wallpaper() -> str:
    if not IS_WIN:
        return ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETDESKWALLPAPER, len(buf), buf, 0)
        return buf.value if ok else ""
    except Exception:
        return ""


def set_wallpaper(path: str) -> tuple[bool, str]:
    if not IS_WIN:
        return False, "wallpaper control is Windows-only"
    try:
        import ctypes
        if path and not Path(path).exists():
            return False, f"file not found: {path}"
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        return (True, path) if ok else (False, "SystemParametersInfoW returned 0")
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


# ----------------------------------------------------------------- journal
def _read_journal() -> dict | None:
    try:
        data = json.loads(JOURNAL.read_text("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write_journal(data: dict) -> None:
    try:
        JOURNAL.write_text(json.dumps(data, indent=2), "utf-8")
    except Exception:
        pass


def _clear_journal() -> None:
    try:
        JOURNAL.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------- controller
class MagicController:
    def __init__(self) -> None:
        self.active = False
        self.wallpaper_changed = False
        self.last_error = ""

    # -- state -----------------------------------------------------------
    @property
    def journal_pending(self) -> bool:
        j = _read_journal()
        return bool(j and j.get("active"))

    # -- enter -----------------------------------------------------------
    def enter(self, wallpaper_png: Path | None = None, change_wallpaper: bool = True) -> tuple[bool, str]:
        """Returns (ok, human-readable detail). Never raises."""
        if self.active:
            return True, "already active"
        before = get_wallpaper()
        _write_journal({"active": True, "wallpaper_before": before,
                        "wallpaper_after": "", "started": time.time()})
        detail = []
        if change_wallpaper and wallpaper_png is not None:
            ok, info = set_wallpaper(str(wallpaper_png))
            if ok:
                self.wallpaper_changed = True
                j = _read_journal() or {}
                j["wallpaper_after"] = str(wallpaper_png)
                _write_journal(j)
                detail.append("wallpaper swapped")
            else:
                self.last_error = info
                detail.append(f"wallpaper unchanged ({info})")
        elif not IS_WIN:
            detail.append("visual takeover only (no OS wallpaper API on this platform)")
        else:
            detail.append("visual takeover only (wallpaper off in settings)")
        self.active = True
        return True, " · ".join(detail)

    # -- exit ------------------------------------------------------------
    def exit(self) -> tuple[bool, str]:
        j = _read_journal() or {}
        before = j.get("wallpaper_before") or ""
        restored = False
        detail = "returned to normal"
        if self.wallpaper_changed and before:
            ok, info = set_wallpaper(before)
            restored = ok
            detail = "wallpaper restored" if ok else f"wallpaper restore failed ({info})"
        elif self.wallpaper_changed and not before:
            detail = "wallpaper left as-is (no original recorded)"
        self.active = False
        self.wallpaper_changed = False
        if restored or not before:
            _clear_journal()
        return True, detail

    # -- crash recovery --------------------------------------------------
    def restore_if_needed(self) -> str | None:
        """Call once at startup. Heals an interrupted session."""
        j = _read_journal()
        if not j or not j.get("active"):
            return None
        before = j.get("wallpaper_before") or ""
        if before and j.get("wallpaper_after"):
            ok, info = set_wallpaper(before)
            if ok:
                _clear_journal()
                return "restored your wallpaper from an interrupted magic session"
            return f"could not restore wallpaper: {info}"
        _clear_journal()
        return "cleared a stale magic session"


# ------------------------------------------------------------------ wallpaper art
def render_wallpaper(path: Path, theme, width: int = 2560, height: int = 1440) -> bool:
    """Paint an JARVIS wallpaper with QPainter — no image assets, any resolution."""
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient

        pm = QPixmap(width, height)
        pm.fill(QColor(theme.bg))
        q = QPainter(pm)
        q.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        grad = QLinearGradient(0, 0, width * 0.4, height)
        grad.setColorAt(0.0, QColor(theme.panel))
        grad.setColorAt(0.55, QColor(theme.bg))
        grad.setColorAt(1.0, QColor(theme.bg).darker(115))
        q.fillRect(0, 0, width, height, grad)

        cx, cy = width * 0.5, height * 0.52
        accent = QColor(theme.accent)
        accent2 = QColor(theme.accent2)

        # big soft reactor bloom
        halo = QRadialGradient(QPointF(cx, cy), min(width, height) * 0.55)
        halo.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 60))
        halo.setColorAt(0.45, QColor(accent.red(), accent.green(), accent.blue(), 22))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(halo)
        q.drawEllipse(QPointF(cx, cy), min(width, height) * 0.55, min(width, height) * 0.55)

        # faint concentric rings + ticks
        base = min(width, height) * 0.38
        q.setBrush(Qt.BrushStyle.NoBrush)
        for i, factor in enumerate((1.0, 0.76, 0.52)):
            col = accent if i % 2 == 0 else accent2
            q.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 46 - i * 10), 2.0))
            q.drawEllipse(QPointF(cx, cy), base * factor, base * factor)
        q.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 34), 1.2))
        import math
        for i in range(96):
            ang = math.radians(i * 3.75)
            r1 = base * 1.02
            r2 = base * (0.98 if i % 4 else 0.95)
            q.drawLine(QPointF(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1),
                       QPointF(cx + math.cos(ang) * r2, cy + math.sin(ang) * r2))

        # subtle grid so icons stay readable
        q.setPen(QPen(QColor(255, 255, 255, 6), 1))
        step = max(48, width // 40)
        for x in range(0, width, step):
            q.drawLine(x, 0, x, height)
        for y in range(0, height, step):
            q.drawLine(0, y, width, y)

        q.end()
        path.parent.mkdir(parents=True, exist_ok=True)
        return bool(pm.save(str(path), "PNG"))
    except Exception:
        return False
