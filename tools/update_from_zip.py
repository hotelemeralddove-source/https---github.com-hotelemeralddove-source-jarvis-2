#!/usr/bin/env python3
r"""Update this copy of JARVIS from one downloaded zip — the same job as
UPDATE-JARVIS.bat, written in the language the app already speaks.

Why both exist: the .bat version failed on a real laptop with

    Unable to find type [IO.Compression.ZipFile]

which is a PowerShell quirk, not a broken download — and it made the app refuse a
perfectly good zip. python's zipfile cannot have that problem, and this route is also
what JARVIS itself can call: "update yourself" becomes a tool, not a set of clicks.

    python tools/update_from_zip.py                    # find the newest zip yourself
    python tools/update_from_zip.py C:\path\new.zip   # or point at one
    python tools/update_from_zip.py --check            # say what it would do
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Never overwritten by an update: the environment, and anything the person changed.
KEEP_TOP = {".venv", "__pycache__", ".git", ".failures", "shots"}
KEEP_NAMES = {"settings.json"}
#: A fix pack is a few files that belong INSIDE the project. Applying one is a copy, not
#: an error - which is what the first version of this tool got wrong: it searched for
#: `arcdesk-fix*.zip`, found one, and then refused it. Offering something you will refuse
#: is worse than not offering it.
FIXPACK_MARKER = "FIXPACK.txt"


def classify(zip_path: Path) -> tuple[str, str]:
    """Is this the whole app, a fix pack, or something else? ("app"|"fixpack"|"unknown").

    * **app** — `run.py` and `requirements.txt` at the root: replace the project.
    * **fixpack** — no `run.py`, but it carries FIXPACK.txt, or its files are files this
      project already has (e.g. `arcdesk/...`, `tools/...`, `*.bat`): copy ON TOP.
    * **unknown** — neither. Refuse, and say why.
    """
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = [n for n in z.namelist() if not n.endswith("/")]
    except Exception as exc:                                     # noqa: BLE001
        return "unknown", f"cannot read the zip: {exc}"
    if "run.py" in names and "requirements.txt" in names:
        return "app", f"{len(names)} files, including run.py"
    if FIXPACK_MARKER in names:
        return "fixpack", f"{len(names)} files, a fix pack for this project"
    # Legacy fix packs (built before the marker existed): a file we already have here is
    # proof enough that it belongs inside the project.
    known = 0
    for name in names:
        if (ROOT / name).exists():
            known += 1
    if known >= 2 and "run.py" not in names:
        return "fixpack", (f"{len(names)} files, {known} of which this project already "
                           f"has - a fix pack")
    return "unknown", ("no run.py at the top and nothing in it belongs to this project — "
                       "this does not look like an ArcDesk download at all")


def looks_like_app(zip_path: Path) -> tuple[bool, str]:
    """Kept for callers that only care whether it is the whole app."""
    kind, why = classify(zip_path)
    return kind == "app", why


def find_zip() -> Path | None:
    """The newest ArcDesk download — but a whole-app zip always wins over a fix pack.

    If both exist, the full project wins even when the fix pack is newer: replacing the
    project with the app is always right, and a fix pack applied over an older base is
    usually not what the person meant.
    """
    home = Path.home()
    places = [ROOT, ROOT.parent, home / "Downloads", home / "Desktop",
              home / "OneDrive" / "Desktop"]
    apps: list[Path] = []
    fixes: list[Path] = []
    for place in places:
        try:
            apps += [p for p in place.glob("ArcDesk-full-project*.zip") if p.is_file()]
            fixes += [p for p in place.glob("arcdesk-fix*.zip") if p.is_file()]
        except OSError:
            continue
    for group in (apps, fixes):
        group[:] = [p for p in group if p.resolve() != Path(__file__).resolve()]
    pool = apps or fixes
    if not pool:
        return None
    return max(pool, key=lambda p: p.stat().st_mtime)


def stop_running_app() -> str:
    """Close the app so its files are not locked. Never fatal."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/IM", "pythonw.exe", "/F"],
                           capture_output=True, timeout=15)
            return "asked any running JARVIS to close"
        except Exception as exc:                                 # noqa: BLE001
            return f"could not close the app ({exc}) — copy anyway"
    return "no app to close on this platform"


