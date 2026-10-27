"""The automation layer — the part that makes JARVIS an assistant and not a chatbot.

Design rules:
  * Every tool returns a STRING (success or a clean error). The model reads it.
  * Nothing here raises into the agent loop; `call()` is the only entry point
    and it always answers.
  * Destructive tools are flagged `confirm=True`; the UI asks the user before
    they run. ARC cannot shutdown your PC on its own.
  * OS-specific actions degrade honestly: a Windows path first, then macOS, then
    Linux (amixer / playerctl / brightnessctl / loginctl / xclip), and a plain
    "not available on this system" when none exists. `platforms=(...)` is kept
    for a tool that cannot be emulated anywhere else at all.
  * Tools that need the GUI (mode switch, timers) go through `host` signals so
    they execute on the main thread, never in the worker thread.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from .. import quiet
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import re

# Imported eagerly: cheap, and used by tools that must answer instantly.
from .. import actions, comms, config, knows, macros, profile


# Imported on first use: `vision` pulls in numpy and Pillow (~55 ms) and `uia` opens
# Windows' accessibility layer. Both are real, neither is needed to draw the window — and
# a startup that spends 55 ms on an image library has already lost the argument.
def _vision():
    from .. import vision
    return vision


def _uia():
    from .. import uia
    return uia

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Set by MainWindow so GUI-bound tools can hop to the main thread.
host: Any = None
# Set by the app once MCP servers are up; None = MCP disabled.
mcp_manager: Any = None
# The drawing currently on the easel, so "make it bigger" has something to act on.
current_sketch: Any = None


def bind_mcp(manager: Any) -> None:
    global mcp_manager
    mcp_manager = manager


def bind_host(obj: Any) -> None:
    global host
    host = obj


@dataclass
class Tool:
    name: str
    description: str
    params: dict = field(default_factory=dict)
    required: tuple = ()
    func: Callable[..., str] | None = None
    confirm: bool = False
    platforms: tuple | None = None
    max_len: int = 1500          # how much of the result the model gets to see


# --------------------------------------------------------------- helpers
def _run(cmd: list[str] | str, timeout: float = 8.0, shell: bool = False) -> str:
    try:
        out = quiet.run(cmd, capture_output=True, text=True, timeout=timeout,
                             shell=shell, errors="replace")
        return (out.stdout or "").strip() or (out.stderr or "").strip()
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _ps(script: str, timeout: float = 8.0) -> str:
    """Run a PowerShell snippet (hidden window). Windows only."""
    if not IS_WIN:
        return "not available"
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                 "-Command", script], timeout=timeout)


def _appdata() -> Path:
    return config.data_dir()


def _open_path(target: str) -> str:
    if not target:
        return "ERROR: nothing to open"
    try:
        if IS_WIN:
            os.startfile(target)  # noqa: S606
        elif IS_MAC:
            quiet.popen(["open", target])
        else:
            quiet.popen(["xdg-open", target], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return f"opened {target}"
    except Exception as exc:
        return f"ERROR opening {target}: {type(exc).__name__}: {exc}"


WIN_APPS = {
    "notepad": "notepad.exe", "calculator": "calc.exe", "calc": "calc.exe",
    "paint": "mspaint.exe", "explorer": "explorer.exe", "files": "explorer.exe",
    "file explorer": "explorer.exe", "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe", "settings": "ms-settings:", "cmd": "cmd.exe",
    "terminal": "wt.exe", "powershell": "powershell.exe", "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:", "store": "ms-windows-store:", "snipping tool": "ms-screenclip:",
}

LINUX_APPS = {
    "notepad": "gedit", "calculator": "gnome-calculator", "files": "xdg-open ~",
    "terminal": "x-terminal-emulator", "browser": "xdg-open https://www.google.com",
}


# ----------------------------------------------------------------- tools
def tool_open_app(app: str) -> str:
    a = (app or "").strip().lower()
    if not a:
        return "ERROR: no app name given"
    table = WIN_APPS if IS_WIN else LINUX_APPS
    target = table.get(a, app if "." in app or ":" in a else None)
    if target is None:
        # try the bare name on PATH, then report honestly
        found = shutil.which(a)
        if not found:
            return (f"ERROR: I could not find an app called '{app}'. "
                    f"Known shortcuts: {', '.join(sorted(table)[:8])}...")
        target = found
    if target.startswith("ms-"):
        return _open_path(target)
    try:
        quiet.popen([target], shell=False, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"launched {app}"
    except Exception as exc:
        return f"ERROR launching {app}: {type(exc).__name__}: {exc}"


def tool_open_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return "ERROR: no URL given"
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        webbrowser.open(u)
        return f"opened {u}"
    except Exception as exc:
        return f"ERROR: {exc}"


def tool_web_search(query: str) -> str:
    """Opens a real search in the user's browser. It does NOT read the results back —
    we say so instead of pretending the model saw the web."""
    q = (query or "").strip()
    if not q:
        return "ERROR: empty query"
    try:
        webbrowser.open("https://duckduckgo.com/?q=" + urllib_quote(q))
        return (f"opened a browser search for '{q}'. I cannot read the results page back, "
                "so tell the user to look, or ask them to paste what they need.")
    except Exception as exc:
        return f"ERROR: {exc}"


def urllib_quote(s: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(s)


def tool_system_report() -> str:
    try:
        import psutil
    except Exception:
        return "ERROR: psutil is not installed"
    try:
        cpu = psutil.cpu_percent(interval=0.3)
        vm = psutil.virtual_memory()
        du = psutil.disk_usage(str(Path.home()))
        lines = [
            f"cpu {cpu:.0f}% ({psutil.cpu_count()} threads)",
            f"ram {vm.percent:.0f}% used, {vm.available / 1024**3:.1f} GB free of {vm.total / 1024**3:.1f} GB",
            f"disk {du.percent:.0f}% used, {du.free / 1024**3:.0f} GB free",
        ]
        try:
            b = psutil.sensors_battery()
            if b:
                lines.append(f"battery {b.percent:.0f}%{' charging' if b.power_plugged else ' on battery'}")
        except Exception:
            pass
        procs = sorted(psutil.process_iter(["name", "memory_percent"]),
                       key=lambda p: p.info.get("memory_percent") or 0, reverse=True)[:3]
        top = ", ".join(f"{p.info['name']}({(p.info.get('memory_percent') or 0):.1f}%)"
                        for p in procs if p.info.get("name"))
        if top:
            lines.append("top memory: " + top)
        return "; ".join(lines)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def tool_running_apps() -> str:
    try:
        import psutil
    except Exception:
        return "ERROR: psutil is not installed"
    try:
        rows = []
        for p in psutil.process_iter(["name", "memory_info"]):
            info = p.info
            mem = info.get("memory_info")
            if info.get("name") and mem:
                rows.append((mem.rss, info["name"]))
        rows.sort(reverse=True)
        seen, out = set(), []
        for rss, name in rows:
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append(f"{name} {rss / 1024**2:.0f}MB")
            if len(out) >= 12:
                break
        return "running: " + ", ".join(out)
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def tool_close_app(app: str) -> str:
    name = (app or "").strip().lower().replace(".exe", "")
    if not name:
        return "ERROR: no app name given"
    try:
        import psutil
    except Exception:
        return "ERROR: psutil is not installed"
    killed = 0
    try:
        for p in psutil.process_iter(["name", "pid"]):
            pname = (p.info.get("name") or "").lower().replace(".exe", "")
            if pname == name:
                try:
                    p.terminate()
                    killed += 1
                except Exception:
                    pass
        return f"closed {killed} process(es) matching {name}" if killed else \
               f"no running process named {name}"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def tool_set_volume(level: int) -> str:
    try:
        lvl = max(0, min(100, int(level)))
    except Exception:
        return "ERROR: level must be 0-100"
    if IS_WIN:
        try:  # exact control if pycaw is installed
            from ctypes import POINTER, cast  # noqa: F401
            from comtypes import CLSCTX_ALL  # type: ignore
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume  # type: ignore
            devices = AudioUtilities.GetSpeakers()
            iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(iface, POINTER(IAudioEndpointVolume))
            vol.SetMasterVolumeLevelScalar(lvl / 100.0, None)
            return f"volume set to {lvl}%"
        except Exception:
            # fallback: nudge with media key presses (2% per step)
            steps = max(0, int(abs(lvl - 50) / 2))
            vk = 0xAF if lvl >= 50 else 0xAE  # VK_VOLUME_UP / DOWN
            script = ("$s=New-Object -ComObject WScript.Shell;"
                      f"1..{max(steps,1)}|%{{$s.SendKeys([char]0)}};" )  # noop guard
            # Use keybd_event through PowerShell for reliability
            script = (
                "Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
                "public class K{[DllImport(\"user32.dll\")]public static extern void keybd_event("
                "byte b,byte s,uint f,int e);}';"
                f"for($i=0;$i -lt {max(steps,1)};$i++){{[K]::keybd_event({vk},0,0,0);"
                f"[K]::keybd_event({vk},0,2,0)}}"
            )
            _ps(script)
            return (f"nudged volume toward {lvl}% using media keys "
                    "(install pycaw for exact levels)")
    if IS_MAC:
        return _run(["osascript", "-e", f"set volume output volume {lvl}"])
    return _run(["amixer", "-q", "sset", "Master", f"{lvl}%"])


def tool_mute(mute: bool = True) -> str:
    if IS_WIN:
        vk = 0xAD  # VK_VOLUME_MUTE
        _ps("Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
            "public class K{[DllImport(\"user32.dll\")]public static extern void keybd_event("
            f"byte b,byte s,uint f,int e);}}';[K]::keybd_event({vk},0,0,0);"
            f"[K]::keybd_event({vk},0,2,0)")
        return "toggled mute"
    return _run(["osascript", "-e", "set volume output muted true"]) if IS_MAC else "unsupported"


def tool_media(action: str) -> str:
    table = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}
    act = (action or "play_pause").lower().replace(" ", "_")
    if act not in table:
        return f"ERROR: action must be one of {', '.join(table)}"
    if IS_WIN:
        vk = table[act]
        _ps("Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
            "public class K{[DllImport(\"user32.dll\")]public static extern void keybd_event("
            f"byte b,byte s,uint f,int e);}}';[K]::keybd_event({vk},0,0,0);"
            f"[K]::keybd_event({vk},0,2,0)")
        return f"media {act}"
    if shutil.which("playerctl"):
        m = {"play_pause": "play-pause", "next": "next", "previous": "previous", "stop": "stop"}
        out = _run(["playerctl", m[act]])
        return f"media {act}" + (f": {out}" if out else "")
    return "ERROR: no media control available on this system"


def tool_brightness(level: int) -> str:
    try:
        lvl = max(0, min(100, int(level)))
    except Exception:
        return "ERROR: level must be 0-100"
    if IS_WIN:
        out = _ps(
            "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods)"
            f" | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout:=1;Brightness:={lvl}}}"
            " | Out-String")
        return f"brightness set to {lvl}%" if "error" not in out.lower() else \
               f"could not set brightness (external monitor?): {out[:120]}"
    if IS_MAC:
        return _run(["osascript", "-e", f"tell application \"System Events\" to set brightness of screen 1 to {lvl/100}"])
    return _run(["brightnessctl", "set", f"{lvl}%"])


def tool_screenshot(path: str = "") -> str:
    target = Path(path) if path else Path.home() / "Pictures" / f"arc_shot_{int(time.time())}.png"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        target = Path(_appdata()) / f"arc_shot_{int(time.time())}.png"
    if IS_WIN:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Left,$b.Top,0,0,$bmp.Size);"
            f"$bmp.Save('{str(target).replace(chr(92), '/')}',[System.Drawing.Imaging.ImageFormat]::Png);"
            "$g.Dispose();$bmp.Dispose()"
        )
        _ps(ps, timeout=15)
        return f"screenshot saved to {target}" if target.exists() else "ERROR: screenshot failed"
    tool = shutil.which("gnome-screenshot") or shutil.which("scrot") or shutil.which("import")
    if not tool:
        return "ERROR: no screenshot tool found"
    _run([tool, str(target)])
    return f"screenshot saved to {target}" if target.exists() else "ERROR: screenshot failed"


def tool_lock_screen() -> str:
    if IS_WIN:
        _run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return "screen locked"
    if IS_MAC:
        _run(["pmset", "displaysleepnow"])
        return "screen locked"
    return _run(["loginctl", "lock-session"]) or "lock requested"


def tool_power(action: str) -> str:
    act = (action or "").strip().lower()
    if IS_WIN:
        if act == "shutdown":
            _run(["shutdown", "/s", "/t", "20"], shell=False)
            return "shutting down in 20 seconds (run 'cancel' to abort)"
        if act == "restart":
            _run(["shutdown", "/r", "/t", "20"], shell=False)
            return "restarting in 20 seconds"
        if act == "sleep":
            _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return "going to sleep"
        if act == "cancel":
            _run(["shutdown", "/a"], shell=False)
            return "cancelled the pending shutdown"
    if act == "cancel" and not IS_WIN:
        return _run(["shutdown", "-c"]) or "cancel requested"
    if act in ("shutdown", "restart"):
        _run(["shutdown", "-h" if act == "shutdown" else "-r", "+1"])
        return f"{act} scheduled"
    if act == "sleep":
        return _run(["systemctl", "suspend"]) or "sleep requested"
    return f"ERROR: unknown action {action!r}"


def tool_timer(minutes: float = 5, label: str = "timer") -> str:
    if host is None:
        return "ERROR: timer needs the Arc Desk window"
    try:
        m = float(minutes)
    except Exception:
        return "ERROR: minutes must be a number"
    if m <= 0:
        return "ERROR: minutes must be positive"
    host.request_timer.emit(int(m * 60), str(label or "timer"))
    return f"timer set for {m:g} minute(s): {label}"


def tool_draw(subject: str = "elephant", colour: str = "", extras: str = "") -> str:
    """Draw a vector sketch, show it, and remember it for follow-up edits."""
    global current_sketch
    from .. import art
    want = (subject or "").strip().lower()
    if want and want not in art.ALIAS:
        near = [k for k in art.SUBJECTS if want in k or k in want]
        known = ", ".join(sorted(art.SUBJECTS))
        if not near:
            return (f"ERROR: I can draw {known}. You asked for '{subject}'."
                    f"{_image_backend_note()}")
        want = near[0]
    sketch = art.Sketch(art.ALIAS.get(want, "elephant"))
    if colour:
        hexv = art.PALETTE.get(colour.strip().lower())
        if hexv:
            sketch.accent = hexv
    for extra in ("sun", "cloud", "tree", "flower", "star"):
        if extra in (extras or "").lower():
            sketch.extras.append(extra)
    current_sketch = sketch
    path = art.save_sketch(sketch)
    shown = ""
    if host is not None and hasattr(host, "request_art"):
        host.request_art.emit(sketch)
        shown = " and put it on screen"
    article = "an" if sketch.subject[0] in "aeiou" else "a"
    # Say out loud what this is: a sketch, not a photograph. The person who asked
    # for a realistic elephant should not have to discover that by looking at it.
    return (f"drew {article} {sketch.subject} in {sketch.accent}{shown}; saved to {path} "
            f"— this is a vector sketch, not a photo. Say \"real photo of "
            f"{article} {sketch.subject}\" for an actual photograph."
            f"{_image_backend_note()}")


def tool_photo(query: str = "elephant", save_to: str = "") -> str:
    """Find a REAL, freely-licensed photograph of something and show it.

    This is the honest answer to "no, I meant a real elephant". `draw` produces a
    vector sketch — correct shapes, cartoon look. A photograph needs either a
    diffusion model on this machine or a picture someone actually took. This tool
    does the second, from Wikimedia Commons, and always reports the photographer
    and the licence so nothing about it is presented as generated.
    """
    from .. import photo
    q = (query or "").strip()
    if not q:
        return "ERROR: tell me what to photograph — e.g. \"real photo of an elephant\""
    got = photo.fetch(q, dest=save_to or "")
    if got.get("ok") and host is not None and hasattr(host, "request_photo"):
        try:
            caption = (f"{got['title']} — {got['artist']} ({got['licence']})")
            host.request_photo.emit(got["path"], caption)
        except Exception:
            pass                # no window on screen (CLI probe) — the file is saved
    return photo.report(got, q)


def tool_art_edit(instruction: str) -> str:
    """Change the last drawing using plain language."""
    from .. import art
    if current_sketch is None:
        return ('ERROR: nothing is drawn yet. Say "draw an elephant" first, then edit it.')
    changed, note = current_sketch.apply(instruction)
    if not changed:
        return f"could not apply that: {note}"
    path = art.save_sketch(current_sketch)
    if host is not None and hasattr(host, "request_art"):
        host.request_art.emit(current_sketch)
    return f"{note} — new version saved to {path}"


def _image_backend_note() -> str:
    from .. import art
    found = art.image_backends()
    if not found:
        return (" (vector sketch engine — for photorealistic images run ComfyUI on "
                ":8188 and I will use that instead)")
    return f" (local image model detected: {found[0][1]} on :{found[0][3]})"


def tool_magic(action: str = "on") -> str:
    if host is None:
        return "ERROR: Arc Desk window not available"
    act = (action or "on").strip().lower()
    if act not in ("on", "off", "toggle"):
        return "ERROR: action must be on, off or toggle"
    if act == "toggle":
        host.request_magic.emit("toggle")
        return "toggling magic mode"
    host.request_magic.emit(act)
    return ("magic mode on: fullscreen JARVIS, wallpaper swapped"
            if act == "on" else "returned to normal Windows, wallpaper restored")


def tool_charms(action: str = "show") -> str:
    if host is None:
        return "ERROR: Arc Desk window not available"
    act = (action or "show").strip().lower()
    if act not in ("show", "hide", "on", "off", "toggle", "edit"):
        return "ERROR: action must be show, hide, toggle or edit"
    if act == "toggle":
        host.request_charms.emit(True) if False else None
        return "ERROR: use show or hide"
    host.request_charms.emit(act in ("show", "on"))
    return f"gravity charms {act}"


def tool_arc_mode(mode: str) -> str:
    if host is None:
        return "ERROR: Arc Desk window not available"
    m = (mode or "").strip().lower()
    if m not in ("focus", "chill", "gaming", "night"):
        return "ERROR: mode must be focus, chill, gaming or night"
    host.request_mode.emit(m)
    return f"Arc Desk switched to {m} mode"


def tool_note(text: str, append: bool = True) -> str:
    if not (text or "").strip():
        return "ERROR: nothing to save"
    path = _appdata() / "notes.md"
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M")
        with path.open("a" if append else "w", encoding="utf-8") as fh:
            fh.write(f"- [{stamp}] {text.strip()}\n")
        return f"note saved ({path.name}, {len(text.strip())} chars)"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def tool_read_notes(limit: int = 10) -> str:
    path = _appdata() / "notes.md"
    try:
        lines = [ln for ln in path.read_text("utf-8").splitlines() if ln.strip()]
        if not lines:
            return "no notes yet"
        return "recent notes: " + " | ".join(lines[-max(1, int(limit)):])
    except Exception:
        return "no notes yet"


def tool_clipboard(action: str = "get", text: str = "") -> str:
    """Clipboard is touched from a worker thread, so it goes through the OS,
    not through Qt's main-thread-only clipboard object."""
    act = (action or "get").lower()
    try:
        if IS_WIN:
            if act == "get":
                return "clipboard: " + (_ps("Get-Clipboard -Raw") or "(empty)")[:500]
            _ps(f"Set-Clipboard -Value '{text.replace(chr(39), chr(39) * 2)}'")
            return "clipboard updated"
        if IS_MAC:
            if act == "get":
                return "clipboard: " + _run(["pbpaste"])[:500]
            p = quiet.run(["pbcopy"], input=text, text=True)
            return "clipboard updated" if p.returncode == 0 else "ERROR: pbcopy failed"
        if act == "get":
            return "clipboard: " + (_run(["xclip", "-selection", "clipboard", "-o"]) or "(empty)")[:500]
        quiet.run(["xclip", "-selection", "clipboard"], input=text, text=True)
        return "clipboard updated"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


