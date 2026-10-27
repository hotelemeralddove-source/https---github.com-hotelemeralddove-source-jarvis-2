"""The crash log, and the one place a windowless app is allowed to say things.

Two jobs, both about a program with no console:

**A log file.** Crashes, Qt warnings and anything logged through `logging` go to
`%APPDATA%\\ArcDesk\\logs\\arcdesk.log`, rotated at 512 KB to one `.1` file, with **API
keys scrubbed** before they are written (`sk-…` → `sk-***`). A log that quietly records
the user's key is worse than no log at all: the first thing anyone does with a crash log
is paste it into a chat window.

**Somewhere for `print()` to go.** `pythonw.exe` — how Windows runs a `.pyw`, how the
Startup shortcut launches ARC, and effectively what the installed exe is
(`console=False`) — hands the process `sys.stdout = None`. The first `print()` then
raises `AttributeError: 'NoneType' object has no attribute 'write'`, so a windowless app
that prints anything dies with nothing on screen and nothing written: the worst kind of
failure. `ensure_streams()` points both streams at the log before anything can print.

Callers:
    run.py            install()      then install_qt()       (boot)
    Settings          tail(200)                              (Open log)
    the holo screen   tail(3)                                (recent events)
    tools/doctor.py   errors(3), log_path()                  (crash-log check)
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import threading
import time
from pathlib import Path

MAX_BYTES = 512 * 1024
BACKUPS = 1
FORMAT = "%(asctime)s %(levelname)-7s %(name)-14s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_redirected: Path | None = None
_installed: Path | None = None
_lock = threading.Lock()

#: Anything that looks like a credential, and what to write instead. Order matters:
#: the specific shapes first, so `sk-ant-…` does not fall through to the generic rule.
_SCRUB = (
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "sk-ant-***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{6,}"), "sk-***"),
    (re.compile(r"gsk_[A-Za-z0-9_\-]{6,}"), "gsk_***"),
    (re.compile(r"AIza[A-Za-z0-9_\-]{10,}"), "AIza***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer ***"),
    (re.compile(r"(?i)(api[_-]?key[\"'\s:=]+)[A-Za-z0-9._\-]{8,}"), r"\1***"),
    (re.compile(r"(?i)(token[\"'\s:=]+)[A-Za-z0-9._\-]{12,}"), r"\1***"),
)


def scrub(text: str) -> str:
    """Replace anything that looks like a key. Never raises, never half-scrubs."""
    out = str(text)
    for pattern, replacement in _SCRUB:
        out = pattern.sub(replacement, out)
    return out


class _ScrubFilter(logging.Filter):
    """Scrub on the way into the file, so nothing above this layer has to remember."""

    def filter(self, record: logging.LogRecord) -> bool:      # noqa: A003
        try:
            record.msg = scrub(record.getMessage())
            record.args = None
        except Exception:                                     # noqa: BLE001
            pass
        return True


#: Marks "this app is running right now". If the file is still here next time, the last
#: session did not end the way it should have — which is exactly what "application auto
#: close aaguthu" looks like from the outside, and it is worth saying out loud.
_SESSION = "session.json"


def session_path() -> Path:
    return log_path().parent.parent / _SESSION


def fault_path() -> Path:
    return log_path().parent / "fault.log"


def watch_crashes() -> None:
    """Catch the crashes Python cannot: segfaults and native aborts (faulthandler).

    An import that pulls a clashing native library kills the process before any `except`
    runs, so `sys.excepthook` never fires and the log stays silent. faulthandler writes
    the Python stack straight to a file at the moment of death, which is the only way to
    know which import did it.
    """
    try:
        import faulthandler
        handle = open(fault_path(), "a", encoding="utf-8")        # noqa: SIM115
        faulthandler.enable(file=handle, all_threads=True)
        setattr(sys, "_arcdesk_fault_file", handle)
    except Exception:                                            # noqa: BLE001
        pass


#: True when the last session was judged unclean because OUR launcher closed it.
last_session_was_launcher_stop = False


def _launcher_stop() -> dict:
    """The launcher's kill record, if a kill happened in the last half hour."""
    try:
        import json
        path = log_path().parent / "launcher-stop.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        if time.time() - float(data.get("ts", 0)) > 1800:
            return {}
        return data
    except Exception:                                            # noqa: BLE001
        return {}


