#!/usr/bin/env python3
"""Carry ARC to another laptop — without carrying the wrong things.

    python tools/move.py check
    python tools/move.py pack   D:\\arcdesk-carry          # a folder
    python tools/move.py pack   D:\\arcdesk-carry.zip      # or one file
    python tools/move.py unpack D:\\arcdesk-carry

What goes into a package, and what deliberately does not:

| kept | why |
|---|---|
| `settings.json` | your prefs — **API keys stripped** unless `--with-keys` |
| `vault/` | your projects, notes and progress: the actual work |
| `voice/` | the clone reference clip + its transcript |
| `profile.json`, `reminders.json`, `focus.json`, `magic_journal.json` | your personal context |
| `notes`, `macros`, `knows` | what it learned about you |

| left behind | why |
|---|---|
| `voiceid/` | **a voice lock is per machine** — laptop B enrols whoever uses it |
| `models/`, HF caches | 2–4 GB of weights; re-downloaded by the installer, not copied |
| `logs/`, `weather_cache.json`, `file_index.json` | this machine's noise, useless there |
| `generated/`, `photos/`, `art/` | can be gigabytes; opt in with `--with-media` |

The one thing this cannot do: **build the .exe.** PyInstaller does not cross-compile,
so the installer is produced on a Windows machine (`packaging\\build_all.bat`) and this
package carries your *data*, not the program.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arcdesk import config  # noqa: E402

PACK_VERSION = 1
MANIFEST = "arcdesk-carry.json"

# directories copied whole
KEEP_DIRS = ["vault", "voice"]
# single files copied when they exist
KEEP_FILES = ["profile.json", "reminders.json", "focus.json", "magic_journal.json",
              "nudges.json", "watchlist.json"]
# skipped on purpose, with the reason shown to the user
SKIP_DIRS = {
    "voiceid": "voice lock is per machine — enroll again on the new laptop",
    "models": "2-4 GB of model weights; the installer fetches them",
    "logs": "this machine's logs",
    "library": "media index for this machine's files",
    "studio": "rendered work, usually large",
    "work": "renders",
    "craft": "cache",
    "coach": "cache",
}
MEDIA_DIRS = ["art", "generated", "photos"]
# settings keys that are secrets, not preferences
SECRET_PATHS = [("ai", "api_key")]


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def _strip_secrets(data: dict) -> tuple[dict, list[str]]:
    data = json.loads(json.dumps(data))
    removed = []
    for section, key in SECRET_PATHS:
        block = data.get(section)
        if isinstance(block, dict) and block.get(key):
            block[key] = ""
            removed.append(f"{section}.{key}")
    return data, removed


def collect(with_media: bool = False) -> dict:
    """What would be packed right now. No side effects — used by pack() and check()."""
    home = config.data_dir()
    items: list[tuple[Path, str]] = []
    for name in KEEP_DIRS:
        p = home / name
        if p.exists():
            items.append((p, name))
    for name in KEEP_FILES:
        p = home / name
        if p.exists():
            items.append((p, name))
    if with_media:
        for name in MEDIA_DIRS:
            p = home / name
            if p.exists():
                items.append((p, name))
    total = sum(_size(p) for p, _ in items)
    return {"home": home, "items": items, "total": total,
            "skipped": [d for d in SKIP_DIRS if (home / d).exists()]}


def pack(dest: str, with_media: bool = False, with_keys: bool = False) -> dict:
    target = Path(dest).expanduser()
    plan = collect(with_media)
    if not plan["items"]:
        return {"ok": False, "message": "there is nothing to pack yet — ARC has never run "
                                        "with your data in this folder"}

    zip_mode = target.suffix.lower() == ".zip"
    stage = target.with_suffix(".staging") if zip_mode else target
    if stage.exists() and not zip_mode:
        return {"ok": False, "message": f"{stage} already exists — pick a new folder name"}
    stage.mkdir(parents=True, exist_ok=True)

    settings = config.load()
    removed: list[str] = []
    if not with_keys:
        settings, removed = _strip_secrets(settings)
    (stage / "settings.json").write_text(json.dumps(settings, indent=1), encoding="utf-8")

    copied = {"settings.json": _size(stage / "settings.json")}
    for src, name in plan["items"]:
        dst = stage / name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copyfile(src, dst)
        copied[name] = _size(dst)

    manifest = {
        "pack_version": PACK_VERSION,
        "created": __import__("time").strftime("%Y-%m-%d %H:%M"),
        "from_host": os.uname().nodename if hasattr(os, "uname") else os.getenv("COMPUTERNAME", ""),
        "items": copied,
        "total_bytes": sum(_size(stage / n) for n in copied),
        "api_keys_removed": removed,
        "left_behind": {k: v for k, v in SKIP_DIRS.items() if k in plan["skipped"]},
        "with_media": with_media,
    }
    (stage / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    if zip_mode:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            for p in stage.rglob("*"):
                if p.is_file():
                    z.write(p, p.relative_to(stage))
        shutil.rmtree(stage, ignore_errors=True)
        final = target
    else:
        final = stage

    return {"ok": True, "path": str(final), "total": _human(manifest["total_bytes"]),
            "items": manifest["items"], "removed": removed,
            "left_behind": manifest["left_behind"], "manifest": manifest}


def _read_pack(src: Path) -> Path:
    """Return a folder holding the package, unzipping a .zip into a temp dir."""
    if src.is_file() and src.suffix.lower() == ".zip":
        tmp = Path(src).with_suffix(".unpacked")
        tmp.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src) as z:
            z.extractall(tmp)
        return tmp
    return src


def _merge_tree(src: Path, dst: Path, added: list[str], prefix: str = "") -> None:
    """Copy what is missing, never overwrite: `projects/` exists on both machines,
    but the individual projects inside it usually do not."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        label = f"{prefix}{item.name}"
        if item.is_dir():
            _merge_tree(item, target, added, prefix=label + "/")
        elif not target.exists():
            shutil.copyfile(item, target)
            added.append(label)