# --------------------------------------------------------------- fold-in zips
# The report, again: "fix pack ah download pannen, update pannala". A fix pack replaces a
# HANDFUL of files that changed in ONE round, so applying fix37 to an old project, then
# fix38, then ... is not an update - it is a stack, and a person who skips one keeps the
# bug the later ones assume is gone. Every pack therefore folds in the files changed since
# the app that was last shipped as a whole, and this list says which ones that is.
#
# Rule when adding a round: append its files here, and keep the fix-pack script's
# --files list equal to this list (tests/test_update.py checks it).
FOLD_IN = [
    # fix37 - one install route (the files that actually exist in the tree)
    "WHICH-ROUTE.md",
    # fix38/39 - an updater that reads both kinds of zip
    "tools/update_from_zip.py", "UPDATE-JARVIS.bat", "tools/make_fixpack.py",
    "tests/test_update.py", "tests/test_installer_bootstrap.py", "tests/test_docs.py",
    # fix40 - use an engine you already installed
    "arcdesk/engines.py", "arcdesk/clone.py", "arcdesk/widgets/engine_dialog.py",
    # fix41 - installing an engine cannot close the app
    "arcdesk/piper_engine.py", "arcdesk/logs.py", "arcdesk/ai/voice.py",
    "tests/test_engine_progress.py", "tests/test_engines.py", "tests/test_install_safe.py",
    # fix42 - the launcher answers the right question
    "run.py", "arcdesk/instance.py", "tools/jarvis_state.py",
    "tests/test_launcher_state.py",
    # fix43 - a pack folder finds the app and offers to apply itself
    "JARVIS.bat", "tools/find_project.bat",
    # fix44 - the magic screen explains itself; one folder, one thing to click
    "arcdesk/widgets/magicscreen.py", "tools/one_place.py", "tests/test_one_place.py",
    "ONE-FOLDER.md",
    # fix45 - "which files are the correct ones?": ask the running app
    "tools/jarvis_state.py", "ONE-PLACE.bat", "CHECK-BEFORE-DELETE.bat",
    "arcdesk/uiwork.py", "arcdesk/blockguard.py", "arcdesk/widgets/engine_dialog.py",
    "arcdesk/widgets/voicelib_dialog.py", "arcdesk/widgets/brain_dialog.py",
    "arcdesk/widgets/aisetup.py", "arcdesk/widgets/welcome.py",
    "tests/test_no_freeze.py", "tests/test_ui_never_blocks.py",
    "tests/test_install_clone_bat.py", "tools/engine_get.py", "install_clone.bat",
    # fix46 - a pack folder applies through the updater; no "%~dp0" handed to robocopy
    "tools/batlint.py",
    # fix48 - Settings must never hang
    "arcdesk/widgets/settings.py", "tests/test_ui_never_blocks.py",
    # docs that move with all of the above
    "TROUBLESHOOT.md", "CAPABILITIES.md", "WHATS_INCLUDED.md",
]


def fold_in_files(root: Path | None = None) -> list[str]:
    """The file list a fix pack must contain to bring an old project up to date."""
    root = root or ROOT
    return [f for f in FOLD_IN if (root / f).exists()]


def copy_over(zip_path: Path, dry_run: bool = False, kind: str | None = None) -> dict:
    """Unpack into a scratch folder, then copy over the project, skipping .venv.

    Both kinds are applied the same way — the whole app replaces the files, a fix pack
    replaces only the files it contains. The only difference is the sanity check: a zip
    that claims to be the app must unpack to a folder with `run.py` in it.
    """
    kind = kind or classify(zip_path)[0]
    written = skipped = 0
    scratch = Path(tempfile.mkdtemp(prefix="jarvis-update-"))
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(scratch)
        if kind == "app" and not (scratch / "run.py").exists():
            return {"ok": False, "why": "the zip did not unpack to a project"}
        for item in scratch.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(scratch)
            if rel.parts and rel.parts[0] in KEEP_TOP:
                skipped += 1
                continue
            if item.name in KEEP_NAMES or item.suffix == ".pyc":
                skipped += 1
                continue
            target = ROOT / rel
            if dry_run:
                written += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
            written += 1
        return {"ok": True, "written": written, "skipped": skipped}
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "why": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def copy_folder_over(source: Path, dry_run: bool = False) -> dict:
    r"""Apply an unzipped FIX PACK folder onto this project — the tested path.

    Why this exists: JARVIS.bat's pack branch used `robocopy "%~dp0" ...`, and `%~dp0`
    ends with a backslash, so `"C:\...\pack\"` escaped its own closing quote and robocopy
    got the whole line as ONE argument:

        ERROR : Invalid Parameter #1 : "C:\...\arcdesk-fix45-..."  (screenshot 17.png)

    Fixed twice over: the batch no longer passes a trailing-backslash path, and this
    function is what it calls, so an unzipped pack goes through the same skip rules as a
    zip (.venv, settings.json, FIXPACK.txt, README-FIX*, *.pyc).
    """
    source = Path(source)
    if not source.is_dir():
        return {"ok": False, "why": f"{source} is not a folder"}
    if not (source / "FIXPACK.txt").exists() and not any(
            (source / name).exists() for name in ("run.py", "arcdesk")):
        return {"ok": False, "why": "that folder does not look like a fix pack"}
    written = skipped = 0
    try:
        for item in source.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(source)
            if rel.parts and rel.parts[0] in KEEP_TOP:
                skipped += 1
                continue
            if item.name in KEEP_NAMES or item.suffix == ".pyc":
                skipped += 1
                continue
            if item.name == FIXPACK_MARKER or item.name.upper().startswith("README-FIX"):
                skipped += 1
                continue
            target = ROOT / rel
            if dry_run:
                written += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
            written += 1
        return {"ok": True, "written": written, "skipped": skipped}
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "why": f"{type(exc).__name__}: {exc}"}