def begin_session() -> str:
    """Write the marker. Returns a note when the PREVIOUS run ended badly ('' if not)."""
    global last_session_was_launcher_stop
    note = ""
    path = session_path()
    try:
        import json
        old = {}
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8") or "{}")
            except Exception:                                    # noqa: BLE001
                old = {}
        old_streak = 0
        level = "warning"
        last_session_was_launcher_stop = False
        if old and not old.get("clean", False):
            stop = _launcher_stop()
            if str(old.get("pid", "?")) in {str(x) for x in stop.get("pids", [])}:
                # The launcher closed it: a double-click that found the app already
                # running (or a frozen one the fresh copy replaced). That is an
                # action, and it must not scare the person or feed the safe counter.
                last_session_was_launcher_stop = True
                note = (f"last time the launcher closed JARVIS at "
                        f"{stop.get('at', '?')} (a double-click while it was already "
                        f"running) — that is expected, not a crash")
                old_streak = 0
                level = "info"
            else:
                note = (f"last time JARVIS stopped without closing properly (started "
                        f"{old.get('started', '?')}, pid {old.get('pid', '?')}). That is the "
                        f"moment that needs explaining — see the log, and fault.log next to it")
                try:
                    old_streak = int(old.get("crash_streak", 1)) + 1
                except Exception:                                # noqa: BLE001
                    old_streak = 2
        import datetime as _dt
        import os as _os
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "pid": _os.getpid(),
            "started": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "clean": False,
            "version": "",
            "crash_streak": old_streak if note else 0,
        }), encoding="utf-8")
        if note:
            getattr(logging.getLogger("arcdesk.crash"), level)("previous session: %s", note)
    except Exception:                                            # noqa: BLE001
        pass
    return note


def crash_streak() -> int:
    """How many runs in a row ended without closing (0 = the last one was clean)."""
    try:
        import json
        path = session_path()
        if not path.exists():
            return 0
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        return int(data.get("crash_streak", 0) or 0)
    except Exception:                                            # noqa: BLE001
        return 0


def env_line() -> str:
    """One line: the python, the Qt, and the machine the app was running on.

    A native crash leaves no traceback, and the one variable nobody used to know from
    the report was *which Qt* the machine had — the QThreadStorage heap-corruption bug
    lived in specific Qt versions only, so the report now says, up front, what died.
    """
    import platform
    parts = [f"python {sys.version.split()[0]}"]
    try:
        import PySide6
        from PySide6 import QtCore
        parts.append(f"PySide6 {PySide6.__version__} (Qt {QtCore.__version__})")
    except Exception:                                            # noqa: BLE001
        pass
    parts.append(platform.platform())
    return " · ".join(parts)


def crash_bundle() -> Path | None:
    """Write one file a person can send: what was happening before the app went away.

    The report this answers is "application crash aagi, close aaguthu" — and the honest
    answer is that a native crash leaves no traceback, so the only way to see it is to keep
    the last minute of the log and the fault log together, in the app folder, named plainly.
    """
    try:
        folder = log_path().parent
        out = folder.parent / "crash-report.txt"
        lines = ["JARVIS stopped unexpectedly — the last things it was doing",
                 "=" * 62, "",
                 "environment: " + env_line(), ""]
        for name in ("fault.log", "arcdesk.log"):
            f = folder / name
            if not f.exists():
                continue
            lines.append(f"--- {name} (last 60 lines) " + "-" * 30)
            try:
                tail = f.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
            except Exception:                                    # noqa: BLE001
                tail = ["(could not be read)"]
            lines.extend(tail)
            lines.append("")
        try:
            import json
            sp = session_path()
            if sp.exists():
                lines.append("--- last session marker " + "-" * 30)
                lines.append(sp.read_text(encoding="utf-8", errors="replace")[:600])
        except Exception:                                        # noqa: BLE001
            pass
        lines += ["", "What to do with this file: send it as it is. It contains no audio, "
                      "no passwords and no documents — only the log lines."]
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
    except Exception:                                            # noqa: BLE001
        return None


