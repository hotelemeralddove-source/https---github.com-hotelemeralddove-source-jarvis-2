"""Find your own files, offline, read-only.

    "where is my invoice"
    "find the pdf about rent"
    "search my files for aadhaar"

Why an index instead of `os.walk` on every question: a home folder with 200 000 files
takes seconds to walk, and seconds feel broken. The index is a single JSON file of
**names, sizes and dates only** — no contents — built once on first use and refreshed
when it is older than `MAX_AGE`, or on demand.

Two rules that keep this safe:

  * **read-only, always** — nothing here writes, moves, renames or deletes anything;
  * **bounded** — a cap on files per scan, a cap on depth, and a skip list for the
    folders that are noise (node_modules, AppData, .git, caches). A search that takes
    ten seconds and returns 4 000 results is worse than no search at all.

Content search exists but is opt-in (`grep=True`), only reads files under 200 KB with
text-ish extensions, and only the first 300 of them.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import config

MAX_FILES = 40_000
MAX_DEPTH = 6
MAX_AGE = 6 * 3600
GREP_MAX_BYTES = 200_000
GREP_MAX_FILES = 300

SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__", ".cache", "AppData",
    "Windows", "$Recycle.Bin", "ProgramData", "site-packages", ".mypy_cache",
    ".pytest_cache", "dist", "build", ".next", "target", "Library",
}

TEXTY = {".txt", ".md", ".py", ".json", ".csv", ".log", ".ini", ".yml", ".yaml",
         ".html", ".js", ".ts", ".bat", ".ps1", ".cfg", ".toml"}

DOC_HINT = {
    "pdf": {".pdf"}, "word": {".doc", ".docx"}, "excel": {".xls", ".xlsx", ".csv"},
    "sheet": {".xls", ".xlsx", ".csv"}, "image": {".png", ".jpg", ".jpeg", ".webp",
                                                  ".bmp", ".gif"},
    "photo": {".png", ".jpg", ".jpeg", ".webp"}, "video": {".mp4", ".mkv", ".mov",
                                                           ".avi", ".webm"},
    "audio": {".mp3", ".wav", ".m4a", ".flac", ".ogg"},
    "code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".rs", ".go"},
    "text": {".txt", ".md"},
}


def _path() -> Path:
    return config.data_dir() / "file_index.json"


def roots() -> list[Path]:
    # ARCDESK_USER_HOME exists so a test (or a portable install) can point the index
    # at a throw-away folder instead of walking the real profile.
    home = Path(os.environ.get("ARCDESK_USER_HOME") or Path.home())
    found = [home]
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Videos"):
        p = home / name
        if p.is_dir():
            found.append(p)
    # keep only what exists and is not the whole filesystem
    return [p for p in found if p.is_dir()][:6]


def _scan() -> list[list]:
    now = time.time()
    rows: list[list] = []
    for root in roots():
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            if len(Path(dirpath).parts) - base_depth >= MAX_DEPTH:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames
                           if d not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                if len(rows) >= MAX_FILES:
                    return rows
                full = os.path.join(dirpath, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                rows.append([full, int(st.st_size), int(st.st_mtime)])
    _ = now
    return rows


def refresh(force: bool = False) -> dict:
    """Build or reuse the index. Never raises; a broken index is just rebuilt."""
    path = _path()
    if not force and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - data.get("built", 0) < MAX_AGE:
                return data
        except Exception:
            pass
    rows = _scan()
    data = {"built": time.time(), "roots": [str(r) for r in roots()], "files": rows}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    except Exception:
        pass
    return data


def _score(name: str, query: str) -> int:
    low_name, low_q = name.lower(), query.lower()
    if low_name == low_q:
        return 100
    if low_name.startswith(low_q):
        return 80
    if low_q in low_name:
        return 60
    # all the query words present in any order
    words = [w for w in low_q.split() if w]
    if words and all(w in low_name for w in words):
        return 45
    # last resort: each word is a prefix of something in the name
    if words and all(any(part.startswith(w) for part in low_name.replace(".", " ").split())
                     for w in words):
        return 30
    return 0


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def find(query: str, kind: str = "", limit: int = 8, grep: bool = False) -> str:
    """Search names (and optionally contents) and return a spoken-friendly list."""
    q = (query or "").strip()
    if not q:
        return "What should I look for?"
    data = refresh()
    files = data.get("files", [])
    wanted_ext = DOC_HINT.get((kind or "").lower().strip(), set())

    hits = []
    for row in files:
        try:
            full, size, mtime = row
        except Exception:
            continue
        name = os.path.basename(full)
        if wanted_ext and os.path.splitext(name)[1].lower() not in wanted_ext:
            continue
        score = _score(name, q)
        if not score:
            # "the arcdesk readme" is a path question, not a filename question
            rel = os.path.relpath(full, str(Path.home()))
            score = int(_score(rel, q) * 0.55)
        if score:
            hits.append((score, mtime, full, size, ""))

    suffix = ""
    if not hits and grep:
        lowered = q.lower()
        checked = 0
        for row in files:
            if checked >= GREP_MAX_FILES:
                break
            full, size, mtime = row
            if size > GREP_MAX_BYTES:
                continue
            if os.path.splitext(full)[1].lower() not in TEXTY:
                continue
            checked += 1
            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                    body = fh.read(GREP_MAX_BYTES)
            except OSError:
                continue
            if lowered in body.lower():
                line = next((ln.strip() for ln in body.splitlines()
                             if lowered in ln.lower()), "")[:80]
                hits.append((25, mtime, full, size, line))
        if checked:
            suffix = f" (looked inside {checked} text files)"

    if not hits:
        shown = len(files)
        return (f"Nothing matching \"{q}\" in {shown} indexed files.{suffix} "
                f"Try a shorter word, or say refresh the file index.")
    hits.sort(key=lambda h: (-h[0], -h[1]))
    lines = [f"Found {len(hits)} match{'es' if len(hits) != 1 else ''} for \"{q}\":{suffix}"]
    for _s, mtime, full, size, line in hits[:limit]:
        when = time.strftime("%d %b", time.localtime(mtime))
        lines.append(f"  · {os.path.basename(full)}  ({_human(size)}, {when})")
        lines.append(f"    {os.path.dirname(full)}")
        if line:
            lines.append(f"    ↳ {line}")
    if len(hits) > limit:
        lines.append(f"  … and {len(hits) - limit} more")
    return "\n".join(lines)


def stats() -> str:
    data = refresh()
    files = data.get("files", [])
    built = time.strftime("%d %b %H:%M", time.localtime(data.get("built", 0)))
    return (f"File index: {len(files)} files from {len(data.get('roots', []))} folders, "
            f"built {built}. Names, sizes and dates only — no contents.")
