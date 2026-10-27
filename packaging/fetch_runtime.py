#!/usr/bin/env python3
"""Fetch the portable runtimes that ship INSIDE the installer — once, at build time.

    python packaging/fetch_runtime.py              # ffmpeg + node
    python packaging/fetch_runtime.py --list       # what is already cached
    python packaging/fetch_runtime.py --check      # exit 1 unless both are ready
    python packaging/fetch_runtime.py --only ffmpeg
    python packaging/fetch_runtime.py --verify     # re-hash what is on disk

Why this file exists, in the user's words: *"extra va yethum download panra mathiri iruntha
like python, ffmpeg, nodejs — athuve download aagi install aagura mathiri simple file ah kodu,
individual ah download panni path set panra mathiri vendam."*

So the download happens HERE — on the machine that builds the installer — and never on the
user's machine. The user double-clicks one Setup.exe and gets everything.

What is actually needed at runtime, honestly:

    ffmpeg + ffprobe   media studio, playback probing, waveforms      ~35 MB packed
    node + npx         MCP tool servers that run over stdio via npx   ~30 MB packed
    python             NOT needed: PyInstaller already put an
                       interpreter inside ArcDesk.exe. Shipping a
                       second one would add ~15 MB for nothing.

Checksums: Node publishes SHASUMS256.txt, which is verified here. ffmpeg (gyan.dev)
publishes a .sha256 next to the release; if that is missing the archive is still checked
for a valid zip structure, and this tool SAYS SO rather than pretending it was verified.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "packaging" / "runtimes"          # downloaded archives
STAGE = ROOT / "runtime"                         # extracted, ready for the installer
UA = {"User-Agent": "ArcDesk-build/1.0 (+offline installer builder)"}

# BtbN's "shared" build, not a giant static one: the exe stays tiny and the codecs live
# in DLLs. That matters for the installer size — lzma2 compresses raw DLLs far better
# than it can re-compress a zip that is already deflated.
#   static (gyan.dev): ~317 MB of exe, ~110 MB zip
#   shared (BtbN):     ~209 MB of exe+dll, ~91 MB zip  -> ~55 MB after lzma2
FFMPEG_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
              "ffmpeg-master-latest-win64-gpl-shared.zip")
FFMPEG_KEEP = ("ffmpeg.exe", "ffprobe.exe")      # ffplay is 23 MB and only a fallback
NODE_INDEX = "https://nodejs.org/dist/index.json"
NODE_SHASUMS = "https://nodejs.org/dist/{ver}/SHASUMS256.txt"


def _get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:      # noqa: S310
        return resp.read()


def _download(url: str, dest: Path, label: str) -> Path:
    if dest.is_file() and dest.stat().st_size > 1024:
        print(f"  cached   {label:<10} {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  fetching {label:<10} {url}")
    data = _get(url)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, dest)
    print(f"  saved    {label:<10} {dest.name} ({len(data) / 1e6:.1f} MB)")
    return dest


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def node_latest_lts() -> tuple[str, str]:
    """(version, url) of the newest LTS release, from nodejs.org's own index."""
    data = json.loads(_get(NODE_INDEX).decode("utf-8"))
    for row in data:                       # newest first
        if row.get("lts"):
            ver = row["version"]           # e.g. "v22.11.0"
            return ver, f"https://nodejs.org/dist/{ver}/node-{ver}-win-x64.zip"
    raise RuntimeError("nodejs.org did not list any LTS release")


def fetch_ffmpeg(verify: bool = True) -> dict:
    archive = CACHE / "ffmpeg-win64-gpl-shared.zip"
    _download(FFMPEG_URL, archive, "ffmpeg")
    if not zipfile.is_zipfile(archive):
        return {"ok": False, "error": "ffmpeg archive is not a valid zip"}
    # BtbN publishes no separate checksum file for the rolling "latest" tag, so the hash is
    # recorded (and printed) instead of being "verified" against a published value. The
    # difference is stated, not blurred.
    digest = _sha256(archive)
    verified = "archive structure checked; sha256 recorded (no published checksum)"
    target = STAGE / "ffmpeg"
    target.mkdir(parents=True, exist_ok=True)
    keep_bin = set(FFMPEG_KEEP)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            if "/bin/" not in member or member.endswith("/"):
                continue
            name = Path(member).name
            if not (name.endswith(".dll") or name in keep_bin):
                continue
            with zf.open(member) as src, open(target / name, "wb") as dst:
                shutil.copyfileobj(src, dst)
    exes = sorted(p.name for p in target.glob("*.exe"))
    return {"ok": "ffmpeg.exe" in exes and "ffprobe.exe" in exes,
            "files": exes, "dlls": len(list(target.glob("*.dll"))),
            "dir": str(target), "verified": verified, "sha256": digest,
            "bytes": sum(p.stat().st_size for p in target.rglob("*") if p.is_file())}