def unpack(src: str, force: bool = False, merge: bool = False) -> dict:
    folder = _read_pack(Path(src).expanduser())
    if not folder.exists():
        return {"ok": False, "message": f"no such package: {folder}"}
    manifest_path = folder / MANIFEST
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    home = config.data_dir()
    settings_file = home / "settings.json"
    vault = home / "vault"
    clash = settings_file.exists() or (vault.exists() and any(vault.iterdir()))
    if clash and not (force or merge):
        return {"ok": False, "message": f"{home} already has settings or a vault. "
                                        f"Re-run with --merge to keep both, or --force "
                                        f"to replace. Nothing was changed."}

    restored: list[str] = []
    for entry in folder.iterdir():
        if entry.name == MANIFEST:
            continue
        dst = home / entry.name
        if entry.is_dir():
            if dst.exists() and merge:
                _merge_tree(entry, dst, restored, prefix=entry.name + "/")
                continue
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(entry, dst)
        else:
            shutil.copyfile(entry, dst)
        restored.append(entry.name)

    return {"ok": True, "home": str(home), "restored": restored, "manifest": manifest}


def check() -> int:
    plan = collect()
    home = config.data_dir()
    print("\nWHERE ARC KEEPS YOUR THINGS ON THIS MACHINE\n" + "=" * 66)
    print(f"  home     {home}")
    print(f"  total    {_human(plan['total'])} in {len(plan['items'])} item(s)")
    for p, name in plan["items"]:
        print(f"    {name:<22} {_human(_size(p))}")
    if plan["skipped"]:
        print("\n  left behind on purpose:")
        for name in plan["skipped"]:
            print(f"    {name:<22} {SKIP_DIRS[name]}")

    print("\nWHAT A SECOND LAPTOP NEEDS\n" + "=" * 66)
    print("  1. the program      build on Windows: packaging\\build_all.bat -> "
          "dist\\ArcDeskSetup.exe")
    print("                      (PyInstaller cannot cross-compile; I cannot make the .exe "
          "from here)")
    print("  2. your data        python tools\\move.py pack D:\\arcdesk-carry")
    print("                      then on laptop B: python tools\\move.py unpack "
          "D:\\arcdesk-carry")
    print("  3. models           install_clone.bat / install_voice.bat on laptop B "
          "(1.5-2 GB, downloaded there)")
    print("  4. a voice lock     per machine by design: lock-enroll with the voice of "
          "whoever uses laptop B")
    print("  5. the clone clip   voice\\ travels in the package; re-import a new clip if the "
          "person changes")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Move ARC's data to another laptop.")
    ap.add_argument("action", choices=["check", "pack", "unpack"], nargs="?", default="check")
    ap.add_argument("target", nargs="?", default="")
    ap.add_argument("--with-media", action="store_true", help="also pack art/ photos/ generated/")
    ap.add_argument("--with-keys", action="store_true", help="keep API keys (off by default)")
    ap.add_argument("--force", action="store_true", help="replace what is on this machine")
    ap.add_argument("--merge", action="store_true", help="keep both sets of projects")
    args = ap.parse_args(argv[1:])

    if args.action == "check":
        return check()
    if not args.target:
        print("give a target: pack <folder|file.zip> / unpack <folder|file.zip>")
        return 2
    if args.action == "pack":
        got = pack(args.target, args.with_media, args.with_keys)
        if not got["ok"]:
            print("FAIL " + got["message"])
            return 1
        print(f"OK   {got['path']}   ({got['total']})")
        for name, size in got["items"].items():
            print(f"       {name:<22} {_human(size)}")
        if got["removed"]:
            print(f"     API keys removed: {', '.join(got['removed'])} "
                  f"(use --with-keys to keep them)")
        if got["left_behind"]:
            print("     left behind:")
            for name, why in got["left_behind"].items():
                print(f"       {name:<18} {why}")
        print("\n     on the other laptop: python tools\\move.py unpack "
              + f'"{args.target}"')
        return 0

    got = unpack(args.target, args.force, args.merge)
    if not got["ok"]:
        print("FAIL " + got["message"])
        return 1
    print(f"OK   restored into {got['home']}: {', '.join(got['restored'])}")
    if got["manifest"].get("left_behind"):
        print("     these were not in the package, on purpose:")
        for name, why in got["manifest"]["left_behind"].items():
            print(f"       {name:<18} {why}")
    print("\n     next: run install_voice.bat and install_clone.bat here (models are "
          "downloaded, never copied),")
    print("           then enroll this machine's voice: "
          "python tools\\voice_setup.py lock-enroll <name> r1.wav r2.wav r3.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
