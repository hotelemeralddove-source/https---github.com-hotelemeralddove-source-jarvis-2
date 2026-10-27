"""Doing things on the machine — the "act on it" half of an assistant.

`tools.py` covers the safe, curated actions (volume, screenshots, notes, drawing).
This module is the bigger reach: switch windows, type, press keys, make files,
read files, run a command. That reach is exactly what makes an assistant feel real
— and exactly what makes it dangerous — so the rules are written down here, in
code, not in a README:

1. **Anything that can lose data needs a human click.** `file_delete` and
   `run_command` are registered with `confirm=True`; the agent loop cannot skip it.

2. **Nothing runs elevated.** No UAC prompt, no `runas`, no service. If a task
   needs admin rights, ARC says so and stops. This app has no business holding
   administrator power on a machine it can also be told to do anything on.

3. **Paths stay inside the user's own space.** Writes are refused outside the home
   folder, so a misheard sentence cannot drop a file into `C:\\Windows`.

4. **Commands are refused by pattern, not by hope.** A blocklist for the classic
   irreversible ones (format, diskpart, bcdedit, reg delete, `rm -rf /`) is checked
   before anything runs.

5. **Every action is journalled.** `~/ArcDesk/logs/actions.log`, one line each —
   what ran, with what arguments, and what happened. You can always find out what
   it did while you were not looking.

6. **OS gaps are spoken plainly.** Window control is PowerShell on Windows,
   `xdotool` on Linux, `osascript` on macOS; if none is present the tool says which
   package would fix it instead of pretending to work.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

from . import quiet
import sys
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# The fence: writes are only allowed inside this folder. Overridable so tests and
# the capability probe cannot touch a real home directory.
HOME = Path(os.environ.get("ARCDESK_USER_HOME") or Path.home())
MAX_READ = 64 * 1024          # bytes
MAX_LINES = 200
MAX_OUTPUT = 1200
CMD_TIMEOUT = 30

# Irreversible, machine-destroying or privilege-escalating patterns. Refused before
# execution; the user is told which word tripped it.
BLOCKED = [
    (r"\bformat\s+[a-z]:", "disk format"),
    (r"\bdiskpart\b", "disk partitioning"),
    (r"\bbcdedit\b", "boot configuration"),
    (r"\breg\s+delete\b", "registry deletion"),
    (r"\bdel\s+/[fsq]\b", "force delete"),
    (r"\brd\s+/s\b|\brmdir\s+/s\b", "recursive directory delete"),
    (r"\brm\s+-[rf]{1,2}\s+/", "recursive delete of root"),
    (r"\bmkfs\b", "filesystem creation"),
    (r"\bcipher\s+/w\b", "free-space wipe"),
    (r"\btakeown\b|\bicacls\b", "ownership/permission change"),
    (r"\bshutdown\b|\breboot\b", "shutdown (use the power tool, which is gated)"),
    (r"\brunas\b|\belevate\b|\bsudo\b", "privilege escalation"),
    (r":\(\)\s*\{.*\};:", "fork bomb"),
    (r"\bnet\s+user\b|\bnet\s+localgroup\b", "account manipulation"),
    (r"\bcurl\b.*\|\s*(ba)?sh", "piping a download into a shell"),
]


# ------------------------------------------------------------------ journalling
def journal(action: str, detail: str, result: str) -> None:
    """One line per action, in the user's own home. Never raises."""
    try:
        from . import config
        log_dir = Path(config.data_dir()) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{action}\t"
                f"{(detail or '').replace(chr(9), ' ')[:300]}\t"
                f"{(result or '').replace(chr(9), ' ')[:300]}\n")
        with open(log_dir / "actions.log", "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def recent_actions(limit: int = 20) -> str:
    try:
        from . import config
        path = Path(config.data_dir()) / "logs" / "actions.log"
        if not path.exists():
            return "no actions logged yet"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:]) or "no actions logged yet"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# ------------------------------------------------------------------ shell helper
def _run(cmd, timeout: float = 8.0, shell: bool = False) -> str:
    try:
        out = quiet.run(cmd, capture_output=True, text=True, timeout=timeout,
                             shell=shell, errors="replace")
        return ((out.stdout or "").strip() or (out.stderr or "").strip())[:MAX_OUTPUT]
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _ps(script: str, timeout: float = 8.0) -> str:
    if not IS_WIN:
        return "not available"
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-Command", script], timeout=timeout)


