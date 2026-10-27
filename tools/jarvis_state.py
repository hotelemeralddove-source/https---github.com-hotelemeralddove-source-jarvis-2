"""Is JARVIS running — and is it *this* JARVIS?

The report: *"jarvis.bat ah close pana ithuku munnadi app open aachu ipo open aagala"*.
JARVIS.bat used to decide with

    tasklist /FI "IMAGENAME eq pythonw.exe" | find /I "pythonw.exe"

which answers "is ANY pythonw.exe on this PC alive?" — a different app, a leftover from a
run that never died, anything. When the answer was yes the launcher printed "already
running - nothing to start" and started nothing, so the window never came back.

This tool answers the question properly, and from three angles:

  * **live** — the app's own single-instance socket on 127.0.0.1 answers. That is the only
    proof a *working* JARVIS is there, because it must be inside the running process.
  * **pids** — the command lines of this PC's python processes, filtered to this project's
    `run.py`. Not every pythonw: ours.
  * **wake** — ask the live one to show itself, which is what a person double-clicking a
    launcher actually wants.

So the launcher can now: wake it (there it is), or kill *only* a stale one of ours and
start fresh — and it can never again silently start nothing.

    python tools/jarvis_state.py --where       # the folder the running app started from
    python tools/jarvis_state.py --status      # 0 live, 2 running but not answering, 1 not
    python tools/jarvis_state.py --wake        # 0 if a live app was brought to the front
    python tools/jarvis_state.py --pids        # one pid per line (nothing if none)
    python tools/jarvis_state.py --kill-stale  # kill ours that do not answer the socket
    python tools/jarvis_state.py --kill-foreign # kill copies from ANOTHER folder (zoo)
    python tools/jarvis_state.py --stop        # kill ours, healthy or not (updater)
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "run.py"


def _bootstrap() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def lock_port() -> int:
    """The port to ask: what the running copy recorded, else what settings say.

    `recorded_port()` is a file the app writes when it takes the lock and deletes when it
    lets go, so this is the app's own answer rather than a guess from a config file that
    might belong to a different profile.
    """
    _bootstrap()
    try:
        from arcdesk import config
        from arcdesk.instance import lock_port as _lp, recorded_port
        return int(recorded_port() or _lp(config.load()))
    except Exception:                                            # noqa: BLE001
        return 8766


def candidate_ports() -> list[int]:
    """Every port worth trying, best first — recorded, configured, then the defaults."""
    _bootstrap()
    seen: list[int] = []
    try:
        from arcdesk import config
        from arcdesk.instance import lock_port as _lp, recorded_port
        cfg = config.load()
        for value in (recorded_port(), _lp(cfg), 8766, 8992):
            value = int(value or 0)
            if value and value not in seen:
                seen.append(value)
    except Exception:                                            # noqa: BLE001
        seen = [8766]
    return seen


def wake(timeout: float = 2.0) -> bool:
    """Ask the live app to show itself. True only when the app ANSWERED.

    Sending is not success. The old version returned True the moment the bytes left, so
    JARVIS.bat printed "already running — brought it to the front" while the desktop
    stayed empty: the app was alive, the message was accepted, and nothing happened.
    `instance.ask` waits for the app's own reply, so this is now a fact.
    """
    try:
        from arcdesk.instance import ask
    except Exception:                                            # noqa: BLE001
        ask = None
    payload = json.dumps({"event": "wake", "from": "launcher"}).encode("utf-8") + b"\n"
    for port in candidate_ports():
        if ask is not None:
            got = ask(port, connect=timeout, wait=timeout + 1.0)
            if got.get("ack"):
                return True
            continue
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
                sock.sendall(payload)
            return True
        except OSError:
            continue
    return False


def live() -> bool:
    """Is a working app on a lock port? Touching it is enough — no wake needed."""
    for port in candidate_ports():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.5):
                return True
        except OSError:
            continue
    return False


def parse_pids(text: str) -> list[int]:
    """PowerShell/wmic output -> pids. Kept separate so it can be tested anywhere."""
    out: list[int] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.isdigit() and int(line) not in out and int(line) != os.getpid():
            out.append(int(line))
    return out


def script_path() -> str:
    """The one command line that means *this* app: <project>/run.py."""
    return str(ROOT / MARKER)


def _ps_query() -> str:
    script = script_path().replace("'", "''")
    return ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" "
            "| Where-Object { $_.CommandLine -like '*" + script + "*' } "
            "| Select-Object -ExpandProperty ProcessId")


def _proc_query() -> list[int]:
    """/proc fallback — the same question, asked without PowerShell (used by the tests)."""
    found: list[int] = []
    base = Path("/proc")
    if not base.exists():
        return found
    here = {os.getpid(), os.getppid()}
    for entry in base.glob("[0-9]*"):
        if int(entry.name) in here:
            continue
        try:
            cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8",
                                                                              "replace")
            comm = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        # It must really be a python running one of these two things: the script by its
        # full path, or anything started by *this* project's own interpreter (a launcher
        # may pass a relative "run.py", and the exe path still gives it away). A shell
        # whose command line merely mentions run.py is not the app.
        if not comm.startswith("python"):
            continue
        own_exe = str(ROOT / ".venv")
        named = script_path() in cmd or (own_exe in cmd and MARKER in cmd)
        if named:
            try:
                found.append(int(entry.name))
            except ValueError:
                continue
    return [p for p in found if p != os.getpid()]


def pids() -> list[int]:
    """PIDs of this project's own python processes. Empty when it is not running."""
    if sys.platform != "win32":
        return _proc_query()
    try:
        got = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              _ps_query()], capture_output=True, text=True, timeout=30)
    except Exception:                                            # noqa: BLE001
        return []
    return parse_pids(got.stdout)


