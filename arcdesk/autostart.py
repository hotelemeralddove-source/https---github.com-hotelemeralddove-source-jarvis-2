"""Start with Windows — on purpose, reversibly, and only if you asked.

A startup entry is one of the few things a desktop app can do that outlives it, so
this module is deliberately boring:

* **Only your own account, only HKCU.** No admin, no HKLM, no service, no scheduled
  task with SYSTEM rights. A per-user Run key is reversible by deleting one value,
  which is the whole reason it was chosen.
* **Verify by reading it back.** "Enabled" is what the registry says, not what the
  code intended. Every write is followed by a read, and the read is what is returned.
* **Never hides itself.** The command it registers is the normal launcher — visible in
  Task Manager → Startup apps, removable from there, and disabling it inside ARC
  deletes the value immediately. Nothing self-heals, nothing re-registers.
* **Honest about the rebuild.** If ARC is later moved or reinstalled, the old path
  lingers; `status()` reports a path that no longer exists as `stale` rather than
  quietly claiming it works.

Linux and macOS are implemented too, because the tests run here: a freedesktop
`.desktop` file in `~/.config/autostart`, and a per-user LaunchAgent on macOS. Same
rules — per-user, reversible, readable back.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ArcDesk"
LINUX_ENTRY = "arcdesk.desktop"
MAC_LABEL = "ai.arena.arcdesk"


# ------------------------------------------------------------------- launcher
def launcher() -> list[str]:
    """The command that starts JARVIS. Frozen builds re-open the exe; source runs pythonw."""
    # `--shadow` is the real flag in run.py: start hidden, no window, no tray icon,
    # hotkeys live. Silent start, never stealth — Ctrl+Alt+Q still quits.
    if getattr(sys, "frozen", False):
        return [sys.executable, "--shadow"]
    script = Path(__file__).resolve().parents[1] / "run.py"
    if not script.is_file():
        script = Path(__file__).resolve().parents[1] / "arc_daemon.py"
    python = sys.executable
    if IS_WIN:
        windowless = Path(python).with_name("pythonw.exe")
        if windowless.is_file():
            python = str(windowless)
    return [python, str(script), "--shadow"]


def command_line(parts: list[str] | None = None) -> str:
    """Quoted, so a path with spaces still works (it is the #1 startup-entry bug).

    `parts` is only used by diagnostics and tests, which need to render a line that is
    not this machine's — the app itself always passes nothing and gets its own launcher.
    """
    chosen = launcher() if parts is None else list(parts)
    return " ".join(f'"{part}"' if " " in part else part for part in chosen)


def _fake() -> bool:
    """True when a test (or a support script) asked for a stand-in store.

    Why this exists: `tests/test_autostart_repair.py` has to prove that a stale entry is
    repaired, so it has to *write* an entry. On Windows that meant writing the real
    HKCU\\...\\Run value of the person running the tests — their laptop would then start
    JARVIS at the next login because a test ran. A test must never change the machine it
    is measuring, so with `ARCDESK_AUTOSTART_FAKE=1` the entry is a small JSON file.
    """
    return bool(os.environ.get("ARCDESK_AUTOSTART_FAKE"))


def _fake_path() -> Path:
    base = Path(os.environ.get("ARCDESK_HOME") or (Path.home() / ".arcdesk"))
    return base / "autostart-fake.json"


def _fake_read() -> str:
    try:
        import json
        return str(json.loads(_fake_path().read_text(encoding="utf-8")).get("command", ""))
    except (OSError, ValueError):
        return ""


def _fake_write(command: str) -> None:
    import json
    path = _fake_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"command": command}), encoding="utf-8")


def _linux_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "autostart" / LINUX_ENTRY


def _mac_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


# --------------------------------------------------------------------- status
def status() -> dict:
    """What is actually registered right now. Never inferred from config."""
    if _fake():
        command = _fake_read()
        if not command:
            return {"supported": True, "enabled": False, "detail": "not registered",
                    "command": command_line()}
        return _describe(command)
    if IS_WIN:
        try:
            import winreg
        except Exception:
            return {"supported": False, "enabled": False,
                    "detail": "the registry is not available in this build"}
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
        except FileNotFoundError:
            return {"supported": True, "enabled": False, "detail": "not registered",
                    "command": command_line()}
        except OSError as exc:
            return {"supported": True, "enabled": False,
                    "detail": f"could not read the key: {exc}", "command": command_line()}
        return _describe(str(value))

    if IS_MAC:
        path = _mac_path()
        if not path.is_file():
            return {"supported": True, "enabled": False, "detail": "not registered",
                    "command": command_line()}
        return {"supported": True, "enabled": True, "detail": f"LaunchAgent at {path}",
                "command": command_line(), "path": str(path)}

    path = _linux_path()
    if not path.is_file():
        return {"supported": True, "enabled": False, "detail": "not registered",
                "command": command_line()}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"supported": True, "enabled": False, "detail": f"unreadable: {exc}",
                "command": command_line()}
    hidden = "Hidden=true" in text.replace(" ", "")
    exec_line = next((line.split("=", 1)[1].strip() for line in text.splitlines()
                      if line.startswith("Exec=")), "")
    result = _describe(exec_line)
    result["path"] = str(path)
    if hidden:
        result["enabled"] = False
        result["detail"] = "an entry exists but is marked Hidden"
    return result


def _split_command(text: str) -> list[str]:
    """Tokens of a registered command line, with quotes respected.

    `str.split(" ")` is the wrong tool: `"C:/Program Files/Py/pythonw.exe" ".../run.py"`
    splits into `C:/Program`, `Files/...` — and then the "is it still there" check looks at
    a path that never existed, so a broken entry can pass for a healthy one.
    """
    tokens: list[str] = []
    cur: list[str] = []
    quoted = False
    for ch in text or "":
        if ch == '"':
            quoted = not quoted
            continue
        if ch.isspace() and not quoted:
            if cur:
                tokens.append("".join(cur))
                cur = []
            continue
        cur.append(ch)
    if cur:
        tokens.append("".join(cur))
    return tokens


def _describe(registered: str) -> dict:
    """Shared check: is the registered command still a real, runnable file?

    Two files matter, and both are checked: the interpreter *and* the script (or the exe
    on its own). Looking only at the first token is how "auto start is on" survived a
    re-unzip that moved run.py somewhere else — the python.exe it named still existed.
    """
    tokens = _split_command(registered)
    interpreter = tokens[0] if tokens else ""
    script = ""
    for token in tokens[1:]:
        if token.lower().endswith((".py", ".pyw")):
            script = token
            break
    target = script or interpreter                       # the thing that must be there
    missing = [t for t in (interpreter, script) if t and not Path(t).exists()]
    exists = bool(target) and not missing
    detail = ("registered and the program is there" if exists
              else f"registered, but {missing[0] if missing else target or 'the program'} "
                   f"is missing — re-enable to fix the path")
    return {
        "supported": True, "enabled": True, "registered": registered,
        "exe": target, "interpreter": interpreter, "missing": missing,
        "stale": not exists, "detail": detail, "command": command_line(),
    }


def enable(silent_start: bool = True) -> dict:
    """Register JARVIS to start with the user's session. Idempotent; returns the read-back."""
    cmd = command_line()
    if _fake():
        try:
            _fake_write(cmd)
        except OSError as exc:
            return {"ok": False, "error": f"could not write the stand-in entry: {exc}"}
        return {"ok": True, "state": status(), "mode": "stand-in (ARCDESK_AUTOSTART_FAKE)"}
    if IS_WIN:
        try:
            import winreg
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
        except Exception as exc:
            return {"ok": False, "error": f"Windows refused the write: {exc}"}
        return {"ok": True, "state": status(), "mode": "HKCU Run key"}

    if IS_MAC:
        path = _mac_path()
        parts = launcher()
        args = "\n".join(f"    <string>{p}</string>" for p in parts[1:])
        plist = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                 f'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                 f'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                 f'<plist version="1.0"><dict>\n'
                 f'  <key>Label</key><string>{MAC_LABEL}</string>\n'
                 f'  <key>ProgramArguments</key><array>\n'
                 f'    <string>{parts[0]}</string>\n{args}\n  </array>\n'
                 f'  <key>RunAtLoad</key><true/>\n'
                 f'</dict></plist>\n')
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(plist, encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": f"could not write the LaunchAgent: {exc}"}
        return {"ok": True, "state": status(), "mode": "per-user LaunchAgent"}

    path = _linux_path()
    entry = ("[Desktop Entry]\n"
             "Type=Application\n"
             "Name=Arc Desk\n"
             "Comment=Your desktop. Your universe.\n"
             f"Exec={cmd}\n"
             "X-GNOME-Autostart-enabled=true\n"
             "Terminal=false\n")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"could not write the autostart entry: {exc}"}
    return {"ok": True, "state": status(), "mode": "freedesktop autostart"}