# ------------------------------------------------------------------ windows
def _win_windows(action: str, title: str) -> str:
    q = (title or "").replace("'", "''")
    if action == "list":
        return _ps(
            "Get-Process | Where-Object { $_.MainWindowTitle -ne '' } | "
            "ForEach-Object { \"$($_.ProcessName) :: $($_.MainWindowTitle)\" } | "
            "Select-Object -First 40")
    if action == "minimize_all":
        return _ps("(New-Object -ComObject Shell.Application).MinimizeAll()") or "all minimized"
    if action in ("focus", "minimize", "maximize", "restore", "close_window"):
        show = {"minimize": 6, "maximize": 3, "restore": 9}.get(action, 9)
        if action == "focus":
            body = (f"(New-Object -ComObject WScript.Shell).AppActivate('{q}')")
        elif action == "close_window":
            body = (f"$p=Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{q}*' }} | "
                    "Select-Object -First 1; if($p){$p.CloseMainWindow();'closed'}else{'no window'}")
        else:
            body = ("Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
                    "public class W{[DllImport(\"user32.dll\")]public static extern bool ShowWindow"
                    "(IntPtr h,int c);[DllImport(\"user32.dll\")]public static extern bool "
                    "SetForegroundWindow(IntPtr h);}';"
                    f"$p=Get-Process | Where-Object {{ $_.MainWindowTitle -like '*{q}*' }} | "
                    f"Select-Object -First 1; if($p){{[W]::ShowWindow($p.MainWindowHandle,{show}) "
                    f"| Out-Null; [W]::SetForegroundWindow($p.MainWindowHandle) | Out-Null; "
                    "'ok'} else {'no window'}")
        return _ps(body)
    return f"ERROR: unknown window action '{action}'"


def _linux_windows(action: str, title: str) -> str:
    xdotool = shutil.which("xdotool")
    if not xdotool:
        return ("ERROR: window control needs xdotool on Linux (sudo apt install xdotool). "
                "On Windows this works out of the box.")
    search = title or ""
    if action == "list":
        return _run([xdotool, "search", "--onlyvisible", "--name", "."], timeout=5) or "no windows"
    if action == "minimize_all":
        return _run([xdotool, "key", "super+d"], timeout=5) or "sent super+d"
    if action in ("focus", "minimize", "maximize", "restore", "close_window"):
        ids = _run([xdotool, "search", "--name", search], timeout=5).split()
        if not ids:
            return f"no window matching {search!r}"
        wid = ids[-1]
        arg = {"focus": "activate", "minimize": "windowminimize",
               "maximize": "windowmaximize", "restore": "windowmap",
               "close_window": "windowkill"}[action]
        return _run([xdotool, arg, wid], timeout=5) or f"{action} {wid}"
    return f"ERROR: unknown window action '{action}'"


def _mac_windows(action: str, title: str) -> str:
    q = (title or "").replace('"', '\\"')
    if action == "list":
        return _run(["osascript", "-e",
                     'tell application "System Events" to get name of every process '
                     'whose background only is false'], timeout=6)
    if action == "minimize_all":
        return _run(["osascript", "-e",
                     'tell application "System Events" to keystroke "m" using {command down, '
                     'option down}'], timeout=6) or "minimized"
    script = {
        "focus": f'tell application "{q}" to activate',
        "close_window": f'tell application "{q}" to close front window',
        "minimize": f'tell application "{q}" to set miniaturized of front window to true',
        "maximize": f'tell application "{q}" to set zoomed of front window to true',
        "restore": f'tell application "{q}" to set zoomed of front window to false',
    }.get(action)
    if not script:
        return f"ERROR: unknown window action '{action}'"
    return _run(["osascript", "-e", script], timeout=6) or action


def windows(action: str = "list", title: str = "") -> str:
    action = (action or "list").lower().strip()
    out = (_win_windows if IS_WIN else _mac_windows if IS_MAC else _linux_windows)(action, title)
    journal("windows", f"{action} {title}".strip(), out)
    return out or f"{action}: done"


# ------------------------------------------------------------------ typing / keys
_SENDKEYS_SPECIAL = set("()+{}[]^%~")


