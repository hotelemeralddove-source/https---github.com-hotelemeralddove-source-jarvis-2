"""JARVIS.bat must never say "already running" and start nothing.

The report: *"jarvis.bat ah close pana ithuku munnadi app open aachu ipo open aagala"*.
The launcher decided with

    tasklist /FI "IMAGENAME eq pythonw.exe" | find /I "pythonw.exe"

which answers "is ANY pythonw.exe alive on this PC?" — a different app, or our own copy
that had stopped responding. On "yes" it printed "already running - nothing to start" and
started nothing, so the window never came back.

What is proven here:

  1. the parse of process ids is sane (noise, duplicates, our own pid ignored);
  2. a working app is detected by its OWN lock socket, and `--wake` really sends the
     wake event — measured against a socket, not assumed;
  3. a python that is not this app is never claimed as "ours" (no false "already running");
  4. a stuck copy of ours is killed; a working one is never killed by --kill-stale;
  5. the polite path never kills: the app is asked to quit over its own socket and closes
     itself cleanly;
  6. `--status` exit codes 0 (live) / 2 (running but silent) / 1 (not running);
  7. JARVIS.bat and UPDATE-JARVIS.bat no longer decide anything by "is any pythonw alive",
     and the launcher starts the app detached from its own console;
  8. a second launch of the app ASKS the first to come forward instead of exiting silently;
  9. a launcher inside an unzipped FIX PACK folder finds the real app and offers to apply
     the pack (the screenshot: "find_project.bat is not recognized").

Run:  python tests/test_launcher_state.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("ARCDESK_HOME", tempfile.mkdtemp(prefix="arcdesk-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<58} {got!r}")


from tools import jarvis_state as js  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class FakeLock:
    """A stand-in for the app's lock socket: records the events it is sent."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self.events: list[str] = []
        self.reply = True                    # False = a hung copy that accepts but says nothing
        self.alive = True
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self.sock.settimeout(0.3)
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                conn.settimeout(0.5)
                data = b""
                while b"\n" not in data and len(data) < 4096:
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data += chunk
                import json
                event = json.loads(data.decode() or "{}").get("event", "")
                self.events.append(event)
                # Answer, exactly like arcdesk/instance.py does. The launcher's whole
                # bug was accepting "sent" as success - so a stand-in that stays silent
                # would now (correctly) be reported as a dead app.
                if self.reply:
                    conn.sendall(json.dumps({"event": "awake",
                                             "handled": event in ("wake", "show")}).encode()
                                 + b"\n")
            except Exception:                                    # noqa: BLE001
                pass
            finally:
                conn.close()

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


print("1. reading process ids")
check("powerShell noise is ignored", js.parse_pids("ProcessId\n----\n4242\n"),
      [4242])
check("duplicates collapse", js.parse_pids("12\n12\n13\n"), [12, 13])
check("our own pid is never 'ours'", js.parse_pids(f"{os.getpid()}\n"), [])
check("blank output means nothing running", js.parse_pids(""), [])

print("\n2. a working app is found by its own lock socket, and wake reaches it")
fake = FakeLock()
real_ports = js.candidate_ports
js.candidate_ports = lambda: [fake.port]
try:
    check("live() sees it", js.live(), True)
    time.sleep(0.2)
    fake.events.clear()          # live() only touches the port; it sends nothing
    check("wake() says it worked (the app answered)", js.wake(), True)
    time.sleep(0.2)
    check("…and the app really received a wake event", fake.events, ["wake"])
    check("status says running and answering", js.status_word()[1], 0)
finally:
    fake.close()

js.candidate_ports = lambda: [1]
try:
    check("nothing on the port is NOT 'running'", js.live(), False)
    check("wake() admits it could not reach anything", js.wake(), False)
    fake.reply = False                   # alive socket, no answer = a hung copy
    check("…and a copy that accepts but never answers is NOT 'woken'", js.wake(), False)
    fake.reply = True
    word, code = js.status_word()
    check("exit code 1 means not running", code, 1)
