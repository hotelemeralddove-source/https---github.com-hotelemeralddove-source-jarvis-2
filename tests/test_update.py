"""Updating is one file — and it must never need PowerShell to load a type.

The real failure, from a laptop:

    Unable to find type [IO.Compression.ZipFile].
    ...
    That zip is not the app: it has no run.py in it.

A perfectly good `ArcDesk-full-project.zip` was refused because the first version of the
updater asked PowerShell to open the zip. These checks make that impossible to repeat:

  1. a full project zip is recognised, a fix pack is refused with a reason;
  2. `--check` writes nothing at all;
  3. a real copy puts the files in place, and never touches `.venv` or settings;
  4. the newest download is found by itself (Downloads/Desktop), newest first;
  5. the .bat prefers the app's own Python, and only falls back to tar/robocopy;
  9. an UNZIPPED fix pack folder is applied by the tested code path, and no launcher ever
     passes "%~dp0" (which ends in a backslash) to robocopy — that is "Invalid Parameter
     #1" on the screenshot.

Run:  python tests/test_update.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import update_from_zip as upd  # noqa: E402

ok = True


def check(label, got, want=True):
    global ok
    good = got == want
    ok = ok and good
    print(("   OK   " if good else "   FAIL ") + f"{label:<58} {got!r}")
    return good


def make_zip(path: Path, entries: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in entries.items():
            z.writestr(name, body)
    return path


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="arc-update-"))
    good_zip = make_zip(work / "ArcDesk-full-project.zip", {
        "run.py": "print('the app')\n",
        "requirements.txt": "PySide6-Essentials\n",
        "arcdesk/__init__.py": "",
        "NEW-FILE.md": "a file this version adds\n",
        ".venv/marker.txt": "must never be copied\n",
        "settings.json": "must never be copied\n",
    })
    fix_zip = make_zip(work / "arcdesk-fix99.zip", {
        "install.bat": "echo hi\n",
        "tools/pybootstrap.bat": "echo hi\n",
    })

    print("1. is this the app, or a fix pack?")
    ok_a, why_a = upd.looks_like_app(good_zip)
    check("a full zip is recognised", (ok_a, "run.py" in why_a), (True, True))
    ok_b, why_b = upd.looks_like_app(fix_zip)
    check("a fix pack is not the whole app", ok_b, False)
    check("…but it is still recognised as ours, to be applied on top",
          upd.classify(fix_zip)[0], "fixpack")
    broken = work / "broken.zip"
    broken.write_bytes(b"not a zip at all")
    check("a corrupt file is refused, not crashed on",
          upd.classify(broken)[0], "unknown")

    print("\n2. --check changes nothing")
    project = work / "project"
    project.mkdir()
    (project / "run.py").write_text("print('the old app')\n", encoding="utf-8")
    (project / "requirements.txt").write_text("PySide6-Essentials\n", encoding="utf-8")
    before = {p.name: p.stat().st_mtime_ns for p in project.rglob("*") if p.is_file()}

    real_root = upd.ROOT
    upd.ROOT = project                                   # point the tool at a pretend app
    try:
        result = upd.copy_over(good_zip, dry_run=True)
        after = {p.name: p.stat().st_mtime_ns for p in project.rglob("*") if p.is_file()}
        check("the plan counts the files it would write", result.get("written"), 4)
        check("…and nothing on disk changed", before, after)
        check("…and the old run.py is untouched",
              (project / "run.py").read_text(encoding="utf-8"), "print('the old app')\n")

        print("\n3. a real copy: new files in, .venv and settings left alone")
        (project / ".venv").mkdir()
        (project / ".venv" / "marker.txt").write_text("keep me", encoding="utf-8")
        (project / "settings.json").write_text('{"mine": true}', encoding="utf-8")
        result = upd.copy_over(good_zip)
        check("it reports success", result.get("ok"), True)
        check("run.py was replaced", (project / "run.py").read_text(encoding="utf-8"),
              "print('the app')\n")
        check("a new file arrived", (project / "NEW-FILE.md").exists())
        check("the environment survived",
              (project / ".venv" / "marker.txt").read_text(encoding="utf-8"), "keep me")
        check("settings were not touched",
              (project / "settings.json").read_text(encoding="utf-8"), '{"mine": true}')
        check("the zip's own .venv was refused",
              (project / ".venv" / "marker.txt").read_text(encoding="utf-8") !=
              "must never be copied", True)
    finally:
        upd.ROOT = real_root

    print("\n4. it finds the download by itself")
    # a self-contained world: the fake home has the zips, the fake project has none,
    # so the real /home/user zips cannot win the "newest" race
    sandbox = Path(tempfile.mkdtemp(prefix="arc-world-"))
    home = sandbox / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Desktop").mkdir()
    fake_project = sandbox / "project"
    fake_project.mkdir()
    older = make_zip(home / "Downloads" / "ArcDesk-full-project.zip", {"run.py": "old"})
    newer = make_zip(home / "Downloads" / "ArcDesk-full-project (6).zip", {"run.py": "new"})
    os.utime(older, (1_600_000_000, 1_600_000_000))
    os.utime(newer, (1_700_000_000, 1_700_000_000))
    real_home, real_root = Path.home, upd.ROOT
    try:
        upd.Path.home = classmethod(lambda cls: home)     # type: ignore[assignment]
        upd.ROOT = fake_project
        found = upd.find_zip()
        check("the newest download wins", found and found.name.endswith("(6).zip"), True)
        check("…and it is the one with the (6) in its name, as Windows saves it",
              found and "(6)" in found.name, True)
    finally:
        upd.Path.home = real_home                         # type: ignore[assignment]
        upd.ROOT = real_root

    print("\n5. the command line behaves like a person expects")
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "update_from_zip.py"),
                          "--check", str(fix_zip)],
                         capture_output=True, text=True, timeout=120)
    check("--check on a fix pack succeeds and changes nothing", out.returncode, 0)
    check("…and it says it is a fix pack, in words",
          "FIX PACK" in (out.stdout or ""))
    junk_zip = make_zip(work / "holiday.zip", {"a.jpg": "x"})
    out2 = subprocess.run([sys.executable, str(ROOT / "tools" / "update_from_zip.py"),
                           "--check", str(junk_zip)],
                          capture_output=True, text=True, timeout=120)
    check("a zip that is not ours exits with a code, not a traceback", out2.returncode, 3)
    check("…and says what to download instead",
          "ArcDesk-full-project.zip" in (out2.stdout or ""))
    check("no traceback in the output", "Traceback" in (out.stdout or ""), False)

    print("\n6. the .bat prefers Python, and does not need PowerShell")
    bat = (ROOT / "UPDATE-JARVIS.bat").read_text(encoding="utf-8", errors="replace")
    check("it calls the app's own Python first", "update_from_zip.py" in bat)
    check("…only then the tar/robocopy route", bat.index("update_from_zip.py") <
          bat.index(":fallback"))
    check("a missing PowerShell type can no longer refuse a good zip",
          "Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop" in bat)
    check("the fallback explains that a fix pack needs an existing project",
          "fix pack belongs inside a project" in bat)

    print("\n7. a fix pack is APPLIED, not refused (the bug you just hit)")
    # Screenshot: the updater found arcdesk-fix38-...zip, then said "that zip is not the
    # app: there is no run.py inside it". Offering what you will refuse is the fault.
    marker_fix = make_zip(work / "arcdesk-fix40.zip", {
        "FIXPACK.txt": "KIND=fixpack\n",
        "arcdesk/__init__.py": "# newer\n",
    })
    kind, why = upd.classify(marker_fix)
    check("a marked fix pack is recognised as a fix pack", kind, "fixpack")
    check("…and it is not mistaken for the whole app", "run.py" in why, False)

    legacy_fix = make_zip(work / "arcdesk-fix41.zip", {
        "run.py": "print('the app')\n", "requirements.txt": "x\n",
    })
    check("a zip that really is the app is still 'app'", upd.classify(legacy_fix)[0], "app")

    junk = make_zip(work / "holiday-photos.zip", {"DCIM/a.jpg": "x", "b.jpg": "y"})
    check("a zip that is not ours is refused", upd.classify(junk)[0], "unknown")

    real_root = upd.ROOT
    upd.ROOT = project
    try:
        # an unmarked fix pack whose files this project already has
        legacy = make_zip(work / "arcdesk-fix42.zip", {
            "arcdesk/__init__.py": "# from a fix pack\n",
            "requirements.txt": "PySide6-Essentials\n",
        })
        check("…an unmarked one is still spotted by the files it shares",
              upd.classify(legacy)[0], "fixpack")
        result = upd.copy_over(legacy, kind="fixpack")
        check("a fix pack is copied on top", result.get("ok"), True)
        check("…its files really landed",
              (project / "arcdesk" / "__init__.py").read_text(encoding="utf-8"),
              "# from a fix pack\n")
        check("…and run.py was NOT deleted by it", (project / "run.py").exists())
        check("…nor was .venv touched",
              (project / ".venv" / "marker.txt").read_text(encoding="utf-8"), "keep me")
    finally:
        upd.ROOT = real_root

    print("\n8. choosing between an app zip and a fix pack")
    sandbox2 = Path(tempfile.mkdtemp(prefix="arc-world2-"))
    home2 = sandbox2 / "home"
    (home2 / "Downloads").mkdir(parents=True)
    app_zip = make_zip(home2 / "Downloads" / "ArcDesk-full-project.zip",
                       {"run.py": "x", "requirements.txt": "y"})
    fix_new = make_zip(home2 / "Downloads" / "arcdesk-fix43.zip", {"FIXPACK.txt": "k"})
    os.utime(app_zip, (1_600_000_000, 1_600_000_000))
    os.utime(fix_new, (1_700_000_000, 1_700_000_000))     # newer, but a fix pack
    real_home, real_root = Path.home, upd.ROOT
    empty = sandbox2 / "empty"
    empty.mkdir()
    try:
        upd.Path.home = classmethod(lambda cls: home2)     # type: ignore[assignment]
        upd.ROOT = empty
        found = upd.find_zip()
        check("the whole app wins even when a fix pack is newer",
              found and found.name == "ArcDesk-full-project.zip", True)
    finally:
        upd.Path.home = real_home                          # type: ignore[assignment]
        upd.ROOT = real_root

    print("\n9. an UNZIPPED fix pack folder (screenshot 17.png)")
    # The pack branch of JARVIS.bat ran
    #     robocopy "%~dp0" "%PROJ%" ...
    # and %~dp0 ends with a backslash, so "C:\...\pack\" escaped its own closing quote
    # and robocopy answered "ERROR : Invalid Parameter #1". Two fixes, both checked here:
    # the batch passes a path without the trailing backslash, and it uses THIS function.
    project2 = work / "project2"
    project2.mkdir()
    (project2 / "run.py").write_text("print('old')\n", encoding="utf-8")
    (project2 / "requirements.txt").write_text("PySide6-Essentials\n", encoding="utf-8")
    (project2 / ".venv").mkdir()
    (project2 / ".venv" / "marker.txt").write_text("keep me", encoding="utf-8")
    (project2 / "settings.json").write_text('{"mine": true}', encoding="utf-8")

    pack = work / "arcdesk-fix45-one-place-and-correct-files"
    (pack / "arcdesk" / "widgets").mkdir(parents=True)
    (pack / "FIXPACK.txt").write_text("KIND=fixpack\nNAME=fix45\n", encoding="utf-8")
    (pack / "README-FIX45.txt").write_text("notes", encoding="utf-8")
    (pack / "JARVIS.bat").write_text("@echo off\r\n", encoding="utf-8")
    (pack / "arcdesk" / "widgets" / "magicscreen.py").write_text("# new web\n",
                                                                 encoding="utf-8")
    (pack / "ONE-PLACE.bat").write_text("@echo off\r\n", encoding="utf-8")
    (pack / "settings.json").write_text('{"theirs": true}', encoding="utf-8")

    real_root2 = upd.ROOT
    upd.ROOT = project2
    try:
        dry = upd.copy_folder_over(pack, dry_run=True)
        check("a plan is printed", dry.get("ok"), True)
        # three: the code, JARVIS.bat and ONE-PLACE.bat. Not FIXPACK.txt, not the README,
        # and never settings.json
        check("…counting only the files that belong on top", dry.get("written"), 3)
        check("…and it writes nothing yet",
              (project2 / "arcdesk").exists(), False)

        got = upd.copy_folder_over(pack)
        check("the pack is applied", got.get("ok"), True)
        check("its code landed",
              (project2 / "arcdesk" / "widgets" / "magicscreen.py").read_text(
                  encoding="utf-8"), "# new web\n")
        check("its launcher landed", (project2 / "JARVIS.bat").exists())
        check("the marker is NOT copied into the project",
              (project2 / "FIXPACK.txt").exists(), False)
        check("nor its README", (project2 / "README-FIX45.txt").exists(), False)
        check("settings.json is never overwritten",
              (project2 / "settings.json").read_text(encoding="utf-8"), '{"mine": true}')
        check("the .venv is untouched",
              (project2 / ".venv" / "marker.txt").read_text(encoding="utf-8"), "keep me")
        check("run.py survived", (project2 / "run.py").exists())

        junk = work / "holiday-photos"
        junk.mkdir()
        (junk / "beach.jpg").write_text("x", encoding="utf-8")
        check("a folder that is not a pack is refused",
              upd.copy_folder_over(junk).get("ok"), False)
        check("…and says why",
              "does not look like a fix pack" in upd.copy_folder_over(junk).get("why", ""),
              True)
    finally:
        upd.ROOT = real_root2

    print("\n10. the launchers never pass a path that ends in a backslash")
    import re as _re
    from pathlib import Path as _P
    bad = []
    for bat in sorted((ROOT).glob("*.bat")):
        text = bat.read_bytes().decode("ascii", "replace")
        for number, line in enumerate(text.splitlines(), 1):
            low = line.strip().lower()
            if not low.startswith(("robocopy", "xcopy", "copy ", "move ", "python",
                                   "powershell", "start ")):
                continue
            if '"%~dp0"' in line:
                bad.append(f"{bat.name}:{number}")
    check("no .bat hands %~dp0 (trailing backslash) to a command", bad, [])
    jarvis = (ROOT / "JARVIS.bat").read_bytes().decode("ascii", "replace")
    check("the pack branch strips the trailing backslash", 'if "%SRC:~-1%"=="\\"' in jarvis,
          True)
    check("…and applies through the tested updater", '--folder "%SRC%"' in jarvis, True)
    check("…with robocopy only as the fallback", "robocopy \"%SRC%\" " in jarvis, True)

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES ABOVE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