def tool_weather() -> str:
    """Only works when the user turned weather on. Keeps the app offline by default."""
    w = config.load().get("weather", {})
    if not w.get("enabled"):
        return ("ERROR: weather is switched off in settings, so I have no network access. "
                "Ask the user to enable it from the ⋯ menu.")
    try:
        from urllib.parse import urlencode
        from urllib.request import urlopen
        url = "https://api.open-meteo.com/v1/forecast?" + urlencode({
            "latitude": w["lat"], "longitude": w["lon"],
            "current": "temperature_2m,relative_humidity_2m,weather_code",
            "timezone": "auto"})
        with urlopen(url, timeout=6) as r:
            cur = json.loads(r.read().decode())["current"]
        return (f"{w.get('city', 'here')}: {cur['temperature_2m']}°C, "
                f"humidity {cur['relative_humidity_2m']}%, code {cur['weather_code']}")
    except Exception as exc:
        return f"ERROR: weather unavailable ({type(exc).__name__})"


def tool_time() -> str:
    return time.strftime("it is %H:%M on %A, %d %B %Y")


# ------------------------------------------- files: read it, change it, make it
# One door per job on purpose. A small local model picks between five obvious
# tools; it cannot pick between forty narrow ones. Each door dispatches on the
# file extension, so "summary of report.docx" and "summarise clip.mp4" are the
# same intent as far as the model is concerned.
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".gif"}


def _holo(action: str = "show") -> str:
    """`holo` — project the full holographic deck, or close it."""
    action = (action or "show").strip().lower()
    if action in ("close", "hide", "off", "stop"):
        win = getattr(host, "_holo_window", None) if host is not None else None
        if win is None:
            return "the deck is not open"
        try:
            win.close()
            return "deck closed"
        except Exception as exc:
            return f"could not close the deck: {exc}"
    if host is None:
        return ("ERROR: the deck needs the Arc Desk window; run `python run.py` "
                "(or `python tools/shot_holo.py` to render it to a file)")
    try:
        return str(host.show_holo())
    except Exception as exc:
        return f"ERROR: could not project the deck ({type(exc).__name__}: {exc})"


def _read_file(path: str = "", mode: str = "summary", limit: int = 4000) -> str:
    """`read_file` — documents, spreadsheets, slides, images, audio, video."""
    from .. import reading
    target = os.path.expanduser(str(path or "").strip().strip('"'))
    if not target:
        return "ERROR: which file? Give a full path."
    doc = reading.read(target)
    if not doc.ok and not doc.text:
        return ("I could not read that file, and I will not invent what is inside it.\n"
                + doc.warning_text())
    mode = (mode or "summary").strip().lower()
    if mode in ("text", "raw", "full", "content"):
        body = doc.text[:max(500, min(int(limit or 4000), 12000))]
        if not body:
            return (f"{Path(target).name} ({doc.kind}) has no extractable text.\n"
                    + doc.warning_text())
        return f"{Path(target).name} ({doc.kind}) — text:\n{body}\n{doc.warning_text()}"
    if mode in ("review", "evaluate", "evaluation", "critique", "feedback"):
        return reading.review(doc)
    if mode in ("outline", "contents", "toc", "structure"):
        return reading.outline(doc)
    return reading.summarise(doc)


