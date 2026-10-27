#!/usr/bin/env python3
"""The launcher's brain: make a window appear, or say exactly why it cannot.

`JARVIS.bat` does the batch-shaped parts — find the folder, fetch Python, build `.venv`.
Everything that has to *reason* lives here, because a batch file cannot tell "no answer
yet" from "died", and "the libraries are broken" from "a stuck copy owns the port".

    python tools\\launch.py --ensure          # what a double-click should do (the default path)
    python tools\\launch.py --start           # just start it, detached, capturing its output
    python tools\\launch.py --wait 25         # wait for a proven window (pid-aware)
    python tools\\launch.py --diagnose        # numbered checks + the app's own last lines

Why `--ensure` exists, in the user's words:

    "jarvis.bat double click pana open aaguthu terminal then jarvis run aaga matiku machi"
    …and later: "again open aagala machi.. ena than nadakuthu"

The launcher used to start the app and wait 25 seconds in silence. When the app died at
import time — a voice-engine install pinning an older dependency, a `.venv` built by a
different Python — nobody could tell, because `pythonw.exe` has no stderr and the wait
never looked at the process it had just started. Three things are different now:

  * the child's own output is captured (`logs/spawn.log`), so a traceback survives;
  * the wait watches **the pid**, so "it exited after 0.8 s" is reported in a second,
    not after three rounds of 25;
  * a missing library is *repaired* here (`pip install -r requirements.txt` in the app's
    own environment) instead of being printed as homework — and it says so while it runs.

Exit codes: 0 a window is proven · 1 it is not, and the reason was printed.
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))


def say(text: str = "") -> None:
    print(text, flush=True)


# --------------------------------------------------------------------- helpers
def _probe() -> dict:
    """Is anything listening on the lock port? No GUI imports, no side effects."""
    try:
        from arcdesk import config
        from arcdesk.instance import lock_port, recorded_port
        port = recorded_port() or lock_port(config.load())
    except Exception:                                            # noqa: BLE001
        return {"live": False, "port": 0}
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return {"live": True, "port": port}
    except OSError:
        return {"live": False, "port": port}


def _ours() -> list[int]:
    """Pids of *this* install's run.py — never "every python on the PC"."""
    try:
        import jarvis_state
        return jarvis_state.pids()
    except Exception:                                            # noqa: BLE001
        return []


def _start_app() -> int:
    """Start the app detached with its output captured. Returns the pid (0 on failure)."""
    from arcdesk import open_now, quiet
    argv = open_now.launch_argv(ROOT)
    log = open_now.spawn_log()
    try:
        handle = log.open("ab")
        handle.write(f"\n==== start {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n"
                     f"{' '.join(argv)}\n".encode("utf-8"))
        handle.flush()
        proc = quiet.popen(argv, stdout=handle, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, cwd=str(ROOT))
    except Exception as exc:                                     # noqa: BLE001
        say(f"   could not start it: {type(exc).__name__}: {exc}")
        return 0
    open_now.remember_pid(proc.pid)
    say(f"   started  pid {proc.pid}  ({Path(argv[0]).name})")
    return int(proc.pid)


def _wait(seconds: float, since: float | None = None, watch_pid: bool = True,
          offset: int | None = None) -> dict:
    """Wait for a proven window; stop early (and say so) if the app has already exited.

    `offset` is the log length before this attempt. Without it a launcher run twice in a
    minute finds the previous run's window line and reports success over an empty screen —
    the same class of lie that "the message was sent" was.
    """
    from arcdesk import open_now
    since = time.time() - 3.0 if since is None else since
    pid = open_now.read_pid() if watch_pid else 0
    started = time.time()
    while True:
        mark = (open_now.window_mark_from(offset) if offset is not None
                else open_now.window_mark_since(since))
        if mark:
            return {"ok": True, "mark": mark, "seconds": round(time.time() - started, 1)}
        elapsed = time.time() - started
        if pid and not open_now.pid_alive(pid):
            return {"ok": False, "exited": True, "seconds": round(elapsed, 1)}
        if elapsed >= seconds:
            return {"ok": False, "exited": False, "seconds": round(elapsed, 1)}
        say(f"   … still waiting for the window  ({int(elapsed)} s of {int(seconds)} s)")
        time.sleep(1.0)


