"""Is JARVIS up — and if not, *why not*? The launcher's honest half.

The report that built this file, for the fifth time:

    "jarvis.bat double click pana open aaguthu terminal then jarvis run aaga matiku machi"

A terminal appears, then nothing. Four separate ways that happens, and the launcher used
to be unable to tell them apart:

1. **It starts, crashes, and the console goes with it.** `pythonw.exe` has no console, so
   the traceback goes to a log nobody reads, and the window that was showing the problem
   closes. This file prints the tail of that log, in the launcher's own window, while the
   window is still open.
2. **Another copy is already running** — usually the hidden one Windows started at login.
   The launcher said "already running, brought it to the front" after *sending* a message;
   it never checked that a window appeared. Now a wake must be **acknowledged** by the
   running app (`instance.ask`), and the launcher waits for the app's own log line
   (`WAKE · the window is in front`) before calling it done.
3. **The window is up but empty** — the arrival cinematic hides the real window and, when
   the clip cannot draw, shows nothing at all. `summon()` now shows a plain window.
4. **A dependency is broken** — an engine install half-finished, PySide6 upgraded under
   it, `.venv` built by a different Python. Preflight checks the things that actually
   stop the app from importing, and says which one, in one line each.

Everything here is a plain function so it can be tested without Windows, without a GUI,
and without starting anything: the CLI wrapper is `tools/launch.py`.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The two lines that prove a window exists. Written by the app itself, on the GUI thread,
# after `show()` — the only honest proof available from outside the process.
# Only lines that mean "a window is on the screen". The stealth line
# (`BOOT · stealth: the window is not shown`) used to be in this tuple — it says the exact
# opposite, and it is written at every login by the copy Windows starts in the background,
# so a launcher waiting for a window would have been told "yes" by the line that says "no".
SHOWN_MARKS = (
    "BOOT · the window is shown",
    "WAKE · the window is in front",
)


# ------------------------------------------------------------------ interpreters
def app_python(root: Path | None = None) -> Path:
    """The interpreter the app should run under: the private venv's, if it exists."""
    root = Path(root or ROOT)
    for name in ("pythonw.exe", "python.exe", "python3", "python"):
        for folder in (root / ".venv" / "Scripts", root / ".venv" / "bin"):
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return Path(sys.executable)


def console_python(root: Path | None = None) -> Path:
    """The same environment, but with a console — used to run checks and print things."""
    root = Path(root or ROOT)
    for folder in (root / ".venv" / "Scripts", root / ".venv" / "bin"):
        for name in ("python.exe", "python3", "python"):
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return Path(sys.executable)


def launch_argv(root: Path | None = None, show: bool = True) -> list[str]:
    """How the launcher starts the app. Never `--shadow`: a double-click means a person."""
    root = Path(root or ROOT)
    python = app_python(root)
    if python.name.lower() == "python.exe" and os.name == "nt":
        windowless = python.with_name("pythonw.exe")
        if windowless.is_file():
            python = windowless
    argv = [str(python), str(root / "run.py")]
    if show:
        argv.append("--show")
    return argv


# ------------------------------------------------------- repairing, not advising
def repair_argv(root: Path | None = None) -> list[str]:
    """The exact command that puts the libraries back, in the app's own environment.

    The rule this keeps: **never tell the person to run something the app can run.** A
    half-finished voice-engine install can take PySide6 with it (it pins torch, which can
    pin an older typing-extensions), and the app then dies before it can draw anything.
    Printing "run pip install" over an empty screen is not a fix.
    """
    root = Path(root or ROOT)
    return [str(console_python(root)), "-m", "pip", "install", "--upgrade",
            "--no-input", "-r", str(root / "requirements.txt")]


def pip_fixable(checks: list[dict]) -> bool:
    """True when the failures are the kind pip can actually repair."""
    names = " ".join(c["name"] for c in checks if not c["ok"])
    return any(word in names for word in ("PySide6", "psutil", "imports"))


def spawn_log() -> Path:
    """Where the started app's own stdout/stderr goes.

    `pythonw.exe` has no console and no stderr: without this file, a crash before logging
    is set up leaves absolutely nothing behind — which is what "nothing happens" looks
    like from the outside.
    """
    folder = _data_dir() / "logs"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path(os.environ.get("TEMP", ".")) / "jarvis-spawn.log"
    return folder / "spawn.log"