def _edit_file(path: str = "", op: str = "", **kw) -> str:
    """`edit_file` — non-destructive editing for every format we can read.

    The original is never touched; every editor writes a timestamped sibling and
    says so. That is why this tool does not ask for confirmation: it cannot lose
    anything, so gating it would only add friction.
    """
    from .. import editing
    target = os.path.expanduser(str(path or "").strip().strip('"'))
    if not target:
        return "ERROR: which file? Give a full path."
    if not Path(target).exists():
        return f"ERROR: no such file: {target}"
    op = (op or "").strip().lower()
    if not op:
        return "ERROR: what should I do to it? (resize, crop, trim, convert, find-replace, ...)"
    ext = Path(target).suffix.lower()
    keep = {k: v for k, v in kw.items() if v not in (None, "")}
    try:
        if ext in IMAGE_EXT:
            return editing.edit_image(target, op, **keep)
        if ext in AUDIO_EXT:
            return editing.edit_audio(target, op, **keep)
        if ext in VIDEO_EXT:
            return editing.edit_video(target, op, **keep)
        if ext == ".docx":
            return editing.edit_docx(target, **keep)
        if ext in (".xlsx", ".xlsm"):
            return editing.edit_xlsx(target, **keep)
        if ext == ".pptx":
            return editing.edit_pptx(target, **keep)
        if ext == ".pdf":
            return editing.edit_pdf(target, op, **keep)
        return editing.edit_text(target, op, **keep)
    except TypeError as exc:
        return f"ERROR: '{op}' needs different details for a {ext or 'text'} file ({exc})"


def _make_media(prompt: str = "", kind: str = "image", width: int = 768,
                height: int = 768, seconds: float = 4.0, style: str = "",
                init_image: str = "", strength: float = 0.6) -> str:
    """`make_media` — free image/video generation, with a local backend if running."""
    from .. import generate
    kind = (kind or "image").strip().lower()
    if kind in ("video", "clip", "movie", "animation"):
        return generate.video(prompt, float(seconds or 4.0), int(width or 960),
                              int(height or 540))
    return generate.image(prompt, int(width or 768), int(height or 768),
                          style=style, init_image=init_image,
                          strength=float(strength or 0.6))


def _market(what: str = "analyse", symbol: str = "", capital: float = 0.0,
            risk_pct: float = 1.0, stop_pct: float = 4.0, rule: str = "uptrend",
            days: int = 7, action: str = "list") -> str:
    """`market` — quotes, momentum, position maths, watchlist. Never a prediction."""
    from .. import market
    what = (what or "analyse").strip().lower()
    try:
        if what in ("quote", "price", "stock"):
            return knows.stock(symbol)
        if what in ("project", "forecast", "predict", "future"):
            return knows.project(symbol, int(days or 7))
        if what in ("brief", "today", "summary", "market"):
            return market.brief()
        if what in ("plan", "position", "size", "sizing", "risk"):
            if not capital:
                return ("ERROR: how much capital? e.g. plan RELIANCE with 100000 and "
                        "1% risk.")
            return market.plan(symbol, float(capital), float(risk_pct or 1.0),
                               float(stop_pct or 4.0))
        if what in ("watch", "watchlist"):
            return market.watchlist(action or "list", symbol)
        if what in ("screen", "filter", "scan"):
            names = [x.strip() for x in str(symbol or "").replace(";", ",").split(",")
                     if x.strip()]
            if not names:
                return "ERROR: which symbols? e.g. RELIANCE, TCS, INFY"
            return market.screen(names, rule)
        return market.analyse(symbol)
    except Exception as exc:
        return f"ERROR: market data unavailable ({type(exc).__name__}) — I will not guess a price."


def _health(what: str = "triage", query: str = "", question: str = "") -> str:
    """`health` — urgency and general knowledge. No diagnosis, no personal dosing.

    The model picks `what`, and a small one picks it wrong (measured: it asked for
    first aid with the query "paracetamol dosage"). So the text wins over the label
    when the two disagree — the words are evidence, the enum is a guess.
    """
    from .. import health
    said = f"{query} {question}".lower()
    what = (what or "triage").strip().lower()
    drug_named = any(name in said or any(alias.split(" (")[0] in said
                                         for alias in info.get("also", []))
                     for name, info in health.DRUGS.items())
    if drug_named or re.search(r"\b(medicine|tablet|dose|dosage|mg)\b", said):
        what = "medicine"
    elif re.search(r"\b(cpr|choking|burn|bleeding|first aid)\b", said) and what in (
            "triage", "first_aid"):
        what = "first_aid"
    elif (what in ("medicine", "drug", "tablet", "dose", "dosage", "medication")
          and not drug_named
          and re.search(r"\b(pain|ache|fever|cough|cold|rash|vomit|nausea|dizzy|"
                        r"breath|bleed|swelling|cramp|symptom)\b", said)):
        what = "triage"            # a symptom beats an empty medicine label too
    if what in ("medicine", "drug", "tablet", "dose", "dosage", "medication"):
        return health.drug(query, question)
    if what in ("anatomy", "body", "organ", "system"):
        return health.anatomy(query)
    if what in ("first_aid", "firstaid", "emergency", "cpr", "burn", "choking"):
        return health.first_aid(query or what)
    return health.triage(query or question)


# ------------------------------------------------------------- registry

# ---------------------------------------------------------------- day layer
def _remind(action: str = "add", text: str = "", which: str = "") -> str:
    """Reminders: add · list · cancel · clear."""
    from .. import reminders
    act = (action or "add").lower().strip()
    if act in ("list", "show", "what", "ls"):
        return reminders.list_text()
    if act in ("cancel", "remove", "delete", "forget"):
        return reminders.cancel(which or text)
    if act in ("clear", "clean", "purge"):
        return f"Cleared {reminders.clear_done()} old reminders."
    if act in ("add", "set", "remind", "create") and text:
        return reminders.add(text)
    return reminders.list_text()


def _find_files(name: str = "", query: str = "", kind: str = "",
                grep: bool = False, refresh_index: bool = False) -> str:
    """Search the file index by name (and optionally inside small text files)."""
    from .. import search
    query = query or name
    if refresh_index:
        data = search.refresh(force=True)
        return (f"File index rebuilt: {len(data.get('files', []))} files from "
                f"{len(data.get('roots', []))} folders.")
    if not (query or "").strip():
        return search.stats()
    return search.find(query, kind=kind, grep=bool(grep))


def _focus(action: str = "status", minutes: str = "", label: str = "") -> str:
    """Focus sessions: start · status · stop · stats."""
    from .. import focus
    act = (action or "status").lower().strip()
    if act in ("start", "begin", "focus"):
        try:
            mins = int(minutes) if str(minutes).strip() else focus.DEFAULT_MINUTES
        except Exception:
            mins = focus.DEFAULT_MINUTES
        return focus.start(mins, label)
    if act in ("stop", "end", "cancel"):
        return focus.finish(completed=False)
    if act in ("stats", "week", "history"):
        return focus.stats()
    return focus.status()


def _briefing(what: str = "full") -> str:
    """The daily briefing, assembled from real sources only."""
    from .. import briefing, config
    if (what or "full").lower() in ("today", "date", "short"):
        return briefing.today()
    return briefing.build(config.load())


def _packages(query: str = "", role: str = "", action: str = "search",
              key: str = "") -> str:
    """The GitHub catalogue: search it, scan this PC, or plan the gaps."""
    from . import packages
    act = (action or "search").lower().strip()
    if act in ("scan", "installed", "check", "what"):
        return packages.scan_text(role)
    if act in ("plan", "missing", "install", "gap", "gaps"):
        return packages.plan_text(role)
    if act in ("all", "summary", "count"):
        return packages.summary_text()
    if act in ("show", "detail", "info"):
        return packages.detail(key or query)
    return packages.list_text(query, role)



# ------------------------------------------------------- the studio layer
def _content(action: str = "outline", topic: str = "", kind: str = "blog",
             tone: str = "friendly", audience: str = "", words: int = 0,
             weeks: int = 2, channels: str = "") -> str:
    """Content creation: outlines, drafts, hooks, hashtags, calendars."""
    from .. import studio
    act = (action or "outline").lower().strip()
    if act in ("kinds", "formats", "list"):
        return studio.kinds_text()
    if act in ("hooks", "openers"):
        return studio.hooks(topic, 6)
    if act in ("hashtags", "tags"):
        return studio.hashtags(topic)
    if act in ("calendar", "plan"):
        return studio.calendar(topic, weeks, channels or "instagram,blog")
    if act in ("draft", "write"):
        body = studio.draft(kind, topic, tone, audience, words)
    else:
        body = studio.outline(kind, topic, tone, audience, words)
    if act in ("save", "export"):
        return body + "\n\n" + studio.save(body, topic or kind)
    return body


def _marketing(action: str = "funnel", impressions: float = 0, clicks: float = 0,
               leads: float = 0, sales: float = 0, spend: float = 0,
               revenue: float = 0, url: str = "", source: str = "instagram",
               medium: str = "social", campaign: str = "launch", text: str = "",
               keyword: str = "", baseline: float = 0.05, lift: float = 0.2,
               business: str = "", weeks: int = 4, channels: str = "",
               product: str = "") -> str:
    """Digital marketing maths and playbooks — no invented benchmarks."""
    from .. import marketing
    act = (action or "funnel").lower().strip()
    if act in ("utm", "link", "tag"):
        return marketing.utm(url, source, medium, campaign)
    if act in ("seo", "readability", "text"):
        return marketing.seo_check(text, keyword)
    if act in ("sample", "ab", "test"):
        return marketing.sample_size(baseline, lift)
    if act in ("plan", "playbook", "strategy"):
        return marketing.plan(business, weeks, channels or "instagram,google")
    if act in ("email", "sequence", "emails"):
        return marketing.email_sequence(product or business)
    return marketing.funnel(impressions, clicks, leads, sales, spend, revenue)


def _strategy(action: str = "swot", subject: str = "", fixed: float = 0,
              price: float = 0, variable: float = 0, cogs: float = 0,
              cac: float = 0, repeat: float = 1, options: str = "",
              criteria: str = "", period: str = "this quarter") -> str:
    """Business strategy frames and the arithmetic that decides them."""
    from .. import strategy
    act = (action or "swot").lower().strip()
    if act in ("forces", "porter", "five"):
        return strategy.five_forces(subject)
    if act in ("bmc", "canvas", "model"):
        return strategy.bmc(subject)
    if act in ("okr", "goals"):
        return strategy.okr(subject, period)
    if act in ("break", "breakeven", "break_even"):
        return strategy.break_even(fixed, price, variable)
    if act in ("unit", "economics", "ltv"):
        return strategy.unit_econ(price, cogs, cac, repeat)
    if act in ("decide", "matrix", "decision"):
        return strategy.decision_matrix(options, criteria)
    return strategy.swot(subject)


def _hotel(action: str = "kpi", rooms: int = 0, sold: int = 0,
           room_revenue: float = 0, other_revenue: float = 0, costs: float = 0,
           items: str = "", target_food_cost: float = 30, department: str = "",
           stage: str = "", base_rate: float = 0, weekend_uplift: float = 0.2,
           season_uplift: float = 0.0) -> str:
    """Hotel, resort and restaurant operations: KPIs, costing, SOPs."""
    from .. import hospitality
    act = (action or "kpi").lower().strip()
    if act in ("menu", "cost", "recipe"):
        return hospitality.menu_cost(items, target_food_cost)
    if act in ("sop", "checklist", "procedure"):
        return hospitality.sop(department or "housekeeping")
    if act in ("journey", "guest"):
        return hospitality.guest_journey(stage)
    if act in ("rates", "rate", "pricing"):
        return hospitality.rate_calendar(base_rate, weekend_uplift, season_uplift)
    return hospitality.kpis(rooms, sold, room_revenue, other_revenue, costs)


