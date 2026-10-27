"""CHECK-BEFORE-DELETE.bat: what it promises before somebody deletes a folder.

The question it answers, word for word: *"ipo nan existing files and folders lan delete
panitu itha matum keep and use panikalama?"*  Yes - but only in the right order, and only
after seeing what is really in the old folder.

A .bat cannot be run here (no cmd.exe on this machine), so this test does the two things
that can be proven without one:

  1. **cmd will not trip over it** - the same linter the build runs (batlint), plus ASCII
     and CRLF, because `move` and `for` silently misread anything else;
  2. **it cannot delete, and cannot guess wrong** - every refusal path is read out of the
     file itself: the folder this file lives in, a folder that *contains* it, a drive
     root, a folder that is not JARVIS. Each one ends in `:nothing`, which changes
     nothing, and only a typed R reaches `move`.

The one thing this test cannot prove is that a rename succeeds on a real PC. It does not
need to: `move` is the last statement before a success message, and a failure there is
caught by `if errorlevel 1 goto :failed`, which is asserted below.

Run:  python tests/test_check_before_delete.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<62} {got!r}")


BAT = ROOT / "CHECK-BEFORE-DELETE.bat"
raw = BAT.read_bytes()
text = raw.decode("ascii", "replace")
lines = text.replace("\r\n", "\n").splitlines()


def body(label: str) -> str:
    """The lines of one label, up to the next label. A grep over the whole file lies."""
    out, inside = [], False
    for line in lines:
        if line.startswith(":"):
            inside = line.split()[0].lower() == ":" + label.lower()
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def section(label: str) -> str:
    """A label and its sub-labels (:rename, :rename_loop, :rename_do) as one block."""
    out, inside = [], False
    for line in lines:
        if line.startswith(":"):
            name = line.split()[0].lower()
            inside = name == ":" + label.lower() or name.startswith(":" + label.lower() + "_")
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def command_lines() -> list[str]:
    """Only lines whose FIRST word is a real command - prose may say 'delete' freely."""
    words = ("del", "erase", "rd", "rmdir", "move", "ren", "rename", "format", "xcopy",
             "robocopy", "deltree")
    return [ln.strip() for ln in lines
            if ln.strip().lower().split(" ")[0] in words]


print("1. cmd will not trip over it")
check("the file is here", BAT.exists(), True)
check("pure ASCII (cmd reads the rest as mojibake)", all(b < 128 for b in raw), True)
check("CRLF line endings", b"\r\n" in raw and b"\n\n" not in raw.replace(b"\r\n", b""), True)
from tools import batlint  # noqa: E402
check("batlint problems", batlint.lint(BAT), [])
check("…and the whole repo is still clean",
      [p.name for p in ROOT.rglob("*.bat")
       if not any(x in p.parts for x in (".venv", "dist", "build")) and batlint.lint(p)], [])

print("\n2. it never deletes anything")
check("no del / erase / rd / rmdir / format anywhere",
      [ln for ln in command_lines()
       if ln.split()[0].lower() in ("del", "erase", "rd", "rmdir", "format", "deltree")], [])
check("the only move is the rename to JARVIS-OLD",
      [ln for ln in command_lines() if ln.split()[0].lower() == "move"],
      ['move "!OLD!" "!DEST!" >nul 2>&1'])
moved_to = section("rename")
check("…and that name is JARVIS-OLD", '"DEST=%PARENT%\\JARVIS-OLD"' in moved_to, True)
check("a taken name falls back to JARVIS-OLD-2 … -9", "JARVIS-OLD-!N!" in moved_to, True)
check("…and gives up instead of overwriting after 9", "if !N! gtr 9 exit /b 1" in moved_to, True)
check("a failed rename is reported, never hidden",
      "if errorlevel 1 exit /b 1" in moved_to
      and "could not rename it" in body("failed"), True)

print("\n3. it refuses the folders that would do damage")
check("…and the trailing backslash %~dp0 carries is stripped first",
      'if "%HERE:~-1%"=="\\" set "HERE=%HERE:~0,-1%"' in text, True)
check("the folder this file lives in is refused",
      'if /i "!OLD!"=="!HERE!" goto :itself' in text, True)
check("…and says why", "the clean copy this file lives in" in body("itself"), True)
check("a folder that CONTAINS this one is refused",
      'set "INHERE=!HERE:%OLD%=!"' in text and "goto :contains" in text, True)
check("…by subtracting it from our own path, with no pipe to mis-parse",
      'if /i not "!INHERE!"=="!HERE!"' in text and "echo(!HERE!" not in text, True)
check("a drive root is refused", 'if /i "!OLD:~1!"==":\\" goto :toobig' in text, True)
check("a folder that is not JARVIS is refused",
      "goto :notjarvis" in text, True)
check("…checked by run.py or arcdesk/, not by the folder name",
      'if not exist "!OLD!\\run.py" if not exist "!OLD!\\arcdesk\\__init__.py" goto :notjarvis'
      in text, True)
for label in ("itself", "contains", "toobig", "notjarvis", "failed"):
    check(f":{label} ends in :nothing (nothing to undo)", "goto :nothing" in body(label), True)

print("\n4. nothing happens unless the answer is R")
check("anything that is not R stops", 'if /i not "!ANS!"=="R" goto :nothing' in text, True)
check("Enter with no folder given stops", "if not defined OLD goto :nothing" in text, True)
check(":nothing changes nothing",
      command_lines() and not [ln for ln in body("nothing").splitlines()
                               if ln.strip().lower().startswith(("move", "ren", "del", "rd"))],
      True)
check("the stop message says the clean copy is untouched",
      "nothing was changed" in body("nothing"), True)

print("\n5. it answers the real question first: what survives the folder")
check("%APPDATA%\\ArcDesk is the data folder it looks at", "%APPDATA%\\ArcDesk" in text, True)
for item, why in (("settings.json", "your settings"),
                  ("vault", "your notes and memory"),
                  ("voice", "your own voice clip"),
                  ("voices", "downloaded voice models")):
    check(f"it shows {item} survives ({why})", f'\\{item}"' in text, True)
check("…and prints where they live", "echo   in: %DATA%" in text, True)

print("\n6. it warns about the two things a delete would really cost")
check("voice engines hidden in the old .venv are listed by name",
      "piper onnx torch tts whisper coqui" in text, True)
check("…read from the old folder's site-packages",
      '"!OLD!\\.venv\\Lib\\site-packages"' in text, True)
check("files that are not part of JARVIS are listed",
      'if not exist "!HERE!\\%%~nxF"' in text, True)
check("…which is how 'your own clips, pdfs' get caught", "not part of JARVIS" in text, True)
check("a running app is called out before a rename", "pythonw.exe" in text, True)
check("the startup tick is called out after a rename", "tick" in text, True)

print("\n7. it is usable by a person in a hurry")
check("a dragged folder is accepted as %1", 'if not "%~1"==""' in text, True)
check("…and quotes pasted with a path are stripped", 'set OLD=%OLD:"=%' in text, True)
check("double-click mode looks in the usual places", "%USERPROFILE%\\Downloads\\JARVIS" in text,
      True)
check("it never claims a copy it did not find", "no second copy found" in text, True)
check("both letters are explained before the prompt", "R = rename" in text and "X = stop" in text,
      True)
check("it writes a log next to itself", "check-before-delete-log.txt" in text, True)

print("\n8. the folder it is shipped in tells the same order")
start = (ROOT / "START-HERE.txt").read_text(encoding="utf-8")
check("START-HERE lists it", "CHECK-BEFORE-DELETE.bat" in start, True)
check("…and says to run the new copy BEFORE tidying", "Run THIS folder once" in start, True)
check("…and says settings survive in %APPDATA%", "%APPDATA%\\ArcDesk" in start, True)
check("ONE-FOLDER.md still describes the tidy-up it belongs to",
      "ONE-PLACE.bat" in (ROOT / "ONE-FOLDER.md").read_text(encoding="utf-8"), True)

print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
raise SystemExit(0 if ok else 1)