def _report(extra: dict | None = None, started: bool = False) -> int:
    """Print everything worth knowing, then leave the caller's window open."""
    from arcdesk import open_now
    state = _probe()
    if started:
        # It was started and is not running now: that is a different verdict from
        # "nothing was tried", and the person deserves the difference in one word.
        state["started"] = True
    report = open_now.diagnose(ROOT, state=state)
    say("")
    say("  what I checked")
    say("  --------------")
    for row in open_now.numbers(report["checks"]):
        say(row)
    say("")
    say(f"  verdict: {report['fault']}")
    if state.get("port"):
        say(f"  lock port {state['port']}: {'answers' if state['live'] else 'silent'}")
    ours = _ours()
    say(f"  copies of this JARVIS running now: {', '.join(str(p) for p in ours) or 'none'}")
    if extra:
        for key, value in extra.items():
            if value:
                say(f"  {key}: {value}")
    spawn = open_now.spawn_text()
    say("")
    say("  what the started process itself said")
    say("  ------------------------------------")
    say(spawn or "  (it printed nothing — it died before it could say anything)")
    say("")
    say("  the app's own log, last lines")
    say("  -----------------------------")
    say(report["tail"] or "  (empty — the app never got to write a log line)")
    if report["reason"]:
        say("")
        say(f"  most useful line: {report['reason']}")
    return 0 if report["ok"] else 1


def _repair() -> bool:
    """Put the libraries back in the app's own environment. True if it then imports."""
    from arcdesk import open_now
    argv = open_now.repair_argv(ROOT)
    say(f"   repairing: {Path(argv[0]).name} -m pip install -r requirements.txt")
    say("   (one time, a minute or two, needs internet — this is the same step the")
    say("    first launch does, so nothing new is being installed globally)")
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), timeout=1800)
        ok = proc.returncode == 0
    except Exception as exc:                                     # noqa: BLE001
        say(f"   the repair command could not run: {type(exc).__name__}: {exc}")
        ok = False
    checks = open_now.preflight(ROOT)
    leftovers = [c["name"] for c in checks if not c["ok"]]
    if ok and not leftovers:
        say("   repaired — the libraries import again")
        return True
    say(f"   still failing: {', '.join(leftovers) or 'the repair command itself'}")
    return False


