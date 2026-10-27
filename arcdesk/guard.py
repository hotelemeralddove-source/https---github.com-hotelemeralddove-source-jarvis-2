"""Auto-throttle guards — the things that stop Arc Desk from ever being
the reason your laptop stutters.

Two triggers, both checked on a slow 10 s timer (cost: ~0):

  fullscreen  A fullscreen app (game / video) is in the foreground
              -> animation drops to 10 fps and the tray keeps working.
  battery     Running on battery, not plugged in
              -> animation drops to 20 fps.

Neither trigger overrides your explicit "pause animations" setting; they
only lower the ceiling.
"""
from __future__ import annotations

import sys

QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4


def fullscreen_app_active() -> bool:
    """Windows only. Returns False everywhere else (including Linux/macOS)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        state = ctypes.c_int(0)
        # SHQueryUserNotificationState -> HRESULT, writes a QUERY_USER_NOTIFICATION_STATE
        ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
        return state.value in (QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE)
    except Exception:
        return False


def on_battery() -> bool:
    try:
        import psutil
        b = psutil.sensors_battery()
        return bool(b is not None and not b.power_plugged)
    except Exception:
        return False


def desired_fps(base_fps: int) -> tuple[int, str]:
    """Return (fps, reason) after applying the guards."""
    if fullscreen_app_active():
        return min(base_fps, 10), "FULLSCREEN APP · THROTTLED"
    if on_battery():
        return min(base_fps, 20), "ON BATTERY · SAVER"
    return base_fps, ""
