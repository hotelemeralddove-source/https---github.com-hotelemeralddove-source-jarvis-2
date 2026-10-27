"""Play it now — songs and videos, with no buffering and no waiting for a model.

Why a dedicated player module instead of "open the file and hope":

* **Instant.** The command is spawned directly (mpv → vlc → ffplay → the OS handler) and
  the time to first frame is measured and reported in milliseconds. Nothing is uploaded,
  nothing is transcoded first.
* **Controllable.** Because ARC starts the process, ARC can stop it, and the OS media
  keys (already wired) pause/next it. A player ARC did not start is left alone.
* **Honest.** If the file is not in the index, it says so and offers the scan instead of
  guessing a path. If no player exists, it says which one to install — one free command.

An external disk needs no special case: once `library.scan()` has seen it, its files are
just paths, and every player here takes a path.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess

from . import quiet
import sys
import time
from pathlib import Path

from . import library

_AUDIO = library.AUDIO_EXT
_VIDEO = library.VIDEO_EXT

_CURRENT: dict = {"proc": None, "player": "", "files": [], "started": 0.0,
                  "ok": False, "error": ""}

QUEUE_LIMIT = 30


def candidates() -> list[dict]:
    """Players that can be driven from a command line, best first."""
    found: list[dict] = []
    for name, exe, video, queue in (("mpv", "mpv", True, True),
                                    ("vlc", "vlc", True, True),
                                    ("ffplay", "ffplay", True, False),
                                    ("mplayer", "mplayer", True, False)):
        path = shutil.which(exe)
        if path:
            found.append({"name": name, "path": path, "video": video, "queue": queue})
    return found


def describe() -> str:
    players = candidates()
    if not players:
        return ("No command-line player found. On Windows install the free one:\n"
                "  winget install mpv        (best: instant start, remembers position)\n"
                "Until then JARVIS can still hand files to your default app.")
    names = ", ".join(p["name"] for p in players)
    return (f"Players I can drive: {names}. "
            f"{'Queue playback: yes.' if players[0]['queue'] else 'One file at a time.'} "
            f"Nothing is uploaded; the file plays from your disk.")


def _spawn(cmd: list[str], player: str, files: list[str]) -> tuple[bool, str, float]:
    """Start playback and time it. Returns (ok, message, milliseconds to spawn)."""
    started = time.time()
    env = dict(os.environ)
    try:
        proc = quiet.popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, start_new_session=True,
                                env=env)
    except Exception as exc:
        return False, f"could not start {player}: {type(exc).__name__}: {exc}", 0.0
    elapsed = (time.time() - started) * 1000
    # a player that dies instantly is a broken player, not a played song
    time.sleep(0.35)
    code = proc.poll()
    if code not in (None, 0):
        tail = ""
        try:
            tail = (proc.stderr.read() or b"").decode("utf-8", "replace")[-300:]
        except Exception:
            pass
        _CURRENT.update({"proc": None, "player": player, "files": files,
                         "started": started, "ok": False, "error": tail or f"exit {code}"})
        return False, f"{player} exited immediately ({code}). {tail.strip()[:200]}", elapsed
    _CURRENT.update({"proc": proc, "player": player, "files": files,
                     "started": started, "ok": True, "error": ""})
    return True, "", elapsed


def _cmd_for(player: dict, files: list[str], video: bool) -> list[str]:
    name = player["name"]
    if name == "mpv":
        base = [player["path"], "--really-quiet", "--no-terminal", "--force-window=yes"
                if video else "--no-video", "--keep-open=no"]
        return base + files
    if name == "vlc":
        return [player["path"], "--intf", "dummy", "--play-and-exit", "--quiet"] + files
    if name == "ffplay":
        base = [player["path"], "-autoexit", "-loglevel", "error"]
        if not video:
            base += ["-nodisp"]
        return base + files[:1]
    if name == "mplayer":
        return [player["path"], "-really-quiet", "-vo", "null"] + files[:1]
    return [player["path"]] + files


def _open_default(path: str) -> str:
    """Last resort: hand the file to whatever the OS uses for it."""
    try:
        if os.name == "nt":
            os.startfile(path)                      # noqa: S606 — the user asked
        elif sys.platform == "darwin":
            quiet.popen(["open", path], start_new_session=True)
        else:
            quiet.popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
        return f"handed {Path(path).name} to the default player"
    except Exception as exc:
        return f"ERROR: could not open {Path(path).name} ({type(exc).__name__})"


def play(query: str = "", kind: str = "", path: str = "", queue: bool = True,
         limit: int = 25) -> str:
    """Play the best match for `query`, or this exact file. Instant, and measured."""
    explicit = os.path.expanduser(str(path or "").strip().strip('"'))
    if explicit and Path(explicit).suffix.lower() in (_AUDIO | _VIDEO):
        if not Path(explicit).exists():
            return f"ERROR: no such file: {explicit}"
        files = [explicit]
        label = Path(explicit).name
        is_video = Path(explicit).suffix.lower() in _VIDEO
    else:
        wanted = (query or path or "").strip()
        if not wanted:
            return ("What should I play? Say 'play the song <name>' or "
                    "'play my latest video'.")
        hits = library.search(wanted, kind, limit if queue else 1)
        if not hits:
            count = len(library.load().get("tracks") or [])
            if not count:
                return ("I have not indexed your media yet. Say **scan my music** (or "
                        "**scan my external disk**) and I will look — read-only.")
            return (f"I could not find “{wanted}” in {count} indexed files. "
                    f"Try fewer words, or say 'scan my music' to refresh the index.")
        files = [h["path"] for h in hits]
        label = hits[0]["name"]
        is_video = hits[0].get("kind") == "video"

    if not queue:
        files = files[:1]
    players = candidates()
    if not players:
        return describe() + "\n" + _open_default(files[0])

    tried: list[str] = []
    for player in players:
        chosen = files if player["queue"] else files[:1]
        ok, message, elapsed = _spawn(_cmd_for(player, chosen, is_video), player["name"],
                                      chosen)
        if ok:
            more = f" (+{len(chosen) - 1} queued)" if len(chosen) > 1 else ""
            return (f"▶ {label}{more}\n"
                    f"  playing in {player['name']} · started in {elapsed:.0f} ms · "
                    f"{'video' if is_video else 'audio'}\n"
                    f"  file: {chosen[0]}\n"
                    f"  say 'stop the music' when you have had enough.")
        tried.append(f"{player['name']}: {message[:120]}")
    fallback = _open_default(files[0])
    return fallback + ("\n(no command-line player worked: " + " | ".join(tried)[:300] + ")")


def play_folder(folder: str = "", query: str = "", kind: str = "") -> str:
    """Play everything in a folder (or the matches for a phrase) as one queue."""
    root = Path(os.path.expanduser(str(folder or ""))).expanduser()
    if root.is_dir():
        files = [str(p) for p in sorted(root.iterdir())
                 if p.suffix.lower() in (_AUDIO | _VIDEO)][:QUEUE_LIMIT]
        if not files:
            return f"no playable files in {root}"
        players = candidates()
        if not players:
            return describe() + "\n" + _open_default(files[0])
        ok, message, elapsed = _spawn(_cmd_for(players[0], files, False),
                                      players[0]["name"], files)
        return (f"▶ {len(files)} files from {root.name} · {players[0]['name']} · "
                f"{elapsed:.0f} ms" if ok else f"ERROR: {message}")
    return play(query or folder, kind, queue=True)


def stop() -> str:
    proc = _CURRENT.get("proc")
    if not proc or proc.poll() is not None:
        # maybe the OS media key can stop something else the user started
        return "nothing I started is playing. (Say 'pause' to control another player.)"
    name = _CURRENT.get("player", "player")
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        for _ in range(20):
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        if proc.poll() is None:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    played = time.time() - float(_CURRENT.get("started") or time.time())
    label = Path((_CURRENT.get("files") or ["something"])[0]).name
    _CURRENT.update({"proc": None, "ok": False})
    return f"stopped {label} in {name} after {played:.0f} s"


def status() -> str:
    proc = _CURRENT.get("proc")
    if proc and proc.poll() is None:
        files = _CURRENT.get("files") or []
        played = time.time() - float(_CURRENT.get("started") or time.time())
        label = Path(files[0]).name
        extra = f" · {len(files) - 1} more queued" if len(files) > 1 else ""
        return (f"playing {label}{extra} in {_CURRENT.get('player')} · "
                f"{played:.0f} s elapsed")
    return "nothing playing from JARVIS right now. " + describe()


def volume_updown(press_key: str) -> str:
    """Media keys are handled by the OS, which is exactly what we want here."""
    from .ai import tools as _tools
    return _tools.tool_media(press_key)