def _travel(action: str = "near", place: str = "", near: str = "",
            radius_km: float = 150, tag: str = "", days: int = 3,
            pace: str = "medium", tier: int = 2, people: int = 2,
            travel_extra: float = 0, budget_word: str = "", months: str = "") -> str:
    """Places, distances, map links, itineraries and honest budget bands."""
    from .. import travel
    act = (action or "near").lower().strip()
    if act in ("map", "maps", "link"):
        return travel.map_link(place or near)
    if act in ("distance", "how far", "route"):
        return travel.distance(place, near)
    if act in ("ideas", "suggest", "recommend"):
        return travel.ideas(tag, budget_word or "", months)
    if act in ("itinerary", "plan", "trip"):
        return travel.itinerary(place or near, days, pace)
    if act in ("budget", "cost", "money"):
        return travel.budget(days, tier, people, travel_extra)
    if act in ("places", "list", "all"):
        return travel.places_text()
    return travel.near(place or near, radius_km, tag)


def _craft(action: str = "palette", base: str = "#48f2ff", scheme: str = "analogous",
           title: str = "", subtitle: str = "", name: str = "", dots: int = 5,
           seed: int = 7, width: int = 900, kind: str = "kolam",
           save_it: bool = True) -> str:
    """Design and craft: palettes, posters, kolam patterns, monograms, as SVG."""
    from .. import craft
    act = (action or "palette").lower().strip()
    if act in ("poster", "card"):
        svg = craft.poster(title or "JARVIS", subtitle, base)
        return craft.save(svg, title or "poster") if save_it else svg
    if act in ("kolam", "rangoli", "pattern"):
        svg = craft.kolam(dots, base, seed)
        return craft.save(svg, "kolam") if save_it else svg
    if act in ("border", "strip"):
        svg = craft.border(kind, width, base)
        return craft.save(svg, "border") if save_it else svg
    if act in ("monogram", "logo", "mark"):
        svg = craft.monogram(name or title or "JARVIS", base)
        return craft.save(svg, "monogram") if save_it else svg
    return craft.palette(base, scheme)


def _mine(action: str = "profile", path: str = "", column: str = "",
          other: str = "", key: str = "", value: str = "", agg: str = "sum",
          periods: int = 0) -> str:
    """Data mining over your own CSV/JSON: profiles, correlation, outliers, trends."""
    from .. import mining
    act = (action or "profile").lower().strip()
    if act in ("report", "all", "everything"):
        return mining.report(path)
    if act in ("correlate", "correlation"):
        return mining.correlate(path, column, other)
    if act in ("outliers", "anomaly"):
        return mining.outliers(path, column)
    if act in ("groupby", "group", "by"):
        return mining.groupby(path, key or column, value, agg)
    if act in ("trend", "slope"):
        return mining.trend(path, column or value, periods)
    return mining.profile(path)


def _mentor(action: str = "questions", subject: str = "") -> str:
    """Mentor and lateral-thinking frames — questions, not confident answers."""
    from .. import mentor
    act = (action or "questions").lower().strip()
    if act in ("rules", "principles"):
        return mentor.principles_list()
    return mentor.mentor(act, subject)


def _foresight(action: str = "scenario", question: str = "", values: str = "",
               periods: int = 3, horizon: str = "6 months") -> str:
    """Honest forecasting: arithmetic extrapolation or scenarios, never prophecy."""
    from .. import foresight
    act = (action or "scenario").lower().strip()
    if act in ("forecast", "numbers", "predict-data"):
        return foresight.forecast(values, periods)
    if act in ("unknown", "dontknow", "don't know"):
        return foresight.unknown(question)
    if act in ("verify", "check", "factcheck"):
        return foresight.verify(question)
    if act in ("rules", "policy"):
        return foresight.rules()
    if act in ("now", "today", "state"):
        return foresight.now_help()
    return foresight.scenario(question, horizon)


def _secure(action: str = "refused", text: str = "") -> str:
    """Defensive security only: password strength, phishing, own machine, recovery."""
    from .. import security
    act = (action or "refused").lower().strip()
    if act in ("password", "strength", "entropy"):
        return security.password_strength(text)
    if act in ("phishing", "scam", "message"):
        return security.phishing_check(text)
    if act in ("machine", "audit", "posture"):
        return security.own_machine()
    if act in ("recovery", "backup", "2fa"):
        return security.recovery_plan()
    return security.refused()



def _facts(action: str = "ask", question: str = "", domain: str = "",
           topic: str = "", path: str = "") -> str:
    """The library: sourced facts, your own indexed files, or a real lookup."""
    from .. import world
    act = (action or "ask").lower().strip()
    if act in ("coverage", "shelf", "what", "all"):
        return world.coverage()
    if act in ("domain", "shelf", "browse"):
        return world.domain(domain or question)
    if act in ("random", "fact", "surprise"):
        return world.random_fact()
    if act in ("unknown", "dontknow"):
        return world.unknown(question or topic)
    if act in ("ingest", "index", "import", "library"):
        return world.ingest(path or topic)
    if act in ("fetch", "lookup", "wiki", "search-web"):
        return world.fetch(topic or question)
    return world.ask(question or topic)



def _video_studio(action: str = "template", clips: str = "", template: str = "reel_hook",
                  transition: str = "", look: str = "", music: str = "", title: str = "",
                  subtitle: str = "", seconds: float = 0.0, strength: float = 1.0,
                  start: float = 0.0, width: int = 540, fps: int = 30,
                  path: str = "") -> str:
    """`video_studio` — real edits: templates, transitions, looks, captions, music."""
    from .. import media
    act = (action or "template").strip().lower()
    if act in ("catalog", "list", "templates", "what"):
        return media.catalog("video")
    if act in ("look", "grade", "effect", "filter"):
        return media.video_look(path or clips, look or "cinematic", float(strength or 1.0))
    if act == "gif":
        return media.video_gif(path or clips, float(start or 0),
                               float(seconds or 4), int(width or 540))
    return media.video_timeline(
        clips or path, template=template or "reel_hook", transition=transition or "",
        look=look or "", music=music or "", title=title or "", subtitle=subtitle or "",
        seconds=float(seconds or 0), fps=int(fps or 30))


def _audio_studio(action: str = "catalog", path: str = "", clips: str = "",
                  gains: str = "", target_lufs: float = -14.0, bass: float = 0.0,
                  mid: float = 0.0, treble: float = 0.0, start: float = 0.0,
                  end: float = 0.0, factor: float = 1.0, seconds: float = 1.0,
                  width: int = 1200, height: int = 300, colour: str = "#48f2ff",
                  as_format: str = "", duck: bool = False) -> str:
    """`audio_studio` — denoise, EQ, loudness, ducking, mixing, waveform, chapters."""
    from .. import media
    act = (action or "catalog").strip().lower()
    if act in ("catalog", "list", "what"):
        return media.catalog("audio")
    if act in ("mix", "mixdown"):
        return media.audio_mix(clips or path, gains or "", "mix",
                               float(target_lufs or -14), bool(duck))
    if act in ("waveform", "wave"):
        return media.audio_waveform(path, int(width or 1200), int(height or 300),
                                   colour or "#48f2ff")
    return media.audio_op(path, act, float(target_lufs or -14), float(bass or 0),
                          float(mid or 0), float(treble or 0), float(start or 0),
                          float(end or 0), float(factor or 1.0),
                          float(seconds or 1.0), 3.0, as_format or "")


def _image_studio(action: str = "catalog", path: str = "", images: str = "",
                  look: str = "", template: str = "", title: str = "", subtitle: str = "",
                  footer: str = "", accent: str = "#48f2ff", background: str = "#0b1213",
                  strength: float = 1.0, cols: int = 2, rows: int = 2, cell: int = 640,
                  out: str = "") -> str:
    """`image_studio` — looks, finished social cards, collages, whole-folder grades."""
    from .. import media
    act = (action or "catalog").strip().lower()
    if act in ("catalog", "list", "what", "templates"):
        return media.catalog("image")
    if act in ("look", "grade", "filter", "effect"):
        return media.image_look(path, look or "cinematic", float(strength or 1.0), out or "")
    if act in ("card", "post", "story", "thumb", "thumbnail"):
        tpl = template or {"post": "instagram_post", "story": "instagram_story",
                           "thumb": "youtube_thumb", "thumbnail": "youtube_thumb"}.get(
                               act, "instagram_post")
        return media.image_card(path, tpl, title or "", subtitle or "", look or "",
                                footer or "", background or "#0b1213", accent or "#48f2ff")
    if act in ("collage", "grid"):
        return media.image_collage(images or path, int(cols or 2), int(rows or 2),
                                   int(cell or 640), 12, background or "#0b1213",
                                   title or "", look or "")
    if act in ("batch", "folder"):
        return media.image_batch(path, look or "cinematic", float(strength or 0.85))
    return f"ERROR: unknown image action '{action}'. Use look | card | collage | batch | catalog."



def _play(action: str = "play", query: str = "", kind: str = "", path: str = "",
          folder: str = "", queue: bool = True) -> str:
    """`play` — songs and videos, started immediately and measured in milliseconds."""
    from .. import player
    act = (action or "play").strip().lower()
    if act in ("stop", "kill", "shut"):
        return player.stop()
    if act in ("status", "now", "what"):
        return player.status()
    if act in ("folder", "album", "all"):
        return player.play_folder(folder, query, kind)
    if act in ("pause", "resume", "next", "next song", "previous", "prev"):
        key = {"pause": "play_pause", "resume": "play_pause", "next": "next",
               "next song": "next", "previous": "previous", "prev": "previous"}[act]
        return player.volume_updown(key)
    if act in ("players", "catalog", "help"):
        return player.describe()
    return player.play(query, kind, path, bool(queue))


def _library(action: str = "scan", roots: str = "", query: str = "", kind: str = "",
             limit: int = 8) -> str:
    """`library` — index and search audio/video, including external disks."""
    from .. import library
    act = (action or "scan").strip().lower()
    if act in ("drives", "disks", "mounts"):
        found = library.drives()
        if not found:
            return ("I could not find any drive to scan. On Windows plug the disk in and "
                    "say 'scan my external disk' — I will look again.")
        lines = [f"{len(found)} drive(s) I can see:"]
        for drive in found:
            size = f"{drive['total_gb']} GB" if drive.get("total_gb") else "size unknown"
            tag = "removable" if drive.get("removable") else "fixed"
            lines.append(f"  {drive['path']}  ({tag}, {size})")
        return "\n".join(lines)
    if act in ("search", "find", "play", "list"):
        return library.results_text(query, kind, int(limit or 8))
    if act in ("stats", "status", "what"):
        return library.stats()
    if act in ("forget", "clear", "reset"):
        return library.forget()
    data = library.scan(roots, include_drives=True)
    if data.get("error"):
        return f"{data['error']} I left the existing index untouched."
    tracks = data.get("tracks") or []
    audio = sum(1 for t in tracks if t.get("kind") == "audio")
    video = len(tracks) - audio
    roots_text = ", ".join(data.get("roots") or [])
    if not tracks:
        return (f"Scanned {data.get('folders', 0)} folders from {roots_text} and found no "
                f"audio or video files. Nothing was changed on disk. If the disk was "
                f"just plugged in, give it a second and say 'scan my external disk' again.")
    return (f"Scanned {data.get('folders', 0)} folders in {data.get('seconds', 0):.1f} s — "
            f"indexed {len(tracks)} media files: {audio} songs, {video} videos\n"
            f"  roots: {roots_text}\n"
            f"  skipped {data.get('skipped', 0)} unreadable/tiny files · read-only · "
            f"say 'play <name>' and I will start it.")