# ------------------------------------------------------------------- commands
def ensure(wait_seconds: float = 25.0) -> int:
    """Make a window appear. Repair, take over, start, verify — in that order."""
    from arcdesk import open_now

    say("")
    say("  J A R V I S")
    say("  -----------")

    say("  1. checking this install")
    checks = open_now.preflight(ROOT)
    broken = [c["name"] for c in checks if not c["ok"]]
    if broken:
        say(f"     not right yet: {', '.join(broken)}")
        if open_now.pip_fixable(checks) and _repair():
            pass
        else:
            _report()
            return 1
    else:
        say("     all six checks pass")

    say("  2. is one already running?")
    state = _probe()
    if state.get("live"):
        from arcdesk.instance import ask
        got = ask(state["port"], connect=1.2, wait=2.5)
        if got.get("ack"):
            say("     yes — asking it to show its window")
            since = time.time() - 1.0
            res = _wait(6.0, since=since, watch_pid=False,
                        offset=open_now.log_offset())
            if res["ok"]:
                say(f"     the window is up after {res['seconds']} s")
                _closing()
                return 0
            say("     it answered but no window appeared — replacing it")
        else:
            say("     a copy is there but it is not answering — replacing it")
        # stop_all, NOT ask_to_quit + kill_stale: a copy whose GUI is frozen can
        # still answer its lock socket (the socket runs on its own thread), so
        # kill_stale would call it healthy and spare it - and every "replace it"
        # would pile a fresh copy up behind the one that is still holding the port.
        # That is the "multiple pythonw.exe" loop. stop_all asks, waits, and closes
        # by pid when the ask goes nowhere.
        try:
            import jarvis_state
            jarvis_state.stop_all(wait=4.0)
        except Exception as exc:                                 # noqa: BLE001
            say(f"     could not close the old one: {type(exc).__name__}")
        time.sleep(1.0)

    ours = _ours()
    if ours:
        say(f"  2b. closing {len(ours)} leftover copy: {', '.join(str(p) for p in ours)}")
        try:
            import jarvis_state
            jarvis_state.stop_all(wait=4.0)      # see above: kill_stale spares the frozen
        except Exception:                                        # noqa: BLE001
            pass
        time.sleep(1.0)

    say("  3. starting it")
    since = time.time()
    from arcdesk import open_now as _on
    offset = _on.log_offset()                 # only lines written from now on count
    pid = _start_app()
    if not pid:
        _report({"start": "the process could not be created"}, started=True)
        return 1

    say("  4. waiting for a window (it writes a line the moment one is up)")
    res = _wait(wait_seconds, since=since - 1.0, watch_pid=True, offset=offset)
    if res["ok"]:
        say(f"     the window is up after {res['seconds']} s  ({res['mark'][:60]}…)")
        _closing()
        return 0
    if res.get("exited"):
        say(f"     it exited after {res['seconds']} s, before any window")
    else:
        say(f"     no window after {int(wait_seconds)} s")
    _report({"start": f"pid {pid}" if pid else "process not created"}, started=True)
    return 1


def _closing() -> None:
    say("")
    say("  Ctrl+Alt+J  open / hide the window      Ctrl+Alt+Q  quit")
    say("  this window closes itself when JARVIS is up")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="launch", add_help=True)
    ap.add_argument("--ensure", action="store_true",
                    help="repair if needed, start, and prove a window (the double-click path)")
    ap.add_argument("--start", action="store_true", help="start it and print the pid")
    ap.add_argument("--wait", type=float, default=0.0,
                    help="seconds to wait for the app's own 'window is up' line")
    ap.add_argument("--since", type=float, default=0.0,
                    help="epoch second the wait counts from (default: 3 s ago)")
    ap.add_argument("--diagnose", action="store_true",
                    help="print numbered checks and the app's last lines")
    ap.add_argument("--log", default="", help="read this log instead of the app's own")
    ap.add_argument("--quiet", action="store_true", help="say nothing while waiting")
    ap.add_argument("--root", default="",
                    help="check this folder instead of the one this file lives in")
    args = ap.parse_args(argv)

    global ROOT
    if args.root:
        ROOT = Path(args.root).expanduser().resolve()

    from arcdesk import open_now

    if args.ensure:
        return ensure(wait_seconds=args.wait or 25.0)

    if args.start:
        return 0 if _start_app() else 1

    if args.diagnose:
        return _report()

    if args.wait:
        since = args.since or (time.time() - 3.0)
        if args.log:                       # a test (or a support script) points at its own
            got = open_now.wait_for_window(
                since, timeout=args.wait, out=None if args.quiet else say,
                path=Path(args.log))
            if got["ok"]:
                say(f"   the window is up after {got['seconds']} s")
                return 0
            say(f"   no window after {int(args.wait)} s")
            return 1
        got = _wait(args.wait, since=since, watch_pid=True)
        if got["ok"]:
            say(f"   the window is up after {got['seconds']} s")
            return 0
        if got.get("exited"):
            say(f"   the app exited after {got['seconds']} s, before showing a window")
            spawn = open_now.spawn_text()
            if spawn:
                say("   it said:")
                for row in spawn.splitlines()[-6:]:
                    say(f"     {row}")
        else:
            say(f"   no window after {int(args.wait)} s")
        return 1

    state = _probe()
    if state["live"]:
        say(f"  JARVIS is answering on port {state['port']}")
        return 0
    say(f"  nothing is answering on port {state['port']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