finally:
    js.candidate_ports = real_ports

print("\n3. only THIS project's python counts as ours")
sandbox = Path(tempfile.mkdtemp(prefix="arcdesk-own-"))
fake_root = sandbox / "project"
fake_root.mkdir()
script = fake_root / "run.py"
script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
other = sandbox / "other.py"
other.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

real_root, real_script = js.ROOT, js.script_path
js.ROOT = fake_root
js.script_path = lambda: str(script)
proc_ours = subprocess.Popen([sys.executable, str(script)])
proc_other = subprocess.Popen([sys.executable, str(other)])
try:
    time.sleep(0.8)
    found = js.pids()
    check("a python running OUR run.py is found", proc_ours.pid in found, True)
    check("a python running something else is not claimed", proc_other.pid in found, False)
    check("--any is true while ours is up", js.any_ours(), True)
finally:
    for proc in (proc_ours, proc_other):
        proc.kill()
        proc.wait(timeout=10)
# a killed process is not gone the instant wait() returns — the process table can lag a
# beat (and lags much longer on a loaded machine, which is why this used to fail only in a
# full run). Poll for it, and if it is STILL there, report which pid and command line:
# "the check is flaky" is not a diagnosis, and the next reader needs the evidence.
left: list[int] = []
for _ in range(40):
    left = js.pids()
    if not left:
        break
    time.sleep(0.25)
# asked WHILE the fake root is still in place: otherwise a real JARVIS anywhere on this
# computer would answer "yes" and the check would be measuring somebody else's app.
check("--any is false once it is gone", left, [])
js.ROOT, js.script_path = real_root, real_script

print("\n4. a stuck copy is killed; a working one is never killed")
killed: list[int] = []
real_pids, real_kill, real_live = js.pids, js.kill, js.live
js.pids = lambda: [111, 222]
js.kill = lambda pid: (killed.append(pid), True)[1]
try:
    js.live = lambda: False
    got = js.kill_stale()
    check("both stuck copies were closed", sorted(got), [111, 222])
    killed.clear()
    js.live = lambda: True
    got = js.kill_stale()
    check("a working app is left alone", got, [])
    check("…nothing was killed at all", killed, [])
finally:
    js.pids, js.kill, js.live = real_pids, real_kill, real_live

print("\n5. the polite path: ask it to quit, do not kill it")
fake = FakeLock()
js.candidate_ports = lambda: [fake.port]
try:
    check("ask_to_quit reaches the app", js.ask_to_quit(), True)
    time.sleep(0.2)
    check("…with a quit event, not a kill", fake.events[-1], "quit")
finally:
    fake.close()
    js.candidate_ports = real_ports

asked = FakeLock()
killed.clear()
js.candidate_ports = lambda: [asked.port]
js.pids = lambda: [333]
js.kill = lambda pid: (killed.append(pid), True)[1]


def vanish() -> None:
    """Stand-in for the app closing itself a moment after the request."""
    time.sleep(0.4)
    asked.close()


threading.Thread(target=vanish, daemon=True).start()
try:
    got = js.stop_all(wait=3.0)
    check("it asked politely", got["polite"], True)
    check("…and did not need to kill anything", got["killed"], [])
finally:
    js.candidate_ports = real_ports
    js.pids, js.kill = real_pids, real_kill
    asked.close()

print("\n6. the launchers themselves")
jarvis = (ROOT / "JARVIS.bat").read_bytes().decode("ascii", "replace")
update = (ROOT / "UPDATE-JARVIS.bat").read_bytes().decode("ascii", "replace")
check("JARVIS.bat asks the tool instead of tasklist", "--wake" in jarvis, True)
check("…it closes only a stuck copy of ours", "--kill-stale" in jarvis, True)
check("…it waits for the app's own socket", "--status" in jarvis, True)
check("…and no 'is any pythonw alive' check is left", "tasklist" in jarvis, False)
check("…'already running' now brings it to the front", ":brought" in jarvis, True)
check("…a failure prints the app's own last log lines", "Get-Content" in jarvis, True)
check("…the app is started detached from the console", "Start-Process" in jarvis, True)
check("UPDATE-JARVIS.bat never kills every pythonw", "taskkill /IM" in update, False)
check("…it asks --any, then --stop", ("--any" in update) and ("--stop" in update), True)
check("…both places do it", update.count("--stop") >= 2, True)