def top_up_libraries() -> str:
    """Install anything new in requirements.txt — only when it actually changed."""
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        return "no .venv here, so nothing to top up (JARVIS.bat builds one)"
    stamp_file = ROOT / ".venv" / ".reqstamp"
    req = ROOT / "requirements.txt"
    stamp = f"{req.stat().st_size}-{int(req.stat().st_mtime)}"
    if stamp_file.exists() and stamp_file.read_text(encoding="utf-8").strip() == stamp:
        return "libraries unchanged"
    done = subprocess.run([str(python), "-m", "pip", "install", "--quiet", "-r", str(req)],
                          capture_output=True, text=True, timeout=900)
    if done.returncode == 0:
        stamp_file.write_text(stamp, encoding="utf-8")
        return "installed the libraries this version needs"
    return "the library update failed, but the app will still start"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Update JARVIS from one downloaded zip.")
    ap.add_argument("zip", nargs="?", help="the zip to apply (default: the newest found)")
    ap.add_argument("--check", action="store_true", help="say what would happen, change nothing")
    ap.add_argument("--no-restart", action="store_true", help="do not start JARVIS afterwards")
    ap.add_argument("--folder", default="",
                    help="apply an UNZIPPED fix pack folder (what JARVIS.bat uses)")
    args = ap.parse_args(argv[1:])

    if args.folder:
        result = copy_folder_over(Path(args.folder).expanduser(), dry_run=args.check)
        if not result.get("ok"):
            print(f"that folder could not be applied: {result.get('why')}")
            return 1
        if args.check:
            print(f"would write {result['written']} files, skip {result['skipped']}")
            return 0
        print(f"wrote {result['written']} files, skipped {result['skipped']} "
              f"(.venv and settings kept)")
        print(top_up_libraries())
        return 0

    target = Path(args.zip).expanduser() if args.zip else find_zip()
    if not target:
        print("No ArcDesk zip found. Download ArcDesk-full-project.zip, then run this again.")
        return 2
    print(f"update file    : {target}")
    kind, why = classify(target)
    if kind == "app":
        print(f"what it is     : the whole app — {why}")
    elif kind == "fixpack":
        print(f"what it is     : a FIX PACK — {why}")
        print("                 its files go on top of this project, which is exactly "
              "what a fix pack is for.")
    else:
        print(f"what it is     : not usable — {why}")
        print("\nNothing was changed. Download ArcDesk-full-project.zip (the whole app) "
              "or a fix pack for this project.")
        return 3
    if args.check:
        result = copy_over(target, dry_run=True, kind=kind)
        print(f"would write {result.get('written')} files, skip {result.get('skipped')} "
              f"(the .venv is never touched)")
        return 0 if result.get("ok") else 1

    print(stop_running_app())
    result = copy_over(target, kind=kind)
    if not result.get("ok"):
        print("Copying failed:", result.get("why"), "— the old version is untouched.")
        return 1
    print(f"wrote {result['written']} files, skipped {result['skipped']} "
          f"(.venv and settings kept)")
    print(top_up_libraries())
    if not args.no_restart:
        launcher = ROOT / "JARVIS.bat"
        if os.name == "nt" and launcher.exists():
            subprocess.Popen(["cmd", "/c", "start", "", str(launcher)], cwd=str(ROOT))
            print("started JARVIS again")
        else:
            print("start it with JARVIS.bat (this is not Windows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