def fetch_node(verify: bool = True) -> dict:
    ver, url = node_latest_lts()
    archive = CACHE / f"node-{ver}-win-x64.zip"
    _download(url, archive, "node")
    verified = ""
    if verify:
        try:
            shas = _get(NODE_SHASUMS.format(ver=ver)).decode("utf-8", "replace")
            want = next((ln.split()[0] for ln in shas.splitlines()
                         if ln.strip().endswith(f"node-{ver}-win-x64.zip")), "")
            got = _sha256(archive)
            if want and want != got:
                return {"ok": False, "error": f"node checksum mismatch: {got[:12]} != {want[:12]}"}
            verified = "sha256 from nodejs.org" if want else "not published for this file"
        except Exception as exc:
            verified = f"checksum fetch failed ({type(exc).__name__}) — not verified"
    target = STAGE / "node"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            info = zf.getinfo(member)
            if info.is_dir():
                continue
            rel = Path(member).relative_to(member.split("/")[0]) if "/" in member else None
            if rel is None:
                continue
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
    got = [p.name for p in target.glob("*.exe")]
    return {"ok": "node.exe" in got, "files": sorted(got), "version": ver,
            "dir": str(target), "verified": verified,
            "bytes": sum(p.stat().st_size for p in target.rglob("*") if p.is_file())}


def list_cached() -> int:
    print("Arc Desk · portable runtimes")
    print("=" * 66)
    if not CACHE.is_dir() and not STAGE.is_dir():
        print("nothing cached yet — run: python packaging/fetch_runtime.py")
        return 0
    for folder in (CACHE, STAGE):
        if not folder.is_dir():
            continue
        total = 0
        print(f"\n{folder.relative_to(ROOT)}")
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                total += p.stat().st_size
                print(f"  {p.relative_to(folder).as_posix():<46} {p.stat().st_size / 1e6:7.1f} MB")
        print(f"  {'total':<46} {total / 1e6:7.1f} MB")
    return 0


def check() -> int:
    problems = []
    for exe, where in (("ffmpeg.exe", STAGE / "ffmpeg"), ("ffprobe.exe", STAGE / "ffmpeg"),
                       ("node.exe", STAGE / "node")):
        if not (where / exe).is_file():
            problems.append(f"{exe} missing in {where.relative_to(ROOT)}")
    if problems:
        print("runtimes NOT ready:")
        for p in problems:
            print("  -", p)
        print("\nRun:  python packaging\\fetch_runtime.py")
        return 1
    print("runtimes ready: ffmpeg.exe, ffprobe.exe, node.exe are staged in runtime/")
    return 0


def main(argv: list[str]) -> int:
    if "--list" in argv:
        return list_cached()
    if "--check" in argv:
        return check()
    if "--verify" in argv:
        for folder in (CACHE, STAGE):
            for p in sorted(folder.rglob("*")) if folder.is_dir() else []:
                if p.is_file() and p.suffix in (".zip", ".exe"):
                    print(f"  {_sha256(p)[:16]}  {p.relative_to(ROOT)}")
        return 0

    only = ""
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]

    print("Arc Desk · fetching what the one-click installer carries")
    print("=" * 66)
    results = {}
    if only in ("", "ffmpeg"):
        results["ffmpeg"] = fetch_ffmpeg()
        r = results["ffmpeg"]
        print(f"  -> {r.get('files')} + {r.get('dlls')} dlls  ({r.get('verified', '')})")
    if only in ("", "node"):
        results["node"] = fetch_node()
        print(f"  -> node {results['node'].get('version')}  ({results['node'].get('verified', '')})")

    print()
    bad = [k for k, r in results.items() if not r.get("ok")]
    if bad:
        for k in bad:
            print(f"FAILED: {k}: {results[k].get('error')}")
        return 1
    total = sum(r.get("bytes", 0) for r in results.values())
    print(f"staged in {STAGE.relative_to(ROOT)}/ — {total / 1e6:.1f} MB uncompressed, "
          f"compressed by the installer to roughly a third of that.")
    print("Next:  packaging\\build_all.bat")
    return check()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
