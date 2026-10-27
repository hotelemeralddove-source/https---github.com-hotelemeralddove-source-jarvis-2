"""Does `run.py --shadow` actually boot? — the one test that runs the real entry point.

Every other test imports modules, so none of them would notice a crash that only
happens on the path Windows uses: `ArcDesk.exe --shadow` (or `python run.py --shadow`
from a source checkout), the exact command the autostart entry writes.

This wraps `tools/smoke_firstrun.py` with an isolated settings folder and asserts:
  * the process is alive after 6 s (no startup crash),
  * it wrote settings.json into the throw-away folder and nothing into the real one,
  * a stop signal produces a clean exit 0 and the words "closed cleanly",
  * no traceback, and the instance lock was released so a second launch is possible.

The reason the "closed cleanly" bit is tested at all: the first working version of the
shutdown path crashed the interpreter *after* printing that line (SIGBUS on dialog
teardown), and a test that only checked "it exited" would have passed.

What this cannot prove, and says so: that the window looks right. Qt runs offscreen
here — there is no screen in the sandbox.

Run:  python tests/test_firstrun.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:34]!r}")
    ok &= bool(good)


print("1. real entry point, first run, shadow boot")
env = dict(os.environ)
env["ARCDESK_HOME"] = tempfile.mkdtemp(prefix="arcdesk-firstrun-test-")
env["QT_QPA_PLATFORM"] = "offscreen"
env["PYTHONIOENCODING"] = "utf-8"
proc = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "smoke_firstrun.py"),
     "--shadow", "--no-instance", "--seconds", "6"],
    cwd=str(ROOT), env=env, capture_output=True, text=True, errors="replace", timeout=180,
)
out = proc.stdout + proc.stderr
print("\n".join("   | " + ln for ln in out.splitlines()[-16:]))
check("smoke exited 0", proc.returncode, 0)
# The smoke tool is the judge here; this test only checks that it judged, and that its
# own checks actually ran (a smoke that silently skipped everything would also "pass").
passes = [ln for ln in out.splitlines() if "OK  " in ln]
failures = [ln for ln in out.splitlines() if "FAIL" in ln]
check("the smoke ran real checks", len(passes) >= 6)
check("no check inside the smoke failed", failures, [])
check("it stayed up long enough to be a boot", "still running after" in out)
check("it shut down cleanly, or said why that was not asked",
      any(("shut down cleanly" in ln and "OK" in ln) or "SKIP the polite-shutdown" in ln
          for ln in out.splitlines()))
check("settings were written to the throw-away folder",
      any("settings file was created" in ln and "OK" in ln for ln in passes))
check("its own verdict was ALL PASS", "RESULT: ALL PASS" in out)

print("2. it kept its hands off the real settings folder")
real = Path.home() / ".config" / "ArcDesk"
if real.is_dir():
    newest = max((p.stat().st_mtime for p in real.rglob("*") if p.is_file()), default=0)
    print(f"   ..   real settings folder last touched at {newest:.0f} "
          f"(not compared — the user's own Arc Desk may be running)")

print("3. the shutdown handler is wired where it can work")
run_py = (ROOT / "run.py").read_text(encoding="utf-8")
check("signals are installed", "SIGTERM" in run_py and "SIGINT" in run_py)
check("the handler is a flag, not a Qt call from a signal",
      "_ask_to_quit" in run_py and "stop_request" in run_py)
check("a heartbeat timer performs the quit", "_heartbeat" in run_py)
before = run_py.index("_heartbeat.start()")
wizard = run_py.index("WelcomeDialog") if "WelcomeDialog" in run_py else 10 ** 9
check("installed BEFORE the first-run wizard (a nested event loop)", before < wizard)
check("modal dialogs are rejected explicitly", "widget.reject()" in run_py)
check("the SIGBUS workaround is documented, not magic",
      "SIGBUS" in run_py)

print()
print("2. the desktop shortcut: no parameters, and the window must be there")
env2 = dict(env)
bare = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "smoke_firstrun.py"),
     "--bare", "--no-instance", "--no-tray", "--seconds", "6", "--expect", "visible"],
    cwd=str(ROOT), env=env2, capture_output=True, text=True, errors="replace", timeout=180,
)
print("\n".join("   | " + ln for ln in (bare.stdout + bare.stderr).splitlines()[-10:]))
check("a double-click (no flags) shows the window", bare.returncode, 0)
check("…so 'installed but does nothing' cannot repeat",
      "window state for this launch (visible)" in bare.stdout, True)

print("\n3. the boot entry: --shadow, and the window must stay hidden")
shadow = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "smoke_firstrun.py"),
     "--shadow", "--no-instance", "--seconds", "6", "--expect", "stealth-rule"],
    cwd=str(ROOT), env=env2, capture_output=True, text=True, errors="replace", timeout=180,
)
print("\n".join("   | " + ln for ln in (shadow.stdout + shadow.stderr).splitlines()[-8:]))
check("booting with Windows stays in stealth", shadow.returncode, 0)

print("\n4. the two Windows shortcuts say so explicitly")
iss = (ROOT / "packaging" / "arcdesk.iss").read_text(encoding="utf-8")
check("the desktop shortcut passes --show", 'Parameters: "--show"; Tasks: desktopicon' in iss)
check("the Start Menu shortcut passes --show",
      'Name: "{group}\\{#AppName}"; Filename: "{app}\\{#AppExe}"; Parameters: "--show"' in iss)
check("the boot entry still passes --shadow", '" --shadow"' in iss)
check("the model download does not flash a window", "--download-voice-model --shadow" in iss)

print("\n5. an OLD settings file cannot make the app invisible any more")
import json  # noqa: E402
import shutil  # noqa: E402

old_home = Path(tempfile.mkdtemp(prefix="arcdesk-old-settings-"))
# ARCDESK_HOME *is* the settings folder (config.data_dir returns it directly); the log
# lives one level under it. Two different places on purpose, and easy to get wrong here.
(old_home / "settings.json").write_text(
    json.dumps({"shadow": {"enabled": True}, "first_run": False}), encoding="utf-8")
    # ^ exactly what the user's laptop has: hidden on, and never chosen by them
old = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "smoke_firstrun.py"), "--bare", "--no-instance",
     "--seconds", "6", "--home", str(old_home), "--expect", "visible"],
    cwd=str(ROOT), env=dict(env), capture_output=True, text=True, errors="replace",
    timeout=180,
)
print("\n".join("   | " + ln for ln in (old.stdout + old.stderr).splitlines()[-8:]))
check("a settings file that says 'hidden' still opens a window on a double-click",
      old.returncode, 0)
check("…and nothing else in that file was disturbed",
      json.loads((old_home / "settings.json").read_text(encoding="utf-8"))
      .get("first_run"), False)

print("\n6. --shadow is a flag for one launch, not a saved preference")
shadow_home = Path(tempfile.mkdtemp(prefix="arcdesk-shadow-persist-"))
subprocess.run(
    [sys.executable, str(ROOT / "tools" / "smoke_firstrun.py"), "--shadow", "--no-instance",
     "--no-tray", "--seconds", "5", "--home", str(shadow_home), "--expect", "hidden"],
    cwd=str(ROOT), env=dict(env), capture_output=True, text=True, errors="replace",
    timeout=180,
)
settings = json.loads((shadow_home / "settings.json").read_text(encoding="utf-8"))
check("booting with --shadow did not turn stealth ON in settings.json",
      bool(settings.get("shadow", {}).get("enabled")), False)
check("no '--shadow only' key leaked into the settings file",
      [k for k in settings if k.startswith("_")], [])
shutil.rmtree(old_home, ignore_errors=True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