def project_from_cmdline(cmd: str) -> str:
    """The project folder a command line points at ('' when it is not ours).

    Pure, so it can be tested on any OS:
        "C:\\...\\JARVIS\\.venv\\Scripts\\pythonw.exe" "C:\\...\\JARVIS\\run.py" --shadow
        -> C:\\...\\JARVIS
    It takes the LAST "run.py" in the line and the folder written right before it, which
    works for a quoted path (Windows always quotes a path with spaces) and for a plain
    one.
    """
    text = (cmd or "").strip()
    if MARKER not in text:
        return ""
    head = text[:text.rfind(MARKER)]
    head = head.rstrip(" \t\r\n\"'")
    if head.endswith(("\\", "/")):
        head = head[:-1]
    if '"' in head or "'" in head:
        cut = max(head.rfind('"'), head.rfind("'"))
        head = head[cut + 1:]
    else:
        parts = head.split()
        head = parts[-1] if parts else ""
    head = head.rstrip(" \t\r\n\"'")
    if head.endswith(("\\", "/")):
        head = head[:-1]
    return head


def running_project() -> str:
    """The folder the RUNNING app was started from — the one that is definitely right.

    "Which files are the correct ones?" has an exact answer while JARVIS is open: the
    folder whose `run.py` that process is executing. Everything else is a guess.
    """
    if sys.platform != "win32":
        base = Path("/proc")
        found = ""
        if base.exists():
            here = {os.getpid(), os.getppid()}
            for entry in base.glob("[0-9]*"):
                if int(entry.name) in here:
                    continue
                try:
                    cmd = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                        "utf-8", "replace")
                except OSError:
                    continue
                got = project_from_cmdline(cmd)
                if got:
                    found = got
        return found
    try:
        script = script_path().replace("'", "''")
        got = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or "
             "Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*" + script +
             "*' } | Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=30)
    except Exception:                                            # noqa: BLE001
        return ""
    for line in (got.stdout or "").splitlines():
        found = project_from_cmdline(line)
        if found:
            return found
    return ""


def _stop_marker_path() -> Path:
    """Where the launcher records its own kills.

    Same folder as arcdesk.logs.log_path(): %APPDATA%\ArcDesk\logs (or ARCDESK_HOME).
    The next launch reads it so a session that WE closed is explained, not blamed.
    """
    base = os.environ.get("ARCDESK_HOME") or os.environ.get("APPDATA")
    folder = Path(base) / "ArcDesk" if base else Path.home() / ".arcdesk"
    return folder / "logs" / "launcher-stop.json"


