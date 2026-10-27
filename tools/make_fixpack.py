#!/usr/bin/env python3
"""Build a fix pack zip: the files changed in this round, plus a marker.

The marker matters. A fix pack has no `run.py` at its root, so an updater cannot tell it
apart from a random zip by looking for the app inside it. `FIXPACK.txt` says plainly what
the archive is, and `tools/update_from_zip.py` applies it on top of the project instead of
refusing it — which is exactly the mistake that made a good download look broken:

    That zip is not the app: it has no run.py in it.

    python tools/make_fixpack.py --name fix39 --files a\b.py c.md
"""
from __future__ import annotations

import argparse
import datetime
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Build a fix pack zip with its marker.")
    ap.add_argument("--name", required=True, help="e.g. fix39")
    ap.add_argument("--files", nargs="+", required=True, help="paths relative to the project")
    ap.add_argument("--readme", default="", help="a README to include")
    ap.add_argument("--out", default="", help="where to write the zip")
    # A pack unzipped as its own folder is what people double-click first. With the
    # launcher inside it, that double-click can find the real app and offer to apply the
    # pack (see the :aboutpack section of JARVIS.bat) instead of printing an error.
    ap.add_argument("--launcher", action="store_true",
                    help="also ship JARVIS.bat and tools/find_project.bat")
    args = ap.parse_args(argv[1:])

    out = Path(args.out) if args.out else Path.home() / f"arcdesk-{args.name}.zip"
    files = list(args.files)
    if args.launcher:
        for extra in ("JARVIS.bat", "tools/find_project.bat"):
            if extra not in files and (ROOT / extra).exists():
                files.append(extra)
    missing = [f for f in files if not (ROOT / f).exists()]
    if missing:
        print("missing files:", ", ".join(missing))
        return 2

    marker = (f"KIND=fixpack\nNAME={args.name}\n"
              f"BUILT={datetime.date.today().isoformat()}\n"
              f"BASE=any ArcDesk project folder (run.py at its root)\n"
              f"LAUNCHER={'yes - JARVIS.bat inside the pack finds the app' if args.launcher else 'no'}\n"
          f"APPLY=unzip into the project, or run tools/update_from_zip.py with this "
              f"file - it will copy these {len(args.files)} files on top and leave .venv "
              f"and settings alone\n")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(ROOT / f, f)
        z.writestr("FIXPACK.txt", marker)
        if args.readme and Path(args.readme).exists():
            z.write(args.readme, f"README-{args.name.upper()}.txt")
    size = out.stat().st_size
    print(f"{out.name}  {size:,} bytes  {len(files) + 1} files  "
          f"(marker included)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