def pid_file() -> Path:
    return spawn_log().with_name("launch.pid")


def remember_pid(pid: int) -> None:
    try:
        pid_file().write_text(str(int(pid)), encoding="utf-8")
    except OSError:
        pass


def read_pid() -> int:
    try:
        return int((pid_file().read_text(encoding="utf-8") or "0").strip() or 0)
    except (OSError, ValueError):
        return 0


def pid_alive(pid: int) -> bool:
    """Is that process still there? Cheap, and it makes a dead start instant to spot."""
    if pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except Exception:                                            # noqa: BLE001
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def spawn_text(lines: int = 25) -> str:
    """The tail of what the started process itself said (usually a traceback)."""
    try:
        text = spawn_log().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    rows = [row for row in text.splitlines() if row.strip()]
    return "\n".join(rows[-max(1, lines):])


# ------------------------------------------------------------------- log reading
def log_path() -> Path:
    from . import logs
    return logs.log_path()


def log_tail(lines: int = 14, path: Path | None = None) -> str:
    """The last lines the app wrote — the sentence the person actually needs."""
    target = Path(path) if path else log_path()
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    rows = [row for row in text.splitlines() if row.strip()]
    return "\n".join(rows[-max(1, lines):])


def window_mark_since(stamp: float, path: Path | None = None) -> str:
    """The first 'a window exists' line written at or after `stamp`, or ''."""
    target = Path(path) if path else log_path()
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for row in text.splitlines():
        if not any(mark in row for mark in SHOWN_MARKS):
            continue
        try:                                   # "2026-10-25 10:10:08 NOTE arcdesk  ..."
            when = time.mktime(time.strptime(row[:19], "%Y-%m-%d %H:%M:%S"))
        except (ValueError, OverflowError):
            continue
        if when >= stamp - 2:                  # two seconds of slack for clock granularity
            return row.strip()
    return ""


def log_offset() -> int:
    """How many bytes the log already holds — so a NEW line can be told from an old one.

    Time is not enough: two launches inside the same second, or a clock that jumps, and a
    launcher that greps by timestamp happily reports the previous run's window as this
    one's. The byte offset is exact.
    """
    try:
        return log_path().stat().st_size
    except OSError:
        return 0


def window_mark_from(offset: int, path: Path | None = None) -> str:
    """The first 'a window exists' line written after `offset` bytes, or ''."""
    target = Path(path) if path else log_path()
    try:
        with target.open("rb") as handle:
            handle.seek(max(0, int(offset)))
            fresh = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    for row in fresh.splitlines():
        if any(mark in row for mark in SHOWN_MARKS):
            return row.strip()
    return ""


def crash_reason(tail: str) -> str:
    """The most useful sentence in a log tail: the exception, if there is one."""
    keys = ("Traceback (most recent call last)", "Error", "error:", "CRASH ·",
            "ModuleNotFoundError", "ImportError", "DLL load failed")
    rows = [row for row in (tail or "").splitlines() if row.strip()]
    for row in reversed(rows):
        if any(key in row for key in keys):
            return row.strip()[:220]
    return rows[-1].strip()[:220] if rows else ""


# -------------------------------------------------------------------- preflight
def _check(name: str, ok: bool, detail: str = "", fix: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, "fix": fix}


def _run(python: Path, code: str, timeout: float = 25.0) -> tuple[int, str]:
    """Run a one-liner in that interpreter. Used only by the diagnostic command.

    Through `quiet`, not `subprocess`: this runs from a launcher that a person is looking
    at, and on Windows a bare spawn flashes a console window for every check.
    """
    from . import quiet
    try:
        proc = quiet.run([str(python), "-c", code], capture_output=True,
                         text=True, encoding="utf-8", errors="replace",
                         timeout=timeout)
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except Exception as exc:                                     # noqa: BLE001
        # TimeoutExpired, CalledProcessError, OSError — the class does not matter here;
        # one readable line does, because this is printed into a launcher window.
        return 1, f"{type(exc).__name__}: {exc}"


