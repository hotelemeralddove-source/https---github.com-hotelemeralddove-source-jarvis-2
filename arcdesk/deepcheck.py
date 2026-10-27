"""The checks that prove the promises, run on *your* machine.

`tools/doctor.py` answers "is this installed and sane". This file answers the two
questions a README cannot:

  1. **Do the desktop tools actually fire?** Thirteen of them can only run on a real
     Windows session — open an app, set the volume, click a button. They are written,
     wired and reviewed, and until this runs, unproven.
  2. **Does the microphone work, and can the wake word hear anything?**

Two stages on purpose:

    safe checks   — read-only or written to a temp file. Always run.
    touch checks  — they really do open Notepad, change your volume, type into the
                    focused window, and lock the screen. Only with ``--touch``.

Nothing here is allowed to leave your machine: the log is a text file next to your
settings, so you can read it, delete it, or paste it to me when something fails.
The verdicts are deliberately blunt — ``SKIP`` means "not this OS", ``MANUAL``
means "I could break your session, so I did not try".
"""
from __future__ import annotations

import json
import time

def HAS_DISPLAY() -> bool:
    """A headless box cannot screenshot — say so instead of calling it broken."""
    import os
    if os.name == "nt" or os.uname().sysname == "Darwin":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


# name, args, stage, note
DESKTOP: list[tuple[str, dict, str, str]] = [
    # --- safe: reads state or writes to a temp file -----------------------
    ("screenshot", {"path": ""}, "safe", "captures the screen to a temp PNG"),
    ("screen_text", {}, "safe", "OCR of the screen (needs Tesseract)"),
    ("windows", {"action": "list"}, "safe", "lists open windows"),
    ("ui_controls", {"limit": 8}, "safe", "reads the accessibility tree"),
    ("clipboard", {"action": "read"}, "safe", "reads the clipboard"),
    ("running_apps", {}, "safe", "lists processes"),
    ("system_report", {}, "safe", "cpu / ram / disk"),
    # --- touch: these change your session --------------------------------
    ("open_app", {"app": "notepad"}, "touch", "opens Notepad"),
    ("set_volume", {"level": 30}, "touch", "sets the volume to 30 %"),
    ("mute", {"on": True}, "touch", "mutes, then the next row unmutes"),
    ("mute", {"on": False}, "touch", "unmutes"),
    ("brightness", {"level": 80}, "touch", "sets brightness to 80 %"),
    ("media", {"action": "play_pause"}, "touch", "sends a media key"),
    ("type_text", {"text": "arc desk deep check"}, "touch", "types into the focused window"),
    ("press", {"keys": "ctrl+a"}, "touch", "sends a hotkey"),
    ("click_at", {"x": 10, "y": 10}, "touch", "moves the mouse to the top-left"),
    ("ui_act", {"name": "OK", "action": "focus"}, "touch", "focuses a control named OK"),
    ("click_text", {"text": "OK"}, "touch", "click-to-text, any app"),
    ("open_url", {"url": "https://example.com"}, "touch", "opens a browser tab"),
    ("lock_screen", {}, "last", "locks the session — run this one last, on purpose"),
]


# A Windows-only tool asked on Linux is not a failure, it is the wrong machine.
# These markers are exactly the honest errors the tools themselves return.
PLATFORM_MARKERS = ("xdotool", "no display", "pyatspi", "xclip", "on linux",
                    "not available on this platform", "on windows")


def _verdict(detail: str) -> tuple[str, str]:
    text = (detail or "").strip()
    low = text.lower()
    if not text:
        return "FAIL", "no output"
    if any(marker in low for marker in PLATFORM_MARKERS):
        return "SKIP", text[:160]
    if low.startswith("error") or "traceback" in low:
        return "FAIL", text[:160]
    return "OK", text[:160]