def disable() -> dict:
    """Remove the entry. Deletes one registry value or one small file — nothing else."""
    if _fake():
        try:
            _fake_path().unlink()
        except FileNotFoundError:
            return {"ok": True, "state": status(), "note": "it was not enabled"}
        except OSError as exc:
            return {"ok": False, "error": f"could not remove the stand-in entry: {exc}"}
        return {"ok": True, "state": status(), "mode": "stand-in (ARCDESK_AUTOSTART_FAKE)"}
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            return {"ok": True, "state": status(), "note": "it was not enabled"}
        except OSError as exc:
            return {"ok": False, "error": f"Windows refused the delete: {exc}"}
        return {"ok": True, "state": status(), "mode": "HKCU Run key"}

    path = _mac_path() if IS_MAC else _linux_path()
    try:
        path.unlink()
    except FileNotFoundError:
        return {"ok": True, "state": status(), "note": "it was not enabled"}
    except OSError as exc:
        return {"ok": False, "error": f"could not remove the entry: {exc}"}
    return {"ok": True, "state": status(), "mode": path.name}


def toggle(on: bool | None = None) -> dict:
    """Enable or disable; `None` flips the current state."""
    current = status()
    if not current.get("supported"):
        return {"ok": False, "error": current.get("detail", "not supported here")}
    want = (not current.get("enabled")) if on is None else bool(on)
    return enable() if want else disable()


