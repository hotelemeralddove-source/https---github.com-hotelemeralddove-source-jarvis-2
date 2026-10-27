#!/usr/bin/env python3
"""How big is this thing, really? — measured, never guessed.

    python tools/sizecheck.py                 # what is in the repo + what would ship
    python tools/sizecheck.py --dist dist\\ArcDesk   # measure a finished PyInstaller build
    python tools/sizecheck.py --compress      # measure the lzma2 ratio of the payload

The user's point 7 was *"file size and space ah compress paniko, work inum nalla irukum"*.
Compression is a trade, so this tool prints the trade instead of a slogan:

  * the raw size of each payload (app, ffmpeg, node),
  * what lzma2 actually makes of it — measured by compressing the real files,
  * and the one thing compression must NOT buy: start-up speed. A one-file build unpacks
    to %TEMP% on every launch, which is exactly why this project ships one folder.

Honest limit: the final Setup.exe size can only be known after Inno Setup runs on Windows.
This tool gives the measured input to that number (the lzma2 ratio), not the number.
"""
from __future__ import annotations

import lzma
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _size(path: Path) -> tuple[int, int]:
    if path.is_file():
        return path.stat().st_size, 1
    if not path.is_dir():
        return 0, 0
    total = count = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
            count += 1
    return total, count


def mb(n: int) -> str:
    return f"{n / 1e6:,.1f} MB"


def lzma_ratio(path: Path) -> tuple[int, int]:
    """Compress every file the way Inno does (solid-ish, per-file here) and add it up."""
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = [p for p in path.rglob("*") if p.is_file()]
    else:
        return 0, 0
    before = after = 0
    for f in files:
        try:
            data = f.read_bytes()
        except OSError:
            continue
        before += len(data)
        after += len(lzma.compress(data, preset=6))       # ultra64 is slightly better
    return before, after


def report(compress: bool = False, dist: Path | None = None) -> int:
    print("ARC DESK · size check")
    print("=" * 74)
    targets: list[tuple[str, Path]] = [
        ("app source (arcdesk/)", ROOT / "arcdesk"),
        ("tests + tools", ROOT / "tools"),
        ("docs", ROOT),
    ]
    if dist:
        targets.insert(0, ("BUILT app (PyInstaller)", dist))
    for name in ("ffmpeg", "node"):
        p = ROOT / "runtime" / name
        if p.is_dir():
            targets.append((f"bundled {name}", p))
        else:
            print(f"  {'(not fetched)':<28} runtime/{name}  — run packaging/fetch_runtime.py")

    for label, path in targets:
        total, count = _size(path)
        if label == "docs":
            total = sum(p.stat().st_size for p in ROOT.glob("*.md"))
            count = len(list(ROOT.glob("*.md")))
        print(f"  {label:<28} {mb(total):>12}   {count:>5} files")

    if compress:
        print("\nlzma2 (what the installer does) — measured on the real files:")
        rows = []
        for label, path in targets:
            if label.startswith(("app source", "docs")):
                continue
            before, after = lzma_ratio(path)
            if before:
                rows.append((label, before, after))
                pct = after / before * 100
                print(f"  {label:<28} {mb(before):>12} -> {mb(after):>10}  ({pct:.0f}%)")
        if rows:
            b = sum(r[1] for r in rows)
            a = sum(r[2] for r in rows)
            print(f"  {'TOTAL payload':<28} {mb(b):>12} -> {mb(a):>10}  ({a / b * 100:.0f}%)")
            print("\n  That second number is what the Setup.exe must carry, plus the")
            print("  installer stub (~5 MB). The exact figure is printed by build_all.bat")
            print("  after Inno Setup runs — this is the measured input to it, not a guess.")

    print("\nWhat compression is NOT allowed to do here:")
    print("  · one-file exe that unpacks to %TEMP% on every launch  -> slower every day")
    print("  · UPX on the exe  -> the #1 cause of antivirus false positives")
    print("  · dropping Qt modules we actually use -> a crash on a screen you open once")
    print("  · stripping ffmpeg to 3 codecs -> a video that silently fails at 11 pm")
    return 0


def main(argv: list[str]) -> int:
    dist = None
    if "--dist" in argv:
        dist = Path(argv[argv.index("--dist") + 1])
        if not dist.is_absolute():
            dist = (ROOT / dist)
        if not dist.exists():
            print(f"no built app at {dist} — run packaging\\build_all.bat first")
            dist = None
    return report(compress="--compress" in argv, dist=dist)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