def _backup(action: str = "copy", source: str = "", target: str = "", include: str = "",
            verify: bool = True, dry_run: bool = False) -> str:
    """`backup` — copy to another disk, verify every byte, never overwrite or delete."""
    from .. import backup
    act = (action or "copy").strip().lower()
    if act in ("drives", "disks", "where"):
        found = backup.drives()
        if not found:
            return "I cannot see any disk to copy to. Plug the external drive in, then ask again."
        return "Disks I can see:\n" + "\n".join(
            f"  {d['path']}  ({d['free_gb']} GB free of {d['total_gb']} GB)" for d in found)
    if act in ("verify", "check", "test"):
        path = target or source
        if not path:
            return ("Tell me which backup to verify — for example "
                    "'verify backup D:\\ArcBackup-20261022-1200'.")
        return backup.verify_report(backup.verify(path))
    if act in ("list", "backups", "history"):
        found = backup.backups(target or "")
        if not found:
            return ("No JARVIS backups found on that disk. Say 'back up my documents' to "
                    "make the first one.")
        return "Backups on that disk, newest first:\n" + "\n".join(
            f"  {b['path']}  {b.get('created', '?')} · {b.get('count', 0)} files"
            + (" · verified" if b.get("verified") else "") for b in found)
    if act in ("plan", "dry", "preview"):
        return backup.report(backup.copy(source or "~", target, include, verify, dry_run=True))
    return backup.report(backup.copy(source or "~", target, include, bool(verify),
                                     bool(dry_run) if dry_run else False))


def _autostart(action: str = "status") -> str:
    """`autostart` — start with the user's session: one per-user entry, reversible."""
    from .. import autostart
    act = (action or "status").strip().lower()
    if act in ("on", "enable", "start", "add"):
        result = autostart.enable()
        if not result.get("ok"):
            return f"ERROR: {result.get('error')}"
        state = result["state"]
        return f"Enabled ({result['mode']}).\n" + autostart.report(state)
    if act in ("off", "disable", "remove", "stop"):
        result = autostart.disable()
        if not result.get("ok"):
            return f"ERROR: {result.get('error')}"
        return (("Removed the startup entry.\n" if not result.get("note")
                 else "It was not enabled, so nothing was removed.\n")
                + autostart.report(result["state"]))
    return autostart.report()



def _vault(action: str = "list", project: str = "", text: str = "", path: str = "",
           dest: str = "") -> str:
    """`vault` — where your work lives: projects, progress, and export to any folder."""
    from .. import vault
    act = (action or "list").strip().lower()

    if act in ("where", "root", "location", "stats"):
        s = vault.stats()
        return (f"Vault folder: {s['root']}\n"
                f"{s['projects']} project(s), {s['megabytes']} MB on disk."
                + (f"\nOpen now: {s['current']}" if s["current"] else ""))

    if act in ("create", "start", "new", "open"):
        if not project:
            return ("Which project? Say 'start a project called Belagavi cafe site'.")
        made = vault.create(project, note=text)
        if not made.get("ok"):
            return f"ERROR: {made.get('error')}"
        return (f"{'Reopened' if made['reopened'] else 'Created'} project "
                f"\"{made['project']['name']}\" at {made['path']}.\n"
                f"Everything I write is saved there as we work — notes, every answer, "
                f"and any file you add. Say 'export this project to my desktop' to take "
                f"a copy outside.")

    if act in ("save", "note", "remember", "log"):
        res = vault.note(text or project, project=project if text else "")
        if not res.get("ok"):
            return f"ERROR: {res.get('error')}"
        return f"Saved to {res['project']} → {res['path']}"

    if act in ("checkpoint", "progress", "auto"):
        res = vault.checkpoint(text, project=project)
        if not res.get("ok"):
            return f"Not saved: {res.get('error') or res.get('skipped')}"
        return f"Progress saved in {res['project']} at {res['at']}."

    if act in ("add", "copy", "attach", "import"):
        if not path:
            return "Which file? Say 'add C:\\Users\\me\\report.docx to this project'."
        res = vault.add(path, project=project)
        if not res.get("ok"):
            return f"ERROR: {res.get('error')}"
        return (f"Copied {res['files']} file(s) into {res['project']} → {res['into']}.\n"
                f"Your original is untouched: {res['original_untouched']}")

    if act in ("export", "download", "take", "out", "backup"):
        res = vault.export(project=project, dest=dest)
        if not res.get("ok"):
            return f"ERROR: {res.get('error')}"
        proof = (" every file compared: sizes match" if res.get("verified")
                 else " (copy not verified — check it yourself)")
        return (f"Exported {res['project']} to {res['to']} "
                f"({res['files']} files, {res['bytes'] / 1024:.0f} KB);{proof}.\n"
                f"The vault copy is still there.")

    if act in ("resume", "continue", "status", "show", "open_project"):
        res = vault.resume(project=project)
        if not res.get("ok"):
            return f"{res['error']}. Known projects: {res.get('known')}"
        lines = [f"Project \"{res['project']}\" — {res['checkpoints']} checkpoints, "
                 f"{res['bytes'] / 1024:.0f} KB, at {res['path']}"]
        for row in res["recent"][-3:]:
            lines.append(f"  {row.get('at')}  {row.get('note', '')[:90]}")
        if res["notes_tail"].strip():
            lines.append("Last notes: " + res["notes_tail"].strip().splitlines()[-1][:120])
        if res["files"]:
            lines.append("Files: " + ", ".join(res["files"][:8]))
        return "\n".join(lines)

    return vault.report()


def _pc_health(action: str = "scan", text: str = "") -> str:
    """`pc_health` — why is it slow: measured, explained, fixable. Read-only."""
    from .. import pchealth
    act = (action or "scan").strip().lower()
    if act in ("quick", "now", "status"):
        return pchealth.quick()
    if act in ("startup", "autostart", "boot"):
        return pchealth.startup_text()
    if act in ("checks", "rules", "catalog", "help"):
        return pchealth.catalog()
    return pchealth.explain(lang_text=text or action)


def _search_inside(action: str = "search", query: str = "", roots: str = "",
                   ocr: bool = False, limit: int = 8) -> str:
    """`search_inside` — find the words inside documents, not just their names."""
    from .. import deepsearch
    act = (action or "search").strip().lower()
    if act in ("index", "scan", "build", "rebuild"):
        data = deepsearch.index(roots, ocr=bool(ocr))
        if data.get("error"):
            return f"{data['error']} I left the existing index untouched."
        stat = data["stats"]
        if not data.get("files"):
            return ("I read the folders but found no readable documents. Only text, Word, "
                    "Excel, PowerPoint and PDF files are indexed — nothing was changed on disk.")
        out = (f"Indexed {stat['found']} searchable documents in {stat['seconds']:.1f} s "
               f"({stat['reread']} read, {stat['unchanged']} unchanged)")
        out += "\n  roots: " + ", ".join(data.get("roots") or [])
        if stat.get("no_text"):
            names = ", ".join(stat.get("no_text_names") or [])
            out += (f"\n  {stat['no_text']} file(s) had no text layer (scans, images): "
                    f"{names}" + (", …" if stat["no_text"] > len(stat.get("no_text_names") or []) else ""))
        if stat.get("capped"):
            out += "\n  capped at the file limit — index a narrower folder for the rest"
        out += "\n  read-only; no document was modified, nothing was uploaded"
        return out
    if act in ("stats", "status", "what"):
        return deepsearch.stats()
    if act in ("forget", "clear", "reset"):
        return deepsearch.forget()
    if act in ("ocr", "scan_ocr", "deep"):
        data = deepsearch.index(roots, ocr=True)
        if data.get("error"):
            return data["error"]
        return (f"Indexed {data['stats']['found']} documents with OCR on — images and "
                f"scanned pages are included now. Slower by design: OCR costs about a "
                f"second per image.")
    return deepsearch.results_text(query, int(limit or 8))



def _explain(text: str = "", where: str = "text") -> str:
    """`explain` — name the error, explain the cause, give ordered steps."""
    from .. import screenhelp
    where = (where or "text").strip().lower()
    if where in ("catalog", "list", "known"):
        return screenhelp.catalog()
    if where in ("clipboard", "clip"):
        clip = screenhelp.read_clipboard()
        if not clip.strip():
            return "Your clipboard is empty, so there is nothing to read."
        return screenhelp.explain(clip, lang_text=text)
    if where in ("screen", "display") or (not (text or "").strip()):
        return screenhelp.from_clipboard_or_screen(lang_text=text)
    if not screenhelp.is_error(text):
        # "explain this" is a command, not an error message: go and find one.
        return ("That message does not contain an error I can read, so I looked at "
                "your clipboard and then your screen.\n\n"
                + screenhelp.from_clipboard_or_screen(lang_text=text))
    return screenhelp.explain(text, lang_text=text)



def _plan(action: str = "do", request: str = "", confirm: bool = True) -> str:
    """`plan` — think, show the steps, then actually do them."""
    from .. import planner
    act = (action or "do").strip().lower()
    if act in ("think", "steps", "explain"):
        plan = planner.think(request)
        described = planner.describe_plan(plan)
        return described or planner.recipes()
    if act in ("recipes", "help", "what"):
        return planner.recipes()
    return planner.run(request, confirm=bool(confirm))


def _coach(mode: str = "", text: str = "", options: str = "", action: str = "") -> str:
    """`coach` — listen, mentor, analyse, decide, plan. Local, private, no diagnosis."""
    from .. import coach
    opts = [o.strip() for o in re.split(r"[|,;]", options or "") if o.strip()] or None
    return coach.respond(text, mode, opts, action)


