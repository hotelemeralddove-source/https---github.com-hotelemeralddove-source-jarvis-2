"""Where things live — source checkout vs frozen .exe.

PyInstaller changes the rules: `sys.executable` is ArcDesk.exe and `__file__` lives
inside a temporary bundle, so any code that spawns a sibling process (the voice
daemon) has to resolve paths differently. Getting this wrong is the #1 reason a
packaged app "works on my machine" but not after install, so it is centralised.
"""
from __future__ import annotations

from . import quiet

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Folder the user sees: build/dist/ArcDesk/ when frozen, repo root in source."""
    if FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundle_root() -> Path:
    """Where bundled data files actually are.

    onefile  -> sys._MEIPASS
    onedir   -> <exe folder>/_internal   (PyInstaller 6 layout)
    source   -> the arcdesk package folder
    """
    if FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return app_dir() / "_internal"
    return Path(__file__).resolve().parent


def page(name: str) -> Path | None:
    """Find a bundled HTML page (TOOLS_PAGE.html and friends), or None.

    Returns None instead of raising: a missing page is a one-line note in the console,
    not a crash on a menu click.
    """
    for candidate in (bundle_root() / "arcdesk" / name, bundle_root() / name,
                      app_dir() / name, app_dir() / "arcdesk" / name):
        if candidate.is_file():
            return candidate
    return None


def runtime_dirs() -> list[Path]:
    """Extra binaries that ship INSIDE the install, so the user never sets a PATH.

    The one-click installer puts portable ffmpeg and Node here:

        <app>/runtime/ffmpeg/ffmpeg.exe
        <app>/runtime/node/node.exe

    In a source checkout the same folders work if you drop them in, which is how the
    bundling can be tested without building an exe.
    """
    base = app_dir() / "runtime"
    return [base / "ffmpeg", base / "node", base / "python", base]


def activate_runtime() -> list[str]:
    """Prepend the bundled runtimes to this process's PATH. Returns what was found.

    Called once at startup. Every existing subprocess call (ffmpeg, node, npx, uvx)
    then finds the bundled copy first, with no user configuration at all. Nothing is
    written to the system PATH or to the registry — this is the process environment
    only, so uninstalling leaves Windows exactly as it was.
    """
    found: list[str] = []
    for d in runtime_dirs():
        if not d.is_dir():
            continue
        exe = {"ffmpeg": "ffmpeg.exe", "node": "node.exe", "python": "python.exe"}
        if any((d / name).exists() for name in exe.values()) or any(d.glob("*.exe")):
            if str(d) not in os.environ.get("PATH", ""):
                os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
            found.append(str(d))
    return found


def which(name: str) -> str:
    """Where a tool would be found right now (bundled or system), or ''."""
    import shutil as _shutil
    return _shutil.which(name) or ""


def daemon_command(port: int, phrase: str, engine: str = "auto",
                   exit_phrase: str = "bye jarvis",
                   launcher_app: str | None = None,
                   extra: list[str] | None = None) -> tuple[list[str], dict]:
    """Return (argv, popen_kwargs) for the voice daemon, frozen or not.

    Frozen  : ArcDeskVoice.exe sits next to ArcDesk.exe
    Source  : python arc_daemon.py, hidden console on Windows
    """
    args = ["--port", str(port), "--phrase", phrase, "--engine", engine,
            "--exit-phrase", exit_phrase]
    if launcher_app:
        args += ["--launcher-app", launcher_app]
    if extra:
        args += extra

    # One rule for every child, in one place: no console window, ever. `detached=True`
    # also takes the daemon out of the caller's job object, so closing the app's
    # launcher cannot kill the ears mid-sentence.
    spawn = quiet.kwargs(detached=True)

    if FROZEN:
        voice = app_dir() / "ArcDeskVoice.exe"
        alt = app_dir() / "ArcDeskVoice"                # extensionless fallback
        if not voice.exists() and alt.exists():
            voice = alt
        return [str(voice), *args], spawn

    script = app_dir() / "arc_daemon.py"
    return [sys.executable, str(script), *args], spawn


def app_command(show: bool = True, shadow: bool = False) -> list[str]:
    """Command that starts the main app (used by the daemon's launcher mode)."""
    if FROZEN:
        exe = Path(sys.executable)
        return [str(exe)] + (["--show"] if show else (["--shadow"] if shadow else []))
    return [sys.executable, str(app_dir() / "run.py")] + \
           (["--show"] if show else (["--shadow"] if shadow else []))
