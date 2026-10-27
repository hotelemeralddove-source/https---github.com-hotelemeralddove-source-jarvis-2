"""One JARVIS, one folder, one thing to double-click.

The report: *"enakku unwanted, multiple files lan ilama correct ah ena ena organized
files, folders ah orey folder ah irukanum.. orey place la irukanum.. vera vera files,
places la irukurathu nala confuse aaguthu, ipo kooda jarvis again open aaga matiku"*.

Fair. A project that exists in four places is not a project, it is a puzzle: you never
know which copy opened, which one has your `.venv`, and which one the update went into.

This tool answers the question once and then makes it true:

  1. **find every copy** — a folder is a copy when it has `run.py` AND
     `requirements.txt` (the same marker the launcher uses, so the answers agree);
  2. **say which one is the real one**, and why (it has a working `.venv`, it is the
     newest, it is already in the right place);
  3. **with --apply, do it**: keep that one at `~/JARVIS`, move every other copy to
     `~/JARVIS-OLD/<name>` (moved, never deleted — nothing is lost), and print the one
     file to double-click from now on.

    python tools/one_place.py            # show what exists, change nothing
    python tools/one_place.py --apply    # keep ONE at ~/JARVIS, park the rest in JARVIS-OLD

Nothing here deletes: `--apply` moves. `--undo` moves the parked folders back.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKERS = ("run.py", "requirements.txt")


def is_temp(path: Path, home: Path | None = None) -> bool:
    """Is this inside a temporary folder? Leftover test copies are not "my JARVIS".

    `one_place.py` reported 61 copies on the build machine — every one a scratch folder
    from a test run under /tmp. A tidy-up tool that lists noise cannot be trusted about
    the real thing either, so temp paths are dropped.

    One exception, and it matters: on Windows `%TEMP%` lives INSIDE the user's home, so a
    temp root that contains `home` is ignored (that only happens when home itself is a
    scratch folder — which is exactly how the tests run).
    """
    try:
        here = path.resolve()
    except OSError:
        return False
    roots: set[Path] = set()
    try:
        import tempfile
        roots.add(Path(tempfile.gettempdir()))
    except Exception:                                            # noqa: BLE001
        pass
    for env in ("TEMP", "TMP", "TMPDIR"):
        value = os.environ.get(env)
        if value:
            roots.add(Path(value))
    base = None
    if home is not None:
        try:
            base = Path(home).resolve()
        except OSError:
            base = None
    resolved: list[Path] = []
    for root in roots:
        try:
            resolved.append(root.resolve())
        except OSError:
            continue
    if base is not None and any(root == base or root in base.parents
                                for root in resolved):
        # home itself is a scratch folder (exactly how the tests run, and where
        # %TEMP% lives on Windows): every filter below would blank the search,
        # including the string checks, so the answer is "nothing under home is
        # temp" and we stop here.
        return False
    for root in resolved:
        if here == root or root in here.parents:
            return True
    lowered = str(here).lower()
    if "\\appdata\\local\\temp\\" in lowered:
        return True
    if base is None and ("/tmp/" in lowered or lowered.startswith("/tmp")):
        return True
    return False


OLD_DIR = "JARVIS-OLD"
MANIFEST = ".moved.json"
KEEP_NAME = "JARVIS"


def is_copy(path: Path) -> bool:
    """A folder is a copy of the app when both markers are there."""
    try:
        return all((path / m).is_file() for m in MARKERS)
    except OSError:
        return False


def version_of(path: Path) -> str:
    """The version the copy claims, read without importing it."""
    for rel in ("arcdesk/__init__.py",):
        try:
            text = (path / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            low = line.strip()
            if low.startswith("__version__"):
                return low.split("=", 1)[-1].strip().strip('"\'')
    return "?"


def has_venv(path: Path) -> bool:
    return (path / ".venv" / "Scripts" / "python.exe").exists() or \
           (path / ".venv" / "bin" / "python").exists()


def weight(path: Path) -> tuple:
    """Sort key: a working environment first, then the newest run.py, then version."""
    try:
        newest = max((path / m).stat().st_mtime for m in MARKERS)
    except OSError:
        newest = 0.0
    return (1 if has_venv(path) else 0, newest, version_of(path))


def protected() -> list[Path]:
    """Folders this tool must never move: the app it is running from, and the cwd.

    Learned the hard way while building it: a tidy-up that moves the folder you are
    standing in is not tidy, it is a disappearance ("jarvis open aaga matiku"). So the
    copy being run from is reported and skipped unless --force is passed.
    """
    out = [ROOT]
    try:
        out.append(Path.cwd())
    except OSError:
        pass
    return [p.resolve() for p in out]


def _inside(path: Path, parents: list[Path]) -> bool:
    """True when `path` is one of `parents`, or contains / is contained by one."""
    try:
        target = path.resolve()
    except OSError:
        return False
    for parent in parents:
        if target == parent:
            return True
        if parent in target.parents or target in parent.parents:
            return True
    return False


def roots(home: Path | None = None) -> list[Path]:
    """Everywhere worth looking, deepest-first order is decided by the caller."""
    home = Path(home) if home else Path.home()
    out = [ROOT, ROOT.parent, ROOT.parent.parent]
    for name in (KEEP_NAME, "Documents", "Downloads", "Desktop", "OneDrive/Desktop",
                 "Documents/GitHub", "Documents/Projects"):
        out.append(home / name)
    return out


def find_copies(home: Path | None = None, depth: int = 2,
                include_self: bool = True) -> list[Path]:
    """All app folders under the usual places, `depth` levels deep. Sorted, no dupes.

    `include_self=False` looks only under `home` — which is what the tests use, so a
    test can never mistake the real project for a stray copy of it.
    """
    places = roots(home) if include_self else [p for p in roots(home) if p not in
                                               (ROOT, ROOT.parent, ROOT.parent.parent)]
    found: dict[str, Path] = {}

    def walk(base: Path, left: int) -> None:
        try:
            if not base.is_dir():
                return
            if is_copy(base):
                if not is_temp(base, home):
                    found[str(base.resolve()).lower()] = base
                return
            if left <= 0:
                return
            for child in sorted(base.iterdir()):
                try:
                    if child.is_dir() and not child.name.startswith("."):
                        walk(child, left - 1)
                except OSError:
                    continue
        except OSError:
            return

    for root in places:
        walk(root, depth)
    return [found[k] for k in sorted(found)]


def running_copy(copies: list[Path]) -> Path | None:
    """The copy that is running right now, if it is one of `copies`.

    This is the only answer to "which files are the correct ones" that is not a guess:
    the running process tells us the folder whose run.py it is executing.
    """
    try:
        import subprocess as _sp
        import sys as _sys
        if _sys.platform == "win32":
            sys.path.insert(0, str(ROOT / "tools"))
        from tools.jarvis_state import running_project
        where = running_project()
    except Exception:                                            # noqa: BLE001
        return None
    if not where:
        return None
    try:
        want = Path(where)
        # it must be a folder that really exists and really is the app - a stale or
        # half-parsed command line must never win this decision
        if not want.is_dir() or not is_copy(want):
            return None
        want = want.resolve()
    except OSError:
        return None
    for copy in copies:
        try:
            if copy.resolve() == want:
                return copy
        except OSError:
            continue
    # it is running, but from a folder the search did not reach: still the right one
    return Path(where)


def choose(copies: list[Path], home: Path | None = None) -> Path | None:
    """Which copy to keep, in order of certainty:

    1. the one that is RUNNING right now — not a guess, the process says so;
    2. a copy already at `~/JARVIS` — already where we want it;
    3. the one with a working `.venv`, then the newest.
    """
    home = Path(home) if home else Path.home()
    target = home / KEEP_NAME
    live = running_copy(copies)
    if live is not None:
        return live
    for copy in copies:
        try:
            if copy.resolve() == target.resolve():
                return copy
        except OSError:
            continue
    if not copies:
        return None
    return max(copies, key=weight)


def verify(path: Path) -> dict:
    """Is this copy actually runnable? Checked, not assumed.

    Four things, cheapest first. The last one runs the copy's own interpreter, which is
    the only real proof that its `.venv` matches its code.
    """
    out = {"path": str(path), "markers": is_copy(path),
           "package": (path / "arcdesk" / "__init__.py").is_file(),
           "venv": has_venv(path), "version": version_of(path), "imports": ""}
    if not out["markers"] or not out["package"]:
        return out
    exe = path / ".venv" / "Scripts" / "python.exe"
    if not exe.exists():
        exe = path / ".venv" / "bin" / "python"
    if not exe.exists():
        out["imports"] = "no environment yet (first run builds it)"
        return out
    try:
        import subprocess
        got = subprocess.run([str(exe), "-c", "import arcdesk; print(arcdesk.__version__)"],
                             cwd=str(path), capture_output=True, text=True, timeout=90)
        out["imports"] = (got.stdout or "").strip() if got.returncode == 0 else \
                         (f"failed: {(got.stderr or '').strip().splitlines()[-1:] or ['?']}"
                          f"")
    except Exception as exc:                                     # noqa: BLE001
        out["imports"] = f"could not run its python: {type(exc).__name__}"
    return out


def plan(copies: list[Path], keep: Path | None, home: Path | None = None) -> dict:
    """What --apply would do, as data — so the tests can check it without moving files."""
    home = Path(home) if home else Path.home()
    target = home / KEEP_NAME
    others = [c for c in copies if keep is None or c.resolve() != keep.resolve()]
    return {
        "keep": str(keep) if keep else "",
        "move_to_target": bool(keep) and keep.resolve() != target.resolve(),
        "target": str(target),
        "park": [{"from": str(c), "to": str(target.parent / OLD_DIR / c.name)}
                 for c in others],
    }


SKIP_IN_COPY = {".venv", "__pycache__", "dist", "build", ".git", ".failures",
                "packaging/work", "runtime"}


def copy_project(src: Path, target: Path) -> dict:
    """Copy an app folder somewhere else, without its environment.

    Used when the copy to keep is the one this tool is running from. Moving a folder you
    are standing in is how a tidy-up becomes a disappearance, so it copies instead, and
    says plainly that the original is still there and that the new folder builds its own
    `.venv` on first start (2-4 minutes, once). Copying a `.venv` is pointless: it holds
    absolute paths to the folder it was made in.
    """
    rows: list[str] = []
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return {"ok": False, "why": f"{target} already exists — nothing copied",
                    "done": []}
        shutil.copytree(src, target,
                        ignore=shutil.ignore_patterns(*SKIP_IN_COPY),
                        symlinks=True)
        rows.append(f"copied {src} -> {target} (without .venv — the new folder builds "
                    f"its own on first start)")
        return {"ok": True, "why": "", "done": rows}
    except Exception as exc:                                     # noqa: BLE001
        return {"ok": False, "why": f"{type(exc).__name__}: {exc}", "done": rows}


def _remember(target: Path, rows: list[dict]) -> None:
    """Record where each parked folder came from, so --undo can put it back exactly."""
    path = target.parent / OLD_DIR / MANIFEST
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        old: list = []
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8") or "[]")
        path.write_text(json.dumps(list(old) + rows, indent=1), encoding="utf-8")
    except Exception:                                            # noqa: BLE001
        pass


def apply_plan(p: dict, force: bool = False) -> dict:
    """Do it. Moves only — nothing is deleted, and a failure is reported, not hidden."""
    done: list[str] = []
    failed: list[dict] = []
    guard = [] if force else protected()
    keep = Path(p["keep"]) if p.get("keep") else None
    target = Path(p["target"])
    if keep is not None and _inside(keep, guard):
        return {"done": [], "failed": [{"what": str(keep),
                "why": "this is the JARVIS you are running the tool from — not moving "
                       "it. Move it by hand, or pass --force"}]}
    try:
        if keep is not None and p.get("move_to_target"):
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                # the target folder is there but is not a copy: keep both, do not merge
                shutil.move(str(keep), str(target.parent / (OLD_DIR + "-kept")))
                done.append(f"kept copy moved aside to {OLD_DIR}-kept (a {target.name} "
                            f"folder was already there and is not a copy)")
            else:
                shutil.move(str(keep), str(target))
                done.append(f"kept copy moved to {target}")
    except Exception as exc:                                     # noqa: BLE001
        failed.append({"what": str(keep), "why": f"{type(exc).__name__}: {exc}"})
    for row in p.get("park", []):
        src, dst = Path(row["from"]), Path(row["to"])
        try:
            if not src.exists():
                continue
            if _inside(src, guard):
                failed.append({"what": str(src),
                               "why": "this is the JARVIS you are running the tool from "
                                      "— left alone (use --force to override)"})
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst = dst.with_name(f"{dst.name}-{int(time.time())}")
            shutil.move(str(src), str(dst))
            _remember(target, [{"from": str(src), "to": str(dst)}])
            done.append(f"parked {src} -> {dst}")
        except Exception as exc:                                 # noqa: BLE001
            failed.append({"what": str(src), "why": f"{type(exc).__name__}: {exc}"})
    return {"done": done, "failed": failed}


def undo(home: Path | None = None) -> dict:
    """Put the parked folders back exactly where they came from.

    Uses the manifest `apply_plan` writes; if there is no manifest it falls back to
    `home/<name>`, which is where a folder parked from the home directory would go.
    """
    home = Path(home) if home else Path.home()
    park = home / OLD_DIR
    moved: list[str] = []
    failed: list[dict] = []
    if not park.is_dir():
        return {"done": moved, "failed": failed}
    manifest = park / MANIFEST
    if manifest.exists():
        try:
            rows = json.loads(manifest.read_text(encoding="utf-8") or "[]")
        except Exception:                                        # noqa: BLE001
            rows = []
        for row in rows:
            src, dst = Path(row.get("from", "")), Path(row.get("to", ""))
            try:
                if not dst.exists() or src.exists():
                    continue
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                moved.append(f"restored {src}")
            except Exception as exc:                             # noqa: BLE001
                failed.append({"what": str(dst), "why": f"{type(exc).__name__}: {exc}"})
        try:
            manifest.unlink()
        except OSError:
            pass
        return {"done": moved, "failed": failed}
    for folder in sorted(park.iterdir()):
        try:
            if not folder.is_dir() or not is_copy(folder):
                continue
            dest = home / folder.name
            if dest.exists():
                continue
            shutil.move(str(folder), str(dest))
            moved.append(f"restored {folder.name} -> {dest}")
        except Exception:                                        # noqa: BLE001
            continue
    return {"done": moved, "failed": []}


def report(copies: list[Path], keep: Path | None, home: Path | None = None,
           live: Path | None = None) -> str:
    """The screen version: every copy, which one wins, and the one file to click."""
    home = Path(home) if home else Path.home()
    lines = []
    if not copies:
        lines.append("no JARVIS folder found anywhere I looked.")
        lines.append("unzip ArcDesk-full-project.zip into  " + str(home / KEEP_NAME))
        lines.append("and double-click JARVIS.bat in it.")
        return "\n".join(lines)
    lines.append(f"{len(copies)} copy(ies) of JARVIS found:")
    shown = copies
    if len(copies) > 8:
        shown = sorted(copies, key=weight, reverse=True)[:8]
        lines.append(f"  (showing the 8 most likely; the other {len(copies) - 8} are older)")
    for copy in shown:
        is_keep = keep is not None and copy.resolve() == keep.resolve()
        tags = []
        if live is not None and copy.resolve() == live.resolve():
            tags.append("RUNNING NOW")
        tags.append(f"version {version_of(copy)}")
        tags.append("environment: yes" if has_venv(copy) else "environment: none yet")
        line = "  " + str(copy)
        if is_keep:
            line += "   <-- keep this one"
        lines.append(line)
        lines.append("     " + " · ".join(tags))
    target = home / KEEP_NAME
    lines.append("")
    lines.append("keep one:" if len(copies) > 1 else "one copy, nothing to tidy:")
    lines.append(f"  {keep}")
    if keep is not None and keep.resolve() != target.resolve():
        lines.append(f"and move it here:  {target}")
    lines.append("")
    lines.append("to make that true:")
    lines.append("  python tools/one_place.py --apply")
    lines.append("")
    lines.append("then, for ever after, ONE thing to open:")
    lines.append(f"  {target / 'JARVIS.bat'}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="one_place",
                                 description="Keep one JARVIS folder and park the rest.")
    ap.add_argument("--apply", action="store_true", help="actually move the folders")
    ap.add_argument("--undo", action="store_true", help="put the parked folders back")
    ap.add_argument("--json", action="store_true", help="machine-readable plan")
    ap.add_argument("--report", default="",
                    help="also write the scan to this file, to read or send")
    ap.add_argument("--verify", action="store_true",
                    help="prove the keeper really runs (starts its own python once)")
    ap.add_argument("--force", action="store_true",
                    help="also move the copy this tool is running from (rarely right)")
    ap.add_argument("--home", default="", help="pretend this is the home folder (tests)")
    args = ap.parse_args(argv)
    home = Path(args.home) if args.home else Path.home()

    if args.undo:
        got = undo(home)
        print("\n".join(got["done"]) or "nothing was parked")
        return 0

    copies = find_copies(home)
    keep = choose(copies, home)
    the_plan = plan(copies, keep, home)
    if args.json:
        print(json.dumps(the_plan, indent=2))
        return 0
    live = running_copy(copies)
    text = report(copies, keep, home, live)
    print(text)
    if args.report:
        try:
            Path(args.report).write_text(text + "\n", encoding="utf-8")
            print("")
            print("written to " + str(args.report))
        except OSError as exc:
            print(f"could not write {args.report}: {exc}")
    if not args.apply:
        return 0 if copies else 1

    got = apply_plan(the_plan, force=args.force)
    if args.verify:
        check = verify(Path(the_plan["target"]) if Path(the_plan["target"]).exists()
                       else Path(the_plan["keep"]))
        print("")
        print(f"verify {check['path']}")
        print(f"  run.py + requirements.txt : {'yes' if check['markers'] else 'NO'}")
        print(f"  the arcdesk package      : {'yes' if check['package'] else 'NO'}")
        print(f"  its own environment      : {'yes' if check['venv'] else 'no'}")
        print(f"  import arcdesk           : {check['imports'] or 'not checked'}")
    if got["failed"] and keep is not None and _inside(keep, protected()):
        # the copy to keep is the one we are running from: copy it, do not move it
        why = got["failed"][0]["why"]
        print("")
        print("  " + why)
        copied = copy_project(keep, Path(the_plan["target"]))
        for line in copied["done"]:
            print("  done: " + line)
        if not copied["ok"]:
            print("  " + copied["why"])
    for line in got["done"]:
        print("  done: " + line)
    for bad in got["failed"]:
        if "running the tool from" in bad["why"]:
            continue
        print(f"  could not move {bad['what']}: {bad['why']}")
    print("")
    print("now double-click:  " + str(home / KEEP_NAME / "JARVIS.bat"))
    return 0 if not got["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