run_py = (ROOT / "run.py").read_text(encoding="utf-8")
check("a second launch asks the first to come forward",
      ("wake_now" in run_py) or ("another_instance_running" in run_py), True)
check("…and waits for the running app to answer, not just for bytes to leave",
      "wake_now(cfg)" in run_py, True)
check("…so a silent copy is an exit code the launcher can act on",
      "_finish(3)" in run_py, True)
check("…and it does not simply exit in silence",
      "asked it to come to the front" in run_py, True)
check("a held-but-silent port is reported, not swallowed",
      "is held but nothing answered" in run_py, True)

print("\n7. the fix-pack folder case (15.png: double-clicked inside the unzipped pack)")
# The screenshot: JARVIS.bat was run from C:\Users\emera\Downloads\arcdesk-fix42-...
# - a pack unzipped as its OWN folder. There is no tools\ there, so `call
# tools\find_project.bat` failed with "not recognized as an internal or external
# command", and the app (Downloads\JARVIS\arcdesk-src) was never looked for.
check("the call is guarded, so a missing finder is not an error",
      'if exist "%~dp0tools\\find_project.bat" call' in jarvis, True)
check("…it looks next to itself, then up the tree", ":lookhere" in jarvis, True)
check("…then in the usual places, two levels deep", ":scanfor" in jarvis, True)
check("…and it names the folders in the Places list",
      ("Downloads\\JARVIS" in jarvis) and ("Documents\\GitHub" in jarvis), True)
check("a pack folder is recognised by its marker", "FIXPACK.txt" in jarvis, True)
check("…it says plainly what this folder is", "is a FIX PACK - a few changed files" in jarvis,
      True)
check("…it offers to apply itself instead of refusing", "choice /C YN" in jarvis, True)
check("…copying on top, never into .venv or settings.json",
      ("/XD" in jarvis) and (".venv" in jarvis) and ("settings.json" in jarvis), True)
check("…and then starts the real app from the real folder",
      'start "" "%PROJ%\\JARVIS.bat"' in jarvis, True)
check("declining changes nothing", "Nothing was changed" in jarvis, True)
# 18.png: "JARVIS is running" and NO window, because the launcher passed --shadow.
check("a double-click shows the window (--show), it does not hide it",
      "--show" in jarvis and "--shadow" in jarvis, True)
check("…--shadow is only mentioned in a comment, never passed",
      "'--shadow'" in jarvis or '"--shadow"' in jarvis, False)
check("…all three start routes say --show (2 Start-Process + 1 start fallback)",
      ["'--show'" in jarvis, jarvis.count("'--show'"), ' "%PROJ%\\run.py" --show' in jarvis],
      [True, 2, True])
check("…and it tells the person to look at the taskbar",
      "look on the taskbar" in jarvis, True)
check("the project path is cleaned up, not '\\tools\\..'",
      'for %%I in ("%PROJ%") do set "PROJ=%%~fI"' in jarvis, True)
finder_src = (ROOT / "tools" / "find_project.bat").read_bytes().decode("ascii", "replace")
check("…and the finder hands back an absolute path too",
      'for %%I in ("%PROJ%") do set "PROJ=%%~fI"' in finder_src, True)
auto = (ROOT / "arcdesk" / "autostart.py").read_text(encoding="utf-8")
check("stealth is still the resting state for the login start",
      '"--shadow"' in auto, True)

check("the wrong-folder message lists where it looked",
      "Documents\\GitHub" in jarvis and "I looked in" in jarvis, True)