TOOLS: dict[str, Tool] = {
    t.name: t for t in [
        Tool("open_app", "Launch an application on this PC by name (notepad, calculator, files, ...).",
             {"app": {"type": "string", "description": "app name, e.g. notepad"}}, ("app",),
             tool_open_app),
        Tool("open_url", "Open a website in the user's default browser.",
             {"url": {"type": "string"}}, ("url",), tool_open_url),
        Tool("web_search", "Open a browser search. Cannot read results back.",
             {"query": {"type": "string"}}, ("query",), tool_web_search),
        Tool("system_report", "Live CPU, RAM, disk, battery and top memory processes.",
             {}, (), tool_system_report),
        Tool("running_apps", "List the heaviest running processes by memory.",
             {}, (), tool_running_apps),
        Tool("close_app", "Terminate a running application by process name.",
             {"app": {"type": "string"}}, ("app",), tool_close_app, confirm=True),
        Tool("set_volume", "Set system output volume, 0-100.",
             {"level": {"type": "integer"}}, ("level",), tool_set_volume),
        Tool("mute", "Toggle system mute.", {}, (), tool_mute),
        Tool("media", "Control media playback: play_pause, next, previous, stop.",
             {"action": {"type": "string"}}, ("action",), tool_media),
        Tool("brightness", "Set screen brightness, 0-100.",
             {"level": {"type": "integer"}}, ("level",), tool_brightness),
        Tool("screenshot", "Capture the screen to a PNG file.",
             {"path": {"type": "string", "description": "optional full path"}}, (), tool_screenshot),
        Tool("lock_screen", "Lock the workstation immediately.", {}, (), tool_lock_screen),
        Tool("power", "Shutdown, restart, sleep or cancel a pending shutdown.",
             {"action": {"type": "string", "enum": ["shutdown", "restart", "sleep", "cancel"]}},
             ("action",), tool_power, confirm=True),
        Tool("timer", "Start a countdown timer that notifies when it finishes.",
             {"minutes": {"type": "number"}, "label": {"type": "string"}}, ("minutes",), tool_timer),
        Tool("magic", "Enter or leave magic mode (fullscreen JARVIS + wallpaper swap).",
             {"action": {"type": "string", "enum": ["on", "off", "toggle"]}},
             ("action",), tool_magic),
        Tool("charms", "Show or hide the floating gravity charms on the desktop.",
             {"action": {"type": "string", "enum": ["show", "hide", "edit"]}},
             ("action",), tool_charms),
        Tool("arc_mode", "Switch Arc Desk's power mode: focus, chill, gaming, night.",
             {"mode": {"type": "string", "enum": ["focus", "chill", "gaming", "night"]}},
             ("mode",), tool_arc_mode),
        Tool("note", "Save a note to the Arc Desk notes file.",
             {"text": {"type": "string"}}, ("text",), tool_note),
        Tool("read_notes", "Read back recent notes.",
             {"limit": {"type": "integer"}}, (), tool_read_notes),
        Tool("clipboard", "Read or set the clipboard.", 
             {"action": {"type": "string", "enum": ["get", "set"]}, "text": {"type": "string"}},
             ("action",), tool_clipboard),
        Tool("weather", "Current weather for the configured city (needs weather enabled).",
             {}, (), tool_weather),
        Tool("time", "Current local time and date.", {}, (), tool_time),
        Tool("draw", "Draw a picture: elephant, cat, dog, house, tree, flower, car, "
                     "robot, fish or sun. Vector sketch, offline, instant.",
             {"subject": {"type": "string"},
              "colour": {"type": "string", "description": "optional, e.g. purple"},
              "extras": {"type": "string", "description": "optional scenery: sun, cloud, tree, star"}},
             ("subject",), tool_draw),
        Tool("photo", "Find a real photograph (not a drawing) of anything, from free "
                      "licences — no key, no account, no GPU. Reports the photographer "
                      "and the licence. Use this when the person says 'real', 'actual' "
                      "or 'photo of'.",
             {"query": {"type": "string", "description": "what the photo should show"},
              "save_to": {"type": "string", "description": "optional folder to save into"}},
             ("query",), tool_photo),
        Tool("art_edit", "Change the picture already drawn: colour, size, position, "
                         "rotation, add or remove scenery, undo.",
             {"instruction": {"type": "string"}}, ("instruction",), tool_art_edit),
        Tool("mcp_servers", "List connected MCP tool servers and their status.", {},
             (), lambda: (mcp_manager.describe() if mcp_manager
                          else "MCP is not enabled in this session")),

        # ---- doing work on the desktop -------------------------------
        Tool("windows", "See and control open windows: list, focus, minimize, maximize, "
                        "restore, minimize_all, close_window. Pass a window title fragment.",
             {"action": {"type": "string",
                         "enum": ["list", "focus", "minimize", "maximize", "restore",
                                  "minimize_all", "close_window"]},
              "title": {"type": "string", "description": "part of the window title"}},
             (), actions.windows),
        Tool("type_text", "Type text into whichever window currently has focus.",
             {"text": {"type": "string"}}, ("text",), actions.type_text),
        Tool("press", "Press keys in the focused window: enter, ctrl+s, alt+tab, ctrl+shift+t.",
             {"keys": {"type": "string"}}, ("keys",), actions.press),
        Tool("file_op", "Create or change files: mkdir, write, append, copy, rename, move. "
                        "Stays inside the home folder.",
             {"action": {"type": "string",
                         "enum": ["mkdir", "write", "append", "copy", "rename", "move"]},
              "path": {"type": "string"},
              "target": {"type": "string", "description": "destination for copy/rename/move"},
              "text": {"type": "string"}},
             ("action", "path"), actions.file_op),
        Tool("file_delete", "Delete a file or empty folder inside the home folder.",
             {"path": {"type": "string"}}, ("path",), actions.file_delete, confirm=True),
        Tool("run_command", "Run a shell command and return its output. Gated and blocklisted.",
             {"command": {"type": "string"}, "timeout": {"type": "number"}},
             ("command",), actions.run_command, confirm=True),
        Tool("action_log", "What JARVIS has actually done on this machine, most recent last.",
             {"limit": {"type": "integer"}}, (),
             lambda limit=20: actions.recent_actions(int(limit))),

        # ---- eyes: seeing the screen ---------------------------------
        Tool("screen_text", "Read the text currently visible on the screen (OCR). Use this "
                            "to answer 'what does this error say' or to find a button.",
             {"lang": {"type": "string", "description": "optional OCR language, e.g. eng"}},
             (), _vision().screen_text),
        Tool("click_text", "Find words on screen and click them. Works in any app, "
                           "including ones with no accessibility tree.",
             {"text": {"type": "string", "description": "visible label, e.g. 'Send'"},
              "double": {"type": "boolean"}}, ("text",),
             lambda text, double=False: _vision().click_text(text, double=bool(double))),
        Tool("click_at", "Click an exact pixel position on screen.",
             {"x": {"type": "integer"}, "y": {"type": "integer"},
              "button": {"type": "string", "enum": ["left", "right", "middle"]}},
             ("x", "y"), lambda x, y, button="left": _vision().click_at(int(x), int(y), button)),

        # ---- inside the app: accessibility tree ----------------------
        Tool("ui_controls", "List the clickable/typeable controls of the focused window "
                            "with their exact names.",
             {"limit": {"type": "integer"}}, (),
             lambda limit=40: _uia().controls(int(limit))),
        Tool("ui_act", "Click, focus or fill a control of the focused window by its name. "
                       "Falls back to reading the screen when there is no accessibility tree.",
             {"name": {"type": "string"},
              "action": {"type": "string", "enum": ["click", "set", "focus"]},
              "value": {"type": "string", "description": "text for action=set"}},
             ("name",), lambda name, action="click", value="": _uia().act(name, action, value)),

        # ---- people ---------------------------------------------------
        Tool("email_send", "Send an email through the user's own SMTP account.",
             {"to": {"type": "string"}, "subject": {"type": "string"},
              "body": {"type": "string"}, "attachment": {"type": "string"}},
             ("to",), comms.send_email, confirm=True),
        Tool("email_draft", "Open the user's mail app with a draft already written "
                            "(no password needed).",
             {"to": {"type": "string"}, "subject": {"type": "string"},
              "body": {"type": "string"}}, (),
             lambda to="", subject="", body="": comms.draft_email(to, subject, body)),
        Tool("calendar", "Add an event or list upcoming ones. Writes real .ics files.",
             {"action": {"type": "string", "enum": ["add", "list"]},
              "title": {"type": "string"}, "when": {"type": "string"},
              "minutes": {"type": "integer"}, "days": {"type": "integer"}},
             ("action",),
             lambda action="list", title="", when="", minutes=30, days=7:
                 comms.add_event(title, when, int(minutes), "")
                 if str(action).lower() == "add"
                 else comms.list_events(int(days))),
        Tool("look", "Look at the user's screen and answer from it. Runs OCR and returns "
                     "the visible text plus the screenshot path. Use this for 'what does "
                     "this error say', 'what is on my screen', 'summarise this page'.",
             {"question": {"type": "string"}, "lang": {"type": "string"}}, (),
             lambda question="", lang="": _look(question, lang)),
        Tool("profile", "What JARVIS remembers about you: name, editor, city, reply language, "
                        "volume taste. action=get|set|forget|clear.",
             {"action": {"type": "string", "enum": ["get", "set", "forget", "clear"]},
              "key": {"type": "string"}, "value": {"type": "string"}}, (),
             lambda action="get", key="", value="": (
                 profile.describe() if action == "get" else
                 profile.set(key, value) if action == "set" else
                 profile.forget(key) if action == "forget" else profile.reset())),
        Tool("read_file", "Read ANY file — pdf, docx, xlsx, pptx, csv, json, txt, "
             "image (OCR), audio/video (metadata) — and summarise, review, outline "
             "or return its text.",
             {"path": {"type": "string", "description": "full path to the file"},
              "mode": {"type": "string", "enum": ["summary", "review", "outline", "text"],
                       "description": "review = what is missing, what to improve, what to add"},
              "limit": {"type": "integer"}}, ("path",), _read_file),
        Tool("edit_file", "Edit a file without touching the original: resize, crop, "
             "rotate, trim, convert, find-and-replace, add text, make a gif, rotate "
             "pdf pages, set a spreadsheet cell. Writes a new copy.",
             {"path": {"type": "string"}, "op": {"type": "string",
                                                "description": "resize, crop, rotate, trim, "
                                                "convert, greyscale, blur, sharpness, "
                                                "brightness, text, thumbnail, gif, speed, "
                                                "volume, fade, normalise, frames, "
                                                "extract_audio, mute, compress, subtitles, "
                                                "watermark, replace, append, prepend, "
                                                "set_cell, append_row, extract, merge, split"},
              "width": {"type": "integer"}, "height": {"type": "integer"},
              "angle": {"type": "number"}, "start": {"type": "number"},
              "duration": {"type": "number"}, "find": {"type": "string"},
              "replace": {"type": "string"}, "text": {"type": "string"},
              "value": {"type": "string"}, "cell": {"type": "string"},
              "sheet": {"type": "string"}, "fmt": {"type": "string"},
              "fps": {"type": "number"}, "pages": {"type": "string"},
              "position": {"type": "string"}, "factor": {"type": "number"}},
             ("path", "op"), _edit_file),
        Tool("make_media", "Generate an image or a video from words — free and local. "
             "Uses a local diffusion backend if one is running, otherwise makes an "
             "offline poster or a ken-burns motion clip.",
             {"prompt": {"type": "string"},
              "kind": {"type": "string", "enum": ["image", "video"]},
              "width": {"type": "integer"}, "height": {"type": "integer"},
              "seconds": {"type": "number"},
              "init_image": {"type": "string", "description": "restyle this image"},
              "style": {"type": "string"}}, ("prompt",), _make_media),
        Tool("video_studio", "Edit video properly: join clips with 26 real transitions, "
             "apply 17 colour looks, fit to 9:16/1:1/16:9/21:9, burn a title, lay music "
             "under the voice with ducking, 10 ready templates (reel, story, ad, hotel "
             "tour, teaser). Local ffmpeg, originals untouched.",
             {"action": {"type": "string", "enum": ["template", "look", "gif", "catalog"]},
              "clips": {"type": "string", "description": "paths separated by |"},
              "template": {"type": "string"}, "transition": {"type": "string"},
              "look": {"type": "string"}, "music": {"type": "string"},
              "title": {"type": "string"}, "subtitle": {"type": "string"},
              "seconds": {"type": "number"}, "strength": {"type": "number"},
              "start": {"type": "number"}, "width": {"type": "integer"},
              "fps": {"type": "integer"}, "path": {"type": "string"}},
             (), _video_studio, max_len=1200),
        Tool("audio_studio", "Edit audio properly: denoise, de-ess, gate, compress, 3-band "
             "EQ, reverb, broadcast loudness (-14/-16 LUFS), tempo without pitch shift, "
             "cut silence, list chapters, render a waveform, mix tracks, duck music under "
             "a voice. Local ffmpeg, originals untouched.",
             {"action": {"type": "string", "enum": ["denoise", "deess", "gate", "compress",
                                                   "eq3", "reverb", "loudnorm", "fade",
                                                   "trim", "speed", "mono", "stereo_width",
                                                   "silence_trim", "chapters", "waveform",
                                                   "mix", "catalog"]},
              "path": {"type": "string"},
              "clips": {"type": "string", "description": "for mix: paths separated by |"},
              "gains": {"type": "string", "description": "dB per track, e.g. -3,-16"},
              "target_lufs": {"type": "number"}, "bass": {"type": "number"},
              "mid": {"type": "number"}, "treble": {"type": "number"},
              "start": {"type": "number"}, "end": {"type": "number"},
              "factor": {"type": "number"}, "seconds": {"type": "number"},
              "width": {"type": "integer"}, "height": {"type": "integer"},
              "colour": {"type": "string"}, "as_format": {"type": "string"},
              "duck": {"type": "boolean"}}, (), _audio_studio, max_len=1400),
        Tool("image_studio", "Edit images properly: 16 looks (cinematic, noir, cyberpunk, "
             "vintage, duotone, tilt-shift), finished social cards at the right pixel size "
             "(post, story, YouTube thumb, quote card, product card, passport), collages, "
             "and grade a whole folder. Local Pillow, originals untouched.",
             {"action": {"type": "string", "enum": ["look", "card", "collage", "batch",
                                                   "catalog"]},
              "path": {"type": "string"}, "images": {"type": "string",
                                                    "description": "paths separated by |"},
              "look": {"type": "string"}, "template": {"type": "string"},
              "title": {"type": "string"}, "subtitle": {"type": "string"},
              "footer": {"type": "string"}, "accent": {"type": "string"},
              "background": {"type": "string"}, "strength": {"type": "number"},
              "cols": {"type": "integer"}, "rows": {"type": "integer"},
              "cell": {"type": "integer"}, "out": {"type": "string"}},
             (), _image_studio, max_len=1200),
        Tool("market", "Share-market facts and arithmetic: quote, momentum analysis, "
             "position size for a risk budget, watchlist, screener, market brief. "
             "Quote and analyse are measurements; nothing here is a prediction or advice.",
             {"what": {"type": "string", "enum": ["quote", "analyse", "project", "plan",
                                                  "watch", "screen", "brief"]},
              "symbol": {"type": "string", "description": "e.g. RELIANCE, NIFTY, BTC-USD"},
              "capital": {"type": "number"}, "risk_pct": {"type": "number"},
              "stop_pct": {"type": "number"}, "rule": {"type": "string"},
              "action": {"type": "string", "enum": ["list", "add", "remove"]},
              "days": {"type": "integer"}}, (), _market, max_len=2200),
        Tool("health", "Health information with safety rails: urgency triage for "
             "symptoms, published label ranges for common medicines, how a body "
             "system works, first aid. Never a diagnosis, never a personal dose.",
             {"what": {"type": "string", "enum": ["triage", "medicine", "anatomy",
                                                  "first_aid"]},
              "query": {"type": "string", "description": "symptoms, medicine name, "
                                                         "body part, or first-aid topic"},
              "question": {"type": "string"}}, (), _health, max_len=2400),
        Tool("holo", "Project the fullscreen holographic deck — live CPU, memory, "
             "network, storage, processes and a wireframe globe with the reactor "
             "core. Say 'close the deck' to dismiss it.",
             {"action": {"type": "string", "enum": ["show", "close"]}}, (), _holo),
        Tool("remind", "Set, list or cancel a reminder. 'in 20 minutes to stretch', "
                       "'at 18:30 to call amma'. It speaks when the time comes.",
             {"action": {"type": "string",
                         "enum": ["add", "list", "cancel", "clear"]},
              "text": {"type": "string", "description": "what and when, in plain words"},
              "which": {"type": "string", "description": "number or word, for cancel"}},
             (), _remind),
        Tool("find_file", "Search the user's own files by name across their real folders "
                          "(and inside small text files when asked). Read-only — names, "
                          "sizes and dates only.",
             {"query": {"type": "string", "description": "part of a filename, or words"},
              "name": {"type": "string", "description": "alias for query"},
              "kind": {"type": "string",
                       "description": "pdf, word, excel, image, video, audio, code…"},
              "grep": {"type": "boolean", "description": "also look inside text files"},
              "refresh_index": {"type": "boolean"}},
             (), _find_files),
        Tool("focus", "Start, check or stop a focus (pomodoro) session and report the "
                      "week's total. Real elapsed time, logged locally.",
             {"action": {"type": "string",
                         "enum": ["start", "status", "stop", "stats"]},
              "minutes": {"type": "string", "description": "block length, default 25"},
              "label": {"type": "string"}},
             (), _focus),
        Tool("briefing", "The morning briefing: time and date, calendar, reminders, "
                         "focus totals and machine health — only from real sources.",
             {"what": {"type": "string", "enum": ["full", "today"]}}, (), _briefing),
        Tool("content", "Create content: outline, draft, hooks, hashtags, or a "
                        "posting calendar. Measures word counts; never invents "
                        "engagement numbers.",
             {"action": {"type": "string",
                         "enum": ["outline", "draft", "hooks", "hashtags",
                                  "calendar", "kinds", "save"]},
              "topic": {"type": "string"}, "kind": {"type": "string",
                         "description": "blog, instagram, reel, youtube, email, ad, "
                                        "product, speech, whatsapp, thankyou"},
              "tone": {"type": "string"}, "audience": {"type": "string"},
              "words": {"type": "integer"}, "weeks": {"type": "integer"},
              "channels": {"type": "string"}}, (), _content, max_len=3000),
        Tool("marketing", "Digital marketing maths: funnel rates, CAC/ROAS, UTM "
                          "links, SEO/readability of your own text, A/B sample size, "
                          "channel playbooks. No invented benchmarks.",
             {"action": {"type": "string",
                         "enum": ["funnel", "utm", "seo", "sample", "plan", "email"]},
              "impressions": {"type": "number"}, "clicks": {"type": "number"},
              "leads": {"type": "number"}, "sales": {"type": "number"},
              "spend": {"type": "number"}, "revenue": {"type": "number"},
              "url": {"type": "string"}, "source": {"type": "string"},
              "medium": {"type": "string"}, "campaign": {"type": "string"},
              "text": {"type": "string"}, "keyword": {"type": "string"},
              "baseline": {"type": "number"}, "lift": {"type": "number"},
              "business": {"type": "string"}, "weeks": {"type": "integer"},
              "channels": {"type": "string"}, "product": {"type": "string"}},
             (), _marketing, max_len=2500),
        Tool("strategy", "Business strategy: SWOT, Porter's five forces, business "
                         "model canvas, OKRs, break-even, unit economics, weighted "
                         "decisions. Your facts, never invented ones.",
             {"action": {"type": "string",
                         "enum": ["swot", "forces", "bmc", "okr", "break", "unit",
                                  "decide"]},
              "subject": {"type": "string"}, "fixed": {"type": "number"},
              "price": {"type": "number"}, "variable": {"type": "number"},
              "cogs": {"type": "number"}, "cac": {"type": "number"},
              "repeat": {"type": "number"}, "options": {"type": "string"},
              "criteria": {"type": "string"}, "period": {"type": "string"}},
             (), _strategy, max_len=2500),
        Tool("hotel", "Hotel and restaurant operations: occupancy/ADR/RevPAR/GOPPAR, "
                      "menu costing, SOP checklists, guest journey, rate ladder.",
             {"action": {"type": "string",
                         "enum": ["kpi", "menu", "sop", "journey", "rates"]},
              "rooms": {"type": "integer"}, "sold": {"type": "integer"},
              "room_revenue": {"type": "number"}, "other_revenue": {"type": "number"},
              "costs": {"type": "number"}, "items": {"type": "string"},
              "target_food_cost": {"type": "number"},
              "department": {"type": "string"}, "stage": {"type": "string"},
              "base_rate": {"type": "number"}, "weekend_uplift": {"type": "number"},
              "season_uplift": {"type": "number"}}, (), _hotel, max_len=2500),
        Tool("travel", "Travel ideas, place finder, OpenStreetMap links, distances, "
                       "itineraries and honest budget bands — from a real dataset of "
                       "places with coordinates.",
             {"action": {"type": "string",
                         "enum": ["near", "map", "distance", "ideas", "itinerary",
                                  "budget", "places"]},
              "place": {"type": "string"}, "near": {"type": "string"},
              "radius_km": {"type": "number"}, "tag": {"type": "string"},
              "days": {"type": "integer"}, "pace": {"type": "string"},
              "tier": {"type": "integer"}, "people": {"type": "integer"},
              "travel_extra": {"type": "number"}, "budget_word": {"type": "string"},
              "months": {"type": "string"}}, (), _travel, max_len=2500),
        Tool("craft", "Design and craft: colour palettes with measured contrast, "
                      "printable posters, kolam patterns, borders, monograms — all "
                      "original SVG, all offline.",
             {"action": {"type": "string",
                         "enum": ["palette", "poster", "kolam", "border", "monogram"]},
              "base": {"type": "string", "description": "hex colour, e.g. #48f2ff"},
              "scheme": {"type": "string",
                         "description": "analogous, complementary, triad, tetrad, mono"},
              "title": {"type": "string"}, "subtitle": {"type": "string"},
              "name": {"type": "string"}, "dots": {"type": "integer"},
              "seed": {"type": "integer"}, "width": {"type": "integer"},
              "kind": {"type": "string"}, "save_it": {"type": "boolean"}},
             (), _craft, max_len=1800),
        Tool("mine", "Data mining on your own CSV/JSON: column profile, correlation "
                     "with n, IQR outliers, group-by totals, trend slope, full report.",
             {"action": {"type": "string",
                         "enum": ["profile", "report", "correlate", "outliers",
                                  "groupby", "trend"]},
              "path": {"type": "string"}, "column": {"type": "string"},
              "other": {"type": "string"}, "key": {"type": "string"},
              "value": {"type": "string"}, "agg": {"type": "string"},
              "periods": {"type": "integer"}}, (), _mine, max_len=2500),
        Tool("mentor", "Mentor and lateral thinking: SCAMPER, six hats, inversion, "
                       "five whys, pre-mortem, first principles, second-order "
                       "thinking, question banks.",
             {"action": {"type": "string",
                         "enum": ["scamper", "six_hats", "invert", "five_whys",
                                  "pre_mortem", "first_principles", "second_order",
                                  "questions", "rules"]},
              "subject": {"type": "string"}}, (), _mentor, max_len=2200),
        Tool("foresight", "Forecasting done honestly: arithmetic extrapolation with "
                          "an error band, scenarios with stated assumptions, and an "
                          "explicit 'I do not know' about live world events.",
             {"action": {"type": "string",
                         "enum": ["forecast", "scenario", "unknown", "verify",
                                  "rules", "now"]},
              "question": {"type": "string"}, "values": {"type": "string"},
              "periods": {"type": "integer"}, "horizon": {"type": "string"}},
             (), _foresight, max_len=2200),
        Tool("secure", "Defensive security only: your own password's entropy and "
                       "crack-time estimate, phishing signals, this PC's posture, a "
                       "recovery plan. No cracking, no intrusion — ever.",
             {"action": {"type": "string",
                         "enum": ["password", "phishing", "machine", "recovery",
                                  "refused"]},
              "text": {"type": "string"}}, (), _secure, max_len=2200),
        Tool("play", "Play a song or video right now — searches your indexed music and "
             "video (including external disks) and starts the best match in mpv/vlc/ffplay. "
             "Instant start, real queue, stop when asked. Also pause/next/previous/status.",
             {"action": {"type": "string", "enum": ["play", "stop", "status", "pause",
                                                   "resume", "next", "previous", "folder",
                                                   "players"]},
              "query": {"type": "string", "description": "song or video name"},
              "kind": {"type": "string", "enum": ["audio", "video"]},
              "path": {"type": "string", "description": "exact file to play"},
              "folder": {"type": "string", "description": "play everything in this folder"},
              "queue": {"type": "boolean"}},
             (), _play, max_len=900),
        Tool("library", "Index and search your audio and video — music folders and any "
             "external/pen drive. scan / search / stats / drives / forget. Read-only: it "
             "stats files, never opens or moves them.",
             {"action": {"type": "string", "enum": ["scan", "search", "stats", "drives",
                                                   "forget"]},
              "roots": {"type": "string", "description": "folders or drives, separated by |"},
              "query": {"type": "string"}, "kind": {"type": "string"},
              "limit": {"type": "integer"}}, (), _library, max_len=1600),
        Tool("plan", "Turn a request into ordered steps and execute them: scan a disk then "
             "play a song, build a reel, grade files, analyse a file, decide, plan a goal. "
             "'think' shows the steps without running them.",
             {"action": {"type": "string", "enum": ["do", "think", "recipes"]},
              "request": {"type": "string", "description": "the task in the user's words"},
              "confirm": {"type": "boolean"}}, (), _plan, max_len=2000),
        Tool("coach", "A mentor, analyst and listener: listen (name the feeling, one "
             "question), mentor (framework + 7-day plan), analyst (fact vs inference vs "
             "guess), decide (reversible test, weighted criteria), checkin, journal and "
             "reflection. Local and private; never diagnoses, always offers real crisis "
             "numbers when they matter.",
             {"mode": {"type": "string", "enum": ["listen", "mentor", "analyst", "decide",
                                                 "plan", "checkin"]},
              "text": {"type": "string"}, "options": {"type": "string",
                                                     "description": "options separated by |"},
              "action": {"type": "string", "enum": ["journal", "reflection", "checkin"]}},
             (), _coach, max_len=2400),
        Tool("backup", "Copy your own folders to another disk and PROVE the copy: every "
                       "file is SHA-256 hashed on the destination. Never overwrites, never "
                       "deletes, never touches the originals; refuses to copy a folder into "
                       "itself or fill a disk.",
             {"action": {"type": "string",
                         "enum": ["copy", "plan", "verify", "list", "drives"]},
              "source": {"type": "string"}, "target": {"type": "string"},
              "include": {"type": "string"}, "verify": {"type": "boolean"},
              "dry_run": {"type": "boolean"}},
             (), _backup, confirm=True, max_len=2400),
        Tool("vault", "Where your work lives. Projects with their own folder, notes and "
                      "progress saved as you go, and a one-command EXPORT to your Desktop "
                      "or any other folder (a verified copy — the vault keeps its own). "
                      "Never moves or overwrites your originals.",
             {"action": {"type": "string",
                         "enum": ["where", "list", "create", "save", "checkpoint", "add",
                                  "export", "resume"]},
              "project": {"type": "string"}, "text": {"type": "string"},
              "path": {"type": "string"}, "dest": {"type": "string"}},
             (), _vault, max_len=1800),
        Tool("autostart", "Start Arc Desk with your own account: one per-user entry, no "
                          "admin, verified by reading it back, removable here or in Task "
                          "Manager. Off unless you ask.",
             {"action": {"type": "string", "enum": ["status", "on", "off"]}},
             (), _autostart, max_len=1200),
        Tool("pc_health", "Why is this PC slow? Two measured samples one second apart, then "
                          "the actual cause with the number that proves it: RAM pressure, "
                          "paging, a CPU hog, a nearly-full drive, startup bloat, heat. "
                          "Suggests fixes; never kills or changes anything.",
             {"action": {"type": "string",
                         "enum": ["scan", "quick", "startup", "checks"]},
              "text": {"type": "string"}},
             (), _pc_health, max_len=2600),
        Tool("search_inside", "Search the WORDS INSIDE your own documents — Word, Excel, "
                              "PowerPoint, PDF, CSV, text — and quote the matching line with "
                              "its file and line number. Read-only; images only with OCR on.",
             {"action": {"type": "string",
                         "enum": ["search", "index", "ocr", "stats", "forget"]},
              "query": {"type": "string"}, "roots": {"type": "string"},
              "ocr": {"type": "boolean"}, "limit": {"type": "integer"}},
             (), _search_inside, max_len=2200),
        Tool("explain", "Read an error message — typed, in your clipboard, or on the "
                         "screen via OCR — and say what it means, why it happens, and "
                         "the ordered steps to fix it. Refuses to invent a cause when it "
                         "does not recognise the error.",
             {"text": {"type": "string", "description": "the error text, if you have it"},
              "where": {"type": "string",
                        "enum": ["text", "clipboard", "screen", "catalog"]}},
             (), _explain, max_len=2600),
        Tool("facts", "What JARVIS knows: 75 dated, sourced facts (India, world, science, "
                      "tech, money, health, food, myths), plus your own indexed files, "
                      "plus a real Wikipedia lookup that cites its date. Says 'I do not "
                      "know' when it does not.",
             {"action": {"type": "string",
                         "enum": ["ask", "coverage", "domain", "random", "unknown",
                                  "ingest", "fetch"]},
              "question": {"type": "string"}, "domain": {"type": "string"},
              "topic": {"type": "string"}, "path": {"type": "string"}},
             (), _facts, max_len=2200),
        Tool("packages", "The GitHub open-source catalogue: which free projects can "
                         "do a job, which are installed on this PC, and the exact "
                         "install command for the rest. Nothing here costs money.",
             {"action": {"type": "string",
                         "enum": ["search", "scan", "plan", "all", "detail"]},
              "query": {"type": "string", "description": "what you want it to do"},
              "role": {"type": "string",
                       "description": "brain, ears, mouth, wake, see, recall, flow, "
                                      "tools, glue, ship"},
              "key": {"type": "string", "description": "package key for detail"}},
             (), _packages, max_len=2200),
        Tool("list_tools", "The full catalogue of what you can do, when the few tools "
                           "you were given are not enough. Pass a query to filter.",
             {"query": {"type": "string"}}, (),
             lambda query="": _catalogue(query)),

        # ---- numbers that must be exact, not guessed by a model -------
        Tool("calc", "Evaluate arithmetic exactly: '(1234*0.18)+56', '18% of 4500', "
                     "'sqrt(144)+2**10'. Use this instead of doing maths in your head.",
             {"expression": {"type": "string"}}, ("expression",), knows.calc),
        Tool("convert", "Convert units: 5 km to mile, 100 f to c, 2 kg to lb.",
             {"value": {"type": "number"}, "from_unit": {"type": "string"},
              "to_unit": {"type": "string"}}, ("value", "from_unit", "to_unit"),
             knows.convert),
        Tool("rates", "Live exchange rates for a base currency (needs internet).",
             {"base": {"type": "string"}, "symbols": {"type": "string"}},
             (),
             lambda base="INR", symbols="": knows.rates(base, symbols)),
        Tool("stock", "A live quote for a ticker or an index: RELIANCE, nifty, sensex, "
                      "bitcoin, gold, usd inr. Includes the 30-day move.",
             {"symbol": {"type": "string"}}, ("symbol",), knows.stock),
        Tool("project", "Fit a straight line to recent prices and show the ±2σ band. "
                        "A trend, not a prophecy — say so when you report it.",
             {"symbol": {"type": "string"}, "days": {"type": "integer"}},
             ("symbol",), lambda symbol, days=7: knows.project(symbol, int(days))),
        Tool("market_summary", "One screen of the Indian market: NIFTY, SENSEX, gold, "
                               "USD/INR, Bitcoin. Fast when you're asked 'market eppadi'.",
             {}, (), knows.market_summary),

        # ---- teaching ARC new commands by talking ---------------------
        Tool("teach_macro", "Learn a repeatable voice command. Example: 'when I say work "
                            "mode, open code and set volume 40'. Only safe actions are kept.",
             {"instruction": {"type": "string"}}, ("instruction",), macros.teach),
        Tool("macros", "List the learned voice commands, run one, or forget one.",
             {"action": {"type": "string", "enum": ["list", "run", "forget"]},
              "name": {"type": "string"}}, ("action",),
             lambda action="list", name="": (
                 macros.run(name) if action == "run" else
                 macros.forget(name) if action == "forget" else macros.describe(name))),
        Tool("whatsapp_send", "Open WhatsApp with a message written to a number.",
             {"number": {"type": "string"}, "message": {"type": "string"}},
             ("number", "message"), comms.whatsapp_send, confirm=True),
    ]
}


