"""Global hotkeys — so commands work when Arc Desk has no window on screen.

Typed automation from *anywhere* needs one thing the window cannot give: a key
combination the OS routes to us even when we are not focused. On Windows that is
RegisterHotKey, which costs one thread blocked in GetMessage — effectively 0 %
CPU and 0 MB.

Design notes:
  * the thread that registers a hotkey must be the one pumping messages, so both
    live inside `_loop`
  * WM_HOTKEY arrives as a plain message; we turn it into a Qt signal, which is
    queued onto the GUI thread automatically
  * non-Windows: the listener reports `available=False` and the app simply works
    without global hotkeys (in-window Ctrl+J still works)
"""
from __future__ import annotations

import ctypes
import sys
import threading

from PySide6.QtCore import QObject, Signal

IS_WIN = sys.platform == "win32"

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
WM_HOTKEY = 0x0312

# Virtual key codes we care about (Windows)
VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "space": 0x20,
    "esc": 0x1B, "escape": 0x1B,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def parse_combo(text: str) -> tuple[int, int]:
    """'ctrl+alt+j' -> (modifiers, vk). Raises ValueError on nonsense."""
    mods = 0
    vk = None
    for part in (text or "").lower().replace(" ", "").split("+"):
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part in ("win", "super", "meta"):
            mods |= MOD_WIN
        elif part in VK:
            vk = VK[part]
        elif len(part) == 1:
            vk = ord(part.upper())
        else:
            raise ValueError(f"unknown key {part!r}")
    if vk is None:
        raise ValueError("combo needs a key, e.g. ctrl+alt+j")
    return mods, vk


class HotkeyListener(QObject):
    triggered = Signal(str)          # action id, e.g. "palette"
    failed = Signal(str)

    def __init__(self, combos: dict[str, str], parent: QObject | None = None) -> None:
        """combos: {"palette": "ctrl+alt+j", "quit": "ctrl+alt+q"}"""
        super().__init__(parent)
        self._combos = combos
        self._parsed: dict[int, str] = {}
        self._ids: list[int] = []
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.available = False
        self._thread_id: int | None = None

    # -- lifecycle -------------------------------------------------------
    def start(self) -> bool:
        if not IS_WIN:
            self.available = False
            return False
        if self._thread is not None:
            return self.available
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="arc-hotkeys")
        self._thread.start()
        self._ready.wait(timeout=3.0)
        return self.available

    def stop(self) -> None:
        if not IS_WIN or self._thread_id is None:
            return
        try:
            user32 = ctypes.windll.user32
            for i in self._ids:
                user32.UnregisterHotKey(None, i)
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
        except Exception:
            pass
        self._thread = None
        self._thread_id = None
        self.available = False

    # -- thread ----------------------------------------------------------
    def _loop(self) -> None:
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self._thread_id = kernel32.GetCurrentThreadId()

            idx = 1
            for action, combo in self._combos.items():
                try:
                    mods, vk = parse_combo(combo)
                except ValueError as exc:
                    self._safe_emit(self.failed, f"{action}: {exc}")
                    continue
                if user32.RegisterHotKey(None, idx, mods, vk):
                    self._parsed[idx] = action
                    self._ids.append(idx)
                    idx += 1
                else:
                    self._safe_emit(self.failed,
                                    f"{combo} already taken by another app")
            self.available = bool(self._ids)
            self._ready.set()
            if not self.available:
                return

            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    action = self._parsed.get(int(msg.wParam))
                    if action:
                        self._safe_emit(self.triggered, action)
        except Exception as exc:
            self.available = False
            self._safe_emit(self.failed, f"hotkey thread: {type(exc).__name__}: {exc}")
        finally:
            self._ready.set()
            try:
                for i in self._ids:
                    ctypes.windll.user32.UnregisterHotKey(None, i)
            except Exception:
                pass

    def _safe_emit(self, sig, *args) -> None:
        try:
            sig.emit(*args)
        except RuntimeError:
            pass


# ctypes.wintypes is not imported by default on non-Windows, and importing the
# module on Linux raises. Guard it so the rest of the app is platform-neutral.
if IS_WIN:
    import ctypes.wintypes  # noqa: E402,F401
else:  # pragma: no cover
    class _Stub:  # minimal placeholder so type hints never explode
        MSG = object
    ctypes.wintypes = _Stub  # type: ignore[attr-defined]