def record_stop(pid: int) -> None:
    """Note that the launcher is killing this pid.

    A process ended this way leaves no clean marker, so the next start would call it
    a crash and escalate the safe-mode counter. Writing the pid here is the
    difference between "it crashed" and "you double-clicked while it was running".
    """
    try:
        import time as _time
        import datetime as _dt
        path = _stop_marker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {"pids": [], "ts": _time.time(),
                      "at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if path.exists():
            try:
                old = json.loads(path.read_text(encoding="utf-8") or "{}")
                if _time.time() - float(old.get("ts", 0)) <= 600:
                    data["pids"] = [x for x in old.get("pids", []) if int(x) != int(pid)]
                    data["ts"] = float(old["ts"])
            except Exception:                                   # noqa: BLE001
                pass
        data["pids"].append(int(pid))
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:                                           # noqa: BLE001
        pass


def kill(pid: int) -> bool:
    record_stop(pid)
    try:
        if sys.platform == "win32":
            got = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                 capture_output=True, text=True, timeout=20)
            return got.returncode == 0
        os.kill(pid, 15)
        return True
    except Exception:                                            # noqa: BLE001
        return False


def ask_to_quit(timeout: float = 2.0) -> bool:
    """Politely ask the running app to close over its own lock socket."""
    payload = json.dumps({"event": "quit", "from": "launcher"}).encode("utf-8") + b"\n"
    for port in candidate_ports():
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
                sock.sendall(payload)
            return True
        except OSError:
            continue
    return False


def stop_all(wait: float = 8.0) -> dict:
    """Close every copy of OURS — politely first, and only by pid if it will not go.

    Politely matters for an updater: a process killed mid-write leaves half a settings
    file. And killing by pid — never `taskkill /IM pythonw.exe` — means the person's
    other python programs survive the update.
    """
    killed: list[int] = []
    asked = ask_to_quit()
    if asked:
        import time as _time
        deadline = _time.monotonic() + max(1.0, wait)
        while _time.monotonic() < deadline:
            if not live():
                return {"killed": killed, "polite": True, "closed": True}
            _time.sleep(0.25)
    for pid in pids():
        if kill(pid):
            killed.append(pid)
    return {"killed": killed, "polite": asked, "closed": not live()}


def any_ours() -> bool:
    """Is any copy of ours around, working or stuck? Exit code question for the .bat."""
    return live() or bool(pids())


def _ps_query_all() -> str:
    """Every python process whose command line runs a `run.py`, with its pid.

    `_ps_query` filters to THIS project by full path; this one catches every copy
    of the app that ever ran on this machine — a zip unzipped in Downloads, an old
    folder that is still alive in the tray, and so on. They all run `run.py`, and
    they all fight for the same lock port, which is why a double-click can end in
    a sentence and no window.
    """
    return ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or "
            "Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*run.py*' } "
            "| ForEach-Object { $_.ProcessId.ToString() + ' ' + "
            "$_.CommandLine }")


def classify_project(cmdline: str, root: str | None = None) -> str:
    """`ours`, `foreign`, or `not-jarvis` for one command line.

    Pure, so it can be tested anywhere. `foreign` needs TWO proofs: the path says
    the folder is a JARVIS/ArcDesk project, and it is not THIS one. A person's own
    `python run.py` in some unrelated project must survive — it is not ours to close.
    """
    root = str(ROOT) if root is None else root
    project = project_from_cmdline(cmdline or "")
    if not project:
        return "not-jarvis"
    if os.path.normcase(project) == os.path.normcase(root):
        return "ours"
    low = project.lower()
    return "foreign" if ("jarvis" in low or "arcdesk" in low) else "not-jarvis"


def all_jarvis() -> list[tuple[int, str]]:
    """(pid, command line) of every python process that runs a `run.py`. [] elsewhere."""
    if sys.platform != "win32":
        return []
    try:
        got = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              _ps_query_all()], capture_output=True, text=True,
                             timeout=30)
    except Exception:                                            # noqa: BLE001
        return []
    out: list[tuple[int, str]] = []
    for line in got.stdout.splitlines():
        line = line.strip()
        if " " not in line:
            continue
        pid_text, cmd = line.split(" ", 1)
        if not pid_text.isdigit():
            continue
        out.append((int(pid_text), cmd))
    return out


