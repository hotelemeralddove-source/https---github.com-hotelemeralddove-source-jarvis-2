#!/usr/bin/env python3
"""Start the real entry point the way Windows will, and watch what it does.

    python tools/smoke_firstrun.py                 # run.py --shadow
    python tools/smoke_firstrun.py --show          # run.py --show
    python tools/smoke_firstrun.py --bare          # run.py with no flags (a double-click)
    python tools/smoke_firstrun.py --bare --home DIR --expect visible
    python tools/smoke_firstrun.py --seconds 10

Why this exists: every other test imports modules directly, so nothing proved that
`python run.py --shadow` — the exact command the autostart entry writes — gets from
"python starts" to "window exists" without a traceback. That gap is where a packaged
app usually dies (a missing data file, an import that only happens on first run).

What it checks, all of it observed rather than assumed:
  * the process is still alive after N seconds (it did not crash on startup)
  * it wrote a settings file in a throw-away ARCDESK_HOME
  * its output contains no Traceback
  * it exits within a few seconds of being asked (Ctrl+Alt+Q / SIGTERM path)

What it cannot check here: that a window actually appears on a real screen. In this
sandbox Qt runs offscreen, so the honest claim is "it boots", not "it looks right".
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ok = True



def _stop_child(proc, wait=10.0):
    """Stop a child the same way on every OS.

    `os.killpg` does not exist on Windows: check.bat died at step 1/9 with
    "AttributeError: module 'os' has no attribute 'killpg'" before a single test ran.
    """
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(timeout=wait)
        return
    except Exception:
        pass
    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass

def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:34]!r}")
    ok &= bool(good)


def main(argv: list[str]) -> int:
    # --bare is the desktop shortcut with no parameters: the exact launch a double-click
    # produces on a machine whose settings file already exists.
    if "--bare" in argv:
        flag = None
    elif "--show" in argv:
        flag = "--show"
    else:
        flag = "--shadow"
    extra = [a for a in argv if a in ("--no-instance", "--no-tray")]
    seconds = 8.0
    if "--seconds" in argv:
        seconds = float(argv[argv.index("--seconds") + 1])

    if "--home" in argv:
        # judge an EXISTING settings folder (that is the interesting case: the person
        # already has settings.json written by an older build)
        home = Path(argv[argv.index("--home") + 1]).resolve()
        home.mkdir(parents=True, exist_ok=True)
    else:
        home = Path(tempfile.mkdtemp(prefix="arcdesk-firstrun-"))
    env = dict(os.environ)
    env["ARCDESK_HOME"] = str(home)
    env["QT_QPA_PLATFORM"] = env.get("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("ARCDESK_TEST", None)

    print(f"ARC DESK · first-run smoke  (run.py {flag})")
    print("=" * 70)
    print(f"  settings folder: {home}")

    started = time.time()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py")] + ([flag] if flag else []) + extra,
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", start_new_session=True,
    )
    alive_at_check = False
    try:
        deadline = started + seconds
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            time.sleep(0.25)
        alive_at_check = proc.poll() is None
    finally:
        boot_seconds = time.time() - started
        # Ask it to close the way a person would, not with a signal.
        #
        # This is why the Windows run reported "it shut down cleanly (exit 0) = 1" and
        # "it said so on the way out = False": the old code called proc.terminate(), which
        # on Windows is TerminateProcess — exit code 1, no shutdown, no message. Two checks
        # could never pass there, and they looked like app bugs for weeks. The app HAS a
        # polite channel (the instance lock socket); use it, and if it is switched off
        # (--no-instance) say that the question was not asked instead of failing it.
        polite = "--no-instance" not in extra
        asked = False
        if polite and proc.poll() is None:
            try:
                sys.path.insert(0, str(ROOT / "tools"))
                import jarvis_state                                    # noqa: PLC0415
                asked = bool(jarvis_state.ask_to_quit(timeout=8.0))
            except Exception:                                          # noqa: BLE001
                asked = False
        if proc.poll() is None:
            try:
                if os.name == "nt":
                    proc.terminate()
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:                                          # noqa: BLE001
                pass
        try:
            out = proc.communicate(timeout=12)[0] or ""
        except subprocess.TimeoutExpired:
            _stop_child(proc, wait=2.0)
            out = (proc.communicate()[0] or "") + "\n<had to be force-killed>"

    already = "already running" in out.lower()
    if already and "--no-instance" not in extra:
        print("   SKIP another Arc Desk holds the instance lock, so this run "
              "correctly forwarded and quit.")
        print("        Re-run with --no-instance for an isolated boot.")
        check("the second launch refused to open a second window", True)
        return 0
    check(f"still running after {seconds:.0f}s (it did not crash)", alive_at_check)
    code = proc.returncode
    if polite:
        check("it was asked to close, not killed", asked)
        check("it shut down cleanly when asked (exit 0)", code, 0)
        check("it said so on the way out", "closed cleanly" in out)
    else:
        print("   ..   SKIP the polite-shutdown checks: --no-instance means this copy has "
              "no lock socket to be asked on.")
        print("        Run without --no-instance to test the real 'bye jarvis' path.")
        check("it did not crash before it was stopped", alive_at_check)
    check("no Traceback in its output", "Traceback" not in out)
    files = sorted(p.name for p in home.rglob("*") if p.is_file())
    check("a settings file was created", any(n.startswith(("settings", "config"))
                                             for n in files) or "settings.json" in files)
    check("it wrote inside the throw-away folder", bool(files))
    print(f"  files: {', '.join(files[:8]) or '(none)'}")
    # Did the window actually get shown? The app now writes that decision to its own
    # log ("BOOT · ..."), which is also what the user can read when nothing appears.
    log = home / "ArcDesk" / "logs" / "arcdesk.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    hidden = "stealth: the window is not shown" in text
    shown = "the window is shown" in text and not hidden
    state = "hidden" if hidden else ("visible" if shown else "unknown")
    handles = [ln for ln in text.splitlines() if "BOOT · handles:" in ln]
    boot_line = [ln for ln in text.splitlines() if "from the double-click" in ln]
    if boot_line:
        print("  the app measured its own start:", boot_line[-1].split("NOTE")[-1].strip())
    tray = "yes" if handles and "tray=yes" in handles[-1] else "no"
    check("the log records what happened to the window", state != "unknown")
    if "--expect" in argv:
        want_state = argv[argv.index("--expect") + 1]
        if want_state == "stealth-rule":
            # what the app's own rule says it must do on THIS machine: hide when there
            # is a tray icon to click, show when there is nothing at all to click.
            want_state = "hidden" if tray == "yes" else "visible"
            print(f"  the rule says: tray={tray} -> {want_state}")
        # an app that never writes the line would silently "pass" a hidden expectation,
        # so unknown is never accepted here.
        check(f"window state for this launch ({want_state})", state, want_state)
    check("boot was not absurdly slow", boot_seconds < seconds + 6)
    print(f"  boot wall time: {boot_seconds:.1f}s (includes the wait, not a measurement)")

    interesting = [ln for ln in out.splitlines()
                   if any(k in ln.lower() for k in ("error", "warn", "fail", "traceback"))]
    if interesting:
        print("  notes from its own output:")
        for line in interesting[:6]:
            print("    ·", line.strip()[:110])
    else:
        print("  it printed nothing alarming.")

    print("=" * 70)
    print("UNVERIFIED here: that the window looks right on a real screen — this "
          "sandbox has no display, Qt runs offscreen.")
    print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