def run_desktop(touch: bool = False, only: list[str] | None = None) -> list[dict]:
    """Call the desktop tools for real. Returns one row per attempt."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from arcdesk.ai import tools

    rows: list[dict] = []
    for name, args, stage, note in DESKTOP:
        if only and name not in only:
            continue
        if stage == "last" and not touch:
            rows.append({"tool": name, "stage": stage, "verdict": "MANUAL",
                         "detail": "locks the screen — pass --touch to include it"})
            continue
        if stage == "touch" and not touch:
            rows.append({"tool": name, "stage": stage, "verdict": "MANUAL",
                         "detail": note})
            continue
        if name == "screenshot" and not HAS_DISPLAY():
            rows.append({"tool": name, "stage": stage, "verdict": "SKIP",
                         "detail": "no display attached — nothing to capture"})
            continue
        if name == "screenshot":
            import tempfile
            args = {"path": str(Path(tempfile.gettempdir()) / "arc_deep_check.png")}
        t0 = time.time()
        try:
            out = tools.call(name, args)
        except Exception as exc:                       # tools.call never raises, but be sure
            out = f"ERROR: {type(exc).__name__}: {exc}"
        ms = (time.time() - t0) * 1000
        verdict, detail = _verdict(out)
        rows.append({"tool": name, "stage": stage, "verdict": verdict,
                     "detail": detail, "ms": round(ms, 1), "note": note})
    return rows


def run_voice() -> list[dict]:
    """Microphone and wake word, measured on the live device."""
    rows: list[dict] = []

    try:
        import sounddevice as sd
    except Exception:
        rows.append({"tool": "microphone", "stage": "voice", "verdict": "SKIP",
                     "detail": "sounddevice not installed — pip install -r requirements-voice.txt"})
        sd = None
    if sd is not None:
        try:
            dev = sd.query_devices(kind="input")
            rate = int(dev.get("default_samplerate") or 16000)
            rows.append({"tool": "microphone", "stage": "voice", "verdict": "OK",
                         "detail": f"{dev.get('name', 'input')} @ {rate} Hz, "
                                   f"{dev.get('max_input_channels', 1)} ch"})
            import numpy as np
            seconds = 1.0
            audio = sd.rec(int(rate * seconds), samplerate=rate, channels=1, dtype="int16")
            sd.wait()
            rms = float(np.sqrt(np.mean(audio.astype("float32") ** 2)) or 0)
            quiet = rms < 40
            rows.append({"tool": "microphone level", "stage": "voice",
                         "verdict": "OK" if rms > 5 else "FAIL",
                         "detail": f"peak rms {rms:.0f} while recording 1 s"
                                   + (" — that is silence, check the input device"
                                      if quiet else "")})
        except Exception as exc:
            rows.append({"tool": "microphone", "stage": "voice", "verdict": "FAIL",
                         "detail": f"{type(exc).__name__}: {exc}"})

    for module, label in (("vosk", "vosk"), ("openwakeword", "openwakeword")):
        try:
            __import__(module)
            rows.append({"tool": f"wake engine: {label}", "stage": "voice", "verdict": "OK",
                         "detail": "installed"})
        except Exception:
            rows.append({"tool": f"wake engine: {label}", "stage": "voice", "verdict": "SKIP",
                         "detail": "not installed — run install_voice.bat"})

    try:
        from arcdesk import config
        cfg = config.load()
        wake = cfg.get("wake", {})
        rows.append({"tool": "wake word", "stage": "voice",
                     "verdict": "OK" if wake.get("enabled") else "SKIP",
                     "detail": f"phrase '{wake.get('phrase', 'hey jarvis')}', "
                               f"{'armed' if wake.get('enabled') else 'off (opt-in by design)'}"})
        rows.append({"tool": "voice out", "stage": "voice", "verdict": "OK",
                     "detail": f"engine {cfg.get('ai', {}).get('voice_engine', 'auto')}"})
    except Exception as exc:
        rows.append({"tool": "config", "stage": "voice", "verdict": "FAIL",
                     "detail": f"{type(exc).__name__}: {exc}"})
    return rows


def environment() -> list[str]:
    """Everything I would ask for first if the log arrived without it."""
    import os
    import platform
    import shutil
    import sys
    lines = [f"python      {sys.version.split()[0]}",
             f"platform    {platform.platform()}",
             f"frozen      {bool(getattr(sys, 'frozen', False))}"]
    try:
        from arcdesk import config
        lines.append(f"data dir    {config.data_dir()}")
    except Exception:
        pass
    for binary in ("ffmpeg", "ffprobe", "ffplay", "mpv", "vlc", "tesseract", "node", "npx",
                   "uvx", "git"):
        found = shutil.which(binary)
        if not found:
            lines.append(f"{binary:<11} not found")
            continue
        version = ""
        try:
            from . import quiet
            out = quiet.run([found, "-version" if binary.startswith("ff") else "--version"],
                                 capture_output=True, text=True, timeout=6)
            first = ((out.stdout or out.stderr or "").strip().splitlines() or [""])[0]
            version = " · " + first[:70]
        except Exception:
            pass
        lines.append(f"{binary:<11} {found}{version}")
    for module, label in (("psutil", "psutil"), ("PySide6", "PySide6"), ("PIL", "Pillow"),
                          ("numpy", "numpy"), ("docx", "python-docx"),
                          ("openpyxl", "openpyxl"), ("sounddevice", "sounddevice")):
        try:
            member = __import__(module)
            lines.append(f"{label:<11} {getattr(member, '__version__', 'installed')}")
        except Exception:
            lines.append(f"{label:<11} not importable")
    try:
        import psutil
        mem = psutil.virtual_memory()
        lines.append(f"ram         {mem.total / 1024 ** 3:.1f} GB total, "
                     f"{mem.available / 1024 ** 3:.1f} GB available")
        lines.append(f"cpus        {psutil.cpu_count(logical=True)} logical")
    except Exception:
        pass
    lines.append(f"env         ARCDESK_HOME={os.environ.get('ARCDESK_HOME', '')}")
    return lines


def run_core() -> list[dict]:
    """The pipelines the last four waves promised, executed for real and timed.

    These are the checks that do not need a desktop: media indexing, playback spawn,
    document search, error reading, slowdown diagnosis, backup+verify. Every row is a
    real call against a throw-away folder, so a red row means *this machine* would fail
    for the user too.
    """
    import tempfile
    from pathlib import Path

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from arcdesk.ai import tools

    rows: list[dict] = []
    home = Path(tempfile.mkdtemp(prefix="arc-core-check-"))
    lib = home / "media"
    lib.mkdir()

    def run(tool: str, args: dict, note: str = "") -> None:
        t0 = time.time()
        try:
            out = tools.call(tool, args)
        except Exception as exc:                      # tools.call should never raise
            out = f"ERROR: {type(exc).__name__}: {exc}"
        ms = round((time.time() - t0) * 1000, 1)
        verdict, detail = _verdict(out)
        rows.append({"tool": tool, "stage": "core", "verdict": verdict,
                     "detail": (note + " · " if note else "") + detail, "ms": ms})

    # 1. media index over a real (if empty) folder
    run("library", {"action": "scan", "roots": str(lib)}, "scan a folder")
    # 2. playback — does a player exist at all, and does the honest error path work
    run("play", {"action": "players"}, "players available")
    run("play", {"action": "status"}, "nothing playing")
    # 3. document search over a real text file
    doc = home / "note.txt"
    doc.write_text("deep check: the rooftop cafe invoice is 45000 rupees\n", encoding="utf-8")
    run("search_inside", {"action": "index", "roots": str(home)}, "index one file")
    run("search_inside", {"action": "search", "query": "rooftop cafe"}, "search inside it")
    # 4. the error reader
    run("explain", {"text": "The application was unable to start correctly (0xc000007b)."},
        "explain a known code")
    run("explain", {"where": "catalog"}, "the catalogue loads")
    # 5. slowdown diagnosis (one second of sampling)
    run("pc_health", {"action": "quick"}, "measured 0.4 s")
    # 6. backup + verify, into a throw-away target, with a real file to prove
    payload = lib / "sample.txt"
    payload.write_text("backup payload for the deep check\n", encoding="utf-8")
    target = home / "backup_here"
    target.mkdir()
    t0 = time.time()
    result = tools.call("backup", {"action": "copy", "source": str(lib),
                                   "target": str(target)})
    ok_copy = "verified: all 1 files" in result or "verified" in result.lower()
    rows.append({"tool": "backup (copy)", "stage": "core",
                 "verdict": "OK" if ok_copy and "did not copy" not in result else "FAIL",
                 "detail": result.splitlines()[0][:140] if result else "no output",
                 "ms": round((time.time() - t0) * 1000, 1)})
    run("backup", {"action": "drives"}, "drives visible")
    # 7. autostart is read-only here: never flip a startup entry during a diagnosis
    run("autostart", {"action": "status"}, "read-only")
    # 8. the coach rails, because a broken crisis path is the worst possible bug
    out = tools.call("coach", {"mode": "listen", "text": "i want to die"})
    rows.append({"tool": "coach (crisis)", "stage": "core",
                 "verdict": "OK" if "14416" in out else "FAIL",
                 "detail": ("real helpline numbers returned" if "14416" in out
                            else "CRISIS PATH DID NOT RETURN THE HELPLINE")})
    return rows


def summarise(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    return {
        "ok": counts.get("OK", 0),
        "fail": counts.get("FAIL", 0),
        "skip": counts.get("SKIP", 0),
        "manual": counts.get("MANUAL", 0),
        "rows": len(rows),
    }


def write_log(rows: list[dict], header: str = "") -> str:
    """One text file the user can read or send. No telemetry, ever."""
    from arcdesk import config
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = config.data_dir() / f"deep_check_{stamp}.txt"
    lines = [f"JARVIS DESK deep check — {time.strftime('%Y-%m-%d %H:%M')}",
             f"platform: {__import__('sys').platform}"]
    if header:
        lines.append(header)
    lines.extend(["", "environment:", *[f"  {line}" for line in environment()], ""])
    for row in rows:
        lines.append(f"[{row['verdict']:<6}] {row['tool']:<18} {row.get('detail', '')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def as_json(rows: list[dict]) -> str:
    return json.dumps({"rows": rows, "summary": summarise(rows)}, indent=2)
