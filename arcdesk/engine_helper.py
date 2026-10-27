"""An engine download that does not live or die with the window.

The report, three times now: *"enakku ithula download aaga matiku and again antha circel
desktop la vanthu hang aagi struck aaiduthu"*. Two symptoms, one shape: the download runs
**inside** the window's process, so anything that stops the window — a native library, a
closed lid, a person pressing the X because the screen stopped moving — also stops the
1.5 GB that was already half-way there. That is the wrong place for it.

So the download moves out:

    helper_start(engine)   -> spawns `tools/engine_get.py install <engine> --progress-file …`
                              DETACHED, no console, no parent link: it keeps going when the
                              window closes, crashes, or is killed
    helper_status(engine)  -> reads the small JSON it writes (stage, %, MB, speed, ETA,
                              done, why) — a file read, safe on the drawing thread
    helper_stop(engine)    -> writes a cancel file that the helper polls; politely stops

The JSON is written atomically (tmp + replace) so a reader never sees half a file, and it
carries the last few log lines so the dialog can show real output, not a spinner.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _folder() -> Path:
    from . import config
    d = config.data_dir() / "engine-install"
    d.mkdir(parents=True, exist_ok=True)
    return d


def progress_path(engine: str) -> Path:
    return _folder() / f"{engine}.json"


def log_path(engine: str) -> Path:
    return _folder() / f"{engine}.log"


def cancel_path(engine: str) -> Path:
    return _folder() / f"{engine}.stop"


def _python() -> str:
    """The interpreter that runs the helper: this app's own, unless it is a frozen build."""
    exe = sys.executable or ""
    if getattr(sys, "frozen", False) or not exe:
        from . import engines
        return engines.external_python() or exe
    return exe


def script() -> Path:
    from . import engines
    return engines.script_path("engine_get.py")


def available() -> tuple[bool, str]:
    """Can a download be started in the background on this machine? (bool, why not)."""
    if not script().is_file():
        return False, f"{script().name} is missing from this app"
    if not _python():
        return False, "no Python on this computer to run the download with"
    return True, ""


def running(engine: str) -> bool:
    """True while a helper for this engine is alive (a stale file is not 'running')."""
    data = read(engine)
    if not data:
        return False
    if data.get("done"):
        return False
    pid = int(data.get("pid") or 0)
    return bool(pid) and _alive(pid)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            from . import quiet
            got = quiet.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                            capture_output=True, text=True, timeout=10)
            return str(pid) in (got.stdout or "")
        except Exception:                                        # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:                                            # noqa: BLE001
        return False


def read(engine: str) -> dict:
    """The last thing the helper wrote, or {} when it has not written anything yet."""
    path = progress_path(engine)
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:                                            # noqa: BLE001
        return {}


def recent_lines(engine: str, count: int = 6) -> list[str]:
    try:
        path = log_path(engine)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return [ln for ln in lines if ln.strip()][-count:]
    except Exception:                                            # noqa: BLE001
        return []


def start(engine: str, lang: str = "", argv: list[str] | None = None) -> dict:
    """Start the download in its own process. Returns {ok, pid, why}.

    `argv` is for the tests: they run a ten-line stand-in that writes the same JSON, so the
    detach/read/stop contract is checked in a second instead of behind a 1.5 GB download.
    """
    can, why = available()
    if not can:
        return {"ok": False, "pid": 0, "why": why}
    if running(engine):
        return {"ok": True, "pid": int(read(engine).get("pid") or 0),
                "why": "already running"}
    try:
        cancel_path(engine).unlink()                    # a previous Stop must not apply
    except Exception:                                            # noqa: BLE001
        pass
    if argv is None:
        argv = [_python(), str(script()), "install", engine,
                "--progress-file", str(progress_path(engine))]
        if lang:
            argv += ["--lang", lang]
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "stdin": subprocess.DEVNULL, "close_fds": True}
    if sys.platform == "win32":
        # fully detached: no console window, and the child is not in this process's job
        # group, so closing the window does not take the download with it
        flags = 0
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs["start_new_session"] = True
    try:
        from . import quiet
        proc = quiet.popen(argv, **kwargs)
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "pid": 0, "why": f"could not start the download: {exc}"}
    try:
        progress_path(engine).write_text(json.dumps({
            "pid": proc.pid, "stage": "starting", "percent": 0.0, "done": False,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "engine": engine,
        }), encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass
    return {"ok": True, "pid": proc.pid, "why": ""}


def stop(engine: str, wait: float = 6.0) -> dict:
    """Ask the helper to stop (it polls this file), then make sure it is gone."""
    data = read(engine)
    pid = int(data.get("pid") or 0)
    try:
        cancel_path(engine).parent.mkdir(parents=True, exist_ok=True)
        cancel_path(engine).write_text("stop\n", encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass
    deadline = time.monotonic() + max(1.0, wait)
    while time.monotonic() < deadline and pid and _alive(pid):
        time.sleep(0.2)
    killed = False
    if pid and _alive(pid):
        try:
            if sys.platform == "win32":
                from . import quiet
                quiet.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True,
                          timeout=15)
            else:
                os.kill(pid, 15)
            killed = True
        except Exception:                                        # noqa: BLE001
            pass
    return {"ok": not (pid and _alive(pid)), "killed": killed}