def _escape_sendkeys(text: str) -> str:
    out = []
    for ch in text:
        if ch in _SENDKEYS_SPECIAL:
            out.append("{" + ch + "}")
        elif ch == "\n":
            out.append("{ENTER}")
        elif ch == "\t":
            out.append("{TAB}")
        else:
            out.append(ch)
    return "".join(out)


_COMBO = {"ctrl": "^", "control": "^", "alt": "%", "shift": "+", "win": "^{ESC}"}


def _combo_to_sendkeys(keys: str) -> str:
    parts = [p.strip().lower() for p in re.split(r"\+|\s+", keys.strip()) if p.strip()]
    if not parts:
        return ""
    mods = ""
    for p in parts[:-1]:
        mods += _COMBO.get(p, "")
    key = parts[-1]
    named = {"enter": "{ENTER}", "tab": "{TAB}", "esc": "{ESC}", "escape": "{ESC}",
             "space": " ", "backspace": "{BACKSPACE}", "delete": "{DELETE}",
             "up": "{UP}", "down": "{DOWN}", "left": "{LEFT}", "right": "{RIGHT}",
             "home": "{HOME}", "end": "{END}", "pgup": "{PGUP}", "pgdn": "{PGDN}",
             "f1": "{F1}", "f2": "{F2}", "f3": "{F3}", "f4": "{F4}", "f5": "{F5}",
             "f6": "{F6}", "f7": "{F7}", "f8": "{F8}", "f9": "{F9}", "f10": "{F10}",
             "f11": "{F11}", "f12": "{F12}"}
    return mods + named.get(key, key)


def type_text(text: str, delay: float = 0.0) -> str:
    """Type into whatever window has focus. Clipboard-paste is not used: SendKeys
    types the characters, so this works in apps that block paste.

    `delay` waits first — "open notepad and type hello" needs the window to exist
    before the keystrokes arrive.
    """
    if delay and delay > 0:
        time.sleep(min(float(delay), 5.0))
    if not text:
        return "ERROR: nothing to type"
    if len(text) > 2000:
        return "ERROR: text too long for one call (2000 characters max)"
    if IS_WIN:
        out = _ps(f"$w=New-Object -ComObject WScript.Shell; "
                  f"$w.SendKeys('{_escape_sendkeys(text).replace(chr(39), chr(39) * 2)}')")
    elif IS_MAC:
        out = _run(["osascript", "-e",
                    'tell application "System Events" to keystroke "'
                    + text.replace('"', '\\"') + '"'], timeout=10)
    else:
        xdotool = shutil.which("xdotool")
        out = (_run([xdotool, "type", "--clearmodifiers", text], timeout=10)
               if xdotool else "ERROR: typing needs xdotool on Linux")
    journal("type_text", f"{len(text)} chars", out or "typed")
    return out or f"typed {len(text)} characters"


def press(keys: str) -> str:
    """Send a keystroke or chord: 'enter', 'ctrl+s', 'alt+tab', 'ctrl+shift+t'."""
    combo = _combo_to_sendkeys(keys)
    if not combo:
        return "ERROR: no keys given"
    if IS_WIN:
        out = _ps(f"$w=New-Object -ComObject WScript.Shell; $w.SendKeys('{combo}')")
    elif IS_MAC:
        out = _run(["osascript", "-e",
                    'tell application "System Events" to keystroke "'
                    + combo.replace('^', '').replace('"', '\\"') + '"'], timeout=10)
    else:
        xdotool = shutil.which("xdotool")
        out = (_run([xdotool, "key", "--clearmodifiers", keys], timeout=10)
               if xdotool else "ERROR: key presses need xdotool on Linux")
    journal("press", keys, out or "sent")
    return out or f"pressed {keys}"


# ------------------------------------------------------------------ files
def _safe_path(raw: str) -> Path:
    """Resolve a user path and refuse anything outside their home folder."""
    p = Path(os.path.expandvars(os.path.expanduser((raw or "").strip())))
    if not p.is_absolute():
        p = HOME / p
    p = p.resolve()
    try:
        p.relative_to(HOME.resolve())
    except ValueError:
        raise ValueError(f"refusing to touch {p} — outside your home folder")
    return p


