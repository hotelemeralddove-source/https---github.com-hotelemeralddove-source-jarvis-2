"""Cinematic cues — generated, not shipped, and never in the way.

The request: *"jarvis open aagi magic mode begin aagum pothu, close aagum pothu athuku
match aagura mathiri fx beats, task process aagum pothu oru beat, completed na oru beat."*

Why generated instead of downloaded: a WAV pack is 5–20 MB of somebody else's audio with
a licence attached, and it would have to be inside the installer or fetched on first run.
These cues are **synthesised once** (a few hundred milliseconds of arithmetic), written
to `%APPDATA%\\ArcDesk\\sfx`, and reused for ever. No download, no licence, no bundle.

Rules that matter more than the sound design:

* **never block the interface** — every cue plays on a thread, and on Windows through
  `winsound` with `SND_ASYNC`; the window never waits for a speaker;
* **never raise** — a machine with no audio device is normal (a server, a headless VM),
  and a missing cue must not be the reason a wake word fails;
* **never nag** — the cues are one short cue per event, and every one can be switched off
  in Settings (Look & sound) with a volume slider;
* **the volume is baked in** the cache key, so changing the slider never regenerates
  anything while the app is running.

The cues are short on purpose (0.25–1.5 s): a 4-second fanfare is charming once and
infuriating the tenth time.
"""
from __future__ import annotations

import array
import math
import os
import subprocess

from . import quiet
import sys
import threading
import wave
from pathlib import Path

RATE = 22050
CUES = {
    "wake": 1.45,          # "hey jarvis" heard: a rising shimmer
    "magic_begin": 1.5,    # the screen takes over: deep bloom + sweep up
    "magic_end": 1.2,      # leaving: sweep down, one soft bell
    "task_start": 0.28,    # a task was assigned: one confident tick
    "task_done": 0.9,      # it finished: two rising notes
    "task_failed": 0.55,   # it did not: a low thud, no drama
    "click": 0.12,
}

_LOCK = threading.Lock()
_LAST: dict[str, float] = {}


# --------------------------------------------------------------------------- paths
def sfx_dir() -> Path:
    from .config import data_dir
    d = data_dir() / "sfx"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _vol_step(volume: float) -> int:
    return max(0, min(10, int(round(float(volume) * 10))))


def cue_path(name: str, volume: float = 0.55) -> Path:
    return sfx_dir() / f"{name}_v{_vol_step(volume)}.wav"


# --------------------------------------------------------------------------- synthesis
def _env(i: int, n: int, attack: float = 0.02, decay: float = 0.55) -> float:
    """A quick attack and a long tail — the shape of every film cue that works."""
    t = i / RATE
    a = max(1e-4, attack)
    if t < a:
        return t / a
    return math.exp(-(t - a) / max(1e-3, decay))


def _tone(buf: list[float], f0: float, f1: float, start: float, dur: float,
          gain: float, decay: float = 0.55, attack: float = 0.02) -> None:
    """Add a gliding sine (f0 → f1) with a bell-ish tail. Pure stdlib, no numpy."""
    i0 = int(start * RATE)
    n = int(dur * RATE)
    for k in range(n):
        i = i0 + k
        if i >= len(buf):
            break
        u = k / max(1, n - 1)
        f = f0 * (1 - u) + f1 * u
        e = _env(k, n, attack, decay)
        buf[i] += gain * e * math.sin(2 * math.pi * f * (k / RATE))


def _noise_whoosh(buf: list[float], start: float, dur: float, gain: float,
                  up: bool = True) -> None:
    """Filtered noise that opens or closes — the 'air' of a cinematic transition."""
    i0 = int(start * RATE)
    n = int(dur * RATE)
    x = 1234567
    lp = 0.0
    for k in range(n):
        i = i0 + k
        if i >= len(buf):
            break
        u = k / max(1, n - 1)
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        white = (x / 0x3FFFFFFF) - 1.0
        cutoff = 0.02 + 0.5 * (u if up else 1 - u)
        lp += cutoff * (white - lp)
        shape = math.sin(math.pi * u) ** 1.6
        buf[i] += gain * shape * lp


def _bell(buf: list[float], f: float, start: float, dur: float, gain: float) -> None:
    """A struck bell: fundamental plus two quiet partials, each decaying a little faster."""
    _tone(buf, f, f, start, dur, gain, decay=dur * 0.45, attack=0.005)
    _tone(buf, f * 2.01, f * 2.01, start, dur * 0.7, gain * 0.28, decay=dur * 0.28,
          attack=0.004)
    _tone(buf, f * 3.02, f * 3.02, start, dur * 0.5, gain * 0.12, decay=dur * 0.2,
          attack=0.003)