def end_session() -> None:
    """The app is closing because the person asked it to. Record that, so it is not a
    "crash" next time."""
    try:
        import json
        path = session_path()
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
            except Exception:                                    # noqa: BLE001
                data = {}
        data["clean"] = True
        data["crash_streak"] = 0
        import datetime as _dt
        data["ended"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass


def log_path() -> Path:
    """`%APPDATA%\\ArcDesk\\logs\\arcdesk.log` (or the sandbox's ARCDESK_HOME)."""
    base = os.environ.get("ARCDESK_HOME") or os.environ.get("APPDATA")
    folder = Path(base) / "ArcDesk" if base else Path.home() / ".arcdesk"
    (folder / "logs").mkdir(parents=True, exist_ok=True)
    return folder / "logs" / "arcdesk.log"


def install(level: int = logging.INFO) -> Path:
    """Start the rotating, scrubbing log. Returns its path. Safe to call twice."""
    global _installed
    path = log_path()
    with _lock:
        root = logging.getLogger()
        already = any(getattr(h, "_arcdesk_log", False) for h in root.handlers)
        if already and _installed == path:
            return path
        try:
            handler = logging.handlers.RotatingFileHandler(
                path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        except OSError:
            handler = logging.StreamHandler(open(os.devnull, "w"))   # noqa: SIM115
        handler.setFormatter(logging.Formatter(FORMAT, DATE_FORMAT))
        handler.addFilter(_ScrubFilter())
        handler._arcdesk_log = True                              # type: ignore[attr-defined]
        root.addHandler(handler)
        if root.level > level or root.level == logging.WARNING:
            root.setLevel(level)
        _installed = path

    # An uncaught error must leave a trace, even in a windowless build.
    def _hook(exc_type, exc, tb) -> None:
        try:
            logging.getLogger("arcdesk.crash").critical(
                "uncaught", exc_info=(exc_type, exc, tb))
        except Exception:                                        # noqa: BLE001
            pass

    def _thread_hook(args) -> None:
        try:
            logging.getLogger("arcdesk.crash").critical(
                "uncaught in thread %s", getattr(args.thread, "name", "?"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        except Exception:                                        # noqa: BLE001
            pass

    sys.excepthook = _hook
    try:
        threading.excepthook = _thread_hook
    except Exception:                                            # noqa: BLE001
        pass
    return path


def install_qt() -> None:
    """Send Qt's own warnings into the log instead of a console that does not exist."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:                                            # noqa: BLE001
        return
    log = logging.getLogger("qt")
    levels = {QtMsgType.QtDebugMsg: logging.DEBUG,
              QtMsgType.QtInfoMsg: logging.INFO,
              QtMsgType.QtWarningMsg: logging.WARNING,
              QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}

    #: Qt messages that are noise, not signal. The setGeometry one in particular fires
    #: every time a resizable dialog is dragged near a screen edge; Qt clamps the
    #: geometry itself (its own "Resulting geometry" half of the line says so), so the
    #: warning was filling the report with six copies of a warning and one line of the
    #: actual fault. DEBUG keeps it there when it ever matters.
    _NOISE = ("QWindowsWindow::setGeometry: Unable to set geometry",)

    def handler(mode, context, message) -> None:                 # noqa: ANN001
        try:
            level = levels.get(mode, logging.INFO)
            if level >= logging.WARNING and any(n in message for n in _NOISE):
                level = logging.DEBUG
            log.log(level, "%s", message)
        except Exception:                                        # noqa: BLE001
            pass

    try:
        qInstallMessageHandler(handler)
    except Exception:                                            # noqa: BLE001
        pass


def ensure_streams() -> Path | None:
    """Give a console-less process a real stdout/stderr. Safe to call repeatedly.

    Returns the log path when it redirected, or None when the process already had a
    console — running `python run.py` from a terminal should keep printing there, because
    a developer watching a terminal is not the same as a user staring at a black box.
    """
    global _redirected
    if sys.stdout is not None and sys.stderr is not None:
        return _redirected
    path = log_path()
    try:
        stream = open(path, "a", encoding="utf-8", buffering=1)   # noqa: SIM115
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")         # noqa: SIM115
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream
    _redirected = path
    try:
        print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ArcDesk start "
              f"(windowless: this is the console) ---", flush=True)
    except Exception:                                            # noqa: BLE001
        pass
    return _redirected


def note(message: str) -> None:
    """Write one line to the log, whether or not a console exists."""
    try:
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime(DATE_FORMAT)} {'NOTE':<7} arcdesk        "
                     f"{scrub(message)}\n")
    except Exception:                                            # noqa: BLE001
        pass


def tail(count: int = 200) -> list[str]:
    """The last `count` lines, newest last. Empty list when there is no log yet."""
    try:
        with open(log_path(), "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
        return [line.rstrip("\n") for line in lines[-max(1, int(count)):]]
    except OSError:
        return []


def errors(count: int = 3) -> list[str]:
    """The last `count` lines that were an ERROR or a CRITICAL, scrubbed already."""
    bad = [line for line in tail(2000)
           if " ERROR " in line or " CRITICAL " in line]
    return bad[-max(1, int(count)):]


def describe() -> str:
    """One line for the diagnostics page."""
    if _redirected is None:
        return "console output: this terminal (no log redirect needed)"
    return f"console output: windowless, so it goes to {_redirected}"