def preflight(root: Path | None = None) -> list[dict]:
    """The checks that separate "the app is broken" from "the window is behind something"."""
    root = Path(root or ROOT)
    checks: list[dict] = []

    checks.append(_check("run.py is here", (root / "run.py").is_file(),
                         str(root / "run.py"),
                         "unzip the whole JARVIS folder again — this is not the app folder"))

    venv = app_python(root)
    checks.append(_check("a Python to run it", venv.is_file() or venv == Path(sys.executable),
                         str(venv),
                         "double-click JARVIS.bat again; it builds .venv itself"))

    checks.append(_check("settings folder is writable", _writable(root),
                         str(_data_dir()),
                         "check the folder permissions, or set ARCDESK_HOME somewhere else"))

    # The interpreter that will really run the app — the private .venv when it exists,
    # otherwise whatever Python we are. Testing the wrong one is how "it works here but
    # not there" happens.
    code, out = _run(venv, "import PySide6; print(PySide6.__version__)")
    # A silent interpreter is its own diagnosis: "no output" means it died before it could
    # even say why, which is a different problem from "module not found".
    out = out or ("(that Python printed nothing and exited with %d)" % code)
    checks.append(_check("PySide6 imports in that Python", code == 0, out,
                         "run: .venv\\Scripts\\python.exe -m pip install -r "
                         "requirements.txt"))
    code2, out2 = _run(venv, "import psutil; print(psutil.__version__)")
    out2 = out2 or ("(that Python printed nothing and exited with %d)" % code2)
    checks.append(_check("psutil imports in that Python", code2 == 0, out2,
                         "same: reinstall from requirements.txt"))

    checks.append(_check("the log can be written", _log_ok(), str(log_path()),
                         "check free space on C:, and that %APPDATA% is not read-only"))
    return checks


def _data_dir() -> Path:
    try:
        from . import config
        return config.data_dir()
    except Exception:                                            # noqa: BLE001
        return Path(os.environ.get("ARCDESK_HOME") or Path.home() / ".arcdesk")


def _writable(root: Path) -> bool:
    try:
        folder = _data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _log_ok() -> bool:
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("")
        return True
    except OSError:
        return False


# ------------------------------------------------------------------- diagnosis
def whose_fault(checks: list[dict], state: dict | None = None) -> str:
    """One sentence: "broken install" / "already running" / "started then died" / "fine"."""
    failed = [c for c in checks if not c["ok"]]
    if failed:
        return "broken install"
    state = state or {}
    if state.get("live"):
        return "already running"
    if state.get("stale_pids"):
        return "a stuck copy is in the way"
    if state.get("started"):
        return "started, then closed itself"
    return "fine"


def diagnose(root: Path | None = None, state: dict | None = None,
             lines: int = 14) -> dict:
    """The whole picture, for one screen of output."""
    checks = preflight(root)
    tail = log_tail(lines)
    failed = [c for c in checks if not c["ok"]]
    return {
        "ok": not failed,
        "fault": whose_fault(checks, state),
        "checks": checks,
        "tail": tail,
        "reason": crash_reason(tail),
        "advice": [c["fix"] for c in failed if c["fix"]],
    }


def wait_for_window(since: float, timeout: float = 25.0, out=None,
                    step: float = 1.0, path: Path | None = None,
                    offset: int | None = None) -> dict:
    """Wait for the app's own "a window exists" line, saying something every second.

    The silent version of this loop is why a launcher looked dead: thirty seconds of a
    blinking cursor and then either a happy message or a log dump.
    """
    started = time.time()
    elapsed = 0.0
    while elapsed <= timeout:
        mark = (window_mark_from(offset, path) if offset is not None
                else window_mark_since(since, path))
        if mark:
            return {"ok": True, "mark": mark, "seconds": round(time.time() - started, 1)}
        if out is not None:
            out(f"   … still waiting for the window  ({int(elapsed)} s of "
                f"{int(timeout)} s)")
        time.sleep(step)
        elapsed = time.time() - started
    return {"ok": False, "mark": "", "seconds": round(time.time() - started, 1)}


def numbers(checks: list[dict]) -> list[str]:
    """The report as numbered lines — what a person can read and act on."""
    rows = []
    for index, check in enumerate(checks, start=1):
        mark = "PASS" if check["ok"] else "FAIL"
        line = f"  {index:>2}. [{mark}] {check['name']}"
        if check["detail"]:
            line += f"  —  {check['detail']}"
        rows.append(line)
    return rows