# ---------------------------------------------------------------------- report
def report(state: dict | None = None) -> str:
    """One honest paragraph. Says which key/value, and what was not touched."""
    state = state or status()
    if not state.get("supported"):
        return f"I cannot set autostart on this platform: {state.get('detail')}"
    where = {"win32": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run → ArcDesk",
             "darwin": "~/Library/LaunchAgents/ai.arena.arcdesk.plist"}.get(
        state.get("platform") or sys.platform)
    if not where:
        where = str(_linux_path())
    if state.get("enabled") and not state.get("stale"):
        return (f"JARVIS starts with your account. It is registered in:\n  {where}\n"
                f"  command: {state.get('command')}\n"
                f"No admin was used, no service was created, and nothing is hidden — it "
                f"appears in Task Manager → Startup apps like any other program.\n"
                f"Say 'stop starting with windows' to remove it.")
    if state.get("stale"):
        return (f"There is an entry, but it points at something that no longer exists:\n"
                f"  {state.get('registered')}\n"
                f"Re-enable it and I will write the current path.")
    return ("JARVIS does not start with your account. Say 'start with windows' and I will add "
            "one per-user entry — no admin, removable from Task Manager or from here.")


# --------------------------------------------------- compatibility shims
# settings.py and the quick menu were written against a two-function API. Keeping
# those names working is cheaper and safer than editing a UI file that cannot be run
# headlessly here — and it means an older build still imports cleanly.
def is_enabled() -> bool:
    """True only when the entry exists AND points at a program that is really there."""
    state = status()
    return bool(state.get("enabled")) and not bool(state.get("stale"))