def file_op(action: str = "write", path: str = "", target: str = "", text: str = "") -> str:
    """mkdir, write, append, copy, rename — the creating half of file work."""
    action = (action or "write").lower().strip()
    try:
        p = _safe_path(path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    try:
        if action == "mkdir":
            p.mkdir(parents=True, exist_ok=True)
            res = f"created folder {p}"
        elif action in ("write", "append"):
            p.parent.mkdir(parents=True, exist_ok=True)
            backup = ""
            if action == "write" and p.exists() and p.stat().st_size:
                # never silently destroy an existing file: keep the previous version
                bak = p.with_name(f"{p.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak")
                shutil.copy2(p, bak)
                backup = f" (previous version kept as {bak.name})"
            mode = "w" if action == "write" else "a"
            with open(p, mode, encoding="utf-8") as fh:
                fh.write(text or "")
            res = (f"{'wrote' if action == 'write' else 'appended'} {p} "
                   f"({len(text or '')} chars){backup}")
        elif action in ("copy", "rename", "move"):
            if not target:
                return "ERROR: copy/rename need a target path"
            dst = _safe_path(target)
            if not p.exists():
                return f"ERROR: {p} does not exist"
            dst.parent.mkdir(parents=True, exist_ok=True)
            if action == "copy":
                shutil.copy2(p, dst)
                res = f"copied {p.name} to {dst}"
            else:
                p.replace(dst) if not dst.exists() else shutil.move(str(p), str(dst))
                res = f"moved {p.name} to {dst}"
        else:
            return f"ERROR: unknown file action '{action}'"
    except Exception as exc:
        res = f"ERROR: {type(exc).__name__}: {exc}"
    journal("file_op", f"{action} {path} {target}".strip(), res)
    return res


def file_delete(path: str) -> str:
    """Delete a file or empty folder inside the home folder. Confirm-gated, and it
    moves to the OS trash when one is available."""
    try:
        p = _safe_path(path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    if not p.exists():
        return f"ERROR: {p} does not exist"
    try:
        trash = shutil.which("gio") or shutil.which("trash-put")
        if trash and not IS_WIN:
            _run([trash, "trash", str(p)], timeout=10)
            res = f"moved {p.name} to the trash"
        else:
            p.unlink() if p.is_file() else p.rmdir()
            res = f"deleted {p}"
    except Exception as exc:
        res = f"ERROR: {type(exc).__name__}: {exc}"
    journal("file_delete", str(path), res)
    return res


def read_file(path: str = "", lines: int = 40) -> str:
    """Read a text file, size-capped so a log file cannot flood the context."""
    try:
        p = _safe_path(path)
    except ValueError as exc:
        return f"ERROR: {exc}"
    if not p.is_file():
        return f"ERROR: {p} is not a file"
    if p.stat().st_size > MAX_READ:
        return f"ERROR: {p.name} is larger than {MAX_READ // 1024} KB — open it in an editor"
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
    if "\x00" in raw[:1000]:
        return f"ERROR: {p.name} looks binary"
    keep = max(1, min(int(lines or 40), MAX_LINES))
    chunk = raw.splitlines()[:keep]
    journal("read_file", str(path), f"{len(chunk)} lines")
    return "\n".join(chunk)[:MAX_OUTPUT] or "(empty file)"


# ------------------------------------------------------------------ commands
def check_command(command: str) -> str:
    """"" when the command is acceptable, otherwise the reason it was refused."""
    low = (command or "").lower()
    for pattern, reason in BLOCKED:
        if re.search(pattern, low):
            return reason
    return ""


def run_command(command: str = "", timeout: float = 20.0) -> str:
    """Run a shell command. Confirm-gated, blocklisted, time-limited, output-capped."""
    command = (command or "").strip()
    if not command:
        return "ERROR: nothing to run"
    reason = check_command(command)
    if reason:
        journal("run_command", command, f"REFUSED: {reason}")
        return (f"ERROR: refused — this looks like {reason}. "
                f"I will not run it. If you really need it, do it yourself.")
    cap = max(1.0, min(float(timeout or 20.0), CMD_TIMEOUT))
    try:
        out = quiet.run(command, shell=True, capture_output=True, text=True,
                             timeout=cap, errors="replace")
        text = ((out.stdout or "").strip() or (out.stderr or "").strip())
        res = f"exit {out.returncode}: {text[:MAX_OUTPUT] or '(no output)'}"
    except subprocess.TimeoutExpired:
        res = f"ERROR: still running after {cap:.0f}s — I stopped waiting"
    except Exception as exc:
        res = f"ERROR: {type(exc).__name__}: {exc}"
    journal("run_command", command, res)
    return res