# The tools people actually speak. Everything else stays available to the model
# that can afford it: 26 schemas cost ~2000 prompt tokens, and on a CPU-only
# laptop prompt evaluation dominates latency. Measured on 2 threads: 2040 tokens
# of prompt took 34 s on a 1.5B model, so halving the schema set is worth more
# than any sampling tweak.
def _look(question: str = "", lang: str = "", limit: int = 2500) -> str:
    """`look` — OCR the screen and hand the text to the model with the question.

    The screenshot is kept, because "it said no text" is only believable when the
    file is right there and the user can open it.
    """
    import tempfile

    shot = str(Path(tempfile.gettempdir()) / time.strftime("arc_look_%H%M%S.png"))
    try:
        text = _vision().screen_text(shot, limit=limit, lang=lang)
    except Exception as exc:
        return f"ERROR: could not read the screen ({type(exc).__name__}: {exc})"
    if text.startswith("ERROR"):
        return text
    head = f'question: {question.strip() or "what is on the screen?"}'
    if not text.strip() or text.startswith("no readable text"):
        return (f"{head}\nI captured the screen ({shot}) but found no readable text — "
                "it may be a game, a video, or an image-only window.")
    return (f"{head}\nscreen text (OCR, may contain errors):\n{text}\n"
            f"screenshot: {shot}")


