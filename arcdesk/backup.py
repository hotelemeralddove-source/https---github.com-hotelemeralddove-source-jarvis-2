"""Copy your files to another drive — and prove the copy is good.

The promise this module exists to keep is the user's first rule: *your files are
never damaged.* Everything here is built so a mistake is impossible rather than
unlikely:

* **The source is opened read-only.** There is no delete, no move, no rename, not
  even a `touch` on a source file. The only writes are inside the backup folder the
  caller named.
* **A backup never overwrites.** Every run creates a new `ArcBackup-<timestamp>`
  folder. Two runs on the same day produce two folders, never one merged one. The
  test asserts this by running twice and comparing.
* **A copy is not a backup until it is verified.** Each file is hashed while it is
  being copied (one pass, no re-read of the source), then the *destination* is hashed
  again and the two are compared. A mismatch is reported as `MISMATCH` and the run
  says plainly that the backup is not trustworthy — it is never summarised as "done".
* **Refuses the dangerous shapes.** Target inside the source, source inside the
  target, same folder, the whole of `C:\\` — each one is a refusal with the reason,
  not a warning buried in a log.

Verify-later is a first-class mode: `verify()` re-hashes an existing backup against
its own manifest, so "is last month's copy still intact?" has an answer that is not
a guess.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"

CHUNK = 1024 * 1024
MAX_FILES = 50_000
MAX_BYTES = 200 * 1024 ** 3            # 200 GB — stop before filling a drive
MIN_FREE_AFTER_GB = 2.0                # leave the target breathing room
MANIFEST = "arc_backup_manifest.json"
SKIP_DIRS = {
    "node_modules", ".git", ".svn", "__pycache__", ".venv", "venv", "site-packages",
    "$recycle.bin", "system volume information", "windows", "winsxs", "appdata",
    ".cache", ".npm", ".gradle", ".m2", "temp", "tmp", ".trash", "arcbackup",
}
SKIP_FILES = {"desktop.ini", "thumbs.db", ".ds_store"}
# Files a backup should not try to carry: locks and live databases copy as garbage.
SKIP_EXT = {".tmp", ".temp", ".lock", ".part", ".crdownload", ".swp"}


# --------------------------------------------------------------------- helpers
def _hash_file(path: Path, into: "hashlib._Hash | None" = None) -> str:
    digest = into or hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _free_gb(path: Path) -> float:
    try:
        usage = shutil.disk_usage(str(path))
        return round(usage.free / 1024 ** 3, 1)
    except OSError:
        return -1.0


def _human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def drives() -> list[dict]:
    """Mounted volumes, so "back up to the external disk" needs no path typing."""
    found: list[dict] = []
    if IS_WIN:
        import string
        for letter in string.ascii_uppercase:
            root = Path(f"{letter}:\\")
            if root.exists():
                try:
                    usage = shutil.disk_usage(str(root))
                except OSError:
                    continue
                found.append({"path": str(root), "free_gb": round(usage.free / 1024 ** 3, 1),
                              "total_gb": round(usage.total / 1024 ** 3, 1),
                              "removable": False})
        return found
    for base in ("/media", "/run/media", "/mnt", "/Volumes"):
        holder = Path(base)
        if not holder.is_dir():
            continue
        for entry in sorted(holder.iterdir()):
            try:
                if not entry.is_dir():
                    continue
                usage = shutil.disk_usage(str(entry))
            except OSError:
                continue
            found.append({"path": str(entry), "free_gb": round(usage.free / 1024 ** 3, 1),
                          "total_gb": round(usage.total / 1024 ** 3, 1),
                          "removable": True})
    home = Path(os.environ.get("ARCDESK_USER_HOME") or Path.home())
    try:
        usage = shutil.disk_usage(str(home))
        found.append({"path": str(home), "free_gb": round(usage.free / 1024 ** 3, 1),
                      "total_gb": round(usage.total / 1024 ** 3, 1), "removable": False,
                      "home": True})
    except OSError:
        pass
    return found


def default_target() -> str:
    """The most likely external disk — never a guess that overwrites something."""
    # Only a *different* volume counts. Backing up to the folder next door on the same
    # disk is not a backup — it shares the same failure.
    elsewhere = [d for d in drives() if d["path"] not in ("/",) and not d.get("home")]
    return elsewhere[0]["path"] if elsewhere else ""


# ------------------------------------------------------------------------ plan
def plan(source: str, target: str = "", include: str = "") -> dict:
    """What would be copied. No writes. Returns {ok, error, files, bytes, ...}."""
    src = Path(os.path.expanduser(source or "")).resolve()
    if not src.exists():
        return {"ok": False, "error": f"nothing at {src} — check the path"}
    if not src.is_dir():
        return {"ok": False, "error": f"{src.name} is a file, not a folder — give me a folder"}

    tgt_text = target or default_target()
    if not tgt_text:
        return {"ok": False,
                "error": "I can see no external disk or second drive. Plug one in, or tell "
                         "me the path to copy to (for example D:\\Backups)."}
    tgt = Path(os.path.expanduser(tgt_text)).resolve()

    if src.parent == src:
        return {"ok": False,
                "error": "that is a whole drive root. Point me at the folders you care "
                         "about (Documents, Pictures) instead of the entire disk."}
    if _is_within(tgt, src):
        return {"ok": False,
                "error": f"{tgt} is inside {src}. Copying a folder into itself would grow "
                         f"forever — pick a different drive."}
    if _is_within(src, tgt):
        return {"ok": False,
                "error": f"{src} is inside {tgt}. The backup would contain itself."}
    if tgt == src:
        return {"ok": False, "error": "source and target are the same folder."}
    wanted = {w.strip().lower() for w in include.replace(";", ",").split(",") if w.strip()}
    files: list[tuple[Path, Path, int]] = []
    skipped = 0
    total = 0
    for folder, dirs, names in os.walk(src, followlinks=False):
        here = Path(folder)
        dirs[:] = [d for d in dirs
                   if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for name in names:
            path = here / name
            low = name.lower()
            if low in SKIP_FILES or path.suffix.lower() in SKIP_EXT:
                skipped += 1
                continue
            if wanted and path.suffix.lower().lstrip(".") not in wanted:
                skipped += 1
                continue
            try:
                if path.is_symlink() or not path.is_file():
                    skipped += 1
                    continue
                size = path.stat().st_size
            except OSError:
                skipped += 1
                continue
            if len(files) >= MAX_FILES or total + size > MAX_BYTES:
                skipped += 1
                continue
            files.append((path, path.relative_to(src), size))
            total += size

    return {"ok": True, "source": str(src), "target": str(tgt), "files": files,
            "count": len(files), "bytes": total, "skipped": skipped,
            "target_free_gb": _free_gb(tgt) if tgt.exists() else _free_gb(tgt.parent),
            "include": sorted(wanted)}


# ------------------------------------------------------------------------ copy
def copy(source: str, target: str = "", include: str = "", verify: bool = True,
         dry_run: bool = False) -> dict:
    """Copy into a new timestamped folder. Never overwrites, never deletes, verifies."""
    planned = plan(source, target, include)
    if not planned["ok"]:
        return {"ok": False, "error": planned["error"], "manifest": ""}
    if not planned["count"]:
        return {"ok": False, "error": "there are no files to copy in that folder "
                                      "(only skipped ones — caches, temp files, links).",
                "manifest": ""}

    need_gb = planned["bytes"] / 1024 ** 3
    free = planned["target_free_gb"]
    # Refuse when the copy would not FIT, and when it would leave the drive nearly full
    # — but never block a small copy on a nearly-full drive. The first version reserved
    # a flat 200 MB, so a 400 KB backup was refused with "0.0 GB to copy, 0.2 GB free",
    # which is the kind of refusal that makes a person stop trusting the feature.
    if free >= 0:
        left = free - need_gb
        # a copy that leaves 5 % of the drive (or MIN_FREE_AFTER_GB, whichever is
        # smaller) is fine; below that, say no with the real numbers
        keep = min(MIN_FREE_AFTER_GB, free * 0.05)
        if need_gb > free or left < keep:
            size = (f"{need_gb * 1024:.0f} MB" if need_gb < 1 else f"{need_gb:.1f} GB")
            where = (f"{free * 1024:.0f} MB" if free < 1 else f"{free:.1f} GB")
            return {"ok": False,
                    "error": f"not enough room: {size} to copy, {where} free. "
                             f"I will not risk filling the disk — free some space or "
                             f"pick another drive.",
                    "manifest": ""}

    stamp = time.strftime("%Y%m%d-%H%M")
    base = Path(planned["target"])
    folder = base / f"ArcBackup-{stamp}"
    counter = 1
    while folder.exists():                       # never merge two runs
        counter += 1
        folder = base / f"ArcBackup-{stamp}-{counter}"

    if dry_run:
        return {"ok": True, "dry_run": True, "plan": planned, "folder": str(folder),
                "error": "", "manifest": ""}

    try:
        folder.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        return {"ok": False, "error": f"could not create {folder}: {exc}", "manifest": ""}

    started = time.time()
    entries: list[dict] = []
    copied_bytes = 0
    ok_rows = mismatch_rows = failed_rows = 0
    mismatches: list[str] = []
    failures: list[str] = []

    for path, rel, size in planned["files"]:
        dest = folder / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            failed_rows += 1
            failures.append(f"{rel}: {exc}")
            continue
        try:
            # one pass: hash what is read, write what is hashed
            digest = hashlib.sha256()
            with open(path, "rb") as src_handle, open(dest, "wb") as dst_handle:
                while True:
                    block = src_handle.read(CHUNK)
                    if not block:
                        break
                    digest.update(block)
                    dst_handle.write(block)
            source_hash = digest.hexdigest()
            dest_hash = _hash_file(dest) if verify else ""
            try:
                shutil.copystat(str(path), str(dest))     # keep the timestamps
            except OSError:
                pass
            copied_bytes += size
            if verify and dest_hash != source_hash:
                mismatch_rows += 1
                mismatches.append(str(rel))
                entries.append({"path": str(rel), "bytes": size, "sha256": source_hash,
                                "copied_sha256": dest_hash, "status": "MISMATCH"})
            else:
                ok_rows += 1
                entries.append({"path": str(rel), "bytes": size, "sha256": source_hash,
                                "copied_sha256": dest_hash, "status": "OK"})
        except OSError as exc:
            failed_rows += 1
            failures.append(f"{rel}: {exc}")

    manifest = {
        "created": int(started),
        "created_text": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
        "source": planned["source"],
        "target": str(folder),
        "verified": bool(verify),
        "files": entries,
        "count": len(entries),
        "bytes": sum(e["bytes"] for e in entries),
        "skipped": planned["skipped"],
        "errors": failures[:20],
    }
    manifest_path = folder / MANIFEST
    try:
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": f"copied the files but could not write the manifest: "
                                     f"{exc} — treat this backup as unverified.",
                "manifest": "", "folder": str(folder)}

    return {
        "ok": mismatch_rows == 0 and failed_rows == 0,
        "source": planned["source"], "folder": str(folder), "manifest": str(manifest_path),
        "count": len(entries), "ok_rows": ok_rows, "mismatch_rows": mismatch_rows,
        "failed_rows": failed_rows, "mismatches": mismatches[:10],
        "failures": failures[:10], "bytes": manifest["bytes"],
        "skipped": planned["skipped"], "verified": bool(verify),
        "seconds": round(time.time() - started, 1),
        "error": "",
    }


# ---------------------------------------------------------------------- verify
def verify(folder: str) -> dict:
    """Re-hash an existing backup against its own manifest. Read-only."""
    base = Path(os.path.expanduser(folder or ""))
    if not base.exists():
        return {"ok": False, "error": f"no folder at {base}"}
    manifest_path = base / MANIFEST if base.is_dir() else base
    if base.is_file() and base.name == MANIFEST:
        manifest_path = base
        base = base.parent
    if not manifest_path.is_file():
        return {"ok": False,
                "error": f"no {MANIFEST} in {base}. I can only verify a backup that JARVIS "
                         f"made, because the manifest is what the hashes are compared to."}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"the manifest is unreadable: {exc}"}

    checked = good = bad = missing = 0
    problems: list[str] = []
    started = time.time()
    for entry in manifest.get("files", []):
        dest = base / entry["path"]
        checked += 1
        if not dest.is_file():
            missing += 1
            problems.append(f"missing: {entry['path']}")
            continue
        wants = entry.get("copied_sha256") or entry.get("sha256") or ""
        got = _hash_file(dest)
        if wants and got == wants:
            good += 1
        else:
            bad += 1
            problems.append(f"changed since the backup: {entry['path']}")
    return {"ok": bad == 0 and missing == 0, "folder": str(base), "checked": checked,
            "good": good, "bad": bad, "missing": missing, "problems": problems[:10],
            "seconds": round(time.time() - started, 1),
            "created_text": manifest.get("created_text", "?"),
            "source": manifest.get("source", "?"), "error": ""}


# ---------------------------------------------------------------------- report
def report(result: dict) -> str:
    """The spoken/typed answer. Says exactly what happened, and never says 'safe'."""
    if result.get("error"):
        return f"I did not copy anything. {result['error']}"

    if result.get("dry_run"):
        planned = result["plan"]
        return (f"Plan only — nothing was written yet.\n"
                f"  from: {planned['source']}\n"
                f"  to:   {result['folder']}\n"
                f"  {planned['count']} files · {_human(planned['bytes'])} · "
                f"{planned['target_free_gb']} GB free on the target\n"
                f"  skipped {planned['skipped']} (caches, temp files, links)\n"
                f"Say 'back it up for real' and I will do exactly this.")

    lines = [f"Backed up {result['count']} files ({_human(result['bytes'])}) in "
             f"{result['seconds']} s", f"  from: {result['source']}",
             f"  to:   {result['folder']}"]
    if result["verified"]:
        if result["mismatch_rows"]:
            lines.append(f"  ⚠ {result['mismatch_rows']} file(s) DID NOT verify: "
                         + ", ".join(result["mismatches"][:5]))
            lines.append("  Do not trust this copy. The source is untouched — copy again "
                         "to a different drive, and check that disk's health.")
        else:
            lines.append(f"  verified: all {result['ok_rows']} files re-hashed on the "
                         f"destination and matched (SHA-256)")
    else:
        lines.append("  NOT verified (you asked for speed over proof) — the files were "
                     "copied, but nothing checked them")
    if result["failed_rows"]:
        lines.append(f"  {result['failed_rows']} file(s) could not be copied: "
                     + "; ".join(result["failures"][:5]))
    lines.append(f"  skipped {result['skipped']} cache/temp/link file(s)")
    lines.append("  Your originals were opened read-only and not modified. Nothing was "
                 "deleted, moved or renamed.")
    lines.append(f"  Re-check this backup any time: 'verify backup {result['folder']}'")
    return "\n".join(lines)


def verify_report(result: dict) -> str:
    if result.get("error"):
        return f"I could not verify that: {result['error']}"
    head = (f"Checked {result['checked']} files against the manifest written on "
            f"{result['created_text']}.")
    if result["ok"]:
        return (f"{head}\n  all {result['good']} files still match their SHA-256 from the "
                f"day of the backup — this copy is intact.\n"
                f"  (Took {result['seconds']} s. Read-only; nothing was changed.)")
    return (f"{head}\n  ⚠ {result['bad']} changed, {result['missing']} missing: "
            + "; ".join(result["problems"][:6])
            + "\n  The backup of {0} is not a faithful copy any more. The original is "
              "still untouched — make a fresh backup rather than repairing this one."
              .format(result.get("source", "that folder")))


def backups(folder: str = "") -> list[dict]:
    """Every backup JARVIS made in a folder, newest first — so 'which one is good?' has an answer."""
    base = Path(os.path.expanduser(folder or default_target() or "."))
    found = []
    if not base.is_dir():
        return found
    for entry in sorted(base.glob("ArcBackup-*"), key=lambda p: p.name, reverse=True):
        manifest = entry / MANIFEST
        if not manifest.is_file():
            found.append({"path": str(entry), "created": "?", "count": 0, "verified": False})
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        found.append({"path": str(entry), "created": data.get("created_text", "?"),
                      "count": data.get("count", 0), "bytes": data.get("bytes", 0),
                      "verified": data.get("verified", False),
                      "source": data.get("source", "?")})
    return found