def render(name: str) -> list[float]:
    """One cue, as float samples in -1..1. Deterministic: same name, same sound."""
    dur = CUES.get(name, 0.5)
    n = int(dur * RATE)
    buf = [0.0] * n
    if name == "wake":
        _noise_whoosh(buf, 0.0, dur * 0.55, 0.28, up=True)
        _tone(buf, 220.0, 440.0, 0.05, dur * 0.7, 0.22, decay=0.45)
        _bell(buf, 880.0, dur * 0.42, dur * 0.55, 0.26)
    elif name == "magic_begin":
        _tone(buf, 70.0, 52.0, 0.0, 0.7, 0.40, decay=0.35, attack=0.01)     # the bloom
        _noise_whoosh(buf, 0.10, dur * 0.75, 0.22, up=True)
        _tone(buf, 330.0, 660.0, 0.35, dur * 0.55, 0.18, decay=0.4)
        _bell(buf, 1320.0, dur * 0.55, 0.55, 0.16)
    elif name == "magic_end":
        _noise_whoosh(buf, 0.0, dur * 0.6, 0.22, up=False)
        _tone(buf, 520.0, 180.0, 0.05, dur * 0.8, 0.22, decay=0.5)
        _bell(buf, 660.0, dur * 0.35, dur * 0.6, 0.18)
    elif name == "task_start":
        _tone(buf, 880.0, 1180.0, 0.0, dur, 0.30, decay=0.10, attack=0.004)
    elif name == "task_done":
        _bell(buf, 784.0, 0.0, 0.45, 0.30)          # G5
        _bell(buf, 1046.5, 0.16, 0.6, 0.26)         # C6
    elif name == "task_failed":
        _tone(buf, 160.0, 96.0, 0.0, dur, 0.34, decay=0.22, attack=0.006)
    elif name == "click":
        _tone(buf, 1500.0, 1200.0, 0.0, dur, 0.16, decay=0.03, attack=0.002)
    # master: a tiny fade at both ends, so nothing starts with a click
    fade = min(220, n // 4)
    for k in range(fade):
        buf[k] *= k / fade
        buf[n - 1 - k] *= k / fade
    peak = max((abs(v) for v in buf), default=0.0) or 1.0
    return [v / peak for v in buf]


def write_cue(name: str, volume: float = 0.55) -> str:
    """Render and cache one cue. Returns the path ('' if it could not be made)."""
    path = cue_path(name, volume)
    try:
        if path.is_file() and path.stat().st_size > 2000:
            return str(path)
        samples = render(name)
        scale = max(0.0, min(1.0, float(volume))) * 0.9
        pcm = array.array("h", (int(max(-1.0, min(1.0, s)) * scale * 32767)
                                for s in samples))
        tmp = path.with_suffix(".part")
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm.tobytes())
        os.replace(tmp, path)
        return str(path)
    except Exception:
        return ""


def ensure_all(volume: float = 0.55) -> dict[str, str]:
    """Make sure every cue exists. Cheap after the first run (~90 KB in total)."""
    return {name: write_cue(name, volume) for name in CUES}


# --------------------------------------------------------------------------- playing
def _play_async(path: str) -> bool:
    """Fire and forget. Returns False only when nothing could play it at all."""
    try:
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC |
                               winsound.SND_NODEFAULT)
            return True
        if sys.platform == "darwin":
            quiet.popen(["afplay", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        for player in ("paplay", "aplay", "ffplay"):
            from shutil import which
            exe = which(player)
            if exe:
                argv = [exe, path] if player != "ffplay" else \
                    [exe, "-nodisp", "-autoexit", "-loglevel", "quiet", path]
                quiet.popen(argv, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return True
    except Exception:
        return False
    return False


def enabled(cfg: dict | None = None) -> bool:
    return bool(((cfg or {}).get("sfx") or {}).get("enabled", True))


def volume(cfg: dict | None = None) -> float:
    try:
        return max(0.0, min(1.0, float(((cfg or {}).get("sfx") or {}).get("volume", 0.55))))
    except Exception:
        return 0.55


def play(name: str, cfg: dict | None = None, min_gap: float = 0.12) -> bool:
    """Play a cue, on a thread, ignoring every reason it might not work.

    `min_gap` stops the same cue from machine-gunning when several tools finish in the
    same second (one task with four tools should not sound like a pinball machine).
    """
    try:
        if not enabled(cfg):
            return False
        if volume(cfg) <= 0.01:
            return False                # silent is silent: do not even queue the work
        import time
        now = time.monotonic()
        with _LOCK:
            last = _LAST.get(name, 0.0)
            if now - last < min_gap:
                return False
            _LAST[name] = now

        def work() -> None:
            # A missing audio device, a locked file, an OS that changed its mind:
            # none of that is the user's problem mid-conversation. Never raise here —
            # an exception in a cue thread would print a traceback over the app.
            try:
                vol = volume(cfg)
                if vol <= 0.01:
                    return
                path = write_cue(name, vol)
                if path:
                    _play_async(path)
            except Exception:
                return

        threading.Thread(target=work, daemon=True, name=f"arc-sfx-{name}").start()
        return True
    except Exception:
        return False


def describe(cfg: dict | None = None) -> str:
    state = "on" if enabled(cfg) else "off"
    files = [p.name for p in sfx_dir().glob("*.wav")]
    return (f"cinematic cues: {state} at {int(volume(cfg) * 100)}% · "
            f"{len(CUES)} cues, {len(files)} rendered in {sfx_dir()}")