def foreign_pids() -> list[int]:
    """Pids of copies of THIS app that live in ANOTHER folder (leftover downloads)."""
    found: list[int] = []
    for pid, cmd in all_jarvis():
        if pid == os.getpid():
            continue
        if classify_project(cmd) == "foreign":
            found.append(pid)
    return found


def kill_foreign() -> list[int]:
    """Close copies of JARVIS that came from another folder. Returns the pids killed.

    The "zoo" case: the zip was unzipped several times, each copy was started once,
    and every copy is still alive — holding the lock port and answering the wake, so
    the fresh double-click gets a sentence instead of a window. By pid only, never by
    name, so no other python program on the PC is touched.
    """
    killed: list[int] = []
    for pid in foreign_pids():
        if kill(pid):
            killed.append(pid)
    return killed


def kill_stale() -> list[int]:
    """Kill ours that are not answering the lock port. Returns the pids killed.

    A stale one is the worst case for a launcher: it exists, so a `tasklist` check says
    "running", but it can never show a window again. Killing only *ours* is the point —
    `taskkill /IM pythonw.exe` used to take every other python app down with it.
    """
    if live():
        return []
    killed: list[int] = []
    for pid in pids():
        if kill(pid):
            killed.append(pid)
    return killed


def status_word() -> tuple[str, int]:
    """(sentence, exit code) — 0 live, 2 running but silent, 1 not running."""
    here = pids()
    if live():
        return ("running, and it answers the window lock", 0)
    if here:
        return (f"running as pid {', '.join(str(p) for p in here)} but it does not answer "
                f"— that is a stuck copy, not a working one", 2)
    return ("not running", 1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis_state", add_help=True)
    ap.add_argument("--status", action="store_true", help="say what is running (exit 0/2/1)")
    ap.add_argument("--wake", action="store_true", help="show the running app (exit 0 if so)")
    ap.add_argument("--pids", action="store_true", help="one pid per line")
    ap.add_argument("--kill-stale", dest="kill_stale", action="store_true",
                    help="kill OUR copies that are not answering")
    ap.add_argument("--kill-foreign", dest="kill_foreign", action="store_true",
                    help="kill copies of this app that came from ANOTHER folder")
    ap.add_argument("--stop", action="store_true",
                    help="close every copy of OURS, healthy or not (an updater needs this)")
    ap.add_argument("--where", action="store_true",
                    help="print the project folder the running app was started from")
    ap.add_argument("--any", action="store_true",
                    help="exit 0 if any copy of ours exists, working or stuck")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.pids:
        here = pids()
        if not args.quiet:
            for pid in here:
                print(pid)
        return 0 if here else 1
    if args.where:
        got = running_project()
        if got:
            print(got)
        return 0 if got else 1
    if args.any:
        return 0 if any_ours() else 1
    if args.stop:
        got = stop_all()
        if not args.quiet:
            if got["closed"] and got["polite"] and not got["killed"]:
                print("closed it - it shut itself down, nothing was killed")
            elif got["killed"]:
                print(f"closed it the hard way ({len(got['killed'])} process(es) ended)")
            else:
                print("nothing was running")
        return 0
    if args.wake:
        ok = wake()
        if not args.quiet:
            print("brought it to the front" if ok else
                  "nothing answered — no working JARVIS is running")
        return 0 if ok else 1
    if args.kill_stale:
        killed = kill_stale()
        if not args.quiet:
            print(f"killed {len(killed)} stuck copy(ies)" if killed else
                  "nothing stuck to kill")
        return 0
    if args.kill_foreign:
        killed = kill_foreign()
        if not args.quiet:
            if killed:
                print("closed a JARVIS left in another folder (pid "
                      + ", ".join(str(p) for p in killed) + ")")
            else:
                print("no JARVIS left in other folders")
        return 0
    word, code = status_word()
    if not args.quiet:
        print(word)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