def _catalogue(query: str = "", limit: int = 40) -> str:
    """`list_tools` — the discovery escape hatch when routing kept a tool out."""
    q = (query or "").strip().lower()
    rows = []
    for t in TOOLS.values():
        label = t.name.replace("_", " ")
        hay = f"{label} {t.description}".lower()
        if q and q not in hay:
            continue
        rows.append(f"{label} — {t.description.split('.')[0]}")
    if not rows:
        return f"nothing matches '{query}'. There are {len(TOOLS)} tools in total."
    head = f"{len(rows)} of {len(TOOLS)} tools"
    if q:
        head += f" matching '{query}'"
    cut = "" if len(rows) <= limit else f"\n… and {len(rows) - limit} more; narrow the query."
    return head + ":\n" + "\n".join(rows[:limit]) + cut


CORE = (
    "open_app", "open_url", "web_search", "time", "system_report", "note",
    "read_notes", "draw", "art_edit", "set_volume", "mute", "media",
    "screenshot", "timer", "weather", "find_file", "arc_mode", "clipboard",
)


def schemas(core_only: bool = False, only: list[str] | None = None) -> list[dict]:
    """OpenAI function-calling schema for the tools, including MCP servers.

    core_only — the speaking-sized subset, for small local models
    only      — an explicit list of names
    """
    chosen = TOOLS.values()
    if core_only:
        chosen = [t for t in TOOLS.values() if t.name in CORE]
    elif only is not None:
        chosen = [t for t in TOOLS.values() if t.name in set(only)]
    out = []
    for t in chosen:
        out.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {"type": "object", "properties": t.params,
                               "required": list(t.required)},
            },
        })
    if mcp_manager is not None:
        try:
            out.extend(mcp_manager.tool_schemas())
        except Exception:
            pass
    return out


def call(name: str, args: dict | str) -> str:
    """Execute a tool. Never raises. Returns a string for the model to read."""
    if name.startswith("mcp__"):
        if mcp_manager is None:
            return "ERROR: MCP is not enabled in this session"
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except Exception:
                return "ERROR: could not parse arguments"
        try:
            return str(mcp_manager.call(name, args or {}))[:1500]
        except Exception as exc:
            return f"ERROR: MCP call failed: {type(exc).__name__}: {exc}"
    t = TOOLS.get(name)
    if t is None:
        return f"ERROR: unknown tool '{name}'"
    if t.platforms and sys.platform not in t.platforms:
        return f"ERROR: {name} is only available on {', '.join(t.platforms)}"
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except Exception:
            return f"ERROR: could not parse arguments for {name}"
    args = args or {}
    missing = [k for k in t.required if k not in args]
    if missing:
        return f"ERROR: {name} needs {', '.join(missing)}"
    try:
        result = str(t.func(**{k: v for k, v in args.items() if k in t.params}))
        return result[:max(200, t.max_len)]
    except TypeError as exc:
        return f"ERROR: bad arguments for {name}: {exc}"
    except Exception as exc:
        return f"ERROR: {name} failed: {type(exc).__name__}: {exc}"


def describe() -> str:
    extra = 0
    if mcp_manager is not None:
        try:
            extra = len(mcp_manager.tool_schemas())
        except Exception:
            extra = 0
    return f"{len(TOOLS)} tools" + (f" + {extra} MCP" if extra else "")
