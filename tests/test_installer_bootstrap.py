"""One double-click must not need Python installed first.

The screenshot that made this file: `install.bat` on a laptop with no Python printed

    Python was not found; run without arguments to install from the Microsoft Store...
    [Arc Desk] setup failed. Is Python 3.10+ installed and on PATH?

That is the project's own rule being broken — "one-file, double-click, zero manual
dependency setup" — so `tools/pybootstrap.bat` now finds Python, or downloads the
official installer, and `install.bat` continues by itself.

These checks read the batch files as text (they only run on Windows) and hold three
promises:

  * the Microsoft Store stub is never accepted as a Python;
  * a missing Python is fetched from an official source, not pointed at;
  * a person is never left with a question and no route: if the download fails the
    script writes out the two-click fallback.

Run:  python tests/test_installer_bootstrap.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ok = True


def check(label: str, got, want=True) -> None:
    global ok
    good = got == want
    print(f"   {'OK  ' if good else 'FAIL'} {label:<58} {str(got)[:46]!r}")
    ok &= bool(good)


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


print("1. the bootstrap exists and is honest about what it does")
boot = read("tools/pybootstrap.bat")
check("tools/pybootstrap.bat is here", "pybootstrap" in boot.lower())
check("it explains the Store stub in a comment", "WindowsApps" in boot)
check("it checks the version, not just the name", "sys.version_info >= (3,10)" in boot)
check("an older Python is rejected", "raise SystemExit(0 if sys.version_info" in boot)

print("\n2. it never trusts the Store alias")
check("the WindowsApps path is skipped before a candidate is accepted",
      'find /i "WindowsApps"' in boot)
check("…and the check runs before the candidate is used",
      boot.index('find /i "WindowsApps"') < boot.index('%CAND% -c'))

print("\n3. a missing Python is fetched, not pointed at")
urls = re.findall(r"https://[^\s\"']+\.exe", boot)
check("it uses an official python.org installer", bool(urls) and "python.org" in urls[0])
check("the download URL and the version cannot drift apart",
      "%PYVER%" in boot and "python-%PYVER%-amd64.exe" in boot)
check("it tries the official package manager first", "winget install" in boot)
check("a silent per-user install (no admin password)", "/quiet InstallAllUsers=0" in boot)
check("PATH is updated so the next step finds it", "PrependPath=1" in boot)
check("it handles the installer's 3010 answer", "errorlevel 3010" in boot)
check("it reports the size it downloaded", "downloaded" in boot)

print("\n4. every installer calls it instead of assuming Python")
for name in ("install.bat", "install_voice.bat", "install_clone.bat"):
    src = read(name)
    check(f"{name} calls the bootstrap", "pybootstrap.bat" in src)
    check(f"{name} no longer asks the user for Python",
          "Is Python 3.10+ installed and on PATH?" in src, False)
    check(f"{name} stops when it really cannot continue", "goto :fail" in src)

print("\n5. failing safely: one route, printed, with the URL")
check("the fallback names the exact URL", "%PYURL%" in boot)
check("…and the one tick box that matters", "Add python.exe to PATH" in boot)
check("declining installs nothing and says so", ":declined" in boot)
check("the script returns a failure code the caller can act on", "exit /b 1" in boot)

print("\n6. the packaged app is still the answer for anyone who has it")
check("install.bat points that out when Python is refused", "ArcDesk.exe" in boot)

print("\n7. the right folder, or a clear message instead of a pip error")
# Screenshot: "ERROR: Could not open requirements file: requirements.txt" — the fix
# pack had been unzipped on its own, so pip was run in a folder that holds no project.
finder = read("tools/find_project.bat")
check("there is a finder", bool(finder))
check("it looks for the marker that cannot be faked (run.py next to requirements.txt)",
      "run.py" in finder and "requirements.txt" in finder)
check("it checks this folder first", '%~dp0run.py' in finder)
check("it checks the parent too (fix pack unzipped inside the project)",
      '%~dp0..' in finder)
check("it looks where GitHub Desktop puts clones",
      "Documents\\GitHub" in finder)
check("it finds nothing cleanly rather than guessing", "exit /b 1" in finder)

for name in ("install.bat", "install_voice.bat", "install_clone.bat"):
    src = read(name)
    check(f"{name} finds the project folder", "find_project.bat" in src)
    check(f"{name} moves into it", 'cd /d "%PROJ%"' in src)
    check(f"{name} checks the folder BEFORE building a venv",
          src.index("if not exist \"requirements.txt\"")
          < src.index("pip install"))
    check(f"{name} explains the mistake in plain words",
          ":wrongfolder" in src and "ArcDesk.exe" in src)
    # Only what the person SEES is judged; a REM may quote pip to explain the bug
    # (learning from the last round: never grep a file for a phrase you just wrote).
    shown = " ".join(line for line in src.splitlines()
                     if line.strip().lower().startswith("echo")).lower()
    check(f"{name} never shows pip's own wording", "could not open" in shown, False)

print("\n8. one file to give someone: JARVIS.bat")
jarvis = read("JARVIS.bat")
check("it exists and is the whole promise in one click", bool(jarvis))
check("it finds the project before doing anything", "find_project.bat" in jarvis)
check("it fetches Python itself", "pybootstrap.bat" in jarvis)
check("it builds the environment only when it is missing",
      r'if not exist "%PROJ%\.venv\pyvenv.cfg" goto :newvenv' in jarvis)
check("…and rebuilds a half-deleted one (python.exe kept, pyvenv.cfg lost)",
      'if not exist "%VPY%" goto :newvenv' in jarvis
      and r'rmdir /s /q "%PROJ%\.venv"' in jarvis)
check("…and a venv copied from another machine (Drive upload) is rebuilt, not trusted",
      '-c "import PySide6"' in jarvis
      and 'if errorlevel 1 goto :newvenv' in jarvis)
check("it installs from the project's own requirements", "-r requirements.txt" in jarvis)
commands = "\n".join(line for line in jarvis.splitlines()
                      if not line.strip().lower().startswith(("rem", "::")))
check("it starts without a console or a window (pythonw, no .vbs)",
      "pythonw.exe" in commands and "start_arcdesk.vbs" in commands, False)
check("…because a .vbs from a download triggers a Windows permission prompt",
      "mark of the web" in jarvis.lower())
check("it writes a log that outlives the window", "jarvis-start-log.txt" in jarvis)
# fix42: the "is any pythonw alive?" check is gone. It was true for other people's python
# programs and for our own stuck copy, so the launcher said "already running" and started
# nothing - the report "app open aagala". It asks the app itself now.
check("it does not treat an already-running app as a failure", ":brought" in jarvis)
check("it asks the app, not the process list", "jarvis_state.py" in jarvis)
check("…and never decides anything from tasklist", "tasklist" in jarvis, False)
check("it waits for the app's own lock socket", "--status" in jarvis)
check("it keeps the window open long enough to read", "timeout /t 15" in jarvis)

diag = read("JARVIS-DIAGNOSE.bat")
check("there is a visible-console diagnosis route", bool(diag))
check("…which prints the real error and waits", "pause" in diag and "run.py" in diag)
check("…and it is not stealth, so a window does appear", "--shadow" in diag, False)
check("a second double-click is fast, not a reinstall", jarvis.count("pybootstrap.bat"), 1)
check("failure stops and explains instead of pretending", ":fail" in jarvis)
check("the wrong folder is still handled", ":wrongfolder" in jarvis)
check("an update that adds a library is picked up on the next start",
      ".reqstamp" in jarvis and "pip install --quiet -r requirements.txt" in jarvis)
check("…and a failed top-up still starts the app", "starting anyway" in jarvis)

print("\n9. updating is ONE file, and it refuses the wrong one")
upd = read("UPDATE-JARVIS.bat")
check("there is one updater", bool(upd))
check("it finds the project first", "find_project.bat" in upd)
check("it looks for the zip where people actually leave it",
      "Downloads" in upd and "Desktop" in upd)
# A fix pack is APPLIED by the Python route (tools/update_from_zip.py decides); only the
# tar fallback, which has no project to patch, turns one away with an explanation.
check("the Python route is what decides what the zip is", "update_from_zip.py" in upd)
check("a zip with no run.py is explained, not silently applied",
      "fix pack belongs inside a project" in upd)
# The first version asked PowerShell to load a .NET type on demand and Windows said
# "Unable to find type [IO.Compression.ZipFile]" — refusing a perfectly good zip.
check("it does not depend on PowerShell loading a type on demand",
      'Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop' in upd)
check("…it unpacks with tar.exe, which is part of Windows 10 1803+", "tar.exe" in upd)
check("…and copies with robocopy, which is always there", "robocopy" in upd)
check("the zip check reads a listing file, not a nested-quoted pipe",
      "jarvis-zip-list.txt" in upd)
check("it stages in %TEMP% and keeps .venv out of the copy",
      "%TEMP%" in upd and "/XD \".venv\"" in upd)
check("if unpacking fails it offers the Explorer route",
      "copy the folder over this one" in upd)
check("it copies WITHOUT rebuilding .venv", ".venv" in upd and "venv .venv" not in upd)
check("…and it says so in words", "left alone" in upd)
check("it closes the running app first, or the files are locked",
      "jarvis_state.py" in upd and "--stop" in upd)
check("…and only OUR app, never every pythonw", "taskkill /IM" in upd, False)
check("it tops up libraries only when requirements.txt changed", ".reqstamp" in upd)
check("it starts the app afterwards", "JARVIS.bat" in upd)
check("a failed copy leaves the old version working", "still there" in upd)

print("\n10. the check.bat doctor ends with something a person can act on")
chk = read("check.bat")
check("it counts the failures", "FAILS+=1" in chk)
check("…and summarises instead of dumping", "EVERYTHING PASSED" in chk)
check("it points at the per-test details", ".failures" in chk)
check("it says which file is the app, not the doctor", "JARVIS.bat" in chk)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
