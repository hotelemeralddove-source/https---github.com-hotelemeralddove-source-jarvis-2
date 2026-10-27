#!/usr/bin/env python3
"""No console window, ever: the spawn layer, and the windowless launcher.

The complaint this answers: "neraya transparent command prompt open aaitae iruku
arcdesk ah run pana". ArcDesk is a windowless program, so on Windows every console
child it started got a brand-new black window: one per spoken sentence (PowerShell
SAPI), one per screen read, one per ffmpeg/tesseract pass, one per wake-daemon
restart. This test proves the fix at the three levels it has to hold:

  1. the keyword translation is right (measured, including the Windows branch),
  2. a real child still runs and its output still arrives (no silent breakage),
  3. **no runtime module can spawn a console behind our back** — the source is
     scanned, so a new `subprocess.run(` somewhere fails the suite instead of
     appearing on the user's screen.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-quiet-"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from arcdesk import quiet  # noqa: E402

ok = True


def check(label: str, got, want) -> None:
    global ok
    good = got == want
    ok = ok and good
    shown = repr(got)
    if len(shown) > 58:
        shown = shown[:55] + "…"
    print(f"   {'OK  ' if good else 'FAIL'} {label:<54} {shown}"
          + ("" if good else f"   (wanted {want!r})"))


print("1) the Windows branch asks for no window at all")
quiet._FORCE_WIN = True
try:
    plain = quiet.kwargs()
    check("CREATE_NO_WINDOW is set", bool(plain["creationflags"] & quiet.CREATE_NO_WINDOW), True)
    check("…and nothing extra", plain["creationflags"], quiet.CREATE_NO_WINDOW)
    check("a STARTUPINFO rides along", type(plain["startupinfo"]).__name__ in
          ("STARTUPINFO", "_ShowHidden"), True)
    check("…with SW_HIDE, so even the first frame is hidden",
          plain["startupinfo"].wShowWindow, quiet.SW_HIDE)
    check("start_new_session is translated, not passed on",
          "start_new_session" in quiet.kwargs(start_new_session=True), False)
    detached = quiet.kwargs(start_new_session=True)["creationflags"]
    check("…into DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP",
          detached & quiet.CREATE_NO_WINDOW, quiet.CREATE_NO_WINDOW)
    check("…both bits", detached & (quiet.DETACHED_PROCESS | quiet.CREATE_NEW_PROCESS_GROUP),
          quiet.DETACHED_PROCESS | quiet.CREATE_NEW_PROCESS_GROUP)
    kept = quiet.kwargs(creationflags=0x4000)["creationflags"]
    check("a caller's own flag is kept and OR'd", kept, 0x4000 | quiet.CREATE_NO_WINDOW)
    check("the other keywords survive",
          sorted(quiet.kwargs(capture_output=True, text=True)),
          ["capture_output", "creationflags", "startupinfo", "text"])
finally:
    quiet._FORCE_WIN = None

print("\n2) nothing is changed on a platform that has no console windows to hide")
quiet._FORCE_WIN = False
try:
    check("creationflags/startupinfo are dropped",
          quiet.kwargs(creationflags=0x08000000, startupinfo=object()), {})
    check("start_new_session is kept", quiet.kwargs(start_new_session=True),
          {"start_new_session": True})
    check("detached still means detached", quiet.kwargs(detached=True),
          {"start_new_session": True})
finally:
    quiet._FORCE_WIN = None

print("\n3) a real child still runs, still answers, still fails when it should")
done = quiet.run([sys.executable, "-c", "print('alive')"],
                 capture_output=True, text=True, timeout=30)
check("stdout comes back", (done.stdout or "").strip(), "alive")
check("the exit code comes back", done.returncode, 0)
check("check_output works", quiet.check_output(
    [sys.executable, "-c", "print('two')"], text=True, timeout=30).strip(), "two")
proc = quiet.popen([sys.executable, "-c", "import sys; sys.exit(3)"])
check("popen works and the code is readable", proc.wait(timeout=30), 3)
check("call works", quiet.call([sys.executable, "-c", "pass"]), 0)
try:
    quiet.run([sys.executable, "-c", "import sys; sys.exit(9)"], check=True,
              capture_output=True, timeout=30)
    raised = False
except subprocess.CalledProcessError:
    raised = True
check("exceptions are not swallowed (check=True still raises)", raised, True)
shell = quiet.run("echo shelled", shell=True, capture_output=True, text=True, timeout=30)
check("shell=True works too", (shell.stdout or "").strip().lower().endswith("shelled"), True)

print("\n4) every module that spawns something goes through quiet")
runtime = sorted(p for p in (ROOT / "arcdesk").rglob("*.py")
                 if "__pycache__" not in p.parts)
raw: list[str] = []
spawners: list[str] = []
SPAWN = {"run", "Popen", "call", "check_output", "check_call"}
for path in runtime:
    if path.name == "quiet.py":
        continue                      # the one place allowed to touch subprocess itself
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    uses_quiet = quiet.imports_quiet(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner, name = node.func.value, node.func.attr
        if isinstance(owner, ast.Name) and owner.id == "subprocess" and name in SPAWN:
            raw.append(f"{path.relative_to(ROOT)}:{node.lineno} subprocess.{name}(")
        if isinstance(owner, ast.Name) and owner.id == "quiet" and name in SPAWN:
            spawners.append(str(path.relative_to(ROOT)))
check("no runtime module calls subprocess directly any more", raw, [])
check("every module that spawns imports quiet",
      all(quiet.imports_quiet((ROOT / p).read_text(encoding="utf-8"))
          for p in set(spawners)), True)
check("that is a real number of modules, not zero", len(set(spawners)) >= 15, True)
check("quiet itself is the only one allowed to touch subprocess",
      "subprocess.run(" in (ROOT / "arcdesk" / "quiet.py").read_text(encoding="utf-8"), True)
missing = [m for m in quiet._EXPECTED if m not in quiet._PATCHED]
check("the declared list and the source agree", missing, [])
check("…and it covers the loud ones (voice, screen, engines, daemon)",
      all(m in quiet._PATCHED for m in
          ("ai/voice", "uia", "vision", "screenhelp", "engines", "wake/daemon_runner")), True)
check("describe() says something a human can read",
      isinstance(quiet.describe(), str) and len(quiet.describe()) > 20, True)

print("\n5) the wake daemon is spawned silently, and detached")
from arcdesk import paths  # noqa: E402
cmd, kwargs = paths.daemon_command(8765, "hey jarvis", "auto", "bye jarvis")
quiet._FORCE_WIN = True
try:
    from arcdesk import quiet as q2  # noqa: E402
    win_kw = q2.kwargs(detached=True)
    check("a Windows daemon gets CREATE_NO_WINDOW",
          bool(win_kw["creationflags"] & quiet.CREATE_NO_WINDOW), True)
    check("…and is detached from the app that started it",
          bool(win_kw["creationflags"] & quiet.DETACHED_PROCESS), True)
finally:
    quiet._FORCE_WIN = None
check("the command is still a real command",
      any(str(c).endswith("arc_daemon.py") for c in cmd), True)
check("…with a port", "8765" in cmd, True)
check("daemon kwargs detach it on POSIX too",
      kwargs.get("start_new_session"), True)

print("\n6) the double-click launcher has no console to show")
launcher = ROOT / "ArcDesk.pyw"
check("ArcDesk.pyw exists (pythonw.exe runs it, so no console)", launcher.exists(), True)
src = launcher.read_text(encoding="utf-8")
check("it says why it exists", "pythonw" in src, True)
# .pyw is not a suffix importlib knows, so load it as plain source — which is all it is.
from importlib.machinery import SourceFileLoader  # noqa: E402
loader = SourceFileLoader("arcdesk_pyw", str(launcher))
spec = importlib.util.spec_from_loader("arcdesk_pyw", loader)
mod = importlib.util.module_from_spec(spec)
loader.exec_module(mod)
saved_out, saved_err = sys.stdout, sys.stderr
try:
    sys.stdout = None                              # exactly what pythonw.exe does
    sys.stderr = None
    stream = mod._open_log()
    rescued_out, rescued_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = saved_out, saved_err     # report on the console again
    check("a missing stdout is given a log instead of crashing a print()",
          rescued_out is not None and rescued_err is not None, True)
    check("…the same file for both, so a traceback is not lost",
          getattr(rescued_out, "name", "") == getattr(rescued_err, "name", ""), True)
    check("the log is a real file", Path(getattr(stream, "name", "")).exists(), True)
    check("…in the app's own folder", "ArcDesk" in str(getattr(stream, "name", ""))
          or "arcdesk" in str(getattr(stream, "name", "")), True)
    stream.write("windowless log line\n")
    stream.flush()
    check("a line written while windowless really reaches the log",
          "windowless log line" in Path(stream.name).read_text(encoding="utf-8",
                                                              errors="replace"), True)
finally:
    sys.stdout, sys.stderr = saved_out, saved_err
check("the launcher hands over to run.main", "run_main()" in src, True)
check("and keeps a traceback if the app dies windowless",
      "traceback.print_exc()" in src, True)

print("\n7) nothing can die just because there was no console to print to")
run_src = (ROOT / "run.py").read_text(encoding="utf-8")
run_tree = ast.parse(run_src)
prints = [n.lineno for n in ast.walk(run_tree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"]
guards = [n.lineno for n in ast.walk(run_tree)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
          and n.func.attr == "ensure_streams"]
check("run.py fixes the streams", bool(guards), True)
check("…before the first print in the file", bool(prints) and min(guards) < min(prints), True)
check("ArcDesk.pyw uses the same one implementation",
      "logs.ensure_streams()" in launcher.read_text(encoding="utf-8"), True)

from arcdesk import logs  # noqa: E402
check("the log path is a file we can name", Path(logs.log_path()).name, "arcdesk.log")
logs.note("test-quiet: a line written by hand")
check("note() reaches the log",
      "test-quiet: a line written by hand" in logs.log_path().read_text(encoding="utf-8",
                                                                       errors="replace"), True)
import logging  # noqa: E402
logs.install()
big = logs.log_path()
# Grow it the way it really grows — through the handler. Writing to the file behind the
# handler's back would prove nothing, because rotation is decided on the handler's own
# stream position.
logger = logging.getLogger("arcdesk.rotate")
for i in range(6000):
    logger.warning("fill line %s %s", i, "x" * 100)
check("a log that grew too big is rotated, not appended to forever",
      big.with_suffix(".log.1").exists(), True)
check("the live log is small again after rotation", big.stat().st_size < logs.MAX_BYTES, True)
check("…and the scrubbing filter is attached to the file handler",
      any(getattr(h, "_arcdesk_log", False) for h in logging.getLogger().handlers), True)
check("describe() says where the console went", isinstance(logs.describe(), str), True)

# The end-to-end version: really launch the windowless entry point in a process whose
# stdout and stderr are None (exactly what pythonw.exe supplies) and make sure it comes
# back with an answer instead of dying silently.
env = {**os.environ, "QT_QPA_PLATFORM": "offscreen",
       "ARCDESK_HOME": tempfile.mkdtemp(prefix="arcdesk-pyw-")}
probe = (
    "import sys, importlib.util;"
    "from importlib.machinery import SourceFileLoader;"
    f"p={str(launcher)!r};"
    "l=SourceFileLoader('p', p); s=importlib.util.spec_from_loader('p', l);"
    "m=importlib.util.module_from_spec(s); l.exec_module(m);"
    "sys.argv=['ArcDesk.pyw','--help'];"
    "sys.stdout=None; sys.stderr=None;"
    "m.main()"
)
proc = subprocess.run([sys.executable, "-c", probe], cwd=str(ROOT), env=env,
                      capture_output=True, text=True, timeout=120)
written = Path(env["ARCDESK_HOME"]) / "ArcDesk" / "logs" / "arcdesk.log"
text = written.read_text(encoding="utf-8", errors="replace") if written.exists() else ""
check("a real windowless launch exits cleanly (argparse --help, exit 0)",
      proc.returncode, 0)
check("…and its output is in the log, not lost", "usage: arcdesk" in text, True)
check("…with no traceback hiding in there", "Traceback" in text, False)

print("\n8) the installer and the spec agree with this (no console build)")
spec_src = (ROOT / "packaging" / "arcdesk.spec").read_text(encoding="utf-8")
check("every frozen entry point is console=False",
      spec_src.count("console=False") >= 2, True)
check("no entry point is console=True", "console=True" in spec_src, False)

t0 = time.time()
for _ in range(5):
    quiet.run([sys.executable, "-c", "pass"], timeout=30)
check("five spawns cost less than two seconds (no hidden wait)", time.time() - t0 < 2.0, True)

print()
print("RESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