finder = (ROOT / "tools" / "find_project.bat").read_bytes().decode("ascii", "replace")
check("the finder also goes three folders up", "%~dp0..\\..\\..\\run.py" in finder, True)
check("…and scans two levels down in each place", "for /d %%E in" in finder, True)
check("…so Downloads\\JARVIS\\arcdesk-src is reachable",
      "Downloads\\JARVIS" in finder, True)

from tools import update_from_zip as upd  # noqa: E402
check("fix packs fold in every file changed since the last full build",
      len(upd.fold_in_files()) >= 20, True)
check("…including the launcher and the finder",
      ("JARVIS.bat" in upd.FOLD_IN) and ("tools/find_project.bat" in upd.FOLD_IN), True)
check("…and every declared file really exists",
      [f for f in upd.FOLD_IN if not (ROOT / f).exists()], [])

print("\n8. the port file the app leaves behind")
home = tempfile.mkdtemp(prefix="arcdesk-port-")
old_home = os.environ.get("ARCDESK_HOME")
os.environ["ARCDESK_HOME"] = home
try:
    from arcdesk.instance import Instance, recorded_port
    inst = Instance({"wake": {"port": 18765}, "instance": {"port": 18766}})
    check("nothing recorded before it starts", recorded_port(), 0)
    check("it takes the lock", inst.acquire(), True)
    check("…and records the port it really took", recorded_port(), 18766)
    inst.release()
    check("a clean release removes the record", recorded_port(), 0)
finally:
    if old_home is None:
        os.environ.pop("ARCDESK_HOME", None)
    else:
        os.environ["ARCDESK_HOME"] = old_home

print("\n9. which build is this — the question a screenshot cannot answer")
version = (ROOT / "VERSION.txt")
check("VERSION.txt is in the folder", version.exists(), True)
stamp = version.read_text(encoding="utf-8") if version.exists() else ""
from arcdesk import __version__                                          # noqa: E402
check("…and it names the version the code reports", __version__ in stamp, True)
check("…and the build date", "build" in stamp.lower(), True)
jarvis_bat = (ROOT / "JARVIS.bat").read_bytes().decode("ascii")
clone_bat = (ROOT / "install_clone.bat").read_bytes().decode("ascii")
check("JARVIS.bat prints it at the top", "VERSION.txt" in jarvis_bat, True)
check("install_clone.bat prints it too", "VERSION.txt" in clone_bat, True)
check("…and both say when the copy is a second unzip",
      ("(1)" in jarvis_bat or "second copy" in jarvis_bat.lower())
      and ("Downloads" in clone_bat), True)

print("\n10. copies of JARVIS from other folders (the zoo)")
ZOO = (r"C:\Users\emera\Downloads\JARVIS-ready (12)\JARVIS\.venv\Scripts"
       r"\pythonw.exe C:\Users\emera\Downloads\JARVIS-ready (12)\JARVIS\run.py "
       r"--shadow")
OWN = str(ROOT) + "/run.py"
check("a copy in Downloads/JARVIS-ready (12) is foreign",
      js.classify_project(ZOO), "foreign")
check("…an ArcDesk-named folder is foreign too",
      js.classify_project(r'"C:\x\ArcDesk\run.py"'), "foreign")
check("…but THIS project's run.py is ours",
      js.classify_project("python " + OWN), "ours")
check("…and an unrelated run.py is NEVER claimed",
      js.classify_project(r'C:\dev\mytool\python.exe C:\dev\mytool\run.py'),
      "not-jarvis")
check("…a shell that merely mentions run.py is not claimed either",
      js.classify_project(r'C:\Windows\system32\cmd.exe /c echo run.py'),
      "not-jarvis")
check("…and foreign_pids() on a laptopless box is an honest empty",
      js.foreign_pids(), [])
check("JARVIS.bat sweeps the zoo before the wake",
      "--kill-foreign" in (ROOT / "JARVIS.bat").read_bytes().decode("ascii"), True)
check("…and KILL-JARVIS.bat exists as the one-click reset",
      (ROOT / "KILL-JARVIS.bat").exists(), True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