def set_enabled(on: bool) -> bool:
    """Enable/disable and report the state read back from the system, not the intent."""
    result = toggle(bool(on))
    return bool(result.get("ok")) and is_enabled() == bool(on)


def repair() -> dict:
    """An entry that is ON but points at a folder that no longer exists: fix it.

    The report: *"laptop shutdown pannitu again on pannum pothu auto start aaganum"* — and
    it did not, because the folder had been unzipped again under a new name
    (`JARVIS-ready (1)`), so the registered command pointed at a path that was gone. The
    entry was still there, so nothing looked wrong; `strict` reading said "stale".

    The rule this keeps: **repair only what is already on.** A person who turned autostart
    off gets silence, never a surprise at the next login. Nothing is ever registered here
    that was not registered before.
    """
    state = status()
    if not state.get("supported"):
        return {"ok": True, "action": "unsupported", "state": state}
    if not state.get("enabled"):
        return {"ok": True, "action": "off", "state": state}      # their choice, not ours
    if not state.get("stale"):
        return {"ok": True, "action": "fine", "state": state}
    was = str(state.get("exe") or "")
    got = enable()
    fixed = bool(got.get("ok")) and is_enabled()
    return {"ok": fixed, "action": "repaired" if fixed else "failed",
            "was": was, "now": command_line(), "state": status(), "error": got.get("error", "")}


def folder() -> str:
    """The folder a repaired entry would point at — so a script can show it before asking."""
    parts = launcher()
    for part in parts:
        if part.lower().endswith(("run.py", "arc_daemon.py", ".exe")):
            return str(Path(part).parent)
    return str(Path(parts[0]).parent)


def store_path() -> str:
    """Exactly where the entry lives, so a diagnostic can point at the real thing."""
    if _fake():
        return str(_fake_path())
    if IS_WIN:
        return f"HKEY_CURRENT_USER\\{RUN_KEY}\\{VALUE_NAME}"
    if IS_MAC:
        return str(_mac_path())
    return str(_linux_path())


# The offer is made once. Without this, "start with the computer" would be re-asked at
# every launch, which is nagging; with it, a person who said no is left alone for good.
def first_time_pending() -> bool:
    """True while the first-run card may still offer to start with the computer."""
    from . import config
    return not bool(config.load().get("autostart_asked"))


def mark_first_time_done() -> None:
    """Remember that the offer has been made — never sets the entry itself."""
    from . import config
    cfg = config.load()
    if not cfg.get("autostart_asked"):
        cfg["autostart_asked"] = True
        config.save(cfg)


def ensure_first_time(pending: dict | None = None, portable: bool | None = None) -> dict:
    """First launch: switch it on, once, and say so. Never on a portable copy.

    *"JARVIS pc start aagum bothu automatic ah start aaganum machi"* is a requirement, not
    a preference, so the first launch turns it on instead of hoping somebody finds the
    checkbox. It stays reversible in three places (Settings, the tray menu, AUTO-START.bat)
    and it never re-turns itself on after being switched off.

    A portable copy (ARCDESK_HOME set) is skipped on purpose: a startup entry that points
    inside a USB stick or a throw-away test folder is a broken entry waiting to happen.
    """
    # A portable copy keeps everything in its own folder; a startup entry that points into
    # a USB stick is a broken entry waiting to happen. `portable` lets a caller (and a test)
    # state this explicitly instead of depending on the environment it happens to run in.
    is_portable = (bool(os.environ.get("ARCDESK_HOME")) if portable is None else portable)
    if is_portable:
        return {"ok": True, "action": "portable"}
    if not first_time_pending():
        return {"ok": True, "action": "already offered"}
    mark_first_time_done()                     # once, even if registering fails
    if is_enabled():
        return {"ok": True, "action": "already on"}
    got = enable()
    return {"ok": bool(got.get("ok")) and is_enabled(),
            "action": "enabled" if got.get("ok") and is_enabled() else "failed",
            "folder": folder(), "error": got.get("error", "")}


def describe_state(state: dict) -> str:
    if state.get("enabled") and not state.get("stale"):
        return "on"
    return "off"
